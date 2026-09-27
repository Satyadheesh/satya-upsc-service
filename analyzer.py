"""LLM layer: stage 1 = strict relevance gate, stage 2 = exam notes.

Both stages use grammar-constrained JSON (llama.cpp json schema) and are then
validated in Python. Pure functions (`validate_gate`, `validate_notes`) are
unit-tested without a model.
"""
import json
import os

from syllabus import EXAM_TYPES, SYLLABUS, paper_of, prompt_tree

PROMPT_VERSION = "v2.1"
MODEL_REPO = os.environ.get("UPSC_MODEL_REPO", "bartowski/Qwen2.5-7B-Instruct-GGUF")
MODEL_FILENAME = os.environ.get("UPSC_MODEL_FILE", "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
MODEL_NAME = MODEL_FILENAME.rsplit(".", 1)[0]

NODE_OWNER = {n: s for s, (_, _, nodes) in SYLLABUS.items() for n in nodes}
POINTER_TYPES = ["constitution", "act_bill", "scheme", "institution", "report_index", "place",
                 "species_environment", "sci_tech", "international_org", "person_post", "data_fact"]

# ------------------------------------------------------------------ stage 1
# How news shows up in UPSC papers. The model must name one before scoring; "none" caps the score.
HOOKS = {
    "constitutional_authority": "action/statement of a constitutional post or body (President, Governor, ECI, CAG, Finance Commission, UPSC, Speaker) incl. firsts and records",
    "court_constitutional": "Supreme Court / High Court hearing or ruling on rights, federalism, elections, citizenship, environment, governance",
    "law_policy_scheme": "new or amended law, bill, rule, central/state scheme, regulator decision (RBI, SEBI, TRAI...)",
    "elections_process": "electoral process itself: roll revision (SIR), delimitation, ECI rules, electoral reforms (NOT campaigns or candidates)",
    "economy": "macro data, budget/tax, trade deals & FTAs, banking, industry policy, agriculture policy",
    "india_foreign_relations": "India's bilateral/multilateral ties: visits, summits, agreements, aid to neighbours, diaspora policy",
    "global_affairs": "major world event aspirants must know: wars, coups, regime change, global treaties, UN/WTO/IMF decisions",
    "report_index": "report, survey or ranking by UN/World Bank/NITI/govt bodies (who publishes it, key findings)",
    "science_tech": "space, defence tech, biotech, AI, semiconductors, nuclear/energy tech",
    "environment": "species, protected areas, pollution, climate policy, conservation, human-wildlife conflict policy",
    "disaster": "cyclones, floods, earthquakes and the disaster-management response",
    "internal_security": "insurgency, LWE, J&K/North-East/Manipur security, border management, terror probes by NIA, cyber security",
    "history_culture": "anniversaries of historical figures, art, architecture, festivals of national significance, heritage/GI tags, awards",
    "society_data": "social issue backed by data or policy: health, education, gender, caste, demography, urbanisation",
    "none": "no exam hook",
}

GATE_SYSTEM = """You screen news for UPSC Civil Services (CSE) aspirants.
Prelims tests FACTS (firsts, bodies, places, reports, schemes, species, historical figures);
Mains tests ISSUES (policy, governance, security, IR, economy, ethics). A story does not need a
policy angle to matter: a factual 'first', a UN finding or a court hearing is Prelims material.

Step 1 - pick the ONE exam hook that fits best:
""" + "\n".join(f"- {k}: {v}" for k, v in HOOKS.items()) + """

Hook is "none" for: individual crimes/arrests/accidents/deaths, party politics (allegations,
protests, campaigns, candidates, seat contests, leadership tussles), routine local administration,
entertainment, celebrities, sports, company news, and another country's domestic crime or society.

Step 2 - score how much an aspirant needs it:
5 = certain to be useful (landmark ruling/law/scheme, major summit or agreement, key report, ISRO/DRDO milestone)
4 = clearly useful (important development under the hook, national relevance)
3 = useful fact or example for the hook (state-level policy, a first/record, ongoing issue update)
2 = weak link to the hook
0-1 = hook is none

Reply JSON only: {"hook": "<hook>", "score": <0-5>, "reason": "<max 12 words>"}"""

GATE_SCHEMA = {
    "type": "object",
    "properties": {"hook": {"type": "string", "enum": list(HOOKS)},
                   "score": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
                   "reason": {"type": "string"}},
    "required": ["hook", "score", "reason"],
}

# ------------------------------------------------------------------ stage 2
NOTES_SYSTEM = f"""You are a senior UPSC CSE mentor writing crisp current-affairs notes.
Map the news to exactly ONE primary syllabus node from this fixed tree (use the keys exactly):
{prompt_tree()}

Fields:
- exam_type: "prelims" (mainly facts), "mains" (mainly analysis) or "both".
- subject, node: primary keys from the tree above. "ir" is ONLY for India's foreign relations and global bodies, never for domestic news. "neighbourhood" means SAARC neighbours + China, Myanmar, Afghanistan; other countries are "bilateral".
- secondary: 0-2 other {{"subject","node"}} pairs if the item clearly also fits another paper.
- why_in_news: one line saying what happened and why it matters for the exam, with the key actor (e.g. "Supreme Court struck down electoral bonds as violating the right to information").
- fact_box: 2-3 sentences of hard facts from the article: who, what, numbers, dates, bodies.
- prelims_pointers: 2-5 short items an MCQ could test, each a complete fact, not just a name
  (e.g. "CEPA: India-UAE trade pact in force since May 2022", "BSF: under the Ministry of Home Affairs").
  type: constitution = Article/Schedule; act_bill = a law or bill; scheme = a government scheme or mission;
  institution = an Indian body/agency; international_org = a foreign or multilateral body/agreement;
  report_index = report or ranking and its publisher; place = location with state/country/river;
  species_environment; sci_tech; person_post = a constitutional or official post; data_fact = a number.
- mains_question: one UPSC-style Mains question (e.g. "Critically examine ...", "Discuss ...") in <= 30 words.
- mains_dimensions: 2-4 short angles to cover in an answer (e.g. "federal concerns", "fiscal cost", "way forward: ...").
- keywords: 3-6 answer-writing terms.

Rules: use only facts from the article. Mention an Article number, Act name, date or figure only if the article states it or you are certain. No party-political opinion. Plain English. JSON only."""

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "exam_type": {"type": "string", "enum": EXAM_TYPES},
        "subject": {"type": "string", "enum": list(SYLLABUS)},
        "node": {"type": "string", "enum": list(NODE_OWNER)},
        "secondary": {"type": "array", "maxItems": 2, "items": {
            "type": "object",
            "properties": {"subject": {"type": "string", "enum": list(SYLLABUS)},
                           "node": {"type": "string", "enum": list(NODE_OWNER)}},
            "required": ["subject", "node"]}},
        "why_in_news": {"type": "string"},
        "fact_box": {"type": "string"},
        "prelims_pointers": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"type": {"type": "string", "enum": POINTER_TYPES}, "text": {"type": "string"}},
            "required": ["type", "text"]}},
        "mains_question": {"type": "string"},
        "mains_dimensions": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "keywords": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
    },
    "required": ["exam_type", "subject", "node", "secondary", "why_in_news", "fact_box",
                 "prelims_pointers", "mains_question", "mains_dimensions", "keywords"],
}


class InvalidOutput(ValueError):
    pass


def _clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def validate_gate(data):
    try:
        score = int(data["score"])
    except (KeyError, TypeError, ValueError):
        raise InvalidOutput(f"bad gate output: {data!r}")
    if not 0 <= score <= 5:
        raise InvalidOutput(f"score out of range: {score}")
    hook = data.get("hook") if data.get("hook") in HOOKS else "none"
    if hook == "none":
        score = min(score, 1)
    return {"score": score, "hook": hook, "reason": _clip(f"{hook}: {data.get('reason') or ''}", 140)}


def validate_notes(data):
    if not isinstance(data, dict):
        raise InvalidOutput("notes not an object")
    node = data.get("node")
    if node not in NODE_OWNER:
        raise InvalidOutput(f"unknown node: {node!r}")
    subject = NODE_OWNER[node]  # node keys are unique -> node decides subject/paper
    exam_type = data.get("exam_type") if data.get("exam_type") in EXAM_TYPES else "both"
    why = _clip(data.get("why_in_news"), 220)
    fact = _clip(data.get("fact_box"), 600)
    if len(why) < 15 or len(fact) < 30:
        raise InvalidOutput("why_in_news/fact_box too short")
    secondary, seen = [], {node}
    for s in data.get("secondary") or []:
        n = (s or {}).get("node")
        if n in NODE_OWNER and n not in seen and NODE_OWNER[n] != subject:
            secondary.append({"subject": NODE_OWNER[n], "node": n})
            seen.add(n)
    pointers = []
    for p in data.get("prelims_pointers") or []:
        t = _clip((p or {}).get("text"), 200)
        if len(t) >= 5:
            pointers.append({"type": p.get("type") if p.get("type") in POINTER_TYPES else "data_fact", "text": t})
    dedupe = lambda xs, n, lim: list(dict.fromkeys(_clip(x, n) for x in (xs or []) if str(x).strip()))[:lim]
    return {
        "exam_type": exam_type,
        "gs_paper": paper_of(subject),
        "subject": subject,
        "syllabus_node": node,
        "secondary": secondary[:2],
        "why_in_news": why,
        "fact_box": fact,
        "prelims_pointers": pointers[:5],
        "mains_question": _clip(data.get("mains_question"), 260) or None,
        "mains_dimensions": dedupe(data.get("mains_dimensions"), 120, 4),
        "keywords": dedupe(data.get("keywords"), 40, 6),
    }


def article_prompt(title, body, category):
    return f"Title: {title}\nCategory: {category or 'n/a'}\nArticle:\n{(body or '')[:2500]}"


class Analyzer:
    def __init__(self, model_path, n_ctx=4096, n_threads=None):
        from llama_cpp import Llama
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads,
                         n_gpu_layers=int(os.environ.get("UPSC_GPU_LAYERS", "-1")), verbose=False)

    def _call(self, system, user, schema, max_tokens):
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object", "schema": schema},
            temperature=0.1, max_tokens=max_tokens,
        )
        return json.loads(out["choices"][0]["message"]["content"])

    def _retry(self, fn, validate):
        err = None
        for _ in range(2):  # one retry on invalid output
            try:
                return validate(fn())
            except (InvalidOutput, json.JSONDecodeError) as e:
                err = e
        raise InvalidOutput(str(err))

    def gate(self, title, body, category):
        user = article_prompt(title, body, category)
        return self._retry(lambda: self._call(GATE_SYSTEM, user, GATE_SCHEMA, 60), validate_gate)

    def notes(self, title, body, category):
        user = article_prompt(title, body, category)
        return self._retry(lambda: self._call(NOTES_SYSTEM, user, NOTES_SCHEMA, 700), validate_notes)


def download_model(model_dir):
    from huggingface_hub import hf_hub_download
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, MODEL_FILENAME)
    if not os.path.exists(path):
        hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILENAME, local_dir=model_dir)
    return path
