# Developer TODO

Actions only the maintainer can take. Remove an entry once it is done.

## Developer Action Required

### 1. Install smoke tests on the four surfaces
Each one: install, then say "find me roles that fit" with any resume. Expected: the search brief
appears and nothing is searched until you confirm.
- **Claude Code:** `/plugin marketplace add sorawit-w/job-scout` then `/plugin install job-scout@job-scout`.
- **Codex:** `codex plugin marketplace add sorawit-w/job-scout`, then `/plugins` in Codex to
  install it, then a new session started with `-c sandbox_workspace_write.network_access=true`.
- **npx:** `npx skills add sorawit-w/job-scout`.
- **claude.ai:** download `job-scout-0.1.0.zip` from https://github.com/sorawit-w/job-scout/releases/tag/v0.1.0 and upload it under Settings → Capabilities → Skills (code
  execution on, job-board hosts allowed). This also answers the old G8 question: the zip's
  SKILL.md keeps only `name`, `description` and `metadata`, so it should be accepted. If it is
  rejected, paste the exact error text in a session.
- **Already checked offline:** the built zip unpacks to `job-scout/`, has no evals, and its
  scripts run on Python 3.9 against a replay world (health, probe, filter, profile).

- **Optional while you are there:** turn on branch protection for `main` (Settings → Branches), so the weekly seed-check workflow can only open PRs.
