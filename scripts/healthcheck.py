#!/usr/bin/env python3
"""Health gate for the local research stack (Firecrawl + SearXNG).

Usage:
  healthcheck.py [--quick]

Quick mode checks reachability only; full mode additionally runs a real
Firecrawl scrape canary (example.com) and a real SearXNG query canary.
Exit 0 when everything passes, 1 otherwise. Run this first whenever
anything in the pipeline behaves oddly; it also belongs in post-reboot
verification.
"""

import argparse
import sys
import time

import fc_client as fc

CANARY_SCRAPE = "https://example.com"
CANARY_NEEDLE = "Example Domain"


def _run_check(rows, name, fn):
    start = time.monotonic()
    try:
        detail = fn() or "ok"
        rows.append((name, "PASS", detail, int((time.monotonic() - start) * 1000)))
    except Exception as e:  # noqa: BLE001 — a health probe reports, never crashes
        rows.append((name, "FAIL", str(e), int((time.monotonic() - start) * 1000)))


def check_firecrawl_root():
    resp = fc.http_json(fc.firecrawl_base() + "/", timeout=5.0)
    if not isinstance(resp, dict):
        raise fc.FirecrawlDown(f"unexpected root response: {str(resp)[:120]}")
    return f"banner ok ({str(resp.get('message'))[:40]!r})"


def check_firecrawl_scrape_canary():
    data = fc.scrape(CANARY_SCRAPE, ("markdown",), timeout=45.0)
    md = data.get("markdown") or ""
    if CANARY_NEEDLE not in md:
        raise fc.FirecrawlJobFailed(
            f"canary scrape returned unexpected markdown: {md[:120]!r}")
    status = (data.get("metadata") or {}).get("statusCode", "?")
    return f"canary markdown ok (HTTP {status}, {len(md)} chars)"


def check_searxng_reachable():
    resp = fc.http_json(
        fc.searxng_endpoint() + "?" + "q=health&format=json", timeout=10.0)
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise fc.SearxngDown(f"no results list: {str(resp)[:120]}")
    return f"json api ok ({len(resp['results'])} results for 'health')"


def check_searxng_canary():
    results = fc.searxng_results("health check canary", limit=1)
    return f"canary ok ({len(results)} result(s))"


def main():
    ap = argparse.ArgumentParser(description="Health gate for Firecrawl + SearXNG.")
    ap.add_argument("--quick", action="store_true",
                    help="connectivity only (skip scrape/search canaries)")
    args = ap.parse_args()

    rows = []
    _run_check(rows, "firecrawl-root", check_firecrawl_root)
    _run_check(rows, "searxng-json", check_searxng_reachable)
    if not args.quick:
        _run_check(rows, "firecrawl-scrape-canary", check_firecrawl_scrape_canary)
        _run_check(rows, "searxng-search-canary", check_searxng_canary)

    width = max(len(name) for name, *_ in rows)
    print("=== firecrawl-harness healthcheck ===")
    failed = False
    for name, status, detail, ms in rows:
        failed |= status != "PASS"
        print(f"{name.ljust(width)}  {status}  {ms:>5} ms  {detail}")
    print("all green" if not failed else "FAILURES PRESENT — see hints above")
    if failed:
        print("hint: docker ps | grep -E 'firecrawl|mcp' ; "
              "journalctl --user -u dsh --since -10min", file=sys.stderr)
    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except fc.HarnessError as e:  # e.g. loopback guard misfires
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)
