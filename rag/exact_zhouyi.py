
import json
import re
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES_PATH = ROOT / "data/extracted/zhouyi_pages.jsonl"
SECTIONS_PATH = ROOT / "data/structured/zhouyi_sections.json"


def load_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


PAGES = load_jsonl(PAGES_PATH)

SECTIONS = json.loads(
    SECTIONS_PATH.read_text(encoding="utf-8")
)

HEXAGRAMS = SECTIONS["hexagrams"]
APPENDICES = SECTIONS["appendices"]


def normalize(text):
    """忽略空白和常见标点，保留汉字原貌。"""
    return re.sub(
        r"[\s，。！？、；：,.;:!?\"'“”‘’（）()]",
        "",
        text
    )



def detect_hexagram(question):
    """
    根据明确的卦名表达识别六十四卦。

    支持：
    - 讼卦九二
    - 第六卦
    - 第6卦
    - 《中孚》
    - 中孚九二
    - 兑卦

    避免：
    - 理解 -> 解卦
    - 需要 -> 需卦
    - 比如 -> 比卦
    """

    line_pattern = (
        r"(?:初[六九]|[六九][二三四五]|上[六九])"
    )

    # 1. 根据明确卦序识别
    number_match = re.search(
        r"第\s*(\d{1,2})\s*卦",
        question
    )

    if number_match:
        number = int(number_match.group(1))

        for item in HEXAGRAMS:
            if item["number"] == number:
                return item

    # 2. 按名称长度排序，防止短卦名抢占长卦名
    names = sorted(
        HEXAGRAMS,
        key=lambda item: len(item["name"]),
        reverse=True
    )

    for item in names:
        name = re.escape(item["name"])

        patterns = [
            # 明确说某卦，例如：讼卦
            rf"{name}卦",

            # 书名号，例如：《中孚》
            rf"《{name}》",

            # 卦名紧接爻位，例如：中孚九二
            rf"{name}{line_pattern}",
        ]

        if any(
            re.search(pattern, question)
            for pattern in patterns
        ):
            return item

    return None



def detect_line(question):
    """识别用户指定的爻位。"""
    patterns = [
        ("初九", 1), ("初六", 1),
        ("九二", 2), ("六二", 2),
        ("九三", 3), ("六三", 3),
        ("九四", 4), ("六四", 4),
        ("九五", 5), ("六五", 5),
        ("上九", 6), ("上六", 6),
    ]

    for name, number in patterns:
        if name in question:
            return name, number

    return None, None


def find_exact(phrase, hexagram=None, top_k=10):
    """在原始逐页 OCR 中搜索指定文字。"""

    phrase = normalize(phrase)

    if not phrase:
        return []

    if hexagram is not None:
        section = next(
            (
                item for item in HEXAGRAMS
                if item["name"] == hexagram
            ),
            None
        )

        if section is None:
            raise ValueError(f"未知卦名: {hexagram}")

        start = section["start_pdf_page"]
        end = section["end_pdf_page_inclusive"]

        candidate_pages = PAGES[start - 1:end]

    else:
        candidate_pages = PAGES

    results = []

    for page in candidate_pages:
        raw_text = page["text"]
        normalized_text = normalize(raw_text)

        pos = normalized_text.find(phrase)

        if pos < 0:
            continue

        # 返回整页原文，避免由于删除标点导致字符偏移
        results.append({
            "pdf_page": page["pdf_page"],
            "source": "zhouyi.pdf",
            "phrase": phrase,
            "text": raw_text,
            "match_count": normalized_text.count(phrase)
        })

    return results[:top_k]


def search_by_question(question, phrase=None, top_k=10):
    hexagram = detect_hexagram(question)
    line_name, line_number = detect_line(question)

    print("识别卦名:", hexagram["name"] if hexagram else None)
    print("识别爻位:", line_name)
    print("爻位序号:", line_number)

    if not phrase:
        print("未提供原文关键词；请通过 --phrase 指定")
        return []

    return find_exact(
        phrase=phrase,
        hexagram=hexagram["name"] if hexagram else None,
        top_k=top_k
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("question")
    parser.add_argument("--phrase")
    parser.add_argument("--top-k", type=int, default=10)

    args = parser.parse_args()

    results = search_by_question(
        question=args.question,
        phrase=args.phrase,
        top_k=args.top_k
    )

    print("\n===== EXACT SEARCH RESULTS =====")

    for result in results:
        print(
            f"PDF第{result['pdf_page']}页 | "
            f"匹配次数: {result['match_count']}"
        )
        print(result["text"][:350])
        print("-" * 50)