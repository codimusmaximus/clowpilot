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
class PluginSpec:
    """A self-contained plugin definition loaded from code."""

    id: str
    name: str
    type: PluginType
    tools: list[ToolSpec] = field(default_factory=list)
    instructions: str = ""
    config_schema: dict[str, Any] | None = None
