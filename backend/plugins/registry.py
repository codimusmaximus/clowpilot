"""Explicit plugin registry.

Plugin definitions live in code. The database only tracks optional enablement
and config for plugins that need it.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import db
from plugins.base import PluginSpec, ToolSpec


# Override in tests to control which plugin modules are loaded.
PLUGIN_MODULES: list = []


def load_plugins() -> list[PluginSpec]:
    """Load plugins from PLUGIN_MODULES if set, otherwise auto-discover."""
    if PLUGIN_MODULES:
        return [m.get_plugin() for m in PLUGIN_MODULES if hasattr(m, "get_plugin")]

    plugins = []
    package = importlib.import_module("plugins")
    for _, name, _is_pkg in pkgutil.iter_modules(package.__path__):
        if name in ("base", "registry"):
            continue
        module_name = f"plugins.{name}"
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "get_plugin"):
                plugins.append(module.get_plugin())
        except Exception as e:
            print(f"Failed to load plugin {module_name}: {e}")
    return plugins


def is_enabled(plugin: PluginSpec, conversation_id: str | None = None) -> bool:
    if plugin.type == "core":
        return True
    if conversation_id:
        return db.is_plugin_enabled_for_conversation(conversation_id, plugin.id)
    return db.is_plugin_enabled(plugin.id)


def enabled_plugins(conversation_id: str | None = None) -> list[PluginSpec]:
    return [plugin for plugin in load_plugins() if is_enabled(plugin, conversation_id)]


def tools(conversation_id: str | None = None) -> list[ToolSpec]:
    return [tool for plugin in enabled_plugins(conversation_id) for tool in plugin.tools]


def instructions(conversation_id: str | None = None) -> str:
    return "\n\n".join(
        plugin.instructions.strip()
        for plugin in enabled_plugins(conversation_id)
        if plugin.instructions.strip()
    )


def list_plugin_status(conversation_id: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for plugin in load_plugins():
        # Use conversation-specific config if available
        config = db.get_plugin_config(plugin.id)
        rows.append(
            {
                "id": plugin.id,
                "name": plugin.name,
                "type": plugin.type,
                "enabled": is_enabled(plugin, conversation_id),
                "config": config,
                "configSchema": plugin.config_schema,
                "tools": [tool.name for tool in plugin.tools],
            }
        )
    return rows
