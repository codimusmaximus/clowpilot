"""Pydantic AI streaming agent loop (OpenAI backend).

Streams a custom JSON event protocol over SSE that the frontend converts
into assistant-ui messages. The protocol is unchanged from the previous
Anthropic implementation so the frontend doesn't need any updates.
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from pydantic_ai import Agent
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


MODEL = os.environ.get("OPENAI_MODEL", "openai:gpt-5.2")

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
"""


def _compose_system_prompt(
    conversation_id: str | None = None,
    base_prompt: str = BASE_SYSTEM_PROMPT,
) -> str:
    plugin_instructions = plugin_registry.instructions(conversation_id)
    if not plugin_instructions:
        return base_prompt
    return f"{base_prompt}\n\nEnabled plugins:\n\n{plugin_instructions}"


def _build_agent(conversation_id: str | None = None) -> Agent:
    runtime_agent = Agent(MODEL)

    def wrap_handler(handler):
        def safe_handler(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
            except Exception as e:
                return f"Tool call failed: {type(e).__name__}: {e}"

        return safe_handler

    for tool in plugin_registry.tools(conversation_id):
        runtime_agent.tool_plain(wrap_handler(tool.handler), name=tool.name)
    return runtime_agent


# ---------- protocol ----------


async def run(
    prompt: str,
    history: list[ModelMessage],
    conversation_id: str | None = None,
    system_prompt: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the agent and yield SSE event dicts mirroring the previous protocol."""

    # index → {"id", "name"} so we can attach deltas to the right tool call
    tool_calls: dict[int, dict[str, str]] = {}

    runtime_agent = _build_agent(conversation_id)

    async for event in runtime_agent.run_stream_events(
        prompt,
        message_history=history,
        instructions=_compose_system_prompt(
            conversation_id, system_prompt or BASE_SYSTEM_PROMPT
        ),
    ):
        if isinstance(event, PartStartEvent):
            part = event.part
            if isinstance(part, TextPart):
                if part.content:
                    yield {"type": "text-delta", "delta": part.content}
            elif isinstance(part, ToolCallPart):
                tool_calls[event.index] = {
                    "id": part.tool_call_id,
                    "name": part.tool_name,
                }
                yield {
                    "type": "tool-call-start",
                    "id": part.tool_call_id,
                    "name": part.tool_name,
                }
                # initial args (if any) arrive on the part itself
                if part.args:
                    delta = part.args if isinstance(part.args, str) else json.dumps(part.args)
                    yield {
                        "type": "tool-call-input-delta",
                        "id": part.tool_call_id,
                        "delta": delta,
                    }

        elif isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, TextPartDelta):
                yield {"type": "text-delta", "delta": delta.content_delta}
            elif isinstance(delta, ToolCallPartDelta):
                tc = tool_calls.get(event.index)
                if tc is None:
                    continue
                if delta.args_delta is not None:
                    chunk = (
                        delta.args_delta
                        if isinstance(delta.args_delta, str)
                        else json.dumps(delta.args_delta)
                    )
                    yield {
                        "type": "tool-call-input-delta",
                        "id": tc["id"],
                        "delta": chunk,
                    }

        elif isinstance(event, FunctionToolCallEvent):
            part = event.part
            args = part.args
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError:
                    args = {}
            yield {
                "type": "tool-call-input",
                "id": part.tool_call_id,
                "name": part.tool_name,
                "input": args or {},
            }

        elif isinstance(event, FunctionToolResultEvent):
            result = event.result
            if isinstance(result, ToolReturnPart):
                yield {
                    "type": "tool-result",
                    "id": result.tool_call_id,
                    "name": result.tool_name,
                    "result": result.content,
                }

    yield {"type": "done"}


# ---------- frontend → ModelMessage conversion ----------


def split_messages(
    msgs: list[dict[str, Any]],
) -> tuple[str, list[ModelMessage]]:
    """Split the frontend's message list into (current_prompt, history).

    Frontend format per message:
      {"role": "user", "content": "string"}     or
      {"role": "user"|"assistant", "content": [parts...]}

    Where parts are:
      {"type": "text", "text": "..."}
      {"type": "tool-call", "id", "name", "input", "result"}
    """
    if not msgs:
        return "", []

    # last message must be the user's new prompt
    last = msgs[-1]
    prompt = ""
    if last.get("role") == "user":
        c = last.get("content")
        if isinstance(c, str):
            prompt = c
        elif isinstance(c, list):
            prompt = "".join(
                p.get("text", "") for p in c if p.get("type") == "text"
            )

    history: list[ModelMessage] = []
    for m in msgs[:-1]:
        role = m.get("role")
        content = m.get("content")

        if role == "user":
            text = content if isinstance(content, str) else "".join(
                p.get("text", "") for p in (content or []) if p.get("type") == "text"
            )
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
                    
                    # If the tool call has a result, use it.
                    # Otherwise, synthesize a failure message so the LLM knows it didn't succeed.
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
