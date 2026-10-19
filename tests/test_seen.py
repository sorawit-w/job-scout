import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    def test_live_and_empty_count_errors_and_dead_do_not(self):
        run = state.new_run(now=NOW)
        state.write_json_atomic(run / "boards.json", {
            "live": 2, "live_boards": ["ashby:acme", "lever:half"], "empty": ["greenhouse:quiet"],
            "dead": ["lever:gone"], "errors": [{"board": "lever:half", "error": "bad job record: x"},
                                               {"board": "ashby:down", "error": "timeout"}]})
        self.assertEqual(state.probed_ok_boards(run), {"ashby:acme", "greenhouse:quiet"})

    def test_missing_boards_file_is_empty(self):
        self.assertEqual(state.probed_ok_boards(state.new_run(now=NOW)), set())

    def test_probe_stores_live_board_list(self):
        env = {"JOB_SCOUT_REPLAY_DIR": FIXTURES, "JOB_SCOUT_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            probe.main(["--boards", "greenhouse:airtable,greenhouse:webflow"])
        run = state.latest_run()
        self.assertEqual(state.read_json(run / "boards.json")["live_boards"], ["greenhouse:airtable"])
        self.assertEqual(state.probed_ok_boards(run), {"greenhouse:airtable", "greenhouse:webflow"})


class DiffTest(unittest.TestCase):
    OK = {"ashby:acme"}

    def diff(self, jobs, seen, ok=None):
        return state.diff(jobs, self.OK if ok is None else ok, seen)

    def test_new_job(self):
        out = self.diff([job()], {})
        self.assertEqual(out["new"], ["ashby:acme:1"])
        self.assertEqual(out["changed"] + out["saved_open"] + out["closed"], [])

    def test_unchanged_seen_job_is_in_no_list(self):
        out = self.diff([job()], {"ashby:acme:1": entry()})
        self.assertEqual(out, {"new": [], "changed": [], "saved_open": [], "applied_open": [], "closed": []})

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

    def test_dismissed_and_already_closed_never_reported_closed(self):
        seen = {"ashby:acme:1": entry(status="dismissed"), "ashby:acme:2": entry(closed_at="2026-10-10T00:00:00Z")}
        self.assertEqual(self.diff([], seen)["closed"], [])

    def test_match_by_variant_key(self):
        seen = {"ashby:acme:7": entry(job("ashby:acme:1", more=["ashby:acme:7"]))}
        out = self.diff([job("ashby:acme:1", more=["ashby:acme:7"])], seen)
        self.assertEqual(out["new"] + out["closed"], [])

    def test_alias_survives_primary_variant_closing(self):
        first = job("ashby:acme:1", more=["ashby:acme:2"])
        seen = {"ashby:acme:1": entry(first, status="saved", aliases=["ashby:acme:2"])}
        now = job("ashby:acme:2")  # primary posting closed; the other variant is the row now
        now["locations"] = first["locations"]
        out = self.diff([now], seen)
        self.assertEqual(out["new"] + out["closed"] + out["changed"], [])
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

    def test_marked_before_record_is_not_changed(self):
        seen = {"ashby:acme:1": dict(entry(status="saved"), sig=None)}  # mark() creates entries with no sig
        self.assertEqual(state.job_state(job(), seen), "saved")
        self.assertEqual(state.diff([job()], {"ashby:acme"}, seen)["changed"], [])


class RecordTest(HomeCase):
    def test_inserts_shown_rows_only(self):
        jobs = [job("ashby:acme:1", more=["ashby:acme:5"]), job("ashby:acme:2")]
        run = self.make_run(jobs, [{"key": "ashby:acme:5", "show": True}, {"key": "ashby:acme:2", "show": False}])
        counts = state.record(run, now=NOW)
        seen = state.load_seen()
        self.assertEqual(list(seen), ["ashby:acme:1"])
        e = seen["ashby:acme:1"]
        self.assertEqual((e["status"], e["first_seen"], e["last_seen"]), ("seen", state.now_iso(NOW), state.now_iso(NOW)))
        self.assertEqual(e["sig"], state.job_sig(jobs[0]))
        self.assertEqual(e["aliases"], ["ashby:acme:5"])
        self.assertIsNone(e["closed_at"])
        self.assertEqual(counts["inserted"], 1)
        self.assertEqual(counts["updated"], 0)

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

    def test_missing_results_raises(self):
        run = state.new_run(now=NOW)
        with self.assertRaises(FileNotFoundError):
            state.record(run, now=NOW)


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
        self.assertEqual(code, 0)
        self.assertEqual(out["counts"], {"new": 1, "changed": 0, "saved_open": 0, "applied_open": 0, "closed": 1})
        self.assertEqual(out["new"], ["ashby:acme:1"])
        code, out = self.cli(["seen", "record"])
        self.assertEqual(code, 0)
        self.assertEqual(out["inserted"], 1)
        code, out = self.cli(["seen", "mark", "ashby:acme:1", "saved", "--reason", "great team"])
        self.assertEqual((code, out["status"]), (0, "saved"))
        code, out = self.cli(["seen", "show"])
        self.assertEqual(code, 0)
        self.assertEqual(out["counts"], {"seen": 1, "saved": 1})
        self.assertEqual(out["saved"], [{"key": "ashby:acme:1", "title": "Senior Frontend Engineer", "company": "Acme",
                                         "closed": False}])
        self.assertEqual(out["applied"], [])

    def test_mark_bad_status_exits_1(self):
        code, out = self.cli(["seen", "mark", "ashby:acme:1", "loved"])
        self.assertEqual(code, 1)
        self.assertIn("error", out)
        self.assertFalse(state.seen_path().exists())

    def test_show_empty(self):
        code, out = self.cli(["seen", "show"])
        self.assertEqual((code, out["counts"], out["saved"]), (0, {}, []))


if __name__ == "__main__":
    unittest.main()
