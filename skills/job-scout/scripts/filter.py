#!/usr/bin/env python3
"""Hard filters and a title prefilter: turn a run's jobs.json into a ranked candidates.json.

Usage (paths relative to the skill folder):
  python3 scripts/filter.py [--run latest|<run-id>] [--limit 150]

Reads <run>/jobs.json (written by probe.py) and the saved profile (~/.job-scout/profile.json).
Writes <run>/candidates.json (full job dicts plus match and flags, ranked, at most --limit) and
prints one compact JSON object:
  {"counts": {"input", "removed": {reason: n}, "candidates"},
   "candidates": [{key, company, title, where, mode, since, pay, match, flags}],
   "near_misses": [{key, company, title, reason}]}
Exit codes: 0 ok · 2 no profile, no run, no jobs.json, or bad arguments.

Rules, in order (the first rule a job fails is its removal reason): company exclude ->
display-variant pick -> work mode / location / remote scope -> seniority -> track -> title
exclusions -> title prefilter (strong / borderline) -> pay floor (structured pay only).
Old postings are flagged ("open over N days"), never removed.

What it does NOT do:
- No judgment of fit. "strong" and "borderline" are word matches on the title only; the LLM
  step in SKILL.md reads the job descriptions and decides.
- No network, and no pay read from description text.
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import normalize  # noqa: E402
import state  # noqa: E402

DEFAULT_LIMIT = 150
MAX_LIMIT = 300
MAX_NEAR_MISSES = 5
REASONS = ("work_mode", "location", "remote_scope", "seniority", "track", "company", "title",
           "title_exclusion", "pay_floor")
SCOPE_NOT_STATED = "remote scope not stated"
AMER_FLAG = "Americas — check US eligibility"
MODE_NOT_STATED = "work mode not stated"
LOCATION_FLAGS = (SCOPE_NOT_STATED, AMER_FLAG, MODE_NOT_STATED)

_ALIASES = {"sr": "senior", "jr": "junior", "swe": "software engineer", "eng": "engineer"}
_LEVEL_WORDS = {"senior", "staff", "lead", "principal"}  # ignored when matching a target role
_GENERIC = {"engineer", "engineering", "software", "developer", "senior", "staff", "lead", "principal",
            "manager", "the", "and", "of", "for", "a", "an", "in", "at", "to", "with"}
_LEVELS = {"intern": 0, "internship": 0, "junior": 1, "entry": 1, "associate": 1, "mid": 2,
           "senior": 3, "staff": 4, "lead": 4, "principal": 5, "distinguished": 6}
_JUNIOR = ("intern", "internship", "junior", "new grad", "new graduate", "entry level")
_NOT_JUNIOR_AFTER_ASSOCIATE = {"director", "principal", "vice", "vp", "partner", "general"}
_SUFFIX_LEVEL_RE = re.compile(r"\b(?:I|II)(?=\s*(?:$|[,(|\-–—]))")  # "Engineer II", not "I/O" or "III"
_MANAGER = ("manager", "director", "head of", "vp", "vice president")
_AMER = {"US", "CA", "MX"}
_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
_PER = {"year": "/yr", "month": "/mo", "week": "/wk", "day": "/day", "hour": "/hr"}


def words(text):
    """Normalized title words: lowercase, no punctuation, front-end -> frontend, sr -> senior."""
    t = re.sub(r"front[\s-]*end", "frontend", (text or "").lower())
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(_ALIASES.get(w, w) for w in t.split()).split()


def has_phrase(ws, phrase):
    """True when the phrase's words appear in a row in ws (so matches are whole words only)."""
    pw = words(phrase)
    n = len(pw)
    return n > 0 and any(ws[i:i + n] == pw for i in range(len(ws) - n + 1))


def _place_check(job, p, cities):
    """(reason, flags, via) for one job or variant. reason None = passes; via is remote/local."""
    modes = p["work_modes"]
    remote_fail = None
    if job.get("remote") is True:
        if "remote" in modes:
            scope = set(job.get("remote_scope") or [])
            want = set(p["remote_scope"])
            if not scope:
                return None, [SCOPE_NOT_STATED], "remote"
            if not want or "ANY" in scope or want & scope:
                return None, [], "remote"
            if "AMER" in scope and want & _AMER:
                return None, [AMER_FLAG], "remote"
            remote_fail = "remote_scope"
        else:
            remote_fail = "work_mode"
    if ("hybrid" in modes or "onsite" in modes) and any(
            has_phrase(words(loc), c) for loc in job.get("locations") or [] for c in cities):
        wp = job.get("workplace")
        if wp is None:
            return None, [MODE_NOT_STATED], "local"
        if wp != "remote" and wp in modes:
            return None, [], "local"
        return remote_fail or "work_mode", [], None  # in a commute city, but not in a wanted mode
    return remote_fail or "location", [], None


def _pick_variant(job, p, cities):
    """Apply the variant the user can take: clean remote, then clean local, then flagged, else primary."""
    best = None
    for v in job.get("variants") or [{}]:
        row = dict(job)
        row.update(v)
        reason, flags, via = _place_check(row, p, cities)
        rank = 3 if reason else 2 if flags else 0 if via == "remote" else 1
        if best is None or rank < best[0]:
            best = (rank, row, reason, flags)
    return best[1:]


def _senior_only(seniority):
    """True when every wanted level is Senior or above. An unknown level word turns the rule off."""
    found = []
    for s in seniority:
        levels = [_LEVELS[w] for w in words(s) if w in _LEVELS]
        if not levels:
            return False
        found.append(min(levels))
    return bool(found) and min(found) >= _LEVELS["senior"]


def _too_junior(title, ws):
    if any(has_phrase(ws, x) for x in _JUNIOR):
        return True
    for i, w in enumerate(ws):
        if w == "associate" and (i + 1 == len(ws) or ws[i + 1] not in _NOT_JUNIOR_AFTER_ASSOCIATE) \
                and (i == 0 or ws[i - 1] not in _LEVEL_WORDS):
            return True
    return bool(_SUFFIX_LEVEL_RE.search(title))


def title_match(ws, p):
    """'strong', 'borderline' or None for normalized title words ws."""
    for role in p["target_roles"] + p["title_synonyms"]:
        need = [w for w in words(role) if w not in _LEVEL_WORDS]
        if need and all(w in ws for w in need):
            return "strong"
    if any(has_phrase(ws, k) for k in p["title_keywords"]):
        return "borderline"
    distinct = {w for role in p["target_roles"] for w in words(role)} - _GENERIC
    return "borderline" if distinct & set(ws) else None


def _pay_check(comp, p):
    """(removed?, flags, near_miss?) against base_pay_floor; only structured pay is compared."""
    floor = p.get("base_pay_floor")
    if not (isinstance(comp, dict) and (comp.get("min") is not None or comp.get("max") is not None)):
        if p.get("hide_no_pay"):
            return True, [], False
        return False, (["pay not listed"] if floor else []), False
    if not floor:
        return False, [], False
    currency = comp.get("currency") or "unknown currency"
    if currency.upper() != floor.get("currency", "USD").upper():
        return False, ["pay in %s" % currency], False
    if comp.get("interval") != floor.get("interval", "year"):
        return False, ["pay per %s" % comp["interval"] if comp.get("interval") else "pay period not stated"], False
    top = comp["max"] if comp.get("max") is not None else comp["min"]
    if top < floor["amount"]:
        return True, [], top >= 0.9 * floor["amount"]
    return False, [], False


def pay_text(comp):
    """'$190,000–$240,000/yr' from structured comp, else 'pay not listed'."""
    if not isinstance(comp, dict) or (comp.get("min") is None and comp.get("max") is None):
        return "pay not listed"
    cur = comp.get("currency") or ""
    sym = _SYMBOLS.get(cur.upper(), cur + " " if cur else "")
    lo, hi = comp.get("min"), comp.get("max")
    if lo is not None and hi is not None and lo != hi:
        amount = "%s%s–%s%s" % (sym, format(lo, ",.0f"), sym, format(hi, ",.0f"))
    elif lo is not None and hi is None:
        amount = "%s%s+" % (sym, format(lo, ",.0f"))
    elif lo is None:
        amount = "up to %s%s" % (sym, format(hi, ",.0f"))
    else:
        amount = "%s%s" % (sym, format(lo, ",.0f"))
    return amount + _PER.get(comp.get("interval"), "")


def _days_open(first_published, today):
    try:
        y, m, d = (int(x) for x in str(first_published)[:10].split("-"))
        return (today - datetime.date(y, m, d)).days
    except (TypeError, ValueError):
        return None


def _judge(job, p, ctx):
    """(removal reason or None, row with the display variant applied, near miss (priority, text) or None)."""
    if normalize.company_norm(job.get("company")) in ctx["excluded"]:
        return "company", job, None
    row, reason, flags = _pick_variant(job, p, ctx["cities"])
    title = row.get("title") or ""
    ws = words(title)
    excluded = next((x for x in p["title_exclusions"] if has_phrase(ws, x)), None)
    if reason:
        near = None
        strong = not excluded and title_match(ws, p) == "strong"
        if reason == "remote_scope" and strong:
            near = (2, "remote, but only in %s" % ", ".join(row.get("remote_scope") or []))
        elif reason == "location" and strong and row.get("locations"):
            near = (2, "%s in %s — outside your commute cities" % (row.get("workplace") or "onsite",
                                                                   row["locations"][0]))
        return reason, row, near
    if ctx["senior_only"] and _too_junior(title, ws):
        return "seniority", row, None
    if p["track"] == "ic" and any(has_phrase(ws, x) for x in _MANAGER):
        return "track", row, None
    match = title_match(ws, p)
    if excluded:
        # Only a title that would otherwise match is "close"; "Mechanical Technician" is just noise.
        # A borderline match ranks after scope misses: it is a weaker signal than a strong title.
        rank = 0 if match == "strong" else 3
        return "title_exclusion", row, ((rank, "title excluded: %s" % excluded) if match else None)
    if not match:
        return "title", row, None
    removed, pay_flags, close = _pay_check(row.get("comp"), p)
    if removed:
        return "pay_floor", row, ((1, "pay just under your floor") if close else None)
    flags = flags + pay_flags
    days = _days_open(row.get("first_published"), ctx["today"])
    if days is not None and days > p["recency_flag_days"]:
        flags.append("open over %d days" % p["recency_flag_days"])
    row["match"], row["flags"] = match, flags
    return None, row, None


def _rank_key(row):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(row.get("first_published") or ""))
    newest = -int("".join(m.groups())) if m else None  # negative, so newer dates sort first
    return (row["match"] != "strong", any(f in LOCATION_FLAGS for f in row["flags"]), newest is None, newest or 0)


def _where(row):
    locs = row.get("locations") or []
    if not locs:
        return "remote" if row.get("remote") else "not stated"
    return "; ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")


def run_filter(jobs, profile, limit=DEFAULT_LIMIT, today=None):
    """Apply every rule. Returns (stdout summary dict, ranked full candidate dicts capped at limit)."""
    p = state.with_profile_defaults(profile)
    limit = max(1, min(int(limit), MAX_LIMIT))
    home_city = (p.get("home_base") or "").split(",")[0].strip()
    ctx = {"excluded": {normalize.company_norm(c) for c in p["companies_exclude"]},
           "cities": [c for c in p["commute_cities"] + [home_city] if c.strip()],
           "senior_only": _senior_only(p["seniority"]),
           "today": today or datetime.date.today()}
    removed = dict.fromkeys(REASONS, 0)
    kept, near = [], []
    for job in jobs:
        reason, row, miss = _judge(job, p, ctx)
        if reason:
            removed[reason] += 1
            if miss:
                near.append((miss[0], len(near), row, miss[1]))
        else:
            kept.append(row)
    kept.sort(key=_rank_key)
    shown = kept[:limit]
    near.sort(key=lambda n: n[:2])
    summary = {
        "counts": {"input": len(jobs), "removed": removed, "candidates": len(kept)},
        "candidates": [{"key": r.get("key"), "company": r.get("company"), "title": r.get("title"),
                        "where": _where(r), "mode": r.get("workplace") or "unknown",
                        "since": r.get("first_published"), "pay": pay_text(r.get("comp")),
                        "match": r["match"], "flags": r["flags"]} for r in shown],
        "near_misses": [{"key": r.get("key"), "company": r.get("company"), "title": r.get("title"), "reason": why}
                        for _, _, r, why in near[:MAX_NEAR_MISSES]],
    }
    return summary, shown


def main(argv=None):
    ap = argparse.ArgumentParser(description="Filter a run's jobs against the saved profile.")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    profile = state.read_json(state.profile_path())
    if not isinstance(profile, dict):
        print(json.dumps({"error": "no profile saved — confirm the search brief first"}))
        return 2
    try:
        run = state.resolve_run(args.run)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"error": str(e)}))
        return 2
    jobs = state.read_json(run / "jobs.json")
    if not isinstance(jobs, list):
        print(json.dumps({"error": "run %s has no jobs.json — run probe.py first" % run.name}))
        return 2
    summary, candidates = run_filter(jobs, profile, args.limit)
    state.write_json_atomic(run / "candidates.json", candidates)
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
