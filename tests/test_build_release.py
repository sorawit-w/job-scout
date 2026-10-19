import importlib.util
import os
import tempfile
import unittest
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("build_release", os.path.join(_ROOT, "scripts", "build_release.py"))
build_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_release)

SKILL = os.path.join(_ROOT, "skills", "job-scout")


class FrontmatterTest(unittest.TestCase):
    def test_keeps_only_the_standard_keys_and_the_body(self):
        text = ("---\nname: x\ndescription: >-\n  Finds jobs.\n  Triggers when.\ninstructions: |\n  Load when.\n"
                "tags: [a, b]\nmetadata:\n  tier: draft\n---\n\n# Body\n")
        out = build_release.claude_ai_frontmatter(text)
        self.assertEqual(out, "---\nname: x\ndescription: >-\n  Finds jobs.\n  Triggers when.\nmetadata:\n"
                              "  tier: draft\n---\n\n# Body\n")

    def test_no_frontmatter_is_an_error(self):
        with self.assertRaises(ValueError):
            build_release.claude_ai_frontmatter("# no frontmatter\n")


class BuildTest(unittest.TestCase):
    def setUp(self):
        stray = os.path.join(SKILL, "scripts", "__pycache__")
        os.makedirs(stray, exist_ok=True)  # a stray cache must never ship
        self.out = tempfile.mkdtemp()
        self.path = build_release.build(self.out)
        with zipfile.ZipFile(self.path) as z:
            self.names = z.namelist()
            self.skill_md = z.read("job-scout/SKILL.md").decode("utf-8")

    def test_zip_name_and_root(self):
        with open(os.path.join(SKILL, "VERSION"), encoding="utf-8") as f:
            version = f.read().strip()
        self.assertEqual(os.path.basename(self.path), "job-scout-%s.zip" % version)
        self.assertTrue(all(n.startswith("job-scout/") for n in self.names))
        for need in ("job-scout/SKILL.md", "job-scout/scripts/probe.py", "job-scout/data/companies.csv",
                     "job-scout/references/rubric.md", "job-scout/LICENSE", "job-scout/NOTICE"):
            self.assertIn(need, self.names)

    def test_no_evals_caches_or_os_files(self):
        bad = [n for n in self.names if "/evals/" in n or "__pycache__" in n or n.endswith((".pyc", ".DS_Store"))]
        self.assertEqual(bad, [])

    def test_skill_md_has_claude_ai_frontmatter(self):
        head = self.skill_md.split("---", 2)[1]
        self.assertIn("name: job-scout", head)
        self.assertIn("description:", head)
        self.assertNotIn("instructions:", head)
        self.assertNotIn("tags:", head)
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            self.assertEqual(self.skill_md.split("---", 2)[2], f.read().split("---", 2)[2])  # body unchanged
