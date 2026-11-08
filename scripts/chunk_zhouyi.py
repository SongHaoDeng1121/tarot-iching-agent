
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGES_FILE = ROOT / "data/extracted/zhouyi_pages.jsonl"
SECTIONS_FILE = ROOT / "data/structured/zhouyi_sections.json"
OUTPUT_FILE = ROOT / "data/chunks/zhouyi_chunks.jsonl"

CHUNK_SIZE = 1100
OVERLAP = 180

def load_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

pages = load_jsonl(PAGES_FILE)
sections = json.loads(
    SECTIONS_FILE.read_text(encoding="utf-8")
)

all_sections = sections["hexagrams"] + sections["appendices"]

assert len(pages) == 708
assert len(sections["hexagrams"]) == 64

def clean_text(text):
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_text(text, size=1100, overlap=180):
    result = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))
        part = text[start:end].strip()

        if part:
            result.append(part)

        if end == len(text):
            break

        start = end - overlap

    return result

records = []

for section in all_sections:
    start_page = section["start_pdf_page"]
    end_page = section["end_pdf_page_inclusive"]

    for page_no in range(start_page, end_page + 1):

        page_text = clean_text(
            pages[page_no - 1]["text"]
        )

        # 标记章节边界页面
        boundary_page = (
            page_no == start_page or
            page_no == end_page
        )

        chunks = split_text(page_text)

        for i, chunk in enumerate(chunks):
            records.append({
                "id": (
                    f"zhouyi_{section['id']}_"
                    f"p{page_no:04d}_c{i:03d}"
                ),
                "source": "zhouyi.pdf",
                "section_id": section["id"],
                "section_type": section["type"],
                "hexagram_number": section.get("number"),
                "hexagram_name": section["name"],
                "pdf_page": page_no,
                "chunk_index": i,
                "boundary_page": boundary_page,
                "text": chunk
            })

if OUTPUT_FILE.exists():
    raise FileExistsError(
        f"文件已存在：{OUTPUT_FILE}"
    )

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_FILE.open("w", encoding="utf-8") as f:
    for record in records:
        f.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )

print("===== CHUNKING COMPLETED =====")
print("PDF pages:", len(pages))
print("Hexagrams:", len(sections["hexagrams"]))
print("Appendices:", len(sections["appendices"]))
print("Total chunks:", len(records))
print("Output:", OUTPUT_FILE)

boundary_count = sum(
    r["boundary_page"] for r in records
)

print("Boundary chunks needing review:", boundary_count)
