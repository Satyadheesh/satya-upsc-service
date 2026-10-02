"""READ-ONLY: which UPSC report PDFs are stored (upsc_reports in the UPSC DB), summarised by edition."""
import collections, os, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_UPSC_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_UPSC_DB_TOKEN"])
try:
    rows = c.execute("SELECT key, items, bytes, chunks, updated_at FROM upsc_reports ORDER BY key").rows
except Exception as e:
    print("no table:", e); rows = []
print(len(rows), "PDFs stored,", sum(r[2] for r in rows) // (1024 * 1024), "MB")
summary = collections.defaultdict(lambda: {"n": 0, "periods": set()})
for key, *_ in rows:
    parts = key.split(":")
    kind, period, lang = parts[0], parts[1], parts[2]
    edition = parts[3] if len(parts) > 3 else "old (single PDF)"
    s = summary[(edition, kind, lang)]
    s["n"] += 1
    s["periods"].add(period)
print("\nedition            kind     lang  count  range")
for (ed, kind, lang), s in sorted(summary.items()):
    ps = sorted(s["periods"])
    print(f"{ed:18} {kind:8} {lang:4} {s['n']:5}  {ps[0]} .. {ps[-1]}")
print("\nnewest 15:")
for r in sorted(rows, key=lambda r: -r[4])[:15]:
    print(f"{r[0]:36} {r[1]:4} notes {r[2] // 1024:6} KB  {round((time.time() - r[4]) / 60)} min ago")
c.close()
