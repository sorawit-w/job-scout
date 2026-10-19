# companies.py fixtures

Recorded by hand on 2026-10-19 with `JOB_SCOUT_RECORD_DIR` (not by `scripts/record_fixtures.py`,
which only manages the top-level fixtures), then list responses trimmed to 3 jobs.

- `ashby:snyk` — a live board that is not in the seed (the guessed-hit case); `greenhouse:snyk` is a real 404.
- `ashby:linear` — for the `--refresh` case.
- "Zzqx" — nine real 404s (three guesses × three hiring tools), so the unknown-company case is honest.

Re-record with the same names if a board changes; `tests/test_companies.py` reads them via
`JOB_SCOUT_REPLAY_DIR`.
