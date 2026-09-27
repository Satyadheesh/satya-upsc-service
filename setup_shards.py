"""Pick the next batch of articles and split it into shards for the matrix job.

Selection is ledger-based (upsc_processed) plus a backfill watermark in upsc_meta.
Nothing is marked done here: articles are only *claimed*; the pipeline writes the
verdict after processing, so a crashed shard's articles are retried later.
"""
import json
import os
import time

import libsql_client

from analyzer import PROMPT_VERSION
from selection import MAX_ATTEMPTS, is_done, make_shards, prefilter

MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")

BATCH_SIZE = int(os.environ.get("BATCH_SIZE") or 50)
MAX_SHARDS = int(os.environ.get("MAX_SHARDS") or 10)
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS") or 365)
MAX_SCAN = int(os.environ.get("MAX_SCAN") or 5000)        # rows scanned per run, upper bound
CLAIM_TTL = int(os.environ.get("CLAIM_TTL") or 6 * 3600)  # > job timeout
RESCAN_DAYS = int(os.environ.get("RESCAN_DAYS") or 3)    # recent articles re-checked every run
PAGE = 1000
FORCE = os.environ.get("FORCE_UNAPPROVED", "").lower() in ("1", "true", "yes")
ELIGIBLE = [s.strip() for s in (os.environ.get("ELIGIBLE_STATUSES")
            or "classified,entity_processed,processed").split(",") if s.strip()]


def client(url, token):
    return libsql_client.create_client_sync(url=url.replace("libsql://", "https://"), auth_token=token)


def in_query(c, sql_prefix, ids, extra_args=()):
    out = []
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        ph = ",".join("?" * len(chunk))
        out.extend(c.execute(sql_prefix.format(ph=ph), [*extra_args, *chunk]).rows)
    return out


def get_meta(c, key, default=None):
    r = c.execute("SELECT value FROM upsc_meta WHERE key = ?", [key]).rows
    return r[0][0] if r else default


def main():
    """Batch = (1) retries of failed rows, (2) anything recent (last RESCAN_DAYS, catches
    articles classified late), (3) backfill walking down from the `backfill_below` watermark.
    Reads stay bounded: recent window + however far the backfill needs to go this run."""
    if not MAIN_DB_URL or not UPSC_DB_URL:
        raise SystemExit("Missing DB credentials")
    main_c = client(MAIN_DB_URL, MAIN_DB_TOKEN)
    upsc_c = client(UPSC_DB_URL, UPSC_DB_TOKEN)
    now = int(time.time())
    cutoff = now - LOOKBACK_DAYS * 86400

    approved = get_meta(upsc_c, "approved_prompt")
    if approved != PROMPT_VERSION and not FORCE:
        print(f"Prompt {PROMPT_VERSION} not approved (approved={approved}); run the UPSC Eval workflow. Skipping.")
        main_c.close()
        upsc_c.close()
        emit([""])
        return
    st_ph = ",".join("?" * len(ELIGIBLE))

    # expired claims = a shard died mid-way; count it as a failed attempt so it is retried (max 3)
    upsc_c.batch([
        libsql_client.Statement(
            "INSERT INTO upsc_processed (article_id, verdict, reason, attempts, processed_at) "
            "SELECT article_id, 'failed', 'claim expired', 1, ? FROM upsc_claims WHERE claimed_at < ? "
            "ON CONFLICT(article_id) DO UPDATE SET verdict='failed', reason='claim expired', "
            "attempts=upsc_processed.attempts + 1, processed_at=excluded.processed_at",
            [now, now - CLAIM_TTL]),
        libsql_client.Statement("DELETE FROM upsc_claims WHERE claimed_at < ?", [now - CLAIM_TTL]),
    ])

    batch, prefiltered, taken = [], [], set()

    # (1) retries
    for r in upsc_c.execute(
            "SELECT article_id FROM upsc_processed WHERE verdict = 'failed' AND attempts < ? "
            "AND article_id NOT IN (SELECT article_id FROM upsc_claims) ORDER BY article_id DESC LIMIT ?",
            [MAX_ATTEMPTS, max(1, BATCH_SIZE // 4)]).rows:
        batch.append(int(r[0])); taken.add(int(r[0]))

    def consider(page):
        """Filter a page of (id, title, category) rows; returns id of the last row examined."""
        ids = [int(r[0]) for r in page]
        ledger = {int(r[0]): (r[1], r[2]) for r in in_query(
            upsc_c, "SELECT article_id, verdict, attempts FROM upsc_processed WHERE article_id IN ({ph})", ids)}
        claimed = {int(r[0]) for r in in_query(
            upsc_c, "SELECT article_id FROM upsc_claims WHERE article_id IN ({ph})", ids)}
        last = None
        for r in page:
            aid = int(r[0])
            if len(batch) >= BATCH_SIZE:
                break
            last = aid
            if aid in taken or aid in claimed or is_done(ledger.get(aid)):
                continue
            reason = prefilter(r[1], r[2])
            if reason:
                prefiltered.append((aid, reason))
            else:
                batch.append(aid)
            taken.add(aid)
        return last

    base = (f"SELECT id, COALESCE(NULLIF(rephrased_title, ''), title), category FROM articles "
            f"WHERE status IN ({st_ph}) AND rephrased_article IS NOT NULL ")

    # (2) recent window, newest first
    recent = main_c.execute(base + "AND scraped_at >= ? ORDER BY id DESC LIMIT ?",
                            [*ELIGIBLE, max(cutoff, now - RESCAN_DAYS * 86400), MAX_SCAN]).rows
    scanned = len(recent)
    for i in range(0, len(recent), PAGE):
        if len(batch) >= BATCH_SIZE:
            break
        consider(recent[i:i + PAGE])

    # (3) backfill below the watermark (starts just under the recent window)
    below = get_meta(upsc_c, "backfill_below")
    below = int(below) if below else (int(recent[-1][0]) if recent else 2**62)
    while len(batch) < BATCH_SIZE and scanned < MAX_SCAN:
        page = main_c.execute(base + f"AND id < ? AND scraped_at >= ? ORDER BY id DESC LIMIT {PAGE}",
                              [*ELIGIBLE, below, cutoff]).rows
        if not page:
            break
        scanned += len(page)
        last = consider(page)
        if last is None:
            break
        below = last
    upsc_c.execute("INSERT OR REPLACE INTO upsc_meta (key, value) VALUES ('backfill_below', ?)", [str(below)])

    stmts = [libsql_client.Statement(
        "INSERT INTO upsc_processed (article_id, verdict, reason, attempts, processed_at) "
        "VALUES (?, 'prefiltered', ?, 1, ?) ON CONFLICT(article_id) DO UPDATE SET "
        "verdict='prefiltered', reason=excluded.reason, processed_at=excluded.processed_at",
        [aid, reason, now]) for aid, reason in prefiltered]
    stmts += [libsql_client.Statement(
        "INSERT OR REPLACE INTO upsc_claims (article_id, claimed_at) VALUES (?, ?)", [aid, now]) for aid in batch]
    for i in range(0, len(stmts), 200):
        upsc_c.batch(stmts[i:i + 200])

    main_c.close()
    upsc_c.close()

    shards = make_shards(batch, MAX_SHARDS) or [""]
    print(f"scanned={scanned} prefiltered={len(prefiltered)} batch={len(batch)} "
          f"backfill_below={below} shards={len(shards)}")
    emit(shards)


def emit(shards):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"shards={json.dumps(shards)}\n")
    else:
        print(f"shards={json.dumps(shards)}")


if __name__ == "__main__":
    main()
