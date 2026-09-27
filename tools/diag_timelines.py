"""READ-ONLY diagnostics for the timeline service against the main DB. Prints markdown."""
import os, time, json
import libsql_client

c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"),
                                     auth_token=os.environ["SATYA_DB_TOKEN"])
ELIG = """a.status IN ('classified','entity_processed','processed')
  AND (a.category != 'international' OR a.party_mentioned NOT IN ('[]','') OR a.ministers_mentioned NOT IN ('[]','')
       OR a.states_mentioned NOT IN ('[]','') OR a.cities_mentioned NOT IN ('[]',''))
  AND (a.ministers_mentioned != '[]' OR a.party_mentioned != '[]' OR a.civic_flag = 1)"""

def q(title, sql, args=()):
    t = time.time()
    try:
        rs = c.execute(sql, list(args))
        print(f"\n### {title}  ({time.time()-t:.1f}s)\n")
        cols = rs.columns
        print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        for r in rs.rows[:60]:
            print("| " + " | ".join(str(v)[:80] for v in r) + " |")
    except Exception as e:
        print(f"\n### {title}\n\nERROR: {e}")

q("checkpoint", "SELECT * FROM timeline_checkpoint")
q("checkpoint article", "SELECT id, datetime(scraped_at,'unixepoch') AS scraped, status FROM articles WHERE id = (SELECT last_article_id FROM timeline_checkpoint WHERE id=1)")
q("articles overall", "SELECT COUNT(*) n, MAX(id) max_id, datetime(MAX(scraped_at),'unixepoch') latest FROM articles")
q("latest event_articles", "SELECT MAX(article_id) max_article, datetime(MAX(event_date),'unixepoch') latest_event_date, COUNT(*) n FROM event_articles")
q("event_articles per day since Aug 25", "SELECT date(event_date,'unixepoch') d, COUNT(*) n FROM event_articles WHERE event_date >= strftime('%s','2026-08-25') GROUP BY d ORDER BY d")
q("events by state", "SELECT state, COUNT(*) n, datetime(MAX(last_seen),'unixepoch') max_last_seen FROM events GROUP BY state")
q("events created per day since Aug 25", "SELECT date(first_seen,'unixepoch') d, COUNT(*) n, SUM(title IS NULL) untitled FROM events WHERE first_seen >= strftime('%s','2026-08-25') GROUP BY d ORDER BY d")
q("articles per day by status since Aug 25", """SELECT date(scraped_at,'unixepoch') d, COUNT(*) total,
   SUM(status='scraped') scraped, SUM(status='rephrased') rephrased, SUM(status='classified') classified,
   SUM(status='entity_processed') entity_processed, SUM(status='processed') processed,
   SUM(status NOT IN ('scraped','rephrased','classified','entity_processed','processed')) other
   FROM articles WHERE scraped_at >= strftime('%s','2026-08-25') GROUP BY d ORDER BY d""")
q("distinct statuses (last 30d)", "SELECT status, COUNT(*) FROM articles WHERE scraped_at >= strftime('%s','now','-30 days') GROUP BY status")
q("eligible per day since Aug 25 (timeline ELIGIBILITY_SQL)", f"SELECT date(a.scraped_at,'unixepoch') d, COUNT(*) n FROM articles a WHERE a.scraped_at >= strftime('%s','2026-08-25') AND {ELIG} GROUP BY d ORDER BY d")
q("eligible after checkpoint, not yet filed", f"""SELECT COUNT(*) n, MIN(a.id) min_id, MAX(a.id) max_id,
   datetime(MIN(a.scraped_at),'unixepoch') oldest, datetime(MAX(a.scraped_at),'unixepoch') newest
   FROM articles a WHERE a.id > (SELECT last_article_id FROM timeline_checkpoint WHERE id=1)
   AND {ELIG} AND a.id NOT IN (SELECT article_id FROM event_articles)""")
q("entity fields on recent articles (last 3 days sample)", """SELECT id, status, category, party_mentioned, ministers_mentioned, states_mentioned, civic_flag
   FROM articles WHERE scraped_at >= strftime('%s','now','-3 days') ORDER BY id DESC LIMIT 15""")
q("NULL milestones", "SELECT COUNT(*) n, MIN(article_id), MAX(article_id) FROM event_articles WHERE milestone IS NULL")
q("id vs scraped_at order check (ids around checkpoint)", """SELECT id, datetime(scraped_at,'unixepoch') s, status FROM articles
   WHERE id > (SELECT last_article_id FROM timeline_checkpoint WHERE id=1) ORDER BY id LIMIT 10""")
c.close()
