"""Restore an authorized, private deployment bundle without executing its contents."""
import hashlib
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, quote

import requests

from rag.runtime_data import knowledge_path

MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


class PrivateDataError(ValueError):
    """Only credential-free, user-actionable messages may use this type."""


def github_source():
    repository = os.getenv("KNOWLEDGE_GITHUB_REPOSITORY", "")
    token = os.getenv("KNOWLEDGE_GITHUB_TOKEN", "")
    commit = os.getenv("KNOWLEDGE_GITHUB_REF", "")
    path = os.getenv("KNOWLEDGE_GITHUB_PATH", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise PrivateDataError("KNOWLEDGE_GITHUB_REPOSITORY must be owner/private-repository.")
    if not token:
        raise PrivateDataError("Missing KNOWLEDGE_GITHUB_TOKEN; configure a fine-grained Contents: read token.")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise PrivateDataError("KNOWLEDGE_GITHUB_REF must be the immutable 40-character data commit SHA.")
    parts = PurePosixPath(path)
    if not path or parts.is_absolute() or ".." in parts.parts or "\\" in path:
        raise PrivateDataError("KNOWLEDGE_GITHUB_PATH must be a relative snapshot file path.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        with requests.get(f"https://api.github.com/repos/{repository}", headers=headers, timeout=(15, 60), allow_redirects=False) as response:
            if response.status_code != 200:
                raise PrivateDataError("Private GitHub repository unavailable; check repository access, token expiry and organization approval.")
            if response.json().get("private") is not True:
                raise PrivateDataError("Knowledge data must be stored in an independent PRIVATE GitHub repository.")
    except requests.RequestException:
        raise PrivateDataError("Cannot reach GitHub; retry or check network access.") from None
    headers["Accept"] = "application/vnd.github.raw+json"
    url = f"https://api.github.com/repos/{repository}/contents/{quote(path, safe='/')}?ref={commit}"
    return url, headers


def verify_snapshot(root):
    """Check the complete file inventory before initializing Chroma."""
    manifest = json.loads((root / "data/deployment_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") not in (1, 2):
        raise PrivateDataError("Unsupported knowledge snapshot format.")
    inventory = manifest.get("files_sha256", {})
    actual = {
        str(file.relative_to(root)) for file in root.rglob("*")
        if file.is_file() and file != root / "data/deployment_manifest.json"
    }
    if not inventory or set(inventory) != actual:
        raise PrivateDataError("Knowledge snapshot manifest does not match its complete file inventory.")
    for relative, checksum in inventory.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise PrivateDataError("Knowledge snapshot file checksum mismatch.")
    if manifest["format_version"] == 2:
        from importlib.metadata import version
        if manifest.get("chromadb_version") != version("chromadb"):
            raise PrivateDataError("Snapshot ChromaDB version differs from the installed runtime; use the same pinned version.")
        if not (root / "storage/chroma/chroma.sqlite3").is_file():
            raise PrivateDataError("Snapshot is missing the Chroma database.")
        import sqlite3
        sqlite_path = root / "storage/chroma/chroma.sqlite3"
        with sqlite3.connect(sqlite_path.resolve().as_uri() + "?mode=ro", uri=True) as database:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PrivateDataError("Snapshot SQLite integrity check failed.")
            segments = [row[0] for row in database.execute("SELECT id FROM segments WHERE scope='VECTOR'")]
        if not segments:
            raise PrivateDataError("Snapshot contains no vector-index directories.")
        for segment in segments:
            for filename in ("header.bin", "data_level0.bin", "length.bin", "link_lists.bin"):
                if f"storage/chroma/{segment}/{filename}" not in inventory:
                    raise PrivateDataError("Snapshot must include every Chroma vector-index directory, not only SQLite.")
        from rag.knowledge_check import COLLECTION_MANIFESTS
        if set(manifest.get("collections", {})) != set(COLLECTION_MANIFESTS):
            raise PrivateDataError("Snapshot manifest must declare all three collections.")
    return manifest


def validate_snapshot_readiness(root, manifest):
    """Validate in a short-lived process, closing Chroma before atomic rename."""
    import subprocess
    import sys
    from rag.runtime_data import ROOT
    result = subprocess.run(
        [sys.executable, "-m", "rag.knowledge_check"], cwd=ROOT,
        env={**os.environ, "KNOWLEDGE_ROOT": str(root)},
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode:
        raise PrivateDataError("Restored snapshot failed knowledge-readiness checks; verify all runtime assets and Linux index compatibility.")
    counts = json.loads(result.stdout)["counts"]
    if manifest["format_version"] == 2:
        if any(counts.get(name) != expected for name, expected in manifest["collections"].items()):
            raise PrivateDataError("Restored collection counts differ from the snapshot manifest.")


def restore_vectors(root):
    """Rebuild Linux-native ANN files using existing vectors; no API calls."""
    manifest_file = root / "data/deployment_manifest.json"
    if not manifest_file.is_file():
        raise ValueError("Private bundle is missing its deployment manifest")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported private bundle format")
    for relative, checksum in manifest["files_sha256"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Private manifest refers to a missing or unsafe file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("Private knowledge file checksum mismatch")
    from rag.knowledge_check import COLLECTION_MANIFESTS
    if set(manifest["collections"]) != set(COLLECTION_MANIFESTS):
        raise ValueError("Private bundle must include all three collections")
    import chromadb
    db = chromadb.PersistentClient(path=str(root / "storage/chroma"))
    if db.list_collections():
        raise ValueError("Vector restore requires a fresh database directory")
    for name, expected in manifest["collections"].items():
        if expected["dimension"] != 1024:
            raise ValueError("Unexpected vector dimension in private manifest")
        collection = db.create_collection(name, metadata=expected["metadata"])
        records = []

        def insert_batch(batch):
            if any(len(item["embedding"]) != 1024 for item in batch):
                raise ValueError("Private vector dimension mismatch")
            collection.add(
                ids=[item["id"] for item in batch],
                documents=[item["text"] for item in batch],
                metadatas=[item["metadata"] for item in batch],
                embeddings=[item["embedding"] for item in batch],
            )

        with (root / "storage/vector_exports" / f"{name}.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
                if len(records) == 128:
                    insert_batch(records)
                    records = []
        if records:
            insert_batch(records)
        if collection.count() != expected["count"]:
            raise ValueError("Restored vector collection count mismatch")


def extract_bundle(archive, destination):
    """Only regular knowledge files/directories; no links or traversal."""
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > MAX_EXPANDED:
            raise ValueError("Private bundle exceeds extraction limits")
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute() or ".." in path.parts or "\\" in member.name
                or not path.parts or path.parts[0] not in {"data", "storage"}
                or not (member.isfile() or member.isdir()) or member.name in seen
            ):
                raise ValueError("Unsafe private bundle member")
            seen.add(member.name)
        # All member types and paths have been validated before any writes.
        for member in members:
            target = Path(destination) / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source = bundle.extractfile(member)
                with source, target.open("xb") as output:
                    import shutil
                    shutil.copyfileobj(source, output)
                target.chmod(0o600)


def restore_private_bundle():
    """Called before RAG imports. Never overlays the developer's local tree."""
    url = os.getenv("KNOWLEDGE_BUNDLE_URL", "")
    github = bool(os.getenv("KNOWLEDGE_GITHUB_REPOSITORY"))
    if not url and not github:
        return knowledge_path("")
    if url and github:
        raise PrivateDataError("Configure one private source: GitHub repository OR HTTPS bundle URL.")
    digest = os.getenv("KNOWLEDGE_BUNDLE_SHA256", "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise PrivateDataError("KNOWLEDGE_BUNDLE_SHA256 must be a 64-character SHA-256 checksum.")
    parsed = urlsplit(url)
    if not github and (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password):
        raise ValueError("Private bundle requires an HTTPS URL")
    cache = Path(os.getenv("KNOWLEDGE_CACHE_DIR", "/tmp/tarot-private-knowledge")).resolve()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = cache / digest
    # filelock is a Chroma dependency, works on Linux and macOS.
    from filelock import FileLock
    with FileLock(str(cache / "restore.lock"), timeout=180):
        if not (target / ".ready").is_file():
            if target.exists():
                raise PrivateDataError("Incomplete legacy cache; set a new KNOWLEDGE_CACHE_DIR and restart.")
            with tempfile.TemporaryDirectory(prefix="restore-", dir=cache) as temporary:
                temporary = Path(temporary)
                archive = temporary / "bundle.tar.gz"
                checksum = hashlib.sha256()
                if github:
                    url, headers = github_source()
                else:
                    headers = {}
                    token = os.getenv("KNOWLEDGE_BUNDLE_TOKEN")
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                # Redirects are disallowed to keep bearer tokens on the configured host.
                with requests.get(url, headers=headers, stream=True, timeout=(15, 120), allow_redirects=False) as response:
                    if response.status_code != 200:
                        raise PrivateDataError("Private snapshot download failed; check file path, data commit, token permissions and URL expiry.")
                    downloaded = 0
                    with archive.open("wb") as output:
                        for block in response.iter_content(1024 * 1024):
                            downloaded += len(block)
                            if downloaded > (90 * 1024 * 1024 if github else MAX_DOWNLOAD):
                                raise ValueError("Private bundle exceeds download limit")
                            checksum.update(block)
                            output.write(block)
                if checksum.hexdigest() != digest:
                    raise PrivateDataError("Private bundle checksum mismatch; verify KNOWLEDGE_BUNDLE_SHA256 and the pinned data commit.")
                staging = temporary / "knowledge"
                staging.mkdir(mode=0o700)
                extract_bundle(archive, staging)
                manifest = verify_snapshot(staging)
                if manifest["format_version"] == 1:
                    # Isolate legacy creation so handles are closed before rename.
                    import subprocess
                    import sys
                    from rag.runtime_data import ROOT
                    legacy = subprocess.run(
                        [sys.executable, "-c", "import sys; from pathlib import Path; from rag.private_bundle import restore_vectors; restore_vectors(Path(sys.argv[1]))", str(staging)],
                        cwd=ROOT, capture_output=True, timeout=180,
                    )
                    if legacy.returncode:
                        raise PrivateDataError("Legacy portable bundle restoration failed; prepare a complete version-2 snapshot.")
                    validate_snapshot_readiness(staging, manifest)
                else:
                    # Complete snapshots are restored as-is: no create/delete,
                    # re-embedding, or rebuilding of any existing collection.
                    validate_snapshot_readiness(staging, manifest)
                (staging / ".ready").write_text(digest, encoding="ascii")
                staging.rename(target)
        elif (target / ".ready").read_text(encoding="ascii") != digest:
            raise PrivateDataError("Private cache marker does not match the configured checksum.")
    os.environ["KNOWLEDGE_ROOT"] = str(target)
    return target
