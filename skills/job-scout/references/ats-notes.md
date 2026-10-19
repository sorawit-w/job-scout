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

## Workday (verified 2026-10-19)

Undocumented public "CXS" JSON behind each employer's `myworkdayjobs.com` careers site; Workday can change it without notice.

| | |
|---|---|
| Slug | `<tenant>.<wdN>.<site>` with dots (a key is `ats:slug:job_id`, so no `:`), e.g. `sharp.wd1.External`. Validated (`tenant` `[a-z0-9-]+`, `wdN` = `wd` + digits, `site` `[A-Za-z0-9_-]+`); anything else raises `ValueError`, since the slug becomes part of a URL |
| List (search) | `POST https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` with `{"appliedFacets":{}, "limit":20, "offset":N, "searchText":term}` → `{total, jobPostings:[…], facets, userAuthenticated}`. **`limit` ≤ 20** (21 → HTTP 400). **`total` is only reliable on page 1**, and an offset past the end repeats page 1 — so paging stops at a short page or at page 1's `total` |
| Caps | up to **3 search terms × 3 pages** (60 postings per term, ≤ 9 requests per board); de-duplicated by `externalPath`. No terms → one blank search, first page only. A board list is a **search, never the whole board**: a job missing from it is unseen, not closed |
| Single job | `GET …/wday/cxs/<tenant>/<site>/job/<jobPostingId>` → `{jobPostingInfo, hiringOrganization, similarJobs?}`, or **404 when it does not exist**. Workday finds the posting by the whole last path part; the location part is ignored (so `/job/<id>` works), but the requisition id alone (`JR209985-1`) 404s. A 200 without `jobPostingInfo` is an error (unverified), never open; a 422 here (board moved) stays unverified |
| Job id | `jobPostingId` = last part of `externalPath` (`/job/San-Diego-CA/Clinical-Nurse-RN-…_JR209985-1` → `Clinical-Nurse-RN-…_JR209985-1`); the detail carries the same value as `jobPostingInfo.jobPostingId`. Long, and it changes if the employer renames the title (the old one then 404s) |
| Unknown board | unknown tenant → **422**; board on the wrong `wdN` host (moved) → **422**; unknown site on a real tenant → **404**. All three → `None` (board gone) |
| Title / URL | `title`. URL = `https://<tenant>.<wdN>.myworkdayjobs.com/<site><externalPath>` at list time; detail `externalUrl` (same page) |
| Location | list `locationsText` ("San Diego, CA", or just "3 Locations" — dropped, the detail has them); detail `location` + `additionalLocations[]`; country from `jobRequisitionLocation.country.alpha2Code` ("US"), else `country.descriptor` |
| Remote / workplace | detail `remoteType`, only on some tenants, free text: "On-site" / "Onsite" / "In-Office" → onsite, "Hybrid", "Remote"; "Not Remote" says nothing about hybrid, so it maps to no hint. Otherwise parsed from location text |
| Date | list `postedOn` is **text** ("Posted Yesterday", "Posted 30+ Days Ago") → `first_published: null` at list time; detail `startDate` (ISO date) |
| Description | detail `jobDescription` (HTML → `html_to_text`); none in the list |
| Pay | **no field.** `$` amounts appear inside some descriptions (bonuses as well as wages) — never parsed; `comp` is always `null` |
| Not available | pay; an ISO date or description at list time; full location list at list time; department |
| Cost | ≤ 9 POSTs per board per run, plus one GET per shortlisted job for `fetch_jd.py` |

## Politeness (all adapters)

User-Agent `job-scout/<version> (+https://github.com/sorawit-w/job-scout)`; 20 s timeout; ≤8
concurrent requests; one retry on timeout/429/5xx; per-run request caps; successful board lists
cached 6 h in `~/.job-scout/cache/`. All through `scripts/net.py`.

## USAJOBS (verified 2026-10-19)

One opt-in, cross-agency keyword search — not a per-company board. Slug is always `all`; key
`usajobs:all:<control number>`; `company` is the hiring agency. Adapter: `adapters/usajobs.py`.

| | |
|---|---|
| Key | Search needs a **free key per user** (form: https://developer.usajobs.gov/apirequest/). Keys "may not be shared or transferred", so job-scout ships none. Read **only** from `JOB_SCOUT_USAJOBS_KEY` + `JOB_SCOUT_USAJOBS_EMAIL`; both unset → `fetch_board` returns `None` with no request, and the caller says "USAJOBS skipped: no key" once. Never in a URL, a log line or a fixture. |
| Search | `GET https://data.usajobs.gov/api/Search?Keyword=…&ResultsPerPage=100&Page=N&SortField=opendate&SortDirection=Desc[&LocationName=…]` with headers `Host: data.usajobs.gov`, `User-Agent: <registered email>`, `Authorization-Key: <key>` (sent through `net.get_json(headers=…)`). Without a key → **401** (checked live 2026-10-19). Docs: https://developer.usajobs.gov/api-reference/get-api-search |
| Limits | `ResultsPerPage` ≤ 500, ≤ 10,000 rows per query. Adapter: ≤ 3 terms, ≤ 2 pages of 100 each (≤ 6 requests), de-duplicated by control number. No terms → `[]`. |
| Response | `SearchResult.SearchResultItems[]` = `{MatchedObjectId (control number), MatchedObjectDescriptor, RelevanceRank}`; paging from `SearchResult.UserArea.NumberOfPages` (a string). `fetch_board` returns these items as-is. |
| Title / URL | `PositionTitle`; `PositionURI` (the usajobs.gov job page — the government's own hiring site). A `:443` some responses add is stripped (reported by an open-source client, not seen here). |
| Location | `PositionLocation[].LocationName` (all of them), fallback `PositionLocationDisplay`; `CountryCode` is a country **name** ("United States") |
| Remote / workplace | `UserArea.Details.RemoteIndicator` → remote; else `TeleworkEligible` → hybrid; **both explicitly false → onsite**; absent → not said. These two field names come from open-source client models, not the official example — unverified. |
| Date / dept | `PublicationStartDate` → `first_published`; `DepartmentName` → `department` |
| Pay | `PositionRemuneration[0]`: `MinimumRange`/`MaximumRange` (strings in the official example), `RateIntervalCode` from the official code list (`/api/codelist/remunerationRateIntervalCodes`): `PA` year, `PM` month, `PD` day, `PH` hour; `BW` bi-weekly, `PW` **piece work** (not weekly), `FB`, `ST`, `SY`, `WC` → interval `null`. Currency USD. |
| Description | `UserArea.Details.JobSummary` + `MajorDuties` (string or list) + `QualificationSummary` |
| Single job | **Historic JOA, no key**: `GET https://data.usajobs.gov/api/historicjoa?USAJOBSControlNumbers=<n>` → `{data:[{usajobsControlNumber, positionOpeningStatus, positionCloseDate, positionExpireDate, positionTitle, hiringAgencyName, minimumSalary, maximumSalary, salaryType, teleworkEligible "Y"/"N", positionlocations[]…}]}`. Live check = "still accepting applications per USAJOBS": status `Accepting applications` **and** close/expire date not before today (a close date of today is still open). `Applications under review` (seen) or any other status → closed. **Unknown control number → 204 with an empty body** (checked live), which net.py reads as invalid JSON; the adapter maps exactly that case to `None`. JOA has no description, so `normalize(fetch_job(…))` has `description_text: null`. |
| Tests | Historic JOA fixtures are real recordings (open, under review, 204). **Search fixtures are synthetic**, hand-built from the documented shape — see `tests/fixtures/http/usajobs/README.md`. |
| Terms | Do not suggest OPM endorses job-scout; attribution encouraged, not required. |
