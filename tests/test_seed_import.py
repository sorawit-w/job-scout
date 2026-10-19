import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
import seed_import  # noqa: E402

GH_1 = (
    "pub const T: &[Tenant] = &[\n"
    '    Tenant { ats: Ats::Greenhouse, slug: "Fliff", company: "Fliff", host: "", site: "" },\n'
    '    Tenant { ats: Ats::Greenhouse, slug: "affinity.co", company: "Affinity", host: "", site: "" },\n'
    '    Tenant { ats: Ats::Greenhouse, slug: "affirm", company: "Affirm", host: "", site: "" },\n'
    "];\n"
)
ASHBY_1 = '    Tenant { ats: Ats::Ashby, slug: "noia", company: "Noïa Labs", host: "", site: "" },\n'
LEVER_1 = (
    '    Tenant { ats: Ats::Lever, slug: "jobgether", company: "Jobgether", host: "", site: "" },\n'
    '    Tenant { ats: Ats::Lever, slug: "acme", company: "Acme", host: "", site: "" },\n'
)
SR_1 = (
    '    Tenant { ats: Ats::SmartRecruiters, slug: "BryceTech", company: "BryceTech", host: "", site: "" },\n'
    '    Tenant { ats: Ats::SmartRecruiters, slug: "AECOM2", company: "AECOM", host: "", site: "" },\n'
)
WORKDAY_1 = '    Tenant { ats: Ats::Workday, slug: "bigco", company: "BigCo", host: "x", site: "y" },\n'
SEED49 = (
    "company,ats,slug,status_2026_10_18,open_jobs_2026_10_18,note\n"
    "affirm,greenhouse,affirm,ok,214,\n"
    "vapi,ashby,vapi,ok,23,\n"
)
DENY = "# aggregators\n\nlever:jobgether  # reposts\n"
HEADER = ["company", "ats", "slug", "sector", "status", "jobs", "us_share", "remote_share", "checked_at", "source"]


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ParseTest(unittest.TestCase):
    def test_parse_keeps_slug_case_and_dots(self):
        got = seed_import.parse_tenants(GH_1)
        self.assertEqual(got, [
            ("greenhouse", "Fliff", "Fliff"),
            ("greenhouse", "affinity.co", "Affinity"),
            ("greenhouse", "affirm", "Affirm"),
        ])

    def test_parse_smartrecruiters(self):
        self.assertEqual(seed_import.parse_tenants(SR_1), [
            ("smartrecruiters", "BryceTech", "BryceTech"), ("smartrecruiters", "AECOM2", "AECOM")])

    def test_parse_skips_other_ats(self):
        self.assertEqual(seed_import.parse_tenants(WORKDAY_1), [])

    def test_read_denylist_ignores_comments(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "deny.txt")
        _write(p, DENY)
        self.assertEqual(seed_import.read_denylist(p), {("lever", "jobgether")})


class BuildRowsTest(unittest.TestCase):
    def setUp(self):
        self.tenants = seed_import.parse_tenants(GH_1 + ASHBY_1 + LEVER_1 + GH_1)  # GH_1 twice: dupes
        self.seed = [
            {"company": "affirm", "ats": "greenhouse", "slug": "affirm"},
            {"company": "vapi", "ats": "ashby", "slug": "vapi"},
        ]
        self.rows, self.stats = seed_import.build_rows(self.tenants, self.seed, {("lever", "jobgether")})

    def test_dedupe_overlap_and_denylist(self):
        keys = [(r["ats"], r["slug"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertNotIn(("lever", "jobgether"), keys)
        self.assertEqual(self.stats["denylisted"], 1)
        self.assertEqual(self.stats["seed49"], 2)
        self.assertEqual(self.stats["overlap"], 1)

    def test_seed49_overrides_with_corphunting_name(self):
        affirm = [r for r in self.rows if r["slug"] == "affirm"]
        self.assertEqual(len(affirm), 1)
        self.assertEqual(affirm[0]["source"], "seed49")
        self.assertEqual(affirm[0]["sector"], "fintech")
        self.assertEqual(affirm[0]["company"], "Affirm")
        vapi = [r for r in self.rows if r["slug"] == "vapi"][0]
        self.assertEqual((vapi["company"], vapi["sector"], vapi["source"]), ("vapi", "ai", "seed49"))

    def test_corphunting_defaults(self):
        fliff = [r for r in self.rows if r["slug"] == "Fliff"][0]
        self.assertEqual(fliff["sector"], "unknown")
        self.assertEqual(fliff["source"], "corphunting")
        self.assertEqual(fliff["status"], "unchecked")
        self.assertEqual(fliff["jobs"], "")

    def test_sorted_by_ats_then_slug_lower(self):
        keys = [(r["ats"], r["slug"]) for r in self.rows]
        self.assertEqual(keys, [
            ("ashby", "noia"), ("ashby", "vapi"),
            ("greenhouse", "affinity.co"), ("greenhouse", "affirm"), ("greenhouse", "Fliff"),
            ("lever", "acme"),
        ])

    def test_every_seed49_slug_has_a_sector(self):
        path = os.path.join(_ROOT, "docs", "reference", "companies_seed.csv")
        for row in seed_import.read_seed49(path):
            self.assertIn(row["slug"], seed_import.SEED49_SECTORS)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        src = os.path.join(self.d, "repo", "src", "tenants")
        os.makedirs(src)
        _write(os.path.join(src, "greenhouse_1.rs"), GH_1)
        _write(os.path.join(src, "ashby_1.rs"), ASHBY_1)
        _write(os.path.join(src, "lever_1.rs"), LEVER_1)
        _write(os.path.join(src, "smartrecruiters_1.rs"), SR_1)
        _write(os.path.join(src, "workday_1.rs"), WORKDAY_1.replace("Workday", "Greenhouse"))  # file filter must skip it
        self.seed = os.path.join(self.d, "seed.csv")
        self.deny = os.path.join(self.d, "deny.txt")
        self.out = os.path.join(self.d, "out", "companies.csv")
        os.makedirs(os.path.dirname(self.out))
        _write(self.seed, SEED49)
        _write(self.deny, DENY)

    def _run(self, src):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = seed_import.main(["--src", src, "--seed49", self.seed, "--denylist", self.deny, "--out", self.out])
        return code, buf.getvalue()

    def test_end_to_end_from_repo_root(self):
        code, out = self._run(os.path.join(self.d, "repo"))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "seed-import: 8 boards (greenhouse 3, ashby 2, lever 1, smartrecruiters 2) · "
                                      "seed49 2 (overlapping 1) · denylisted 1 · kept checks 0 · source 92fab36")
        with open(self.out, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], HEADER)
        slugs = [r[2] for r in rows[1:]]
        self.assertNotIn("bigco", slugs)
        self.assertIn("Noïa Labs", [r[0] for r in rows[1:]])
        self.assertEqual(os.listdir(os.path.dirname(self.out)), ["companies.csv"])  # no temp file left

    def test_reimport_keeps_existing_check_results(self):
        self._run(os.path.join(self.d, "repo"))
        with open(self.out, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if r["slug"] == "affirm":
                r.update(status="live", jobs="214", us_share="0.9", remote_share="0.1", checked_at="2026-10-19")
        with open(self.out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows(rows)
        code, out = self._run(os.path.join(self.d, "repo"))
        self.assertEqual(code, 0)
        self.assertIn("kept checks 1", out)
        with open(self.out, encoding="utf-8", newline="") as f:
            got = {r["slug"]: r for r in csv.DictReader(f)}
        self.assertEqual([got["affirm"][k] for k in ("status", "jobs", "us_share", "remote_share", "checked_at")],
                         ["live", "214", "0.9", "0.1", "2026-10-19"])
        self.assertEqual(got["BryceTech"]["status"], "unchecked")

    def test_flat_dir_works(self):
        code, _ = self._run(os.path.join(self.d, "repo", "src", "tenants"))
        self.assertEqual(code, 0)

    def test_empty_source_fails_without_writing(self):
        empty = os.path.join(self.d, "empty")
        os.makedirs(empty)
        with contextlib.redirect_stderr(io.StringIO()):
            code, _ = self._run(empty)
        self.assertNotEqual(code, 0)
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
