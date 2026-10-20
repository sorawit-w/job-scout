# Contributing

Thank you for helping. The most useful contribution is small: **add a company** job-scout
should check.

## Add a company (one CSV row)

1. Find the company's job board. job-scout reads these hiring tools:

   | Hiring tool | The board URL looks like | `ats` | `slug` |
   |---|---|---|---|
   | Greenhouse | `boards.greenhouse.io/figma` | `greenhouse` | `figma` |
   | Ashby | `jobs.ashbyhq.com/linear` | `ashby` | `linear` |
   | Lever | `jobs.lever.co/plaid` | `lever` | `plaid` |
   | SmartRecruiters | `jobs.smartrecruiters.com/BryceTech` | `smartrecruiters` | `BryceTech` (case matters) |
   | Workday | `kaiserpermanente.wd5.myworkdayjobs.com/External` | `workday` | `kaiserpermanente.wd5.External` |

   The skill can also find the row for you: `python3 skills/job-scout/scripts/companies.py add
   "Company Name"` (or `--board <Workday URL>`) prints a suggested row.

2. Add one line to `skills/job-scout/data/companies.csv`. The file is sorted by `ats`, then
   `slug` (ignoring case), so put the line in that place:

   ```
   company,ats,slug,sector,status,jobs,us_share,remote_share,checked_at,source
   Figma,greenhouse,figma,unknown,unchecked,,,,,community
   ```

   Leave `status` as `unchecked` and the numbers empty: the weekly seed check fills them in.
   (That check runs every Monday and opens a PR with the refreshed list. The PR merges itself
   when the tests pass and `scripts/seed_guard.py` finds only routine change; anything unusual
   waits for a maintainer.)
   Use `sector` `unknown` unless you are sure.

3. Open a pull request. CI live-checks every new board, and the check fails if a board does not
   answer with at least one job.

Please don't add job aggregators or staffing marketplaces that list other companies' jobs.
`skills/job-scout/data/denylist.txt` holds the known ones.

## Code changes

- Python 3.9+ standard library only. No dependencies.
- Run the gate before you push:

  ```bash
  python3 -m compileall -q skills scripts tests && python3 scripts/check-skill-compat.py && python3 -m unittest discover -s tests -t .
  ```

- Tests never touch the network. Recorded responses live in `tests/fixtures/http/`.
- A change to `SKILL.md` or `references/` needs an eval run. See
  `skills/job-scout/evals/README.md`.
- Open an issue first for a new hiring tool, so we can agree on how it is searched.

## Reporting a bad result

Open an issue with the role link, what job-scout said, and what was wrong (closed role, wrong
location, a quote that isn't in the posting). Please leave out your resume and personal details.
