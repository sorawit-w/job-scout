import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import probe

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")


def run(argv, replay_dir=FIXTURES, home=None):
    env = {"JOB_SCOUT_REPLAY_DIR": replay_dir, "JOB_SCOUT_HOME": home or tempfile.mkdtemp()}
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
        code = probe.main(argv)
    return code, json.loads(out.getvalue())


class SelectBoardsTest(unittest.TestCase):
    ROWS = [
        {"company": "Big", "ats": "greenhouse", "slug": "big", "sector": "unknown", "status": "live", "jobs": "900", "us_share": "0.9", "remote_share": "0.1", "source": "corphunting"},
        {"company": "Eval", "ats": "ashby", "slug": "eval", "sector": "ai", "status": "live", "jobs": "5", "us_share": "", "remote_share": "", "source": "seed49"},
        {"company": "Dead", "ats": "lever", "slug": "dead", "sector": "ai", "status": "dead", "jobs": "", "us_share": "", "remote_share": "", "source": "corphunting"},
        {"company": "Fin", "ats": "lever", "slug": "fin", "sector": "fintech", "status": "unchecked", "jobs": "", "us_share": "", "remote_share": "", "source": "corphunting"},
        {"company": "Small", "ats": "greenhouse", "slug": "small", "sector": "unknown", "status": "live", "jobs": "3", "us_share": "0", "remote_share": "0", "source": "corphunting"},
    ]

    def test_priority_order_and_dead_excluded(self):
        user = [{"company": "Mine", "ats": "lever", "slug": "mine"}]
        picked = probe.select_boards(self.ROWS, {"industries_prefer": ["fintech"]}, user, 10)
        self.assertEqual([p[1] for p in picked], ["mine", "eval", "fin", "big", "small"])

    def test_cap_and_exclude(self):
        # no preferred sectors: US/remote share first, then job count (small: 3 jobs > fin: unknown)
        picked = probe.select_boards(self.ROWS, {"companies_exclude": ["Eval"]}, (), 2)
        self.assertEqual([p[1] for p in picked], ["big", "small"])

    def test_include_comes_before_seed49(self):
        picked = probe.select_boards(self.ROWS, {"companies_include": ["Small"]}, (), 3)
        self.assertEqual(picked[0][1], "small")


class ProbeRunTest(unittest.TestCase):
    def test_happy_path_three_boards(self):
        code, out = run(["--boards", "greenhouse:airtable,ashby:attention,lever:airslate"])
        self.assertEqual(code, 0)
        self.assertEqual(out["boards"]["live"], 3)
        self.assertEqual(out["jobs"], 3 + 2 + 3)
        self.assertLessEqual(out["collapsed"], out["jobs"])

    def test_jobs_file_has_employer_urls_and_variants(self):
        home = tempfile.mkdtemp()
        code, out = run(["--boards", "greenhouse:airtable,ashby:attention"], home=home)
        with open(os.path.join(home, "runs", out["run"], "jobs.json"), encoding="utf-8") as f:
            jobs = json.load(f)
        self.assertTrue(jobs)
        for job in jobs:
            self.assertTrue(job["variants"])
            self.assertNotIn("jobgether", job["url"])

    def test_empty_board_is_listed_not_counted_live(self):
        code, out = run(["--boards", "greenhouse:webflow,ashby:raycast"])
        self.assertEqual(code, 0)
        self.assertEqual(out["boards"]["live"], 0)
        self.assertEqual(sorted(out["boards"]["empty"]), ["ashby:raycast", "greenhouse:webflow"])

    def test_unknown_board_is_dead(self):
        code, out = run(["--boards", "lever:job-scout-no-such-board"])
        self.assertEqual(out["boards"]["dead"], ["lever:job-scout-no-such-board"])

    def test_denylisted_board_is_skipped(self):
        code, out = run(["--boards", "lever:jobgether,greenhouse:airtable"])
        self.assertEqual(out["denylisted"], 1)
        self.assertEqual(out["boards"]["live"], 1)

    def test_rerun_within_ttl_uses_cache(self):
        home = tempfile.mkdtemp()
        run(["--boards", "greenhouse:airtable,ashby:attention"], home=home)
        code, out = run(["--boards", "greenhouse:airtable,ashby:attention"], replay_dir=tempfile.mkdtemp(), home=home)
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 0)
        self.assertEqual(out["boards"]["cached"], 2)

    def test_health_blocked_with_empty_replay_dir(self):
        code, out = run(["--health"], replay_dir=tempfile.mkdtemp())
        self.assertEqual(code, 3)
        self.assertFalse(out["ok"])
        self.assertEqual(out["hint"], "replay_miss")

    def test_health_ok_on_fixtures(self):
        code, out = run(["--health"])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    def test_all_blocked_exits_3(self):
        code, out = run(["--boards", "greenhouse:airtable"], replay_dir=tempfile.mkdtemp())
        self.assertEqual(code, 3)

    def test_request_cap_exits_4_with_partial_results(self):
        with mock.patch.object(probe, "RETRY_ALLOWANCE", -1):
            code, out = run(["--boards", "greenhouse:airtable,ashby:attention"])
        self.assertEqual(code, 4)
        self.assertEqual(out["boards"]["probed"], 1)
        self.assertEqual(out["requests"], 1)

    def test_bad_board_spec_is_usage_error(self):
        code, out = run(["--boards", "nocolon"])
        self.assertEqual(code, 2)


class QaFixesProbeTest(unittest.TestCase):
    def test_traversal_slug_is_a_usage_error(self):
        code, out = run(["--boards", "greenhouse:../../x"])
        self.assertEqual(code, 2)

    def test_malformed_user_company_rows_are_skipped(self):
        rows = [{"company": "Mine"}, {"ats": "lever", "slug": ""}, {"company": "Ok", "ats": "lever", "slug": "ok"}]
        picked = probe.select_boards([], {}, rows, 10)
        self.assertEqual([p[1] for p in picked], ["ok"])

    def test_cap_hit_still_writes_partial_jobs_file(self):
        home = tempfile.mkdtemp()
        with mock.patch.object(probe, "RETRY_ALLOWANCE", -1):
            code, out = run(["--boards", "greenhouse:airtable,ashby:attention"], home=home)
        self.assertEqual(code, 4)
        with open(os.path.join(home, "runs", out["run"], "jobs.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f))

    def test_smartrecruiters_row_is_selected_and_probed(self):
        csv_path = os.path.join(tempfile.mkdtemp(), "companies.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("company,ats,slug,sector,status,jobs,us_share,remote_share,checked_at,source\n"
                    "BryceTech,smartrecruiters,BryceTech,unknown,live,45,1.0,0.04,2026-10-19,corphunting\n"
                    "Gone,smartrecruiters,gone,unknown,dead,,,,2026-10-19,corphunting\n")
        code, out = run(["--companies", csv_path])
        self.assertEqual(code, 0)
        self.assertEqual((out["boards"]["selected"], out["boards"]["live"], out["jobs"]), (1, 1, 3))

    def test_board_at_the_adapter_page_cap_cannot_close_roles(self):
        import adapters
        import state
        sr = adapters.REGISTRY["smartrecruiters"]
        raws = [{"id": str(i), "name": "Job %d" % i, "location": {"country": "us"}} for i in range(sr.MAX_JOBS)]
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}), \
                mock.patch.object(sr, "fetch_board", return_value=raws):
            summary, jobs = probe.probe([("smartrecruiters", "bigco", "BigCo")], None)
        self.assertEqual(summary["live"], 1)
        self.assertEqual(summary["jobs"], sr.MAX_JOBS)  # the capped jobs are still shown
        self.assertEqual([e["board"] for e in summary["errors"]], ["smartrecruiters:bigco"])
        run_dir = tempfile.mkdtemp()
        state.write_json_atomic(os.path.join(run_dir, "boards.json"), summary)
        self.assertEqual(state.probed_ok_boards(run_dir), set())

    def test_dead_and_errored_boards_are_not_cached(self):
        home = tempfile.mkdtemp()
        run(["--boards", "lever:job-scout-no-such-board,ashby:no-fixture-board"], home=home)
        self.assertFalse(os.path.exists(os.path.join(home, "cache", "lever", "job-scout-no-such-board.json")))
        self.assertFalse(os.path.exists(os.path.join(home, "cache", "ashby", "no-fixture-board.json")))

if __name__ == "__main__":
    unittest.main()
