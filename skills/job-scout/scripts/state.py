"""Local state for job-scout: the one module that reads and writes the user's disk.

Purpose:
    All local disk I/O for the skill lives here, so a privacy review has one
    place to look. State lives under ``$JOB_SCOUT_HOME`` (default
    ``~/.job-scout``), never inside the repo. This milestone holds:
      * atomic JSON read/write helpers,
      * the per-board fetch cache (6 h TTL),
      * run directories (newest 3 kept).

Usage:
    import state
    data = state.cache_get("greenhouse", "anthropic")
    if data is None:
        data = fetch(...)                      # adapter code, not here
        state.cache_put("greenhouse", "anthropic", data)
    run_dir = state.new_run()
    state.write_json_atomic(run_dir / "jobs.json", jobs)

What it does NOT do:
    * No network access; adapters fetch, this module only stores.
    * No profile.json or seen.json logic yet (arrives in M2 / M4, in this module).
    * Never caches errors: callers store only successful fetches.
"""
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

CACHE_TTL = 6 * 3600
_ATS_RE = re.compile(r"^[a-z_]+$")
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")  # what new_run() creates; nothing else resolves


def home():
    """Return the state directory, creating it (mode 0o700) if missing."""
    env = os.environ.get("JOB_SCOUT_HOME")
    path = Path(os.path.expanduser(env)) if env else Path.home() / ".job-scout"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def write_json_atomic(path, data):
    """Write UTF-8 JSON via temp file + fsync + os.replace, so readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path, default=None):
    """Return parsed JSON, or ``default`` if the file is missing, unreadable or corrupt."""
    try:
        with open(str(path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# --- board cache -------------------------------------------------------------

def cache_path(ats, slug):
    """Return home()/cache/<ats>/<slug>.json; raise ValueError on unsafe names."""
    if not isinstance(ats, str) or not _ATS_RE.match(ats):
        raise ValueError("bad ats name: %r" % (ats,))
    if (not isinstance(slug, str) or not slug or slug.startswith(".")
            or "/" in slug or "\\" in slug or ".." in slug):
        raise ValueError("bad board slug: %r" % (slug,))
    return home() / "cache" / ats / (slug + ".json")


def cache_put(ats, slug, data, now=None):
    """Store a successful fetch. Errors are never cached: callers pass only good data."""
    write_json_atomic(cache_path(ats, slug), {"fetched_at": time.time() if now is None else now, "data": data})


def _cache_entry(ats, slug):
    entry = read_json(cache_path(ats, slug))
    if isinstance(entry, dict) and isinstance(entry.get("fetched_at"), (int, float)) and "data" in entry:
        return entry
    return None


def cache_age(ats, slug, now=None):
    """Seconds since the board was cached, or None if there is no valid entry."""
    entry = _cache_entry(ats, slug)
    if entry is None:
        return None
    return (time.time() if now is None else now) - entry["fetched_at"]


def cache_get(ats, slug, ttl=CACHE_TTL, now=None):
    """Return cached data if younger than ``ttl`` seconds, else None (also for corrupt files)."""
    entry = _cache_entry(ats, slug)  # read once: a second read could race a concurrent delete
    if entry is None or (time.time() if now is None else now) - entry["fetched_at"] >= ttl:
        return None
    return entry["data"]


# --- run directories -------------------------------------------------------

def _runs_dir():
    return home() / "runs"


def _run_dirs():
    root = _runs_dir()
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and _RUN_ID_RE.match(p.name)), key=_run_key)


def _run_key(path):
    """Chronological order: timestamp, then numeric suffix ("-10" after "-2")."""
    base, _, suffix = path.name.partition("-")
    return base, int(suffix) if suffix.isdigit() else 1


def new_run(now=None):
    """Create runs/<UTC %Y%m%dT%H%M%SZ>[-N], prune old runs, return the new path."""
    root = _runs_dir()
    root.mkdir(parents=True, exist_ok=True)
    base = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    # Always number above any run with this timestamp, even if pruning deleted the lower ones,
    # so a newer run never sorts as older than a survivor.
    same = [_run_key(p)[1] for p in _run_dirs() if p.name.partition("-")[0] == base]
    n = max(same) + 1 if same else 1
    while True:
        path = root / (base if n == 1 else "%s-%d" % (base, n))
        try:
            path.mkdir()
            break
        except FileExistsError:
            n += 1
    prune_runs()
    return path


def latest_run():
    """Return the newest run directory, or None."""
    runs = _run_dirs()
    return runs[-1] if runs else None


def resolve_run(spec):
    """Map "latest" or a run id to its directory. ValueError on unsafe ids."""
    if spec == "latest":
        run = latest_run()
        if run is None:
            raise FileNotFoundError("no runs yet")
        return run
    if not spec or not _RUN_ID_RE.match(spec):
        raise ValueError("bad run id: %r" % (spec,))
    path = _runs_dir() / spec
    if not path.is_dir():
        raise FileNotFoundError("no such run: %s" % spec)
    return path


def prune_runs(keep=3):
    """Delete all but the newest ``keep`` run directories under home()/runs."""
    runs = _run_dirs()
    for path in runs[:max(len(runs) - keep, 0)]:
        shutil.rmtree(str(path))


def now_iso(now=None):
    """UTC timestamp like 2026-10-18T09:30:00Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
