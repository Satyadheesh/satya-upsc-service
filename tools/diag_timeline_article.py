"""READ-ONLY: inspect the next eligible articles after the timeline checkpoint."""
import os, zlib
import libsql_client
c = libsql_client.create_client_sync(url=os.environ["SATYA_DB_URL"].replace("libsql://", "https://"),
                                     auth_token=os.environ["SATYA_DB_TOKEN"])
ELIG = """a.status IN ('classified','entity_processed','processed')
  AND (a.category != 'international' OR a.party_mentioned NOT IN ('[]','') OR a.ministers_mentioned NOT IN ('[]','')
       OR a.states_mentioned NOT IN ('[]','') OR a.cities_mentioned NOT IN ('[]',''))
  AND (a.ministers_mentioned != '[]' OR a.party_mentioned != '[]' OR a.civic_flag = 1)"""
def dec(b):
    if b is None: return ""
    if isinstance(b, (bytes, bytearray, memoryview)):
        try: return zlib.decompress(bytes(b)).decode("utf-8", "ignore")
        except Exception: return bytes(b).decode("utf-8", "ignore")
    return str(b)
rows = c.execute(f"""SELECT a.id, a.title, a.rephrased_title, a.rephrased_article, a.scraped_at, a.party_mentioned,
   a.ministers_mentioned, a.states_mentioned, a.cities_mentioned, a.civic_flag, a.category, length(a.rephrased_article), length(a.content)
   FROM articles a WHERE a.id > (SELECT last_article_id FROM timeline_checkpoint WHERE id=1) AND {ELIG}
   AND a.id NOT IN (SELECT article_id FROM event_articles) ORDER BY a.id LIMIT 8""").rows
print("### Next eligible articles after checkpoint\n")
print("| id | title | rephrased chars (decoded) | blob len | party | ministers | states | cities | civic | cat |\n|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    body = dec(r[3])
    print(f"| {r[0]} | {(r[2] or r[1] or '')[:70]} | {len(body)} | {r[11]} | {str(r[5])[:40]} | {str(r[6])[:60]} | {str(r[7])[:40]} | {str(r[8])[:40]} | {r[9]} | {r[10]} |")
first = rows[0]
print(f"\n### Article {first[0]} detail\n")
print("title:", repr(first[1]))
print("\nrephrased_title:", repr(first[2]))
body = dec(first[3])
print(f"\nrephrased_article ({len(body)} chars), first 1500:\n\n```\n{body[:1500]}\n```")
print("\nministers_mentioned raw:", repr(first[6])[:2000])
print("\nparty raw:", repr(first[5])[:500], "\nstates raw:", repr(first[7])[:500], "\ncities raw:", repr(first[8])[:500])
nonascii = sum(1 for ch in body if ord(ch) > 0xFFFF)
print("\nchars outside BMP:", nonascii, "| NUL bytes:", body.count("\x00"))
# is 119618 itself malformed JSON in entity fields?
import json
for name, v in (("party", first[5]), ("ministers", first[6]), ("states", first[7]), ("cities", first[8])):
    try: json.loads(v) if v else None; ok = "ok"
    except Exception as e: ok = f"BAD JSON: {e}"
    print(f"{name}: {ok}")
c.close()
