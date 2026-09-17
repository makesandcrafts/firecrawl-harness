# Changelog

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
