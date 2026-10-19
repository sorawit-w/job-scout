import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import state


def good(**over):
    p = {"schema": 1, "target_roles": ["Design Engineer", "Staff Frontend Engineer"],
         "work_modes": ["remote", "hybrid"], "remote_scope": ["US"], "needs_sponsorship": "no",
         "base_pay_floor": {"amount": 180000, "currency": "USD", "interval": "year"},
         "sources": {"target_roles": "resume", "work_modes": "you"}}
    p.update(over)
    return p


class ValidateTest(unittest.TestCase):
    def test_good_profile_has_no_errors(self):
        self.assertEqual(state.validate_profile(good()), [])

    def test_unknown_keys_are_rejected_including_protected_attributes(self):
        for key in ("age", "gender", "race", "nationality", "religion", "favorite_color"):
            errors = state.validate_profile(good(**{key: "x"}))
            self.assertTrue(any(key in e for e in errors), (key, errors))

    def test_required_fields(self):
        for key in ("target_roles", "work_modes", "needs_sponsorship", "base_pay_floor"):
            p = good()
            del p[key]
            self.assertTrue(any(key in e for e in state.validate_profile(p)), key)

    def test_no_floor_is_an_explicit_null(self):
        self.assertEqual(state.validate_profile(good(base_pay_floor=None)), [])

    def test_bad_enum_values(self):
        self.assertTrue(state.validate_profile(good(needs_sponsorship="maybe")))
        self.assertTrue(state.validate_profile(good(work_modes=["remote", "beach"])))
        self.assertTrue(state.validate_profile(good(track="astronaut")))
        self.assertTrue(state.validate_profile(good(sources={"target_roles": "guess"})))

    def test_bad_types_and_ranges(self):
        self.assertTrue(state.validate_profile(good(target_roles="Design Engineer")))
        self.assertTrue(state.validate_profile(good(target_roles=[])))
        self.assertTrue(state.validate_profile(good(base_pay_floor={"amount": "lots"})))
        self.assertTrue(state.validate_profile(good(result_count=0)))
        self.assertTrue(state.validate_profile(good(result_count=500)))
        self.assertTrue(state.validate_profile("not a dict"))

    def test_defaults_are_applied(self):
        p = state.with_profile_defaults(good())
        self.assertEqual(p["result_count"], 15)
        self.assertEqual(p["recency_flag_days"], 90)
        self.assertIs(p["hide_no_pay"], False)
        self.assertEqual(p["companies_exclude"], [])


class ProfileCliTest(unittest.TestCase):
    def run_cli(self, argv, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            code = state.main(argv)
        return code, out.getvalue()

    def test_save_then_show_round_trip(self):
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}):
            code, out = self.run_cli(["profile", "save", "--stdin"], json.dumps(good()))
            self.assertEqual(code, 0)
            code, out = self.run_cli(["profile", "show"])
            self.assertEqual(code, 0)
            shown = json.loads(out)
            self.assertEqual(shown["target_roles"], ["Design Engineer", "Staff Frontend Engineer"])
            self.assertEqual(shown["result_count"], 15)

    def test_save_rejects_invalid_and_writes_nothing(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": home}):
            code, out = self.run_cli(["profile", "save", "--stdin"], json.dumps(good(age=40)))
            self.assertEqual(code, 1)
            self.assertIn("errors", json.loads(out))
            self.assertFalse(os.path.exists(os.path.join(home, "profile.json")))

    def test_validate_does_not_write(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": home}):
            code, out = self.run_cli(["profile", "validate"], json.dumps(good()))
            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(os.path.join(home, "profile.json")))

    def test_show_without_profile(self):
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}):
            code, out = self.run_cli(["profile", "show"])
            self.assertEqual(code, 1)
            self.assertIn("no profile", out)

    def test_bad_json_is_reported(self):
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}):
            code, out = self.run_cli(["profile", "save", "--stdin"], "{not json")
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
