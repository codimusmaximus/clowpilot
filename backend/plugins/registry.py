"""Explicit plugin registry.

Plugin definitions live in code. The database only tracks optional enablement
and config for plugins that need it.
"""

from __future__ import annotations

from typing import Any

import db
from plugins import workspace
from plugins.base import PluginSpec, ToolSpec


PLUGIN_MODULES = [
    workspace,
]


def load_plugins() -> list[PluginSpec]:
    return [module.get_plugin() for module in PLUGIN_MODULES]


def is_enabled(plugin: PluginSpec) -> bool:
    if plugin.type == "core":
        return True
    return db.is_plugin_enabled(plugin.id)


def enabled_plugins() -> list[PluginSpec]:
    return [plugin for plugin in load_plugins() if is_enabled(plugin)]


def tools() -> list[ToolSpec]:
    return [tool for plugin in enabled_plugins() for tool in plugin.tools]


def instructions() -> str:
    return "\n\n".join(
        plugin.instructions.strip()
        for plugin in enabled_plugins()
        if plugin.instructions.strip()
    )


def list_plugin_status() -> list[dict[str, Any]]:
    rows = []
    for plugin in load_plugins():
        config = db.get_plugin_config(plugin.id)
        rows.append(
            {
                "id": plugin.id,
                "name": plugin.name,
                "type": plugin.type,
                "enabled": is_enabled(plugin),
                "config": config,
                "configSchema": plugin.config_schema,
                "tools": [tool.name for tool in plugin.tools],
            }
        )
    return rows
