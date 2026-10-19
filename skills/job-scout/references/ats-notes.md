# ATS notes — what each job board API returns

Verified live on **2026-10-19** (dates below are when each fact was checked). Read this before
changing an adapter. The adapters live in `scripts/adapters/`; the contract is in
`scripts/adapters/__init__.py`.

## Normalized job (what every adapter's `normalize()` returns)

```
key              "ats:slug:job_id"            stable id used everywhere (seen.json, run files)
company, ats, slug, job_id, title
locations        [str]                        cleaned location strings, primary first
countries        [ISO-2]                      from structured country fields first, else parsed text
remote           true | false | null          null = the posting does not say
remote_scope     [code] | null                only when remote is true; e.g. ["US"], ["AMER"], ["ANY"]
workplace        "remote" | "hybrid" | "onsite" | null
department       str | null
first_published  "YYYY-MM-DD" | null          "open since" — never used to drop a role
url              employer ATS URL only (never an aggregator)
comp             {min, max, currency, interval, source: "ats_field"} | null
description_text str | null                   plain text (html_to_text); filled at list time when the list includes it
fetched_at       "YYYY-MM-DDTHH:MM:SSZ"
variants         [ {job_id, key, title, url, locations, first_published,
                    countries, remote, remote_scope, workplace, comp} ]       (added by collapse_variants)
```

**Pay comes only from structured fields.** Scripts never parse pay out of description text; the
judgment step may *quote* pay from the description, with a citation.

## Greenhouse

| | |
|---|---|
| List | `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` → `{jobs:[…], meta:{total}}` |
| Single job | `GET …/boards/{slug}/jobs/{id}?pay_transparency=true` → job object, or **404 when closed** (checked 2026-10-19) |
| Unknown board | 404 (checked 2026-10-19) |
| Empty board | 200 with `jobs: []` — e.g. `webflow` (M0); treat as **unverified**, not coverage |
| Title / URL | `title`; `absolute_url` (sometimes the employer's own careers site — still the employer) |
| Location | `location.name` (free text, e.g. "Hybrid - London"); `offices[].location` ("London, England, United Kingdom") |
| Remote / workplace | no structured field — parse `location.name` and office names |
| Date | `first_published` (ISO with offset); fall back to `updated_at` |
| Description | `content` — **double-escaped HTML** (`&lt;div&gt;…`); run `html_to_text` |
| Pay | **only on the single-job endpoint** with `?pay_transparency=true`: `pay_input_ranges: [{min_cents, max_cents, currency_type, title}]`. Filled on some boards (figma, anthropic), empty on others (vercel, affirm, airtable, discord) — 2026-10-19. Divide cents by 100; `interval = "year"` when `title` mentions annual/year, else `null`. So Greenhouse `comp` is `null` at list time and filled for the shortlist by `fetch_jd.py`. |

## Ashby

| | |
|---|---|
| List | `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` → `{apiVersion, jobs:[…]}` (checked 2026-10-19) |
| Single job | none — the list is the only endpoint; a job missing from a fresh list is closed |
| Skip | `isListed: false` |
| Title / URL | `title`; `jobUrl` (fallback `applyUrl`) |
| Location | `location` (primary text) + `secondaryLocations[].location`; each carries `address.postalAddress.addressCountry` ("United States", "USA", "Canada") — **use the structured country first** |
| Remote / workplace | `isRemote` (bool); `workplaceType` ("OnSite" / "Hybrid" / "Remote") |
| Date | `publishedAt` |
| Description | `descriptionPlain` (prefer) / `descriptionHtml` |
| Pay | `compensation.compensationTiers[].components[]` where `compensationType == "Salary"`: `minValue`, `maxValue`, `currencyCode`, `interval` ("1 YEAR" → "year", "1 HOUR" → "hour"). Present on ramp (167/167 jobs), absent on attention (2026-10-19). Ignore equity components. |
| Regional variants | the same role posted per region ("Design Engineer - Americas / Canada / EU / UK") — collapsed by `collapse_variants` |

## Lever

| | |
|---|---|
| List | `GET https://api.lever.co/v0/postings/{slug}?mode=json` → JSON **array** of postings |
| Single job | `GET …/v0/postings/{slug}/{id}?mode=json` → posting, or 404 when closed |
| Unknown board | 404 (checked 2026-10-19) |
| EU host | `api.eu.lever.co` returned **404 for all 10 sampled corpHuntingMCP Lever slugs**, which all answered on `api.lever.co` (2026-10-19). The `site` field some tenants carry equals the slug and does not mean EU. → No `lever_eu` adapter in v0 (ROADMAP follow-up if a real EU board appears). |
| Title / URL | `text`; `hostedUrl` (fallback `applyUrl`) |
| Location | `categories.location`, `categories.allLocations[]`; `country` (ISO-2, e.g. "CA") — **use `country` first** |
| Remote / workplace | `workplaceType` ("remote" / "hybrid" / "onsite") |
| Date | `createdAt` (epoch **milliseconds**) |
| Description | `descriptionPlain` + `lists[]` (requirements as `{text, content(html)}`) + `additionalPlain` |
| Pay | `salaryRange: {min, max, currency, interval}` (e.g. `per-year-salary`) — rare: 3/159 postings across 3 boards (2026-10-19). Map `per-year-salary` → "year", `per-hour-wage` → "hour", else `null`. |
| Aggregators | `lever:jobgether` hosts ~3,600 reposts of unnamed employers → `data/denylist.txt` |

## SmartRecruiters (verified 2026-10-19)

| | |
|---|---|
| List | `GET https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset=N` → `{offset, limit, totalFound, content:[…]}`, newest first. `limit` above 100 is silently clamped to 100. The adapter pages until `totalFound` or a short page, **capped at 5 pages (500 postings)**; probe.py lists a capped board under `errors` so it never closes saved roles. |
| Single job | `GET …/companies/{company}/postings/{id}` → posting with `jobAd`, `compensation`, `postingUrl`, `active`; **404 when it does not exist** (checked with id `1`). A real closed posting was not observed; `active: false` is treated as closed too. An id from another company → **400**, which stays unverified. |
| Unknown company | **200 with `totalFound: 0`** — never 404 (checked 2026-10-19), so seed_check marks it `unverified`, never `dead` |
| Slug | case-insensitive (`endava` answers for `Endava`); the key keeps the slug as imported |
| Title / URL | `name`; detail `postingUrl` (`https://jobs.smartrecruiters.com/{company}/{id}-{title-slug}`). The list has only `ref` (an API URL), so list-time `url` is built as `https://jobs.smartrecruiters.com/{company.identifier}/{id}` — that page answers 200 without the title part (checked 2026-10-19). `applyUrl` is the same page with `?oga=true`. |
| Location | one structured `location{city, region, country (ISO-2 lowercase), fullLocation, remote, hybrid}` per posting; `fullLocation` has empty parts ("Staines, , United Kingdom") — dropped. **Use `country` first.** |
| Remote / workplace | `location.remote` / `location.hybrid`. Both false on most postings, including some titled "remote" — so false means "not said" (`remote: null`), never onsite |
| Date | `releasedDate` |
| Department | `department.label` (often empty `{}`) |
| Description | **detail only**: `jobAd.sections` → `companyDescription`, `jobDescription`, `qualifications`, `additionalInformation`, each `{title, text(html)}`; joined as "title + text" in that order. List items have none (`description_text: null`, like Greenhouse list pay) |
| Pay | **detail only**: `compensation: {min, max, currency, period}` (`YEARLY` → "year", `HOURLY` → "hour", `MONTHLY`/`WEEKLY`/`DAILY` mapped the same way). Seen on 2 of 25 sampled companies (BryceTech, GalileoLearning), both US. |
| Not available | no description or pay in the list; no workplace text beyond the two flags; no requisition close date |
| Cost | one request per 100 postings per board, plus one per shortlisted job for `fetch_jd.py` |
| Seed | 6,282 tenants from corpHuntingMCP `src/tenants/smartrecruiters_*.rs` at the pinned SHA |

## Politeness (all adapters)

User-Agent `job-scout/<version> (+https://github.com/sorawit-w/job-scout)`; 20 s timeout; ≤8
concurrent requests; one retry on timeout/429/5xx; per-run request caps; successful board lists
cached 6 h in `~/.job-scout/cache/`. All through `scripts/net.py`.
