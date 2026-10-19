#!/usr/bin/env python3
"""Build skills/job-scout/data/companies.csv from corpHuntingMCP + the 49 eval boards.

Purpose:
  Import the Greenhouse, Ashby, Lever and SmartRecruiters tenant slugs from
  corpHuntingMCP (github.com/ZmoleCristian/corpHuntingMCP, 0BSD, src/tenants/*.rs),
  merge the 49 hand-checked eval boards from docs/reference/companies_seed.csv (with
  a hand-tagged sector), drop denylisted aggregators, dedupe on (ats, slug) exactly,
  and write one sorted CSV. New boards are marked status "unchecked"; a board already
  checked in the existing --out file keeps its status, jobs, shares and checked_at.

Usage:
  python3 scripts/seed_import.py --fetch [--sha SHA]
  python3 scripts/seed_import.py --src DIR      # flat dir of .rs files, or a repo clone root
      [--seed49 docs/reference/companies_seed.csv]
      [--denylist skills/job-scout/data/denylist.txt]
      [--out skills/job-scout/data/companies.csv]

What it does NOT do:
  It does not check that any board is live or has jobs (scripts/seed_check.py does
  that). It does not guess sectors for corpHuntingMCP rows ("unknown"), and it does
  not fix slugs: they are kept exactly as written (the ATS APIs can be case-sensitive).
"""
import argparse
import csv
import json
import os
import re
import sys
import tempfile
import urllib.request

PINNED_SHA = "92fab3600f36d470f1bd4f1e84c06fcf5609ac86"
REPO = "ZmoleCristian/corpHuntingMCP"
USER_AGENT = "job-scout-seed-import (+https://github.com/sorawit-w/job-scout)"
ATS_MAP = {"Greenhouse": "greenhouse", "Ashby": "ashby", "Lever": "lever", "SmartRecruiters": "smartrecruiters"}
TENANT_RE = re.compile(r'Tenant \{ ats: Ats::(\w+), slug: "([^"]*)", company: "([^"]*)"')
FILE_RE = re.compile(r"^(greenhouse|ashby|lever|smartrecruiters)_[^/]*\.rs$")
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
    for ats, slug, company in tenants:
        rows.setdefault((ats, slug), _row(company, ats, slug, "unknown", "corphunting"))
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


def keep_checks(rows, path):
    """Copy seed_check results from the existing CSV at `path` onto matching rows; returns how many."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8", newline="") as f:
        old = {(r.get("ats"), r.get("slug")): r for r in csv.DictReader(f)}
    kept = 0
    for row in rows:
        prev = old.get((row["ats"], row["slug"]))
        if prev and prev.get("status", "unchecked") != "unchecked":
            row.update({k: prev.get(k, "") for k in CHECK_COLS})
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
    p.add_argument("--seed49", default="docs/reference/companies_seed.csv")
    p.add_argument("--denylist", default="skills/job-scout/data/denylist.txt")
    p.add_argument("--out", default="skills/job-scout/data/companies.csv")
    a = p.parse_args(argv)

    try:
        texts = fetch_texts(a.sha) if a.fetch else read_src(a.src)
    except Exception as e:
        print("seed-import: fetch failed: %s" % e, file=sys.stderr)
        return 1
    tenants = [t for text in texts for t in parse_tenants(text)]
    missing = [k for k in ATS_MAP.values() if not any(t[0] == k for t in tenants)]
    if missing:
        print("seed-import: no %s tenants found; nothing written" % "/".join(missing), file=sys.stderr)
        return 1

    rows, stats = build_rows(tenants, read_seed49(a.seed49), read_denylist(a.denylist))
    kept = keep_checks(rows, a.out)
    write_csv(rows, a.out)
    n = {k: sum(r["ats"] == k for r in rows) for k in ATS_MAP.values()}
    print("seed-import: %d boards (greenhouse %d, ashby %d, lever %d, smartrecruiters %d) · seed49 %d "
          "(overlapping %d) · denylisted %d · kept checks %d · source %s" % (
              len(rows), n["greenhouse"], n["ashby"], n["lever"], n["smartrecruiters"],
              stats["seed49"], stats["overlap"], stats["denylisted"], kept, a.sha[:7]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
