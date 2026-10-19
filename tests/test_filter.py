import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import filter as jfilter
import state

TODAY = datetime.date(2026, 10, 18)
USD = {"min": 190000, "max": 240000, "currency": "USD", "interval": "year", "source": "ats_field"}


def profile(**over):
    """Synthetic senior frontend persona (HANDOFF section 4 example)."""
    p = {"schema": 1,
         "target_roles": ["Design Engineer", "Staff Frontend Engineer", "UI Platform Engineer", "Design Systems Engineer"],
         "title_synonyms": ["Frontend Engineer", "UI Engineer"], "title_keywords": ["react"],
         "title_exclusions": ["electrical", "rtl", "mechanical", "product designer"],
         "seniority": ["Senior", "Staff", "Lead"], "track": "ic",
         "home_base": "Pasadena, CA", "commute_cities": ["Los Angeles", "Burbank"],
         "work_modes": ["remote", "hybrid"], "remote_scope": ["US"], "needs_sponsorship": "no",
         "base_pay_floor": {"amount": 180000, "currency": "USD", "interval": "year"},
         "companies_exclude": ["Current Co"], "hide_no_pay": False, "recency_flag_days": 90}
    p.update(over)
    return p


_N = [0]


def job(title="Senior Frontend Engineer", company="Acme", locations=("Remote - US",), remote=True,
        scope=("US",), workplace="remote", comp=USD, date="2026-10-01", variants=None, key=None, ats="ashby"):
    _N[0] += 1
    j = {"key": key or "%s:acme:%d" % (ats, _N[0]), "job_id": str(_N[0]), "company": company, "ats": ats,
         "slug": "acme", "title": title, "locations": list(locations), "countries": [],
         "remote": remote, "remote_scope": list(scope) if scope is not None else None,
         "workplace": workplace, "department": None, "first_published": date,
         "url": "https://jobs.ashbyhq.com/acme/%d" % _N[0], "comp": comp, "description_text": None,
         "fetched_at": "2026-10-18T00:00:00Z"}
    j["variants"] = variants if variants is not None else [
        {k: j[k] for k in ("job_id", "key", "ats", "slug", "title", "url", "locations", "first_published",
                           "countries", "remote", "remote_scope", "workplace", "comp")}]
    return j


def local(title="Senior Frontend Engineer", city="Los Angeles, CA", workplace="hybrid", **kw):
    return job(title, locations=(city,), remote=False, scope=None, workplace=workplace, **kw)


def run(jobs, limit=150, **pover):
    return jfilter.run_filter(jobs, profile(**pover), limit=limit, today=TODAY)


def outcome(j, **pover):
    """('strong'|'borderline', candidate) when kept, else (removal reason, None)."""
    out, cands = run([j], **pover)
    if cands:
        return cands[0]["match"], cands[0]
    return [k for k, v in out["counts"]["removed"].items() if v][0], None


class ProfileFixtureTest(unittest.TestCase):
    def test_test_profile_is_valid(self):
        self.assertEqual(state.validate_profile(profile()), [])


class CompanyTest(unittest.TestCase):
    def test_current_employer_excluded_by_normalized_name(self):
        self.assertEqual(outcome(job(company="Current Co, Inc."))[0], "company")

    def test_other_company_kept(self):
        self.assertEqual(outcome(job(company="Currently"))[0], "strong")


class WorkModeLocationTest(unittest.TestCase):
    def test_remote_us_passes_clean(self):
        m, c = outcome(job())
        self.assertEqual(m, "strong")
        self.assertEqual(c["flags"], [])

    def test_remote_poland_removed_for_us_scope(self):
        self.assertEqual(outcome(job(locations=("Remote - Poland",), scope=("PL",)))[0], "remote_scope")

    def test_americas_kept_with_flag(self):
        m, c = outcome(job(locations=("Remote - Americas",), scope=("AMER",)))
        self.assertEqual(m, "strong")
        self.assertIn("Americas — check US eligibility", c["flags"])

    def test_bare_remote_kept_with_flag(self):
        m, c = outcome(job(locations=("Remote",), scope=None))
        self.assertEqual(m, "strong")
        self.assertIn("remote scope not stated", c["flags"])

    def test_anywhere_passes_clean(self):
        self.assertEqual(outcome(job(scope=("ANY",)))[1]["flags"], [])

    def test_la_hybrid_via_commute_city(self):
        m, c = outcome(local())
        self.assertEqual(m, "strong")
        self.assertEqual(c["flags"], [])

    def test_home_base_city_counts_as_local(self):
        self.assertEqual(outcome(local(city="Pasadena, CA"), commute_cities=[])[0], "strong")

    def test_city_match_is_word_boundary(self):
        self.assertEqual(outcome(local(city="Orangeburg, SC"), commute_cities=["Orange"])[0], "location")

    def test_commute_city_in_another_state_removed(self):
        self.assertEqual(outcome(local(city="Burbank, WA"))[0], "location")
        self.assertEqual(outcome(local(city="Burbank, Washington, United States"))[0], "location")

    def test_commute_city_same_or_unstated_state_kept(self):
        self.assertEqual(outcome(local(city="Burbank, California"))[0], "strong")
        self.assertEqual(outcome(local(city="Burbank Medical Pavilion"))[0], "strong")

    def test_commute_city_written_with_its_state_allows_that_state(self):
        md = local(city="Bethesda, MD")
        self.assertEqual(outcome(md, home_base="Arlington, VA", commute_cities=["Bethesda"])[0], "location")
        self.assertEqual(outcome(md, home_base="Arlington, VA", commute_cities=["Bethesda, MD"])[0], "strong")

    def test_onsite_removed_when_only_remote_and_hybrid_wanted(self):
        self.assertEqual(outcome(local(workplace="onsite"))[0], "work_mode")

    def test_onsite_kept_when_wanted(self):
        self.assertEqual(outcome(local(workplace="onsite"), work_modes=["onsite"])[0], "strong")

    def test_unknown_workplace_in_commute_city_kept_with_flag(self):
        m, c = outcome(local(workplace=None))
        self.assertEqual(m, "strong")
        self.assertIn("work mode not stated", c["flags"])

    def test_remote_job_removed_when_remote_not_wanted(self):
        self.assertEqual(outcome(job(), work_modes=["hybrid"])[0], "work_mode")

    def test_far_city_removed_as_location(self):
        self.assertEqual(outcome(local(city="New York, NY"))[0], "location")


def elsewhere(city, countries, workplace="hybrid", **kw):
    """A non-remote job outside the commute cities, with parsed countries on the job and its variant."""
    j = local(city=city, workplace=workplace, **kw)
    j["countries"] = list(countries)
    for v in j["variants"]:
        v["countries"] = list(countries)
    return j


class RelocationTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(outcome(elsewhere("San Francisco, CA", ["US"]))[0], "location")

    def test_open_to_relocation_keeps_hybrid_elsewhere_with_a_flag(self):
        res, cand = outcome(elsewhere("San Francisco, CA", ["US"]), open_to_relocation=True)
        self.assertEqual(res, "strong")
        self.assertIn("relocation: hybrid in San Francisco, CA", cand["flags"])

    def test_relocation_ranks_after_a_clean_local_match(self):
        sf = elsewhere("San Francisco, CA", ["US"], key="sf", date="2026-10-10")
        la = local(key="la", date="2026-09-01")
        out, _ = run([sf, la], open_to_relocation=True)
        self.assertEqual([c["key"] for c in out["candidates"]], ["la", "sf"])

    def test_only_home_and_remote_scope_countries(self):
        self.assertEqual(outcome(elsewhere("London", ["GB"]), open_to_relocation=True)[0], "location")
        res, _ = outcome(elsewhere("Toronto", ["CA"]), open_to_relocation=True, remote_scope=["US", "CA"])
        self.assertEqual(res, "strong")

    def test_mode_must_still_be_wanted(self):
        res, _ = outcome(elsewhere("San Francisco, CA", ["US"], workplace="onsite"), open_to_relocation=True)
        self.assertIsNotNone(res)
        self.assertNotIn(res, ("strong", "borderline"))

    def test_near_miss_names_the_unwanted_mode(self):
        out, _ = run([elsewhere("San Francisco, CA", ["US"], workplace="onsite", title="Design Engineer")],
                     open_to_relocation=True)
        self.assertEqual(out["near_misses"][0]["reason"], "onsite in San Francisco, CA — onsite is not a mode you picked")

    def test_unparsed_location_is_not_relocatable(self):
        self.assertEqual(outcome(elsewhere("Somewhere", []), open_to_relocation=True)[0], "location")

    def test_unknown_mode_elsewhere_kept_with_both_flags(self):
        res, cand = outcome(elsewhere("San Francisco, CA", ["US"], workplace=None), open_to_relocation=True)
        self.assertEqual(res, "strong")
        self.assertEqual(cand["flags"][:2], ["work mode not stated", "relocation: onsite or hybrid in San Francisco, CA"])
        self.assertEqual(outcome(elsewhere("San Francisco, CA", ["US"], workplace=None))[0], "location")
        self.assertEqual(outcome(elsewhere("London", ["GB"], workplace=None), open_to_relocation=True)[0], "location")
        self.assertEqual(outcome(elsewhere("San Francisco, CA", ["US"], workplace=None), open_to_relocation=True,
                                 work_modes=["remote"])[0], "location")

    def test_flag_names_a_real_place_not_the_word_hybrid(self):
        j = elsewhere("Hybrid", ["US"])
        j["locations"] = j["variants"][0]["locations"] = ["Hybrid", "Austin, TX"]
        res, cand = outcome(j, open_to_relocation=True)
        self.assertIn("relocation: hybrid in Austin, TX", cand["flags"])

    def test_amer_scope_lets_relocation_reach_canada(self):
        res, _ = outcome(elsewhere("Toronto", ["CA"]), open_to_relocation=True, remote_scope=["AMER"])
        self.assertEqual(res, "strong")

    def test_no_resolvable_country_means_no_relocation(self):
        p = state.with_profile_defaults(profile(open_to_relocation=True, home_base=None, remote_scope=["EU"]))
        self.assertIsNone(jfilter._relocation_countries(p))
        self.assertEqual(outcome(elsewhere("London", ["GB"]), open_to_relocation=True, home_base=None,
                                 remote_scope=[])[0], "location")
        anywhere = state.with_profile_defaults(profile(open_to_relocation=True, remote_scope=["ANY"]))
        self.assertEqual(jfilter._relocation_countries(anywhere), frozenset())


class RequestedScopeTest(unittest.TestCase):
    def test_any_in_the_profile_accepts_every_country(self):
        res, _ = outcome(job(locations=("Remote - UK",), scope=("GB",)), remote_scope=["ANY"])
        self.assertIn(res, ("strong", "borderline"))

    def test_amer_in_the_profile_accepts_a_us_role(self):
        res, cand = outcome(job(), remote_scope=["AMER"])
        self.assertIn(res, ("strong", "borderline"))
        self.assertEqual(cand["flags"], [])


class DisplayVariantTest(unittest.TestCase):
    def test_us_remote_variant_applied_with_its_pay(self):
        eur = {"min": 80000, "max": 100000, "currency": "EUR", "interval": "year", "source": "ats_field"}
        variants = [
            {"job_id": "e1", "key": "ashby:acme:e1", "title": "Design Engineer - EU", "url": "https://x/e1",
             "locations": ["Remote - Portugal"], "first_published": "2026-09-01", "countries": ["PT"],
             "remote": True, "remote_scope": ["PT"], "workplace": "remote", "comp": eur},
            {"job_id": "u1", "key": "ashby:acme:u1", "title": "Design Engineer - Americas", "url": "https://x/u1",
             "locations": ["Remote - US"], "first_published": "2026-09-02", "countries": ["US"],
             "remote": True, "remote_scope": ["US"], "workplace": "remote", "comp": USD},
        ]
        row = job("Design Engineer - EU", locations=("Remote - Portugal", "Remote - US"), scope=("PT", "US"),
                  comp=eur, key="ashby:acme:e1", variants=variants)
        out, cands = run([row])
        c = cands[0]
        self.assertEqual(c["key"], "ashby:acme:u1")
        self.assertEqual(c["url"], "https://x/u1")
        self.assertEqual(c["title"], "Design Engineer - Americas")
        self.assertEqual(c["locations"], ["Remote - US"])
        self.assertEqual(c["remote_scope"], ["US"])
        self.assertEqual(c["comp"]["currency"], "USD")
        self.assertEqual(c["flags"], [])
        self.assertEqual(out["candidates"][0]["pay"], "$190,000–$240,000/yr")
        self.assertEqual(out["candidates"][0]["where"], "Remote - US")

    def test_local_variant_beats_unusable_primary(self):
        variants = [
            {"job_id": "p1", "key": "k:p1", "title": "Frontend Engineer", "url": "u1", "locations": ["Remote - Poland"],
             "first_published": "2026-09-01", "countries": ["PL"], "remote": True, "remote_scope": ["PL"],
             "workplace": "remote", "comp": None},
            {"job_id": "l1", "key": "k:l1", "title": "Frontend Engineer", "url": "u2", "locations": ["Los Angeles, CA"],
             "first_published": "2026-09-03", "countries": ["US"], "remote": False, "remote_scope": None,
             "workplace": "hybrid", "comp": USD},
        ]
        row = job("Frontend Engineer", locations=("Remote - Poland", "Los Angeles, CA"), scope=("PL",), variants=variants)
        m, c = outcome(row)
        self.assertEqual(c["key"], "k:l1")
        self.assertEqual(c["workplace"], "hybrid")

    def test_no_usable_variant_falls_back_to_primary_and_is_removed(self):
        variants = [
            {"job_id": "p1", "key": "k:p1", "title": "Frontend Engineer", "url": "u1", "locations": ["Remote - Poland"],
             "first_published": "2026-09-01", "countries": ["PL"], "remote": True, "remote_scope": ["PL"],
             "workplace": "remote", "comp": None},
            {"job_id": "p2", "key": "k:p2", "title": "Frontend Engineer", "url": "u2", "locations": ["Berlin"],
             "first_published": "2026-09-03", "countries": ["DE"], "remote": False, "remote_scope": None,
             "workplace": "onsite", "comp": None},
        ]
        row = job("Frontend Engineer", locations=("Remote - Poland", "Berlin"), scope=("PL",), variants=variants)
        self.assertEqual(outcome(row)[0], "remote_scope")

    def test_row_without_variants_still_works(self):
        row = job()
        del row["variants"]
        self.assertEqual(outcome(row)[0], "strong")


class SeniorityTrackTest(unittest.TestCase):
    def test_junior_levels_removed_for_senior_profile(self):
        for title in ("Software Engineer II, Frontend", "Frontend Engineer I", "Frontend Engineer Intern",
                      "Frontend Engineering Internship", "Junior Frontend Engineer", "Jr. Frontend Engineer",
                      "Associate Frontend Engineer", "New Grad Frontend Engineer", "Entry-Level UI Engineer"):
            self.assertEqual(outcome(job(title))[0], "seniority", title)

    def test_titles_without_level_kept(self):
        self.assertEqual(outcome(job("Frontend Engineer"))[0], "strong")
        self.assertEqual(outcome(job("Frontend Engineer III"))[0], "strong")
        self.assertEqual(outcome(job("Frontend Engineer, I/O Platform"))[0], "strong")

    def test_levels_kept_when_profile_wants_mid(self):
        self.assertEqual(outcome(job("Frontend Engineer II"), seniority=["Mid", "Senior"])[0], "strong")

    def test_manager_titles_removed_for_ic_track(self):
        for title in ("Engineering Manager, Frontend", "Director of Design Engineering", "Head of Frontend",
                      "VP, UI Platform"):
            self.assertEqual(outcome(job(title))[0], "track", title)

    def test_manager_word_in_a_target_role_is_not_a_track_miss(self):
        pm = {"target_roles": ["Product Manager"], "title_synonyms": [], "title_keywords": [], "title_exclusions": []}
        self.assertEqual(outcome(job("Senior Product Manager"), **pm)[0], "strong")
        self.assertEqual(outcome(job("Engineering Manager, Frontend"))[0], "track")

    def test_manager_titles_kept_for_either_track(self):
        self.assertIn(outcome(job("Engineering Manager, Frontend"), track="either")[0], ("strong", "borderline"))


class TitleTest(unittest.TestCase):
    def test_strong_needs_the_role_words_as_a_phrase(self):
        p = jfilter.state.with_profile_defaults(profile())
        self.assertEqual(jfilter.title_match(jfilter.words("Senior Design Engineer, Growth"), p), "strong")
        self.assertEqual(jfilter.title_match(jfilter.words("Senior Frontend Engineer, Platform"), p), "strong")
        # Both words present but not as the role: a weaker signal, not "strong".
        self.assertNotEqual(jfilter.title_match(jfilter.words("AV Engineer, Builds and Design"), p), "strong")

    def test_generic_engineering_title_matched_on_its_description(self):
        # Live 49 boards, 2026-10-19: "Staff Software Engineer, Dashboard Product" was frontend work.
        fe = job("Staff Software Engineer, Dashboard Product")
        fe["description_text"] = ("You will build our dashboard in React and TypeScript, own the frontend architecture "
                                  "and grow our design system.")
        kw = {"title_keywords": ["react", "frontend", "design system", "ui", "web"]}
        res, cand = outcome(fe, **kw)
        self.assertEqual(res, "borderline")
        self.assertIn("title is generic — matched on the description", cand["flags"])
        weak = job("Staff Software Engineer, Payments")
        weak["description_text"] = "Our web UI uses React; you build the Go services behind it."  # one real keyword
        self.assertEqual(outcome(weak, **kw)[0], "title")
        sales = job("Account Executive")
        sales["description_text"] = "Sell our React and frontend tooling to design system teams."
        self.assertEqual(outcome(sales, **kw)[0], "title")
        one = job("Staff Software Engineer, Platform")
        one["description_text"] = "Help our design system and design systems tooling grow."
        self.assertEqual(outcome(one, title_keywords=["design system", "design systems"])[0], "title")

    def test_a_weak_word_alone_is_not_a_match(self):
        # Live 49 boards, 2026-10-19: "systems" from "Design Systems Engineer" pulled in IT roles.
        p = jfilter.state.with_profile_defaults(profile())
        for title in ("IT Systems Engineer", "Financial Systems Engineer", "Platform Engineer, Data"):
            self.assertIsNone(jfilter.title_match(jfilter.words(title), p), title)
        for title in ("Frontend Developer", "Design Systems Lead"):
            self.assertEqual(jfilter.title_match(jfilter.words(title), p), "borderline", title)

    def test_handoff_false_positives_excluded(self):
        for title, phrase in (("Data Center Design Engineer, Electrical", "electrical"),
                              ("RTL Design Engineer", "rtl"),
                              ("Mechanical Design Engineer", "mechanical"),
                              ("Product Designer, Design Systems", "product designer")):
            out, cands = run([job(title)])
            self.assertEqual(out["counts"]["removed"]["title_exclusion"], 1, title)
            self.assertEqual(out["near_misses"][0]["reason"], "title excluded: " + phrase)

    def test_backend_swe_is_never_strong_for_frontend_profile(self):
        self.assertIn(outcome(job("Senior SWE, Backend (Product Engineering)"))[0], ("borderline", "title"))

    def test_strong_matches_after_normalization(self):
        for title in ("Senior Frontend Engineer", "Sr. Front-End Engineer", "Staff Front End Engineer",
                      "Design Engineer - Americas", "Senior Software Engineer, Frontend", "Staff UI Eng"):
            self.assertEqual(outcome(job(title))[0], "strong", title)

    def test_borderline_matches(self):
        self.assertEqual(outcome(job("React Native Developer"))[0], "borderline")  # title keyword
        self.assertEqual(outcome(job("Senior Platform Engineer"))[0], "title")  # "platform" alone is too weak
        self.assertEqual(outcome(job("Senior Frontend Platform Engineer"))[0], "borderline")  # still a candidate

    def test_unrelated_title_removed(self):
        self.assertEqual(outcome(job("Senior Accountant"))[0], "title")
        self.assertEqual(outcome(job("Senior Software Engineer"))[0], "title")  # only generic words shared


class PayTest(unittest.TestCase):
    def comp(self, lo, hi, cur="USD", interval="year"):
        return {"min": lo, "max": hi, "currency": cur, "interval": interval, "source": "ats_field"}

    def test_below_floor_removed(self):
        out, _ = run([job(comp=self.comp(120000, 150000))])
        self.assertEqual(out["counts"]["removed"]["pay_floor"], 1)
        self.assertEqual(out["near_misses"], [])

    def test_within_ten_percent_is_a_near_miss(self):
        out, _ = run([job(comp=self.comp(140000, 170000))])
        self.assertEqual(out["counts"]["removed"]["pay_floor"], 1)
        self.assertEqual(out["near_misses"][0]["reason"], "pay just under your floor")

    def test_min_only_compared_when_no_max(self):
        self.assertEqual(outcome(job(comp=self.comp(200000, None)))[0], "strong")
        self.assertEqual(outcome(job(comp=self.comp(100000, None)))[0], "pay_floor")

    def test_eur_comp_with_usd_floor_kept_with_flag(self):
        m, c = outcome(job(comp=self.comp(90000, 110000, cur="EUR")))
        self.assertEqual(m, "strong")
        self.assertIn("pay in EUR", c["flags"])

    def test_hourly_comp_not_compared_to_yearly_floor(self):
        m, c = outcome(job(comp=self.comp(80, 100, interval="hour")))
        self.assertEqual(m, "strong")
        self.assertIn("pay per hour", c["flags"])

    def test_missing_pay_kept_with_flag(self):
        m, c = outcome(job(comp=None))
        self.assertEqual(m, "strong")
        self.assertIn("pay not listed", c["flags"])

    def test_hide_no_pay_removes_missing_pay(self):
        self.assertEqual(outcome(job(comp=None), hide_no_pay=True)[0], "pay_floor")

    def test_greenhouse_pay_is_checked_after_fetch_jd_not_at_list_time(self):
        m, c = outcome(job(comp=None, ats="greenhouse"))
        self.assertEqual(m, "strong")
        self.assertNotIn("pay not listed", c["flags"])
        self.assertEqual(outcome(job(comp=None, ats="greenhouse"), hide_no_pay=True)[0], "strong")
        self.assertEqual(outcome(job(comp=self.comp(100000, 120000), ats="greenhouse"))[0], "pay_floor")

    def test_no_floor_keeps_low_pay(self):
        self.assertEqual(outcome(job(comp=self.comp(50000, 60000)), base_pay_floor=None)[0], "strong")

    def test_pay_text(self):
        self.assertEqual(jfilter.pay_text(USD), "$190,000–$240,000/yr")
        self.assertEqual(jfilter.pay_text(self.comp(90000, 110000, cur="EUR")), "€90,000–€110,000/yr")
        self.assertEqual(jfilter.pay_text(self.comp(80, 100, interval="hour")), "$80–$100/hr")
        self.assertEqual(jfilter.pay_text(self.comp(150000, None)), "$150,000+/yr")
        self.assertEqual(jfilter.pay_text(None), "pay not listed")


class RecencyTest(unittest.TestCase):
    def test_old_posting_flagged_not_removed(self):
        m, c = outcome(job(date="2026-01-05"))
        self.assertEqual(m, "strong")
        self.assertIn("open over 90 days", c["flags"])

    def test_recent_posting_not_flagged(self):
        self.assertEqual(outcome(job(date="2026-10-01"))[1]["flags"], [])

    def test_threshold_follows_profile(self):
        self.assertIn("open over 10 days", outcome(job(date="2026-10-01"), recency_flag_days=10)[1]["flags"])


class RankTest(unittest.TestCase):
    def test_description_relevance_breaks_ties_before_date(self):
        old = job("React Developer", key="relevant-old", date="2026-08-01")
        old["description_text"] = "Own our React frontend and the design system."
        new = job("React Developer", key="vague-new", date="2026-10-15")
        new["description_text"] = "Join our team."
        out, _ = run([new, old], title_keywords=["react", "frontend", "design system"])
        self.assertEqual([c["key"] for c in out["candidates"]], ["relevant-old", "vague-new"])

    def test_order(self):
        jobs = [
            job("React Developer", key="border-new", date="2026-10-15"),
            job("Frontend Engineer", key="strong-flagged", locations=("Remote",), scope=None, date="2026-10-16"),
            job("Frontend Engineer", key="strong-old", date="2026-08-01"),
            job("Frontend Engineer", key="strong-nodate", date=None),
            job("Frontend Engineer", key="strong-new", date="2026-10-10"),
        ]
        out, cands = run(jobs)
        self.assertEqual([c["key"] for c in out["candidates"]],
                         ["strong-new", "strong-old", "strong-nodate", "strong-flagged", "border-new"])
        self.assertEqual([c["key"] for c in cands], [c["key"] for c in out["candidates"]])

    def test_limit(self):
        out, cands = run([job() for _ in range(5)], limit=2)
        self.assertEqual(len(out["candidates"]), 2)
        self.assertEqual(out["counts"]["candidates"], 5)


class NearMissTest(unittest.TestCase):
    def test_priority_and_cap(self):
        jobs = ([job("Frontend Engineer", locations=("Remote - Poland",), scope=("PL",), key="scope%d" % i) for i in range(3)]
                + [job(comp={"min": 1, "max": 170000, "currency": "USD", "interval": "year"}, key="pay%d" % i) for i in range(2)]
                + [job("RTL Design Engineer", key="rtl%d" % i) for i in range(2)])
        out, _ = run(jobs)
        self.assertEqual([n["key"] for n in out["near_misses"]], ["rtl0", "rtl1", "pay0", "pay1", "scope0"])
        self.assertEqual(out["near_misses"][4]["reason"], "remote, but only in PL")
        self.assertEqual(sorted(out["near_misses"][0]), ["company", "key", "reason", "title"])

    def test_excluded_borderline_title_ranks_after_scope_misses(self):
        # Live run 2026-10-19: "...First Party Hardware" (borderline) outranked Affirm frontend roles.
        jobs = [job("Electrical React Tooling Lead", key="weak"),
                job("Frontend Engineer", locations=("Remote - Poland",), scope=("PL",), key="scope")]
        out, _ = run(jobs)
        self.assertEqual([n["key"] for n in out["near_misses"]], ["scope", "weak"])

    def test_strong_title_outside_commute_is_a_near_miss(self):
        out, _ = run([job("Design Engineer", locations=("San Francisco",), remote=False, workplace="hybrid",
                          scope=None, key="sf")])
        self.assertEqual(out["counts"]["removed"]["location"], 1)
        self.assertEqual(out["near_misses"][0]["reason"], "hybrid in San Francisco — outside your commute cities")

    def test_remote_scope_miss_needs_a_strong_title(self):
        out, _ = run([job("Senior Accountant", locations=("Remote - Poland",), scope=("PL",))])
        self.assertEqual(out["near_misses"], [])

    def test_excluded_title_that_would_not_match_is_not_a_near_miss(self):
        out, _ = run([job("Mechanical Technician")])
        self.assertEqual(out["counts"]["removed"]["title_exclusion"], 1)
        self.assertEqual(out["near_misses"], [])


class CountsTest(unittest.TestCase):
    def test_removed_plus_candidates_equals_input(self):
        jobs = [job(), job(company="Current Co"), job(locations=("Remote - Poland",), scope=("PL",)),
                local(workplace="onsite"), local(city="Boston, MA"), job("Frontend Engineer Intern"),
                job("Engineering Manager"), job("RTL Design Engineer"), job("Accountant"),
                job(comp={"min": 1, "max": 2, "currency": "USD", "interval": "year"}), job(locations=("Remote",), scope=None)]
        out, cands = run(jobs)
        c = out["counts"]
        self.assertEqual(sorted(c["removed"]), sorted(["work_mode", "location", "remote_scope", "seniority", "track",
                                                       "company", "title", "title_exclusion", "pay_floor",
                                                       "already_seen", "dismissed_or_applied"]))
        self.assertEqual(sum(c["removed"].values()) + c["candidates"], c["input"])
        self.assertEqual(c["input"], len(jobs))
        self.assertEqual(c["candidates"], 2)
        first_run = {k: v for k, v in c["removed"].items() if k not in ("already_seen", "dismissed_or_applied")}
        self.assertTrue(all(v == 1 for v in first_run.values()), c["removed"])
        self.assertEqual((c["removed"]["already_seen"], c["removed"]["dismissed_or_applied"]), (0, 0))

    def test_input_not_mutated(self):
        j = job()
        before = json.dumps(j, sort_keys=True)
        run([j])
        self.assertEqual(json.dumps(j, sort_keys=True), before)


def seen_entry(j, status="seen"):
    return {"first_seen": "2026-10-01T00:00:00Z", "last_seen": "2026-10-01T00:00:00Z", "status": status,
            "reason": None, "closed_at": None, "sig": state.job_sig(j), "aliases": []}


class SeenStateTest(unittest.TestCase):
    def setUp(self):
        self.jobs = {s: job(key="ashby:acme:%s" % s) for s in ("new", "seen", "saved", "applied", "dismissed", "changed")}
        self.seen = {j["key"]: seen_entry(j, s) for s, j in self.jobs.items() if s != "new"}
        self.seen["ashby:acme:changed"] = seen_entry(dict(self.jobs["changed"], title="Old title"))

    def filt(self, show_all=False, seen=None):
        return jfilter.run_filter(list(self.jobs.values()), profile(), today=TODAY,
                                  seen=self.seen if seen is None else seen, show_all=show_all)

    def test_first_run_everything_new(self):
        out, cands = self.filt(seen={})
        self.assertEqual(len(cands), 6)
        self.assertEqual({c["state"] for c in cands}, {"new"})
        self.assertEqual({c["state"] for c in out["candidates"]}, {"new"})

    def test_rerun_keeps_new_changed_saved_and_ranks_saved_last(self):
        out, cands = self.filt()
        self.assertEqual([(c["key"], c["state"]) for c in out["candidates"]],
                         [("ashby:acme:new", "new"), ("ashby:acme:changed", "changed"), ("ashby:acme:saved", "saved")])
        self.assertEqual([c["state"] for c in cands], ["new", "changed", "saved"])
        c = out["counts"]
        self.assertEqual((c["removed"]["already_seen"], c["removed"]["dismissed_or_applied"]), (1, 2))
        self.assertEqual(sum(c["removed"].values()) + c["candidates"], c["input"])

    def test_all_flag_shows_everything_tagged(self):
        out, cands = self.filt(show_all=True)
        self.assertEqual([c["state"] for c in cands], ["new", "changed", "saved", "seen", "applied", "dismissed"])
        self.assertEqual(out["counts"]["candidates"], 6)
        self.assertEqual(out["counts"]["removed"]["already_seen"], 0)

    def test_hard_filter_reason_wins_over_seen(self):
        bad = job("RTL Design Engineer", key="ashby:acme:rtl")
        out, _ = jfilter.run_filter([bad], profile(), today=TODAY, seen={bad["key"]: seen_entry(bad)})
        self.assertEqual(out["counts"]["removed"]["title_exclusion"], 1)
        self.assertEqual(out["counts"]["removed"]["already_seen"], 0)

    def test_state_uses_collapsed_job_not_display_variant(self):
        # the display variant has a different title/key; the seen entry was signed on the collapsed row
        v_local = {"key": "ashby:acme:v2", "title": "Senior Frontend Engineer (LA)", "locations": ["Los Angeles, CA"],
                   "remote": False, "remote_scope": None, "workplace": "hybrid", "comp": USD, "countries": []}
        j = job(key="ashby:acme:v1", locations=("Remote - Poland",), scope=("PL",))
        j["variants"] = [dict(j["variants"][0], remote_scope=["PL"], locations=["Remote - Poland"]), v_local]
        out, cands = jfilter.run_filter([j], profile(), today=TODAY, seen={j["key"]: seen_entry(j)}, show_all=True)
        self.assertEqual(cands[0]["key"], "ashby:acme:v2")
        self.assertEqual(cands[0]["state"], "seen")


    def test_regrouped_job_takes_the_strongest_status_of_its_entries(self):
        # two roles recorded separately now collapse into one job
        j = job(key="ashby:acme:r1")
        j["variants"].append(dict(j["variants"][0], key="ashby:acme:r2"))
        for statuses, want_state, want_removed in ((("seen", "saved"), "saved", None),
                                                   (("seen", "applied"), None, "dismissed_or_applied"),
                                                   (("dismissed", "seen"), None, "dismissed_or_applied")):
            seen = {"ashby:acme:r1": seen_entry(j, statuses[0]), "ashby:acme:r2": seen_entry(j, statuses[1])}
            out, cands = jfilter.run_filter([j], profile(), today=TODAY, seen=seen)
            self.assertEqual([c["state"] for c in cands], [want_state] if want_state else [], statuses)
            if want_removed:
                self.assertEqual(out["counts"]["removed"][want_removed], 1, statuses)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {"JOB_SCOUT_HOME": self.home})
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = jfilter.main(argv)
        text = out.getvalue()
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        return code, json.loads(text)

    def make_run(self, jobs):
        run_dir = state.new_run()
        state.write_json_atomic(run_dir / "jobs.json", jobs)
        return run_dir

    def test_no_profile_exits_2(self):
        self.make_run([job()])
        code, out = self.main([])
        self.assertEqual(code, 2)
        self.assertEqual(out, {"error": "no profile saved — confirm the search brief first"})

    def test_no_run_exits_2(self):
        state.write_json_atomic(state.profile_path(), profile())
        code, out = self.main(["--run", "latest"])
        self.assertEqual(code, 2)
        self.assertIn("error", out)

    def test_run_without_jobs_file_exits_2(self):
        state.write_json_atomic(state.profile_path(), profile())
        state.new_run()
        code, out = self.main([])
        self.assertEqual(code, 2)
        self.assertIn("error", out)

    def test_bad_run_id_exits_2(self):
        state.write_json_atomic(state.profile_path(), profile())
        code, out = self.main(["--run", "../etc"])
        self.assertEqual(code, 2)

    def test_happy_path_shape_and_candidates_file(self):
        state.write_json_atomic(state.profile_path(), profile())
        run_dir = self.make_run([job(), job("RTL Design Engineer"), job(locations=("Remote",), scope=None, comp=None)])
        code, out = self.main(["--run", run_dir.name, "--limit", "150"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out), ["candidates", "counts", "near_misses"])
        self.assertEqual(sorted(out["counts"]), ["candidates", "input", "removed"])
        self.assertEqual(out["counts"]["input"], 3)
        row = out["candidates"][0]
        self.assertEqual(sorted(row), ["company", "flags", "key", "match", "mode", "pay", "since", "state", "title", "where"])
        self.assertEqual(row["mode"], "remote")
        self.assertEqual(row["since"], "2026-10-01")
        self.assertEqual(out["candidates"][1]["pay"], "pay not listed")
        saved = state.read_json(run_dir / "candidates.json")
        self.assertEqual([c["key"] for c in saved], [c["key"] for c in out["candidates"]])
        for c in saved:
            self.assertIn("match", c)
            self.assertIn("flags", c)
            self.assertIn("description_text", c)  # full job dict, not the summary row

    def test_limit_hard_ceiling(self):
        state.write_json_atomic(state.profile_path(), profile())
        self.make_run([job() for _ in range(305)])
        code, out = self.main(["--limit", "1000"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out["candidates"]), 300)
        self.assertEqual(out["counts"]["candidates"], 305)

    def test_unknown_workplace_shows_unknown_mode(self):
        state.write_json_atomic(state.profile_path(), profile())
        self.make_run([local(workplace=None)])
        code, out = self.main([])
        self.assertEqual(out["candidates"][0]["mode"], "unknown")

    def test_unreadable_seen_json_exits_2_and_writes_nothing(self):
        state.write_json_atomic(state.profile_path(), profile())
        run_dir = self.make_run([job()])
        for raw in (b"[]", b'{"ashby:acme:1": {"sta'):
            state.seen_path().write_bytes(raw)
            code, out = self.main([])
            self.assertEqual(code, 2)
            self.assertIn("seen.json", out["error"])
            self.assertIn("not changed", out["error"])
            self.assertFalse((run_dir / "candidates.json").exists())  # never treated as a first run
            self.assertEqual(state.seen_path().read_bytes(), raw)

    def test_rerun_uses_seen_json_and_all_flag(self):
        state.write_json_atomic(state.profile_path(), profile())
        a, b = job(key="ashby:acme:a"), job(key="ashby:acme:b")
        self.make_run([a, b])
        state.write_json_atomic(state.seen_path(), {"ashby:acme:a": seen_entry(a)})
        code, out = self.main([])
        self.assertEqual((code, [c["key"] for c in out["candidates"]]), (0, ["ashby:acme:b"]))
        self.assertEqual(out["counts"]["removed"]["already_seen"], 1)
        code, out = self.main(["--all"])
        self.assertEqual(sorted((c["key"], c["state"]) for c in out["candidates"]),
                         [("ashby:acme:a", "seen"), ("ashby:acme:b", "new")])


if __name__ == "__main__":
    unittest.main()
