# Handoff: `job-scout` skill v0

Resume → **confirmed search brief** → verified-open, direct-link job matches.

| | |
|---|---|
| Builder | A coding agent |
| Repo | This repo (private until M6; name still TBD, see §13). Also list it as an external entry in the agent-skills README and `docs/skill-graph.md`, to borrow that audience. |
| Audience | **Public tool for job seekers**, including non-developers |
| Date | 2026-10-18 (rev. 3: M0 results folded in; rev. 2 moved it from agent-skills to its own repo) |
| Status | **M0 done** (§1b, full report in `docs/m0/M0_REPORT.md`). Ready for M1 after the open decisions in §13 |

---

## 0. TL;DR for the builder

- **What to build.** An agent skill (not a server, not an MCP) that:
  - reads a user's resume,
  - **proposes search parameters and gets the user to confirm them before any search**,
  - queries public ATS job-board APIs directly (Greenhouse, Ashby, Lever first),
  - reads the job descriptions of the shortlist,
  - returns a ranked table of open roles with direct employer links and an honest "why / why not" for each.
- **Why a skill.** A web-search-only agent failed a real test (§1). The gap is *data access*: freshness, recall, and direct links. Bundled scripts close that gap for one user with zero infrastructure.
- **Starting point.** Most of the data layer already exists as a prototype in `docs/reference/`.
- **Hard requirement from the maintainer:** the agent must confirm the job parameters with the user before searching (§4).
- **M0 is done (§1b).** claude.ai Pro/Max, Claude Code and Codex (with one setting) can all reach the job-board APIs. No thin MCP is needed.
- **The bar is now jobscope, not only web search.** An existing open-source skill does most of the same flow; job-scout must beat it on the same 49 boards (§1b, §11).
- **Before writing code,** ask the maintainer the open decisions in §13.

---

## 1. Why this exists (evidence)

On 2026-10-18 we ran a test with a real senior frontend engineer's resume (not committed). A plain agent ran 7 web searches and returned 20 "matching" roles. Each was verified against the employer's live ATS:

| Metric | Web-search agent |
|---|---|
| Links direct to the employer ATS | **0 / 20** (all aggregators or recruiters) |
| Exact duplicates | 2 (one role syndicated across 3 BuiltIn city sites) |
| Unique postings already closed | **61%** (11 / 18) |
| Open, posted in the last 7 days, and a strong fit | **0 / 20** |
| Recall: strong-fit open roles found on 49 boards probed directly | **2 / 18 (11%)** |

Lessons that shape this spec:

- **Aggregator dates lie.** BuiltIn showed one role as "posted 4 days ago." The employer's Ashby board says first published 2025-08-08.
- **Keyword search confuses meanings.** "Design engineer" returned mechanical, RF, and civil jobs. "Greenhouse" returned agricultural greenhouses.
- **"Posted in the last N days" is the wrong filter.** Only 1 of 18 strong fits was under 7 days old. Three were more than 6 months old and still open (evergreen postings).
- **Title matching misses roles.** The ground truth itself used title keywords, so it is a lower bound. Titles like "Software Engineer, Product" slip through. Fit must be judged from the job description.

The full scorecard is in `docs/reference/baseline_scorecard.py`. That is the bar to beat.

---

## 1b. M0 results (2026-10-18)

Full report: `docs/m0/M0_REPORT.md`. Scripts: `docs/m0/connector_scorecard.py`, `docs/m0/jobscope_scorecard.py`.

- **Ground truth still holds.** All 18 strong-fit roles were still open on the employer ATS.
- **Network access per surface:**
  - claude.ai Pro/Max, default "All domains": ✅ all 3 APIs.
  - Claude Code: ✅ all 3 APIs.
  - Codex CLI: ❌ blocked by default; ✅ with network access turned on (§5 Environment).
  - claude.ai Team/Enterprise: not tested. Third-party sources say the default is "Package managers only".
- **Job-board connectors don't close the gap.** Indeed, Dice and ZipRecruiter gave **0 direct employer links** and found 0–1 of the 18 roles. ZipRecruiter held 3 of them when searched by name, but showed the wrong pay (Vercel: $69.6k–$100.8k vs $208k–$312k on the employer page), wrong dates and a wrong work mode.
- **Similar tools exist.** At least 5 open-source tools read Greenhouse/Ashby/Lever directly. Four are MCP servers. One, **jobscope** (`canmenzo/jobscope`, MIT), is a Claude Code skill with a similar flow: setup questions, ATS fetch, scoring, sponsorship flags, reruns.
- **jobscope on the same 18 roles:**
  - On our 49 seed boards, it kept 13 of 18, but showed only **4 of 18** under its default 30-day filter and ranked **3 of 18** in its top 15 (438 roles total).
  - On its own catalog, it kept 10 of 18, showed 4, and ranked 0 in its top 15 (1,021 roles total).
  - Its misses come from cutting old postings and matching on titles. job-scout's design (§5 "Old ≠ closed", §6 JD-based fit) targets exactly those two things.
- **The seed list limits recall most.** The connectors surfaced 10 strong-fit employers missing from our 49 boards (ClickUp, Thumbtack, Grafana and others).

---

## 2. Scope

**Goals (v0)**
1. Turn a resume plus confirmed preferences into a search brief.
2. Probe a seed list of employer boards, plus companies the user adds.
3. Return roles that are open at run time, deduped, linked directly to the employer, ranked, and explained from the job description.
4. Remember what the user has seen, saved, applied to, or dismissed (local file), so reruns show **what's new**.

**Non-goals (v0). Don't build these.**
- **Anything LinkedIn.** No scraping, no session cookies. It violates their User Agreement §8.2.
- **Scraping any site that requires login.**
- **Auto-apply, mass outreach, or bulk messaging.**
- **Cover letters or outreach drafts.** If a writing skill is installed (e.g., `ghostwriter` from agent-skills), route to it by name. Otherwise, say drafting is out of scope for v0. Never depend on it being present.
- **Any server, hosted index, or MCP** (see §12).
- **Workday-hosted employers.** This is a known coverage gap: many large LA employers use Workday. Now planned for v0 as M5b (see `implementation-plan.yaml`); until it ships, document it in the README.
- **Recruiter-side features.**

---

## 3. User flow

1. **Ingest the resume.** Accept a file (PDF, DOCX, HTML, MD) or pasted text. Extract a draft profile.
2. **Search brief and confirmation gate** (§4). No network calls to job boards before this step completes.
3. **Probe** the seed boards plus user-added companies, using a cache (§5).
4. **Normalize, dedupe, and apply hard filters** (§5, §6).
5. **Shortlist** about 30–40 candidates. Fetch their job descriptions.
6. **Judge fit** against the rubric, citing job-description text (§6).
7. **Output** a ranked table, plus a short "close but excluded" list with the reason for each (§6).
8. **Collect feedback** (save / apply / dismiss with reason) and write it to local state (§7).
   - If feedback implies a parameter change ("3 dismissals, all hybrid"), **propose** the change and confirm it. Never update silently.
9. **Rerun:** show the previous brief as a diff ("same as last time, change anything?"), then show only new or changed roles by default.

---

## 4. The confirmation gate (required)

**Rule:** before the first request to any job board, show the user a search brief and get an explicit confirmation or edits. The only exception is when the user explicitly says to skip it ("just go", "use your best guess"). Even then, show the brief with every default visibly labeled.

**Why it matters:**
- Wrong parameters waste the probe budget and anchor the ranking on the wrong things.
- Users trust results more when they've seen and approved the assumptions behind them.

### Parameters (`profile.json` schema)

| Field | Example | Rule |
|---|---|---|
| `target_roles` | Design Engineer; Staff/Lead Frontend; UI/Frontend Platform; Design Systems | Infer from the resume. Confirm. |
| `title_synonyms` / `title_exclusions` | exclude: mechanical, RF, RTL, civil, data center, "Product Designer" | Infer. Show only if non-obvious. |
| `seniority` + `track` | Senior / Staff / Lead · IC | Infer from the resume. Confirm. |
| `home_base` | Pasadena, CA | From the resume. Confirm. |
| `work_modes` | remote_us, hybrid (LA area), onsite | **Never guess. Ask.** |
| `remote_scope` | US only | Ask if remote is chosen. Many remote roles are restricted by country. |
| `needs_sponsorship` | yes / no / prefer not to say | **Never guess or infer** (not from name, education, or work history). Ask as a plain yes/no. Use only as a filter. |
| `base_pay_floor` | USD amount, or none | **Never guess. Ask.** Also ask whether to hide roles with no listed pay (default: keep them, labeled "pay not listed"). |
| `industries_prefer` / `industries_exclude` | prefer AI/devtools | Infer softly. Label as inferred. |
| `companies_include` / `companies_exclude` | exclude the current employer? | Infer the current employer from the resume. **Confirm** it. |
| `must_haves` / `dealbreakers` | "TypeScript", "no on-call" | Ask once, optionally. |
| `recency` | all open roles; flag first published > 90 days | Default. Label it. |
| `result_count` | 15 | Default. |

### Interaction rules

- **One round.** Show the whole brief as a compact table with a `Source` column (`resume` / `inferred` / `default` / **`needs you`**).
- **Ask only what's missing or critical.** That's at most about 5 questions, in one message.
- **Use structured choice UI when available** (e.g., an ask-user tool in Claude Code or claude.ai). Fall back to plain text.
  - The skill must stay agent-agnostic: claude.ai, Claude Code, Codex, and Copilot.
- **Never ask about protected attributes** (age, race, gender, etc.). Never infer them.

Example (synthetic senior frontend persona):

```
Search brief — confirm or edit before I search

| Parameter          | Value                                                        | Source    |
|--------------------|--------------------------------------------------------------|-----------|
| Target roles       | Design Engineer · Staff/Lead Frontend · UI Platform · Design Systems | resume |
| Seniority / track  | Senior, Staff, Lead · IC                                     | resume    |
| Home base          | Pasadena, CA                                                 | resume    |
| Work mode          | ?                                                            | needs you |
| Base pay floor     | ?                                                            | needs you |
| Visa sponsorship   | ?                                                            | needs you |
| Exclude companies  | current employer                                             | inferred — confirm |
| Industries         | AI / devtools preferred, none excluded                       | inferred  |
| Recency            | all open roles; flag >90 days old                            | default   |

1. Work mode: remote (US) / LA-area hybrid / onsite — pick any
2. Minimum base pay? (or "no floor")
3. Do you need visa sponsorship? yes / no / prefer not to say
```

---

## 5. Data layer

### ATS adapters

| ATS | List endpoint | Date field | Status |
|---|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` | `first_published` (also `updated_at`) | ✅ verified 2026-10-18 |
| Greenhouse (single job) | `.../boards/{slug}/jobs/{id}` → 404 when closed | — | ✅ verified |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{slug}` | `publishedAt`; also `isRemote`, `secondaryLocations` | ✅ verified |
| Lever | `https://api.lever.co/v0/postings/{slug}?mode=json` | `createdAt` (ms epoch) | ✅ verified |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{id}/postings` | check | ⚠️ responded 200; fields not verified |
| Workable | widget/account endpoint | check | ❌ unverified. Treat as v0.1. |

Job-description fetching (verify each before relying on it):
- **Greenhouse:** `?content=true` on the list or single-job endpoint.
- **Ashby:** description fields in the board response; `includeCompensation=true` for pay.
- **Lever:** descriptions are included in the list response.

### Normalized job schema

```
{ company, ats, job_id, title, locations[], remote: bool|null, remote_scope,
  department, first_published, url /* employer ATS URL only */,
  comp: {min,max,currency}|null, description_text|null, fetched_at }
```

### Gotchas from the prototype run (handle all of them)

- **Regional variants.** Ashby posted the same role as 4 regional variants (Americas / Canada / EU / UK). Collapse them into one row with a list of locations.
- **Multi-location strings.** Locations like `Remote | United States | Poland | United Kingdom` must parse into a list, plus a remote-scope value.
- **Aggregators hosted on an ATS.** `lever:jobgether` held about 3,600 reposts of unnamed employers. Keep a **denylist**. Never treat these as employers.
- **Empty boards.** Some slugs return 200 with 0 jobs (wrong slug, or the company moved ATS). Mark them `unverified`. Don't count them as coverage.
- **Old ≠ closed.** Evergreen postings can stay open for 12+ months. Show "open since {date}" instead of discarding them.
- **Title false positives seen:**
  - "Data Center Design Engineer, Electrical"
  - "RTL Design Engineer"
  - "Product Designer, Design Systems" (a designer, not an engineer)
  - "Senior SWE, Backend (Product Engineering)"

### Coverage (public positioning)

- **Seed list:** `docs/reference/companies_seed.csv` has 49 boards from the run (46 with jobs, 3 empty to re-verify). It leans toward AI and devtools.
  - A public tool needs a broader seed, tagged by sector (`sector`, `hq_region`, `remote_friendly`).
  - **Seed source (from M0):** don't grow the list by hand. Import the Greenhouse, Ashby and Lever slugs from `ZmoleCristian/corpHuntingMCP` (`src/tenants/*.rs`, 0BSD license): about 1,400 + 3,000 + 800 candidates. Then let `seed-check.yml` keep only boards that return jobs. Credit the source in the README, even though 0BSD doesn't require it.
  - A board that returns 200 with 0 jobs is **not** healthy (jobscope's Vercel entry fails this way). Treat it as `unverified`.
- **Be honest about coverage.** Greenhouse, Ashby, and Lever skew toward tech and startup employers. Large enterprises, healthcare, retail, and government mostly use Workday, iCIMS, Taleo, or USAJOBS.
  - The README and the skill itself must say v0 is **best for tech/startup roles**.
  - When a user's profile is outside that, say coverage will be thin rather than returning weak matches.
- **Adding companies:** when the user names a company, guess its slug across ATSs (`gh`, `ashby`, `lever`; slugified name plus common variants). Save hits to the user's local company list.
  - Offer to open a PR or issue so the company gets added to the shared seed. **Community contributions to the seed list are the growth loop.**

### Politeness

- **Concurrency** of 8 or less, a 20 s timeout, and an identifying User-Agent.
- **Cache:** per-board cache with about a 6 h TTL in a local `.cache/`.
- **Terms:** this is low-volume, single-user use of public job-board endpoints. **Re-check each provider's API terms before any hosted or multi-user version** (that's the §12 decision, not v0).

### Environment

- **Network required.** Run one health probe first.
- **If the sandbox blocks egress,** say so plainly, explain which setting would allow it, and stop. Don't fall back to web search silently.
- **Settings to name in the stop message and the README (verified in M0):**
  - **Codex:** blocked by default (`sandbox: read-only`). Allow it with `codex --sandbox workspace-write -c sandbox_workspace_write.network_access=true`, or set the same value in `~/.codex/config.toml`.
  - **claude.ai:** Settings → Capabilities → Code execution → domain allowlist. Pro/Max default "All domains" works. Team/Enterprise admins may need to add `boards-api.greenhouse.io`, `api.ashbyhq.com` and `api.lever.co` (not yet tested).
  - **Claude Code:** worked in M0 with no change.

---

## 6. Matching and output

### Pipeline

1. **Hard filters in a script** (deterministic): work mode / location / remote scope, seniority exclusions, company include/exclude, the denylist.
2. **Title prefilter in a script:** permissive for recall, using synonyms plus exclusions. Send borderline titles to the LLM step; don't drop them.
3. **Fetch job descriptions** for the top ~30–40.
4. **LLM fit judgment in SKILL.md** (the judgment step is not a script), scored on a rubric:
   - **Pass/fail gates:** location/mode, sponsorship (if the job description states it), pay floor (if pay is listed).
   - **0–2 on each:** role-family match, skills overlap, level match, domain preference.
   - **Every claim about the job must cite job-description text.**
   - **Unknowns stay unknown:** "pay not listed", "sponsorship not stated".

### Output (in chat; CSV export optional)

| # | Company | Role | Location / mode | Pay | Open since | First seen | Fit | Why | Risk | Link |
|---|---|---|---|---|---|---|---|---|---|---|

- **Links must be employer ATS URLs only.** Never aggregators.
- **After the table:** a "close but excluded" list (3–5 rows, one-line reason each), so the user can spot over-tight filters.
- **End with the feedback prompt** (save / apply / dismiss + reason).
- **Hand off, don't draft:** if the user asks for a cover letter or outreach, hand off to an installed writing skill with the job URL and the profile, or say drafting is out of scope (§2).

---

## 7. State and reruns

Keep all state local. Never write it into the repo.

- **`profile.json`:** the confirmed brief (schema in §4).
- **`seen.json`:** `{job_key: {first_seen, last_seen, status: seen|saved|applied|dismissed, reason}}`, where `job_key = ats:slug:job_id`.
- **Reruns:**
  - Show "new since {last run}" first.
  - Then show "still open, previously saved".
  - Mark jobs that disappeared from the board as **closed**.
- **Where state lives:**
  - In Claude Code, state persists in a user-level directory (decision in §13).
  - In claude.ai, the container resets. Say that state won't persist, and offer to export `profile.json` for next time.

---

## 8. Packaging (own public repo)

- **Borrow conventions, not code.**
  - Read 1–2 skills in agent-skills for style (`screenwright` for its eval loop, `ghostwriter` for routing boundaries).
  - Keep the same install path (`npx skills`), so agent-skills users get a familiar experience.
  - Don't import from that repo.
- **Proposed layout:**

```
job-scout/                      # repo root
├── skill/job-scout/            # the installable skill
│   ├── SKILL.md                # workflow, confirmation gate, rubric, output format (<500 lines)
│   ├── scripts/                # probe.py, filter.py, fetch_jd.py, state.py
│   ├── references/             # ats-notes.md (§5), rubric.md (§6)
│   └── data/                   # companies_seed.csv, denylist.txt
├── tests/                      # unit tests on recorded fixtures (offline)
├── evals/                      # evals.json + synthetic resumes (several personas)
├── .github/workflows/
│   ├── ci.yml                  # lint + offline tests on every PR
│   └── seed-check.yml          # weekly cron: probe every seed slug, flag dead/empty ones
├── README.md                   # for job seekers first: what it does, coverage limits, install per surface
├── PRIVACY.md                  # what leaves the machine (job-board list requests only), what's stored locally
├── CONTRIBUTING.md             # how to add a company (one CSV row, CI validates the slug)
├── CHANGELOG.md
└── LICENSE
```

- **Distribution per surface:**
  - Claude Code / Codex: `npx skills`.
  - claude.ai: release a zipped skill for upload (M0 passed on Pro/Max defaults). Say in the README that Team/Enterprise admins may need to allowlist the three hosts.
  - Publish each release as a GitHub Release artifact.
- **Public-repo essentials:**
  - A "not affiliated with any job board or employer" disclaimer.
  - No telemetry by default.
  - Per-run request caps, so the tool can't be repurposed as a bulk crawler.

- **Positioning (from M0).** Direct ATS access is **not** new: at least 5 open-source tools do it (§1b). Don't claim it as the headline. Lead with what they lack:
  - **"Checked open today, linked straight to the employer"**: job boards can't say this, because their links go to themselves and their dates and pay can be wrong (§1b).
  - **Fit read from the job description, with quotes**, instead of title matching.
  - **Long-open roles stay visible**, labeled "open since {date}", instead of being cut at 30 days.
  - **Runs where non-developers are**: claude.ai, plus Claude Code and Codex. jobscope is Claude Code only.
  - **A short, ranked list (about 15)** instead of hundreds of roles.

- **Write SKILL.md in the imperative,** and explain *why* rules exist rather than shouting MUSTs (skill-creator guidance).
- **Make the description a bit "pushy"** so it triggers on job-search intents ("find me jobs", "match my resume to roles", "what should I apply to"). It should *not* trigger on cover letters or interview prep.

---

## 9. Guardrails

- **Privacy:** the resume and profile never leave the user's machine except as search parameters sent to job-board APIs. In practice those are filters applied locally, so job boards only see list requests.
- **Public repo hygiene:** don't commit any real resume or any real profile or state files. Build eval fixtures from a **redacted or synthetic** resume (§11).
- **Honesty:**
  - Never invent pay, sponsorship, or remote status.
  - Show "unverified" when unsure.
  - Never present a job as open without a live check during this run, or a cache entry younger than the TTL.
- **No auto-actions:** the skill never applies or messages anyone.

---

## 10. Build order

1. **M0, spike plus decisions. ✅ Done 2026-10-18** (§1b, `docs/m0/`). Egress checked on all three surfaces, job-board connectors and jobscope scored, competitor scan done. Still open: the §13 decisions.
2. **M1, data layer.**
   - `probe.py` with adapters, cache, the normalized schema, regional-variant dedupe, and the denylist.
   - **Fix three prototype issues** when rewriting it: use an identifying User-Agent (not `Mozilla/5.0`), cap threads at 8 (not 12), and use the current time instead of the hardcoded `NOW = 2026-10-18`.
   - **Import the seed** from corpHuntingMCP and run the seed check once (§5 Coverage).
   - **Record API responses as fixtures** (`tests/fixtures/`) so tests run offline.
3. **M2, confirmation gate.** `profile.json` schema plus the brief rendering and question logic in SKILL.md.
4. **M3, matching.** `filter.py`, `fetch_jd.py`, the rubric, and the output table.
5. **M4, state.** `seen.json`, the rerun diff, and the "new since last run" view.
6. **M5, evals** with the skill-creator workflow (with-skill vs. baseline), then iterate.
7. **M6, public launch.**
   - Write the README for job seekers, PRIVACY.md, CONTRIBUTING.md, LICENSE, and CI (including the weekly seed check).
   - Tune the description's triggering.
   - Cut the first release.
   - Add an external entry to agent-skills.
   - **Ask the maintainer before making the repo public or publishing anything.**

---

## 11. Evals and acceptance criteria

### Test prompts (`evals/evals.json`)

| ID | Setup | What it tests |
|---|---|---|
| E1 | Redacted eval resume + "find me roles that fit" | Gate fires; asks work mode, pay floor, sponsorship; no network call before confirmation |
| E2 | Resume without a location + "remote only, US" | Remote-scope parsing; no non-US remote roles |
| E3 | User needs sponsorship | Roles whose job description says no sponsorship are excluded or flagged, with citations; "not stated" is labeled, not assumed |
| E4 | "Skip the questions, just go" | Proceeds with labeled defaults; brief still shown |
| E5 | Rerun after marking 2 applied and 1 dismissed | Only new or changed roles by default; closed roles marked |
| E6 | "Also check Linear and Figma" | Slug discovery works; saved to the local company list |
| E7 (negative trigger) | "Write a cover letter for this Vercel role" | Does **not** run the search; routes to an installed writing skill, or says drafting is out of scope |
| E8 | Synthetic non-tech resume (e.g., hospital nurse) | Says coverage is thin for this profile; doesn't pad results with weak matches |
| E9 | Synthetic non-developer user, plain-language request, no file ("I'm a marketing manager in Austin, what's out there?") | Gate still works from chat-only input; no jargon in questions or output |

### Acceptance criteria (v0 is done when all pass)

- [ ] **Confirmation gate** holds in 100% of transcripts (E1–E3, E5). E4 shows a labeled brief.
- [ ] **100% of output links** are employer ATS URLs. 0 aggregators.
- [ ] **0 exact duplicates.** Regional variants collapsed.
- [ ] **Every listed role is open** per a live check or fresh cache during the run.
- [ ] **Every fit claim cites job-description text.** Missing pay or sponsorship is labeled, never invented.
- [ ] **Recall:** on the same 49-board seed with the senior frontend eval persona, surface **at least 15 of the 18** strong-fit roles in `docs/reference/baseline_scorecard.py`. The skill may find more, because it reads job descriptions. That's fine; spot-check the extras.
  - These 18 are a 2026-10-18 snapshot. **Re-label the ground truth on the day you run the eval**, since roles open and close.
- [ ] **Beat jobscope on the same 49 boards and persona** (`docs/m0/jobscope_scorecard.py`). On 2026-10-18, jobscope showed 4 of 18 by default and ranked 3 of 18 in its top 15. job-scout's top 15 should hold clearly more. Re-run jobscope on the eval day, because both tools and the roles change.
- [ ] **Rerun diff is correct** (E5).
- [ ] **Graceful failures:** blocked network gives a clear stop message. Zero results explains which filter removed the most.

*(The thresholds are the authors' judgment, not industry standards. Adjust them after the first eval round if they prove too loose or too tight.)*

---

## 12. Out of scope now: when to graduate to an MCP service

Build a hosted index plus an MCP server only when **all three** hold:

1. **Sustained use:** The maintainer plus 5–10 others use the skill weekly for 3+ weeks.
2. **Plumbing complaints:** the top complaints are about state, alerts, or probing speed ("it forgot what I saw", "I want alerts", "probing is slow"), not about matching quality.
3. **Indeed doesn't close the gap:** the §1 scorecard, run against **Indeed's official Claude connector** (the real competitor, untested so far), still shows a large gap. For example, ≥30% stale or closed, or many direct-from-employer roles missed.
   - **M0 answer:** the gap holds. Indeed gave 0 direct links and found 0 of 18 roles; Dice and ZipRecruiter did no better on links (§1b).

If any of the three fails, stay a skill.

**Separate, earlier exception: a thin MCP for reach.** **M0 answer: not needed now.** claude.ai Pro/Max reaches all three APIs under default settings. Revisit only if Team/Enterprise users turn out to be blocked and can't get the hosts allowlisted. The original plan, kept for that case: if claude.ai blocks job-board egress by default, non-developers can't use the skill there. In that case, propose to the maintainer a **stateless** MCP:
- **Tools:** `search_jobs(filters)` and `get_job(id)`, proxying the same ATS adapters with a shared cache.
- **No accounts, no resume upload, no stored user data.** The confirmation gate, matching, and state stay on the agent side.
- **This solves reach, not state.** The full hosted index (alerts, saved jobs) still waits for the three criteria above.

---

## 13. Open decisions: ask the maintainer before building

| Decision | Proposed default |
|---|---|
| Skill / repo name | `job-scout` (placeholder). Check that the name is free on GitHub and npm before committing to it. **New from M0:** `job-scout` is very close to `jobscope`, an existing skill doing similar work. Consider a more distinct name. |
| License | MIT |
| Location of state on disk (Claude Code) | `~/.job-scout/` (profile, seen, cache, user companies) |
| Job-description fetch budget per run | top 40 after hard filters |
| SmartRecruiters in v0? | Yes if the field check passes in M1; Workable deferred to v0.1 |
| Seed list scope | **Changed after M0:** import corpHuntingMCP's ~5,000 Greenhouse/Ashby/Lever slugs (0BSD), keep only live boards via the seed check, then add sector tags; community PRs after that |
| Build vs. contribute to jobscope | **Build** (M0 §1b: jobscope showed 4/18 by default, 3/18 in its top 15). Borrow its MIT adapters with credit where useful. |
| Workday in v0.1? | Moved into v0: M5b (2026-10-19, maintainer) adds SmartRecruiters, Workday with a verified company list, and opt-in USAJOBS before launch. |
| Default `result_count` | 15 |
| Eval resumes | 3–4 synthetic personas (senior frontend matching the §1 test, data analyst, PM, one out-of-coverage). Any real resume is used locally only, never committed. |
| Thin MCP (§12 exception) | **Not needed** (M0: claude.ai Pro/Max works by default). Revisit only for blocked Team/Enterprise users. |
| Repo visibility | Private until M6; the maintainer flips it public |

---

## Appendix: files in this handoff

| File | What it is |
|---|---|
| `docs/reference/ats_probe_prototype.py` | Working Greenhouse/Ashby/Lever prober from the test run. Rewrite it into `scripts/probe.py`. |
| `docs/reference/companies_seed.csv` | 49 boards verified on 2026-10-18 (ATS, slug, job count, status). |
| `docs/reference/baseline_scorecard.py` | The web-search baseline results plus metric definitions. Reuse the metrics for the skill's evals. |
| `docs/m0/M0_REPORT.md` | M0 results: egress per surface, connector and jobscope scorecards, competitor scan. |
| `docs/m0/connector_scorecard.py` | Indeed / Dice / ZipRecruiter scorecard, same metrics as the baseline. |
| `docs/m0/jobscope_scorecard.py` | Scores a jobscope `_run.json` against the 18 roles. Reuse it for the "beat jobscope" check (§11). |
| `docs/m0/egress-check/` | The minimal skill used for the egress test. Zip the folder to upload it (`cd docs/m0 && zip -r egress-check.zip egress-check`). Reuse it for Team/Enterprise checks. |
