"""Export an authorized private bundle with portable vectors (no embedding API).

The destination must be outside the checkout. Run only when legally permitted
to process these books on the selected private host and model providers.
"""
import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import chromadb

from rag.knowledge_check import FILES, COLLECTION_MANIFESTS, check_knowledge
from rag.runtime_data import ROOT, knowledge_path, chroma_path


def build_package(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError("Private bundle output must be outside the public checkout")
    if destination.exists():
        raise ValueError("Destination already exists; choose a new filename")
    result = check_knowledge()
    if not result["ready"]:
        raise ValueError("Knowledge preflight failed; run python -m rag.knowledge_check")
    db = chromadb.PersistentClient(path=str(chroma_path()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tarot-package-") as temporary:
        staging = Path(temporary)
        optional = (
            "data/extracted/tarot_pages.jsonl",
            "data/structured/tarot_sections.json",
            "data/structured/greer_tarot_reversals_sections.json",
        )
        for relative in (*FILES, *(name for name in optional if knowledge_path(name).is_file())):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(knowledge_path(relative), target)
        collections = {}
        for name in COLLECTION_MANIFESTS:
            collection = db.get_collection(name)
            target = staging / "storage/vector_exports" / f"{name}.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as output:
                for offset in range(0, collection.count(), 128):
                    batch = collection.get(limit=128, offset=offset, include=["documents", "metadatas", "embeddings"])
                    for index, record_id in enumerate(batch["ids"]):
                        output.write(json.dumps({
                            "id": record_id, "text": batch["documents"][index],
                            "metadata": batch["metadatas"][index],
                            "embedding": batch["embeddings"][index].tolist(),
                        }, ensure_ascii=False) + "\n")
            collections[name] = {"count": collection.count(), "dimension": 1024, "metadata": collection.metadata}
        checksums = {
            str(path.relative_to(staging)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in staging.rglob("*") if path.is_file()
        }
        manifest = {"format_version": 1, "files_sha256": checksums, "collections": collections}
        (staging / "data/deployment_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with destination.open("xb") as raw:
            with tarfile.open(fileobj=raw, mode="w:gz") as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.add(path, arcname=str(path.relative_to(staging)), recursive=False)
        destination.chmod(0o600)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"Private bundle: {destination}")
    print(f"KNOWLEDGE_BUNDLE_SHA256={digest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--rights-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.rights_confirmed:
        parser.error("Confirm you have rights to host/process this knowledge using --rights-confirmed")
    build_package(args.output)


if __name__ == "__main__":
    main()
