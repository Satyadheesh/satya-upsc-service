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
        self.assertEqual(prefilter("Man arrested for robbery", "crime"), "category:crime")
        self.assertEqual(prefilter("Delhi Police files chargesheet in minor's rape case", "regional"), "sensitive_crime")
        self.assertEqual(prefilter("Accused remanded to custody in POCSO case", "crime"), "sensitive_crime")
        self.assertEqual(prefilter("Man arrested for stabbing woman", "crime"), "sensitive_crime")
        self.assertTrue(prefilter("Parimala and Co movie review: lazy", "other").startswith("noise"))
        self.assertTrue(prefilter("Veteran actor passes away", "regional").startswith("noise"))

    def test_keeps(self):
        self.assertIsNone(prefilter("NIA searches nine locations in J&K", "crime"))
        self.assertIsNone(prefilter("Papa Rao, 17 other Maoists surrender", "crime"))
        self.assertIsNone(prefilter("Supreme Court 5-judge Constitution Bench hearing on marital rape exception", "judiciary"))
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
        self.assertEqual(validate_gate({"hook": "economy", "score": 4, "reason": "x"})["score"], 4)
        self.assertEqual(validate_gate({"hook": "none", "score": 4, "reason": "x"})["score"], 1)
        self.assertEqual(validate_gate({"score": 4, "reason": "x"})["score"], 1)  # missing hook = none
        g = lambda **k: validate_gate({"hook": "law_policy_scheme", "scope": "national", "party_political": False,
                                       "score": 4, "reason": "x", **k})["score"]
        self.assertEqual(g(), 4)
        self.assertEqual(g(scope="local"), 1)
        self.assertEqual(g(party_political=True), 1)
        self.assertEqual(g(scope="international_other"), 1)                   # foreign + non-global hook
        self.assertEqual(g(scope="international_other", hook="report_index"), 4)
        self.assertEqual(g(scope="international_other", hook="report_index", score=3), 3)  # UN report etc.
        self.assertEqual(g(scope="international_other", hook="global_affairs", score=3), 2)
        self.assertEqual(g(hook="court_constitutional", party_political=True), 4)
        self.assertEqual(g(hook="history_culture", scope="local", score=3), 3)
        self.assertEqual(g(scope="state", score=3), 3)
        v = lambda india: validate_gate({"hook": "law_policy_scheme", "scope": "national", "party_political": False,
                                         "score": 4, "reason": "x"}, india)["score"]
        self.assertEqual(v(False), 1)  # "national" but text never mentions India

    def test_india_link(self):
        from analyzer import india_link
        self.assertTrue(india_link("Kerala HC order", ""))
        self.assertTrue(india_link("Scheme gets Rs 500 crore", ""))
        self.assertTrue(india_link("PM visits Sri Lanka", "Prime Minister of India said"))
        self.assertFalse(india_link("NSW considering plan to halve power of ebikes", "Sydney council said"))
        self.assertFalse(india_link("Hondurans vote amid Trump threat", "Tegucigalpa"))
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

        # Test boilerplate stripping and generic label discarding
        boilerplate_case = {
            **GOOD,
            "mains_dimensions": [
                "Way forward: Strengthen inter-ministerial coordination between FSSAI and state bodies",
                "Challenges: Enforcement deficit due to shortage of food inspectors under IMS Act",
                "Significance",
                "Role of technology",
            ]
        }
        res = validate_notes(boilerplate_case)
        self.assertEqual(res["mains_dimensions"], [
            "Strengthen inter-ministerial coordination between FSSAI and state bodies",
            "Enforcement deficit due to shortage of food inspectors under IMS Act",
        ])

    def test_notes_reject(self):
        with self.assertRaises(InvalidOutput):
            validate_notes({**GOOD, "node": "made_up"})
        with self.assertRaises(InvalidOutput):
            validate_notes({**GOOD, "fact_box": "short"})
        # Sensitive crime misclassified as terrorism_insurgency must be rejected
        with self.assertRaises(InvalidOutput):
            validate_notes({
                **GOOD,
                "node": "terrorism_insurgency",
                "why_in_news": "Delhi Police filed chargesheet in minor rape case before court.",
                "fact_box": "The accused was remanded to custody in connection with the minor's rape and POCSO offense.",
            })
        # Legitimate terrorism note must pass
        valid_sec = validate_notes({
            **GOOD,
            "node": "terrorism_insurgency",
            "why_in_news": "NIA filed chargesheet against J&K terror funding operatives.",
            "fact_box": "Five individuals affiliated with a banned militant outfit in Kashmir were booked under UAPA.",
        })
        self.assertEqual(valid_sec["syllabus_node"], "terrorism_insurgency")

    def test_schema_enums_match_syllabus(self):
        self.assertEqual(NOTES_SCHEMA["properties"]["subject"]["enum"], list(SYLLABUS))


if __name__ == "__main__":
    unittest.main()
