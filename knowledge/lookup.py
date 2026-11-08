
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "structured"
    / "hexagrams.json"
)


def load_hexagrams():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_hexagram(hexagram_id):
    data = load_hexagrams()
    return data.get(str(hexagram_id))


def get_line(hexagram_id, line_number):
    hexagram = get_hexagram(hexagram_id)

    if hexagram is None:
        return None

    return hexagram["lines"].get(str(line_number))


if __name__ == "__main__":

    hexagram = get_hexagram(6)
    line = get_line(6, 2)

    print("=" * 45)
    print("YI KNOWLEDGE BASE TEST")
    print("=" * 45)

    print("卦名：", hexagram["full_name"])
    print("爻名：", line["name"])
    print("爻辞：", line["text"])
    print("是否当位：", line["is_correct_position"])
    print("是否得中：", line["is_central"])
    print("解释：", line["explanation"])
