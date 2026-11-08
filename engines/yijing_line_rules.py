"""Deterministic six-line interpretation metadata (bottom to top).

Rules: yang at odd positions / yin at even positions = correctly placed;
2 and 5 are central; corresponding positions are (1,4), (2,5), (3,6),
and form 正应 when their yin/yang values differ.
"""
from __future__ import annotations

from typing import Any

PAIRS = {1: 4, 2: 5, 3: 6, 4: 1, 5: 2, 6: 3}


def analyze_lines(cast: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute line structure from the ORIGINAL hexagram, not changed hexagram."""
    values = cast["original_hexagram"]["lines_bottom_to_top"]
    if len(values) != 6 or any(type(x) is not int or x not in (0, 1) for x in values):
        raise ValueError("original_hexagram.lines_bottom_to_top must be six 0/1 integers")
    supplied_lines = cast.get("lines", [])
    if len(supplied_lines) != 6:
        raise ValueError("cast.lines must contain six positions")
    details = []
    for i, value in enumerate(values):
        position = i + 1
        counterpart = PAIRS[position]
        correct = (value == 1) if position % 2 else (value == 0)
        complementary = value != values[counterpart - 1]
        entry = supplied_lines[i]
        if entry.get("position") != position or entry.get("yang") != value:
            raise ValueError(f"cast.lines[{i}] disagrees with original hexagram")
        details.append({
            "position": position,
            "label": entry["label"],
            "yin_yang": "阳" if value else "阴",
            "central": position in (2, 5),
            "correct_position": correct,
            "corresponding_position": counterpart,
            "proper_correspondence": complementary,
            "moving": bool(entry["moving"]),
        })
    return details


def format_line_analysis(cast: dict[str, Any], moving_only: bool = True) -> str:
    """Produce an authoritative structural block for the LLM."""
    lines = analyze_lines(cast)
    if moving_only:
        lines = [line for line in lines if line["moving"]]
    if not lines:
        return "本次无动爻；无须指定某一动爻的结构。"
    parts = ["以下爻位结构由Python按本卦六爻计算，不是语言模型推测："]
    for line in lines:
        parts.append(
            f"{line['label']}：{line['yin_yang']}爻；"
            f"{'得中' if line['central'] else '不得中'}；"
            f"{'当位' if line['correct_position'] else '失位'}；"
            f"与第{line['corresponding_position']}爻"
            f"{'阴阳相异，构成正应' if line['proper_correspondence'] else '阴阳相同，无正应'}。"
        )
    parts.append("注意：'三与上相对应'只指爻位配对；阴阳相同则无正应。")
    return "\n".join(parts)
