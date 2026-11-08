
from pathlib import Path
import json
import re
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data/raw/tarot_78_degrees.pdf"
OUTPUT = ROOT / "data/extracted/tarot_pages.jsonl"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

def clean_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

total_chars = 0
extracted_pages = 0

with pymupdf.open(PDF_PATH) as doc:
    with OUTPUT.open("w", encoding="utf-8") as out:
        for index, page in enumerate(doc):
            text = clean_text(
                page.get_text("text", sort=True)
            )

            if not text:
                continue

            record = {
                "id": f"tarot_page_{index + 1:03d}",
                "source": "tarot_78_degrees",
                "pdf_page": index + 1,
                "text": text,
            }

            out.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

            total_chars += len(text)
            extracted_pages += 1

print("Extracted pages:", extracted_pages)
print("Total characters:", total_chars)
print("Output:", OUTPUT)
