
# rag/zhouyi_exact.py
# Exact hexagram and moving-line retrieval from OCR pages

import json
import re
import argparse
from pathlib import Path
from rag.runtime_data import knowledge_path

from engines.hexagram_utils import HEXAGRAM_NAMES

ROOT = Path(__file__).resolve().parents[1]
PAGES_FILE = knowledge_path("data/extracted/zhouyi_pages.jsonl")

LINE_LABELS = (
    "初九", "初六", "九二", "六二",
    "九三", "六三", "九四", "六四",
    "九五", "六五", "上九", "上六",
)


def load_pages():
    pages = {}

    with PAGES_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                pages[int(item["pdf_page"])] = item["text"]

    return pages



def find_chapter_heading(pages, name):
    """
    Locate a hexagram chapter heading in OCR text.

    Accept examples such as:
        中孚（ ）
        中孚（某个乱码）
        中孚？
        中孚
        中 孚

    A valid candidate must be followed by 【题解】.
    Do not silently guess chapter boundaries.
    """
    import re

    compact_name = r"\s*".join(
        re.escape(char) for char in name
    )

    candidates = []

    for page in sorted(pages):
        content = pages[page]

        # Require the hexagram title near the start
        # of a line, rather than inside a paragraph.
        pattern = re.compile(
            rf"(?m)^[ \t]*({compact_name})"
            rf"[^\n]{{0,35}}$"
        )

        for match in pattern.finditer(content):

            # Examine only text immediately following
            # the heading line.
            following = content[
                match.end():match.end() + 200
            ]

            if re.match(
                r"\s*【\s*题\s*解\s*】",
                following,
            ):
                candidates.append(
                    (page, match.start())
                )

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise ValueError(
            f"无法定位《{name}》章首："
            "OCR标题可能有错字或题解标记缺失。"
            "请运行章节诊断脚本。"
        )

    raise ValueError(
        f"《{name}》找到多个候选章首：{candidates}。"
        "为避免跨卦引用，请人工核对。"
    )


def get_chapter(pages, number):
    """
    Locate a chapter using its heading and
    the next King Wen hexagram heading.

    Return page-aware segments.
    """
    if not 1 <= number <= 64:
        raise ValueError("Hexagram number must be 1-64")

    name = HEXAGRAM_NAMES[number - 1]
    start_page, start_offset = find_chapter_heading(
        pages, name
    )

    if number < 64:
        next_name = HEXAGRAM_NAMES[number]
        end_page, end_offset = find_chapter_heading(
            pages, next_name
        )
    else:
        # Do not guess where the final chapter ends.
        raise ValueError(
            "Hexagram 64 requires a verified end boundary."
        )

    if (end_page, end_offset) <= (start_page, start_offset):
        raise ValueError(
            f"Invalid chapter boundaries for 《{name}》"
        )

    segments = []

    for page in range(start_page, end_page + 1):
        text = pages.get(page)

        if text is None:
            raise ValueError(
                f"OCR page {page} is missing"
            )

        start = start_offset if page == start_page else 0
        end = end_offset if page == end_page else len(text)

        content = text[start:end]

        if content.strip():
            segments.append({
                "pdf_page": page,
                "text": content,
            })

    return {
        "number": number,
        "name": name,
        "segments": segments,
    }


def extract_text_window(segments, start, max_chars):
    """
    Extract text while retaining exact PDF page origins.
    """
    pieces = []
    current = 0

    for segment in segments:
        text = segment["text"]
        end = current + len(text)

        if end > start and current < start + max_chars:
            local_start = max(0, start - current)
            local_end = min(
                len(text),
                start + max_chars - current,
            )

            part = text[local_start:local_end]

            if part.strip():
                pieces.append({
                    "pdf_page": segment["pdf_page"],
                    "text": part,
                })

        current = end

    return pieces



def find_moving_line(chapter, label):
    """
    Extract a moving-line passage from its verified chapter.

    Includes:
      - 爻辞
      - 注释
      - 译文
      - 小象传
      - 评析

    For 上六/上九, continue to the end of the
    current hexagram chapter.

    For other lines, stop at the next actual
    line-position heading.
    """

    if label not in LINE_LABELS:
        raise ValueError(f"Invalid line label: {label}")

    segments = chapter["segments"]

    full_text = "".join(
        segment["text"]
        for segment in segments
    )

    label_pattern = r"\s*".join(
        re.escape(char)
        for char in label
    )

    heading_pattern = re.compile(
        rf"(?m)^[ \t]*{label_pattern}[ \t]*[，,:：]"
    )

    match = heading_pattern.search(full_text)

    if match is None:
        raise ValueError(
            f"Cannot locate 《{chapter['name']}》{label}"
        )

    # Identify position, independently of yin/yang.
    if label.startswith("初"):
        position = 1
    elif label.startswith("上"):
        position = 6
    else:
        position = {
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
        }[label[-1]]

    start = match.start()

    if position == 6:
        # 上爻是本卦最后一爻。
        # Do not stop at repeated mentions of 上六
        # inside annotations or translations.
        end = len(full_text)

    else:
        # Only look for headings of later positions.
        # Repeated references to the same position
        # within commentary must not terminate extraction.
        later_labels = []

        for next_position in range(position + 1, 7):
            if next_position == 6:
                later_labels.extend(["上六", "上九"])
            else:
                character = {
                    2: "二",
                    3: "三",
                    4: "四",
                    5: "五",
                }[next_position]
                later_labels.extend([
                    f"六{character}",
                    f"九{character}",
                ])

        patterns = [
            r"\s*".join(re.escape(c) for c in name)
            for name in later_labels
        ]

        next_heading = re.compile(
            r"(?m)^[ \t]*(?:"
            + "|".join(patterns)
            + r")[ \t]*[，,:：]"
        )

        next_match = next_heading.search(
            full_text,
            match.end(),
        )

        end = (
            next_match.start()
            if next_match
            else len(full_text)
        )

    if end <= start:
        raise RuntimeError(
            f"Invalid moving-line range: {label}"
        )

    return extract_text_window(
        segments,
        start,
        min(end - start, 6000),
    )


def format_segments(segments):
    """
    Format every evidence segment with its real page.
    """
    return "\n\n".join(
        f"[PDF第{s['pdf_page']}页]\n{s['text']}"
        for s in segments
    )


def retrieve_cast_evidence(cast):
    """
    Get:
      1. Original hexagram introduction
      2. Moving-line passages
      3. Changed hexagram introduction
    """
    pages = load_pages()

    original = cast["original_hexagram"]
    changed = cast["changed_hexagram"]

    original_chapter = get_chapter(
        pages, original["number"]
    )

    evidence = []

    introduction = extract_text_window(
        original_chapter["segments"],
        start=0,
        max_chars=4500,
    )

    evidence.append({
        "type": "original_hexagram",
        "name": original["name"],
        "segments": introduction,
    })

    for label in cast["moving_line_labels"]:
        parts = find_moving_line(
            original_chapter,
            label,
        )

        evidence.append({
            "type": "moving_line",
            "name": f"{original['name']}·{label}",
            "segments": parts,
        })

    if changed["number"] != original["number"]:
        changed_chapter = get_chapter(
            pages, changed["number"]
        )

        introduction = extract_text_window(
            changed_chapter["segments"],
            start=0,
            max_chars=4500,
        )

        evidence.append({
            "type": "changed_hexagram",
            "name": changed["name"],
            "segments": introduction,
        })

    return evidence


def main():
    from engines.yijing_cast import build_cast_result

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lines",
        default="7,8,8,8,7,6",
    )
    args = parser.parse_args()

    values = [
        int(v.strip())
        for v in args.lines.split(",")
    ]

    cast = build_cast_result(values)
    evidence = retrieve_cast_evidence(cast)

    print("\n===== EXACT ZHOUYI RETRIEVAL =====")

    for item in evidence:
        pages = [
            s["pdf_page"]
            for s in item["segments"]
        ]

        print(
            f"\nTYPE: {item['type']}"
            f"\nNAME: {item['name']}"
            f"\nPDF PAGES: {pages}"
        )

        print(
            format_segments(item["segments"])[:900]
        )


if __name__ == "__main__":
    main()
