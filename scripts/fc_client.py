"""Shared helpers for the firecrawl-harness scripts.

Stdlib only (urllib) — no third-party dependencies. Talks to your self-hosted
Firecrawl stack (loopback by default) and your self-hosted SearXNG instance.

Configuration — no personal endpoints are baked in; you supply your own:
  SEARXNG_URL          REQUIRED. e.g. https://searxng.example.org/search
                       Resolved from env, then the repo ./.env (see
                       .env.example), then ~/.config/firecrawl-harness/config
                       (KEY=VALUE lines; env wins over files).
  FIRECRAWL_API_URL    optional; defaults to http://127.0.0.1:3002
  FC_ALLOW_REMOTE_API  set to "1" to permit a non-loopback FIRECRAWL_API_URL
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Cortex-Agent/1.0"
_DEFAULT_FIRECRAWL = "http://127.0.0.1:3002"
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "0.0.0.0")
_USER_CONFIG = os.path.join(os.path.expanduser("~"), ".config",
                            "firecrawl-harness", "config")


class HarnessError(RuntimeError):
    """Base for all script errors; subclasses map to stable exit codes."""


class FirecrawlDown(HarnessError):
    HINT = "check the stack: docker ps | grep firecrawl ; then scripts/healthcheck.py"


class SearxngDown(HarnessError):
    HINT = ("set SEARXNG_URL via env, repo .env, or ~/.config/firecrawl-harness/config; "
            "'<url>?q=x&format=json' must return a results list")


class ServiceTimeout(HarnessError):
    pass


class FirecrawlJobFailed(HarnessError):
    pass


EXIT_FOR = {FirecrawlDown: 3, SearxngDown: 2, ServiceTimeout: 4, FirecrawlJobFailed: 5}


def run_main(main):
    """Run main(); map HarnessError subclasses to exit codes (see EXIT_FOR)."""
    try:
        main()
    except HarnessError as e:
        hint = getattr(e, "HINT", "")
        print(f"error: {e}" + (f"\nhint: {hint}" if hint else ""), file=sys.stderr)
        raise SystemExit(EXIT_FOR.get(type(e), 1))


def _read_config_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.split("#", 1)[0].strip().strip('"').strip("'")
                if key and key not in values:
                    values[key] = value
    except FileNotFoundError:
        return {}
    return values


def _config_value(key):
    """Env wins, then repo-local .env, then ~/.config/firecrawl-harness/config."""
    value = os.environ.get(key)
    if value:
        return value.strip()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (os.path.join(root, ".env"), _USER_CONFIG):
        value = _read_config_file(candidate).get(key)
        if value:
            return value
    return None


def firecrawl_base() -> str:
    base = (_config_value("FIRECRAWL_API_URL") or _DEFAULT_FIRECRAWL).rstrip("/")
    if not base.startswith("http"):
        base = "http://" + base
    host = urllib.parse.urlparse(base).hostname or ""
    if host not in _LOOPBACK_HOSTS and _config_value("FC_ALLOW_REMOTE_API") != "1":
        raise HarnessError(
            f"refusing to use non-loopback Firecrawl API {base!r}; "
            "set FC_ALLOW_REMOTE_API=1 only if you mean it")
    return base


def searxng_endpoint() -> str:
    value = _config_value("SEARXNG_URL")
    if not value:
        raise HarnessError(
            "SEARXNG_URL is not configured — set the env var, or add "
            "'SEARXNG_URL=https://your-searxng.example.org/search' to the repo .env "
            "(see .env.example) or to ~/.config/firecrawl-harness/config")
    return value


def http_json(url, *, payload=None, timeout=30.0, retries=1):
    """GET (payload None) or POST JSON; returns the parsed dict.

    One retry with 2 s backoff on connection errors, timeouts, and 5xx
    responses; 4xx surfaces immediately and is never retried. (The retry may
    submit a duplicate idempotent-by-URL scrape job server-side — accepted.)
    """
    attempts = 1 + max(0, retries)
    last = None
    for attempt in range(attempts):
        try:
            data = None
            headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
            method = "GET"
            if payload is not None:
                data = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
                method = "POST"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            try:
                return json.loads(body)
            except ValueError as e:
                raise HarnessError(f"non-JSON response from {url}: {body[:200]!r}") from None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if e.code >= 500 and attempt + 1 < attempts:
                last = HarnessError(f"HTTP {e.code} from {url}: {body!r}")
                time.sleep(2.0)
                continue
            raise HarnessError(f"HTTP {e.code} from {url}: {body!r}") from None
        except OSError as e:  # URLError and socket timeouts are OSError subclasses
            reason = getattr(e, "reason", None) or e
            last = HarnessError(f"connection failure to {url}: {reason}")
            if attempt + 1 < attempts:
                time.sleep(2.0)
                continue
            raise last from None
    raise last or HarnessError(f"request to {url} failed")


def _fc_request(path, *, payload=None, timeout=30.0):
    resp = http_json(firecrawl_base() + path, payload=payload, timeout=timeout)
    if not isinstance(resp, dict) or resp.get("success") is not True:
        detail = str(resp.get("error") or resp)[:300] if isinstance(resp, dict) else str(resp)[:300]
        raise FirecrawlJobFailed(f"firecrawl {path} reported failure: {detail}")
    return resp


def scrape(url, formats=("markdown",), *, only_main_content=False,
           wait_for_selector=None, wait_for_ms=None, extra=None, timeout=45.0):
    """POST /v1/scrape; returns the response 'data' dict (markdown, metadata…)."""
    payload = {"url": url, "formats": list(formats)}
    if only_main_content:
        payload["onlyMainContent"] = True
    if wait_for_selector:
        payload["waitForSelector"] = {"cssSelector": wait_for_selector}
    if wait_for_ms:
        payload["waitFor"] = int(wait_for_ms)
    if extra:
        payload.update(extra)
    resp = _fc_request("/v1/scrape", payload=payload, timeout=timeout)
    data = resp.get("data")
    return data if isinstance(data, dict) else {}


def map_urls(url, *, limit=25, search=None, timeout=20.0):
    """POST /v1/map; returns a list of URL strings (or dicts with url/title)."""
    payload = {"url": url, "limit": min(int(limit), 100)}
    if search:
        payload["search"] = search
    resp = _fc_request("/v1/map", payload=payload, timeout=timeout)
    data = resp.get("data")
    links = (data.get("links") if isinstance(data, dict) else None) or resp.get("links")
    return links if isinstance(links, list) else []


_TERMINAL_BAD = {"failed", "error", "cancelled", "canceled", "timed_out", "timedout"}


def _submit(path, payload, *, timeout=20.0):
    resp = _fc_request(path, payload=payload, timeout=timeout)
    job_id = resp.get("id")
    if not job_id:
        raise FirecrawlJobFailed(f"no job id in {path} response: {str(resp)[:200]}")
    return job_id


def submit_crawl(payload, *, timeout=20.0):
    return _submit("/v1/crawl", payload, timeout=timeout)


def submit_batch_scrape(urls, *, timeout=20.0):
    # This build (2343d7b) accepts only {"urls": [...]} on the batch route —
    # scrapeOptions is rejected there as an unrecognized key (verified live;
    # /v1/crawl *does* accept scrapeOptions). Keep the body minimal.
    return _submit("/v1/batch/scrape", {"urls": list(urls)}, timeout=timeout)


def poll_job(path_template, job_id, *, budget=600.0, interval=2.0, label="job"):
    """Poll GET path_template.format(id=job_id) until status is terminal.

    Verified response shape (local stack, build 2343d7b):
      {"success": true, "status": "started|scraping|completed|failed",
       "completed": n, "total": n, "data": [{"markdown": …, "metadata": {...}}]}
    Unknown interim statuses keep polling until the deadline.
    """
    deadline = time.monotonic() + budget
    while True:
        resp = _fc_request(path_template.format(id=job_id), timeout=20.0)
        status = str(resp.get("status") or "")
        if status == "completed":
            return resp
        if status in _TERMINAL_BAD:
            detail = str(resp.get("error") or resp)[:300]
            raise FirecrawlJobFailed(f"{label} {job_id} ended as {status!r}: {detail}")
        if time.monotonic() >= deadline:
            raise ServiceTimeout(f"{label} {job_id} did not complete within {budget:.0f} s")
        time.sleep(interval)


def searxng_results(query, *, limit=10, timeout=10.0):
    """Query SearXNG with format=json; returns up to `limit` result dicts.

    Raises SearxngDown on any transport/format failure (exit code 2). An empty
    results list is a legitimate outcome and is returned as-is.
    """
    url = searxng_endpoint() + "?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "language": "en"})
    try:
        resp = http_json(url, timeout=timeout)
    except HarnessError as e:
        raise SearxngDown(f"{e}") from None
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise SearxngDown(f"SearXNG returned no results list: {str(resp)[:200]}")
    return resp["results"][:limit]


def slugify(text, max_len=60):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (slug[:max_len] if slug else "page")


def cache_dir(sub):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".cache", sub)
    os.makedirs(path, exist_ok=True)
    return path
