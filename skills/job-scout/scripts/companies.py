#!/usr/bin/env python3
"""Companies the user wants job-scout to always check ("also check Linear and Figma").

Purpose:
  Find each named company's job board — first in the shipped seed (data/companies.csv,
  0 requests), else by guessing slugs on Greenhouse, Ashby and Lever — and save the hits to
  ~/.job-scout/companies.csv, which probe.py always checks first. For a guessed board the
  seed lacks, print the CSV row and a short issue body the user could contribute.

Usage (paths relative to the skill folder):
  python3 scripts/companies.py add "Linear" "Figma" [--refresh]   # 1-5 names
  python3 scripts/companies.py add "Acme" --board greenhouse:acme  # one name, a board the user knows
  python3 scripts/companies.py list
  python3 scripts/companies.py remove "Linear"

  --refresh  do not trust the seed: re-fetch the seed's boards for the name, then guess
             slugs if none of them has jobs.
  --board    fetch exactly this ATS:SLUG board (no seed, no guessing); saved when it has ≥1 job.

A guessed board (from "guess") or a --board board (from "board") carries sample_titles (up to
3) and sample_url: a guessed slug can belong to a different company with the same name, so the
agent shows them and asks the user to confirm (or run `remove`). The hit is still saved.

Stdout is one JSON object. Exit codes: 0 ok (even if some names were not found) · 2 usage ·
3 network blocked (no request got an answer) · 4 request cap hit (partial results printed,
hits so far saved).

What it does NOT do: it never writes into the repo and never opens a GitHub issue (it only
prints the row and text), tries at most MAX_TRIES boards per company (and stops after
MAX_BLOCKED_IN_A_ROW blocked requests in a row), never confirms that a guessed board is the
right company (the user does), and leaves sector and US/remote shares blank
(scripts/seed_check.py fills those for contributed rows).
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import adapters  # noqa: E402
import net  # noqa: E402
import normalize  # noqa: E402
import state  # noqa: E402

from adapters import _common  # noqa: E402

SEED = os.path.join(os.path.dirname(HERE), "data", "companies.csv")
HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]
ATS_ORDER = ("greenhouse", "ashby", "lever")
MAX_NAMES = 5
MAX_NAME_LEN = 80
MAX_TRIES = 15  # boards tried per company, across all three ATS
RETRY_ALLOWANCE = 15  # requests on top of MAX_TRIES per name, for net.py's one retry
MAX_BLOCKED_IN_A_ROW = 3  # a blocked network fails every guess; stop instead of trying all 15
MAX_SAMPLES = 3
SUFFIXES = ("inc", "labs", "hq", "ai", "technologies")


def user_path():
    return state.home() / "companies.csv"


def load_csv(path):
    if not os.path.exists(str(path)):
        return []
    with open(str(path), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path, rows):
    """Temp file + fsync + os.replace (as state.write_json_atomic), so probe.py never reads half a file."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore", restval="")
            w.writeheader()
            w.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def check_name(raw):
    """Stripped name, or ValueError: 1-MAX_NAME_LEN chars and no path separators."""
    name = (raw or "").strip()
    if not 1 <= len(name) <= MAX_NAME_LEN or "/" in name or "\\" in name:
        raise ValueError("bad company name %r (want 1-%d characters, no / or \\)" % (raw, MAX_NAME_LEN))
    return name


def _words(name):
    base = name.lower().strip()
    if base.endswith(".com"):
        base = base[:-4]
    words = re.findall(r"[a-z0-9]+", base)
    core = list(words)
    while len(core) > 1 and core[-1] in SUFFIXES:
        core.pop()
    return words, core


def slug_guesses(name):
    """Joined and hyphenated forms of the name, then without SUFFIXES, then <core>hq / <core>-hq."""
    words, core = _words(name)
    if not core:
        return []
    out = []
    for g in ("".join(words), "-".join(words), "".join(core), "-".join(core), "".join(core) + "hq", "-".join(core) + "-hq"):
        if g not in out:
            out.append(g)
    return out


def plan_tries(name, seed_rows):
    """[(ats, slug)] to fetch in order: the given seed boards, then each guess on every ATS."""
    tries = []
    for pair in [(r["ats"], r["slug"]) for r in seed_rows] + [(a, g) for g in slug_guesses(name) for a in ATS_ORDER]:
        if pair not in tries:
            tries.append(pair)
    return tries[:MAX_TRIES]


def seed_matches(name, seed):
    """Seed rows for this name (same company_norm, or slug equal to the name's slug form), live first."""
    key = normalize.company_norm(name)
    words, _ = _words(name)
    forms = {"".join(words), "-".join(words)} - {""}
    rows = [r for r in seed if r.get("ats") in adapters.REGISTRY and r.get("slug")
            and (normalize.company_norm(r.get("company")) == key or r["slug"].lower() in forms)]
    return sorted(rows, key=lambda r: r.get("status") != "live")


def _jobs(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _csv_line(row):
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", restval="", lineterminator="").writerow(row)
    return buf.getvalue()


def _issue_text(row, line):
    board_url = adapters.REGISTRY[row["ats"]].BASE % _common.quote_slug(row["slug"])
    return ("Please add %s to skills/job-scout/data/companies.csv. job-scout found a public %s job board "
            "that looks like %s's, with %s open jobs on %s (%s); please confirm it belongs to this company "
            "before adding it. The company is not in the seed list yet. "
            "Suggested row: %s" % (row["company"], row["ats"].capitalize(), row["company"], row["jobs"],
                                   row["checked_at"], board_url, line))


def _samples(ats, slug, name, raws):
    """{sample_titles, sample_url} from a board's first jobs, so the user can tell whose board it is."""
    titles, url = [], None
    for raw in raws[:MAX_SAMPLES]:
        try:
            job = adapters.REGISTRY[ats].normalize(raw, slug, name)
        except (KeyError, TypeError, ValueError):  # as probe.py: one bad record never sinks the board
            continue
        if job.get("title"):
            titles.append(job["title"])
        url = url or job.get("url")
    return {"sample_titles": titles, "sample_url": url}


def find_one(name, seed, seed_keys, budget, refresh, stats, board=None):
    """One name -> (result dict, rows to save). Raises nothing but lets BudgetExceeded mark the result.
    board=(ats, slug) fetches only that board (--board), skipping the seed and slug guesses."""
    result = {"name": name, "hits": [], "tried": [], "saved": False, "suggest_row": None, "errors": []}
    if board:
        tries = [board]
    else:
        matches = seed_matches(name, seed)
        live = [r for r in matches if r.get("status") == "live"]
        if matches and not refresh:
            shown = live or matches
            result["hits"] = [{"ats": r["ats"], "slug": r["slug"], "company": r["company"],
                               "jobs": _jobs(r.get("jobs")), "from": "seed", "status": r.get("status")} for r in shown]
            if live:
                result["note"] = "found in the seed list; no requests needed"
                return result, [dict(r, source="user") for r in live]
            result["note"] = ("the seed list marks this board %s, so it was not saved; rerun with --refresh to "
                              "check it again and guess other slugs" % shown[0].get("status"))
            return result, []
        tries = plan_tries(name, matches if refresh else [])

    blocked_in_a_row = 0
    for ats, slug in tries:
        label = "%s:%s" % (ats, slug)
        try:
            raws = adapters.REGISTRY[ats].fetch_board(slug, budget)
        except net.BudgetExceeded:
            result["note"] = "request cap reached before this company was fully checked"
            result["capped"] = True
            return result, []
        except net.NetError as e:
            blocked = isinstance(e, net.Blocked)
            stats["blocked" if blocked else "answered"] += 1
            result["tried"].append(label)
            result["errors"].append({"board": label, "error": getattr(e, "hint", None) or str(e)})
            blocked_in_a_row = blocked_in_a_row + 1 if blocked else 0
            if blocked_in_a_row >= MAX_BLOCKED_IN_A_ROW:
                result["note"] = ("stopped after %d blocked requests in a row — the network looks blocked; "
                                  "nothing was saved for this company" % blocked_in_a_row)
                return result, []
            continue
        blocked_in_a_row = 0
        stats["answered"] += 1
        result["tried"].append(label)
        if not raws:  # 404 (None) or an empty board ([]) is not a hit
            continue
        source = "board" if board else "seed" if (ats, slug.lower()) in seed_keys else "guess"
        row = {"company": name, "ats": ats, "slug": slug, "sector": "unknown", "status": "live",
               "jobs": len(raws), "us_share": "", "remote_share": "",
               "checked_at": datetime.date.today().isoformat(), "source": "user"}
        hit = {"ats": ats, "slug": slug, "company": name, "jobs": len(raws), "from": source}
        if source != "seed":  # same-name companies exist: let the user see whose board this is
            hit.update(_samples(ats, slug, name, raws))
        if source == "guess":
            line = _csv_line(dict(row, source="community"))
            result["suggest_row"] = line
            hit["issue_text"] = _issue_text(row, line)
        result["hits"] = [hit]
        result["note"] = "found by checking %s" % label
        return result, [row]
    if board:
        result["note"] = ("not found: %s:%s has no open jobs or does not exist; nothing was saved" % board
                          if not result["errors"] else "the check of %s:%s failed (see errors); nothing was saved" % board)
    elif result["errors"]:
        result["note"] = "not found, but %d checks failed (see errors), so it may still exist" % len(result["errors"])
    else:
        result["note"] = "not found on Greenhouse, Ashby or Lever under the slugs tried; nothing was saved"
    return result, []


def budget_for(n_names):
    return net.Budget(n_names * MAX_TRIES + RETRY_ALLOWANCE)


def add(names, refresh=False, board=None):
    seed = load_csv(SEED)
    seed_keys = {(r.get("ats"), (r.get("slug") or "").lower()) for r in seed}
    budget = budget_for(len(names))
    stats = {"answered": 0, "blocked": 0}
    results, to_save, capped = [], [], False
    for name in names:
        if capped:
            results.append({"name": name, "hits": [], "tried": [], "saved": False, "suggest_row": None,
                            "errors": [], "note": "not checked: request cap reached"})
            continue
        result, rows = find_one(name, seed, seed_keys, budget, refresh, stats, board)
        capped = bool(result.pop("capped", False))
        result["saved"] = bool(rows)
        to_save += rows
        results.append(result)
    if to_save:
        path = user_path()
        merged = {(r.get("ats"), r.get("slug")): r for r in load_csv(path)}
        for row in to_save:
            merged[(row["ats"], row["slug"])] = row
        write_csv_atomic(path, list(merged.values()))
    out = {"results": results, "requests": budget.used}
    if capped:
        return out, 4
    if stats["blocked"] and not stats["answered"]:
        return out, 3
    return out, 0


def remove(name):
    path = user_path()
    rows = load_csv(path)
    key = normalize.company_norm(name)
    removed = [r for r in rows if normalize.company_norm(r.get("company")) == key]
    kept = [r for r in rows if r not in removed]
    if removed:
        write_csv_atomic(path, kept)
    return {"removed": removed, "remaining": len(kept)}


def parse_board(spec, n_names):
    """"ats:slug" -> (ats, slug), or ValueError: one name only, a known ATS, a safe slug."""
    if n_names != 1:
        raise ValueError("--board takes exactly one company name (got %d)" % n_names)
    ats, _, slug = spec.strip().partition(":")
    if ats not in adapters.REGISTRY:
        raise ValueError("bad --board %r: ATS must be one of %s" % (spec, ", ".join(sorted(adapters.REGISTRY))))
    state.cache_path(ats, slug)  # the same slug rules as the board cache and probe.py (raises ValueError)
    return ats, slug


def main(argv=None):
    ap = argparse.ArgumentParser(description="Companies job-scout should always check.")
    sub = ap.add_subparsers(dest="cmd")
    p_add = sub.add_parser("add")
    p_add.add_argument("names", nargs="+")
    p_add.add_argument("--refresh", action="store_true")
    p_add.add_argument("--board", help="ATS:SLUG of a board the user knows (exactly one name)")
    sub.add_parser("list")
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("name")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    if args.cmd is None:
        ap.print_usage(sys.stderr)
        return 2
    if args.cmd == "list":
        print(json.dumps({"companies": load_csv(user_path())}))
        return 0
    try:
        if args.cmd == "remove":
            name = check_name(args.name)
        else:
            if len(args.names) > MAX_NAMES:
                raise ValueError("at most %d names per call (got %d)" % (MAX_NAMES, len(args.names)))
            names = []
            for raw in args.names:
                name = check_name(raw)
                if normalize.company_norm(name) not in [normalize.company_norm(n) for n in names]:
                    names.append(name)
            board = parse_board(args.board, len(args.names)) if args.board is not None else None
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    if args.cmd == "remove":
        print(json.dumps(remove(name)))
        return 0
    out, code = add(names, refresh=args.refresh, board=board)
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    sys.exit(main())
