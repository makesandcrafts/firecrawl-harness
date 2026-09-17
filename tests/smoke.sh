#!/usr/bin/env bash
# Acceptance smoke for the firecrawl-harness skill surface. Exit 0 = all pass.
set -euo pipefail
here="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
cd "$here/.."
PY="${PYTHON:-python3}"
S=scripts
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "[1/6] healthcheck (full canaries)"
"$PY" "$S/healthcheck.py" || fail "healthcheck reported failures"

echo "[2/6] scrape example.com returns expected content"
"$PY" "$S/fc_scrape.py" https://example.com | grep -q "Example Domain" || fail "scrape"
echo "      ok"

echo "[3/6] map python.org yields URLs"
out="$("$PY" "$S/fc_map.py" https://www.python.org --limit 5)"
echo "$out" | grep -q '^http' || fail "map produced no urls: ${out:0:120}"
echo "      ok"

echo "[4/6] crawl example.com (guardrail + manifest path)"
"$PY" "$S/fc_crawl.py" https://example.com --limit 3 --max-depth 1 \
  | grep -q "manifest:" || fail "crawl manifest missing"
echo "      ok"

echo "[5/6] research fusion digest (--scrape 1)"
"$PY" "$S/fc_research.py" "python anyio release notes" --limit 3 --scrape 1 \
  | grep -q "^URL: http" || fail "research digest lacks result URLs"
echo "      ok"

echo "[6/6] degradation: unreachable SearXNG must exit 2"
rc=0
SEARXNG_URL="http://127.0.0.1:9/search" \
  "$PY" "$S/fc_research.py" "anything" --scrape 0 2>/dev/null || rc=$?
test "$rc" -eq 2 || fail "expected exit 2 on dead SearXNG, got $rc"
echo "      ok (exit 2 as designed)"

echo "ALL SMOKE TESTS PASSED"
