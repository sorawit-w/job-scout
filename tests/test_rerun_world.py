"""Guard the day2 rerun world that evals E5 and E6 run against.

Purpose:
    1. Rebuild the seen.json a user has after day1 feedback by running the real scripts on
       the day1 world: probe -> filter -> fetch_jd -> a hand-written results.json (quotes
       checked by cite_check) -> `state.py seen record` -> `state.py seen mark` (saved,
       applied, dismissed "too senior"). It must equal evals/files/seen-after-feedback.json,
       timestamps aside.
    2. Seed JOB_SCOUT_HOME with that file and the day1 profile, run probe on the day2 world,
       then `state.py seen diff` and filter.py, and check each rerun case: new, changed,
       closed (a saved role), a board error that must not close anything, applied still open.
    3. companies.py add for a name in the seed list (0 requests) lands in the user's
       companies file, and probe then checks that board first.
    Replay only: any real network call fails the test.

Usage:
    python3 -m unittest tests.test_rerun_world
    python3 -m tests.test_rerun_world --write   # regenerate seen-after-feedback.json

What it does NOT do: judge fit or check the LLM steps. If day1 or day2 changes, update the
job ids here and in worlds/day2/README.md.
"""
import collections
import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import cite_check
import companies
import fetch_jd
import filter as jfilter
import net
import probe
import state
from adapters import greenhouse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = os.path.join(ROOT, "skills", "job-scout", "evals", "files")
DAY1 = os.path.join(FILES, "worlds", "day1")
DAY2 = os.path.join(FILES, "worlds", "day2")
PROFILE = os.path.join(DAY2, "profile.json")  # the brief the user confirmed on day1
SEEN = os.path.join(FILES, "seen-after-feedback.json")
BOARDS = "greenhouse:koboldmetals,greenhouse:arizeai,ashby:turquoise-health,ashby:reactivemarkets"

SAVED_CLOSED = "greenhouse:arizeai:5778086004"  # Senior Open Source Design Engineer: saved, gone on day2
APPLIED = "ashby:turquoise-health:806f5f93-6eb6-4aea-9483-f8f7458e6730"  # Senior Design Engineer
CHANGED = "greenhouse:arizeai:5396420004"  # "..., Fullstack" on day1, "..., Frontend" on day2
SEEN_SAME = "greenhouse:arizeai:5396396004"  # Senior AI Product Engineer, Backend: unchanged
DISMISSED = "ashby:turquoise-health:87306d91-a18e-490c-b4e6-4758d63b12a1"  # "too senior"
ERROR_BOARD_JOB = "greenhouse:koboldmetals:4286209005"  # its board answers 503 on day2
NEW = "greenhouse:arizeai:6311447004"  # Design Engineer, Design Systems: only on day2
SHOWN = [SAVED_CLOSED, APPLIED, CHANGED, SEEN_SAME, DISMISSED, ERROR_BOARD_JOB]
CHANGED_TITLES = ("Senior AI Product Engineer, Fullstack", "Senior AI Product Engineer, Frontend")
TIMESTAMPS = ("first_seen", "last_seen")
JUDGMENT_STAMPS = ("run", "judged_at")  # the run id is a timestamp too


def _row(key, total, why, risk=()):
    return {"key": key, "gates": {"location": "pass", "sponsorship": "unknown", "pay": "pass", "exclusions": "pass"},
            "scores": {}, "total": total, "show": True,
            "why": [{"text": t, "quote": q} for t, q in why], "risk": [{"text": t, "quote": q} for t, q in risk]}


# What the Phase 6 judgment step wrote on day1: all six shown; every quote is from the live description.
RESULTS = {"rows": [
    _row(APPLIED, 7, [("Owns the internal design system",
                       "maintain reusable pv-components within our internal design system")],
         [("Vue first, React counts as comparable", "Production-level experience with Vue")]),
    _row(SAVED_CLOSED, 7, [("Design-system component work", "Develop reusable components and templates for our design system"),
                           ("React and TypeScript with design sense", "Have strong frontend engineering skills (React, TypeScript)")],
         [("sponsorship not stated", None)]),
    _row(CHANGED, 6, [("Mostly React and TypeScript", "primarily in Typescript and React")]),
    _row(ERROR_BOARD_JOB, 6, [("Frontend-led role", "architecting, developing, and maintaining frontend applications")],
         [("Open to the US or Canada", "anywhere in the United States or Canada")]),
    _row(DISMISSED, 4, [("Uses a frontend framework", "Proficiency with modern front end frameworks such as Vue or React")]),
    _row(SEEN_SAME, 3, [("Some TypeScript", "with opportunities to work in TypeScript")],
         [("Mostly backend work", "backend code primarily in Go, Java, and Python")]),
]}
FEEDBACK = [[SAVED_CLOSED, "saved"], [APPLIED, "applied"], [DISMISSED, "dismissed", "--reason", "too senior"]]


def call(main, argv, stdin=None):
    """Run a script's main(argv) and return (exit code, parsed stdout JSON)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO(stdin or "")):
        code = main(argv)
    return code, json.loads(out.getvalue())


def no_network(*args, **kwargs):
    raise AssertionError("real network call during a replay test")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seeded_home():
    home = tempfile.mkdtemp()
    shutil.copy(PROFILE, os.path.join(home, "profile.json"))
    shutil.copy(SEEN, os.path.join(home, "seen.json"))
    return home


class _Replay(contextlib.ExitStack):
    """Replay world as the only network, state in home."""

    def __init__(self, world, home):
        super().__init__()
        self.enter_context(mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": world, "JOB_SCOUT_HOME": home}))
        self.enter_context(mock.patch.object(net, "_urlopen", no_network))


def day1_feedback(home):
    """Run day1 end to end in home, as Phases 4-8 do. Returns {step: (exit code, stdout JSON)}."""
    steps = {}
    with _Replay(DAY1, home):
        shutil.copy(PROFILE, os.path.join(home, "profile.json"))
        steps["probe"] = call(probe.main, ["--boards", BOARDS])
        steps["filter"] = call(jfilter.main, [])
        steps["fetch_jd"] = call(fetch_jd.main, ["--keys", ",".join(SHOWN)])
        state.write_json_atomic(state.latest_run() / "results.json", RESULTS)
        steps["cite_check"] = call(cite_check.main, [], stdin=json.dumps(RESULTS))
        steps["record"] = call(state.main, ["seen", "record"])
        for i, argv in enumerate(FEEDBACK):
            steps["mark%d" % i] = call(state.main, ["seen", "mark"] + argv)
    return steps


def without_timestamps(seen):
    def strip(e):
        out = {f: v for f, v in e.items() if f not in TIMESTAMPS}
        if "judgment" in out:
            out["judgment"] = {f: v for f, v in out["judgment"].items() if f not in JUDGMENT_STAMPS}
        return out
    return {k: strip(e) for k, e in seen.items()}


class SeenAfterFeedbackTest(unittest.TestCase):
    """seen-after-feedback.json is exactly what record + mark produce on day1."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.steps = day1_feedback(cls.home)
        cls.built = read_json(os.path.join(cls.home, "seen.json"))
        cls.stored = read_json(SEEN)
        cls.unread = {c["key"] for c in cls.steps["filter"][1]["candidates"]} - set(SHOWN)

    def test_every_day1_step_succeeds(self):
        for name, (code, _) in self.steps.items():
            self.assertEqual(code, 0, name)
        self.assertEqual(self.steps["probe"][1]["boards"]["live"], 4)
        self.assertTrue(self.steps["cite_check"][1]["ok"], self.steps["cite_check"][1])
        self.assertEqual(sorted(j["key"] for j in self.steps["fetch_jd"][1]["jobs"]), sorted(SHOWN))
        self.assertEqual(self.steps["record"][1], {"inserted": 6, "updated": 0, "judged": len(self.unread), "missing": 0,
                                                   "closed": 0, "reopened": 0, "pruned": 0})

    def test_shown_roles_were_day1_candidates(self):
        self.assertTrue(set(SHOWN) <= {c["key"] for c in self.steps["filter"][1]["candidates"]})
        self.assertNotIn(NEW, {c["key"] for c in self.steps["filter"][1]["candidates"]})

    def test_stored_file_matches_record_and_mark(self):
        self.assertEqual(without_timestamps(self.stored), without_timestamps(self.built))
        for e in self.stored.values():
            for f in TIMESTAMPS:
                self.assertRegex(e[f], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_feedback_statuses(self):
        status = {k: (e["status"], e["reason"]) for k, e in self.stored.items()}
        self.assertEqual(status, dict({SAVED_CLOSED: ("saved", None), APPLIED: ("applied", None),
                                       DISMISSED: ("dismissed", "too senior"), CHANGED: ("seen", None),
                                       SEEN_SAME: ("seen", None), ERROR_BOARD_JOB: ("seen", None)},
                                      **{k: ("judged", None) for k in self.unread}))
        self.assertTrue(self.unread)  # day1 candidates the judgment step never read
        self.assertFalse([k for k in self.unread if "judgment" in self.stored[k]])
        self.assertEqual(self.stored[CHANGED]["title"], CHANGED_TITLES[0])


class RerunDay2Test(unittest.TestCase):
    """Day2 rerun: probe -> seen diff -> filter, with the day1 profile and seen.json."""

    @classmethod
    def setUpClass(cls):
        cls.home = seeded_home()
        with _Replay(DAY2, cls.home):
            cls.probe = call(probe.main, ["--boards", BOARDS])
            cls.diff = call(state.main, ["seen", "diff"])
            cls.all = call(jfilter.main, ["--all"])
            cls.filter = call(jfilter.main, [])  # last, so candidates.json is the default rerun list
            cls.jd = call(fetch_jd.main, ["--keys", "%s,%s" % (NEW, CHANGED)])
            cls.closed_job = greenhouse.fetch_job("arizeai", SAVED_CLOSED.rsplit(":", 1)[1])
        cls.boards = read_json(os.path.join(cls.home, "runs", cls.probe[1]["run"], "boards.json"))

    def test_probe_reports_the_error_board_as_an_error_not_a_block(self):
        code, out = self.probe
        self.assertEqual(code, 0)
        self.assertEqual(out["boards"]["live"], 3)
        self.assertEqual([e["board"] for e in out["boards"]["errors"]], ["greenhouse:koboldmetals"])
        self.assertIn("HTTP 503", out["boards"]["errors"][0]["error"])
        self.assertEqual(self.boards["blocked"], 0)
        self.assertNotIn("greenhouse:koboldmetals", state.probed_ok_boards(os.path.join(self.home, "runs", out["run"])))

    def test_diff_changed_closed_applied(self):
        code, d = self.diff
        self.assertEqual(code, 0)
        self.assertNotIn("new", d)  # filter.py's per-candidate state counts new roles
        self.assertEqual(d["changed"], [CHANGED])
        self.assertEqual(d["closed"], [SAVED_CLOSED])  # the saved role that closed
        self.assertEqual(d["applied_open"], [APPLIED])
        self.assertEqual(d["saved_open"], [])

    def test_error_board_jobs_are_not_closed(self):
        self.assertNotIn(ERROR_BOARD_JOB, self.diff[1]["closed"])
        self.assertFalse([k for k in self.diff[1]["closed"] if k.startswith("greenhouse:koboldmetals:")])

    def test_closed_job_answers_404(self):
        self.assertIsNone(self.closed_job)

    def test_rerun_filter_leads_with_new_then_changed(self):
        code, out = self.filter
        self.assertEqual(code, 0)
        # one list: the role seen last week stays (after the roles to read); day1's unread (judged)
        # candidates are all on the KoBold board, which errors on day2
        self.assertEqual([(c["key"], c["state"], c["badges"]) for c in out["candidates"]],
                         [(NEW, "new", ["NEW"]), (CHANGED, "changed", ["CHANGED"]), (SEEN_SAME, "seen", [])])
        self.assertEqual(out["candidates"][1]["changes"], ['title: "%s" → "%s"' % CHANGED_TITLES])
        self.assertIsNotNone(out["candidates"][2]["first_shown"])
        removed = out["counts"]["removed"]
        self.assertEqual(removed["dismissed_or_applied"], 2)  # APPLIED, DISMISSED
        self.assertEqual(sum(removed.values()) + out["counts"]["candidates"], out["counts"]["input"])

    def test_all_brings_back_seen_applied_and_dismissed_tagged(self):
        code, out = self.all
        self.assertEqual(code, 0)
        states = {c["key"]: c["state"] for c in out["candidates"]}
        self.assertEqual(states.get(APPLIED), "applied")
        self.assertEqual(states.get(DISMISSED), "dismissed")
        self.assertEqual(states.get(SEEN_SAME), "seen")
        self.assertEqual(states.get(NEW), "new")
        self.assertEqual(out["counts"]["removed"]["dismissed_or_applied"], 0)

    def test_new_and_changed_jobs_are_open_with_live_fields(self):
        code, out = self.jd
        self.assertEqual(code, 0)
        jobs = {j["key"]: j for j in out["jobs"]}
        self.assertEqual(sorted(jobs), sorted([NEW, CHANGED]))
        self.assertEqual(jobs[CHANGED]["title"], CHANGED_TITLES[1])
        self.assertEqual(jobs[NEW]["comp"]["min"], 175000)
        self.assertEqual(out["closed"], [])
        self.assertEqual(out["unverified"], [])


# --- the 2026-10-19 world: 102 candidates, 38 read, 15 shown; run 2 the same day adds one posting ---
PASSPORT = "ashby:workos:passport"  # WorkOS, Product Engineer – Passport: published on the day of run 2
TAPCART = "ashby:tapcart:sr-product-engineer"  # 6/8, ranked 16th in run 1: cut by the 15-row limit
BRIEF_1019 = {"schema": 1, "target_roles": ["Product Engineer"], "work_modes": ["remote"], "remote_scope": ["US"],
              "needs_sponsorship": "no", "base_pay_floor": None, "result_count": 15}
LIVE_1019 = {"status": "open", "full": "We build product features end to end, from the database to the UI.", "comp": None}


def _live_job(jobs, key):
    """The live display fields fetch_jd keeps in a jds.json entry."""
    j = next(j for j in jobs if j["key"] == key)
    return {f: j[f] for f in ("title", "locations", "workplace", "remote_scope")}


def _posting(key, company, title, published):
    ats, slug, _ = key.split(":", 2)
    return {"key": key, "ats": ats, "company": company, "title": title, "remote": True, "remote_scope": ["US"],
            "workplace": "remote", "locations": ["Remote - US"], "comp": None, "first_published": published,
            "url": "https://jobs.ashbyhq.com/%s/%s" % (slug, key.rsplit(":", 1)[1]), "variants": [{"key": key}]}


def world_1019():
    """(run 1 jobs, run 1 results rows, run 2 jobs). Read rows 0-14 are shown (totals 8 down to 6),
    Tapcart is row 15 (6/8, cut by the limit), rows 16-37 read and cut, rows 38-101 never read."""
    jobs = [_posting("ashby:co%02d:%d" % (i, i), "Co %02d" % i, "Product Engineer", "2026-10-%02d" % (18 - i % 18))
            for i in range(101)]
    jobs.insert(15, _posting(TAPCART, "Tapcart", "Sr. Product Engineer", "2026-09-01"))
    totals = [8, 8, 8, 7, 7, 7, 7, 7, 7, 6, 6, 6, 6, 6, 6, 6] + [4] * 22
    rows = [{"key": j["key"], "show": i < 15, "total": t,
             "gates": {"location": "pass", "sponsorship": "pass", "pay": "unknown", "exclusions": "pass"},
             "scores": {"role": 2, "skills": 2, "level": 1, "domain": t - 5}, "style": [],
             "why": [{"text": "Product engineering role", "quote": "build product features end to end"}],
             "risk": [{"text": "pay not listed", "quote": None}]}
            for i, (j, t) in enumerate(zip(jobs, totals))]
    return jobs, rows, jobs + [_posting(PASSPORT, "WorkOS", "Product Engineer – Passport", "2026-10-19")]


class Rerun20261019Test(unittest.TestCase):
    """The bug from 2026-10-19: run 2 the same day tagged all 88 candidates new; one was."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        jobs1, cls.rows, jobs2 = world_1019()
        with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": cls.home}):
            state.write_json_atomic(state.profile_path(), BRIEF_1019)
            run1 = state.new_run()
            state.write_json_atomic(run1 / "jobs.json", jobs1)
            cls.filter1 = call(jfilter.main, ["--run", run1.name])
            state.write_json_atomic(run1 / "results.json", {"rows": cls.rows})
            state.write_json_atomic(run1 / "jds.json", {r["key"]: dict(LIVE_1019, job=_live_job(jobs1, r["key"]))
                                                        for r in cls.rows})
            cls.record1 = call(state.main, ["seen", "record", "--run", run1.name])
            cls.seen1 = state.load_seen()
            cls.live1 = state.read_json(run1 / "jds.json")
            run2 = state.new_run()
            state.write_json_atomic(run2 / "jobs.json", jobs2)
            cls.filter2 = call(jfilter.main, ["--run", run2.name])

    def test_run_1_shape(self):
        self.assertEqual(self.filter1[1]["counts"]["candidates"], 102)
        self.assertEqual((sum(r["show"] for r in self.rows), len(self.rows)), (15, 38))
        self.assertEqual(self.record1, (0, {"inserted": 15, "updated": 0, "judged": 87, "missing": 0,
                                            "closed": 0, "reopened": 0, "pruned": 0}))

    def test_shown_roles_are_seen_and_the_rest_judged(self):
        status = {k: e["status"] for k, e in self.seen1.items()}
        shown = {r["key"] for r in self.rows if r["show"]}
        self.assertEqual({k for k, v in status.items() if v == "seen"}, shown)
        judged = {k for k, v in status.items() if v == "judged"}
        self.assertEqual(len(judged), 87)
        read_cut = {k for k in judged if "judgment" in self.seen1[k]}
        self.assertEqual(read_cut, {r["key"] for r in self.rows if not r["show"]})  # 23, Tapcart among them
        self.assertEqual((len(read_cut), self.seen1[TAPCART]["judgment"]["total"]), (23, 6))

    def test_run_2_tags_exactly_one_role_new(self):
        code, out = self.filter2
        self.assertEqual(code, 0)
        states = {c["key"]: c["state"] for c in out["candidates"]}
        self.assertEqual([k for k, v in states.items() if v == "new"], [PASSPORT])
        self.assertEqual(len(states), 103)  # one list: 15 shown before + 87 screened before + Passport
        self.assertEqual(collections.Counter(states.values()), {"judged": 87, "seen": 15, "new": 1})

    def test_editing_the_brief_invalidates_every_cached_judgment(self):
        jobs = {j["key"]: j for j in world_1019()[2]}
        cached = [k for k in self.seen1 if state.cached_judgment(jobs[k], self.seen1, BRIEF_1019, self.live1.get(k))]
        self.assertEqual(len(cached), 38)  # every read role, shown or cut
        edited = dict(BRIEF_1019, work_modes=["remote", "hybrid"])
        self.assertEqual([k for k in self.seen1 if state.cached_judgment(jobs[k], self.seen1, edited, self.live1.get(k))], [])


class AddCompanyTest(unittest.TestCase):
    """companies.py add for a seed name: 0 requests, saved, then probed first."""

    @classmethod
    def setUpClass(cls):
        cls.home = seeded_home()
        with _Replay(DAY2, cls.home):
            cls.add = call(companies.main, ["add", "Reactive Markets"])
            cls.probe = call(probe.main, ["--max-boards", "1"])
        cls.boards = read_json(os.path.join(cls.home, "runs", cls.probe[1]["run"], "boards.json"))

    def test_seed_hit_costs_no_requests_and_is_saved(self):
        code, out = self.add
        self.assertEqual(code, 0)
        self.assertEqual(out["requests"], 0)
        result = out["results"][0]
        self.assertTrue(result["saved"])
        self.assertEqual([(h["ats"], h["slug"], h["from"]) for h in result["hits"]], [("ashby", "reactivemarkets", "seed")])
        with open(os.path.join(self.home, "companies.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([(r["ats"], r["slug"], r["source"]) for r in rows], [("ashby", "reactivemarkets", "user")])

    def test_probe_checks_the_added_board_first(self):
        code, out = self.probe
        self.assertEqual(code, 0)
        self.assertEqual(out["boards"]["selected"], 1)
        self.assertEqual(self.boards["live_boards"], ["ashby:reactivemarkets"])


def write_seen_file():
    home = tempfile.mkdtemp()
    steps = day1_feedback(home)
    bad = {name: out for name, (code, out) in steps.items() if code != 0}
    if bad:
        raise SystemExit("day1 step failed: %s" % bad)
    shutil.copy(os.path.join(home, "seen.json"), SEEN)
    print("wrote %s" % SEEN)


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        write_seen_file()
    else:
        unittest.main()
