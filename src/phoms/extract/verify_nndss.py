"""
Pre-build verification #1 — NNDSS provisional-revision behavior.

WHY THIS EXISTS
---------------
The entire nowcasting layer rests on one assumption: CDC revises prior weeks'
counts as late cases are confirmed. If prior weeks never move between pulls,
there is no lag to learn, the revision lane produces nothing, and the nowcast
mart has no input. Brief §7 requires confirming this by eye before any real
code is written.

WHAT IT DOES
------------
  discover : queries the Socrata catalog for NNDSS datasets on data.cdc.gov.
             CDC migrated the weekly tables off WONDER into a consolidated
             dataset, superseding the per-table-per-year datasets (frozen 2022),
             so the current dataset is discovered rather than hardcoded.
  schema   : prints the column list for DATASET_ID. Run before `pull` — field
             names changed in the migration and must not be assumed.
  pull     : fetches all cyclosporiasis rows and writes a snapshot-dated CSV to
             snapshots/. Never overwrites (ADR 5) — accumulating snapshots ARE
             the raw material the lag profile is learned from.

HOW TO USE IT
-------------
    python -m phoms.extract.verify_nndss discover
    python -m phoms.extract.verify_nndss schema
    python -m phoms.extract.verify_nndss pull      # run again 3-4 days later
    # then diff the two CSVs on (states, year, week); rows whose m1 moved
    # are revisions. Rows returned => nowcast premise confirmed.

FINDINGS (2026-07-19)
---------------------
  * Current dataset: x9gk-5huc "NNDSS Weekly Data", updated 2026-07-15.
  * Schema: states, year, week, label, m1..m4 (+ *_flag), location1/2, geocode.
    - `label` filters exactly: one value, "Cyclosporiasis". No variant sweep.
    - `m1` is the current-week count. m2-m4 are cumulative/prior-year
      comparatives — CONFIRM which before the diff treats one as the count.
    - `m1_flag` non-null means suppressed/not-reported, NOT zero. The diff must
      treat flag transitions as distinct from count changes or the lag profile
      is polluted.
  * Pull #1: 16,520 rows, 2022-2026. Baseline depth is 4 prior years — thin;
    argues for a baseline that pools across weeks rather than treating each
    week-of-year independently at n=4.
  * `states` MIXES GRAINS: national rollups ("U.S. Residents", "Total"), census
    divisions ("East North Central"), and states ("Michigan"). NY and NYC report
    separately. Staging must add a jurisdiction-grain column and the anomaly
    mart must filter to state, or rollups double-count and fire false alerts.
  * 2026 leaders: Michigan 482, Ohio 436 — Michigan validated as a real
    crawl-lane target, not a hypothetical one.

STATUS: pull #1 complete; pull #2 outstanding. The gate is not closed until
two snapshots have been diffed.
"""
import csv
import datetime
import pathlib
import sys

import requests

CATALOG = "https://api.us.socrata.com/api/catalog/v1"
DATASET_ID = "x9gk-5huc"  # NNDSS Weekly Data — verify via `discover` if pulls fail
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def discover():
    """List candidate NNDSS datasets with IDs and last-updated dates."""
    r = requests.get(
        CATALOG,
        params={"domains": "data.cdc.gov", "q": "NNDSS weekly notifiable", "limit": 10},
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    for res in r.json()["results"]:
        rs = res["resource"]
        print(f"{rs['id']}  {rs['updatedAt'][:10]}  {rs['name']}")


def schema():
    """Print DATASET_ID's columns. Field names are discovered, never assumed."""
    meta = requests.get(
        f"https://data.cdc.gov/api/views/{DATASET_ID}.json", headers=UA, timeout=30
    ).json()
    for c in meta["columns"]:
        print(f"{c['fieldName']:<30} {c['dataTypeName']}")


def pull(disease_col="label"):
    """Snapshot all cyclosporiasis rows to a date-stamped CSV (ADR 5: never overwrite)."""
    rows = requests.get(
        f"https://data.cdc.gov/resource/{DATASET_ID}.json",
        params={"$where": f"lower({disease_col}) like '%cyclospor%'", "$limit": 50000},
        headers=UA,
        timeout=60,
    ).json()
    if not rows:
        print("no rows — check the disease column name")
        return
    snap = pathlib.Path("snapshots")
    snap.mkdir(exist_ok=True)
    out = snap / f"nndss_cyclospora_{datetime.date.today()}.csv"
    fields = sorted({k for r in rows for k in r})
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows → {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    {"discover": discover, "schema": schema, "pull": pull}[cmd]()
