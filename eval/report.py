"""Merge eval shard outputs, print a markdown report, and approve the prompt if targets are met.

    python eval/report.py eval_out/*.json [--approve]

With --approve and a passing run, writes upsc_meta.approved_prompt = PROMPT_VERSION in the
UPSC DB; setup_shards.py refuses to schedule work for an unapproved prompt version.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

TARGET_FP = 0.10       # max share of 'no' cases passing the gate
TARGET_RECALL = 0.80   # min share of 'yes' cases passing
TARGET_SUBJECT = 0.80  # min subject accuracy on 'yes' cases with notes


def pct(a, b):
    return f"{a}/{b} ({(100 * a / b if b else 0):.0f}%)"


def main():
    args = sys.argv[1:]
    md_out = args[args.index("--md") + 1] if "--md" in args else None
    files = [f for f in args if f.endswith(".json")]
    runs = [json.load(open(f)) for f in files]
    if not runs:
        raise SystemExit("no eval outputs")
    pv, smin = runs[0]["prompt_version"], runs[0]["score_min"]
    model = runs[0].get("model", "?")
    approval = f"{pv}|{model}"
    res = [r for run in runs for r in run["results"]]
    by = lambda lab: [r for r in res if r["label"] == lab]
    passed = lambda rs: [r for r in rs if r["score"] >= smin]

    no, yes, border = by("no"), by("yes"), by("borderline")
    fp, tp = passed(no), passed(yes)
    noted = [r for r in yes if "notes" in r]
    subj_ok = [r for r in noted if r["notes"]["subject"] in r["subjects"]]
    errors = [r for r in res if r["score"] < 0] + [r for r in yes if "notes_error" in r]

    fp_rate = len(fp) / max(1, len(no))
    recall = len(tp) / max(1, len(yes))
    subj = len(subj_ok) / max(1, len(noted))
    ok = fp_rate <= TARGET_FP and recall >= TARGET_RECALL and subj >= TARGET_SUBJECT

    L = [f"## UPSC eval — prompt {pv}, {model} (score ≥ {smin}) — {'✅ PASS' if ok else '❌ FAIL'}", "",
         "| metric | result | target |", "|---|---|---|",
         f"| false positives on `no` | {pct(len(fp), len(no))} | ≤ {TARGET_FP:.0%} |",
         f"| recall on `yes` | {pct(len(tp), len(yes))} | ≥ {TARGET_RECALL:.0%} |",
         f"| subject accuracy | {pct(len(subj_ok), len(noted))} | ≥ {TARGET_SUBJECT:.0%} |",
         f"| 'Also' tags kept / dropped as unrelated (checked on the note's words) | "
         f"{sum(len(r['notes'].get('secondary') or []) for r in noted)} / "
         f"{sum(1 for r in noted for d in r['notes'].get('dropped') or [] if d.startswith('secondary:'))} | – |",
         f"| borderline passed | {pct(len(passed(border)), len(border))} | – |",
         f"| errors | {len(errors)} | 0 |",
         "", "v1 baseline: false positives 64%, recall 82%. v2.0: FP 1%, recall 27%. v2.1: FP 34%, recall 100%. v2.2 (7B): FP 26%, recall 100%. v2.3: Qwen14B FP 21%/recall 91%, Gemma4-12B FP 3%/recall 73%, Gemma4-E4B FP 25%/recall 91%.", "",
         "### By threshold", "| keep score ≥ | FP on `no` | recall on `yes` | borderline kept |", "|---|---|---|---|",
         *[f"| {t}{' (current)' if t == smin else ''} | {pct(sum(r['score'] >= t for r in no), len(no))} | "
           f"{pct(sum(r['score'] >= t for r in yes), len(yes))} | {pct(sum(r['score'] >= t for r in border), len(border))} |"
           for t in (2, 3, 4)], ""]
    if fp:
        L += ["### False positives", *[f"- s={r['score']} {r['title'][:90]} — _{r['reason']}_" for r in fp], ""]
    fn = [r for r in yes if r["score"] < smin]
    if fn:
        L += ["### Missed", *[f"- s={r['score']} {r['title'][:90]} — _{r['reason']}_" for r in fn], ""]
    if noted:
        L += ["### Sample notes"]
        for r in noted:
            n = r["notes"]
            mark = "✅" if r in subj_ok else f"❌ want {r['subjects']}"
            L += [f"**{r['title'][:90]}** — {n['gs_paper']} › {n['subject']} › {n['syllabus_node']} {mark}",
                  f"- Why: {n['why_in_news']}",
                  *[f"- [{p['type']}] {p['text']}" for p in n["prelims_pointers"]],
                  f"- Q: {n['mains_question']}",
                  f"- Also: {', '.join(x['node'] for x in n.get('secondary') or []) or '—'}"
                  + (f" (dropped: {', '.join(d.split(' ')[1] for d in n.get('dropped') or [] if d.startswith('secondary:'))})"
                     if any(d.startswith('secondary:') for d in n.get('dropped') or []) else ""), ""]
    if errors:
        L += ["### Errors", *[f"- {r['title'][:80]}: {r.get('reason') or r.get('notes_error')}" for r in errors]]
    md = "\n".join(L)
    print(md)
    if md_out:
        with open(md_out, "w") as f:
            f.write(md + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md + "\n")

    if "--approve" in sys.argv and ok:
        from turso_http import execute
        execute([("INSERT OR REPLACE INTO upsc_meta (key, value) VALUES ('approved_prompt', ?)", [approval])])
        print(f"\nApproved {approval} for production.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
