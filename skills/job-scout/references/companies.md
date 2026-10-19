# Adding companies

Read this when the user names companies to always check (SKILL.md Phase 8), e.g. "also check
Linear and Figma". Run `python3 scripts/companies.py add "Linear" "Figma"` (up to 5 names) and
report what it found:

- A **guessed** board (`"from": "guess"`) may belong to a different company with the same
  name. Show its `sample_titles` and ask "is this the right company?"; if not, run
  `python3 scripts/companies.py remove "<name>"`.
- No hits → nothing is saved; say so. If the user knows the company's board address (a
  Greenhouse, Ashby, Lever or SmartRecruiters jobs page), run
  `companies.py add "<name>" --board ats:slug`; for a Workday careers site, pass its URL:
  `--board https://<tenant>.wd5.myworkdayjobs.com/<site>`.
- Exit 4 → the request cap stopped it; what was found is saved — say the rest wasn't checked.
  Exit 3 → the job boards can't be reached (SKILL.md Phase 3).
- If it prints a `suggest_row`, mention that the user can share it with the project so
  everyone gets that company. `companies.py list` shows the saved companies.
