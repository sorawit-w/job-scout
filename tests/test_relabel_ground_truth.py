import contextlib
import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "relabel_ground_truth", os.path.join(_ROOT, "scripts", "relabel_ground_truth.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
_spec = importlib.util.spec_from_file_location("score_run", os.path.join(_ROOT, "scripts", "score_run.py"))
score_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_run)

from adapters import _common  # noqa: E402  (R put the skill scripts on sys.path)
import normalize  # noqa: E402
import state  # noqa: E402

LEAKS = ("title_net", "previous_gt", "job_scout", "jobscope", "sources", "pool", "score", "strong match")


def _job(slug, jid, title, locs, date, remote=None, mode=None):
    return _common.job("ashby", slug, slug.title(), jid, title, "https://jobs.ashbyhq.com/%s/%s" % (slug, jid),
                       locs, remote_flag=remote, workplace_hint=mode, first_published=date)


def snapshot_jobs():
    raw = [
        _job("acme", "a1", "Senior Frontend Engineer", ["Remote (United States)"], "2026-10-10", True, "Remote"),
        # Two postings of one role; the older ground truth names the second (a variant, not the primary).
        _job("brio", "b1", "Design Engineer - Canada", ["Toronto, Canada"], "2026-09-01", False, "Hybrid"),
        _job("brio", "b2", "Design Engineer - Americas", ["Remote (United States)"], "2026-09-20", True, "Remote"),
        _job("cora", "c1", "Backend Engineer", ["New York, NY"], "2026-08-01", False, "Onsite"),
        _job("dune", "d1", "Accountant", ["Los Angeles, CA"], "2026-08-02", False, "Onsite"),
        _job("eon", "e1", "Web Designer", ["London, UK"], "2026-08-03", False, "Onsite"),
    ]
    return normalize.collapse_variants(raw)


PREV_GT = {"date": "2026-10-18", "persona": "t", "roles": [
    {"ats": "ashby", "slug": "brio", "title": "Design Engineer - Americas", "first_published": "2026-09-20"},
    {"ats": "ashby", "slug": "cora", "title": "Backend Engineer", "first_published": "2026-08-01"},
    {"ats": "ashby", "slug": "gone", "title": "Closed Role", "first_published": "2026-01-01"},
]}
JOBSCOPE = {"min_score": 0, "companies": [{"jobs": [
    {"id": "ashby:cora:x", "title": "Backend Engineer", "posted": "2026-08-01T00:00:00Z", "score": 50},
    {"id": "ashby:elsewhere:y", "title": "Frontend Engineer", "posted": "2026-08-01", "score": 90},
]}]}


def make_snapshot(jobs=None):
    d = tempfile.mkdtemp()
    snap = os.path.join(d, "2026-10-19")
    os.makedirs(snap)
    with open(os.path.join(snap, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(jobs if jobs is not None else snapshot_jobs(), f)
    with open(os.path.join(snap, "boards.json"), "w", encoding="utf-8") as f:
        json.dump({"date": "2026-10-19"}, f)
    for name, data in (("gt.json", PREV_GT), ("js.json", JOBSCOPE)):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(data, f)
    return d, snap


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = R.main(argv)
    return code, out.getvalue(), err.getvalue()


def key(jobs, slug):
    return next(r["key"] for r in jobs if r["slug"] == slug)


class ProfileTest(unittest.TestCase):
    def test_frontend_profile_is_valid(self):
        self.assertEqual(state.validate_profile(R.FRONTEND_PROFILE), [])


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.jobs = snapshot_jobs()
        self.pool, self.by, self.notes = R.build_pool(self.jobs, PREV_GT, JOBSCOPE)

    def test_union_and_dedupe(self):
        k = lambda s: key(self.jobs, s)  # noqa: E731
        self.assertEqual(set(self.pool), {k("acme"), k("brio"), k("cora"), k("eon")})
        self.assertEqual(self.pool[k("acme")], {"title_net", "job_scout"})
        # Proposed by three sources through different variants, still one row under the collapsed key.
        self.assertEqual(self.pool[k("brio")], {"title_net", "previous_gt", "job_scout"})
        self.assertEqual(self.pool[k("cora")], {"previous_gt", "jobscope"})
        self.assertEqual(self.pool[k("eon")], {"title_net"})

    def test_notes(self):
        self.assertEqual(self.notes["jobscope_unmatched"], 1)
        self.assertEqual([g["slug"] for g in self.notes["previous_gt_absent"]], ["gone"])
        self.assertEqual(self.notes["title_net"], "broad")

    def test_tight_net_needs_engineering_word_and_us_option(self):
        pool, by, notes = R.build_pool(self.jobs, None, None, tight=True)
        self.assertEqual(by["title_net"], {key(self.jobs, "acme"), key(self.jobs, "brio")})
        self.assertTrue(notes["title_net"].startswith("tightened"))
        self.assertFalse(R.in_net({"title": "Senior Frontend Engineer", "countries": ["GB"]}, tight=True))
        self.assertTrue(R.in_net({"title": "Senior Frontend Engineer", "countries": ["GB"]}))


class SheetTest(unittest.TestCase):
    def test_sheet_is_blind_and_pool_json_is_not(self):
        d, snap = make_snapshot()
        code, out, _ = run(["sheet", "--snapshot", snap, "--prev-gt", os.path.join(d, "gt.json"),
                            "--jobscope", os.path.join(d, "js.json")])
        self.assertEqual(code, 0)
        self.assertIn("pool 4 rows", out)
        with open(os.path.join(snap, "sheet.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), list(R.SHEET_COLUMNS))
        self.assertTrue(all(r["label"] == "" and r["note"] == "" for r in rows))
        for name in ("sheet.csv", "sheet.html"):
            with open(os.path.join(snap, name), encoding="utf-8") as f:
                text = f.read().lower()
            for word in LEAKS:
                self.assertNotIn(word, text, "%s leaks %r" % (name, word))
        with open(os.path.join(snap, "sheet.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link", page)
        self.assertIn('target="_blank"', page)
        with open(os.path.join(snap, "pool.json"), encoding="utf-8") as f:
            pool = json.load(f)
        self.assertEqual({r["key"] for r in pool["rows"]}, {r["key"] for r in rows})
        self.assertIn("jobscope", {s for r in pool["rows"] for s in r["sources"]})
        self.assertEqual(pool["profile"], R.FRONTEND_PROFILE)
        self.assertEqual(pool["counts"]["pool"], 4)

    def test_only_writes_a_blind_review_subset_and_leaves_the_sheet(self):
        d, snap = make_snapshot()
        run(["sheet", "--snapshot", snap, "--prev-gt", os.path.join(d, "gt.json")])
        with open(os.path.join(snap, "sheet.csv"), encoding="utf-8") as f:
            before, keys = f.read(), [r["key"] for r in csv.DictReader(open(os.path.join(snap, "sheet.csv")))][:2]
        only = os.path.join(d, "only.json")
        with open(only, "w", encoding="utf-8") as f:
            json.dump(keys, f)
        code, out, _ = run(["sheet", "--snapshot", snap, "--only", only])
        self.assertEqual(code, 0)
        with open(os.path.join(snap, "review.csv"), encoding="utf-8") as f:
            self.assertEqual(sorted(r["key"] for r in csv.DictReader(f)), sorted(keys))
        self.assertTrue(os.path.exists(os.path.join(snap, "review.html")))
        with open(os.path.join(snap, "sheet.csv"), encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        with open(only, "w", encoding="utf-8") as f:
            json.dump(["greenhouse:nope:1"], f)
        self.assertEqual(run(["sheet", "--snapshot", snap, "--only", only])[0], 1)

    def test_shuffle_is_deterministic(self):
        jobs = [{"key": "ashby:s:%d" % i, "title": "T%d" % i, "url": "javascript:alert(1)"} for i in range(12)]
        keys = [j["key"] for j in jobs]
        a = R.sheet_rows(jobs, keys, 1)
        self.assertEqual(a, R.sheet_rows(jobs, list(reversed(keys)), 1))
        self.assertNotEqual([r["key"] for r in a], [r["key"] for r in R.sheet_rows(jobs, keys, 2)])
        self.assertEqual([r["n"] for r in a], list(range(1, 13)))
        self.assertEqual({r["link"] for r in a}, {""})  # only http(s) links reach the page


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.d, self.snap = make_snapshot()
        self.jobs = snapshot_jobs()
        self.out = os.path.join(self.d, "gt_out.json")

    def write_labels(self, labels):
        path = os.path.join(self.d, "labels.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"snapshot": "2026-10-19", "labels": labels, "notes": {key(self.jobs, "brio"): "check level"}}, f)
        return path

    def test_import_is_score_run_compatible(self):
        k = lambda s: key(self.jobs, s)  # noqa: E731
        path = self.write_labels({k("acme"): "strong", k("brio"): "maybe", k("dune"): "no"})
        code, out, _ = run(["import", path, "--snapshot", self.snap, "--out", self.out])
        self.assertEqual(code, 0, out)
        with open(self.out, encoding="utf-8") as f:
            gt = json.load(f)
        self.assertEqual(gt["date"], "2026-10-19")
        self.assertEqual(gt["snapshot"], "2026-10-19")
        self.assertEqual([r["slug"] for r in gt["roles"]], ["acme"])
        self.assertEqual([r["slug"] for r in gt["maybe"]], ["brio"])
        self.assertEqual(gt["notes"], {k("brio"): "check level"})
        res = score_run.score(gt, self.snap)
        self.assertEqual((res["recall"]["found"], res["recall"]["total"]), (1, 1))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            score_run.main(["--gt", self.out, "--run", self.snap])
        self.assertIn("recall: 1/1 found", buf.getvalue())

    def test_unknown_key_is_an_error(self):
        path = self.write_labels({"ashby:nope:1": "strong"})
        code, _, err = run(["import", path, "--snapshot", self.snap, "--out", self.out])
        self.assertEqual(code, 1)
        self.assertIn("ashby:nope:1", err)
        self.assertFalse(os.path.exists(self.out))

    def test_bad_label_is_an_error(self):
        path = self.write_labels({key(self.jobs, "acme"): "yes"})
        code, _, err = run(["import", path, "--snapshot", self.snap, "--out", self.out])
        self.assertEqual(code, 1)
        self.assertIn("strong/maybe/no", err)


class SnapshotTest(unittest.TestCase):
    def test_wiring_records_into_dir_with_temp_home(self):
        seen = {}
        before = {k: os.environ.get(k) for k in ("JOB_SCOUT_RECORD_DIR", "JOB_SCOUT_HOME")}

        def fake_probe(boards, budget, refresh=False, denylist=frozenset()):
            seen.update(boards=boards, refresh=refresh, record=os.environ.get("JOB_SCOUT_RECORD_DIR"),
                        home=os.environ.get("JOB_SCOUT_HOME"))
            R.net.write_fixture(os.environ["JOB_SCOUT_RECORD_DIR"], "https://example.test/x", 200, "{}")
            jobs = snapshot_jobs()
            return ({"probed": len(boards), "cached": 0, "live": 1, "live_boards": [], "empty": [], "dead": [],
                     "errors": [], "denylisted": 0, "capped": 0, "blocked": 0, "jobs": 6,
                     "collapsed": len(jobs)}, jobs)

        out_dir = os.path.join(tempfile.mkdtemp(), "snap")
        real = R.probe.probe
        R.probe.probe = fake_probe
        try:
            code, out, _ = run(["snapshot", "--out", out_dir])
            again, out2, _ = run(["snapshot", "--out", out_dir])
        finally:
            R.probe.probe = real
        self.assertEqual(code, 0)
        self.assertIn("49 boards", out)
        self.assertEqual(len(seen["boards"]), 49)
        self.assertTrue(seen["refresh"])
        self.assertEqual(seen["record"], os.path.join(out_dir, "http"))
        self.assertFalse(os.path.exists(seen["home"]))  # throwaway home removed afterwards
        self.assertEqual({k: os.environ.get(k) for k in before}, before)
        self.assertEqual(len(os.listdir(os.path.join(out_dir, "http"))), 1)
        with open(os.path.join(out_dir, "boards.json"), encoding="utf-8") as f:
            boards = json.load(f)
        self.assertEqual(len(boards["boards"]), 49)
        with open(os.path.join(out_dir, "jobs.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 5)
        self.assertEqual(again, 2)  # never overwrite a snapshot that labels may point at
        self.assertIn("already has jobs.json", out2)


if __name__ == "__main__":
    unittest.main()
