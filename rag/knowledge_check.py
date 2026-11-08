"""Offline preflight: fail before importing modules that load the knowledge base."""
import argparse
import json
from pathlib import Path

import chromadb

from rag.runtime_data import knowledge_path, chroma_path

FILES = (
    "data/structured/tarot_meanings.json",
    "data/structured/zhouyi_sections.json",
    "data/structured/hexagrams.json",
    "data/extracted/zhouyi_pages.jsonl",
    "data/chunks/zhouyi_index_ready.jsonl",
    "data/chunks/tarot_chunks.jsonl",
    "data/chunks/greer_tarot_reversals_chunks.jsonl",
)
COLLECTION_MANIFESTS = {
    "tarot_bge_m3_v1": ("data/chunks/tarot_chunks.jsonl", "id"),
    "zhouyi_bge_m3_v1": ("data/chunks/zhouyi_index_ready.jsonl", "id"),
    "tarot_greer_reversals_bge_m3_v1": ("data/chunks/greer_tarot_reversals_chunks.jsonl", "chunk_id"),
}


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def check_knowledge():
    errors, warnings, counts = [], [], {}
    missing = [relative for relative in FILES if not knowledge_path(relative).is_file()]
    if not (chroma_path() / "chroma.sqlite3").is_file():
        missing.append("storage/chroma/chroma.sqlite3")
    if missing:
        return {"ready": False, "errors": [f"Missing private data: {name}" for name in missing], "warnings": [], "counts": {}}
    try:
        meanings = json.loads(knowledge_path(FILES[0]).read_text(encoding="utf-8"))
        if len(meanings) != 78:
            errors.append("Tarot meanings must contain 78 canonical cards")
        for card in meanings.values():
            if not card.get("upright_text") or not card.get("pdf_pages"):
                errors.append("Tarot exact evidence is incomplete")
                break
        ocr = jsonl(knowledge_path("data/extracted/zhouyi_pages.jsonl"))
        page_ids = [item["pdf_page"] for item in ocr]
        if any(type(page) is not int or page < 1 for page in page_ids) or len(set(page_ids)) != len(page_ids):
            errors.append("OCR page numbers must be unique positive integers")
        if not ocr or any(not isinstance(item.get("text"), str) for item in ocr):
            errors.append("OCR text data is invalid")
        pages = set(page_ids)
        sections = json.loads(knowledge_path("data/structured/zhouyi_sections.json").read_text(encoding="utf-8"))
        expected_pages = int(sections["source_page_count"])
        if pages != set(range(1, expected_pages + 1)):
            errors.append("OCR page coverage differs from the source page count")
        if len(sections["hexagrams"]) != 64:
            errors.append("Zhouyi section map must contain 64 hexagrams")
        # Open only an existing DB. This never creates a missing collection.
        db = chromadb.PersistentClient(path=str(chroma_path()))
        available = {collection.name for collection in db.list_collections()}
        for name, (relative, id_field) in COLLECTION_MANIFESTS.items():
            records = jsonl(knowledge_path(relative))
            ids = [item[id_field] for item in records]
            if not ids or len(ids) != len(set(ids)):
                errors.append(f"{name}: active IDs are empty or duplicated")
            if any(not item.get("text", "").strip() for item in records):
                errors.append(f"{name}: empty text in active manifest")
            if name not in available:
                errors.append(f"Missing collection: {name}")
                continue
            collection = db.get_collection(name)
            stored = set(collection.get(include=[])["ids"])
            counts[name] = {"stored": collection.count(), "active": len(ids)}
            if set(ids) - stored:
                errors.append(f"{name}: {len(set(ids) - stored)} active IDs absent from collection")
            if stored - set(ids):
                warnings.append(f"{name}: {len(stored - set(ids))} extra stored IDs (current active manifest remains authoritative)")
            sample = collection.peek(limit=1)
            vectors = sample.get("embeddings")
            if vectors is None or len(vectors) == 0 or len(vectors[0]) != 1024:
                errors.append(f"{name}: expected 1024-dimensional embeddings")
            else:
                # Exercise ANN access using an existing stored vector; no model/API.
                collection.query(query_embeddings=[vectors[0].tolist()], n_results=1, include=[])
            expected_text = {item[id_field]: item["text"] for item in records}
            for start in range(0, len(ids), 128):
                found = collection.get(ids=ids[start:start + 128], include=["documents", "metadatas"])
                for record_id, text, metadata in zip(found["ids"], found["documents"], found["metadatas"]):
                    if text != expected_text[record_id]:
                        errors.append(f"{name}: indexed content differs from active manifest")
                        break
                    if name == "tarot_greer_reversals_bge_m3_v1":
                        import hashlib
                        if (metadata or {}).get("content_sha256") != hashlib.sha256(text.encode()).hexdigest():
                            errors.append("Greer indexed content hash is invalid")
                            break
            if name == "zhouyi_bge_m3_v1" and any(item.get("pdf_page") not in pages for item in records):
                errors.append("Zhouyi chunks refer to missing OCR pages")
            if name == "tarot_greer_reversals_bge_m3_v1":
                if {item.get("card_id") for item in records if item.get("card_id")} != set(meanings):
                    errors.append("Greer active manifest does not cover the 78 canonical cards")
        counts["zhouyi_ocr_pages"] = len(pages)
    except Exception as exc:
        # Never include document text, remote URLs, or credentials in diagnostics.
        errors.append(f"Knowledge validation failed: {type(exc).__name__}")
    return {"ready": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = check_knowledge()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
