"""READ-ONLY: UPSC pipeline backfill progress (ledger, watermark, what remains)."""
import os, time, libsql_client
m = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
u = libsql_client.create_client_sync(url=os.environ["SATYA_UPSC_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_UPSC_DB_TOKEN"])
now = int(time.time())
print("meta:", [tuple(r) for r in u.execute("SELECT key, value FROM upsc_meta").rows])
print("ledger by verdict:", [tuple(r) for r in u.execute("SELECT verdict, COUNT(*), MIN(article_id), MAX(article_id) FROM upsc_processed GROUP BY verdict").rows])
print("notes:", u.execute("SELECT COUNT(*), MIN(published_at), MAX(published_at) FROM upsc_articles").rows)
for d in (30, 90, 180, 365):
    f = m.execute("SELECT id FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [now - d * 86400]).rows
    print(f"{d}d floor id:", f[0][0] if f else None)
print("oldest article:", m.execute("SELECT MIN(scraped_at), MIN(id) FROM articles").rows)
done_below = u.execute("SELECT COUNT(*) FROM upsc_processed WHERE article_id >= ?", [0]).rows
print("claims open:", u.execute("SELECT COUNT(*) FROM upsc_claims").rows)
print("processed per day (last 7d):", [tuple(r) for r in u.execute("SELECT date(processed_at,'unixepoch') d, COUNT(*) FROM upsc_processed WHERE processed_at >= ? GROUP BY d ORDER BY d", [now - 7 * 86400]).rows])
m.close(); u.close()
