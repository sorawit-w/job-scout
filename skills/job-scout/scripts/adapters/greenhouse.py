"""Greenhouse adapter (boards-api.greenhouse.io). Field notes: references/ats-notes.md.

What it does NOT do: no caching (probe.py) and no pay parsing from description text —
pay comes only from the single-job `pay_transparency` field.
"""
import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

BASE = "https://boards-api.greenhouse.io/v1/boards/%s/jobs"


def fetch_board(slug, budget=None):
    """Raw job list; [] for an empty board; None when the board is gone (404)."""
    data = net.get_json(BASE % _common.quote_slug(slug) + "?content=true", budget)
    if data is None:
        return None
    return data.get("jobs") or []


def fetch_job(slug, job_id, budget=None):
    """Raw single job with pay ranges, or None when it has closed (404)."""
    return net.get_json(BASE % _common.quote_slug(slug) + "/%s?pay_transparency=true" % job_id, budget)


def _pay(raw):
    ranges = raw.get("pay_input_ranges") or []
    if not ranges:
        return None
    r = ranges[0]
    title = (r.get("title") or "").lower()
    interval = "year" if ("annual" in title or "year" in title) else None
    lo, hi = r.get("min_cents"), r.get("max_cents")
    return _common.comp(lo / 100 if lo is not None else None, hi / 100 if hi is not None else None,
                        r.get("currency_type"), interval)


def normalize(raw, slug, company):
    locations = []
    name = (raw.get("location") or {}).get("name")
    if name:
        locations.append(name)
    for office in raw.get("offices") or []:
        loc = office.get("location")
        if loc and loc not in locations:
            locations.append(loc)
    departments = raw.get("departments") or []
    return _common.job(
        "greenhouse", slug, company, raw.get("id"), raw.get("title"), raw.get("absolute_url"), locations,
        department=departments[0].get("name") if departments else None,
        first_published=_common.iso_date(raw.get("first_published") or raw.get("updated_at")),
        pay=_pay(raw),
        description_text=norm.html_to_text(raw.get("content")) or None,
    )
