"""GS4 (Ethics) check for a written note: a separate, strict model call plus code checks.

A note gets the GS4 tag only if ALL agree:
  1. the GS4 call says yes and names an issue type;
  2. its quote is a sentence found word for word in the article;
  3. the quote itself contains words of that issue type;
  4. a second, independent call that sees only the quote and the issue also says yes.
Any doubt -> no tag. Nothing here changes the note itself.
"""
import re

ISSUES = {
    "probity": "corruption, bribery, misuse of office, conflict of interest, nepotism or misconduct by a public "
               "official, judge, legislator, police officer or regulator, with an inquiry, finding, order or official action",
    "institutional_integrity": "the neutrality, independence, integrity or accountability of a public institution "
                               "questioned or defended by a court, an official body or the institution's own head",
    "civil_service_values": "a public servant's duty, honesty, impartiality, whistleblowing or code of conduct, "
                            "or the values public service should rest on",
    "tech_business_ethics": "a company's or technology developer's conduct that raises consent, privacy, deception, "
                            "bias, manipulation, or safety-versus-profit questions, or a government or court acting on such conduct",
    "bioethics": "a court or authority deciding a medical, reproductive, end-of-life or research-ethics question",
}

ISSUE_WORDS = {
    "probity": r"corrupt\w*|brib\w*|graft|kickbacks?|embezzl\w*|misuse\w*|misappropriat\w*|conflicts? of interest|nepotis\w*|"
               r"misconduct|disproportionate assets|irregularit\w*|fraud\w*|vigilance|lokpal|lokayukta|quid pro quo|"
               r"favouritism|favoritism|abuse of (?:power|office|position)",
    "institutional_integrity": r"neutral\w*|independen\w*|integrity|accountab\w*|impartial\w*|credibilit\w*|bias\w*|"
                               r"introspect\w*|politici[sz]\w*|captur\w*|autonomy|transparen\w*",
    "civil_service_values": r"dut(?:y|ies)|conduct|whistle-?blow\w*|integrity|values?|honest\w*|impartial\w*|"
                            r"public service|ethic\w*|probity|accountab\w*",
    "tech_business_ethics": r"consent|privacy|decept\w*|deceiv\w*|mislead\w*|bias\w*|safety|misuse\w*|harm\w*|"
                            r"manipulat\w*|surveil\w*|deepfakes?|morph\w*|ethic\w*|responsib\w*|rogue|conceal\w*|lie\w*|lying",
    "bioethics": r"ethic\w*|consent|life|reproduct\w*|ivf|surrog\w*|euthanas\w*|organs?|embryo\w*|clinical trials?|"
                 r"dignity|age limit",
}
ISSUE_RE = {k: re.compile(r"(?<![\w-])(?:" + v + r")(?![\w])", re.I) for k, v in ISSUE_WORDS.items()}

GS4_SYSTEM = """You decide whether a news story is material for UPSC GS4 (Ethics, Integrity and Aptitude).

Answer gs4 = true ONLY if the article itself is about one of these (issue):
""" + "\n".join(f"- {k}: {v}" for k, v in ISSUES.items()) + """

Answer gs4 = false for:
- technology news about what a model, product or research can do, with no conduct question;
- laws, rules, regulation or policy news with no question about anyone's conduct;
- individual crimes, arrests, FIRs, chargesheets, bail or trials;
- a politician or party alleging wrongdoing by rivals, or protests and campaigns;
- economy, diplomacy, disasters, science results, sports, culture;
- stories where ethics is only a general implication you could add to any story.

If gs4 is true:
- quote: copy ONE sentence from the article, word for word, that shows the ethical issue;
- angle: one line naming the ethical issue and whose conduct it concerns (max 25 words);
- question: one GS4-style question on the underlying dilemma (max 35 words), no person's name.
If gs4 is false, set issue to "none" and leave quote, angle and question empty.
When unsure, answer false."""

GS4_SCHEMA = {
    "type": "object",
    "properties": {"gs4": {"type": "boolean"},
                   "issue": {"type": "string", "enum": list(ISSUES) + ["none"]},
                   "quote": {"type": "string", "maxLength": 400},
                   "angle": {"type": "string", "maxLength": 220},
                   "question": {"type": "string", "maxLength": 260}},
    "required": ["gs4", "issue", "quote", "angle", "question"],
}

VERIFY_SYSTEM = """You check one claim. Given a sentence from a news article and an ethics issue type with its
definition, answer yes only if the sentence ITSELF shows a specific actor's conduct raising that ethical issue.
A sentence that only reports a capability, a policy, a statistic, a crime or an allegation by a political rival is no.
When unsure, answer no. Reply JSON only."""

VERIFY_SCHEMA = {"type": "object", "properties": {"yes": {"type": "boolean"}}, "required": ["yes"]}


def _norm(s):
    s = (s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", re.sub(r"[^\w%'\" .,-]", " ", s)).strip(" .")


def check(an, title, body, note):
    """-> dict(tag: bool, issue, quote, angle, question, why) where `why` says which check decided."""
    text = (body or "")[:2500]
    user = (f"Title: {title}\nArticle:\n{text}\n\nOur note: {note.get('why_in_news', '')} "
            f"{note.get('fact_box', '')}")
    out = {"tag": False, "issue": "none", "quote": "", "angle": "", "question": "", "why": ""}
    try:
        r = an._call(GS4_SYSTEM, user, GS4_SCHEMA, 260)
    except Exception as e:
        out["why"] = f"error: {str(e)[:120]}"
        return out
    issue, quote = r.get("issue"), (r.get("quote") or "").strip()
    out.update(issue=issue or "none", quote=quote, angle=(r.get("angle") or "").strip(),
               question=(r.get("question") or "").strip())
    if not r.get("gs4") or issue not in ISSUES:
        out["why"] = "model: no"
        return out
    if len(quote.split()) < 6 or _norm(quote) not in _norm(f"{title}. {text}"):
        out["why"] = "quote not found word for word in the article"
        return out
    if not ISSUE_RE[issue].search(quote):
        out["why"] = f"quote has no {issue} words"
        return out
    if not out["angle"] or not out["question"]:
        out["why"] = "no angle/question"
        return out
    try:
        v = an._call(VERIFY_SYSTEM, f"Issue: {issue} = {ISSUES[issue]}\nSentence: {quote}", VERIFY_SCHEMA, 20)
    except Exception as e:
        out["why"] = f"verify error: {str(e)[:120]}"
        return out
    if not v.get("yes"):
        out["why"] = "second check: no"
        return out
    out.update(tag=True, why="all checks passed")
    return out
