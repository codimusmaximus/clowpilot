"""Pydantic AI streaming agent loop.

Supports OpenAI, Google Gemini, Mistral, DeepSeek, and Anthropic backends.

Model selection (in priority order):
  1. LLM_MODEL env var — explicit override, any provider string
  2. Auto: first Flash/Haiku model available (GOOGLE_API_KEY → Gemini 3 Flash,
     ANTHROPIC_API_KEY → Claude Haiku, DEEPSEEK_API_KEY → DeepSeek Chat,
     OPENAI_API_KEY → GPT)
  Pro/Opus models are listed in the selector but default is Flash/Haiku to
  avoid free-tier quota=0 limits.

Auto-fallback: if the active model hits a quota / rate-limit error before
emitting any events, the agent transparently retries with the next available
provider and emits a brief notice in the chat.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from pydantic_ai import Agent
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
    UserPromptPart,
)

from plugins import registry as plugin_registry
import db


# ---------------------------------------------------------------------------
# Provider catalogue
# ---------------------------------------------------------------------------

# Each entry: id, display name, pydantic-ai model string, env keys (any one suffices).
# Order defines the fallback chain when quota is exhausted.
PROVIDERS: list[dict] = [
    # ── Google — tested working with this key ────────────────────────────────
    {
        "id": "gemini-3.1-pro",
        "name": "Gemini 3.1 Pro",
        "model": "google-gla:gemini-3.1-pro-preview",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    },
    {
        "id": "gemini-3-flash",
        "name": "Gemini 3 Flash",
        "model": "google-gla:gemini-3-flash-preview",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    },
    {
        "id": "gemini-3.1-flash-lite",
        "name": "Gemini 3.1 Flash Lite",
        "model": "google-gla:gemini-3.1-flash-lite",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    },
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "model": "google-gla:gemini-2.5-flash",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    },
    # ── Mistral ──────────────────────────────────────────────────────────────
    {
        "id": "mistral-large",
        "name": "Mistral Large",
        "model": "mistral:mistral-large-latest",
        "env_keys": ["MISTRAL_API_KEY"],
    },
    {
        "id": "magistral-medium",
        "name": "Magistral Medium",
        "model": "mistral:magistral-medium-latest",
        "env_keys": ["MISTRAL_API_KEY"],
    },
    {
        "id": "mistral-medium",
        "name": "Mistral Medium",
        "model": "mistral:mistral-medium-latest",
        "env_keys": ["MISTRAL_API_KEY"],
    },
    {
        "id": "mistral-small",
        "name": "Mistral Small",
        "model": "mistral:mistral-small-latest",
        "env_keys": ["MISTRAL_API_KEY"],
    },
    {
        "id": "codestral",
        "name": "Codestral",
        "model": "mistral:codestral-latest",
        "env_keys": ["MISTRAL_API_KEY"],
    },
    # ── Anthropic ────────────────────────────────────────────────────────────
    {
        "id": "claude-opus-4-8",
        "name": "Claude Opus 4.8",
        "model": "anthropic:claude-opus-4-8",
        "env_keys": ["ANTHROPIC_API_KEY"],
    },
    {
        "id": "claude-opus-4-7",
        "name": "Claude Opus 4.7",
        "model": "anthropic:claude-opus-4-7",
        "env_keys": ["ANTHROPIC_API_KEY"],
    },
    {
        "id": "claude-sonnet-4-6",
        "name": "Claude Sonnet 4.6",
        "model": "anthropic:claude-sonnet-4-6",
        "env_keys": ["ANTHROPIC_API_KEY"],
    },
    {
        "id": "claude-haiku-4-5",
        "name": "Claude Haiku 4.5",
        "model": "anthropic:claude-haiku-4-5-20251001",
        "env_keys": ["ANTHROPIC_API_KEY"],
    },
    # ── DeepSeek ─────────────────────────────────────────────────────────────
    {
        "id": "deepseek-chat",
        "name": "DeepSeek Chat",
        "model": "deepseek:deepseek-chat",
        "env_keys": ["DEEPSEEK_API_KEY"],
    },
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner",
        "model": "deepseek:deepseek-reasoner",
        "env_keys": ["DEEPSEEK_API_KEY"],
    },
    # ── OpenAI ───────────────────────────────────────────────────────────────
    {
        "id": "gpt-5.4",
        "name": "GPT-5.4",
        "model": os.environ.get("OPENAI_MODEL", "openai:gpt-5.4"),
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.4-mini",
        "name": "GPT-5.4 Mini",
        "model": "openai:gpt-5.4-mini",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.4-nano",
        "name": "GPT-5.4 Nano",
        "model": "openai:gpt-5.4-nano",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.3-chat-latest",
        "name": "GPT-5.3 Chat Latest",
        "model": "openai:gpt-5.3-chat-latest",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.2",
        "name": "GPT-5.2",
        "model": "openai:gpt-5.2",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.2-pro",
        "name": "GPT-5.2 Pro",
        "model": "openai:gpt-5.2-pro",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.1",
        "name": "GPT-5.1",
        "model": "openai:gpt-5.1",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5.1-mini",
        "name": "GPT-5.1 Mini",
        "model": "openai:gpt-5.1-mini",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-5-chat-latest",
        "name": "GPT-5 Chat Latest",
        "model": "openai:gpt-5-chat-latest",
        "env_keys": ["OPENAI_API_KEY"],
    },
    {
        "id": "gpt-4.1",
        "name": "GPT-4.1",
        "model": "openai:gpt-4.1",
        "env_keys": ["OPENAI_API_KEY"],
    },
]


def list_available_models() -> list[dict[str, str]]:
    """Return models whose provider key is present in the environment."""
    seen: set[str] = set()
    available: list[dict[str, str]] = []
    for p in PROVIDERS:
        if any(os.environ.get(k) for k in p["env_keys"]) and p["model"] not in seen:
            seen.add(p["model"])
            available.append({"id": p["id"], "name": p["name"], "model": p["model"]})
    return available


def _resolve_initial_model() -> str:
    explicit = os.environ.get("LLM_MODEL")
    if explicit:
        return explicit
    available = list_available_models()
    # Prefer a cheap/fast default (Flash/Haiku) — Pro/Opus may hit quota=0
    for m in available:
        if "flash" in m["model"] or "haiku" in m["model"]:
            return m["model"]
    return available[0]["model"] if available else "openai:gpt-5.4"


# Module-level active model — mutated by set_active_model() on auto-fallback
# or by the /api/models/active endpoint.
_active_model: str = _resolve_initial_model()


def get_active_model() -> str:
    return _active_model


def set_active_model(model: str) -> None:
    global _active_model
    _active_model = model


def _model_display_name(model: str) -> str:
    """Return a short human-readable name for a model string."""
    for m in list_available_models():
        if m["model"] == model:
            return m["name"]
    # Fallback: strip the provider prefix
    return model.split(":", 1)[-1] if ":" in model else model


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are a workspace copilot embedded in a UI with three panes:
a left sidebar (file tree + threads), a centre chat (this conversation), and a
right workspace pane (where files and snippets are displayed to the user).

Use enabled plugin tools to inspect, create, modify, and project artefacts onto
the right-hand workspace. Plugin instructions below describe the capabilities
available in this runtime.

Working principles:
- Prefer tool use over explanation when the user asks you to inspect or change
  workspace state.
- Keep chat replies brief and grounded in the artefacts you show.
- The workspace is where you show; chat is where you narrate.

Attachments:
- User messages may include uploaded attachments.
- Small text-like attachments may be inlined into the user prompt automatically.
- Larger documents are indexed into semantic search chunks and should be explored
    with the search tool before making claims about their contents.
- Image attachments may be stored as files and accompanied by derived text
    descriptions for search, but you should still inspect referenced artefacts and
    search results before relying on them.

Images — only two valid forms:
1. Workspace file:  ![description](relative/path.png)
    Use a workspace-root-relative path exactly as it appears in the workspace tree
    (e.g. report/transactions_plot.png, outputs/chart.png).
    Do not use a path relative to the current markdown file unless it is also
    workspace-root-relative.
   Never use a full URL, never use an <img> tag, never add /api/... prefixes.
   Also call display_image(path) so the image opens as a tab in the workspace panel.
2. External URL:    ![description](https://example.com/image.png)
   Only for images that already exist on the internet.

Snippets:
- Use snippet(format="markdown") for text, tables, prose, and static images.
- In markdown snippets, image and file links must use workspace-root-relative
    paths, not paths relative to the snippet or current document.
- Use snippet(format="html") for anything that requires JavaScript — charts,
  interactive widgets, animations. The HTML runs inside an iframe where scripts
  execute normally. Never put <script> tags in a markdown snippet.
"""


def compose_system_prompt(
    base_prompt: str | None = None,
    conversation_id: str | None = None,
) -> str:
    """Public-facing accessor for the same composition used at chat-time.

    Mirrors the call from _stream_model so the UI can show the exact prompt
    the model will see for the given conversation.
    """
    return _compose_system_prompt(
        base_prompt=base_prompt or BASE_SYSTEM_PROMPT,
        conversation_id=conversation_id,
    )


def _compose_system_prompt(
    base_prompt: str = BASE_SYSTEM_PROMPT,
    conversation_id: str | None = None,
) -> str:
    parts: list[str] = [base_prompt]

    knowledge_block = _project_knowledge_block(conversation_id)
    if knowledge_block:
        parts.append(knowledge_block)

    plugin_instructions = plugin_registry.instructions(conversation_id)
    if plugin_instructions:
        parts.append(f"Enabled plugins:\n\n{plugin_instructions}")

    return "\n\n".join(parts)


def _project_knowledge_block(conversation_id: str | None) -> str:
    if not conversation_id:
        return ""
    convo = db.get_conversation(conversation_id)
    project_id = convo.get("projectId") if convo else None
    if not project_id:
        return ""
    expanded = db.expand_project_knowledge(project_id)
    links = db.list_project_knowledge(project_id)
    if not links and not expanded["included"]:
        return ""

    # Per-link summary: count how many of each pinned folder/page made it in.
    included_by_folder: dict[str, list[dict[str, Any]]] = {}
    truncated_by_folder: dict[str, list[dict[str, Any]]] = {}
    for item in expanded["included"]:
        key = item.get("from_folder")
        if key:
            included_by_folder.setdefault(key, []).append(item)
    for item in expanded["truncated"]:
        key = item.get("from_folder")
        if key:
            truncated_by_folder.setdefault(key, []).append(item)
    included_pages = {i["ref_path"]: i for i in expanded["included"] if not i.get("from_folder")}
    truncated_pages = {t["ref_path"]: t for t in expanded["truncated"] if not t.get("from_folder")}

    mode = expanded.get("mode", "full")
    preview_tokens = expanded.get("preview_tokens", 500)

    parts: list[str] = ["## Project knowledge"]
    if mode == "metadata":
        parts.append(
            f"This project has {len(links)} pinned item{'s' if len(links) != 1 else ''}. "
            "**Metadata-only mode** — no contents are inlined. The inventory below "
            "lists paths and sizes; use `page_read` / `page_search` to read anything "
            "before relying on it."
        )
    elif mode == "preview":
        parts.append(
            f"This project has {len(links)} pinned item{'s' if len(links) != 1 else ''}. "
            f"**Preview mode** — the first ~{preview_tokens:,} tokens of each pinned page "
            f"are inlined below (~{expanded['total_tokens']:,} tokens total, "
            f"cap: {expanded['max_tokens']:,}). "
            "If a preview is clipped, use `page_read` to fetch the full page."
        )
    else:  # full
        parts.append(
            f"This project has {len(links)} pinned item{'s' if len(links) != 1 else ''}. "
            f"~{expanded['total_tokens']:,} tokens of content are inlined below "
            f"(cap: {expanded['max_tokens']:,}). "
            "Treat the inlined contents as authoritative background. "
            "Anything listed in Inventory but missing from Contents is too large — "
            "fetch it with `page_read` / `page_search` on demand."
        )

    parts.append("\n### Inventory")
    for link in links:
        rp = link["ref_path"]
        if link["ref_type"] == "page":
            if rp in included_pages:
                t = included_pages[rp]["tokens"]
                parts.append(f"- page `{rp}` — {t:,} tok, inlined")
            elif rp in truncated_pages:
                parts.append(
                    f"- page `{rp}` — {truncated_pages[rp]['reason']}"
                )
            else:
                parts.append(f"- page `{rp}`")
        else:  # page_folder
            inc = included_by_folder.get(rp, [])
            trc = truncated_by_folder.get(rp, [])
            total = len(inc) + len(trc)
            inc_tok = sum(i["tokens"] for i in inc)
            if total == 0:
                parts.append(f"- folder `{rp}/` — no pages found")
            elif not trc:
                parts.append(
                    f"- folder `{rp}/` — {len(inc)} page"
                    f"{'s' if len(inc) != 1 else ''}, {inc_tok:,} tok, all inlined"
                )
            else:
                if mode == "metadata":
                    parts.append(
                        f"- folder `{rp}/` — {total} page"
                        f"{'s' if total != 1 else ''} (metadata-only; use page_read)"
                    )
                else:
                    parts.append(
                        f"- folder `{rp}/` — {len(inc)} of {total} pages inlined "
                        f"({inc_tok:,} tok); {len(trc)} omitted (token cap, fetch with page_read)"
                    )

    if expanded["truncated"]:
        parts.append("\n_Not inlined (omitted from Contents below):_")
        for t in expanded["truncated"]:
            via = f" (from `{t['from_folder']}/`)" if t.get("from_folder") else ""
            parts.append(
                f"- `{t['ref_path']}` — {t['reason']}, ~{t['tokens']:,} tok{via}"
            )

    if expanded["included"]:
        parts.append("\n### Contents\n")
        for item in expanded["included"]:
            tag = " _(preview)_" if item.get("preview_clipped") else ""
            parts.append(f"\n#### {item['ref_path']}{tag}\n")
            parts.append(item["content"].rstrip())

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

def _build_agent(conversation_id: str | None = None, model: str | None = None) -> Agent:
    model_str = model or _active_model
    runtime_agent = Agent(
        model_str,
        toolsets=plugin_registry.mcp_toolsets(conversation_id),
    )

    def wrap_handler(handler):
        @functools.wraps(handler)
        async def safe_handler(*args, **kwargs):
            try:
                result = handler(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception as e:
                return f"Tool call failed: {type(e).__name__}: {e}"
        return safe_handler

    for tool in plugin_registry.tools(conversation_id):
        runtime_agent.tool_plain(wrap_handler(tool.handler), name=tool.name)
    return runtime_agent


# ---------------------------------------------------------------------------
# Quota / rate-limit detection
# ---------------------------------------------------------------------------

_QUOTA_KEYWORDS = (
    "quota", "rate limit", "rate_limit", "429",
    "insufficient", "token limit", "context window",
    "exceeded", "capacity", "overloaded",
)


def _is_retryable_error(exc: Exception) -> bool:
    """Return True if the error should trigger an auto-fallback to the next model."""
    if isinstance(exc, ContentFilterError):
        return True
    msg = str(exc).lower()
    return any(kw in msg for kw in _QUOTA_KEYWORDS)


# ---------------------------------------------------------------------------
# Tool-call previews — a small/fast LLM narrates each tool call
# ---------------------------------------------------------------------------

# How long to wait for a tool to finish before narrating from arguments alone.
# If the tool completes within this window we narrate from args + result;
# otherwise we narrate from the arguments at this mark so a preview shows fast.
PREVIEW_RESULT_WINDOW = 0.3  # seconds

_PREVIEW_SYSTEM = (
    "You narrate a single agent tool call for a non-technical user. "
    "Reply with ONE short past-tense clause, at most ~10 words — what the call "
    "did or is doing. No quotes, no markdown, no trailing period, no preamble. "
    "If a result is given, describe the outcome; otherwise describe the intent. "
    "Examples: 'searched the web for Q3 revenue', "
    "'read report/summary.md', 'sent an email to the finance team'."
)

# Cache one lightweight Agent per preview model.
_preview_agents: dict[str, Agent] = {}


def _preview_model() -> str | None:
    """Pick a small/fast model for narrating tool calls, or None if unavailable."""
    explicit = os.environ.get("TOOL_PREVIEW_MODEL")
    if explicit:
        return explicit
    available = list_available_models()
    if not available:
        return None
    # Prefer Claude Haiku when Anthropic is configured.
    if os.environ.get("ANTHROPIC_API_KEY"):
        for m in available:
            if "haiku" in m["model"]:
                return m["model"]
    # Otherwise the smallest/cheapest available tier.
    for kw in ("haiku", "flash-lite", "flash", "mini", "nano", "small"):
        for m in available:
            if kw in m["model"]:
                return m["model"]
    return available[0]["model"]


def _get_preview_agent(model: str) -> Agent:
    agent = _preview_agents.get(model)
    if agent is None:
        agent = Agent(model, system_prompt=_PREVIEW_SYSTEM)
        _preview_agents[model] = agent
    return agent


async def _summarize_tool_call(
    model: str | None,
    name: str,
    args: Any,
    result: Any = None,
) -> str:
    """One-line natural-language description of a tool call. '' on any failure."""
    if not model:
        return ""
    try:
        payload: dict[str, Any] = {"tool": name, "arguments": args}
        if result is not None:
            payload["result"] = result
        prompt = json.dumps(payload, default=str)[:1500]
        run = await _get_preview_agent(model).run(prompt)
        return (run.output or "").strip().strip('"').rstrip(".")[:140]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Main run loop with auto-fallback
# ---------------------------------------------------------------------------

async def _stream_model(
    model_str: str,
    prompt: str,
    history: list[ModelMessage],
    conversation_id: str | None,
    system_prompt: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield processed SSE event dicts for one model run.

    Tool calls are narrated by a small LLM (see `_summarize_tool_call`). Because
    narration is async and timing-dependent, the main stream and the concurrent
    preview tasks both feed an `asyncio.Queue` that this generator drains.
    """
    preview_model = _preview_model()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    sentinel = object()

    tool_meta: dict[str, dict[str, Any]] = {}  # id -> {name, args, start}
    resulted: set[str] = set()
    previewed: set[str] = set()
    bg: set[asyncio.Task] = set()

    def track(coro) -> None:
        t = asyncio.create_task(coro)
        bg.add(t)
        t.add_done_callback(bg.discard)

    async def gen_preview(tool_id: str, name: str, args: Any, result: Any) -> None:
        if tool_id in previewed:
            return
        previewed.add(tool_id)
        text = await _summarize_tool_call(preview_model, name, args, result)
        if text:
            stage = "result" if result is not None else "args"
            await queue.put({"type": "tool-preview", "id": tool_id, "stage": stage, "text": text})

    async def preview_timer(tool_id: str, name: str, args: Any) -> None:
        # Tool is still running after the window — narrate from arguments alone.
        try:
            await asyncio.sleep(PREVIEW_RESULT_WINDOW)
        except asyncio.CancelledError:
            return
        if tool_id not in resulted:
            await gen_preview(tool_id, name, args, None)

    async def producer() -> None:
        tool_calls: dict[int, dict[str, str]] = {}
        try:
            runtime_agent = _build_agent(conversation_id, model_str)
            # Entering the agent context opens connections to any attached MCP
            # servers (a cheap no-op when there are none).
            async with runtime_agent:
                async for event in runtime_agent.run_stream_events(
                    prompt,
                    message_history=history,
                    instructions=_compose_system_prompt(
                        base_prompt=system_prompt or BASE_SYSTEM_PROMPT,
                        conversation_id=conversation_id,
                    ),
                ):
                    if isinstance(event, PartStartEvent):
                        part = event.part
                        if isinstance(part, TextPart):
                            if part.content:
                                await queue.put({"type": "text-delta", "delta": part.content})
                        elif isinstance(part, ToolCallPart):
                            tool_calls[event.index] = {"id": part.tool_call_id, "name": part.tool_name}
                            await queue.put({"type": "tool-call-start", "id": part.tool_call_id, "name": part.tool_name})
                            if part.args:
                                delta = part.args if isinstance(part.args, str) else json.dumps(part.args)
                                await queue.put({"type": "tool-call-input-delta", "id": part.tool_call_id, "delta": delta})

                    elif isinstance(event, PartDeltaEvent):
                        delta = event.delta
                        if isinstance(delta, TextPartDelta):
                            await queue.put({"type": "text-delta", "delta": delta.content_delta})
                        elif isinstance(delta, ToolCallPartDelta):
                            tc = tool_calls.get(event.index)
                            if tc and delta.args_delta is not None:
                                chunk = (
                                    delta.args_delta
                                    if isinstance(delta.args_delta, str)
                                    else json.dumps(delta.args_delta)
                                )
                                await queue.put({"type": "tool-call-input-delta", "id": tc["id"], "delta": chunk})

                    elif isinstance(event, FunctionToolCallEvent):
                        part = event.part
                        args = part.args
                        if isinstance(args, str):
                            try:
                                args = json.loads(args) if args else {}
                            except json.JSONDecodeError:
                                args = {}
                        args = args or {}
                        await queue.put({"type": "tool-call-input", "id": part.tool_call_id, "name": part.tool_name, "input": args})
                        if preview_model:
                            tool_meta[part.tool_call_id] = {
                                "name": part.tool_name,
                                "args": args,
                                "start": asyncio.get_running_loop().time(),
                            }
                            track(preview_timer(part.tool_call_id, part.tool_name, args))

                    elif isinstance(event, FunctionToolResultEvent):
                        result = event.result
                        if isinstance(result, ToolReturnPart):
                            await queue.put({"type": "tool-result", "id": result.tool_call_id, "name": result.tool_name, "result": result.content})
                            resulted.add(result.tool_call_id)
                            meta = tool_meta.get(result.tool_call_id)
                            if meta and preview_model:
                                elapsed = asyncio.get_running_loop().time() - meta["start"]
                                # Fast tool: narrate from arguments AND result.
                                # (Slow tools were already narrated from args by the timer.)
                                if elapsed < PREVIEW_RESULT_WINDOW:
                                    track(gen_preview(result.tool_call_id, meta["name"], meta["args"], result.content))

            # Flush any in-flight preview tasks before signalling completion.
            if bg:
                await asyncio.gather(*list(bg), return_exceptions=True)
        finally:
            await queue.put(sentinel)

    prod = asyncio.create_task(producer())
    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
        await prod  # surface any exception (e.g. quota) for run()'s fallback
    finally:
        if not prod.done():
            prod.cancel()
        for t in list(bg):
            if not t.done():
                t.cancel()


async def run(
    prompt: str,
    history: list[ModelMessage],
    conversation_id: str | None = None,
    system_prompt: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the agent and yield SSE event dicts.

    On quota/rate-limit errors, automatically falls back through the chain of
    available models (in PROVIDERS order) and emits a notice in the chat stream.
    """
    available = list_available_models()
    active = _active_model

    # Build fallback chain: active model first, then remaining available models
    model_chain = [active] + [m["model"] for m in available if m["model"] != active]

    last_exc: Exception | None = None

    for idx, model_str in enumerate(model_chain):
        events_sent = 0
        try:
            async for event in _stream_model(model_str, prompt, history, conversation_id, system_prompt):
                events_sent += 1
                yield event
            yield {"type": "done"}
            return

        except Exception as exc:
            last_exc = exc
            is_last = idx == len(model_chain) - 1

            if events_sent == 0 and _is_retryable_error(exc) and not is_last:
                next_model = model_chain[idx + 1]
                set_active_model(next_model)
                notice = (
                    f"_(Quota limit on **{_model_display_name(model_str)}** — "
                    f"switched to **{_model_display_name(next_model)}**)_\n\n"
                )
                yield {"type": "text-delta", "delta": notice}
                yield {"type": "model-switch", "from": model_str, "to": next_model}
                continue

            # Non-quota error or no fallbacks left — propagate
            raise

    if last_exc:
        raise last_exc


# ---------------------------------------------------------------------------
# Frontend → ModelMessage conversion
# ---------------------------------------------------------------------------

def split_messages(
    msgs: list[dict[str, Any]],
) -> tuple[str, list[ModelMessage]]:
    """Split the frontend's message list into (current_prompt, history)."""
    if not msgs:
        return "", []

    last = msgs[-1]
    prompt = ""
    if last.get("role") == "user":
        c = last.get("content")
        if isinstance(c, str):
            prompt = c
        elif isinstance(c, list):
            prompt = "".join(p.get("text", "") for p in c if p.get("type") == "text")

        prompt = _augment_prompt_with_attachments(prompt, last.get("attachments"))

    history: list[ModelMessage] = []
    for m in msgs[:-1]:
        role = m.get("role")
        content = m.get("content")
        attachments = m.get("attachments")

        if role == "user":
            text = content if isinstance(content, str) else "".join(
                p.get("text", "") for p in (content or []) if p.get("type") == "text"
            )
            text = _augment_prompt_with_attachments(text, attachments)
            if text:
                history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
            continue

        if role == "assistant" and isinstance(content, list):
            response_parts: list[Any] = []
            tool_returns: list[ToolReturnPart] = []
            for p in content:
                ptype = p.get("type")
                if ptype == "text" and p.get("text"):
                    response_parts.append(TextPart(content=p["text"]))
                elif ptype == "tool-call" and p.get("id") and p.get("name"):
                    response_parts.append(
                        ToolCallPart(
                            tool_name=p["name"],
                            args=p.get("input") or {},
                            tool_call_id=p["id"],
                        )
                    )
                    result = p.get("result")
                    if result is None:
                        result = f"Tool call failed: '{p['name']}' was interrupted or returned no result."
                    tool_returns.append(
                        ToolReturnPart(
                            tool_name=p["name"],
                            content=result,
                            tool_call_id=p["id"],
                        )
                    )
            if response_parts:
                history.append(ModelResponse(parts=response_parts))
            if tool_returns:
                history.append(ModelRequest(parts=list(tool_returns)))

    return prompt, history


def _augment_prompt_with_attachments(
    text: str,
    attachments: Any,
    inline_char_limit: int = 40_000,
) -> str:
    if not isinstance(attachments, list) or not attachments:
        return text

    extras: list[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        name = str(attachment.get("name") or "attachment")
        path = str(attachment.get("path") or "")
        content_type = str(attachment.get("contentType") or "application/octet-stream")
        content = attachment.get("content")

        inline_text = ""
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    inline_text += str(part.get("text", ""))

                if part.get("type") == "file" and part.get("data") and not inline_text:
                    stored_path = str(part.get("data"))
                    chunks = db.get_chunks_for_path(stored_path)
                    if chunks:
                        inline_text = "\n\n".join(chunk["content"] for chunk in chunks)

        if inline_text and len(inline_text) <= inline_char_limit:
            extras.append(
                f"[Attachment: {name}]\n"
                f"Path: {path or '(unspecified)'}\n"
                f"Content-Type: {content_type}\n"
                f"Inline text:\n{inline_text.strip()}"
            )
            continue

        extras.append(
            f"[Attachment: {name}]\n"
            f"Path: {path or '(unspecified)'}\n"
            f"Content-Type: {content_type}\n"
            "Note: This attachment is not inlined. Use semantic search or workspace tools to inspect it."
        )

    if not extras:
        return text
    attachment_block = "\n\n".join(extras)
    if text.strip():
        return f"{text}\n\nAttached context:\n{attachment_block}"
    return f"Attached context:\n{attachment_block}"
