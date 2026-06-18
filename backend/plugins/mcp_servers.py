"""MCP server registry.

MCP servers are exposed to the agent as remote toolsets (HTTP / SSE transport).
Unlike code-defined plugins, the set of servers is dynamic:

  * **Presets** (Fiken, Outlook) ship in code with ``${ENV_VAR}`` placeholders so
    a user only has to drop a URL + token into the environment to light them up.
  * **Custom servers** are stored in the database (see ``db.mcp_servers``) and can
    be added / removed at runtime via the ``/api/mcp-servers`` endpoints.

Both kinds surface as ``PluginSpec`` entries (``type="external"``, ``mcp`` set) so
they share the existing plugin enablement, per-conversation toggling, and UI.

Secrets never touch the database: ``url`` and ``headers`` values may contain
``${VAR}`` placeholders that are resolved against ``os.environ`` only when a
toolset is built. A server whose placeholders are unset is treated as
unconfigured and is silently skipped at agent-build time.
"""

from __future__ import annotations

import os
import re
from typing import Any

import db
from plugins.base import McpServerConfig, PluginSpec


_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Z0-9_]+)\}")


# ---------------------------------------------------------------------------
# Presets — wired with env-var placeholders, not real credentials.
# ---------------------------------------------------------------------------

PRESETS: list[PluginSpec] = [
    PluginSpec(
        id="mcp.fiken",
        name="Fiken",
        type="external",
        description=(
            "Fiken accounting (Norwegian bookkeeping) over MCP. "
            "Set FIKEN_MCP_URL and FIKEN_API_TOKEN to enable."
        ),
        instructions=(
            "Fiken MCP server:\n"
            "- Use the Fiken tools to read and create accounting data "
            "(invoices, contacts, transactions, accounts).\n"
            "- Always confirm company/organisation context before writing data.\n"
            "- Summarise figures clearly; never invent account numbers."
        ),
        mcp=McpServerConfig(
            transport="http",
            url="${FIKEN_MCP_URL}",
            headers={"Authorization": "Bearer ${FIKEN_API_TOKEN}"},
            tool_prefix="fiken",
        ),
    ),
    # Outlook is provided by the native `plugins.outlook` plugin (Graph direct,
    # device-code OAuth), not an MCP server.
]

_PRESET_IDS = {p.id for p in PRESETS}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _db_server_to_plugin(row: dict[str, Any]) -> PluginSpec:
    transport = row.get("transport") or "http"
    if transport not in ("http", "sse"):
        transport = "http"
    return PluginSpec(
        id=row["id"],
        name=row["name"],
        type="external",
        description=row.get("description") or "",
        instructions=row.get("instructions") or "",
        mcp=McpServerConfig(
            transport=transport,  # type: ignore[arg-type]
            url=row["url"],
            headers=row.get("headers") or {},
            tool_prefix=row.get("toolPrefix"),
        ),
    )


def load_mcp_plugins() -> list[PluginSpec]:
    """Return all MCP servers (presets + DB custom) as plugin specs.

    A DB row sharing a preset id overrides the preset, so users can customise a
    preset's URL/headers without losing the entry.
    """
    overridden = {row["id"] for row in db.list_mcp_servers()}
    plugins = [p for p in PRESETS if p.id not in overridden]
    plugins.extend(_db_server_to_plugin(row) for row in db.list_mcp_servers())
    return plugins


# ---------------------------------------------------------------------------
# Toolset construction
# ---------------------------------------------------------------------------

def _resolve_env(value: str) -> str | None:
    """Substitute ``${VAR}`` placeholders. Returns None if any var is unset."""
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        env = os.environ.get(name)
        if not env:
            missing.append(name)
            return ""
        return env

    resolved = _ENV_PLACEHOLDER.sub(repl, value)
    return None if missing else resolved


def is_configured(plugin: PluginSpec) -> bool:
    """True if every ``${VAR}`` in the server's url/headers is set."""
    cfg = plugin.mcp
    if cfg is None:
        return False
    if _resolve_env(cfg.url) is None:
        return False
    return all(_resolve_env(v) is not None for v in cfg.headers.values())


def build_toolset(plugin: PluginSpec) -> Any | None:
    """Build a pydantic-ai MCP toolset for ``plugin``.

    Returns None if the plugin is not an MCP server or its env placeholders are
    unresolved, so callers can simply skip it.
    """
    cfg = plugin.mcp
    if cfg is None:
        return None

    url = _resolve_env(cfg.url)
    if url is None:
        return None
    headers: dict[str, str] = {}
    for key, raw in cfg.headers.items():
        resolved = _resolve_env(raw)
        if resolved is None:
            return None
        headers[key] = resolved

    # Imported lazily: pydantic_ai.mcp requires the optional `mcp` package.
    from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

    cls = MCPServerSSE if cfg.transport == "sse" else MCPServerStreamableHTTP
    return cls(
        url=url,
        headers=headers or None,
        tool_prefix=cfg.tool_prefix,
        id=plugin.id,
    )
