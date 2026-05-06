"""SQLite persistence for workspace files and chat messages."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


DB_PATH = Path(os.environ.get("SQLITE_DB_PATH", "./copilot.sqlite3")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                kind TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS folders (
                path TEXT PRIMARY KEY,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                system_prompt_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (system_prompt_id) REFERENCES system_prompts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS system_prompts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                parts TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "conversation_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT")
        conversation_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "system_prompt_id" not in conversation_columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN system_prompt_id TEXT")
        row = conn.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()
        if int(row["count"]) == 0:
            conversation_id = str(uuid.uuid4())
            now = int(time.time() * 1000)
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, "New chat", now, now),
            )
            conn.execute(
                "UPDATE messages SET conversation_id = ? WHERE conversation_id IS NULL",
                (conversation_id,),
            )
        conn.execute("DELETE FROM messages WHERE conversation_id IS NULL")


def upsert_file(path: str, content: str, kind: str) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    now = time.time()
    existed = file_exists(path)
    with _connect() as conn:
        for folder in _parent_folders(path):
            conn.execute(
                "INSERT OR IGNORE INTO folders (path, created_at) VALUES (?, ?)",
                (folder, now),
            )
        conn.execute(
            """
            INSERT INTO files (path, content, kind, bytes, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                content = excluded.content,
                kind = excluded.kind,
                bytes = excluded.bytes,
                updated_at = excluded.updated_at
            """,
            (path, content, kind, len(encoded), now),
        )
    return {
        "path": path,
        "content": content,
        "kind": kind,
        "bytes": len(encoded),
        "lines": content.count("\n") + 1,
        "action": "updated" if existed else "created",
    }


def _parent_folders(path: str) -> list[str]:
    parts = path.strip("/").split("/")[:-1]
    folders: list[str] = []
    current = ""
    for part in parts:
        current = f"{current}/{part}".strip("/")
        folders.append(current)
    return folders


def create_folder(path: str) -> dict[str, Any]:
    rel = path.strip("/")
    now = time.time()
    existed = folder_exists(rel)
    with _connect() as conn:
        for folder in _parent_folders(f"{rel}/.keep"):
            conn.execute(
                "INSERT OR IGNORE INTO folders (path, created_at) VALUES (?, ?)",
                (folder, now),
            )
    return {
        "path": rel,
        "name": Path(rel).name if rel else "workspace",
        "type": "dir",
        "action": "existing" if existed else "created",
    }


def folder_exists(path: str) -> bool:
    rel = path.strip("/")
    if rel == "":
        return True
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM folders WHERE path = ?", (rel,)).fetchone()
    return row is not None


def file_exists(path: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM files WHERE path = ?", (path,)).fetchone()
    return row is not None


def get_file(path: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT path, content, kind, bytes FROM files WHERE path = ?", (path,)
        ).fetchone()
    if row is None:
        return None
    content = str(row["content"])
    return {
        "path": row["path"],
        "content": content,
        "kind": row["kind"],
        "bytes": row["bytes"],
        "lines": content.count("\n") + 1,
    }


def list_files() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT path, kind, bytes FROM files ORDER BY path COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def list_folders() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT path FROM folders ORDER BY path COLLATE NOCASE").fetchall()
    return [str(row["path"]) for row in rows]


def delete_path(path: str) -> int:
    with _connect() as conn:
        file_cursor = conn.execute(
            "DELETE FROM files WHERE path = ? OR path LIKE ?", (path, f"{path}/%")
        )
        folder_cursor = conn.execute(
            "DELETE FROM folders WHERE path = ? OR path LIKE ?", (path, f"{path}/%")
        )
    return int(file_cursor.rowcount) + int(folder_cursor.rowcount)


def list_paths_under(path: str) -> list[str]:
    with _connect() as conn:
        file_rows = conn.execute(
            "SELECT path FROM files WHERE path = ? OR path LIKE ? ORDER BY path",
            (path, f"{path}/%"),
        ).fetchall()
        folder_rows = conn.execute(
            "SELECT path FROM folders WHERE path = ? OR path LIKE ? ORDER BY path",
            (path, f"{path}/%"),
        ).fetchall()
    return [str(row["path"]) for row in folder_rows + file_rows]


def create_conversation(
    title: str = "New chat",
    system_prompt_id: str | None = None,
) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, system_prompt_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, title, system_prompt_id, now, now),
        )
    return {
        "id": conversation_id,
        "title": title,
        "systemPromptId": system_prompt_id,
        "createdAt": now,
        "updatedAt": now,
    }


def list_conversations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, system_prompt_id, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "systemPromptId": row["system_prompt_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def conversation_exists(conversation_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return row is not None


def ensure_conversation(conversation_id: str | None = None) -> dict[str, Any]:
    if conversation_id and conversation_exists(conversation_id):
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id, title, system_prompt_id, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return {
            "id": row["id"],
            "title": row["title"],
            "systemPromptId": row["system_prompt_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
    conversations = list_conversations()
    if conversations:
        return conversations[0]
    return create_conversation()


def set_conversation_system_prompt(
    conversation_id: str,
    system_prompt_id: str | None,
) -> dict[str, Any] | None:
    now = int(time.time() * 1000)
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE conversations
            SET system_prompt_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (system_prompt_id, now, conversation_id),
        )
        row = conn.execute(
            """
            SELECT id, title, system_prompt_id, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
    if cursor.rowcount == 0 or row is None:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "systemPromptId": row["system_prompt_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _title_from_messages(messages: list[dict[str, Any]]) -> str | None:
    for message in messages:
        if message.get("role") != "user":
            continue
        parts = message.get("parts", [])
        text = ""
        for part in parts:
            if part.get("type") == "text":
                text += str(part.get("text", ""))
        text = " ".join(text.split())
        if text:
            return text[:60]
    return None


def replace_messages(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    ensure_conversation(conversation_id)
    now = int(time.time() * 1000)
    title = _title_from_messages(messages)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        conn.executemany(
            """
            INSERT INTO messages (id, conversation_id, role, parts, created_at, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    m["id"],
                    conversation_id,
                    m["role"],
                    json.dumps(m.get("parts", [])),
                    int(m.get("createdAt", 0)),
                    i,
                )
                for i, m in enumerate(messages)
            ],
        )
        if title:
            conn.execute(
                """
                UPDATE conversations
                SET title = CASE WHEN title = 'New chat' THEN ? ELSE title END,
                    updated_at = ?
                WHERE id = ?
                """,
                (title, now, conversation_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, role, parts, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY position
            """,
            (conversation_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "parts": json.loads(row["parts"]),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def create_system_prompt(name: str, content: str) -> dict[str, Any]:
    prompt_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO system_prompts (id, name, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_id, name, content, now, now),
        )
    return {
        "id": prompt_id,
        "name": name,
        "content": content,
        "createdAt": now,
        "updatedAt": now,
    }


def list_system_prompts() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, content, created_at, updated_at
            FROM system_prompts
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "content": row["content"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def get_system_prompt(prompt_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, content, created_at, updated_at
            FROM system_prompts
            WHERE id = ?
            """,
            (prompt_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "content": row["content"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_system_prompt_by_name(name: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, content, created_at, updated_at
            FROM system_prompts
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "content": row["content"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def update_system_prompt(prompt_id: str, name: str, content: str) -> dict[str, Any] | None:
    now = int(time.time() * 1000)
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE system_prompts
            SET name = ?, content = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, content, now, prompt_id),
        )
    if cursor.rowcount == 0:
        return None
    return get_system_prompt(prompt_id)


def get_active_system_prompt_id() -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'active_system_prompt_id'"
        ).fetchone()
    return str(row["value"]) if row else None


def set_active_system_prompt(prompt_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES ('active_system_prompt_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (prompt_id,),
        )


def ensure_system_prompt(name: str, content: str) -> dict[str, Any]:
    prompts = list_system_prompts()
    active_id = get_active_system_prompt_id()
    if prompts:
        if active_id is None or get_system_prompt(active_id) is None:
            set_active_system_prompt(prompts[0]["id"])
        prompt = get_system_prompt(get_active_system_prompt_id() or prompts[0]["id"]) or prompts[0]
        with _connect() as conn:
            conn.execute(
                "UPDATE conversations SET system_prompt_id = ? WHERE system_prompt_id IS NULL",
                (prompt["id"],),
            )
        return prompt
    prompt = create_system_prompt(name, content)
    set_active_system_prompt(prompt["id"])
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET system_prompt_id = ? WHERE system_prompt_id IS NULL",
            (prompt["id"],),
        )
    return prompt


init()
