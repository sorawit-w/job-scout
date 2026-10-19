import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import cite_check

RUN_ID = "20261018T000000Z"
FULL = ("Requirements\n- 5+ years building   React applications\n- You’ll mentor “junior” engineers\n\n"
        "Our culture\nWe like long lunches.\n\nPay\nThe range is $150,000 – $180,000 per year.")
TRIMMED = "Requirements\n- 5+ years building   React applications\n…\nPay\nThe range is $150,000 – $180,000 per year."
JDS = {
    "gh:a:1": {"status": "open", "full": FULL, "trimmed": TRIMMED, "comp": None,
               "checked_at": "2026-10-18T00:00:00Z", "error": None},
    "gh:a:2": {"status": "closed", "full": None, "trimmed": None, "comp": None,
               "checked_at": "2026-10-18T00:00:00Z", "error": None},
}


def make_home():
    home = tempfile.mkdtemp()
    run_dir = os.path.join(home, "runs", RUN_ID)
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "jds.json"), "w", encoding="utf-8") as f:
        json.dump(JDS, f)
    return home


def results(why=(), risk=(), key="gh:a:1"):
    return {"rows": [{"key": key, "gates": {}, "scores": {}, "total": 5,
                      "why": [{"text": t, "quote": q} for t, q in why],
                      "risk": [{"text": t, "quote": q} for t, q in risk]}]}


def run(payload, home=None):
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": home or make_home()}), \
            mock.patch("sys.stdin", stdin), contextlib.redirect_stdout(out):
        code = cite_check.main([])
    return code, json.loads(out.getvalue())


class CiteCheckTest(unittest.TestCase):
    def assertFails(self, payload, reason):
        code, out = run(payload)
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn(reason, out["failed"][0]["why"])
        return out

    def test_exact_quote_passes(self):
        code, out = run(results(why=[("knows React", "years building   React applications")]))
        self.assertEqual((code, out), (0, {"ok": True, "checked": 1, "failed": []}))

    def test_whitespace_curly_quotes_and_dashes_are_normalized(self):
        code, out = run(results(
            why=[("mentoring", "You'll mentor \"junior\" engineers"),
                 ("react", "5+ YEARS building React applications")],
            risk=[("pay range", "$150,000 - $180,000 per year")]))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["checked"], 3)

    def test_paraphrase_fails(self):
        self.assertFails(results(why=[("react", "five years of React experience")]), "not found")

    def test_quote_across_a_trim_join_fails(self):
        joined = TRIMMED.split("…")[0][-20:] + "…" + TRIMMED.split("…")[1][:10]
        self.assertFails(results(why=[("x", joined)]), "not found")
        self.assertFails(results(why=[("x", "React applications Pay The range")]), "not found")

    def test_null_quote_only_for_unknown_labels(self):
        code, out = run(results(risk=[("Pay not listed", None), ("sponsorship not stated", ""),
                                      ("location unclear", None)]))
        self.assertEqual(code, 0, out)
        self.assertFails(results(risk=[("no visa help", None)]), "quote")

    def test_short_quote_fails(self):
        self.assertFails(results(why=[("react", "React")]), "too short")

    def test_closed_or_missing_key_fails(self):
        self.assertFails(results(why=[("x", "years building React applications")], key="gh:a:2"),
                         "no live job description")
        self.assertFails(results(risk=[("pay not listed", None)], key="gh:a:9"), "no live job description")

    def test_row_without_a_live_jd_fails_once_even_with_no_items(self):
        code, out = run(results(key="gh:a:2"))
        self.assertEqual(code, 1)
        self.assertEqual(out["failed"], [{"key": "gh:a:2", "quote": None, "why": "no live job description for this key"}])
        code, out = run(results(why=[("x", "years building React applications"), ("y", "another made up quote")],
                                key="gh:a:9"))
        self.assertEqual(out["failed"], [{"key": "gh:a:9", "quote": None, "why": "no live job description for this key"}])
        self.assertEqual(out["checked"], 2)

    def test_shown_row_needs_a_quoted_reason(self):
        payload = results(risk=[("pay not listed", None)])
        payload["rows"][0]["show"] = True
        self.assertFails(payload, "shown row has no quoted reason")
        payload["rows"][0]["show"] = False
        self.assertEqual(run(payload)[0], 0)

    def test_failure_lists_key_and_quote_and_counts_all(self):
        out = self.assertFails(results(why=[("ok", "years building React applications"), ("bad", "made up text here")]),
                               "not found")
        self.assertEqual(out["checked"], 2)
        self.assertEqual(out["failed"], [{"key": "gh:a:1", "quote": "made up text here",
                                          "why": out["failed"][0]["why"]}])

    def test_bad_json_exits_2(self):
        code, out = run("{not json")
        self.assertEqual(code, 2)
        self.assertFalse(out["ok"])
        code, out = run({"no_rows": []})
        self.assertEqual(code, 2)


class NormalizeTest(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(cite_check.norm("A  “B”\n‘c’ – d — e"), "a \"b\" 'c' - d - e")


if __name__ == "__main__":
    unittest.main()
