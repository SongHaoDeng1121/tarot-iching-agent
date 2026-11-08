"""Reproducible retrieval and boundary evaluation for the Greer integration."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import chromadb
import pymupdf

from rag.answer import load_cards
from rag.hybrid_tarot import retrieve_for_card
from rag.spread import prepare_exact_evidence
from rag.tarot_sources import load_source_chunks

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "reports/rag/greer_reversals_evaluation.json"
REPORT_MD = ROOT / "reports/rag/greer_reversals_evaluation.md"

CASES = [
    {
        "id": "A",
        "question": "How should The Magician reversed be interpreted when it appears in the Thoughts position?",
        "card_id": "the_magician",
        "card_name": "The Magician",
        "orientation": "reversed",
        "position": "Thoughts",
    },
    {
        "id": "B",
        "question": "What are possible interpretations of the Ten of Pentacles reversed?",
        "card_id": "ten_of_pentacles",
        "card_name": "Ten of Pentacles",
        "orientation": "reversed",
        "position": "Situation",
    },
    {
        "id": "C",
        "question": "How should the Queen of Pentacles upright be interpreted in the Feelings position?",
        "card_id": "queen_of_pentacles",
        "card_name": "Queen of Pentacles",
        "orientation": "upright",
        "position": "Feelings",
    },
    {
        "id": "D1",
        "question": "How do my thoughts, feelings, and actions interact in this situation?",
        "card_id": "five_of_pentacles",
        "card_name": "Five of Pentacles",
        "orientation": "upright",
        "position": "Thoughts",
    },
    {
        "id": "D2",
        "question": "How do my thoughts, feelings, and actions interact in this situation?",
        "card_id": "king_of_cups",
        "card_name": "King of Cups",
        "orientation": "upright",
        "position": "Feelings",
    },
    {
        "id": "D3",
        "question": "How do my thoughts, feelings, and actions interact in this situation?",
        "card_id": "four_of_pentacles",
        "card_name": "Four of Pentacles",
        "orientation": "upright",
        "position": "Actions",
    },
]


def evaluate(online: bool) -> dict[str, Any]:
    chunks = load_source_chunks("data/chunks/greer_tarot_reversals_chunks.jsonl")
    structure = json.loads(
        (ROOT / "data/structured/greer_tarot_reversals_sections.json").read_text(encoding="utf-8")
    )
    source_page_counts = {}
    for source_id, relative_path in {
        "greer_tarot_reversals": "data/raw/The complete book of tarot reversals.pdf",
        "pollack_78_degrees": "data/raw/tarot_78_degrees.pdf",
    }.items():
        with pymupdf.open(ROOT / relative_path) as pdf:
            source_page_counts[source_id] = len(pdf)
    source_text_pages = {}
    for source_id, relative_path in {
        "greer_tarot_reversals": "data/extracted/greer_tarot_reversals_pages.jsonl",
        "pollack_78_degrees": "data/extracted/tarot_pages.jsonl",
    }.items():
        page_records = [
            json.loads(line)
            for line in (ROOT / relative_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        source_text_pages[source_id] = {
            int(item["pdf_page"]): item["text"] for item in page_records
        }

    case_results = []
    correct_at_1 = 0
    correct_at_3 = 0
    citation_checks = 0
    citation_valid = 0
    for case in CASES:
        results = retrieve_for_card(
            question=case["question"],
            card_id=case["card_id"],
            card_name=case["card_name"],
            orientation=case["orientation"],
            position=case["position"],
            top_k=4,
            include_vectors=online,
        )
        tagged = [item for item in results if item.get("card_id")]
        at_1 = bool(tagged and tagged[0]["card_id"] == case["card_id"])
        at_3 = any(item.get("card_id") == case["card_id"] for item in results[:3])
        correct_at_1 += at_1
        correct_at_3 += at_3
        for item in results:
            citation_checks += 1
            pages = item.get("pages", [])
            page_count = source_page_counts.get(item["source_id"], 0)
            page_text = " ".join(
                source_text_pages.get(item["source_id"], {}).get(page, "")
                for page in pages
            )
            normalize = lambda value: re.sub(r"\W+", "", value).lower()
            snippet = normalize(item["text"])[:120]
            if (
                pages
                and all(1 <= page <= page_count for page in pages)
                and snippet
                and snippet in normalize(page_text)
            ):
                citation_valid += 1
        case_results.append({
            "case": case["id"],
            "expected_card": case["card_id"],
            "correct_tagged_card_at_1": at_1,
            "correct_card_at_3": at_3,
            "results": [
                {
                    "source_id": item["source_id"],
                    "card_id": item.get("card_id"),
                    "orientation_context": item.get("orientation_context"),
                    "pages": item.get("pages"),
                    "methods": item.get("retrieval_methods"),
                    "score": item.get("score"),
                }
                for item in results
            ],
        })

    cards_covered = {item["card_id"] for item in chunks if item.get("card_id")}
    ambiguous = [
        card_id for card_id, item in structure["cards"].items()
        if item.get("needs_review")
    ]
    duplicate_ids = len(chunks) - len({item["chunk_id"] for item in chunks})
    db = chromadb.PersistentClient(path=str(ROOT / "storage/chroma"))
    counts = {collection.name: collection.count() for collection in db.list_collections()}

    spread = json.loads(
        (ROOT / "data/spreads/greer_evaluation_three_card.json").read_text(encoding="utf-8")
    )
    exact = prepare_exact_evidence(spread, load_cards())
    source_pairs = {
        card["card_id"]: sorted({
            item["source_id"] for item in exact if item["card_id"] == card["card_id"]
        })
        for card in spread["cards"]
    }
    return {
        "online_vectors_enabled": online,
        "recognized_card_sections": len(structure["cards"]),
        "distinct_canonical_cards": len(cards_covered),
        "ambiguous_boundaries": ambiguous,
        "unmapped_sections": [
            card_id for card_id, item in structure["cards"].items()
            if item.get("status") != "detected"
        ],
        "chunk_count": len(chunks),
        "duplicate_chunk_ids": duplicate_ids,
        "correct_tagged_card_at_1": correct_at_1 / len(CASES),
        "correct_card_at_3": correct_at_3 / len(CASES),
        "citation_page_validity": citation_valid / max(citation_checks, 1),
        "citation_checks": citation_checks,
        "source_coverage_for_three_card_exact": source_pairs,
        "collection_counts": counts,
        "cases": case_results,
    }


def write_reports(result: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Greer reversals retrieval evaluation",
        "",
        f"- Online vectors enabled: {result['online_vectors_enabled']}",
        f"- Recognized card sections: {result['recognized_card_sections']}",
        f"- Distinct canonical cards: {result['distinct_canonical_cards']}",
        f"- Automatic low-confidence boundary flags: {len(result['ambiguous_boundaries'])}",
        f"- Unmapped sections: {len(result['unmapped_sections'])}",
        f"- Chunks: {result['chunk_count']}",
        f"- Duplicate chunk IDs: {result['duplicate_chunk_ids']}",
        f"- Correct tagged card at 1: {result['correct_tagged_card_at_1']:.3f}",
        f"- Correct card at 3: {result['correct_card_at_3']:.3f}",
        f"- Citation page validity: {result['citation_page_validity']:.3f} ({result['citation_checks']} checks)",
        "",
        "## Per-case results",
        "",
        "| Case | Expected | Card@1 | Card@3 | Top sources |",
        "|---|---|---|---|---|",
    ]
    for case in result["cases"]:
        sources = ", ".join(item["source_id"] for item in case["results"][:3])
        lines.append(
            f"| {case['case']} | {case['expected_card']} | "
            f"{'PASS' if case['correct_tagged_card_at_1'] else 'FAIL'} | "
            f"{'PASS' if case['correct_card_at_3'] else 'FAIL'} | {sources} |"
        )
    lines.extend([
        "",
        "## Notes",
        "",
        "- Pollack semantic chunks predate card metadata; Pollack card correctness is guaranteed by the separate exact-section evidence, not inferred from vector metadata.",
        "- The three boundary items below 0.95 automatic confidence were rendered and visually verified; the flags preserve text-layer uncertainty.",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.online)
    write_reports(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
