"""LLM layer: stage 1 = strict relevance gate, stage 2 = exam notes.

Both stages use grammar-constrained JSON (llama.cpp json schema) and are then
validated in Python. Pure functions (`validate_gate`, `validate_notes`) are
unit-tested without a model.
"""
import json
import os

from syllabus import EXAM_TYPES, SYLLABUS, paper_of, prompt_tree

PROMPT_VERSION = "v2.0"
MODEL_REPO = os.environ.get("UPSC_MODEL_REPO", "bartowski/Qwen2.5-7B-Instruct-GGUF")
MODEL_FILENAME = os.environ.get("UPSC_MODEL_FILE", "Qwen2.5-7B-Instruct-Q4_K_M.gguf")
MODEL_NAME = MODEL_FILENAME.rsplit(".", 1)[0]

NODE_OWNER = {n: s for s, (_, _, nodes) in SYLLABUS.items() for n in nodes}
POINTER_TYPES = ["constitution", "act_bill", "scheme", "institution", "report_index", "place",
                 "species_environment", "sci_tech", "international_org", "person_post", "data_fact"]

# ------------------------------------------------------------------ stage 1
GATE_SYSTEM = """You are a strict editor for UPSC Civil Services (CSE) current affairs.
Decide if an aspirant NEEDS this news item for Prelims or Mains. Most news is NOT useful; be stingy.

Score 0-5:
5 = core exam material: constitutional amendment or new law/bill; landmark Supreme Court judgment; major central scheme/policy launch or reform; RBI policy or key economic data; major agreement/summit involving India; important report or index (who publishes it, India's rank); ISRO/DRDO/S&T milestone; species, protected area, climate or pollution policy; appointment to a constitutional post.
4 = clearly useful: national policy debate with facts; government/committee report; internal security development (LWE, insurgency, cyber, border); global event with direct impact on India (trade, energy, diaspora, neighbourhood).
3 = useful as a Mains example: state policy with national relevance; governance or social-sector case with data; disaster and its management.
2 = marginal. 1 = barely. 0 = none.

ALWAYS score 0 or 1 for:
- individual crimes, arrests, murders, assaults, accidents, fires, deaths, obituaries
- party politics: allegations, protests, campaign speeches, defections talk, candidate or seat contests, poll predictions
- routine events: ministerial visits, review meetings, inaugurations of local works, statements of intent, festivals, temple events
- local civic complaints (roads, drains, traffic) without a policy angle
- entertainment, celebrities, sports, business gossip, company results, stock tips
- another country's domestic politics, crime or society with no India link and no global significance

Reply JSON only: {"score": <0-5>, "reason": "<max 12 words>"}"""

GATE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
                   "reason": {"type": "string"}},
    "required": ["score", "reason"],
}

# ------------------------------------------------------------------ stage 2
NOTES_SYSTEM = f"""You are a senior UPSC CSE mentor writing crisp current-affairs notes.
Map the news to exactly ONE primary syllabus node from this fixed tree (use the keys exactly):
{prompt_tree()}

Fields:
- exam_type: "prelims" (mainly facts), "mains" (mainly analysis) or "both".
- subject, node: primary keys from the tree above. "ir" is ONLY for India's foreign relations and global bodies, never for domestic news.
- secondary: 0-2 other {{"subject","node"}} pairs if the item clearly also fits another paper.
- why_in_news: one line, starts with the event (e.g. "Supreme Court struck down ...").
- fact_box: 2-3 sentences of hard facts from the article: who, what, numbers, dates, bodies.
- prelims_pointers: 2-5 short items an MCQ could test (the scheme and its ministry, the Act or Article, the body and its parent ministry, the report and its publisher, the place and its state/river/neighbour, the species and its IUCN status). type from: {", ".join(POINTER_TYPES)}.
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
    return {"score": score, "reason": _clip(data.get("reason"), 120)}


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
