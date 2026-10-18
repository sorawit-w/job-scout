# M0 report (2026-10-18)

**Bottom line:** The case for job-scout holds. None of the three job-board connectors gave a
single direct employer link, and their recall on our 18 strong-fit roles was 0–6%. But job-scout
is not the first tool to read Greenhouse, Ashby and Lever directly: at least five open-source
tools already do. Its value has to come from the confirmation gate, fit judgment that cites the
job description, and honesty about what it does not know, not from the data access alone.

claude.ai Pro/Max reaches all three APIs under default settings (see §1). The thin-MCP exception in
HANDOFF §12 is not needed. Team/Enterprise plans are untested.

---

## 1. Network access per surface

| Surface | Default settings | How to allow it |
|---|---|---|
| Claude Code (this machine) | ✅ All 3 APIs reached | — |
| Codex CLI 0.154.0 | ❌ All 3 blocked (`sandbox: read-only`, DNS fails) | `--sandbox workspace-write -c sandbox_workspace_write.network_access=true` → ✅ all 3 reached |
| claude.ai Pro/Max (default "All domains", never changed) | ✅ All 3 APIs reached (2026-10-18) | — |
| claude.ai Team/Enterprise | ⏳ Not tested. Third-party sources say the default is "Package managers only" | Admin adds the 3 hosts to the domain allowlist (unverified) |

**To test claude.ai:** go to Settings → Capabilities, zip `docs/m0/egress-check/` and upload it as a skill,
start a new chat, and say "run the egress check". Please note your plan (Pro / Max / Team) and the
Code execution domain setting you see. Sources disagree on the default for each plan.

## 2. Ground truth re-check

All **18 of 18** strong-fit roles from `baseline_scorecard.py` are still open on the employer
ATS today. The ground truth is still valid for evals.

## 3. Connector scorecard

Script: `connector_scorecard.py`. Each connector got the same 4 searches: three role searches for
remote US, and one for Los Angeles.

| | Returned | Exact dups | Direct employer links | Strong fit (by title) | Recall on 18 (search) | Found when named (of 3) |
|---|---|---|---|---|---|---|
| Indeed | 30 | 4 | **0** | 2 | 0 / 18 | 0 / 3 |
| Dice | 40 | 7 | **0** | 10 | 1 / 18 | 0 / 3 |
| ZipRecruiter | 20 | 0 | **0** | 4 | 0 / 18 | **3 / 3** |
| *Web-search baseline* | *20* | *2* | *0* | — | *2 / 18* | — |

What this means:

- **Indeed** returned mostly unrelated results: AI-trainer gigs, hardware "design engineers" and
  recruiters. The Los Angeles search returned nothing.
- **Dice** gave the most useful results. Most were direct-hire listings, but every link goes to
  dice.com. Its `company_name` filter seemed to be ignored.
- **ZipRecruiter** holds the roles we care about, but its search does not surface them. When it
  did find them, the data was wrong in 4 places across 2 of the 3 roles:

| Role | Field | ZipRecruiter shows | Employer ATS says |
|---|---|---|---|
| Vercel Design Engineer | Pay | $69,600–$100,800 | **$208,000–$312,000** |
| Vercel Design Engineer | Date | 2 days ago | first published 2026-09-15 |
| Harvey Sr SWE, Frontend | Date | 27 days ago | first published 2024-03-08 |
| Harvey Sr SWE, Frontend | Mode | On-site | San Francisco, remote allowed |

- **The connectors find employers our seed does not have.** Ten strong-fit employers they
  surfaced are missing from the 49-board seed: ClickUp, Thumbtack, Grafana, Hims & Hers, Sift,
  Keeper, 1Password, Circles, Chamberlain and Ravenna.

**HANDOFF §12, condition 3 ("Indeed doesn't close the gap"):** answered for this persona. Indeed
does not close the gap.

## 4. Existing tools (competitor scan)

| Tool | What it is | License | Last push | Stars |
|---|---|---|---|---|
| [corpHuntingMCP](https://github.com/ZmoleCristian/corpHuntingMCP) | MCP, 10 ATS platforms, about 20k boards | 0BSD | 2026-10-13 | 0 |
| [jobscope](https://github.com/canmenzo/jobscope) | **Claude Code skill**, scores roles 0–100, HTML view | MIT | 2026-10-01 | 0 |
| [openhire](https://github.com/gzchenhao/openhire) | MCP + CLI, 154 employers, resume stays local | MIT | 2026-10-15 | 11 |
| [jobs-mcp](https://github.com/Ashishkosana/jobs-mcp) | MCP, US SWE roles, title matching | none stated | 2026-09-07 | 0 |
| [autoapply-mcp](https://github.com/niragmehta/autoapply-mcp) | MCP, discover → rank → draft → submit | MIT | 2026-10-15 | 1 |

I did not read their code or test them. None of them has a real user base yet.

**Only jobscope is an agent skill, and it is close to job-scout** (README read on 2026-10-18).
It is a Claude Code skill. Setup reads the resume and asks about salary, level, remote preference
and sponsorship. It pulls from 9 ATS systems, including Workday, and shows the reason for each
score. It flags sponsorship and ghost postings, shows "new only" on reruns, and never applies.
Differences: it runs in Claude Code only (Python 3.11 + pip), it scores with a script formula
instead of JD-cited judgment, and it hides roles older than 30 days by default. The other four are
MCP servers: same data, different form.

**Most useful find:** corpHuntingMCP's 0BSD license allows reuse of its board lists. They hold
about **1,400 Greenhouse, 3,000 Ashby and 800 Lever** slugs, compared with 49 in our seed. The
lists include Vercel, Harvey, Ramp, ClickUp, Thumbtack and Grafana. I have not checked how many
of those boards are still live.

## 4b. jobscope tested against the 18 roles

Script: `jobscope_scorecard.py`. jobscope commit `0e3e0e2`, installed in an isolated venv. It ran
with a synthetic persona: frontend / design-engineer titles, Senior to Staff, 10 years, no
sponsorship, and a $200k pay target (an assumption; the handoff gives none).

| Run | Roles kept | Recall in run file | Visible with default 30-day filter | In top 15 by score | Aggregator links |
|---|---|---|---|---|---|
| A: jobscope's own catalog (~250 boards, 69 s) | 1,021 | 10 / 18 | **4 / 18** | **0 / 18** | 82 (8%, The Muse) |
| B: our 49 seed boards | 438 | 13 / 18 | **4 / 18** | 3 / 18 | 82 (19%, The Muse) |
| *HANDOFF §11 target* | *~15* | *≥ 15 / 18* | | | *0* |

Why it missed roles (each traced in jobscope's code):

- **Old postings are dropped.** The freshness penalty pushes long-open roles below the 55 cutoff,
  for example Harvey Sr SWE Frontend (2024 and 2026 postings) and Perplexity MTS Design System. The
  dashboard then hides anything older than 30 days by default, which hides 9 of the 13 hits in
  run B.
- **Title matching.** "Design Systems Lead" (Ramp) and "Member of Technical Staff, Frontend"
  (Vapi) match none of its title phrases, so they never reach scoring.
- **Coverage.** 3 of the 10 ground-truth companies are not in its catalog (Vapi, Perplexity,
  Ashby). Its Vercel entry is listed under Ashby, but Vercel uses Greenhouse. The board returns
  0 jobs with no error and is counted as healthy.
- **Volume.** It kept 1,021 roles for one persona, and none of the 18 strong fits was in the top 15.

Where it is strong: it is fast, it reads 9 ATS systems including Workday, links mostly go to the
employer, it has tests, and it uses the MIT license.

Limits: one synthetic persona and one run. My title choices affect its title matching. Adding
"Senior Software Engineer" as a title would likely recover the Harvey Senior roles.

## 5. What this changes in the handoff

1. **Seed list (§5, §13).** Replace "hand-grow to 200–300" with this process: import
   corpHuntingMCP's Greenhouse/Ashby/Lever slugs as candidates, then let the weekly
   `seed-check.yml` keep only live boards. Add a credit line in the README, even though 0BSD does
   not require one.
2. **Positioning (§0, README).** Do not claim "direct ATS access" as new. Lead with what the
   other tools lack: the confirmation gate, fit judgment that cites the job description, honest
   unknowns, and the rerun diff.
3. **Codex (§5 Environment, §8).** The blocked-network stop message and the README must name the
   Codex setting from §1.
4. **Optional, v0.1:** when a job connector is installed, use its results only to *discover*
   employers. Then resolve each role to the employer ATS link before showing it. Never show
   connector links or connector pay data.
5. **Small fixes found earlier:** the handoff says `reference/` but the files are in `docs/`. The
   prototype uses a browser User-Agent, 12 threads and a hardcoded date.

## 6. Limits of this test

- Each connector got 4 searches; the baseline used 7. One persona only.
- Fit was judged from titles, as in the baseline.
- Open status was checked only for the 18 ground-truth roles, not for connector results.
- I did not run the competitor tools.
- The Claude Code result is from this machine's setup. Another user's sandbox settings may differ.

## 7. Open decisions

1. ~~Run the claude.ai egress test.~~ Done: works on Pro/Max defaults.
2. Build job-scout, or contribute to jobscope? **Recommend build.** In the test (§4b), jobscope
   showed 4 of 18 strong fits by default and ranked none in its top 15. Its misses come from exactly
   what job-scout plans to do differently: judging fit from the job description instead of the
   title, and showing "open since" instead of cutting old roles. job-scout also runs on claude.ai.
   Its MIT-licensed ATS adapters, especially Workday, are worth borrowing, with credit.
3. Approve using corpHuntingMCP's board list as the seed source.
