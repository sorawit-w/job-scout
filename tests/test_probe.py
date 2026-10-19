import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import probe

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")
WORKDAY = os.path.join(FIXTURES, "workday")
USAJOBS = os.path.join(FIXTURES, "usajobs")
SHARP = "sharp.wd1.External"  # Workday fixtures: a "nurse" search, first page
KEY_ENV, EMAIL_ENV = "JOB_SCOUT_USAJOBS_KEY", "JOB_SCOUT_USAJOBS_EMAIL"
FAKE_KEY = {KEY_ENV: "FAKE-USAJOBS-KEY-0000", EMAIL_ENV: "scout-test@example.test"}


def run(argv, replay_dir=FIXTURES, home=None, extra_env=None):
    env = {"JOB_SCOUT_REPLAY_DIR": replay_dir, "JOB_SCOUT_HOME": home or tempfile.mkdtemp(),
           KEY_ENV: "", EMAIL_ENV: ""}  # a developer's real USAJOBS key never reaches these tests
    env.update(extra_env or {})
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
        picked = probe.select_boards(self.ROWS, {"target_roles": ["Frontend Engineer"], "industries_prefer": ["fintech"]}, user, 10)
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


def save_profile(home, **fields):
    p = {"schema": 1, "target_roles": ["nurse"], "work_modes": ["onsite"], "needs_sponsorship": "no",
         "base_pay_floor": None}
    p.update(fields)
    with open(os.path.join(home, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    return home


def boards_file(home, out):
    with open(os.path.join(home, "runs", out["run"], "boards.json"), encoding="utf-8") as f:
        return json.load(f)


class SearchTermsTest(unittest.TestCase):
    def test_roles_then_synonyms_without_blanks_or_repeats(self):
        p = {"target_roles": ["Registered Nurse", " Clinical Nurse "], "title_synonyms": ["registered nurse", "", "RN"],
             "title_keywords": ["icu"]}
        self.assertEqual(probe.search_terms(p), ["Registered Nurse", "Clinical Nurse", "RN"])

    def test_no_titles(self):
        self.assertEqual(probe.search_terms({}), [])


class BriefFieldTest(unittest.TestCase):
    def test_tech(self):
        for p in ({"target_roles": ["Design Engineer"]}, {"target_roles": ["Product Manager"]},
                  {"target_roles": ["Nurse"], "title_synonyms": ["Software Developer"]},
                  {"title_keywords": ["devops"]}, {"target_roles": ["ML Researcher"]},
                  {"target_roles": ["Machine Learning Scientist"]}, {"target_roles": ["Front-end Lead"]},
                  {"target_roles": ["Data Analyst"]}, {"target_roles": ["Security Engineer"]}):
            self.assertEqual(probe.brief_field(p), "tech", p)

    def test_general(self):
        for p in ({"target_roles": ["Registered Nurse", "Clinical Nurse"]}, {"target_roles": ["Pharmacist"]},
                  {"target_roles": ["Account Executive"]}, {"target_roles": ["Security Guard"]}, {}):
            self.assertEqual(probe.brief_field(p), "general", p)


class FieldSelectionTest(unittest.TestCase):
    def rows(self):
        def r(ats, slug, us, source="corphunting"):
            return {"company": slug, "ats": ats, "slug": slug, "sector": "unknown", "status": "live", "jobs": "10",
                    "us_share": str(us), "remote_share": "0", "source": source}
        return [r("greenhouse", "gh", 0.5), r("workday", "acme.wd1.External", 0.9), r("smartrecruiters", "sr", 0.8),
                r("ashby", "ash", 0.4), r("lever", "lev", 0.3), r("workday", "seed.wd5.Careers", 0.0, "seed49")]

    def slugs(self, profile, **kw):
        user = [{"company": "Mine", "ats": "lever", "slug": "mine"}]
        return [p[1] for p in probe.select_boards(self.rows(), profile, user, **kw)]

    def test_tech_rest_tier_prefers_greenhouse_ashby_lever(self):
        self.assertEqual(self.slugs({"target_roles": ["Frontend Engineer"]}),
                         ["mine", "seed.wd5.Careers", "gh", "ash", "lev", "sr", "acme.wd1.External"])

    def test_general_rest_tier_prefers_workday_then_smartrecruiters(self):
        # the tech eval boards (seed49) get no head start for a general brief
        self.assertEqual(self.slugs({"target_roles": ["Registered Nurse"]}),
                         ["mine", "acme.wd1.External", "seed.wd5.Careers", "sr", "gh", "ash", "lev"])

    def test_usajobs_follows_user_companies_for_a_general_brief(self):
        self.assertEqual(self.slugs({"target_roles": ["Registered Nurse"]}, max_boards=3, usajobs=True),
                         ["mine", "all", "acme.wd1.External"])

    def test_preferred_industry_words_match_company_names(self):
        def r(company, ats="workday", us="0.9"):
            return {"company": company, "ats": ats, "slug": company.lower().replace(" ", "-"), "sector": "unknown",
                    "status": "live", "jobs": "10", "us_share": us, "remote_share": "0", "source": "corphunting"}
        rows = [r("Acme Retail"), r("Valley Systems"), r("Sharp HealthCare", us="0.1"), r("Mercy Hospital", "greenhouse"),
                r("Denver Health", us="0.2")]
        brief = {"target_roles": ["Registered Nurse"], "industries_prefer": ["hospitals and health systems"]}
        self.assertEqual([p[2] for p in probe.select_boards(rows, brief)],
                         ["Denver Health", "Sharp HealthCare", "Mercy Hospital", "Acme Retail", "Valley Systems"])

    def test_usajobs_takes_the_last_slot_for_a_tech_brief(self):
        picked = probe.select_boards(self.rows(), {"target_roles": ["Frontend Engineer"]}, (), 3, usajobs=True)
        self.assertEqual(picked, [("workday", "seed.wd5.Careers", "seed.wd5.Careers"),
                                  ("greenhouse", "gh", "gh"), ("usajobs", "all", "USAJOBS")])

    def test_no_usajobs_unless_asked(self):
        self.assertNotIn("all", self.slugs({"target_roles": ["Registered Nurse"]}))


class PartialBoardTest(unittest.TestCase):
    def test_workday_board_searches_with_the_brief_and_is_partial(self):
        home = save_profile(tempfile.mkdtemp(), title_synonyms=["Nurse"])  # repeat: one search only
        code, out = run(["--boards", "workday:" + SHARP], replay_dir=WORKDAY, home=home)
        self.assertEqual(code, 0)
        self.assertEqual((out["boards"]["live"], out["jobs"], out["requests"]), (1, 3, 1))
        b = boards_file(home, out)
        self.assertEqual((b["live_boards"], b["partial_boards"]), ([], ["workday:" + SHARP]))

    def test_bad_workday_slug_is_an_error_not_a_crash(self):
        home = save_profile(tempfile.mkdtemp())
        code, out = run(["--boards", "workday:not-a-workday-slug,workday:" + SHARP], replay_dir=WORKDAY, home=home)
        self.assertEqual((code, out["boards"]["live"]), (0, 1))
        self.assertEqual([e["board"] for e in out["boards"]["errors"]], ["workday:not-a-workday-slug"])

    def test_partial_board_is_never_cached(self):
        home = save_profile(tempfile.mkdtemp())
        run(["--boards", "workday:" + SHARP], replay_dir=WORKDAY, home=home)
        self.assertFalse(os.path.exists(os.path.join(home, "cache", "workday")))

    def test_terms_go_only_to_partial_adapters_cut_to_their_cap(self):
        import adapters
        wd, gh = adapters.REGISTRY["workday"], adapters.REGISTRY["greenhouse"]
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}), \
                mock.patch.object(wd, "fetch_board", return_value=[]) as wd_fetch, \
                mock.patch.object(gh, "fetch_board", return_value=[]) as gh_fetch:
            probe.probe([("workday", SHARP, "Sharp"), ("greenhouse", "x", "X")], None, terms=list("abcde"))
        wd_fetch.assert_called_once_with(SHARP, None, terms=list("abcde")[:wd.MAX_TERMS])
        gh_fetch.assert_called_once_with("x", None)

    def test_request_cap_counts_every_search_page(self):
        import adapters
        wd = adapters.REGISTRY["workday"]
        boards = [("greenhouse", "a", "A"), ("workday", SHARP, "S")]
        self.assertEqual(probe.request_cap(boards, list("abcdef")), 1 + wd.MAX_TERMS * wd.MAX_PAGES + probe.RETRY_ALLOWANCE)
        self.assertEqual(probe.request_cap(boards, ["a"]), 1 + wd.MAX_PAGES + probe.RETRY_ALLOWANCE)
        self.assertEqual(probe.request_cap(boards, []), 2 + probe.RETRY_ALLOWANCE)

    def test_usajobs_without_a_key_is_skipped_once_with_no_request(self):
        home = save_profile(tempfile.mkdtemp())
        code, out = run(["--boards", "usajobs:all,greenhouse:airtable"], home=home)
        self.assertEqual(code, 0)
        self.assertEqual((out["skipped"], out["requests"], out["boards"]["dead"]), (["usajobs: no key"], 1, []))
        self.assertEqual(boards_file(home, out)["skipped"], ["usajobs: no key"])

    def test_usajobs_with_a_key_is_picked_and_searched_with_the_brief(self):
        home = save_profile(tempfile.mkdtemp(), target_roles=["nurse", "data scientist"])
        csv_path = os.path.join(home, "seed.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("company,ats,slug,sector,status,jobs,us_share,remote_share,checked_at,source\n")
        code, out = run(["--companies", csv_path], replay_dir=USAJOBS, home=home, extra_env=FAKE_KEY)
        self.assertEqual(code, 0)
        self.assertEqual((out["boards"]["selected"], out["boards"]["live"], out["skipped"]), (1, 1, []))
        self.assertEqual(out["requests"], 3)  # nurse pages 1-2, data scientist page 1
        self.assertEqual(boards_file(home, out)["partial_boards"], ["usajobs:all"])


if __name__ == "__main__":
    unittest.main()
