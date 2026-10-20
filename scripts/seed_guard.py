#!/usr/bin/env python3
"""Decide whether a weekly seed-check update is routine enough to merge without a human.

Usage:
  python3 scripts/seed_guard.py --base BASE.csv [--new skills/job-scout/data/companies.csv]

  Compares the companies.csv on main (BASE) with the one seed_check.py just wrote (NEW).
  seed_check.py edits rows in place and never adds or removes one, so rows are paired by
  position (a Workday board that moved host keeps its place but changes its slug).

  Routine means all of these hold:
    * fewer than 1% of all boards changed status;
    * the number of live boards dropped by less than 1%;
    * no hiring tool (ashby, greenhouse, ...) lost more than 5% of its live boards.
  Job counts and shares can move freely: that is what the weekly check is for.

  Stdout: one summary line, then one line per reason it is not routine.
  Exit codes: 0 routine · 1 needs a human · 2 bad input (missing file, rows added or removed).

What it does NOT do: it never edits either file, and it never decides about aggregators
(the workflow log still lists those for a human).
"""
import argparse
import collections
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_NEW = os.path.join(ROOT, "skills", "job-scout", "data", "companies.csv")
MAX_STATUS_CHANGE = 0.01  # share of all boards
MAX_LIVE_DROP = 0.01      # share of live boards, net
MAX_ATS_LOSS = 0.05       # share of one tool's live boards that stopped being live


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def review(base, new):
    """(summary, reasons) for two row lists of the same length; no reasons means routine."""
    changed = sum(1 for o, n in zip(base, new) if o.get("status") != n.get("status"))
    live_before = sum(1 for r in base if r.get("status") == "live")
    live_after = sum(1 for r in new if r.get("status") == "live")
    was_live, lost = collections.Counter(), collections.Counter()
    for o, n in zip(base, new):
        if o.get("status") == "live":
            was_live[o.get("ats")] += 1
            if n.get("status") != "live":
                lost[o.get("ats")] += 1
    reasons = []
    if base and changed / len(base) >= MAX_STATUS_CHANGE:
        reasons.append("%d of %d boards changed status (%.1f%%; the limit is under %d%%)" % (
            changed, len(base), 100.0 * changed / len(base), MAX_STATUS_CHANGE * 100))
    if live_before and (live_before - live_after) / live_before >= MAX_LIVE_DROP:
        reasons.append("live boards dropped from %d to %d (%.1f%%; the limit is under %d%%)" % (
            live_before, live_after, 100.0 * (live_before - live_after) / live_before, MAX_LIVE_DROP * 100))
    for ats in sorted(was_live):
        if lost[ats] / was_live[ats] > MAX_ATS_LOSS:
            reasons.append("%s: %d of %d live boards stopped being live (%.1f%%; the limit is %d%%)" % (
                ats, lost[ats], was_live[ats], 100.0 * lost[ats] / was_live[ats], MAX_ATS_LOSS * 100))
    summary = "seed-guard: %d boards · %d changed status · live %d → %d" % (len(base), changed, live_before, live_after)
    return summary, reasons


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="companies.csv as it is on main")
    ap.add_argument("--new", default=DEFAULT_NEW, help="companies.csv after seed_check.py")
    args = ap.parse_args(argv)
    try:
        base, new = load(args.base), load(args.new)
    except OSError as e:
        print("seed-guard: %s" % e)
        return 2
    if len(base) != len(new):
        print("seed-guard: row count changed (%d → %d); seed_check never adds or removes rows" % (len(base), len(new)))
        return 2
    summary, reasons = review(base, new)
    print(summary + (" · routine" if not reasons else " · needs review"))
    for r in reasons:
        print("  " + r)
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
