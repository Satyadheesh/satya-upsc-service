"""Apply schema v2 to the satya-upsc Turso DB.

  python migrate.py          # create/upgrade tables (safe, idempotent)
  python migrate.py --retry-failed   # clear 'failed' ledger rows so they are retried

Reads SATYA_UPSC_DB_URL / SATYA_UPSC_DB_TOKEN from env or a .env up the tree.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
from turso_http import execute, rows  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def split_sql(text):
    out, buf = [], []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";")
            if stmt:
                out.append(stmt)
            buf = []
    return out


def main():
    # v1 -> v2: old upsc_articles lacks upsc_score. Drop if empty, else keep a backup.
    cols = rows(execute(["PRAGMA table_info(upsc_articles)"])[0])
    names = {c[1] for c in cols}
    if names and "upsc_score" not in names:
        n = int(rows(execute(["SELECT COUNT(*) FROM upsc_articles"])[0])[0][0])
        if n == 0:
            print("Dropping empty v1 upsc_articles")
            execute(["DROP TABLE upsc_articles"])
        else:
            print(f"Renaming v1 upsc_articles ({n} rows) -> upsc_articles_v1")
            execute(["DROP TABLE IF EXISTS upsc_articles_v1",
                     "ALTER TABLE upsc_articles RENAME TO upsc_articles_v1"])
        execute(["DROP INDEX IF EXISTS idx_upsc_paper"])
    execute(["DROP TABLE IF EXISTS upsc_checkpoint"])

    with open(os.path.join(HERE, "schema.sql")) as f:
        execute(split_sql(f.read()))
    print("Schema v2 applied.")

    if "--retry-failed" in sys.argv:
        execute(["DELETE FROM upsc_processed WHERE verdict = 'failed'"])
        print("Cleared failed rows.")

    for t in ("upsc_articles", "upsc_processed", "upsc_claims"):
        print(t, rows(execute([f"SELECT COUNT(*) FROM {t}"])[0])[0][0])


if __name__ == "__main__":
    main()
