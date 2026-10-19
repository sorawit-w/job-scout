# companies.py fixtures

Recorded by hand on 2026-10-19 with `JOB_SCOUT_RECORD_DIR` (not by `scripts/record_fixtures.py`,
which only manages the top-level fixtures), then list responses trimmed to 3 jobs.

- `ashby:snyk` — a live board that is not in the seed (the guessed-hit case); `greenhouse:snyk` is a real 404.
- `ashby:linear` — for the `--refresh` case.
- "Zzqx" — nine real 404s (three guesses × three hiring tools), plus `smartrecruiters:Zzqx` and
  `smartrecruiters:Zzqx1`, which answer a real **200 with zero postings** (SmartRecruiters' answer for
  an unknown company), so the unknown-company case is honest.
- "International Spy Museum" — `smartrecruiters:InternationalSpyMuseum`, a live board (3 postings, so
  not trimmed) that is not in the seed: the SmartRecruiters guessed-hit case. Its twelve
  Greenhouse/Ashby/Lever guesses (four slugs × three hiring tools) are real 404s.
- `seed.csv` — not a recording: seven rows copied from `skills/job-scout/data/companies.csv`
  (Linear, Notion, Brex, Figma, Vercel live; City of Boulder, an unchecked Workday row).
  `tests/test_companies.py` uses it as the seed, so imports into the real seed never change the tests.

The Workday `--board` and unchecked-seed tests replay `tests/fixtures/http/workday/` (City of Boulder
blank search, the 422 and 404 boards); nothing Workday is recorded here.

Re-record with the same names if a board changes; `tests/test_companies.py` reads them via
`JOB_SCOUT_REPLAY_DIR`.
