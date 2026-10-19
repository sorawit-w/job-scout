#!/usr/bin/env python3
"""Fetch job boards, normalize and collapse their jobs, and write a run file.

Usage (paths relative to the skill folder):
  python3 scripts/probe.py --health
  python3 scripts/probe.py [--max-boards 400] [--refresh] [--boards ats:slug,... | --boards FILE]

Stdout is one compact JSON summary; jobs go to ~/.job-scout/runs/<id>/jobs.json.
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


def select_boards(rows, profile=None, user_rows=(), max_boards=DEFAULT_MAX_BOARDS):
    """Ordered, deduped [(ats, slug, company)] — user companies, seed49, preferred sectors,
    US/remote share, then job count. Seed rows must be live or unchecked; user rows always count."""
    profile = profile or {}
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

    for row in user_rows:
        add(row)
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
    rest = sorted(eligible, key=lambda r: (-(_num(r.get("us_share")) + _num(r.get("remote_share"))), -_num(r.get("jobs"))))
    for row in rest:
        add(row)
    return picked[:max_boards]


def _probe_one(board, budget, refresh):
    ats, slug, company = board
    module = adapters.REGISTRY.get(ats)
    if module is None:
        return board, "error", None, "unknown ats %s" % ats, False
    try:
        raws = None if refresh else state.cache_get(ats, slug)
    except ValueError as e:  # unsafe slug from a data file: report it, never crash the run
        return board, "error", None, str(e), False
    if raws is not None:
        return board, ("live" if raws else "empty"), raws, None, True
    try:
        raws = module.fetch_board(slug, budget)
    except net.BudgetExceeded:
        return board, "capped", None, "request cap reached", False
    except net.Blocked as e:
        return board, "blocked", None, e.hint, False
    except net.NetError as e:
        return board, "error", None, str(e), False
    if raws is None:
        return board, "dead", None, None, False
    state.cache_put(ats, slug, raws)
    return board, ("live" if raws else "empty"), raws, None, False


def probe(boards, budget, refresh=False, denylist=frozenset()):
    """Fetch boards concurrently. Returns (summary dict, collapsed jobs list)."""
    summary = {"probed": 0, "cached": 0, "live": 0, "live_boards": [], "empty": [], "dead": [], "errors": [],
               "denylisted": 0}
    jobs, outcomes = [], []
    todo = []
    for board in boards:
        if "%s:%s" % (board[0], board[1]) in denylist:
            summary["denylisted"] += 1
        else:
            todo.append(board)
    with cf.ThreadPoolExecutor(max_workers=net.MAX_WORKERS) as pool:
        outcomes = list(pool.map(lambda b: _probe_one(b, budget, refresh), todo))
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
            summary["live_boards"].append(name)  # state.probed_ok_boards: only probed boards can close jobs
            module = adapters.REGISTRY[ats]
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

    try:
        if args.boards:
            boards = parse_boards(args.boards)[:MAX_BOARDS_CEILING]
            available = len(boards)
        else:
            rows = load_csv(args.companies)
            user_rows = load_csv(str(state.home() / "companies.csv"))
            profile = state.read_json(state.home() / "profile.json", {})
            limit = max(1, min(args.max_boards, MAX_BOARDS_CEILING))
            boards = select_boards(rows, profile, user_rows, limit)
            available = sum(1 for r in rows if r.get("status", "unchecked") in SELECTABLE)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2

    budget = net.Budget(len(boards) + RETRY_ALLOWANCE)
    summary, jobs = probe(boards, budget, refresh=args.refresh, denylist=load_denylist())
    run = state.new_run()
    state.write_json_atomic(run / "jobs.json", jobs)
    state.write_json_atomic(run / "boards.json", summary)
    out = {"run": run.name, "boards": {"selected": len(boards), "available": available, **{
        k: summary[k] for k in ("probed", "cached", "live", "empty", "dead", "errors")}},
        "jobs": summary["jobs"], "collapsed": summary["collapsed"], "denylisted": summary["denylisted"],
        "requests": budget.used}
    print(json.dumps(out))
    if summary["capped"]:
        return 4
    if summary["probed"] and summary["blocked"] == summary["probed"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
