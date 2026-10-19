"""Single gateway for every network request job-scout makes.

Polite GETs (identifying User-Agent, 20 s timeout, one retry on 429/5xx/timeout),
mapping of transport failures to Blocked(hint) so the skill can explain blocked
egress, an optional request Budget, offline record/replay fixtures, and a health probe.

Usage:
    import net
    data = net.get_json(url, budget=net.Budget(200))  # None for 404/410
    report = net.health()  # {"ok": bool, "hosts": {...}, "hint": ...}
    JOB_SCOUT_REPLAY_DIR=tests/fixtures/http  -> serve fixtures, never touch the network
    JOB_SCOUT_RECORD_DIR=tests/fixtures/http  -> save every live HTTP response as a fixture

What it does NOT do: caching, concurrency (callers size pools with MAX_WORKERS),
or any non-GET / non-JSON request.
"""
import hashlib
import http.client
import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "VERSION"), encoding="utf-8") as _f:
        VERSION = _f.read().strip() or "0.0.0"
except OSError:
    VERSION = "0.0.0"

USER_AGENT = "job-scout/%s (+https://github.com/sorawit-w/job-scout)" % VERSION
TIMEOUT = 20
MAX_WORKERS = 8
RETRY_AFTER_CAP = 10.0
DEFAULT_RETRY_WAIT = 2.0

# Deliberately nonexistent boards: any HTTP response (200, 404, ...) proves the host is reachable.
HEALTH_URLS = {
    "boards-api.greenhouse.io": "https://boards-api.greenhouse.io/v1/boards/job-scout-health-check/jobs",
    "api.ashbyhq.com": "https://api.ashbyhq.com/posting-api/job-board/job-scout-health-check",
    "api.lever.co": "https://api.lever.co/v0/postings/job-scout-health-check?mode=json",
}

# Test seams: patched by tests so nothing real is opened or slept.
_urlopen = urllib.request.urlopen
_sleep = time.sleep


class NetError(Exception):
    pass


class Blocked(NetError):
    """The host could not be reached. hint: dns, tls, timeout, proxy_403, network, replay_miss."""

    def __init__(self, message, hint="network"):
        super().__init__(message)
        self.hint = hint


class BudgetExceeded(NetError):
    pass


class HTTPStatusError(NetError):
    def __init__(self, status, url=""):
        super().__init__("HTTP %d from %s" % (status, url))
        self.status = status


class Budget:
    """Thread-safe request counter shared by a pool of workers. cap=None means unlimited."""

    def __init__(self, cap=None):
        self.cap = cap
        self.used = 0
        self._lock = threading.Lock()

    def take(self):
        with self._lock:
            if self.cap is not None and self.used >= self.cap:
                raise BudgetExceeded("request budget of %d used up" % self.cap)
            self.used += 1


def fixture_key(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def write_fixture(directory, url, status, body):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, fixture_key(url) + ".json"), "w", encoding="utf-8") as f:
        json.dump({"url": url, "status": status, "body": body}, f, indent=1)
        f.write("\n")


def _blocked(url, err):
    if isinstance(err, socket.gaierror):
        hint = "dns"
    elif isinstance(err, ssl.SSLError):  # includes certificate verification errors
        hint = "tls"
    elif isinstance(err, (socket.timeout, TimeoutError)):
        hint = "timeout"
    else:
        hint = "network"
    return Blocked("cannot reach %s (%s: %s)" % (url, hint, err), hint)


def _is_proxy_block(status, headers, body):
    if status != 403:
        return False
    if headers.get("Proxy-Agent") or headers.get("Via"):
        return True
    text = (body or "").lower()
    return "proxy" in text or "allowlist" in text


def _attempt(url, budget):
    """One request (live or replayed). Returns (status, headers, body_text); raises Blocked on transport failure."""
    if budget is not None:
        budget.take()
    replay_dir = os.environ.get("JOB_SCOUT_REPLAY_DIR")
    if replay_dir:
        try:
            with open(os.path.join(replay_dir, fixture_key(url) + ".json"), encoding="utf-8") as f:
                fixture = json.load(f)
        except FileNotFoundError:
            raise Blocked("no replay fixture for %s" % url, "replay_miss")
        return fixture["status"], {}, fixture["body"]

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        try:
            with _urlopen(req, timeout=TIMEOUT) as resp:
                status, headers, raw = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            status, headers, raw = e.code, e.headers, e.read()
    except urllib.error.URLError as e:
        raise _blocked(url, e.reason)
    except (OSError, http.client.HTTPException) as e:
        raise _blocked(url, e)
    body = raw.decode("utf-8", "replace")
    record_dir = os.environ.get("JOB_SCOUT_RECORD_DIR")
    if record_dir:
        write_fixture(record_dir, url, status, body)
    return status, headers, body


def _retry_wait(headers):
    try:
        return max(0.0, min(float(headers.get("Retry-After")), RETRY_AFTER_CAP))
    except (TypeError, ValueError):  # missing, or an HTTP-date we don't parse
        return DEFAULT_RETRY_WAIT


def get_json(url, budget=None):
    """GET url and return parsed JSON; None for 404/410. Raises NetError subclasses otherwise."""
    replaying = bool(os.environ.get("JOB_SCOUT_REPLAY_DIR"))
    for attempt in (1, 2):
        try:
            status, headers, body = _attempt(url, budget)
        except Blocked as e:
            if e.hint == "timeout" and attempt == 1:
                continue
            raise
        if (status == 429 or status >= 500) and attempt == 1 and not replaying:
            _sleep(_retry_wait(headers))
            continue
        break
    if 200 <= status < 300:
        try:
            return json.loads(body)
        except (TypeError, ValueError):
            raise NetError("invalid JSON from %s" % url)
    if status in (404, 410):
        return None
    if _is_proxy_block(status, headers, body):
        raise Blocked("proxy refused %s (HTTP 403)" % url, "proxy_403")
    raise HTTPStatusError(status, url)


def health(urls=HEALTH_URLS, budget=None):
    """One unretried request per host; any HTTP answer except a proxy 403 counts as reachable."""
    hosts = {}
    for host, url in urls.items():
        try:
            status, headers, body = _attempt(url, budget)
            hosts[host] = "blocked: proxy_403" if _is_proxy_block(status, headers, body) else "ok"
        except Blocked as e:
            hosts[host] = "blocked: " + e.hint
    hint = next((v[len("blocked: "):] for v in hosts.values() if v != "ok"), None)
    return {"ok": hint is None, "hosts": hosts, "hint": hint}
