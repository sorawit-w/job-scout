import os
import unittest
from unittest import mock

import adapters
import net
from adapters import ashby, greenhouse, lever

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")
HOSTS = ("greenhouse.io", "ashbyhq.com", "lever.co")


def replay():
    return mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": FIXTURES})


class RegistryTest(unittest.TestCase):
    def test_registry_has_the_three_adapters(self):
        self.assertEqual(sorted(adapters.REGISTRY), ["ashby", "greenhouse", "lever"])
        for module in adapters.REGISTRY.values():
            self.assertEqual(adapters.missing(module), [])


class SchemaMixin:
    KEYS = {"key", "company", "ats", "slug", "job_id", "title", "locations", "countries", "remote",
            "remote_scope", "workplace", "department", "first_published", "url", "comp",
            "description_text", "fetched_at"}

    def check_job(self, job, ats, slug):
        self.assertEqual(set(job), self.KEYS)
        self.assertEqual(job["ats"], ats)
        self.assertTrue(job["key"].startswith("%s:%s:" % (ats, slug)))
        self.assertTrue(job["title"])
        self.assertTrue(any(h in job["url"] for h in HOSTS + ("airtable.com",)), job["url"])
        self.assertIn(job["workplace"], (None, "remote", "hybrid", "onsite"))
        if job["first_published"]:
            self.assertRegex(job["first_published"], r"^\d{4}-\d{2}-\d{2}$")
        if job["comp"] is not None:
            self.assertEqual(job["comp"]["source"], "ats_field")


class GreenhouseTest(SchemaMixin, unittest.TestCase):
    def test_board_lists_and_normalizes(self):
        with replay():
            raws = greenhouse.fetch_board("airtable")
        self.assertEqual(len(raws), 3)
        job = greenhouse.normalize(raws[0], "airtable", "Airtable")
        self.check_job(job, "greenhouse", "airtable")
        self.assertIsNone(job["comp"])  # list endpoint carries no pay
        self.assertNotIn("&lt;", job["description_text"] or "")

    def test_empty_board_is_an_empty_list(self):
        with replay():
            self.assertEqual(greenhouse.fetch_board("webflow"), [])

    def test_unknown_board_is_none(self):
        with replay():
            self.assertIsNone(greenhouse.fetch_board("job-scout-no-such-board"))

    def test_single_job_pay_is_structured(self):
        figma = [f for f in os.listdir(FIXTURES) if f.endswith(".json")]
        url = next(u for u in (self._url(f) for f in figma) if "/figma/jobs/" in u)
        job_id = url.split("/jobs/")[1].split("?")[0]
        with replay():
            raw = greenhouse.fetch_job("figma", job_id)
        job = greenhouse.normalize(raw, "figma", "Figma")
        self.assertEqual(job["comp"]["currency"], "USD")
        self.assertEqual(job["comp"]["min"], 165000)
        self.assertEqual(job["comp"]["interval"], "year")

    def test_closed_job_is_none(self):
        with replay():
            self.assertIsNone(greenhouse.fetch_job("vercel", "1"))

    @staticmethod
    def _url(name):
        import json
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
            return json.load(f)["url"]


class AshbyTest(SchemaMixin, unittest.TestCase):
    def test_board_lists_and_normalizes_with_structured_country(self):
        with replay():
            raws = ashby.fetch_board("attention")
        self.assertEqual(len(raws), 2)
        job = ashby.normalize(raws[0], "attention", "Attention")
        self.check_job(job, "ashby", "attention")
        self.assertIn("US", job["countries"])

    def test_pay_from_salary_component(self):
        with replay():
            raws = ashby.fetch_board("ramp")
        jobs = [ashby.normalize(r, "ramp", "Ramp") for r in raws]
        paid = [j for j in jobs if j["comp"]]
        self.assertTrue(paid)
        self.assertEqual(paid[0]["comp"]["currency"], "USD")
        self.assertEqual(paid[0]["comp"]["interval"], "year")
        self.assertLessEqual(paid[0]["comp"]["min"], paid[0]["comp"]["max"])

    def test_unlisted_jobs_are_skipped(self):
        fake = {"jobs": [{"id": "a", "title": "A", "isListed": True}, {"id": "b", "title": "B", "isListed": False}]}
        with mock.patch.object(net, "get_json", return_value=fake):
            self.assertEqual([j["id"] for j in ashby.fetch_board("x")], ["a"])

    def test_empty_and_unknown_boards(self):
        with replay():
            self.assertEqual(ashby.fetch_board("raycast"), [])
            self.assertIsNone(ashby.fetch_board("job-scout-no-such-board"))

    def test_fetch_job_finds_listed_job_or_none(self):
        with replay():
            raws = ashby.fetch_board("clerk")
            self.assertEqual(ashby.fetch_job("clerk", raws[0]["id"])["id"], raws[0]["id"])
            self.assertIsNone(ashby.fetch_job("clerk", "not-a-real-id"))


class LeverTest(SchemaMixin, unittest.TestCase):
    def test_board_lists_and_normalizes(self):
        with replay():
            raws = lever.fetch_board("airslate")
        self.assertEqual(len(raws), 3)
        job = lever.normalize(raws[0], "airslate", "airSlate")
        self.check_job(job, "lever", "airslate")
        self.assertEqual(job["workplace"], "remote")
        self.assertTrue(job["remote"])
        self.assertTrue(job["description_text"])

    def test_epoch_ms_date(self):
        raw = {"id": "x", "text": "Engineer", "hostedUrl": "https://jobs.lever.co/a/x", "createdAt": 1736955783359,
               "categories": {"location": "Canada, Remote"}, "country": "CA", "workplaceType": "remote",
               "salaryRange": {"min": 100, "max": 200, "currency": "CAD", "interval": "per-year-salary"}}
        job = lever.normalize(raw, "a", "A")
        self.assertEqual(job["first_published"], "2025-01-15")
        self.assertEqual(job["countries"], ["CA"])
        self.assertEqual(job["comp"], {"min": 100, "max": 200, "currency": "CAD", "interval": "year", "source": "ats_field"})

    def test_single_job_and_closed_job(self):
        with replay():
            self.assertEqual(lever.fetch_job("airslate", "9a4add3b-1bbc-453d-94da-502113da3c53")["id"],
                             "9a4add3b-1bbc-453d-94da-502113da3c53")
            self.assertIsNone(lever.fetch_job("airslate", "00000000-0000-0000-0000-000000000000"))

    def test_unknown_board_is_none(self):
        with replay():
            self.assertIsNone(lever.fetch_board("job-scout-no-such-board"))


class QaFixesAdapterTest(unittest.TestCase):
    def test_structured_iso2_country_is_kept(self):
        from adapters import _common
        self.assertEqual(_common.country_codes(["CA"]), ["CA"])
        self.assertEqual(_common.country_codes(["LA"]), ["LA"])  # Laos, not Los Angeles
        self.assertEqual(_common.country_codes(["United States", "de"]), ["DE", "US"])

    def test_lever_remote_with_only_structured_country_gets_a_scope(self):
        raw = {"id": "y", "text": "Engineer", "hostedUrl": "https://jobs.lever.co/a/y", "createdAt": 1736955783359,
               "categories": {"location": "Remote"}, "country": "DE", "workplaceType": "remote"}
        job = lever.normalize(raw, "a", "A")
        self.assertEqual(job["countries"], ["DE"])
        self.assertEqual(job["remote_scope"], ["DE"])

    def test_ashby_fetch_job_reads_a_fresh_cache_without_network(self):
        import tempfile
        import state
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp(), "JOB_SCOUT_REPLAY_DIR": tempfile.mkdtemp()}):
            state.cache_put("ashby", "acme", [{"id": "j1", "title": "A"}])
            self.assertEqual(ashby.fetch_job("acme", "j1")["id"], "j1")

if __name__ == "__main__":
    unittest.main()
