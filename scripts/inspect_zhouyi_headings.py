import json
from pathlib import Path

INPUT = Path("data/extracted/zhouyi_pages.jsonl")
OUTPUT = Path("data/structured/zhouyi_heading_candidates.json")

pages = [
    json.loads(line)
    for line in INPUT.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

candidates = []

for i, page in enumerate(pages):
    text = page["text"]
    lines = [line.strip() for line in text.splitlines()]

    for j, line in enumerate(lines):
        # 找到题解标题，允许 OCR 产生空格
        normalized = "".join(line.split())

        if normalized not in ("【题解】", "[题解]", "题解"):
            continue

        # 当前题解之前的若干行
        context_before = lines[max(0, j - 12):j]

        # 当前题解之后的若干行
        context_after = lines[j + 1:j + 5]

        item = {
            "pdf_page": page["pdf_page"],
            "heading_before": context_before,
            "text_after": context_after
        }

        candidates.append(item)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(candidates, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("=" * 55)
print("《周易》章节标题诊断")
print("=" * 55)

print("PDF页数:", len(pages))
print("找到的【题解】数量:", len(candidates))
print("结果保存到:", OUTPUT)

print("\n===== 前80个候选章节 =====")

for index, item in enumerate(candidates[:80], start=1):
    before = [
        line for line in item["heading_before"]
        if line
    ]

    print(
        f"{index:02d}. PDF第{item['pdf_page']:03d}页 | "
        f"题解前: {' / '.join(before[-4:])[:110]}"
    )
