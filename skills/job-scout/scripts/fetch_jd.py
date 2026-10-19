#!/usr/bin/env python3
"""Live-check the shortlist and fetch each job's description for the fit judgment step.

Purpose:
    For each chosen row of <run>/candidates.json, ask the employer's ATS whether the job is
    still open (HANDOFF §9: never show a job as open without a live check this run, or a
    board cache younger than the TTL — Ashby's fetch_job uses that cache). Open jobs get their
    full description and pay re-read from the ATS (Greenhouse pay exists only on the single-job
    endpoint) and a verbatim trimmed copy for the LLM to quote from.

Usage (paths relative to the skill folder):
    python3 scripts/fetch_jd.py [--run latest] --top [N]        # first N rows (default 40, max 60)
    python3 scripts/fetch_jd.py [--run latest] --keys k1,k2,...  # rows by key

    Writes <run>/jds.json (merged with any existing file):
      {key: {status: open|closed|unverified, full, trimmed, comp, checked_at, error}}
    Stdout is one JSON object: {jobs: [open jobs, with "jd" = trimmed text], closed: [...],
    unverified: [{key, error}], requests: n}.
    Exit codes: 0 ok · 2 usage (no run / no candidates.json / neither --keys nor --top) ·
    4 request budget hit (what was checked is still written).

What it does NOT do:
    * No judging or scoring — that is the LLM step in SKILL.md; cite_check.py verifies its quotes.
    * Never rewords description text: trim_jd only selects whole lines, so quotes stay checkable.
    * Never treats a network error as open or closed — that row is "unverified".
    * Never parses pay out of description text; comp comes only from ATS pay fields.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adapters  # noqa: E402
import net  # noqa: E402
import state  # noqa: E402

DEFAULT_JOBS = 40
MAX_JOBS = 60
RETRY_ALLOWANCE = 10
JOIN = "\n…\n"

_SECTION_RE = re.compile(
    r"requirement|qualification|what you(?:['’]ll| will) do|responsibilit|about you|you have|must have|"
    r"nice to have|compensation|salary|\bpay\b|location|remote|hybrid|visa|sponsor|work authori", re.I)
# Benefits sections are not kept whole; their pay lines are caught here by the money amount.
_LINE_RE = re.compile(r"[$€£]\s?\d|sponsor|\bvisa|authori[sz]ation|\bremote|\bhybrid|on-?site|relocat", re.I)


def _is_heading(lines, i):
    """A short, non-bullet line that opens a block (after a blank line) or ends with a colon."""
    s = lines[i].strip()
    if not s or len(s) > 80 or s[0] in "-•*" or s.endswith("."):
        return False
    return s.endswith(":") or i == 0 or not lines[i - 1].strip()


def trim_jd(text, limit=2500):
    """Verbatim lines most useful for judging fit, in original order, blocks joined by "\\n…\\n"."""
    if not text:
        return None
    lines = text.split("\n")
    keep, in_section = [], False
    for i, line in enumerate(lines):
        if _is_heading(lines, i):
            in_section = bool(_SECTION_RE.search(line))
        keep.append(in_section or bool(_LINE_RE.search(line)))
    blocks, run = [], []
    for line, kept in zip(lines + [""], keep + [False]):
        if kept:
            run.append(line)
            continue
        block = "\n".join(run).strip("\n")
        if block.strip():
            blocks.append(block)
        run = []
    if not blocks:
        return text[:limit]
    out = JOIN.join(blocks)
    if len(out) > limit:
        cut = out[:limit + 1].rfind("\n")
        out = out[:cut] if cut > 0 else out[:limit]
        if out.endswith("\n…"):
            out = out[:-2]
    return out


def check(row, budget):
    """One live check -> jds.json entry. Raises net.BudgetExceeded for the caller to stop on."""
    entry = {"status": "unverified", "full": None, "trimmed": None, "comp": None,
             "checked_at": state.now_iso(), "error": None}
    module = adapters.REGISTRY.get(row.get("ats"))
    if module is None or not row.get("slug") or not row.get("job_id"):
        entry["error"] = "bad candidate row (ats, slug or job_id missing or unknown)"
        return entry
    try:
        raw = module.fetch_job(row["slug"], row["job_id"], budget)
    except net.BudgetExceeded:
        raise
    except net.NetError as e:
        entry["error"] = str(e)
        return entry
    if raw is None:
        entry["status"] = "closed"
        return entry
    try:
        job = module.normalize(raw, row["slug"], row.get("company") or row["slug"])
    except (KeyError, TypeError, ValueError) as e:
        entry["error"] = "bad job record: %s" % e
        return entry
    full = job.get("description_text")
    entry.update(status="open", full=full, trimmed=trim_jd(full), comp=job.get("comp"))
    return entry


def _fail(message):
    print(json.dumps({"error": message}))
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="Live-check shortlisted jobs and fetch their descriptions.")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--keys")
    ap.add_argument("--top", type=int, nargs="?", const=DEFAULT_JOBS)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not args.keys and args.top is None:
        return _fail("give --keys k1,k2,... or --top N")
    try:
        run = state.resolve_run(args.run)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    rows = state.read_json(run / "candidates.json")
    if not isinstance(rows, list):
        return _fail("no readable candidates.json in run %s (run filter.py first)" % run.name)
    rows = [r for r in rows if isinstance(r, dict) and r.get("key")]

    unverified = []
    if args.keys:
        by_key = {r["key"]: r for r in rows}
        wanted = list(dict.fromkeys(k.strip() for k in args.keys.split(",") if k.strip()))
        unverified += [{"key": k, "error": "unknown key: not in candidates.json"} for k in wanted if k not in by_key]
        selected = [by_key[k] for k in wanted if k in by_key]
    else:
        selected = rows[:max(args.top, 0)]
    selected = selected[:MAX_JOBS]

    budget = net.Budget(len(selected) + RETRY_ALLOWANCE)
    jds_path = run / "jds.json"
    jds = state.read_json(jds_path, {})
    if not isinstance(jds, dict):
        jds = {}
    jobs, closed, capped = [], [], False
    # shortcut: sequential, so jobs on one Ashby board share its cached list; use a pool if 60 is too slow.
    for i, row in enumerate(selected):
        try:
            entry = check(row, budget)
        except net.BudgetExceeded:
            capped = True
            unverified += [{"key": r["key"], "error": "not checked: request budget used up"} for r in selected[i:]]
            break
        jds[row["key"]] = entry
        if entry["status"] == "open":
            job = {k: row.get(k) for k in ("key", "company", "title", "url", "locations", "workplace",
                                           "remote_scope", "first_published")}
            job.update(comp=entry["comp"], status="open", jd=entry["trimmed"])
            jobs.append(job)
        elif entry["status"] == "closed":
            closed.append({"key": row["key"], "company": row.get("company"), "title": row.get("title")})
        else:
            unverified.append({"key": row["key"], "error": entry["error"]})
    state.write_json_atomic(jds_path, jds)
    print(json.dumps({"jobs": jobs, "closed": closed, "unverified": unverified, "requests": budget.used},
                     ensure_ascii=False))
    return 4 if capped else 0


if __name__ == "__main__":
    sys.exit(main())
