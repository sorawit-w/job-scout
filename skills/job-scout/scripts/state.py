"""Local state for job-scout: the one module that reads and writes the user's disk.

Purpose:
    All local disk I/O for the skill lives here, so a privacy review has one
    place to look. State lives under ``$JOB_SCOUT_HOME`` (default
    ``~/.job-scout``), never inside the repo. This milestone holds:
      * atomic JSON read/write helpers,
      * the per-board fetch cache (6 h TTL),
      * run directories (newest 3 kept),
      * the profile (validate_profile + the `profile` CLI),
      * seen.json: which roles the user has seen, saved, applied to or dismissed, and the
        new / changed / saved-open / closed diff for reruns (the `seen` CLI).

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
    * A board that errored, was dead or was not probed this run never closes its seen roles:
      only boards probed successfully (probed_ok_boards) can.
    * Never caches errors: callers store only successful fetches.
"""
import hashlib
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


# --- seen memory (seen.json) ---------------------------------------------------
# {job_key: {first_seen, last_seen, status, reason, closed_at, sig, aliases, [title, company]}}
# A collapsed job's variants can close or reorder, so an entry matches a job when its key or
# any alias equals the job's key or any variant key.

SEEN_STATUSES = ("seen", "saved", "applied", "dismissed")
_OPEN_STATUSES = ("seen", "saved", "applied")  # dismissed roles are never reported closed
_KEY_RE = re.compile(r"^[a-z_]+:[^:/\\\s]+:\S+$")  # ats:slug:job_id
MAX_REASON = 200


def seen_path():
    return home() / "seen.json"


def load_seen():
    seen = read_json(seen_path(), {})
    return seen if isinstance(seen, dict) else {}


def job_sig(job):
    """sha1[:12] of title, pay and sorted locations; any change to these makes the job "changed"."""
    comp = job.get("comp") if isinstance(job.get("comp"), dict) else {}
    parts = [job.get("title") or "", comp.get("min"), comp.get("max"), comp.get("currency"), comp.get("interval"),
             sorted(job.get("locations") or [])]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def job_keys(job):
    """The collapsed job's key, then its variants' keys, without duplicates."""
    keys = [job.get("key")] + [v.get("key") for v in job.get("variants") or [] if isinstance(v, dict)]
    return [k for i, k in enumerate(keys) if k and k not in keys[:i]]


def seen_index(seen):
    """{key or alias: entry key} for matching current jobs against seen.json."""
    index = {}
    for key, e in seen.items():
        for k in [key] + list(e.get("aliases") or []):
            index.setdefault(k, key)
    return index


def _match(job, index):
    return next((index[k] for k in job_keys(job) if k in index), None)


def job_state(job, seen, index=None):
    """new | changed | seen | saved | applied | dismissed for one collapsed job."""
    key = _match(job, seen_index(seen) if index is None else index)
    if key is None:
        return "new"
    e = seen[key]
    if e.get("status") in ("seen", "saved") and e.get("sig") and e["sig"] != job_sig(job):  # no sig: marked before record
        return "changed"
    return e.get("status") or "seen"


def _board(key):
    return ":".join(key.split(":", 2)[:2])


def probed_ok_boards(run_dir):
    """{"ats:slug"} boards probed successfully this run (live or empty, with no error)."""
    b = read_json(Path(run_dir) / "boards.json", {})
    if not isinstance(b, dict):
        return set()
    bad = {e.get("board") for e in b.get("errors") or [] if isinstance(e, dict)}
    return (set(b.get("live_boards") or []) | set(b.get("empty") or [])) - bad


def diff(jobs, probed_ok, seen):
    """Lists of keys: new / changed / saved_open / applied_open (current job keys) and closed
    (seen.json keys whose boards were all probed ok this run but no current job matches)."""
    index = seen_index(seen)
    out = {"new": [], "changed": [], "saved_open": [], "applied_open": [], "closed": []}
    matched = set()
    for job in jobs:
        key = _match(job, index)
        st = job_state(job, seen, index)
        if key is None:
            out["new"].append(job.get("key"))
            continue
        matched.add(key)
        if st == "changed":
            out["changed"].append(job.get("key"))
        status = seen[key].get("status")
        if status in ("saved", "applied"):
            out[status + "_open"].append(job.get("key"))
    for key, e in seen.items():
        if (key not in matched and e.get("status") in _OPEN_STATUSES and not e.get("closed_at")
                and all(_board(k) in probed_ok for k in [key] + list(e.get("aliases") or []))):
            out["closed"].append(key)
    return out


def record(run_dir, now=None):
    """Mark results.json rows with show true as seen, set or clear closed_at; return counts.
    Raises FileNotFoundError when the run has no results.json or jobs.json."""
    run_dir = Path(run_dir)
    results, jobs = read_json(run_dir / "results.json"), read_json(run_dir / "jobs.json")
    if not isinstance(results, dict) or not isinstance(jobs, list):
        raise FileNotFoundError("run %s has no results.json or jobs.json" % run_dir.name)
    stamp = now_iso(now)
    seen = load_seen()
    by_key = {k: j for j in jobs for k in job_keys(j)}
    counts = {"inserted": 0, "updated": 0, "missing": 0, "closed": 0, "reopened": 0}
    for row in results.get("rows") or []:
        if not (isinstance(row, dict) and row.get("show") is True):
            continue
        job = by_key.get(row.get("key"))
        if job is None:
            counts["missing"] += 1  # shown row not in jobs.json: nothing to sign
            continue
        keys = job_keys(job)
        key = _match(job, seen_index(seen))
        if key is None:
            key = keys[0]
            seen[key] = {"first_seen": stamp, "status": "seen", "reason": None, "closed_at": None, "aliases": []}
            counts["inserted"] += 1
        else:
            counts["updated"] += 1
        e = seen[key]
        merged = list(e.get("aliases") or []) + keys  # old aliases stay: a closed variant can come back
        e.update(last_seen=stamp, sig=job_sig(job), title=job.get("title"), company=job.get("company"),
                 aliases=[k for i, k in enumerate(merged) if k != key and k not in merged[:i]])
    index = seen_index(seen)
    for job in jobs:
        key = _match(job, index)
        if key is not None and seen[key].get("closed_at"):
            seen[key]["closed_at"] = None
            counts["reopened"] += 1
    for key in diff(jobs, probed_ok_boards(run_dir), seen)["closed"]:
        seen[key]["closed_at"] = stamp
        counts["closed"] += 1
    write_json_atomic(seen_path(), seen)
    return counts


def mark(key, status, reason=None, now=None):
    """Set a role's status (creating the entry if record never saw it). ValueError on bad input."""
    if status not in SEEN_STATUSES:
        raise ValueError("status must be one of %s" % "/".join(SEEN_STATUSES))
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise ValueError("bad job key %r (want ats:slug:job_id)" % (key,))
    if reason is not None and (not isinstance(reason, str) or len(reason) > MAX_REASON):
        raise ValueError("reason must be a string of at most %d characters" % MAX_REASON)
    seen = load_seen()
    target = seen_index(seen).get(key, key)
    e = seen.setdefault(target, {"first_seen": now_iso(now), "last_seen": now_iso(now), "closed_at": None,
                                 "sig": None, "aliases": []})
    e.update(status=status, reason=reason)
    write_json_atomic(seen_path(), seen)
    return dict(e, key=target)


def _seen_cli(args):
    """seen diff|record [--run] · seen mark KEY STATUS [--reason] · seen show. Exit 0 ok, 1 bad input, 2 no run."""
    if args.action in ("diff", "record"):
        try:
            run = resolve_run(args.run)
        except ValueError as e:
            print(json.dumps({"error": str(e)}))
            return 1
        except FileNotFoundError as e:
            print(json.dumps({"error": str(e)}))
            return 2
        if args.action == "record":
            try:
                out = record(run)
            except FileNotFoundError as e:
                print(json.dumps({"error": str(e)}))
                return 2
        else:
            jobs = read_json(run / "jobs.json")
            if not isinstance(jobs, list):
                print(json.dumps({"error": "run %s has no jobs.json — run probe.py first" % run.name}))
                return 2
            out = diff(jobs, probed_ok_boards(run), load_seen())
            out = dict(out, counts={k: len(v) for k, v in out.items()})
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if args.action == "mark":
        try:
            e = mark(args.key, args.status, args.reason)
        except ValueError as err:
            print(json.dumps({"error": str(err)}))
            return 1
        print(json.dumps({"ok": True, "key": e["key"], "status": e["status"], "reason": e["reason"]}, ensure_ascii=False))
        return 0
    seen = load_seen()
    counts = {}
    for e in seen.values():
        counts[e.get("status")] = counts.get(e.get("status"), 0) + 1
    out = {"counts": counts}
    for status in ("saved", "applied"):
        out[status] = [{"key": k, "title": e.get("title"), "company": e.get("company"), "closed": bool(e.get("closed_at"))}
                       for k, e in seen.items() if e.get("status") == status]
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv=None):
    """CLI: state.py profile validate|save --stdin|show  (JSON on stdin/stdout);
    state.py seen diff|record [--run latest] · seen mark KEY STATUS [--reason TEXT] · seen show."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="state.py")
    sub = ap.add_subparsers(dest="area", required=True)
    prof = sub.add_parser("profile")
    prof.add_argument("action", choices=("validate", "save", "show"))
    prof.add_argument("--stdin", action="store_true", help="read the profile JSON from stdin (save)")
    seen = sub.add_parser("seen")
    seen_sub = seen.add_subparsers(dest="action", required=True)
    for name in ("diff", "record"):
        seen_sub.add_parser(name).add_argument("--run", default="latest")
    mark_p = seen_sub.add_parser("mark")
    mark_p.add_argument("key")
    mark_p.add_argument("status")  # checked by mark(), so a bad status is exit 1, not argparse's 2
    mark_p.add_argument("--reason")
    seen_sub.add_parser("show")
    args = ap.parse_args(argv)

    if args.area == "seen":
        return _seen_cli(args)
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
