"""Integration regressions against an available authorized knowledge snapshot."""
import unittest

from engines.hexagram_utils import HEXAGRAM_NAMES
from engines.yijing_cast import build_cast_result
from rag.runtime_data import knowledge_path
from rag.zhouyi_exact import load_pages, get_chapter, retrieve_cast_evidence


@unittest.skipUnless(
    knowledge_path("data/extracted/zhouyi_pages.jsonl").is_file()
    and knowledge_path("data/structured/zhouyi_sections.json").is_file(),
    "Requires the private OCR and section metadata; use synthetic tests in public CI",
)
class PrivateChapterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = load_pages()

    def test_all_64_chapters_resolve_with_adjacent_exclusive_boundaries(self):
        previous = None
        for number, name in enumerate(HEXAGRAM_NAMES, 1):
            with self.subTest(number=number, name=name):
                chapter = get_chapter(self.pages, number)
                boundaries = chapter["boundaries"]
                self.assertEqual(chapter["name"], name)
                self.assertTrue(chapter["segments"])
                if previous:
                    self.assertEqual(
                        (previous["pdf_page"], previous["offset"]),
                        (boundaries["start"]["pdf_page"], boundaries["start"]["offset"]),
                    )
                previous = boundaries["end_exclusive"]
        self.assertEqual(previous["pdf_page"], 580)

    def test_observed_cast_evidence_excludes_guimei_and_uses_correct_line(self):
        cast = build_cast_result([8, 8, 6, 8, 7, 7])
        evidence = retrieve_cast_evidence(cast)
        self.assertEqual([item["name"] for item in evidence], ["观", "观·六三", "渐"])
        line = evidence[1]
        self.assertEqual([part["pdf_page"] for part in line["segments"]], [214, 215])
        self.assertTrue(line["segments"][0]["text"].lstrip().startswith("六三"))
        self.assertTrue(all(part["pdf_page"] < 489 for item in evidence for part in item["segments"]))


if __name__ == "__main__":
    unittest.main()
