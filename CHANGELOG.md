# Changelog

## v1.0.2 — 2026-09-17
Agent-safety hardening of the MCP guidance (docs only).

- After an in-the-wild misfire (`unknown tool "firecrawl_search"` from an
  agent guessing bare tool names), `skill/SKILL.md` and the README now state
  the callable contract explicitly: only
  `mcp__firecrawl__firecrawl_scrape|map|crawl|check_crawl_status` (full
  registered name, doubled prefix), never the bare `firecrawl_*` names, never
  the self-hosted-dead set (`firecrawl_search`, `monitor_*`, `research_*`,
  `agent`, `interact`, `parse`, `developer_search`, `extract`) — search is
  always `scripts/fc_research.py`.
- Documented the session tool-list snapshot semantics: sessions opened before
  the MCP row went live have no MCP tools; scripts need none.

## v1.0.1 — 2026-09-17
Privacy scrub — the public artifact carries no personal hosting endpoints.

- `scripts/fc_client.py`: no baked-in SearXNG default; `SEARXNG_URL` is
  required config resolved from env → repo `.env` → 
  `~/.config/firecrawl-harness/config`; missing config fails fast (exit 1)
  with a setup hint. `FIRECRAWL_API_URL` / `FC_ALLOW_REMOTE_API` resolve
  through the same chain.
- Added `.env.example` (placeholder endpoints only); `.gitignore` covers `.env`.
- README/SKILL/docs generalized: no personal instance strings, no
  homelab-specific phrasing.
- History rewritten (squashed to a single clean initial commit) to expunge
  personal endpoints that lived in early development blobs.

## v1.0.0 — 2026-09-17
Initial release: SearXNG ⇄ self-hosted Firecrawl ⇄ DeepSeek Harness local
web-research integration.

- Skill surface: `fc_research` (search→scrape fusion digest), `fc_scrape`,
  `fc_map`, `fc_crawl` (hard caps: pages ≤ 50, depth ≤ 3), `healthcheck`
  canary gate; stdlib-only Python client with retry/exit-code contracts.
- MCP surface: `@deepseek-ai/dsh-mcp-client` insert-form row running
  `npx -y firecrawl-mcp@3.24.0` against the loopback API; 27 tools incl.
  scrape/map/crawl; `failOnStartupError: false`; repo-local `npm_config_cache`
  workaround for the host `~/.npm` root-owned-files bug.
- Acceptance: `tests/smoke.sh` (6 checks incl. batch→sequential fallback and
  dead-SearXNG degradation exit code) green against stack build `2343d7b`.
- Docs: `docs/ARCHITECTURE.md` (incl. the DSH patch-grammar lesson: new rows
  require id-less `insert:` lists), `docs/OPERATIONS.md` (runbook + dated
  verification log).
- Credits: designed and implemented autonomously by **qwen3.8-flash-next** on
  a single NVIDIA DGX Spark via DeepSeek Harness.
