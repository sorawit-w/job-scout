import unittest
import normalize

from normalize import classify, collapse_variants, company_norm, html_to_text, title_stem


class HtmlToTextTest(unittest.TestCase):
    def test_double_escaped_greenhouse(self):
        self.assertEqual(html_to_text("&lt;p&gt;Hi&amp;amp;bye&lt;/p&gt;"), "Hi&bye")

    def test_list_items_get_bullets(self):
        self.assertEqual(
            html_to_text("<p>You will:</p><ul><li>Build   things</li><li>Ship</li></ul>"),
            "You will:\n\n- Build things\n- Ship",
        )

    def test_br_and_blank_lines(self):
        self.assertEqual(html_to_text("a<br>b<br/><br><br><br>c"), "a\nb\n\nc")

    def test_headings_and_divs(self):
        self.assertEqual(html_to_text("<h2>About</h2><div>We  build.</div>"), "About\n\nWe build.")

    def test_none_and_plain(self):
        self.assertEqual(html_to_text(None), "")
        self.assertEqual(html_to_text("  plain text  "), "plain text")


class TitleStemTest(unittest.TestCase):
    def test_strips_place_suffix(self):
        self.assertEqual(title_stem("Design Engineer - Americas"), "design engineer")
        self.assertEqual(title_stem("Design Engineer - Canada"), "design engineer")
        self.assertEqual(title_stem("Design Engineer - EU"), "design engineer")
        self.assertEqual(title_stem("Design Engineer – UK"), "design engineer")
        self.assertEqual(title_stem("Staff Design Engineer - Americas"), "staff design engineer")

    def test_strips_parenthesized_remote(self):
        self.assertEqual(title_stem("Software Engineer (Remote, US)"), "software engineer")
        self.assertEqual(title_stem("Software Engineer, Remote"), "software engineer")
        self.assertEqual(title_stem("Software Engineer (London)"), "software engineer")

    def test_keeps_non_place_suffix(self):
        self.assertEqual(
            title_stem("Senior SWE, Backend (Product Engineering)"),
            "senior swe, backend (product engineering)",
        )
        self.assertEqual(
            title_stem("Data Center Design Engineer, Electrical"),
            "data center design engineer, electrical",
        )
        self.assertEqual(title_stem("RTL Design Engineer"), "rtl design engineer")

    def test_whitespace(self):
        self.assertEqual(title_stem("  Senior   Engineer "), "senior engineer")


class CompanyNormTest(unittest.TestCase):
    def test_suffixes_and_punctuation(self):
        self.assertEqual(company_norm("Harvey, Inc."), "harvey")
        self.assertEqual(company_norm("Acme  Corp"), "acme")
        self.assertEqual(company_norm("Foo GmbH"), "foo")
        self.assertEqual(company_norm("Bar LLC"), "bar")
        self.assertEqual(company_norm("Scale AI"), "scale ai")


def job(company, title, loc, date, job_id, remote_flag=None):
    c = classify(loc, remote_flag=remote_flag)
    return {
        "key": "ashby:%s:%s" % (company.lower(), job_id),
        "company": company,
        "title": title,
        "url": "https://jobs.example/%s" % job_id,
        "locations": c["locations"],
        "countries": c["countries"],
        "remote": c["remote"],
        "remote_scope": c["remote_scope"],
        "workplace": c["workplace"],
        "first_published": date,
        "comp": None,
        "job_id": job_id,
    }


class CollapseVariantsTest(unittest.TestCase):
    def ashby_four(self):
        return [
            job("Acme", "Design Engineer - Americas", "Remote - US", "2026-06-12", "a1"),
            job("Acme", "Design Engineer - Canada", "Canada", "2026-06-12", "a2", remote_flag=True),
            job("Acme", "Design Engineer - EU", "Portugal", "2026-06-12", "a3", remote_flag=True),
            job("Acme", "Design Engineer - UK", "United Kingdom", "2026-06-12", "a4", remote_flag=True),
        ]

    def test_four_regional_variants_collapse(self):
        rows = collapse_variants(self.ashby_four())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["job_id"], "a1")  # tie on date -> input order
        self.assertEqual(row["title"], "Design Engineer - Americas")
        self.assertEqual(row["countries"], ["CA", "GB", "PT", "US"])
        self.assertEqual(row["locations"], ["Remote - US", "Canada", "Portugal", "United Kingdom"])
        self.assertIs(row["remote"], True)
        self.assertEqual(row["remote_scope"], ["CA", "GB", "PT", "US"])
        self.assertEqual([v["job_id"] for v in row["variants"]], ["a1", "a2", "a3", "a4"])
        self.assertEqual(
            sorted(row["variants"][0]),
            ["comp", "countries", "first_published", "job_id", "key", "locations", "remote",
             "remote_scope", "title", "url", "workplace"],
        )

    def test_variant_keeps_its_own_pay_and_scope(self):
        jobs = self.ashby_four()
        jobs[0]["comp"] = {"min": 150000, "max": 200000, "currency": "USD", "interval": "year", "source": "ats_field"}
        jobs[2]["comp"] = {"min": 70000, "max": 90000, "currency": "EUR", "interval": "year", "source": "ats_field"}
        v = collapse_variants(jobs)[0]["variants"]
        self.assertEqual(v[0]["comp"]["currency"], "USD")
        self.assertEqual(v[0]["remote_scope"], ["US"])
        self.assertEqual(v[0]["countries"], ["US"])
        self.assertIs(v[0]["remote"], True)
        self.assertEqual(v[0]["workplace"], "remote")
        self.assertEqual(v[2]["comp"]["currency"], "EUR")
        self.assertEqual(v[2]["remote_scope"], ["PT"])
        self.assertIsNone(v[1]["comp"])

    def test_staff_title_is_a_separate_role(self):
        jobs = self.ashby_four() + [
            job("Acme", "Staff Design Engineer - Americas", "Remote - US", "2026-06-12", "s1")
        ]
        rows = collapse_variants(jobs)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["job_id"], "s1")
        self.assertEqual(len(rows[1]["variants"]), 1)

    def test_harvey_primary_is_earliest(self):
        jobs = [
            job("Harvey", "Senior Software Engineer, Frontend", "New York, NY", "2026-06-24", "h2"),
            job("Harvey", "Senior Software Engineer, Frontend", "San Francisco, CA", "2024-03-08", "h1"),
        ]
        rows = collapse_variants(jobs)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["job_id"], "h1")
        self.assertEqual(row["url"], "https://jobs.example/h1")
        self.assertEqual(row["first_published"], "2024-03-08")
        self.assertEqual([v["job_id"] for v in row["variants"]], ["h1", "h2"])
        self.assertEqual(row["locations"], ["San Francisco, CA", "New York, NY"])  # primary first
        self.assertIsNone(row["remote"])
        self.assertIsNone(row["remote_scope"])

    def test_none_date_sorts_last(self):
        jobs = [
            job("Harvey", "Engineer", "Berlin", None, "n1"),
            job("Harvey", "Engineer", "Paris", "2025-01-01", "n2"),
        ]
        row = collapse_variants(jobs)[0]
        self.assertEqual(row["job_id"], "n2")
        self.assertEqual(row["first_published"], "2025-01-01")

    def test_remote_all_false(self):
        a = job("Acme", "Engineer", "Berlin", "2025-01-01", "f1")
        b = job("Acme", "Engineer", "Paris", "2025-01-02", "f2")
        a["remote"] = b["remote"] = False
        self.assertIs(collapse_variants([a, b])[0]["remote"], False)

    def test_same_title_different_companies(self):
        jobs = [
            job("Harvey", "Software Engineer", "London", "2025-01-01", "x1"),
            job("Acme", "Software Engineer", "London", "2025-01-01", "x2"),
        ]
        rows = collapse_variants(jobs)
        self.assertEqual([r["job_id"] for r in rows], ["x1", "x2"])

    def test_single_job_has_one_variant(self):
        rows = collapse_variants([job("Acme", "Engineer", "Berlin", "2025-01-01", "o1")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["variants"]), 1)
        self.assertEqual(rows[0]["variants"][0]["job_id"], "o1")

    def test_input_not_mutated(self):
        jobs = self.ashby_four()
        collapse_variants(jobs)
        self.assertNotIn("variants", jobs[0])
        self.assertEqual(jobs[0]["countries"], ["US"])


class QaFixesCollapseTest(unittest.TestCase):
    def _job(self, title, dept, date="2026-01-01", loc="New York, NY", remote=False, workplace="onsite", n=[0]):
        n[0] += 1
        return {"key": "g:x:%d" % n[0], "job_id": str(n[0]), "company": "Acme", "title": title, "department": dept,
                "url": "u", "locations": [loc], "countries": ["US"], "remote": remote,
                "remote_scope": ["US"] if remote else None, "workplace": workplace, "first_published": date, "comp": None}

    def test_same_title_in_different_departments_stays_separate(self):
        rows = normalize.collapse_variants([self._job("Software Engineer", "Payments"), self._job("Software Engineer", "Infra")])
        self.assertEqual(len(rows), 2)

    def test_same_department_regional_variants_still_merge(self):
        rows = normalize.collapse_variants([self._job("Engineer - Americas", "Eng"), self._job("Engineer - EU", "Eng")])
        self.assertEqual(len(rows), 1)

    def test_merged_remote_row_reports_remote_workplace(self):
        rows = normalize.collapse_variants([self._job("PM - US", "Product", date="2026-01-01"),
                                            self._job("PM - Remote", "Product", date="2026-02-01", loc="Remote", remote=True, workplace="remote")])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["remote"])
        self.assertEqual(rows[0]["workplace"], "remote")

    def test_more_region_words_are_stripped_from_titles(self):
        for suffix in ("LATAM", "ANZ", "DACH", "Nordics"):
            self.assertEqual(normalize.title_stem("Design Engineer - " + suffix), "design engineer")

if __name__ == "__main__":
    unittest.main()
