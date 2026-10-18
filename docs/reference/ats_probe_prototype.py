# PROTOTYPE (written in a claude.ai chat, 2026-10-18). Verified working against live
# Greenhouse / Ashby / Lever public job-board APIs that day. Reference only: rewrite into
# scripts/probe.py with caching, a normalized schema, fixtures, and tests (see HANDOFF.md §5).
# Usage: python3 ats_probe_prototype.py gh:vercel ashby:linear lever:<site>
import json, re, sys, concurrent.futures as cf
from datetime import datetime, timezone, timedelta
import urllib.request

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=7)
UA = {"User-Agent": "Mozilla/5.0 (job-search-research)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def greenhouse(slug):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    out = []
    for j in d.get("jobs", []):
        pub = j.get("first_published") or j.get("updated_at")
        out.append(dict(title=j["title"], loc=(j.get("location") or {}).get("name",""),
                        published=pub, url=j.get("absolute_url"), id=str(j["id"])))
    return out

def ashby(slug):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in d.get("jobs", []):
        locs = [j.get("location","")] + [s.get("location","") for s in j.get("secondaryLocations",[]) or []]
        if j.get("isRemote"): locs.append("Remote")
        out.append(dict(title=j["title"], loc=" | ".join(l for l in locs if l),
                        published=j.get("publishedAt"), url=j.get("jobUrl"), id=j.get("id")))
    return out

def lever(slug):
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for j in d:
        ts = j.get("createdAt")
        pub = datetime.fromtimestamp(ts/1000, tz=timezone.utc).isoformat() if ts else None
        out.append(dict(title=j["text"], loc=(j.get("categories") or {}).get("location",""),
                        published=pub, url=j.get("hostedUrl"), id=j.get("id")))
    return out

FN = {"gh": greenhouse, "ashby": ashby, "lever": lever}

def parse(ts):
    if not ts: return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def probe(pair):
    ats, slug = pair
    try:
        return pair, FN[ats](slug), None
    except Exception as e:
        return pair, [], f"{type(e).__name__}: {e}"[:80]

if __name__ == "__main__":
    pairs = [tuple(p.split(":")) for p in sys.argv[1:]]
    with cf.ThreadPoolExecutor(12) as ex:
        results = list(ex.map(probe, pairs))
    json.dump([{"ats":a,"slug":s,"jobs":jobs,"err":err} for (a,s),jobs,err in results],
              open("ats_raw.json","w"), indent=1)
    for (a,s),jobs,err in results:
        print(f"{a}:{s:16s} jobs={len(jobs):4d} {('ERR '+err) if err else ''}")
