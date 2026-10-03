"""PILOT, READ-ONLY: link recent Polity notes to static syllabus anchors (static/polity_anchors.json).

    python tools/static_pilot.py select --days 30 --limit 50 > ids.txt
    python tools/static_pilot.py run --ids 1,2,3 --shard 0/3 --out out/0.json
    python tools/static_pilot.py report out/*.json --md report.md

Step 1 (no model): keyword shortlist of anchors for each note. Step 2: Gemma may pick 0-2 ids from that
shortlist only. It never writes static text: what a reader would see is the anchor's checked label + line.
Nothing is written to any DB; the report is for a human to judge accuracy before anything goes live.
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

ANCHORS = json.load(open(os.path.join(ROOT, "static", "polity_anchors.json"), encoding="utf-8"))["anchors"]
BY_ID = {a["id"]: a for a in ANCHORS}
MAX_CANDIDATES = 8

SYSTEM = """You link a current-affairs note for UPSC aspirants to the static Polity topic it applies.
You get the note and a short list of candidate static topics (Constitution articles, parts, schedules,
amendments, landmark cases). Pick at most 2 candidates, and only if the news DIRECTLY involves that
provision or case: the story invokes, uses, amends, challenges, or is decided under it, so that a
student writing a Mains answer on this news would cite it. Do NOT pick a topic that is only loosely
related, shares a word, or is general background. Picking none is the right answer when nothing fits.
For each pick, give one short reason (max 20 words) tied to the note."""


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\barts?\.\s*", "article ", s)
    s = re.sub(r"\barticle[-\s]+(\d)", r"article \1", s)
    return re.sub(r"\s+", " ", s)


PATTERNS = {a["id"]: [re.compile(r"(?<![\w])" + re.escape(norm(k)) + r"(?![\w])") for k in a["keywords"]]
            for a in ANCHORS}


def note_text(n):
    ptrs = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in n["pointers"])
    return " \n".join([n["title"], n["why_in_news"], n["fact_box"], ptrs, n["mains_question"] or "",
                       " ".join(n["keywords"])])


def shortlist(text):
    t = norm(text)
    hits = []
    for aid, pats in PATTERNS.items():
        found = [p.pattern for p in pats if p.search(t)]
        if found:
            hits.append((len(found), aid))
    hits.sort(key=lambda x: -x[0])
    return [aid for _, aid in hits[:MAX_CANDIDATES]]


def load_notes(upsc, ids):
    ph = ",".join("?" * len(ids))
    rows = upsc.execute(f"SELECT article_id, published_at, syllabus_node, why_in_news, fact_box, prelims_pointers, "
                        f"mains_question, keywords, prompt_version FROM upsc_articles WHERE article_id IN ({ph})",
                        ids).rows
    return {int(r[0]): {"id": int(r[0]), "published_at": r[1], "node": r[2], "why_in_news": r[3] or "",
                        "fact_box": r[4] or "", "pointers": json.loads(r[5] or "[]"), "mains_question": r[6],
                        "keywords": json.loads(r[7] or "[]"), "prompt_version": r[8]} for r in rows}


def select(a):
    from upsc_pipeline import UPSC_DB_TOKEN, UPSC_DB_URL, client
    upsc = client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        since = int(time.time()) - a.days * 86400
        rows = upsc.execute("SELECT article_id, cluster_id FROM upsc_articles WHERE subject = 'polity' "
                            "AND published_at >= ? ORDER BY published_at DESC LIMIT ?", [since, a.limit * 3]).rows
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


def schema(cands):
    return {"type": "object", "properties": {"links": {"type": "array", "maxItems": 2, "items": {
        "type": "object", "properties": {"id": {"type": "string", "enum": cands},
                                         "reason": {"type": "string", "maxLength": 160}},
        "required": ["id", "reason"]}}}, "required": ["links"]}


def run(a):
    from analyzer import MODEL_NAME, Analyzer, download_model
    from upsc_pipeline import MAIN_DB_TOKEN, MAIN_DB_URL, UPSC_DB_TOKEN, UPSC_DB_URL, client, fetch_articles
    k, n = map(int, a.shard.split("/"))
    ids = [int(x) for x in a.ids.split(",") if x.strip()][k::n]
    main_c, upsc = client(MAIN_DB_URL, MAIN_DB_TOKEN), client(UPSC_DB_URL, UPSC_DB_TOKEN)
    try:
        titles = {x["id"]: x["title"] for x in fetch_articles(main_c, ids)} if ids else {}
        notes = load_notes(upsc, ids) if ids else {}
    finally:
        main_c.close()
        upsc.close()
    an = None
    results = []
    for aid in ids:
        note = notes.get(aid)
        if not note:
            continue
        note["title"] = titles.get(aid, "")
        cands = shortlist(note_text(note))
        r = {**note, "candidates": cands, "links": []}
        t0 = time.time()
        if cands:
            an = an or Analyzer(download_model(a.model_dir), n_threads=os.cpu_count())
            lines = "\n".join(f"- {c}: {BY_ID[c]['label']} ({BY_ID[c]['kind']}): {BY_ID[c]['text']}" for c in cands)
            user = (f"Note title: {note['title']}\nWhy in news: {note['why_in_news']}\nFacts: {note['fact_box']}\n"
                    f"Mains question: {note['mains_question'] or 'n/a'}\n\nCandidate static topics:\n{lines}")
            try:
                out = an._call(SYSTEM, user, schema(cands), 200)
                picked, seen = [], set()
                for l in out.get("links") or []:
                    if l.get("id") in BY_ID and l["id"] in cands and l["id"] not in seen:
                        seen.add(l["id"])
                        picked.append({"id": l["id"], "reason": (l.get("reason") or "")[:200]})
                r["links"] = picked[:2]
            except Exception as e:
                r["error"] = str(e)[:300]
        r["seconds"] = round(time.time() - t0)
        print(f"{aid} cands={cands} links={[l['id'] for l in r['links']]} {r['seconds']}s", flush=True)
        results.append(r)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"model": MODEL_NAME, "anchors": len(ANCHORS), "results": results}, open(a.out, "w"),
              ensure_ascii=False)


def report(a):
    runs = [json.load(open(f)) for f in a.files]
    res = sorted((r for run in runs for r in run["results"]), key=lambda r: -(r["published_at"] or 0))
    with_c = [r for r in res if r["candidates"]]
    linked = [r for r in res if r["links"]]
    errors = [r for r in res if r.get("error")]
    use = Counter(l["id"] for r in res for l in r["links"])
    L = [f"## Static linking pilot: Polity ({len(res)} notes, {runs[0]['anchors'] if runs else 0} anchors)", "",
         "READ-ONLY trial. Nothing here is on the site, PDFs or channels.", "",
         "| | count |", "|---|---|",
         f"| notes checked | {len(res)} |",
         f"| notes with at least one keyword candidate | {len(with_c)} |",
         f"| notes the model linked | {len(linked)} |",
         f"| links suggested | {sum(len(r['links']) for r in res)} |",
         f"| notes where the model said none fits | {len(with_c) - len(linked) - len(errors)} |",
         f"| errors | {len(errors)} |", "",
         "**Most used anchors:** " + (", ".join(f"{BY_ID[i]['label']} ×{c}" for i, c in use.most_common(10)) or "none"),
         "", "How to judge: tick a link if a topper would cite it in a Mains answer on this news. "
         "Wrong or forced links are the risk to watch.", ""]
    for r in res:
        day = time.strftime("%d %b", time.gmtime((r["published_at"] or 0) + 19800))
        L += ["---", f"### {r['id']} · {day} · {r['title'][:120]}",
              f"_{r['why_in_news']}_", ""]
        if r["links"]:
            for l in r["links"]:
                an = BY_ID[l["id"]]
                L += [f"- [ ] **→ {an['label']}** ({an['kind']}): {an['text']}",
                      f"  - model's reason: {l['reason']}"]
        elif r.get("error"):
            L += [f"**ERROR** {r['error']}"]
        else:
            L += ["**No link.**" + ("" if r["candidates"] else " (no keyword candidate)")]
        rest = [c for c in r["candidates"] if c not in {l["id"] for l in r["links"]}]
        if rest:
            L += ["", "Candidates not picked: " + ", ".join(BY_ID[c]["label"] for c in rest)]
        L += [""]
    md = "\n".join(L)
    print(md[:4000])
    open(a.md, "w").write(md + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(md + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--limit", type=int, default=50)
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
