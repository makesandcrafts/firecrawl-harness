#!/usr/bin/env python3
"""SearXNG ⇄ Firecrawl research fusion: search, then read the winners.

This is the local replacement for Firecrawl's /v1/search (which needs Google
keys and is not usable on the self-hosted stack): SearXNG answers the query,
Firecrawl turns the top results into clean markdown.

Usage:
  fc_research.py QUERY [--limit 5] [--scrape 3] [--no-scrape]
                    [--blacklist FILE] [--out-dir DIR]

Pipeline:
  1. SearXNG format=json results (fetched 2x deeper than needed).
  2. Filter: http(s) only, domain blacklist (assets/blacklist.txt by default),
     at most 2 results per host.
  3. Firecrawl batch scrape of the top --scrape (cap 5) URLs via
     /v1/batch/scrape (async job + poll, 180 s budget); any batch failure
     falls back to sequential /v1/scrape. Per-URL failures degrade to
     snippet-only with a visible note — they never abort the digest.
  4. Digest to stdout: per result — title, URL, SearXNG snippet, and the
     scraped markdown inline (or file-referenced when > 60 KB).

Exit codes: 2 SearXNG down (hard), 3/4/5 Firecrawl-side problems, 1 other.
"""

import argparse
import os
import sys
import time
import urllib.parse

import fc_client as fc

SCRAPE_CAP = 5
LIMIT_CAP = 10
BATCH_BUDGET = 180.0
INLINE_CAP_BYTES = 60 * 1024
PREVIEW_LINES = 20
_DEFAULT_BLACKLIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "blacklist.txt")


def load_blacklist(path):
    domains = set()
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    domains.add(line)
    return domains


def pick_results(results, limit, blacklist):
    seen_hosts = {}
    picked = []
    for r in results:
        url = r.get("url") or ""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        host = (parsed.hostname or "").lower()
        if not host:
            continue
        if any(host == d or host.endswith("." + d) for d in blacklist):
            continue
        if seen_hosts.get(host, 0) >= 2:
            continue
        seen_hosts[host] = seen_hosts.get(host, 0) + 1
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


def scrape_targets(urls):
    """Return {url: (markdown|None, error|None)} for the requested URLs."""
    outcomes = {u: (None, "not scraped") for u in urls}
    if not urls:
        return outcomes
    by_source = {}
    try:
        job = fc.submit_batch_scrape(urls)
        resp = fc.poll_job("/v1/batch/scrape/{id}", job, budget=BATCH_BUDGET,
                           label="batch scrape")
        for item in resp.get("data") or []:
            meta = item.get("metadata") or {}
            md = item.get("markdown") or ""
            for key in (meta.get("url"), meta.get("sourceURL")):
                if key:
                    by_source[key] = md
        for u in urls:
            if u in by_source:
                outcomes[u] = (by_source[u], None)
    except fc.HarnessError as batch_err:
        print(f"note: batch scrape unavailable ({batch_err}); falling back to "
              f"sequential scrapes", file=sys.stderr)
        for u in urls:
            if u in by_source:
                outcomes[u] = (by_source[u], None)
                continue
            try:
                data = fc.scrape(u, ("markdown",), timeout=45.0)
                outcomes[u] = (data.get("markdown") or "", None)
            except fc.HarnessError as e:
                outcomes[u] = (None, str(e))
    # Any url the batch job silently omitted still gets a sequential try.
    for u in urls:
        md, err = outcomes[u]
        if md is None and err == "not scraped":
            try:
                data = fc.scrape(u, ("markdown",), timeout=45.0)
                outcomes[u] = (data.get("markdown") or "", None)
            except fc.HarnessError as e:
                outcomes[u] = (None, str(e))
    return outcomes


def emit_markdown(out_dir, url, md):
    if len(md.encode("utf-8")) > INLINE_CAP_BYTES:
        fname = f"{fc.slugify(urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path)}-" \
                f"{time.strftime('%H%M%S')}.md"
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"[large page — full markdown in {path}; first {PREVIEW_LINES} lines]")
        for line in md.splitlines()[:PREVIEW_LINES]:
            print(line)
    else:
        print(md.strip())


def main():
    ap = argparse.ArgumentParser(
        description="SearXNG search fused with Firecrawl scraping → research digest.")
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=5, help=f"results to show (cap {LIMIT_CAP})")
    ap.add_argument("--scrape", type=int, default=3,
                    help=f"top N results to read via Firecrawl (cap {SCRAPE_CAP}, 0 to skip)")
    ap.add_argument("--no-scrape", action="store_true", help="links only")
    ap.add_argument("--blacklist", default=_DEFAULT_BLACKLIST)
    ap.add_argument("--out-dir", default=None,
                    help="where large-page markdown files land (default .cache/research/<ts>/)")
    args = ap.parse_args()

    limit = max(1, min(args.limit, LIMIT_CAP))
    n_scrape = 0 if args.no_scrape else max(0, min(args.scrape, SCRAPE_CAP))

    results = fc.searxng_results(args.query, limit=min(limit * 2, 25))
    picked = pick_results(results, limit, load_blacklist(args.blacklist))
    if not picked:
        print(f"(no usable SearXNG results for {args.query!r}"
              f"{'; check blacklist/limits' if results else ''})")
        return

    out_dir = args.out_dir or fc.cache_dir(
        os.path.join("research", time.strftime("%Y%m%d-%H%M%S")))
    targets = [r["url"] for r in picked[:n_scrape]]
    outcomes = scrape_targets(targets)

    print(f"# Research digest: {args.query}")
    print(f"source: SearXNG ({fc.searxng_endpoint()}) → Firecrawl "
          f"({fc.firecrawl_base()}), {len(picked)} results shown, "
          f"{len(targets)} scraped\n")
    for idx, r in enumerate(picked, 1):
        url = r["url"]
        print(f"## [{idx}] {r.get('title') or '(untitled)'}")
        print(f"URL: {url}")
        snippet = (r.get("content") or "").strip().replace("\n", " ")
        if snippet:
            print(f"SearXNG: {snippet[:280]}")
        if url in outcomes:
            md, err = outcomes[url]
            if err:
                print(f"⚠ scrape failed: {err} — snippet only")
            elif md:
                print()
                emit_markdown(out_dir, url, md)
            else:
                print("(empty page content)")
        print()

    print(f"[digest complete — artifacts dir: {out_dir}]")


if __name__ == "__main__":
    fc.run_main(main)
