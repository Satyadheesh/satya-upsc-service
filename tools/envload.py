"""Tiny .env loader (no dependency). Walks up from cwd and this file's dir,
loading KEY=VALUE lines without overriding variables already set."""
import os
from pathlib import Path


def load_env() -> None:
    seen = set()
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for d in [start, *start.parents]:
            f = d / ".env"
            if f in seen or not f.is_file():
                continue
            seen.add(f)
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require(*names: str) -> list:
    load_env()
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)} (set them or add to .env)")
    return [os.environ[n] for n in names]
