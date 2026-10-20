You are running on claude.ai: files do not persist between chats. Say what you would do in each
reply of two separate chats.

## Chat 1 — first message
"I'm a senior frontend engineer in Denver. Remote in the US only, I don't need sponsorship, pay
floor $170k. Find me jobs — just go."

### Command outputs (use exactly)
`python3 scripts/state.py profile show` (before searching) → exit 1, {"error": "no profile saved yet"}
`python3 scripts/state.py profile save --stdin` → {"ok": true, "saved": true}
`python3 scripts/probe.py --health` → {"ok": true}
`python3 scripts/probe.py` → exit 0, 48 boards probed, 610 jobs
`python3 scripts/filter.py` → exit 0: 4 candidates, all new: greenhouse:linear:101 (Senior Frontend Engineer, Linear), ashby:vercel:7 (Frontend Engineer, Vercel), lever:acme:3c (Staff Frontend Engineer, Acme; the same role is also posted as lever:acme:3d), ashby:ramp:12 (Senior Software Engineer, Frontend, Ramp)
`python3 scripts/fetch_jd.py --keys greenhouse:linear:101,ashby:vercel:7,lever:acme:3c,ashby:ramp:12` → exit 0, 4 jobs open, with descriptions
You judged all four; `judged rank` → {"shown": 4, "matches": 4}; cite_check → {"ok": true}
`python3 scripts/report.py` → {"report": "/tmp/js/runs/r1/report.html"}
`python3 scripts/state.py seen record` → {"inserted": 4}

### Chat 1 — second message (after the results)
"save 1, dismiss 3: too senior"

`python3 scripts/state.py seen mark greenhouse:linear:101 saved` → {"ok": true}
`python3 scripts/state.py seen mark lever:acme:3c dismissed --reason="too senior"` → {"ok": true}
`python3 scripts/state.py profile show` → {"schema": 1, "target_roles": ["Senior Frontend Engineer"], "work_modes": ["remote"], "remote_scope": ["US"], "needs_sponsorship": "no", "base_pay_floor": {"amount": 170000, "currency": "USD", "interval": "year"}, "home_base": "Denver, CO", "track": "ic", "result_count": 15, "recency_flag_days": 90, "hide_no_pay": false, "open_to_relocation": false, "sources": {}}
`python3 scripts/state.py seen show` → {"counts": {"saved": 1, "dismissed": 1, "seen": 2}, "saved": [{"key": "greenhouse:linear:101", "aliases": [], "title": "Senior Frontend Engineer", "company": "Linear", "url": "https://jobs.linear.app/101", "closed": false}], "applied": [], "dismissed": [{"key": "lever:acme:3c", "aliases": ["lever:acme:3d"], "title": "Staff Frontend Engineer", "company": "Acme", "url": "https://jobs.lever.co/acme/3c", "closed": false}]}

## Chat 2 — a new chat, first message
The block you offered at the end of chat 1, pasted in full, followed by "anything new?"

### Command outputs (use exactly)
`python3 scripts/state.py profile save --stdin` → {"ok": true, "saved": true}
`python3 scripts/state.py seen mark greenhouse:linear:101 saved` → {"ok": true}
`python3 scripts/state.py seen mark lever:acme:3c dismissed --aliases=lever:acme:3d` → {"ok": true}
The search then runs as a rerun with no new roles: filter.py keeps Linear (SAVED), Vercel and Ramp come back NEW, Acme is not in the list.
`python3 scripts/state.py profile show` (at the end) → the same profile as in chat 1
`python3 scripts/state.py seen show` (at the end) → {"counts": {"saved": 1, "dismissed": 1, "seen": 2}, "saved": [{"key": "greenhouse:linear:101", "aliases": [], "title": "Senior Frontend Engineer", "company": "Linear", "url": "https://jobs.linear.app/101", "closed": false}], "applied": [], "dismissed": [{"key": "lever:acme:3c", "aliases": ["lever:acme:3d"], "title": null, "company": null, "url": null, "closed": false}]}
