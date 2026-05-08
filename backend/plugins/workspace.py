"""Core workspace plugin.

This plugin deliberately keeps the existing public tool names so current chat
history and frontend tool rendering continue to work.
"""

from __future__ import annotations

from typing import Any

import tools

from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Workspace plugin:
- Use workspace tools to inspect, create, move, search, and edit files.
- Call `search` before reading when the user references a topic rather than a known path.
- Call `display_file` when the user should look at a file in the workspace pane.
- Use `highlight` for line-specific explanations and `snippet` for unsaved rendered output.
- If a user message includes a `:command[...]` directive for a plugin or tool,
  treat it as explicit context about which capability the user wants you to use.
"""


def list_tree(path: str = "") -> dict[str, Any]:
    """List the workspace file tree."""
    return tools.list_tree(path)


def create_folder(path: str) -> dict[str, Any]:
    """Create an empty virtual subfolder in the workspace."""
    return tools.create_folder(path)


def read_file(path: str) -> dict[str, Any]:
    """Read the full contents of a workspace file."""
    return tools.read_file(path)


def write_file(path: str, content: str, type: str | None = None) -> dict[str, Any]:
    """Create or overwrite a workspace file."""
    return tools.write_file(path, content, type)


def replace_in_file(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Patch a file by replacing one exact unique text fragment."""
    return tools.replace_in_file(path, old_text, new_text)


def replace_file_lines(
    path: str,
    start_line: int,
    end_line: int,
    content: str,
) -> dict[str, Any]:
    """Patch a file by replacing an inclusive 1-based line range."""
    return tools.replace_file_lines(path, start_line, end_line, content)


def delete_file(path: str) -> dict[str, Any]:
    """Delete a file or virtual folder from the workspace."""
    return tools.delete_file(path)


def display_file(path: str) -> dict[str, Any]:
    """Open a file as a tab in the workspace pane."""
    return tools.display_file(path)


def highlight(
    path: str,
    start_line: int,
    end_line: int,
    comment: str,
) -> dict[str, Any]:
    """Highlight a line range in a displayed file."""
    return tools.highlight(path, start_line, end_line, comment)


def snippet(content: str, format: str = "markdown") -> dict[str, Any]:
    """Render an ad-hoc snippet in the workspace pane."""
    return tools.snippet(content, format)


def move_path(source: str, destination: str = "") -> dict[str, Any]:
    """Move a file or folder to another workspace folder."""
    return tools.move_path(source, destination)


def search(query: str, limit: int = 5, kind: str | None = None) -> dict[str, Any]:
    """Semantic search across workspace files."""
    return tools.search(query, limit, kind)


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.workspace",
        name="Workspace",
        type="core",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("list_tree", list_tree),
            ToolSpec("create_folder", create_folder),
            ToolSpec("read_file", read_file),
            ToolSpec("write_file", write_file),
            ToolSpec("replace_in_file", replace_in_file),
            ToolSpec("replace_file_lines", replace_file_lines),
            ToolSpec("delete_file", delete_file),
            ToolSpec("display_file", display_file),
            ToolSpec("highlight", highlight),
            ToolSpec("snippet", snippet),
            ToolSpec("move_path", move_path),
            ToolSpec("search", search),
        ],
    )
