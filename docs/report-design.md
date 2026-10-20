---
version: alpha
name: job-scout report — Signal refined (teal)
description: >-
  Design tokens and layout spec for the per-run HTML report written by
  skills/job-scout/scripts/report.py (CSS and JS are constants in that file). Operate-mode
  surface: a master–detail table. Shaped with impeccable (M7 redesign), refined after a
  Codex + Antigravity design critique (design pass v2); audited with screenwright. Badge pass v3
  (2026-10-20): NEW/CHANGED/SAVED became pills, merged from blind impeccable, screenwright and
  taste-skill runs on the same report.
colors:
  primary: "#0f766e"        # teal: top-fit segments, selected row title, focus ring, sorted mark, primary button
  secondary: "#52525b"      # muted text
  neutral: "#e4e4e7"        # row lines, empty segments
  surface: "#f7f7f8"        # page canvas
  on-surface: "#18181b"     # body text
  error: "#b91c1c"          # gate fail
  success: "#15803d"        # gate pass, why mark
  warning: "#a14a07"        # risk mark, flag note (5.4:1 on the selected row)
  table: "#ffffff"          # table and pane surface
  faint: "#71717a"          # column headers on the white table only; never on hover/selected rows
  line-strong: "#d4d4d8"    # chip and button borders, quote rule
  hover: "#f4f4f5"          # row hover
  accent-soft: "#e6f6f4"    # selected/open summary row, top-fit pill
  accent-ink: "#134e4a"     # text on accent-soft, primary button hover
  on-accent: "#ffffff"      # text on the primary button
  warn-bg: "#fef3c7"        # "Check first" box, unknown gate badge
  warn-ink: "#92400e"
  warn-line: "#f59e0b"
  new-bg: "#1d4ed8"         # blue: the NEW pill fill, CHANGED outline and text, "N new to you", New only chip dot
  new-ink: "#ffffff"        # text on the NEW pill (6.7:1)
  dark:
    primary: "#5eead4"
    secondary: "#a1a1aa"
    neutral: "#26262b"
    surface: "#0e0e10"
    on-surface: "#f4f4f5"
    error: "#f87171"
    success: "#4ade80"
    warning: "#fbbf24"
    table: "#161619"
    faint: "#8b8b94"
    line-strong: "#34343a"
    hover: "#1d1d21"
    accent-soft: "#12302e"
    accent-ink: "#ccfbf1"
    on-accent: "#042f2e"    # dark text on the light teal button
    warn-bg: "#2e1f05"
    warn-ink: "#fbbf24"
    warn-line: "#a16207"
    new-bg: "#60a5fa"
    new-ink: "#0b1530"
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

# job-scout report — Signal refined (teal)

## Overview
An Operate surface. The reader's question is "which of these roles fit me?" and only then
"why?". The first screen shows every role as one row, and the fit column does the sorting work
for the eye: top fits are the only colored rows. Details open on demand and lead with what needs
checking. Familiar data-table conventions, a calm neutral page, one teal accent. The page is
complete with JavaScript off and prints as a document.

## Colors
Neutral gray carries the page. Teal is spent on: top-fit segments and pill, the selected row
(accent-soft background, title in accent-ink), the focus ring, the sorted-column mark, pressed
quick-filter chips, and the one primary button ("Open posting"). Green, amber and red appear only
on gates, risk marks, flags and the "Check first" box, always with an icon and a word, so no
meaning rests on color. Blue is the one "new to you" hue and nothing else: the NEW pill, the
CHANGED outline, the header's "N new to you" pill and the dot on the "New only" chip. It is not
teal on purpose: a teal NEW pill would blend into the teal fit pill on the same row. Print resets
every token to the light palette.

## Typography
One system sans. Numbers use `tabular-nums`. Hierarchy comes from weight and color, not size:
titles 600, secondary text muted, column headers 12px/500 faint.

## Layout

### Header (all widths)
1. `h1`: "N matching roles" ("No matching roles" when empty). No kicker above it. On a rerun with
   NEW roles shown, a blue "N new to you" pill sits beside the h1 (outside it, so the heading
   text stays the count); N counts the shown rows badged NEW.
2. One muted meta line: date, then the brief fields, split by 1px vertical rules.
3. Coverage: "Checked P of A company job boards and read K open roles in full." On a rerun:
   "Checked P of A company job boards: K new or changed since last time · showing top R of J matches."
   With no new or changed posting, one bold line, "No new or changed postings since last time.", sits above
   the full list (a NEW row in it is new to the user, not a new posting).

### Toolbar (JS on, roles present)
Quick-filter chips (`aria-pressed` buttons, shown only when their count is above zero):
"New only n" (roles badged NEW, reruns only), "Top fit n" (fit 7 or 8) and "No flags n". A pressed chip shows a check icon and the teal tint.
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
- **Top (7–8):** teal segments; "N/8" in a teal-soft pill (pill turns table-white on the selected row).
- **Middle (6):** muted gray segments.
- **Low (≤ 5):** faint segments, muted number.

### Row anatomy
`# | [chevron] Title  NEW  ! 1 flag | where | pay | fit | since`. The title is the row's button
(it expands the detail inline, or selects the role in split view; the whole row is clickable).
NEW / CHANGED / SAVED badges are pills (`.tag .tag-new|changed|saved`; 12px/700, 4px radius,
1px border, no letter spacing, never wrapping inside): NEW is filled blue, CHANGED is a blue
outline, SAVED a neutral outline. The word stays on every badge, so no meaning rests on color.
They show only on reruns and are never used for rank (rank is the rubric's, set by
`state.py judged rank`). The chevron hangs in the cell's left padding, so a wrapped title, its
badges and the second line all start on one left edge. The detail's meta line adds "first shown <date>"
for a role shown before, and "Check first" lists what changed (before → after) for a CHANGED one. Flags show as an amber "1 flag"
note with an icon. In split view the chevron is hidden.

### Detail anatomy (inline row and split pane share one markup)
1. Pane only: title (16px/650) and "company · where · pay · open since".
2. **Check first** (only when something needs checking): an amber box listing every gate that
   did not pass ("sponsorship: unknown", "pay: failed") and every flag.
3. "Why it fits" and "Watch for": the reason, then the verbatim quote on its own line, not
   italic, behind a 1px line-strong rule.
4. Scores (four 2-segment meters) and Gates (passed gates muted with no ": pass"; unknown in an
   amber badge; failed in red). Stacked inline; two columns in the pane. Score rows keep the gate
   rows' 29px height, so the two columns line up.
5. Actions: "Open posting" (the primary teal button), then the group "Copy reply to chat":
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
(max 5; reason is the first failed gate or "fit N/8, below 5").

## States
- Hover row: hover background. Selected/open row: accent-soft on the summary row only; the
  detail sits on the table background.
- Focus: 2px teal outline.
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
- Don't switch to cards on phones; don't spend teal on hover or decoration.
- Don't use a colored left border wider than 1px; don't use unicode glyphs as icons.
- Do keep 44px targets for chips and detail buttons below 768px.
- Do escape every value and keep links http(s) only.

## Voice
Plain, short labels in sentence case: "Check first", "Why it fits", "Watch for", "Open posting",
"Copy reply to chat". Unknowns stay visible ("pay not listed").
