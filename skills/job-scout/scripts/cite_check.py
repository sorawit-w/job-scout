#!/usr/bin/env python3
"""Verify that every claim in the fit judgment quotes the job's live description.

Purpose:
    HANDOFF §6: every claim about a job must cite job-description text, and unknowns stay
    unknown. The LLM judgment step writes results.json; this script checks each why/risk
    quote is a contiguous substring of that job's FULL description in <run>/jds.json, after
    normalizing whitespace, curly quotes, dashes, non-breaking spaces and case.

Usage (paths relative to the skill folder):
    python3 scripts/cite_check.py [--run latest] < results.json

    results.json: {"rows": [{"key", "gates", "scores", "total",
                             "why": [{"text", "quote"}], "risk": [{"text", "quote"}]}]}
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
MIN_QUOTE = 12
_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-"})


def norm(s):
    """Collapse whitespace, straighten quotes, dashes to "-", nbsp to space, lowercase."""
    return re.sub(r"\s+", " ", s.translate(_TRANS)).strip().lower()


def problem(item, jd):
    """Why this why/risk item fails, or None when it is verified."""
    if not isinstance(jd, dict) or jd.get("status") != "open" or not jd.get("full"):
        return "no live job description for this key"
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

    checked, failed = 0, []
    for row in rows:
        key = row.get("key")
        jd = jds.get(key) if isinstance(key, str) else None
        for item in list(row.get("why") or []) + list(row.get("risk") or []):
            checked += 1
            why = problem(item, jd)
            if why:
                failed.append({"key": key, "quote": item.get("quote") if isinstance(item, dict) else None, "why": why})
    print(json.dumps({"ok": not failed, "checked": checked, "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
