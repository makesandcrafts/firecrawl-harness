# Operations runbook

## Prerequisites
- Self-hosted Firecrawl compose stack up (api/redis/rabbitmq/postgres/playwright)
  — `docker ps | grep firecrawl`; API default `http://127.0.0.1:3002`.
- A SearXNG with JSON API enabled (`format=json` reachable without auth) —
  point `SEARXNG_URL` at it (env, repo `.env`, or
  `~/.config/firecrawl-harness/config`). The repo ships only placeholders;
  unconfigured runs fail fast with a setup hint (exit 1).
- `python3` ≥ 3.10 (stdlib only — nothing to pip-install).
- Optional (MCP surface): node + npx on PATH; internet reachability to the npm
  registry once per pinned version (then served from `.npm-cache`).

## Install (from scratch)
1. `git clone <this repo> && cd firecrawl-harness`
2. Configure: `cp .env.example .env`, set `SEARXNG_URL` to your instance
   (or use `~/.config/firecrawl-harness/config`; env vars win over files).
3. Skill: `ln -s "$PWD/skill" ~/.agents/skills/firecrawl`
4. MCP (optional): append the insert-form hunk from `README.md` §DSH wiring to
   your profile patch (e.g. `~/.dsh/profiles/web/cordis.patch.yml`). With
   `patchReload: live` this takes effect on save; verify composition:
   `dsh --profile web --dump-config | grep mcp-firecrawl`
5. Gate: `python3 scripts/healthcheck.py` → expect four `PASS` rows.
6. Accept: `./tests/smoke.sh` → expect `ALL SMOKE TESTS PASSED`.

## Day-2 commands
| Need | Command |
|---|---|
| anything odd? | `python3 scripts/healthcheck.py` (add `--quick` for connectivity-only) |
| after reboots | healthcheck + `docker ps` |
| regression | `./tests/smoke.sh` |
| research | `python3 scripts/fc_research.py "<q>" [--limit 5] [--scrape 3] [--no-scrape]` |
| read a URL | `python3 scripts/fc_scrape.py <url> [--only-main-content] [--json]` |
| recon | `python3 scripts/fc_map.py <url> [--limit N] [--search term]` |
| collect | `python3 scripts/fc_crawl.py <url> [--limit 10] [--max-depth 2] [--include-path g]` |

## Failure → cause → fix
| Exit | Symptom (stderr hint) | Likely cause | Fix |
|---|---|---|---|
| 2 | `SearXNG down` | instance down / JSON api disabled / bad `SEARXNG_URL` | check the SearXNG container/unit; `curl '<SEARXNG_URL>?q=x&format=json'` |
| 3 | `Firecrawl down … docker ps` | api container stopped/unhealthy | `docker restart` the stack; then healthcheck |
| 4 | `did not complete within Ns` | crawl too big / slow origin / playwright saturation | lower `--limit`/`--max-depth`; raise `--poll-timeout` deliberately |
| 5 | `reported failure: …` | bad URL, blocked by robots, queue reject, validation | read the excerpt; robots blocks are final — do not bypass |
| — | digest shows `note: batch scrape unavailable … falling back` | batch route rejected the body (build drift) | informational; fallback is automatic — re-probe `POST /v1/batch/scrape {"urls":[…]}` |

## Lifecycle notes
- **No restart for patch changes** (`patchReload: live`) — but a session's tool
  list snapshots at boot, so brand-new sessions are where MCP tool additions
  show up.
- The MCP stdio child lives under the harness service cgroup
  (`dsh → npm exec firecrawl-mcp@3.24.0 → sh -c firecrawl-mcp`); if it dies the
  bridge reconnects with backoff (500 ms → 30 s ceiling, budget then removal of
  that server's tools until reload).
- Version pin lives in the patch hunk; upgrades = edit the pin, save, new
  sessions get the new server (cold install into `.npm-cache` if uncached).

## Known limitations / watch items
- 27 MCP tool schemas cost per-request tokens; if it stings, delete the hunk —
  the skill scripts are fully independent of the MCP layer.
- Cloud-only MCP tools error locally **by design**; search is SearXNG's job.
- `/v1/extract` unwrapped (needs an LLM service on the compose; candidate:
  local OpenAI-compat endpoint).
- `/v1/batch/scrape` body is deliberately `{"urls":[…]}` only (this build
  rejects `scrapeOptions` there).

## Rollback (full, no residue)
1. Remove the `mcp-firecrawl` hunk (hot-applies; tools disappear for new sessions).
2. `rm ~/.agents/skills/firecrawl` (symlink only).
3. `rm -rf firecrawl-harness` — nothing else was mutated; upstream containers
   and their volumes untouched throughout.

## Verification log — 2026-09-17 (initial build, all by the agent author)
- `tests/smoke.sh` 6/6 twice (after fixes to batch body + fallback path).
- Live research digest on "DGX Spark" (5 shown / 3 scraped) — real-world pass.
- `dsh --profile web --dump-config`: row present, stderr clean.
- `patch: entry "mcp-firecrawl" not found` bug found via that dump; root-caused
  in compiled `cordis-plugin-include` (patch grammar: insert vs retarget);
  fixed to id-less insert form; **no restart**, live hot-apply.
- Bridge proven with a direct JSON-RPC drive (initialize → tools/list → 27
  tools) before harness wiring, and post-deploy by a real tool call
  (`mcp__firecrawl__firecrawl_scrape` example.com → HTTP 200 markdown).
- Continuous: stdio child steady-state under the service; journal clean since
  activation.
