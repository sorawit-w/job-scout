import contextlib
import copy
import csv
import importlib.util
import io
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("seed_guard", os.path.join(_ROOT, "scripts", "seed_guard.py"))
seed_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_guard)

HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]


def seed(n_ashby=300, n_greenhouse=100):
    """A base list: every board live."""
    rows = []
    for ats, n in (("ashby", n_ashby), ("greenhouse", n_greenhouse)):
        rows += [{"company": "%s %d" % (ats, i), "ats": ats, "slug": "%s-%d" % (ats, i), "sector": "unknown",
                  "status": "live", "jobs": "5", "us_share": "1.0", "remote_share": "1.0",
                  "checked_at": "2026-10-12", "source": "test"} for i in range(n)]
    return rows


def write(rows):
    path = os.path.join(tempfile.mkdtemp(), "companies.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    return path


def run(base, new):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = seed_guard.main(["--base", write(base), "--new", write(new)])
    return code, out.getvalue()


def set_status(rows, ats, count, status):
    for r in [r for r in rows if r["ats"] == ats][:count]:
        r["status"] = status


class SeedGuardTest(unittest.TestCase):
    def test_routine_week_passes(self):
        # last week's shape: counts and shares move freely, a few boards churn, a Workday-style move keeps its place
        base = seed()
        new = copy.deepcopy(base)
        for r in new:
            r.update(jobs="7", remote_share="0.0", checked_at="2026-10-19")
        set_status(new, "ashby", 3, "unverified")  # 3 of 400 = 0.75%
        new[-1]["slug"] = "greenhouse-moved"
        code, out = run(base, new)
        self.assertEqual(code, 0, out)
        self.assertIn("3 changed status", out)
        self.assertIn("routine", out)

    def test_too_many_status_changes_need_review(self):
        base = seed()
        new = copy.deepcopy(base)
        set_status(new, "ashby", 2, "unverified")
        set_status(new, "greenhouse", 2, "dead")  # 4 of 400 = 1%: not under the limit
        code, out = run(base, new)
        self.assertEqual(code, 1)
        self.assertIn("4 of 400 boards changed status", out)

    def test_live_drop_needs_review_even_when_spread_out(self):
        base = seed(n_ashby=1000, n_greenhouse=1000)
        for r in base[:30]:
            r["status"] = "unverified"  # mostly-live base, so status changes stay under 1% ...
        new = copy.deepcopy(base)
        for r in new[100:115] + new[1100:1115]:
            r["status"] = "dead"  # ... 30 changes of 2000 = 1.5%, live 1970 -> 1940
        code, out = run(base, new)
        self.assertEqual(code, 1)
        self.assertIn("live boards dropped from 1970 to 1940", out)

    def test_one_tool_losing_over_5_percent_needs_review(self):
        base = seed(n_ashby=3000, n_greenhouse=60)
        new = copy.deepcopy(base)
        set_status(new, "greenhouse", 4, "unverified")  # 4 of 3060 overall, but 4 of 60 greenhouse = 6.7%
        code, out = run(base, new)
        self.assertEqual(code, 1)
        self.assertIn("greenhouse: 4 of 60 live boards stopped being live", out)
        self.assertNotIn("changed status (", out)  # the overall share is fine; only the one tool trips

    def test_boards_coming_back_never_block(self):
        base = seed()
        set_status(base, "ashby", 3, "dead")
        new = copy.deepcopy(base)
        set_status(new, "ashby", 3, "live")
        self.assertEqual(run(base, new)[0], 0)

    def test_added_or_removed_rows_are_bad_input(self):
        base = seed()
        code, out = run(base, base[:-1])
        self.assertEqual(code, 2)
        self.assertIn("row count changed", out)
        code, out = io.StringIO(), None
        with contextlib.redirect_stdout(code):
            self.assertEqual(seed_guard.main(["--base", "/no/such/file.csv", "--new", write(base)]), 2)


if __name__ == "__main__":
    unittest.main()
