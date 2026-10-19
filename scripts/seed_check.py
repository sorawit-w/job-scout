#!/usr/bin/env python3
"""Check every board in companies.csv and record whether it is live, unverified or dead.

Usage:
  python3 scripts/seed_check.py [--companies skills/job-scout/data/companies.csv]
                                [--only ats:slug,...] [--changed-only] [--workers 8]

  live        200 with at least one job  → jobs, us_share, remote_share filled
  unverified  200 with zero jobs (wrong slug or the company moved ATS) — never coverage;
              SmartRecruiters answers this way for an unknown company too (it never 404s a company)
  dead        404/410 (Workday: 404/410/422 on its own host and on every host the seed uses)
  error       network/HTTP failure → the row keeps its previous status

  jobs is what the adapter's list returned, so a SmartRecruiters board stops at its page cap
  (adapters/smartrecruiters.py MAX_JOBS) and a Workday board at its first search page (20), and
  neither is ever flagged as a possible aggregator.

  Workday: one blank search (fetch_board with no terms). Tenants move between wdN hosts and the
  old host answers 422, so a board that answers None is tried on every other host the seed uses,
  with the same site; when one answers, the row's slug is rewritten to that host ("moved"). The shares come
  from that first page's locationsText, so a "3 Locations" posting counts as neither US nor remote.

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
from adapters import workday  # noqa: E402

REGISTRY = adapters.REGISTRY
WORKDAY_HOSTS = ("wd1", "wd3", "wd5", "wd12", "wd103", "wd501", "wd503", "wd504")  # most common hosts

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


def workday_hosts(rows):
    """WORKDAY_HOSTS, then every other host a Workday row in the seed uses (a board can move to any)."""
    seen = [r["slug"].split(".")[1] for r in rows if r.get("ats") == "workday" and r.get("slug", "").count(".") >= 2]
    return WORKDAY_HOSTS + tuple(sorted(set(seen) - set(WORKDAY_HOSTS)))


def fetch(module, row, hosts=WORKDAY_HOSTS):
    """(raws, slug that answered). A Workday board that answers None (404/410/422) is tried on
    the other hosts with the same site — fetch_board maps all three to None, so a 404 costs the
    same extra tries as a moved board's 422."""
    raws = module.fetch_board(row["slug"])
    if raws is not None or row["ats"] != "workday":
        return raws, row["slug"]
    tenant, host, site = row["slug"].split(".", 2)
    for other in hosts:
        if other != host:
            slug = "%s.%s.%s" % (tenant, other, site)
            raws = module.fetch_board(slug)
            if raws is not None:
                return raws, slug
    return None, row["slug"]


def check_board(row, hosts=WORKDAY_HOSTS):
    """Return (status, jobs, us_share, remote_share, error, slug) for one CSV row; slug may be a new host."""
    module = REGISTRY.get(row["ats"])
    if module is None:
        return "error", None, None, None, "unknown ats %s" % row["ats"], row["slug"]
    try:
        raws, slug = fetch(module, row, hosts)
    except net.NetError as e:
        return "error", None, None, None, str(e), row["slug"]
    if raws is None:
        return "dead", "", "", "", None, slug
    if not raws:
        return "unverified", "0", "", "", None, slug
    jobs = []
    for raw in raws:
        try:
            jobs.append(module.normalize(raw, slug, row["company"]))
        except (KeyError, TypeError, ValueError):
            continue
    us, remote = shares(jobs)
    return "live", str(len(raws)), str(us), str(remote), None, slug


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
        hosts = workday_hosts(rows)
        results = list(pool.map(lambda r: check_board(r, hosts), todo))

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    counts = {"live": 0, "unverified": 0, "dead": 0, "error": 0}
    flagged, errors, moved = [], [], 0
    for row, (status, jobs, us, remote, err, slug) in zip(todo, results):
        counts[status] += 1
        if status == "error":
            errors.append("%s:%s — %s" % (row["ats"], row["slug"], err))
            continue  # keep the previous status
        moved += slug != row["slug"]
        row.update({"slug": slug, "status": status, "jobs": jobs, "us_share": us, "remote_share": remote,
                    "checked_at": today})
        if jobs and int(jobs) > AGGREGATOR_JOBS:
            flagged.append("%s:%s (%s jobs)" % (row["ats"], row["slug"], jobs))

    share = counts["error"] / len(todo)
    print("seed-check: %d boards · live %d · unverified %d · dead %d · errors %d (%.0f%%)%s" % (
        len(todo), counts["live"], counts["unverified"], counts["dead"], counts["error"], share * 100,
        " · moved %d" % moved if moved else ""))
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
