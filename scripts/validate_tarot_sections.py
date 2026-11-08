
# scripts/validate_tarot_sections.py

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INDEX = ROOT / "data/structured/tarot_sections_auto.json"
PAGES = ROOT / "data/extracted/tarot_pages.jsonl"

OUTPUT = ROOT / "data/structured/tarot_card_texts.json"
REPORT = ROOT / "data/structured/tarot_validation_report.txt"


def load_jsonl(path):
    result = {}

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                result[record["pdf_page"]] = record["text"]

    return result



def extract_section(card, pages):
    start_page = card.get("pdf_start_page")
    end_page = card.get("pdf_end_page")

    start_offset = card.get("start_offset")
    end_offset = card.get("end_offset_exclusive")

    if any(x is None for x in (
        start_page, end_page, start_offset, end_offset
    )):
        return None, "missing_boundary"

    start = (start_page, start_offset)
    end = (end_page, end_offset)

    if start >= end:
        return None, "invalid_boundary"

    parts = []

    for page_no in range(start_page, end_page + 1):

        # 跳过已核实没有提取文字的第276页
        if page_no not in pages:
            if (
                card["card_id"] == "ace_of_pentacles"
                and page_no == 276
            ):
                continue

            return None, f"missing_pdf_page_{page_no}"

        # 必须放在缺失页判断之后
        text = pages[page_no]

        if page_no == start_page and start_offset > len(text):
            return None, "invalid_start_offset"

        if page_no == end_page and end_offset > len(text):
            return None, "invalid_end_offset"

        left = start_offset if page_no == start_page else 0
        right = end_offset if page_no == end_page else len(text)

        if left < 0 or right < left:
            return None, "invalid_text_slice"

        segment = text[left:right]

        if segment.strip():
            parts.append({
                "pdf_page": page_no,
                "text": segment
            })

    if not parts:
        return None, "empty_section"

    return parts, "extracted"



def main():
    cards = json.loads(INDEX.read_text(encoding="utf-8"))
    pages = load_jsonl(PAGES)

    extracted = {}
    issues = []

    # 逐张检查章节边界和原文
    for card_id, card in cards.items():
        parts, status = extract_section(card, pages)

        if status != "extracted":
            issues.append(f"{card_id}: {status}")
            continue

        extracted[card_id] = {
            "card_id": card_id,
            "name_en": card["name_en"],
            "source": card["source"],
            "pdf_start_page": card["pdf_start_page"],
            "pdf_end_boundary_page": card["pdf_end_page"],
            "status": "boundary_extracted_unreviewed",
            "pages": parts,
        }

    # 检查自动标题的相对顺序
    ordered = sorted(
        [
            (
                card["pdf_start_page"],
                card["start_offset"],
                card_id
            )
            for card_id, card in cards.items()
            if card.get("pdf_start_page") is not None
            and card.get("start_offset") is not None
        ]
    )

    positions = [(p, o) for p, o, _ in ordered]

    if len(set(positions)) != len(positions):
        issues.append("Duplicate card heading positions found")

    # 比较已确定边界的章节，检查是否重叠
    for i in range(len(ordered) - 1):
        page, offset, card_id = ordered[i]
        next_page, next_offset, next_id = ordered[i + 1]

        card = cards[card_id]

        if card.get("pdf_end_page") is None:
            continue

        end = (
            card["pdf_end_page"],
            card["end_offset_exclusive"]
        )

        if end[0] is not None and end[1] is not None:
            if end > (next_page, next_offset):
                issues.append(
                    f"Overlap: {card_id} -> {next_id}"
                )

    OUTPUT.write_text(
        json.dumps(extracted, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    lines = [
        "TAROT CHAPTER VALIDATION",
        "=" * 60,
        f"Cards in index: {len(cards)}",
        f"Sections extracted: {len(extracted)}",
        f"Sections unresolved: {len(cards) - len(extracted)}",
        "",
        "ISSUES",
        *issues,
        "",
        "EXTRACTED SECTIONS",
    ]

    for card_id, item in extracted.items():
        char_count = sum(
            len(p["text"]) for p in item["pages"]
        )

        lines.append(
            f"{card_id}: "
            f"{len(item['pages'])} pages, "
            f"{char_count} characters"
        )

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("=" * 50)
    print("Cards:", len(cards))
    print("Extracted:", len(extracted))
    print("Unresolved:", len(cards) - len(extracted))
    print("Issues:", len(issues))
    print("Output:", OUTPUT)
    print("Report:", REPORT)
    print("=" * 50)


if __name__ == "__main__":
    main()
