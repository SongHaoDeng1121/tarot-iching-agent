"""Restore an authorized, private deployment bundle without executing its contents."""
import hashlib
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import requests

from rag.runtime_data import knowledge_path

MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


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
    if not url:
        return knowledge_path("")
    digest = os.getenv("KNOWLEDGE_BUNDLE_SHA256", "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("KNOWLEDGE_BUNDLE_SHA256 must be a SHA-256 checksum")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Private bundle requires an HTTPS URL")
    cache = Path(os.getenv("KNOWLEDGE_CACHE_DIR", "/tmp/tarot-private-knowledge")).resolve()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = cache / digest
    # filelock is a Chroma dependency, works on Linux and macOS.
    from filelock import FileLock
    with FileLock(str(cache / "restore.lock"), timeout=180):
        if not (target / ".ready").is_file():
            if target.exists():
                raise ValueError("Incomplete private cache; use a new cache location")
            with tempfile.TemporaryDirectory(prefix="restore-", dir=cache) as temporary:
                temporary = Path(temporary)
                archive = temporary / "bundle.tar.gz"
                checksum = hashlib.sha256()
                headers = {}
                token = os.getenv("KNOWLEDGE_BUNDLE_TOKEN")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                # Redirects are disallowed to keep bearer tokens on the configured host.
                with requests.get(url, headers=headers, stream=True, timeout=(15, 120), allow_redirects=False) as response:
                    if response.status_code != 200:
                        raise ValueError("Private bundle download failed (check access and URL expiry)")
                    downloaded = 0
                    with archive.open("wb") as output:
                        for block in response.iter_content(1024 * 1024):
                            downloaded += len(block)
                            if downloaded > MAX_DOWNLOAD:
                                raise ValueError("Private bundle exceeds download limit")
                            checksum.update(block)
                            output.write(block)
                if checksum.hexdigest() != digest:
                    raise ValueError("Private bundle checksum mismatch")
                staging = temporary / "knowledge"
                staging.mkdir(mode=0o700)
                extract_bundle(archive, staging)
                staging.rename(target)
                restore_vectors(target)
                (target / ".ready").write_text(digest, encoding="ascii")
    os.environ["KNOWLEDGE_ROOT"] = str(target)
    return target
