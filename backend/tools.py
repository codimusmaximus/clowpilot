"""Tool implementations for the copilot agent.

All tools operate on a sandboxed workspace directory. Paths are normalized and
rejected if they escape the sandbox.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "./workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


# ---------- path helpers ----------

def _safe_path(rel: str) -> Path:
    """Resolve a sandbox-relative path. Refuses traversal."""
    rel = (rel or "").lstrip("/")
    p = (WORKSPACE / rel).resolve()
    if WORKSPACE not in p.parents and p != WORKSPACE:
        raise ValueError(f"path '{rel}' escapes workspace")
    return p


def _ext_kind(path: Path) -> str:
    e = path.suffix.lstrip(".").lower()
    return {
        "md": "markdown", "markdown": "markdown",
        "py": "python", "ts": "typescript", "tsx": "typescript",
        "js": "javascript", "jsx": "javascript",
        "json": "json", "yml": "yaml", "yaml": "yaml",
        "css": "css", "html": "html", "sh": "bash",
        "txt": "text", "csv": "csv", "sql": "sql",
        "go": "go", "rs": "rust",
    }.get(e, "text")


# ---------- tools ----------

def list_tree(path: str = "") -> dict[str, Any]:
    """Walk the sandbox subtree at `path` and return a nested structure."""
    root = _safe_path(path) if path else WORKSPACE

    def walk(p: Path) -> dict[str, Any]:
        node: dict[str, Any] = {
            "name": p.name or "workspace",
            "path": str(p.relative_to(WORKSPACE)) if p != WORKSPACE else "",
        }
        if p.is_dir():
            node["type"] = "dir"
            children = []
            for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name)):
                if child.name.startswith("."):
                    continue
                children.append(walk(child))
            node["children"] = children
        else:
            node["type"] = "file"
            node["kind"] = _ext_kind(p)
            node["size"] = p.stat().st_size
        return node

    return walk(root)


def read_file(path: str) -> dict[str, Any]:
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        return {"error": f"file not found: {path}"}
    content = p.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(p.relative_to(WORKSPACE)),
        "content": content,
        "kind": _ext_kind(p),
        "lines": content.count("\n") + 1,
    }


def write_file(
    path: str,
    content: str,
    type: str | None = None,
) -> dict[str, Any]:
    """Create or update a file. `type` is an optional language/format hint;
    if missing we infer from the extension."""
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(content, encoding="utf-8")
    return {
        "path": str(p.relative_to(WORKSPACE)),
        "kind": type or _ext_kind(p),
        "bytes": len(content.encode("utf-8")),
        "lines": content.count("\n") + 1,
        "action": "updated" if existed else "created",
        "content": content,
    }


def display_file(path: str) -> dict[str, Any]:
    """Open a file as a tab in the right-hand workspace."""
    res = read_file(path)
    if "error" in res:
        return res
    res["display"] = True
    return res


Anchor = Literal["start", "end"]


def highlight(
    path: str,
    start_line: int,
    end_line: int,
    comment: str,
) -> dict[str, Any]:
    """Highlight a line range in the open file viewer with an attached comment."""
    p = _safe_path(path)
    if not p.exists():
        return {"error": f"file not found: {path}"}
    return {
        "path": str(p.relative_to(WORKSPACE)),
        "start_line": int(start_line),
        "end_line": int(end_line),
        "comment": comment,
    }


def snippet(content: str, format: str = "markdown") -> dict[str, Any]:
    """Open an ad-hoc rendered tab in the workspace (markdown or html)."""
    fmt = format.lower()
    if fmt not in ("markdown", "md", "html"):
        return {"error": f"unsupported format: {format}"}
    if fmt == "md":
        fmt = "markdown"
    return {"format": fmt, "content": content}


# ---------- tool registry / Anthropic schema ----------

TOOLS: dict[str, Any] = {
    "list_tree": list_tree,
    "read_file": read_file,
    "write_file": write_file,
    "display_file": display_file,
    "highlight": highlight,
    "snippet": snippet,
}


TOOL_SCHEMAS = [
    {
        "name": "list_tree",
        "description": (
            "List the workspace file tree. Use first to understand what files "
            "exist before reading or modifying them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Subdirectory relative to workspace root. Empty = root.",
                },
            },
        },
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a file in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file in the workspace. Provide the full new "
            "contents. Parent folders are created as needed. `type` is an "
            "optional language hint (python, markdown, json, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "type": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "display_file",
        "description": (
            "Open a file as a tab in the user's workspace pane on the right. "
            "Use this when you want the user to look at a specific file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "highlight",
        "description": (
            "Highlight a line range in a file currently shown in the workspace, "
            "with a comment pinned to that range. The file should already be "
            "displayed (call display_file first if not)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
                "comment": {"type": "string"},
            },
            "required": ["path", "start_line", "end_line", "comment"],
        },
    },
    {
        "name": "snippet",
        "description": (
            "Render an ad-hoc snippet as its own workspace tab. Use for diagrams, "
            "summaries, tables, mini-reports — anything you want to show without "
            "saving to disk. `format` is 'markdown' or 'html'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "format": {"type": "string", "enum": ["markdown", "html"]},
            },
            "required": ["content"],
        },
    },
]


def execute(name: str, args: dict[str, Any]) -> Any:
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:  # noqa: BLE001 — surface to model
        return {"error": f"{type(e).__name__}: {e}"}
