#!/usr/bin/env python3
"""Plain text from a .docx resume, using only the standard library.

Usage:
  python3 scripts/docx_text.py resume.docx      # prints the text; exit 1 if unreadable

Claude Code and Codex cannot read .docx files directly; PDF, Markdown, HTML and pasted
text the agent reads itself.

What it does NOT do: no tables-as-grids, headers/footers, images, or tracked changes —
just the body paragraphs in order, which is what a resume's content needs.
"""
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract(path):
    """Body text, one line per paragraph. ValueError if the file is not a readable .docx."""
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        raise ValueError("cannot read %s as a .docx (%s)" % (path, e))
    lines = []
    for para in root.iter(W + "p"):
        parts = []
        for node in para.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "tab":
                parts.append("\t")
            elif node.tag in (W + "br", W + "cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines).strip()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: docx_text.py FILE.docx", file=sys.stderr)
        return 2
    try:
        print(extract(argv[0]))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
