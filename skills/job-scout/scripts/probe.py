#!/usr/bin/env python3
"""Fetch job boards, normalize and collapse their jobs, and write a run file.

Usage (paths relative to the skill folder):
  python3 scripts/probe.py --health
  python3 scripts/probe.py [--max-boards 400] [--refresh] [--boards ats:slug,... | --boards FILE]

Stdout is one compact JSON summary; jobs go to ~/.job-scout/runs/<id>/jobs.json.
Search sources (adapters with PARTIAL, e.g. Workday, USAJOBS) are searched with the brief's
target_roles then title_synonyms; only those titles leave the machine, and a search board is
listed under "partial_boards" so it never closes a saved role. An opt-in source with no key is
not asked and is named once under "skipped".
Exit codes: 0 ok · 2 usage · 3 network blocked (nothing reachable) · 4 request cap hit
(partial results written).

What it does NOT do: no filtering by the user's brief (filter.py), no job descriptions for
the shortlist (fetch_jd.py), and never more than MAX_BOARDS_CEILING boards per run.
"""
import argparse
import concurrent.futures as cf
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import adapters  # noqa: E402
import net  # noqa: E402
import normalize  # noqa: E402
import state  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
DEFAULT_MAX_BOARDS = 400
MAX_BOARDS_CEILING = 600
RETRY_ALLOWANCE = 100  # requests on top of one per board, for retries
SELECTABLE = ("live", "unchecked")
USAJOBS_BOARD = ("usajobs", "all", "USAJOBS")  # one cross-agency search, not a company board
# A brief is "tech" when its titles name one of these (whole words, any case); anything else is
# "general". Kept short on purpose: it only orders the last selection tier, it filters nothing.
TECH_WORDS = re.compile(r"\b(?:software|engineer|engineering|developer|programmer|data|design|designer|product|"
                        r"front[\s-]?end|back[\s-]?end|full[\s-]?stack|devops|ml|machine learning|"
                        r"security engineer(?:ing)?)\b", re.I)
# Last-tier order by hiring tool, per field; tools not named sort after the named ones.
# General puts Workday before SmartRecruiters: a Workday board answers with roles matching the
# brief's titles, while a SmartRecruiters board returns its whole list whatever the field.
FAMILY_RANK = {"tech": {"greenhouse": 0, "ashby": 0, "lever": 0, "smartrecruiters": 1, "workday": 2},
               "general": {"workday": 0, "smartrecruiters": 1}}


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_denylist(path=os.path.join(DATA, "denylist.txt")):
    out = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    out.add(line)
    return out


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def search_terms(profile):
    """The brief's target_roles, then title_synonyms: trimmed, no blanks, no repeats (any case)."""
    out, seen = [], set()
    for t in list(profile.get("target_roles") or []) + list(profile.get("title_synonyms") or []):
        t = t.strip() if isinstance(t, str) else ""
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def brief_field(profile):
    """"tech" when the brief's target_roles, title_synonyms or title_keywords match TECH_WORDS, else "general"."""
    titles = [t for k in ("target_roles", "title_synonyms", "title_keywords") for t in profile.get(k) or []
              if isinstance(t, str)]
    return "tech" if any(TECH_WORDS.search(t) for t in titles) else "general"


def select_boards(rows, profile=None, user_rows=(), max_boards=DEFAULT_MAX_BOARDS, usajobs=False):
    """Ordered, deduped [(ats, slug, company)] — user companies, seed49, preferred sectors, then the
    rest by hiring tool for the brief's field (FAMILY_RANK), US/remote share and job count. Seed rows
    must be live or unchecked; user rows always count. usajobs=True adds the USAJOBS search: right
    after user companies for a general brief, in the last slot for a tech brief."""
    profile = profile or {}
    field = brief_field(profile)
    include = {c.lower() for c in profile.get("companies_include") or []}
    exclude = {c.lower() for c in profile.get("companies_exclude") or []}
    sectors = {s.lower() for s in profile.get("industries_prefer") or []}
    picked, seen = [], set()

    def add(row):
        if not row.get("ats") or not row.get("slug"):
            return  # malformed row (e.g. a hand-edited ~/.job-scout/companies.csv)
        key = (row["ats"], row["slug"])
        if key in seen or row.get("company", "").lower() in exclude or row["slug"].lower() in exclude:
            return
        seen.add(key)
        picked.append((row["ats"], row["slug"], row.get("company") or row["slug"]))

    usa = dict(zip(("ats", "slug", "company"), USAJOBS_BOARD))
    for row in user_rows:
        add(row)
    if usajobs and field == "general":
        add(usa)
    eligible = [r for r in rows if r.get("status", "unchecked") in SELECTABLE]
    for row in eligible:
        if row.get("company", "").lower() in include or row["slug"].lower() in include:
            add(row)
    for row in eligible:
        if row.get("source") == "seed49":
            add(row)
    for row in eligible:
        if sectors and row.get("sector", "").lower() in sectors:
            add(row)
    rank = FAMILY_RANK[field]
    rest = sorted(eligible, key=lambda r: (rank.get(r.get("ats"), len(FAMILY_RANK["tech"])),
                                           -(_num(r.get("us_share")) + _num(r.get("remote_share"))), -_num(r.get("jobs"))))
    for row in rest:
        add(row)
    picked = picked[:max_boards]
    if usajobs and USAJOBS_BOARD not in picked:  # the user set a key: opted in, so keep it inside the cap
        picked = picked[:max_boards - 1] + [USAJOBS_BOARD]
    return picked


def _partial(module):
    return getattr(module, "PARTIAL", False)


def request_cap(boards, terms):
    """One request per board, every page of every term for a search board, plus RETRY_ALLOWANCE."""
    total = RETRY_ALLOWANCE
    for ats, _, _ in boards:
        module = adapters.REGISTRY.get(ats)
        if module is not None and _partial(module):
            total += min(len(terms), module.MAX_TERMS) * module.MAX_PAGES or 1  # no terms: one blank search page
        else:
            total += 1
    return total


def _probe_one(board, budget, refresh, terms=()):
    ats, slug, company = board
    module = adapters.REGISTRY.get(ats)
    if module is None:
        return board, "error", None, "unknown ats %s" % ats, False
    partial = _partial(module)
    try:
        # shortcut: a search board is never cached, since its result depends on the terms;
        # cache it keyed by the terms if reruns within the TTL spend too many requests.
        raws = None if refresh or partial else state.cache_get(ats, slug)
    except ValueError as e:  # unsafe slug from a data file: report it, never crash the run
        return board, "error", None, str(e), False
    if raws is not None:
        return board, ("live" if raws else "empty"), raws, None, True
    try:
        if partial:
            raws = module.fetch_board(slug, budget, terms=list(terms)[:module.MAX_TERMS])
        else:
            raws = module.fetch_board(slug, budget)
    except net.BudgetExceeded:
        return board, "capped", None, "request cap reached", False
    except net.Blocked as e:
        return board, "blocked", None, e.hint, False
    except net.NetError as e:
        return board, "error", None, str(e), False
    except ValueError as e:  # a slug the adapter rejects (search boards skip the cache's slug check)
        return board, "error", None, str(e), False
    if raws is None:
        return board, "dead", None, None, False
    if not partial:
        state.cache_put(ats, slug, raws)
    return board, ("live" if raws else "empty"), raws, None, False


def probe(boards, budget, refresh=False, denylist=frozenset(), terms=()):
    """Fetch boards concurrently; search boards (PARTIAL adapters) get `terms`.
    Returns (summary dict, collapsed jobs list)."""
    summary = {"probed": 0, "cached": 0, "live": 0, "live_boards": [], "partial_boards": [], "empty": [],
               "dead": [], "errors": [], "denylisted": 0}
    off = {ats for ats, m in adapters.REGISTRY.items() if callable(getattr(m, "enabled", None)) and not m.enabled()}
    summary["skipped"] = ["%s: no key" % ats for ats in sorted(off)]  # said once per run, picked or not
    jobs, outcomes = [], []
    todo = []
    for board in boards:
        if "%s:%s" % (board[0], board[1]) in denylist:
            summary["denylisted"] += 1
        elif board[0] not in off:
            todo.append(board)
    with cf.ThreadPoolExecutor(max_workers=net.MAX_WORKERS) as pool:
        outcomes = list(pool.map(lambda b: _probe_one(b, budget, refresh, terms), todo))
    capped = blocked = 0
    for (ats, slug, company), status, raws, err, cached in outcomes:
        name = "%s:%s" % (ats, slug)
        if status == "capped":
            capped += 1
            continue
        summary["probed"] += 1
        summary["cached"] += 1 if cached else 0
        if status == "live":
            summary["live"] += 1
            module = adapters.REGISTRY[ats]
            # state.probed_ok_boards reads live_boards: only a whole board, probed this run, closes jobs
            summary["partial_boards" if _partial(module) else "live_boards"].append(name)
            for raw in raws:
                try:
                    jobs.append(module.normalize(raw, slug, company))
                except (KeyError, TypeError, ValueError) as e:
                    summary["errors"].append({"board": name, "error": "bad job record: %s" % e})
            cap = getattr(module, "MAX_JOBS", None)  # paged adapters stop at a cap; older postings are unseen
            if cap and len(raws) >= cap:  # an error entry keeps it out of probed_ok_boards: unseen != closed
                summary["errors"].append({"board": name, "error": "list capped at %d jobs; not used to close roles" % cap})
        elif status == "empty":
            summary["empty"].append(name)
        elif status == "dead":
            summary["dead"].append(name)
        else:
            blocked += 1 if status == "blocked" else 0
            summary["errors"].append({"board": name, "error": err})
    summary["capped"] = capped
    summary["blocked"] = blocked
    summary["jobs"] = len(jobs)
    collapsed = normalize.collapse_variants(jobs)
    summary["collapsed"] = len(collapsed)
    return summary, collapsed


def parse_boards(spec):
    if os.path.exists(spec):
        with open(spec, encoding="utf-8") as f:
            items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        items = [s.strip() for s in spec.split(",") if s.strip()]
    out = []
    for item in items:
        ats, _, slug = item.partition(":")
        if not ats or not slug or "/" in slug or "\\" in slug or ".." in slug or slug.startswith("."):
            raise ValueError("bad board %r (want ats:slug)" % item)
        out.append((ats, slug, slug))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Probe job boards and write a run file.")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--max-boards", type=int, default=DEFAULT_MAX_BOARDS)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--boards")
    ap.add_argument("--companies", default=os.path.join(DATA, "companies.csv"))
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    if args.health:
        report = net.health(budget=net.Budget(len(net.HEALTH_URLS)))
        print(json.dumps(report))
        return 0 if report["ok"] else 3

    profile = state.read_json(state.home() / "profile.json", {})
    profile = profile if isinstance(profile, dict) else {}
    terms = search_terms(profile)
    try:
        if args.boards:
            boards = parse_boards(args.boards)[:MAX_BOARDS_CEILING]
            available = len(boards)
        else:
            rows = load_csv(args.companies)
            user_rows = load_csv(str(state.home() / "companies.csv"))
            limit = max(1, min(args.max_boards, MAX_BOARDS_CEILING))
            boards = select_boards(rows, profile, user_rows, limit, usajobs=adapters.usajobs.enabled())
            available = sum(1 for r in rows if r.get("status", "unchecked") in SELECTABLE)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2

    budget = net.Budget(request_cap(boards, terms))
    summary, jobs = probe(boards, budget, refresh=args.refresh, denylist=load_denylist(), terms=terms)
    run = state.new_run()
    state.write_json_atomic(run / "jobs.json", jobs)
    state.write_json_atomic(run / "boards.json", summary)
    out = {"run": run.name, "boards": {"selected": len(boards), "available": available, **{
        k: summary[k] for k in ("probed", "cached", "live", "empty", "dead", "errors")}},
        "jobs": summary["jobs"], "collapsed": summary["collapsed"], "denylisted": summary["denylisted"],
        "skipped": summary["skipped"], "requests": budget.used}
    print(json.dumps(out))
    if summary["capped"]:
        return 4
    if summary["probed"] and summary["blocked"] == summary["probed"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
