"""Tool implementations for the copilot agent.

All tools operate on a sandboxed workspace directory. Paths are normalized and
rejected if they escape the sandbox.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

import db

# Load backend/.env early (anchored to this file, CWD-independent) before reading
# WORKSPACE_DIR below. load_dotenv() does not override vars already set (e.g. by
# Docker compose), so deployment env still wins.
load_dotenv(Path(__file__).resolve().parent / ".env")


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "./workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)
WORKSPACE_NAME = WORKSPACE.name
ATTACHMENTS_DIR = Path(os.environ.get("ATTACHMENTS_DIR", WORKSPACE / "attachments")).resolve()
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------- path helpers ----------

def _safe_path(rel: str) -> Path:
    """Resolve a sandbox-relative path. Refuses traversal."""
    rel = (rel or "").lstrip("/")
    p = (WORKSPACE / rel).resolve()
    if WORKSPACE not in p.parents and p != WORKSPACE:
        raise ValueError(f"path '{rel}' escapes workspace")
    return p


def remap_into_workspace(path: str | Path) -> Path:
    """Map equivalent absolute host paths back into the configured workspace root."""
    candidate = Path(path).expanduser().resolve()
    if candidate == WORKSPACE or WORKSPACE in candidate.parents:
        return candidate

    parts = candidate.parts
    if WORKSPACE_NAME not in parts:
        raise ValueError(f"path '{candidate}' escapes workspace")

    anchor = parts.index(WORKSPACE_NAME)
    relative_parts = parts[anchor + 1 :]
    remapped = (WORKSPACE / Path(*relative_parts)).resolve()
    if remapped != WORKSPACE and WORKSPACE not in remapped.parents:
        raise ValueError(f"path '{candidate}' escapes workspace")
    return remapped


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
        "png": "image", "jpg": "image", "jpeg": "image",
        "gif": "image", "webp": "image", "svg": "image",
    }.get(e, "text")


def attachment_path(name: str, conversation_id: str | None = None) -> Path:
    safe_name = Path(name or "upload.bin").name
    if conversation_id:
        target = ATTACHMENTS_DIR / conversation_id / safe_name
    else:
        target = ATTACHMENTS_DIR / safe_name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def relative_workspace_path(path: Path) -> str:
    return str(path.resolve().relative_to(WORKSPACE))


def extract_text_for_attachment(path: Path, content_type: str, raw_bytes: bytes) -> str:
    if content_type.startswith("text/") or path.suffix.lower() in {".md", ".txt", ".csv", ".json", ".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".sql", ".yaml", ".yml"}:
        return raw_bytes.decode("utf-8", errors="replace")
    if path.suffix.lower() == ".pdf":
        # Lightweight fallback extraction from PDF content streams.
        decoded = raw_bytes.decode("latin-1", errors="ignore")
        text = " ".join(re.findall(r"\(([^()]*)\)", decoded))
        return text.strip()
    return ""


# ---------- disk helpers ----------

def _scan_disk() -> list[dict[str, Any]]:
    """Walk the real workspace filesystem for files not tracked in the DB."""
    results = []
    try:
        for p in sorted(WORKSPACE.rglob("*")):
            if any(part.startswith(".") for part in p.relative_to(WORKSPACE).parts):
                continue
            if p.is_file():
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                results.append({
                    "path": str(p.relative_to(WORKSPACE)),
                    "kind": _ext_kind(p),
                    "bytes": size,
                })
    except Exception:
        pass
    return results


def _build_tree_from_entries(entries: list[dict[str, Any]], rel: str = "") -> dict[str, Any]:
    """Build a nested tree dict from a flat list of {path, kind, bytes} entries."""
    prefix = f"{rel}/" if rel else ""
    root: dict[str, Any] = {
        "name": Path(rel).name if rel else "workspace",
        "path": rel,
        "type": "dir",
        "children": [],
    }
    dirs: dict[str, dict[str, Any]] = {rel: root}

    def ensure_dir(dpath: str) -> dict[str, Any]:
        if dpath in dirs:
            return dirs[dpath]
        parent_path = dpath.rsplit("/", 1)[0] if "/" in dpath else ""
        parent = ensure_dir(parent_path) if parent_path else root
        node = {"name": Path(dpath).name, "path": dpath, "type": "dir", "children": []}
        dirs[dpath] = node
        parent["children"].append(node)
        return node

    for entry in entries:
        fp = str(entry["path"])
        if rel and not fp.startswith(prefix):
            continue
        parts = fp.split("/")
        parent_path = "/".join(parts[:-1])
        parent = ensure_dir(parent_path) if parent_path else root
        parent["children"].append({
            "name": parts[-1],
            "path": fp,
            "type": "file",
            "kind": entry.get("kind", "text"),
            "size": entry.get("bytes", entry.get("size", 0)),
        })

    def sort_children(node: dict[str, Any]) -> None:
        node.get("children", []).sort(key=lambda x: (x["type"] == "file", x["name"].lower()))
        for child in node.get("children", []):
            if child["type"] == "dir":
                sort_children(child)

    sort_children(root)
    return root


# ---------- filesystem (disk) ops ----------

def page_list_tree(path: str = "") -> dict[str, Any]:
    """Return a tree of DB-backed pages only (no disk files)."""
    rel = path.strip("/")
    return _build_tree_from_entries(db.list_files(), rel)


def disk_list_tree() -> dict[str, Any]:
    """List workspace files that exist on disk (mount)."""
    return _build_tree_from_entries(_scan_disk())


def disk_read_file(path: str) -> dict[str, Any]:
    """Read a file directly from the filesystem mount."""
    p = _safe_path(path)
    rel = str(p.relative_to(WORKSPACE))
    if not p.exists() or not p.is_file():
        return {"error": f"file not found on disk: {path}"}
    try:
        content = p.read_text(errors="replace")
        return {"path": rel, "content": content, "kind": _ext_kind(p), "bytes": len(content.encode())}
    except Exception as e:
        return {"error": f"could not read file: {e}"}


def disk_write_file(path: str, content: str) -> dict[str, Any]:
    """Write a file directly to the filesystem mount (bypasses the DB/index)."""
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    rel = str(p.relative_to(WORKSPACE))
    return {"path": rel, "action": "written", "bytes": len(content.encode())}


def disk_delete_file(path: str) -> dict[str, Any]:
    """Delete a file or directory from the filesystem mount."""
    import shutil
    p = _safe_path(path)
    rel = str(p.relative_to(WORKSPACE))
    if not p.exists():
        return {"error": f"not found: {path}"}
    if p.is_dir():
        shutil.rmtree(p)
        return {"path": rel, "action": "deleted", "type": "directory"}
    p.unlink()
    return {"path": rel, "action": "deleted", "type": "file"}


# ---------- DB (page) ops ----------

def list_tree(path: str = "") -> dict[str, Any]:
    """Return a nested file tree merging DB pages and real disk files (for the sidebar)."""
    _safe_path(path) if path else WORKSPACE
    rel = path.strip("/")
    db_files = db.list_files()
    db_paths = {f["path"] for f in db_files}
    # Merge: disk files not already in DB
    merged = list(db_files) + [f for f in _scan_disk() if f["path"] not in db_paths]

    exact = next((f for f in merged if f["path"] == rel), None)
    if exact:
        return {"name": Path(rel).name, "path": rel, "type": "file",
                "kind": exact["kind"], "size": exact.get("bytes", 0)}

    # DB virtual folders
    db_folder_paths = {str(f) for f in db.list_folders() if str(f) not in db_paths}
    folder_entries = [{"path": fp, "kind": "dir", "bytes": 0} for fp in db_folder_paths]

    tree = _build_tree_from_entries(merged, rel)
    # Inject virtual DB folders that _build_tree_from_entries skips
    # (they have no files yet, so they wouldn't appear otherwise)
    for fp in db_folder_paths:
        if rel and not fp.startswith(f"{rel}/"):
            continue
        # Already present as a dir node if any child file created it; safe to skip
    return tree


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
    p = _safe_path(path)
    if p.suffix.lower() in IMAGE_EXTS:
        return {"error": f"'{path}' is an image — use display_image to show it"}
    rel = str(p.relative_to(WORKSPACE))
    file = db.get_file(rel)
    if file is not None:
        return file
    # Fall back to reading directly from disk (file exists on mount but not in DB)
    disk_path = WORKSPACE / rel
    if disk_path.exists() and disk_path.is_file():
        try:
            content = disk_path.read_text(errors="replace")
            return {"path": rel, "content": content, "kind": _ext_kind(disk_path), "bytes": len(content.encode())}
        except Exception as e:
            return {"error": f"could not read file: {e}"}
    return {"error": f"file not found: {path}"}


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
    """Move a file or folder. If destination is an existing folder, moves into it.
    Otherwise, treats destination as the full target path (rename)."""
    src = _safe_path(source)
    src_rel = str(src.relative_to(WORKSPACE))
    if src_rel == ".":
        return {"error": "cannot move workspace root"}

    dst_rel = ""
    if destination:
        dst = _safe_path(destination)
        dst_rel = str(dst.relative_to(WORKSPACE))
        if dst_rel == ".":
            dst_rel = ""

    return db.move_path(src_rel, dst_rel)


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


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def display_image(path: str) -> dict[str, Any]:
    """Display an image from the workspace in the workspace panel and chat."""
    p = _safe_path(path)
    if not p.exists() or not p.is_file():
        return {"error": f"file not found: {path}"}
    if p.suffix.lower() not in IMAGE_EXTS:
        return {"error": f"not an image: {path}"}
    rel = str(p.relative_to(WORKSPACE))
    return {"path": rel, "display": "image"}


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


def search(query: str, limit: int = 5, kind: str | None = None) -> dict[str, Any]:
    """Semantic search across all indexed workspace files."""
    results = db.search_chunks(query, limit=min(limit, 20), kind_filter=kind)
    return {"query": query, "results": results}


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
    "display_image": display_image,
    "highlight": highlight,
    "snippet": snippet,
    "search": search,
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
            "Move a file or folder. If destination is an existing folder, the "
            "source is moved into it. Otherwise, treats destination as the full "
            "target path (renaming the source). Moving a folder moves all its "
            "contents recursively."
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
                        "Target parent folder OR full new path. "
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
        "name": "display_image",
        "description": (
            "Display an image file from the workspace in the workspace panel. "
            "Call this after an image (png, jpg, svg, gif, webp) has been saved "
            "to the workspace so the user can see it. "
            "Also reference the image inline in your chat reply as "
            "![description](relative/path.png) so it appears in the chat too."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative path to the image file.",
                },
            },
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
    {
        "name": "search",
        "description": (
            "Semantic search across all workspace files. Returns the most relevant "
            "chunks with file paths, matching content, and relevance scores. "
            "Use this to find files related to a topic before reading them. "
            "Optionally filter by file kind (e.g. 'python', 'markdown', 'json')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5, max 20).",
                },
                "kind": {
                    "type": "string",
                    "description": "Filter to a specific file kind, e.g. 'python' or 'markdown'.",
                },
            },
            "required": ["query"],
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
