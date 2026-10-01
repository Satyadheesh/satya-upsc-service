"""READ-ONLY: why the headline validator never runs - test its pre-check SQL as written."""
import os, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
cut = int(time.time()) - 3 * 86400
base = "FROM articles INDEXED BY idx_articles_scraped WHERE scraped_at >= {} AND rephrased_title IS NOT NULL AND rephrased_title != {} AND (headline_verified = 0 OR headline_verified IS NULL)"
for label, lit in (('double-quoted ""', '""'), ("single-quoted ''", "''")):
    try:
        print(label, "->", c.execute("SELECT COUNT(*) " + base.format(cut, lit)).rows)
    except Exception as e:
        print(label, "-> ERROR:", e)
# when were articles last verified, and how were unverified ones produced
print("verified=1 by day:", c.execute("SELECT date(scraped_at,'unixepoch') d, SUM(headline_verified=1), COUNT(*) FROM articles WHERE scraped_at >= ? GROUP BY d ORDER BY d", [int(time.time()) - 14*86400]).rows)
c.close()
