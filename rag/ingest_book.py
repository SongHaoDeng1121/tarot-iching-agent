"""Config-driven, non-destructive ingestion for Tarot reference books.

The first parser targets Mary K. Greer's *The Complete Book of Tarot
Reversals*.  The output schema and indexing path are source-neutral so a
future parser can be registered without changing the retriever.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import chromadb
import pymupdf
import yaml
from dotenv import load_dotenv
from openai import OpenAI

from rag.tarot_catalog import (
    CARD_BY_ID,
    ORDERED_CARDS,
    card_metadata,
    compact_heading,
    source_heading_aliases,
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True, order=True)
class Pointer:
    pdf_page: int
    offset: int


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["_config_path"] = str(config_path)
    return data


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def clean_extracted_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def printed_page(pdf_page: int, offset: int) -> int | None:
    value = pdf_page + offset
    return value if value > 0 else None


def extract_pages(config: dict[str, Any]) -> list[dict[str, Any]]:
    pdf_path = resolve_path(config["pdf_path"])
    output = resolve_path(config["outputs"]["pages"])
    output.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    with pymupdf.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            warnings: list[str] = []
            text = clean_extracted_text(page.get_text("text", sort=True))
            if not text:
                warnings.append("empty_native_text")
            records.append({
                "source_id": config["source_id"],
                "pdf_page": index,
                "printed_page": printed_page(
                    index, int(config["printed_page_offset"])
                ),
                "text": text,
                "extraction_method": "pymupdf_native_text",
                "warnings": warnings,
            })

    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    nonempty = sum(bool(item["text"]) for item in records)
    print(f"Extracted {len(records)} pages ({nonempty} with native text)")
    print(f"Page output: {output}")
    return records


def read_pages(config: dict[str, Any]) -> list[dict[str, Any]]:
    path = resolve_path(config["outputs"]["pages"])
    if not path.exists():
        return extract_pages(config)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _line_records(text: str) -> Iterable[tuple[str, int]]:
    offset = 0
    for line in text.splitlines(keepends=True):
        raw = line.strip()
        if raw:
            leading = len(line) - len(line.lstrip())
            yield raw, offset + leading
        offset += len(line)


def _heading_match(line: str, aliases: list[str]) -> tuple[str, float] | None:
    if len(line) > 90:
        return None
    actual = compact_heading(line)
    expected_aliases = sorted(
        {compact_heading(alias) for alias in aliases}, key=len, reverse=True
    )
    for expected in expected_aliases:
        if actual == expected:
            return "upright", 0.99
        if actual == expected + "REVERSED":
            return "reversed", 0.99
    for expected in expected_aliases:
        # Rotated image labels sometimes precede the visible heading in the
        # text layer.  Suffix matching is retained but reported for review.
        if actual.endswith(expected + "REVERSED"):
            return "reversed", 0.85
        if actual.endswith(expected):
            return "upright", 0.85
    for expected in expected_aliases:
        if expected + "REVERSED" in actual:
            return "reversed", 0.75
        if expected in actual and len(actual) <= len(expected) + 18:
            return "upright", 0.75
    return None


def detect_card_markers(
    config: dict[str, Any], pages: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    limits = config["card_interpretation_range"]
    start_page = int(limits["start_pdf_page"])
    end_page = int(limits["end_pdf_page"])
    candidates: dict[str, dict[str, list[dict[str, Any]]]] = {
        card_id: {"upright": [], "reversed": []}
        for card_id, _ in ORDERED_CARDS
    }

    for page in pages:
        page_no = int(page["pdf_page"])
        if not start_page <= page_no <= end_page:
            continue
        page_lines = list(_line_records(page["text"]))
        for line_index, (line, offset) in enumerate(page_lines):
            variants = [(line, 1.0)]
            if (
                line_index + 1 < len(page_lines)
                and compact_heading(page_lines[line_index + 1][0]) == "REVERSED"
            ):
                variants.append((line + " Reversed", 0.75))
            for candidate_line, confidence_cap in variants:
                for card_id, card_name in ORDERED_CARDS:
                    match = _heading_match(
                        candidate_line, source_heading_aliases(card_id, card_name)
                    )
                    if not match:
                        continue
                    orientation, confidence = match
                    candidates[card_id][orientation].append({
                        "pdf_page": page_no,
                        "offset": offset,
                        "heading": candidate_line,
                        "confidence": min(confidence, confidence_cap),
                    })

    selected: dict[str, dict[str, Any]] = {}
    previous = Pointer(start_page, -1)
    for card_id, card_name in ORDERED_CARDS:
        upright_options = sorted(
            candidates[card_id]["upright"],
            key=lambda item: (item["pdf_page"], item["offset"]),
        )
        upright_options = [
            item for item in upright_options
            if Pointer(item["pdf_page"], item["offset"]) > previous
        ]
        if not upright_options:
            selected[card_id] = {
                "card_id": card_id,
                "card_name": card_name,
                "status": "missing_upright_heading",
                "needs_review": True,
            }
            continue
        upright = upright_options[0]
        up_pointer = Pointer(upright["pdf_page"], upright["offset"])
        reversed_options = sorted(
            candidates[card_id]["reversed"],
            key=lambda item: (item["pdf_page"], item["offset"]),
        )
        reversed_options = [
            item for item in reversed_options
            if Pointer(item["pdf_page"], item["offset"]) > up_pointer
        ]
        reversed_marker = reversed_options[0] if reversed_options else None
        confidence = min(
            upright["confidence"],
            reversed_marker["confidence"] if reversed_marker else 0.0,
        )
        selected[card_id] = {
            "card_id": card_id,
            "card_name": card_name,
            **card_metadata(card_id),
            "status": "detected" if reversed_marker else "missing_reversed_heading",
            "needs_review": confidence < 0.95,
            "mapping_confidence": round(confidence, 2),
            "upright_heading": upright,
            "reversed_heading": reversed_marker,
        }
        previous = up_pointer

    ordered_detected = [
        selected[card_id]
        for card_id, _ in ORDERED_CARDS
        if selected[card_id].get("upright_heading")
    ]
    terminal = Pointer(int(limits["end_boundary_pdf_page"]), 0)
    pages_by_number = {int(item["pdf_page"]): item for item in pages}
    end_overrides: dict[str, Pointer] = {}
    for card_id, marker in config.get("card_end_markers", {}).items():
        page_no = int(marker["pdf_page"])
        pattern = re.compile(marker["line_pattern"], re.I)
        match = next(
            (
                Pointer(page_no, offset)
                for line, offset in _line_records(pages_by_number[page_no]["text"])
                if pattern.search(line.strip())
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"Configured end marker not found for {card_id}")
        end_overrides[card_id] = (
            Pointer(page_no, 0) if marker.get("end_at_page_start") else match
        )
    for index, section in enumerate(ordered_detected):
        start = section["upright_heading"]
        reversed_marker = section.get("reversed_heading")
        next_pointer = terminal
        if index + 1 < len(ordered_detected):
            next_start = ordered_detected[index + 1]["upright_heading"]
            next_pointer = Pointer(next_start["pdf_page"], next_start["offset"])
        if section["card_id"] in end_overrides:
            next_pointer = end_overrides[section["card_id"]]
            section["end_boundary_source"] = "configured_verified_text_marker"
        else:
            section["end_boundary_source"] = "next_card_heading"
        section["start"] = start
        section["end_exclusive"] = {
            "pdf_page": next_pointer.pdf_page,
            "offset": next_pointer.offset,
        }
        if reversed_marker:
            rev_pointer = Pointer(
                reversed_marker["pdf_page"], reversed_marker["offset"]
            )
            section["orientation_spans"] = {
                "upright": {
                    "start": start,
                    "end_exclusive": {
                        "pdf_page": rev_pointer.pdf_page,
                        "offset": rev_pointer.offset,
                    },
                },
                "reversed": {
                    "start": reversed_marker,
                    "end_exclusive": {
                        "pdf_page": next_pointer.pdf_page,
                        "offset": next_pointer.offset,
                    },
                },
            }
    return selected


def write_structure(
    config: dict[str, Any], pages: list[dict[str, Any]]
) -> dict[str, Any]:
    cards = detect_card_markers(config, pages)
    result = {
        "source_id": config["source_id"],
        "title": config["title"],
        "author": config["author"],
        "pdf_page_count": len(pages),
        "printed_page_offset": int(config["printed_page_offset"]),
        "general_sections": [
            {
                **section,
                "confidence": section.get("confidence", 0.99),
                "boundary_source": section.get(
                    "boundary_source", "verified_heading_and_contents"
                ),
            }
            for section in config["general_sections"]
        ],
        "cards": cards,
    }
    output = resolve_path(config["outputs"]["sections"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_boundary_report(config, result)
    detected = sum(item.get("status") == "detected" for item in cards.values())
    print(f"Detected complete upright/reversed boundaries: {detected}/78")
    print(f"Structure output: {output}")
    return result


def read_structure(
    config: dict[str, Any], pages: list[dict[str, Any]]
) -> dict[str, Any]:
    path = resolve_path(config["outputs"]["sections"])
    if not path.exists():
        return write_structure(config, pages)
    return json.loads(path.read_text(encoding="utf-8"))


def write_boundary_report(config: dict[str, Any], structure: dict[str, Any]) -> None:
    path = resolve_path(config["outputs"]["boundary_report"])
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Greer reversals boundary audit",
        "",
        f"- PDF pages: {structure['pdf_page_count']}",
        f"- Printed-page offset: PDF page {abs(structure['printed_page_offset'])} pages ahead of printed page",
        "- Extraction: native PyMuPDF text; no whole-book OCR used",
        "- End boundaries are exclusive and point to the next card heading.",
        "",
        "| Card | Upright start | Reversed start | End exclusive | Confidence | Review |",
        "|---|---:|---:|---:|---:|---|",
    ]
    unresolved: list[str] = []
    for card_id, _ in ORDERED_CARDS:
        item = structure["cards"][card_id]
        up = item.get("upright_heading") or {}
        rev = item.get("reversed_heading") or {}
        end = item.get("end_exclusive") or {}
        review = "yes" if item.get("needs_review") else "no"
        if item.get("status") != "detected" or item.get("needs_review"):
            unresolved.append(f"- {card_id}: {item.get('status')}, confidence={item.get('mapping_confidence')}")
        lines.append(
            f"| {item['card_name']} | {up.get('pdf_page', '-')}:{up.get('offset', '-')} "
            f"| {rev.get('pdf_page', '-')}:{rev.get('offset', '-')} "
            f"| {end.get('pdf_page', '-')}:{end.get('offset', '-')} "
            f"| {item.get('mapping_confidence', 0):.2f} | {review} |"
        )
    lines.extend(["", "## Automatic low-confidence items", ""])
    lines.extend(unresolved or ["None."])
    lines.extend([
        "",
        "## Calibration notes",
        "",
        "- Major Arcana transitions were checked at PDF pages 54-60.",
        "- Number-card transition was checked at PDF pages 109-114.",
        "- Court-card transition was checked at PDF pages 190-194.",
        "- Page images show upright and reversed headings can share one PDF page; offsets therefore control boundaries.",
        "- Hierophant, Hermit, and Moon reversed headings were rendered and visually verified; their flags preserve text-layer uncertainty.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pointer(value: dict[str, Any]) -> Pointer:
    return Pointer(int(value["pdf_page"]), int(value["offset"]))


def slice_fragments(
    pages_by_number: dict[int, dict[str, Any]],
    start: Pointer,
    end: Pointer,
) -> list[tuple[int, str]]:
    fragments: list[tuple[int, str]] = []
    for page_no in range(start.pdf_page, end.pdf_page + 1):
        if page_no not in pages_by_number:
            continue
        text = pages_by_number[page_no]["text"]
        left = start.offset if page_no == start.pdf_page else 0
        right = end.offset if page_no == end.pdf_page else len(text)
        if page_no == end.pdf_page and right == 0:
            continue
        fragment = text[left:right].strip()
        if fragment:
            fragments.append((page_no, fragment))
    return fragments


def _split_long_unit(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    output: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                output.append(current)
                current = ""
            output.extend(
                sentence[index:index + max_chars]
                for index in range(0, len(sentence), max_chars)
            )
        elif len(current) + len(sentence) + 1 <= max_chars:
            current += (" " if current else "") + sentence
        else:
            output.append(current)
            current = sentence
    if current:
        output.append(current)
    return output


def make_chunks_from_fragments(
    fragments: list[tuple[int, str]],
    max_chars: int,
    min_chars: int,
    overlap_paragraphs: int,
) -> list[dict[str, Any]]:
    units: list[tuple[int, str]] = []
    for page_no, fragment in fragments:
        paragraphs = [
            item.strip()
            for item in re.split(r"\n\s*\n", fragment)
            if item.strip()
        ]
        for paragraph in paragraphs:
            for piece in _split_long_unit(paragraph, max_chars):
                units.append((page_no, piece))

    chunks: list[dict[str, Any]] = []
    current: list[tuple[int, str]] = []
    current_size = 0
    index = 0
    while index < len(units):
        page_no, text = units[index]
        addition = len(text) + (2 if current else 0)
        if current and current_size + addition > max_chars:
            merged = "\n\n".join(item[1] for item in current)
            if len(merged) >= min_chars:
                chunks.append({
                    "text": merged,
                    "pdf_page_start": min(item[0] for item in current),
                    "pdf_page_end": max(item[0] for item in current),
                })
            current = current[-overlap_paragraphs:] if overlap_paragraphs else []
            current_size = sum(len(item[1]) + 2 for item in current)
            # A retained overlap unit may itself leave no room for the next
            # paragraph. Drop overlap in that case so the loop always makes
            # forward progress.
            if current and current_size + len(text) + 2 > max_chars:
                current = []
                current_size = 0
            continue
        current.append((page_no, text))
        current_size += addition
        index += 1
    if current:
        merged = "\n\n".join(item[1] for item in current)
        if len(merged) >= min_chars:
            chunks.append({
                "text": merged,
                "pdf_page_start": min(item[0] for item in current),
                "pdf_page_end": max(item[0] for item in current),
            })
    return chunks


def _chunk_record(
    config: dict[str, Any],
    base: dict[str, Any],
    chunk: dict[str, Any],
    chunk_index: int,
) -> dict[str, Any]:
    stable_key = (
        f"{config['source_id']}|{base['section_id']}|"
        f"{base.get('orientation_context')}|{chunk_index:03d}"
    )
    chunk_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    content_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
    offset = int(config["printed_page_offset"])
    return {
        "source_id": config["source_id"],
        "title": config["title"],
        "author": config["author"],
        **base,
        "pdf_page_start": chunk["pdf_page_start"],
        "pdf_page_end": chunk["pdf_page_end"],
        "printed_page_start": printed_page(chunk["pdf_page_start"], offset),
        "printed_page_end": printed_page(chunk["pdf_page_end"], offset),
        "chunk_index": chunk_index,
        "chunk_id": chunk_id,
        "content_sha256": content_hash,
        "text": chunk["text"],
    }


def build_chunks(
    config: dict[str, Any],
    pages: list[dict[str, Any]],
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    cards = structure["cards"]
    incomplete = [
        card_id for card_id, item in cards.items()
        if item.get("status") != "detected"
    ]
    if incomplete:
        raise RuntimeError(
            "Refusing to chunk before all card boundaries validate: "
            + ", ".join(incomplete)
        )

    settings = config["chunking"]
    pages_by_number = {int(item["pdf_page"]): item for item in pages}
    records: list[dict[str, Any]] = []

    for card_id, card_name in ORDERED_CARDS:
        section = cards[card_id]
        for orientation in ("upright", "reversed"):
            span = section["orientation_spans"][orientation]
            fragments = slice_fragments(
                pages_by_number, _pointer(span["start"]), _pointer(span["end_exclusive"])
            )
            chunks = make_chunks_from_fragments(
                fragments,
                int(settings["max_chars"]),
                int(settings["min_chars"]),
                int(settings["overlap_paragraphs"]),
            )
            meta = card_metadata(card_id)
            base = {
                "section_id": f"{card_id}_{orientation}",
                "section_title": f"{card_name} {'Reversed' if orientation == 'reversed' else 'Upright'}",
                "section_type": "card_interpretation",
                "card_id": card_id,
                **meta,
                "orientation_context": orientation,
                "is_card_specific": True,
                "mapping_confidence": section["mapping_confidence"],
                "mapping_uncertain": bool(section["needs_review"]),
            }
            records.extend(
                _chunk_record(config, base, chunk, index)
                for index, chunk in enumerate(chunks)
            )

    for section in config["general_sections"]:
        fragments = [
            (page_no, pages_by_number[page_no]["text"])
            for page_no in range(
                int(section["start_pdf_page"]),
                int(section["end_pdf_page"]) + 1,
            )
            if page_no in pages_by_number and pages_by_number[page_no]["text"]
        ]
        chunks = make_chunks_from_fragments(
            fragments,
            int(settings["max_chars"]),
            int(settings["min_chars"]),
            int(settings["overlap_paragraphs"]),
        )
        base = {
            "section_id": section["id"],
            "section_title": section["title"],
            "section_type": section["section_type"],
            "card_id": None,
            "card_name": None,
            "arcana": None,
            "suit": None,
            "rank": None,
            "orientation_context": "general",
            "is_card_specific": False,
            "mapping_confidence": 1.0,
            "mapping_uncertain": False,
        }
        records.extend(
            _chunk_record(config, base, chunk, index)
            for index, chunk in enumerate(chunks)
        )

    output = resolve_path(config["outputs"]["chunks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    duplicates = len(records) - len({item["chunk_id"] for item in records})
    print(f"Created {len(records)} chunks; duplicate IDs: {duplicates}")
    print(f"Chunk output: {output}")
    return records


def read_chunks(config: dict[str, Any]) -> list[dict[str, Any]]:
    path = resolve_path(config["outputs"]["chunks"])
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def chroma_metadata(record: dict[str, Any], model: str) -> dict[str, Any]:
    fields = (
        "source_id", "title", "author", "section_id", "section_title",
        "section_type", "card_id", "card_name", "arcana", "suit", "rank",
        "orientation_context", "is_card_specific", "mapping_confidence",
        "mapping_uncertain", "pdf_page_start", "pdf_page_end",
        "printed_page_start", "printed_page_end", "chunk_index",
        "content_sha256",
    )
    metadata = {key: record.get(key) for key in fields}
    metadata = {key: value for key, value in metadata.items() if value is not None}
    metadata["model"] = model
    return metadata


def index_chunks(config: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is missing from the project environment")
    model = config["embedding_model"]
    expected_dimension = int(config["embedding_dimension"])
    collection_name = config["collection"]
    estimated_tokens = math.ceil(sum(len(item["text"]) for item in records) / 4)
    print(f"Chunks eligible for embedding: {len(records)}")
    print(f"Approximate token count: {estimated_tokens:,}")
    print("This operation calls the configured embedding API and may incur API costs.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.siliconflow.cn/v1",
        timeout=90.0,
        max_retries=4,
    )
    db = chromadb.PersistentClient(path=str(ROOT / "storage/chroma"))
    collection = db.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )
    log_path = resolve_path(config["outputs"]["index_log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    success = 0
    failed = 0
    skipped = 0
    batch_size = 8

    with log_path.open("a", encoding="utf-8") as log:
        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            ids = [item["chunk_id"] for item in batch]
            existing = collection.get(ids=ids, include=["metadatas"])
            hashes = {
                item_id: (meta or {}).get("content_sha256")
                for item_id, meta in zip(existing["ids"], existing["metadatas"])
            }
            pending = [
                item for item in batch
                if hashes.get(item["chunk_id"]) != item["content_sha256"]
            ]
            skipped += len(batch) - len(pending)
            if not pending:
                continue
            try:
                response = client.embeddings.create(
                    model=model, input=[item["text"] for item in pending]
                )
                vectors: list[list[float] | None] = [None] * len(pending)
                for item in response.data:
                    vectors[item.index] = item.embedding
                if any(
                    vector is None or len(vector) != expected_dimension
                    for vector in vectors
                ):
                    raise ValueError("Embedding response dimension is incomplete or unexpected")
                collection.upsert(
                    ids=[item["chunk_id"] for item in pending],
                    documents=[item["text"] for item in pending],
                    embeddings=vectors,  # type: ignore[arg-type]
                    metadatas=[chroma_metadata(item, model) for item in pending],
                )
                success += len(pending)
                event = {
                    "batch_start": start,
                    "status": "success",
                    "count": len(pending),
                    "collection_count": collection.count(),
                }
            except Exception as exc:
                failed += len(pending)
                event = {
                    "batch_start": start,
                    "status": "failed",
                    "count": len(pending),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps(event, ensure_ascii=False), flush=True)
            time.sleep(0.4)

    result = {
        "collection": collection_name,
        "collection_count": collection.count(),
        "embedded": success,
        "skipped_unchanged": skipped,
        "failed": failed,
        "estimated_tokens": estimated_tokens,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a configured Tarot book")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--stage",
        choices=("extract", "structure", "chunk", "index", "all"),
        default="all",
    )
    parser.add_argument(
        "--allow-paid-api",
        action="store_true",
        help="Required before the index stage can call the embedding API",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if config.get("parser") != "greer_reversals":
        raise SystemExit(f"Unsupported parser: {config.get('parser')}")

    pages: list[dict[str, Any]] | None = None
    structure: dict[str, Any] | None = None
    records: list[dict[str, Any]] | None = None

    if args.stage in {"extract", "all"}:
        pages = extract_pages(config)
    if args.stage in {"structure", "all"}:
        pages = pages or read_pages(config)
        structure = write_structure(config, pages)
    if args.stage in {"chunk", "all"}:
        pages = pages or read_pages(config)
        structure = structure or read_structure(config, pages)
        records = build_chunks(config, pages, structure)
    if args.stage in {"index", "all"}:
        records = records or read_chunks(config)
        if not args.allow_paid_api:
            estimated = math.ceil(sum(len(item["text"]) for item in records) / 4)
            print(f"Chunks eligible for embedding: {len(records)}")
            print(f"Approximate token count: {estimated:,}")
            print("Indexing paused: rerun with --allow-paid-api to authorize the remote embedding call.")
            return
        index_chunks(config, records)


if __name__ == "__main__":
    main()
