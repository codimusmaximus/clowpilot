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

import tools


MODEL = os.environ.get("OPENAI_MODEL", "openai:gpt-5.2")

SYSTEM_PROMPT = """You are a workspace copilot embedded in a UI with three panes:
a left sidebar (file tree + threads), a centre chat (this conversation), and a
right workspace pane (where files and snippets are displayed to the user).

You operate inside a sandboxed virtual file workspace backed by SQLite. Files and
their contents are stored in the SQLite database, and folders are derived from
the stored file paths; the local `workspace/` directory is not the source of
truth. Use the tools to inspect, create, and modify these database-backed files,
and to project visual artefacts onto the right-hand workspace.

Working principles:
- When the user references files, call `list_tree` to orient yourself before
  acting, unless you already know the layout from earlier in the conversation.
- Use `create_folder` when the user asks for empty folders or subfolder
  structure before files exist. Writing files still creates parent folders.
- When you want the user to *look* at a file, call `display_file` so it opens
  in their workspace pane. Don't dump file contents into chat.
- Use `replace_in_file` or `replace_file_lines` for small targeted edits. Use
  `write_file` when creating a file or intentionally replacing the full content.
- Use `delete_file` when the user asks you to remove a file or virtual folder.
  The tool returns the deleted path or paths after the operation.
- File CRUD tools return structured results after they run. Create/update/patch
  results include the stored file content and metadata; delete results include
  the removed path or paths.
- Use `highlight` to draw the user's attention to specific line ranges with a
  comment — this is your primary teaching tool when explaining code or data.
- Use `snippet` for ad-hoc artefacts: summaries, tables, diagrams (markdown),
  or rendered HTML you want the user to see without writing to disk.
- Keep chat replies brief. The workspace is where you show; chat is where you
  narrate.
"""


agent = Agent(MODEL)


@agent.tool_plain
def list_tree(path: str = "") -> dict[str, Any]:
    """List the workspace file tree. Use first to understand what files exist
    before reading or modifying them. `path` is a subdirectory relative to
    the workspace root; empty means root."""
    return tools.list_tree(path)


@agent.tool_plain
def create_folder(path: str) -> dict[str, Any]:
    """Create an empty virtual subfolder in the SQLite-backed workspace."""
    return tools.create_folder(path)


@agent.tool_plain
def read_file(path: str) -> dict[str, Any]:
    """Read the full contents of a file in the workspace."""
    return tools.read_file(path)


@agent.tool_plain
def write_file(path: str, content: str, type: str | None = None) -> dict[str, Any]:
    """Create or overwrite a file in the workspace. Provide the full new
    contents. Parent folders are created as needed. `type` is an optional
    language hint (python, markdown, json, etc.)."""
    return tools.write_file(path, content, type)


@agent.tool_plain
def replace_in_file(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Patch a file by replacing one exact unique text fragment. Use for small
    targeted edits when you know the old text exactly."""
    return tools.replace_in_file(path, old_text, new_text)


@agent.tool_plain
def replace_file_lines(
    path: str,
    start_line: int,
    end_line: int,
    content: str,
) -> dict[str, Any]:
    """Patch a file by replacing an inclusive 1-based line range. Use when
    exact text replacement is ambiguous or line numbers are known."""
    return tools.replace_file_lines(path, start_line, end_line, content)


@agent.tool_plain
def delete_file(path: str) -> dict[str, Any]:
    """Delete a file or virtual folder from the SQLite-backed workspace. Returns
    the deleted path or paths after the operation."""
    return tools.delete_file(path)


@agent.tool_plain
def display_file(path: str) -> dict[str, Any]:
    """Open a file as a tab in the user's workspace pane on the right.
    Use this when you want the user to look at a specific file."""
    return tools.display_file(path)


@agent.tool_plain
def highlight(
    path: str,
    start_line: int,
    end_line: int,
    comment: str,
) -> dict[str, Any]:
    """Highlight a line range in a file currently shown in the workspace,
    with a comment pinned to that range. The file should already be displayed
    (call display_file first if not)."""
    return tools.highlight(path, start_line, end_line, comment)


@agent.tool_plain
def snippet(content: str, format: str = "markdown") -> dict[str, Any]:
    """Render an ad-hoc snippet as its own workspace tab. Use for diagrams,
    summaries, tables, mini-reports — anything you want to show without
    saving to disk. `format` is 'markdown' or 'html'."""
    return tools.snippet(content, format)


# ---------- protocol ----------


async def run(
    prompt: str,
    history: list[ModelMessage],
    system_prompt: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the agent and yield SSE event dicts mirroring the previous protocol."""

    # index → {"id", "name"} so we can attach deltas to the right tool call
    tool_calls: dict[int, dict[str, str]] = {}

    async for event in agent.run_stream_events(
        prompt,
        message_history=history,
        instructions=system_prompt or SYSTEM_PROMPT,
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
                    if p.get("result") is not None:
                        tool_returns.append(
                            ToolReturnPart(
                                tool_name=p["name"],
                                content=p["result"],
                                tool_call_id=p["id"],
                            )
                        )
            if response_parts:
                history.append(ModelResponse(parts=response_parts))
            if tool_returns:
                history.append(ModelRequest(parts=list(tool_returns)))

    return prompt, history
