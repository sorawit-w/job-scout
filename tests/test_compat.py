import importlib.util
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("check_skill_compat", os.path.join(_ROOT, "scripts", "check-skill-compat.py"))
compat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compat)


def _write(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


class VersionCheckTest(unittest.TestCase):
    def release(self, version="1.2.3", claude=None, entry=None):
        """A repo whose four release places say `version`; claude/entry put one in the Claude manifests."""
        root = tempfile.mkdtemp()
        _write(root, ".codex-plugin/plugin.json", {"name": "x", "version": version})
        _write(root, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n\n## [%s] — 2026-10-20\n" % version)
        _write(root, "README.md", "- **Status:** Current release: `%s`.\n" % version)
        _write(root, "skills/job-scout/VERSION", version + "\n")
        _write(root, ".claude-plugin/plugin.json", dict({"name": "x"}, **({"version": claude} if claude else {})))
        _write(root, ".claude-plugin/marketplace.json",
               {"plugins": [dict({"name": "x"}, **({"version": entry} if entry else {}))]})
        return root

    def test_four_places_agree_and_claude_manifests_have_no_version(self):
        self.assertEqual(compat.check_versions(self.release()), ([], "1.2.3"))

    def test_a_version_in_either_claude_manifest_fails(self):
        for kw, label in (({"claude": "1.2.3"}, ".claude-plugin/plugin.json"),
                          ({"entry": "1.2.3"}, ".claude-plugin/marketplace.json plugins[0]")):
            errors, _ = compat.check_versions(self.release(**kw))
            self.assertEqual(len(errors), 1, kw)
            self.assertTrue(errors[0].startswith(label + " has version '1.2.3': remove it"), errors)

    def test_drift_in_the_four_release_places_still_fails(self):
        root = self.release()
        _write(root, "skills/job-scout/VERSION", "1.2.4\n")
        errors, agreed = compat.check_versions(root)
        self.assertIsNone(agreed)
        self.assertTrue(any(e.startswith("version mismatch across manifests") for e in errors), errors)

    def test_the_repo_itself_passes(self):
        self.assertEqual(compat.check_versions(_ROOT)[0], [])


class DeclaredSkillsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_nothing_declared_and_nothing_present_passes(self):
        _write(self.root, ".claude-plugin/plugin.json", {"name": "x"})
        self.assertEqual(compat.check_declared_skills(self.root), [])

    def test_declared_path_without_skill_md_fails(self):
        _write(self.root, ".claude-plugin/plugin.json", {"skills": ["./skills/job-scout"]})
        errors = compat.check_declared_skills(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("skills/job-scout", errors[0])

    def test_declared_path_with_skill_md_passes(self):
        _write(self.root, ".claude-plugin/plugin.json", {"skills": ["./skills/job-scout"]})
        _write(self.root, "skills/job-scout/SKILL.md", "---\nname: job-scout\n---\n")
        self.assertEqual(compat.check_declared_skills(self.root), [])

    def test_codex_directory_form_with_no_skill_fails(self):
        _write(self.root, ".codex-plugin/plugin.json", {"skills": "./skills/"})
        os.makedirs(os.path.join(self.root, "skills"))
        self.assertEqual(len(compat.check_declared_skills(self.root)), 1)

    def test_marketplace_entry_declaration_is_checked(self):
        _write(self.root, ".claude-plugin/marketplace.json", {"plugins": [{"name": "x", "skills": ["./skills/gone"]}]})
        self.assertEqual(len(compat.check_declared_skills(self.root)), 1)

    def test_present_but_undeclared_skill_fails(self):
        _write(self.root, ".claude-plugin/plugin.json", {"name": "x"})
        _write(self.root, "skills/job-scout/SKILL.md", "---\nname: job-scout\n---\n")
        errors = compat.check_declared_skills(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("not declared", errors[0])


if __name__ == "__main__":
    unittest.main()
