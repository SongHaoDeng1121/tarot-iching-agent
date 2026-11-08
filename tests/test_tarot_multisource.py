import json
import unittest
from pathlib import Path

from rag.answer import load_cards
from rag.hybrid_tarot import retrieve_for_card
from rag.spread import prepare_exact_evidence, validate_spread
from rag.tarot_sources import greer_exact_evidence, load_source_chunks

ROOT = Path(__file__).resolve().parents[1]


class TarotMultiSourceTests(unittest.TestCase):
    def test_all_card_boundaries_are_complete(self):
        path = ROOT / "data/structured/greer_tarot_reversals_sections.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["cards"]), 78)
        self.assertTrue(all(
            item["status"] == "detected" and item.get("orientation_spans")
            for item in data["cards"].values()
        ))

    def test_chunk_ids_are_unique_and_cover_all_cards(self):
        chunks = load_source_chunks(
            "data/chunks/greer_tarot_reversals_chunks.jsonl"
        )
        self.assertEqual(len(chunks), len({item["chunk_id"] for item in chunks}))
        self.assertEqual(
            len({item["card_id"] for item in chunks if item.get("card_id")}),
            78,
        )

    def test_greer_reversed_exact_evidence_is_card_specific(self):
        evidence = greer_exact_evidence("the_magician", "reversed")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["card_id"], "the_magician")
        self.assertIn("REVERSED CONTEXT", evidence["text"])
        self.assertIn(57, evidence["pages"])

    def test_spread_exact_evidence_has_both_sources_per_card(self):
        spread = {
            "question": "What should I understand?",
            "cards": [
                {"card_id": "five_of_pentacles", "orientation": "upright", "position": "Thoughts"},
                {"card_id": "king_of_cups", "orientation": "upright", "position": "Feelings"},
                {"card_id": "four_of_pentacles", "orientation": "upright", "position": "Actions"},
            ],
        }
        knowledge = load_cards()
        validate_spread(spread, knowledge)
        evidence = prepare_exact_evidence(spread, knowledge)
        self.assertEqual(len(evidence), 6)
        for card in spread["cards"]:
            sources = {
                item["source_id"] for item in evidence
                if item["card_id"] == card["card_id"]
            }
            self.assertEqual(
                sources, {"pollack_78_degrees", "greer_tarot_reversals"}
            )

    def test_offline_hybrid_prioritizes_selected_card(self):
        results = retrieve_for_card(
            question="The Magician reversed in Thoughts",
            card_id="the_magician",
            card_name="The Magician",
            orientation="reversed",
            position="Thoughts",
            top_k=3,
            include_vectors=False,
        )
        self.assertEqual(results[0]["card_id"], "the_magician")
        self.assertIn("greer_tarot_reversals", {item["source_id"] for item in results})
        self.assertIn("pollack_78_degrees", {item["source_id"] for item in results})


if __name__ == "__main__":
    unittest.main()
