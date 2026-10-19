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
        roles.append(dict(
            base, rank=len(roles) + 1, url=_safe_url(job.get("url")), where=_where(job),
            pay=jfilter.pay_text(entry["comp"] if "comp" in entry else job.get("comp")),  # live check wins
            since=str(job.get("first_published") or "")[:10], total=row.get("total"),
            scores={s: scores.get(s) for s in SCORES}, gates={g: gates.get(g) or "unknown" for g in GATES},
            why=_items(row.get("why")), risk=_items(row.get("risk")),
            state=cand.get("state") if cand.get("state") in ("new", "changed") else None,
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

CSS = """
:root{--bg:#f4f6f9;--card:#fff;--ink:#0f172a;--muted:#475569;--line:#e2e8f0;--accent:#4338ca;
--accent-soft:#eef2ff;--ok:#047857;--bad:#b91c1c;--warn:#a16207;--chip:#e2e8f0;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--indent:32px;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0b1120;--card:#111a2e;--ink:#e2e8f0;--muted:#94a3b8;
--line:#334155;--accent:#a5b4fc;--accent-soft:#1e1b4b;--ok:#34d399;--bad:#f87171;--warn:#fbbf24;
--chip:#1e293b;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 48px}
a{color:var(--accent)}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h1{font-size:20px;margin:0 0 8px}h2{font-size:16px;margin:32px 0 8px}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:0;padding:0;list-style:none}
.chips li{background:var(--chip);border-radius:999px;padding:2px 10px;font-size:13px}
.coverage,.muted{color:var(--muted);font-size:14px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 12px}
.controls label{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px}
input,select,button{font:inherit;font-size:14px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:5px 9px}
button{cursor:pointer}button:hover{border-color:var(--accent)}
ol.roles{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.head{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.rank{font-family:var(--mono);color:var(--muted);min-width:22px}
.title{flex:1 1 12em;min-width:0;font-weight:600;font-size:16px;overflow-wrap:anywhere}
.fit{margin-left:auto;white-space:nowrap;font-size:13px;color:var(--muted)}
.bar{display:inline-block;width:64px;height:6px;border-radius:3px;background:var(--line);vertical-align:middle;margin-left:6px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--accent)}
.meta{color:var(--muted);font-size:14px;margin:2px 0 8px var(--indent);overflow-wrap:anywhere}
.tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;border-radius:4px;padding:1px 6px;background:var(--accent-soft);color:var(--accent);margin-left:6px;vertical-align:middle}
.body{margin-left:var(--indent)}
.flags{margin:0 0 8px;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:6px}
.flags li{font-size:12px;border:1px solid var(--line);border-radius:4px;padding:0 6px;color:var(--warn)}
.quotes{margin:0 0 10px;padding:0;list-style:none}
.quotes li{margin:4px 0;overflow-wrap:anywhere}
.quotes .mark{display:inline-block;width:1.2em;font-weight:700}
.why .mark{color:var(--ok)}.risk .mark{color:var(--warn)}
q{font-style:italic}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:0 0 10px}
.grid div{display:flex;justify-content:space-between;align-items:baseline;gap:6px;border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-size:12px;color:var(--muted)}
.grid b{color:var(--ink);font-family:var(--mono);font-size:13px}
.gate-pass b{color:var(--ok)}.gate-fail b{color:var(--bad)}
.copy{display:flex;flex-wrap:wrap;gap:6px}.copy button{font-size:13px;padding:3px 8px}
.list{margin:0;padding-left:1.2em}.list li{margin:3px 0;overflow-wrap:anywhere}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:10px;padding:16px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--bg);border-radius:6px;padding:6px 12px;font-size:14px}
footer{margin-top:32px;font-size:13px;color:var(--muted)}footer p{margin:0 0 4px}
@media (max-width:560px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.meta,.body{margin-left:0}.fit{display:block}}
@media print{body{background:#fff;color:#000}.controls,.copy,.toast,.copy-help{display:none!important}
.card{break-inside:avoid;border-color:#999}a{color:#000}a[href^="http"]::after{content:" (" attr(href) ")";font-size:11px;word-break:break-all}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """(function(){
var list=document.querySelector('ol.roles');var controls=document.querySelector('.controls');
if(!list||!controls)return;controls.hidden=false;
var cards=Array.prototype.slice.call(list.children);
function sortBy(k){cards.slice().sort(function(a,b){
if(k==='company')return a.dataset.company.localeCompare(b.dataset.company)||a.dataset.rank-b.dataset.rank;
if(k==='newest')return (b.dataset.since||'').localeCompare(a.dataset.since||'')||a.dataset.rank-b.dataset.rank;
if(k==='fit')return (b.dataset.fit===''?-1:+b.dataset.fit)-(a.dataset.fit===''?-1:+a.dataset.fit)||a.dataset.rank-b.dataset.rank;
return a.dataset.rank-b.dataset.rank;}).forEach(function(c){list.appendChild(c);});}
document.getElementById('sort').addEventListener('change',function(e){sortBy(e.target.value);});
document.getElementById('filter').addEventListener('input',function(e){var q=e.target.value.trim().toLowerCase();
var shown=0;cards.forEach(function(c){var hit=!q||c.dataset.text.indexOf(q)>=0;c.hidden=!hit;if(hit)shown++;});
document.getElementById('count').textContent=shown+' of '+cards.length;});
function toast(msg){var t=document.createElement('div');t.className='toast';t.setAttribute('role','status');t.textContent=msg;
document.body.appendChild(t);setTimeout(function(){t.remove();},1800);}
function fallback(text){var a=document.createElement('textarea');a.value=text;a.setAttribute('readonly','');
a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();var ok=false;
try{ok=document.execCommand('copy');}catch(e){}a.remove();toast(ok?'Copied: '+text:'Press Cmd/Ctrl+C to copy: '+text);}
document.addEventListener('click',function(e){var b=e.target.closest('button[data-copy]');if(!b)return;var text=b.dataset.copy;
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(function(){toast('Copied: '+text);},function(){fallback(text);});}
else{fallback(text);}});
})();"""


def _e(value):
    return html.escape(str(value), quote=True)


def _link(text, url):
    return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (_e(url), text) if url else text


def _clip(quote):
    """The verbatim quote, with "…" where it starts or ends mid-sentence (display only)."""
    q = quote.strip()
    head = "" if q[:1].isupper() or q[:1] in "\"'(“‘" or q[:1].isdigit() else "…"
    tail = "" if q[-1:] in ".!?\"'”’)" else "…"
    return head + q + tail


def _quotes(items, cls, mark, label):
    if not items:
        return ""
    lis = "".join('<li><span class="mark" aria-hidden="true">%s</span><span class="sr">%s: </span>%s%s</li>' % (
        mark, label, _e(i["text"]), ' — <q dir="auto">%s</q>' % _e(_clip(i["quote"])) if i.get("quote") else "")
        for i in items)
    return '<ul class="quotes %s">%s</ul>' % (cls, lis)


def _card(r):
    name = "%s, %s" % (r["company"], r["title"]) if r["company"] else r["title"]
    total = r["total"] if isinstance(r["total"], int) else None
    fit = ('Fit <span class="num">%d/8</span><span class="bar" aria-hidden="true"><span style="width:%d%%">'
           '</span></span>' % (total, total * 100 // 8)) if total is not None else "Fit not scored"
    tag = {"new": "NEW", "changed": "CHANGED"}.get(r["state"], "")
    grid = "".join('<div>%s<b>%s/2</b></div>' % (s, _e(r["scores"][s]) if r["scores"][s] is not None else "–")
                   for s in SCORES)
    grid += "".join('<div class="gate-%s">%s gate<b>%s</b></div>' % (_e(r["gates"][g]), g, _e(r["gates"][g]))
                    for g in GATES)
    flags = '<ul class="flags">%s</ul>' % "".join("<li>%s</li>" % _e(f) for f in r["flags"]) if r["flags"] else ""
    copies = "".join('<button type="button" data-copy="%s">%s %d</button>' % (
        _e("%s %d (%s)%s" % (verb, r["rank"], name, ": " if verb == "dismiss" else "")), verb, r["rank"])
        for verb in ("save", "applied", "dismiss"))
    text = " ".join((r["title"], r["company"], r["where"])).lower()
    return (
        '<li class="card" data-rank="%d" data-fit="%s" data-since="%s" data-company="%s" data-text="%s">'
        '<div class="head"><span class="rank">%d</span><span class="title" dir="auto">%s</span>%s'
        '<span class="fit">%s</span></div>'
        '<div class="meta" dir="auto">%s · %s · %s%s</div>'
        '<div class="body">%s%s%s<div class="grid">%s</div><div class="copy" role="group" aria-label="Copy a reply">%s</div></div></li>'
    ) % (r["rank"], "" if total is None else total, _e(r["since"]), _e(r["company"].lower()), _e(text),
         r["rank"], _link(_e(r["title"]), r["url"]), '<span class="tag">%s</span>' % tag if tag else "", fit,
         _e(r["company"]) or "company not listed", _e(r["where"]), _e(r["pay"]),
         " · open since %s" % _e(r["since"]) if r["since"] else "",
         flags, _quotes(r["why"], "why", "✓", "Why"), _quotes(r["risk"], "risk", "!", "Risk"), grid, copies)


def _simple_list(items, show_status=False):
    return '<ul class="list">%s</ul>' % "".join('<li dir="auto">%s%s%s</li>' % (
        _link(_e(i["title"]), i.get("url")), " — %s" % _e(i["company"]) if i.get("company") else "",
        " (%s)" % _e(i["status"]) if show_status and i.get("status") else "") for i in items)


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
            _e(cov["probed"]), _e(cov["available"]), cov["moved"])
    else:
        coverage = "Checked %s of %s company job boards (%d job%s open today). Best for tech and startup roles." % (
            _e(cov["probed"]), _e(cov["available"]), cov["open"], "" if cov["open"] == 1 else "s")
    parts = ['<header><h1>job-scout · %d role%s%s</h1>' % (
        len(roles), "" if len(roles) == 1 else "s", " · %s" % _e(view["date"]) if view["date"] else "")]
    if view["brief"]:
        parts.append('<ul class="chips" aria-label="Search brief">%s</ul>' % "".join(
            "<li>%s</li>" % _e(c) for c in view["brief"]))
    parts.append('<p class="coverage">%s</p></header>' % coverage)
    if roles:
        parts.append(
            '<div class="controls" hidden><label>Sort <select id="sort"><option value="rank">Rank</option>'
            '<option value="fit">Fit</option><option value="newest">Newest</option>'
            '<option value="company">Company</option></select></label>'
            '<label>Filter <input id="filter" type="search" placeholder="title, company, place"></label>'
            '<span class="muted" id="count" aria-live="polite"></span></div>')
        parts.append('<ol class="roles">%s</ol>' % "".join(_card(r) for r in roles))
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
        parts.append("<h2>Saved or applied, still open</h2>" + _simple_list(view["still_open"], True))
    if view["closed"]:
        parts.append("<h2>Closed since last time</h2>" + _simple_list(view["closed"], True))
    if view["excluded"]:
        parts.append('<h2>Close but excluded</h2><ul class="list">%s</ul>' % "".join(
            '<li dir="auto">%s%s — %s</li>' % (_e(x["title"]), ", %s" % _e(x["company"]) if x["company"] else "",
                                               _e(x["reason"])) for x in view["excluded"]))
    parts.append("<footer>%s<p>This page makes no network requests; links open only when you click.</p></footer>" % (
        '<p class="copy-help">Copy a line with the buttons and paste it into the chat to save, mark applied, '
        "or dismiss a role.</p>" if roles else ""))
    return ('<!doctype html><html lang="en"><head><meta http-equiv="Content-Security-Policy" content="%s">'
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer"><title>job-scout report%s</title><style>%s</style></head>'
            '<body><main>%s</main><script>%s</script></body></html>\n') % (
        csp, " · %s" % _e(view["date"]) if view["date"] else "", CSS, "".join(parts), JS)


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
