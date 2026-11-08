
# scripts/download_tarot_images.py
# Download the 78 Rider-Waite-Smith tarot card images.

import json
from pathlib import Path
from urllib.request import Request, urlopen
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

KNOWLEDGE_FILE = (
    ROOT / "data/structured/tarot_meanings.json"
)

OUTPUT_DIR = ROOT / "assets/tarot"

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "seven102161/elaine-tarot-cards/"
    "main/cards"
)

# Major Arcana: Rider-Waite numbering
MAJOR = [
    "the_fool",
    "the_magician",
    "the_high_priestess",
    "the_empress",
    "the_emperor",
    "the_hierophant",
    "the_lovers",
    "the_chariot",
    "strength",
    "the_hermit",
    "wheel_of_fortune",
    "justice",
    "the_hanged_man",
    "death",
    "temperance",
    "the_devil",
    "the_tower",
    "the_star",
    "the_moon",
    "the_sun",
    "judgement",
    "the_world",
]

MAJOR_CODES = {
    card_id: f"ar{i:02d}"
    for i, card_id in enumerate(MAJOR)
}

# Compatible alternative card IDs
MAJOR_CODES.update({
    "the_strength": "ar08",
    "the_wheel_of_fortune": "ar10",
    "the_justice": "ar11",
    "the_death": "ar13",
    "the_temperance": "ar14",
    "the_judgement": "ar20",
    "judgment": "ar20",
    "the_judgment": "ar20",
})

SUIT_CODES = {
    "wands": "wa",
    "cups": "cu",
    "swords": "sw",
    "pentacles": "pe",
}

RANK_CODES = {
    "ace": "ac",
    "two": "02",
    "three": "03",
    "four": "04",
    "five": "05",
    "six": "06",
    "seven": "07",
    "eight": "08",
    "nine": "09",
    "ten": "10",
    "page": "pa",
    "knight": "kn",
    "queen": "qu",
    "king": "ki",
}


def card_id_to_image_code(card_id):
    """Convert local knowledge card_id to image code."""

    if card_id in MAJOR_CODES:
        return MAJOR_CODES[card_id]

    if "_of_" not in card_id:
        raise ValueError(f"Unknown major card: {card_id}")

    rank, suit = card_id.split("_of_", 1)

    if rank not in RANK_CODES:
        raise ValueError(f"Unknown rank: {rank}")

    if suit not in SUIT_CODES:
        raise ValueError(f"Unknown suit: {suit}")

    return SUIT_CODES[suit] + RANK_CODES[rank]


def download_image(card_id, code):
    """Download one image and verify its format."""

    destination = OUTPUT_DIR / f"{card_id}.jpg"

    if destination.exists():
        try:
            with Image.open(destination) as img:
                img.verify()
            return "existing"
        except Exception:
            destination.unlink()

    url = f"{BASE_URL}/{code}.jpg"

    request = Request(
        url,
        headers={"User-Agent": "TarotWisdom/1.0"},
    )

    temporary = destination.with_suffix(".tmp")

    try:
        with urlopen(request, timeout=25) as response:
            data = response.read()

        temporary.write_bytes(data)

        with Image.open(temporary) as img:
            if img.format != "JPEG":
                raise ValueError(
                    f"Unexpected image format for {card_id}"
                )
            img.verify()

        temporary.replace(destination)
        return "downloaded"

    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with KNOWLEDGE_FILE.open(
        "r", encoding="utf-8"
    ) as f:
        knowledge = json.load(f)

    card_ids = list(knowledge.keys())

    if len(card_ids) != 78:
        raise ValueError(
            f"Expected 78 cards, found {len(card_ids)}"
        )

    # Validate all mappings before downloading.
    mappings = {
        card_id: card_id_to_image_code(card_id)
        for card_id in card_ids
    }

    if len(set(mappings.values())) != 78:
        raise ValueError(
            "Image code mapping contains duplicates. "
            "Check card IDs."
        )

    successes = 0
    failures = []

    for index, (card_id, code) in enumerate(
        mappings.items(), start=1
    ):
        try:
            status = download_image(card_id, code)
            successes += 1
            print(
                f"[{index}/78] {card_id}: {status}"
            )
        except Exception as exc:
            failures.append((card_id, str(exc)))
            print(
                f"[{index}/78] {card_id}: FAILED - {exc}"
            )

    print("\n=== DOWNLOAD REPORT ===")
    print("Available images:", successes)
    print("Failed:", len(failures))
    print("Directory:", OUTPUT_DIR)

    if failures:
        for card_id, error in failures:
            print(card_id, error)
        raise SystemExit(
            "Some images are missing. "
            "Fix errors and run the script again."
        )


if __name__ == "__main__":
    main()
