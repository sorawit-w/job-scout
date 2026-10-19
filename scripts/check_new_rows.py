#!/usr/bin/env python3
"""Live-check the company boards a pull request adds to companies.csv.

Usage (CI, from the repo root):
  git show origin/main:skills/job-scout/data/companies.csv > /tmp/base.csv
  python3 scripts/check_new_rows.py --base /tmp/base.csv [--head skills/job-scout/data/companies.csv]

A board is new when its (ats, slug) is not in the base file; a status or count change on an
existing board is not checked again. Each new board is checked once with seed_check.check_board
(the weekly seed check's own rule) and must come back "live". At most MAX_CHECKS new boards are
checked; the rest are listed as not checked and do not fail the run.
Exit codes: 0 every checked board is live (or nothing new) · 1 a new board is not live or uses a
hiring tool job-scout can't read.
"""
import argparse
import csv
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("seed_check", os.path.join(ROOT, "scripts", "seed_check.py"))
seed_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_check)

DEFAULT_COMPANIES = os.path.join(ROOT, "skills", "job-scout", "data", "companies.csv")
BOARD_ATS = {"greenhouse", "ashby", "lever", "smartrecruiters", "workday"}  # company boards, not USAJOBS search
MAX_CHECKS = 50


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default=DEFAULT_COMPANIES)
    args = ap.parse_args(argv)

    known = {(r.get("ats"), r.get("slug")) for r in read_rows(args.base)}
    new = [r for r in read_rows(args.head) if (r.get("ats"), r.get("slug")) not in known]
    if not new:
        print("check-new-rows: no new boards")
        return 0

    failed = 0
    hosts = seed_check.workday_hosts(read_rows(args.head))
    for i, row in enumerate(new):
        board = "%s:%s" % (row.get("ats"), row.get("slug"))
        if i >= MAX_CHECKS:
            print("%s not checked (over %d new boards)" % (board, MAX_CHECKS))
            continue
        if row.get("ats") not in BOARD_ATS or not row.get("slug") or not row.get("company"):
            print("%s FAIL: needs company, slug and one of %s" % (board, ", ".join(sorted(BOARD_ATS))))
            failed += 1
            continue
        status, jobs, _, _, error, slug = seed_check.check_board(row, hosts)
        line = "%s %s" % (board, status)
        if slug != row["slug"]:
            line += " (answers as %s:%s — use that slug)" % (row["ats"], slug)
        if error:
            line += " (%s)" % error
        if status != "live" or slug != row["slug"]:
            failed += 1
            line += " FAIL"
        print(line)
    print("check-new-rows: %d new · %d failed" % (len(new), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
