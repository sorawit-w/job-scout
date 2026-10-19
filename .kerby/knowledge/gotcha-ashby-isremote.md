# Ashby isRemote means "not onsite", not remote

Ashby's job-board API sets `isRemote: true` on every job whose `workplaceType` is `Hybrid`
(1,352 of 1,352 hybrid jobs on the 49 eval boards, 2026-10-19). `isRemote` equals
`workplaceType != "OnSite"`. The job descriptions of those hybrid jobs say "in-office",
"in-person" or "relocate".

**Rule:** an explicit `workplaceType` (Hybrid / OnSite) wins over `isRemote`. A job is remote
only if `workplaceType` is Remote or a location string says "Remote" (Ramp lists
"Remote (US)" as a secondary location on a Hybrid job — that one is really remote).
Implemented in `normalize.classify`; tested in `tests/test_locations.py`.

**Why it matters:** trusting `isRemote` let hybrid jobs in San Francisco and New York pass as
"remote US". The M0 ground truth was labelled the same way, so 12 of its 18 roles only fit a
persona who would relocate — hence the `open_to_relocation` brief field.
