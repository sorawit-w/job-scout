import contextlib
import csv
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("seed_check", os.path.join(_ROOT, "scripts", "seed_check.py"))
seed_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_check)

FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "http")
HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]


def make_csv(rows):
    path = os.path.join(tempfile.mkdtemp(), "companies.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for company, ats, slug, status in rows:
            w.writerow({"company": company, "ats": ats, "slug": slug, "sector": "unknown", "status": status,
                        "jobs": "", "us_share": "", "remote_share": "", "checked_at": "", "source": "corphunting"})
    return path


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return {(r["ats"], r["slug"]): r for r in csv.DictReader(f)}


def run(argv):
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": FIXTURES}), contextlib.redirect_stdout(out):
        code = seed_check.main(argv)
    return code, out.getvalue()


class SeedCheckTest(unittest.TestCase):
    def test_statuses_and_shares(self):
        path = make_csv([("Airtable", "greenhouse", "airtable", "unchecked"),
                         ("Webflow", "greenhouse", "webflow", "live"),
                         ("Gone", "lever", "job-scout-no-such-board", "live"),
                         ("Attention", "ashby", "attention", "unchecked")])
        code, out = run(["--companies", path])
        self.assertEqual(code, 0)
        rows = read(path)
        self.assertEqual(rows[("greenhouse", "airtable")]["status"], "live")
        self.assertEqual(rows[("greenhouse", "airtable")]["jobs"], "3")
        self.assertEqual(rows[("greenhouse", "webflow")]["status"], "unverified")
        self.assertEqual(rows[("lever", "job-scout-no-such-board")]["status"], "dead")
        self.assertEqual(rows[("ashby", "attention")]["us_share"], "1.0")
        self.assertTrue(rows[("ashby", "attention")]["checked_at"])
        self.assertIn("seed-check: 4 boards · live 2 · unverified 1 · dead 1 · errors 0 (0%)", out)

    def test_smartrecruiters_live_and_unknown_company(self):
        path = make_csv([("BryceTech", "smartrecruiters", "BryceTech", "unchecked"),
                         ("Nobody", "smartrecruiters", "job-scout-no-such-board", "unchecked")])
        code, out = run(["--companies", path, "--changed-only"])
        self.assertEqual(code, 0)
        rows = read(path)
        bryce = rows[("smartrecruiters", "BryceTech")]
        self.assertEqual((bryce["status"], bryce["jobs"], bryce["us_share"]), ("live", "3", "1.0"))
        # an unknown SmartRecruiters company answers 200 with no postings: unverified, never dead
        self.assertEqual(rows[("smartrecruiters", "job-scout-no-such-board")]["status"], "unverified")
        self.assertIn("live 1 · unverified 1 · dead 0 · errors 0", out)

    def test_error_keeps_previous_status_below_threshold(self):
        # 10 boards, one without a fixture (a replay miss = a network error)
        path = make_csv([("A", "greenhouse", "airtable", "live"), ("W", "greenhouse", "webflow", "live"),
                         ("X", "ashby", "no-fixture-here", "live"), ("L", "lever", "airslate", "live"),
                         ("C", "ashby", "clerk", "live"), ("T", "ashby", "attention", "live"),
                         ("R", "ashby", "raycast", "live"), ("G", "lever", "job-scout-no-such-board", "live"),
                         ("F", "greenhouse", "job-scout-no-such-board", "live"), ("Y", "ashby", "ramp", "live")])
        code, out = run(["--companies", path])
        self.assertEqual(code, 0)  # 1 error in 10 boards = 10%, not above the threshold
        self.assertEqual(read(path)[("ashby", "no-fixture-here")]["status"], "live")
        self.assertIn("errors 1 (10%)", out)

    def test_too_many_errors_aborts_and_leaves_file_unchanged(self):
        path = make_csv([("Airtable", "greenhouse", "airtable", "unchecked"),
                         ("X", "ashby", "no-fixture-a", "live"), ("Y", "lever", "no-fixture-b", "live")])
        with open(path, "rb") as f:
            before = f.read()
        code, out = run(["--companies", path])
        self.assertEqual(code, 1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertIn("aborted", out)

    def test_changed_only_checks_unchecked_rows(self):
        path = make_csv([("Airtable", "greenhouse", "airtable", "unchecked"),
                         ("Webflow", "greenhouse", "webflow", "live")])
        code, out = run(["--companies", path, "--changed-only"])
        self.assertIn("seed-check: 1 boards", out)
        self.assertEqual(read(path)[("greenhouse", "webflow")]["status"], "live")  # untouched

    def test_only_filter(self):
        path = make_csv([("Airtable", "greenhouse", "airtable", "unchecked"),
                         ("Attention", "ashby", "attention", "unchecked")])
        run(["--companies", path, "--only", "ashby:attention"])
        rows = read(path)
        self.assertEqual(rows[("ashby", "attention")]["status"], "live")
        self.assertEqual(rows[("greenhouse", "airtable")]["status"], "unchecked")

    def test_aggregator_flag(self):
        many = [{"countries": ["US"], "remote_scope": None, "remote": False}] * 3
        self.assertEqual(seed_check.shares(many), (1.0, 0.0))
        with mock.patch.object(seed_check, "AGGREGATOR_JOBS", 2):
            path = make_csv([("Airtable", "greenhouse", "airtable", "unchecked")])
            code, out = run(["--companies", path])
        self.assertIn("possible aggregator", out)


POSTING = {"title": "Clinical Nurse RN", "externalPath": "/job/San-Diego-CA/Clinical-Nurse-RN_JR1",
           "locationsText": "San Diego, CA"}


def fake_workday(answers, calls=None):
    """A stand-in for workday.fetch_board: answers[slug] is a list, or an exception to raise; else None."""
    def fetch_board(slug, budget=None, terms=None):
        if calls is not None:
            calls.append(slug)
        got = answers.get(slug)
        if isinstance(got, Exception):
            raise got
        return got
    return fetch_board


def run_workday(path, answers, calls=None):
    with mock.patch.object(seed_check.workday, "fetch_board", fake_workday(answers, calls)):
        return run(["--companies", path])


class WorkdayCheckTest(unittest.TestCase):
    def test_statuses_and_moved_host(self):
        path = make_csv([("Sharp", "workday", "sharp.wd1.External", "unchecked"),
                         ("Empty", "workday", "empty.wd5.careers", "unchecked"),
                         ("Gone", "workday", "gone.wd1.x", "live"),
                         ("Kohl's", "workday", "kohls.wd1.kohlscareers", "unchecked")])
        calls = []
        code, out = run_workday(path, {"sharp.wd1.External": [POSTING, dict(POSTING, externalPath="/job/x/y_JR2")],
                                       "empty.wd5.careers": [],
                                       "kohls.wd504.kohlscareers": [POSTING]}, calls)
        self.assertEqual(code, 0)
        rows = read(path)
        sharp = rows[("workday", "sharp.wd1.External")]
        self.assertEqual((sharp["status"], sharp["jobs"], sharp["us_share"], sharp["remote_share"]),
                         ("live", "2", "1.0", "0.0"))
        self.assertEqual(rows[("workday", "empty.wd5.careers")]["status"], "unverified")
        self.assertEqual(rows[("workday", "gone.wd1.x")]["status"], "dead")
        self.assertNotIn(("workday", "kohls.wd1.kohlscareers"), rows)  # the row's slug was rewritten
        self.assertEqual(rows[("workday", "kohls.wd504.kohlscareers")]["status"], "live")
        # a dead board is tried on its own host, then once on each other host in the fixed list
        gone = [s for s in calls if s.startswith("gone.")]
        self.assertEqual(len(gone), len(seed_check.WORKDAY_HOSTS))
        self.assertEqual(len(set(gone)), len(gone))
        self.assertIn("seed-check: 4 boards · live 2 · unverified 1 · dead 1 · errors 0 (0%) · moved 1", out)

    def test_moved_board_tries_every_host_the_seed_uses(self):
        # wd108 is not in the fixed list, but another row uses it, so a board moved there is found
        path = make_csv([("Moved", "workday", "moved.wd1.jobs", "live"), ("Other", "workday", "other.wd108.jobs", "live")])
        code, out = run_workday(path, {"moved.wd108.jobs": [POSTING], "other.wd108.jobs": [POSTING]})
        self.assertEqual(code, 0)
        self.assertEqual(read(path)[("workday", "moved.wd108.jobs")]["status"], "live")

    def test_network_error_keeps_previous_status(self):
        rows = [("A%d" % i, "workday", "a%d.wd1.jobs" % i, "unverified") for i in range(9)]
        path = make_csv(rows + [("Err", "workday", "err.wd1.jobs", "live")])
        answers = {"a%d.wd1.jobs" % i: [POSTING] for i in range(9)}
        answers["err.wd1.jobs"] = seed_check.net.NetError("boom")
        code, out = run_workday(path, answers)
        self.assertEqual(code, 0)  # 1 error in 10 = 10%, not above the limit
        got = read(path)
        self.assertEqual(got[("workday", "err.wd1.jobs")]["status"], "live")
        self.assertEqual(got[("workday", "a0.wd1.jobs")]["status"], "live")

    def test_too_many_workday_errors_abort(self):
        path = make_csv([("A", "workday", "a.wd1.jobs", "unchecked"), ("B", "workday", "b.wd1.jobs", "unchecked")])
        with open(path, "rb") as f:
            before = f.read()
        code, out = run_workday(path, {"a.wd1.jobs": [POSTING], "b.wd1.jobs": seed_check.net.NetError("boom")})
        self.assertEqual(code, 1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertIn("aborted", out)


if __name__ == "__main__":
    unittest.main()
