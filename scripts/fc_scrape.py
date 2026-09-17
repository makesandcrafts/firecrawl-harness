#!/usr/bin/env python3
"""Scrape one URL with the self-hosted Firecrawl stack; print markdown.

Usage:
  fc_scrape.py URL [--formats markdown,links,html] [--only-main-content]
               [--wait-for-selector CSS] [--wait-for-ms N] [--timeout S]
               [--json] [--out FILE]

Large outputs (>200 KB) or --out write a file under .cache/scrape/ and print
a preview instead of flooding stdout. Exit codes: 2 SearXNG down, 3 Firecrawl
down, 4 timeout, 5 job/validation failure, 1 other.
"""

import argparse
import json
import os
import sys
import time

import fc_client as fc

LARGE_BYTES = 200 * 1024
PREVIEW_LINES = 30
_ALLOWED_FORMATS = ("markdown", "links", "html")


def main():
    ap = argparse.ArgumentParser(
        description="Scrape a URL via self-hosted Firecrawl (/v1/scrape).")
    ap.add_argument("url")
    ap.add_argument("--formats", default="markdown",
                    help="comma list of markdown,links,html (default: markdown)")
    ap.add_argument("--only-main-content", action="store_true")
    ap.add_argument("--wait-for-selector", default=None,
                    help="CSS selector to wait for before capture (waitForSelector)")
    ap.add_argument("--wait-for-ms", type=int, default=None,
                    help="extra settle wait in ms after load (waitFor)")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="print the raw data object as JSON")
    ap.add_argument("--out", default=None, help="write markdown to this file")
    args = ap.parse_args()

    if args.url.startswith(("file:", "ftp:", "data:")):
        sys.exit("error: only http(s) URLs are supported")
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    invalid = [f for f in formats if f not in _ALLOWED_FORMATS]
    if invalid or not formats:
        sys.exit(f"error: unsupported --formats {invalid}; allowed: {_ALLOWED_FORMATS}")

    data = fc.scrape(args.url, formats,
                     only_main_content=args.only_main_content,
                     wait_for_selector=args.wait_for_selector,
                     wait_for_ms=args.wait_for_ms,
                     timeout=args.timeout)

    if args.as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    meta = data.get("metadata") or {}
    md = data.get("markdown") or ""
    print(f"# {meta.get('title') or args.url}")
    print(f"URL: {meta.get('url') or args.url} (HTTP {meta.get('statusCode', '?')})")
    if meta.get("sourceURL") and meta["sourceURL"] != meta.get("url"):
        print(f"Redirected from: {meta['sourceURL']}")
    print()

    if args.out or len(md.encode("utf-8")) > LARGE_BYTES:
        out = args.out
        if not out:
            host = fc.slugify(meta.get("url") or args.url)
            out = os.path.join(fc.cache_dir("scrape"),
                              f"{host}-{time.strftime('%Y%m%d-%H%M%S')}.md")
            os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"[markdown written to {out} — {len(md)} chars; showing first "
              f"{PREVIEW_LINES} lines]")
        for line in md.splitlines()[:PREVIEW_LINES]:
            print(line)
    else:
        print(md)


if __name__ == "__main__":
    fc.run_main(main)
