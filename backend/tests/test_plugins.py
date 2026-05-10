from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
import json


DB_FILE = tempfile.NamedTemporaryFile(prefix="copilot-plugin-tests-", suffix=".sqlite3", delete=False)
DB_FILE.close()
os.environ["SQLITE_DB_PATH"] = DB_FILE.name
os.environ.setdefault("OPENAI_MODEL", "openai:gpt-5.2")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402

_REAL_INDEX_FILE = db.index_file


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
                "display",
                "highlight",
                "snippet",
            ],
        )

    def test_core_plugins_are_enabled_without_db_state(self) -> None:
        self.assertEqual(
            [plugin.id for plugin in registry.enabled_plugins()],
            ["core.workspace"],
        )
        self.assertIn("display", [tool.name for tool in registry.tools()])

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
        self.assertIn("Workspace plugin (UI display):", prompt)

    def test_plugin_api_lists_available_plugins(self) -> None:
        registry.PLUGIN_MODULES = [workspace]
        client = TestClient(main.app)

        response = client.get("/api/plugins")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["plugins"][0]["id"], "core.workspace")
        self.assertTrue(data["plugins"][0]["enabled"])
        self.assertIn("display", data["plugins"][0]["tools"])

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

    def test_attachment_upload_indexes_text_and_lists_metadata(self) -> None:
        db.index_file = _REAL_INDEX_FILE
        client = TestClient(main.app)
        conversation = client.post("/api/conversations", json={"title": "Attachment test"}).json()
        conversation_id = conversation["id"]

        response = client.post(
            f"/api/upload?conversationId={conversation_id}",
            files={"file": ("note.txt", b"hello attachment search\nchunk me", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        uploaded = response.json()
        self.assertEqual(uploaded["conversationId"], conversation_id)
        self.assertEqual(uploaded["contentType"], "text/plain")
        self.assertTrue(uploaded["path"].startswith(f"attachments/{conversation_id}/"))

        listed = client.get(f"/api/attachments?conversationId={conversation_id}").json()
        self.assertEqual(len(listed["attachments"]), 1)
        self.assertEqual(listed["attachments"][0]["id"], uploaded["id"])

        results = db.search_chunks("attachment search", limit=5)
        self.assertTrue(any(r["file_path"] == uploaded["path"] for r in results))
        db.index_file = _skip_indexing

    def test_message_persistence_roundtrips_attachments(self) -> None:
        conversation = db.create_conversation("Attachment persistence")
        attachment = {
            "id": "att-1",
            "type": "document",
            "name": "note.txt",
            "contentType": "text/plain",
            "path": "attachments/test/note.txt",
            "content": [
                {
                    "type": "file",
                    "data": "attachments/test/note.txt",
                    "mimeType": "text/plain",
                    "filename": "note.txt",
                }
            ],
            "status": {"type": "complete"},
        }
        db.replace_messages(
            conversation["id"],
            [
                {
                    "id": "m1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "see attachment"}],
                    "attachments": [attachment],
                    "createdAt": 1,
                    "parentId": None,
                }
            ],
        )
        messages = db.get_messages(conversation["id"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["attachments"][0]["id"], "att-1")

    def test_split_messages_inlines_small_attachment_text(self) -> None:
        prompt, history = agent.split_messages(
            [
                {
                    "role": "user",
                    "content": "Use the uploaded note",
                    "attachments": [
                        {
                            "name": "note.txt",
                            "path": "attachments/test/note.txt",
                            "contentType": "text/plain",
                            "content": [{"type": "text", "text": "small attachment body"}],
                        }
                    ],
                }
            ]
        )
        self.assertIn("Use the uploaded note", prompt)
        self.assertIn("small attachment body", prompt)
        self.assertEqual(history, [])

    def test_split_messages_uses_retrieval_hint_for_non_inlined_attachment(self) -> None:
        original = db.get_chunks_for_path
        db.get_chunks_for_path = lambda path, limit=200: [
            {"content": "indexed attachment text", "chunk_index": 0, "file_path": path, "metadata": {"kind": "text"}}
        ]
        try:
            prompt, _history = agent.split_messages(
                [
                    {
                        "role": "user",
                        "content": "Check the attached file",
                        "attachments": [
                            {
                                "name": "indexed.txt",
                                "path": "attachments/test/indexed.txt",
                                "contentType": "text/plain",
                                "content": [
                                    {
                                        "type": "file",
                                        "data": "attachments/test/indexed.txt",
                                        "mimeType": "text/plain",
                                        "filename": "indexed.txt",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            )
        finally:
            db.get_chunks_for_path = original

        self.assertIn("indexed attachment text", prompt)


if __name__ == "__main__":
    unittest.main()
