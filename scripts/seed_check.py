#!/usr/bin/env python3
"""Check every board in companies.csv and record whether it is live, unverified or dead.

Usage:
  python3 scripts/seed_check.py [--companies skills/job-scout/data/companies.csv]
                                [--only ats:slug,...] [--changed-only] [--workers 8]

  live        200 with at least one job  → jobs, us_share, remote_share filled
  unverified  200 with zero jobs (wrong slug or the company moved ATS) — never coverage;
              SmartRecruiters answers this way for an unknown company too (it never 404s a company)
  dead        404/410
  error       network/HTTP failure → the row keeps its previous status

  jobs is what the adapter's list returned, so a SmartRecruiters board stops at its page cap
  (adapters/smartrecruiters.py MAX_JOBS) and is never flagged as a possible aggregator.

If more than 10% of the checked boards error, nothing is written (exit 1), so a bad
network day can't wipe the seed. --changed-only checks only rows whose status is
"unchecked" (new rows from imports or contributors).

What it does NOT do: it never deletes rows, never edits the denylist (boards with more
than AGGREGATOR_JOBS jobs are only flagged for a human), and never caches.
"""
import argparse
import concurrent.futures as cf
import csv
import datetime
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "job-scout", "scripts"))
import adapters  # noqa: E402
import net  # noqa: E402

DEFAULT_COMPANIES = os.path.join(ROOT, "skills", "job-scout", "data", "companies.csv")
ERROR_ABORT_SHARE = 0.10
AGGREGATOR_JOBS = 2000
US_SCOPES = {"US", "AMER", "ANY"}


def shares(jobs):
    """(us_share, remote_share) over normalized jobs, rounded to 2 places."""
    if not jobs:
        return 0.0, 0.0
    us = sum(1 for j in jobs if "US" in j["countries"] or US_SCOPES & set(j["remote_scope"] or []))
    remote = sum(1 for j in jobs if j["remote"])
    return round(us / len(jobs), 2), round(remote / len(jobs), 2)


def check_board(row):
    """Return (status, jobs, us_share, remote_share, error) for one CSV row."""
    module = adapters.REGISTRY.get(row["ats"])
    if module is None:
        return "error", None, None, None, "unknown ats %s" % row["ats"]
    try:
        raws = module.fetch_board(row["slug"])
    except net.NetError as e:
        return "error", None, None, None, str(e)
    if raws is None:
        return "dead", "", "", "", None
    if not raws:
        return "unverified", "0", "", "", None
    jobs = []
    for raw in raws:
        try:
            jobs.append(module.normalize(raw, row["slug"], row["company"]))
        except (KeyError, TypeError, ValueError):
            continue
    us, remote = shares(jobs)
    return "live", str(len(raws)), str(us), str(remote), None


def write_csv(rows, fieldnames, path):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--companies", default=DEFAULT_COMPANIES)
    ap.add_argument("--only", help="comma-separated ats:slug list")
    ap.add_argument("--changed-only", action="store_true")
    ap.add_argument("--workers", type=int, default=net.MAX_WORKERS)
    args = ap.parse_args(argv)

    with open(args.companies, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames, rows = reader.fieldnames, list(reader)
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    todo = [r for r in rows
            if (only is None or "%s:%s" % (r["ats"], r["slug"]) in only)
            and (not args.changed_only or r.get("status") == "unchecked")]
    if not todo:
        print("seed-check: nothing to check")
        return 0

    workers = max(1, min(args.workers, net.MAX_WORKERS))
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(check_board, todo))

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    counts = {"live": 0, "unverified": 0, "dead": 0, "error": 0}
    flagged, errors = [], []
    for row, (status, jobs, us, remote, err) in zip(todo, results):
        counts[status] += 1
        if status == "error":
            errors.append("%s:%s — %s" % (row["ats"], row["slug"], err))
            continue  # keep the previous status
        row.update({"status": status, "jobs": jobs, "us_share": us, "remote_share": remote, "checked_at": today})
        if jobs and int(jobs) > AGGREGATOR_JOBS:
            flagged.append("%s:%s (%s jobs)" % (row["ats"], row["slug"], jobs))

    share = counts["error"] / len(todo)
    print("seed-check: %d boards · live %d · unverified %d · dead %d · errors %d (%.0f%%)" % (
        len(todo), counts["live"], counts["unverified"], counts["dead"], counts["error"], share * 100))
    for line in errors[:20]:
        print("  error: " + line)
    for line in flagged:
        print("  possible aggregator (review for denylist.txt): " + line)
    if share > ERROR_ABORT_SHARE:
        print("seed-check: aborted — more than %d%% of boards errored; %s left unchanged" % (
            ERROR_ABORT_SHARE * 100, os.path.relpath(args.companies, ROOT)))
        return 1
    write_csv(rows, fieldnames, args.companies)
    return 0


if __name__ == "__main__":
    sys.exit(main())
