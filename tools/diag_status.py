"""READ-ONLY: article status pipeline health (classified -> entity_processed -> processed)."""
import os, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
def q(t, s):
    rs = c.execute(s); print(f"\n### {t}\n\n| " + " | ".join(rs.columns) + " |\n|" + "---|" * len(rs.columns))
    for r in rs.rows: print("| " + " | ".join(str(v) for v in r) + " |")
q("status by day (since Sep 15)", """SELECT date(scraped_at,'unixepoch') d, COUNT(*) total, SUM(status='rephrased') rephrased,
  SUM(status='classified') classified, SUM(status='entity_processed') entity_processed, SUM(status='processed') processed
  FROM articles WHERE scraped_at >= strftime('%s','2026-09-15') GROUP BY d ORDER BY d""")
q("totals (last 30 days)", "SELECT status, COUNT(*) FROM articles WHERE scraped_at >= strftime('%s','now','-30 days') GROUP BY status")
c.close()
