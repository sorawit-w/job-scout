"""Whole-pipeline invariants: what job-scout sends out, and what links it hands back.

Purpose:
    Run probe -> filter -> fetch_jd in-process on the day1 replay world with a profile whose
    every free-text field holds a sentinel, and record every URL net.py is asked for.
      * Privacy: the sentinel never appears in a requested URL, and every request goes to an
        allowed hiring-tool API host — the user's brief never leaves the machine.
      * Search tools (Workday, USAJOBS) are the one exception, and a narrow one: they search with
        the brief's target_roles / title_synonyms, so those titles may leave as search words.
        A second run puts the sentinel in every OTHER free-text field and checks it never
        appears in a URL or a POST body, that POST bodies go only to Workday hosts, and that
        the USAJOBS key stays out of URLs and bodies.
      * Links: every job `url` in jobs.json, candidates.json and fetch_jd's stdout is an https
        employer job page, never an ATS API endpoint or a job aggregator.

Usage:
    python3 -m unittest tests.test_invariants

What it does NOT do: no live network (replay only), and no check of the LLM steps — the
links the LLM shows come from these files, so checking them here covers the source.
"""
import glob
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from unittest import mock

import fetch_jd
import filter as jfilter
import net
import probe
import state
from tests.test_replay_world import WORLD, call, no_network

SENTINEL = "ZZSENTINEL"
API_HOSTS = {"boards-api.greenhouse.io", "api.ashbyhq.com", "api.lever.co", "api.smartrecruiters.com",
             "data.usajobs.gov"}
WORKDAY_HOST = ".myworkdayjobs.com"  # <tenant>.<wdN>.myworkdayjobs.com: API and job pages share the host
JOB_PAGE_HOSTS = {"job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.ashbyhq.com", "jobs.lever.co",
                  "jobs.smartrecruiters.com", "www.usajobs.gov"}
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")
FAKE_KEY = "FAKE-USAJOBS-KEY-0000"
FAKE_EMAIL = "scout-test@example.test"
AGGREGATORS = ("indeed", "linkedin", "ziprecruiter", "glassdoor", "dice", "jobgether", "themuse",
               "simplyhired", "monster", "talent.com")
COMPANIES_CSV = """company,ats,slug,sector,status,jobs,us_share,remote_share,checked_at,source
Kobold Metals,greenhouse,koboldmetals,unknown,live,32,0.5,1.0,2026-10-18,corphunting
Arize AI,greenhouse,arizeai,unknown,live,25,0.5,1.0,2026-10-18,corphunting
Turquoise Health,ashby,turquoise-health,unknown,live,15,1.0,1.0,2026-10-18,corphunting
Reactive Markets,ashby,reactivemarkets,unknown,live,7,0.0,1.0,2026-10-18,corphunting
"""

# Every free-text field carries the sentinel; one real title per role list keeps candidates flowing.
PROFILE = {
    "schema": 1,
    "target_roles": [SENTINEL + " Engineer", "Design Engineer"],
    "title_synonyms": [SENTINEL + " Developer", "Frontend Software Engineer"],
    "title_keywords": [SENTINEL],
    "title_exclusions": [SENTINEL + " Intern"],
    "seniority": [SENTINEL],
    "track": "either",
    "home_base": SENTINEL + " Town, CA",
    "work_modes": ["remote", "hybrid"],
    "commute_cities": [SENTINEL + " City"],
    "remote_scope": ["US"],  # codes only (validate_profile), so it cannot carry free text
    "needs_sponsorship": "yes",
    "base_pay_floor": {"amount": 0, "currency": SENTINEL, "interval": "year"},
    "industries_prefer": [SENTINEL + " Health"],
    "industries_exclude": [SENTINEL + " Gambling"],
    "companies_include": [SENTINEL + " Corp"],
    "companies_exclude": [SENTINEL + " Inc"],
    "must_haves": [SENTINEL + " must"],
    "dealbreakers": [SENTINEL + " never"],
}


def is_allowed_api_host(host):
    return host in API_HOSTS or (host or "").endswith(WORKDAY_HOST)


def is_employer_job_page(url):
    # Rule: https, and the host is where a person reads the job — a known ATS job-page host, or
    # the employer's own domain (Greenhouse's absolute_url can point there). So any https host
    # passes except an ATS API host (machine endpoint) or a job aggregator.
    parts = urllib.parse.urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host in API_HOSTS or parts.path.startswith("/wday/cxs/"):
        return False
    return host in JOB_PAGE_HOSTS or not any(a in host for a in AGGREGATORS)


class PipelineInvariantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.urls = []
        real_attempt = net._attempt

        def logged_attempt(url, budget, *rest):  # the lowest point in net.py that sees every URL
            cls.urls.append(url)
            return real_attempt(url, budget, *rest)

        home = tempfile.mkdtemp()
        companies = os.path.join(home, "seed.csv")
        with open(companies, "w", encoding="utf-8") as f:
            f.write(COMPANIES_CSV)
        env = {"JOB_SCOUT_REPLAY_DIR": WORLD, "JOB_SCOUT_HOME": home,
               "JOB_SCOUT_USAJOBS_KEY": "", "JOB_SCOUT_USAJOBS_EMAIL": ""}  # no search tool in this run
        with mock.patch.dict(os.environ, env), mock.patch.object(net, "_urlopen", no_network), \
                mock.patch.object(net, "_attempt", logged_attempt):
            state.write_json_atomic(state.profile_path(), PROFILE)
            call(probe.main, ["--health"])
            cls.probe_code, probe_out = call(probe.main, ["--companies", companies])  # profile-driven board pick
            cls.filter_code, cls.filter_out = call(jfilter.main, [])
            cls.jd_code, cls.jd_out = call(fetch_jd.main, ["--top", "60"])
        run_dir = os.path.join(home, "runs", probe_out["run"])
        cls.files = {}
        for name in ("jobs.json", "candidates.json"):
            with open(os.path.join(run_dir, name), encoding="utf-8") as f:
                cls.files[name] = json.load(f)

    def test_profile_is_valid(self):
        self.assertEqual(state.validate_profile(PROFILE), [])

    def test_pipeline_ran_end_to_end(self):
        self.assertEqual((self.probe_code, self.filter_code, self.jd_code), (0, 0, 0))
        self.assertGreater(self.filter_out["counts"]["candidates"], 0)
        self.assertTrue(self.jd_out["jobs"], "no candidate reached fetch_jd's live check")
        hosts = {urllib.parse.urlsplit(u).hostname for u in self.urls}
        self.assertTrue(any("/jobs/" in u for u in self.urls), "no Greenhouse single-job request was made")
        self.assertEqual(hosts, {"boards-api.greenhouse.io", "api.ashbyhq.com", "api.lever.co"})

    def test_sentinel_never_leaves_in_a_url(self):
        leaked = [u for u in self.urls if SENTINEL.lower() in urllib.parse.unquote(u).lower()]
        self.assertEqual(leaked, [])

    def test_requests_go_only_to_ats_api_hosts(self):
        others = [u for u in self.urls if urllib.parse.urlsplit(u).scheme != "https"
                  or not is_allowed_api_host(urllib.parse.urlsplit(u).hostname)]
        self.assertEqual(others, [])

    def test_every_job_link_is_an_employer_page(self):
        sources = dict(self.files, fetch_jd=self.jd_out["jobs"])
        for name, jobs in sources.items():
            self.assertTrue(jobs, name)
            bad = [j.get("url") for j in jobs if not is_employer_job_page(j.get("url"))]
            self.assertEqual(bad, [], name)

    def test_link_rule_rejects_api_aggregator_and_http(self):
        for url in ("https://boards-api.greenhouse.io/v1/boards/x/jobs/1", "https://www.indeed.com/viewjob?jk=1",
                    "https://www.linkedin.com/jobs/view/1", "http://jobs.lever.co/x/1", "https://jobgether.com/offer/1",
                    "", None):
            self.assertFalse(is_employer_job_page(url), url)
        for url in ("https://job-boards.greenhouse.io/x/jobs/1", "https://jobs.ashbyhq.com/x/abc",
                    "https://jobs.lever.co/x/abc", "https://careers.example.com/jobs/1"):
            self.assertTrue(is_employer_job_page(url), url)
        self.assertFalse(is_employer_job_page("https://sharp.wd1.myworkdayjobs.com/wday/cxs/sharp/External/job/x"))
        self.assertTrue(is_employer_job_page("https://sharp.wd1.myworkdayjobs.com/External/job/San-Diego-CA/x"))


# The search titles may leave the machine; every other free-text field must not.
SEARCH_PROFILE = dict(PROFILE, target_roles=["nurse"], title_synonyms=["Nurse"],  # one search word: "nurse"
                      work_modes=["remote", "hybrid", "onsite"], commute_cities=[SENTINEL + " City", "San Diego"])


class SearchToolInvariantTest(unittest.TestCase):
    """probe -> filter -> fetch_jd on a Workday board and USAJOBS (with a fake key), replayed."""

    @classmethod
    def setUpClass(cls):
        cls.requests = []  # (url, post body, headers)
        real_attempt = net._attempt

        def logged_attempt(url, budget, post=None, headers=None):
            cls.requests.append((url, post, headers))
            return real_attempt(url, budget, post, headers)

        replay = tempfile.mkdtemp()  # one replay dir holding both tools' fixtures
        for path in glob.glob(os.path.join(FIXTURES, "workday", "*.json")) + \
                glob.glob(os.path.join(FIXTURES, "usajobs", "*.json")):
            shutil.copy(path, replay)
        home = tempfile.mkdtemp()
        env = {"JOB_SCOUT_REPLAY_DIR": replay, "JOB_SCOUT_HOME": home,
               "JOB_SCOUT_USAJOBS_KEY": FAKE_KEY, "JOB_SCOUT_USAJOBS_EMAIL": FAKE_EMAIL}
        with mock.patch.dict(os.environ, env), mock.patch.object(net, "_urlopen", no_network), \
                mock.patch.object(net, "_attempt", logged_attempt):
            state.write_json_atomic(state.profile_path(), SEARCH_PROFILE)
            cls.probe_code, cls.probe_out = call(probe.main, ["--boards", "workday:sharp.wd1.External,usajobs:all"])
            cls.filter_code, cls.filter_out = call(jfilter.main, [])
            cls.jd_code, cls.jd_out = call(fetch_jd.main, ["--top", "60"])

    def test_profile_is_valid(self):
        self.assertEqual(state.validate_profile(SEARCH_PROFILE), [])

    def test_pipeline_ran_end_to_end(self):
        self.assertEqual((self.probe_code, self.filter_code, self.jd_code), (0, 0, 0))
        self.assertEqual(self.probe_out["boards"]["live"], 2)
        self.assertTrue(self.jd_out["jobs"], "no candidate reached fetch_jd's live check")
        self.assertTrue(any(post for _, post, _ in self.requests), "no Workday search was made")
        self.assertTrue(any("data.usajobs.gov/api/Search" in u for u, _, _ in self.requests), "no USAJOBS search")

    def test_only_the_search_titles_leave(self):
        sent = {post["searchText"] for _, post, _ in self.requests if post}
        sent |= {v for u, _, _ in self.requests for k, v in urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)
                 if k == "Keyword"}
        self.assertEqual(sent, {"nurse"})

    def test_sentinel_never_leaves_in_a_url_or_body(self):
        leaked = [(u, post) for u, post, _ in self.requests
                  if SENTINEL.lower() in (urllib.parse.unquote(u) + json.dumps(post)).lower()]
        self.assertEqual(leaked, [])

    def test_post_bodies_go_only_to_workday(self):
        hosts = {urllib.parse.urlsplit(u).hostname for u, post, _ in self.requests if post is not None}
        self.assertTrue(hosts)
        self.assertTrue(all(h.endswith(WORKDAY_HOST) for h in hosts), hosts)

    def test_requests_go_only_to_allowed_api_hosts(self):
        others = [u for u, _, _ in self.requests if urllib.parse.urlsplit(u).scheme != "https"
                  or not is_allowed_api_host(urllib.parse.urlsplit(u).hostname)]
        self.assertEqual(others, [])

    def test_usajobs_key_only_in_usajobs_headers(self):
        for url, post, headers in self.requests:
            self.assertNotIn(FAKE_KEY, url + json.dumps(post))
            self.assertNotIn(FAKE_EMAIL, url + json.dumps(post))
            if headers and FAKE_KEY in json.dumps(headers):
                self.assertEqual(urllib.parse.urlsplit(url).hostname, "data.usajobs.gov")

    def test_every_job_link_is_an_employer_page(self):
        bad = [j.get("url") for j in self.jd_out["jobs"] if not is_employer_job_page(j.get("url"))]
        self.assertEqual(bad, [])


class StatusTableTest(unittest.TestCase):
    """A seen.json status must reach every table that reads one (state strength, mark, filter's rerun drop)."""

    def test_every_status_has_a_strength_and_only_record_sets_judged(self):
        self.assertEqual(set(state._STRENGTH), set(state.SEEN_STATUSES))
        self.assertEqual(set(state.SEEN_STATUSES) - set(state.MARK_STATUSES), {"judged"})
        self.assertEqual(state._STRENGTH[-1], "judged")  # weakest: any other entry for the role decides

    def test_filter_handles_every_state_job_state_returns(self):
        j = {"key": "ashby:acme:1", "title": "Engineer", "variants": [{"key": "ashby:acme:1"}]}
        states = {state.job_state(j, {"ashby:acme:1": {"status": status, "sig": sig, "aliases": []}})
                  for status in state.SEEN_STATUSES for sig in (state.job_sig(j), "000000000000")}
        states.add(state.job_state(j, {}))
        self.assertEqual(states, {"new", "changed", "seen", "saved", "applied", "dismissed", "judged"})
        self.assertTrue(set(jfilter._RERUN_DROP) <= states)
        self.assertEqual(states - set(jfilter._RERUN_DROP), {"new", "changed", "saved", "judged"})  # kept on a rerun


if __name__ == "__main__":
    unittest.main()
