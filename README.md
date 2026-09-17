# firecrawl-harness

Local web-research integration for DeepSeek Harness (DSH): the self-hosted
**Firecrawl** stack on your machine (`http://127.0.0.1:3002`, auth-free) fused
with **your** self-hosted **SearXNG** instance (configured via `SEARXNG_URL` —
the public repo ships placeholders only, never anyone's personal endpoint).
No cloud API keys, no fork of Firecrawl — glue lives entirely here.

> **About this build.** This entire integration — architecture, code, tests,
> and deployment wiring — was conceived and executed autonomously by
> **qwen3.8-flash-next** served on a **single NVIDIA DGX Spark** (GB10 Grace
> Blackwell, 128 GB unified memory), driving [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
> end to end: from plan-mode exploration through acceptance testing to live
> MCP-tool validation. One small inference node, one agent, zero cloud APIs.

- Purpose: give agent sessions first-class local tools to *search* (SearXNG),
  *read* (Firecrawl scrape), *recon* (map), and *collect* (crawl) the web;
  `/v1/search` on self-hosted Firecrawl needs Google keys, so SearXNG covers
  search at this layer instead.
- Status: active (created 2026-09-17, verified against stack build `2343d7b`).
- Provenance: adapts `https://github.com/firecrawl/firecrawl` (upstream
  container kept as-is; `firecrawl-mcp` official server pin `3.24.0`).

## Important files

| Path | Role |
|---|---|
| `scripts/fc_client.py` | Shared stdlib client: transport, retries, envelopes, job polling, env config |
| `scripts/fc_research.py` | SearXNG → Firecrawl research fusion digest (the marquee tool) |
| `scripts/fc_scrape.py` | One-URL scrape → markdown (`/v1/scrape`) |
| `scripts/fc_map.py` | URL discovery (`/v1/map`) |
| `scripts/fc_crawl.py` | Small polite async crawls (`/v1/crawl`), caps: pages ≤ 50, depth ≤ 3 |
| `scripts/healthcheck.py` | PASS/FAIL gate incl. scrape+search canaries; run after reboots/incidents |
| `assets/blacklist.txt` | Domain filter for research digests (suffix match) |
| `skill/SKILL.md` | DSH skill manifest; symlinked as `~/.agents/skills/firecrawl` |
| `tests/smoke.sh` | Codified acceptance run (6 checks incl. degradation exit code) |
| `docs/ARCHITECTURE.md` | How it fits together; transport/API facts pinned by probe; DSH patch-grammar lesson |
| `docs/OPERATIONS.md` | Install, runbook, failure→fix table, rollback, dated verification log |
| `.cache/` | Generated digests/crawl output (gitignored) |

## Common commands

```bash
python3 scripts/healthcheck.py                # all green?
./tests/smoke.sh                              # acceptance suite
python3 scripts/fc_research.py "some topic" --scrape 3
python3 scripts/fc_scrape.py https://example.com --only-main-content
python3 scripts/fc_map.py https://docs.example.org --limit 30
python3 scripts/fc_crawl.py https://docs.example.org/guide --limit 10 --max-depth 2
```

Environment/config: `SEARXNG_URL` is **required** — your own SearXNG's JSON
endpoint (`<url>?q=x&format=json` must return a results list). Resolution
order: env → repo `.env` (`cp .env.example .env`) →
`~/.config/firecrawl-harness/config` (KEY=VALUE lines; env wins). Unconfigured
scripts fail fast with a clear hint. `FIRECRAWL_API_URL` (default
`http://127.0.0.1:3002`; guarded to loopback unless `FC_ALLOW_REMOTE_API=1`).
Exit codes: `2` SearXNG down, `3` Firecrawl down, `4` timeout, `5` job/validation failure.

## DSH wiring

1. **Skill** — `ln -s ~/projects/firecrawl-harness/skill ~/.agents/skills/firecrawl`
   (already in place). New sessions list `firecrawl` in the skill catalog.
2. **Native MCP tools** — one **id-less `insert:` list** in
   `~/.dsh/profiles/web/cordis.patch.yml` adds the `@deepseek-ai/dsh-mcp-client`
   row (a plain `- id: … name: … config:` in a patch only *retargets existing*
   rows and warns `patch: entry … not found`; new rows must be inserted —
   learned live from the compiled `cordis-plugin-include` and confirmed by
   `dsh --profile web --dump-config`). Runs the official MCP server over
   stdio: `npx -y firecrawl-mcp@3.24.0` with `FIRECRAWL_API_URL` set; tools
   appear as `mcp__firecrawl__firecrawl_<tool>` (the npm server's raw tool
   names are already `firecrawl_*`, so the bridge's namespacing doubles the
   prefix — verified live: 27 tools registered, but the callable set in
   practice is `mcp__firecrawl__firecrawl_scrape|map|crawl|check_crawl_status`;
   bare names like `firecrawl_search` are not registered in any session
   (`unknown tool`), and the tools behind `firecrawl_search` (needs Google
   keys) plus the cloud-only `monitor_*`/`research_*`/`agent`/`interact`/
   `parse`/`developer_search`/`extract` error against this stack by design —
   search goes through `scripts/fc_research.py`/SearXNG, never those tools).
   `failOnStartupError: false` keeps DSH bootable if npx/registry is
   unavailable. Remove that single hunk to roll back — the profile's
   `patchReload: live` hot-applies patch edits, so the original (broken)
   patch was ignored live and this corrected row took effect with **no service
   restart**. The host `~/.npm` cache contains root-owned files (pre-existing
   npm bug fallout), so the entry injects `npm_config_cache=…/.npm-cache` — a
   repo-local scratch cache proven to cold-install the pin (a `chown -R
   1000:1001 ~/.npm` fixes the host cache globally if ever desired).

## Related links

- Firecrawl repo / docs: https://github.com/firecrawl/firecrawl · https://docs.firecrawl.dev
- Firecrawl MCP server: `firecrawl-mcp` on npm (pinned 3.24.0)
- Stack check: `docker ps | grep firecrawl` (api/redis/rabbitmq/postgres/playwright)
- Sibling skill (raw search): `~/.agents/skills/local-web-search`

## Notes

- Verified response envelope for async jobs: `{success, status, completed,
  total, data:[{markdown, metadata}]}`; unknown interim statuses keep polling.
- `/v1/extract` deliberately unwrapped: needs an LLM service the compose
  doesn't configure (possible future twist: point it at the DGX Spark
  OpenAI-compat endpoint).
- One retry (2 s backoff) on connection errors/timeouts/5xx only; 4xx never
  retried. A retried POST can duplicate a scrape job server-side — accepted.
- Respect robots: delegated to Firecrawl defaults; blocked pages surface as
  visible scrape errors, never bypassed.

## Next actions

- Done 2026-09-17: skill symlinked + smoke suite green; `mcp-firecrawl` row
  composed (dump-config clean) and serving live via `patchReload: live`
  hot-apply — stdio child tree `dsh → npm exec firecrawl-mcp` steady, MCP
  handshake previously verified directly (27 tools). No service restart was
  ever actually required.
- Watch: per-request token weight of the 27-tool schema; trim by removing the
  hunk if it stings (skill scripts are independent of it).
- Optional: `chown -R 1000:1001 ~/.npm` to retire the cache workaround;
  a deployment note in your own ops-notes location.
