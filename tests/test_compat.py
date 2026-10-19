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
