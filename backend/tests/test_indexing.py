"""Tests for the unified embedding index (DB pages + real filesystem).

The embedding microservice is replaced with a deterministic lexical-overlap
fake, so these tests run offline and search ranking is predictable: chunks that
share words with the query rank closest.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


# Isolated temp DB + workspace, wired before importing the app modules so module
# level paths (db.DB_PATH, tools.WORKSPACE) resolve to them.
_DB = tempfile.NamedTemporaryFile(prefix="copilot-index-tests-", suffix=".sqlite3", delete=False)
_DB.close()
os.environ["SQLITE_DB_PATH"] = _DB.name
_WS = tempfile.mkdtemp(prefix="copilot-index-ws-")
os.environ["WORKSPACE_DIR"] = _WS
os.environ["ATTACHMENTS_DIR"] = str(Path(_WS) / "attachments")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402
import tools  # noqa: E402
from plugins import registry, search as search_plugin  # noqa: E402

# mkdtemp can return a /var symlink that resolves to /private/var on macOS;
# _safe_path compares against the resolved path, so resolve up front.
_WS_PATH = Path(_WS).resolve()


# Match the real model's dimensionality so fake and real vectors can coexist in
# a shared test DB without a sqlite-vec dimension mismatch.
_EMBED_DIM = 384


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Hash words into a fixed-dim bag-of-words vector, L2-normalised.

    Cosine distance between these vectors falls as lexical overlap rises, so the
    chunk sharing the most words with a query ranks first — enough to test
    retrieval wiring deterministically without the real model.
    """
    vectors = []
    for text in texts:
        vec = [0.0] * _EMBED_DIM
        for word in text.lower().split():
            vec[hash(word) % _EMBED_DIM] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


class TokenChunkingTests(unittest.TestCase):
    def test_token_chunks_respect_size_and_overlap(self) -> None:
        # Force the word-approximation path for an exact, deterministic boundary
        # check (one word == one token).
        original = db._encoder
        db._encoder = False
        try:
            words = [f"w{i}" for i in range(25)]
            chunks = db._chunk_text(" ".join(words), size=10, overlap=3)
        finally:
            db._encoder = original

        # step = size - overlap = 7 -> starts at 0, 7, 14, 21
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0].split(), words[0:10])
        self.assertEqual(chunks[1].split(), words[7:17])
        self.assertEqual(chunks[3].split(), words[21:25])
        # Consecutive chunks overlap by exactly `overlap` tokens.
        self.assertEqual(chunks[0].split()[-3:], chunks[1].split()[:3])

    def test_real_tokenizer_chunks_long_text(self) -> None:
        text = "lorem ipsum dolor sit amet " * 400  # well over 500 tokens
        chunks = db._chunk_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.strip() for c in chunks))


class IndexSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_embed = db._embed
        db._embed = _fake_embed
        with db._connect() as conn:
            conn.execute("DELETE FROM chunks")

    def tearDown(self) -> None:
        db._embed = self._orig_embed
        with db._connect() as conn:
            conn.execute("DELETE FROM chunks")

    def test_index_content_stores_metadata_and_hash(self) -> None:
        result = db.index_content(
            "page", "notes/alpha.md", "the quick brown fox", "markdown"
        )
        self.assertEqual(result["indexed"], 1)
        chunks = db.get_chunks_for_path("notes/alpha.md")
        meta = chunks[0]["metadata"]
        self.assertEqual(meta["source"], "page")
        self.assertEqual(meta["kind"], "markdown")
        self.assertEqual(meta["path"], "notes/alpha.md")
        self.assertEqual(meta["chunk_index"], 0)

    def test_unchanged_content_skips_reembedding(self) -> None:
        calls = {"n": 0}

        def counting_embed(texts: list[str]) -> list[list[float]]:
            calls["n"] += 1
            return _fake_embed(texts)

        db._embed = counting_embed
        db.index_content("page", "p.md", "hello world body", "markdown")
        first = calls["n"]
        out = db.index_content("page", "p.md", "hello world body", "markdown")
        self.assertEqual(out["skipped"], "unchanged")
        self.assertEqual(calls["n"], first)  # no second embed call

        # Changing the content re-embeds.
        out2 = db.index_content("page", "p.md", "hello world body changed", "markdown")
        self.assertNotIn("skipped", out2)
        self.assertGreater(calls["n"], first)

    def test_unified_search_across_sources_with_filter(self) -> None:
        db.index_content("page", "alpha.md", "the quick brown fox jumps", "markdown")
        db.index_content("file", "beta.txt", "lorem ipsum dolor amet", "text")

        results = db.search_chunks("quick brown fox", limit=5)
        self.assertEqual(results[0]["file_path"], "alpha.md")
        self.assertEqual(results[0]["source"], "page")

        only_files = db.search_chunks("quick brown fox", limit=5, source_filter="file")
        self.assertTrue(all(r["source"] == "file" for r in only_files))
        self.assertTrue(all(r["file_path"] == "beta.txt" for r in only_files))

    def test_search_result_includes_page_folder_context(self) -> None:
        # upsert_file populates the files table that the page namespace reads.
        try:
            db.upsert_file("proj/spec.md", "alpha specification uniquepagehit", "markdown")
            db.upsert_file("proj/readme.md", "project readme", "markdown")
            db.create_folder("proj/assets")

            hits = tools.search("uniquepagehit", source="page")["results"]
            top = next(h for h in hits if h["file_path"] == "proj/spec.md")
            ctx = top["context"]
            self.assertEqual(ctx["folder"], "proj")
            self.assertEqual(ctx["ancestors"], ["proj"])
            siblings = {s["path"]: s for s in ctx["siblings"]}
            self.assertIn("proj/readme.md", siblings)
            self.assertIn("proj/assets", siblings)
            self.assertEqual(siblings["proj/assets"]["type"], "dir")
            self.assertEqual(siblings["proj/readme.md"]["type"], "file")
        finally:
            db.delete_path("proj")

    def test_index_status_counts_per_source(self) -> None:
        db.index_content("page", "a.md", "alpha content", "markdown")
        db.index_content("file", "b.txt", "beta content", "text")
        status = db.index_status()
        self.assertEqual(status["chunk_tokens"], 500)
        self.assertEqual(status["chunk_overlap"], 100)
        self.assertEqual(status["by_source"]["page"]["documents"], 1)
        self.assertEqual(status["by_source"]["file"]["documents"], 1)


class FilesystemIndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        # Point the shared tools module at this suite's temp workspace, saving
        # the originals so other test modules sharing `tools` aren't disturbed.
        self._orig_embed = db._embed
        self._orig_ws = tools.WORKSPACE
        self._orig_att = tools.ATTACHMENTS_DIR
        self._orig_attrel = tools._ATTACHMENTS_REL
        db._embed = _fake_embed
        tools.WORKSPACE = _WS_PATH
        tools.ATTACHMENTS_DIR = _WS_PATH / "attachments"
        tools.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        tools._ATTACHMENTS_REL = "attachments"
        with db._connect() as conn:
            conn.execute("DELETE FROM chunks")

    def tearDown(self) -> None:
        db._embed = self._orig_embed
        tools.WORKSPACE = self._orig_ws
        tools.ATTACHMENTS_DIR = self._orig_att
        tools._ATTACHMENTS_REL = self._orig_attrel
        with db._connect() as conn:
            conn.execute("DELETE FROM chunks")

    def test_disk_write_indexes_and_delete_unindexes(self) -> None:
        out = tools.disk_write_file("docs/readme.md", "searchable disk content here")
        self.assertGreaterEqual(out["indexed"], 1)

        hits = db.search_chunks("searchable disk content", source_filter="file")
        self.assertTrue(any(h["file_path"] == "docs/readme.md" for h in hits))

        tools.disk_delete_file("docs/readme.md")
        self.assertEqual(db.list_indexed_paths("file"), [])

    def test_search_result_includes_filesystem_folder_context(self) -> None:
        tools.disk_write_file("docs/guide.md", "unique searchable guidetoken content")
        tools.disk_write_file("docs/notes.md", "some other notes here")
        tools.disk_write_file("docs/sub/deep.md", "a deeper file")

        hits = tools.search("guidetoken", source="file")["results"]
        top = next(h for h in hits if h["file_path"] == "docs/guide.md")
        ctx = top["context"]
        self.assertEqual(ctx["folder"], "docs")
        self.assertEqual(ctx["ancestors"], ["docs"])
        siblings = {s["path"]: s for s in ctx["siblings"]}
        # Siblings include both the neighbouring file and the sub-folder.
        self.assertIn("docs/notes.md", siblings)
        self.assertIn("docs/sub", siblings)
        self.assertEqual(siblings["docs/sub"]["type"], "dir")
        # A file hit has no children of its own.
        self.assertEqual(ctx["children"], [])

    def test_images_and_attachments_are_not_indexed(self) -> None:
        tools.disk_write_file("logo.png", "not real png but image kind")
        self.assertNotIn("logo.png", db.list_indexed_paths("file"))

    def test_reindex_picks_up_and_prunes_disk_files(self) -> None:
        # Write a file straight to disk, bypassing the indexing hook.
        target = Path(_WS) / "raw" / "dropped.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("dropped file content for sweep")

        summary = tools.reindex_disk()
        self.assertGreaterEqual(summary["chunks_indexed"], 1)
        self.assertIn("raw/dropped.txt", db.list_indexed_paths("file"))

        # Re-running with no changes skips re-embedding.
        again = tools.reindex_disk()
        self.assertEqual(again["files_indexed"], 0)
        self.assertGreaterEqual(again["files_unchanged"], 1)

        # Removing the file on disk and sweeping prunes its index entries.
        target.unlink()
        pruned = tools.reindex_disk()
        self.assertGreaterEqual(pruned["chunks_pruned"], 1)
        self.assertNotIn("raw/dropped.txt", db.list_indexed_paths("file"))


class SearchPluginTests(unittest.TestCase):
    def test_plugin_is_discovered_with_expected_tools(self) -> None:
        plugin = search_plugin.get_plugin()
        self.assertEqual(plugin.id, "core.search")
        self.assertEqual(plugin.type, "core")
        self.assertEqual(
            [t.name for t in plugin.tools],
            ["index_search", "reindex", "index_status"],
        )

    def test_plugin_auto_registers_as_core(self) -> None:
        registry.PLUGIN_MODULES = []
        ids = [p.id for p in registry.load_plugins()]
        self.assertIn("core.search", ids)
        self.assertIn("index_search", [t.name for t in registry.tools()])


if __name__ == "__main__":
    unittest.main()
