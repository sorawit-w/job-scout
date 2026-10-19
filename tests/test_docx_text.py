import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

import docx_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(paragraphs, path=None):
    path = path or os.path.join(tempfile.mkdtemp(), "resume.docx")
    body = "".join(
        "<w:p>%s</w:p>" % "".join(
            '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % run if run != "\t" else "<w:r><w:tab/></w:r>"
            for run in runs)
        for runs in paragraphs)
    xml = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s"><w:body>%s</w:body></w:document>' % (W, body)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return path


class DocxTextTest(unittest.TestCase):
    def test_paragraphs_and_runs(self):
        path = make_docx([["Jane ", "Doe"], ["Senior Frontend Engineer"], ["React", "\t", "TypeScript"], ["Noïa Labs — 2021–2024"]])
        self.assertEqual(docx_text.extract(path), "Jane Doe\nSenior Frontend Engineer\nReact\tTypeScript\nNoïa Labs — 2021–2024")

    def test_not_a_docx_raises_value_error(self):
        path = os.path.join(tempfile.mkdtemp(), "x.docx")
        with open(path, "w") as f:
            f.write("plain text")
        with self.assertRaises(ValueError):
            docx_text.extract(path)

    def test_cli_prints_text_and_fails_cleanly(self):
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "job-scout", "scripts", "docx_text.py")
        ok = subprocess.run([sys.executable, script, make_docx([["Hello"]])], capture_output=True, text=True)
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "Hello"))
        bad = subprocess.run([sys.executable, script, "/nonexistent.docx"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("cannot read", bad.stderr)


if __name__ == "__main__":
    unittest.main()
