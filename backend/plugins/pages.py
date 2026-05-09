"""Pages plugin — DB-backed content store (Notion-style pages).

Pages live in SQLite: they are indexed, semantically searchable, and
versioned through the database. Think of them like Notion pages or
wiki articles — structured content managed by the assistant.

Use the Files plugin when you need to operate on real files on disk.
"""

from __future__ import annotations

from typing import Any

import tools
from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Pages plugin (DB-backed content store):
Pages are structured content records stored in the database — think Notion
pages or wiki articles. They are indexed for semantic search and managed
entirely by the assistant.

- `page_list`  — browse the page tree (sections and pages)
- `page_read`  — read a page's content
- `page_write` — create or fully overwrite a page
- `page_patch` — replace one unique text fragment in a page (targeted edit)
- `page_patch_lines` — replace a line range in a page
- `page_delete` — delete a page or section
- `page_move`  — move or rename a page/section
- `section_create` — create an empty section (folder)
- `page_search` — semantic search across all pages

Use `page_write` for new content; `page_patch` / `page_patch_lines` for edits.
Call `page_search` before reading when the user references a topic rather than a known path.
"""


def page_list(path: str = "") -> dict[str, Any]:
    """List pages and sections as a tree. Pass a section path to list only that subtree."""
    return tools.list_tree(path)


def page_read(path: str) -> dict[str, Any]:
    """Read the full content of a page."""
    return tools.read_file(path)


def page_write(path: str, content: str, type: str | None = None) -> dict[str, Any]:
    """Create or fully overwrite a page. Parent sections are created automatically."""
    return tools.write_file(path, content, type)


def page_patch(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Replace one exact unique text fragment in a page. Use for targeted edits."""
    return tools.replace_in_file(path, old_text, new_text)


def page_patch_lines(path: str, start_line: int, end_line: int, content: str) -> dict[str, Any]:
    """Replace an inclusive 1-based line range in a page."""
    return tools.replace_file_lines(path, start_line, end_line, content)


def page_delete(path: str) -> dict[str, Any]:
    """Delete a page or section (deletes all pages under a section)."""
    return tools.delete_file(path)


def page_move(source: str, destination: str = "") -> dict[str, Any]:
    """Move or rename a page or section."""
    return tools.move_path(source, destination)


def section_create(path: str) -> dict[str, Any]:
    """Create an empty section (like a Notion database or folder)."""
    return tools.create_folder(path)


def page_search(query: str, limit: int = 5, kind: str | None = None) -> dict[str, Any]:
    """Semantic search across all indexed pages. Use before reading when exploring by topic."""
    return tools.search(query, limit, kind)


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.pages",
        name="Pages",
        type="core",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("page_list", page_list),
            ToolSpec("page_read", page_read),
            ToolSpec("page_write", page_write),
            ToolSpec("page_patch", page_patch),
            ToolSpec("page_patch_lines", page_patch_lines),
            ToolSpec("page_delete", page_delete),
            ToolSpec("page_move", page_move),
            ToolSpec("section_create", section_create),
            ToolSpec("page_search", page_search),
        ],
    )
