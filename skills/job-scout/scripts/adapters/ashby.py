"""Ashby adapter (api.ashbyhq.com posting API). Field notes: references/ats-notes.md.

Ashby has no single-job endpoint: a job missing from a fresh board list is closed.

What it does NOT do: no caching (probe.py) and no pay parsing from description text —
pay comes only from `compensation` salary components.
"""
import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

BASE = "https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true"
_INTERVALS = {"1 YEAR": "year", "1 MONTH": "month", "1 WEEK": "week", "1 DAY": "day", "1 HOUR": "hour"}


def fetch_board(slug, budget=None):
    """Raw listed jobs; [] for an empty board; None when the board is gone (404)."""
    data = net.get_json(BASE % _common.quote_slug(slug), budget)
    if data is None:
        return None
    return [j for j in data.get("jobs") or [] if j.get("isListed", True)]


def fetch_job(slug, job_id, budget=None):
    """The job from a fresh board list, or None if it is no longer listed (closed)."""
    jobs = fetch_board(slug, budget)
    for raw in jobs or []:
        if str(raw.get("id")) == str(job_id):
            return raw
    return None


def _pay(raw):
    for tier in (raw.get("compensation") or {}).get("compensationTiers") or []:
        for c in tier.get("components") or []:
            if c.get("compensationType") == "Salary":
                return _common.comp(c.get("minValue"), c.get("maxValue"), c.get("currencyCode"),
                                    _INTERVALS.get((c.get("interval") or "").upper()))
    return None


def normalize(raw, slug, company):
    locations, country_names = [], []
    entries = [{"location": raw.get("location"), "address": raw.get("address")}] + list(raw.get("secondaryLocations") or [])
    for entry in entries:
        loc = entry.get("location")
        if loc and loc not in locations:
            locations.append(loc)
        postal = ((entry.get("address") or {}).get("postalAddress") or {})
        country_names.append(postal.get("addressCountry"))
    description = raw.get("descriptionPlain") or norm.html_to_text(raw.get("descriptionHtml"))
    return _common.job(
        "ashby", slug, company, raw.get("id"), raw.get("title"), raw.get("jobUrl") or raw.get("applyUrl"), locations,
        remote_flag=raw.get("isRemote"), workplace_hint=raw.get("workplaceType"),
        countries=_common.country_codes(country_names),
        department=raw.get("department") or raw.get("team"),
        first_published=_common.iso_date(raw.get("publishedAt")),
        pay=_pay(raw),
        description_text=description or None,
    )
