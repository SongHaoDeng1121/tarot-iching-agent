"""Deployment security and admission tests use synthetic data, never API calls."""
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from rag.cloud_access import reserve
from rag.private_bundle import extract_bundle, restore_private_bundle, restore_vectors
from rag.runtime_data import ROOT, knowledge_path, session_history_dir


class DeploymentTests(unittest.TestCase):
    def test_local_paths_preserved_and_private_root_supported(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(knowledge_path("data/chunks/test.jsonl"), ROOT / "data/chunks/test.jsonl")
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"KNOWLEDGE_ROOT": temporary}):
            self.assertEqual(knowledge_path("storage/chroma"), Path(temporary).resolve() / "storage/chroma")

    def test_histories_are_session_scoped(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"APP_RUNTIME_DIR": temporary}):
            alice = session_history_dir("a" * 32)
            bob = session_history_dir("b" * 32)
            (alice / "private.json").write_text('{"question":"alice"}')
            self.assertEqual(list(bob.glob("*.json")), [])
            self.assertNotEqual(alice, bob)
            with self.assertRaises(ValueError):
                session_history_dir("../alice")

    def test_global_quota_survives_new_session_and_failure(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "API_GLOBAL_DAILY_UNITS": "8", "API_SESSION_DAILY_UNITS": "24", "API_COOLDOWN_SECONDS": "0",
        }):
            path = Path(temporary) / "usage.sqlite3"
            reserve("alice", 8, path, now=1700000000)
            with self.assertRaisesRegex(RuntimeError, "应用额度"):
                reserve("bob", 2, path, now=1700000001)

    def test_session_cooldown_and_concurrency(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "API_GLOBAL_DAILY_UNITS": "100", "API_SESSION_DAILY_UNITS": "24",
            "API_COOLDOWN_SECONDS": "30", "API_MAX_CONCURRENT": "1",
        }):
            path = Path(temporary) / "usage.sqlite3"
            reserve("alice", 8, path, now=1700000000)
            with self.assertRaisesRegex(RuntimeError, "频繁"):
                reserve("alice", 2, path, now=1700000001)
            with self.assertRaisesRegex(RuntimeError, "人数"):
                reserve("bob", 2, path, now=1700000001)

    def test_atomic_quota_under_concurrent_sessions(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "API_GLOBAL_DAILY_UNITS": "8", "API_SESSION_DAILY_UNITS": "24",
            "API_COOLDOWN_SECONDS": "0", "API_MAX_CONCURRENT": "10",
        }):
            path = Path(temporary) / "usage.sqlite3"

            def attempt(session):
                try:
                    reserve(session, 8, path, now=1700000000)
                    return True
                except RuntimeError:
                    return False

            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(attempt, ["a", "b", "c", "d"])), 1)

    def make_archive(self, path, name, link=False):
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            if link:
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                archive.addfile(member)
            else:
                content = b'{"private":true}'
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))

    def test_bundle_rejects_traversal_symlinks_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (name, link) in enumerate([
                ("../outside.json", False), ("/data/absolute.json", False),
                ("data/link", True), (".env", False),
            ]):
                archive = root / f"test{index}.tgz"
                self.make_archive(archive, name, link)
                with self.assertRaises(ValueError):
                    extract_bundle(archive, root / f"output{index}")
            self.assertFalse((root / "outside.json").exists())

    def test_missing_data_fails_preflight_without_creating_db(self):
        from rag.knowledge_check import check_knowledge
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"KNOWLEDGE_ROOT": temporary}):
            result = check_knowledge()
            self.assertFalse(result["ready"])
            self.assertFalse((Path(temporary) / "storage/chroma").exists())

    def test_preflight_detects_missing_active_ids_and_ocr_pages(self):
        import hashlib
        import chromadb
        from rag.knowledge_check import check_knowledge, COLLECTION_MANIFESTS
        from rag.tarot_catalog import CARD_BY_ID
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"KNOWLEDGE_ROOT": temporary}):
            root = Path(temporary)

            def write(relative, data, lines=False):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "\n".join(json.dumps(item) for item in data) if lines else json.dumps(data),
                    encoding="utf-8",
                )

            write("data/structured/tarot_meanings.json", {
                card: {"upright_text": "fixture", "pdf_pages": [1]} for card in CARD_BY_ID
            })
            write("data/structured/zhouyi_sections.json", {
                "source_page_count": 2, "hexagrams": [{} for _ in range(64)]
            })
            write("data/structured/hexagrams.json", {})
            write("data/extracted/zhouyi_pages.jsonl", [
                {"pdf_page": 1, "text": "fixture"}, {"pdf_page": 2, "text": "fixture"}
            ], True)
            db = chromadb.PersistentClient(path=str(root / "storage/chroma"))
            for name, (relative, field) in COLLECTION_MANIFESTS.items():
                records = [{field: "synthetic", "text": "fixture", "pdf_page": 1}]
                if "greer" in name:
                    records = [{field: card, "card_id": card, "text": "fixture"} for card in CARD_BY_ID]
                write(relative, records, True)
                collection = db.create_collection(name, metadata={"hnsw:space": "cosine"})
                collection.add(
                    ids=[item[field] for item in records],
                    documents=["fixture"] * len(records),
                    embeddings=[[1.0] + [0.0] * 1023 for _ in records],
                    metadatas=[{"content_sha256": hashlib.sha256(b"fixture").hexdigest()} for _ in records],
                )
            self.assertTrue(check_knowledge()["ready"])
            # Delete only one synthetic test record from this temporary fixture.
            db.get_collection("tarot_greer_reversals_bge_m3_v1").delete(ids=["the_magician"])
            self.assertTrue(any("active IDs absent" in error for error in check_knowledge()["errors"]))
            write("data/extracted/zhouyi_pages.jsonl", [{"pdf_page": 1, "text": "fixture"}], True)
            self.assertTrue(any("OCR page coverage" in error for error in check_knowledge()["errors"]))

    def test_download_checksum_failure_does_not_activate_private_root(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [b"invalid-payload"]
        response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "KNOWLEDGE_ROOT": "/original", "KNOWLEDGE_BUNDLE_URL": "https://example.invalid/private",
            "KNOWLEDGE_BUNDLE_SHA256": "a" * 64, "KNOWLEDGE_CACHE_DIR": temporary,
        }), patch("requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                restore_private_bundle()
            self.assertEqual(os.environ["KNOWLEDGE_ROOT"], "/original")
            self.assertFalse((Path(temporary) / ("a" * 64)).exists())

    def test_private_bundle_restore_uses_supplied_vectors_without_network(self):
        from rag.knowledge_check import COLLECTION_MANIFESTS
        import hashlib
        import chromadb
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {"format_version": 1, "files_sha256": {}, "collections": {}}
            for name in COLLECTION_MANIFESTS:
                file = root / "storage/vector_exports" / f"{name}.jsonl"
                file.parent.mkdir(parents=True, exist_ok=True)
                vector = [1.0] + [0.0] * 1023
                record = {"id": "synthetic", "text": "fixture", "metadata": {"fixture": True}, "embedding": vector}
                file.write_text(json.dumps(record) + "\n")
                manifest["files_sha256"][str(file.relative_to(root))] = hashlib.sha256(file.read_bytes()).hexdigest()
                manifest["collections"][name] = {"count": 1, "dimension": 1024, "metadata": {"hnsw:space": "cosine"}}
            (root / "data").mkdir()
            (root / "data/deployment_manifest.json").write_text(json.dumps(manifest))
            with patch("requests.get", side_effect=AssertionError("unexpected network")):
                restore_vectors(root)
            db = chromadb.PersistentClient(path=str(root / "storage/chroma"))
            self.assertEqual({c.name: c.count() for c in db.list_collections()}, {name: 1 for name in COLLECTION_MANIFESTS})

    def test_cloud_entry_stops_before_rag_import_on_missing_data(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "KNOWLEDGE_ROOT": temporary, "KNOWLEDGE_BUNDLE_URL": "",
            "APP_ACCESS_PASSWORD": "fixture-password-at-least-20-characters",
        }):
            app = AppTest.from_file(str(ROOT / "cloud_app.py"))
            app.session_state["_authorized"] = True
            app.run(timeout=30)
            self.assertFalse(app.exception)
            self.assertTrue(any("知识库尚未就绪" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
