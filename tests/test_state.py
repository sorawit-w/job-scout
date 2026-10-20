import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import state

NOW = 1760000000.0  # fixed epoch for deterministic run ids and cache times


class StateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name) / "home"
        patcher = mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)


class HomeTest(StateTestCase):
    def test_env_var_is_honoured_and_created(self):
        self.assertFalse(self.tmp.exists())
        self.assertEqual(state.home(), self.tmp)
        self.assertTrue(self.tmp.is_dir())

    def test_default_home_without_env_var(self):
        os.environ.pop("JOB_SCOUT_HOME")
        fake_user = Path(self._tmp.name) / "user"
        with mock.patch.object(Path, "home", return_value=fake_user):
            self.assertEqual(state.home(), fake_user / ".job-scout")
        self.assertTrue((fake_user / ".job-scout").is_dir())


class JsonTest(StateTestCase):
    def test_atomic_write_round_trip_non_ascii(self):
        path = self.tmp / "a" / "b.json"
        data = {"company": "Noïa Labs", "n": [1, 2]}
        state.write_json_atomic(path, data)
        self.assertEqual(state.read_json(path), data)
        self.assertIn("Noïa Labs", path.read_text(encoding="utf-8"))
        self.assertEqual(os.listdir(str(path.parent)), ["b.json"])  # no temp file left

    def test_atomic_text_write(self):
        path = self.tmp / "r" / "report.html"
        state.write_text_atomic(path, "<p>Noïa</p>\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "<p>Noïa</p>\n")
        self.assertEqual(os.listdir(str(path.parent)), ["report.html"])

    def test_read_json_missing_returns_default(self):
        self.assertEqual(state.read_json(self.tmp / "nope.json", default={}), {})
        self.assertIsNone(state.read_json(self.tmp / "nope.json"))

    def test_read_json_corrupt_returns_default(self):
        path = self.tmp / "bad.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(state.read_json(path, default=[]), [])


class CacheTest(StateTestCase):
    def test_put_then_get_within_ttl(self):
        state.cache_put("greenhouse", "anthropic", {"jobs": [1]}, now=NOW)
        self.assertEqual(state.cache_get("greenhouse", "anthropic", now=NOW + 60), {"jobs": [1]})

    def test_expired_after_ttl(self):
        state.cache_put("greenhouse", "anthropic", {"jobs": []}, now=NOW)
        self.assertIsNone(state.cache_get("greenhouse", "anthropic", now=NOW + state.CACHE_TTL))
        self.assertIsNone(state.cache_get("greenhouse", "anthropic", ttl=10, now=NOW + 11))

    def test_get_missing_or_corrupt_is_none(self):
        self.assertIsNone(state.cache_get("lever", "absent", now=NOW))
        path = state.cache_path("lever", "broken")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("garbage", encoding="utf-8")
        self.assertIsNone(state.cache_get("lever", "broken", now=NOW))
        self.assertIsNone(state.cache_age("lever", "broken", now=NOW))

    def test_cache_age(self):
        self.assertIsNone(state.cache_age("ashby", "x", now=NOW))
        state.cache_put("ashby", "x", [], now=NOW)
        self.assertAlmostEqual(state.cache_age("ashby", "x", now=NOW + 90), 90.0)

    def test_cache_path_rejects_bad_input(self):
        for slug in ("../x", "a/b", "a\\b", ".hidden", "", "a..b"):
            with self.assertRaises(ValueError, msg=slug):
                state.cache_path("greenhouse", slug)
        for ats in ("Green house", "", "gh1", "../x"):
            with self.assertRaises(ValueError, msg=ats):
                state.cache_path(ats, "ok")

    def test_cache_path_accepts_dots_and_case(self):
        self.assertEqual(state.cache_path("ashby", "affinity.co"), self.tmp / "cache" / "ashby" / "affinity.co.json")
        self.assertEqual(state.cache_path("lever", "Fliff"), self.tmp / "cache" / "lever" / "Fliff.json")


class RunsTest(StateTestCase):
    def test_new_run_unique_in_same_second(self):
        a = state.new_run(now=NOW)
        b = state.new_run(now=NOW)
        self.assertNotEqual(a, b)
        self.assertTrue(a.is_dir() and b.is_dir())
        self.assertRegex(a.name, r"^\d{8}T\d{6}Z$")
        self.assertEqual(b.name, a.name + "-2")
        self.assertEqual(a.parent, self.tmp / "runs")

    def test_prune_keeps_newest_three(self):
        runs = [state.new_run(now=NOW + i) for i in range(5)]
        self.assertEqual(sorted(p.name for p in (self.tmp / "runs").iterdir()), [p.name for p in runs[2:]])

    def test_resolve_latest_and_by_id(self):
        state.new_run(now=NOW)
        newest = state.new_run(now=NOW + 5)
        self.assertEqual(state.latest_run(), newest)
        self.assertEqual(state.resolve_run("latest"), newest)
        older = sorted((self.tmp / "runs").iterdir())[0]
        self.assertEqual(state.resolve_run(older.name), older)

    def test_resolve_latest_with_no_runs(self):
        self.assertIsNone(state.latest_run())
        with self.assertRaises(FileNotFoundError):
            state.resolve_run("latest")

    def test_resolve_rejects_traversal_and_missing(self):
        with self.assertRaises(ValueError):
            state.resolve_run("../etc")
        with self.assertRaises(ValueError):
            state.resolve_run("a/b")
        with self.assertRaises(FileNotFoundError):
            state.resolve_run("20000101T000000Z")


class BriefSigTest(unittest.TestCase):
    BRIEF = {"schema": 1, "target_roles": ["Design Engineer"], "work_modes": ["remote"], "needs_sponsorship": "no",
             "base_pay_floor": None}

    def test_defaults_and_display_only_fields_do_not_change_it(self):
        sig = state.brief_sig(self.BRIEF)
        self.assertRegex(sig, r"^[0-9a-f]{12}$")
        self.assertEqual(state.brief_sig(state.with_profile_defaults(self.BRIEF)), sig)
        for same in ({"work_style": {"travel": "none"}}, {"result_count": 5}, {"title_keywords": ["react"]},
                     {"sources": {"work_modes": "you"}}, {"recency_flag_days": 30}):
            self.assertEqual(state.brief_sig(dict(self.BRIEF, **same)), sig, same)

    def test_every_judgment_field_changes_it(self):
        sig = state.brief_sig(self.BRIEF)
        values = {"track": "ic", "home_base": "Austin, TX", "needs_sponsorship": "yes", "open_to_relocation": True,
                  "hide_no_pay": True, "base_pay_floor": {"amount": 1}}
        for field in state.BRIEF_FIELDS:
            self.assertNotEqual(state.brief_sig(dict(self.BRIEF, **{field: values.get(field, ["X"])})), sig, field)


class NowIsoTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(state.now_iso(0), "1970-01-01T00:00:00Z")
        self.assertRegex(state.now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class QaFixesStateTest(unittest.TestCase):
    def test_resolve_run_rejects_dot_and_non_run_ids(self):
        import tempfile
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}):
            for bad in (".", "runs", "20261019T000000Z/x", "latestish"):
                with self.assertRaises(ValueError):
                    state.resolve_run(bad)

class CodexReviewRunOrderTest(unittest.TestCase):
    def test_five_runs_in_one_second_keep_the_newest_three(self):
        import tempfile
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": tempfile.mkdtemp()}):
            made = [state.new_run(now=1760000000.0) for _ in range(5)]
            self.assertEqual(state.latest_run(), made[-1])
            kept = sorted(p.name for p in (state.home() / "runs").iterdir())
            self.assertEqual(sorted(kept), sorted(p.name for p in made[-3:]))

if __name__ == "__main__":
    unittest.main()
