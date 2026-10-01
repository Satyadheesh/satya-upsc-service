"""READ-ONLY: full schema (tables + indexes) of the main DB, plus row counts of each table."""
import os, libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"), auth_token=os.environ["SATYA_DB_TOKEN"])
rows = c.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, tbl_name, name").rows
print("```sql")
for r in rows:
    print(r[3].strip() + ";")
print("```")
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").rows:
    try:
        n = c.execute(f'SELECT COUNT(*) FROM "{r[0]}"').rows[0][0]
    except Exception as e:
        n = f"err {e}"
    print(f"-- rows {r[0]}: {n}")
c.close()
