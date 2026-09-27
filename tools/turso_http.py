"""Minimal Turso HTTP (v2 pipeline) client for admin scripts."""
import json
import urllib.request

from envload import require


def execute(statements, url_var="SATYA_UPSC_DB_URL", token_var="SATYA_UPSC_DB_TOKEN"):
    """statements: list of SQL strings or (sql, args) tuples. Returns list of result dicts."""
    db_url, token = require(url_var, token_var)
    db_url = db_url.replace("libsql://", "https://").rstrip("/")
    reqs = []
    for s in statements:
        sql, args = (s, []) if isinstance(s, str) else s
        reqs.append({"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}})
    reqs.append({"type": "close"})
    body = json.dumps({"requests": reqs}).encode()
    req = urllib.request.Request(
        f"{db_url}/v2/pipeline", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        results = json.loads(r.read())["results"][:-1]
    for s, res in zip(statements, results):
        if res.get("type") == "error":
            raise RuntimeError(f"{res['error']} :: {s if isinstance(s, str) else s[0]}")
    return [res["response"]["result"] for res in results]


def rows(result):
    return [[c.get("value") for c in row] for row in result["rows"]]


def _arg(a):
    if a is None:
        return {"type": "null"}
    if isinstance(a, bool):
        return {"type": "integer", "value": str(int(a))}
    if isinstance(a, int):
        return {"type": "integer", "value": str(a)}
    if isinstance(a, float):
        return {"type": "float", "value": a}
    return {"type": "text", "value": str(a)}
