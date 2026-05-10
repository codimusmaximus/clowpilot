"""SQLite persistence for workspace files and chat messages."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
import time
import uuid
from pathlib import Path
from typing import Any

import sqlite_vec


DB_PATH = Path(os.environ.get("SQLITE_DB_PATH", "./copilot.sqlite3")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
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
            CREATE TABLE IF NOT EXISTS chunks (
                id          TEXT PRIMARY KEY,
                file_path   TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content     TEXT NOT NULL,
                metadata    TEXT NOT NULL DEFAULT '{}',
                embedding   BLOB,
                UNIQUE(file_path, chunk_index)
            );
            CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_path);

            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                kind TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS attachments_conversation_id ON attachments(conversation_id);
            """
        )
        # Migrate existing chunks table if it still carries the legacy foreign key to files.
        chunks_info = conn.execute("PRAGMA foreign_key_list(chunks)").fetchall()
        has_file_fk = any(row["table"] == "files" for row in chunks_info)
        if has_file_fk:
            conn.executescript(
                """
                DROP TABLE chunks;
                CREATE TABLE chunks (
                    id          TEXT PRIMARY KEY,
                    file_path   TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content     TEXT NOT NULL,
                    metadata    TEXT NOT NULL DEFAULT '{}',
                    embedding   BLOB,
                    UNIQUE(file_path, chunk_index)
                );
                CREATE INDEX chunks_file ON chunks(file_path);
                """
            )

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                system_prompt_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (system_prompt_id) REFERENCES system_prompts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                system_prompt_id TEXT,
                project_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (system_prompt_id) REFERENCES system_prompts(id) ON DELETE SET NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
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

            CREATE TABLE IF NOT EXISTS plugin_settings (
                plugin_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                config TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_plugins (
                conversation_id TEXT NOT NULL,
                plugin_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                config TEXT,
                PRIMARY KEY (conversation_id, plugin_id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
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
        if "parent_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN parent_id TEXT")
        conversation_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "head_message_id" not in conversation_columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN head_message_id TEXT")
        if "system_prompt_id" not in conversation_columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN system_prompt_id TEXT")
        if "project_id" not in conversation_columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT")
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
    _backfill_chunks()


def _backfill_chunks() -> None:
    """Index any file that has no chunks yet (handles files written before indexing existed)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT f.path, f.content, f.kind
            FROM files f
            LEFT JOIN chunks c ON c.file_path = f.path
            WHERE c.file_path IS NULL
            """
        ).fetchall()
    for row in rows:
        index_file(row["path"], row["content"], row["kind"])


_EMBED_MODEL = None
_MAX_INDEX_BYTES = 200_000


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL


def _embed(texts: list[str]) -> list[list[float]]:
    return _get_embed_model().encode(texts, normalize_embeddings=True).tolist()


def _serialize_vec(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def _chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def index_file(path: str, content: str, kind: str) -> None:
    if len(content.encode()) > _MAX_INDEX_BYTES:
        return
    chunks = _chunk_text(content)
    if not chunks:
        return
    embeddings = _embed(chunks)
    with _connect() as conn:
        conn.execute("DELETE FROM chunks WHERE file_path = ?", (path,))
        conn.executemany(
            """
            INSERT INTO chunks (id, file_path, chunk_index, content, metadata, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    path,
                    i,
                    chunk,
                    json.dumps({"kind": kind}),
                    _serialize_vec(emb),
                )
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
            ],
        )


def search_chunks(
    query: str,
    limit: int = 5,
    kind_filter: str | None = None,
) -> list[dict[str, Any]]:
    query_bytes = _serialize_vec(_embed([query])[0])
    if kind_filter:
        sql = """
            SELECT file_path, chunk_index, content, metadata,
                   vec_distance_cosine(embedding, ?) AS distance
            FROM chunks
            WHERE embedding IS NOT NULL
              AND json_extract(metadata, '$.kind') = ?
            ORDER BY distance
            LIMIT ?
        """
        params: tuple = (query_bytes, kind_filter, limit)
    else:
        sql = """
            SELECT file_path, chunk_index, content, metadata,
                   vec_distance_cosine(embedding, ?) AS distance
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY distance
            LIMIT ?
        """
        params = (query_bytes, limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "file_path": row["file_path"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]),
            "score": round(1.0 - float(row["distance"]), 4),
        }
        for row in rows
    ]


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
    index_file(path, content, kind)
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


def upsert_attachment(
    *,
    path: str,
    name: str,
    content_type: str,
    kind: str,
    bytes_count: int,
    extracted_text: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    now = int(time.time() * 1000)
    attachment_id = get_attachment_id_by_path(path) or str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO attachments (
                id, conversation_id, path, name, content_type, kind, bytes,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                conversation_id = excluded.conversation_id,
                name = excluded.name,
                content_type = excluded.content_type,
                kind = excluded.kind,
                bytes = excluded.bytes,
                updated_at = excluded.updated_at
            """,
            (
                attachment_id,
                conversation_id,
                path,
                name,
                content_type,
                kind,
                bytes_count,
                now,
                now,
            ),
        )
    if extracted_text.strip():
        index_file(path, extracted_text, kind)
    return get_attachment(attachment_id) or {
        "id": attachment_id,
        "conversationId": conversation_id,
        "path": path,
        "name": name,
        "contentType": content_type,
        "kind": kind,
        "bytes": bytes_count,
        "createdAt": now,
        "updatedAt": now,
    }


def get_attachment_id_by_path(path: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT id FROM attachments WHERE path = ?", (path,)).fetchone()
    return str(row["id"]) if row else None


def get_attachment(attachment_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
             SELECT id, conversation_id, path, name, content_type, kind, bytes,
                 created_at, updated_at
            FROM attachments
            WHERE id = ?
            """,
            (attachment_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "path": row["path"],
        "name": row["name"],
        "contentType": row["content_type"],
        "kind": row["kind"],
        "bytes": row["bytes"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_attachment_by_path(path: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
             SELECT id, conversation_id, path, name, content_type, kind, bytes,
                 created_at, updated_at
            FROM attachments
            WHERE path = ?
            """,
            (path,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "path": row["path"],
        "name": row["name"],
        "contentType": row["content_type"],
        "kind": row["kind"],
        "bytes": row["bytes"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_chunks_for_path(path: str, limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT file_path, chunk_index, content, metadata
            FROM chunks
            WHERE file_path = ?
            ORDER BY chunk_index
            LIMIT ?
            """,
            (path, limit),
        ).fetchall()
    return [
        {
            "file_path": row["file_path"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]),
        }
        for row in rows
    ]


def list_attachments(conversation_id: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, conversation_id, path, name, content_type, kind, bytes, created_at, updated_at "
        "FROM attachments"
    )
    params: tuple[Any, ...] = ()
    if conversation_id is not None:
        sql += " WHERE conversation_id = ?"
        params = (conversation_id,)
    sql += " ORDER BY updated_at DESC"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": row["id"],
            "conversationId": row["conversation_id"],
            "path": row["path"],
            "name": row["name"],
            "contentType": row["content_type"],
            "kind": row["kind"],
            "bytes": row["bytes"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


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
        conn.execute(
            "DELETE FROM chunks WHERE file_path = ? OR file_path LIKE ?",
            (path, f"{path}/%"),
        )
    return int(file_cursor.rowcount) + int(folder_cursor.rowcount)


def move_path(source: str, destination: str) -> dict[str, Any]:
    """Move a file or folder. If destination is an existing folder, moves into it.
    Otherwise, treats destination as the full target path (rename)."""
    src_rel = source.strip("/")
    dst_rel = destination.strip("/")

    if not src_rel:
        return {"error": "source path cannot be empty"}

    src_name = Path(src_rel).name
    
    # If destination is an existing folder, move INTO it.
    # Otherwise, treat destination as the NEW PATH.
    if folder_exists(dst_rel):
        new_rel = f"{dst_rel}/{src_name}".strip("/") if dst_rel else src_name
    else:
        new_rel = dst_rel

    if not new_rel:
        return {"error": "destination path cannot be empty"}

    if src_rel == new_rel:
        return {"error": "source and destination are the same", "path": src_rel}

    if new_rel.startswith(f"{src_rel}/"):
        return {"error": "cannot move a folder into one of its own subfolders"}

    now = time.time()
    with _connect() as conn:
        is_file = conn.execute("SELECT 1 FROM files WHERE path = ?", (src_rel,)).fetchone() is not None
        is_folder = conn.execute("SELECT 1 FROM folders WHERE path = ?", (src_rel,)).fetchone() is not None

        if not is_file and not is_folder:
            return {"error": f"not found: {source}"}

        if conn.execute("SELECT 1 FROM files WHERE path = ?", (new_rel,)).fetchone():
            return {"error": f"destination already exists: {new_rel}"}
        # Only block if we are renaming to a folder name that already exists
        if not folder_exists(dst_rel) and conn.execute("SELECT 1 FROM folders WHERE path = ?", (new_rel,)).fetchone():
            return {"error": f"destination already exists as a folder: {new_rel}"}

        # Create parent folders for the new location
        parent_path = "/".join(new_rel.split("/")[:-1])
        if parent_path:
            for folder in _parent_folders(f"{new_rel}"):
                conn.execute(
                    "INSERT OR IGNORE INTO folders (path, created_at) VALUES (?, ?)",
                    (folder, now),
                )
        elif is_folder:
            # If it's a folder being moved to root, it needs to be in folders table
            conn.execute(
                "INSERT OR IGNORE INTO folders (path, created_at) VALUES (?, ?)",
                (new_rel, now),
            )

        moved_files = 0
        moved_folders = 0

        if is_file:
            conn.execute("UPDATE files SET path = ? WHERE path = ?", (new_rel, src_rel))
            conn.execute("UPDATE chunks SET file_path = ? WHERE file_path = ?", (new_rel, src_rel))
            moved_files = 1
        else:
            conn.execute("UPDATE folders SET path = ? WHERE path = ?", (new_rel, src_rel))
            moved_folders = 1

            for row in conn.execute(
                "SELECT path FROM files WHERE path LIKE ?", (f"{src_rel}/%",)
            ).fetchall():
                old = str(row["path"])
                new = new_rel + old[len(src_rel):]
                conn.execute("UPDATE files SET path = ? WHERE path = ?", (new, old))
                conn.execute("UPDATE chunks SET file_path = ? WHERE file_path = ?", (new, old))
                moved_files += 1

            for row in conn.execute(
                "SELECT path FROM folders WHERE path LIKE ?", (f"{src_rel}/%",)
            ).fetchall():
                old = str(row["path"])
                new = new_rel + old[len(src_rel):]
                conn.execute("UPDATE folders SET path = ? WHERE path = ?", (new, old))
                moved_folders += 1

    return {
        "source": src_rel,
        "destination": new_rel,
        "action": "moved",
        "moved_files": moved_files,
        "moved_folders": moved_folders,
    }


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
    project_id: str | None = None,
) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, system_prompt_id, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, title, system_prompt_id, project_id, now, now),
        )
    return {
        "id": conversation_id,
        "title": title,
        "systemPromptId": system_prompt_id,
        "projectId": project_id,
        "createdAt": now,
        "updatedAt": now,
    }


def list_conversations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, system_prompt_id, project_id, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "systemPromptId": row["system_prompt_id"],
            "projectId": row["project_id"],
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
                SELECT id, title, system_prompt_id, project_id, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return {
            "id": row["id"],
            "title": row["title"],
            "systemPromptId": row["system_prompt_id"],
            "projectId": row["project_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
    conversations = list_conversations()
    if conversations:
        return conversations[0]
    return create_conversation()


def delete_conversation(conversation_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    return cursor.rowcount > 0


def set_conversation_project(
    conversation_id: str,
    project_id: str | None,
) -> dict[str, Any] | None:
    now = int(time.time() * 1000)
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE conversations SET project_id = ?, updated_at = ? WHERE id = ?",
            (project_id, now, conversation_id),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT id, title, system_prompt_id, project_id, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    return {
        "id": row["id"],
        "title": row["title"],
        "systemPromptId": row["system_prompt_id"],
        "projectId": row["project_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def create_project(name: str, system_prompt_id: str | None = None) -> dict[str, Any]:
    project_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, system_prompt_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, name, system_prompt_id, now, now),
        )
    return {
        "id": project_id,
        "name": name,
        "systemPromptId": system_prompt_id,
        "createdAt": now,
        "updatedAt": now,
    }


def list_projects() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, system_prompt_id, created_at, updated_at FROM projects ORDER BY created_at ASC"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "systemPromptId": row["system_prompt_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def get_project(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, system_prompt_id, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "systemPromptId": row["system_prompt_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def delete_project(project_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return cursor.rowcount > 0


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
            SELECT id, title, system_prompt_id, project_id, created_at, updated_at
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
        "projectId": row["project_id"],
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


def _normalize_message_for_storage(message: dict[str, Any]) -> dict[str, Any]:
    attachments = message.get("attachments", [])
    return {
        "parts": list(message.get("parts", [])),
        "attachments": list(attachments) if attachments else [],
    }


def replace_messages(
    conversation_id: str,
    messages: list[dict[str, Any]],
    head_id: str | None = None,
) -> None:
    ensure_conversation(conversation_id)
    now = int(time.time() * 1000)
    title = _title_from_messages(messages)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        conn.executemany(
            """
            INSERT INTO messages (id, conversation_id, role, parts, created_at, position, parent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    m["id"],
                    conversation_id,
                    m["role"],
                    json.dumps(_normalize_message_for_storage(m)),
                    int(m.get("createdAt", 0)),
                    i,
                    m.get("parentId"),
                )
                for i, m in enumerate(messages)
            ],
        )
        head_update = head_id or (messages[-1]["id"] if messages else None)
        if title:
            conn.execute(
                """
                UPDATE conversations
                SET title = CASE WHEN title = 'New chat' THEN ? ELSE title END,
                    updated_at = ?, head_message_id = ?
                WHERE id = ?
                """,
                (title, now, head_update, conversation_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = ?, head_message_id = ? WHERE id = ?",
                (now, head_update, conversation_id),
            )


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, role, parts, created_at, parent_id
            FROM messages
            WHERE conversation_id = ?
            ORDER BY position
            """,
            (conversation_id,),
        ).fetchall()
    result = []
    for i, row in enumerate(rows):
        parent_id = row["parent_id"]
        # Backfill parentId for legacy messages that predate branch support
        if parent_id is None and i > 0:
            parent_id = rows[i - 1]["id"]
        stored = json.loads(row["parts"])
        if isinstance(stored, dict):
            parts = stored.get("parts", [])
            attachments = stored.get("attachments", [])
        else:
            parts = stored
            attachments = []
        result.append({
            "id": row["id"],
            "role": row["role"],
            "parts": parts,
            "attachments": attachments,
            "createdAt": row["created_at"],
            "parentId": parent_id,
        })
    return result


def get_head_message_id(conversation_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT head_message_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    if row and row["head_message_id"]:
        return str(row["head_message_id"])
    # Fallback for conversations that predate branch support
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE conversation_id = ? ORDER BY position DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    return str(row["id"]) if row else None


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


def get_plugin_config(plugin_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT config FROM plugin_settings WHERE plugin_id = ?",
            (plugin_id,),
        ).fetchone()
    if row is None:
        return {}
    try:
        value = json.loads(str(row["config"]))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def is_plugin_enabled(plugin_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM plugin_settings WHERE plugin_id = ?",
            (plugin_id,),
        ).fetchone()
    return bool(row and row["enabled"])


def set_plugin_enabled(
    plugin_id: str,
    enabled: bool,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_config = get_plugin_config(plugin_id)
    next_config = current_config if config is None else config
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO plugin_settings (plugin_id, enabled, config, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET
                enabled = excluded.enabled,
                config = excluded.config,
                updated_at = excluded.updated_at
            """,
            (plugin_id, int(enabled), json.dumps(next_config), now),
        )
    return {
        "id": plugin_id,
        "enabled": enabled,
        "config": next_config,
        "updatedAt": now,
    }


def get_conversation_plugins(conversation_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT plugin_id, enabled, config FROM conversation_plugins WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
    return [
        {
            "plugin_id": row["plugin_id"],
            "enabled": bool(row["enabled"]),
            "config": json.loads(row["config"]) if row["config"] else None,
        }
        for row in rows
    ]


def set_conversation_plugin_enabled(
    conversation_id: str,
    plugin_id: str,
    enabled: bool,
    config: dict[str, Any] | None = None,
) -> None:
    config_json = json.dumps(config) if config is not None else None
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_plugins (conversation_id, plugin_id, enabled, config)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(conversation_id, plugin_id) DO UPDATE SET
                enabled = excluded.enabled,
                config = COALESCE(excluded.config, config)
            """,
            (conversation_id, plugin_id, int(enabled), config_json),
        )


def is_plugin_enabled_for_conversation(conversation_id: str, plugin_id: str) -> bool:
    # Check conversation override first
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM conversation_plugins WHERE conversation_id = ? AND plugin_id = ?",
            (conversation_id, plugin_id),
        ).fetchone()
        if row is not None:
            return bool(row["enabled"])
    # Fallback to global setting
    return is_plugin_enabled(plugin_id)


def get_conversation_disabled_tools(conversation_id: str, plugin_id: str) -> list[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT config FROM conversation_plugins WHERE conversation_id = ? AND plugin_id = ?",
            (conversation_id, plugin_id),
        ).fetchone()
    if row is None or not row["config"]:
        return []
    try:
        config = json.loads(str(row["config"]))
        return config.get("disabled_tools", []) if isinstance(config, dict) else []
    except (json.JSONDecodeError, AttributeError):
        return []


def set_conversation_tool_enabled(
    conversation_id: str, plugin_id: str, tool_name: str, enabled: bool
) -> None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT config FROM conversation_plugins WHERE conversation_id = ? AND plugin_id = ?",
            (conversation_id, plugin_id),
        ).fetchone()
    config: dict = {}
    if row and row["config"]:
        try:
            config = json.loads(str(row["config"])) or {}
        except json.JSONDecodeError:
            config = {}
    disabled: set[str] = set(config.get("disabled_tools", []))
    if enabled:
        disabled.discard(tool_name)
    else:
        disabled.add(tool_name)
    config["disabled_tools"] = sorted(disabled)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_plugins (conversation_id, plugin_id, enabled, config)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(conversation_id, plugin_id) DO UPDATE SET config = excluded.config
            """,
            (conversation_id, plugin_id, json.dumps(config)),
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
