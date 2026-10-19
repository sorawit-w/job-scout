import importlib.util
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("record_fixtures", os.path.join(_ROOT, "scripts", "record_fixtures.py"))
record_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(record_fixtures)
FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "http")


class RecordFixturesTest(unittest.TestCase):
    def test_every_committed_fixture_is_re_recorded_by_default(self):
        committed = set()
        for name in os.listdir(FIXTURES):
            if name.endswith(".json"):
                with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
                    committed.add(json.load(f)["url"])
        self.assertEqual(committed - set(record_fixtures.urls()), set())

    def test_trim_skips_a_fixture_that_was_never_written(self):
        record_fixtures.trim(os.path.join(tempfile.mkdtemp(), "missing.json"))  # must not raise

    def test_trim_cuts_a_smartrecruiters_page(self):
        path = os.path.join(tempfile.mkdtemp(), "sr.json")
        body = {"offset": 0, "limit": 100, "totalFound": 5, "content": [{"id": str(i)} for i in range(5)]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"url": "u", "status": 200, "body": json.dumps(body)}, f)
        record_fixtures.trim(path)
        with open(path, encoding="utf-8") as f:
            fx = json.load(f)
        self.assertTrue(fx["trimmed"])
        self.assertEqual([j["id"] for j in json.loads(fx["body"])["content"]], ["0", "1", "2"])


if __name__ == "__main__":
    unittest.main()
