"""PILOT, READ-ONLY: run the GS4 (Ethics) check (gs4.py) on recent notes and list what it would tag, for a human
to review before anything goes live. Writes nothing to any DB.

    python tools/gs4_pilot.py select --days 14 --limit 600 > ids.txt
    python tools/gs4_pilot.py run --ids 1,2,3 --shard 0/10 --out out/0.json
    python tools/gs4_pilot.py report out/*.json --md report.md
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Only to list possible misses in the report (stories with ethics words the check said no to); not used to decide.
HINT = re.compile(r"\b(corrupt\w*|brib\w*|conflicts? of interest|misconduct|whistle-?blow\w*|code of conduct|probity|"
                  r"lokpal|lokayukta|ethic\w*|integrity|neutrality|deceiv\w*|deception|consent)\b", re.I)


def select(a):
    from upsc_pipeline import UPSC_DB_TOKEN, UPSC_DB_URL, client
    upsc = client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        rows = upsc.execute("SELECT article_id, cluster_id FROM upsc_articles INDEXED BY idx_upsc_pub WHERE published_at >= ? "
                            "ORDER BY published_at DESC", [int(time.time()) - a.days * 86400]).rows
    finally:
        upsc.close()
    ids, seen = [], set()
    for aid, cl in rows:
        if cl and cl in seen:
            continue
        seen.add(cl)
        ids.append(int(aid))
        if len(ids) >= a.limit:
            break
    print(",".join(map(str, ids)))


def run(a):
    import gs4
    from analyzer import Analyzer, download_model
    from upsc_pipeline import MAIN_DB_TOKEN, MAIN_DB_URL, UPSC_DB_TOKEN, UPSC_DB_URL, client, fetch_articles
    k, n = map(int, a.shard.split("/"))
    ids = [int(x) for x in a.ids.split(",") if x.strip()][k::n]
    main_c, upsc = client(MAIN_DB_URL, MAIN_DB_TOKEN), client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        arts = {x["id"]: x for x in fetch_articles(main_c, ids)} if ids else {}
        ph = ",".join("?" * len(ids))
        notes = {int(r[0]): {"published_at": r[1], "gs_paper": r[2], "subject": r[3], "node": r[4],
                             "why_in_news": r[5] or "", "fact_box": r[6] or "", "mains_question": r[7] or ""}
                 for r in (upsc.execute(f"SELECT article_id, published_at, gs_paper, subject, syllabus_node, why_in_news, "
                                        f"fact_box, mains_question FROM upsc_articles WHERE article_id IN ({ph})", ids).rows
                           if ids else [])}
    finally:
        main_c.close()
        upsc.close()
    an = Analyzer(download_model(a.model_dir), n_threads=os.cpu_count())
    results = []
    for aid in ids:
        art, note = arts.get(aid), notes.get(aid)
        if not art or not note:
            continue
        t0 = time.time()
        r = gs4.check(an, art["title"], art["body"], note)
        r.update(id=aid, title=art["title"], seconds=round(time.time() - t0), **note,
                 hint=bool(HINT.search(f"{art['title']} {note['why_in_news']} {note['fact_box']}")))
        print(f"{aid} {r['seconds']}s tag={r['tag']} issue={r['issue']} ({r['why']})", flush=True)
        results.append(r)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"results": results}, open(a.out, "w"), ensure_ascii=False)


def report(a):
    res = sorted((r for f in a.files for r in json.load(open(f))["results"]), key=lambda r: -r["published_at"])
    tagged = [r for r in res if r["tag"]]
    stopped = [r for r in res if not r["tag"] and r["why"] != "model: no"]
    misses = [r for r in res if r["why"] == "model: no" and r["hint"]]
    day = lambda r: time.strftime("%d %b", time.gmtime(r["published_at"] + 19800))
    L = [f"## GS4 (Ethics) check — pilot on {len(res)} notes", "", "READ-ONLY. Nothing here is on the site.", "",
         "| | count |", "|---|---|",
         f"| notes checked | {len(res)} |",
         f"| would get the GS4 tag (all 4 checks passed) | {len(tagged)} |",
         f"| model said yes but a later check stopped it | {len(stopped)} |",
         f"| model said no although the note has ethics words (possible misses) | {len(misses)} |",
         f"| errors | {sum(1 for r in res if r['why'].startswith(('error', 'verify error')))} |",
         f"| avg seconds per note | {round(sum(r['seconds'] for r in res) / max(1, len(res)))} |", "",
         "**By issue:** " + ", ".join(f"{k} {v}" for k, v in Counter(r["issue"] for r in tagged).most_common()), "",
         "How to review: tick a note only if a GS4 answer would really use it. Any wrong tick = not ready.", "",
         "### Would be tagged GS4"]
    for r in tagged:
        L += [f"- [ ] **{r['id']}** · {day(r)} · {r['gs_paper']} {r['subject']} › {r['node']} · **{r['issue']}**",
              f"  **{r['title'][:130]}**",
              f"  > {r['quote']}",
              f"  - Angle: {r['angle']}",
              f"  - GS4 question: {r['question']}"]
    L += ["", "### Stopped by a check (model said yes)"]
    L += [f"- {r['id']} · {r['title'][:110]} — **{r['why']}** ({r['issue']}) — _{r['quote'][:160]}_" for r in stopped] or ["- none"]
    L += ["", "### Possible misses (ethics words, model said no)"]
    L += [f"- {r['id']} · {r['title'][:120]}" for r in misses] or ["- none"]
    md = "\n".join(L)
    print(md[:4000])
    open(a.md, "w").write(md + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(md + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--limit", type=int, default=600)
    r = sub.add_parser("run")
    r.add_argument("--ids", required=True)
    r.add_argument("--shard", default="0/1")
    r.add_argument("--out", required=True)
    r.add_argument("--model-dir", default=os.path.join(ROOT, "models"))
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+")
    p.add_argument("--md", required=True)
    a = ap.parse_args()
    {"select": select, "run": run, "report": report}[a.cmd](a)
