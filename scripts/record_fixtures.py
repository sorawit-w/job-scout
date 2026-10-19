#!/usr/bin/env python3
"""Re-record the live HTTP fixtures the offline tests replay (tests/fixtures/http/).

Usage:
  python3 scripts/record_fixtures.py            # re-record everything in FIXTURES
  JOB_SCOUT_REPLAY_DIR=tests/fixtures/http python3 -m unittest ...   # how tests use them

Each fixture is the real response to one URL, saved by net.py's record mode under
sha1(url)[:16].json. Large board lists are trimmed to TRIM jobs after recording so the
repo stays small; trimmed files carry "trimmed": true.

What it does NOT do: it is not run in CI (it needs the network), and it never edits a
fixture except to trim a board list.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "skills", "job-scout", "scripts"))
import net  # noqa: E402

OUT = os.path.join(ROOT, "tests", "fixtures", "http")
TRIM = 3
GH = "https://boards-api.greenhouse.io/v1/boards/%s/jobs"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true"
LEVER = "https://api.lever.co/v0/postings/%s?mode=json"
# Single jobs the adapter tests read (ids were open on 2026-10-19; if one closes, pick a new
# open id from the same board and update the test that names it).
SINGLE_JOBS = [
    "https://boards-api.greenhouse.io/v1/boards/airtable/jobs/8403107002?pay_transparency=true",
    "https://boards-api.greenhouse.io/v1/boards/figma/jobs/5426468004?pay_transparency=true",
    "https://api.lever.co/v0/postings/airslate/9a4add3b-1bbc-453d-94da-502113da3c53?mode=json",
    "https://api.lever.co/v0/postings/airslate/00000000-0000-0000-0000-000000000000?mode=json",
]


def urls():
    out = list(net.HEALTH_URLS.values())
    out += [GH % "airtable" + "?content=true", GH % "webflow" + "?content=true",
            GH % "job-scout-no-such-board" + "?content=true",
            GH % "vercel" + "/1?pay_transparency=true"]
    out += [ASHBY % s for s in ("attention", "clerk", "raycast", "ramp", "job-scout-no-such-board")]
    out += [LEVER % s for s in ("airslate", "job-scout-no-such-board", "jobgether")]
    out += SINGLE_JOBS
    return out


def trim(path):
    if not os.path.exists(path):  # the request failed before any response was recorded
        return
    with open(path, encoding="utf-8") as f:
        fx = json.load(f)
    if not fx.get("body") or fx["status"] != 200:
        return
    body = json.loads(fx["body"])
    if isinstance(body, list) and len(body) > TRIM:
        body = body[:TRIM]
    elif isinstance(body, dict) and isinstance(body.get("jobs"), list) and len(body["jobs"]) > TRIM:
        body["jobs"] = body["jobs"][:TRIM]
    else:
        return
    fx["body"], fx["trimmed"] = json.dumps(body), True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fx, f, indent=1)
        f.write("\n")


def main():
    os.environ["JOB_SCOUT_RECORD_DIR"] = OUT
    os.environ.pop("JOB_SCOUT_REPLAY_DIR", None)
    extra = sys.argv[1:]  # optional extra URLs (e.g. a single job found below)
    for url in urls() + extra:
        try:
            net.get_json(url)
            status = "ok"
        except net.NetError as e:
            status = "error: %s" % e
        trim(os.path.join(OUT, net.fixture_key(url) + ".json"))
        print("%s  %s" % (status, url))


if __name__ == "__main__":
    main()
