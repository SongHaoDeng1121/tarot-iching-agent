
# engines/hexagram_utils.py
# 六十四卦映射：文王卦序
# 所有爻位均按「从下到上」排列。
# 1 = 阳爻，0 = 阴爻

TRIGRAM_ORDER = (
    "乾", "兑", "离", "震",
    "巽", "坎", "艮", "坤"
)

# 每组三爻也是从下到上
TRIGRAM_BITS = {
    "乾": (1, 1, 1),
    "兑": (1, 1, 0),
    "离": (1, 0, 1),
    "震": (1, 0, 0),
    "巽": (0, 1, 1),
    "坎": (0, 1, 0),
    "艮": (0, 0, 1),
    "坤": (0, 0, 0),
}

TRIGRAM_SYMBOLS = {
    "乾": "☰",
    "兑": "☱",
    "离": "☲",
    "震": "☳",
    "巽": "☴",
    "坎": "☵",
    "艮": "☶",
    "坤": "☷",
}

# 按文王卦序，从第1卦到第64卦
HEXAGRAM_NAMES = (
    "乾", "坤", "屯", "蒙", "需", "讼", "师", "比",
    "小畜", "履", "泰", "否", "同人", "大有",
    "谦", "豫", "随", "蛊", "临", "观",
    "噬嗑", "贲", "剥", "复", "无妄", "大畜",
    "颐", "大过", "坎", "离", "咸", "恒",
    "遯", "大壮", "晋", "明夷", "家人", "睽",
    "蹇", "解", "损", "益", "夬", "姤",
    "萃", "升", "困", "井", "革", "鼎",
    "震", "艮", "渐", "归妹", "丰", "旅",
    "巽", "兑", "涣", "节", "中孚", "小过",
    "既济", "未济",
)

# 行 = 上卦，列 = 下卦
# 行列顺序都是 乾、兑、离、震、巽、坎、艮、坤
KING_WEN_MATRIX = (
    (1, 10, 13, 25, 44, 6, 33, 12),
    (43, 58, 49, 17, 28, 47, 31, 45),
    (14, 38, 30, 21, 50, 64, 56, 35),
    (34, 54, 55, 51, 32, 40, 62, 16),
    (9, 61, 37, 42, 57, 59, 53, 20),
    (5, 60, 63, 3, 48, 29, 39, 8),
    (26, 41, 22, 27, 18, 4, 52, 23),
    (11, 19, 36, 24, 46, 7, 15, 2),
)


def build_hexagram_index():
    """
    构建从六爻阴阳组合到64卦的映射。
    六爻顺序：初爻 -> 上爻。
    """
    index = {}

    for upper_i, upper in enumerate(TRIGRAM_ORDER):
        for lower_i, lower in enumerate(TRIGRAM_ORDER):

            number = KING_WEN_MATRIX[upper_i][lower_i]

            # 下卦三爻在前，上卦三爻在后
            bits = (
                TRIGRAM_BITS[lower]
                + TRIGRAM_BITS[upper]
            )

            index[bits] = {
                "number": number,
                "name": HEXAGRAM_NAMES[number - 1],
                "upper_trigram": upper,
                "lower_trigram": lower,
                "upper_symbol": TRIGRAM_SYMBOLS[upper],
                "lower_symbol": TRIGRAM_SYMBOLS[lower],
                "unicode": chr(0x4DC0 + number - 1),
            }

    if len(index) != 64:
        raise ValueError("Hexagram index must contain 64 entries")

    numbers = {item["number"] for item in index.values()}

    if numbers != set(range(1, 65)):
        raise ValueError("Invalid King Wen numbering")

    return index


HEXAGRAM_INDEX = build_hexagram_index()


def identify_hexagram(lines):
    """
    通过六个阴阳值确定卦名。

    参数：
        lines: [0, 1, 0, 1, 1, 1]

    0为阴，1为阳；
    从初爻到上爻。
    """

    if len(lines) != 6:
        raise ValueError("Exactly six lines are required")

    if any(type(x) is not int or x not in (0, 1) for x in lines):
        raise ValueError("Each line must be 0 or 1")

    key = tuple(lines)

    return {
        **HEXAGRAM_INDEX[key],
        "lines_bottom_to_top": list(key),
    }


def get_hexagram_by_number(number):
    """按文王序号查找卦象。"""

    if not isinstance(number, int) or not 1 <= number <= 64:
        raise ValueError("Hexagram number must be 1-64")

    for bits, info in HEXAGRAM_INDEX.items():
        if info["number"] == number:
            return {
                **info,
                "lines_bottom_to_top": list(bits),
            }

    raise RuntimeError("Hexagram not found")


def render_hexagram(lines):
    """
    终端打印卦象：上爻在上、初爻在下。
    """
    if len(lines) != 6 or any(x not in (0, 1) for x in lines):
        raise ValueError("Invalid hexagram lines")

    symbols = {
        1: "━━━━━━━",
        0: "━━━ ━━━",
    }

    return "\n".join(
        f"{6 - i}  {symbols[value]}"
        for i, value in enumerate(reversed(lines))
    )
