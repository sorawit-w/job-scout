---
version: alpha
name: job-scout report — Signal
description: >-
  Design tokens for the per-run HTML report written by skills/job-scout/scripts/report.py
  (CSS and JS are constants in that file). Inferred from report.py's first version (M7) and
  audited with screenwright; edit tokens here and in report.py together.
colors:
  primary: "#4338ca"        # indigo accent: links, fit bar, NEW/CHANGED tag, focus ring
  secondary: "#475569"      # muted slate text
  neutral: "#e2e8f0"        # lines, chips, empty bar
  surface: "#f4f6f9"        # page background (cards are #ffffff)
  on-surface: "#0f172a"     # body text
  error: "#b91c1c"          # failed gate
  success: "#047857"        # passed gate, why mark
  warning: "#a16207"        # risk mark, flags
  dark:
    primary: "#a5b4fc"
    secondary: "#94a3b8"
    neutral: "#1e293b"
    surface: "#0b1120"      # cards #111a2e
    on-surface: "#e2e8f0"
    error: "#f87171"
    success: "#34d399"
    warning: "#fbbf24"
typography:
  body: { family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", size: 15px, line-height: 1.5 }
  h1: { size: 20px, weight: 700 }
  h2: { size: 16px, weight: 700 }
  title: { size: 16px, weight: 600 }
  meta: { size: 14px }
  small: { size: 12-13px }
  numbers: { family: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", feature: tabular-nums }
rounded:
  card: 10px
  control: 6px
  tag: 4px
  chip: 999px
spacing:
  page-gutter: 16px
  card-padding: 14px 16px
  card-gap: 12px
  max-width: 860px
a11y:
  wcag: "2.2-AA"
breakpoints:
  mobile: 375
  tablet: 768
  desktop: 1280
---

# job-scout report — Signal

## Overview
A calm tool page, not a dashboard: one column of compact role cards on a slate background, one
indigo accent, numbers in monospace. It must read fully with JavaScript off, print cleanly, and
fit a 375px phone with no horizontal scroll. It loads nothing from the network.

## Colors
Slate neutrals carry everything; indigo is the only accent (links, the fit bar, tags, focus).
Green and red appear only on gate results; amber only on risks and flags. Every pair meets
WCAG AA in light and dark.

## Typography
System sans for text. Monospace with tabular figures for ranks, fit scores and score values.

## Layout
- Header: title line, brief chips, coverage line.
- Controls (hidden until the script runs): sort and filter.
- Role cards in rank order. Each card has a head row (rank, title, tag, fit), a meta line, then
  quotes, flags, the score/gate grid and the copy buttons.
- Sections after the cards: saved/applied still open, closed, close but excluded. Then the footer.
- Below 560px the grid becomes two columns and the card body loses its left indent.

## Shapes
Cards 10px radius with a 1px line border, no shadow. Controls 6px. Tags 4px. Chips fully round.

## Do's and Don'ts
- Do escape every value; do keep links `http(s)` only, opening in a new tab.
- Do keep the fixed rank number on every card, even after sorting.
- Don't add a second accent color, web fonts, images, or saved state.
- Don't hide the score grid behind a toggle: it must print.

## Voice
Plain English, short labels ("Fit 7/8", "location gate: pass"). Unknowns stay visible
("pay not listed").
