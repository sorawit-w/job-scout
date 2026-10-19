"""Guard the day1 replay world that evals E2, E3 and E8 run against.

Purpose:
    Run probe -> filter -> fetch_jd in-process on skills/job-scout/evals/files/worlds/day1
    with a frontend profile (remote only, US) and check the facts the evals rely on: the
    "Remote, UK" job is removed for remote scope, the sponsorship-refusal sentence is in the
    stored description, and the chosen jobs come back open. Replay only: any real network
    call fails the test.

Usage:
    python3 -m unittest tests.test_replay_world

What it does NOT do: judge fit or check the LLM steps. If the world is re-recorded and these
job ids change, update the ids here and in the world README.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import fetch_jd
import filter as jfilter
import net
import probe
import state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLD = os.path.join(ROOT, "skills", "job-scout", "evals", "files", "worlds", "day1")
BOARDS = "greenhouse:koboldmetals,greenhouse:arizeai,ashby:turquoise-health,ashby:reactivemarkets"

US_DESIGN = "ashby:turquoise-health:806f5f93-6eb6-4aea-9483-f8f7458e6730"  # refuses sponsorship
US_OPEN_SOURCE = "greenhouse:arizeai:5778086004"  # silent on sponsorship
AMERICAS = "greenhouse:koboldmetals:4286209005"  # "Remote, North America"
REMOTE_UK = "ashby:reactivemarkets:50abf8d2-33fe-40bb-85ba-10a69bec0403"
REFUSAL = ("Turquoise does not sponsor employment visas (H-1B, PERM, etc.) or assume "
           "sponsorship of existing visas for this position.")

FRONTEND = {"schema": 1, "target_roles": ["Senior Frontend Engineer", "Design Engineer"],
            "title_synonyms": ["Frontend Software Engineer", "UI Engineer"], "seniority": ["Senior", "Staff"],
            "track": "ic", "work_modes": ["remote"], "remote_scope": ["US"], "needs_sponsorship": "no",
            "base_pay_floor": None, "companies_exclude": ["Lumenly"]}


def call(main, argv):
    """Run a script's main(argv) and return (exit code, parsed stdout JSON)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, json.loads(out.getvalue())


def no_network(*args, **kwargs):
    raise AssertionError("real network call during a replay test")


class ReplayWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        env = {"JOB_SCOUT_REPLAY_DIR": WORLD, "JOB_SCOUT_HOME": cls.home}
        with mock.patch.dict(os.environ, env), mock.patch.object(net, "_urlopen", no_network):
            state.write_json_atomic(state.profile_path(), FRONTEND)
            cls.probe_code, cls.probe_out = call(probe.main, ["--boards", BOARDS])
            cls.filter_code, cls.filter_out = call(jfilter.main, [])
            cls.jd_code, cls.jd_out = call(fetch_jd.main, ["--keys", ",".join([US_DESIGN, US_OPEN_SOURCE, AMERICAS])])
        cls.run_dir = os.path.join(cls.home, "runs", cls.probe_out["run"])

    def read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as f:
            return json.load(f)

    def test_profile_is_valid(self):
        self.assertEqual(state.validate_profile(FRONTEND), [])

    def test_probe_reads_every_board_from_the_world(self):
        self.assertEqual(self.probe_code, 0)
        self.assertEqual(self.probe_out["boards"]["live"], 4)
        self.assertEqual(self.probe_out["boards"]["errors"], [])

    def test_remote_uk_job_is_removed_for_remote_scope(self):
        self.assertEqual(self.filter_code, 0)
        self.assertGreaterEqual(self.filter_out["counts"]["removed"]["remote_scope"], 1)
        self.assertNotIn(REMOTE_UK, [c["key"] for c in self.read("candidates.json")])
        near = {n["key"]: n["reason"] for n in self.filter_out["near_misses"]}
        self.assertEqual(near.get(REMOTE_UK), "remote, but only in GB")

    def test_us_and_americas_jobs_are_candidates_with_the_right_flags(self):
        flags = {c["key"]: c["flags"] for c in self.filter_out["candidates"]}
        self.assertIn(US_DESIGN, flags)
        self.assertIn(US_OPEN_SOURCE, flags)
        self.assertIn(jfilter.AMER_FLAG, flags.get(AMERICAS, []))

    def test_chosen_jobs_are_open(self):
        self.assertEqual(self.jd_code, 0)
        self.assertEqual(sorted(j["key"] for j in self.jd_out["jobs"]), sorted([US_DESIGN, US_OPEN_SOURCE, AMERICAS]))
        self.assertEqual(self.jd_out["closed"], [])
        self.assertEqual(self.jd_out["unverified"], [])

    def test_refusal_sentence_is_stored_for_quoting(self):
        jds = self.read("jds.json")
        self.assertIn(REFUSAL, jds[US_DESIGN]["full"])
        self.assertIn(REFUSAL, jds[US_DESIGN]["trimmed"])  # what the LLM reads in fetch_jd's stdout
        self.assertNotIn("sponsor", jds[US_OPEN_SOURCE]["full"].lower())


if __name__ == "__main__":
    unittest.main()
