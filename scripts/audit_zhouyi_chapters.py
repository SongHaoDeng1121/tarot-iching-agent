"""Compare the old resolver and corroborated boundaries for all 64 chapters."""
import argparse
import json
from pathlib import Path

from engines.hexagram_utils import HEXAGRAM_NAMES
from engines.yijing_cast import build_cast_result
from rag.zhouyi_exact import load_pages, find_chapter_heading, get_chapter, retrieve_cast_evidence


def audit():
    pages = load_pages()
    rows = []
    for number, name in enumerate(HEXAGRAM_NAMES, 1):
        row = {"number": number, "name": name}
        try:
            find_chapter_heading(pages, name)
            if number == 64:
                raise ValueError("Hexagram 64 requires a verified end boundary.")
            find_chapter_heading(pages, HEXAGRAM_NAMES[number])
            row["legacy_passed"] = True
        except ValueError as exc:
            row.update(legacy_passed=False, legacy_error=str(exc))
        try:
            chapter = get_chapter(pages, number)
            row.update(passed=True, boundaries=chapter["boundaries"], pages=[item["pdf_page"] for item in chapter["segments"]])
        except ValueError as exc:
            row.update(passed=False, error=str(exc))
        rows.append(row)
    cast = build_cast_result([8, 8, 6, 8, 7, 7])
    evidence = retrieve_cast_evidence(cast)
    return {
        "legacy_passed": sum(row["legacy_passed"] for row in rows),
        "passed": sum(row["passed"] for row in rows),
        "total": 64,
        "observed_cast": {"values": cast["line_values_bottom_to_top"], "original": 20, "changed": 53, "moving": cast["moving_line_labels"]},
        "observed_evidence": [{"type": item["type"], "name": item["name"], "pages": [segment["pdf_page"] for segment in item["segments"]]} for item in evidence],
        "chapters": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "chapters"}, ensure_ascii=False, indent=2))
    if result["passed"] != 64:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
