import json
import os
import tempfile
import unittest
from unittest import mock

import adapters
import net
from adapters import workday

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http", "workday")
SHARP = "sharp.wd1.External"  # hospital system (Sharp HealthCare)
BOULDER = "bouldercolorado.wd1.external"  # public employer (City of Boulder)
CLOSED_ID = "Clinical-Nurse_JR0000000-1"  # recorded as a real 404


def replay(directory=FIXTURES):
    return mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": directory})


def no_network():
    return mock.patch.object(net, "_urlopen", side_effect=AssertionError("network touched"))


class _Resp:
    """Stands in for urlopen()'s response."""

    def __init__(self, status, body):
        self.status, self.headers, self._body = status, {}, body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _page(term, offset, size, total):
    return {"total": total, "jobPostings": [
        {"title": "%s %d" % (term, offset + i), "externalPath": "/job/X/%s-%d_JR%d" % (term, offset + i, offset + i),
         "locationsText": "Boulder, CO", "postedOn": "Posted Today"} for i in range(size)]}


class ContractTest(unittest.TestCase):
    def test_workday_meets_the_adapter_contract(self):
        self.assertEqual(adapters.missing(workday), [])


class SlugTest(unittest.TestCase):
    BAD = ["", "sharp", "sharp.wd1", "sharp.wd1.External.x", "Sharp.wd1.External", "sharp.wdx.External",
           "sharp.wd.External", "sharp.wd1.Ext/../x", "evil.com/a.wd1.s", "sharp.wd1.Ext?x=1", "sharp.wd1.Ext#x",
           "sharp:wd1:External", "sharp.wd1.Ext ernal", "sharp.wd1.External\n", "sh@rp.wd1.External"]

    def test_bad_slugs_raise_before_any_request(self):
        with no_network():
            for slug in self.BAD:
                with self.subTest(slug=slug):
                    self.assertRaises(ValueError, workday.fetch_board, slug)
                    self.assertRaises(ValueError, workday.fetch_job, slug, "x_JR1")
                    self.assertRaises(ValueError, workday.normalize, {"externalPath": "/job/A/x_JR1"}, slug, "Co")

    def test_good_slugs_build_the_board_urls(self):
        self.assertEqual(workday.site_url("cvshealth.wd1.CVS_Health_Careers"),
                         "https://cvshealth.wd1.myworkdayjobs.com/wday/cxs/cvshealth/CVS_Health_Careers")
        self.assertEqual(workday.site_url("7eleven.wd3.7eleven"),
                         "https://7eleven.wd3.myworkdayjobs.com/wday/cxs/7eleven/7eleven")

    def test_bad_job_ids_raise_and_odd_ones_are_escaped(self):
        with no_network():
            for job_id in ("", ".", "..", None):
                self.assertRaises(ValueError, workday.fetch_job, SHARP, job_id)
        with mock.patch.object(net, "get_json", return_value=None) as get:
            workday.fetch_job(SHARP, "a/b?c")
        self.assertTrue(get.call_args[0][0].endswith("/job/a%2Fb%3Fc"))


class SearchTest(unittest.TestCase):
    """Paging rules, with the transport faked so page sizes and totals are exact."""

    def run_board(self, pages, terms=None, budget=None):
        calls = []

        def fake(url, payload, budget=None):
            calls.append(payload)
            return pages(payload["searchText"], payload["offset"])

        with mock.patch.object(workday, "_post_json", side_effect=fake):
            out = workday.fetch_board(BOULDER, budget, terms=terms)
        return out, calls

    def test_no_terms_is_one_blank_search_first_page_only(self):
        out, calls = self.run_board(lambda t, o: _page(t, o, 20, 500))
        self.assertEqual(calls, [{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}])
        self.assertEqual(len(out), 20)

    def test_stops_at_a_short_page(self):
        out, calls = self.run_board(lambda t, o: _page(t, o, 20 if o == 0 else 5, 999), terms=["nurse"])
        self.assertEqual([c["offset"] for c in calls], [0, 20])
        self.assertEqual(len(out), 25)

    def test_stops_at_the_page_one_total(self):
        # Past the end Workday repeats page 1, so the page-1 total must stop the loop.
        out, calls = self.run_board(lambda t, o: _page(t, 0, 20, 40 if o == 0 else 0), terms=["nurse"])
        self.assertEqual([c["offset"] for c in calls], [0, 20])
        self.assertEqual(len(out), 20)  # page 2 repeated page 1: de-duplicated

    def test_page_and_term_caps(self):
        terms = ["a", "b", "c", "d", "e"]
        out, calls = self.run_board(lambda t, o: _page(t, o, 20, 10000), terms=terms)
        self.assertEqual([c["searchText"] for c in calls], ["a"] * 3 + ["b"] * 3 + ["c"] * 3)
        self.assertEqual([c["offset"] for c in calls[:3]], [0, 20, 40])
        self.assertEqual(len(out), workday.MAX_TERMS * workday.MAX_PAGES * workday.LIMIT)

    def test_blank_terms_fall_back_to_one_blank_search(self):
        _, calls = self.run_board(lambda t, o: _page(t, o, 3, 3), terms=["", "  "])
        self.assertEqual([c["searchText"] for c in calls], [""])

    def test_dedupes_across_terms_by_external_path(self):
        out, calls = self.run_board(lambda t, o: _page("same", o, 4, 4), terms=["nurse", "rn"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(out), 4)

    def test_gone_board_is_none(self):
        out, _ = self.run_board(lambda t, o: None, terms=["nurse"])
        self.assertIsNone(out)

    def test_malformed_search_raises(self):
        for bad in ({"total": 3}, {"jobPostings": "nope"}):
            with self.subTest(bad=bad):
                self.assertRaises(net.NetError, self.run_board, lambda t, o: bad)

    def test_budget_stops_paging(self):
        budget = net.Budget(2)

        def fake(url, payload, budget=None):
            budget.take()
            return _page(payload["searchText"], payload["offset"], 20, 999)

        with mock.patch.object(workday, "_post_json", side_effect=fake):
            self.assertRaises(net.BudgetExceeded, workday.fetch_board, BOULDER, budget, terms=["nurse"])
        self.assertEqual(budget.used, 2)


class PostTest(unittest.TestCase):
    URL = "https://bouldercolorado.wd1.myworkdayjobs.com/wday/cxs/bouldercolorado/external/jobs"

    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("JOB_SCOUT_RE")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sends_a_json_post_through_net(self):
        seen = []

        def opener(req, timeout):
            seen.append(req)
            return _Resp(200, '{"total": 0, "jobPostings": []}')

        with mock.patch.object(net, "_urlopen", side_effect=opener):
            self.assertEqual(workday._post_json(self.URL, {"searchText": "x"}), {"total": 0, "jobPostings": []})
        req = seen[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data), {"searchText": "x"})
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(req.get_header("User-agent"), net.USER_AGENT)

    def test_record_then_replay_keys_on_url_and_body(self):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"JOB_SCOUT_RECORD_DIR": tmp}), \
                mock.patch.object(net, "_urlopen", return_value=_Resp(200, '{"jobPostings": [], "total": 0}')):
            workday._post_json(self.URL, {"searchText": "nurse", "offset": 0})
        name = net.fixture_key(self.URL, {"offset": 0, "searchText": "nurse"}) + ".json"
        self.assertEqual(os.listdir(tmp), [name])
        with replay(tmp), no_network():
            self.assertEqual(workday._post_json(self.URL, {"searchText": "nurse", "offset": 0})["total"], 0)
            with self.assertRaises(net.Blocked) as cm:  # another search is another fixture
                workday._post_json(self.URL, {"searchText": "rn", "offset": 0})
        self.assertEqual(cm.exception.hint, "replay_miss")

    def test_statuses(self):
        tmp = tempfile.mkdtemp()
        payload = {"searchText": ""}
        for status, body in ((404, ""), (410, ""), (422, '{"errorCode":"HTTP_422"}')):
            net.write_fixture(tmp, self.URL, status, body, post=payload)
            with self.subTest(status=status), replay(tmp):
                self.assertIsNone(workday._post_json(self.URL, payload))
        for status, body in ((400, "{}"), (200, "not json"), (200, "[1, 2]"), (500, "")):
            net.write_fixture(tmp, self.URL, status, body, post=payload)
            with self.subTest(status=status, body=body), replay(tmp):
                self.assertRaises(net.NetError, workday._post_json, self.URL, payload)

    def test_retries_once_on_5xx(self):
        responses = [_Resp(503, ""), _Resp(200, '{"jobPostings": []}')]
        with mock.patch.object(net, "_urlopen", side_effect=lambda req, timeout: responses.pop(0)), \
                mock.patch.object(net, "_sleep") as sleep:
            self.assertEqual(workday._post_json(self.URL, {}), {"jobPostings": []})
        sleep.assert_called_once()


class RecordedBoardsTest(unittest.TestCase):
    """Real responses recorded 2026-10-19 (tests/fixtures/http/workday/README.md)."""

    def test_hospital_search_normalizes(self):
        with replay(), no_network():
            raws = workday.fetch_board(SHARP, terms=["nurse"])
        self.assertTrue(raws)
        for raw in raws:
            job = workday.normalize(raw, SHARP, "Sharp HealthCare")
            pid = raw["externalPath"].rsplit("/", 1)[1]
            self.assertEqual(job["job_id"], pid)
            self.assertEqual(job["key"], "workday:%s:%s" % (SHARP, pid))
            self.assertEqual(job["url"], "https://sharp.wd1.myworkdayjobs.com/External" + raw["externalPath"])
            self.assertEqual(job["title"], raw["title"].strip())
            self.assertEqual(job["countries"], ["US"])
            self.assertIsNone(job["first_published"])  # postedOn is text ("Posted Yesterday")
            self.assertIsNone(job["description_text"])
            self.assertIsNone(job["comp"])

    def test_public_employer_blank_search(self):
        with replay(), no_network():
            raws = workday.fetch_board(BOULDER)
        self.assertTrue(raws)
        job = workday.normalize(raws[0], BOULDER, "City of Boulder")
        self.assertEqual(job["locations"], ["Boulder, CO"])
        self.assertTrue(job["url"].startswith("https://bouldercolorado.wd1.myworkdayjobs.com/external/job/"))

    def test_open_job_detail_matches_its_list_id(self):
        with replay(), no_network():
            first = workday.fetch_board(SHARP, terms=["nurse"])[0]
            listed = workday.normalize(first, SHARP, "Sharp HealthCare")
            raw = workday.fetch_job(SHARP, listed["job_id"])
        job = workday.normalize(raw, SHARP, "Sharp HealthCare")
        self.assertEqual(job["key"], listed["key"])  # fetch_jd requires the same job_id back
        self.assertEqual(job["title"], listed["title"])
        self.assertRegex(job["first_published"], r"^\d{4}-\d{2}-\d{2}$")  # startDate
        self.assertGreater(len(job["description_text"]), 200)
        self.assertIn("US", job["countries"])
        self.assertIsNone(job["comp"])
        self.assertTrue(job["url"].startswith("https://sharp.wd1.myworkdayjobs.com/External/job/"))

    def test_closed_job_is_none(self):
        with replay(), no_network():
            self.assertIsNone(workday.fetch_job(SHARP, CLOSED_ID))

    def test_unknown_boards_are_none(self):
        with replay(), no_network():
            self.assertIsNone(workday.fetch_board("zzqxjobscout.wd1.careers"))  # unknown tenant: 422
            self.assertIsNone(workday.fetch_board("sharp.wd1.ZzqxNoSuchSite"))  # unknown site: 404

    def test_budget_counts_every_request(self):
        with replay(), no_network():
            budget = net.Budget(1)
            workday.fetch_board(SHARP, budget, terms=["nurse"])  # one short page = one request
            self.assertEqual(budget.used, 1)
            self.assertRaises(net.BudgetExceeded, workday.fetch_job, SHARP, CLOSED_ID, budget)

    def test_malformed_detail_is_an_error_not_open(self):
        tmp = tempfile.mkdtemp()
        url = workday.site_url(SHARP) + "/job/" + CLOSED_ID
        net.write_fixture(tmp, url, 200, "{}")
        with replay(tmp):
            self.assertRaises(net.NetError, workday.fetch_job, SHARP, CLOSED_ID)


class NormalizeTest(unittest.TestCase):
    def detail(self, **info):
        base = {"title": "Staff Nurse", "jobPostingId": "Staff-Nurse_JR1-1", "location": "Austin, TX",
                "jobDescription": "<p>Care for patients. Pay: $50/hour.</p>", "startDate": "2026-10-18",
                "externalUrl": "https://sharp.wd1.myworkdayjobs.com/External/job/Austin-TX/Staff-Nurse_JR1-1"}
        base.update(info)
        return {"jobPostingInfo": base}

    def test_location_count_text_is_not_a_place(self):
        job = workday.normalize({"title": "RN", "externalPath": "/job/A/RN_JR1", "locationsText": "3 Locations"},
                                SHARP, "Sharp")
        self.assertEqual(job["locations"], [])

    def test_detail_fields(self):
        job = workday.normalize(self.detail(additionalLocations=["Denver, CO"], remoteType="Remote",
                                            jobRequisitionLocation={"country": {"alpha2Code": "US"}}),
                                SHARP, "Sharp")
        self.assertEqual(job["job_id"], "Staff-Nurse_JR1-1")
        self.assertEqual(job["locations"], ["Austin, TX", "Denver, CO"])
        self.assertEqual(job["countries"], ["US"])
        self.assertIs(job["remote"], True)
        self.assertEqual(job["workplace"], "remote")
        self.assertEqual(job["first_published"], "2026-10-18")
        self.assertEqual(job["description_text"], "Care for patients. Pay: $50/hour.")
        self.assertIsNone(job["comp"])  # no pay field; never parsed from text

    def test_remote_type_spellings(self):
        for text, workplace, remote in (("On-Site", "onsite", False), ("Onsite", "onsite", False),
                                        ("In-Office", "onsite", False), ("Hybrid", "hybrid", False),
                                        ("Not Remote", None, None)):
            with self.subTest(text=text):
                job = workday.normalize(self.detail(remoteType=text), SHARP, "Sharp")
                self.assertEqual(job["workplace"], workplace)
                self.assertIs(job["remote"], remote)

    def test_detail_without_external_url_builds_the_careers_page(self):
        job = workday.normalize(self.detail(externalUrl=None), SHARP, "Sharp")
        self.assertEqual(job["url"], "https://sharp.wd1.myworkdayjobs.com/External/job/Staff-Nurse_JR1-1")

    def test_posting_without_an_id_raises(self):
        self.assertRaises(ValueError, workday.normalize, {"title": "RN"}, SHARP, "Sharp")
        self.assertRaises(ValueError, workday.normalize, self.detail(jobPostingId=None), SHARP, "Sharp")


if __name__ == "__main__":
    unittest.main()
