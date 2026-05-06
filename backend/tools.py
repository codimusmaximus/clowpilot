"""Tool implementations for the copilot agent.

All tools operate on a sandboxed workspace directory. Paths are normalized and
rejected if they escape the sandbox.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import db


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
    """Return a nested file tree from the SQLite-backed workspace."""
    _safe_path(path) if path else WORKSPACE
    rel = path.strip("/")
    files = db.list_files()
    folders = db.list_folders()
    exact = next((f for f in files if f["path"] == rel), None)
    if exact:
        return {
            "name": Path(rel).name,
            "path": rel,
            "type": "file",
            "kind": exact["kind"],
            "size": exact["bytes"],
        }

    root: dict[str, Any] = {
        "name": Path(rel).name if rel else "workspace",
        "path": rel,
        "type": "dir",
        "children": [],
    }
    dirs: dict[str, dict[str, Any]] = {rel: root}
    prefix = f"{rel}/" if rel else ""

    def ensure_dir(path: str) -> dict[str, Any]:
        if path in dirs:
            return dirs[path]
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        parent = ensure_dir(parent_path) if parent_path else root
        node = {
            "name": Path(path).name,
            "path": path,
            "type": "dir",
            "children": [],
        }
        dirs[path] = node
        parent["children"].append(node)
        return node

    for folder in folders:
        folder_path = str(folder)
        if folder_path == rel or (rel and not folder_path.startswith(prefix)):
            continue
        ensure_dir(folder_path)

    for file in files:
        file_path = str(file["path"])
        if rel and not file_path.startswith(prefix):
            continue
        parts = file_path.split("/")
        parent_path = "/".join(parts[:-1])
        parent = ensure_dir(parent_path) if parent_path else root
        if rel and parent_path == rel:
            parent = root
        parent["children"].append(
            {
                "name": parts[-1],
                "path": file_path,
                "type": "file",
                "kind": file["kind"],
                "size": file["bytes"],
            }
        )

    def sort_children(node: dict[str, Any]) -> None:
        children = node.get("children", [])
        children.sort(key=lambda x: (x["type"] == "file", x["name"].lower()))
        for child in children:
            if child["type"] == "dir":
                sort_children(child)

    sort_children(root)
    return root


def create_folder(path: str) -> dict[str, Any]:
    """Create an empty virtual folder in the SQLite-backed workspace."""
    rel = str(_safe_path(path).relative_to(WORKSPACE))
    if rel == ".":
        rel = ""
    if not rel:
        return {"error": "path must name a subfolder"}
    if db.file_exists(rel):
        return {"error": f"file already exists at: {path}", "path": rel}
    return db.create_folder(rel)


def read_file(path: str) -> dict[str, Any]:
    rel = str(_safe_path(path).relative_to(WORKSPACE))
    file = db.get_file(rel)
    if file is None:
        return {"error": f"file not found: {path}"}
    return file


def write_file(
    path: str,
    content: str,
    type: str | None = None,
) -> dict[str, Any]:
    """Create or update a file. `type` is an optional language/format hint;
    if missing we infer from the extension."""
    p = _safe_path(path)
    return db.upsert_file(str(p.relative_to(WORKSPACE)), content, type or _ext_kind(p))


def replace_in_file(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Replace one exact text fragment inside a file."""
    current = read_file(path)
    if "error" in current:
        return current
    if old_text == "":
        return {"error": "old_text cannot be empty"}
    content = str(current["content"])
    count = content.count(old_text)
    if count == 0:
        return {"error": "old_text not found", "path": current["path"]}
    if count > 1:
        return {
            "error": "old_text is not unique; use replace_file_lines instead",
            "path": current["path"],
            "matches": count,
        }
    updated = content.replace(old_text, new_text, 1)
    result = db.upsert_file(str(current["path"]), updated, str(current["kind"]))
    result["action"] = "patched"
    return result


def replace_file_lines(
    path: str,
    start_line: int,
    end_line: int,
    content: str,
) -> dict[str, Any]:
    """Replace an inclusive 1-based line range inside a file."""
    current = read_file(path)
    if "error" in current:
        return current
    if start_line < 1 or end_line < start_line:
        return {"error": "invalid line range", "path": current["path"]}

    existing = str(current["content"])
    had_trailing_newline = existing.endswith("\n")
    lines = existing.splitlines()
    if start_line > len(lines) + 1 or end_line > len(lines):
        return {
            "error": "line range outside file",
            "path": current["path"],
            "lines": len(lines),
        }

    replacement = content.splitlines()
    updated_lines = lines[: start_line - 1] + replacement + lines[end_line:]
    updated = "\n".join(updated_lines)
    if had_trailing_newline or content.endswith("\n"):
        updated += "\n"
    result = db.upsert_file(str(current["path"]), updated, str(current["kind"]))
    result["action"] = "patched"
    return result


def move_path(source: str, destination: str = "") -> dict[str, Any]:
    """Move a file or folder into destination folder (empty string = workspace root)."""
    src = _safe_path(source)
    src_rel = str(src.relative_to(WORKSPACE))
    if src_rel == ".":
        return {"error": "cannot move workspace root"}

    dst_folder = ""
    if destination:
        dst = _safe_path(destination)
        dst_rel = str(dst.relative_to(WORKSPACE))
        dst_folder = "" if dst_rel == "." else dst_rel

    return db.move_path(src_rel, dst_folder)


def delete_file(path: str) -> dict[str, Any]:
    """Delete a file or virtual folder from the SQLite-backed workspace."""
    rel = str(_safe_path(path).relative_to(WORKSPACE))
    deleted_paths = db.list_paths_under(rel)
    if not deleted_paths:
        return {"error": f"file not found: {path}", "path": rel}
    deleted = db.delete_path(rel)
    return {
        "path": rel,
        "action": "deleted",
        "deleted": deleted,
        "deleted_paths": deleted_paths,
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
    if not db.file_exists(str(p.relative_to(WORKSPACE))):
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
    "create_folder": create_folder,
    "read_file": read_file,
    "write_file": write_file,
    "replace_in_file": replace_in_file,
    "replace_file_lines": replace_file_lines,
    "move_path": move_path,
    "delete_file": delete_file,
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
        "name": "create_folder",
        "description": (
            "Create an empty virtual subfolder in the SQLite-backed workspace. "
            "Use this when the user wants folder structure before files exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
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
        "name": "replace_in_file",
        "description": (
            "Patch a file by replacing one exact unique text fragment. Use this "
            "for small targeted edits when you know the old text exactly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "replace_file_lines",
        "description": (
            "Patch a file by replacing an inclusive 1-based line range. Use this "
            "when exact text replacement is ambiguous or line numbers are known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
                "content": {"type": "string"},
            },
            "required": ["path", "start_line", "end_line", "content"],
        },
    },
    {
        "name": "move_path",
        "description": (
            "Move a file or folder to a different folder in the workspace. "
            "Set destination to '' (empty string) to move to the workspace root. "
            "Moving a folder moves all its contents recursively."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Current path of the file or folder to move.",
                },
                "destination": {
                    "type": "string",
                    "description": (
                        "Target parent folder path. "
                        "Empty string or omit to move to workspace root."
                    ),
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "Delete a file or virtual folder from the SQLite-backed workspace. "
            "Deleting a folder deletes all files whose paths are under it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
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
