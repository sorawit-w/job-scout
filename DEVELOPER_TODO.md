# Developer TODO

Actions only the maintainer can take. Remove an entry once it is done.

## Developer Action Required

### 1. Make the repository public
- **What:** GitHub → `sorawit-w/job-scout` → Settings → General → Danger Zone → Change visibility → Public.
- **Why:** the install commands, the User-Agent link and the README badges point at this repo.
  Going public is your call; nothing was published for you.
- **Before you do it (optional):** turn on branch protection for `main` (Settings → Branches), so
  the weekly seed-check workflow can only open PRs.

### 2. Publish the 0.1.0 release with the zip
- **How (from the repo root, on `main` after the M6 PR is merged):**
  ```bash
  python3 scripts/build_release.py
  gh release create v0.1.0 dist/job-scout-0.1.0.zip --title "job-scout 0.1.0" --notes-file CHANGELOG.md
  ```
  (Or trim the notes to the 0.1.0 section first.)
- **Why:** claude.ai users install from the zip on the Releases page.

### 3. Install smoke tests on the four surfaces (after steps 1–2)
Each one: install, then say "find me roles that fit" with any resume. Expected: the search brief
appears and nothing is searched until you confirm.
- **Claude Code:** `/plugin marketplace add sorawit-w/job-scout` then `/plugin install job-scout@job-scout`.
- **Codex (0.133.0+):** the same two commands, `/reload-plugins`, and start Codex with
  `-c sandbox_workspace_write.network_access=true`.
- **npx:** `npx skills add sorawit-w/job-scout`.
- **claude.ai:** upload `job-scout-0.1.0.zip` under Settings → Capabilities → Skills (code
  execution on, job-board hosts allowed). This also answers the old G8 question: the zip's
  SKILL.md keeps only `name`, `description` and `metadata`, so it should be accepted. If it is
  rejected, paste the exact error text in a session.
- **Already checked offline:** the built zip unpacks to `job-scout/`, has no evals, and its
  scripts run on Python 3.9 against a replay world (health, probe, filter, profile).

### 4. Add job-scout to the agent-skills shelf (after step 1)
- **What:** an external entry in `sorawit-w/agent-skills` README, like kerby's. Suggested place:
  "Calibration & personal voice", next to ghostwriter (they chain: find the role, then write the
  message). Suggested text:
  ```
  [`job-scout`](https://github.com/sorawit-w/job-scout) *(external)* — open roles that fit your resume, read straight from employer job boards, with every fit reason quoted from the posting.

  *Try:*
    - "Here's my CV — what should I apply to?"
    - "Anything new since last week?"
  ```
