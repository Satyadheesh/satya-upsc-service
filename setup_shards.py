"""Pick the next batch of articles and split it into shards for the matrix job.

Selection is ledger-based (upsc_processed) plus a backfill watermark in upsc_meta.
Nothing is marked done here: articles are only *claimed*; the pipeline writes the
verdict after processing, so a crashed shard's articles are retried later.
"""
import json
import os
import time

import libsql_client

from analyzer import MODEL_NAME, NODE_CHECK, NODE_OWNER, PROMPT_VERSION, checked_node
from syllabus import paper_of
from selection import MAX_ATTEMPTS, is_done, make_shards, prefilter

MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")

BATCH_SIZE = int(os.environ.get("BATCH_SIZE") or 180)
MAX_SHARDS = int(os.environ.get("MAX_SHARDS") or 18)
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS") or 365)
MAX_SCAN = int(os.environ.get("MAX_SCAN") or 5000)        # rows scanned per run, upper bound
CLAIM_TTL = int(os.environ.get("CLAIM_TTL") or 6 * 3600)  # > job timeout
RESCAN_DAYS = int(os.environ.get("RESCAN_DAYS") or 3)    # recent articles re-checked every run
REDO_DAYS = int(os.environ.get("REDO_DAYS") or 30)       # notes this recent are rewritten with a new prompt version
REDO_PER_RUN = int(os.environ.get("REDO_PER_RUN") or 60)
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


def retag_once(upsc_c, now, marker="retag_nodes_v1"):
    """One-time: notes of the last REDO_DAYS days filed under an over-used node (analyzer.NODE_CHECK) that say
    nothing about it move to their secondary node / Infrastructure, as new notes do. Few rows, cheap."""
    if get_meta(upsc_c, marker):
        return
    ph = ",".join("?" * len(NODE_CHECK))
    rows = upsc_c.execute(f"SELECT article_id, syllabus_node, secondary, why_in_news, fact_box, keywords FROM upsc_articles "
                          f"WHERE published_at >= ? AND syllabus_node IN ({ph})",
                          [now - REDO_DAYS * 86400, *NODE_CHECK]).rows
    moved = 0
    for aid, node, sec, why, fact, kws in rows:
        try:
            secondary = [x for x in json.loads(sec or "[]") if isinstance(x, dict) and x.get("node") in NODE_OWNER]
            words = " ".join(k for k in json.loads(kws or "[]") if isinstance(k, str))
        except ValueError:
            secondary, words = [], ""
        new, rest = checked_node(node, secondary, f"{why} {fact} {words}")
        if new != node:
            subj = NODE_OWNER[new]
            rest = [x for x in rest if NODE_OWNER.get(x.get("node")) != subj]
            upsc_c.execute("UPDATE upsc_articles SET syllabus_node = ?, subject = ?, gs_paper = ?, secondary = ?, updated_at = ? "
                           "WHERE article_id = ?", [new, subj, paper_of(subj), json.dumps(rest), now, int(aid)])
            moved += 1
            print(f"retag {aid}: {node} -> {new}")
    upsc_c.execute("INSERT OR REPLACE INTO upsc_meta (key, value) VALUES (?, ?)", [marker, str(now)])
    print(f"retag: {moved} of {len(rows)} notes moved")


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
    if approved != f"{PROMPT_VERSION}|{MODEL_NAME}" and not FORCE:
        print(f"{PROMPT_VERSION}|{MODEL_NAME} not approved (approved={approved}); run the UPSC Eval workflow. Skipping.")
        main_c.close()
        upsc_c.close()
        emit([""], more=False)
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

    try:
        retag_once(upsc_c, now)
    except Exception as e:  # never block selection on this
        print(f"retag skipped: {e}")

    # (1b) rewrite recent notes written by an older prompt (gate skipped: the stored score is kept).
    # Stops reading once every note of the window is on the current version (upsc_meta 'redo_done').
    redo = 0
    if get_meta(upsc_c, "redo_done") != PROMPT_VERSION:
        rows = upsc_c.execute(
            "SELECT article_id FROM upsc_articles INDEXED BY idx_upsc_pub WHERE published_at >= ? "
            "AND COALESCE(prompt_version, '') != ? ORDER BY published_at DESC LIMIT ?",
            [now - REDO_DAYS * 86400, PROMPT_VERSION, REDO_PER_RUN * 3]).rows
        claimed_now = {int(r[0]) for r in in_query(
            upsc_c, "SELECT article_id FROM upsc_claims WHERE article_id IN ({ph})", [int(r[0]) for r in rows])} if rows else set()
        for r in rows:
            aid = int(r[0])
            if redo >= REDO_PER_RUN or len(batch) >= BATCH_SIZE:
                break
            if aid not in taken and aid not in claimed_now:
                batch.append(aid); taken.add(aid); redo += 1
        if not rows:
            upsc_c.execute("INSERT OR REPLACE INTO upsc_meta (key, value) VALUES ('redo_done', ?)", [PROMPT_VERSION])
            print(f"redo: every note of the last {REDO_DAYS} days is on {PROMPT_VERSION}")

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
    # Lower id bound = first article inside the lookback window (1 row via the scraped_at index).
    # Without it, once the watermark passed the window, 'id < ? AND scraped_at >= ?' matched nothing
    # and walked the id index down to 1 on every run (~190k rows read per query).
    first = main_c.execute("SELECT id FROM articles WHERE scraped_at >= ? ORDER BY scraped_at LIMIT 1", [cutoff]).rows
    floor_id = int(first[0][0]) if first else below
    while len(batch) < BATCH_SIZE and scanned < MAX_SCAN and below > floor_id:
        # '+status' / '+scraped_at' keep SQLite on the primary-key range (walks ids down from
        # the watermark, stops after PAGE rows). Otherwise it picked the (status, scraped_at)
        # index, read every eligible article of the last year and sorted them for one page.
        page = main_c.execute(
            f"SELECT id, COALESCE(NULLIF(rephrased_title, ''), title), category FROM articles "
            f"WHERE +status IN ({st_ph}) AND rephrased_article IS NOT NULL "
            f"AND id < ? AND id >= ? AND +scraped_at >= ? ORDER BY id DESC LIMIT {PAGE}",
            [*ELIGIBLE, below, floor_id, cutoff]).rows
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
    print(f"scanned={scanned} prefiltered={len(prefiltered)} batch={len(batch)} redo={redo} "
          f"backfill_below={below} shards={len(shards)}")
    # a full batch means there is backlog left -> the workflow chains another run
    emit(shards, more=len(batch) >= BATCH_SIZE)


def emit(shards, more=False):
    out = os.environ.get("GITHUB_OUTPUT")
    lines = f"shards={json.dumps(shards)}\nmore={'true' if more else 'false'}\n"
    if out:
        with open(out, "a") as f:
            f.write(lines)
    else:
        print(lines, end="")


if __name__ == "__main__":
    main()
