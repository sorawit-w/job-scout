---
version: alpha
name: job-scout report — Stone & petrol
description: >-
  The repo's design-token authority. job-scout's only UI is the per-run HTML report written by
  skills/job-scout/scripts/report.py (CSS and JS are constants in that file), so this file
  specifies that report; a new UI surface adds its own section here. Operate-mode
  surface: a master–detail table. Shaped with impeccable (M7 redesign), refined after a
  Codex + Antigravity design critique (design pass v2); audited with screenwright. Badge pass v3
  (2026-10-20): NEW/CHANGED/SAVED became pills, merged from blind impeccable, screenwright and
  taste-skill runs on the same report. Palette pass v4 (2026-10-20): stone neutrals, a petrol accent,
  re-stepped status colors and ink NEW badges, chosen by the user from three options authored with
  impeccable, sourced from taste-skill's app library and checked with the dataviz palette validator.
colors:
  primary: "#1b6c80"        # petrol: top-fit segments, selected row title, focus ring, sorted mark, primary button
  secondary: "#57534e"      # muted text, flag note text
  neutral: "#e6e5e2"        # row lines, empty segments
  surface: "#f4f4f2"        # page canvas (stone, low chroma; not cream)
  on-surface: "#1c1917"     # body text
  error: "#7f1d1d"          # gate fail (10.0:1)
  success: "#46750f"        # gate pass, why mark (olive)
  warning: "#c47d00"        # risk and flag icons only, never text (3.0:1 on the selected row)
  table: "#ffffff"          # table and pane surface
  faint: "#736d68"          # column headers on the white table only; never on hover/selected rows
  line-strong: "#d5d3cf"    # chip and button borders, quote rule
  hover: "#f6f5f3"          # row hover
  accent-soft: "#eef5f6"    # selected/open summary row, pressed chip
  accent-ink: "#0f4a59"     # text on accent-soft, top-fit number, primary button hover
  on-accent: "#ffffff"      # text on the primary button
  warn-bg: "#fcf1d8"        # "Check first" box, unknown gate badge
  warn-ink: "#8a3f08"
  warn-line: "#e0a23a"
  new-bg: "#1c1917"         # ink: the NEW pill fill, CHANGED outline and text, "N new to you", New only chip dot
  new-ink: "#ffffff"        # text on the NEW pill (17.5:1)
  dark:
    primary: "#7fb6c4"      # desaturated petrol, not neon
    secondary: "#aaa49c"
    neutral: "#2b2925"
    surface: "#12110f"
    on-surface: "#f5f4f1"
    error: "#e5534b"
    success: "#78b648"
    warning: "#f8c96a"
    table: "#1a1916"
    faint: "#8f8981"
    line-strong: "#3d3a35"
    hover: "#22201d"
    accent-soft: "#1b2d32"
    accent-ink: "#d5ebf0"
    on-accent: "#0b2a32"    # dark text on the light petrol button
    warn-bg: "#221809"
    warn-ink: "#f0c37a"
    warn-line: "#8a6220"
    new-bg: "#f5f4f1"       # light ink pill
    new-ink: "#1c1917"
typography:
  family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif (one family; numbers use tabular-nums)"
  h1: { size: 20px, weight: 650, tracking: -0.015em }
  h2: { size: 14px, weight: 600 }
  pane-title: { size: 16px, weight: 650 }
  body: { size: 14px, line-height: 1.45 }
  title: { size: 14px, weight: 600 }
  meta: { size: 13px }
  label: { size: 12px, weight: 500–600 }  # column headers 500, section labels 600; sentence case
rounded:
  control: 6px
  tag: 4px
  box: 8px
  pane: 10px
  chip: 999px
spacing:
  page-gutter: 24px (16px below 768)
  row-padding: 11px 12px (10px 8px below 768)
  detail-padding: 4px 20px 20px 74px (title-aligned; 4px 12px 16px below 768)
a11y:
  wcag: "2.2-AA"
breakpoints:
  mobile: 375
  tablet: 768
  split: 1200
  wide: 1600
---

# job-scout report — Stone & petrol

## Overview
An Operate surface. The reader's question is "which of these roles fit me?" and only then
"why?". The first screen shows every role as one row, and the fit column does the sorting work
for the eye: top fits are the only colored rows. Details open on demand and lead with what needs
checking. Familiar data-table conventions, a calm stone-gray page, one petrol accent. The page is
complete with JavaScript off and prints as a document.

## Colors
Warm stone neutrals carry the page: low-chroma grays with a slight warm cast, never a yellow cream.
Petrol is the one accent, spent on: top-fit segments and the top-fit number, the selected row
(accent-soft background, title in accent-ink), the focus ring, the sorted-column mark, pressed
quick-filter chips, and the one primary button ("Open posting"). The top-fit number has no tinted
pill, so each row spends petrol on its segments only. Dark mode uses a desaturated petrol, not a neon
one.

Green, amber and red appear only on gates, risk marks, flags and the "Check first" box, always with an
icon and a word, so no meaning rests on color. They are stepped apart by lightness so color-blind
readers can still tell them apart: the earlier amber and red were ΔE 0.6 apart for deutan readers
(dataviz palette validator, OKLab ×100), which left only the icon and the word to separate them.
Now light mode passes (worst pair 8.1, protan) and dark mode is in the 6–8 band (red vs green 6.4,
deutan), which is allowed only because every status mark has an icon and a word. Amber is an icon
color only: the "N flags" note is muted text beside an amber icon, so flags on most rows do not read
as texture.

"New to you" is ink, not a hue: the NEW pill is filled ink, CHANGED is an ink outline, and the
header's "N new to you" pill and the dot on the "New only" chip are ink too. A blue NEW pill sat too
close to petrol on the same row. Print resets every token to the light palette.

## Typography
One system sans. Numbers use `tabular-nums`. Hierarchy comes from weight and color, not size:
titles 600, secondary text muted, column headers 12px/500 faint.

## Layout

### Header (all widths)
1. `h1`: "N matching roles" ("No matching roles" when empty). No kicker above it. On a rerun with
   NEW roles shown, an ink "N new to you" pill sits beside the h1 (outside it, so the heading
   text stays the count); N counts the shown rows badged NEW.
2. One muted meta line: date, then the brief fields, split by 1px vertical rules.
3. Coverage: "Checked P of A company job boards and read K open roles in full." On a rerun:
   "Checked P of A company job boards: K new or changed since last time · showing top R of J matches."
   With no new or changed posting, one bold line, "No new or changed postings since last time.", sits above
   the full list (a NEW row in it is new to the user, not a new posting).

### Toolbar (JS on, roles present)
Quick-filter chips (`aria-pressed` buttons, shown only when their count is above zero):
"New only n" (roles badged NEW, reruns only), "Top fit n" (fit 7 or 8) and "No flags n". A pressed chip shows a check icon and the petrol tint.
Chips combine with the text filter; the count reads "n of N shown" only while a filter is on.

### Columns per width
| Width | Mode | Columns (left to right) |
|---|---|---|
| < 768 | inline rows | # · Role (title; second line "company · where · pay") · Fit |
| 768–1199 | inline rows | # · Role (title; second line company) · Where · Pay · Fit · Since |
| 1200–1599 | split pane | list 58%: # · Role (second line "company · where") · Pay · Fit · Since — pane 42% (min 380px, max 560px) |
| ≥ 1600 | split pane | list 60%: # · Role · Where · Pay · Fit · Since — pane 40% (max 640px) |

Pay is right-aligned in ink; "pay not listed" is a missing value and is set muted. Rows sort by
any column header; rank stays with its row.

### Fit encoding (tiered)
Fit is the sum of the four 0–2 scores (one source of truth, not the agent's total). Eight 5×12px
segments (3px wide below 768) plus "N/8":
- **Top (7–8):** petrol segments; "N/8" in accent-ink, with no pill fill.
- **Middle (6):** muted gray segments.
- **Low (≤ 5):** faint segments, muted number.

### Row anatomy
`# | [chevron] Title  NEW  ! 1 flag | where | pay | fit | since`. The title is the row's button
(it expands the detail inline, or selects the role in split view; the whole row is clickable).
NEW / CHANGED / SAVED badges are pills (`.tag .tag-new|changed|saved`; 12px/700, 4px radius,
1px border, no letter spacing, never wrapping inside): NEW is filled ink, CHANGED is an ink
outline, SAVED a neutral outline. The word stays on every badge, so no meaning rests on color.
They show only on reruns and are never used for rank (rank is the rubric's, set by
`state.py judged rank`). The chevron hangs in the cell's left padding, so a wrapped title, its
badges and the second line all start on one left edge. The detail's meta line adds "first shown <date>"
for a role shown before, and "Check first" lists what changed (before → after) for a CHANGED one. Flags show as a muted "1 flag"
note with an amber icon. In split view the chevron is hidden.

### Detail anatomy (inline row and split pane share one markup)
1. Pane only: title (16px/650) and "company · where · pay · open since".
2. **Check first** (only when something needs checking): an amber box listing every gate that
   did not pass ("sponsorship: unknown", "pay: failed") and every flag.
3. "Why it fits" and "Watch for": the reason, then the verbatim quote on its own line, not
   italic, behind a 1px line-strong rule.
4. Scores (four 2-segment meters) and Gates (passed gates muted with no ": pass"; unknown in an
   amber badge; failed in red). Stacked inline; two columns in the pane. Score rows keep the gate
   rows' 29px height, so the two columns line up.
5. Actions: "Open posting" (the primary petrol button), then the group "Copy reply to chat":
   Save / Applied / Dismiss. Each copies `save 3 (Company, Title)` etc. In the pane the actions
   bar sticks to the pane's bottom edge.

### Split pane behavior (≥ 1200px, JavaScript on)
The list stays left; the pane is sticky (top 16px, max height viewport − 32px, scrolls on its
own). The first role is selected on load. Clicking a row or pressing Enter/Space selects it; ↑/↓
on a focused row button move selection and focus together. The selected detail moves into the
pane (one copy in the DOM); a polite live region announces "Showing <title> at <company>". A
filter that hides everything empties the pane with "No roles match the filter."
The detail's title `<h2>` shows only in the pane. Inline it is visually hidden (the `.sr` method),
not `display:none`, so the heading outline stays h1 → h2 → h3 and axe's heading-order passes.

### Secondary sections (below the table)
Compact tables: "Saved or applied, still open", "Closed since last time", "Close but excluded"
(max 5). The reason says why the role was left out, in this order: "<gate> gate failed",
"fit N/8, not in the top R" (eligible, but R roles were already shown), "fit N/8, below 5", or
"fit N/8, not all gates checked".

## States
- Hover row: hover background. Selected/open row: accent-soft on the summary row only; the
  detail sits on the table background.
- Focus: 2px petrol outline.
- Empty: one plain sentence on the table surface, then the secondary sections.

## Motion
Only the chevron rotates (90°, 120ms ease-out); none under `prefers-reduced-motion`.

## Print
Light tokens, white page, no toolbar, pane or copy buttons. Badges print as ink outlines (browsers
drop background fills by default, which would leave white text on white). Every detail prints inline under its
row; a row and its detail never split across pages; "Open posting" prints as plain text with its
URL.

## Do's and Don'ts
- Do keep fit visible and sortable at every width; keep table semantics at every width.
- Don't switch to cards on phones; don't spend petrol on hover or decoration.
- Don't use a colored left border wider than 1px; don't use unicode glyphs as icons.
- Do keep 44px targets for chips and detail buttons below 768px.
- Do escape every value and keep links http(s) only.

## Voice
Plain, short labels in sentence case: "Check first", "Why it fits", "Watch for", "Open posting",
"Copy reply to chat". Unknowns stay visible ("pay not listed").
