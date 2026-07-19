# ADR 5 — Snapshot-dated keys, never overwrite

**Status:** Accepted

## Decision

S3 keys carry the pull date, not just the reporting week:

    raw/{source}/{pull_date}/{filename}

## Why

NNDSS counts are provisional. CDC rewrites prior weeks as late cases confirm,
and those rewrites are the only source of the lag profile the nowcast learns
from. Overwrite-on-rerun destroys the exact signal the project depends on.

The revision log is *derived* from these snapshots, not a replacement for them.
S3 stays the durable record.

## Verification status

Pull #1 complete (2026-07-19, 16,520 rows, 2022-2026). Pull #2 outstanding —
the premise is not confirmed until two snapshots have been diffed and prior
weeks are observed to move.
