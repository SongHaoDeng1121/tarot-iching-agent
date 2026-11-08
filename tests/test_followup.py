"""Unit tests requiring dotenv/openai already installed in project .venv."""
import unittest
from rag.followup import build_followup_messages, answer_followup


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            'question': '我应该怎么调整行动？',
            'fusion': '建议先稳定当前节奏。',
            'tarot_spread': {'cards': [{'card_id': 'test', 'orientation': 'upright'}]},
            'cast': {'moving_line_labels': ['上六'], 'original_hexagram': {'name': '屯'}, 'changed_hexagram': {'name': '益'}},
            'tarot': {'answer': '塔罗侧重现状。'},
            'yijing': {'answer': '屯上六的爻辞需要具体分析。'},
            'followups': [{'question': '上六指什么？', 'answer': '是最上面的一爻。'}],
        }

    def test_retains_same_cast_and_spread(self):
        messages = build_followup_messages(self.record, '能解释具体一些吗？')
        content = messages[1]['content']
        self.assertIn('"屯"', content)
        self.assertIn('"益"', content)
        self.assertIn('"上六"', content)
        self.assertIn('"test"', content)

    def test_maintains_history(self):
        messages = build_followup_messages(self.record, '继续追问')
        self.assertEqual(messages[-3]['content'], '上六指什么？')
        self.assertEqual(messages[-2]['content'], '是最上面的一爻。')
        self.assertEqual(messages[-1]['content'], '继续追问')

    def test_dry_run_no_api_call(self):
        result = answer_followup(self.record, '追问', dry_run=True)
        self.assertEqual(result['answer'], '')
        self.assertGreaterEqual(len(result['messages']), 5)

    def test_rejects_undrawn(self):
        with self.assertRaises(ValueError):
            build_followup_messages({}, '追问')

    def test_rejects_empty_question(self):
        with self.assertRaises(ValueError):
            build_followup_messages(self.record, '  ')


if __name__ == '__main__':
    unittest.main()
