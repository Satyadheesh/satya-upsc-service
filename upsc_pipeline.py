"""Process one shard of article IDs: gate every article, write notes for the relevant ones.

Every article ends with a ledger row in upsc_processed (relevant / irrelevant / failed),
and its claim is released. Two passes (all gates, then all notes) so llama.cpp can
reuse the cached system-prompt prefix within each pass.
"""
import argparse
import json
import logging
import os
import time
import zlib

import libsql_client

from analyzer import MODEL_NAME, PROMPT_VERSION, Analyzer, InvalidOutput, download_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("upsc")

MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")
SCORE_MIN = int(os.environ.get("UPSC_SCORE_MIN") or 3)
DEADLINE = int(os.environ.get("SHARD_DEADLINE_SEC") or 4 * 3600)  # stop cleanly before job timeout
MODEL_DIR = os.environ.get("UPSC_MODEL_DIR") or os.path.join(os.getcwd(), "models")


def client(url, token):
    return libsql_client.create_client_sync(url=url.replace("libsql://", "https://"), auth_token=token)


def decode(blob):
    if blob is None:
        return ""
    if isinstance(blob, (bytes, bytearray, memoryview)):
        try:
            return zlib.decompress(bytes(blob)).decode("utf-8")
        except zlib.error:
            return bytes(blob).decode("utf-8", "ignore")
    return str(blob)


def json_list(s):
    try:
        v = json.loads(s) if s else []
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def record(upsc, aid, verdict, score=None, reason=None):
    now = int(time.time())
    upsc.batch([
        libsql_client.Statement(
            "INSERT INTO upsc_processed (article_id, verdict, upsc_score, reason, attempts, prompt_version, processed_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?) ON CONFLICT(article_id) DO UPDATE SET verdict=excluded.verdict, "
            "upsc_score=excluded.upsc_score, reason=excluded.reason, prompt_version=excluded.prompt_version, "
            "processed_at=excluded.processed_at, "
            "attempts=CASE WHEN excluded.verdict='failed' THEN upsc_processed.attempts + 1 ELSE upsc_processed.attempts END",
            [aid, verdict, score, reason, PROMPT_VERSION, now]),
        libsql_client.Statement("DELETE FROM upsc_claims WHERE article_id = ?", [aid]),
        *([libsql_client.Statement("DELETE FROM upsc_articles WHERE article_id = ?", [aid])]
          if verdict == "irrelevant" else []),
    ])


def save_notes(upsc, art, score, n):
    now = int(time.time())
    upsc.execute(
        """INSERT INTO upsc_articles (article_id, published_at, event_id, cluster_id, upsc_score, exam_type,
             gs_paper, subject, syllabus_node, secondary, why_in_news, fact_box, prelims_pointers,
             mains_question, mains_dimensions, keywords, states, model, prompt_version, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(article_id) DO UPDATE SET published_at=excluded.published_at, event_id=excluded.event_id,
             cluster_id=excluded.cluster_id, upsc_score=excluded.upsc_score, exam_type=excluded.exam_type,
             gs_paper=excluded.gs_paper, subject=excluded.subject, syllabus_node=excluded.syllabus_node,
             secondary=excluded.secondary, why_in_news=excluded.why_in_news, fact_box=excluded.fact_box,
             prelims_pointers=excluded.prelims_pointers, mains_question=excluded.mains_question,
             mains_dimensions=excluded.mains_dimensions, keywords=excluded.keywords, states=excluded.states,
             model=excluded.model, prompt_version=excluded.prompt_version, updated_at=excluded.updated_at""",
        [art["id"], art["published_at"], art["event_id"], art["cluster_id"], score, n["exam_type"],
         n["gs_paper"], n["subject"], n["syllabus_node"], json.dumps(n["secondary"]), n["why_in_news"],
         n["fact_box"], json.dumps(n["prelims_pointers"], ensure_ascii=False), n["mains_question"],
         json.dumps(n["mains_dimensions"], ensure_ascii=False), json.dumps(n["keywords"], ensure_ascii=False),
         json.dumps(art["states"], ensure_ascii=False), MODEL_NAME, PROMPT_VERSION, now, now],
    )
    # New or rewritten note: the Hindi service must (re)translate it. The column is added by the
    # Hindi service; before that exists this is a no-op.
    try:
        upsc.execute("UPDATE upsc_articles SET translated_hi = 0 WHERE article_id = ?", [art["id"]])
    except Exception:
        pass


def fetch_articles(main, ids):
    ph = ",".join("?" * len(ids))
    rows = main.execute(
        f"SELECT id, COALESCE(NULLIF(rephrased_title, ''), title), rephrased_article, content, category, "
        f"scraped_at, cluster_id, states_mentioned FROM articles WHERE id IN ({ph})", ids).rows
    events = {}
    try:
        for r in main.execute(
                f"SELECT article_id, MIN(event_id) FROM event_articles WHERE article_id IN ({ph}) GROUP BY article_id",
                ids).rows:
            events[int(r[0])] = int(r[1])
    except Exception as e:  # timeline tables optional
        log.warning(f"event lookup failed: {e}")
    arts = []
    for r in rows:
        body = decode(r[2])
        if len(body) < 400:  # thin rephrase -> fall back to original text
            body = (body + "\n" + decode(r[3])).strip()
        arts.append({"id": int(r[0]), "title": r[1] or "", "body": body, "category": r[4],
                     "published_at": int(r[5] or 0), "cluster_id": r[6], "states": json_list(r[7]),
                     "event_id": events.get(int(r[0]))})
    return arts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=str, default="")
    args = ap.parse_args()
    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    if not ids:
        log.info("Empty shard.")
        return
    if not MAIN_DB_URL or not UPSC_DB_URL:
        raise SystemExit("Missing DB credentials")

    started = time.time()
    main_c, upsc = client(MAIN_DB_URL, MAIN_DB_TOKEN), client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        arts = fetch_articles(main_c, ids)
        missing = set(ids) - {a["id"] for a in arts}
        for aid in missing:
            record(upsc, aid, "failed", reason="missing in main DB")
        log.info(f"{len(arts)} articles; loading {MODEL_NAME}")
        an = Analyzer(download_model(MODEL_DIR), n_threads=os.cpu_count())

        # pass 1: gate
        keep = []
        for a in arts:
            if time.time() - started > DEADLINE:
                log.warning("deadline hit; remaining claims will expire and be retried")
                return
            try:
                g = an.gate(a["title"], a["body"], a["category"])
            except Exception as e:
                log.error(f"[gate fail] {a['id']}: {e}")
                record(upsc, a["id"], "failed", reason=f"gate: {str(e)[:200]}")
                continue
            if g["score"] >= SCORE_MIN:
                keep.append((a, g))
                log.info(f"[gate {g['score']}] {a['id']} {a['title'][:70]}")
            else:
                record(upsc, a["id"], "irrelevant", g["score"], g["reason"])
                log.info(f"[skip {g['score']}] {a['id']} {a['title'][:70]} — {g['reason']}")

        # pass 2: notes
        for a, g in keep:
            if time.time() - started > DEADLINE:
                log.warning("deadline hit during notes")
                return
            try:
                n = an.notes(a["title"], a["body"], a["category"], a["published_at"])
                for d in n.get("dropped") or []:
                    log.info(f"[grounding] {a['id']} dropped {d[:160]}")
                save_notes(upsc, a, g["score"], n)
                record(upsc, a["id"], "relevant", g["score"], g["reason"])
                log.info(f"[saved] {a['id']} {n['gs_paper']} › {n['subject']} › {n['syllabus_node']}")
            except (InvalidOutput, Exception) as e:
                log.error(f"[notes fail] {a['id']}: {e}")
                record(upsc, a["id"], "failed", g["score"], f"notes: {str(e)[:200]}")
    finally:
        main_c.close()
        upsc.close()
    log.info(f"Shard done in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
