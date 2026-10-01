"""READ-ONLY: work-queue sizes the background services scan (statuses, headline queues)."""
import os, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
q = lambda s, a=(): c.execute(s, list(a)).rows
now = int(time.time())
print("status all-time:", [tuple(r) for r in q("SELECT status, COUNT(*) FROM articles GROUP BY status")])
print("headline todo all-time:", q("SELECT COUNT(*) FROM articles WHERE rephrased_title IS NULL AND rephrased_article IS NOT NULL"))
print("headline unverified all-time:", q("SELECT COUNT(*) FROM articles WHERE rephrased_title IS NOT NULL AND rephrased_title != '' AND (headline_verified = 0 OR headline_verified IS NULL)"))
for d in (1, 3):
    cut = now - d * 86400
    print(f"{d}d window rows:", q("SELECT COUNT(*) FROM articles WHERE scraped_at >= ?", [cut]),
          "todo:", q("SELECT COUNT(*) FROM articles WHERE scraped_at >= ? AND rephrased_title IS NULL AND rephrased_article IS NOT NULL", [cut]),
          "unverified:", q("SELECT COUNT(*) FROM articles WHERE scraped_at >= ? AND rephrased_title IS NOT NULL AND rephrased_title != '' AND (headline_verified = 0 OR headline_verified IS NULL)", [cut]))
print("headline_verified values 3d:", [tuple(r) for r in q("SELECT typeof(headline_verified), headline_verified, COUNT(*) FROM articles WHERE scraped_at >= ? GROUP BY 1,2", [now - 3*86400])])
print("indexes:", [r[0] for r in q("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='articles'")])
c.close()
