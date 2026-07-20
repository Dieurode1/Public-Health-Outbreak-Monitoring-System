# ADR 9 — Counts carry a measure_type and are never compared across types

**Status:** Accepted (2026-07-19)

## Problem

Michigan reports three different cyclosporiasis figures for 2026, all correct:

| Figure | Source | What it counts |
|---|---|---|
| ~2 | MDHHS Weekly Disease Report (wk 15) | routine MDSS surveillance, 2026 YTD as of week 15 (mid-April) |
| 482 | NNDSS via CDC | what Michigan transmits to CDC, cumulative |
| 5,002 | MDHHS outbreak investigation page | cases in the outbreak investigation window (from late June 2026), as of 2026-07-16 |

They differ by three orders of magnitude because they are different systems with
different case definitions, reporting windows, and update cadences — not because
any of them is wrong. The windows alone explain much of the gap: the WSR figure
predates the outbreak entirely.

A corroboration join on `(disease, state, week)` that ignored this would compare
an outbreak-investigation total against a routine-surveillance weekly count and
produce a meaningless ratio.

## Decision

Every count carries `measure_type`:

- `routine_surveillance` — NNDSS, state weekly reports
- `outbreak_investigation` — incident-specific case counts
- `advisory` — recall/alert events, not case counts

Marts compare within a `measure_type`. Cross-type comparison is allowed only as
explicit context in the payload, never as an input to a detection score.

## Consequence

The corroboration mart's scoped join gains `measure_type` in its key. An outbreak
investigation count can corroborate an anomaly qualitatively — it cannot be
differenced against a surveillance baseline.
