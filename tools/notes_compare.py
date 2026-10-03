"""READ-ONLY side-by-side of stored notes vs the notes the current analyzer.py writes for the same articles.

    python tools/notes_compare.py run --ids 129424,123894 --shard 0/5 --out out/0.json
    python tools/notes_compare.py report out/*.json --md notes_compare.md

For each article: the stored note (older prompt), the new note, what the new grounding check dropped, and the
facts in the stored note the article doesn't support (numbers, years, states). Nothing is written to any DB.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def stored_notes(upsc, ids):
    ph = ",".join("?" * len(ids))
    rows = upsc.execute(f"SELECT article_id, prompt_version, why_in_news, fact_box, prelims_pointers, gs_paper, subject, "
                        f"syllabus_node FROM upsc_articles WHERE article_id IN ({ph})", ids).rows
    return {int(r[0]): {"prompt_version": r[1], "why_in_news": r[2] or "", "fact_box": r[3] or "",
                        "prelims_pointers": json.loads(r[4] or "[]"), "gs_paper": r[5], "subject": r[6],
                        "syllabus_node": r[7]} for r in rows}


def problems(src, note):
    out = []
    for field in ("why_in_news", "fact_box"):
        bad = src.problems(note.get(field))
        if bad:
            out.append(f"{field}: {', '.join(bad[:4])}")
    for p in note.get("prelims_pointers") or []:
        t = p.get("text") if isinstance(p, dict) else str(p)
        bad = src.problems(t)
        if bad:
            out.append(f"pointer '{t[:80]}': {', '.join(bad[:4])}")
    return out


def run(a):
    from analyzer import MODEL_NAME, PROMPT_VERSION, Analyzer, Source, download_model
    from upsc_pipeline import MAIN_DB_TOKEN, MAIN_DB_URL, UPSC_DB_TOKEN, UPSC_DB_URL, client, fetch_articles
    k, n = map(int, a.shard.split("/"))
    ids = [int(x) for x in a.ids.split(",") if x.strip()][k::n]
    main_c, upsc = client(MAIN_DB_URL, MAIN_DB_TOKEN), client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        arts = {x["id"]: x for x in fetch_articles(main_c, ids)}
        old = stored_notes(upsc, ids)
    finally:
        main_c.close()
        upsc.close()
    an = Analyzer(download_model(a.model_dir), n_threads=os.cpu_count())
    results = []
    for aid in ids:
        art = arts.get(aid)
        if not art:
            continue
        src = Source(art["title"], art["body"], art["published_at"])
        r = {"id": aid, "title": art["title"], "article": art["body"][:2500], "old": old.get(aid),
             "old_problems": problems(src, old[aid]) if aid in old else []}
        t0 = time.time()
        try:
            r["new"] = an.notes(art["title"], art["body"], art["category"], art["published_at"])
            r["new_problems"] = problems(src, r["new"])
        except Exception as e:
            r["error"] = str(e)[:300]
        r["seconds"] = round(time.time() - t0)
        print(f"{aid} {r['seconds']}s old={len(r['old_problems'])} dropped={len((r.get('new') or {}).get('dropped') or [])} "
              f"{'ERROR ' + r['error'] if 'error' in r else ''}", flush=True)
        results.append(r)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"prompt_version": PROMPT_VERSION, "model": MODEL_NAME, "results": results}, open(a.out, "w"), ensure_ascii=False)


def ptrs(note):
    return [f"  - [{p.get('type')}] {p.get('text')}" if isinstance(p, dict) else f"  - {p}"
            for p in (note or {}).get("prelims_pointers") or []]


def report(a):
    runs = [json.load(open(f)) for f in a.files]
    res = sorted((r for run in runs for r in run["results"]), key=lambda r: r["id"])
    pv = runs[0]["prompt_version"] if runs else "?"
    new = [r for r in res if "new" in r]
    old_bad = sum(1 for r in res if r["old_problems"])
    new_bad = sum(1 for r in new if r["new_problems"])
    dropped = sum(len(r["new"]["dropped"]) for r in new)
    few = sum(1 for r in new if len(r["new"]["prelims_pointers"]) < 2)
    L = [f"## Notes: stored vs {pv} ({len(res)} articles)", "",
         "| | stored | new |", "|---|---|---|",
         f"| notes with facts the article doesn't state (numbers, years, states) | {old_bad} | {new_bad} |",
         f"| notes written | {sum(1 for r in res if r['old'])} | {len(new)} (errors {len(res) - len(new)}) |",
         f"| items dropped by the grounding check | – | {dropped} |",
         f"| notes with fewer than 2 prelims pointers | {sum(1 for r in res if len((r['old'] or {}).get('prelims_pointers') or []) < 2)} | {few} |",
         f"| avg seconds per note | – | {round(sum(r['seconds'] for r in res) / max(1, len(res)))} |", ""]
    for r in res:
        o, n = r["old"] or {}, r.get("new") or {}
        L += [f"---\n### {r['id']} · {r['title'][:110]}",
              f"<details><summary>Article</summary>\n\n{r['article']}\n\n</details>\n",
              f"**Stored ({o.get('prompt_version')}):** {o.get('why_in_news')}", f"> {o.get('fact_box')}", *ptrs(o)]
        if r["old_problems"]:
            L += [f"_Not in the article: {'; '.join(r['old_problems'])}_"]
        if "error" in r:
            L += ["", f"**New: ERROR** {r['error']}", ""]
            continue
        L += ["", f"**New ({pv}):** {n.get('why_in_news')}", f"> {n.get('fact_box')}", *ptrs(n)]
        if n.get("dropped"):
            L += ["_Dropped by the check:_", *[f"  - ~~{d}~~" for d in n["dropped"]]]
        L += [""]
    md = "\n".join(L)
    print(md[:3000])
    open(a.md, "w").write(md + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(L[:10]) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--ids", required=True)
    r.add_argument("--shard", default="0/1")
    r.add_argument("--out", required=True)
    r.add_argument("--model-dir", default=os.path.join(os.path.dirname(HERE), "models"))
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+")
    p.add_argument("--md", required=True)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else report(a)
