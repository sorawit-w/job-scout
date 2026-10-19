import types
import unittest

import adapters


class AdapterContractTest(unittest.TestCase):
    def test_contract_names(self):
        self.assertEqual(adapters.CONTRACT, ("fetch_board", "normalize", "fetch_job"))

    def test_registry_is_a_dict(self):
        self.assertIsInstance(adapters.REGISTRY, dict)

    def test_missing_reports_absent_functions(self):
        partial = types.SimpleNamespace(fetch_board=lambda slug: [], normalize="not callable")
        self.assertEqual(adapters.missing(partial), ["normalize", "fetch_job"])

    def test_missing_is_empty_for_a_complete_adapter(self):
        full = types.SimpleNamespace(**{name: (lambda *a: None) for name in adapters.CONTRACT})
        self.assertEqual(adapters.missing(full), [])

    def test_every_registered_adapter_meets_the_contract(self):
        for ats, module in adapters.REGISTRY.items():
            self.assertEqual(adapters.missing(module), [], ats)


if __name__ == "__main__":
    unittest.main()
