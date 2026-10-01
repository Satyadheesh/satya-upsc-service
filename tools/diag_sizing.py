"""READ-ONLY: sizes the 30-day window and checks assumptions for precomputed site stats."""
import os, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
q = lambda s, a=(): c.execute(s, list(a)).rows
now = int(time.time())
print("stat tables:", q("SELECT name FROM sqlite_master WHERE name LIKE 'sqlite_stat%'"))
print("max id:", q("SELECT MAX(id) FROM articles"))
for d in (1, 3, 7, 30):
    cut = now - d * 86400
    f = q("SELECT id, scraped_at FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [cut])
    fid = f[0][0] if f else None
    n = q("SELECT COUNT(*), SUM(scraped_at < ?), MIN(scraped_at) FROM articles WHERE id >= ?", [cut, fid])[0] if fid else None
    ae = q("SELECT COUNT(*) FROM article_entities WHERE article_id >= ?", [fid])[0][0] if fid else None
    print(f"{d}d: floor_id={fid} rows_by_id={n[0] if n else None} older_than_cut_in_range={n[1] if n else None} ae_rows={ae}")
cut30 = now - 30 * 86400
fid30 = q("SELECT id FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [cut30])[0][0]
print("ids >= floor30 but scraped_at older than 31d:", q("SELECT COUNT(*) FROM articles WHERE id >= ? AND scraped_at < ?", [fid30, cut30 - 86400]))
print("ids < floor30 but scraped_at within 30d:", q("SELECT COUNT(*) FROM articles WHERE id < ? AND id >= ? - 20000 AND scraped_at >= ?", [fid30, fid30, cut30]))
print("status 30d:", q("SELECT status, COUNT(*) FROM articles WHERE id >= ? GROUP BY status", [fid30]))
print("civic_flag values 30d:", q("SELECT typeof(civic_flag), civic_flag, COUNT(*) FROM articles WHERE id >= ? GROUP BY 1, 2", [fid30]))
print("ae kinds 30d:", q("SELECT kind, COUNT(DISTINCT slug), COUNT(*) FROM article_entities WHERE article_id >= ? GROUP BY kind", [fid30]))
print("ae on non-classified 30d:", q("SELECT a.status, COUNT(*) FROM article_entities ae JOIN articles a ON a.id = ae.article_id WHERE ae.article_id >= ? GROUP BY a.status", [fid30]))
print("ae distinct slugs all-time by kind:", q("SELECT kind, COUNT(*) FROM (SELECT DISTINCT kind, slug FROM article_entities) GROUP BY kind"))
ev = q("SELECT e.id, e.article_count, (SELECT COUNT(*) FROM event_articles ea WHERE ea.event_id = e.id) FROM events e ORDER BY e.last_seen DESC LIMIT 400")
print("events article_count mismatches (of 400 recent):", sum(1 for r in ev if r[1] != r[2]), [tuple(r) for r in ev if r[1] != r[2]][:10])
print("titled events:", q("SELECT COUNT(*) FROM events WHERE title IS NOT NULL AND slug IS NOT NULL AND slug != ''"))
c.close()
