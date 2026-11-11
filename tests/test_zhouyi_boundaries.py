"""Synthetic, non-copyrighted OCR fixtures for precise chapter resolution."""
import copy
import unittest
from unittest.mock import patch

from engines.yijing_cast import build_cast_result
from rag.zhouyi_boundaries import resolve_start, resolve_boundaries
from rag.zhouyi_exact import get_chapter
from rag.zhouyi_source_audit import audit_page_citations
from rag.spread import check_citations


def entry(number, name, start, end, title=None):
    return {"number": number, "name": name, "start_pdf_page": start,
            "end_pdf_page_inclusive": end, "end_boundary_verified": False,
            "needs_review": True, "heading_context_ocr": [title or name]}


class ChapterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.pages = {
            1: "前章结尾\n  渐（图）\n\n 【题解】\n渐的测试资料\n",
            2: "渐的末段\n  归1妹（图）\n\n 【题解】\n归妹的测试资料\n",
            3: "归妹的末段\n  丰（图）\n\n 【题解】\n丰的测试资料\n",
        }
        self.sections = {"hexagrams": [
            entry(53, "渐", 1, 2, "渐（图）"),
            entry(54, "归妹", 2, 3, "归1妹（图）"),
            entry(55, "丰", 3, 4, "丰（图）"),
        ], "appendices": []}

    def test_observed_cast_mapping_is_unchanged(self):
        cast = build_cast_result([8, 8, 6, 8, 7, 7])
        self.assertEqual(cast["original_hexagram"]["number"], 20)
        self.assertEqual(cast["changed_hexagram"]["number"], 53)
        self.assertEqual(cast["moving_line_labels"], ["六三"])

    def test_next_title_is_an_endpoint_not_evidence(self):
        chapter = get_chapter(self.pages, 53, self.sections)
        text = "".join(item["text"] for item in chapter["segments"])
        self.assertIn("渐的末段", text)
        self.assertNotIn("归1妹", text)
        self.assertNotIn("归妹的测试", text)
        self.assertNotIn("前章结尾", text)
        self.assertEqual(chapter["boundaries"]["end_boundary_name"], "归妹")

    def test_endpoint_error_identifies_requested_and_boundary_chapters(self):
        pages = {**self.pages, 2: "没有足够的章首证据"}
        with self.assertRaisesRegex(ValueError, "《渐》结束边界《归妹》"):
            get_chapter(pages, 53, self.sections)

    def test_inserted_digit_is_a_general_title_rule(self):
        pages = {1: "小3过（图）\n【题解】\n测试"}
        boundary = resolve_start(pages, entry(62, "小过", 1, 2, "小3过（图）"))
        self.assertEqual(boundary["offset"], 0)

    def test_established_title_variant(self):
        boundary = resolve_start({1: "遁（图）\n【题解】\n测试"}, entry(33, "遯", 1, 2))
        self.assertEqual(boundary["offset"], 0)

    def test_recorded_misspelling_requires_both_independent_body_anchors(self):
        record = entry(25, "无妄", 1, 2, "无安（图）")
        valid = "无安（图）\n【题解】\n《无妄》测试，《无妄》说明。\n无妄：测试卦辞。\n"
        result = resolve_start({1: valid}, record)
        self.assertIn("judgement", result["method"])
        for invalid in [valid.replace("无妄：", "注释："), valid.replace("《无妄》", "《其他》")]:
            with self.assertRaises(ValueError):
                resolve_start({1: invalid}, record)

    def test_wrong_known_title_cannot_be_relabelled_using_body_mentions(self):
        record = entry(54, "归妹", 1, 2, "丰（图）")
        pages = {1: "丰（图）\n【题解】\n《归妹》对比《归妹》。\n归妹：引用。\n"}
        with self.assertRaises(ValueError):
            resolve_start(pages, record)

    def test_misspelling_cannot_borrow_identity_from_next_chapter_page(self):
        pages = {
            1: "误字（图）\n【题解】\n不相关内容。",
            2: "渐（图）\n【题解】\n《渐》与《渐》说明。\n渐：卦辞。",
        }
        with self.assertRaises(ValueError):
            resolve_start(pages, entry(53, "渐", 1, 2, "误字（图）"))

    def test_provisional_page_alone_is_not_a_boundary(self):
        with self.assertRaises(ValueError):
            resolve_start({1: "只有正文，无标题、无题解"}, entry(20, "观", 1, 2))

    def test_duplicate_titles_fail_closed(self):
        pages = {1: "观（图）\n【题解】\n测试\n观（图）\n【题解】\n测试"}
        with self.assertRaisesRegex(ValueError, "候选2个"):
            resolve_start(pages, entry(20, "观", 1, 2))

    def test_conflicting_or_missing_metadata_fails_closed(self):
        wrong = copy.deepcopy(self.sections)
        wrong["hexagrams"][0]["name"] = "观"
        with self.assertRaisesRegex(ValueError, "name/number"):
            resolve_boundaries(self.pages, 53, wrong)
        wrong = copy.deepcopy(self.sections)
        wrong["hexagrams"][0]["end_pdf_page_inclusive"] = 3
        with self.assertRaisesRegex(ValueError, "end page conflicts"):
            resolve_boundaries(self.pages, 53, wrong)
        with self.assertRaises(ValueError):
            get_chapter({1: self.pages[1]}, 53, self.sections)

    def test_last_chapter_stops_before_correlated_appendix(self):
        pages = {1: "未济（图）\n【题解】\n末卦资料\n", 2: "周易系辞上\n【题解】\n附录资料"}
        sections = {"hexagrams": [entry(64, "未济", 1, 2)], "appendices": [
            {"name": "系辞上传", "start_pdf_page": 2},
        ]}
        chapter = get_chapter(pages, 64, sections)
        self.assertEqual([item["pdf_page"] for item in chapter["segments"]], [1])
        self.assertNotIn("系辞", "".join(item["text"] for item in chapter["segments"]))
        sections["appendices"] = []
        with self.assertRaisesRegex(ValueError, "verified appendix"):
            get_chapter(pages, 64, sections)

    def test_strict_citation_validation_has_not_been_relaxed(self):
        audit = audit_page_citations("[《周易》，PDF第489页]", [{"pdf_page": 480, "verified": True}])
        self.assertFalse(audit["passed"])
        invalid, _ = check_citations("[EXACT_Pollack_the_magician]", [{"id": "EXACT_POLLACK_the_magician"}], [])
        self.assertEqual(invalid, ["EXACT_Pollack_the_magician"])


if __name__ == "__main__":
    unittest.main()
