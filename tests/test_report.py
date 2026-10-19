import base64
import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

import report
import state

RUN_ID = "20261019T120000Z"


def job(key, title="Design Engineer", company="Vercel", url=None, state_="new", **extra):
    j = {"key": key, "title": title, "company": company, "url": url or "https://jobs.example.com/%s" % key,
         "locations": ["Remote - US"], "workplace": "remote", "remote": True, "remote_scope": ["US"],
         "first_published": "2026-10-01", "comp": {"min": 190000, "max": 230000, "currency": "USD",
                                                  "interval": "year", "source": "ats_field"},
         "flags": [], "state": state_}
    j.update(extra)
    return j


def row(key, total=7, show=True, gates=None, why=None, risk=None):
    return {"key": key, "gates": gates or {"location": "pass", "sponsorship": "unknown", "pay": "pass",
                                           "exclusions": "pass"},
            "scores": {"role": 2, "skills": 2, "level": 1, "domain": 2}, "total": total, "show": show,
            "why": why or [{"text": "Design systems at the core", "quote": "own and evolve our design system"}],
            "risk": risk or [{"text": "sponsorship not stated", "quote": None}]}


def make_run(home, jobs, rows=None, filter_summary=None, boards=None, jds=None):
    run_dir = os.path.join(home, "runs", RUN_ID)
    os.makedirs(run_dir)
    files = {"jobs": jobs, "candidates": jobs, "boards": boards or {"probed": 4, "available": 4, "live_boards": []},
             "jds": jds if jds is not None else {j["key"]: {"status": "open", "comp": j["comp"]} for j in jobs},
             "filter": filter_summary or {"counts": {"input": 10, "removed": {"title": 6}, "candidates": len(jobs)},
                                          "near_misses": []}}
    if rows is not None:
        files["results"] = {"rows": rows}
    for name, data in files.items():
        with open(os.path.join(run_dir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
    return run_dir


def run(argv, home):
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": home}), contextlib.redirect_stdout(out):
        code = report.main(argv)
    return code, json.loads(out.getvalue())


def page(home):
    with open(os.path.join(home, "runs", RUN_ID, "report.html"), encoding="utf-8") as f:
        return f.read()


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_order_ranks_and_sections(self):
        jobs = [job("gh:a:1", "Staff Frontend"), job("gh:b:2", "Design Engineer", "Linear", state_="changed"),
                job("gh:c:3", "UI Engineer", "Figma")]
        make_run(self.home, jobs, [row("gh:b:2", 6), row("gh:a:1", 7), row("gh:c:3", 3, show=False)],
                 filter_summary={"counts": {"input": 9, "removed": {"title": 5}, "candidates": 3},
                                 "near_misses": [{"key": "gh:d:4", "company": "Ramp", "title": "Web Engineer",
                                                  "reason": "pay tops out below your floor"}]})
        code, out = run([], self.home)
        self.assertEqual((code, out["shown"], out["excluded"], out["skipped"], out["opened"]), (0, 2, 2, [], None))
        html = page(self.home)
        # results.json order, fixed ranks, the changed tag on Linear
        self.assertLess(html.index("Design Engineer"), html.index("Staff Frontend"))
        self.assertIn('data-rank="1" data-fit="6"', html)
        self.assertIn('<th scope="col" class="c-rank" data-sort="rank" aria-sort="ascending">', html)
        # no-JS default: every detail sits open under its row; the script collapses them
        self.assertIn('aria-expanded="true" aria-controls="d1"', html)
        self.assertIn('<tr class="det"><td class="det-cell" colspan="6"><div class="detail" id="d1"', html)
        self.assertIn('<aside class="pane" id="pane" aria-label="Role details" hidden><p class="pane-empty">', html)
        self.assertNotIn(">CHANGED<", html)  # first run (no seen.json): tags would be noise
        self.assertIn('<td dir="auto">UI Engineer</td><td dir="auto">Figma</td><td dir="auto">fit 3/8, below 5</td>', html)
        self.assertIn('<td dir="auto">Web Engineer</td><td dir="auto">Ramp</td><td dir="auto">pay tops out below your floor</td>', html)
        self.assertIn("Checked 4 of 4 company job boards (3 jobs open today)", html)
        self.assertIn("$190,000–$230,000/yr", html)  # full pay in the detail
        self.assertIn('<td class="c-pay">$190k–$230k</td>', html)  # short pay in the table
        self.assertIn('<td class="c-since">Oct 1</td>', html)

    def test_failed_gate_is_the_excluded_reason(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1", 7, show=False, gates={
            "location": "fail", "sponsorship": "pass", "pay": "pass", "exclusions": "pass"})])
        run([], self.home)
        self.assertIn('<td dir="auto">location gate failed</td>', page(self.home))

    def test_escaping_and_unsafe_links(self):
        evil = job("gh:x:1", '<script>alert(1)</script> Engineer', 'Acme "Labs"', url="javascript:alert(1)")
        make_run(self.home, [evil], [row("gh:x:1", why=[{"text": "<b>bold</b>", "quote": "</q><img src=x>"}])])
        run([], self.home)
        html = page(self.home)
        body = html[html.index("<main>"):html.index("</main>")]
        self.assertNotIn("<script>alert", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; Engineer", body)
        self.assertIn("Acme &quot;Labs&quot;", body)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>bold", body)

    def test_page_loads_nothing_and_csp_matches_the_script(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1")])
        run([], self.home)
        html = page(self.home)
        digest = base64.b64encode(hashlib.sha256(report.JS.encode("utf-8")).digest()).decode()
        self.assertIn("script-src 'sha256-%s'" % digest, html)
        self.assertTrue(html.startswith('<!doctype html><html lang="en"><head><meta http-equiv="Content-Security-Policy"'))
        self.assertIn("<script>%s</script>" % report.JS, html)
        self.assertNotRegex(html, r"\son[a-z]+=")  # no inline handlers
        for bad in ("<link", "<img", "<iframe", "fetch(", "XMLHttpRequest", "localStorage", "src="):
            self.assertNotIn(bad, html)
        hrefs = re.findall(r'href="([^"]+)"', html)
        self.assertEqual([h for h in hrefs if not h.startswith("#i-")], ["https://jobs.example.com/gh:a:1"])
        self.assertTrue(all(h[3:] in ("up", "down", "check", "x", "question", "alert", "chev", "out")
                            for h in hrefs if h.startswith("#i-")))  # only the inline icon sprite

    def test_copy_text_names_the_role_and_rtl_is_safe(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1")])
        run([], self.home)
        html = page(self.home)
        self.assertIn('data-copy="save 1 (Vercel, Design Engineer)"', html)
        self.assertIn('data-copy="dismiss 1 (Vercel, Design Engineer): "', html)
        self.assertIn('dir="auto"', html)

    def test_live_fields_win_over_the_candidate_row(self):
        old = job("gh:a:1", "Old title")
        live = dict(job("gh:a:1", "New title"), url="https://jobs.example.com/live")
        make_run(self.home, [old], [row("gh:a:1")], jds={"gh:a:1": {"status": "open", "comp": None, "job": live}})
        run([], self.home)
        html = page(self.home)
        self.assertIn("New title", html)
        self.assertIn("https://jobs.example.com/live", html)
        self.assertIn("pay not listed", html)  # comp from the live check, which had none

    def test_live_check_that_cleared_the_flags_wins(self):
        stale = job("gh:a:1", flags=["work mode unknown — checked on the live job"])
        live = dict(job("gh:a:1"), flags=[])
        make_run(self.home, [stale], [row("gh:a:1")], jds={"gh:a:1": {"status": "open", "comp": None, "job": live}})
        run([], self.home)
        self.assertNotIn("work mode unknown", page(self.home))

    def test_duplicate_and_unknown_keys(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1", 7), row("gh:a:1", 2), row("gh:zz:9")])
        code, out = run([], self.home)
        self.assertEqual((out["shown"], out["skipped"]), (1, ["gh:zz:9"]))

    def test_no_results_names_the_top_removal(self):
        make_run(self.home, [job("gh:a:1")], rows=None, filter_summary={
            "counts": {"input": 50, "removed": {"location": 40, "title": 9}, "candidates": 0}, "near_misses": []})
        code, out = run([], self.home)
        self.assertEqual((code, out["shown"]), (0, 0))
        self.assertIn("Most jobs were removed by location (40 of 50).", page(self.home))

    def test_rerun_nothing_new_and_saved_still_open(self):
        jobs = [job("gh:a:1", state_="saved")]
        make_run(self.home, jobs, rows=None, boards={"probed": 1, "available": 1, "live_boards": ["gh:a", "gh:b"]},
                 filter_summary={"counts": {"input": 2, "removed": {"already_seen": 1, "dismissed_or_applied": 1},
                                            "candidates": 0}, "near_misses": []})
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": self.home}):
            state.write_json_atomic(state.seen_path(), {
                "gh:a:1": {"status": "saved", "title": "Design Engineer", "company": "Vercel", "sig": ""},
                "gh:b:2": {"status": "applied", "title": "Gone Role", "company": "Plaid",
                           "url": "https://jobs.example.com/gone", "sig": ""}})
        run([], self.home)
        html = page(self.home)
        self.assertIn("Nothing new since last time.", html)
        self.assertIn("Checked 1 of 1 company job boards — 0 new or changed since last time.", html)
        self.assertNotIn("open today", html)
        self.assertIn("Saved or applied, still open", html)
        self.assertIn("Closed since last time", html)
        self.assertIn("Gone Role", html)

    def test_quotes_show_where_they_are_cut_but_stay_verbatim(self):
        self.assertEqual(report._clip("gap between design intent and the experience we"),
                         "…gap between design intent and the experience we…")
        self.assertEqual(report._clip("Own the design system."), "Own the design system.")
        self.assertEqual(report._clip("“Ship weekly” is our motto"), "“Ship weekly” is our motto…")

    def test_copy_help_only_with_role_cards(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1")])
        run([], self.home)
        html = page(self.home)
        self.assertIn('role="group" aria-label="Copy a reply"', html)
        self.assertIn('class="copy-help"', html)
        empty = tempfile.mkdtemp()
        make_run(empty, [job("gh:a:1")], rows=None)
        run([], empty)
        self.assertNotIn("copy-help", page(empty).split("<style>")[0] + page(empty).split("</style>")[1])

    def test_new_tag_only_on_reruns(self):
        make_run(self.home, [job("gh:a:1", state_="new")], [row("gh:a:1")])
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": self.home}):
            state.write_json_atomic(state.seen_path(), {"gh:old:1": {"status": "seen", "title": "Old", "sig": ""}})
        run([], self.home)
        self.assertIn('<span class="tag">NEW</span>', page(self.home))

    def test_same_run_gives_the_same_bytes(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1")])
        run([], self.home)
        first = page(self.home)
        run([], self.home)
        self.assertEqual(first, page(self.home))

    def test_out_and_open(self):
        make_run(self.home, [job("gh:a:1")], [row("gh:a:1")])
        target = os.path.join(self.home, "elsewhere", "r.html")
        with mock.patch.object(report.webbrowser, "open", return_value=True) as opener:
            code, out = run(["--out", target, "--open"], self.home)
        self.assertEqual((code, out["report"], out["opened"]), (0, target, True))
        self.assertTrue(opener.call_args.args[0].startswith("file://"))
        self.assertTrue(os.path.exists(target))

    def test_missing_run_files_exit_2(self):
        os.makedirs(os.path.join(self.home, "runs", RUN_ID))
        code, out = run([], self.home)
        self.assertEqual(code, 2)
        self.assertIn("jobs.json", out["error"])
        code, out = run(["--run", "nope"], tempfile.mkdtemp())
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class ShortFormsTest(unittest.TestCase):
    def test_short_pay_and_dates(self):
        usd = {"currency": "USD", "interval": "year"}
        self.assertEqual(report._pay_short(dict(usd, min=190000, max=230000)), "$190k–$230k")
        self.assertEqual(report._pay_short(dict(usd, min=210000, max=None)), "$210k+")
        self.assertEqual(report._pay_short(dict(usd, min=None, max=200000)), "up to $200k")
        self.assertEqual(report._pay_short({"min": 45, "max": 60, "currency": "USD", "interval": "hour"}), "$45–$60/hr")
        self.assertEqual(report._pay_short({}), "pay not listed")
        self.assertEqual(report._short_date("2026-10-01", "2026"), "Oct 1")
        self.assertEqual(report._short_date("2025-12-10", "2026"), "Dec 10, 2025")
