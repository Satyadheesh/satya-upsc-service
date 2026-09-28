"""READ-ONLY: Hindi translation backlog (articles.translated_hi, events.translated_hi)."""
import os, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
def q(t, s):
    rs = c.execute(s); print(f"\n### {t}\n\n| " + " | ".join(rs.columns) + " |\n|" + "---|" * len(rs.columns))
    for r in rs.rows: print("| " + " | ".join(str(v) for v in r) + " |")
q("articles by translated_hi (rephrased only)", "SELECT translated_hi, COUNT(*) n, MIN(id), MAX(id) FROM articles WHERE rephrased_article IS NOT NULL GROUP BY translated_hi")
q("untranslated rephrased articles by day (last 14 days)", """SELECT date(scraped_at,'unixepoch') d, COUNT(*) total, SUM(translated_hi=1) done, SUM(translated_hi=0) todo
  FROM articles WHERE rephrased_article IS NOT NULL AND scraped_at >= strftime('%s','now','-14 days') GROUP BY d ORDER BY d""")
q("last translated article", "SELECT MAX(id) FROM articles WHERE translated_hi = 1")
q("events by translated_hi", "SELECT translated_hi, COUNT(*) FROM events GROUP BY translated_hi")
c.close()
