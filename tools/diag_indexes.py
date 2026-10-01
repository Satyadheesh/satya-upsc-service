"""READ-ONLY: indexes on the main DB's hot tables, plus row counts."""
import os, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
for t in ("articles", "events", "event_articles", "article_entities"):
    print(f"\n### {t}")
    for r in c.execute(f"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='{t}'").rows:
        print("-", r[0], ":", r[1])
for s in ("SELECT COUNT(*) FROM articles", "SELECT translated_hi, COUNT(*) FROM articles GROUP BY translated_hi",
          "SELECT COUNT(*) FROM articles WHERE scraped_at >= strftime('%s','now','-2 days')"):
    print("\n", s, "->", [tuple(r) for r in c.execute(s).rows])
c.close()
