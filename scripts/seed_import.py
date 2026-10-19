#!/usr/bin/env python3
"""Build skills/job-scout/data/companies.csv from corpHuntingMCP, kalil0321 + the 49 eval boards.

Purpose:
  Import the Greenhouse, Ashby, Lever, SmartRecruiters and Workday tenant slugs from
  corpHuntingMCP (github.com/ZmoleCristian/corpHuntingMCP, 0BSD, src/tenants/*.rs), add
  Workday boards from kalil0321/ats-scrapers (MIT, ats-companies/workday.csv), merge
  the 49 hand-checked eval boards from docs/reference/companies_seed.csv (with
  a hand-tagged sector), drop denylisted aggregators, dedupe on (ats, slug) exactly,
  and write one sorted CSV. New boards are marked status "unchecked"; a board already
  checked in the existing --out file keeps its status, jobs, shares and checked_at.

  Workday keeps one board per tenant (slug "<tenant>.<wdN>.<site>"): corpHuntingMCP's site
  first, else kalil0321's main site (kalil names a tenant's other sites "Company (Site)"),
  else its first. Rows the Workday adapter would reject are skipped and counted. A Workday
  board seed_check.py moved to another wdN host keeps that host on re-import.

Usage:
  python3 scripts/seed_import.py --fetch [--sha SHA] [--kalil-sha SHA]
  python3 scripts/seed_import.py --src DIR      # flat dir of .rs files, or a repo clone root
      [--kalil workday.csv]                     # kalil0321's list; without it, no kalil rows
      [--seed49 docs/reference/companies_seed.csv]
      [--denylist skills/job-scout/data/denylist.txt]
      [--out skills/job-scout/data/companies.csv]

What it does NOT do:
  It does not check that any board is live or has jobs (scripts/seed_check.py does
  that). It does not guess sectors for corpHuntingMCP rows ("unknown"), and it does
  not fix slugs: they are kept exactly as written (the ATS APIs can be case-sensitive).
  It does not read robots.txt to pick a Workday site: the import stays offline.
"""
import argparse
import csv
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "job-scout", "scripts"))
from adapters import workday  # noqa: E402

PINNED_SHA = "92fab3600f36d470f1bd4f1e84c06fcf5609ac86"
REPO = "ZmoleCristian/corpHuntingMCP"
KALIL_SHA = "6b44a1badc9bfbf5cf176f75265cc5729e520e99"
KALIL_URL = "https://raw.githubusercontent.com/kalil0321/ats-scrapers/%s/ats-companies/workday.csv"
USER_AGENT = "job-scout-seed-import (+https://github.com/sorawit-w/job-scout)"
ATS_MAP = {"Greenhouse": "greenhouse", "Ashby": "ashby", "Lever": "lever", "SmartRecruiters": "smartrecruiters"}
TENANT_RE = re.compile(r'Tenant \{ ats: Ats::(\w+), slug: "([^"]*)", company: "([^"]*)"')
FILE_RE = re.compile(r"^(?:(greenhouse|ashby|lever|smartrecruiters)_[^/]*|workday)\.rs$")
WORKDAY_RE = re.compile(r'Tenant \{ ats: Ats::Workday, slug: "[^"]*", company: "([^"]*)", host: "([^"]*)", site: "([^"]*)"')
WORKDAY_HOST = ".myworkdayjobs.com"
LOCALE_RE = re.compile(r"[a-z]{2}-[A-Z]{2}")
SITE_SUFFIX_RE = re.compile(r"\s*\([^()]*\)$")  # kalil's "Company (Site Name)" for a tenant's other sites
HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]
CHECK_COLS = ("status", "jobs", "us_share", "remote_share", "checked_at")  # written by seed_check.py

# Hand-tagged sectors for the 49 eval boards, keyed by slug.
SEED49_SECTORS = {
    "affirm": "fintech", "airtable": "productivity", "anthropic": "ai", "asana": "productivity",
    "ashby": "hr-tech", "attention": "ai", "brex": "fintech", "clerk": "devtools",
    "cloudflare": "infrastructure", "cursor": "devtools", "databricks": "data", "datadog": "devtools",
    "decagon": "ai", "discord": "consumer", "dropbox": "productivity", "elevenlabs": "ai",
    "figma": "design", "gitlab": "devtools", "givebutter": "fintech", "greenhouse": "hr-tech",
    "harvey": "legal-tech", "hex": "data", "linear": "productivity", "mercury": "fintech",
    "mintlify": "devtools", "modal": "infrastructure", "netlify": "devtools", "notion": "productivity",
    "openai": "ai", "perplexity": "ai", "plaid": "fintech", "posthog": "devtools",
    "ramp": "fintech", "replit": "devtools", "resend": "devtools", "riotgames": "gaming",
    "runway": "ai", "sentry": "devtools", "sierra": "ai", "stripe": "fintech",
    "supabase": "devtools", "twilio": "devtools", "vanta": "security", "vapi": "ai",
    "vercel": "devtools", "xai": "ai", "raycast": "devtools", "webflow": "design",
}


def parse_tenants(text):
    """Return [(ats, slug, company)] for the ATS_MAP tenant lines in a .rs file."""
    return [(ATS_MAP[a], s, c) for a, s, c in TENANT_RE.findall(text) if a in ATS_MAP]


def _workday_slug(host, site):
    """"<tenant>.<wdN>.myworkdayjobs.com" + site -> the adapter's slug, or None if the adapter rejects it."""
    if not host.endswith(WORKDAY_HOST):
        return None
    slug = "%s.%s" % (host[:-len(WORKDAY_HOST)], site)
    try:
        workday.site_url(slug)
    except ValueError:
        return None
    return slug


def _readable(tenant):
    return tenant.replace("-", " ").title()


def parse_workday_rs(text):
    """corpHuntingMCP workday.rs -> ([(slug, company)], invalid row count)."""
    rows, bad = [], 0
    for company, host, site in WORKDAY_RE.findall(text):
        slug = _workday_slug(host, site)
        if slug is None:
            bad += 1
        else:
            rows.append((slug, company or _readable(slug.split(".")[0])))
    return rows, bad


def parse_kalil_csv(text):
    """kalil0321 workday.csv (name,slug,url) -> ([(slug, company)] one per tenant, invalid row count).
    The site comes from the url (its slug column is lower-cased); a row without "(Site)" is the main site."""
    best, bad = {}, 0
    for r in csv.DictReader(text.splitlines()):
        u = urllib.parse.urlsplit(r.get("url") or "")
        parts = [p for p in u.path.split("/") if p]
        if parts and LOCALE_RE.fullmatch(parts[0]):
            parts = parts[1:]
        slug = _workday_slug(u.hostname or "", parts[0] if parts else "")
        if slug is None:
            bad += 1
            continue
        tenant, name = slug.split(".")[0], (r.get("name") or "").strip()
        main = not SITE_SUFFIX_RE.search(name)
        if tenant not in best or (main and not best[tenant][2]):
            best[tenant] = (slug, SITE_SUFFIX_RE.sub("", name) or _readable(tenant), main)
    return [(slug, company) for slug, company, _ in best.values()], bad


def pick_workday(corp, kalil):
    """One board per tenant, corpHuntingMCP's first -> [("workday", slug, company, source)]."""
    out = {}
    for rows, source in ((corp, "corphunting"), (kalil, "kalil0321")):
        for slug, company in rows:
            out.setdefault(slug.split(".")[0], ("workday", slug, company, source))
    return list(out.values())


def read_src(directory):
    texts = []
    for d in (directory, os.path.join(directory, "src", "tenants")):
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if FILE_RE.match(name):
                    with open(os.path.join(d, name), encoding="utf-8") as f:
                        texts.append(f.read())
    return texts


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8")


def fetch_texts(sha):
    """Download the tenant files at `sha`. Any HTTP/network error propagates."""
    tree = json.loads(_get("https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, sha)))
    if tree.get("truncated"):
        raise RuntimeError("GitHub tree listing was truncated")
    paths = [t["path"] for t in tree.get("tree", [])
             if t["path"].startswith("src/tenants/") and FILE_RE.match(t["path"][len("src/tenants/"):])]
    return [_get("https://raw.githubusercontent.com/%s/%s/%s" % (REPO, sha, p)) for p in sorted(paths)]


def read_seed49(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("ats") in ATS_MAP.values()]


def read_denylist(path):
    deny = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                ats, _, slug = line.partition(":")
                deny.add((ats.strip(), slug.strip()))
    return deny


def _row(company, ats, slug, sector, source):
    return {"company": company, "ats": ats, "slug": slug, "sector": sector, "status": "unchecked",
            "jobs": "", "us_share": "", "remote_share": "", "checked_at": "", "source": source}


def build_rows(tenants, seed49, denylist):
    """Merge, dedupe on exact (ats, slug), apply the denylist, sort. Returns (rows, stats)."""
    rows = {}
    for ats, slug, company, *source in tenants:
        rows.setdefault((ats, slug), _row(company, ats, slug, "unknown", source[0] if source else "corphunting"))
    overlap = 0
    for r in seed49:
        key = (r["ats"], r["slug"])
        prev = rows.get(key)
        overlap += prev is not None
        company = prev["company"] if prev and prev["source"] == "corphunting" else r["company"]
        rows[key] = _row(company, r["ats"], r["slug"], SEED49_SECTORS.get(r["slug"], "unknown"), "seed49")
    denied = [k for k in rows if k in denylist]
    for k in denied:
        del rows[k]
    out = sorted(rows.values(), key=lambda r: (r["ats"], r["slug"].lower(), r["slug"]))
    stats = {"seed49": len(seed49), "overlap": overlap, "denylisted": len(denied)}
    return out, stats


def _check_key(ats, slug):
    """Workday rows match without their wdN host, so a board seed_check.py moved keeps its new host."""
    if ats == "workday":
        tenant, _, rest = (slug or "").partition(".")
        return ats, tenant, rest.partition(".")[2]
    return ats, slug


def keep_checks(rows, path):
    """Copy seed_check results (and a moved Workday slug) from the existing CSV at `path`; returns how many."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8", newline="") as f:
        old = {_check_key(r.get("ats"), r.get("slug")): r for r in csv.DictReader(f)}
    kept = 0
    for row in rows:
        prev = old.get(_check_key(row["ats"], row["slug"]))
        if prev and prev.get("status", "unchecked") != "unchecked":
            row.update({k: prev.get(k, "") for k in CHECK_COLS + ("slug",)})
            kept += 1
    return kept


def write_csv(rows, path):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description="Import ATS board slugs into companies.csv.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--src", help="local dir with the tenant .rs files (or a repo clone root)")
    g.add_argument("--fetch", action="store_true", help="download the tenant files from GitHub at --sha")
    p.add_argument("--sha", default=PINNED_SHA)
    p.add_argument("--kalil", help="local kalil0321 workday.csv (with --src)")
    p.add_argument("--kalil-sha", default=KALIL_SHA)
    p.add_argument("--seed49", default="docs/reference/companies_seed.csv")
    p.add_argument("--denylist", default="skills/job-scout/data/denylist.txt")
    p.add_argument("--out", default="skills/job-scout/data/companies.csv")
    a = p.parse_args(argv)

    try:
        texts = fetch_texts(a.sha) if a.fetch else read_src(a.src)
        if a.fetch:
            kalil_text = _get(KALIL_URL % a.kalil_sha)
        elif a.kalil:
            with open(a.kalil, encoding="utf-8") as f:
                kalil_text = f.read()
        else:
            kalil_text = None
    except Exception as e:
        print("seed-import: fetch failed: %s" % e, file=sys.stderr)
        return 1
    tenants = [t for text in texts for t in parse_tenants(text)]
    corp, kalil, bad = [], [], 0
    for text in texts:
        got, n = parse_workday_rs(text)
        corp, bad = corp + got, bad + n
    if kalil_text is not None:
        kalil, n = parse_kalil_csv(kalil_text)
        bad += n
    wd = pick_workday(corp, kalil)
    tenants += wd
    missing = [k for k in list(ATS_MAP.values()) + ["workday"] if not any(t[0] == k for t in tenants)]
    if missing:
        print("seed-import: no %s tenants found; nothing written" % "/".join(missing), file=sys.stderr)
        return 1

    rows, stats = build_rows(tenants, read_seed49(a.seed49), read_denylist(a.denylist))
    kept = keep_checks(rows, a.out)
    write_csv(rows, a.out)
    n = {k: sum(r["ats"] == k for r in rows) for k in list(ATS_MAP.values()) + ["workday"]}
    by_source = {s: sum(t[3] == s for t in wd) for s in ("corphunting", "kalil0321")}
    print("seed-import: %d boards (greenhouse %d, ashby %d, lever %d, smartrecruiters %d, workday %d) · "
          "workday corphunting %d + kalil0321 %d, invalid skipped %d · seed49 %d (overlapping %d) · "
          "denylisted %d · kept checks %d · source %s%s" % (
              len(rows), n["greenhouse"], n["ashby"], n["lever"], n["smartrecruiters"], n["workday"],
              by_source["corphunting"], by_source["kalil0321"], bad,
              stats["seed49"], stats["overlap"], stats["denylisted"], kept, a.sha[:7],
              " + kalil0321 %s" % a.kalil_sha[:7] if kalil_text is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
