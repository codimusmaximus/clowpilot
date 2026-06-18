"""Small plugin contract for agent tools and instructions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


PluginType = Literal["core", "external"]


@dataclass(frozen=True)
class ToolSpec:
    """A callable capability exposed to the agent."""

    name: str
    handler: Callable[..., Any]
    description: str | None = None


@dataclass(frozen=True)
class McpServerConfig:
    """Connection details for a remote MCP server (HTTP / SSE transport).

    `url` and `headers` values may contain ``${ENV_VAR}`` placeholders that are
    resolved against the process environment when the toolset is built, so that
    secrets (API tokens) live in the environment rather than the database.
    """

    transport: Literal["http", "sse"]
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    tool_prefix: str | None = None


@dataclass(frozen=True)
class PluginSpec:
    """A self-contained plugin definition loaded from code.

    Most plugins expose local ``tools``. A plugin may instead (or additionally)
    carry an ``mcp`` config, in which case its capabilities are provided by a
    remote MCP server attached to the agent as a toolset.
    """

    id: str
    name: str
    type: PluginType
    tools: list[ToolSpec] = field(default_factory=list)
    instructions: str = ""
    description: str = ""
    config_schema: dict[str, Any] | None = None
    mcp: McpServerConfig | None = None
