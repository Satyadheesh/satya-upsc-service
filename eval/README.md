# UPSC gate/notes eval

`cases.jsonl`: 120 articles (Nov 2025) sampled from the v1 run, hand-labelled:

- `yes` (11): an aspirant should see it (gate score >= 3). `subjects` = acceptable primary subjects.
- `no` (87): noise (crime, party politics, local events, foreign domestic news...).
- `borderline` (22): reasonable either way; reported but not scored.

Runs in GitHub Actions (`UPSC Eval` workflow), automatically on every push that touches
`analyzer.py`, `syllabus.py` or `eval/`, or by hand from the Actions tab. Six shards run the gate
(and notes for gate-passed `yes` cases); the report job posts a markdown summary on the run page.

Targets (a pass writes `upsc_meta.approved_prompt`; the pipeline only runs approved prompts): false-positive rate on `no` <= 10%, recall on `yes` >= 80%,
subject accuracy on `yes` >= 80%. Add cases whenever you see a bad card in prod.
