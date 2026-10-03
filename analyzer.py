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


# Topic signals: words a note must contain to carry a syllabus tag. Used for the "Also" (secondary) tags, which
# the model adds to ~97% of notes as filler (e.g. Putin on Ukraine "Also GS3 · Terrorism & insurgency (J&K,
# North-East)"), and for the primary tag of the few nodes the model over-uses. Matched on the note's own text
# (title, why-in-news, facts, mains question), not the whole article.
_SIGNAL_WORDS = {
    # GS1 history & culture
    "art_culture": r"art|arts|artist\w*|architect\w*|culture|cultural|dance|music\w*|paint\w*|sculpt\w*|festival\w*|literature|literary|theatre|craft\w*|classical",
    "ancient_medieval": r"ancient|medieval|mughal\w*|maurya\w*|gupta|chola\w*|vijayanagar\w*|sultanate|harappa\w*|vedic|buddhis\w*|jain\w*|inscription\w*|dynasty|maratha\w*|empire",
    "modern_freedom": r"freedom (?:struggle|fighter\w*|movement)|independence movement|british|colonial|gandhi|nehru|ambedkar|non-cooperation|quit india|dandi|1857|swadeshi|revolt",
    "post_independence": r"post-independence|integration of (?:princely )?states|linguistic states|partition|1947|reorgani[sz]ation",
    "world_history": r"world war|revolution|cold war|colonialism|imperialism|renaissance|industrial revolution",
    "heritage": r"heritage|unesco|gi tag|geographical indication|monument\w*|asi\b|archaeolog\w*|world heritage",
    # GS1 society
    "women": r"wom[ae]n|gender|girl\w*|female|maternal|dowry|sexual harassment|feminis\w*",
    "population": r"population|demograph\w*|migra\w*|fertility|census|ageing|aging|birth rate|super-aged",
    "urbanisation": r"urban\w*|cit(?:y|ies)|municipal\w*|slum\w*|smart cit\w*|metropolitan",
    "communalism_secularism": r"communal\w*|secular\w*|regionalism|religio\w*|riot\w*|sectarian",
    "diversity": r"sc/st|caste\w*|tribe\w*|tribal|adivasi\w*|scheduled castes?|scheduled tribes?|obc|dalit\w*|diversity|ethnic\w*",
    "globalisation_society": r"globali[sz]ation|global culture|consumeris\w*|westerni[sz]ation",
    # GS1 geography
    "physical": r"landform\w*|ocean\w*|glacier\w*|river\w*|mountain\w*|himalaya\w*|plateau\w*|monsoon|climate|current\w*",
    "phenomena": r"earthquake\w*|cyclone\w*|volcan\w*|tsunami\w*|landslide\w*|el ni[nñ]o|la ni[nñ]a|flood\w*|drought\w*|monsoon|heatwave\w*",
    "resources": r"mineral\w*|resource\w*|coal|iron ore|rare earth\w*|lithium|reserves|groundwater|forest\w*",
    "industry_location": r"industr\w*|plant|factor(?:y|ies)|cluster\w*|corridor\w*",
    # GS2 polity
    "constitution": r"constitution\w*|amendment\w*|basic structure|article \d+|schedule",
    "fundamental_rights": r"fundamental rights?|article (?:1[4-9]|2[0-9]|3[0-2])|directive principles?|dpsp|fundamental dut\w*|right to|privacy|free speech|freedom of",
    "parliament": r"parliament\w*|lok sabha|rajya sabha|legislat\w*|assembly|speaker|mla\w*|mp\b|mps\b|bill\b|session",
    "executive": r"president|prime minister|pm\b|governor\w*|chief minister|cm\b|cabinet|council of ministers|ordinance",
    "judiciary": r"court\w*|judge\w*|judicia\w*|justice|cji|bench|verdict\w*|ruling|petition\w*|tribunal\w*",
    "federalism": r"federal\w*|centre-state|centre and state\w*|inter-state|interstate|state government\w*|finance commission|gst council|governor",
    "elections": r"election\w*|electoral|voter\w*|ballot\w*|poll\w*|eci\b|election commission|by-?election\w*|evm\w*",
    "constitutional_bodies": r"cag\b|comptroller|upsc|finance commission|election commission|ncsc|ncst|ncbc|attorney general|constitutional bod\w*",
    "statutory_bodies": r"sebi|rbi|trai|cci|nhrc|ngt|regulator\w*|authority|commission|tribunal\w*|statutory",
    "local_government": r"panchayat\w*|gram sabha|municipal\w*|local bod(?:y|ies)|urban local|ward\w*|zila parishad|nagar",
    # GS2 governance
    "schemes": r"scheme\w*|yojana|mission|programme\w*|program\b|subsid\w*|welfare|initiative\w*|policy|policies|guidelines?",
    "transparency": r"rti\b|right to information|transparen\w*|accountab\w*|lokpal|lokayukta|corruption|whistle-?blower\w*|audit\w*|disclosure\w*",
    "egovernance": r"e-governance|digital|online|portal\w*|app\b|aadhaar|digili?ocker|dbt\b|citizen services?|upi|fastag",
    "civil_services": r"ias\b|ips\b|ifs\b|civil servi\w*|bureaucra\w*|officer\w*|cadre|secretar(?:y|ies)|collector\w*|deputation",
    "civil_society": r"ngo\w*|non-governmental|self-help group\w*|shg\w*|civil society|voluntary|volunteer\w*|cooperative\w*|activist\w*|trust\b|foundation",
    "legislation": r"bill\w*|act\b|acts\b|ordinance\w*|law\w*|legislat\w*|amendment\w*|rules\b|notif\w*",
    # GS2 social justice
    "vulnerable_sections": r"scheduled castes?|scheduled tribes?|sc/st|dalit\w*|minorit\w*|disab\w*|divyang\w*|elderly|senior citizens?|child\w*|transgender\w*|orphan\w*|vulnerable|marginali[sz]ed",
    "health": r"health\w*|hospital\w*|disease\w*|medic\w*|doctor\w*|patient\w*|vaccin\w*|drug\w*|pharma\w*|nutrition|leprosy|cancer|tb\b|tuberculosis|pandemic|epidemic|aiims",
    "education": r"educat\w*|school\w*|universit\w*|college\w*|student\w*|teacher\w*|ncert|ugc|nep\b|curriculum|textbook\w*|exam\w*",
    "poverty_hunger": r"povert\w*|hunger|nutrition|malnutrition|food security|ration\w*|pds\b|bpl\b|poor",
    "human_resources": r"skill\w*|training|workforce|labour|labor|employab\w*|jobs?\b|apprentice\w*",
    # GS2 IR
    "neighbourhood": r"pakistan|china|chinese|nepal|bhutan|bangladesh|sri lanka|myanmar|afghanistan|maldives|saarc|lac\b|loc\b",
    "bilateral": r"bilateral|foreign minister|external affairs|jaishankar|summit|ambassador|high commission\w*|embassy|visit\w*|talks|ties|partnership|treaty|mou\b|agreement",
    "groupings": r"quad|brics|sco\b|g20|g7|asean|bimstec|ibsa|saarc|groupings?|i2u2|imec",
    "institutions": r"\bun\b|united nations|wto|imf|world bank|who\b|unesco|unga|security council|unfccc|iaea|interpol|fatf|ilo\b",
    "global_impact_on_india": r"tariff\w*|sanction\w*|us\b|u\.s\.|united states|america\w*|european union|eu\b|oil price\w*|global|trump|federal reserve|fed\b|treasury|visa\w*|h-1b",
    "diaspora": r"diaspora|indian-origin|indians abroad|overseas indians?|nri\w*|migrant workers?|expatriate\w*|evacuat\w*",
    # GS3 economy
    "growth_indicators": r"gdp|growth|inflation|cpi|wpi|economy|economic|macro\w*|recession|output|iip\b",
    "monetary_banking": r"rbi|reserve bank|bank\w*|repo|interest rates?|monetary|credit|loan\w*|npa\w*|deposit\w*|upi|payments?|mdr\b|fintech|insurance",
    "fiscal_budget": r"budget\w*|fiscal|tax\w*|gst|revenue|deficit|expenditure|borrowing\w*|cess|excise|duty|duties",
    "external_trade": r"trade|export\w*|import\w*|fdi|foreign direct investment|fpi\w*|current account|tariff\w*|rupee|forex|fta\b|free trade",
    "industry_investment": r"industr\w*|manufactur\w*|invest\w*|msme\w*|startup\w*|companies|company|firm\w*|plant\w*|pli\b|semiconductor\w*|production",
    "employment_inclusion": r"employ\w*|jobs?\b|unemploy\w*|labour|labor|workers?|wages?|inclusive|plfs|mgnregs|epfo|gig",
    "infrastructure": r"infrastructure|rail\w*|trains?|road\w*|highway\w*|port\w*|airport\w*|bridge\w*|metro|power|electricity|energy|grid|pipeline\w*|logistic\w*|data cent(?:re|er)s?|telecom|toll",
    "capital_markets": r"sebi|stock\w*|shares?|equit(?:y|ies)|market\w*|ipo\w*|mutual funds?|bonds?|sensex|nifty|investors?|derivative\w*|fpi\w*",
    # GS3 agriculture
    "cropping_irrigation": r"crop\w*|irrigat\w*|kharif|rabi|sowing|harvest\w*|farm\w*|agricultur\w*|paddy|wheat|rice|seeds?|soil|canal\w*|water",
    "msp_procurement": r"msp|minimum support price|procure\w*|pds\b|food security|fci\b|buffer stock|ration",
    "agri_subsidies": r"subsid\w*|fertili[sz]er\w*|pm-kisan|kisan|farm support|crop insurance|loan waiver",
    "food_processing": r"food processing|cold chain|supply chain|warehous\w*|processing|value chain",
    "land_reforms": r"land reform\w*|land records?|tenancy|land ceiling|land acquisition|land titles?|patta",
    "allied": r"livestock|dairy|milk|fisher\w*|fish\b|poultry|animal husbandry|cattle|aquaculture|sericulture",
    # GS3 science & tech
    "space": r"space|isro|satellite\w*|orbit\w*|launch\w*|rocket\w*|nasa|astronaut\w*|lunar|moon|mars|gaganyaan|in-space",
    "defence_tech": r"defen[cs]e|missile\w*|aircraft|fighter\w*|jet\w*|tank\w*|drdo|hal\b|warship\w*|navy|naval|army|air force|iaf|weapon\w*|drone\w*",
    "biotech_health": r"biotech\w*|gene\w*|genom\w*|dna|vaccin\w*|virus\w*|viral|research\w*|scientist\w*|clinical|medic\w*|drug\w*|protein\w*|cell\w*|disease\w*",
    "it_ai": r"ai\b|artificial intelligence|digital\w*|cyber\w*|software|semiconductor\w*|chips?\b|data|internet|comput\w+|technolog\w+|tech\b|it\b|quantum|3d|apps?\b|online|robot\w*|algorithm\w*|telecom|5g|6g|deepfake\w*|startup\w*",
    "energy_nuclear": r"nuclear|reactors?|uranium|thorium|energy|power|electricity|solar|wind|hydrogen|renewables?|batter(?:y|ies)|grid|fuels?|coal|oil|gas|lng|biofuels?|ethanol|emissions?|carbon|climate|petroleum|crude",
    "ipr": r"patent\w*|copyright\w*|trademark\w*|intellectual property|ipr\b|gi tag|geographical indication",
    # GS3 environment
    "biodiversity": r"biodivers\w*|species|conservation|wildlife|forest\w*|ecosystem\w*|flora|fauna|endemic|endangered",
    "species_protected_areas": r"tiger\w*|elephant\w*|leopard\w*|vulture\w*|species|sanctuar(?:y|ies)|national park\w*|reserve\w*|wetland\w*|ramsar|protected area\w*",
    "pollution": r"pollut\w*|air quality|aqi|emission\w*|plastic\w*|waste|sewage|smog|stubble|firecracker\w*|contaminat\w*",
    "climate_change": r"climate|warming|carbon|emission\w*|net zero|unfccc|cop\d+|paris agreement|greenhouse|heatwave\w*|el ni[nñ]o|glacier\w*|ice loss",
    "env_laws_eia": r"environment(?:al)? (?:law|clearance|impact)|eia\b|forest (?:rights|conservation)|ngt|moefcc|environment ministry|wildlife protection act|clearance\w*",
    # GS3 disaster
    "natural_disasters": r"flood\w*|cyclone\w*|earthquake\w*|landslide\w*|drought\w*|disaster\w*|heatwave\w*|tsunami\w*|cloudburst\w*|relief|rescue",
    "dm_framework": r"ndma|sdma|ndrf|sdrf|disaster management|early warning|preparedness|relief fund",
    # GS3 security
    "lwe": r"maoist\w*|naxal\w*|left-wing extremis\w*|lwe\b|red corridor",
    "terrorism_insurgency": r"terror\w*|insurgen\w*|militan\w*|jammu|kashmir|j&k|manipur|naga\w*|ulfa|north-?east\w*|uapa|extremis\w*|jihad\w*|jaish|lashkar|infiltrat\w*",
    "border_management": r"border\w*|lac\b|loc\b|bsf|itbp|ssb\b|assam rifles|fenc\w*|infiltrat\w*|smuggl\w*|pla\b",
    "cyber": r"cyber\w*|hack\w*|malware|ransomware|phishing|data breach\w*|cert-in|online fraud|digital arrest",
    "money_laundering": r"money laundering|pmla|enforcement directorate|\bed\b|hawala|organi[sz]ed crime|smuggl\w*|drug\w*|narcotic\w*|gang\w*|fraud\w*",
    "security_forces": r"army|police|crpf|bsf|cisf|nsg|paramilitary|security forces?|armed forces|soldier\w*|jawan\w*|agnipath|nia\b",
    # GS4 ethics
    "public_admin_ethics": r"ethic\w*|integrity|conduct|accountab\w*|public servants?|officer\w*|administration",
    "probity_corruption": r"corrupt\w*|brib\w*|probity|integrity|lokpal|vigilance|misconduct",
    "tech_business_ethics": r"ethic\w*|privacy|data protection|ai\b|artificial intelligence|corporate governance|deepfake\w*|misinformation",
}

# places_in_news and case_study have no word list: always allowed.
NODE_SIGNALS = {n: re.compile(r"(?<![\w-])(?:" + w + r")(?![\w])", re.I) for n, w in _SIGNAL_WORDS.items()}
PRIMARY_CHECK = {"energy_nuclear", "it_ai", "schemes", "civil_services", "transparency", "civil_society"}
TRANSPORT_RE = re.compile(r"\b(?:rail\w*|trains?|bridges?|highways?|roads?|expressways?|ports?|airports?|metro|"
                          r"tunnels?|vande bharat)\b", re.I)


def node_supported(node, text):
    pat = NODE_SIGNALS.get(node)
    return bool(pat is None or pat.search(text or ""))


def supported_secondary(secondary, text):
    """(kept, dropped) secondary tags: kept only if the note talks about that topic."""
    kept, dropped = [], []
    for x in secondary or []:
        (kept if node_supported(x.get("node"), text) else dropped).append(x)
    return kept, dropped


def checked_node(node, secondary, text):
    """(node, secondary): a primary tag from PRIMARY_CHECK that the note doesn't talk about moves to Infrastructure
    for transport news, else to its first supported secondary tag (not Places in news); otherwise it stays."""
    secondary, _ = supported_secondary(secondary, text)
    if node not in PRIMARY_CHECK or node_supported(node, text):
        return node, secondary
    if TRANSPORT_RE.search(text or "") and "infrastructure" in NODE_OWNER:
        return "infrastructure", [x for x in secondary if x.get("node") != "infrastructure"]
    real = [x for x in secondary if x.get("node") in NODE_SIGNALS]  # not the always-allowed places/case-study tags
    if real:
        return real[0]["node"], [x for x in secondary if x is not real[0]]
    return node, secondary


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
    note_text = " ".join([src.text.split("\n", 1)[0] if src is not None else "", why, fact,
                          str(data.get("mains_question") or "")])
    for x in supported_secondary(secondary, note_text)[1]:
        dropped.append(f"secondary: {x['node']} [note is not about it]")
    node, secondary = checked_node(node, secondary, note_text)
    subject = NODE_OWNER[node]
    secondary = [x for x in secondary if x["subject"] != subject]
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
