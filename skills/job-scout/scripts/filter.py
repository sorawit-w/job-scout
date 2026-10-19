#!/usr/bin/env python3
"""Hard filters and a title prefilter: turn a run's jobs.json into a ranked candidates.json.

Usage (paths relative to the skill folder):
  python3 scripts/filter.py [--run latest|<run-id>] [--limit 150] [--all]

Reads <run>/jobs.json (written by probe.py), the saved profile (~/.job-scout/profile.json) and
seen.json (via state.py). Writes <run>/candidates.json (full job dicts plus match, flags and
state, ranked, at most --limit) and prints one compact JSON object:
  {"counts": {"input", "removed": {reason: n}, "candidates"},
   "candidates": [{key, company, title, where, mode, since, pay, match, flags, state}],
   "near_misses": [{key, company, title, reason}]}
state is new | changed | saved | applied | seen | dismissed (no seen.json: all new).
Exit codes: 0 ok · 2 no profile, no run, no jobs.json, unreadable seen.json (left unchanged,
nothing written), or bad arguments.

Rules, in order (the first rule a job fails is its removal reason): company exclude ->
display-variant pick -> work mode / location / remote scope (open_to_relocation keeps a wanted-mode
or unknown-mode job elsewhere in the home or remote-scope countries, flagged) -> seniority -> track
-> title exclusions -> title prefilter (strong / borderline) -> pay floor (structured pay only;
Greenhouse lists no pay, so its pay is checked after fetch_jd).
Old postings are flagged ("open over N days"), never removed.
Rerun (seen.json has entries), after every rule above: unchanged seen roles are removed as
"already_seen", applied and dismissed ones as "dismissed_or_applied"; new, changed and saved stay.
--all keeps them all (still tagged). Ranking puts new and changed before saved (then the rest),
keeping the usual order within each group. removed + candidates always equals input.

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

import adapters  # noqa: E402
import normalize  # noqa: E402
import state  # noqa: E402

DEFAULT_LIMIT = 150
MAX_LIMIT = 300
MAX_NEAR_MISSES = 5
REASONS = ("work_mode", "location", "remote_scope", "seniority", "track", "company", "title",
           "title_exclusion", "pay_floor",
           "already_seen", "dismissed_or_applied")
_STATE_TIER = {"new": 0, "changed": 0, "saved": 1}  # everything else (only shown with --all) after
_RERUN_DROP = {"seen": "already_seen", "applied": "dismissed_or_applied", "dismissed": "dismissed_or_applied"}
SCOPE_NOT_STATED = "remote scope not stated"
AMER_FLAG = "Americas — check US eligibility"
MODE_NOT_STATED = "work mode not stated"
RELOCATE_FLAG = "relocation: %s in %s"
DESC_FLAG = "title is generic — matched on the description"
MODE_ON_DETAIL_FLAG = "work mode unknown — checked on the live job"
LOCATION_ON_DETAIL_FLAG = "location not listed — checked on the live job"
LOCATION_FLAGS = (SCOPE_NOT_STATED, AMER_FLAG, MODE_NOT_STATED, MODE_ON_DETAIL_FLAG, LOCATION_ON_DETAIL_FLAG)
# Hiring tools whose board list never states a work mode, and may give only a location count
# (adapters with MODE_ON_DETAIL): fetch_jd.py re-filters their rows on the detail record.
_MODE_ON_DETAIL = {name for name, m in adapters.REGISTRY.items() if getattr(m, "MODE_ON_DETAIL", False)}

_ALIASES = {"sr": "senior", "jr": "junior", "swe": "software engineer", "eng": "engineer"}
_LEVEL_WORDS = {"senior", "staff", "lead", "principal"}  # ignored when matching a target role
_GENERIC = {"engineer", "engineering", "software", "developer", "senior", "staff", "lead", "principal",
            "manager", "the", "and", "of", "for", "a", "an", "in", "at", "to", "with"}
_WEAK = {"systems", "system", "platform", "product", "data", "infrastructure", "technical", "solutions"}  # too common to match alone
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


def _place_check(job, p, ctx):
    """(reason, flags, via) for one job or variant. reason None = passes; via is remote/local."""
    modes, cities = p["work_modes"], ctx["cities"]
    remote_fail = None
    if job.get("remote") is True:
        if "remote" in modes:
            scope = set(job.get("remote_scope") or [])
            want = set(p["remote_scope"])
            if not scope:
                return None, [SCOPE_NOT_STATED], "remote"
            if not want or "ANY" in want or "ANY" in scope or want & scope or ("AMER" in want and scope & _AMER):
                return None, [], "remote"
            if "AMER" in scope and want & _AMER:
                return None, [AMER_FLAG], "remote"
            remote_fail = "remote_scope"
        else:
            remote_fail = "work_mode"
    if ("hybrid" in modes or "onsite" in modes) and any(
            has_phrase(words(loc), city) and not (states and states.isdisjoint(normalize.us_states(loc) or states))
            for loc in job.get("locations") or [] for city, states in cities):  # "Lincoln, NE" for a CA home
        wp = job.get("workplace")
        if wp is None:
            return None, [MODE_NOT_STATED], "local"
        if wp != "remote" and wp in modes:
            return None, [], "local"
        return remote_fail or "work_mode", [], None  # in a commute city, but not in a wanted mode
    wp, allowed = job.get("workplace"), ctx["relocate"]
    if allowed is not None and job.get("countries") and (not allowed or allowed & set(job["countries"])):
        locs = job.get("locations") or ["?"]
        where = next((loc for loc in locs if normalize.place_codes(loc)), locs[0])  # not "Hybrid"
        if wp is None and ("hybrid" in modes or "onsite" in modes):
            return None, [MODE_NOT_STATED, RELOCATE_FLAG % ("onsite or hybrid", where)], "local"
        if wp in ("hybrid", "onsite") and wp in modes:
            return None, [RELOCATE_FLAG % (wp, where)], "local"
    if job.get("ats") in _MODE_ON_DETAIL and job.get("remote") is None and not job.get("locations"):
        return None, [LOCATION_ON_DETAIL_FLAG], "local"  # "3 Locations": the detail record lists them
    if ("remote" in modes and job.get("ats") in _MODE_ON_DETAIL and job.get("remote") is None
            and wp is None and _scope_could_fit(job, p["remote_scope"])):
        return None, [MODE_ON_DETAIL_FLAG], "remote"
    return remote_fail or "location", [], None


def _scope_could_fit(job, want):
    """False only when the job's locations name countries all outside the wanted remote scope."""
    codes = {c for loc in job.get("locations") or [] for c in normalize.place_codes(loc)}
    want = set(want)
    return (not want or "ANY" in want or not codes or bool(codes & want)
            or ("AMER" in want and bool(codes & _AMER)))


def _relocation_countries(p):
    """None when not relocating or no country resolves; else the countries they would move within
    (empty set = anywhere, only for "ANY" in remote_scope)."""
    if not p["open_to_relocation"]:
        return None
    if "ANY" in p["remote_scope"]:
        return frozenset()
    home = normalize.place_codes(p.get("home_base") or "")
    wanted = set(home) | set(p["remote_scope"]) | (_AMER if "AMER" in p["remote_scope"] else set())
    # shortcut: only AMER expands to countries; other regions need the ROADMAP region map.
    return frozenset(c for c in wanted if c not in normalize.REGION_CODES) or None


def _pick_variant(job, p, ctx):
    """Apply the variant the user can take: clean remote, then clean local, then flagged, else primary."""
    best = None
    for v in job.get("variants") or [{}]:
        row = dict(job)
        row.update(v)
        reason, flags, via = _place_check(row, p, ctx)
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
        # Adjacent words, either order for two-word roles ("Software Engineer, Frontend"), so
        # "AV Engineer, Builds and Design" is not a design engineer.
        if need and (has_phrase(ws, " ".join(need)) or (len(need) == 2 and has_phrase(ws, " ".join(need[::-1])))):
            return "strong"
    if any(has_phrase(ws, k) for k in p["title_keywords"]):
        return "borderline"
    distinct = {w for role in p["target_roles"] for w in words(role)} - _GENERIC - _WEAK
    return "borderline" if distinct & set(ws) else None


def _description_match(ws, row, p):
    """An engineering title that matched nothing ("Staff Software Engineer, Product") whose description
    names at least three of the brief's title keywords. Keywords under 4 letters ("ui", "web") are too
    common in descriptions to count; two keywords let in too many backend roles that mention React."""
    return bool({"engineer", "developer"} & set(ws)) and _desc_hits(row, p) >= 3


def _desc_hits(row, p):
    """How many distinct title keywords (4+ letters) the description names — a relevance signal."""
    text = " %s " % " ".join(words(row.get("description_text") or ""))
    found = {t for t in (" ".join(words(k)) for k in p["title_keywords"] if len(k) >= 4) if " %s " % t in text}
    return len({t for t in found if not any(t != o and t in o for o in found)})  # "design system(s)" counts once


def _pay_check(comp, p, ats=None):
    """(removed?, flags, near_miss?) against base_pay_floor; only structured pay is compared."""
    floor = p.get("base_pay_floor")
    if not (isinstance(comp, dict) and (comp.get("min") is not None or comp.get("max") is not None)):
        if ats == "greenhouse":  # Greenhouse pay is only on the single-job endpoint; checked after fetch_jd
            return False, [], False
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
    row, reason, flags = _pick_variant(job, p, ctx)
    title = row.get("title") or ""
    ws = words(title)
    excluded = next((x for x in p["title_exclusions"] if has_phrase(ws, x)), None)
    if reason:
        near = None
        strong = not excluded and title_match(ws, p) == "strong"
        if reason == "remote_scope" and strong:
            near = (2, "remote, but only in %s" % ", ".join(row.get("remote_scope") or []))
        elif reason == "location" and strong and row.get("locations"):
            wp = row.get("workplace") or "onsite"
            why = "outside your commute cities" if wp in p["work_modes"] else "%s is not a mode you picked" % wp
            near = (2, "%s in %s — %s" % (wp, row["locations"][0], why))
        return reason, row, near
    if ctx["senior_only"] and _too_junior(title, ws):
        return "seniority", row, None
    if p["track"] == "ic" and any(has_phrase(ws, x) for x in ctx["manager"]):
        return "track", row, None
    match = title_match(ws, p)
    if excluded:
        # Only a title that would otherwise match is "close"; "Mechanical Technician" is just noise.
        # A borderline match ranks after scope misses: it is a weaker signal than a strong title.
        rank = 0 if match == "strong" else 3
        return "title_exclusion", row, ((rank, "title excluded: %s" % excluded) if match else None)
    if not match and _description_match(ws, row, p):
        match, flags = "borderline", flags + [DESC_FLAG]
    if not match:
        return "title", row, None
    removed, pay_flags, close = _pay_check(row.get("comp"), p, row.get("ats"))
    if removed:
        return "pay_floor", row, ((1, "pay just under your floor") if close else None)
    flags = flags + pay_flags
    days = _days_open(row.get("first_published"), ctx["today"])
    if days is not None and days > p["recency_flag_days"]:
        flags.append("open over %d days" % p["recency_flag_days"])
    row["match"], row["flags"] = match, flags
    return None, row, None


def _rank_key(row, p):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(row.get("first_published") or ""))
    newest = -int("".join(m.groups())) if m else None  # negative, so newer dates sort first
    on_detail = any(f in (MODE_ON_DETAIL_FLAG, LOCATION_ON_DETAIL_FLAG) for f in row["flags"])  # unconfirmed fit: last
    return (_STATE_TIER.get(row["state"], 2), on_detail, row["match"] != "strong",
            any(f in LOCATION_FLAGS or f.startswith("relocation:") for f in row["flags"]),
            -_desc_hits(row, p), newest is None, newest or 0)


def _where(row):
    locs = row.get("locations") or []
    if not locs:
        return "remote" if row.get("remote") else "not stated"
    return "; ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")


def run_filter(jobs, profile, limit=DEFAULT_LIMIT, today=None, seen=None, show_all=False):
    """Apply every rule. Returns (stdout summary dict, ranked full candidate dicts capped at limit).
    seen is seen.json's content; empty or None is a first run (nothing dropped, all "new")."""
    p = state.with_profile_defaults(profile)
    limit = max(1, min(int(limit), MAX_LIMIT))
    home_states = normalize.us_states(p.get("home_base") or "")
    ctx = {"excluded": {normalize.company_norm(c) for c in p["companies_exclude"]},
           # (city, states a job there may name): a commute city's own state ("Jersey City, NJ"),
           # else the home base's; an empty set means no state check.
           "cities": [(c.split(",")[0].strip(), normalize.us_states(c) if "," in c else home_states)
                      for c in p["commute_cities"] + [p.get("home_base") or ""] if c.split(",")[0].strip()],
           "senior_only": _senior_only(p["seniority"]),
           "relocate": _relocation_countries(p),
           # A "Product Manager" target keeps "manager" titles: only phrases not in their own roles count.
           "manager": [x for x in _MANAGER
                       if not any(has_phrase(words(r), x) for r in p["target_roles"] + p["title_synonyms"])],
           "today": today or datetime.date.today()}
    seen = seen or {}
    index = state.seen_index(seen)
    removed = dict.fromkeys(REASONS, 0)
    kept, near = [], []
    for job in jobs:
        reason, row, miss = _judge(job, p, ctx)
        if not reason:
            row["state"] = state.job_state(job, seen, index)  # the collapsed job: same sig as record()
            reason = None if show_all else _RERUN_DROP.get(row["state"])
        if reason:
            removed[reason] += 1
            if miss:
                near.append((miss[0], len(near), row, miss[1]))
        else:
            kept.append(row)
    kept.sort(key=lambda r: _rank_key(r, p))
    shown = kept[:limit]
    near.sort(key=lambda n: n[:2])
    summary = {
        "counts": {"input": len(jobs), "removed": removed, "candidates": len(kept)},
        "candidates": [{"key": r.get("key"), "company": r.get("company"), "title": r.get("title"),
                        "where": _where(r), "mode": r.get("workplace") or "unknown",
                        "since": r.get("first_published"), "pay": pay_text(r.get("comp")),
                        "match": r["match"], "flags": r["flags"], "state": r["state"]} for r in shown],
        "near_misses": [{"key": r.get("key"), "company": r.get("company"), "title": r.get("title"), "reason": why}
                        for _, _, r, why in near[:MAX_NEAR_MISSES]],
    }
    return summary, shown


def main(argv=None):
    ap = argparse.ArgumentParser(description="Filter a run's jobs against the saved profile.")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--all", action="store_true", help="on a rerun, also show seen, applied and dismissed roles")
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
    try:
        seen = state.load_seen()
    except ValueError as e:  # never fall back to a first run: that would show every seen role as new
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2
    summary, candidates = run_filter(jobs, profile, args.limit, seen=seen, show_all=args.all)
    state.write_json_atomic(run / "candidates.json", candidates)
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
