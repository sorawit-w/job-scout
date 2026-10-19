"""Helpers shared by the ATS adapters, so every adapter emits the same job schema.

What it does NOT do: no network (adapters call net.py) and no location logic
(normalize.py owns that).
"""
import datetime
import urllib.parse

import normalize
import state


def quote_slug(slug):
    """URL-escape a board slug; keeps case and dots (e.g. "Fliff", "affinity.co")."""
    return urllib.parse.quote(slug, safe=".-_~")


def iso_date(value):
    """'YYYY-MM-DD' from an ISO timestamp string or epoch milliseconds; None if absent/unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value / 1000.0, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    text = str(value)
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")[:25]).strftime("%Y-%m-%d")
    except ValueError:
        return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def comp(min_value, max_value, currency, interval):
    """Structured pay or None. Only called with values read from an ATS pay field."""
    if min_value is None and max_value is None:
        return None
    return {"min": min_value, "max": max_value, "currency": currency or None,
            "interval": interval, "source": "ats_field"}


def job(ats, slug, company, job_id, title, url, locations, remote_flag=None, workplace_hint=None,
        countries=None, department=None, first_published=None, pay=None, description_text=None):
    """Build one normalized job dict (schema: references/ats-notes.md).

    `countries` are structured country codes from the ATS; they are merged with the
    codes normalize.classify() finds in the location text.
    """
    cls = normalize.classify(locations, remote_flag=remote_flag, workplace_hint=workplace_hint)
    merged = sorted(set(cls["countries"]) | set(countries or []))
    scope = cls["remote_scope"]
    if cls["remote"] and scope is None and countries:
        scope = sorted(set(countries))  # "Remote" text plus a structured country (e.g. Lever's `country`)
    return {
        "key": "%s:%s:%s" % (ats, slug, job_id),
        "company": company,
        "ats": ats,
        "slug": slug,
        "job_id": str(job_id),
        "title": (title or "").strip(),
        "locations": cls["locations"],
        "countries": merged,
        "remote": cls["remote"],
        "remote_scope": scope,
        "workplace": cls["workplace"],
        "department": department,
        "first_published": first_published,
        "url": url,
        "comp": pay,
        "description_text": description_text,
        "fetched_at": state.now_iso(),
    }


def country_codes(names):
    """ISO codes for structured country names/codes ("United States", "USA", "ca").

    A bare two-letter value is already an ISO code — taken as-is, never looked up as a
    place (place_codes would read "LA" as Los Angeles and miss "DE").
    """
    out = set()
    for name in names:
        text = str(name).strip() if name else ""
        if len(text) == 2 and text.isalpha():
            out.add(text.upper())
        elif text:
            out.update(c for c in normalize.place_codes(text) if len(c) == 2)
    return sorted(out)
