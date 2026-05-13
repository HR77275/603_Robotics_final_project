import unittest

from cs603_voice_intent.intent_classifier import (
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_STOP,
    CMD_UNKNOWN,
    classify_intent,
    normalize_text,
)


class IntentClassifierTest(unittest.TestCase):
    def test_stop_synonyms_win_first(self):
        self.assertEqual(classify_intent("please stop following me"), CMD_STOP)
        self.assertEqual(classify_intent("red light"), CMD_STOP)
        self.assertEqual(classify_intent("wait"), CMD_STOP)

    def test_approach_synonyms(self):
        self.assertEqual(classify_intent("come here"), CMD_APPROACH)
        self.assertEqual(classify_intent("come over"), CMD_APPROACH)
        self.assertEqual(classify_intent("move closer please"), CMD_APPROACH)

    def test_follow_synonyms(self):
        self.assertEqual(classify_intent("follow me"), CMD_FOLLOW)
        self.assertEqual(classify_intent("come along"), CMD_FOLLOW)
        self.assertEqual(classify_intent("green light"), CMD_FOLLOW)

    def test_unknown(self):
        self.assertEqual(classify_intent("bring me coffee"), CMD_UNKNOWN)

    def test_normalizes_case_punctuation_and_spacing(self):
        self.assertEqual(normalize_text("  STOP,   Robot!!! "), "stop robot")
        self.assertEqual(classify_intent("GREEN-light"), CMD_FOLLOW)

    def test_empty_or_punctuation_only_text_is_unknown(self):
        self.assertEqual(classify_intent(""), CMD_UNKNOWN)
        self.assertEqual(classify_intent("   !!!   "), CMD_UNKNOWN)

    def test_command_words_require_word_boundaries(self):
        self.assertEqual(classify_intent("the stopper is ongoing"), CMD_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
