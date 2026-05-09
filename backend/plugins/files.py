"""Files plugin — real filesystem operations on the mounted workspace.

Files live on disk at WORKSPACE_DIR (mounted volume). They are NOT
automatically indexed or searchable — use the Pages plugin for content
you want the assistant to search and manage.

Typical use cases:
- Reading config files, scripts, or data the user dropped into the mount
- Writing outputs the user needs to access outside the assistant (exports, builds)
- Direct file manipulation when the user explicitly wants disk-level operations
"""

from __future__ import annotations

from typing import Any

import tools
from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Files plugin (real filesystem — mounted volume):
Files are actual files on disk at the workspace mount. Unlike pages, they are
NOT indexed for search. Use this plugin when operating on the raw filesystem.

- `file_list`  — list files on disk (what's actually in the mounted volume)
- `file_read`  — read a file from disk
- `file_write` — write a file to disk (does not index in the page database)
- `file_delete` — delete a file or directory from disk

When to use Files vs Pages:
- Use **Pages** when you want to create/edit/search content the assistant manages.
- Use **Files** when the user dropped files into the workspace mount that you
  need to read, or when writing outputs that should live on disk directly.
"""


def file_list() -> dict[str, Any]:
    """List files that exist on the mounted workspace filesystem."""
    return tools.disk_list_tree()


def file_read(path: str) -> dict[str, Any]:
    """Read a file directly from the filesystem mount."""
    return tools.disk_read_file(path)


def file_write(path: str, content: str) -> dict[str, Any]:
    """Write a file directly to the filesystem mount (does not index in DB)."""
    return tools.disk_write_file(path, content)


def file_delete(path: str) -> dict[str, Any]:
    """Delete a file or directory from the filesystem mount."""
    return tools.disk_delete_file(path)


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.files",
        name="Files",
        type="core",
        description="Real filesystem access — read and write files on the mounted volume.",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("file_list", file_list),
            ToolSpec("file_read", file_read),
            ToolSpec("file_write", file_write),
            ToolSpec("file_delete", file_delete),
        ],
    )
