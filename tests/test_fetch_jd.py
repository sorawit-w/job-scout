import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import adapters
import fetch_jd
import net
import state

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")
RUN_ID = "20261018T000000Z"

JD = """About the company
We build tools for designers.

What you'll do:
- Own our design system
- Ship React components

Our culture
We like long lunches and board games.

Requirements
- 5+ years of frontend experience
- Strong TypeScript

Perks
- Free snacks
The base salary range is $150,000 - $180,000 per year.
We are unable to sponsor visas for this role.
Team offsites twice a year."""


def row(ats, slug, job_id, company=None, **extra):
    r = {"key": "%s:%s:%s" % (ats, slug, job_id), "ats": ats, "slug": slug, "job_id": job_id,
         "company": company or slug, "title": "Role %s" % job_id, "url": "https://example.com/%s" % job_id,
         "locations": ["Remote"], "workplace": "remote", "remote_scope": ["US"], "first_published": "2026-10-01",
         "comp": None, "description_text": None, "match": {}, "flags": []}
    r.update(extra)
    return r


FIGMA = row("greenhouse", "figma", "5426468004", "Figma")
VERCEL = row("greenhouse", "vercel", "1", "Vercel")
AIRSLATE = row("lever", "airslate", "9a4add3b-1bbc-453d-94da-502113da3c53", "airSlate")
AIRSLATE_GONE = row("lever", "airslate", "00000000-0000-0000-0000-000000000000", "airSlate")
BRYCE = row("smartrecruiters", "BryceTech", "744000154771568", "BryceTech")
BRYCE_GONE = row("smartrecruiters", "BryceTech", "1", "BryceTech")
WORKDAY = os.path.join(FIXTURES, "workday")
SHARP = "sharp.wd1.External"
SHARP_GONE = row("workday", SHARP, "Clinical-Nurse_JR0000000-1", "Sharp HealthCare")  # recorded 404
USAJOBS = os.path.join(FIXTURES, "usajobs")
USAJOBS_OPEN_ID = "887700000"  # real Historic JOA record: accepting applications until 2026-11-06


def sharp_open():
    """The first posting of the recorded "nurse" search, as filter.py would pass it on."""
    with open(os.path.join(WORKDAY, "b810e0c228ba0cfc.json"), encoding="utf-8") as f:
        posting = json.loads(json.load(f)["body"])["jobPostings"][0]
    job_id = posting["externalPath"].rsplit("/", 1)[-1]
    return row("workday", SHARP, job_id, "Sharp HealthCare", title=posting["title"],
               locations=[posting["locationsText"]], workplace=None, remote_scope=[])


def make_home(rows, jds=None):
    home = tempfile.mkdtemp()
    run_dir = os.path.join(home, "runs", RUN_ID)
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f)
    if jds is not None:
        with open(os.path.join(run_dir, "jds.json"), "w", encoding="utf-8") as f:
            json.dump(jds, f)
    return home


def save_profile(home, **over):
    """A saved brief the Figma fixture job matches: "Account Executive, Enterprise" in San Francisco."""
    p = {"schema": 1, "target_roles": ["Account Executive"], "work_modes": ["remote", "hybrid", "onsite"],
         "commute_cities": ["San Francisco"], "remote_scope": ["US"], "needs_sponsorship": "no",
         "base_pay_floor": None}
    p.update(over)
    with open(os.path.join(home, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)


def run(argv, home, replay_dir=FIXTURES):
    env = {"JOB_SCOUT_REPLAY_DIR": replay_dir, "JOB_SCOUT_HOME": home}
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
        code = fetch_jd.main(argv)
    return code, json.loads(out.getvalue())


def read_jds(home):
    with open(os.path.join(home, "runs", RUN_ID, "jds.json"), encoding="utf-8") as f:
        return json.load(f)


class TrimJdTest(unittest.TestCase):
    def test_keeps_requirement_pay_and_visa_lines_verbatim(self):
        out = fetch_jd.trim_jd(JD)
        for line in ("What you'll do:", "- Own our design system", "Requirements", "- Strong TypeScript",
                     "The base salary range is $150,000 - $180,000 per year.",
                     "We are unable to sponsor visas for this role."):
            self.assertIn(line, out)
        for line in ("long lunches", "Free snacks", "Team offsites", "About the company"):
            self.assertNotIn(line, out)

    def test_every_kept_line_is_copied_from_the_source(self):
        source_lines = set(JD.split("\n"))
        for line in fetch_jd.trim_jd(JD).split("\n"):
            if line != "…":
                self.assertIn(line, source_lines)

    def test_preserves_order_and_joins_blocks(self):
        out = fetch_jd.trim_jd(JD)
        self.assertLess(out.index("Own our design system"), out.index("Strong TypeScript"))
        self.assertLess(out.index("Strong TypeScript"), out.index("$150,000"))
        self.assertIn("\n…\n", out)

    def test_respects_limit_at_a_line_boundary(self):
        text = "Requirements\n" + "\n".join("- requirement number %d is long enough" % i for i in range(200))
        out = fetch_jd.trim_jd(text, limit=300)
        self.assertLessEqual(len(out), 300)
        self.assertTrue(text.startswith(out))  # cut at a whole line, nothing reworded

    def test_falls_back_to_the_head(self):
        text = "We like dogs. " * 400
        self.assertEqual(fetch_jd.trim_jd(text, limit=100), text[:100])

    def test_empty(self):
        self.assertIsNone(fetch_jd.trim_jd(None))


class LiveCheckTest(unittest.TestCase):
    def test_greenhouse_open_with_pay_and_closed(self):
        home = make_home([FIGMA, VERCEL])
        code, out = run(["--top", "2"], home)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], [FIGMA["key"]])
        job = out["jobs"][0]
        self.assertEqual(job["status"], "open")
        self.assertEqual(job["comp"]["currency"], "USD")
        self.assertGreaterEqual(job["comp"]["min"], 165000)
        self.assertTrue(job["jd"])
        self.assertEqual(out["closed"], [{"key": VERCEL["key"], "company": "Vercel", "title": VERCEL["title"]}])
        self.assertEqual(out["unverified"], [])
        self.assertEqual(out["requests"], 2)
        self.assertEqual(set(job), {"key", "company", "title", "url", "locations", "workplace", "remote_scope",
                                    "first_published", "comp", "status", "jd", "flags"})

    def test_live_fields_replace_the_stale_candidate_row(self):
        home = make_home([FIGMA])
        _, out = run(["--top", "1"], home)
        job = out["jobs"][0]
        self.assertNotEqual(job["title"], FIGMA["title"])  # the row's placeholder title is stale
        self.assertIn("figma", job["url"])
        self.assertEqual(job["key"], FIGMA["key"])

    def test_job_that_no_longer_fits_the_brief_is_not_shown(self):
        home = make_home([FIGMA])
        save_profile(home, work_modes=["remote"], remote_scope=["GB"])
        _, out = run(["--top", "1"], home)
        self.assertEqual(out["jobs"], [])
        self.assertEqual(out["unverified"][0]["key"], FIGMA["key"])
        self.assertIn("changed since the search", out["unverified"][0]["error"])

    def test_job_that_still_fits_keeps_live_flags(self):
        home = make_home([FIGMA])
        save_profile(home)
        _, out = run(["--top", "1"], home)
        self.assertEqual([j["key"] for j in out["jobs"]], [FIGMA["key"]])
        self.assertIsInstance(out["jobs"][0]["flags"], list)

    def test_jds_file_written(self):
        home = make_home([FIGMA, VERCEL])
        run(["--top", "2"], home)
        jds = read_jds(home)
        self.assertEqual(jds[FIGMA["key"]]["status"], "open")
        self.assertIn("Enterprise Account Executive", jds[FIGMA["key"]]["full"])
        self.assertIn(jds[FIGMA["key"]]["trimmed"].split("\n")[0], jds[FIGMA["key"]]["full"])
        self.assertIsNone(jds[FIGMA["key"]]["error"])
        self.assertTrue(jds[FIGMA["key"]]["checked_at"].endswith("Z"))
        self.assertEqual(jds[VERCEL["key"]]["status"], "closed")
        self.assertIsNone(jds[VERCEL["key"]]["full"])

    def test_lever_open_and_closed(self):
        home = make_home([AIRSLATE, AIRSLATE_GONE])
        code, out = run(["--keys", "%s,%s" % (AIRSLATE["key"], AIRSLATE_GONE["key"])], home)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], [AIRSLATE["key"]])
        self.assertTrue(read_jds(home)[AIRSLATE["key"]]["full"])
        self.assertEqual([c["key"] for c in out["closed"]], [AIRSLATE_GONE["key"]])

    def test_smartrecruiters_open_with_description_and_pay_and_closed(self):
        home = make_home([BRYCE, BRYCE_GONE])
        code, out = run(["--keys", "%s,%s" % (BRYCE["key"], BRYCE_GONE["key"])], home)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], [BRYCE["key"]])
        job = out["jobs"][0]
        self.assertEqual(job["comp"]["min"], 130000)
        self.assertTrue(job["url"].startswith("https://jobs.smartrecruiters.com/BryceTech/"))
        self.assertIn("Qualifications", read_jds(home)[BRYCE["key"]]["full"])
        self.assertTrue(job["jd"])
        self.assertEqual([c["key"] for c in out["closed"]], [BRYCE_GONE["key"]])
        self.assertEqual(out["requests"], 2)

    def test_ashby_from_a_fresh_cached_board(self):
        with open(os.path.join(FIXTURES, "e81a421f50a9d5e6.json"), encoding="utf-8") as f:
            board = json.loads(json.load(f)["body"])["jobs"]
        job_id = board[0]["id"]
        home = make_home([row("ashby", "attention", job_id), row("ashby", "attention", "no-such-id")])
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": home}):
            state.cache_put("ashby", "attention", board)
        code, out = run(["--top", "2"], home)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], ["ashby:attention:%s" % job_id])
        self.assertEqual([c["key"] for c in out["closed"]], ["ashby:attention:no-such-id"])
        self.assertEqual(out["requests"], 0)  # the cache younger than the TTL counts as the live check

    def test_network_error_is_unverified_never_open_or_closed(self):
        home = make_home([FIGMA])
        with mock.patch.object(adapters.greenhouse, "fetch_job", side_effect=net.Blocked("down", "dns")):
            code, out = run(["--top", "1"], home)
        self.assertEqual(code, 0)
        self.assertEqual(out["jobs"], [])
        self.assertEqual(out["closed"], [])
        self.assertEqual(out["unverified"][0]["key"], FIGMA["key"])
        self.assertIn("down", out["unverified"][0]["error"])
        self.assertEqual(read_jds(home)[FIGMA["key"]]["status"], "unverified")

    def test_empty_or_wrong_200_body_is_unverified(self):
        other = {"id": 999, "title": "Other", "content": "&lt;p&gt;Some other job&lt;/p&gt;"}
        for body in ({}, {"error": "not found"}, [], "oops", other):
            home = make_home([FIGMA])
            with mock.patch.object(adapters.greenhouse, "fetch_job", return_value=body):
                code, out = run(["--top", "1"], home)
            self.assertEqual(code, 0, body)
            self.assertEqual((out["jobs"], out["closed"]), ([], []), body)
            self.assertEqual(out["unverified"][0]["key"], FIGMA["key"], body)
            self.assertTrue(out["unverified"][0]["error"], body)
            self.assertEqual(read_jds(home)[FIGMA["key"]]["status"], "unverified", body)

    def test_keys_over_the_limit_are_reported_not_dropped(self):
        rows = [row("greenhouse", "x", str(i)) for i in range(62)]
        home = make_home(rows)
        with mock.patch.object(adapters.greenhouse, "fetch_job", return_value=None) as fetch:
            code, out = run(["--keys", ",".join(r["key"] for r in rows)], home)
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_count, 60)
        self.assertEqual(out["unverified"], [{"key": r["key"], "error": "not checked: over the 60-job limit"}
                                             for r in rows[60:]])

    def test_top_is_clamped_to_the_ceiling(self):
        home = make_home([row("greenhouse", "x", str(i)) for i in range(100)])
        with mock.patch.object(adapters.greenhouse, "fetch_job", return_value=None) as fetch:
            code, out = run(["--top", "100"], home)
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_count, 60)
        self.assertEqual(len(out["closed"]), 60)
        self.assertEqual(fetch.call_args[0][2].cap, 70)  # net.Budget(n_jobs + 10)

    def test_budget_hit_exits_4_and_keeps_what_it_has(self):
        home = make_home([FIGMA, VERCEL])
        real = adapters.greenhouse.fetch_job
        calls = []

        def fetch(slug, job_id, budget=None):
            calls.append(job_id)
            if len(calls) == 2:
                raise net.BudgetExceeded("request budget of 1 used up")
            return real(slug, job_id, budget)

        with mock.patch.object(adapters.greenhouse, "fetch_job", side_effect=fetch):
            code, out = run(["--top", "2"], home)
        self.assertEqual(code, 4)
        self.assertEqual([j["key"] for j in out["jobs"]], [FIGMA["key"]])
        self.assertEqual(list(read_jds(home)), [FIGMA["key"]])

    def test_unknown_key_is_reported(self):
        home = make_home([VERCEL])
        code, out = run(["--keys", "%s,greenhouse:nope:9" % VERCEL["key"]], home)
        self.assertEqual(code, 0)
        self.assertEqual([c["key"] for c in out["closed"]], [VERCEL["key"]])
        self.assertEqual(out["unverified"][0]["key"], "greenhouse:nope:9")
        self.assertIn("candidates", out["unverified"][0]["error"])

    def test_jds_file_is_merged(self):
        old = {"lever:old:1": {"status": "open", "full": "kept", "trimmed": "kept", "comp": None,
                               "checked_at": "2026-10-18T00:00:00Z", "error": None}}
        home = make_home([VERCEL], jds=old)
        run(["--top", "1"], home)
        jds = read_jds(home)
        self.assertEqual(jds["lever:old:1"]["full"], "kept")
        self.assertEqual(jds[VERCEL["key"]]["status"], "closed")


class SearchSourceLiveCheckTest(unittest.TestCase):
    def test_workday_open_with_description_and_closed(self):
        sharp = sharp_open()
        home = make_home([sharp, SHARP_GONE])
        save_profile(home, target_roles=["nurse"], commute_cities=["San Diego"])
        code, out = run(["--top", "2"], home, replay_dir=WORKDAY)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], [sharp["key"]])
        job = out["jobs"][0]
        self.assertTrue(job["url"].startswith("https://sharp.wd1.myworkdayjobs.com/External/job/"), job["url"])
        self.assertEqual(job["first_published"], "2026-10-18")  # live detail field, not the search row's
        self.assertTrue(job["jd"])
        self.assertTrue(read_jds(home)[sharp["key"]]["full"])
        self.assertEqual([c["key"] for c in out["closed"]], [SHARP_GONE["key"]])
        self.assertEqual(out["requests"], 2)

    def test_workday_live_data_is_refiltered_against_the_brief(self):
        sharp = sharp_open()
        home = make_home([sharp])
        save_profile(home, target_roles=["nurse"], work_modes=["onsite"], commute_cities=["Boston"])
        code, out = run(["--top", "1"], home, replay_dir=WORKDAY)
        self.assertEqual((code, out["jobs"]), (0, []))
        self.assertEqual(read_jds(home)[sharp["key"]]["status"], "open")
        self.assertTrue(out["unverified"][0]["error"].startswith("changed since the search"), out["unverified"])

    def test_usajobs_live_record_without_description_keeps_the_board_description(self):
        # The Historic JOA live check has no description; the search result the row came from does.
        text = "Duties\nProvide nursing care to veterans.\n\nRequirements\n- Active RN license"
        with_text = row("usajobs", "all", USAJOBS_OPEN_ID, "USAJOBS", description_text=text)
        home = make_home([with_text])
        with mock.patch("adapters.usajobs._today", return_value=datetime.date(2026, 10, 19)):
            code, out = run(["--top", "1"], home, replay_dir=USAJOBS)
        self.assertEqual(code, 0)
        self.assertEqual([j["key"] for j in out["jobs"]], [with_text["key"]])
        self.assertIn("Active RN license", out["jobs"][0]["jd"])
        self.assertEqual(read_jds(home)[with_text["key"]]["full"], text)
        self.assertEqual(out["jobs"][0]["url"], "https://www.usajobs.gov/job/%s" % USAJOBS_OPEN_ID)

    def test_usajobs_remote_search_result_stays_remote_after_the_live_check(self):
        # The Historic JOA record has no remote field (only telework), so the search row's remote fields win.
        remote = row("usajobs", "all", USAJOBS_OPEN_ID, "USAJOBS", title="Equipment Specialist (Electronic)",
                     remote=True, description_text="Duties\nMaintain equipment.")
        home = make_home([remote])
        save_profile(home, target_roles=["Equipment Specialist"], work_modes=["remote"], commute_cities=[])
        with mock.patch("adapters.usajobs._today", return_value=datetime.date(2026, 10, 19)):
            code, out = run(["--top", "1"], home, replay_dir=USAJOBS)
        self.assertEqual((code, out["unverified"]), (0, []))
        self.assertEqual((out["jobs"][0]["workplace"], out["jobs"][0]["remote_scope"]), ("remote", ["US"]))

    def test_usajobs_with_no_description_anywhere_is_unverified(self):
        home = make_home([row("usajobs", "all", USAJOBS_OPEN_ID, "USAJOBS")])
        with mock.patch("adapters.usajobs._today", return_value=datetime.date(2026, 10, 19)):
            code, out = run(["--top", "1"], home, replay_dir=USAJOBS)
        self.assertEqual((code, out["jobs"], out["closed"]), (0, [], []))
        self.assertIn("no description", out["unverified"][0]["error"])


class UsageTest(unittest.TestCase):
    def test_needs_keys_or_top(self):
        code, out = run([], make_home([FIGMA]))
        self.assertEqual(code, 2)
        self.assertIn("error", out)

    def test_no_run(self):
        code, out = run(["--top", "1"], tempfile.mkdtemp())
        self.assertEqual(code, 2)
        self.assertIn("error", out)

    def test_no_candidates_file(self):
        home = tempfile.mkdtemp()
        os.makedirs(os.path.join(home, "runs", RUN_ID))
        code, out = run(["--top", "1"], home)
        self.assertEqual(code, 2)
        self.assertIn("candidates.json", out["error"])


if __name__ == "__main__":
    unittest.main()
