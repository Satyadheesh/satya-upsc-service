"""READ-ONLY: timeline service backlog - checkpoint, lag, eligible articles still to file."""
import os, time, datetime as dt, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
q = lambda s, a=(): c.execute(s, list(a)).rows
ELIG = """a.status IN ('classified','entity_processed','processed')
  AND (a.category != 'international' OR a.party_mentioned NOT IN ('[]','') OR a.ministers_mentioned NOT IN ('[]','')
       OR a.states_mentioned NOT IN ('[]','') OR a.cities_mentioned NOT IN ('[]',''))
  AND (a.ministers_mentioned != '[]' OR a.party_mentioned != '[]' OR a.civic_flag = 1)"""
cp = q("SELECT last_article_id FROM timeline_checkpoint WHERE id = 1")[0][0]
sa = q("SELECT scraped_at FROM articles WHERE id = ?", [cp])
now = int(time.time())
print("checkpoint article id:", cp, "| scraped", dt.datetime.utcfromtimestamp(sa[0][0]).isoformat() if sa else "?", f"| lag {round((now - sa[0][0]) / 3600, 1)} h" if sa else "")
print("newest article id:", q("SELECT MAX(id) FROM articles")[0][0])
rows = q(f"SELECT date(a.scraped_at,'unixepoch') d, COUNT(*) FROM articles a WHERE a.id > ? AND {ELIG} AND a.id NOT IN (SELECT article_id FROM event_articles) GROUP BY d ORDER BY d", [cp])
print("eligible still to file (by scrape day):", [tuple(r) for r in rows], "total", sum(r[1] for r in rows))
fl = q("SELECT id FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [now - 7 * 86400])[0][0]
per = q(f"SELECT date(a.scraped_at,'unixepoch') d, COUNT(*) FROM articles a WHERE a.id >= ? AND {ELIG} GROUP BY d ORDER BY d", [fl])
print("eligible arriving per day (last 7d):", [tuple(r) for r in per])
filed = q("SELECT date(a.scraped_at,'unixepoch') d, COUNT(*) FROM event_articles ea JOIN articles a ON a.id = ea.article_id WHERE ea.article_id >= ? GROUP BY d ORDER BY d", [fl])
print("filed into timelines (by article day, last 7d):", [tuple(r) for r in filed])
print("events open/closed:", [tuple(r) for r in q("SELECT state, COUNT(*) FROM events GROUP BY state")])
print("open events past 21d (closure queue):", q("SELECT COUNT(*) FROM events WHERE state = 'open' AND last_seen < ?", [(sa[0][0] if sa else now) - 21 * 86400])[0][0])
c.close()
