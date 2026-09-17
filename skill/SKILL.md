---
name: firecrawl
description: Read, map, and crawl the web with a self-hosted Firecrawl stack (loopback http://127.0.0.1:3002) and turn SearXNG queries into research digests. Use when asked to scrape/read a URL, discover a site's structure, crawl a small site, or turn a search query into readable page content without cloud APIs. Triggers: scrape, crawl, read this URL, site structure, site map, web research, research query pipeline.
---

# Firecrawl local research stack

Self-hosted Firecrawl (loopback API) fused with **your** self-hosted SearXNG
instance. Python-stdlib-only scripts — nothing to install. If anything
misbehaves, run the healthcheck first.

Scripts live in this repo's `scripts/` — invoke via bash from the repo root
(or substitute your clone path for `$FH`).

## Configuration (one-time)
`SEARXNG_URL` is required — point it at your SearXNG's JSON endpoint via the
env, `cp .env.example .env`, or `~/.config/firecrawl-harness/config`
(KEY=VALUE lines; env wins). Unconfigured scripts fail fast with a hint.

## Health check (run first when in doubt)
```bash
python3 $FH/scripts/healthcheck.py [--quick]
```

## Research fusion — search then read (preferred for open-ended questions)
```bash
python3 $FH/scripts/fc_research.py "<query>" [--limit 5] [--scrape 3]
```
SearXNG answers the query; the top results are batch-scraped by Firecrawl into
clean markdown and printed as a digest (large pages get file references under
`.cache/`). Use `--no-scrape` for links only.

## Read one known URL
```bash
python3 $FH/scripts/fc_scrape.py <URL> [--only-main-content] [--json]
```

## Discover a site's URLs (cheap recon — prefer before crawling)
```bash
python3 $FH/scripts/fc_map.py <URL> [--limit 25] [--search TERM]
```

## Crawl a small site (polite; hard caps: pages ≤ 50, depth ≤ 3)
```bash
python3 $FH/scripts/fc_crawl.py <URL> [--limit 10] [--max-depth 2]
```
Writes `NNN-slug.md` pages + `index.md` into `.cache/crawl/...`; prints the
manifest. Keep total pages ≤ 100 across one session — real memory pressure
under heavy crawls has been observed in production.

## Notes
- Raw keyword search without scraping is one curl away:
  `curl "$SEARXNG_URL?q=topic&format=json"`.
- `FIRECRAWL_API_URL` defaults to `http://127.0.0.1:3002`; a non-loopback
  value additionally needs `FC_ALLOW_REMOTE_API=1`.
- Exit codes: 2 SearXNG down · 3 Firecrawl down · 4 timeout · 5 job failed.
- MCP tools registered via `@deepseek-ai/dsh-mcp-client` with
  `npx -y firecrawl-mcp@3.24.0` appear (verified handshake) as
  `mcp__firecrawl__firecrawl_scrape`, `mcp__firecrawl__firecrawl_map`,
  `mcp__firecrawl__firecrawl_crawl` (+ `firecrawl_check_crawl_status`) —
  note the doubled prefix, the npm server already names tools `firecrawl_*`.
  `firecrawl_search` targets `/v1/search` (needs Google keys) and
  cloud-only tools (`firecrawl_monitor_*`, `firecrawl_research_*`, `agent`,
  `interact`, `parse`, `developer_search`, `extract`) will error locally —
  for search use `fc_research.py`. If the 27-tool schema overhead costs too
  many tokens per request, remove the `mcp-firecrawl` hunk from your DSH
  profile's `cordis.patch.yml` (skill scripts work without it).
