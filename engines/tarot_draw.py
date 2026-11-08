
# engines/tarot_draw.py

import json
import secrets
from pathlib import Path
from rag.runtime_data import knowledge_path

ROOT = Path(__file__).resolve().parents[1]

KNOWLEDGE_FILE = knowledge_path("data/structured/tarot_meanings.json")

DEFAULT_POSITIONS = ["现状", "阻碍", "建议"]


def load_deck():
    """
    从知识库读取标准78张塔罗牌。
    card_id 直接对应 RAG 知识索引。
    """
    with KNOWLEDGE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    deck = list(data.keys())

    if len(deck) != 78 or len(set(deck)) != 78:
        raise ValueError(
            "Tarot deck must contain 78 unique cards."
        )

    return deck


def draw_cards(count=3, reversed_probability=0.5):
    """
    无放回随机抽牌，并独立决定正逆位。

    reversed_probability:
        0.0 = 全部正位
        0.5 = 正逆位各50%概率
        1.0 = 全部逆位
    """
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("count must be an integer")

    if not 1 <= count <= 78:
        raise ValueError("count must be between 1 and 78")

    if not 0 <= reversed_probability <= 1:
        raise ValueError(
            "reversed_probability must be between 0 and 1"
        )

    deck = load_deck()
    rng = secrets.SystemRandom()

    selected = rng.sample(deck, count)

    result = []

    for card_id in selected:
        orientation = (
            "reversed"
            if rng.random() < reversed_probability
            else "upright"
        )

        result.append({
            "card_id": card_id,
            "orientation": orientation,
        })

    return result


def make_three_card_spread(question, positions=None):
    """
    生成与 rag/spread.py 完全兼容的结构。
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty")

    positions = (
        list(positions)
        if positions is not None
        else DEFAULT_POSITIONS.copy()
    )

    if len(positions) != 3 or len(set(positions)) != 3:
        raise ValueError(
            "Exactly three distinct positions are required"
        )

    drawn = draw_cards(count=3)

    cards = []

    for position, card in zip(positions, drawn):
        cards.append({
            "position": position,
            "card_id": card["card_id"],
            "orientation": card["orientation"],
        })

    return {
        "spread_name": "Three-Card Reflection",
        "question": question.strip(),
        "cards": cards,
    }


if __name__ == "__main__":
    spread = make_three_card_spread(
        "我应该如何反思目前的计划？"
    )

    print(json.dumps(
        spread,
        ensure_ascii=False,
        indent=2,
    ))
