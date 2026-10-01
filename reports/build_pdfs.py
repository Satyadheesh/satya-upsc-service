"""Builds the UPSC report PDFs (daily / weekly / monthly, English + Hindi) for satyadheesh.in.

1. Ask the site which reports should exist and their content hash
   (GET /api/upsc/reports/manifest; ?all=1 with --all).
2. For each publishable report whose hash differs from the stored PDF's hash, print the site's
   print layout (/upsc/reports/print/...) with Chromium - real browser text shaping, so Hindi
   matras and conjuncts come out right - and store the PDF in the UPSC DB
   (upsc_reports + upsc_report_chunks, ~400 KB per chunk row).

Unchanged reports cost nothing; a PDF is rebuilt only when its notes change.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

import libsql_client
from playwright.sync_api import sync_playwright

SITE = os.environ.get("SITE_URL", "https://satyadheesh.in").rstrip("/")
CHUNK = 400 * 1024
FOOTER = ('<div style="width:100%;font-size:7.5px;color:#888;font-family:sans-serif;'
          'text-align:center;">satyadheesh.in/upsc &middot; <span class="pageNumber"></span> / '
          '<span class="totalPages"></span></div>')


_clients = []


def db():
    url = os.environ["SATYA_UPSC_DB_URL"].replace("libsql://", "https://")
    c = libsql_client.create_client_sync(url=url, auth_token=os.environ["SATYA_UPSC_DB_TOKEN"])
    _clients.append(c)
    return c


def ensure_tables(c):
    c.batch([
        "CREATE TABLE IF NOT EXISTS upsc_reports (key TEXT PRIMARY KEY, kind TEXT NOT NULL, period TEXT NOT NULL, "
        "lang TEXT NOT NULL, hash TEXT NOT NULL, items INTEGER NOT NULL, bytes INTEGER NOT NULL, "
        "chunks INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS upsc_report_chunks (key TEXT NOT NULL, n INTEGER NOT NULL, data BLOB NOT NULL, "
        "PRIMARY KEY (key, n))",
    ])


def fetch_json(url, attempts=3):
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "satya-report-builder"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  fetch failed ({i + 1}/{attempts}): {e}")
            time.sleep(15 * (i + 1))
    raise SystemExit(f"::error::could not fetch {url}")


def store(c, rep, pdf):
    key = rep["file_key"]
    parts = [pdf[i:i + CHUNK] for i in range(0, len(pdf), CHUNK)]
    stmts = [libsql_client.Statement("DELETE FROM upsc_report_chunks WHERE key = ?", [key])]
    stmts += [libsql_client.Statement("INSERT INTO upsc_report_chunks (key, n, data) VALUES (?, ?, ?)", [key, n, p])
              for n, p in enumerate(parts)]
    stmts.append(libsql_client.Statement(
        "INSERT OR REPLACE INTO upsc_reports (key, kind, period, lang, hash, items, bytes, chunks, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [key, rep["kind"], rep["period"], rep["lang"], rep["hash"], rep["items"], len(pdf), len(parts), int(time.time())]))
    c.batch(stmts)  # one transaction: readers never see half a PDF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="consider every period, not just recent ones")
    ap.add_argument("--force", action="store_true", help="rebuild even if the hash is unchanged")
    ap.add_argument("--only", default="", help="only file keys containing this text, e.g. 'monthly:'")
    args = ap.parse_args()

    manifest = fetch_json(f"{SITE}/api/upsc/reports/manifest{'?all=1' if args.all else ''}")
    reports = [r for r in manifest["reports"] if args.only in r["file_key"]]
    c = db()
    ensure_tables(c)
    stored = {row[0]: row[1] for row in c.execute("SELECT key, hash FROM upsc_reports").rows}

    todo = [r for r in reports if r["publishable"] and (args.force or stored.get(r["file_key"]) != r["hash"])]
    skipped_hi = [r["file_key"] for r in reports if not r["publishable"]]
    print(f"{len(reports)} reports in manifest, {len(todo)} to build"
          + (f", {len(skipped_hi)} Hindi not ready yet (<80% translated)" if skipped_hi else ""))
    if not todo:
        return

    built, failed = 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="en-IN")
        page = ctx.new_page()
        for rep in todo:
            url = f"{SITE}{rep['print_path']}"
            t0 = time.time()
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=180_000)
                if not resp or resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status if resp else '?'}")
                page.evaluate("document.fonts.ready")
                page.wait_for_timeout(300)
                pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                               display_header_footer=True, header_template="<div></div>", footer_template=FOOTER)
                store(c, rep, pdf)
                built += 1
                print(f"  built {rep['file_key']}: {rep['items']} notes, {len(pdf) // 1024} KB, {time.time() - t0:.1f}s")
            except Exception as e:
                failed += 1
                print(f"::warning::{rep['file_key']} failed: {e}")
        browser.close()
    print(f"done: {built} built, {failed} failed")
    if failed and not built:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        # libsql_client's sync client runs a background thread: close it or the process never exits
        for c in _clients:
            try:
                c.close()
            except Exception:
                pass
