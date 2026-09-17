#!/usr/bin/env python3
"""Discover a site's URLs with the self-hosted Firecrawl stack (cheap recon).

Usage:
  fc_map.py URL [--limit 25] [--search TERM] [--json]

Prints one URL per line (with title when the API supplies one). --limit is
capped at 100 by the client layer. Exit codes as in fc_client.run_main.
"""

import argparse
import json
import sys

import fc_client as fc


def main():
    ap = argparse.ArgumentParser(
        description="Map a site's URL structure via self-hosted Firecrawl (/v1/map).")
    ap.add_argument("url")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--search", default=None, help="ranked filter term")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.limit < 1:
        sys.exit("error: --limit must be >= 1")
    links = fc.map_urls(args.url, limit=args.limit, search=args.search)

    if args.as_json:
        print(json.dumps(links, indent=2, ensure_ascii=False))
        return
    if not links:
        print("(no URLs discovered — robots rules or empty site?)")
        return
    for item in links:
        if isinstance(item, dict):
            title = f"  # {item.get('title')}" if item.get("title") else ""
            print(f"{item.get('url', '')}{title}")
        else:
            print(item)


if __name__ == "__main__":
    fc.run_main(main)
