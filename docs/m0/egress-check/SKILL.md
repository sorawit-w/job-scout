---
name: egress-check
description: M0 spike for job-scout. Use only when the user says "run the egress check". Tests whether this sandbox can reach the Greenhouse, Ashby and Lever public job-board APIs.
---

# Egress check

Run `python3 scripts/egress_check.py` from this skill's folder and show the output exactly as printed.

Then add one line per host: reachable or blocked. If any host is blocked, say which setting
controls outbound network access on this surface, if you know it. Do not try other ways to reach
the hosts (no web search, no fetch tools); the point is to test the code sandbox only.
