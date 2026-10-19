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
    * Profile: validate_profile() + the `profile` CLI (M2). seen.json logic arrives in M4.
    * Never caches errors: callers store only successful fetches.
"""
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import normalize  # pure text helpers, no I/O; must never import state

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


# --- profile (the confirmed search brief) -----------------------------------
# Only these keys are allowed. Rejecting everything else is how protected attributes
# (age, gender, nationality, ...) are kept out of the profile: there is no field for them.

_STR_LISTS = ("target_roles", "title_synonyms", "title_keywords", "title_exclusions", "seniority",
              "commute_cities", "remote_scope", "industries_prefer", "industries_exclude",
              "companies_include", "companies_exclude", "must_haves", "dealbreakers")
_ENUMS = {"track": ("ic", "manager", "either"), "needs_sponsorship": ("yes", "no", "undisclosed")}
_WORK_MODES = ("remote", "hybrid", "onsite")
_SOURCES = ("resume", "inferred", "default", "you")
_INTERVALS = ("year", "month", "week", "day", "hour")
_CODE_RE = re.compile(r"^[A-Z]{2}$")
_REQUIRED = ("schema", "target_roles", "work_modes", "needs_sponsorship", "base_pay_floor")
PROFILE_DEFAULTS = {"track": "either", "home_base": None, "hide_no_pay": False, "open_to_relocation": False,
                    "recency_flag_days": 90, "result_count": 15, "sources": {}}
PROFILE_KEYS = set(_STR_LISTS) | set(_ENUMS) | set(_REQUIRED) | set(PROFILE_DEFAULTS)


def validate_profile(p):
    """Return a list of error strings; empty means the profile is valid."""
    if not isinstance(p, dict):
        return ["profile must be a JSON object"]
    errors = ["unknown field %r — the profile has no place for it" % k for k in sorted(set(p) - PROFILE_KEYS)]
    errors += ["missing required field %r" % k for k in _REQUIRED if k not in p]
    if p.get("schema", 1) != 1:
        errors.append("schema must be 1")
    for key in _STR_LISTS + ("work_modes",):
        if key in p and not (isinstance(p[key], list) and all(isinstance(x, str) and x.strip() for x in p[key])):
            errors.append("%s must be a list of non-empty strings" % key)
    for key in ("target_roles", "work_modes"):  # both are answers the confirmation gate must have
        if isinstance(p.get(key), list) and not p[key]:
            errors.append("%s must not be empty" % key)
    if isinstance(p.get("remote_scope"), list):  # filter.py compares these to ISO codes, not names
        errors += ['remote_scope: %r is not a code — use two-letter country codes like "US" or "GB", or a region '
                   'like %s' % (c, "/".join(normalize.REGION_CODES))
                   for c in p["remote_scope"] if isinstance(c, str) and not (_CODE_RE.match(c) or c in normalize.REGION_CODES)]
    if isinstance(p.get("work_modes"), list):
        errors += ["work_modes: %r is not one of %s" % (m, "/".join(_WORK_MODES)) for m in p["work_modes"] if m not in _WORK_MODES]
    for key, allowed in _ENUMS.items():
        if key in p and p[key] not in allowed:
            errors.append("%s must be one of %s" % (key, "/".join(allowed)))
    floor = p.get("base_pay_floor")
    if floor is not None:
        if not (isinstance(floor, dict) and isinstance(floor.get("amount"), (int, float)) and not isinstance(floor["amount"], bool) and floor["amount"] >= 0
                and isinstance(floor.get("currency", "USD"), str) and floor.get("interval", "year") in _INTERVALS
                and set(floor) <= {"amount", "currency", "interval"}):
            errors.append("base_pay_floor must be null or {amount: number, currency: str, interval: %s}" % "/".join(_INTERVALS))
    if "home_base" in p and p["home_base"] is not None and not isinstance(p["home_base"], str):
        errors.append("home_base must be a string or null")
    for key in ("hide_no_pay", "open_to_relocation"):
        if key in p and not isinstance(p[key], bool):
            errors.append("%s must be true or false" % key)
    for key, lo, hi in (("result_count", 1, 50), ("recency_flag_days", 1, 3650)):
        if key in p and not (isinstance(p[key], int) and not isinstance(p[key], bool) and lo <= p[key] <= hi):
            errors.append("%s must be an integer from %d to %d" % (key, lo, hi))
    sources = p.get("sources", {})
    if not isinstance(sources, dict) or any(k not in PROFILE_KEYS or v not in _SOURCES for k, v in sources.items()):
        errors.append("sources must map profile fields to one of %s" % "/".join(_SOURCES))
    return errors


def with_profile_defaults(p):
    out = dict(PROFILE_DEFAULTS, sources={})
    out.update({k: [] for k in _STR_LISTS})
    out.update(p)
    return out


def profile_path():
    return home() / "profile.json"


def main(argv=None):
    """CLI: state.py profile validate|save --stdin|show  (JSON on stdin/stdout)."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="state.py")
    sub = ap.add_subparsers(dest="area", required=True)
    prof = sub.add_parser("profile")
    prof.add_argument("action", choices=("validate", "save", "show"))
    prof.add_argument("--stdin", action="store_true", help="read the profile JSON from stdin (save)")
    args = ap.parse_args(argv)

    if args.action == "show":
        p = read_json(profile_path())
        if p is None:
            print(json.dumps({"error": "no profile saved yet"}))
            return 1
        print(json.dumps(with_profile_defaults(p), ensure_ascii=False, indent=1))
        return 0
    try:
        p = json.loads(sys.stdin.read())
    except ValueError as e:
        print(json.dumps({"errors": ["invalid JSON: %s" % e]}))
        return 1
    errors = validate_profile(p)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False))
        return 1
    if args.action == "save":
        write_json_atomic(profile_path(), p)
    print(json.dumps({"ok": True, "saved": args.action == "save"}))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
