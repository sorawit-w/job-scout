import ast
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("score_run", os.path.join(_ROOT, "scripts", "score_run.py"))
score_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_run)

GT_PATH = os.path.join(_ROOT, "docs", "reference", "ground_truth_2026-10-18.json")

GT = {"date": "2026-10-18", "persona": "test", "roles": [
    {"ats": "ashby", "slug": "ramp", "title": "Design Engineer", "first_published": "2026-07-08"},
    {"ats": "ashby", "slug": "ashby", "title": "Design Engineer - Americas", "first_published": "2026-06-12"},
    {"ats": "greenhouse", "slug": "vercel", "title": "Design Engineer", "first_published": "2026-09-15"},
]}


def row(ats, slug, job_id, title, date, company=None, url=None, variants=None):
    r = {"key": f"{ats}:{slug}:{job_id}", "ats": ats, "slug": slug, "job_id": job_id,
         "company": company or slug.title(), "title": title, "first_published": date,
         "url": url or f"https://jobs.{ats}.com/{slug}/{job_id}"}
    if variants is not None:
        r["variants"] = variants
    return r


RAMP = row("ashby", "ramp", "r1", "Design Engineer", "2026-07-08")
VERCEL_WRONG_DATE = row("greenhouse", "vercel", "v1", "Design Engineer", "2026-09-16")
ASHBY_COLLAPSED = row("ashby", "ashby", "a2", "Design Engineer - Canada", "2026-06-01", variants=[
    {"job_id": "a2", "key": "ashby:ashby:a2", "title": "Design Engineer - Canada", "first_published": "2026-06-01"},
    {"job_id": "a1", "key": "ashby:ashby:a1", "title": "Design Engineer - Americas", "first_published": "2026-06-12"},
])
FILLER = row("ashby", "ramp", "r9", "Backend Engineer", "2026-01-01")


def make_run(**files):
    d = tempfile.mkdtemp()
    for name, data in files.items():
        with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
    return d


def keys(rows):
    return [r["key"] for r in rows]


class RecallTest(unittest.TestCase):
    def test_found_via_primary_row(self):
        res = score_run.score(GT, make_run(jobs=[RAMP]), "jobs")
        self.assertEqual(res["recall"]["found"], 1)
        self.assertEqual(res["recall"]["total"], 3)

    def test_found_only_via_variant(self):
        res = score_run.score(GT, make_run(jobs=[ASHBY_COLLAPSED]), "jobs")
        self.assertEqual(res["recall"]["found"], 1)
        self.assertNotIn("Design Engineer - Americas", [m["title"] for m in res["recall"]["missing"]])

    def test_wrong_date_not_found(self):
        res = score_run.score(GT, make_run(jobs=[VERCEL_WRONG_DATE]), "jobs")
        self.assertEqual(res["recall"]["found"], 0)
        self.assertIn("vercel", [m["slug"] for m in res["recall"]["missing"]])

    def test_board_absent_is_not_probed(self):
        res = score_run.score(GT, make_run(jobs=[RAMP]), "jobs")
        rec = res["recall"]
        self.assertEqual(sorted(m["slug"] for m in rec["not_probed"]), ["ashby", "vercel"])
        self.assertEqual(rec["missing"], [])

    def test_top_limits_rows(self):
        run = make_run(jobs=[FILLER, RAMP], candidates=[FILLER, RAMP])
        self.assertEqual(score_run.score(GT, run, "candidates", top=1)["recall"]["found"], 0)
        self.assertEqual(score_run.score(GT, run, "candidates", top=2)["recall"]["found"], 1)
        self.assertEqual(score_run.score(GT, run, "candidates", top=1)["rows"], 1)
        # A GT role cut by --top on a probed board is missing, not "not probed".
        self.assertEqual(score_run.score(GT, run, "candidates", top=1)["recall"]["missing"][0]["slug"], "ramp")


class StageTest(unittest.TestCase):
    def test_shortlist_uses_jds_status(self):
        run = make_run(jobs=[RAMP, FILLER], candidates=[FILLER, RAMP],
                       jds={RAMP["key"]: {"status": "open"}, FILLER["key"]: {"status": "closed"}})
        self.assertEqual(keys(score_run.stage_rows(run, "shortlist")), [RAMP["key"]])

    def test_results_resolves_keys_in_order(self):
        run = make_run(jobs=[RAMP, ASHBY_COLLAPSED], candidates=[RAMP],
                       results={"rows": [{"key": ASHBY_COLLAPSED["key"], "total": 9},
                                         {"key": RAMP["key"], "total": 7}]})
        rows = score_run.stage_rows(run, "results")
        self.assertEqual(keys(rows), [ASHBY_COLLAPSED["key"], RAMP["key"]])
        self.assertIn("variants", rows[0])  # resolved to the full jobs.json row
        self.assertEqual(score_run.score(GT, run, "results")["recall"]["found"], 2)

    def test_results_keeps_only_shown_rows(self):
        run = make_run(jobs=[RAMP, FILLER, ASHBY_COLLAPSED], candidates=[RAMP],
                       results={"rows": [{"key": RAMP["key"], "show": True}, {"key": FILLER["key"], "show": False},
                                         {"key": ASHBY_COLLAPSED["key"]}]})
        self.assertEqual(keys(score_run.stage_rows(run, "results")), [RAMP["key"], ASHBY_COLLAPSED["key"]])

    def test_missing_stage_file_raises(self):
        with self.assertRaises(SystemExit):
            score_run.stage_rows(make_run(jobs=[RAMP]), "shortlist")


class OtherMetricsTest(unittest.TestCase):
    def test_aggregator_link_counted(self):
        agg = row("ashby", "ramp", "r2", "X", "2026-01-02", url="https://www.linkedin.com/jobs/view/1")
        res = score_run.score(GT, make_run(jobs=[RAMP, agg]), "jobs")
        self.assertEqual(res["links_direct"], {"direct": 1, "total": 2})

    def test_duplicates_counted(self):
        dup = row("ashby", "ramp", "r3", "design engineer", "2026-07-08", company="Ramp, Inc.")
        res = score_run.score(GT, make_run(jobs=[RAMP, dup, FILLER]), "jobs")
        self.assertEqual(res["duplicates"], 1)

    def test_open_share(self):
        run = make_run(jobs=[RAMP, FILLER], jds={RAMP["key"]: {"status": "open"}, FILLER["key"]: {"status": "closed"}})
        self.assertEqual(score_run.score(GT, run, "jobs")["open_share"], {"open": 1, "checked": 2})
        self.assertIsNone(score_run.score(GT, make_run(jobs=[RAMP]), "jobs")["open_share"])


class JobscopeTest(unittest.TestCase):
    def test_jobscope_recall_overall_and_top_n(self):
        js = {"min_score": 0, "companies": [
            {"jobs": [{"id": "ashby:ramp:1", "title": "Design Engineer", "posted": "2026-07-08T10:00:00Z",
                       "url": "u", "score": 10},
                      {"id": "ashby:ramp:2", "title": "Other", "posted": "2026-01-01", "url": "u", "score": 90}]},
            {"jobs": [{"id": "greenhouse:vercel:3", "title": "Design Engineer", "posted": "2026-09-15",
                       "url": "u", "score": 50},
                      {"id": "ashby:ashby:4", "title": "Design Engineer - Americas", "posted": "2026-06-13",
                       "url": "u", "score": 99}]}]}
        path = os.path.join(make_run(), "_run.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(js, f)
        res = score_run.jobscope_recall(GT["roles"], path, top=2)
        self.assertEqual(res, {"jobs": 4, "found": 2, "total": 3, "top": 2, "found_in_top": 0})
        self.assertEqual(score_run.jobscope_recall(GT["roles"], path, top=3)["found_in_top"], 1)


class CliTest(unittest.TestCase):
    def _run(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            score_run.main(argv)
        return out.getvalue()

    def test_json_shape(self):
        gt_path = os.path.join(make_run(), "gt.json")
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(GT, f)
        run = make_run(jobs=[RAMP, FILLER])
        data = json.loads(self._run(["--gt", gt_path, "--run", run, "--json"]))
        self.assertEqual(set(data), {"stage", "rows", "recall", "links_direct", "duplicates", "open_share"})
        self.assertEqual(set(data["recall"]), {"found", "total", "missing", "not_probed"})
        self.assertEqual((data["stage"], data["rows"]), ("jobs", 2))

    def test_human_output_is_short(self):
        run = make_run(jobs=[RAMP, FILLER])
        text = self._run(["--gt", GT_PATH, "--run", run])
        self.assertIn("recall", text)
        self.assertLessEqual(len(text.strip().splitlines()), 15)


class GroundTruthFileTest(unittest.TestCase):
    def test_matches_jobscope_scorecard(self):
        with open(os.path.join(_ROOT, "docs", "m0", "jobscope_scorecard.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        src = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "GT")
        with open(GT_PATH, encoding="utf-8") as f:
            gt = json.load(f)
        self.assertEqual(gt["date"], "2026-10-18")
        self.assertEqual(len(gt["roles"]), 18)
        self.assertEqual([(r["slug"], r["title"], r["first_published"]) for r in gt["roles"]], src)
        greenhouse = {"vercel", "affirm"}
        for r in gt["roles"]:
            self.assertEqual(r["ats"], "greenhouse" if r["slug"] in greenhouse else "ashby", r)


if __name__ == "__main__":
    unittest.main()
