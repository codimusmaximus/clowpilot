"""Workspace plugin — UI display tools.

Controls the right-hand workspace pane: opening pages/files as tabs,
highlighting line ranges, and rendering ad-hoc snippets.
"""

from __future__ import annotations

from typing import Any

import tools
from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Workspace plugin (UI display):
Controls the right-hand workspace pane visible to the user.

- `display`   — open a page or file as a tab in the workspace pane
- `highlight` — highlight a line range in the currently displayed file with a comment
- `snippet`   — render an ad-hoc markdown or HTML snippet as its own workspace tab

Use `display` whenever you want the user to look at a specific page or file.
Use `snippet` for summaries, tables, or reports you want to show without saving.
Use `highlight` to draw attention to a specific section in an already-displayed file.
"""


def display(path: str) -> dict[str, Any]:
    """Open a page or file as a tab in the workspace pane."""
    return tools.display_file(path)


def highlight(path: str, start_line: int, end_line: int, comment: str) -> dict[str, Any]:
    """Highlight a line range in a displayed file with a pinned comment."""
    return tools.highlight(path, start_line, end_line, comment)


def snippet(content: str, format: str = "markdown") -> dict[str, Any]:
    """Render an ad-hoc snippet as a workspace tab. format: 'markdown' or 'html'."""
    return tools.snippet(content, format)


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.workspace",
        name="Workspace",
        type="core",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("display", display),
            ToolSpec("highlight", highlight),
            ToolSpec("snippet", snippet),
        ],
    )
