# ADR 8 — Jurisdiction grain is explicit, and only states drive alerts

**Status:** Accepted (2026-07-19)

## Problem

NNDSS `states` mixes three grains in one column:

- national rollups — `U.S. Residents`, `Total`
- census divisions — `East North Central`, `South Atlantic`, `Middle Atlantic`
- states — `Michigan`, `Ohio`, `Florida`

`New York` and `New York City` also report as separate jurisdictions.

Undifferentiated, a revision diff double-counts: a Michigan revision also
appears in East North Central and in Total, producing three change events for
one real change and inflating every downstream rate.

## Decision

Staging adds a `jurisdiction_grain` column (`national` | `region` | `state`).
The anomaly mart filters to `state`. Rollups are retained for display context
only and never originate an alert.

## Note

This was not in the brief. It surfaced from inspecting pull #1 and is a day-one
lock — retrofitting it after the change-event table has data means reshaping a
table with history in it.
