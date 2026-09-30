"""READ-ONLY: Hindi translation coverage per news source (last 7 and 30 days)."""
import os, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
def q(t, s):
    rs = c.execute(s); print(f"\n### {t}\n\n| " + " | ".join(rs.columns) + " |\n|" + "---|" * len(rs.columns))
    for r in rs.rows: print("| " + " | ".join(str(v) for v in r) + " |")
q("per source, last 7 / 30 days (classified+)", """
SELECT s.name AS source,
  SUM(a.scraped_at >= strftime('%s','now','-7 days')) AS n7,
  SUM(a.scraped_at >= strftime('%s','now','-7 days') AND a.translated_hi = 1) AS hi7,
  SUM(a.scraped_at >= strftime('%s','now','-30 days')) AS n30,
  SUM(a.scraped_at >= strftime('%s','now','-30 days') AND a.translated_hi = 1) AS hi30
FROM articles a JOIN sources s ON s.id = a.source_id
WHERE a.status IN ('classified','entity_processed','processed') AND a.scraped_at >= strftime('%s','now','-30 days')
GROUP BY s.name ORDER BY n30 DESC LIMIT 40""")
c.close()
