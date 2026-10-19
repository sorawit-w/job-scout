#!/usr/bin/env python3
"""Re-label the frontend-persona ground truth on today's live data, pooled and blind (M5 V3).

Usage:
  python3 scripts/relabel_ground_truth.py snapshot [--out DIR]
  python3 scripts/relabel_ground_truth.py sheet [--snapshot DIR] [--jobscope RUN.json] [--seed 1]
  python3 scripts/relabel_ground_truth.py import LABELS.json [--snapshot DIR] [--out PATH]

snapshot  probes the 49 seed49 boards live (probe.py's probe()) with net.py record mode on
          (DIR/http) and a throwaway JOB_SCOUT_HOME; writes DIR/jobs.json (collapsed) and
          DIR/boards.json. Default DIR: skills/job-scout/evals/snapshots/<UTC date>/.
          Both job-scout and jobscope can later be replayed from DIR/http.
sheet     pools candidate rows (union of: a broad title net, the previous ground truth, job-scout's
          own filter with a frontend profile, and optionally a jobscope run file), dedupes them by
          collapsed job key, shuffles with a fixed seed and writes a BLIND sheet.csv + sheet.html
          (no source, score or match shown) and pool.json (which sources proposed each row; not
          for the labeller). Default --snapshot: the newest dir under evals/snapshots/.
import    turns the sheet's exported labels JSON into the score_run.py ground-truth format:
          strong rows -> roles, maybe rows -> maybe. Unknown keys or labels exit 1.
          Default out: skills/job-scout/evals/ground_truth/<snapshot date>.json.

What it does NOT do: no labelling (a human does that), no network outside `snapshot`, and
jobscope rows that are not in the snapshot are counted in pool.json but not put on the sheet
(the ground truth only holds roles both systems could see).
"""
import argparse
import csv
import datetime
import html
import json
import os
import random
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_SCRIPTS = os.path.join(ROOT, "skills", "job-scout", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import filter as jsfilter  # noqa: E402
import net  # noqa: E402
import probe  # noqa: E402
import state  # noqa: E402
from score_run import _match_keys  # noqa: E402

SNAPSHOTS = os.path.join(ROOT, "skills", "job-scout", "evals", "snapshots")
GT_DIR = os.path.join(ROOT, "skills", "job-scout", "evals", "ground_truth")
PREV_GT = os.path.join(ROOT, "docs", "reference", "ground_truth_2026-10-18.json")
PERSONA = ("senior frontend / design engineer, LA area, remote US or hybrid; "
           "open to relocating within the US")
LABELS = ("strong", "maybe", "no")
SOURCES = ("title_net", "previous_gt", "job_scout", "jobscope")
POOL_SOFT_CAP = 200
SHEET_COLUMNS = ("n", "key", "company", "title", "location", "mode", "posted", "link", "label", "note")

# Source (c): the frontend persona as a job-scout profile (validated by state.validate_profile in tests).
FRONTEND_PROFILE = {
    "schema": 1,
    "target_roles": ["Design Engineer", "Frontend Engineer", "Design Systems Engineer"],
    "title_synonyms": ["Front End Engineer", "Frontend Developer", "Software Engineer, Frontend",
                       "Frontend Software Engineer", "Frontend Platform Engineer", "UI Engineer",
                       "UX Engineer", "Design System Engineer", "Design Systems", "Design Technologist",
                       "Creative Technologist", "Web Engineer"],
    "title_keywords": ["frontend", "design system", "design systems", "design engineer", "react", "ui", "ux",
                       "web", "full stack", "fullstack", "typescript", "javascript", "product engineer"],
    "title_exclusions": [],
    "seniority": ["Senior", "Staff"],
    "track": "ic",
    "work_modes": ["remote", "hybrid"],
    "remote_scope": ["US"],
    "open_to_relocation": True,
    "home_base": "Pasadena, CA",
    "commute_cities": ["Los Angeles", "Pasadena", "Glendale", "Burbank", "Santa Monica", "Culver City",
                       "Playa Vista", "Venice", "El Segundo", "Long Beach"],
    "needs_sponsorship": "no",
    "base_pay_floor": None,
}

# Source (a): a deliberately broad title net. Generous on purpose: the human decides.
TITLE_NET = re.compile(
    r"front[\s-]*end|design[\s-]*engineer|design[\s-]*systems?\b|\bui\b|\bux\b|\bweb\b|\breact\b"
    r"|product[\s-]*engineer|full[\s-]*stack|(?:design|creative)[\s-]*technologist|\bjavascript\b"
    r"|\btypescript\b|user[\s-]*interface",
    re.I)
MTS_DESIGN = re.compile(r"member of technical staff.*\bdesign|\bdesign\b.*member of technical staff", re.I)
# Tightened net, used only when the broad pool is far above POOL_SOFT_CAP: the title must also name
# engineering work, and the posting must have a US option (a role the persona cannot take is never strong).
ENG_WORD = re.compile(r"engineer|developer|technologist|programmer|member of technical staff|\blead\b", re.I)
TIGHT_RULE = "tightened: a net word plus an engineering word, and a US location or US-eligible remote option"


def us_option(v):
    countries = set(v.get("countries") or [])
    scope = v.get("remote_scope")
    return (not countries or "US" in countries
            or bool(v.get("remote") and (not scope or set(scope) & {"US", "AMER", "ANY"})))


def in_net(row, tight=False):
    """True when the row or any variant (variants carry their own title and place) is in the net."""
    for v in [{}] + list(row.get("variants") or []):
        v = dict(row, **v)
        t = v.get("title") or ""
        if (TITLE_NET.search(t) or MTS_DESIGN.search(t)) and (not tight or (ENG_WORD.search(t) and us_option(v))):
            return True
    return False


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    state.write_json_atomic(path, data)


def utc_date():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


# --- snapshot ---------------------------------------------------------------

def seed49_boards(path=os.path.join(probe.DATA, "companies.csv")):
    """Every seed49 row, whatever its status: the eval board list is fixed."""
    return [(r["ats"], r["slug"], r.get("company") or r["slug"]) for r in probe.load_csv(path)
            if r.get("source") == "seed49"]


def cmd_snapshot(args):
    out = args.out or os.path.join(SNAPSHOTS, utc_date())
    if os.path.exists(os.path.join(out, "jobs.json")):
        print("snapshot: %s already has jobs.json; pick another --out (labels may point at it)" % out)
        return 2
    boards = seed49_boards()
    http_dir = os.path.join(out, "http")
    os.makedirs(http_dir, exist_ok=True)
    saved = {k: os.environ.get(k) for k in ("JOB_SCOUT_RECORD_DIR", "JOB_SCOUT_HOME")}
    budget = net.Budget(len(boards) + probe.RETRY_ALLOWANCE)
    with tempfile.TemporaryDirectory() as home:
        os.environ["JOB_SCOUT_RECORD_DIR"] = http_dir
        os.environ["JOB_SCOUT_HOME"] = home  # empty cache: every board is fetched (and recorded) live
        try:
            summary, jobs = probe.probe(boards, budget, refresh=True, denylist=probe.load_denylist())
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    summary.update({"date": utc_date(), "boards": ["%s:%s" % b[:2] for b in boards],
                    "requests": budget.used})
    _write_json(os.path.join(out, "jobs.json"), jobs)
    _write_json(os.path.join(out, "boards.json"), summary)
    print("snapshot %s: %d boards (%d live, %d empty, %d dead, %d errors), %d jobs -> %d collapsed, %d requests"
          % (out, len(boards), summary["live"], len(summary["empty"]), len(summary["dead"]),
             len(summary["errors"]), summary["jobs"], summary["collapsed"], budget.used))
    if summary["capped"]:
        return 4
    return 3 if summary["probed"] and summary["blocked"] == summary["probed"] else 0


# --- sheet ------------------------------------------------------------------

def latest_snapshot():
    dirs = sorted(d for d in os.listdir(SNAPSHOTS) if os.path.exists(os.path.join(SNAPSHOTS, d, "jobs.json"))) \
        if os.path.isdir(SNAPSHOTS) else []
    if not dirs:
        sys.exit("relabel: no snapshot found under %s; run `snapshot` first" % SNAPSHOTS)
    return os.path.join(SNAPSHOTS, dirs[-1])


def _index(jobs):
    """(ats, slug, title, date) of every row and variant -> collapsed row key (score_run's rule)."""
    idx = {}
    for r in jobs:
        for t in _match_keys([r]):
            idx.setdefault(t, r["key"])
    return idx


def build_pool(jobs, prev_gt=None, jobscope=None, profile=FRONTEND_PROFILE, tight=None):
    """{key: set(sources)} plus notes. tight None = broad net, tightened if the pool is far above the cap."""
    idx = _index(jobs)
    variant_to_row = {}
    for r in jobs:
        for v in [r] + list(r.get("variants") or []):
            variant_to_row.setdefault(v.get("key"), r["key"])
    notes = {"jobscope_unmatched": 0, "previous_gt_absent": [], "title_net": "broad"}

    def net_keys(t):
        return {r["key"] for r in jobs if in_net(r, t)}

    by_source = {"title_net": net_keys(False)}
    if prev_gt:
        found = set()
        for g in prev_gt["roles"]:
            k = idx.get((g["ats"], g["slug"], g["title"], g["first_published"]))
            if k:
                found.add(k)
            else:
                notes["previous_gt_absent"].append(g)
        by_source["previous_gt"] = found
    # filter.py's default --limit: the candidate list the skill actually hands on (SKILL.md runs it bare).
    summary, cands = jsfilter.run_filter(jobs, profile, limit=jsfilter.DEFAULT_LIMIT)
    notes["job_scout_candidates_total"] = summary["counts"]["candidates"]
    by_source["job_scout"] = {variant_to_row.get(c.get("key"), c.get("key")) for c in cands}
    if jobscope:
        by_slug = {(t[1], t[2], t[3]): k for t, k in idx.items()}
        found = set()
        for c in jobscope["companies"]:
            for j in c["jobs"]:
                k = by_slug.get((j["id"].split(":")[1], (j.get("title") or "").strip(), (j.get("posted") or "")[:10]))
                if k:
                    found.add(k)
                else:
                    notes["jobscope_unmatched"] += 1
        by_source["jobscope"] = found
    broad_pool = len(set().union(*by_source.values()))
    if tight or (tight is None and broad_pool > POOL_SOFT_CAP * 1.25):
        by_source["title_net"] = net_keys(True)
        notes["title_net"] = TIGHT_RULE + ("" if tight else " (broad pool was %d rows)" % broad_pool)
    pool = {}
    for src, keys in by_source.items():
        for k in keys:
            pool.setdefault(k, set()).add(src)
    return pool, by_source, notes


def _where(r):
    locs = r.get("locations") or []
    if not locs:
        return "remote" if r.get("remote") else "not stated"
    return "; ".join(locs[:3]) + (" +%d more" % (len(locs) - 3) if len(locs) > 3 else "")


def _link(url):
    return url if isinstance(url, str) and re.match(r"https?://", url) else ""


def sheet_rows(jobs, keys, seed):
    """Blind rows in a seeded shuffle: only what the labeller needs, nothing about who proposed them."""
    by_key = {r["key"]: r for r in jobs}
    order = sorted(keys)
    random.Random(seed).shuffle(order)
    rows = []
    for n, k in enumerate(order, 1):
        r = by_key[k]
        rows.append({"n": n, "key": k, "company": r.get("company") or "", "title": r.get("title") or "",
                     "location": _where(r), "mode": r.get("workplace") or "not stated",
                     "posted": (r.get("first_published") or "")[:10], "link": _link(r.get("url")),
                     "label": "", "note": ""})
    return rows


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)


HTML_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label jobs — %(snap)s</title>
<style>
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#5f5f5a;--card:#fff;--line:#deded8;--accent:#2457c5;
--strong:#1f7a3a;--maybe:#946200;--no:#a3312a;--sel-fg:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#a5a59f;--card:#20201e;
--line:#3a3a36;--accent:#8fb0ff;--strong:#5cc47a;--maybe:#e2b04a;--no:#f07a70;--sel-fg:#111}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:.5rem 0}
.intro{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px}
.intro p{margin:.4rem 0}
.bar{position:sticky;top:0;z-index:1;background:var(--bg);display:flex;gap:12px;align-items:center;
flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}
.bar .grow{flex:1}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
.card.current{outline:3px solid var(--accent);outline-offset:2px}
.card h2{font-size:1.05rem;margin:0}
.meta{color:var(--muted);font-size:.92rem;margin:.2rem 0 .6rem}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button{font:inherit;border:1px solid var(--line);background:var(--bg);color:var(--fg);
border-radius:8px;padding:6px 12px;cursor:pointer}
button[data-v=strong][aria-pressed=true]{background:var(--strong);border-color:var(--strong);color:var(--sel-fg)}
button[data-v=maybe][aria-pressed=true]{background:var(--maybe);border-color:var(--maybe);color:var(--sel-fg)}
button[data-v=no][aria-pressed=true]{background:var(--no);border-color:var(--no);color:var(--sel-fg)}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
input[type=text],textarea{font:inherit;width:100%%;background:var(--bg);color:var(--fg);
border:1px solid var(--line);border-radius:8px;padding:6px 8px}
.note{flex:1;min-width:200px}
.sr{position:absolute;left:-9999px}
kbd{border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:.85em}
#out{display:none;margin-top:8px;height:8rem}
</style></head><body><main>
<h1>Label these jobs</h1>
<section class="intro" aria-labelledby="who">
<p id="who"><strong>The person:</strong> a senior frontend / design engineer who lives near Los Angeles.
They want a remote job anywhere in the US, or a hybrid job. They would move within the US for a hybrid
or onsite job. Level: Senior or Staff. They want to stay an individual contributor, not a manager.</p>
<p><strong>The rule:</strong> Strong fit = you would tell this person to apply. If the title is clearly
not frontend or design work (backend, security, infrastructure, sales…), choose No without opening it.
If it might fit, open the job page and decide from the page, not the title.</p>
<p>Keys: <kbd>1</kbd> Strong fit, <kbd>2</kbd> Maybe, <kbd>3</kbd> No, <kbd>j</kbd>/<kbd>k</kbd> next / previous.
Labels are saved in this browser as you go. When done, press Export labels and send the text.</p>
</section>
<div class="bar"><span id="progress" aria-live="polite"></span><span class="grow"></span>
<button type="button" id="export">Export labels</button></div>
<label class="sr" for="out">Exported labels</label><textarea id="out" readonly></textarea>
"""

HTML_CARD = """<article class="card" id="c%(n)d" data-key="%(key)s" tabindex="-1" aria-labelledby="t%(n)d">
<h2 id="t%(n)d">%(n)d. %(title)s</h2>
<p class="meta">%(company)s · %(location)s · %(mode)s · posted %(posted)s</p>
<div class="row">%(link)s
<span role="group" aria-label="Label for %(title)s at %(company)s">
<button type="button" data-v="strong" aria-pressed="false">Strong fit</button>
<button type="button" data-v="maybe" aria-pressed="false">Maybe</button>
<button type="button" data-v="no" aria-pressed="false">No</button></span>
<label class="sr" for="n%(n)d">Note for %(title)s</label>
<input class="note" type="text" id="n%(n)d" placeholder="Note (optional)"></div>
</article>
"""

HTML_TAIL = """</main>
<script>
(function () {
  var SNAP = %(snap_js)s, STORE = "relabel:" + SNAP;
  var data = {labels: {}, notes: {}};
  try { var s = JSON.parse(localStorage.getItem(STORE) || "null"); if (s && s.labels) data = s; } catch (e) {}
  if (!data.notes) data.notes = {};
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
  var cur = 0;
  function save() { try { localStorage.setItem(STORE, JSON.stringify(data)); } catch (e) {} }
  function progress() {
    var done = cards.filter(function (c) { return data.labels[c.dataset.key]; }).length;
    document.getElementById("progress").textContent = done + " of " + cards.length + " labelled";
  }
  function paint(card) {
    var v = data.labels[card.dataset.key];
    card.querySelectorAll("button[data-v]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.v === v));
    });
  }
  function setCur(i, focus) {
    if (!cards.length) return;
    cur = Math.max(0, Math.min(cards.length - 1, i));
    cards.forEach(function (c, j) { c.classList.toggle("current", j === cur); });
    if (focus) { cards[cur].focus({preventScroll: true}); cards[cur].scrollIntoView({block: "center"}); }
  }
  function label(i, v) {
    var c = cards[i], k = c.dataset.key;
    if (data.labels[k] === v) delete data.labels[k]; else data.labels[k] = v;
    save(); paint(c); progress();
  }
  cards.forEach(function (c, i) {
    var note = c.querySelector(".note");
    note.value = data.notes[c.dataset.key] || "";
    note.addEventListener("input", function () {
      if (note.value.trim()) data.notes[c.dataset.key] = note.value; else delete data.notes[c.dataset.key];
      save();
    });
    c.querySelectorAll("button[data-v]").forEach(function (b) {
      b.addEventListener("click", function () { setCur(i, false); label(i, b.dataset.v); });
    });
    c.addEventListener("focusin", function () { setCur(i, false); });
    paint(c);
  });
  document.addEventListener("keydown", function (e) {
    var t = e.target.tagName;
    if (t === "INPUT" || t === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
    var map = {"1": "strong", "2": "maybe", "3": "no"};
    if (map[e.key]) { label(cur, map[e.key]); if (data.labels[cards[cur].dataset.key]) setCur(cur + 1, true); }
    else if (e.key === "j") setCur(cur + 1, true);
    else if (e.key === "k") setCur(cur - 1, true);
  });
  document.getElementById("export").addEventListener("click", function () {
    var out = document.getElementById("out");
    out.value = JSON.stringify({snapshot: SNAP, labels: data.labels, notes: data.notes}, null, 1);
    out.style.display = "block"; out.focus(); out.select();
    var done = function () { document.getElementById("export").textContent = "Copied — export again"; };
    try {
      if (navigator.clipboard) navigator.clipboard.writeText(out.value).then(done, function () {
        if (document.execCommand("copy")) done(); });
      else if (document.execCommand("copy")) done();
    } catch (e) {}
  });
  setCur(0, false); progress();
})();
</script></body></html>
"""


def write_html(path, rows, snap):
    e = html.escape
    parts = [HTML_HEAD % {"snap": e(snap)}]
    for r in rows:
        link = ('<a href="%s" target="_blank" rel="noopener noreferrer">Open job page</a>' % e(r["link"])
                if r["link"] else "<span>No link</span>")
        parts.append(HTML_CARD % {"n": r["n"], "key": e(r["key"]), "title": e(r["title"]), "company": e(r["company"]),
                                  "location": e(r["location"]), "mode": e(r["mode"]),
                                  "posted": e(r["posted"] or "not stated"), "link": link})
    parts.append(HTML_TAIL % {"snap_js": json.dumps(snap).replace("<", "\\u003c")})
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def cmd_sheet(args):
    snap_dir = os.path.abspath(args.snapshot or latest_snapshot())
    snap = os.path.basename(snap_dir.rstrip(os.sep))
    jobs = _read_json(os.path.join(snap_dir, "jobs.json"))
    prev = _read_json(args.prev_gt) if args.prev_gt and os.path.exists(args.prev_gt) else None
    js = _read_json(args.jobscope) if args.jobscope else None
    pool, by_source, notes = build_pool(jobs, prev, js)
    rows = sheet_rows(jobs, pool, args.seed)
    write_csv(os.path.join(snap_dir, "sheet.csv"), rows)
    write_html(os.path.join(snap_dir, "sheet.html"), rows, snap)
    _write_json(os.path.join(snap_dir, "pool.json"), {
        "snapshot": snap, "seed": args.seed, "persona": PERSONA, "profile": FRONTEND_PROFILE,
        "title_net": {"rule": notes["title_net"], "pattern": TITLE_NET.pattern, "mts_design": MTS_DESIGN.pattern,
                      "tight_needs": ENG_WORD.pattern},
        "counts": dict({s: len(k) for s, k in by_source.items()}, pool=len(pool)),
        "notes": notes,
        "rows": [{"n": r["n"], "key": r["key"], "sources": sorted(pool[r["key"]])} for r in rows]})
    per = ", ".join("%s %d" % (s, len(by_source[s])) for s in SOURCES if s in by_source)
    print("pool %d rows (%s) -> %s/sheet.html" % (len(pool), per, snap_dir))
    if notes["title_net"] != "broad":
        print("title_net " + notes["title_net"])
    if notes["previous_gt_absent"]:
        print("previous ground truth: %d of %d roles not in this snapshot"
              % (len(notes["previous_gt_absent"]), len(prev["roles"])))
    if notes["jobscope_unmatched"]:
        print("jobscope: %d jobs not in this snapshot (left off the sheet)" % notes["jobscope_unmatched"])
    if notes["job_scout_candidates_total"] > len(by_source["job_scout"]):
        print("job_scout: top %d of %d candidates pooled (filter.py's default --limit)"
              % (len(by_source["job_scout"]), notes["job_scout_candidates_total"]))
    return 0


# --- import -----------------------------------------------------------------

def to_ground_truth(labels, jobs, snap, date):
    """GT dict in score_run's format; raises ValueError on unknown keys or labels."""
    by_key = {r["key"]: r for r in jobs}
    lab = labels.get("labels") or {}
    bad_keys = sorted(k for k in lab if k not in by_key)
    bad_vals = sorted("%s=%r" % (k, v) for k, v in lab.items() if v not in LABELS)
    if bad_keys or bad_vals:
        raise ValueError("; ".join(filter(None, [
            "keys not in snapshot %s: %s" % (snap, ", ".join(bad_keys)) if bad_keys else "",
            "labels must be strong/maybe/no: %s" % ", ".join(bad_vals) if bad_vals else ""])))

    def role(k):
        r = by_key[k]
        return {"ats": r["ats"], "slug": r["slug"], "title": (r.get("title") or "").strip(),
                "first_published": (r.get("first_published") or "")[:10], "key": k}

    pick = lambda v: [role(k) for k in sorted(lab) if lab[k] == v]  # noqa: E731
    notes = {k: v for k, v in (labels.get("notes") or {}).items() if k in by_key and str(v).strip()}
    gt = {"date": date, "persona": PERSONA, "snapshot": snap, "roles": pick("strong"), "maybe": pick("maybe")}
    if notes:
        gt["notes"] = notes
    return gt


def cmd_import(args):
    labels = _read_json(args.labels)
    snap_dir = os.path.abspath(args.snapshot or os.path.join(SNAPSHOTS, str(labels.get("snapshot") or "")))
    snap = os.path.basename(snap_dir.rstrip(os.sep))
    if not os.path.exists(os.path.join(snap_dir, "jobs.json")):
        print("import: no jobs.json in %s" % snap_dir, file=sys.stderr)
        return 1
    if labels.get("snapshot") and labels["snapshot"] != snap:
        print("import: warning: labels are for %r, snapshot is %r" % (labels["snapshot"], snap), file=sys.stderr)
    boards_path = os.path.join(snap_dir, "boards.json")
    date = (_read_json(boards_path).get("date") if os.path.exists(boards_path) else None) or snap[:10]
    try:
        gt = to_ground_truth(labels, _read_json(os.path.join(snap_dir, "jobs.json")), snap, date)
    except ValueError as e:
        print("import: %s" % e, file=sys.stderr)
        return 1
    out = args.out or os.path.join(GT_DIR, "%s.json" % date)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    _write_json(out, gt)
    print("ground truth %s: %d strong, %d maybe, %d labelled" % (out, len(gt["roles"]), len(gt["maybe"]),
                                                                 len(labels.get("labels") or {})))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pooled, blind re-labelling of the ground truth.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("snapshot")
    s.add_argument("--out")
    s = sub.add_parser("sheet")
    s.add_argument("--snapshot")
    s.add_argument("--jobscope")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--prev-gt", default=PREV_GT, help=argparse.SUPPRESS)
    s = sub.add_parser("import")
    s.add_argument("labels")
    s.add_argument("--snapshot")
    s.add_argument("--out")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    return {"snapshot": cmd_snapshot, "sheet": cmd_sheet, "import": cmd_import}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
