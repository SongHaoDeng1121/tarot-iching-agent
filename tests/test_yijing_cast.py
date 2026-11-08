
# tests/test_yijing_cast.py

import unittest

from engines.hexagram_utils import (
    HEXAGRAM_INDEX,
    identify_hexagram,
    get_hexagram_by_number,
)

from engines.yijing_cast import (
    build_cast_result,
    cast_hexagram,
)


class TestHexagramMapping(unittest.TestCase):

    def test_all_64_hexagrams(self):
        self.assertEqual(
            len(HEXAGRAM_INDEX), 64
        )

        numbers = {
            item["number"]
            for item in HEXAGRAM_INDEX.values()
        }

        self.assertEqual(
            numbers, set(range(1, 65))
        )

    def test_all_numbers_roundtrip(self):
        for number in range(1, 65):
            info = get_hexagram_by_number(number)
            rebuilt = identify_hexagram(
                info["lines_bottom_to_top"]
            )
            self.assertEqual(rebuilt["number"], number)

    def test_qian(self):
        info = identify_hexagram([1] * 6)
        self.assertEqual(info["number"], 1)
        self.assertEqual(info["name"], "乾")

    def test_kun(self):
        info = identify_hexagram([0] * 6)
        self.assertEqual(info["number"], 2)
        self.assertEqual(info["name"], "坤")

    def test_song(self):
        # 讼：上乾下坎
        # 坎（下）= 0,1,0
        # 乾（上）= 1,1,1
        info = identify_hexagram(
            [0, 1, 0, 1, 1, 1]
        )
        self.assertEqual(info["number"], 6)
        self.assertEqual(info["name"], "讼")

    def test_xu(self):
        # 需：上坎下乾
        info = identify_hexagram(
            [1, 1, 1, 0, 1, 0]
        )
        self.assertEqual(info["number"], 5)
        self.assertEqual(info["name"], "需")

    def test_tai(self):
        # 泰：上坤下乾
        info = identify_hexagram(
            [1, 1, 1, 0, 0, 0]
        )
        self.assertEqual(info["number"], 11)

    def test_pi(self):
        # 否：上乾下坤
        info = identify_hexagram(
            [0, 0, 0, 1, 1, 1]
        )
        self.assertEqual(info["number"], 12)


class TestCasting(unittest.TestCase):

    def test_six_old_yin(self):
        result = build_cast_result([6] * 6)

        self.assertEqual(
            result["original_hexagram"]["number"], 2
        )
        self.assertEqual(
            result["changed_hexagram"]["number"], 1
        )
        self.assertEqual(
            result["moving_positions"],
            [1, 2, 3, 4, 5, 6]
        )

    def test_six_old_yang(self):
        result = build_cast_result([9] * 6)

        self.assertEqual(
            result["original_hexagram"]["number"], 1
        )
        self.assertEqual(
            result["changed_hexagram"]["number"], 2
        )

    def test_no_changes(self):
        result = build_cast_result(
            [7, 8, 7, 8, 7, 8]
        )

        self.assertFalse(result["has_changes"])
        self.assertEqual(result["moving_positions"], [])

        self.assertEqual(
            result["original_hexagram"]["number"],
            result["changed_hexagram"]["number"]
        )

    def test_old_yin_and_old_yang(self):
        result = build_cast_result(
            [7, 8, 9, 7, 6, 8]
        )

        self.assertEqual(
            result["moving_positions"],
            [3, 5]
        )
        self.assertEqual(
            result["moving_line_labels"],
            ["九三", "六五"]
        )

        self.assertEqual(result["lines"][2]["changed_yang"], 0)
        self.assertEqual(result["lines"][4]["changed_yang"], 1)

    def test_random_cast_validity(self):
        for _ in range(100):
            result = cast_hexagram()

            self.assertEqual(len(result["lines"]), 6)
            self.assertTrue(
                all(
                    v in (6, 7, 8, 9)
                    for v in result["line_values_bottom_to_top"]
                )
            )
            self.assertTrue(
                1 <= result["original_hexagram"]["number"] <= 64
            )
            self.assertTrue(
                1 <= result["changed_hexagram"]["number"] <= 64
            )

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            build_cast_result([7, 8, 9])

        with self.assertRaises(ValueError):
            build_cast_result([7, 8, 9, 7, 6, 10])


if __name__ == "__main__":
    unittest.main()
