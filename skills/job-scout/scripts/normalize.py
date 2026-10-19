"""Turn raw ATS job fields into the normalized job schema (HANDOFF section 5).

Pure functions, Python 3.9+ standard library only:

- split_locations / place_codes / classify: location strings -> places, countries,
  remote flag, Remote scope and workplace mode.
- html_to_text: job-description HTML (including Greenhouse's double-escaped HTML) -> text.
- title_stem / company_norm / collapse_variants: merge Regional variants of one role
  into a single row that keeps every posting in variants[].

Usage:
    from normalize import classify, collapse_variants
    loc = classify("Remote | United States | Poland", remote_flag=None, workplace_hint="Remote")
    # {'locations': [...], 'countries': ['PL', 'US'], 'remote': True,
    #  'remote_scope': ['PL', 'US'], 'workplace': 'remote'}
    roles = collapse_variants(jobs)  # jobs = list of normalized job dicts

What it does NOT do:
- No I/O and no network. No geocoding: places come from the small built-in table below.
  An unknown city resolves to nothing; it is never guessed.
- It does not decide whether a role matches the user (filters live elsewhere).
- Names are matched on word boundaries only, never as substrings ("Jerusalem" is not "usa").
"""
import html
import re
import unicodedata
from html.parser import HTMLParser

REGION_CODES = ("AMER", "EU", "EMEA", "APAC", "ANY")

# ---- place table. Names written in ALL CAPS match case-sensitively; others ignore case.
_REGIONS = {
    "AMER": "Americas|AMER|North America",
    "EU": "Europe|EU|European Union",
    "EMEA": "EMEA",
    "APAC": "APAC|Asia Pacific|Asia-Pacific",
    "ANY": "Anywhere|Worldwide|Global",
    "LATAM": "LATAM|Latin America",
    "ANZ": "ANZ",
    "DACH": "DACH",
    "NORDICS": "Nordics",
}
_COUNTRIES = {
    "US": "United States|United States of America|USA|US|U.S.|U.S.A.",
    "CA": "Canada", "GB": "United Kingdom|UK|U.K.|Great Britain|Britain|England|Scotland|Wales|Northern Ireland",
    "IE": "Ireland", "DE": "Germany", "FR": "France", "NL": "Netherlands|The Netherlands|Holland",
    "BE": "Belgium", "PT": "Portugal", "ES": "Spain", "IT": "Italy", "PL": "Poland", "SE": "Sweden",
    "NO": "Norway", "DK": "Denmark", "FI": "Finland", "CH": "Switzerland", "AT": "Austria",
    "CZ": "Czech Republic|Czechia", "RO": "Romania", "HU": "Hungary", "GR": "Greece", "UA": "Ukraine",
    "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia", "RS": "Serbia", "HR": "Croatia",
    "BG": "Bulgaria", "TR": "Turkey|Türkiye", "IL": "Israel", "AE": "United Arab Emirates|UAE",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "EG": "Egypt", "IN": "India",
    "PK": "Pakistan", "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia", "PH": "Philippines",
    "VN": "Vietnam", "TH": "Thailand", "JP": "Japan", "KR": "South Korea|Korea", "CN": "China",
    "HK": "Hong Kong", "TW": "Taiwan", "AU": "Australia", "NZ": "New Zealand", "BR": "Brazil|Brasil",
    "MX": "Mexico", "CO": "Colombia", "AR": "Argentina", "CL": "Chile", "PE": "Peru",
    "UY": "Uruguay", "CR": "Costa Rica",
}
_US_STATES = (
    "AL Alabama|AK Alaska|AZ Arizona|AR Arkansas|CA California|CO Colorado|CT Connecticut|"
    "DE Delaware|FL Florida|GA Georgia|HI Hawaii|ID Idaho|IL Illinois|IN Indiana|IA Iowa|"
    "KS Kansas|KY Kentucky|LA Louisiana|ME Maine|MD Maryland|MA Massachusetts|MI Michigan|"
    "MN Minnesota|MS Mississippi|MO Missouri|MT Montana|NE Nebraska|NV Nevada|NH New Hampshire|"
    "NJ New Jersey|NM New Mexico|NY New York|NC North Carolina|ND North Dakota|OH Ohio|"
    "OK Oklahoma|OR Oregon|PA Pennsylvania|RI Rhode Island|SC South Carolina|SD South Dakota|"
    "TN Tennessee|TX Texas|UT Utah|VT Vermont|VA Virginia|WA Washington|WV West Virginia|"
    "WI Wisconsin|WY Wyoming|DC District of Columbia"
)
_CA_PROVINCES = (
    "AB Alberta|BC British Columbia|MB Manitoba|NB New Brunswick|NL Newfoundland and Labrador|"
    "NS Nova Scotia|ON Ontario|PE Prince Edward Island|QC Quebec|SK Saskatchewan|"
    "YT Yukon|NT Northwest Territories|NU Nunavut"
)
_CITIES = {
    "US": "San Francisco|SF|Bay Area|NYC|New York City|Seattle|Austin|Boston|Chicago|Los Angeles|LA|"
          "Denver|Atlanta|Miami|Foster City|Palo Alto|Mountain View|Menlo Park|San Jose|Oakland|"
          "Brooklyn|Washington DC|DC|San Diego|Sunnyvale|Redwood City|San Mateo|Santa Clara|"
          "Philadelphia|Pittsburgh|Portland|Salt Lake City|Phoenix|Dallas|Houston|Raleigh|"
          "Nashville|Minneapolis|Detroit",
    "CA": "Toronto|Vancouver|Montreal|Montréal|Ottawa|Calgary|Edmonton",
    "GB": "London|Manchester|Edinburgh|Bristol", "IE": "Dublin",
    "DE": "Berlin|Munich|Hamburg|Frankfurt", "FR": "Paris", "NL": "Amsterdam|Rotterdam",
    "PT": "Lisbon|Porto", "ES": "Madrid|Barcelona", "PL": "Warsaw|Krakow|Kraków|Wroclaw",
    "SE": "Stockholm", "CH": "Zurich|Zürich|Geneva", "IL": "Tel Aviv|Jerusalem|Haifa",
    "IN": "Bangalore|Bengaluru|Hyderabad|Mumbai|Pune|Delhi|New Delhi|Gurgaon|Gurugram|Chennai|Noida",
    "AU": "Sydney|Melbourne", "JP": "Tokyo", "BR": "São Paulo", "MX": "Mexico City|Guadalajara",
    "CO": "Bogotá|Medellín", "AR": "Buenos Aires", "GE": "Tbilisi", "DK": "Copenhagen",
    "AT": "Vienna", "CZ": "Prague", "IT": "Milan|Rome", "KR": "Seoul", "FI": "Helsinki",
    "NO": "Oslo", "EE": "Tallinn", "UA": "Kyiv", "RO": "Bucharest", "TR": "Istanbul",
    "AE": "Dubai", "ZA": "Cape Town", "NG": "Lagos", "KE": "Nairobi", "NZ": "Auckland",
}
_AMBIGUOUS = {"georgia"}  # US state or country: counts as a place but gives no code alone


def _fold(s):
    """Strip accents, turn "U.S." into "US", collapse whitespace. Keeps case."""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group(0).replace(".", ""), s)
    return " ".join(s.split())


def _key(name):
    return name if name.isupper() else name.lower()


_NAMES = {}  # key -> (code or None, kind) ; kind: region | country | state | city
_SUBDIV = {}  # 2-letter state/province code -> country


def _add(names, code, kind):
    for n in names.split("|"):
        k = _key(_fold(n))
        _NAMES[k] = (None if k in _AMBIGUOUS else code, kind)


for _c, _n in _REGIONS.items():
    _add(_n, _c, "region")
for _c, _n in _COUNTRIES.items():
    _add(_n, _c, "country")
for _country, _table in (("US", _US_STATES), ("CA", _CA_PROVINCES)):
    for _entry in _table.split("|"):
        _code, _name = _entry.split(" ", 1)
        _SUBDIV[_code] = _country
        _add(_name, _country, "state")
for _c, _n in _CITIES.items():
    _add(_n, _c, "city")

_NAME_RE = re.compile(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % "|".join(
    re.escape(n) if n.isupper() else "(?i:%s)" % re.escape(n)
    for n in sorted(_NAMES, key=len, reverse=True)))
_COMMA_CODE_RE = re.compile(r",\s*([A-Z]{2})(?![A-Za-z])")  # state codes count only after a comma
_REMOTE_RE = re.compile(r"\b(?:remote|anywhere|distributed|work from home|wfh)\b", re.I)
_MODE_RE = re.compile(r"\b(?:remote|anywhere|distributed|hybrid|on-?site|in office|work from home|wfh)\b", re.I)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
_MODES = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "inoffice": "onsite",
          "office": "onsite", "inperson": "onsite"}


def place_codes(loc):
    """Sorted country (ISO alpha-2) and region codes one location string names."""
    t = _fold(loc or "")
    # Exact key first ("US"), then lowercase: all-caps text like "CANADA" matched case-insensitively.
    hits = [_NAMES.get(m.group(0)) or _NAMES[m.group(0).lower()] for m in _NAME_RE.finditer(t)]
    named = {c for c, k in hits if c and k in ("country", "city")}
    for m in _COMMA_CODE_RE.finditer(t):
        # "Berlin, DE" / "Toronto, CA": the code repeats a named country, so it is not a US state.
        if m.group(1) not in named and m.group(1) in _SUBDIV:
            hits.append((_SUBDIV[m.group(1)], "state"))
    broad = any(c and k in ("country", "state") for c, k in hits)
    # A named country/state/province beats a city ("London, ON" is Canada).
    return sorted({c for c, k in hits if c and not (broad and k == "city")})


def _is_place(s, allow_mode=False):
    """True when s is only place names (plus work-mode words if allow_mode) and punctuation."""
    t = _fold(s or "")
    rest = _NAME_RE.sub(" ", t)
    rest = _COMMA_CODE_RE.sub(lambda m: " " if m.group(1) in _SUBDIV or m.group(1) in _COUNTRIES else m.group(0), rest)
    if allow_mode:
        rest = _MODE_RE.sub(" ", rest)
    return rest != t and not re.search(r"[A-Za-z]", rest)


def _dedupe(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def split_locations(text):
    """Split one location string into a list of locations (order kept, no duplicates)."""
    out = []
    for part in re.split(r"\s*[|;·]\s*|\s+/\s+", text or ""):
        pieces = re.split(r"\s+(?:or|and)\s+", part, flags=re.I)
        if len(pieces) > 1 and all(_is_place(p) for p in pieces):
            out.extend(pieces)
        else:
            out.append(part)
    return _dedupe(p.strip() for p in out if p.strip())


def _mode(hint):
    return _MODES.get(re.sub(r"[^a-z]", "", str(hint).lower())) if hint else None


def classify(locations, remote_flag=None, workplace_hint=None):
    """Locations -> {locations, countries, remote, remote_scope, workplace}."""
    if locations is None or isinstance(locations, str):
        locations = [locations]
    locs = _dedupe(p for loc in locations for p in split_locations(loc))
    codes = {loc: place_codes(loc) for loc in locs}
    hint = _mode(workplace_hint)
    remote_locs = [loc for loc in locs if _REMOTE_RE.search(loc)]

    remote = None
    if remote_flag is True or remote_locs or hint == "remote":
        remote = True
    elif remote_flag is False or hint == "onsite":
        remote = False

    scope = None
    if remote:
        # Places named with the remote evidence; if it names none ("Remote | US | Poland"), all places.
        found = {c for loc in remote_locs for c in codes[loc]} or {c for loc in locs for c in codes[loc]}
        scope = sorted(found) or None

    workplace = hint or ("hybrid" if any(_HYBRID_RE.search(loc) for loc in locs) else None)
    if workplace is None and remote:
        workplace = "remote"
    return {
        "locations": locs,
        "countries": sorted({c for cs in codes.values() for c in cs if c not in REGION_CODES}),
        "remote": remote,
        "remote_scope": scope,
        "workplace": workplace,
    }


class _TextParser(HTMLParser):
    BLOCK = {"p", "div", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("br", "tr"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.out.append("\n\n")
        elif tag == "tr":
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(s):
    """HTML (possibly escaped twice, as Greenhouse sends it) -> readable plain text."""
    if not s:
        return ""
    for _ in range(3):
        un = html.unescape(s)
        if un == s:
            break
        s = un
    p = _TextParser()
    p.feed(s)
    p.close()
    lines = [" ".join(line.split()) for line in "".join(p.out).split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def title_stem(title):
    """Lowercase title without a trailing place/region/Remote suffix ("X - Americas" -> "x")."""
    t = " ".join((title or "").split())
    while True:
        m = re.match(r"^(.*\S)\s*\(([^()]*)\)$", t)
        if not (m and _is_place(m.group(2), allow_mode=True)):
            m = re.match(r"^(.*\S)(?:\s+[-–—]\s+|\s*,\s+)(.+)$", t)
            if not (m and _is_place(m.group(2), allow_mode=True)):
                return t.lower()
        t = m.group(1)


def company_norm(name):
    """Company name for grouping: lowercase, no punctuation, no inc/llc/ltd/corp/gmbh suffix."""
    words = re.sub(r"[^\w\s]", " ", (name or "").lower()).split()
    while words and words[-1] in ("inc", "llc", "ltd", "corp", "gmbh"):
        words.pop()
    return " ".join(words)


def collapse_variants(jobs):
    """Merge postings with the same company, title stem and department into one role row with
    variants[]. Department is part of the key: big boards post "Software Engineer" in many teams."""
    groups = {}
    for j in jobs:
        dept = re.sub(r"\s+", " ", str(j.get("department") or "").strip().lower())
        groups.setdefault((company_norm(j.get("company")), title_stem(j.get("title")), dept), []).append(j)
    rows = []
    for members in groups.values():
        # Earliest first; None dates last; sorted() is stable, so ties keep input order.
        members = sorted(members, key=lambda j: (j.get("first_published") is None, j.get("first_published") or ""))
        row = dict(members[0])
        remotes = [m.get("remote") for m in members]
        scopes = [m.get("remote_scope") for m in members if m.get("remote_scope") is not None]
        row["locations"] = _dedupe(loc for m in members for loc in (m.get("locations") or []))
        row["countries"] = sorted({c for m in members for c in (m.get("countries") or [])})
        row["remote"] = True if True in remotes else (False if all(r is False for r in remotes) else None)
        row["remote_scope"] = sorted({c for s in scopes for c in s}) if scopes else None
        if row["remote"]:
            row["workplace"] = "remote"  # some posting of this role can be done remotely
        row["variants"] = [{k: m.get(k) for k in ("job_id", "key", "title", "url", "locations", "first_published")}
                           for m in members]
        rows.append(row)
    return rows
