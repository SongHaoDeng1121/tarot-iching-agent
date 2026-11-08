import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data/structured/zhouyi_heading_candidates.json"
OUTPUT = ROOT / "data/structured/zhouyi_sections.json"

HEXAGRAM_NAMES = [
    "乾", "坤", "屯", "蒙", "需", "讼", "师", "比",
    "小畜", "履", "泰", "否", "同人", "大有", "谦", "豫",
    "随", "蛊", "临", "观", "噬嗑", "贲", "剥", "复",
    "无妄", "大畜", "颐", "大过", "坎", "离", "咸", "恒",
    "遁", "大壮", "晋", "明夷", "家人", "睽", "蹇", "解",
    "损", "益", "夬", "姤", "萃", "升", "困", "井",
    "革", "鼎", "震", "艮", "渐", "归妹", "丰", "旅",
    "巽", "兑", "涣", "节", "中孚", "小过", "既济", "未济"
]

APPENDIX_NAMES = [
    "系辞上传",
    "说卦传",
    "序卦传",
    "杂卦传"
]

candidates = json.loads(INPUT.read_text(encoding="utf-8"))

if len(candidates) != 68:
    raise ValueError(
        f"预期68个候选，实际{len(candidates)}个，请人工检查"
    )

if len(HEXAGRAM_NAMES) != 64:
    raise ValueError("六十四卦名称列表长度错误")

# 验证目前已经观察到的关键位置
expected_pages = {
    1: 21,
    6: 91,
    31: 301,
    48: 440,
    58: 521,
    61: 544,
    64: 571
}

for number, page in expected_pages.items():
    actual = candidates[number - 1]["pdf_page"]
    if actual != page:
        raise ValueError(
            f"第{number}卦起始页异常：{actual}，预期{page}"
        )

sections = []

for i, name in enumerate(HEXAGRAM_NAMES):
    current = candidates[i]
    following = candidates[i + 1]

    sections.append({
        "id": f"hexagram_{i + 1:02d}",
        "type": "hexagram",
        "number": i + 1,
        "name": name,
        "source": "zhouyi.pdf",
        "start_pdf_page": current["pdf_page"],
        # 保留下一章节所在页，避免跨页边界遗漏；
        # 后续使用字符级定位再去除交叠部分。
        "end_pdf_page_inclusive": following["pdf_page"],
        "end_boundary_verified": False,
        "heading_context_ocr": current["heading_before"][-4:],
        "needs_review": True
    })

appendices = []

for i, name in enumerate(APPENDIX_NAMES):
    index = 64 + i
    current = candidates[index]

    end = (
        candidates[index + 1]["pdf_page"]
        if index + 1 < len(candidates)
        else 708
    )

    appendices.append({
        "id": f"appendix_{i + 1:02d}",
        "type": "appendix",
        "name": name,
        "source": "zhouyi.pdf",
        "start_pdf_page": current["pdf_page"],
        "end_pdf_page_inclusive": end,
        "end_boundary_verified": False,
        "needs_review": True
    })

data = {
    "source": "zhouyi.pdf",
    "source_page_count": 708,
    "index_type": "provisional_page_boundaries",
    "hexagrams": sections,
    "appendices": appendices,
    "notes": [
        "边界页可能同时包含相邻两个章节",
        "标准卦名根据六十四卦通行卦序映射",
        "章节标题OCR结果尚未逐一人工核实",
        "系辞下传尚未单独定位",
        "不要直接将重叠页全文作为精确章节引用"
    ]
}

if OUTPUT.exists():
    raise FileExistsError(
        f"输出文件已存在，停止覆盖：{OUTPUT}"
    )

OUTPUT.write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("===== ZHOUYI SECTION INDEX =====")
print("Hexagrams:", len(sections))
print("Appendices:", len(appendices))
print("Saved:", OUTPUT)

print("\n关键章节：")
for number in [1, 6, 31, 48, 58, 61, 64]:
    item = sections[number - 1]
    print(
        f"{number:02d} {item['name']}: "
        f"PDF {item['start_pdf_page']}"
        f"–{item['end_pdf_page_inclusive']}"
    )

print("\n其他篇章：")
for item in appendices:
    print(
        f"{item['name']}: "
        f"PDF {item['start_pdf_page']}"
        f"–{item['end_pdf_page_inclusive']}"
    )
