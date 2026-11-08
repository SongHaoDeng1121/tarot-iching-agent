
# scripts/locate_zhouyi_evidence.py

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES_FILE = (
    ROOT / "data/extracted/zhouyi_pages.jsonl"
)


def load_pages():
    pages = {}

    with PAGES_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)

            pages[int(item["pdf_page"])] = item["text"]

    return pages


def find_matches(pages, pattern, label, limit=20):
    """
    Search OCR pages and show text around each match.
    """

    print(f"\n===== {label} =====")

    regex = re.compile(pattern, re.MULTILINE)

    count = 0

    for page in sorted(pages):
        text = pages[page]

        for match in regex.finditer(text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 180)

            snippet = text[start:end]
            snippet = re.sub(r"\s+", " ", snippet)

            print(f"\nPDF page: {page}")
            print(snippet)

            count += 1

            if count >= limit:
                print("\nReached display limit.")
                return

    print(f"\nMatches displayed: {count}")


def main():
    pages = load_pages()

    print("Loaded PDF pages:", len(pages))

    # 屯卦章首
    find_matches(
        pages,
        r"^\s*屯\s*[（(：:]",
        "TUN CHAPTER HEADINGS",
    )

    # 屯上六的关键字与可能的OCR变体
    find_matches(
        pages,
        r"泣\s*血|涟\s*如|漣\s*如",
        "TUN UPPER-SIX PASSAGE CANDIDATES",
    )

    # 益卦章首
    find_matches(
        pages,
        r"^\s*益\s*[（(：:]",
        "YI CHAPTER HEADINGS",
    )

    # 显示屯卦附近的上六候选
    print("\n===== UPPER SIX NEAR TUN =====")

    for page in range(64, 77):
        text = pages.get(page, "")

        for match in re.finditer(r"上\s*六", text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 350)

            snippet = re.sub(
                r"\s+",
                " ",
                text[start:end],
            )

            print(f"\nPDF page: {page}")
            print(snippet)


if __name__ == "__main__":
    main()
