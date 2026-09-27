"""Run the gate (and notes for gate-passed 'yes' cases) over eval/cases.jsonl.

Runs in GitHub Actions (upsc_eval.yml), sharded:
    python eval/run_eval.py --shard 0/4 --out eval_out/0.json
then eval/report.py merges shards, prints a markdown report and decides pass/fail.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def load_cases():
    with open(os.path.join(HERE, "cases.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", default=os.path.join(os.path.dirname(HERE), "models"))
    ap.add_argument("--score-min", type=int, default=int(os.environ.get("UPSC_SCORE_MIN") or 3))
    a = ap.parse_args()
    k, n = map(int, a.shard.split("/"))
    cases = load_cases()[k::n]

    from analyzer import MODEL_NAME, PROMPT_VERSION, Analyzer, download_model
    an = Analyzer(download_model(a.model_dir), n_threads=os.cpu_count())

    results, t0 = [], time.time()
    for i, c in enumerate(cases, 1):
        r = {"id": c["id"], "title": c["title"], "label": c["label"], "subjects": c["subjects"]}
        try:
            g = an.gate(c["title"], c["body"], c["category"])
            r.update(g)  # score, raw_score, hook, scope, party_political, reason
        except Exception as e:
            r.update(score=-1, reason=f"ERROR {e}")
        print(f"[{i}/{len(cases)}] {c['label']:<10} score={r['score']} {c['title'][:60]}", flush=True)
        results.append(r)

    # notes only where they'd be written in prod and we know the right answer
    for r in results:
        if r["label"] == "yes" and r["score"] >= a.score_min:
            c = next(x for x in cases if x["id"] == r["id"])
            try:
                r["notes"] = an.notes(c["title"], c["body"], c["category"])
            except Exception as e:
                r["notes_error"] = str(e)[:300]
            print(f"[notes] {c['title'][:60]}", flush=True)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump({"prompt_version": PROMPT_VERSION, "model": MODEL_NAME, "score_min": a.score_min,
                   "seconds": round(time.time() - t0), "results": results}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
