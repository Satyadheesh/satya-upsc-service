"""READ-ONLY: which UPSC report PDFs are stored (upsc_reports in the UPSC DB)."""
import os, time, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_UPSC_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_UPSC_DB_TOKEN"])
try:
    rows = c.execute("SELECT key, items, bytes, chunks, updated_at FROM upsc_reports ORDER BY updated_at DESC").rows
except Exception as e:
    print("no table:", e); rows = []
print(len(rows), "PDFs stored")
for r in rows:
    print(f"{r[0]:32} {r[1]:4} notes {r[2] // 1024:6} KB {r[3]} chunks  {round((time.time() - r[4]) / 60)} min ago")
c.close()
