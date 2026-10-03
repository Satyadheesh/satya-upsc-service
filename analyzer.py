"""LLM layer: stage 1 = strict relevance gate, stage 2 = exam notes.

Both stages use grammar-constrained JSON (llama.cpp json schema) and are then
validated in Python. Pure functions (`validate_gate`, `validate_notes`) are
unit-tested without a model.
"""
import json
import os
import re
import time

from syllabus import EXAM_TYPES, SYLLABUS, paper_of, prompt_tree

PROMPT_VERSION = "v2.7"
MODEL_REPO = os.environ.get("UPSC_MODEL_REPO", "unsloth/gemma-4-12b-it-GGUF")
MODEL_FILENAME = os.environ.get("UPSC_MODEL_FILE", "gemma-4-12b-it-Q4_K_M.gguf")
MODEL_NAME = MODEL_FILENAME.rsplit(".", 1)[0]

# Deterministic India-link check: the model often calls foreign stories "national".
INDIA_RE = re.compile(
    r"\b(india|indian|indians|new delhi|delhi|lok sabha|rajya sabha|niti aayog|rbi|isro|drdo|"
    r"union (?:minister|government|cabinet|budget)|centre's|crore|lakh|rs\.? ?\d|"
    r"andhra|arunachal|assam|bihar|chhattisgarh|goa|gujarat|haryana|himachal|jharkhand|karnataka|"
    r"kerala|madhya pradesh|maharashtra|manipur|meghalaya|mizoram|nagaland|odisha|punjab|rajasthan|"
    r"sikkim|tamil nadu|telangana|tripura|uttar pradesh|uttarakhand|west bengal|jammu|kashmir|ladakh|"
    r"puducherry|chandigarh|lakshadweep|andaman|mumbai|kolkata|chennai|bengaluru|hyderabad|"
    r"ahmedabad|pune|lucknow|patna|bhopal|jaipur|guwahati|thiruvananthapuram|kochi|imphal)\b|₹", re.I)


def india_link(title, body):
    return bool(INDIA_RE.search(f"{title}\n{(body or '')[:4000]}"))


# ------------------------------------------------------------------ grounding (v2.6)
# A note may only state what the article (the part the model saw) states. Checked in code, not trusted to the
# prompt: numbers and years must appear in the article (1% rounding allowed; a year may also be the publication
# year), an Indian state or UT may only be named if the article names it, and a prelims pointer must share most
# of its content words with the article. Ungrounded pointers / fact-box sentences are dropped; an ungrounded
# why-in-news is retried with feedback.
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
STATE_RE = re.compile(
    r"\b(andhra pradesh|arunachal pradesh|assam|bihar|chhattisgarh|goa|gujarat|haryana|himachal pradesh|jharkhand|"
    r"karnataka|kerala|madhya pradesh|maharashtra|manipur|meghalaya|mizoram|nagaland|odisha|orissa|punjab|rajasthan|"
    r"sikkim|tamil nadu|telangana|tripura|uttar pradesh|uttarakhand|west bengal|jammu and kashmir|ladakh|puducherry|"
    r"chandigarh|lakshadweep|andaman and nicobar)\b", re.I)
WORD_RE = re.compile(r"[a-z][a-z'\-]+|\d+(?:[.,]\d+)*")
STOP = set("""about above after again against also among and another any are around because been before being below
between both but by can could did does doing down during each either even ever every few for from further had has have
having here him his how however into its itself just least less made make many may might more most much must near
neither never nor not now off often once only other others our out over own per rather same several shall should since
some such than that the their them then there these they this those though through thus till under until upon very was
were what when where whether which while who whom whose why will with within without would yet india indian new said
says year years including""".split())
TRIVIA_RE = re.compile(
    r"\b(?:is|was|serves as)\s+(?:the\s+)?(?:current\s+)?(?:prime minister|president|chief minister|governor|capital)\s+of\b|"
    r"^\S[^:]{0,40}:\s*(?:located|situated)\s+in\b", re.I)


def _num(x):
    return x.replace(",", "")


class Source:
    """What the model saw (title + the first 2,500 characters of the article) as numbers and words."""

    def __init__(self, title, body, published_at=None):
        self.text = f"{title or ''}\n{(body or '')[:2500]}"
        self.nums = {_num(n) for n in NUM_RE.findall(self.text)}
        self.words = _words(self.text)
        self.states = {m.lower() for m in STATE_RE.findall(self.text)}
        self.year = time.gmtime(published_at + 19800).tm_year if published_at else None

    def number_ok(self, n):
        if n in self.nums or (self.year and n in (str(self.year), str(self.year)[2:])):
            return True
        try:
            v = float(n)
        except ValueError:
            return False
        return any(w and abs(v - w) / abs(w) <= 0.01 for w in (_float(m) for m in self.nums) if w is not None)

    def problems(self, text):
        """What in `text` the article doesn't support: numbers, then states."""
        bad = []
        for m in NUM_RE.finditer(text or ""):
            n = _num(m.group())
            small = n.isdigit() and int(n) <= 5 and not text[m.end():m.end() + 2].lstrip().startswith("%")
            if not small and not self.number_ok(n) and n not in bad:
                bad.append(n)
        bad += [s for s in {x.lower() for x in STATE_RE.findall(text or "")} if s not in self.states]
        return bad

    def overlap(self, text):
        ws = _words(text)
        return 1.0 if not ws else len(ws & self.words) / len(ws)


def _float(x):
    try:
        return float(x)
    except ValueError:
        return None


def _words(text):
    return {w[:6] for w in WORD_RE.findall((text or "").lower()) if w not in STOP and (len(w) >= 4 or w[0].isdigit())}


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text or "") if s.strip()]


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

Hook is "none" for:
- individual crimes, FIRs, police chargesheets, arrests, bail hearings, sexual offenses (rape, POCSO, molestation),
  domestic violence, murder, or local trials (even if heard in High Court/Supreme Court). UPSC CSE tests policy,
  statutory amendments, and landmark Constitution Benches, NEVER individual crimes or criminal trials.
- party politics (allegations, protests, campaigns, candidates, seat contests, leadership tussles),
- routine local administration, accidents, or local disputes (does NOT apply to conflict zones like Manipur, J&K, or border areas which belong to internal_security),
- entertainment, celebrities, sports, company news, and another country's domestic crime or society.

Step 2 - scope: the level at which the SUBJECT matters (not where the event happened;
a national anniversary observed in one city is "national"):
- local: one city, district, municipality, university, temple, company or project
- state: a state government, legislature, High Court or a state-wide issue
- national: India-wide law, institution, policy, security or social issue
- international_india: involves India or Indians (visits, deals, aid, diaspora, trade)
- international_other: another country's affairs with no India involvement

Step 3 - party_political: true if the story is mainly a politician or party criticising rivals,
making claims or promises, campaigning, or commenting on elections/candidates. False for
official actions (a law passed, an order issued, a court or ECI decision, a visit or agreement).

Step 4 - score how much an aspirant needs it:
5 = certain to be useful (landmark ruling/law/scheme, major summit or agreement, key report, ISRO/DRDO milestone)
4 = clearly useful (important development under the hook, national relevance)
3 = useful fact or example for the hook (state-level policy, a first/record, ongoing issue update)
2 = weak link to the hook
0-1 = hook is none

Reply JSON only: {"hook": "<hook>", "scope": "<scope>", "party_political": <true|false>, "score": <0-5>, "reason": "<max 12 words>"}"""

SCOPES = ["local", "state", "national", "international_india", "international_other"]
# hooks that can matter even with no India involvement
GLOBAL_HOOKS = {"global_affairs", "report_index", "environment", "science_tech"}

GATE_SCHEMA = {
    "type": "object",
    "properties": {"hook": {"type": "string", "enum": list(HOOKS)},
                   "scope": {"type": "string", "enum": SCOPES},
                   "party_political": {"type": "boolean"},
                   "score": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
                   "reason": {"type": "string"}},
    "required": ["hook", "scope", "party_political", "score", "reason"],
}

# ------------------------------------------------------------------ stage 2
NOTES_SYSTEM = f"""You are a senior UPSC CSE mentor writing crisp, authoritative current-affairs notes.
Map the news to exactly ONE primary syllabus node from this fixed tree (use the keys exactly):
{prompt_tree()}

Fields:
- exam_type: "prelims" (mainly facts), "mains" (mainly analysis) or "both".
- subject, node: primary keys from the tree above. "ir" is ONLY for India's foreign relations and global bodies, never for domestic news. "neighbourhood" means SAARC neighbours + China, Myanmar, Afghanistan; other countries are "bilateral".
  "places_in_news" only when the location itself is the fact (a new site, a map question); security,
  border or conflict news goes under "security", never geography.
- secondary: 0-2 other {{"subject","node"}} pairs if the item clearly also fits another paper.
- why_in_news: one line saying what happened and why it matters for the exam, with the key actor (e.g. "Supreme Court struck down electoral bonds as violating the right to information").
  Say who did or said what exactly as the article does: a petitioner's argument, an allegation, a demand or a proposal
  is never a court ruling, an official finding or a decision.
- fact_box: 2-3 sentences of hard facts from the article: who, what, numbers, dates, bodies.
- prelims_pointers: 2-5 short items an MCQ could test, each a complete fact FROM THIS ARTICLE, not just a name
  (e.g. "CEPA: India-UAE trade pact in force since May 2022", "BSF: under the Ministry of Home Affairs").
  No general-knowledge trivia the article doesn't state (who heads a country, where a city or fort is, what a festival is).
  type: constitution = Article/Schedule; act_bill = a law or bill; scheme = a government scheme or mission;
  institution = an Indian body/agency; international_org = a foreign or multilateral body/agreement;
  report_index = report or ranking and its publisher; place = location with state/country/river;
  species_environment; sci_tech; person_post = a constitutional or official post; data_fact = a number.
- mains_question: one UPSC-style Mains question (e.g. "Critically examine ...", "Discuss ...") in <= 30 words,
  about the underlying issue or institution, never about a person's career or image.
- mains_dimensions: 2-4 substantive, issue-specific analytical angles (8-20 words, under 150 characters each) covering institutional bottlenecks, constitutional/legal conflicts, or policy trade-offs.
  * STRICT NEGATIVE RULE: DO NOT use generic one-phrase headings like "Way forward", "Challenges", "Significance", "Need for reforms", "Role of technology", "Way ahead", or "Impact on economy".
  * BAD (generic): "Challenges: implementation issues", "Role of technology in tracking", "Way forward: better funding".
  * GOOD (specific): "Enforcement gap: Shortage of food safety officers and accredited testing labs under IMS Act", "Federal friction: State regulatory autonomy vs Central guidelines", "Supply chain bottleneck: High import reliance on raw wafer inputs despite PLI scheme incentives".
- keywords: 3-6 answer-writing terms.

Core Accuracy Rules:
1. Grounding: every fact must be stated in the article: names, places and the state or country they are in, numbers,
   dates, Article numbers, Act names and years. Do not add background from memory, even if you are sure it is true;
   leave it out instead. Do not compute new numbers (ages, anniversaries, differences).
2. Dates: write a year only if the article gives it, or it is the publication year given above and the article clearly
   means this year ("on Tuesday", "this October"). Never guess an older year. No year known: give the month alone or
   leave the date out.
3. Cross-field consistency: targets and dates in why_in_news, fact_box and prelims_pointers must agree (e.g. an interim
   phase target vs the final cumulative target).
4. No party-political opinion. Plain English. JSON only."""

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


def _fit(s, n, seps=(". ", "; ", ": ", " — ", ", ")):
    """The whole text if it fits in n characters; otherwise the longest clean cut (a sentence or clause end in the
    second half) — never mid-word and never with '…'. None if there is no clean cut."""
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    head = s[:n]
    for sep in seps:
        k = head.rfind(sep)
        if k >= n // 2:
            return head[:k].rstrip(" ,;:—") + ("." if sep == ". " else "")
    return None


def _clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def validate_gate(data, india=True):
    try:
        score = int(data["score"])
    except (KeyError, TypeError, ValueError):
        raise InvalidOutput(f"bad gate output: {data!r}")
    if not 0 <= score <= 5:
        raise InvalidOutput(f"score out of range: {score}")
    hook = data.get("hook") if data.get("hook") in HOOKS else "none"
    scope = data.get("scope") if data.get("scope") in SCOPES else "national"
    if not india:
        scope = "international_other"  # text never mentions India: trust that over the model
    political = data.get("party_political") is True
    cap, why = 5, ""
    official = hook in {"court_constitutional", "constitutional_authority", "elections_process"}
    if hook == "none":
        cap, why = 1, "no hook"
    elif political and not official:
        # a court case or an ECI/President action stays useful even when parties are involved
        cap, why = 1, "party-political"
    elif scope == "local" and hook != "history_culture":
        # anniversaries/culture are often reported via one local event
        cap, why = 1, "local"
    elif scope == "international_other" and hook not in GLOBAL_HOOKS:
        cap, why = 1, "foreign, no India link"
    elif scope == "international_other" and hook == "global_affairs":
        cap, why = (score if score >= 4 else 2), "foreign politics: needs 4+"
    capped = min(score, cap)
    tag = f"{hook}/{scope}" + (f" capped:{why}" if capped < score else "")
    return {"score": capped, "raw_score": score, "hook": hook, "scope": scope, "party_political": political,
            "reason": _clip(f"{tag}: {data.get('reason') or ''}", 160)}


def validate_notes(data, src=None):
    """Clean and check model notes. With `src` (the article as the model saw it), facts the article doesn't
    support are dropped (pointers, fact-box sentences) or rejected (why-in-news)."""
    if not isinstance(data, dict):
        raise InvalidOutput("notes not an object")
    dropped = []
    if src is not None:
        bad = src.problems(data.get("why_in_news"))
        if bad:
            raise InvalidOutput(f"why_in_news states what the article doesn't: {', '.join(bad[:3])}")
        keep = []
        for sent in _sentences(" ".join(str(data.get("fact_box") or "").split())):
            bad = src.problems(sent)
            (dropped.append(f"fact: {sent} [{', '.join(bad[:3])}]") if bad else keep.append(sent))
        data = {**data, "fact_box": " ".join(keep)}
        ptrs = []
        for p in data.get("prelims_pointers") or []:
            t = " ".join(str((p or {}).get("text") or "").split())
            bad = src.problems(t)
            if bad:
                dropped.append(f"pointer: {t} [{', '.join(bad[:3])}]")
            elif TRIVIA_RE.search(t):
                dropped.append(f"pointer: {t} [trivia]")
            elif src.overlap(t) < 0.5:
                dropped.append(f"pointer: {t} [not in article]")
            else:
                ptrs.append(p)
        data = {**data, "prelims_pointers": ptrs}
    node = data.get("node")
    if node not in NODE_OWNER:
        raise InvalidOutput(f"unknown node: {node!r}")
    subject = NODE_OWNER[node]  # node keys are unique -> node decides subject/paper
    exam_type = data.get("exam_type") if data.get("exam_type") in EXAM_TYPES else "both"
    why = _fit(data.get("why_in_news"), 220)
    if why is None:
        raise InvalidOutput("why_in_news is too long: one line under 200 characters")
    fact = _fit(data.get("fact_box"), 600, seps=(". ",)) or ""
    if src is not None and len(fact) < 30 and any(d.startswith("fact:") for d in dropped):
        raise InvalidOutput("fact_box states what the article doesn't: "
                            + "; ".join(d.split("[", 1)[-1].rstrip("]") for d in dropped if d.startswith("fact:"))[:120])
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
        t = _fit((p or {}).get("text"), 200) or ""  # too long to cut cleanly -> dropped below
        if len(t) >= 5:
            pointers.append({"type": p.get("type") if p.get("type") in POINTER_TYPES else "data_fact", "text": t})
    dedupe = lambda xs, n, lim: [x for x in dict.fromkeys(_fit(x, n) for x in (xs or []) if str(x).strip()) if x][:lim]
    sec_crime_re = re.compile(
        r"\b(rape|rapist|pocso|sexual(?:ly)? (?:assault|harass|abuse)|molest|minor(?:'s)? (?:rape|assault)|"
        r"dowry|domestic violence)\b", re.I
    )
    sec_valid_re = re.compile(
        r"\b(terror|militan|insurgen|infiltrat|j&k|jammu|kashmir|nagaland|manipur|assam|"
        r"ulfa|nscn|lashkar|jaish|hizb|isi\b|nia\b|uapa|border|line of control|loc\b|cross-border)\b", re.I
    )
    if node in {"terrorism_insurgency", "lwe", "border_management"}:
        combined = f"{why} {fact} {data.get('mains_question') or ''}"
        if sec_crime_re.search(combined) and not sec_valid_re.search(combined):
            raise InvalidOutput(f"{node} assigned to non-security crime story: {why[:80]}")

    GENERIC_DIMENSIONS = {
        'way forward', 'challenges', 'significance', 'role of technology', 'need for reforms',
        'way ahead', 'impact on economy', 'conclusion', 'challenges faced', 'importance',
        'major challenges', 'future outlook', 'key challenges', 'background', 'overview',
    }

    clean_dims = []
    for d in (data.get("mains_dimensions") or []):
        cleaned_d = _fit(d, 160)  # a dimension that can't be cut cleanly is dropped, never shown cut off
        if not cleaned_d:
            continue
        stripped = re.sub(
            r'^(?:way forward|challenges?|significance|role of technology|need for reforms?|way ahead)[:\-—]\s*',
            '', cleaned_d, flags=re.I
        ).strip()
        lower = stripped.lower().rstrip('.,;: ')
        if lower in GENERIC_DIMENSIONS or not stripped:
            continue
        clean_dims.append(stripped)

    final_dims = list(dict.fromkeys(clean_dims))[:4] if clean_dims else dedupe(data.get("mains_dimensions"), 160, 4)

    return {
        "exam_type": exam_type,
        "gs_paper": paper_of(subject),
        "subject": subject,
        "syllabus_node": node,
        "secondary": secondary[:2],
        "why_in_news": why,
        "fact_box": fact,
        "prelims_pointers": pointers[:5],
        "mains_question": _fit(data.get("mains_question"), 260, seps=("? ", ". ")) or None,
        "mains_dimensions": final_dims,
        "keywords": dedupe(data.get("keywords"), 40, 6),
        "dropped": dropped,  # what the grounding check removed (not stored; for logs and the eval)
    }


def article_prompt(title, body, category, published_at=None):
    pub = time.strftime("%d %B %Y", time.gmtime(published_at + 19800)).lstrip("0") if published_at else "n/a"
    return f"Title: {title}\nCategory: {category or 'n/a'}\nPublished: {pub}\nArticle:\n{(body or '')[:2500]}"


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
        india = india_link(title, body)
        return self._retry(lambda: self._call(GATE_SYSTEM, user, GATE_SCHEMA, 80),
                           lambda d: validate_gate(d, india))

    def notes(self, title, body, category, published_at=None):
        """Notes grounded in the article; a rejected answer is retried once, told what was wrong."""
        user = article_prompt(title, body, category, published_at)
        src, err = Source(title, body, published_at), None
        for _ in range(2):
            ask = user if err is None else (f"{user}\n\nYour previous answer was rejected: {err}. "
                                            "Write it again using only facts stated in the article.")
            try:
                return validate_notes(self._call(NOTES_SYSTEM, ask, NOTES_SCHEMA, 700), src)
            except (InvalidOutput, json.JSONDecodeError) as e:
                err = str(e)
        raise InvalidOutput(err)


def download_model(model_dir):
    from huggingface_hub import hf_hub_download
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, MODEL_FILENAME)
    if not os.path.exists(path):
        hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILENAME, local_dir=model_dir)
    return path
