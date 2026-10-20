# Saving the confirmed brief

Read this when saving the brief (SKILL.md Phase 2). Write the confirmed profile as JSON and save it:

```
python3 scripts/state.py profile save --stdin <<'JSON'
{"schema": 1, "target_roles": [...], "title_synonyms": [...], "title_exclusions": [...],
 "seniority": [...], "track": "ic", "home_base": "...", "work_modes": ["remote", "hybrid"],
 "commute_cities": ["Los Angeles", "Pasadena", ...], "remote_scope": ["US"],
 "open_to_relocation": false, "needs_sponsorship": "no",
 "base_pay_floor": {"amount": 180000, "currency": "USD", "interval": "year"},
 "hide_no_pay": false, "industries_prefer": [...], "industries_exclude": [], "companies_include": [],
 "companies_exclude": ["Acme"], "must_haves": [], "dealbreakers": [], "recency_flag_days": 90,
 "result_count": 15, "work_style": {"meetings": "async", "travel": "none"},
 "sources": {"target_roles": "resume", "work_modes": "you", ...}}
JSON
```

- `needs_sponsorship` is `yes`, `no`, or `undisclosed`; `base_pay_floor` is `null` for "no floor".
- `remote_scope` uses two-letter country codes (`"US"`, `"CA"`) or a region (`"AMER"`, `"EU"`,
  `"ANY"`), never country names.
- `commute_cities`: if they accept hybrid or onsite, list the cities within a reasonable commute
  of their home base and include them in the brief so they can correct it. Write a city in
  another state with its state (`"Jersey City, NJ"`): a local job naming any other state is removed.
- `industries_prefer`: words from it also pick employers by name ("hospitals and health
  systems" puts health employers first), so use plain industry words.
- `work_style` (optional, SKILL.md Phase 2): only these topics and choices — `meetings`
  `async`/`meetings_ok`, `on_call` `none`/`ok`, `travel` `none`/`some`/`lots`, `autonomy`
  `high`/`guided`, `stage` `startup`/`growth`/`established`. Leave out topics the user skipped;
  save `{}` when they skipped all. Leave the key out entirely until they have been asked. Never
  store a reason with a choice — there is no field for one.
- If `save` prints `errors`, fix the JSON and save again — never drop the user's answer to make
  it pass. Unknown fields are rejected on purpose.
