#!/usr/bin/env python3
"""Build the release zip: dist/job-scout-<VERSION>.zip with job-scout/ at its root.

Usage (from the repo root):
  python3 scripts/build_release.py [--out dist]

The zip is the skill folder (skills/job-scout) plus the repo's LICENSE and NOTICE, without
evals/, __pycache__, *.pyc or .DS_Store. Its SKILL.md keeps only the standard frontmatter keys
(CLAUDE_AI_KEYS), so claude.ai accepts the upload; the repo's SKILL.md is not changed. Files are
written in sorted order with a fixed timestamp, so the same tree gives the same zip.
Prints one line: dist/job-scout-<VERSION>.zip (N files, X KB).
"""
import argparse
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "job-scout")
CLAUDE_AI_KEYS = ("name", "description", "license", "allowed-tools", "metadata")
SKIP_DIRS = {"evals", "__pycache__"}
SKIP_FILES = (".pyc", ".DS_Store")
EXTRA = ("LICENSE", "NOTICE")  # repo-root files the zip carries (NOTICE holds the MIT data notices)
STAMP = (2026, 1, 1, 0, 0, 0)


def claude_ai_frontmatter(text):
    """SKILL.md text with only CLAUDE_AI_KEYS left in its frontmatter; the body is unchanged."""
    lines = text.split("\n")
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("SKILL.md has no --- frontmatter block")
    end = lines.index("---", 1)
    kept, keep = [], False
    for line in lines[1:end]:
        if line and not line[0].isspace():  # a top-level key starts a block
            keep = line.split(":", 1)[0].strip() in CLAUDE_AI_KEYS
        if keep:
            kept.append(line)
    return "\n".join(["---"] + kept + lines[end:])


def files():
    """(path on disk, name in the zip), sorted."""
    out = []
    for d, dirs, names in os.walk(SKILL):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for n in sorted(names):
            if not n.endswith(SKIP_FILES):
                path = os.path.join(d, n)
                out.append((path, "job-scout/" + os.path.relpath(path, SKILL).replace(os.sep, "/")))
    out += [(os.path.join(ROOT, n), "job-scout/" + n) for n in EXTRA]
    return sorted(out, key=lambda p: p[1])


def build(out_dir):
    with open(os.path.join(SKILL, "VERSION"), encoding="utf-8") as f:
        version = f.read().strip()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "job-scout-%s.zip" % version)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in files():
            with open(src, "rb") as f:
                data = f.read()
            if name == "job-scout/SKILL.md":
                data = claude_ai_frontmatter(data.decode("utf-8")).encode("utf-8")
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args(argv)
    path = build(args.out)
    with zipfile.ZipFile(path) as z:
        count = len(z.namelist())
    print("%s (%d files, %d KB)" % (os.path.relpath(path, ROOT), count, os.path.getsize(path) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
