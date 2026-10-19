import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import companies
import net

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Own subfolder: test_record_fixtures checks that every top-level fixture is in record_fixtures.urls().
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "http", "companies")
BOARD_FIXTURES = os.path.dirname(FIXTURES)  # greenhouse:airtable (3 jobs), greenhouse:webflow (empty)
WORKDAY_FIXTURES = os.path.join(BOARD_FIXTURES, "workday")  # bouldercolorado.wd1.external blank search (3 jobs)
DATA = os.path.join(ROOT, "skills", "job-scout", "data")
# A fixed slice of the real seed, so imports into data/companies.csv never change these tests.
TEST_SEED = os.path.join(FIXTURES, "seed.csv")


def run(argv, home=None, replay_dir=FIXTURES, seed=TEST_SEED):
    env = {"JOB_SCOUT_REPLAY_DIR": replay_dir, "JOB_SCOUT_HOME": home or tempfile.mkdtemp()}
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), mock.patch.object(companies, "SEED", seed), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = companies.main(argv)
    text = out.getvalue()
    return code, (json.loads(text) if text else None)


def user_rows(home):
    path = os.path.join(home, "companies.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class SlugGuessTest(unittest.TestCase):
    def test_single_word(self):
        self.assertEqual(companies.slug_guesses("Linear"), ["linear", "linearhq", "linear-hq"])

    def test_suffixes_are_stripped(self):
        self.assertEqual(companies.slug_guesses("Scale AI"),
                         ["scaleai", "scale-ai", "scale", "scalehq", "scale-hq"])
        self.assertEqual(companies.slug_guesses("Acme Labs Inc")[2:], ["acme", "acmehq", "acme-hq"])
        self.assertEqual(companies.slug_guesses("Cal.com"), ["cal", "calhq", "cal-hq"])

    def test_tries_are_deduped_and_capped(self):
        tries = companies.plan_tries("Big Data Labs AI", [])
        self.assertEqual(len(tries), companies.MAX_TRIES)
        self.assertEqual(len(set(tries)), len(tries))
        self.assertEqual(tries[:3], [("greenhouse", "bigdatalabsai"), ("ashby", "bigdatalabsai"), ("lever", "bigdatalabsai")])
        # the SmartRecruiters guesses always fit inside the cap, last
        self.assertEqual(tries[-2:], [("smartrecruiters", "BigDataLabsAI"), ("smartrecruiters", "BigDataLabsAI1")])

    def test_smartrecruiters_guesses(self):
        self.assertEqual(companies.sr_guesses("Linear"), ["Linear", "Linear1"])
        self.assertEqual(companies.sr_guesses("international spy museum"),
                         ["InternationalSpyMuseum", "InternationalSpyMuseum1"])
        self.assertEqual(companies.sr_guesses("ABP Food Group & Affiliates")[0], "ABPFoodGroupAndAffiliates")
        self.assertEqual(companies.sr_guesses("Cal.com"), ["Cal", "Cal1"])
        self.assertEqual(companies.sr_guesses("!!!"), [])

    def test_workday_is_never_guessed(self):
        self.assertNotIn("workday", {ats for ats, _ in companies.plan_tries("Kaiser Permanente", [])})


class WorkdayUrlTest(unittest.TestCase):
    def test_valid_urls(self):
        for url, slug in (
                ("https://kaiserpermanente.wd5.myworkdayjobs.com/External", "kaiserpermanente.wd5.External"),
                ("https://kaiserpermanente.wd5.myworkdayjobs.com/External/", "kaiserpermanente.wd5.External"),
                ("https://kaiserpermanente.wd5.myworkdayjobs.com/en-US/External", "kaiserpermanente.wd5.External"),
                ("https://sharp.wd1.myworkdayjobs.com/en-US/External/job/San-Diego-CA/Nurse_JR1?source=x",
                 "sharp.wd1.External"),
                ("https://bouldercolorado.wd1.myworkdayjobs.com/external?q=clerk#top", "bouldercolorado.wd1.external"),
                ("  http://city-of-x.wd12.myworkdayjobs.com/fr-CA/Careers_2  ", "city-of-x.wd12.Careers_2")):
            self.assertEqual(companies.workday_slug(url), slug, url)

    def test_invalid_urls(self):
        for url in ("https://evil.com/myworkdayjobs.com/External",
                    "https://kaiser.wd5.myworkdayjobs.com.evil.com/External",
                    "https://evil.com@kaiser.wd5.myworkdayjobs.com/External",
                    "https://kaiser.wd5.myworkdayjobs.com:8443/External",
                    "https://KaiserPermanente.wd5.myworkdayjobs.com/External",  # uppercase tenant
                    "https://kaiser.myworkdayjobs.com/External",  # no wdN
                    "https://kaiser.wd5.myworkdayjobs.com/",  # no site
                    "https://kaiser.wd5.myworkdayjobs.com/en-US/",
                    "https://kaiser.wd5.myworkdayjobs.com/../External",
                    "https://kaiser.wd5.myworkdayjobs.com/%2e%2e/External",
                    "https://kaiser.wd5.myworkdayjobs.com/Ext.ernal",
                    "ftp://kaiser.wd5.myworkdayjobs.com/External",
                    "kaiser.wd5.myworkdayjobs.com/External"):
            with self.assertRaises(ValueError, msg=url):
                companies.workday_slug(url)


class AddTest(unittest.TestCase):
    def test_seed_hit_costs_no_requests_and_is_saved(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Linear"], home=home)
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 0)
        res = out["results"][0]
        self.assertEqual([(h["ats"], h["slug"], h["from"]) for h in res["hits"]], [("ashby", "linear", "seed")])
        self.assertTrue(res["saved"])
        self.assertIsNone(res["suggest_row"])
        self.assertNotIn("sample_titles", res["hits"][0])  # seed boards need no confirming
        rows = user_rows(home)
        self.assertEqual([(r["ats"], r["slug"], r["source"], r["status"]) for r in rows],
                         [("ashby", "linear", "user", "live")])

    def test_refresh_refetches_the_seed_board(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Linear", "--refresh"], home=home)
        self.assertEqual((code, out["requests"]), (0, 1))
        res = out["results"][0]
        self.assertEqual(res["tried"], ["ashby:linear"])
        self.assertEqual((res["hits"][0]["from"], res["hits"][0]["jobs"]), ("seed", 3))
        self.assertIsNone(res["suggest_row"])
        self.assertEqual([r["jobs"] for r in user_rows(home)], ["3"])

    def test_dead_seed_row_does_not_stop_the_guesses(self):
        seed = os.path.join(tempfile.mkdtemp(), "companies.csv")
        with open(seed, "w", encoding="utf-8", newline="") as f:
            f.write(",".join(companies.HEADER) + "\nSnyk,workday,snyk.wd1.External,unknown,dead,,,,,test\n")
        home = tempfile.mkdtemp()
        code, out = run(["add", "Snyk"], home=home, seed=seed)
        self.assertEqual((code, out["requests"]), (0, 2))  # the dead board is skipped, not refetched
        res = out["results"][0]
        self.assertEqual(res["tried"], ["greenhouse:snyk", "ashby:snyk"])
        self.assertEqual((res["hits"][0]["slug"], res["hits"][0]["from"]), ("snyk", "guess"))
        self.assertEqual([r["slug"] for r in user_rows(home)], ["snyk"])

    def test_unchecked_seed_board_is_fetched_not_skipped(self):
        home = tempfile.mkdtemp()  # City of Boulder: an imported Workday seed row, status "unchecked"
        code, out = run(["add", "City of Boulder"], home=home, replay_dir=WORKDAY_FIXTURES)
        self.assertEqual((code, out["requests"]), (0, 1))
        res = out["results"][0]
        self.assertEqual(res["tried"], ["workday:bouldercolorado.wd1.external"])
        self.assertEqual((res["hits"][0]["jobs"], res["hits"][0]["from"]), (3, "seed"))
        self.assertIsNone(res["suggest_row"])
        self.assertEqual([(r["ats"], r["status"], r["jobs"]) for r in user_rows(home)], [("workday", "live", "3")])

    def test_guessed_hit_not_in_seed(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Snyk"], home=home)
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 2)
        res = out["results"][0]
        self.assertEqual(res["tried"], ["greenhouse:snyk", "ashby:snyk"])
        hit = res["hits"][0]
        self.assertEqual((hit["ats"], hit["slug"], hit["company"], hit["jobs"], hit["from"]),
                         ("ashby", "snyk", "Snyk", 3, "guess"))
        self.assertTrue(res["saved"])
        self.assertRegex(res["suggest_row"], r"^Snyk,ashby,snyk,unknown,live,3,,,\d{4}-\d\d-\d\d,community$")
        text = hit["issue_text"]
        self.assertIn(res["suggest_row"], text)
        self.assertEqual(text.count("http"), 1)
        self.assertIn("https://api.ashbyhq.com/posting-api/job-board/snyk", text)
        self.assertIn("looks like", text)  # same-name companies exist: the user confirms the board
        self.assertEqual(hit["sample_titles"], ["Senior Product Security Engineer", "Senior Revenue Accountant",
                                                "Technical Success Manager"])
        self.assertTrue(hit["sample_url"].startswith("https://jobs.ashbyhq.com/snyk/"))
        rows = user_rows(home)
        self.assertEqual([(r["company"], r["ats"], r["slug"], r["source"], r["jobs"]) for r in rows],
                         [("Snyk", "ashby", "snyk", "user", "3")])

    def test_smartrecruiters_guess_hit(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "International Spy Museum"], home=home)
        self.assertEqual(code, 0)
        res = out["results"][0]
        self.assertEqual(len(res["tried"]), 13)  # 4 slugs x 3 hiring tools (all 404), then SmartRecruiters
        self.assertEqual(out["requests"], 13)
        self.assertEqual(res["tried"][-1], "smartrecruiters:InternationalSpyMuseum")
        hit = res["hits"][0]
        self.assertEqual((hit["ats"], hit["slug"], hit["jobs"], hit["from"]),
                         ("smartrecruiters", "InternationalSpyMuseum", 3, "guess"))
        self.assertEqual(len(hit["sample_titles"]), 3)
        self.assertTrue(hit["sample_url"].startswith("https://jobs.smartrecruiters.com/"))
        self.assertIn("https://api.smartrecruiters.com/v1/companies/InternationalSpyMuseum/postings", hit["issue_text"])
        self.assertRegex(res["suggest_row"],
                         r"^International Spy Museum,smartrecruiters,InternationalSpyMuseum,unknown,live,3,")
        self.assertEqual([(r["ats"], r["slug"], r["source"]) for r in user_rows(home)],
                         [("smartrecruiters", "InternationalSpyMuseum", "user")])

    def test_unknown_company_writes_nothing(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Zzqx"], home=home)
        self.assertEqual(code, 0)
        res = out["results"][0]
        self.assertEqual(res["hits"], [])
        self.assertFalse(res["saved"])
        self.assertEqual(len(res["tried"]), 11)
        self.assertEqual(out["requests"], 11)
        # SmartRecruiters answers 200 with zero postings for an unknown company: not a hit
        self.assertEqual(res["tried"][-2:], ["smartrecruiters:Zzqx", "smartrecruiters:Zzqx1"])
        self.assertEqual(res["errors"], [])
        self.assertIn("not found", res["note"])
        self.assertIn("Workday", res["note"])  # Workday cannot be guessed: point at --board
        self.assertIn("--board", res["note"])
        self.assertFalse(os.path.exists(os.path.join(home, "companies.csv")))

    def test_several_names_share_one_budget_and_dedupe_rows(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Linear", "Snyk", "Zzqx"], home=home)
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 13)
        run(["add", "Linear", "snyk"], home=home)  # again: same boards, no duplicate rows
        self.assertEqual(sorted((r["ats"], r["slug"]) for r in user_rows(home)),
                         [("ashby", "linear"), ("ashby", "snyk")])

    def test_budget_hit_prints_partial_and_saves_what_was_found(self):
        home = tempfile.mkdtemp()
        with mock.patch.object(companies, "budget_for", lambda n: net.Budget(2)):
            code, out = run(["add", "Snyk", "Zzqx"], home=home)
        self.assertEqual(code, 4)
        self.assertEqual(out["requests"], 2)
        self.assertTrue(out["results"][0]["saved"])
        self.assertEqual(out["results"][1]["hits"], [])
        self.assertIn("cap", out["results"][1]["note"])
        self.assertEqual([r["slug"] for r in user_rows(home)], ["snyk"])

    def test_every_request_blocked_exits_3(self):
        code, out = run(["add", "Qqzz"], replay_dir=tempfile.mkdtemp())  # no fixtures: replay_miss
        self.assertEqual(code, 3)
        self.assertFalse(out["results"][0]["saved"])

    def test_blocked_network_stops_guessing_after_3_in_a_row(self):
        code, out = run(["add", "Qqzz", "Wwxx"], replay_dir=tempfile.mkdtemp())  # every request: replay_miss
        self.assertEqual(code, 3)
        self.assertEqual(out["requests"], 6)
        for res in out["results"]:
            self.assertEqual(len(res["tried"]), 3)
            self.assertIn("blocked", res["note"])

    def test_nothing_is_written_under_the_repo(self):
        before = {n: os.stat(os.path.join(DATA, n)).st_mtime for n in os.listdir(DATA)}
        home = tempfile.mkdtemp()
        run(["add", "Linear", "Snyk", "Zzqx"], home=home)
        run(["remove", "Linear"], home=home)
        after = {n: os.stat(os.path.join(DATA, n)).st_mtime for n in os.listdir(DATA)}
        self.assertEqual(before, after)
        self.assertEqual([r["slug"] for r in user_rows(home)], ["snyk"])


class BoardTest(unittest.TestCase):
    def test_known_board_is_fetched_and_saved(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Airtable", "--board", "greenhouse:airtable"], home=home, replay_dir=BOARD_FIXTURES)
        self.assertEqual((code, out["requests"]), (0, 1))
        res = out["results"][0]
        self.assertEqual(res["tried"], ["greenhouse:airtable"])
        hit = res["hits"][0]
        self.assertEqual((hit["ats"], hit["slug"], hit["company"], hit["jobs"], hit["from"]),
                         ("greenhouse", "airtable", "Airtable", 3, "board"))
        self.assertEqual(len(hit["sample_titles"]), 3)
        self.assertTrue(hit["sample_url"].startswith("https://job-boards.greenhouse.io/airtable/jobs/"))
        self.assertTrue(res["saved"])
        self.assertEqual([(r["company"], r["ats"], r["slug"], r["source"], r["jobs"]) for r in user_rows(home)],
                         [("Airtable", "greenhouse", "airtable", "user", "3")])

    def test_board_with_no_jobs_saves_nothing(self):
        home = tempfile.mkdtemp()
        code, out = run(["add", "Webflow", "--board", "greenhouse:webflow"], home=home, replay_dir=BOARD_FIXTURES)
        self.assertEqual(code, 0)
        res = out["results"][0]
        self.assertEqual((res["hits"], res["saved"]), ([], False))
        self.assertIn("not found", res["note"])
        self.assertEqual(user_rows(home), [])

    def test_workday_careers_url_is_checked_and_saved(self):
        home = tempfile.mkdtemp()
        url = "https://bouldercolorado.wd1.myworkdayjobs.com/en-US/external?q=clerk"
        code, out = run(["add", "City of Boulder", "--board", url], home=home, replay_dir=WORKDAY_FIXTURES)
        self.assertEqual((code, out["requests"]), (0, 1))  # one blank search
        res = out["results"][0]
        self.assertEqual(res["tried"], ["workday:bouldercolorado.wd1.external"])
        hit = res["hits"][0]
        self.assertEqual((hit["ats"], hit["slug"], hit["jobs"], hit["from"]),
                         ("workday", "bouldercolorado.wd1.external", 3, "board"))
        self.assertEqual(hit["sample_titles"][0], "Traffic Signal Maintenance Technician III")
        self.assertTrue(hit["sample_url"].startswith("https://bouldercolorado.wd1.myworkdayjobs.com/external/job/"))
        self.assertIsNone(res["suggest_row"])
        self.assertEqual([(r["company"], r["ats"], r["slug"], r["source"], r["jobs"]) for r in user_rows(home)],
                         [("City of Boulder", "workday", "bouldercolorado.wd1.external", "user", "3")])

    def test_workday_ats_slug_form_and_gone_boards(self):
        code, out = run(["add", "City of Boulder", "--board", "workday:bouldercolorado.wd1.external"],
                        replay_dir=WORKDAY_FIXTURES)
        self.assertEqual((code, out["results"][0]["saved"]), (0, True))
        for board in ("workday:zzqxjobscout.wd1.careers", "workday:sharp.wd1.ZzqxNoSuchSite"):  # 422, 404
            home = tempfile.mkdtemp()
            code, out = run(["add", "Zzqx", "--board", board], home=home, replay_dir=WORKDAY_FIXTURES)
            self.assertEqual(code, 0, board)
            self.assertEqual((out["results"][0]["hits"], out["results"][0]["saved"]), ([], False))
            self.assertIn("not found", out["results"][0]["note"])
            self.assertEqual(user_rows(home), [])

    def test_bad_workday_board_exits_2_with_help(self):
        for board in ("https://evil.com/myworkdayjobs.com/External", "https://KP.wd5.myworkdayjobs.com/External",
                      "workday:a", "workday:sharp.wd1.../x", "workday:Sharp.wd1.External"):
            code, out = run(["add", "A", "--board", board], replay_dir=WORKDAY_FIXTURES)
            self.assertEqual(code, 2, board)
            self.assertIn("myworkdayjobs.com", out["error"])

    def test_bad_board_input_exits_2(self):
        for argv in (["add", "A", "B", "--board", "greenhouse:a"], ["add", "A", "--board", "workday:a"],
                     ["add", "A", "--board", "greenhouse:../a"], ["add", "A", "--board", "greenhouse:"],
                     ["add", "A", "--board", "greenhouse"], ["add", "A", "--board", "greenhouse:.a"],
                     ["add", "A", "--board", "usajobs:x"]):  # not a company board
            code, out = run(argv, replay_dir=BOARD_FIXTURES)
            self.assertEqual(code, 2, argv)
            self.assertIn("error", out)


class UsageTest(unittest.TestCase):
    def test_bad_input_exits_2(self):
        for argv in ([], ["add"], ["add", "a", "b", "c", "d", "e", "f"], ["add", "   "],
                     ["add", "x" * 81], ["add", "a/b"], ["add", "..\\evil"], ["remove"], ["frobnicate"]):
            code, _ = run(argv)
            self.assertEqual(code, 2, argv)

    def test_five_names_is_allowed(self):
        code, out = run(["add", "Linear", "Figma", "Notion", "Vercel", "Brex"])
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 0)


class ListRemoveTest(unittest.TestCase):
    def test_list_and_remove(self):
        home = tempfile.mkdtemp()
        code, out = run(["list"], home=home)
        self.assertEqual((code, out), (0, {"companies": []}))
        run(["add", "Linear", "Snyk"], home=home)
        code, out = run(["list"], home=home)
        self.assertEqual(sorted(r["slug"] for r in out["companies"]), ["linear", "snyk"])
        code, out = run(["remove", "linear inc"], home=home)
        self.assertEqual(code, 0)
        self.assertEqual([r["slug"] for r in out["removed"]], ["linear"])
        self.assertEqual(out["remaining"], 1)
        code, out = run(["remove", "Nobody"], home=home)
        self.assertEqual((out["removed"], out["remaining"]), ([], 1))


if __name__ == "__main__":
    unittest.main()


class BudgetSizeTest(unittest.TestCase):
    def test_every_smartrecruiters_guess_may_read_all_its_pages(self):
        sr = companies.ADAPTERS["smartrecruiters"]
        per_name = companies.MAX_TRIES + 2 * (sr.MAX_PAGES - 1)  # two guesses, each up to MAX_PAGES requests
        self.assertEqual(companies.budget_for(5).cap, 5 * per_name + companies.RETRY_ALLOWANCE)
