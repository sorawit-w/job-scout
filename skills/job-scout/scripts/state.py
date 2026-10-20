"""Local state for job-scout: the one module that reads and writes the user's disk.

Purpose:
    All local disk I/O for the skill lives here, so a privacy review has one
    place to look. State lives under ``$JOB_SCOUT_HOME`` (default
    ``~/.job-scout``), never inside the repo. This milestone holds:
      * atomic JSON read/write helpers,
      * the per-board fetch cache (6 h TTL),
      * run directories (newest 3 kept),
      * the profile (validate_profile + the `profile` CLI),
      * seen.json: which roles the user has seen, saved, applied to or dismissed, the roles an
        earlier run screened but never showed (judged, with the cached judgment), and the
        changed / saved-open / closed diff for reruns (the `seen` CLI).

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
    * A board that errored, was dead, was empty or was not probed this run never closes its seen
      roles: only live boards with no error (probed_ok_boards) can.
    * Never treats an unreadable seen.json as empty: load_seen raises and nothing is written.
    * Never caches errors: callers store only successful fetches.
"""
import calendar
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


def _write_atomic(path, write):
    """Run write(file) on a temp file next to path, fsync, then os.replace, so readers never see
    half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json_atomic(path, data):
    """Write UTF-8 JSON atomically (see _write_atomic)."""
    _write_atomic(path, lambda f: json.dump(data, f, indent=1, ensure_ascii=False))


def write_text_atomic(path, text):
    """Write UTF-8 text atomically (see _write_atomic)."""
    _write_atomic(path, lambda f: f.write(text))


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
# Work style: fixed job choices only (never free text, never the reason behind a choice). An absent
# key means "never asked", {} means "asked, skipped all", so it is not in PROFILE_DEFAULTS.
WORK_STYLE = {"meetings": {"async": "async-first", "meetings_ok": "meetings OK"},
              "on_call": {"none": "no on-call", "ok": "on-call OK"},
              "travel": {"none": "no travel", "some": "some travel", "lots": "travel OK"},
              "autonomy": {"high": "high autonomy", "guided": "guided"},
              "stage": {"startup": "startup", "growth": "growth stage", "established": "established"}}
PROFILE_KEYS = set(_STR_LISTS) | set(_ENUMS) | set(_REQUIRED) | set(PROFILE_DEFAULTS) | {"work_style"}


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
    style = p.get("work_style", {})
    if not (isinstance(style, dict) and all(k in WORK_STYLE and isinstance(v, str) and v in WORK_STYLE[k] for k, v in style.items())):
        errors.append("work_style must map %s to one of their choices (%s)" % (
            "/".join(WORK_STYLE), "; ".join("%s: %s" % (k, "/".join(v)) for k, v in WORK_STYLE.items())))
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


# The brief fields a judgment can depend on: what the rubric's gates and scores read, plus must_haves,
# which the judging model sees in the brief. work_style is display only (rubric §4), and title/company
# exclusions are applied by filter.py on every run, so neither is here.
BRIEF_FIELDS = ("target_roles", "title_synonyms", "seniority", "track", "work_modes", "commute_cities", "home_base",
                "remote_scope", "open_to_relocation", "needs_sponsorship", "base_pay_floor", "hide_no_pay",
                "industries_prefer", "industries_exclude", "must_haves", "dealbreakers")


def brief_sig(profile):
    """sha1[:12] of the brief fields a judgment depends on; editing any of them invalidates every cached judgment."""
    p = with_profile_defaults(profile if isinstance(profile, dict) else {})
    parts = {k: p.get(k) for k in BRIEF_FIELDS}
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def run_profile(run_dir):
    """The brief a run was searched with (filter.py saves a copy), else the saved profile: a later
    "change my work style" must not relabel an older run's verdicts."""
    p = read_json(Path(run_dir) / "profile.json")
    return p if isinstance(p, dict) else read_json(profile_path(), {})


# --- seen memory (seen.json) ---------------------------------------------------
# {job_key: {first_seen, last_seen, status, reason, closed_at, sig, aliases, [snap, title, company, url, judgment]}}
# snap = job_snap(): the readable fields behind sig, so `seen diff` can say what changed.
# status judged = an earlier run screened the role but never showed it (read and cut, or never read).
# Only `seen record` sets it; first_seen is when it was first shown once a shown row promotes it to seen.
# judgment = the last results.json row for the role plus run, judged_at, sig and jd_sig (the posting and
# description it judged), brief_sig and work_style (the choices its style items answer); it is reused
# only while sig, jd_sig and brief_sig still match, its style only while work_style does (cached_judgment).
# `judged forget` drops every judgment (a new resume changes the skills score; the profile has no resume).
# A collapsed job's variants can close or reorder, so an entry matches a job when its key or
# any alias equals the job's key or any variant key.

MARK_STATUSES = ("seen", "saved", "applied", "dismissed")  # what `seen mark` may set
SEEN_STATUSES = MARK_STATUSES + ("judged",)
JUDGED_DAYS = 60  # a judged entry not listed on any board for this long is pruned; no other status is
_OPEN_STATUSES = ("saved", "applied")  # only roles the user cared about are reported closed
_KEY_RE = re.compile(r"^[a-z_]+:[^:/\\\s]+:\S+$")  # ats:slug:job_id
MAX_REASON = 200


def seen_path():
    return home() / "seen.json"


def load_seen():
    """seen.json's content; {} only when the file does not exist. A file that exists but cannot be
    read as a JSON object raises ValueError naming it, so no caller ever writes over the history."""
    path = seen_path()
    if not path.exists():
        return {}
    try:
        with open(str(path), encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("%s is unreadable (%s); it was not changed — fix or move it, then rerun" % (path, e))
    if not isinstance(seen, dict):
        raise ValueError("%s is unreadable (not a JSON object); it was not changed — fix or move it, then rerun" % path)
    for key, e in seen.items():
        aliases = e.get("aliases", []) if isinstance(e, dict) else None
        if not (isinstance(e, dict) and e.get("status") in SEEN_STATUSES and isinstance(aliases, list)
                and all(isinstance(a, str) for a in aliases)):
            raise ValueError("%s is unreadable (bad entry %r); it was not changed — fix or move it, then rerun"
                             % (path, key))
    return seen


def job_sig(job):
    """sha1[:12] of title, pay and sorted locations; any change to these makes the job "changed"."""
    comp = job.get("comp") if isinstance(job.get("comp"), dict) else {}
    parts = [job.get("title") or "", comp.get("min"), comp.get("max"), comp.get("currency"), comp.get("interval"),
             sorted(job.get("locations") or [])]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def job_snap(job):
    """The fields job_sig hashes, kept readable so a rerun can say what changed (e.g. pay only)."""
    comp = job.get("comp")
    return {"title": job.get("title"),
            "comp": {k: comp.get(k) for k in ("min", "max", "currency", "interval")} if isinstance(comp, dict) else None,
            "locations": sorted(job.get("locations") or [])}


def job_keys(job):
    """The collapsed job's key, then its variants' keys, without duplicates."""
    keys = [job.get("key")] + [v.get("key") for v in job.get("variants") or [] if isinstance(v, dict)]
    return [k for i, k in enumerate(keys) if k and k not in keys[:i]]


def seen_index(seen):
    """{key or alias: entry key} for matching current jobs against seen.json. An entry's own key
    wins over another entry's alias for the same key."""
    index = {key: key for key in seen}
    for key, e in seen.items():
        for k in e.get("aliases") or []:
            index.setdefault(k, key)
    return index


def _matches(job, index):
    """Every seen.json entry key any of the job's keys points at (two roles can regroup into one)."""
    keys = [index[k] for k in job_keys(job) if k in index]
    return [k for i, k in enumerate(keys) if k not in keys[:i]]


_STRENGTH = ("saved", "applied", "dismissed", "seen", "judged")  # saved must stay shown; applied/dismissed stay hidden


def _strength(e):
    return _STRENGTH.index(e.get("status")) if e.get("status") in _STRENGTH else len(_STRENGTH)


def _deciding_entry(job, seen, index=None):
    """The matching entry with the strongest status (saved > applied > dismissed > seen > judged), or None."""
    keys = _matches(job, seen_index(seen) if index is None else index)
    return min((seen[k] for k in keys), key=_strength) if keys else None


def job_state(job, seen, index=None):
    """new | changed | seen | saved | applied | dismissed | judged for one collapsed job; with several
    matching entries, the strongest status (saved > applied > dismissed > seen > judged) decides.
    A judged role whose posting changed is new: the user never saw either version."""
    e = _deciding_entry(job, seen, index)
    if e is None:
        return "new"
    if e.get("status") == "judged":
        return "new" if e.get("sig") and e["sig"] != job_sig(job) else "judged"
    if e.get("status") in ("seen", "saved") and e.get("sig") and e["sig"] != job_sig(job):  # no sig: marked before record
        return "changed"
    return e.get("status") or "seen"


def jd_sig(text):
    """sha1[:12] of a job description with whitespace collapsed, or None for no text."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else None


def cached_judgment(job, seen, profile, description, index=None):
    """The deciding entry's judgment when it was made on this posting (same sig), this description (same
    jd_sig: an employer can add "no sponsorship" without touching title, pay or places) and this brief
    (same brief_sig), else None, and the role is read again. description is this run's full text, or
    None before the live check: then only posting and brief are compared, and the caller must check
    again once the text is fetched. With other work_style choices the judgment comes back with style
    None: a conflict under "no travel" can be a match under "some travel", so the style is written again."""
    e = _deciding_entry(job, seen, index)
    j = e.get("judgment") if e else None
    if not (isinstance(j, dict) and j.get("sig") == job_sig(job) and j.get("brief_sig") == brief_sig(profile)):
        return None
    if description is not None and not (j.get("jd_sig") and j["jd_sig"] == jd_sig(description)):
        return None
    return j if (j.get("work_style") or {}) == _work_style(profile) else dict(j, style=None)


def _work_style(profile):
    return (profile.get("work_style") if isinstance(profile, dict) else None) or {}


def _board(key):
    return ":".join(key.split(":", 2)[:2])


def probed_ok_boards(run_dir):
    """{"ats:slug"} boards probed successfully this run: live (≥1 job) with no error. An empty
    board does not count — a board that briefly returns no jobs must not close every role on it."""
    b = read_json(Path(run_dir) / "boards.json", {})
    if not isinstance(b, dict):
        return set()
    bad = {e.get("board") for e in b.get("errors") or [] if isinstance(e, dict)}
    return set(b.get("live_boards") or []) - bad


def live_split(jobs, jds):
    """(open, gone): jobs split by their live check in jds.json. A job is gone when the live check
    found every one of its variants closed, even while the board list (which can lag) still shows
    it; one closed variant leaves the group open while another may still be available."""
    closed = {k for k, e in (jds if isinstance(jds, dict) else {}).items()
              if isinstance(e, dict) and e.get("status") == "closed"}
    flags = [closed.issuperset(job_keys(j)) for j in jobs]
    return [_live_face(j, closed) for j, f in zip(jobs, flags) if not f], [j for j, f in zip(jobs, flags) if f]


def _live_face(job, closed):
    """When the job's own posting is closed, a still-listed variant takes over the shown fields (key,
    url, places) so nothing links to the gone posting. The variants stay, so history still matches."""
    if job.get("key") not in closed:
        return job
    live = next(v for v in job.get("variants") or [] if isinstance(v, dict) and v.get("key") not in closed)
    return dict(job, **live)


def diff(jobs, probed_ok, seen, gone=()):
    """Lists of keys: changed / saved_open / applied_open (current job keys) and closed (seen.json
    keys whose boards were all probed ok this run but no current job matches, or that match a job in
    `gone`: a live check is direct evidence, even on a partially searched board). No "new" list: over
    all of jobs.json it counts roles the brief rules out; filter.py's per-candidate state is the count."""
    index = seen_index(seen)
    direct = {k for job in gone for k in _matches(job, index)}
    out = {"changed": [], "saved_open": [], "applied_open": [], "closed": []}
    matched = set()
    for job in jobs:
        keys = _matches(job, index)
        if not keys:
            continue
        matched.update(keys)
        if job_state(job, seen, index) == "changed":
            out["changed"].append(job.get("key"))
        statuses = {seen[k].get("status") for k in keys}
        for status in ("saved", "applied"):
            if status in statuses:
                out[status + "_open"].append(job.get("key"))
    for key, e in seen.items():
        if (key not in matched and e.get("status") in _OPEN_STATUSES and not e.get("closed_at")
                and (key in direct or all(_board(k) in probed_ok for k in [key] + list(e.get("aliases") or [])))):
            out["closed"].append(key)
    return out


def _merge_aliases(e, key, keys):
    merged = list(e.get("aliases") or []) + keys  # old aliases stay: a closed variant can come back
    e["aliases"] = [k for i, k in enumerate(merged) if k != key and k not in merged[:i]]


def _shown_url(job, row_key):
    """The link the user saw: the variant whose key is the results row key, else the job's url."""
    v = next((v for v in job.get("variants") or [] if isinstance(v, dict) and v.get("key") == row_key), {})
    return v.get("url") or job.get("url")


def _judgment(row, run_dir, stamp, job, profile, jd):
    j = {f: row.get(f) for f in ("total", "scores", "gates", "show", "why", "risk", "style")}
    return dict(j, run=Path(run_dir).name, judged_at=stamp, sig=job_sig(job),
                jd_sig=jd_sig(jd.get("full") if isinstance(jd, dict) else None), brief_sig=brief_sig(profile),
                work_style=_work_style(profile))


def _set_posting(e, job, row_key):
    e.update(sig=job_sig(job), snap=job_snap(job), title=job.get("title"), company=job.get("company"),
             url=_shown_url(job, row_key))


def _iso_epoch(iso):
    try:
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def record(run_dir, now=None):
    """Remember what this run showed and screened.
    * results.json rows with show true: seen (a judged entry is promoted, first_seen = now); sig, snap,
      title, url and judgment refreshed on every matching entry.
    * every other results.json row, and every candidates.json job that was never read: judged, unless
      a stronger entry matches. A read row's judgment is stored on any matching entry, but sig and snap
      move only on judged entries, so a role the user saw can still read "changed".
    * every job in jobs.json that matches an entry: aliases and last_seen refreshed; closed_at set or
      cleared. A job whose live check in jds.json found the posting gone counts as absent, even while
      the board still lists it. A run with no results.json (a rerun with nothing new) records closures.
    * judged entries whose last_seen is over JUDGED_DAYS old are dropped.
    Returns counts. Raises FileNotFoundError when the run has no jobs.json or an unreadable
    results.json, ValueError (nothing written) when seen.json is unreadable."""
    run_dir = Path(run_dir)
    jobs = read_json(run_dir / "jobs.json")
    results = read_json(run_dir / "results.json") if (run_dir / "results.json").exists() else {"rows": []}
    if not isinstance(results, dict) or not isinstance(jobs, list):
        raise FileNotFoundError("run %s has no jobs.json, or results.json is unreadable" % run_dir.name)
    stamp = now_iso(now)
    seen = load_seen()
    profile = run_profile(run_dir)
    jds = read_json(run_dir / "jds.json", {})
    jds = jds if isinstance(jds, dict) else {}
    by_key = {k: j for j in jobs for k in job_keys(j)}
    counts = {"inserted": 0, "updated": 0, "judged": 0, "missing": 0, "closed": 0, "reopened": 0, "pruned": 0}
    rows = [r for r in results.get("rows") or [] if isinstance(r, dict)]
    read = {id(by_key.get(r.get("key"))) for r in rows}  # by job, so another variant's key still counts as read
    unread = [{"key": c.get("key")} for c in read_json(run_dir / "candidates.json", [])
              if isinstance(c, dict) and id(by_key.get(c.get("key"))) not in read]
    for row, was_read in [(r, True) for r in rows] + [(c, False) for c in unread]:
        job = by_key.get(row.get("key"))
        shown = row.get("show") is True
        if job is None:
            if shown:
                counts["missing"] += 1  # shown row not in jobs.json: nothing to sign
            continue
        keys = job_keys(job)
        targets = _matches(job, seen_index(seen))
        if not targets:
            targets = keys[:1]
            seen[keys[0]] = {"first_seen": stamp, "status": "seen" if shown else "judged", "reason": None,
                             "closed_at": None, "aliases": []}
            counts["inserted" if shown else "judged"] += 1
        elif not was_read:
            continue  # known already: the jobs loop below refreshes it, and an earlier judgment stays
        else:
            counts["updated" if shown else "judged"] += 1
        for key in targets:
            e = seen[key]
            _merge_aliases(e, key, keys)
            e["last_seen"] = stamp
            if shown and e["status"] == "judged":
                e.update(status="seen", first_seen=stamp)
            if shown or e["status"] == "judged":
                _set_posting(e, job, row.get("key"))
            if was_read:
                e["judgment"] = _judgment(row, run_dir, stamp, job, profile, jds.get(row.get("key")))
    index = seen_index(seen)
    jobs, gone = live_split(jobs, jds)  # a live-closed role closes, not reopens
    for job in jobs:  # unshown too: filter drops unchanged roles, and their variants keep moving
        keys = job_keys(job)
        for key in _matches(job, index):
            e = seen[key]
            _merge_aliases(e, key, keys)
            e["last_seen"] = stamp
            if e.get("closed_at"):
                e["closed_at"] = None
                counts["reopened"] += 1
    for key in diff(jobs, probed_ok_boards(run_dir), seen, gone)["closed"]:
        seen[key]["closed_at"] = stamp
        counts["closed"] += 1
    cutoff = _iso_epoch(stamp) - JUDGED_DAYS * 86400
    for key in [k for k, e in seen.items() if e["status"] == "judged" and (_iso_epoch(e.get("last_seen")) or cutoff) < cutoff]:
        del seen[key]
        counts["pruned"] += 1
    write_json_atomic(seen_path(), seen)
    return counts


def forget_judgments():
    """Drop every cached judgment (statuses stay), so every role is read again; returns how many.
    For a new resume: the skills score depends on it, and the profile does not store it."""
    seen = load_seen()
    n = sum(1 for e in seen.values() if e.pop("judgment", None) is not None)
    if n:
        write_json_atomic(seen_path(), seen)
    return n


def mark(key, status, reason=None, now=None):
    """Set a role's status (creating the entry if record never saw it). ValueError on bad input,
    including "judged", which only `seen record` sets."""
    if status not in MARK_STATUSES:
        raise ValueError("status must be one of %s" % "/".join(MARK_STATUSES))
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


def seen_summary():
    """{"counts": {status: n}, "saved"/"applied": [{key, title, company, url, closed}]} — `seen show`."""
    seen = load_seen()
    counts = {}
    for e in seen.values():
        counts[e.get("status")] = counts.get(e.get("status"), 0) + 1
    out = {"counts": counts}
    for status in ("saved", "applied"):
        out[status] = [{"key": k, "title": e.get("title"), "company": e.get("company"), "url": e.get("url"),
                        "closed": bool(e.get("closed_at"))} for k, e in seen.items() if e.get("status") == status]
    return out


def _seen_cli(args):
    """seen diff|record [--run] · seen mark KEY STATUS [--reason] · seen show. Exit 0 ok, 1 bad input
    (including an unreadable seen.json, which is left unchanged), 2 no run."""
    try:
        if args.action in ("diff", "record"):
            try:
                run = resolve_run(args.run)
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
                seen = load_seen()
                open_jobs, gone = live_split(jobs, read_json(run / "jds.json", {}))
                out = diff(open_jobs, probed_ok_boards(run), seen, gone)
                index, by_key = seen_index(seen), {j.get("key"): j for j in open_jobs}  # promoted keys too
                out = dict(out, counts={k: len(v) for k, v in out.items()},
                           changed_details=[{"key": k, "before": _deciding_entry(by_key[k], seen, index).get("snap"),
                                             "after": job_snap(by_key[k])} for k in out["changed"]],
                           closed_details=[{"key": k, "title": seen[k].get("title"), "company": seen[k].get("company"),
                                            "status": seen[k].get("status"), "url": seen[k].get("url")}
                                           for k in out["closed"]])
        elif args.action == "mark":
            e = mark(args.key, args.status, args.reason)
            out = {"ok": True, "key": e["key"], "status": e["status"], "reason": e["reason"]}
        else:
            out = seen_summary()
    except ValueError as e:  # bad run id, bad mark input, or unreadable seen.json
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv=None):
    """CLI: state.py profile validate|save --stdin|show  (JSON on stdin/stdout);
    state.py seen diff|record [--run latest] · seen mark KEY STATUS [--reason TEXT] · seen show;
    state.py judged forget (drop every cached judgment, e.g. after a new resume)."""
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
    sub.add_parser("judged").add_argument("action", choices=("forget",))
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        # seen exit 2 means "no run"; an argparse failure there (e.g. --reason -onsite) is bad input
        if e.code and list(sys.argv[1:] if argv is None else argv)[:1] == ["seen"]:
            print(json.dumps({"error": "bad arguments for seen (usage on stderr); "
                                       "write a reason that starts with - as --reason=-text"}))
            return 1
        raise

    if args.area == "seen":
        return _seen_cli(args)
    if args.area == "judged":
        try:
            print(json.dumps({"forgot": forget_judgments()}))
        except ValueError as e:  # unreadable seen.json, left unchanged
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
        return 0
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
