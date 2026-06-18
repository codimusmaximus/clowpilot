"""Search plugin — unified semantic search over the whole workspace.

A single embedding index (SQLite + sqlite-vec) covers two sources:

- ``page`` — DB-backed pages managed by the assistant (Pages plugin)
- ``file`` — real files on the mounted filesystem (Files plugin)

Both are chunked at 500 tokens with 100-token overlap, embedded, and stored
with metadata (source, kind, path, size, mtime). Page indexing happens on every
page write; filesystem indexing happens on every disk write/delete and on a
manual full sweep (`reindex`). Re-embedding is skipped when content is unchanged
(content-hash based), so calling these tools repeatedly is cheap.
"""

from __future__ import annotations

from typing import Any

import db
import tools
from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Search plugin (unified semantic index):
One semantic index spans BOTH DB-backed pages and real filesystem files.

- `index_search` — semantic search across everything. Filter by `source`
  ("page" or "file") or `kind` ("markdown", "python", "csv", …) when you only
  want one. Use this before reading when the user references a topic rather than
  a known path. Each hit carries a `context` block with its `folder`, the
  `ancestors` breadcrumb up to the root, its `children` (sub-folders/files), and
  `siblings` (neighbours in the same folder) — use it to navigate around a hit
  without extra `list_tree`/`file_list` calls.
- `reindex` — sweep the mounted filesystem and (re)index any new/changed files.
  Run this after the user drops files into the workspace mount, or if a search
  unexpectedly misses something on disk. Cheap to re-run (unchanged files skip).
- `index_status` — report what's indexed (chunk/document counts per source).

Files written via the Files plugin and pages written via the Pages plugin are
indexed automatically; `reindex` is only needed for files that appeared on disk
out-of-band.
"""


def index_search(
    query: str,
    limit: int = 5,
    source: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Semantic search over pages + filesystem. Optional source/kind filters."""
    return tools.search(query, limit=limit, kind=kind, source=source)


def reindex() -> dict[str, Any]:
    """Sweep the mounted filesystem and (re)index new or changed text files."""
    return tools.reindex_disk()


def index_status() -> dict[str, Any]:
    """Summarise the index: chunk/document counts per source and chunk settings."""
    return db.index_status()


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.search",
        name="Search",
        type="core",
        description="Unified semantic search over DB pages and the real filesystem.",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("index_search", index_search),
            ToolSpec("reindex", reindex),
            ToolSpec("index_status", index_status),
        ],
    )
