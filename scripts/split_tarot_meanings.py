
# scripts/split_tarot_meanings.py

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data/structured/tarot_card_texts.json"
OUTPUT = ROOT / "data/structured/tarot_meanings.json"
REPORT = ROOT / "data/structured/tarot_meanings_report.txt"

# 允许 REVERSED 字母之间存在任意空格
REVERSED = re.compile(
    r"(?<![A-Za-z])R\s*E\s*V\s*E\s*R\s*S\s*E\s*D(?![A-Za-z])",
    re.IGNORECASE,
)

# 仅处理明显的整行页眉、页脚
PAGE_NUMBER = re.compile(
    r"^\s*[\(\[�]\s*\d(?:[\d\s]*\d)?\s*[\)\]�]\s*$"
)


def normalize_letters(text):
    return re.sub(r"[^A-Z]", "", text.upper())


def clean_page(text):
    lines = text.splitlines()
    cleaned = []

    for line in lines:
        stripped = line.strip()
        compact = normalize_letters(stripped)

        if not stripped:
            cleaned.append("")
            continue

        # 常见的重复页眉
        if (
            "SEVENTYEIGHTDEGREESOFWISDOM" in compact
            and len(compact) < 65
        ):
            continue

        if (
            compact.startswith("THEMINORARCANA")
            and len(compact) < 60
        ):
            continue

        if (
            compact.startswith("THEMAJORARCANA")
            and len(compact) < 70
        ):
            continue

        if PAGE_NUMBER.fullmatch(stripped):
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def find_reversed_heading(text):
    """
    只匹配独立标题行，避免把正文中的
    'reversed' 当成章节分界。
    """
    offset = 0
    matches = []

    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        if stripped and REVERSED.fullmatch(stripped):
            matches.append({
                "offset": offset,
                "length": len(line),
                "heading": stripped,
            })

        offset += len(line)

    return matches


def split_card(card):
    pages = card["pages"]

    # 每页独立清理，再合并
    cleaned_pages = [
        {
            "pdf_page": page["pdf_page"],
            "text": clean_page(page["text"])
        }
        for page in pages
    ]

    # 建立字符偏移到 PDF 页码的映射
    spans = []
    texts = []
    offset = 0

    for page in cleaned_pages:
        text = page["text"]
        if not text:
            continue

        if texts:
            texts.append("\n\n")
            offset += 2

        start = offset
        texts.append(text)
        offset += len(text)

        spans.append({
            "start": start,
            "end": offset,
            "pdf_page": page["pdf_page"]
        })

    full_text = "".join(texts)
    headings = find_reversed_heading(full_text)

    if len(headings) == 1:
        heading = headings[0]
        position = heading["offset"]

        upright_text = full_text[:position].strip()
        reversed_text = full_text[
            position + heading["length"]:
        ].strip()

        status = "explicit_reversed_heading"

    elif len(headings) == 0:
        upright_text = full_text
        reversed_text = None
        status = "not_explicitly_separated"

    else:
        upright_text = full_text
        reversed_text = None
        status = "multiple_reversed_headings_review"

    return {
        "card_id": card["card_id"],
        "name_en": card["name_en"],
        "source": card["source"],
        "pdf_pages": [
            p["pdf_page"] for p in cleaned_pages if p["text"]
        ],
        "upright_text": upright_text,
        "reversed_text": reversed_text,
        "separation_status": status,
        "needs_review": True,
        "source_page_segments": cleaned_pages,
    }


def main():
    cards = json.loads(INPUT.read_text(encoding="utf-8"))
    output = {}

    for card_id, card in cards.items():
        output[card_id] = split_card(card)

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    counts = {}

    for item in output.values():
        status = item["separation_status"]
        counts[status] = counts.get(status, 0) + 1

    lines = [
        "TAROT MEANINGS EXTRACTION REPORT",
        "=" * 55,
        f"Total cards: {len(output)}",
    ]

    for status, count in counts.items():
        lines.append(f"{status}: {count}")

    lines.append("\nCARDS REQUIRING REVIEW")

    for card_id, item in output.items():
        if item["separation_status"] != "explicit_reversed_heading":
            lines.append(
                f"{card_id}: {item['separation_status']}"
            )

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("=" * 50)
    print("Total cards:", len(output))

    for status, count in counts.items():
        print(status, ":", count)

    print("Output:", OUTPUT)
    print("Report:", REPORT)
    print("=" * 50)


if __name__ == "__main__":
    main()
