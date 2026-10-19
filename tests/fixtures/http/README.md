# Recorded HTTP fixtures

Real responses from the Greenhouse, Ashby, Lever and SmartRecruiters public job-board APIs, recorded on
2026-10-19 by `scripts/record_fixtures.py` (net.py record mode). Each file is named
`sha1(url)[:16].json` and holds `{"url", "status", "body"}`. Tests and evals replay them
with `JOB_SCOUT_REPLAY_DIR=tests/fixtures/http` so nothing touches the network.

- Board lists longer than 3 jobs are trimmed to their first 3 (`"trimmed": true`; for
  SmartRecruiters `totalFound` keeps the untrimmed count).
- Covered: health-check URLs (404 = reachable), small live boards (greenhouse:airtable,
  ashby:attention, ashby:clerk, lever:airslate), Ashby pay (ashby:ramp), Greenhouse single
  jobs with and without pay (figma, airtable), Lever single job + unknown job (404), empty
  boards (greenhouse:webflow, ashby:raycast → 200 with no jobs), unknown boards (404 on all
  three), the lever:jobgether aggregator, and a closed Greenhouse job (vercel/1 → 404).
- SmartRecruiters: two small companies (BryceTech, GalileoLearning — first page, trimmed to 3
  postings), an unknown company (200 with `totalFound: 0`; it never 404s), one open posting
  detail with description and pay (BryceTech/744000154771568), and a missing posting
  (BryceTech/1 → 404).

Re-record with `python3 scripts/record_fixtures.py [extra URLs…]`; job ids change over time,
so tests key on what a fixture contains, not on today's ids.
