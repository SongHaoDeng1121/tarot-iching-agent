
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data/extracted/tarot_pages.jsonl"

# 先查看圣杯组附近的页面
START_PAGE = 195
END_PAGE = 215

with FILE.open("r", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        page = record["pdf_page"]

        if not START_PAGE <= page <= END_PAGE:
            continue

        text = record["text"]

        # 识别 Knight、Queen、King 等可能的章节标题
        matches = re.findall(
            r"\b(?:KNIGHT|QUEEN|KING|PAGE|CUPS)\b",
            text,
            flags=re.IGNORECASE
        )

        print("=" * 50)
        print("PDF page:", page)
        print("Keywords:", matches[:15])
        print("First 350 characters:")
        print(text[:350].replace("\n", " "))
        print()
