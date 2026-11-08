import unittest
from engines.yijing_cast import build_cast_result
from engines.yijing_line_rules import analyze_lines, format_line_analysis
from rag.fusion import build_fusion_prompt, fuse_readings


class TestRules(unittest.TestCase):
    def test_tun_upper_six_has_no_proper_correspondence(self):
        cast = build_cast_result([7, 8, 8, 8, 7, 6])
        upper = analyze_lines(cast)[5]
        self.assertTrue(upper["correct_position"])
        self.assertFalse(upper["central"])
        self.assertEqual(upper["corresponding_position"], 3)
        self.assertFalse(upper["proper_correspondence"])
        self.assertIn("无正应", format_line_analysis(cast))

    def test_six_yang_and_six_yin(self):
        yang = analyze_lines(build_cast_result([7] * 6))
        yin = analyze_lines(build_cast_result([8] * 6))
        self.assertEqual(sum(x["correct_position"] for x in yang), 3)
        self.assertEqual(sum(x["correct_position"] for x in yin), 3)
        self.assertTrue(all(not x["proper_correspondence"] for x in yang))
        self.assertTrue(all(not x["proper_correspondence"] for x in yin))

    def test_complementary_pairs(self):
        # All three opposite yin/yang pairs form proper correspondences.
        lines = analyze_lines(build_cast_result([7, 7, 7, 8, 8, 8]))
        self.assertTrue(all(x["proper_correspondence"] for x in lines))


class TestFusion(unittest.TestCase):
    def test_dry_run_no_api(self):
        tarot = {"spread": [{"card": "The Hermit"}], "answer": "独立的塔罗解释"}
        yijing = {"cast": {"moving_positions": [6]}, "answer": "独立的周易解释"}
        result = fuse_readings("如何行动？", tarot, yijing, dry_run=True)
        self.assertEqual(result["answer"], "")
        self.assertIn("独立的塔罗解释", result["prompt"])
        self.assertIn("独立的周易解释", result["prompt"])

    def test_missing_interpretation_rejected(self):
        with self.assertRaises(ValueError):
            build_fusion_prompt("问题", {"spread": []}, {"answer": "周易解释"})


if __name__ == "__main__":
    unittest.main()
