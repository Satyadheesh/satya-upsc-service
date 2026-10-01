"""READ-ONLY: what the frontend's daily site_stats row and persistent data cache contain."""
import os, json, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
q = lambda s, a=(): c.execute(s, list(a)).rows
for t in ("site_stats", "next_data_cache", "next_data_cache_tags"):
    print(t, "exists:", bool(q("SELECT 1 FROM sqlite_master WHERE name = ?", [t])))
for r in q("SELECT key, updated_at, length(value) FROM site_stats"):
    print("row", r[0], "age_min", round((time.time() - r[1]) / 60, 1), "bytes", r[2])
s = q("SELECT value FROM site_stats WHERE key = 'stats'")
if s:
    s = json.loads(s[0][0])
    print("overview:", {k: v for k, v in s["overview"].items() if not isinstance(v, dict)})
    print("categories:", s["overview"]["category_breakdown_30d"])
    print("top parties:", list(s["overview"]["top_parties_30d"].items())[:5])
    print("ledger:", s["ledger"])
    print("sources:", len(s["sources"]), s["sources"][:3])
    ents = s["entities"]
    print("entities:", len(ents))
    for k in ("party:bjp", "party:inc", "state:uttar-pradesh", "state:delhi", "topic:corruption_scam", "minister:narendra-modi"):
        e = ents.get(k)
        print(" ", k, e and {x: (y if not isinstance(y, dict) else list(y.items())[:3]) for x, y in e.items()})
    print("party keys:", sorted(k for k in ents if k.startswith("party:"))[:15])
t = q("SELECT value FROM site_stats WHERE key = 'totals'")
if t:
    t = json.loads(t[0][0]); print("totals hwm", t["hwm"], "articles", t["articles"])
if q("SELECT 1 FROM sqlite_master WHERE name = 'next_data_cache'"):
    print("cache entries by ver:", q("SELECT ver, COUNT(*), SUM(length(value)) FROM next_data_cache GROUP BY ver"))
    print("tags:", q("SELECT tag, revalidated_at FROM next_data_cache_tags"))
# live check of the numbers the stats replace
cut = int(time.time()) - 30 * 86400
fid = q("SELECT id FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [cut])[0][0]
print("live check bjp n30:", q("SELECT COUNT(*) FROM article_entities ae JOIN articles a ON a.id = ae.article_id WHERE ae.kind='party' AND ae.slug='bjp' AND ae.article_id >= ? AND a.status IN ('classified','entity_processed','processed')", [fid]))
c.close()
