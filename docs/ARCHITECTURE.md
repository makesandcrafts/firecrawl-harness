# Architecture

How the pieces fit: a local agent (DeepSeek Harness) gets first-class web
*reading* (self-hosted Firecrawl) and *searching* (SearXNG) with no cloud API
keys and no fork of anything.

```
 agent (DSH session)
   ├─ skill layer ── ~/.agents/skills/firecrawl → repo skill/SKILL.md
   │      └─ bash → scripts/*.py ──┬─ SearXNG  https://…/search?format=json
   │                               └─ Firecrawl http://127.0.0.1:3002/v1/*
   └─ MCP layer ─── @deepseek-ai/dsh-mcp-client (plugin row `mcp-firecrawl`)
          └─ stdio → npx -y firecrawl-mcp@3.24.0 → same Firecrawl API
             tools surface as mcp__firecrawl__firecrawl_<name>
```

## Why this shape

Self-hosted Firecrawl's own `/v1/search` needs Google/Serper keys and errors
(500) without them — it is the one capability that does not survive
self-hosting. SearXNG fills exactly that gap locally. Everything else
(scrape/map/crawl) self-hosts cleanly, so the design keeps upstream containers
untouched and puts all adaptation in a repo of stdlib-only Python plus one DSH
profile-patch hunk. Two surfaces serve the same stack: scripts (zero
token-schema cost, deterministic) and MCP tools (native-feeling, 27 schemas of
per-request token cost). They are independent; either can be removed alone.

## Component inventory

| Piece | Path | Notes |
|---|---|---|
| Shared client | `scripts/fc_client.py` | stdlib `urllib` only; transport policy, envelope validation, job polling, env config, loopback guard |
| Research fusion | `scripts/fc_research.py` | SearXNG → filter → batch scrape → digest (the `/v1/search` replacement) |
| Single-page read | `scripts/fc_scrape.py` | `POST /v1/scrape`; >200 KB or `--out` → file + preview |
| Recon | `scripts/fc_map.py` | `POST /v1/map`, cap 100 links |
| Collection | `scripts/fc_crawl.py` | async `POST /v1/crawl` + poll; caps pages ≤ 50, depth ≤ 3 |
| Gate | `scripts/healthcheck.py` | canaries: root banner, real scrape of example.com, real SearXNG query |
| Skill | `skill/SKILL.md` | DSH skill discovery is directory-based under `~/.agents/skills` |
| MCP row | `~/.dsh/profiles/web/cordis.patch.yml` | insert-list form (see below) |
| Filter list | `assets/blacklist.txt` | domain suffix filter for digests |

## Transport policy (fc_client)

- One retry, 2 s backoff, **only** on connection errors, socket timeouts, and
  5xx; 4xx is final. A retried POST can duplicate an idempotent-by-URL scrape
  job server-side — accepted trade.
- Envelope: `{"success":true,…}`; anything else is `FirecrawlJobFailed` with a
  300-char excerpt.
- Async jobs (`/v1/crawl`, `/v1/batch/scrape`) return `{success,id,url}`;
  poll `GET …/:id` until `status=="completed"`, terminal-bad set
  `{failed,error,cancelled,canceled,timed_out,timedout}`; unknown interim
  statuses keep polling until the deadline. Verified page payload:
  `data:[{markdown,metadata:{url,sourceURL,title,statusCode,…}}]`.
- Exit codes: 2 SearXNG down · 3 Firecrawl down · 4 timeout · 5 job/validation
  failure · 1 other. Degradation is data, not silence: a failed page within a
  digest degrades to snippet-only with a visible note.

## Firecrawl API facts pinned by probe (stack build `2343d7b`)

- `/v1/scrape|crawl|map|extract` exist and are auth-free (`USE_DB_AUTHENTICATION=false`).
- `/v1/batch/scrape` accepts **only** `{"urls":[…]}` — `scrapeOptions` is
  rejected there as unrecognized (while `/v1/crawl` *does* accept it). Code
  keeps the batch body minimal; on any batch failure the research script falls
  back to a sequential `/v1/scrape` loop.
- `/v1/extract` is unwrapped: this compose configures no LLM service for it.
  Possible future twist: point it at a local OpenAI-compat endpoint (e.g. a
  DGX Spark serving box) — untested at time of writing.

## Search-fusion pipeline (fc_research)

1. SearXNG `format=json` fetch, 2× depth of what is needed.
2. Filters: http(s)-only, domain-suffix blacklist, ≤ 2 results per host,
   order-preserving dedupe.
3. Top `--scrape` (cap 5) batch-scraped (180 s budget); failures → sequential;
   per-URL failures → snippet-only.
4. Digest: title, URL, snippet, then markdown inline or file-referenced
   (> 60 KB → artifacts dir + preview head).

## DSH MCP wiring — the non-obvious parts (lessons, earned live)

- The profile composes: shipped bundles → `cordis.patch.yml` → `--patch`
  overlays. Patch entries keyed by `id` only **retarget existing rows**
  (missing → warning `patch: entry … not found`). A new plugin row must arrive
  as an **id-less insert list**:
  ```yaml
  - insert:
    - id: mcp-firecrawl
      name: '@deepseek-ai/dsh-mcp-client'
      config: {serverName, transport, command, args, env, …}
  ```
- `patchReload: live` (web profile): patch edits hot-apply — no service
  restart was ever required, for breaking or fixing.
- Bridge naming: public tool names are `mcp__<serverName>__<rawName>`; the npm
  server's raw names are already `firecrawl_*`, hence
  `mcp__firecrawl__firecrawl_scrape` etc. 27 tools; cloud-only ones
  (`firecrawl_search`, `monitor_*`, `research_*`, `agent`, `interact`, `parse`,
  `extract`, `developer_search`) error against this stack **by design**.
- `failOnStartupError: false` — a dead npx/registry can never brick boot.
- Host `~/.npm` contained root-owned files (legacy npm bug); the row injects
  `npm_config_cache=<repo>/.npm-cache` so the stdio child cold-installs
  reliably. A one-time `sudo chown -R 1000:1001 ~/.npm` retires the need.

## Security posture

- Firecrawl base URL defaults to loopback; non-loopback requires an explicit
  opt-in env (`FC_ALLOW_REMOTE_API=1`). No API keys anywhere. No telemetry
  beyond your own SearXNG's engine policy. Robots handling delegated to
  Firecrawl defaults; blocks surface as visible errors, never bypassed.
  Crawl caps are hard ceilings, not defaults to raise casually — the API node
  was observed at ~3 GiB under crawl load in production history.
