# Workday fixtures

Recorded by hand on 2026-10-19 with `JOB_SCOUT_RECORD_DIR` through `adapters/workday.py` (not by
`scripts/record_fixtures.py`, which only manages the top-level fixtures). Search pages are
POSTs: their file name is `net.fixture_key(url, body)` (URL plus the canonical JSON body) and
the file carries a `"post"` field. Detail calls are GETs, named by URL alone. Search pages are
trimmed to their first 3 postings (`"trimmed": true`; `total` keeps the untrimmed count), so
the adapter stops after one short page.

- `sharp.wd1.External` (Sharp HealthCare, hospital system): search `"nurse"`, page 1.
- `sharp.wd1.External`: detail of the first posting on that page (has `startDate`,
  `jobDescription`, `jobRequisitionLocation.country.alpha2Code`; no `remoteType`).
- `sharp.wd1.External`: posting `Clinical-Nurse_JR0000000-1` → real 404 (the closed-job case;
  a truly closed posting was not at hand, and Workday answers a missing one the same way).
- `bouldercolorado.wd1.external` (City of Boulder, public employer): blank search, page 1.
- `zzqxjobscout.wd1.careers` → real **422** (unknown tenant; a board on the wrong `wdN` host
  answers 422 too).
- `sharp.wd1.ZzqxNoSuchSite` → real **404** (known tenant, unknown site).

Re-record with the same boards if a posting disappears; `tests/test_workday.py` reads the
search page first and takes the detail id from it, so only the closed id is hard-coded.
