"""USAJOBS adapter tests — offline only (replays tests/fixtures/http/usajobs).

Search fixtures are synthetic (no key to record with); Historic JOA fixtures are real
recordings. See tests/fixtures/http/usajobs/README.md.
"""
import datetime
import os
import tempfile
import unittest
from unittest import mock

import net
from adapters import usajobs

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http", "usajobs")
KEY = "FAKE-USAJOBS-KEY-0000"
EMAIL = "scout-test@example.test"
# Real credentials, if the developer has them set: they must never reach a fixture either.
REAL = [os.environ.get(v) for v in (usajobs.KEY_ENV, usajobs.EMAIL_ENV) if os.environ.get(v)]
TERMS = ["nurse", "data scientist", "pharmacist", "never requested"]


def env(enabled=True):
    values = {"JOB_SCOUT_REPLAY_DIR": FIXTURES, "JOB_SCOUT_HOME": tempfile.mkdtemp(),
              usajobs.KEY_ENV: "", usajobs.EMAIL_ENV: ""}
    if enabled:
        values.update({usajobs.KEY_ENV: KEY, usajobs.EMAIL_ENV: EMAIL})
    return mock.patch.dict(os.environ, values)


def today(y, m, d):
    return mock.patch.object(usajobs, "_today", return_value=datetime.date(y, m, d))


class DisabledTest(unittest.TestCase):
    def test_no_credentials_means_none_and_no_request(self):
        for key, email in (("", ""), (KEY, ""), ("", EMAIL)):
            with env(enabled=False), mock.patch.dict(os.environ, {usajobs.KEY_ENV: key, usajobs.EMAIL_ENV: email}), \
                    mock.patch.object(net, "get_json") as get:
                self.assertFalse(usajobs.enabled())
                self.assertIsNone(usajobs.fetch_board("all", terms=["nurse"]))
            get.assert_not_called()

    def test_enabled_needs_both(self):
        with env():
            self.assertTrue(usajobs.enabled())


class SearchTest(unittest.TestCase):
    def test_pages_dedups_and_caps_terms_and_pages(self):
        budget = net.Budget()
        with env():  # a request past the caps has no fixture and would raise Blocked(replay_miss)
            raws = usajobs.fetch_board("all", budget, terms=TERMS)
        ids = [r["MatchedObjectId"] for r in raws]
        self.assertEqual(ids, ["900000100", "900000101", "900000102", "900000103"])
        # nurse p1+p2 (p3 exists but MAX_PAGES=2), data scientist p1, pharmacist p1 (empty); 4th term dropped
        self.assertEqual(budget.used, 4)

    def test_no_terms_is_empty_without_a_request(self):
        with env(), mock.patch.object(net, "get_json") as get:
            self.assertEqual(usajobs.fetch_board("all", terms=[" ", ""]), [])
        get.assert_not_called()

    def test_credentials_go_in_headers_never_the_url(self):
        empty = {"SearchResult": {"SearchResultItems": [], "UserArea": {"NumberOfPages": "0"}}}
        with env(), mock.patch.object(net, "get_json", return_value=empty) as get:
            usajobs.fetch_board("all", terms=["nurse"], location="Denver, Colorado")
        url, headers = get.call_args.args[0], get.call_args.kwargs["headers"]
        self.assertEqual(headers, {"Host": "data.usajobs.gov", "User-Agent": EMAIL, "Authorization-Key": KEY})
        self.assertNotIn(KEY, url)
        self.assertNotIn(EMAIL.split("@")[0], url)
        self.assertIn("LocationName=Denver%2C+Colorado", url)
        self.assertIn("ResultsPerPage=%d" % usajobs.PAGE, url)

    def test_search_respects_the_budget(self):
        with env(), self.assertRaises(net.BudgetExceeded):
            usajobs.fetch_board("all", net.Budget(1), terms=TERMS)


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        with env():
            self.raws = {r["MatchedObjectId"]: r for r in usajobs.fetch_board("all", terms=TERMS)}

    def norm(self, cid):
        return usajobs.normalize(self.raws[cid], "all", "USAJOBS")

    def test_remote_job_with_yearly_pay(self):
        job = self.norm("900000100")
        self.assertEqual(job["key"], "usajobs:all:900000100")
        self.assertEqual(job["ats"], "usajobs")
        self.assertEqual(job["company"], "Veterans Health Administration")
        self.assertEqual(job["department"], "Department of Veterans Affairs")
        self.assertEqual(job["title"], "Nurse (Telehealth)")
        self.assertEqual(job["url"], "https://www.usajobs.gov/job/900000100")
        self.assertEqual(job["first_published"], "2026-10-14")
        self.assertEqual(job["comp"], {"min": 85000.0, "max": 110500.0, "currency": "USD",
                                       "interval": "year", "source": "ats_field"})
        self.assertTrue(job["remote"])
        self.assertEqual(job["workplace"], "remote")
        self.assertIn("Provide telehealth nursing care", job["description_text"])
        self.assertIn("Must hold an active RN license", job["description_text"])

    def test_telework_is_hybrid_with_hourly_pay(self):
        job = self.norm("900000101")
        self.assertEqual(job["workplace"], "hybrid")
        self.assertFalse(job["remote"])
        self.assertEqual(job["comp"]["interval"], "hour")
        self.assertEqual(job["locations"], ["Denver, Colorado"])
        self.assertEqual(job["countries"], ["US"])

    def test_no_telework_is_onsite_with_every_location(self):
        job = self.norm("900000102")
        self.assertEqual(job["workplace"], "onsite")
        self.assertFalse(job["remote"])
        self.assertEqual(job["locations"], ["Bethesda, Maryland", "Baltimore, Maryland"])

    def test_duties_list_port_443_and_unmapped_interval(self):
        job = self.norm("900000103")
        self.assertEqual(job["url"], "https://www.usajobs.gov/job/900000103")  # API adds :443
        self.assertIn("Build models.", job["description_text"])
        self.assertIn("Present findings.", job["description_text"])
        self.assertIsNone(job["comp"]["interval"])  # BW (bi-weekly) is not a schema interval
        self.assertIsNone(job["workplace"])  # no flags at all: not said


class FetchJobTest(unittest.TestCase):
    def test_open_job_returns_the_record(self):
        with env(), today(2026, 10, 19):
            raw = usajobs.fetch_job("all", "887700000")
        self.assertEqual(raw["positionOpeningStatus"], "Accepting applications")
        job = usajobs.normalize(raw, "all", "USAJOBS")
        self.assertEqual(job["key"], "usajobs:all:887700000")
        self.assertEqual(job["url"], "https://www.usajobs.gov/job/887700000")
        self.assertTrue(job["title"])
        self.assertTrue(job["company"])
        self.assertEqual(job["comp"]["interval"], "year")

    def test_past_close_date_is_closed_even_if_status_says_open(self):
        with env(), today(2026, 11, 7):
            self.assertIsNone(usajobs.fetch_job("all", "887700000"))

    def test_close_date_today_is_still_open(self):
        with env(), today(2026, 11, 6):
            self.assertIsNotNone(usajobs.fetch_job("all", "887700000"))

    def test_under_review_is_closed(self):
        with env(), today(2026, 10, 1):
            self.assertIsNone(usajobs.fetch_job("all", "887776000"))

    def test_unknown_control_number_is_none(self):  # the API answers 204 No Content
        with env():
            self.assertIsNone(usajobs.fetch_job("all", "887776101"))

    def test_needs_no_key(self):
        with env(enabled=False), today(2026, 10, 19):
            self.assertIsNotNone(usajobs.fetch_job("all", "887700000"))

    def test_network_errors_raise(self):
        with mock.patch.object(net, "get_json", side_effect=net.Blocked("down", "dns")):
            with self.assertRaises(net.Blocked):
                usajobs.fetch_job("all", "887700000")

    def test_fetch_job_respects_the_budget(self):
        with env(), self.assertRaises(net.BudgetExceeded):
            usajobs.fetch_job("all", "887700000", net.Budget(0))


class NoCredentialsInFixturesTest(unittest.TestCase):
    def test_no_fixture_holds_a_key_an_email_or_the_header(self):
        names = [n for n in os.listdir(FIXTURES) if n.endswith(".json")]
        self.assertGreaterEqual(len(names), 7)
        for name in names:
            with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
                text = f.read()
            for secret in [KEY, EMAIL, "Authorization-Key", "@"] + REAL:
                self.assertNotIn(secret, text, name)


if __name__ == "__main__":
    unittest.main()
