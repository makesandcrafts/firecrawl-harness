#!/usr/bin/env python3
"""Small polite crawls with the self-hosted Firecrawl stack (async job + poll).

Usage:
  fc_crawl.py URL [--limit 10] [--max-depth 2] [--include-path GLOB]
              [--exclude-path GLOB] [--poll-timeout 600] [--out-dir DIR]
              [--only-main-content]

Guardrails (hard, do not loosen without asking the operator):
  --limit  capped at 50 (default 10) — the API node has been measured at
           ~3 GiB under crawl load in production; crawls stay small & sequential
  depth    capped at 3
Keep total pages across one working session at <= 100 (session guidance).

Writes pages to OUT_DIR (default .cache/crawl/<slug>-<ts>/) as NNN-slug.md
plus an index.md manifest; prints the manifest to stdout.
"""

import argparse
import os
import sys
import time
import urllib.parse

import fc_client as fc

LIMIT_CAP = 50
DEPTH_CAP = 3


def main():
    ap = argparse.ArgumentParser(
        description="Crawl a site via self-hosted Firecrawl (/v1/crawl, async).")
    ap.add_argument("url")
    ap.add_argument("--limit", type=int, default=10, help=f"max pages (cap {LIMIT_CAP})")
    ap.add_argument("--max-depth", type=int, default=2, help=f"max depth (cap {DEPTH_CAP})")
    ap.add_argument("--include-path", default=None)
    ap.add_argument("--exclude-path", default=None)
    ap.add_argument("--poll-timeout", type=float, default=600.0)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--only-main-content", action="store_true")
    args = ap.parse_args()

    limit = args.limit
    depth = args.max_depth
    if limit > LIMIT_CAP:
        print(f"warn: --limit {limit} clamped to {LIMIT_CAP}", file=sys.stderr)
        limit = LIMIT_CAP
    if depth > DEPTH_CAP:
        print(f"warn: --max-depth {depth} clamped to {DEPTH_CAP}", file=sys.stderr)
        depth = DEPTH_CAP
    if limit < 1 or depth < 0:
        sys.exit("error: --limit must be >= 1 and --max-depth >= 0")

    payload = {
        "url": args.url,
        "limit": limit,
        "maxDepth": depth,
        "scrapeOptions": {"formats": ["markdown"],
                          "onlyMainContent": bool(args.only_main_content)},
    }
    if args.include_path:
        payload["includePaths"] = args.include_path
    if args.exclude_path:
        payload["excludePaths"] = args.exclude_path

    job_id = fc.submit_crawl(payload)
    resp = fc.poll_job("/v1/crawl/{id}", job_id, budget=args.poll_timeout,
                       label=f"crawl of {args.url}")
    pages = resp.get("data") or []

    parsed = urllib.parse.urlparse(args.url)
    slug_root = fc.slugify(f"{parsed.netloc}{parsed.path}")
    out_dir = args.out_dir or os.path.join(
        fc.cache_dir("crawl"), f"{slug_root}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)

    manifest = []
    for idx, page in enumerate(pages, 1):
        md = page.get("markdown") or ""
        meta = page.get("metadata") or {}
        page_url = meta.get("url") or meta.get("sourceURL") or f"{args.url}#{idx}"
        fname = f"{idx:03d}-{fc.slugify(page_url)}.md"
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as fh:
            fh.write(md)
        manifest.append((fname, page_url, meta.get("title") or "",
                         meta.get("statusCode", "?")))

    index_path = os.path.join(out_dir, "index.md")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Crawl of {args.url}\n\n")
        fh.write(f"pages: {len(pages)} (limit {limit}, maxDepth {depth})\n\n")
        for fname, page_url, title, status in manifest:
            fh.write(f"- [{title or page_url}]({fname}) — {page_url} (HTTP {status})\n")

    if not pages:
        print(f"(no pages captured — robots rules, seed not crawlable, or excluded?) "
              f"job {job_id}")
        return
    print(f"# Crawl of {args.url} — {len(pages)} pages")
    print(f"manifest: {index_path}")
    for fname, page_url, title, status in manifest:
        print(f"- {os.path.join(out_dir, fname)} — {page_url} "
              f"(HTTP {status}){f' — {title}' if title else ''}")


if __name__ == "__main__":
    fc.run_main(main)
