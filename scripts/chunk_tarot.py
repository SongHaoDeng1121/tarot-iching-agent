
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/extracted/tarot_pages.jsonl"
OUTPUT = ROOT / "data/chunks/tarot_chunks.jsonl"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

MAX_CHARS = 1100
MIN_CHARS = 80

count = 0

with INPUT.open("r", encoding="utf-8") as f_in:
    with OUTPUT.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            page = json.loads(line)
            text = page["text"]

            paragraphs = [
                p.strip()
                for p in re.split(r"\n\s*\n", text)
                if p.strip()
            ]

            chunks = []
            current = ""

            for paragraph in paragraphs:
                # 对超长段落按字符长度切割
                while len(paragraph) > MAX_CHARS:
                    if current:
                        chunks.append(current)
                        current = ""

                    chunks.append(paragraph[:MAX_CHARS])
                    paragraph = paragraph[MAX_CHARS:]

                if len(current) + len(paragraph) + 2 <= MAX_CHARS:
                    current += ("\n\n" if current else "") + paragraph
                else:
                    if current:
                        chunks.append(current)
                    current = paragraph

            if current:
                chunks.append(current)

            for i, chunk in enumerate(chunks):
                if len(chunk) < MIN_CHARS:
                    continue

                record = {
                    "id": f"{page['id']}_chunk_{i:03d}",
                    "source": page["source"],
                    "pdf_page": page["pdf_page"],
                    "text": chunk,
                }

                f_out.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

                count += 1

print("Total chunks:", count)
print("Output:", OUTPUT)
