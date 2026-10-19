import unittest

from normalize import classify, place_codes, split_locations


class SplitLocationsTest(unittest.TestCase):
    def test_pipe_list(self):
        self.assertEqual(
            split_locations("Remote | United States | Poland | United Kingdom"),
            ["Remote", "United States", "Poland", "United Kingdom"],
        )

    def test_semicolon(self):
        self.assertEqual(split_locations("San Francisco; London"), ["San Francisco", "London"])

    def test_slash_and_dot(self):
        self.assertEqual(split_locations("Berlin / Paris · Madrid"), ["Berlin", "Paris", "Madrid"])

    def test_or_between_places(self):
        self.assertEqual(split_locations("Toronto or New York"), ["Toronto", "New York"])

    def test_or_kept_when_a_side_is_not_a_place(self):
        self.assertEqual(split_locations("Remote - Canada or US"), ["Remote - Canada or US"])

    def test_dedupe_and_empties(self):
        self.assertEqual(split_locations("London | | London ;"), ["London"])

    def test_none_and_empty(self):
        self.assertEqual(split_locations(None), [])
        self.assertEqual(split_locations(""), [])


class PlaceCodesTest(unittest.TestCase):
    def check(self, loc, expected):
        self.assertEqual(place_codes(loc), expected, loc)

    def test_countries_and_aliases(self):
        self.check("United States", ["US"])
        self.check("USA", ["US"])
        self.check("U.S.", ["US"])
        self.check("UK", ["GB"])
        self.check("England", ["GB"])
        self.check("Poland", ["PL"])

    def test_jerusalem_is_not_usa(self):
        self.check("Jerusalem, Israel", ["IL"])
        self.check("Jerusalem", ["IL"])

    def test_cities_and_states(self):
        self.check("New York, NY", ["US"])
        self.check("San Francisco", ["US"])
        self.check("Austin, TX", ["US"])
        self.check("Indiana", ["US"])
        self.check("São Paulo", ["BR"])

    def test_georgia(self):
        self.check("Georgia", [])
        self.check("Georgia, USA", ["US"])
        self.check("Atlanta, Georgia", ["US"])
        self.check("Tbilisi, Georgia", ["GE"])

    def test_london(self):
        self.check("London", ["GB"])
        self.check("London, UK", ["GB"])
        self.check("London, ON", ["CA"])
        self.check("London, Ontario", ["CA"])

    def test_ca_after_comma(self):
        self.check("Palo Alto, CA", ["US"])
        self.check("Remote, CA", ["US"])
        self.check("Remote, CA, Canada", ["CA"])

    def test_state_codes_need_a_comma(self):
        self.check("Remote, IN", ["US"])
        self.check("Remote IN office", [])
        self.check("Or anywhere ME", ["ANY"])

    def test_remote_with_two_countries(self):
        self.check("Remote - Canada or US", ["CA", "US"])

    def test_regions(self):
        self.check("Americas", ["AMER"])
        self.check("North America", ["AMER"])
        self.check("Europe", ["EU"])
        self.check("EMEA", ["EMEA"])
        self.check("Asia Pacific", ["APAC"])
        self.check("Anywhere", ["ANY"])

    def test_all_caps(self):
        self.check("REMOTE - CANADA", ["CA"])
        self.check("SAN FRANCISCO, CA", ["US"])

    def test_bare_remote(self):
        self.check("Remote", [])
        self.check("", [])


class ClassifyTest(unittest.TestCase):
    def test_jerusalem_countries(self):
        self.assertEqual(classify("Jerusalem, Israel")["countries"], ["IL"])

    def test_multi_location_remote(self):
        r = classify("Remote | United States | Poland | United Kingdom")
        self.assertEqual(r["locations"], ["Remote", "United States", "Poland", "United Kingdom"])
        self.assertTrue(r["remote"])
        self.assertEqual(r["remote_scope"], ["GB", "PL", "US"])
        self.assertEqual(r["countries"], ["GB", "PL", "US"])
        self.assertEqual(r["workplace"], "remote")

    def test_remote_canada_or_us(self):
        r = classify("Remote - Canada or US")
        self.assertTrue(r["remote"])
        self.assertEqual(r["remote_scope"], ["CA", "US"])

    def test_remote_us(self):
        self.assertEqual(classify("Remote - US")["remote_scope"], ["US"])

    def test_two_cities(self):
        r = classify("San Francisco; London")
        self.assertEqual(r["countries"], ["GB", "US"])
        self.assertIsNone(r["remote"])
        self.assertIsNone(r["remote_scope"])
        self.assertIsNone(r["workplace"])

    def test_region_only(self):
        r = classify("Americas")
        self.assertEqual(r["countries"], [])
        self.assertIsNone(r["remote"])

    def test_remote_americas(self):
        r = classify("Remote (Americas)")
        self.assertTrue(r["remote"])
        self.assertEqual(r["remote_scope"], ["AMER"])

    def test_anywhere(self):
        r = classify("Anywhere")
        self.assertTrue(r["remote"])
        self.assertEqual(r["remote_scope"], ["ANY"])

    def test_bare_remote(self):
        r = classify("Remote")
        self.assertTrue(r["remote"])
        self.assertIsNone(r["remote_scope"])

    def test_remote_flag_uses_locations_as_scope(self):
        r = classify(["Toronto"], remote_flag=True)
        self.assertTrue(r["remote"])
        self.assertEqual(r["remote_scope"], ["CA"])
        self.assertEqual(r["countries"], ["CA"])

    def test_remote_indiana(self):
        self.assertEqual(classify("Remote, IN")["remote_scope"], ["US"])

    def test_workplace_hint_hybrid(self):
        r = classify("New York, NY", workplace_hint="Hybrid")
        self.assertEqual(r["workplace"], "hybrid")
        self.assertEqual(r["countries"], ["US"])

    def test_hybrid_in_location(self):
        r = classify("Austin, TX (Hybrid)")
        self.assertEqual(r["workplace"], "hybrid")
        self.assertEqual(r["countries"], ["US"])

    def test_onsite_hint(self):
        for hint in ("OnSite", "On-site", "in_office", "In Office"):
            r = classify("Berlin", workplace_hint=hint)
            self.assertIs(r["remote"], False, hint)
            self.assertEqual(r["workplace"], "onsite", hint)

    def test_remote_hint(self):
        r = classify("Remote - US", workplace_hint="Remote")
        self.assertEqual(r["workplace"], "remote")
        self.assertTrue(r["remote"])

    def test_list_input_is_split(self):
        r = classify(["Berlin | Paris", "Lisbon"])
        self.assertEqual(r["locations"], ["Berlin", "Paris", "Lisbon"])
        self.assertEqual(r["countries"], ["DE", "FR", "PT"])

    def test_empty(self):
        r = classify(None)
        self.assertEqual(r["locations"], [])
        self.assertEqual(r["countries"], [])
        self.assertIsNone(r["remote"])


if __name__ == "__main__":
    unittest.main()
