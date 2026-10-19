---
version: alpha
name: job-scout report — Signal refined
description: >-
  Design tokens and layout spec for the per-run HTML report written by
  skills/job-scout/scripts/report.py (CSS and JS are constants in that file). Operate-mode
  surface: a master–detail table. Shaped with impeccable (M7 redesign); audited with screenwright.
colors:
  primary: "#4f46e5"        # indigo: fit bar fill, selected/open row title, focus ring, sorted header mark
  secondary: "#52525b"      # muted text
  neutral: "#e4e4e7"        # row lines
  surface: "#f6f6f7"        # page canvas
  on-surface: "#18181b"     # body text
  error: "#b91c1c"          # gate fail
  success: "#15803d"        # gate pass, why mark
  warning: "#a16207"        # risk mark, flags
  table: "#ffffff"          # table and pane surface
  faint: "#71717a"          # column headers on the white table only (4.8:1); never on hover/selected rows
  line-strong: "#d4d4d8"    # header underline, pane edge
  hover: "#f4f4f5"          # row hover
  accent-soft: "#eef2ff"    # selected/open row background
  accent-ink: "#3730a3"     # text on accent-soft (NEW tag)
  dark:
    primary: "#818cf8"
    secondary: "#a1a1aa"
    neutral: "#27272a"
    surface: "#0f0f11"
    on-surface: "#ececef"
    error: "#f87171"
    success: "#4ade80"
    warning: "#fbbf24"
    table: "#17171a"
    faint: "#8b8b94"
    line-strong: "#3f3f46"
    hover: "#1f1f23"
    accent-soft: "#1f1d3d"
    accent-ink: "#c7d2fe"
typography:
  family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif (one family; numbers use tabular-nums)"
  h1: { size: 18px, weight: 600 }
  h2: { size: 15px, weight: 600 }
  body: { size: 14px, line-height: 1.45 }
  title: { size: 14px, weight: 600 }
  meta: { size: 13px }
  label: { size: 12px, weight: 600 }     # column headers, section labels; sentence case
rounded:
  control: 6px
  tag: 4px
  pane: 10px
spacing:
  page-gutter: 24px (16px below 768)
  row-padding: 10px 12px
  cell-gap: 12px
  detail-padding: 12px 16px 16px 48px (16px left below 768)
a11y:
  wcag: "2.2-AA"
breakpoints:
  mobile: 375
  tablet: 768
  desktop: 1280
  wide: 1600
---

# job-scout report — Signal refined

## Overview
An Operate surface. The reader's question is "which of these roles fit me?" and only then
"why?". The first screen therefore shows every role as one dense row with the fit score as the
strongest visual; the quoted reasons open on demand. Familiar data-table conventions, a calm
neutral page, one indigo accent. The page is complete with JavaScript off and prints as a
document.

## Colors
Neutral gray (not blue-slate) carries the page. Indigo is spent on exactly four things: the fit
bar fill, the selected/open row (accent-soft background, title in accent-ink), the focus ring,
and the sorted-column mark. Green, amber and red appear only on gates, risk marks and
flags, always with an icon and a word (check pass, cross fail, question unknown, alert risk) so no
meaning rests on color. Icons are one inline SVG sprite (16px grid, 1.75 stroke, round caps):
check, x, question, alert, chevron, sort-up, sort-down, arrow-up-right.

## Typography
One system sans. Numbers (rank, fit, pay, dates) use `font-variant-numeric: tabular-nums` so
columns align; no monospace font. Column headers are 12px/600 in the faint color, sentence case.
Secondary text inside rows (company, where, pay, dates) uses the secondary color, which keeps
AA contrast on the hover and selected backgrounds too.

## Layout

### Header (all widths)
Title line "job-scout · N roles · date", then the brief chips, then the coverage line. On a
rerun the coverage line counts new or changed roles.

### Columns per width
| Width | Mode | Columns (left to right) |
|---|---|---|
| < 768 | inline rows | # (28px) · Role (title; second line "Company · pay") · Fit (88px) |
| 768–1199 | inline rows | # (36) · Role (title; second line company) · Where (18%) · Pay (14%) · Fit (120) · Since (96) |
| 1200–1599 | split pane | list 58%: # · Role (title; second line "company · where") · Pay · Fit · Since — pane 42% (min 380px, max 560px) |
| ≥ 1600 | split pane | list 60%: # · Role · Where · Pay · Fit · Since — pane 40% (max 640px) |

Fit is visible at every width: a 56px bar (2px radius track in the line color, indigo fill
proportional to N/8) and "N/8" in tabular figures. Rows sort by any column header; rank is fixed
and stays with its row.

### Row anatomy
`# | [chevron] Title  NEW | company … | pay | fit | since`. The title cell holds the row's button
(it expands the detail inline, or selects the role in split mode); the whole row is clickable,
the button is the keyboard path. NEW / CHANGED is a 11px/700 tag in accent-ink on accent-soft.
Flags show as a small amber "!" count after the title ("! 2") with the full text in the detail.

### Detail anatomy (inline row and split pane share the same markup)
1. Pane only: title (16px/600), "company · where · pay · open since", and an "Open posting ↗"
   link button.
2. Two columns at ≥ 768 (stacked below): left 60% "Why it fits" (✓ text — quote) and
   "Watch for" (! text — quote); right 40% the score meters and gates.
3. Score meters: four lines "role ▮▮ 2/2", each two 14×6px segments (filled = indigo, empty =
   line color), label left, value right.
4. Gates: four inline badges "✓ location", "? sponsorship", "✕ pay" — glyph and word, colored.
5. Flags as full text lines (amber "!").
6. Actions row: "Open posting ↗" (inline mode), then copy buttons "save 3", "applied 3",
   "dismiss 3" whose copied text names the role.

### Split pane behavior (≥ 1200px, JavaScript on)
The list stays left; the pane is sticky (top 16px, max height viewport − 32px, scrolls on its
own). The first role is selected on load. Clicking a row or pressing Enter/Space on its button
selects it; ↑/↓ on a focused row button move the selection and focus together. The selected
row's detail is moved into the pane (one copy in the DOM); a polite live region announces
"Showing <title> at <company>". Below 1200px, on print, and with JS off, every detail sits
inline under its row instead.

### Secondary sections (below the table)
Compact tables, same row style, no expand: "Saved or applied, still open" (role, company,
status), "Closed since last time" (role, company), "Close but excluded" (role, company, reason,
max 5).

## Shapes
Hairline row dividers only; no card borders, no shadows. The table sits on the table surface
with a 1px line-strong header underline. The split pane has a 1px line-strong left edge and a
10px radius on its outer corners.

## States
- Hover row: hover background.
- Open/selected row: accent-soft background; title in accent-ink; chevron rotated.
- Focus: 2px indigo outline, offset −2px on row buttons, 2px elsewhere.
- Sorted header: indigo ▲/▼ mark and `aria-sort`.
- Empty: one plain sentence on the table surface ("No roles matched your brief. Most jobs were
  removed by location (40 of 50)." or "Nothing new since last time."), then the secondary
  sections.

## Motion
Only the chevron rotates (90°, 120ms ease-out) when a row opens; none under
`prefers-reduced-motion`. Nothing else animates.

## Print
Single column, white, no controls, no pane, no copy buttons. Every detail prints inline under
its row; a role's row and detail never split across pages; the posting URL prints after the
title.

## Do's and Don'ts
- Do keep fit visible and sortable at every width; do keep table semantics at every width.
- Don't switch to cards on phones; don't spend indigo on hover or decoration.
- Don't animate row expansion; don't hide meaning in color alone.
- Do escape every value and keep links http(s) only.
- Do theme the browser surfaces: `::selection` in accent-soft, `accent-color` and
  `scrollbar-color` from the palette, `text-underline-offset: 2px` on links.

## Voice
Plain, short labels in sentence case: "Why it fits", "Watch for", "Open posting". Unknowns
stay visible ("pay not listed").
