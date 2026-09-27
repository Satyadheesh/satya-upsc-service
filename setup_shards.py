import os
import json
import libsql_client
import math

MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")

BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 50))
MAX_SHARDS = 10

def main():
    if not MAIN_DB_URL or not UPSC_DB_URL:
        print("Missing DB credentials")
        return

    main_client = libsql_client.create_client_sync(url=MAIN_DB_URL.replace('libsql://', 'https://'), auth_token=MAIN_DB_TOKEN)
    upsc_client = libsql_client.create_client_sync(url=UPSC_DB_URL.replace('libsql://', 'https://'), auth_token=UPSC_DB_TOKEN)

    res = upsc_client.execute("SELECT last_article_id FROM upsc_checkpoint WHERE id = 1")
    last_id = res.rows[0][0] if res.rows else 0

    res = main_client.execute(
        "SELECT id FROM articles WHERE id > ? AND status IN ('classified', 'entity_processed', 'processed') ORDER BY id ASC LIMIT ?",
        [last_id, BATCH_SIZE]
    )
    article_ids = [int(row[0]) for row in res.rows]

    shards = []
    if article_ids:
        highest_id = max(article_ids)
        upsc_client.execute("UPDATE upsc_checkpoint SET last_article_id = ? WHERE id = 1", [highest_id])
        
        chunk_size = math.ceil(len(article_ids) / MAX_SHARDS)
        for i in range(0, len(article_ids), chunk_size):
            chunk = article_ids[i:i + chunk_size]
            shards.append(",".join(map(str, chunk)))
    
    if not shards:
        shards = [""] # Empty shard so the matrix doesn't fail completely, though it will do nothing

    # Write to GITHUB_OUTPUT
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"shards={json.dumps(shards)}\n")
    else:
        print(f"shards={json.dumps(shards)}")

if __name__ == "__main__":
    main()
