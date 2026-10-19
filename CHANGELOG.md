# Changelog

All notable changes to `job-scout` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [0.0.1] — 2026-10-18

**Repo scaffold (M1a).** No runtime behavior yet — this release only sets up the project.

### Added
- `agent-context.yaml`, `CONTEXT.md` (domain glossary), `ROADMAP.md`, and `implementation-plan.yaml` covering M1a–M6.
- The ATS adapter port (`skills/job-scout/scripts/adapters/__init__.py`) with its contract test.
- Plugin manifests for Claude Code and Codex, `skills/job-scout/VERSION`, and `scripts/check-skill-compat.py` (copied from kerby; checks SKILL.md frontmatter and version parity).
- CI on Python 3.9 and 3.13: compile, compat check, unit tests.

### Notes
- The spec is `docs/HANDOFF.md` (rev. 3); M0 results are in `docs/m0/`.
