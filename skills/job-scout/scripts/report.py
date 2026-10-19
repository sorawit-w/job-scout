#!/usr/bin/env python3
"""Write one self-contained HTML report for a search run.

Purpose:
    The chat table stays the main output; this page is an extra the user can keep, sort and
    print. It reads only the run's files (boards.json, candidates.json, filter.json, jds.json,
    results.json) plus profile.json and seen.json, and writes <run dir>/report.html.

Usage (paths relative to the skill folder):
    python3 scripts/report.py [--run latest] [--out PATH] [--open]

    Run it after cite_check.py passes and BEFORE `state.py seen record`: record marks closed roles
    as reported, after which the "closed since last time" list would be empty.
    Prints {"report": path, "shown": n, "excluded": n, "skipped": [keys], "opened": bool|null}.
    --open opens the file in the local browser (webbrowser); "opened" is false when there is none.

Exit codes: 0 written · 2 bad run id, or the run has no jobs.json / candidates.json.

What it does NOT do: no network (the page itself also loads nothing: inline CSS and JS under a
Content-Security-Policy; links open only when clicked), no saved state in the page (seen.json stays
the only record), no job-description text beyond the quotes the rubric already checked.
"""
import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import filter as jfilter  # noqa: E402
import state  # noqa: E402

MAX_EXCLUDED = 5
GATES = ("location", "sponsorship", "pay", "exclusions")
SCORES = ("role", "skills", "level", "domain")
REASON_TEXT = {"work_mode": "work mode", "location": "location", "remote_scope": "remote scope",
               "seniority": "level", "track": "track", "company": "excluded companies",
               "title": "job title", "title_exclusion": "excluded titles", "pay_floor": "pay floor",
               "already_seen": "already seen", "dismissed_or_applied": "dismissed or applied"}
SPONSOR_TEXT = {"yes": "Needs visa sponsorship", "no": "No sponsorship needed",
                "undisclosed": "Sponsorship not said"}
RERUN_REASONS = ("already_seen", "dismissed_or_applied")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# ---------- view: plain data, no HTML ----------

def load_run(run_dir):
    """The run's files as parsed JSON (missing ones as None)."""
    names = ("boards", "jobs", "candidates", "filter", "jds", "results")
    return {n: state.read_json(Path(run_dir) / ("%s.json" % n)) for n in names}


def _run_date(run_id):
    m = re.match(r"(\d{4})(\d{2})(\d{2})T", run_id or "")
    return "%s %d, %s" % (MONTHS[int(m.group(2)) - 1], int(m.group(3)), m.group(1)) if m else ""


def _where(job):
    mode = job.get("workplace") or ("remote" if job.get("remote") else "")
    locs = [loc for loc in job.get("locations") or [] if isinstance(loc, str) and loc.lower() != mode.lower()]
    place = "; ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")
    return " · ".join(p for p in (mode.capitalize(), place) if p) or "not stated"


def _safe_url(url):
    return url if isinstance(url, str) and re.match(r"https?://", url, re.I) else None


def _items(items):
    return [{"text": str(i.get("text") or ""), "quote": i.get("quote")}
            for i in items or [] if isinstance(i, dict)]


def _brief(profile):
    p = profile if isinstance(profile, dict) else {}
    chips = []
    roles = p.get("target_roles") if isinstance(p.get("target_roles"), list) else []
    if roles:
        chips.append(" · ".join(str(r) for r in roles[:3]))
    modes = [str(m) for m in p.get("work_modes") or [] if isinstance(p.get("work_modes"), list)]
    if modes:
        place = ", ".join(str(s) for s in p.get("remote_scope") or []) if modes == ["remote"] else (
            p.get("home_base") or "")
        chips.append("/".join(m.capitalize() for m in modes) + (" · %s" % place if place else ""))
    floor = p.get("base_pay_floor")
    chips.append("Pay floor %s" % jfilter.pay_text({"min": floor.get("amount"), "max": None,
                                                     "currency": floor.get("currency"),
                                                     "interval": floor.get("interval")})
                 if isinstance(floor, dict) and floor.get("amount") else "No pay floor")
    if p.get("needs_sponsorship") in SPONSOR_TEXT:
        chips.append(SPONSOR_TEXT[p["needs_sponsorship"]])
    return chips


def _pay_short(comp):
    """'$190k–$230k' for yearly pay in a table cell; anything else falls back to pay_text."""
    lo, hi = comp.get("min"), comp.get("max")
    nums = [v for v in (lo, hi) if v is not None]
    if not nums or comp.get("interval") not in (None, "year") or min(nums) < 1000:
        return jfilter.pay_text(comp)
    cur = (comp.get("currency") or "").upper()
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " " if cur else "")
    k = lambda v: "%s%sk" % (sym, format(v / 1000.0, ".0f"))  # noqa: E731
    if lo is not None and hi is not None and lo != hi:
        return "%s–%s" % (k(lo), k(hi))
    return k(lo) + "+" if lo is not None else "up to " + k(hi)


def _short_date(iso, run_year):
    """'Oct 1' (or 'Oct 1, 2025' outside the run's year) from 'YYYY-MM-DD'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return iso or ""
    day = "%s %d" % (MONTHS[int(m.group(2)) - 1], int(m.group(3)))
    return day if m.group(1) == run_year else "%s, %s" % (day, m.group(1))


def _excluded_reason(row):
    failed = [g for g in GATES if (row.get("gates") or {}).get(g) == "fail"]
    if failed:
        return "%s gate failed" % failed[0]
    return "fit %s/8, below 5" % row.get("total") if row.get("total") is not None else "not a fit"


def build_view(files, profile, seen, run_id, probed_ok=()):
    """Everything the page shows, as plain data. Pure: same inputs, same view."""
    cands = {c.get("key"): c for c in files.get("candidates") or [] if isinstance(c, dict)}
    jds = files.get("jds") if isinstance(files.get("jds"), dict) else {}
    results = files.get("results") if isinstance(files.get("results"), dict) else None
    rows = [r for r in (results or {}).get("rows") or [] if isinstance(r, dict)]
    roles, excluded, skipped, used = [], [], [], set()
    for row in rows:
        key = row.get("key")
        if key in used:
            continue  # a duplicate row: the first one wins
        used.add(key)
        entry = jds.get(key) if isinstance(jds.get(key), dict) else {}
        job = entry.get("job") if isinstance(entry.get("job"), dict) else cands.get(key)
        if not isinstance(job, dict):
            skipped.append(key)
            continue
        base = {"key": key, "title": str(job.get("title") or "Untitled role"),
                "company": str(job.get("company") or "")}
        if not row.get("show"):
            excluded.append(dict(base, reason=_excluded_reason(row)))
            continue
        cand = cands.get(key) or {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        gates = row.get("gates") if isinstance(row.get("gates"), dict) else {}
        comp = entry["comp"] if "comp" in entry else job.get("comp")  # the live check wins, even "none"
        comp = comp if isinstance(comp, dict) else {}
        pay_sort = comp.get("min") if comp.get("min") is not None else comp.get("max")
        roles.append(dict(
            base, rank=len(roles) + 1, url=_safe_url(job.get("url")), where=_where(job),
            pay=jfilter.pay_text(comp), pay_short=_pay_short(comp),
            pay_sort=pay_sort if isinstance(pay_sort, (int, float)) else None,
            since=str(job.get("first_published") or "")[:10], total=row.get("total"),
            since_short=_short_date(str(job.get("first_published") or "")[:10], (run_id or "")[:4]),
            scores={s: scores.get(s) for s in SCORES}, gates={g: gates.get(g) or "unknown" for g in GATES},
            why=_items(row.get("why")), risk=_items(row.get("risk")),
            state=cand.get("state") if seen and cand.get("state") in ("new", "changed") else None,  # all new on a first run
            flags=[f for f in job.get("flags") or cand.get("flags") or [] if isinstance(f, str)]))
    summary = files.get("filter") if isinstance(files.get("filter"), dict) else {}
    for nm in summary.get("near_misses") or []:
        if isinstance(nm, dict) and nm.get("key") not in used:
            excluded.append({"key": nm.get("key"), "title": str(nm.get("title") or ""),
                             "company": str(nm.get("company") or ""), "reason": str(nm.get("reason") or "")})
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    removed = {k: v for k, v in (counts.get("removed") or {}).items()
               if isinstance(v, int) and v > 0 and k not in RERUN_REASONS}  # on a rerun, "seen" is not a filter
    top = max(removed, key=removed.get) if removed else None
    boards = files.get("boards") if isinstance(files.get("boards"), dict) else {}
    jobs = [j for j in files.get("jobs") or [] if isinstance(j, dict)]
    lists = state.diff(jobs, set(probed_ok), seen) if seen else {}

    by_key = {j.get("key"): j for j in jobs}

    def listed(keys, status=None):
        """Saved/applied/closed roles: this run's job fields when listed, else what seen.json kept."""
        out = []
        for k in keys:
            src = by_key.get(k) or seen.get(k)
            if isinstance(src, dict):
                entry = seen.get(k) if isinstance(seen.get(k), dict) else {}
                out.append({"title": str(src.get("title") or k), "company": str(src.get("company") or ""),
                            "url": _safe_url(src.get("url")), "status": status or entry.get("status")})
        return out

    return {
        "date": _run_date(run_id), "brief": _brief(profile), "roles": roles,
        "excluded": excluded[:MAX_EXCLUDED], "skipped": skipped, "rerun": bool(seen),
        "coverage": {"probed": boards.get("probed"), "available": boards.get("available"),
                     "moved": sum(1 for c in cands.values() if c.get("state") in ("new", "changed")),
                     "open": sum(1 for e in jds.values()
                                 if isinstance(e, dict) and e.get("status") == "open" and not e.get("dropped"))},
        "top_removed": {"reason": REASON_TEXT.get(top, top), "n": removed[top], "of": counts.get("input")} if top else None,
        "still_open": listed(lists.get("saved_open", []), "saved") + listed(lists.get("applied_open", []), "applied"),
        "closed": listed(lists.get("closed", [])),
    }


# ---------- render: view -> one HTML string ----------
# Design spec: docs/report-design.md ("Signal refined"). One table, master–detail: details expand
# inline under their row; at >= 1200px (JS on) a sticky side pane shows the selected role instead.

CSS = """
:root{--canvas:#f6f6f7;--table:#fff;--ink:#18181b;--muted:#52525b;--faint:#71717a;--line:#e4e4e7;
--line-strong:#d4d4d8;--hover:#f4f4f5;--accent:#4f46e5;--accent-soft:#eef2ff;--accent-ink:#3730a3;
--ok:#15803d;--warn:#a16207;--bad:#b91c1c;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--canvas:#0f0f11;--table:#17171a;--ink:#ececef;--muted:#a1a1aa;
--faint:#8b8b94;--line:#27272a;--line-strong:#3f3f46;--hover:#1f1f23;--accent:#818cf8;--accent-soft:#1f1d3d;
--accent-ink:#c7d2fe;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;color-scheme:dark}}
*{box-sizing:border-box}
html{accent-color:var(--accent);scrollbar-color:var(--line-strong) transparent}
::selection{background:var(--accent-soft);color:var(--ink)}
body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
main{padding:24px}
a{color:var(--accent-ink);text-underline-offset:2px}
@media (prefers-color-scheme:dark){a{color:var(--accent)}}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h1{font-size:18px;font-weight:600;margin:0 0 10px;letter-spacing:-.01em}
h2{font-size:15px;font-weight:600;margin:32px 0 8px}
.i{width:16px;height:16px;flex:none;vertical-align:-3px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px;padding:0;list-style:none}
.chips li{border:1px solid var(--line-strong);border-radius:999px;padding:1px 10px;font-size:13px;color:var(--muted)}
.coverage{margin:0;color:var(--muted);font-size:13px}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:20px 0 10px}
.toolbar label{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
input,button{font:inherit;font-size:13px;color:var(--ink)}
input{background:var(--table);border:1px solid var(--line-strong);border-radius:6px;padding:5px 9px;min-width:14em}
.count{font-size:13px;color:var(--muted)}
.layout{display:block}
table{width:100%;border-collapse:collapse;background:var(--table);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th{font-size:12px;font-weight:600;color:var(--faint);text-align:left;padding:8px 12px;border-bottom:1px solid var(--line-strong);white-space:nowrap}
th button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:2px;border-radius:4px}
th button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
th[aria-sort] .sort{color:var(--accent)}
th .sort{width:12px;height:12px;visibility:hidden}
th[aria-sort] .sort{visibility:visible}
td{padding:10px 12px;vertical-align:top}
tbody.role{border-top:1px solid var(--line)}
tbody.role:first-of-type{border-top:0}
tr.sum{cursor:pointer}
tr.sum:hover{background:var(--hover)}
tbody.role.is-open tr.sum,tbody.role.is-open tr.det{background:var(--accent-soft)}
.c-rank{width:36px;color:var(--muted);text-align:right;padding-right:4px}
.c-fit{width:120px}.c-since{width:96px;color:var(--muted);white-space:nowrap}.c-pay{width:15%;color:var(--muted);white-space:nowrap}.c-where{width:20%;color:var(--muted)}
.toggle{all:unset;cursor:pointer;display:inline-flex;align-items:flex-start;gap:6px;font-weight:600;border-radius:4px;overflow-wrap:anywhere}
.toggle .chev{color:var(--muted);margin-top:2px}
.toggle:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.is-open .toggle{color:var(--accent-ink)}
.is-open .chev{transform:rotate(90deg)}
@media (prefers-reduced-motion:no-preference){.chev{transition:transform 120ms cubic-bezier(.23,1,.32,1)}}
.tag{display:inline-block;margin-left:6px;font-size:11px;font-weight:700;letter-spacing:.02em;color:var(--accent-ink);background:var(--accent-soft);border:1px solid var(--accent);border-radius:4px;padding:0 5px;vertical-align:1px}
.flagcount{display:inline-flex;align-items:center;gap:2px;margin-left:6px;font-size:12px;color:var(--warn);vertical-align:-1px}
.sub{margin:2px 0 0 22px;font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.s-where::before,.s-pay::before{content:" · "}
.fit{display:flex;align-items:center;gap:8px}
.bar{width:56px;height:6px;border-radius:3px;background:var(--line);overflow:hidden;flex:none}
.bar span{display:block;height:100%;background:var(--accent)}
.fit b{font-weight:600}
td.det-cell{padding:0}
.detail{padding:4px 16px 18px 70px;display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:16px 32px}
.detail h3{font-size:12px;font-weight:600;color:var(--muted);margin:10px 0 6px}
.dhead{display:none}
.quotes{list-style:none;margin:0;padding:0}
.quotes li{display:flex;gap:8px;margin:0 0 6px;overflow-wrap:anywhere}
.quotes .i{margin-top:1px}
.why .i{color:var(--ok)}.risk .i{color:var(--warn)}
q{font-style:italic;color:var(--muted)}
.meters{list-style:none;margin:0;padding:0;display:grid;gap:4px;max-width:260px}
.meters li{display:grid;grid-template-columns:5.5em auto auto;justify-content:start;align-items:center;gap:10px;font-size:13px;color:var(--muted)}
.seg{display:inline-flex;gap:3px}.seg span{width:14px;height:6px;border-radius:2px;background:var(--line)}.seg span.on{background:var(--accent)}
.meters b{font-weight:600;color:var(--ink)}
.gates{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.gates li{display:inline-flex;align-items:center;gap:4px;font-size:12px;border:1px solid var(--line-strong);border-radius:999px;padding:1px 8px 1px 5px;color:var(--muted)}
.g-pass .i{color:var(--ok)}.g-fail{color:var(--bad)!important;border-color:var(--bad)!important}.g-fail .i{color:var(--bad)}.g-unknown .i{color:var(--muted)}
.flags{list-style:none;margin:10px 0 0;padding:0}.flags li{display:flex;gap:6px;font-size:13px;color:var(--warn);margin:0 0 4px}
.actions{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding-top:4px}
.actions a,.actions button{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--line-strong);background:var(--table);border-radius:6px;padding:4px 10px;font-size:13px;text-decoration:none;color:var(--ink);cursor:pointer;min-height:28px}
.actions a{color:var(--accent-ink);font-weight:600}
@media (prefers-color-scheme:dark){.actions a{color:var(--accent)}}
.actions a:hover,.actions button:hover{border-color:var(--accent)}
.pane{display:none}
.mini{width:100%;table-layout:fixed;border-collapse:collapse;background:var(--table);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.mini td{border-top:1px solid var(--line);color:var(--muted);overflow-wrap:anywhere}.mini tr:first-child td{border-top:0}.mini td:first-child{color:var(--ink);font-weight:600}
.empty{background:var(--table);border:1px solid var(--line);border-radius:10px;padding:16px;margin:20px 0 0}
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--canvas);border-radius:6px;padding:6px 12px;font-size:13px}
footer{margin-top:32px;font-size:13px;color:var(--muted)}footer p{margin:0 0 4px}
@media (max-width:767px){main{padding:16px}.c-where,.c-pay,.c-since{display:none}.c-fit{width:92px}.c-fit .bar{width:36px}
.s-where{display:none}.detail{grid-template-columns:minmax(0,1fr);padding:4px 12px 16px 12px}.c-rank{width:24px}}
@media (min-width:768px){.s-pay,.s-where{display:none}}
@media (min-width:1200px){
.split .layout{display:grid;grid-template-columns:minmax(0,58fr) minmax(380px,42fr);gap:20px;align-items:start}
.split .c-where{display:none}.split .s-where{display:inline}.split tr.det{display:none}
.split .pane{display:block;position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;background:var(--table);border:1px solid var(--line-strong);border-radius:10px;max-width:560px}
.split .pane .detail{grid-template-columns:minmax(0,1fr);padding:16px 20px 20px}
.split .pane .dhead{display:block}.split .pane .dhead h2{margin:0 0 4px;font-size:16px}.split .pane .dhead p{margin:0;color:var(--muted);font-size:13px}}
@media (min-width:1600px){.split .layout{grid-template-columns:minmax(0,60fr) minmax(380px,40fr)}.split .c-where{display:table-cell}.split .s-where{display:none}.split .pane{max-width:640px}}
@media print{body{background:#fff;color:#000;font-size:12px}main{padding:0}.toolbar,.copy,.pane,.toast,.copy-help{display:none!important}
tr.det{display:table-row!important}tbody.role{break-inside:avoid}tr.sum:hover,tbody.role.is-open tr.sum,tbody.role.is-open tr.det{background:none}
table,.mini,.empty{border-color:#999}.c-where,.c-pay,.c-since{display:table-cell!important}
.layout{display:block!important}.s-where,.s-pay{display:none!important}
.detail .actions a::after{content:" " attr(href);font-weight:400;word-break:break-all}}
"""

ICONS = (
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
    '<symbol id="i-check" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-x" viewBox="0 0 16 16"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round"/></symbol>'
    '<symbol id="i-question" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" '
    'stroke-width="1.5"/><path d="M6.4 6.3a1.7 1.7 0 1 1 2.4 1.5c-.5.3-.8.6-.8 1.3" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".8" fill="currentColor"/></symbol>'
    '<symbol id="i-alert" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" '
    'stroke-width="1.5"/><path d="M8 4.8v3.8" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round"/><circle cx="8" cy="11.2" r=".8" fill="currentColor"/></symbol>'
    '<symbol id="i-chev" viewBox="0 0 16 16"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-up" viewBox="0 0 16 16"><path d="M4.5 10l3.5-3.5 3.5 3.5" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-down" viewBox="0 0 16 16"><path d="M4.5 6l3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-out" viewBox="0 0 16 16"><path d="M5.5 10.5l5-5M6.5 5.5h4v4" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol></svg>')

JS = """(function(){
var d=document,table=d.querySelector('table.roles');if(!table)return;
var root=d.documentElement,pane=d.getElementById('pane'),live=d.getElementById('live'),wide=matchMedia('(min-width:1200px)');
var rows=Array.prototype.slice.call(table.tBodies);var tb=d.querySelector('.toolbar');if(tb)tb.hidden=false;
var home={};rows.forEach(function(r){var det=r.querySelector('.detail');home[det.id]=det.parentNode;});
var split=false,sel=null;
function btn(r){return r.querySelector('.toggle');}
function setOpen(r,open){r.classList.toggle('is-open',open);btn(r).setAttribute('aria-expanded',open?'true':'false');}
function select(r,announce){if(sel&&sel!==r){var old=sel.querySelector('.detail')||pane.querySelector('.detail');
if(old){home[old.id].appendChild(old);}setOpen(sel,false);}
sel=r;setOpen(r,true);var det=d.getElementById(btn(r).getAttribute('aria-controls'));pane.appendChild(det);
if(announce)live.textContent='Showing '+btn(r).textContent.trim()+(r.dataset.company?' at '+r.dataset.company:'');}
function visible(){return rows.filter(function(r){return !r.hidden;});}
function mode(){var want=wide.matches;if(want===split)return;split=want;
if(split){root.classList.add('split');pane.hidden=false;rows.forEach(function(r){setOpen(r,false);});
var v=visible();if(v.length)select(v[0],false);}
else{root.classList.remove('split');if(sel){var det=pane.querySelector('.detail');if(det)home[det.id].appendChild(det);}
sel=null;pane.hidden=true;rows.forEach(function(r){setOpen(r,false);r.querySelector('tr.det').hidden=true;});}}
rows.forEach(function(r){r.querySelector('tr.det').hidden=true;setOpen(r,false);});
function toggle(r){if(split){select(r,true);return;}var open=!r.classList.contains('is-open');setOpen(r,open);r.querySelector('tr.det').hidden=!open;}
table.addEventListener('click',function(e){if(e.target.closest('a,.actions'))return;var r=e.target.closest('tbody.role');
if(!r||e.target.closest('tr.det'))return;toggle(r);if(!e.target.closest('.toggle'))btn(r).focus();});
table.addEventListener('keydown',function(e){var b=e.target.closest('.toggle');if(!b||(e.key!=='ArrowDown'&&e.key!=='ArrowUp'))return;
var v=visible(),i=v.indexOf(b.closest('tbody.role')),n=v[i+(e.key==='ArrowDown'?1:-1)];if(!n)return;e.preventDefault();
btn(n).focus();if(split)select(n,true);});
var dir={};d.querySelectorAll('th[data-sort] button').forEach(function(h){h.addEventListener('click',function(){
var th=h.parentNode,k=th.dataset.sort,asc=dir[k]===undefined?(k==='rank'||k==='title'):!dir[k];dir={};dir[k]=asc;
d.querySelectorAll('th[data-sort]').forEach(function(x){x.removeAttribute('aria-sort');var u=x.querySelector('use');if(u)u.setAttribute('href','#i-up');});
th.setAttribute('aria-sort',asc?'ascending':'descending');th.querySelector('use').setAttribute('href',asc?'#i-up':'#i-down');
rows.slice().sort(function(a,b){var x=a.dataset[k],y=b.dataset[k],c;
if(k==='title')c=x.localeCompare(y);else{var nx=x===''?null:+x,ny=y===''?null:+y;
if(nx===null&&ny===null)c=0;else if(nx===null)return 1;else if(ny===null)return -1;else c=nx-ny;}
return (asc?c:-c)||a.dataset.rank-b.dataset.rank;}).forEach(function(r){table.appendChild(r);});});});
var f=d.getElementById('filter'),count=d.getElementById('count');
if(f)f.addEventListener('input',function(){var q=f.value.trim().toLowerCase(),n=0;
rows.forEach(function(r){var hit=!q||r.dataset.text.indexOf(q)>=0;r.hidden=!hit;if(hit)n++;});
count.textContent=n+' of '+rows.length+' shown';if(split&&sel&&sel.hidden){var v=visible();if(v.length)select(v[0],true);}});
function toast(msg){var t=d.createElement('div');t.className='toast';t.setAttribute('role','status');t.textContent=msg;
d.body.appendChild(t);setTimeout(function(){t.remove();},1800);}
function fallback(text){var a=d.createElement('textarea');a.value=text;a.setAttribute('readonly','');a.style.position='fixed';a.style.opacity='0';
d.body.appendChild(a);a.select();var ok=false;try{ok=d.execCommand('copy');}catch(e){}a.remove();toast(ok?'Copied: '+text:'Press Cmd/Ctrl+C to copy: '+text);}
d.addEventListener('click',function(e){var b=e.target.closest('button[data-copy]');if(!b)return;var text=b.dataset.copy;
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(function(){toast('Copied: '+text);},function(){fallback(text);});}else{fallback(text);}});
addEventListener('beforeprint',function(){var det=pane.querySelector('.detail');if(det)home[det.id].appendChild(det);
rows.forEach(function(r){r.querySelector('tr.det').hidden=false;});});
addEventListener('afterprint',function(){rows.forEach(function(r){r.querySelector('tr.det').hidden=split||!r.classList.contains('is-open');});
if(split&&sel)pane.appendChild(d.getElementById(btn(sel).getAttribute('aria-controls')));});
if(wide.addEventListener)wide.addEventListener('change',mode);mode();
})();"""


def _e(value):
    return html.escape(str(value), quote=True)


def _num(value):
    return format(value, ",") if isinstance(value, int) else _e(value)


def _icon(name, cls="i"):
    return '<svg class="%s" aria-hidden="true" focusable="false"><use href="#i-%s"></use></svg>' % (cls, name)


def _link(text, url):
    return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (_e(url), text) if url else text


def _clip(quote):
    """The verbatim quote, with "…" where it starts or ends mid-sentence (display only)."""
    q = quote.strip()
    head = "" if q[:1].isupper() or q[:1] in "\"'(“‘" or q[:1].isdigit() else "…"
    tail = "" if q[-1:] in ".!?\"'”’)" else "…"
    return head + q + tail


def _quotes(items, cls, icon, label):
    if not items:
        return ""
    lis = "".join('<li>%s<span><span class="sr">%s: </span>%s%s</span></li>' % (
        _icon(icon), label, _e(i["text"]), ': <q dir="auto">%s</q>' % _e(_clip(i["quote"])) if i.get("quote") else "")
        for i in items)
    return '<ul class="quotes %s">%s</ul>' % (cls, lis)


GATE_ICON = {"pass": "check", "fail": "x", "unknown": "question"}


def _detail(r):
    """The detail block: one copy, moved into the side pane in split mode."""
    name = "%s, %s" % (r["company"], r["title"]) if r["company"] else r["title"]
    meters = "".join(
        '<li><span>%s</span><span class="seg" aria-hidden="true">%s</span><b>%s/2</b></li>' % (
            s, "".join('<span class="%s"></span>' % ("on" if isinstance(r["scores"][s], int) and r["scores"][s] > k else "")
                       for k in range(2)), _e(r["scores"][s]) if r["scores"][s] is not None else "–")
        for s in SCORES)
    gates = "".join('<li class="g-%s">%s%s: %s</li>' % (
        _e(r["gates"][g]), _icon(GATE_ICON.get(r["gates"][g], "question")), g, _e(r["gates"][g])) for g in GATES)
    flags = '<ul class="flags">%s</ul>' % "".join(
        "<li>%s<span>%s</span></li>" % (_icon("alert"), _e(f)) for f in r["flags"]) if r["flags"] else ""
    link = ('<a href="%s" target="_blank" rel="noopener noreferrer">Open posting%s</a>' % (_e(r["url"]), _icon("out"))
            if r["url"] else "")
    copies = "".join('<button type="button" data-copy="%s">%s %d</button>' % (
        _e("%s %d (%s)%s" % (verb, r["rank"], name, ": " if verb == "dismiss" else "")), verb, r["rank"])
        for verb in ("save", "applied", "dismiss"))
    meta = " · ".join(_e(p) for p in (r["company"], r["where"], r["pay"],
                                       "open since %s" % r["since"] if r["since"] else "") if p)
    return (
        '<div class="detail" id="d%d" role="region" aria-labelledby="b%d">'
        '<div class="dhead"><h2 dir="auto">%s</h2><p dir="auto">%s</p></div>'
        '<div><h3>Why it fits</h3>%s%s%s</div>'
        '<div><h3>Scores</h3><ul class="meters">%s</ul><ul class="gates" aria-label="Gates">%s</ul>%s</div>'
        '<div class="actions"><span class="sr">Actions:</span>%s<span class="copy" role="group" aria-label="Copy a reply">%s</span></div>'
        '</div>'
    ) % (r["rank"], r["rank"], _e(r["title"]), meta,
         _quotes(r["why"], "why", "check", "Why"),
         '<h3>Watch for</h3>' if r["risk"] else "", _quotes(r["risk"], "risk", "alert", "Risk"),
         meters, gates, flags, link, copies)


def _row(r):
    total = r["total"] if isinstance(r["total"], int) else None
    fit = ('<span class="fit"><span class="bar" aria-hidden="true"><span style="width:%d%%"></span></span>'
           '<b>%d/8</b></span>' % (total * 100 // 8, total)) if total is not None else '<span class="fit">–</span>'
    tag = {"new": "NEW", "changed": "CHANGED"}.get(r["state"], "")
    flagcount = ('<span class="flagcount" title="%d flag%s">%s%d<span class="sr"> flags</span></span>' % (
        len(r["flags"]), "" if len(r["flags"]) == 1 else "s", _icon("alert"), len(r["flags"])) if r["flags"] else "")
    text = " ".join((r["title"], r["company"], r["where"], r["pay"])).lower()
    return (
        '<tbody class="role" data-rank="%d" data-fit="%s" data-pay="%s" data-since="%s" data-title="%s" '
        'data-company="%s" data-text="%s">'
        '<tr class="sum"><td class="c-rank">%d</td>'
        '<td class="c-role"><button type="button" class="toggle" id="b%d" aria-expanded="true" aria-controls="d%d">'
        '%s<span dir="auto">%s</span></button>%s%s'
        '<div class="sub" dir="auto"><span class="s-company">%s</span><span class="s-where">%s</span>'
        '<span class="s-pay">%s</span></div></td>'
        '<td class="c-where" dir="auto">%s</td><td class="c-pay">%s</td><td class="c-fit">%s</td>'
        '<td class="c-since">%s</td></tr>'
        '<tr class="det"><td class="det-cell" colspan="6">%s</td></tr></tbody>'
    ) % (r["rank"], "" if total is None else total, "" if r["pay_sort"] is None else r["pay_sort"],
         _e(r["since"].replace("-", "")), _e(r["title"].lower()), _e(r["company"]), _e(text),
         r["rank"], r["rank"], r["rank"], _icon("chev", "i chev"), _e(r["title"]),
         '<span class="tag">%s</span>' % tag if tag else "", flagcount,
         _e(r["company"]) or "company not listed", _e(r["where"]), _e(r["pay_short"]),
         _e(r["where"]), _e(r["pay_short"]), fit, _e(r["since_short"]) or "–", _detail(r))


def _mini(items, cols):
    """A compact table for the secondary sections."""
    body = "".join("<tr>%s</tr>" % "".join('<td dir="auto">%s</td>' % c for c in cols(i)) for i in items)
    return '<table class="mini"><tbody>%s</tbody></table>' % body


def render(view):
    """The whole page. Deterministic: no clock, no randomness."""
    roles = view["roles"]
    script_hash = base64.b64encode(hashlib.sha256(JS.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-%s'; base-uri 'none'; "
           "form-action 'none'" % script_hash)
    cov = view["coverage"]
    if cov.get("probed") is None:
        coverage = ""
    elif view["rerun"]:  # output-format §1: on a rerun, count what moved, not what is open
        coverage = "Checked %s of %s company job boards — %d new or changed since last time." % (
            _num(cov["probed"]), _num(cov["available"]), cov["moved"])
    else:
        coverage = "Checked %s of %s company job boards (%d job%s open today). Best for tech and startup roles." % (
            _num(cov["probed"]), _num(cov["available"]), cov["open"], "" if cov["open"] == 1 else "s")
    parts = ['<header><h1>job-scout · %d role%s%s</h1>' % (
        len(roles), "" if len(roles) == 1 else "s", " · %s" % _e(view["date"]) if view["date"] else "")]
    if view["brief"]:
        parts.append('<ul class="chips" aria-label="Search brief">%s</ul>' % "".join(
            "<li>%s</li>" % _e(c) for c in view["brief"]))
    parts.append('<p class="coverage">%s</p></header>' % coverage)
    if roles:
        def th(key, label, cls, sort=True, current=False):
            if not sort:
                return '<th scope="col" class="%s">%s</th>' % (cls, label)
            return ('<th scope="col" class="%s" data-sort="%s"%s><button type="button">%s%s</button></th>' % (
                cls, key, ' aria-sort="ascending"' if current else "", label, _icon("up", "i sort")))
        parts.append(
            '<div class="toolbar" hidden><label>Filter <input id="filter" type="search" '
            'placeholder="title, company, place" aria-describedby="count"></label>'
            '<span class="count" id="count" aria-live="polite"></span></div>')
        parts.append(
            '<div class="layout"><table class="roles"><caption class="sr">Roles that fit your brief, in rank order. '
            'Open a role to see why it fits.</caption><thead><tr>%s%s%s%s%s%s</tr></thead>%s</table>'
            '<aside class="pane" id="pane" aria-label="Role details" hidden></aside></div>'
            '<div class="sr" id="live" aria-live="polite"></div>' % (
                th("rank", "#", "c-rank", current=True), th("title", "Role", "c-role"),
                th("where", "Where", "c-where", sort=False), th("pay", "Pay", "c-pay"),
                th("fit", "Fit", "c-fit"), th("since", "Open since", "c-since"),
                "".join(_row(r) for r in roles)))
    else:
        top = view["top_removed"]
        if view["rerun"] and not top:
            msg = "Nothing new since last time."
        elif top:
            msg = "No roles matched your brief. Most jobs were removed by %s (%s of %s)." % (
                _e(top["reason"]), _e(top["n"]), _e(top["of"]))
        else:
            msg = "No roles matched your brief."
        parts.append('<p class="empty">%s</p>' % msg)
    if view["still_open"]:
        parts.append("<h2>Saved or applied, still open</h2>" + _mini(view["still_open"], lambda i: (
            _link(_e(i["title"]), i.get("url")), _e(i["company"]), _e(i.get("status") or ""))))
    if view["closed"]:
        parts.append("<h2>Closed since last time</h2>" + _mini(view["closed"], lambda i: (
            _link(_e(i["title"]), i.get("url")), _e(i["company"]), _e(i.get("status") or ""))))
    if view["excluded"]:
        parts.append("<h2>Close but excluded</h2>" + _mini(view["excluded"], lambda x: (
            _e(x["title"]), _e(x["company"]), _e(x["reason"]))))
    parts.append("<footer>%s<p>This page makes no network requests; links open only when you click.</p></footer>" % (
        '<p class="copy-help">Copy a line with the buttons and paste it into the chat to save, mark applied, '
        "or dismiss a role.</p>" if roles else ""))
    return ('<!doctype html><html lang="en"><head><meta http-equiv="Content-Security-Policy" content="%s">'
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer"><title>job-scout report%s</title><style>%s</style></head>'
            '<body>%s<main>%s</main><script>%s</script></body></html>\n') % (
        csp, " · %s" % _e(view["date"]) if view["date"] else "", CSS, ICONS, "".join(parts), JS)


def _fail(message):
    print(json.dumps({"error": message}, ensure_ascii=False))
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write a self-contained HTML report for a search run.")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--out")
    ap.add_argument("--open", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        run = state.resolve_run(args.run)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    files = load_run(run)
    if not isinstance(files["jobs"], list) or not isinstance(files["candidates"], list):
        return _fail("run %s has no jobs.json or candidates.json — run probe.py and filter.py first" % run.name)
    try:
        seen = state.load_seen()
    except ValueError as e:
        return _fail(str(e))
    view = build_view(files, state.read_json(state.profile_path(), {}), seen, run.name,
                      state.probed_ok_boards(run))
    out = Path(args.out).expanduser() if args.out else run / "report.html"
    state.write_text_atomic(out, render(view))
    opened = webbrowser.open(out.resolve().as_uri()) if args.open else None
    print(json.dumps({"report": str(out), "shown": len(view["roles"]), "excluded": len(view["excluded"]),
                      "skipped": view["skipped"], "opened": opened}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
