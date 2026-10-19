#!/usr/bin/env python3
"""Score one job-scout run directory against a labeled ground-truth file (HANDOFF.md §11).

Usage:
  python3 scripts/score_run.py --gt docs/reference/ground_truth_2026-10-18.json --run <dir>
                               [--stage jobs|candidates|shortlist|results] [--top 15]
                               [--jobscope <_run.json>] [--json]

  jobs        every probed row (jobs.json)
  candidates  filter output, ranked (candidates.json)
  shortlist   candidates whose jds.json status is "open"
  results     results.json rows in order, resolved to full rows via candidates.json / jobs.json

Recall: a ground-truth role is found when any scored row, or any entry of a row's variants[],
has the same ats + slug, the exact title and the same first-published date. A role whose
board is absent from jobs.json is "not probed", not missing. --top N scores only the first N
rows of the stage. --jobscope scores a jobscope _run.json with the same rule (slug from id,
posted date), overall and within its top N by score (N = --top, default 15).

Also reported on the scored rows: links direct to the employer (host is not an aggregator),
exact duplicates (company + lowercase title + first_published seen more than once) and the
open share from jds.json when it exists.

What it does NOT do: no network calls (it reads only the files given); it does not label
ground truth — re-label the GT file by hand on the eval day.
"""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "job-scout", "scripts"))
from normalize import company_norm  # noqa: E402

STAGES = ("jobs", "candidates", "shortlist", "results")
AGGREGATORS = {"indeed", "linkedin", "ziprecruiter", "dice", "glassdoor", "builtin", "jobgether",
               "themuse", "simplyhired", "monster"}


def _load(run_dir, name):
    """Parsed <run_dir>/<name>.json, or None when the file is absent."""
    path = os.path.join(run_dir, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rows(data):
    return data["rows"] if isinstance(data, dict) else (data or [])


def _require(run_dir, name):
    data = _load(run_dir, name)
    if data is None:
        sys.exit(f"score_run: {name}.json not found in {run_dir}")
    return data


def stage_rows(run_dir, stage):
    """The rows a stage hands on, in order."""
    if stage == "jobs":
        return _rows(_require(run_dir, "jobs"))
    cands = _rows(_require(run_dir, "candidates")) if stage != "results" else _rows(_load(run_dir, "candidates"))
    if stage == "candidates":
        return cands
    if stage == "shortlist":
        jds = _require(run_dir, "jds")
        return [r for r in cands if (jds.get(r.get("key")) or {}).get("status") == "open"]
    by_key = {r.get("key"): r for r in _rows(_load(run_dir, "jobs"))}
    by_key.update({r.get("key"): r for r in cands})
    return [by_key.get(r.get("key"), r) for r in _rows(_require(run_dir, "results"))]


def _match_keys(rows):
    """(ats, slug, title, date) for every row and every variant; a variant inherits ats/slug from its key or row."""
    out = set()
    for r in rows:
        for v in [r] + list(r.get("variants") or []):
            parts = (v.get("key") or "").split(":")
            ats, slug = (parts[0], parts[1]) if len(parts) >= 3 else (r.get("ats"), r.get("slug"))
            out.add((ats, slug, (v.get("title") or "").strip(), (v.get("first_published") or "")[:10]))
    return out


def recall(roles, rows, probed=None):
    """found/total over GT roles; probed is the set of (ats, slug) boards in jobs.json (None = unknown)."""
    have = _match_keys(rows)
    missing, not_probed = [], []
    for g in roles:
        if (g["ats"], g["slug"], g["title"], g["first_published"]) in have:
            continue
        (not_probed if probed is not None and (g["ats"], g["slug"]) not in probed else missing).append(g)
    return {"found": len(roles) - len(missing) - len(not_probed), "total": len(roles),
            "missing": missing, "not_probed": not_probed}


def _direct(url):
    host = (urlparse(url or "").hostname or "").lower()
    return bool(host) and not AGGREGATORS & set(host.split("."))


def score(gt, run_dir, stage="jobs", top=None, jobscope=None):
    rows = stage_rows(run_dir, stage)[:top]
    jobs = _load(run_dir, "jobs")
    probed = {(r.get("ats"), r.get("slug")) for r in _rows(jobs)} if jobs is not None else None
    dup_keys = [(company_norm(r.get("company")), (r.get("title") or "").strip().lower(), r.get("first_published"))
                for r in rows]
    jds = _load(run_dir, "jds")
    checked = [jds[r["key"]] for r in rows if jds and r.get("key") in jds]
    res = {"stage": stage, "rows": len(rows), "recall": recall(gt["roles"], rows, probed),
           "links_direct": {"direct": sum(_direct(r.get("url")) for r in rows), "total": len(rows)},
           "duplicates": len(dup_keys) - len(set(dup_keys)),
           "open_share": {"open": sum(c.get("status") == "open" for c in checked), "checked": len(checked)}
           if jds is not None else None}
    if jobscope:
        res["jobscope"] = jobscope_recall(gt["roles"], jobscope, top or 15)
    return res


def jobscope_recall(roles, path, top=15):
    """GT recall of a jobscope _run.json: overall and within its top N by score."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    ranked = sorted((j for c in d["companies"] for j in c["jobs"]), key=lambda j: -(j.get("score") or 0))

    def found(jobs):
        have = {(j["id"].split(":")[1], (j.get("title") or "").strip(), (j.get("posted") or "")[:10]) for j in jobs}
        return sum((g["slug"], g["title"], g["first_published"]) in have for g in roles)

    return {"jobs": len(ranked), "found": found(ranked), "total": len(roles), "top": top,
            "found_in_top": found(ranked[:top])}


def _fmt_roles(roles):
    return "; ".join(f"{g['slug']} \"{g['title']}\" {g['first_published']}" for g in roles)


def render(res, top=None):
    rec = res["recall"]
    lines = [f"stage: {res['stage']} · rows scored: {res['rows']}" + (f" (top {top})" if top else ""),
             f"recall: {rec['found']}/{rec['total']} found · {len(rec['missing'])} missing · "
             f"{len(rec['not_probed'])} on boards not probed"]
    if rec["missing"]:
        lines.append(f"  missing: {_fmt_roles(rec['missing'])}")
    if rec["not_probed"]:
        lines.append(f"  not probed: {_fmt_roles(rec['not_probed'])}")
    ld = res["links_direct"]
    lines.append(f"links direct to employer: {ld['direct']}/{ld['total']}")
    lines.append(f"exact duplicates: {res['duplicates']}")
    op = res["open_share"]
    lines.append(f"open: {op['open']}/{op['checked']} checked" if op else "open: no jds.json")
    js = res.get("jobscope")
    if js:
        lines.append(f"jobscope: {js['found']}/{js['total']} in run file ({js['jobs']} roles) · "
                     f"{js['found_in_top']}/{js['total']} in its top {js['top']} by score")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score a job-scout run against ground truth.")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--stage", choices=STAGES, default="jobs")
    ap.add_argument("--top", type=int)
    ap.add_argument("--jobscope")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    with open(args.gt, encoding="utf-8") as f:
        gt = json.load(f)
    res = score(gt, args.run, args.stage, args.top, args.jobscope)
    print(json.dumps(res, indent=2) if args.json else render(res, args.top))


if __name__ == "__main__":
    main()
