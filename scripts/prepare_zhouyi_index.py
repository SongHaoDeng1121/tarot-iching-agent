import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/chunks/zhouyi_chunks.jsonl"
OUTPUT = ROOT / "data/chunks/zhouyi_index_ready.jsonl"

with SOURCE.open(encoding="utf-8") as f:
    records = [json.loads(line) for line in f if line.strip()]

if not records:
    raise ValueError("输入文件没有记录")

# 同一PDF页的相同chunk只保留一次
unique = {}

for record in records:
    page = record["pdf_page"]
    index = record["chunk_index"]
    key = (page, index)

    if key in unique:
        if unique[key]["text"] != record["text"]:
            raise ValueError(
                f"重复片段内容不一致: PDF页{page}, chunk {index}"
            )

        # 任何一个副本标记为边界，都视为边界
        unique[key]["boundary_page"] = (
            unique[key]["boundary_page"]
            or record["boundary_page"]
        )
    else:
        unique[key] = dict(record)

cleaned = []

for (page, index), record in sorted(unique.items()):
    boundary = record["boundary_page"]

    item = {
        "id": f"zhouyi_p{page:04d}_c{index:03d}",
        "source": "zhouyi.pdf",
        "pdf_page": page,
        "chunk_index": index,
        "text": record["text"],
        "boundary_page": boundary,
        "section_type": (
            "unverified_boundary"
            if boundary else record["section_type"]
        ),
        "section_id": (
            None if boundary else record["section_id"]
        ),
        "hexagram_name": (
            None if boundary else record.get("hexagram_name")
        ),
        "hexagram_number": (
            None if boundary else record.get("hexagram_number")
        ),
    }

    cleaned.append(item)

if OUTPUT.exists():
    raise FileExistsError(
        f"输出文件已存在，不会覆盖: {OUTPUT}"
    )

with OUTPUT.open("w", encoding="utf-8") as f:
    for record in cleaned:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

counts = Counter(r["section_type"] for r in cleaned)

print("===== INDEX PREPARATION =====")
print("Original chunks:", len(records))
print("Unique chunks:", len(cleaned))
print("Duplicates removed:", len(records) - len(cleaned))
print("Boundary chunks:", counts["unverified_boundary"])
print("Empty texts:", sum(not r["text"].strip() for r in cleaned))
print("Output:", OUTPUT)
