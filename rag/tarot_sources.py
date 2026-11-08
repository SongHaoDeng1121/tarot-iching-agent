"""Tarot source registry and local document access."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "configs/tarot_sources.yaml"


@lru_cache(maxsize=4)
def load_source_registry(path: str | None = None) -> list[dict[str, Any]]:
    selected = path or os.getenv("TAROT_SOURCE_REGISTRY") or str(DEFAULT_REGISTRY)
    registry_path = Path(selected)
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    return [item for item in data["sources"] if item.get("enabled", True)]


@lru_cache(maxsize=16)
def load_source_chunks(path: str) -> list[dict[str, Any]]:
    chunk_path = Path(path)
    if not chunk_path.is_absolute():
        chunk_path = ROOT / chunk_path
    if not chunk_path.exists():
        return []
    return [
        json.loads(line)
        for line in chunk_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def registry_by_id() -> dict[str, dict[str, Any]]:
    return {item["source_id"]: item for item in load_source_registry()}


def greer_exact_evidence(
    card_id: str, orientation: str, max_chars: int = 7600
) -> dict[str, Any] | None:
    source = registry_by_id().get("greer_tarot_reversals")
    if not source:
        return None
    chunks = [
        item for item in load_source_chunks(source["chunks_path"])
        if item.get("card_id") == card_id
    ]
    if not chunks:
        return None
    primary = sorted(
        [item for item in chunks if item.get("orientation_context") == orientation],
        key=lambda item: item["chunk_index"],
    )
    background: list[dict[str, Any]] = []
    if orientation == "reversed":
        background = sorted(
            [item for item in chunks if item.get("orientation_context") == "upright"],
            key=lambda item: item["chunk_index"],
        )[:1]
    selected = background + primary
    if not selected:
        selected = sorted(chunks, key=lambda item: item["chunk_index"])
    parts: list[str] = []
    remaining = max_chars
    for item in selected:
        if remaining <= 0:
            break
        label = item.get("orientation_context", "general").upper()
        passage = item["text"][:remaining]
        parts.append(f"{label} CONTEXT (PDF {item['pdf_page_start']}-{item['pdf_page_end']}):\n{passage}")
        remaining -= len(passage)
    pages = sorted({
        page
        for item in selected
        for page in range(item["pdf_page_start"], item["pdf_page_end"] + 1)
    })
    sample = selected[0]
    return {
        "id": f"EXACT_GREER_{card_id}_{orientation.upper()}",
        "source_id": source["source_id"],
        "title": source["title"],
        "author": source["author"],
        "card_id": card_id,
        "name": sample["card_name"],
        "pages": pages,
        "text": "\n\n".join(parts),
        "separation_status": "explicit_upright_and_reversed_headings",
        "orientation_context": orientation,
        "evidence_chunk_ids": [item["chunk_id"] for item in selected],
    }
