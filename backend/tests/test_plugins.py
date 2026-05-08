from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


DB_FILE = tempfile.NamedTemporaryFile(prefix="copilot-plugin-tests-", suffix=".sqlite3", delete=False)
DB_FILE.close()
os.environ["SQLITE_DB_PATH"] = DB_FILE.name
os.environ.setdefault("OPENAI_MODEL", "openai:gpt-5.2")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402


def _skip_indexing(*_args, **_kwargs) -> None:
    return None


db.index_file = _skip_indexing

from fastapi.testclient import TestClient  # noqa: E402
from plugins import registry, workspace  # noqa: E402
from plugins.base import PluginSpec, ToolSpec  # noqa: E402

import agent  # noqa: E402
import main  # noqa: E402


def fake_tool() -> dict[str, bool]:
    return {"ok": True}


class FakeExternalPluginModule:
    @staticmethod
    def get_plugin() -> PluginSpec:
        return PluginSpec(
            id="external.fake",
            name="Fake External",
            type="external",
            instructions="Fake external plugin instructions.",
            config_schema={
                "type": "object",
                "properties": {"account": {"type": "string"}},
            },
            tools=[ToolSpec("fake_tool", fake_tool)],
        )


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        registry.PLUGIN_MODULES = [workspace]
        db.set_plugin_enabled("external.fake", False, {})

    def test_workspace_plugin_exposes_existing_tools(self) -> None:
        plugin = workspace.get_plugin()

        self.assertEqual(plugin.id, "core.workspace")
        self.assertEqual(plugin.type, "core")
        self.assertIn("Workspace plugin", plugin.instructions)
        self.assertEqual(
            [tool.name for tool in plugin.tools],
            [
                "list_tree",
                "create_folder",
                "read_file",
                "write_file",
                "replace_in_file",
                "replace_file_lines",
                "delete_file",
                "display_file",
                "highlight",
                "snippet",
                "move_path",
                "search",
            ],
        )

    def test_core_plugins_are_enabled_without_db_state(self) -> None:
        self.assertEqual(
            [plugin.id for plugin in registry.enabled_plugins()],
            ["core.workspace"],
        )
        self.assertIn("search", [tool.name for tool in registry.tools()])

    def test_external_plugins_require_enablement(self) -> None:
        registry.PLUGIN_MODULES = [workspace, FakeExternalPluginModule]

        self.assertNotIn(
            "external.fake",
            [plugin.id for plugin in registry.enabled_plugins()],
        )
        self.assertNotIn("fake_tool", [tool.name for tool in registry.tools()])

        db.set_plugin_enabled("external.fake", True, {"account": "a@example.com"})

        self.assertIn(
            "external.fake",
            [plugin.id for plugin in registry.enabled_plugins()],
        )
        self.assertIn("fake_tool", [tool.name for tool in registry.tools()])

    def test_plugin_status_includes_config_schema_and_tools(self) -> None:
        registry.PLUGIN_MODULES = [workspace, FakeExternalPluginModule]
        db.set_plugin_enabled("external.fake", True, {"account": "a@example.com"})

        statuses = registry.list_plugin_status()
        fake = next(status for status in statuses if status["id"] == "external.fake")

        self.assertTrue(fake["enabled"])
        self.assertEqual(fake["config"], {"account": "a@example.com"})
        self.assertEqual(fake["tools"], ["fake_tool"])
        self.assertEqual(fake["configSchema"]["type"], "object")

    def test_system_prompt_includes_enabled_plugin_instructions(self) -> None:
        prompt = agent._compose_system_prompt("Base prompt.")

        self.assertIn("Base prompt.", prompt)
        self.assertIn("Enabled plugins:", prompt)
        self.assertIn("Workspace plugin:", prompt)
        self.assertIn(":command[", prompt)

    def test_plugin_api_lists_available_plugins(self) -> None:
        registry.PLUGIN_MODULES = [workspace]
        client = TestClient(main.app)

        response = client.get("/api/plugins")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["plugins"][0]["id"], "core.workspace")
        self.assertTrue(data["plugins"][0]["enabled"])
        self.assertIn("read_file", data["plugins"][0]["tools"])

    def test_plugin_api_rejects_unknown_plugin(self) -> None:
        client = TestClient(main.app)

        response = client.put("/api/plugins/missing.plugin", json={"enabled": True})

        self.assertEqual(response.status_code, 404)

    def test_plugin_api_can_enable_configured_external_plugin(self) -> None:
        registry.PLUGIN_MODULES = [workspace, FakeExternalPluginModule]
        client = TestClient(main.app)

        response = client.put(
            "/api/plugins/external.fake",
            json={"enabled": True, "config": {"account": "a@example.com"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        self.assertEqual(db.get_plugin_config("external.fake"), {"account": "a@example.com"})


if __name__ == "__main__":
    unittest.main()
