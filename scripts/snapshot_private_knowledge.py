"""Create a complete local Chroma snapshot; never upload or regenerate vectors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

from rag.knowledge_check import FILES
from rag.runtime_data import ROOT, chroma_path, knowledge_path


def hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def validate_root(root):
    environment = {**os.environ, "KNOWLEDGE_ROOT": str(root)}
    result = subprocess.run(
        [sys.executable, "-m", "rag.knowledge_check"], cwd=ROOT,
        env=environment, capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise ValueError("Snapshot readiness validation failed; inspect the local knowledge check")
    return json.loads(result.stdout)


def build_snapshot(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.is_relative_to(ROOT) or destination.exists():
        raise ValueError("Choose a new snapshot filename outside the checkout")
    source = knowledge_path("")
    original = validate_root(source)
    database = chroma_path()
    before = hashes(database)
    required_before = {relative: hashlib.sha256(knowledge_path(relative).read_bytes()).hexdigest() for relative in FILES}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tarot-full-snapshot-") as temporary:
        staging = Path(temporary)
        for relative in FILES:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(knowledge_path(relative), target)
        # Copy every index directory/file, then produce a consistent SQLite
        # backup (including any committed WAL state) using SQLite's backup API.
        copied_db = staging / "storage/chroma"
        shutil.copytree(database, copied_db)
        for name in ("chroma.sqlite3", "chroma.sqlite3-wal", "chroma.sqlite3-shm"):
            path = copied_db / name
            if path.exists():
                path.unlink()  # Only disposable staging copies, never source files.
        with sqlite3.connect(database.as_uri() + "/chroma.sqlite3?mode=ro", uri=True) as reader:
            with sqlite3.connect(copied_db / "chroma.sqlite3") as writer:
                reader.backup(writer)
                if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Snapshot SQLite integrity check failed")
        if before != hashes(database) or any(
            required_before[name] != hashlib.sha256(knowledge_path(name).read_bytes()).hexdigest()
            for name in FILES
        ):
            raise ValueError("Knowledge changed during snapshot; pause writers and retry")
        restored = validate_root(staging)
        if restored["counts"] != original["counts"]:
            raise ValueError("Snapshot collection counts changed")
        from importlib.metadata import version
        manifest = {
            "format_version": 2,
            "snapshot_kind": "complete_chroma_directory",
            "chromadb_version": version("chromadb"),
            "source_platform": platform.system() + "-" + platform.machine(),
            "files_sha256": hashes(staging),
            "collections": {key: value for key, value in restored["counts"].items() if isinstance(value, dict)},
            "ocr_pages": restored["counts"]["zhouyi_ocr_pages"],
        }
        (staging / "data/deployment_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with destination.open("xb") as raw:
            os.chmod(destination, 0o600)
            with tarfile.open(fileobj=raw, mode="w:gz") as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.add(path, arcname=str(path.relative_to(staging)), recursive=False)
    size = destination.stat().st_size
    summary = {
        "snapshot": str(destination), "bytes": size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "github_contents_api_suitable": size < 90 * 1024 * 1024,
        "counts": restored["counts"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build_snapshot(args.output)


if __name__ == "__main__":
    main()
