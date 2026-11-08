
import json
from pathlib import Path
from rag.runtime_data import knowledge_path

ROOT = Path(__file__).resolve().parents[1]

INDEX_FILE = knowledge_path("data/structured/tarot_sections.json")
PAGES_FILE = knowledge_path("data/extracted/tarot_pages.jsonl")


def get_card_section(card_id):
    sections = json.loads(
        INDEX_FILE.read_text(encoding="utf-8")
    )

    card = sections.get(card_id)

    if card is None:
        return None

    pages = []

    with PAGES_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)

            if (
                card["pdf_start_page"]
                <= record["pdf_page"]
                <= card["pdf_end_page"]
            ):
                pages.append(record)

    return {
        "card": card,
        "pages": pages
    }


if __name__ == "__main__":
    result = get_card_section("knight_of_cups")

    if result is None:
        print("Card not found")
    else:
        print("Card:", result["card"]["name_en"])
        print("PDF pages:",
              result["card"]["pdf_start_page"],
              "-",
              result["card"]["pdf_end_page"])

        for page in result["pages"]:
            print("\n" + "=" * 50)
            print("PDF page:", page["pdf_page"])
            print(page["text"][:700])
