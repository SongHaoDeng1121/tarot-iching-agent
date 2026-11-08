
# scripts/fix_tarot_boundaries.py

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INDEX = ROOT / "data/structured/tarot_sections_auto.json"
BACKUP = ROOT / "data/structured/tarot_sections_auto.backup.json"

# 下一章节的起点，作为当前卡牌的排他性终点
# (pdf_page, character_offset)
BOUNDARIES = {
    "the_world": (159, 0),
    "ace_of_wands": (200, 0),
    "ace_of_cups": (224, 0),
    "ace_of_swords": (248, 0),
    "ace_of_pentacles": (277, 0),
}


def main():
    data = json.loads(INDEX.read_text(encoding="utf-8"))

    # 保存现有识别结果，方便需要时恢复
    shutil.copy2(INDEX, BACKUP)

    for card_id, (end_page, end_offset) in BOUNDARIES.items():
        card = data[card_id]

        if card.get("pdf_start_page") is None:
            raise ValueError(f"Missing start for {card_id}")

        if (end_page, end_offset) <= (
            card["pdf_start_page"],
            card["start_offset"],
        ):
            raise ValueError(f"Invalid boundary: {card_id}")

        card["pdf_end_page"] = end_page
        card["end_offset_exclusive"] = end_offset
        card["end_boundary_is_next_heading"] = False
        card["boundary_source"] = "verified_part_or_chapter_start"
        card["status"] = "candidate"
        card["needs_review"] = True

        print(
            f"Fixed: {card_id} | "
            f"{card['pdf_start_page']} -> {end_page}"
        )

    INDEX.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nBoundary repair complete.")
    print("Backup:", BACKUP)


if __name__ == "__main__":
    main()
