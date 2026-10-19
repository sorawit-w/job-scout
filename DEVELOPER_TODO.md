# Developer TODO

Actions only the maintainer can take. Remove an entry once it is done.

## Developer Action Required

### claude.ai: check the skill uploads with its full frontmatter (M2 task G8)
- **What:** Upload the job-scout skill to claude.ai and say whether it is accepted.
- **Why:** SKILL.md uses the agent-skills house frontmatter (`instructions`, `tags`, `metadata.tier`). If claude.ai rejects extra keys, the M6 release script must strip them from the claude.ai zip only.
- **How:**
  1. From the repo root: `cd skills && zip -r /tmp/job-scout-test.zip job-scout -x '*/__pycache__/*' -x 'job-scout/evals/*' && cd ..`
  2. claude.ai → Settings → Capabilities → Skills → upload `/tmp/job-scout-test.zip`.
  3. Start a chat and say "find me roles that fit" with any resume. Expected today: the search brief and questions appear (the search step itself arrives in M3).
- **Where to put the result:** Reply in the session: "accepted" or the exact error text.
- **Blocked tasks:** M6 L6 (release zip) uses the answer; nothing earlier is blocked.
