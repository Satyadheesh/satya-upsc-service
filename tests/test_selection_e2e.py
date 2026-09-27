"""End-to-end run of setup_shards.main() against the local satya.db snapshot."""
import importlib
import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN_DB = os.path.join(os.path.dirname(ROOT), "satya.db")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import fake_libsql  # noqa: E402

sys.modules["libsql_client"] = fake_libsql


def split_sql(text):
    out, buf = [], []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(buf).strip().rstrip(";"))
            buf = []
    return [s for s in out if s]


@unittest.skipUnless(os.path.exists(MAIN_DB), "needs ../satya.db")
class E2E(unittest.TestCase):
    def setUp(self):
        upsc = sqlite3.connect(":memory:")
        for s in split_sql(open(os.path.join(ROOT, "schema.sql")).read()):
            upsc.execute(s)
        fake_libsql.DBS.update({"https://main": sqlite3.connect(f"file:{MAIN_DB}?mode=ro", uri=True),
                                "https://upsc": upsc})
        os.environ.update(SATYA_DB_URL="libsql://main", SATYA_DB_TOKEN="x", SATYA_UPSC_DB_URL="libsql://upsc",
                          SATYA_UPSC_DB_TOKEN="x", BATCH_SIZE="50", LOOKBACK_DAYS="400", RESCAN_DAYS="75")
        os.environ.pop("GITHUB_OUTPUT", None)
        import setup_shards
        self.mod = importlib.reload(setup_shards)
        self.upsc = upsc
        from analyzer import PROMPT_VERSION
        upsc.execute("INSERT INTO upsc_meta VALUES ('approved_prompt', ?)", [PROMPT_VERSION])
        upsc.commit()

    def test_unapproved_prompt_does_nothing(self):
        self.upsc.execute("DELETE FROM upsc_meta WHERE key='approved_prompt'")
        self.upsc.commit()
        self.assertEqual(self.run_once(), set())

    def run_once(self):
        self.mod.main()
        return {r[0] for r in self.upsc.execute("SELECT article_id FROM upsc_claims")}

    def test_runs_do_not_overlap_and_failures_retry(self):
        first = self.run_once()
        self.assertEqual(len(first), 50)
        pre = self.upsc.execute("SELECT COUNT(*) FROM upsc_processed WHERE verdict='prefiltered'").fetchone()[0]
        self.assertGreater(pre, 0)
        # second run while first is still claimed -> disjoint batch
        second = self.run_once() - first
        self.assertEqual(len(second), 50)
        # finish run 1: mark relevant, except one failure
        ids = sorted(first)
        for a in ids[1:]:
            self.upsc.execute("INSERT INTO upsc_processed (article_id, verdict, attempts, processed_at) VALUES (?, 'relevant', 1, 0)", [a])
        self.upsc.execute("INSERT INTO upsc_processed (article_id, verdict, attempts, processed_at) VALUES (?, 'failed', 1, 0)", [ids[0]])
        self.upsc.execute("DELETE FROM upsc_claims WHERE article_id IN (%s)" % ",".join(map(str, ids)))
        # expire run 2's claims -> they become failed attempts, and get retried
        self.upsc.execute("UPDATE upsc_claims SET claimed_at = 0")
        self.upsc.commit()
        third = self.run_once()
        self.assertIn(ids[0], third)            # explicit failure retried
        self.assertTrue(third & second)         # expired claims retried
        self.assertFalse(third & set(ids[1:]))  # finished work never re-selected
        wm = self.upsc.execute("SELECT value FROM upsc_meta WHERE key='backfill_below'").fetchone()
        self.assertIsNotNone(wm)


if __name__ == "__main__":
    unittest.main()
