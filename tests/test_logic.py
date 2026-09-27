import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import InvalidOutput, NOTES_SCHEMA, validate_gate, validate_notes  # noqa: E402
from selection import is_done, make_shards, prefilter  # noqa: E402
from syllabus import SYLLABUS  # noqa: E402


class Prefilter(unittest.TestCase):
    def test_drops(self):
        self.assertEqual(prefilter("India win the T20 final", "sports"), "category:sports")
        self.assertEqual(prefilter("Man arrested for stabbing woman", "crime"), "category:crime")
        self.assertTrue(prefilter("Parimala and Co movie review: lazy", "other").startswith("noise"))
        self.assertTrue(prefilter("Veteran actor passes away", "regional").startswith("noise"))

    def test_keeps(self):
        self.assertIsNone(prefilter("NIA searches nine locations in J&K", "crime"))
        self.assertIsNone(prefilter("Papa Rao, 17 other Maoists surrender", "crime"))
        self.assertIsNone(prefilter("PM Modi launches multi-nation tour", "politics"))   # 'odi' in Modi
        self.assertIsNone(prefilter("PSG celebrations spark clashes", "international"))  # 'celeb'
        self.assertIsNone(prefilter("Capital Factory founder killed", "international"))  # 'actor'
        self.assertIsNone(prefilter("Putin to visit India in December", "international"))

    def test_empty(self):
        self.assertEqual(prefilter("", "politics"), "empty_title")


class Ledger(unittest.TestCase):
    def test_done(self):
        self.assertFalse(is_done(None))
        self.assertTrue(is_done(("irrelevant", 1)))
        self.assertTrue(is_done(("prefiltered", 1)))
        self.assertFalse(is_done(("failed", 2)))
        self.assertTrue(is_done(("failed", 3)))

    def test_shards(self):
        s = make_shards(list(range(1, 24)), 10)
        self.assertEqual(len(s), 10)
        self.assertEqual(sorted(int(x) for sh in s for x in sh.split(",")), list(range(1, 24)))
        self.assertEqual(make_shards([5, 6], 10), ["5", "6"])
        self.assertEqual(make_shards([], 10), [])


GOOD = {
    "exam_type": "both", "subject": "ir", "node": "judiciary",  # wrong subject: node wins
    "secondary": [{"subject": "polity", "node": "elections"}, {"subject": "polity", "node": "judiciary"}],
    "why_in_news": "Supreme Court said ECI citizenship scrutiny powers are limited.",
    "fact_box": "ECI told the Supreme Court that it cannot decide citizenship during SIR.",
    "prelims_pointers": [{"type": "constitution", "text": "Article 324: superintendence of elections"},
                         {"type": "bogus", "text": "Representation of the People Act, 1950"}],
    "mains_question": "Discuss the limits of ECI powers during electoral roll revision.",
    "mains_dimensions": ["federal concerns", "federal concerns", "citizenship"],
    "keywords": ["SIR", "Article 324"],
}


class Validation(unittest.TestCase):
    def test_gate(self):
        self.assertEqual(validate_gate({"score": 4, "reason": "x"})["score"], 4)
        with self.assertRaises(InvalidOutput):
            validate_gate({"score": 9})
        with self.assertRaises(InvalidOutput):
            validate_gate({})

    def test_notes(self):
        n = validate_notes(GOOD)
        self.assertEqual((n["gs_paper"], n["subject"], n["syllabus_node"]), ("GS2", "polity", "judiciary"))
        self.assertEqual(n["secondary"], [])  # same-subject secondaries dropped
        self.assertEqual(n["prelims_pointers"][1]["type"], "data_fact")
        self.assertEqual(n["mains_dimensions"], ["federal concerns", "citizenship"])

    def test_notes_reject(self):
        with self.assertRaises(InvalidOutput):
            validate_notes({**GOOD, "node": "made_up"})
        with self.assertRaises(InvalidOutput):
            validate_notes({**GOOD, "fact_box": "short"})

    def test_schema_enums_match_syllabus(self):
        self.assertEqual(NOTES_SCHEMA["properties"]["subject"]["enum"], list(SYLLABUS))


if __name__ == "__main__":
    unittest.main()
