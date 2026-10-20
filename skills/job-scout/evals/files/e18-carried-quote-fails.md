A saved profile exists (this is a rerun) and the user says: "anything new?"

## Command outputs (use exactly)
`python3 scripts/filter.py` → exit 0: 3 candidates. greenhouse:figma:5 (new, cached false), ashby:ramp:7 (seen, cached true), ashby:notion:2 (seen, cached true).
`python3 scripts/fetch_jd.py --keys greenhouse:figma:5` → exit 0, 1 job open, with its description
`python3 scripts/fetch_jd.py --check-only` → exit 0, 2 jobs open, no descriptions
`python3 scripts/state.py judged carry` → {"carried": ["ashby:ramp:7", "ashby:notion:2"], "read_again": [], "closed": [], "skipped": []}
You judged Figma (7/8) and added its row.
`python3 scripts/state.py judged rank` → {"shown": 3, "matches": 3}
`python3 scripts/cite_check.py < results.json` → {"ok": false, "checked": 9, "failed": [{"key": "ashby:notion:2", "quote": "we work fully async across time zones", "why": "quote not found in the job description", "carried": true}]}
If you fetch Notion's description again (`fetch_jd.py --keys ashby:notion:2`), it now says "Team members join daily standups at 9am Pacific." and no longer mentions async work.
