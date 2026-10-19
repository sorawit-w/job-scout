import contextlib
import csv
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("check_new_rows", os.path.join(_ROOT, "scripts", "check_new_rows.py"))
check_new_rows = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_new_rows)

HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]


def csv_file(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        for company, ats, slug in rows:
            w.writerow([company, ats, slug, "unknown", "live", "5", "1.0", "0.0", "2026-10-19", "community"])
    return path


def run(base, head, statuses):
    out = io.StringIO()
    fake = lambda row, hosts=None: (statuses[row["slug"]], "5", "1.0", "0.0", None, row["slug"])  # noqa: E731
    with mock.patch.object(check_new_rows.seed_check, "check_board", side_effect=fake), contextlib.redirect_stdout(out):
        code = check_new_rows.main(["--base", base, "--head", head])
    return code, out.getvalue()


class CheckNewRowsTest(unittest.TestCase):
    def setUp(self):
        self.base = csv_file([("Old", "greenhouse", "old")])

    def test_only_new_boards_are_checked_and_live_passes(self):
        head = csv_file([("Old", "greenhouse", "old"), ("New", "ashby", "new")])
        code, out = run(self.base, head, {"new": "live"})
        self.assertEqual(code, 0)
        self.assertIn("ashby:new live", out)
        self.assertNotIn("greenhouse:old", out)

    def test_a_new_board_that_is_not_live_fails(self):
        head = csv_file([("Old", "greenhouse", "old"), ("Gone", "lever", "gone")])
        code, out = run(self.base, head, {"gone": "dead"})
        self.assertEqual(code, 1)
        self.assertIn("lever:gone dead", out)

    def test_unknown_hiring_tool_fails_without_a_request(self):
        head = csv_file([("Old", "greenhouse", "old"), ("X", "usajobs", "all")])
        code, out = run(self.base, head, {})
        self.assertEqual(code, 1)
        self.assertIn("usajobs:all", out)

    def test_nothing_new(self):
        code, out = run(self.base, self.base, {})
        self.assertEqual(code, 0)
        self.assertIn("no new boards", out)
