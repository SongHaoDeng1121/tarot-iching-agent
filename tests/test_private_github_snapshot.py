"""Private GitHub transport tests: synthetic credentials, no remote writes."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from rag.private_bundle import github_source, PrivateDataError, restore_private_bundle


ENV = {
    "KNOWLEDGE_GITHUB_REPOSITORY": "fixture/private-data",
    "KNOWLEDGE_GITHUB_REF": "a" * 40,
    "KNOWLEDGE_GITHUB_PATH": "snapshots/test.tar.gz",
    "KNOWLEDGE_GITHUB_TOKEN": "github_pat_SYNTHETIC_TEST_ONLY",
    "KNOWLEDGE_BUNDLE_URL": "",
    "KNOWLEDGE_BUNDLE_SHA256": "b" * 64,
}


def response(status=200, private=True):
    item = MagicMock()
    item.__enter__.return_value = item
    item.status_code = status
    item.json.return_value = {"private": private}
    return item


class GitHubSnapshotTests(unittest.TestCase):
    def test_sqlite_only_snapshot_rejected_before_chroma_initialization(self):
        import hashlib
        import json
        import sqlite3
        from importlib.metadata import version
        from rag.private_bundle import verify_snapshot
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "storage/chroma/chroma.sqlite3"
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE segments (id TEXT, scope TEXT)")
                db.execute("INSERT INTO segments VALUES ('synthetic-segment','VECTOR')")
            (root / "data").mkdir()
            manifest = {
                "format_version": 2, "chromadb_version": version("chromadb"),
                "files_sha256": {"storage/chroma/chroma.sqlite3": hashlib.sha256(database.read_bytes()).hexdigest()},
            }
            (root / "data/deployment_manifest.json").write_text(json.dumps(manifest))
            with patch("chromadb.PersistentClient", side_effect=AssertionError("must not initialize incomplete DB")):
                with self.assertRaisesRegex(PrivateDataError, "every Chroma vector-index"):
                    verify_snapshot(root)

    def test_public_repository_is_rejected_before_contents_download(self):
        with patch.dict(os.environ, ENV), patch("requests.get", return_value=response(private=False)) as get:
            with self.assertRaisesRegex(PrivateDataError, "PRIVATE"):
                github_source()
            self.assertEqual(get.call_count, 1)

    def test_raw_api_uses_fixed_host_immutable_ref_and_header_token(self):
        with patch.dict(os.environ, ENV), patch("requests.get", return_value=response()):
            url, headers = github_source()
            self.assertTrue(url.startswith("https://api.github.com/repos/fixture/private-data/contents/"))
            self.assertTrue(url.endswith("?ref=" + "a" * 40))
            self.assertNotIn(ENV["KNOWLEDGE_GITHUB_TOKEN"], url)
            self.assertEqual(headers["Accept"], "application/vnd.github.raw+json")

    def test_mutable_ref_and_traversal_are_rejected(self):
        for key, value in [("KNOWLEDGE_GITHUB_REF", "main"), ("KNOWLEDGE_GITHUB_PATH", "../file")]:
            with patch.dict(os.environ, {**ENV, key: value}), patch("requests.get") as get:
                with self.assertRaises(PrivateDataError):
                    github_source()
                get.assert_not_called()

    def test_expired_token_diagnostic_does_not_echo_credentials(self):
        with patch.dict(os.environ, ENV), patch("requests.get", return_value=response(status=401)):
            with self.assertRaises(PrivateDataError) as caught:
                github_source()
            self.assertNotIn(ENV["KNOWLEDGE_GITHUB_TOKEN"], str(caught.exception))

    def test_download_404_does_not_install_or_activate_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            **ENV, "KNOWLEDGE_ROOT": "/original", "KNOWLEDGE_CACHE_DIR": temporary,
        }), patch("requests.get", side_effect=[response(), response(status=404)]):
            with self.assertRaisesRegex(PrivateDataError, "download failed"):
                restore_private_bundle()
            self.assertEqual(os.environ["KNOWLEDGE_ROOT"], "/original")
            self.assertFalse((Path(temporary) / ("b" * 64)).exists())

    def test_incomplete_staging_failure_leaves_no_installed_root(self):
        import hashlib
        payload = b"synthetic-invalid-archive"
        downloaded = response()
        downloaded.iter_content.return_value = [payload]
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            **ENV, "KNOWLEDGE_ROOT": "/original", "KNOWLEDGE_CACHE_DIR": temporary,
            "KNOWLEDGE_BUNDLE_SHA256": digest,
        }), patch("requests.get", side_effect=[response(), downloaded]), patch(
            "rag.private_bundle.extract_bundle", side_effect=ValueError("invalid fixture")
        ):
            with self.assertRaises(ValueError):
                restore_private_bundle()
            self.assertFalse((Path(temporary) / digest).exists())


if __name__ == "__main__":
    unittest.main()
