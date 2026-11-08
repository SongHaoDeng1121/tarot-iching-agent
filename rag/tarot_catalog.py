"""Canonical Tarot identifiers shared by ingestion and retrieval."""

from __future__ import annotations

import re

MAJORS = [
    ("the_fool", "The Fool"),
    ("the_magician", "The Magician"),
    ("the_high_priestess", "The High Priestess"),
    ("the_empress", "The Empress"),
    ("the_emperor", "The Emperor"),
    ("the_hierophant", "The Hierophant"),
    ("the_lovers", "The Lovers"),
    ("the_chariot", "The Chariot"),
    ("strength", "Strength"),
    ("the_hermit", "The Hermit"),
    ("wheel_of_fortune", "Wheel of Fortune"),
    ("justice", "Justice"),
    ("the_hanged_man", "The Hanged Man"),
    ("death", "Death"),
    ("temperance", "Temperance"),
    ("the_devil", "The Devil"),
    ("the_tower", "The Tower"),
    ("the_star", "The Star"),
    ("the_moon", "The Moon"),
    ("the_sun", "The Sun"),
    ("judgement", "Judgement"),
    ("the_world", "The World"),
]

SUITS = ("wands", "cups", "swords", "pentacles")
NUMBER_RANKS = (
    "ace", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten",
)
COURT_RANKS = ("page", "knight", "queen", "king")


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("_"))


MINORS = [
    (f"{rank}_of_{suit}", f"{title_case(rank)} of {title_case(suit)}")
    for suit in SUITS
    for rank in NUMBER_RANKS
]

COURTS = [
    (f"{rank}_of_{suit}", f"{title_case(rank)} of {title_case(suit)}")
    for suit in SUITS
    for rank in COURT_RANKS
]

ORDERED_CARDS = MAJORS + MINORS + COURTS
CARD_BY_ID = dict(ORDERED_CARDS)


def compact_heading(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def source_heading_aliases(card_id: str, card_name: str) -> list[str]:
    aliases = [card_name]
    if card_id == "the_high_priestess":
        aliases.append("The High Priestess/Papess")
    elif card_id == "the_hierophant":
        aliases.append("The Hierophant/Pope")
    elif card_id == "wheel_of_fortune":
        aliases.append("The Wheel of Fortune")
    elif card_id.startswith("page_of_"):
        aliases.append(card_name.replace("Page", "Page (or Princess)", 1))
    elif card_id.startswith("knight_of_"):
        aliases.append(card_name.replace("Knight", "Knight (or Prince)", 1))
    return aliases


def card_metadata(card_id: str) -> dict[str, str | None]:
    name = CARD_BY_ID[card_id]
    if card_id in dict(MAJORS):
        return {
            "card_name": name,
            "arcana": "major",
            "suit": None,
            "rank": None,
        }
    rank, suit = card_id.split("_of_", 1)
    return {
        "card_name": name,
        "arcana": "minor",
        "suit": suit,
        "rank": rank,
    }
