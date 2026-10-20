import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cite_check
import probe
import state

NOW = 1760000000.0
LATER = NOW + 86400
USD = {"min": 190000, "max": 240000, "currency": "USD", "interval": "year"}
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "http")


def job(key="ashby:acme:1", title="Senior Frontend Engineer", comp=USD, locations=("Remote - US",), more=()):
    """A collapsed job: primary key plus variants (the primary is the first variant)."""
    keys = [key] + list(more)
    return {"key": key, "company": "Acme", "title": title, "comp": dict(comp) if comp else comp,
            "locations": list(locations), "variants": [{"key": k} for k in keys]}


def entry(j=None, status="seen", aliases=(), sig=None, closed_at=None):
    return {"first_seen": "2026-10-01T00:00:00Z", "last_seen": "2026-10-01T00:00:00Z", "status": status,
            "reason": None, "closed_at": closed_at, "sig": sig if sig is not None else state.job_sig(j or job()),
            "aliases": list(aliases)}


class HomeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        patcher = mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_run(self, jobs, rows, live=("ashby:acme",), empty=(), errors=()):
        run = state.new_run(now=NOW)
        state.write_json_atomic(run / "jobs.json", jobs)
        state.write_json_atomic(run / "boards.json", {"live": len(live), "live_boards": list(live), "empty": list(empty),
                                                      "dead": [], "errors": [{"board": b, "error": "x"} for b in errors]})
        state.write_json_atomic(run / "results.json", {"rows": rows})
        return run


class JobSigTest(unittest.TestCase):
    def test_short_stable_hex(self):
        sig = state.job_sig(job())
        self.assertRegex(sig, r"^[0-9a-f]{12}$")
        self.assertEqual(sig, state.job_sig(job()))

    def test_location_order_and_other_fields_do_not_matter(self):
        a = job(locations=("NYC", "Remote - US"))
        b = job(locations=("Remote - US", "NYC"))
        b["url"], b["first_published"] = "https://x", "2026-01-01"
        self.assertEqual(state.job_sig(a), state.job_sig(b))

    def test_each_tracked_field_changes_it(self):
        base = state.job_sig(job())
        for changed in (job(title="Staff Frontend Engineer"), job(comp=dict(USD, min=200000)),
                        job(comp=dict(USD, max=250000)), job(comp=dict(USD, currency="EUR")),
                        job(comp=dict(USD, interval="hour")), job(locations=("Remote - US", "NYC")), job(comp=None)):
            self.assertNotEqual(state.job_sig(changed), base, changed)


class ProbedOkBoardsTest(HomeCase):
    def test_live_counts_empty_errors_and_dead_do_not(self):
        run = state.new_run(now=NOW)
        state.write_json_atomic(run / "boards.json", {
            "live": 2, "live_boards": ["ashby:acme", "lever:half"], "empty": ["greenhouse:quiet"],
            "dead": ["lever:gone"], "errors": [{"board": "lever:half", "error": "bad job record: x"},
                                               {"board": "ashby:down", "error": "timeout"}]})
        self.assertEqual(state.probed_ok_boards(run), {"ashby:acme"})

    def test_missing_boards_file_is_empty(self):
        self.assertEqual(state.probed_ok_boards(state.new_run(now=NOW)), set())

    def test_probe_stores_live_board_list(self):
        env = {"JOB_SCOUT_REPLAY_DIR": FIXTURES, "JOB_SCOUT_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            probe.main(["--boards", "greenhouse:airtable,greenhouse:webflow"])
        run = state.latest_run()
        self.assertEqual(state.read_json(run / "boards.json")["live_boards"], ["greenhouse:airtable"])
        self.assertEqual(state.probed_ok_boards(run), {"greenhouse:airtable"})  # webflow is empty


class DiffTest(unittest.TestCase):
    OK = {"ashby:acme"}

    def diff(self, jobs, seen, ok=None):
        return state.diff(jobs, self.OK if ok is None else ok, seen)

    def test_new_job_is_in_no_list(self):
        # filter.py's per-candidate state counts new roles; diff over all of jobs.json would not mean anything
        out = self.diff([job()], {})
        self.assertEqual(out, {"changed": [], "saved_open": [], "applied_open": [], "closed": []})

    def test_unchanged_seen_job_is_in_no_list(self):
        out = self.diff([job()], {"ashby:acme:1": entry()})
        self.assertEqual(out, {"changed": [], "saved_open": [], "applied_open": [], "closed": []})

    def test_changed_seen_and_saved(self):
        seen = {"ashby:acme:1": entry(), "ashby:acme:2": entry(status="saved")}
        jobs = [job(title="Staff Frontend Engineer"), job("ashby:acme:2", comp=dict(USD, max=300000))]
        out = self.diff(jobs, seen)
        self.assertEqual(out["changed"], ["ashby:acme:1", "ashby:acme:2"])
        self.assertEqual(out["saved_open"], ["ashby:acme:2"])

    def test_dismissed_and_applied_never_changed(self):
        seen = {"ashby:acme:1": entry(status="dismissed"), "ashby:acme:2": entry(status="applied")}
        out = self.diff([job(title="Other"), job("ashby:acme:2", title="Other")], seen)
        self.assertEqual(out["changed"], [])
        self.assertEqual(out["applied_open"], ["ashby:acme:2"])

    def test_closed_only_when_board_probed_ok(self):
        seen = {"ashby:acme:1": entry(status="saved"), "lever:down:9": entry(), "lever:skipped:8": entry()}
        out = self.diff([], seen, ok={"ashby:acme"})  # lever:down errored, lever:skipped not probed
        self.assertEqual(out["closed"], ["ashby:acme:1"])

    def test_seen_only_role_is_never_reported_closed(self):
        # The closed list is for roles the user cared about; an expired search result is just gone.
        self.assertEqual(self.diff([], {"ashby:acme:1": entry()})["closed"], [])

    def test_dismissed_and_already_closed_never_reported_closed(self):
        seen = {"ashby:acme:1": entry(status="dismissed"), "ashby:acme:2": entry(closed_at="2026-10-10T00:00:00Z")}
        self.assertEqual(self.diff([], seen)["closed"], [])

    def test_match_by_variant_key(self):
        seen = {"ashby:acme:7": entry(job("ashby:acme:1", more=["ashby:acme:7"]))}
        out = self.diff([job("ashby:acme:1", more=["ashby:acme:7"])], seen)
        self.assertEqual(out["closed"], [])
        self.assertEqual(state.job_state(job("ashby:acme:1", more=["ashby:acme:7"]), seen), "seen")

    def test_alias_survives_primary_variant_closing(self):
        first = job("ashby:acme:1", more=["ashby:acme:2"])
        seen = {"ashby:acme:1": entry(first, status="saved", aliases=["ashby:acme:2"])}
        now = job("ashby:acme:2")  # primary posting closed; the other variant is the row now
        now["locations"] = first["locations"]
        out = self.diff([now], seen)
        self.assertEqual(out["closed"] + out["changed"], [])
        self.assertEqual(state.job_state(now, seen), "saved")
        self.assertEqual(out["saved_open"], ["ashby:acme:2"])

    def test_job_state(self):
        seen = {"ashby:acme:1": entry(), "ashby:acme:2": entry(status="saved"), "ashby:acme:3": entry(status="dismissed")}
        idx = state.seen_index(seen)
        self.assertEqual(state.job_state(job(), seen, idx), "seen")
        self.assertEqual(state.job_state(job(title="X"), seen, idx), "changed")
        self.assertEqual(state.job_state(job("ashby:acme:2"), seen, idx), "saved")
        self.assertEqual(state.job_state(job("ashby:acme:3", title="X"), seen, idx), "dismissed")
        self.assertEqual(state.job_state(job("ashby:acme:4"), seen, idx), "new")
        self.assertEqual(state.job_state(job("ashby:acme:4"), {}), "new")

    def test_one_job_matching_two_entries_matches_both(self):
        # two roles recorded separately, now collapsed into one job
        seen = {"ashby:acme:1": entry(), "ashby:acme:2": entry(status="saved")}
        out = self.diff([job("ashby:acme:1", more=["ashby:acme:2"])], seen)
        self.assertEqual(out["closed"], [])
        self.assertEqual(out["saved_open"], ["ashby:acme:1"])

    def test_job_state_takes_the_strongest_status_of_all_matches(self):
        j = job("ashby:acme:1", more=["ashby:acme:2"])
        for first, second, want in (("seen", "saved", "saved"), ("saved", "applied", "saved"),
                                    ("seen", "applied", "applied"), ("seen", "dismissed", "dismissed"),
                                    ("dismissed", "applied", "applied"), ("seen", "seen", "seen")):
            seen = {"ashby:acme:1": entry(j, status=first), "ashby:acme:2": entry(j, status=second)}
            self.assertEqual(state.job_state(j, seen), want, (first, second))

    def test_index_prefers_an_entrys_own_key_over_another_entrys_alias(self):
        seen = {"ashby:acme:1": entry(aliases=["ashby:acme:2"]), "ashby:acme:2": entry(status="saved")}
        self.assertEqual(state.seen_index(seen)["ashby:acme:2"], "ashby:acme:2")
        self.assertEqual(state.job_state(job("ashby:acme:2"), seen), "saved")

    def test_marked_before_record_is_not_changed(self):
        seen = {"ashby:acme:1": dict(entry(status="saved"), sig=None)}  # mark() creates entries with no sig
        self.assertEqual(state.job_state(job(), seen), "saved")
        self.assertEqual(state.diff([job()], {"ashby:acme"}, seen)["changed"], [])


class RecordTest(HomeCase):
    def test_inserts_shown_rows_as_seen_and_unshown_rows_as_judged(self):
        jobs = [job("ashby:acme:1", more=["ashby:acme:5"]), job("ashby:acme:2")]
        run = self.make_run(jobs, [{"key": "ashby:acme:5", "show": True}, {"key": "ashby:acme:2", "show": False}])
        counts = state.record(run, now=NOW)
        seen = state.load_seen()
        self.assertEqual({k: e["status"] for k, e in seen.items()}, {"ashby:acme:1": "seen", "ashby:acme:2": "judged"})
        e = seen["ashby:acme:1"]
        self.assertEqual((e["status"], e["first_seen"], e["last_seen"]), ("seen", state.now_iso(NOW), state.now_iso(NOW)))
        self.assertEqual(e["sig"], state.job_sig(jobs[0]))
        self.assertEqual(e["aliases"], ["ashby:acme:5"])
        self.assertIsNone(e["closed_at"])
        self.assertEqual((counts["inserted"], counts["updated"], counts["judged"]), (1, 0, 1))

    def test_record_keeps_the_shown_link_and_show_lists_it(self):
        j = job("ashby:acme:1", more=["ashby:acme:5"])
        j["url"] = "https://jobs.ashbyhq.com/acme/1"
        j["variants"][1]["url"] = "https://jobs.ashbyhq.com/acme/5"
        run = self.make_run([j], [{"key": "ashby:acme:5", "show": True}])
        state.record(run, now=NOW)
        self.assertEqual(state.load_seen()["ashby:acme:1"]["url"], "https://jobs.ashbyhq.com/acme/5")
        state.mark("ashby:acme:1", "saved")
        self.assertEqual(state.seen_summary()["saved"][0]["url"], "https://jobs.ashbyhq.com/acme/5")

    def test_record_keeps_a_snapshot_of_what_sig_hashes_for_shown_rows_only(self):
        j = job("ashby:acme:1", locations=("NYC", "Remote - US"))
        j["comp"]["source"] = "ats_field"  # not part of sig, so not part of the snapshot
        state.record(self.make_run([j], [{"key": "ashby:acme:1", "show": True}]), now=NOW)
        snap = {"title": "Senior Frontend Engineer", "comp": USD, "locations": ["NYC", "Remote - US"]}
        self.assertEqual(state.load_seen()["ashby:acme:1"]["snap"], snap)
        state.record(self.make_run([job("ashby:acme:1", comp=dict(USD, max=300000))], []), now=LATER)
        self.assertEqual(state.load_seen()["ashby:acme:1"]["snap"], snap)  # unshown: like sig, untouched

    def test_record_keeps_the_live_variants_link_after_a_fallback(self):
        # fetch_jd found the shown posting closed and used variant 5: the user's link must be variant 5's
        j = job("ashby:acme:1", more=["ashby:acme:5"])
        j["url"] = "https://jobs.ashbyhq.com/acme/1"
        j["variants"][1]["url"] = "https://jobs.ashbyhq.com/acme/5"
        run = self.make_run([j], [{"key": "ashby:acme:1", "show": True}])
        state.write_json_atomic(run / "jds.json", {"ashby:acme:1": {"status": "open", "full": "x", "variant": "ashby:acme:5"}})
        state.record(run, now=NOW)
        self.assertEqual(state.load_seen()["ashby:acme:1"]["url"], "https://jobs.ashbyhq.com/acme/5")

    def test_update_keeps_status_and_first_seen(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved")})
        j = job("ashby:acme:9", title="Staff Frontend Engineer", more=["ashby:acme:1"])
        run = self.make_run([j], [{"key": "ashby:acme:9", "show": True}])
        counts = state.record(run, now=LATER)
        e = state.load_seen()["ashby:acme:1"]
        self.assertEqual((e["status"], e["first_seen"], e["last_seen"]), ("saved", "2026-10-01T00:00:00Z", state.now_iso(LATER)))
        self.assertEqual(e["sig"], state.job_sig(j))
        self.assertEqual(e["aliases"], ["ashby:acme:9"])
        self.assertEqual(counts["updated"], 1)

    def test_closed_at_set_then_cleared(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved"), "lever:down:2": entry()})
        run = self.make_run([], [], errors=["lever:down"])
        self.assertEqual(state.record(run, now=NOW)["closed"], 1)
        seen = state.load_seen()
        self.assertEqual(seen["ashby:acme:1"]["closed_at"], state.now_iso(NOW))
        self.assertIsNone(seen["lever:down:2"]["closed_at"])
        run = self.make_run([job()], [])  # back again, not even shown
        self.assertEqual(state.record(run, now=LATER)["reopened"], 1)
        self.assertIsNone(state.load_seen()["ashby:acme:1"]["closed_at"])

    def test_record_without_results_json_still_saves_closures(self):
        # A rerun with nothing new writes no results.json; closures must still be recorded once.
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved")})
        run = self.make_run([], [])
        (run / "results.json").unlink()
        self.assertEqual(state.record(run, now=NOW)["closed"], 1)
        self.assertEqual(state.load_seen()["ashby:acme:1"]["closed_at"], state.now_iso(NOW))

    def test_live_check_closure_is_recorded_though_the_board_list_lags(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved")})
        run = self.make_run([job()], [])  # still on the board list, but fetch_jd found the posting gone
        state.write_json_atomic(run / "jds.json", {"ashby:acme:1": {"status": "closed"}})
        counts = state.record(run, now=NOW)
        self.assertEqual((counts["closed"], counts["reopened"]), (1, 0))
        self.assertEqual(state.load_seen()["ashby:acme:1"]["closed_at"], state.now_iso(NOW))

    def test_live_check_closes_a_role_on_a_partially_searched_board(self):
        # A Workday list is a keyword search, so its board never counts as probed whole; the live check
        # finding the posting gone is direct evidence all the same.
        key = "workday:acme.wd1.External:Nurse_JR1-1"
        state.write_json_atomic(state.seen_path(), {key: entry(job(key), status="saved")})
        run = self.make_run([job(key)], [], live=())
        state.write_json_atomic(run / "jds.json", {key: {"status": "closed"}})
        self.assertEqual(state.record(run, now=NOW)["closed"], 1)
        self.assertEqual(state.load_seen()[key]["closed_at"], state.now_iso(NOW))

    def test_one_closed_variant_leaves_the_grouped_role_open(self):
        for gone in ("ashby:acme:2", "ashby:acme:1"):  # another variant, or the job's own posting
            state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved")})
            grouped = dict(job(), variants=[{"key": "ashby:acme:1"}, {"key": "ashby:acme:2"}])
            run = self.make_run([grouped], [])
            state.write_json_atomic(run / "jds.json", {gone: {"status": "closed"}})
            self.assertEqual(state.record(run, now=NOW)["closed"], 0, gone)
            self.assertIsNone(state.load_seen()["ashby:acme:1"]["closed_at"])

    def test_empty_board_never_closes_a_role(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status="saved")})
        run = self.make_run([], [], live=(), empty=("ashby:acme",))  # board briefly returned {"jobs": []}
        self.assertEqual(state.record(run, now=NOW)["closed"], 0)
        self.assertIsNone(state.load_seen()["ashby:acme:1"]["closed_at"])

    def test_saved_workday_role_missing_from_todays_search_is_not_closed(self):
        # A Workday list is a keyword search, never the whole board: a role it did not return is unseen.
        gone = "workday:sharp.wd1.External:Old-Nurse-Role_JR1-1"
        state.write_json_atomic(state.seen_path(), {gone: entry(status="saved")})
        state.write_json_atomic(state.profile_path(), {"schema": 1, "target_roles": ["nurse"], "work_modes": ["onsite"],
                                                       "needs_sponsorship": "no", "base_pay_floor": None})
        env = {"JOB_SCOUT_REPLAY_DIR": os.path.join(FIXTURES, "workday"), "JOB_SCOUT_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(["--boards", "workday:sharp.wd1.External"]), 0)
        run = state.latest_run()
        self.assertTrue(state.read_json(run / "jobs.json"))  # the board answered; the role just was not in it
        self.assertEqual(state.probed_ok_boards(run), set())
        self.assertEqual(state.record(run, now=NOW)["closed"], 0)
        self.assertIsNone(state.load_seen()[gone]["closed_at"])

    def test_unshown_jobs_refresh_aliases_and_last_seen_so_churning_variants_keep_matching(self):
        run = self.make_run([job("ashby:acme:a", more=["ashby:acme:b"])], [{"key": "ashby:acme:a", "show": True}])
        state.record(run, now=NOW)
        run = self.make_run([job("ashby:acme:b", more=["ashby:acme:c"])], [])  # unchanged: filter dropped it
        state.record(run, now=LATER)
        e = state.load_seen()["ashby:acme:a"]
        self.assertEqual((e["aliases"], e["last_seen"]), (["ashby:acme:b", "ashby:acme:c"], state.now_iso(LATER)))
        out = state.diff([job("ashby:acme:c")], {"ashby:acme"}, state.load_seen())
        self.assertEqual(out["closed"], [])
        self.assertEqual(state.job_state(job("ashby:acme:c"), state.load_seen()), "seen")

    def test_unshown_job_keeps_its_old_sig_so_it_still_reads_changed(self):
        run = self.make_run([job("ashby:acme:a")], [{"key": "ashby:acme:a", "show": True}])
        state.record(run, now=NOW)
        moved = job("ashby:acme:a", title="Staff Frontend Engineer", more=["ashby:acme:b"])
        state.record(self.make_run([moved], []), now=LATER)
        e = state.load_seen()["ashby:acme:a"]
        self.assertEqual((e["sig"], e["aliases"]), (state.job_sig(job("ashby:acme:a")), ["ashby:acme:b"]))
        self.assertEqual(state.job_state(moved, state.load_seen()), "changed")

    def test_shown_job_matching_two_entries_updates_both(self):
        j = job("ashby:acme:1", title="Staff Frontend Engineer", more=["ashby:acme:2"])
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(), "ashby:acme:2": entry(status="saved")})
        state.record(self.make_run([j], [{"key": "ashby:acme:1", "show": True}]), now=LATER)
        seen = state.load_seen()
        self.assertEqual([seen[k]["sig"] for k in sorted(seen)], [state.job_sig(j)] * 2)
        self.assertEqual(state.job_state(j, seen), "saved")

    def test_missing_results_raises(self):
        run = state.new_run(now=NOW)
        with self.assertRaises(FileNotFoundError):
            state.record(run, now=NOW)


def row(key, show, total=6):
    """A results.json row as the judgment step writes it."""
    scores = dict(zip(("role", "skills", "level", "domain"), (min(2, max(0, total - 2 * i)) for i in range(4))))
    return {"key": key, "show": show, "total": total, "gates": {"location": "pass", "sponsorship": "unknown",
            "pay": "pass", "exclusions": "pass"}, "scores": scores,  # the four scores sum to total
            "why": [{"text": "Owns the design system", "quote": "own and evolve our design system"}],
            "risk": [{"text": "sponsorship not stated", "quote": None}], "style": []}


JD = "Build product features end to end. Own and evolve our design system."


def live(text=JD, comp=None, **job_fields):
    """A jds.json entry as fetch_jd writes it: the description plus the live pay and display fields."""
    return {"status": "open", "full": text, "comp": comp,
            "job": dict({"title": "Senior Frontend Engineer", "locations": ["Remote - US"], "workplace": "remote",
                         "remote_scope": ["US"]}, **job_fields)}
BRIEF = {"schema": 1, "target_roles": ["Product Engineer"], "work_modes": ["remote"], "remote_scope": ["US"],
         "needs_sponsorship": "no", "base_pay_floor": None}


class JudgedTest(HomeCase):
    """judged = screened by an earlier run (read and cut, or never read), judgment cached, never shown."""

    def setUp(self):
        super().setUp()
        state.write_json_atomic(state.profile_path(), BRIEF)

    def run_with_jd(self, jobs, rows, text=JD):
        run = self.make_run(jobs, rows)
        state.write_json_atomic(run / "jds.json", {r["key"]: live(text) for r in rows})
        return run

    def test_unshown_row_is_judged_with_its_judgment_and_posting(self):
        j = job("ashby:acme:1")
        j["url"] = "https://jobs.ashbyhq.com/acme/1"
        run = self.run_with_jd([j], [row("ashby:acme:1", False)])
        state.record(run, now=NOW)
        e = state.load_seen()["ashby:acme:1"]
        self.assertEqual((e["status"], e["sig"], e["snap"], e["title"], e["company"], e["url"]),
                         ("judged", state.job_sig(j), state.job_snap(j), j["title"], "Acme", j["url"]))
        r = row("ashby:acme:1", False)
        self.assertEqual(e["judgment"], {"total": 6, "scores": r["scores"], "gates": r["gates"], "show": False,
                                         "why": r["why"], "risk": r["risk"], "style": [], "run": run.name,
                                         "judged_at": state.now_iso(NOW), "sig": state.job_sig(j),
                                         "jd_sig": state.jd_sig(live()), "brief_sig": state.brief_sig(BRIEF),
                                         "work_style": {}})

    def test_unread_candidate_is_judged_without_a_judgment(self):
        jobs = [job("ashby:acme:1"), job("ashby:acme:2")]
        run = self.make_run(jobs, [row("ashby:acme:1", True)])
        state.write_json_atomic(run / "candidates.json", jobs)  # acme:2 passed filter.py but was never read
        counts = state.record(run, now=NOW)
        e = state.load_seen()["ashby:acme:2"]
        self.assertEqual((e["status"], e["sig"]), ("judged", state.job_sig(jobs[1])))
        self.assertNotIn("judgment", e)
        self.assertEqual(counts["judged"], 1)

    def test_unread_candidate_keeps_an_earlier_judgment(self):
        run = self.make_run([job()], [row("ashby:acme:1", False)])
        state.record(run, now=NOW)
        run = self.make_run([job()], [])
        state.write_json_atomic(run / "candidates.json", [job()])
        state.record(run, now=LATER)
        e = state.load_seen()["ashby:acme:1"]
        self.assertEqual((e["status"], e["judgment"]["judged_at"], e["last_seen"]),
                         ("judged", state.now_iso(NOW), state.now_iso(LATER)))

    def test_shown_row_promotes_judged_to_seen_and_first_seen_is_when_shown(self):
        state.record(self.make_run([job()], [row("ashby:acme:1", False)]), now=NOW)
        state.record(self.make_run([job()], [row("ashby:acme:1", True, total=7)]), now=LATER)
        e = state.load_seen()["ashby:acme:1"]
        self.assertEqual((e["status"], e["first_seen"]), ("seen", state.now_iso(LATER)))
        self.assertEqual((e["judgment"]["show"], e["judgment"]["total"]), (True, 7))

    def test_unshown_row_never_weakens_a_stronger_entry_or_moves_its_sig(self):
        for status in ("seen", "saved", "applied", "dismissed"):
            state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(status=status)})
            moved = job(title="Staff Frontend Engineer")
            state.record(self.make_run([moved], [row("ashby:acme:1", False)]), now=LATER)
            e = state.load_seen()["ashby:acme:1"]
            self.assertEqual((e["status"], e["sig"]), (status, state.job_sig(job())), status)
            self.assertEqual(e["judgment"]["sig"], state.job_sig(moved), status)  # what was judged: the new posting

    def test_job_state_judged_then_new_when_the_posting_changes(self):
        seen = {"ashby:acme:1": entry(status="judged")}
        self.assertEqual(state.job_state(job(), seen), "judged")
        self.assertEqual(state.job_state(job(comp=dict(USD, max=300000)), seen), "new")

    def test_judged_is_the_weakest_status(self):
        j = job("ashby:acme:1", more=["ashby:acme:2"])
        for other in ("seen", "saved", "applied", "dismissed"):
            seen = {"ashby:acme:1": entry(j, status="judged"), "ashby:acme:2": entry(j, status=other)}
            self.assertEqual(state.job_state(j, seen), other)

    def test_judged_role_is_never_reported_closed(self):
        self.assertEqual(state.diff([], {"ashby:acme"}, {"ashby:acme:1": entry(status="judged")})["closed"], [])

    def test_mark_refuses_judged(self):
        with self.assertRaises(ValueError):
            state.mark("ashby:acme:1", "judged")
        self.assertFalse(state.seen_path().exists())

    def test_mark_saves_a_judged_role(self):
        state.record(self.make_run([job()], [row("ashby:acme:1", False)]), now=NOW)
        state.mark("ashby:acme:1", "saved")
        self.assertEqual(state.load_seen()["ashby:acme:1"]["status"], "saved")

    def test_cached_judgment_needs_the_same_posting_and_the_same_brief(self):
        state.record(self.run_with_jd([job()], [row("ashby:acme:1", False)]), now=NOW)
        seen = state.load_seen()
        self.assertEqual(state.cached_judgment(job(), seen, BRIEF, live())["total"], 6)
        self.assertIsNone(state.cached_judgment(job(title="Staff Frontend Engineer"), seen, BRIEF, live()))
        for edit in ({"work_modes": ["remote", "hybrid"]}, {"base_pay_floor": {"amount": 150000}},
                     {"dealbreakers": ["crypto"]}, {"seniority": ["Staff"]}, {"needs_sponsorship": "yes"},
                     {"must_haves": ["Go"]}):
            self.assertIsNone(state.cached_judgment(job(), seen, dict(BRIEF, **edit), live()), edit)
        # work style is display only, so changing it keeps the cached gates and scores
        self.assertIsNotNone(state.cached_judgment(job(), seen, dict(BRIEF, work_style={"travel": "none"}), live()))

    def test_cached_judgment_needs_the_same_description(self):
        # An employer can edit a posting in place (add "no sponsorship") without touching title, pay or places.
        state.record(self.run_with_jd([job()], [row("ashby:acme:1", False)]), now=NOW)
        seen = state.load_seen()
        self.assertIsNotNone(state.cached_judgment(job(), seen, BRIEF, live("  " + JD.replace(" ", "\n ") + "\n")))
        self.assertIsNone(state.cached_judgment(job(), seen, BRIEF, live(JD + " We do not sponsor visas.")))
        self.assertIsNone(state.cached_judgment(job(), seen, BRIEF, live("")))
        self.assertIsNone(state.cached_judgment(job(), seen, BRIEF, {"status": "closed"}))
        # before the live check there is no text yet: posting and brief only, and the caller checks again
        self.assertIsNotNone(state.cached_judgment(job(), seen, BRIEF, None))

    def test_cached_judgment_needs_the_same_live_pay_and_places(self):
        # Greenhouse lists no pay on the board: the live check's pay is what the pay gate judged.
        state.record(self.run_with_jd([job(comp=None)], [row("ashby:acme:1", False)]), now=NOW)
        seen = state.load_seen()
        self.assertIsNotNone(state.cached_judgment(job(comp=None), seen, BRIEF, live()))
        for changed in (live(comp=USD), live(locations=["Remote - Canada"]), live(workplace="hybrid"),
                        live(remote_scope=["CA"]), live(title="Staff Frontend Engineer")):
            self.assertIsNone(state.cached_judgment(job(comp=None), seen, BRIEF, changed), changed)

    def test_changed_work_style_drops_only_the_cached_style(self):
        styled = dict(BRIEF, work_style={"travel": "none"})
        state.write_json_atomic(state.profile_path(), styled)
        r = dict(row("ashby:acme:1", True), style=[{"topic": "travel", "verdict": "conflict",
                                                    "text": "Some travel", "quote": "travel up to 25% of the time"}])
        state.record(self.run_with_jd([job()], [r]), now=NOW)
        seen = state.load_seen()
        self.assertEqual(state.cached_judgment(job(), seen, styled, live())["style"], r["style"])
        moved = state.cached_judgment(job(), seen, dict(BRIEF, work_style={"travel": "some"}), live())
        self.assertIsNone(moved["style"])  # a conflict under "none" may be a match under "some": write it again
        self.assertEqual((moved["total"], moved["gates"]), (6, r["gates"]))  # work style never moves fit

    def test_forget_drops_every_cached_judgment_and_keeps_statuses(self):
        # A new resume can change the skills score, and the profile does not store the resume.
        state.write_json_atomic(state.seen_path(), {"ashby:acme:2": entry(status="saved")})
        state.record(self.run_with_jd([job(), job("ashby:acme:2")],
                                      [row("ashby:acme:1", False), row("ashby:acme:2", True)]), now=NOW)
        self.assertEqual(state.forget_judgments(), 2)
        seen = state.load_seen()
        self.assertEqual({k: e["status"] for k, e in seen.items()}, {"ashby:acme:1": "judged", "ashby:acme:2": "saved"})
        self.assertFalse([k for k, e in seen.items() if "judgment" in e])
        self.assertIsNone(state.cached_judgment(job(), seen, BRIEF, live()))

    def test_no_cached_judgment_when_the_judged_text_was_not_kept(self):
        state.record(self.make_run([job()], [row("ashby:acme:1", False)]), now=NOW)  # no jds.json
        self.assertIsNone(state.cached_judgment(job(), state.load_seen(), BRIEF, live()))

    def test_no_cached_judgment_for_an_unread_or_unknown_role(self):
        run = self.make_run([job()], [])
        state.write_json_atomic(run / "candidates.json", [job()])
        state.record(run, now=NOW)
        self.assertIsNone(state.cached_judgment(job(), state.load_seen(), BRIEF, None))
        self.assertIsNone(state.cached_judgment(job("ashby:acme:9"), state.load_seen(), BRIEF, None))

    def test_judged_entries_are_pruned_60_days_after_last_seen_and_no_other_status_is(self):
        day = 86400
        state.write_json_atomic(state.seen_path(), {
            "ashby:acme:1": dict(entry(status="judged"), last_seen=state.now_iso(NOW - 61 * day)),
            "ashby:acme:2": dict(entry(status="judged"), last_seen=state.now_iso(NOW - 59 * day)),
            "ashby:acme:3": dict(entry(status="seen"), last_seen=state.now_iso(NOW - 400 * day)),
            "ashby:acme:4": dict(entry(status="saved"), last_seen=state.now_iso(NOW - 400 * day))})
        counts = state.record(self.make_run([], [], live=()), now=NOW)
        self.assertEqual(sorted(state.load_seen()), ["ashby:acme:2", "ashby:acme:3", "ashby:acme:4"])
        self.assertEqual(counts["pruned"], 1)

    def test_a_judged_role_still_listed_is_never_pruned(self):
        old = dict(entry(status="judged"), last_seen=state.now_iso(NOW - 90 * 86400))
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": old})
        state.record(self.make_run([job()], []), now=NOW)  # on the board today: last_seen refreshed first
        self.assertIn("ashby:acme:1", state.load_seen())


class CarryRankTest(HomeCase):
    """judged carry seeds results.json with still-valid judgments; judged rank orders it by rubric §2."""

    def setUp(self):
        super().setUp()
        state.write_json_atomic(state.profile_path(), BRIEF)

    def judged_run(self, jobs, rows):
        """Run 1: judge rows and record them. Returns the jobs for run 2."""
        state.record(self.run_with_jd(jobs, rows), now=NOW)

    def run2(self, jobs, live_by_key, cached=None):
        run = self.make_run(jobs, [])
        (run / "results.json").unlink()
        state.write_json_atomic(run / "candidates.json",
                                [dict(j, cached=j["key"] in (cached if cached is not None else live_by_key)) for j in jobs])
        state.write_json_atomic(run / "jds.json", live_by_key)
        return run

    run_with_jd = JudgedTest.run_with_jd

    def test_carry_seeds_valid_judgments_and_lists_what_to_read_again(self):
        jobs = [job("ashby:acme:%d" % i) for i in range(1, 5)]
        self.judged_run(jobs, [row(j["key"], i < 2, total=7 - i) for i, j in enumerate(jobs)])
        run = self.run2(jobs, {"ashby:acme:1": live(), "ashby:acme:2": live(JD + " Must be in Berlin."),
                               "ashby:acme:3": {"status": "closed"}}, cached=[j["key"] for j in jobs])
        out = state.carry(run)
        self.assertEqual(out, {"carried": ["ashby:acme:1"], "read_again": ["ashby:acme:2"], "closed": ["ashby:acme:3"],
                               "skipped": [{"key": "ashby:acme:4", "why": "no live check this run"}]})
        rows = state.read_json(run / "results.json")["rows"]
        r = row("ashby:acme:1", True, total=7)
        self.assertEqual(rows, [{"key": "ashby:acme:1", "carried": True, "total": 7, "scores": r["scores"],
                                 "gates": r["gates"], "show": True, "why": r["why"], "risk": r["risk"], "style": []}])

    def test_carry_skips_unverified_and_no_longer_fitting_roles(self):
        jobs = [job("ashby:acme:1"), job("ashby:acme:2")]
        self.judged_run(jobs, [row("ashby:acme:1", True), row("ashby:acme:2", True)])
        run = self.run2(jobs, {"ashby:acme:1": {"status": "unverified"},
                               "ashby:acme:2": dict(live(), dropped="changed since the search: now removed by location")})
        self.assertEqual(state.carry(run)["skipped"], [
            {"key": "ashby:acme:1", "why": "live check: unverified"},
            {"key": "ashby:acme:2", "why": "changed since the search: now removed by location"}])
        self.assertEqual(state.read_json(run / "results.json")["rows"], [])

    def test_carry_keeps_the_models_rows_and_does_not_repeat_itself(self):
        jobs = [job("ashby:acme:1"), job("ashby:acme:2")]
        self.judged_run(jobs[:1], [row("ashby:acme:1", True)])
        run = self.run2(jobs, {"ashby:acme:1": live()}, cached=["ashby:acme:1"])
        state.write_json_atomic(run / "results.json", {"rows": [row("ashby:acme:2", True, total=8)]})
        state.carry(run)
        state.carry(run)
        self.assertEqual([r["key"] for r in state.read_json(run / "results.json")["rows"]], ["ashby:acme:2", "ashby:acme:1"])

    def test_carry_never_overrides_a_row_the_model_wrote_for_the_same_role(self):
        self.judged_run([job()], [row("ashby:acme:1", True)])
        run = self.run2([job()], {"ashby:acme:1": live()})
        state.write_json_atomic(run / "results.json", {"rows": [row("ashby:acme:1", False, total=3)]})  # judged again
        self.assertEqual(state.carry(run)["carried"], [])
        self.assertEqual(state.read_json(run / "results.json")["rows"], [row("ashby:acme:1", False, total=3)])

    def test_carried_style_is_empty_when_the_work_style_changed(self):
        styled = dict(BRIEF, work_style={"travel": "none"})
        state.write_json_atomic(state.profile_path(), styled)
        r = dict(row("ashby:acme:1", True), style=[{"topic": "travel", "verdict": "conflict", "text": "x",
                                                    "quote": "travel up to 25% of the time"}])
        self.judged_run([job()], [r])
        state.write_json_atomic(state.profile_path(), dict(BRIEF, work_style={"travel": "some"}))
        run = self.run2([job()], {"ashby:acme:1": live()})
        state.carry(run)
        self.assertEqual(state.read_json(run / "results.json")["rows"][0]["style"], [])  # cite_check then asks for it

    def rank(self, rows, cands, result_count=2):
        state.write_json_atomic(state.profile_path(), dict(BRIEF, result_count=result_count))
        run = self.make_run([], rows)
        state.write_json_atomic(run / "candidates.json", cands)
        out = state.rank(run)
        return out, state.read_json(run / "results.json")["rows"]

    def test_rank_orders_by_total_then_exact_scope_then_newest_and_sets_show(self):
        cands = [dict(job("ashby:acme:%d" % i), flags=f, first_published=d) for i, f, d in (
            (1, [], "2026-10-01"), (2, ["remote scope not stated"], "2026-10-09"), (3, [], "2026-10-05"),
            (4, [], "2026-10-09"), (5, [], "2026-10-09"), (6, [], None))]
        rows = [row("ashby:acme:1", False, 6), row("ashby:acme:2", True, 7), row("ashby:acme:3", True, 7),
                dict(row("ashby:acme:4", True, 8), gates=dict(row("x", True)["gates"], location="fail")),
                row("ashby:acme:5", True, 4), row("ashby:acme:6", True, 7)]
        out, ranked = self.rank(rows, cands)
        self.assertEqual([(r["key"][-1], r["show"]) for r in ranked],
                         [("3", True), ("6", True), ("2", False), ("1", False), ("4", False), ("5", False)])
        self.assertEqual(out, {"shown": 2, "matches": 4})

    def test_rank_prefers_the_live_flags_and_date(self):
        cands = [dict(job("ashby:acme:1"), flags=[], first_published="2026-10-01"),
                 dict(job("ashby:acme:2"), flags=[], first_published="2026-10-02")]
        state.write_json_atomic(state.profile_path(), dict(BRIEF, result_count=5))
        run = self.make_run([], [row("ashby:acme:1", True, 7), row("ashby:acme:2", True, 7)])
        state.write_json_atomic(run / "candidates.json", cands)
        state.write_json_atomic(run / "jds.json", {"ashby:acme:2": {"status": "open", "job": {
            "flags": ["remote scope not stated"], "first_published": "2026-10-09"}}})
        state.rank(run)
        self.assertEqual([r["key"] for r in state.read_json(run / "results.json")["rows"]], ["ashby:acme:1", "ashby:acme:2"])

    def test_rank_falls_back_to_the_candidate_for_a_field_the_live_check_lacks(self):
        cands = [dict(job("ashby:acme:1"), flags=[], first_published="2026-10-01"),
                 dict(job("ashby:acme:2"), flags=[], first_published="2026-10-09")]
        state.write_json_atomic(state.profile_path(), dict(BRIEF, result_count=5))
        run = self.make_run([], [row("ashby:acme:1", True, 7), row("ashby:acme:2", True, 7)])
        state.write_json_atomic(run / "candidates.json", cands)
        state.write_json_atomic(run / "jds.json", {"ashby:acme:2": {"status": "open", "job": {"title": "x"}}})
        state.rank(run)
        self.assertEqual([r["key"] for r in state.read_json(run / "results.json")["rows"]], ["ashby:acme:2", "ashby:acme:1"])

    def test_rank_clears_style_on_rows_it_cuts_so_cite_check_passes(self):
        state.write_json_atomic(state.profile_path(), dict(BRIEF, work_style={"travel": "none"}, result_count=1))
        style = [{"topic": "travel", "verdict": "match", "text": "No travel", "quote": "own and evolve our design system"}]
        rows = [dict(row("ashby:acme:1", True, 7), style=style, carried=True), dict(row("ashby:acme:2", True, 8), style=style)]
        run = self.run_with_jd([job("ashby:acme:1"), job("ashby:acme:2")], rows)
        state.write_json_atomic(run / "candidates.json", [job("ashby:acme:1"), job("ashby:acme:2")])
        state.rank(run)
        ranked = state.read_json(run / "results.json")["rows"]
        self.assertEqual([(r["key"], r["show"], r["style"]) for r in ranked],
                         [("ashby:acme:2", True, style), ("ashby:acme:1", False, [])])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(json.dumps({"rows": ranked}))):
            self.assertEqual(cite_check.main(["--run", run.name]), 0, out.getvalue())

    def test_rank_uses_the_sum_of_the_four_scores_like_the_report(self):
        # an inconsistent total must not let a 4/8 role through the rubric's cutoff at 5
        bad = dict(row("ashby:acme:1", True, 7), scores={"role": 1, "skills": 1, "level": 1, "domain": 1})
        out, ranked = self.rank([bad, row("ashby:acme:2", True, 5)],
                                [job("ashby:acme:1"), job("ashby:acme:2")], result_count=5)
        self.assertEqual([(r["key"], r["show"]) for r in ranked], [("ashby:acme:2", True), ("ashby:acme:1", False)])
        self.assertEqual(out, {"shown": 1, "matches": 1})

    def test_rank_never_shows_a_row_with_a_missing_gate_or_a_score_out_of_range(self):
        no_gate = dict(row("ashby:acme:1", True, 8), gates={"location": "pass", "pay": "pass", "exclusions": "pass"})
        too_big = dict(row("ashby:acme:2", True, 8), scores={"role": 2, "skills": 2, "level": 2, "domain": 3}, total=9)
        out, ranked = self.rank([no_gate, too_big, row("ashby:acme:3", True, 5)],
                                [job("ashby:acme:%d" % i) for i in (1, 2, 3)], result_count=5)
        self.assertEqual({r["key"]: r["show"] for r in ranked},
                         {"ashby:acme:1": False, "ashby:acme:2": False, "ashby:acme:3": True})
        self.assertEqual(out, {"shown": 1, "matches": 1})
        self.assertIsNone(state.fit(too_big))

    def test_an_extra_gate_never_hides_a_role(self):
        extra = dict(row("ashby:acme:1", True, 8), gates=dict(row("x", True)["gates"], work_style="fail"))
        out, ranked = self.rank([extra], [job("ashby:acme:1")])
        self.assertEqual((ranked[0]["show"], out["matches"]), (True, 1))

    def test_rank_treats_an_impossible_date_as_unknown(self):
        cands = [dict(job("ashby:acme:1"), flags=[], first_published="2026-99-99"),
                 dict(job("ashby:acme:2"), flags=[], first_published="2026-10-01")]
        _, ranked = self.rank([row("ashby:acme:1", True, 7), row("ashby:acme:2", True, 7)], cands, result_count=1)
        self.assertEqual([(r["key"], r["show"]) for r in ranked], [("ashby:acme:2", True), ("ashby:acme:1", False)])

    def test_rank_keeps_one_row_per_role(self):
        rows = [row("ashby:acme:1", True, 8), row("ashby:acme:1", True, 8), row("ashby:acme:2", True, 6)]
        out, ranked = self.rank(rows, [job("ashby:acme:1"), job("ashby:acme:2")], result_count=2)
        self.assertEqual([(r["key"], r["show"]) for r in ranked], [("ashby:acme:1", True), ("ashby:acme:2", True)])
        self.assertEqual(out, {"shown": 2, "matches": 2})

    def test_judged_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(state.main(["judged", "carry"]), 2)  # no run yet
            self.assertEqual(state.main(["judged", "rank", "--run", "../x"]), 1)
        run = self.make_run([job()], [row("ashby:acme:1", True)])
        state.write_json_atomic(run / "candidates.json", [job()])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(state.main(["judged", "rank", "--run", run.name]), 0)
            self.assertEqual(state.main(["judged", "carry", "--run", run.name]), 0)
        self.assertEqual([json.loads(l) for l in out.getvalue().splitlines()],
                         [{"shown": 1, "matches": 1}, {"carried": [], "read_again": [], "closed": [], "skipped": []}])


class MarkTest(HomeCase):
    def test_creates_unknown_key(self):
        state.mark("ashby:acme:1", "saved", now=NOW)
        e = state.load_seen()["ashby:acme:1"]
        self.assertEqual((e["status"], e["reason"], e["first_seen"]), ("saved", None, state.now_iso(NOW)))

    def test_alias_updates_existing_entry_with_reason(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(aliases=["ashby:acme:2"])})
        state.mark("ashby:acme:2", "dismissed", reason="too senior")
        seen = state.load_seen()
        self.assertEqual(list(seen), ["ashby:acme:1"])
        self.assertEqual((seen["ashby:acme:1"]["status"], seen["ashby:acme:1"]["reason"]), ("dismissed", "too senior"))

    def test_bad_status_and_key(self):
        for key, status in (("ashby:acme:1", "loved"), ("", "saved"), ("no-colons", "saved")):
            with self.assertRaises(ValueError):
                state.mark(key, status)
        with self.assertRaises(ValueError):
            state.mark("ashby:acme:1", "saved", reason="x" * 201)
        self.assertFalse(state.seen_path().exists())


class CorruptSeenTest(HomeCase):
    BAD = (b'{"ashby:acme:1": {"status": "sa', b"[]", b'"text"', b"\xff\xfe{}")

    def test_malformed_entries_raise(self):
        for bad in ({"ashby:acme:1": None}, {"ashby:acme:1": {"status": "maybe"}},
                    {"ashby:acme:1": {"status": "seen", "aliases": "ashby:acme:2"}},
                    {"ashby:acme:1": {"status": "seen", "aliases": [3]}}):
            state.write_json_atomic(state.seen_path(), bad)
            with self.assertRaises(ValueError):
                state.load_seen()

    def test_missing_file_is_a_first_run(self):
        self.assertEqual(state.load_seen(), {})

    def test_corrupt_or_wrong_shape_raises_and_nothing_is_written(self):
        run = self.make_run([job()], [{"key": "ashby:acme:1", "show": True}])
        for raw in self.BAD:
            state.seen_path().write_bytes(raw)
            for call in (state.load_seen, lambda: state.mark("ashby:acme:1", "saved"), lambda: state.record(run, now=NOW)):
                with self.assertRaises(ValueError) as ctx:
                    call()
                self.assertIn(str(state.seen_path()), str(ctx.exception))
                self.assertEqual(state.seen_path().read_bytes(), raw)

    def test_unreadable_file_raises(self):
        state.seen_path().mkdir(parents=True)  # exists but cannot be read as a file
        with self.assertRaises(ValueError):
            state.load_seen()

    def test_mark_by_another_entrys_alias_hits_the_entry_that_owns_the_key(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": entry(aliases=["ashby:acme:2"]),
                                                    "ashby:acme:2": entry()})
        state.mark("ashby:acme:2", "applied")
        seen = state.load_seen()
        self.assertEqual((seen["ashby:acme:1"]["status"], seen["ashby:acme:2"]["status"]), ("seen", "applied"))


class SeenCliTest(HomeCase):
    def cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = state.main(argv)
        return code, json.loads(out.getvalue())

    def test_no_run_exits_2(self):
        for argv in (["seen", "diff"], ["seen", "record"]):
            code, out = self.cli(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("error", out)

    def test_bad_run_id_exits_1(self):
        code, out = self.cli(["seen", "diff", "--run", "../etc"])
        self.assertEqual(code, 1)

    def test_diff_record_mark_show(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:9": entry()})
        run = self.make_run([job()], [{"key": "ashby:acme:1", "show": True}])
        code, out = self.cli(["seen", "diff", "--run", run.name])
        self.assertEqual(code, 0)  # acme:9 was only seen, so its closing is not reported
        self.assertEqual(out["counts"], {"changed": 0, "saved_open": 0, "applied_open": 0, "closed": 0})
        self.assertNotIn("new", out)
        code, out = self.cli(["seen", "record"])
        self.assertEqual(code, 0)
        self.assertEqual(out["inserted"], 1)
        code, out = self.cli(["seen", "mark", "ashby:acme:1", "saved", "--reason", "great team"])
        self.assertEqual((code, out["status"]), (0, "saved"))
        code, out = self.cli(["seen", "show"])
        self.assertEqual(code, 0)
        self.assertEqual(out["counts"], {"seen": 1, "saved": 1})
        self.assertEqual(out["saved"], [{"key": "ashby:acme:1", "aliases": [], "title": "Senior Frontend Engineer",
                                         "company": "Acme", "url": None, "closed": False}])
        self.assertEqual(out["applied"], [])

    def test_corrupt_seen_exits_1_and_is_not_changed(self):
        self.make_run([job()], [{"key": "ashby:acme:1", "show": True}])
        state.seen_path().write_bytes(b"[]")
        for argv in (["seen", "diff"], ["seen", "record"], ["seen", "mark", "ashby:acme:1", "saved"], ["seen", "show"]):
            code, out = self.cli(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("unreadable", out["error"])
            self.assertIn("not changed", out["error"])
            self.assertEqual(state.seen_path().read_bytes(), b"[]")

    def test_diff_lists_closed_details(self):
        state.write_json_atomic(state.seen_path(), {"ashby:acme:9": dict(entry(status="saved"), title="Old role",
                                                                         company="Acme", url="https://x/9")})
        run = self.make_run([], [])
        code, out = self.cli(["seen", "diff", "--run", run.name])
        self.assertEqual(code, 0)
        self.assertEqual(out["closed"], ["ashby:acme:9"])
        self.assertEqual(out["closed_details"], [{"key": "ashby:acme:9", "title": "Old role", "company": "Acme",
                                                  "status": "saved", "url": "https://x/9"}])
        self.assertEqual(out["counts"]["closed"], 1)
        self.assertNotIn("closed_details", out["counts"])

    def test_diff_details_a_promoted_variant(self):
        # The job's own posting is live-closed; the still-listed variant takes over and reads changed.
        old = job("ashby:acme:1")
        state.write_json_atomic(state.seen_path(), {"ashby:acme:1": dict(entry(old, status="saved"),
                                                                         snap=state.job_snap(old))})
        grouped = dict(old, variants=[{"key": "ashby:acme:1"},
                                      {"key": "ashby:acme:2", "title": "Staff Frontend Engineer"}])
        run = self.make_run([grouped], [])
        state.write_json_atomic(run / "jds.json", {"ashby:acme:1": {"status": "closed"}})
        code, out = self.cli(["seen", "diff", "--run", run.name])
        self.assertEqual((code, out["changed"], out["saved_open"]), (0, ["ashby:acme:2"], ["ashby:acme:2"]))
        self.assertEqual(out["changed_details"][0]["after"]["title"], "Staff Frontend Engineer")

    def test_diff_lists_changed_details(self):
        old, new = job("ashby:acme:1"), job("ashby:acme:1", comp=dict(USD, max=300000))
        nosnap = job("ashby:acme:2", title="Staff Frontend Engineer")
        state.write_json_atomic(state.seen_path(), {
            "ashby:acme:1": dict(entry(old), snap=state.job_snap(old)),
            "ashby:acme:2": entry(job("ashby:acme:2"))})  # written before snapshots existed
        run = self.make_run([new, nosnap], [])
        code, out = self.cli(["seen", "diff", "--run", run.name])
        self.assertEqual(code, 0)
        self.assertEqual(out["changed"], ["ashby:acme:1", "ashby:acme:2"])
        self.assertEqual(out["changed_details"], [
            {"key": "ashby:acme:1", "before": {"title": "Senior Frontend Engineer", "comp": USD, "locations": ["Remote - US"]},
             "after": {"title": "Senior Frontend Engineer", "comp": dict(USD, max=300000), "locations": ["Remote - US"]}},
            {"key": "ashby:acme:2", "before": None,
             "after": {"title": "Staff Frontend Engineer", "comp": USD, "locations": ["Remote - US"]}}])
        self.assertNotIn("changed_details", out["counts"])

    def test_reason_starting_with_a_dash(self):
        code, out = self.cli(["seen", "mark", "ashby:acme:1", "dismissed", "--reason=-3 yrs"])
        self.assertEqual((code, out["reason"]), (0, "-3 yrs"))
        with contextlib.redirect_stderr(io.StringIO()):
            code, out = self.cli(["seen", "mark", "ashby:acme:2", "dismissed", "--reason", "-onsite"])
        self.assertEqual(code, 1)  # argparse failure is bad input, never 2 (= no run)
        self.assertIn("error", out)
        self.assertNotIn("ashby:acme:2", state.load_seen())

    def test_judged_forget(self):
        code, out = self.cli(["judged", "forget"])
        self.assertEqual((code, out), (0, {"forgot": 0}))
        state.seen_path().write_bytes(b"[]")
        code, out = self.cli(["judged", "forget"])
        self.assertEqual(code, 1)
        self.assertEqual(state.seen_path().read_bytes(), b"[]")

    def test_mark_bad_status_exits_1(self):
        for status in ("loved", "judged"):  # judged is set only by `seen record`
            code, out = self.cli(["seen", "mark", "ashby:acme:1", status])
            self.assertEqual(code, 1, status)
            self.assertIn("error", out)
            self.assertFalse(state.seen_path().exists())

    def test_show_empty(self):
        code, out = self.cli(["seen", "show"])
        self.assertEqual((code, out["counts"], out["saved"], out["dismissed"]), (0, {}, [], []))

    def test_claude_ai_paste_block_round_trip_keeps_a_dismissed_role_hidden(self):
        state.record(self.make_run([job(more=["ashby:acme:5"])], [{"key": "ashby:acme:1", "show": True}]), now=NOW)
        self.cli(["seen", "mark", "ashby:acme:1", "dismissed"])
        code, out = self.cli(["seen", "show"])
        self.assertEqual([(d["key"], d["aliases"], d["title"], d["company"]) for d in out["dismissed"]],
                         [("ashby:acme:1", ["ashby:acme:5"], "Senior Frontend Engineer", "Acme")])
        state.seen_path().unlink()  # a new claude.ai chat: nothing persisted
        # restoring the pasted block; the primary posting has since closed, so only variant 5 is listed
        self.assertEqual(self.cli(["seen", "mark", "ashby:acme:1", "dismissed", "--aliases", "ashby:acme:5"])[0], 0)
        self.assertEqual(state.job_state(job("ashby:acme:5"), state.load_seen()), "dismissed")

    def test_mark_rejects_a_bad_alias_and_writes_nothing(self):
        code, out = self.cli(["seen", "mark", "ashby:acme:1", "saved", "--aliases", "not a key"])
        self.assertEqual(code, 1)
        self.assertIn("bad job key", out["error"])
        self.assertFalse(state.seen_path().exists())


if __name__ == "__main__":
    unittest.main()
