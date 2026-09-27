"""Pure selection/prefilter logic (no DB I/O) so it can be unit-tested."""
import re

MAX_ATTEMPTS = 3

# Categories from the main classifier that are never UPSC material.
DROP_CATEGORIES = {"sports"}

# 'crime' is mostly noise, but internal-security / judiciary items matter.
CRIME_KEEP_RE = re.compile(
    r"\b(maoist|naxal|lwe|terror|terrorist|militant|insurgen|nia\b|uapa|blast|infiltrat|"
    r"cyber|money laundering|pmla|\bed\b|enforcement directorate|hawala|narco|drug traffick|"
    r"human traffick|supreme court|\bsc\b|high court|\bhc\b|cbi|lokpal|lokayukta|"
    r"custodial|encounter|border|bsf|crpf|surrender)",
    re.I,
)

# Obvious non-exam noise, applied to every category.
NOISE_RE = re.compile(
    r"\b(movie review|film review|box office|trailer|teaser|bigg boss|ott|web series|"
    r"bollywood|tollywood|kollywood|hollywood|actors?|actress(es)?|celebrit(y|ies)|"
    r"ipl|cricket|t20|odis?|"
    r"horoscope|zodiac|astrology|recipes?|fashion|lifestyle|destination-of-the-week|"
    r"april fools?|passes away|dies at \d+|obituary|"
    r"gold (rate|price)s? today|petrol price today|weather today)\b"
    r"|\| (movie|entertainment|sports|cricket)",
    re.I,
)


def prefilter(title: str, category: str | None):
    """Return a reason string if the article should be skipped without the LLM, else None."""
    t = title or ""
    cat = (category or "").lower()
    if not t.strip():
        return "empty_title"
    if cat in DROP_CATEGORIES:
        return f"category:{cat}"
    if cat == "crime" and not CRIME_KEEP_RE.search(t):
        return "category:crime"
    m = NOISE_RE.search(t)
    if m:
        return f"noise:{m.group(0).lower().strip()}"
    return None


def is_done(ledger_row) -> bool:
    """ledger_row: (verdict, attempts) or None."""
    if ledger_row is None:
        return False
    verdict, attempts = ledger_row
    return verdict != "failed" or int(attempts or 0) >= MAX_ATTEMPTS


def make_shards(ids, max_shards):
    if not ids:
        return []
    n = min(max_shards, len(ids))
    # round-robin so every shard gets a mix of new and old articles
    shards = [ids[i::n] for i in range(n)]
    return [",".join(map(str, s)) for s in shards if s]
