#!/usr/bin/env python3
"""Verify that every claim in the fit judgment quotes the job's live description.

Purpose:
    HANDOFF §6: every claim about a job must cite job-description text, and unknowns stay
    unknown. The LLM judgment step writes results.json; this script checks each why/risk
    quote is a contiguous substring of that job's FULL description in <run>/jds.json, after
    normalizing whitespace, curly quotes, dashes, non-breaking spaces and case.

Usage (paths relative to the skill folder):
    python3 scripts/cite_check.py [--run latest] < results.json

    results.json: {"rows": [{"key", "show", "gates", "scores", "total",
                             "why": [{"text", "quote"}], "risk": [{"text", "quote"}],
                             "style": [{"topic", "verdict", "text", "quote"}]}]}
    A style item's topic is a work_style topic and its verdict match / conflict / not_stated;
    match and conflict need a quote, not_stated has quote null (rubric §4). Each shown row needs
    exactly one style item per topic in the run's work_style (state.run_profile), and none for others.
    Each row's key must have an open job description in jds.json, and a row with show: true
    needs at least one why item; each failing row is reported once, with quote null.
    Stdout: {"ok": bool, "checked": n, "failed": [{"key", "quote", "why"}]}
    Exit codes: 0 all quotes verified · 1 any failure · 2 bad input JSON or no run.

What it does NOT do:
    * Does not judge whether a quote supports its claim — only that the quote is real.
    * Does not check against the trimmed text: a quote that jumps across a "…" join passes
      only if it is contiguous in the full description.
    * Never fixes or rewrites a quote; the judgment step re-reads the description instead.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state  # noqa: E402

UNKNOWN_LABELS = ("pay not listed", "sponsorship not stated", "location unclear")
NO_JD = "no live job description for this key"
MIN_QUOTE = 12
VERDICTS = ("match", "conflict", "not_stated")
_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-"})


def norm(s):
    """Collapse whitespace, straighten quotes, dashes to "-", nbsp to space, lowercase."""
    return re.sub(r"\s+", " ", s.translate(_TRANS)).strip().lower()


def live(jd):
    """True when jds.json has an open entry with a full description."""
    return isinstance(jd, dict) and jd.get("status") == "open" and bool(jd.get("full"))


def problem(item, jd):
    """Why this why/risk item fails, or None when it is verified."""
    if not live(jd):
        return NO_JD
    if not isinstance(item, dict):
        return "item must be an object with text and quote"
    quote, text = item.get("quote"), item.get("text")
    if not quote:
        if isinstance(text, str) and text.strip().lower() in UNKNOWN_LABELS:
            return None
        return "missing quote (only %s may have no quote)" % ", ".join('"%s"' % l for l in UNKNOWN_LABELS)
    if not isinstance(quote, str):
        return "quote must be a string"
    q = norm(quote)
    if len(q) < MIN_QUOTE:
        return "quote too short to verify"
    if q not in norm(jd["full"]):
        return "quote not found in the job description"
    return None


def style_problem(item, jd):
    """Why this work-style item fails, or None: match/conflict need a verified quote, not_stated none."""
    if not live(jd):
        return NO_JD
    if not (isinstance(item, dict) and isinstance(item.get("topic"), str) and item["topic"] in state.WORK_STYLE
            and item.get("verdict") in VERDICTS):
        return "style item must be {topic: %s, verdict: %s, text, quote}" % ("/".join(state.WORK_STYLE), "/".join(VERDICTS))
    if item["verdict"] == "not_stated":
        return None if item.get("quote") is None else "a not_stated item has no quote"
    if not item.get("quote"):
        return "a %s item needs a quote from the job description" % item["verdict"]
    return problem(item, jd)


def style_coverage(style, wanted):
    """Why a shown row's style items don't cover the saved work_style topics exactly once, or None."""
    got = [i["topic"] for i in style if isinstance(i, dict) and isinstance(i.get("topic"), str)]
    gaps = [("missing for", sorted(wanted - set(got))),
            ("given for topics the user did not set", sorted(set(got) - wanted)),
            ("given more than once for", sorted({t for t in got if t and got.count(t) > 1}))]
    gaps = ["style %s: %s" % (what, ", ".join(map(str, topics))) for what, topics in gaps if topics]
    return "; ".join(gaps) or None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check results.json quotes against the live job descriptions.")
    ap.add_argument("--run", default="latest")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        data = json.loads(sys.stdin.read())
    except ValueError as e:
        print(json.dumps({"ok": False, "error": "invalid JSON: %s" % e}))
        return 2
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        print(json.dumps({"ok": False, "error": 'expected {"rows": [{"key", "why", "risk", ...}]}'}))
        return 2
    try:
        run = state.resolve_run(args.run)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    jds = state.read_json(run / "jds.json", {})
    if not isinstance(jds, dict):
        jds = {}
    profile = state.run_profile(run)  # the work_style this run was judged against
    saved = profile.get("work_style") if isinstance(profile, dict) else None
    wanted = {t for t in saved if t in state.WORK_STYLE} if isinstance(saved, dict) else set()

    checked, failed = 0, []
    for row in rows:
        key = row.get("key")
        jd = jds.get(key) if isinstance(key, str) else None
        lists = {f: row.get(f) if isinstance(row.get(f), list) else [] for f in ("why", "risk", "style")}
        bad = [f for f in lists if row.get(f) not in (None, []) and not isinstance(row.get(f), list)]
        if bad:  # valid JSON of the wrong shape: report it, never crash
            failed.append({"key": key, "quote": None, "why": "%s must be a list" % " and ".join(bad)})
        items, style = lists["why"] + lists["risk"], lists["style"]
        checked += len(items) + len(style)
        if not live(jd):  # one failure per row, even with no items to check
            failed.append({"key": key, "quote": None, "why": NO_JD})
            continue
        if row.get("show") is True and not row.get("why"):
            failed.append({"key": key, "quote": None, "why": "shown row has no quoted reason"})
        gap = style_coverage(style, wanted) if row.get("show") is True else (
            "excluded row has style items (rubric §4: shown rows only)" if style else None)
        if gap:
            failed.append({"key": key, "quote": None, "why": gap})
        for item, check in [(i, problem) for i in items] + [(i, style_problem) for i in style]:
            why = check(item, jd)
            if why:
                failed.append({"key": key, "quote": item.get("quote") if isinstance(item, dict) else None, "why": why})
    print(json.dumps({"ok": not failed, "checked": checked, "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
