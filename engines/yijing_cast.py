
# engines/yijing_cast.py

import argparse
import json
import secrets

from engines.hexagram_utils import (
    identify_hexagram,
    render_hexagram,
)

LINE_NAMES = {
    6: "老阴",
    7: "少阳",
    8: "少阴",
    9: "老阳",
}

POSITION_NAMES = (
    "初爻", "二爻", "三爻",
    "四爻", "五爻", "上爻"
)

# 用户的爻辞检索所需名称
POSITION_LABELS = (
    ("初六", "初九"),
    ("六二", "九二"),
    ("六三", "九三"),
    ("六四", "九四"),
    ("六五", "九五"),
    ("上六", "上九"),
)


def cast_one_line():
    """
    三枚铜钱起一爻。

    每枚铜钱独立产生2或3，
    三枚相加得到6、7、8、9。
    """
    coins = [
        2 + secrets.randbelow(2)
        for _ in range(3)
    ]
    return sum(coins)


def cast_six_lines():
    """
    六次起爻，从下到上记录。
    """
    return [
        cast_one_line()
        for _ in range(6)
    ]


def original_yang(value):
    """6/8 = 阴；7/9 = 阳。"""
    return int(value in (7, 9))


def changed_yang(value):
    """6变阳，9变阴；7/8不变。"""
    return int(value in (6, 7))


def line_label(position, value):
    """
    返回传统爻位名称，例如初九、六二。
    """
    yang = original_yang(value)
    return POSITION_LABELS[position - 1][yang]


def build_cast_result(values):
    """
    根据六个铜钱数值生成完整起卦结果。

    values:
      list[int], 长度为6
      从初爻到上爻

    Returns:
      本卦、动爻、变卦、每爻详情
    """
    if len(values) != 6:
        raise ValueError("Exactly six line values required")

    if any(type(v) is not int or v not in (6, 7, 8, 9) for v in values):
        raise ValueError("Line values must be 6, 7, 8 or 9")

    original = [
        original_yang(v)
        for v in values
    ]

    changed = [
        changed_yang(v)
        for v in values
    ]

    original_hexagram = identify_hexagram(original)
    changed_hexagram = identify_hexagram(changed)

    lines = []
    moving_positions = []

    for index, value in enumerate(values):
        position = index + 1
        moving = value in (6, 9)

        if moving:
            moving_positions.append(position)

        lines.append({
            "position": position,
            "position_name": POSITION_NAMES[index],
            "label": line_label(position, value),
            "coin_value": value,
            "type": LINE_NAMES[value],
            "yang": original[index],
            "changed_yang": changed[index],
            "moving": moving,
        })

    return {
        "method": "three_coins",
        "line_values_bottom_to_top": list(values),
        "original_hexagram": original_hexagram,
        "changed_hexagram": changed_hexagram,
        "moving_positions": moving_positions,
        "moving_line_labels": [
            lines[i - 1]["label"]
            for i in moving_positions
        ],
        "has_changes": bool(moving_positions),
        "lines": lines,
    }


def cast_hexagram():
    """
    完整随机起卦入口。
    """
    values = cast_six_lines()
    return build_cast_result(values)


def print_cast(result):
    """在终端展示起卦结果。"""

    original = result["original_hexagram"]
    changed = result["changed_hexagram"]

    print("\n===== 本卦 =====")
    print(
        f"第{original['number']}卦 "
        f"{original['name']} "
        f"{original['unicode']}"
    )

    print(
        f"上卦：{original['upper_trigram']} "
        f"{original['upper_symbol']}"
    )
    print(
        f"下卦：{original['lower_trigram']} "
        f"{original['lower_symbol']}"
    )
    print(
        render_hexagram(
            original["lines_bottom_to_top"]
        )
    )

    print("\n===== 六爻 =====")
    for line in reversed(result["lines"]):
        tag = " [动爻]" if line["moving"] else ""
        print(
            f"{line['label']}: "
            f"{line['type']} ({line['coin_value']})"
            f"{tag}"
        )

    print("\n===== 变卦 =====")
    print(
        f"第{changed['number']}卦 "
        f"{changed['name']} "
        f"{changed['unicode']}"
    )
    print(
        render_hexagram(
            changed["lines_bottom_to_top"]
        )
    )

    print("\n动爻：", (
        "、".join(result["moving_line_labels"])
        if result["has_changes"]
        else "无动爻"
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Three-coin I Ching casting engine"
    )

    parser.add_argument(
        "--lines",
        default=None,
        help=(
            "Optional six values from bottom to top, "
            "e.g. 7,8,9,7,6,8"
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON only",
    )

    args = parser.parse_args()

    if args.lines:
        try:
            values = [
                int(x.strip())
                for x in args.lines.split(",")
            ]
        except ValueError as exc:
            parser.error(
                "Use six integers separated by commas"
            )

        result = build_cast_result(values)

    else:
        result = cast_hexagram()

    if args.json:
        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print_cast(result)


if __name__ == "__main__":
    main()
