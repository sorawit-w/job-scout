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


if __name__ == "__main__":
    unittest.main()
