
# scripts/build_tarot_sections.py

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/extracted/tarot_pages.jsonl"
OUTPUT = ROOT / "data/structured/tarot_sections_auto.json"
REPORT = ROOT / "data/structured/tarot_sections_report.txt"

SUITS = ["Wands", "Cups", "Swords", "Pentacles"]

# 原书小阿尔卡那采用从 King 到 Ace 的顺序
RANKS = [
    "King", "Queen", "Knight", "Page",
    "Ten", "Nine", "Eight", "Seven", "Six",
    "Five", "Four", "Three", "Two", "Ace"
]

MAJORS = [
    "The Fool", "The Magician", "The High Priestess",
    "The Empress", "The Emperor", "The Hierophant",
    "The Lovers", "The Chariot", "Strength",
    "The Hermit", "Wheel of Fortune", "Justice",
    "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star",
    "The Moon", "The Sun", "Judgement", "The World"
]

# 部分版本使用不同拼写

ALIASES = {
    "Judgement": {
        "JUDGEMENT",
        "JUDGMENT",
    },
    "The Hierophant": {
        "THEHIEROPHANT",
        "HIEROPHANT",
    },
    "Wheel of Fortune": {
        "WHEELOFFORTUNE",
        "THEWHEELOFFORTUNE",
    },
    "Strength": {
        "STRENGTH",
    },
}


def compact(text):
    """删除空格和标点，便于识别字母间隔的标题。"""
    return re.sub(r"[^A-Z]", "", text.upper())


def key(name):
    return name.lower().replace(" ", "_")


def read_pages():
    pages = []

    with INPUT.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pages.append(json.loads(line))

    pages.sort(key=lambda x: x["pdf_page"])
    return pages


def heading_lines(page):
    """提取可能的独立标题及其文本偏移。"""
    text = page["text"]
    offset = 0

    for line in text.splitlines(keepends=True):
        raw = line.strip()
        normalized = compact(raw)

        # 排除空行、正文长句、单纯数字等
        letters = [c for c in raw if c.isalpha()]

        if (
            normalized
            and len(raw) <= 65
            and letters
            and sum(c.isupper() for c in letters) / len(letters) >= 0.75
        ):
            yield {
                "text": raw,
                "normalized": normalized,
                "offset": offset + len(line) - len(line.lstrip()),
            }

        offset += len(line)


def detect_suits(pages):
    """根据 CHAPTER + 花色名称确定花色章节起点。"""
    found = {}

    for page in pages:
        # 只扫描页面开头，降低正文提及花色造成的误判
        beginning = compact(page["text"][:450])

        if "CHAPTER" not in beginning:
            continue

        for suit in SUITS:
            if suit in found:
                continue

            name = suit.upper()

            if re.search(r"CHAPTER[A-Z]*" + name, beginning):
                found[suit] = page["pdf_page"]

    # 已直接核对的原书位置作为保底值
    # 不推测其他三个花色的页码
    found.setdefault("Cups", 200)

    return found


def title_matches(title, name):
    actual = title["normalized"]
    expected = compact(name)

    variants = ALIASES.get(name, {expected})
    return actual in variants


def scan_titles(pages, suits):
    """在相应章节范围内搜集候选牌名标题。"""
    candidates = {}
    starts = sorted(
        (page, suit) for suit, page in suits.items()
    )

    for index, (start_page, suit) in enumerate(starts):
        end_page = (
            starts[index + 1][0]
            if index + 1 < len(starts)
            else float("inf")
        )

        for page in pages:
            page_no = page["pdf_page"]

            if not start_page <= page_no < end_page:
                continue

            for heading in heading_lines(page):
                for rank in RANKS:
                    if title_matches(heading, rank):
                        card_id = key(f"{rank} of {suit}")

                        candidates.setdefault(card_id, []).append({
                            "page": page_no,
                            "offset": heading["offset"],
                            "heading": heading["text"],
                        })

    return candidates


def scan_majors(pages, first_minor_page):
    """识别大阿尔卡那的独立牌名标题。"""
    candidates = {}

    for page in pages:
        if page["pdf_page"] >= first_minor_page:
            continue

        for heading in heading_lines(page):
            for name in MAJORS:
                if title_matches(heading, name):
                    candidates.setdefault(key(name), []).append({
                        "page": page["pdf_page"],
                        "offset": heading["offset"],
                        "heading": heading["text"],
                    })

    return candidates


def choose_ordered(names, candidates):
    """
    按原书牌序选择第一个有效候选。
    缺失时不编造位置。
    """
    chosen = {}
    previous = (-1, -1)

    for name in names:
        card_id = key(name)

        matches = sorted(
            candidates.get(card_id, []),
            key=lambda x: (x["page"], x["offset"])
        )

        valid = [
            m for m in matches
            if (m["page"], m["offset"]) > previous
        ]

        if valid:
            chosen[card_id] = valid[0]
            previous = (valid[0]["page"], valid[0]["offset"])

    return chosen


def build_sections(chosen, names, source, suit=None):
    """根据下一张牌的标题确定上一张牌的边界。"""
    output = {}

    for i, name in enumerate(names):
        card_id = key(name)
        current = chosen.get(card_id)

        if current is None:
            output[card_id] = {
                "card_id": card_id,
                "name_en": name,
                "suit": suit,
                "source": source,
                "status": "missing",
                "needs_review": True,
                "pdf_start_page": None,
                "pdf_end_page": None,
                "start_offset": None,
                "end_offset_exclusive": None,
            }
            continue

        # 仅当紧接的下一张牌已经找到时才确定结束边界
        next_name = names[i + 1] if i + 1 < len(names) else None
        next_card = chosen.get(key(next_name)) if next_name else None

        output[card_id] = {
            "card_id": card_id,
            "name_en": name,
            "suit": suit,
            "source": source,
            "status": "candidate",
            "needs_review": True,
            "pdf_start_page": current["page"],
            "pdf_end_page": next_card["page"] if next_card else None,
            "start_offset": current["offset"],
            "end_offset_exclusive": (
                next_card["offset"] if next_card else None
            ),
            "end_boundary_is_next_heading": bool(next_card),
            "detected_heading": current["heading"],
        }

    return output


def main():
    pages = read_pages()
    suits = detect_suits(pages)

    print("Extracted pages:", len(pages))
    print("Detected suit chapters:", suits)

    minor_candidates = scan_titles(pages, suits)
    first_minor = min(suits.values()) if suits else 200
    major_candidates = scan_majors(pages, first_minor)

    result = {}
    all_candidates = {**minor_candidates, **major_candidates}

    # 每个花色分别按 King -> Ace 的顺序识别
    for suit in SUITS:
        names = [f"{rank} of {suit}" for rank in RANKS]

        if suit not in suits:
            for name in names:
                result[key(name)] = {
                    "card_id": key(name),
                    "name_en": name,
                    "suit": suit,
                    "source": "tarot_78_degrees",
                    "status": "suit_chapter_not_found",
                    "needs_review": True,
                    "pdf_start_page": None,
                    "pdf_end_page": None,
                }
            continue

        chosen = choose_ordered(names, minor_candidates)
        result.update(
            build_sections(
                chosen, names, "tarot_78_degrees", suit
            )
        )

    # 大阿尔卡那也采用原书牌序寻找候选标题
    major_chosen = choose_ordered(MAJORS, major_candidates)
    result.update(
        build_sections(
            major_chosen, MAJORS, "tarot_78_degrees"
        )
    )

    # 输出所有78张卡牌，包括暂未识别的项目
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    identified = sum(
        item.get("pdf_start_page") is not None
        for item in result.values()
    )

    lines = [
        "TAROT SECTION DETECTION REPORT",
        "=" * 65,
        f"Total cards: {len(result)}",
        f"Detected candidates: {identified}",
        f"Missing candidates: {len(result) - identified}",
        "",
        "CHAPTER STARTS",
        str(suits),
        "",
        "CARD CANDIDATES",
    ]

    for card_id, item in result.items():
        matches = all_candidates.get(card_id, [])

        lines.append(
            f"{card_id:28} "
            f"start={str(item.get('pdf_start_page')):5} "
            f"end={str(item.get('pdf_end_page')):5} "
            f"candidates={len(matches)} "
            f"status={item['status']}"
        )

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("=" * 45)
    print("Total cards:", len(result))
    print("Detected candidates:", identified)
    print("Missing candidates:", len(result) - identified)
    print("Output:", OUTPUT)
    print("Report:", REPORT)
    print("=" * 45)


if __name__ == "__main__":
    main()
