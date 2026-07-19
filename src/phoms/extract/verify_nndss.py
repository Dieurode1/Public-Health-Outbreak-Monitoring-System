"""
Verification script — does CDC actually revise its published case counts?

NNDSS (National Notifiable Diseases Surveillance System) is CDC's weekly count
of reportable diseases by state and week. Its counts are provisional: as late
cases are confirmed, CDC rewrites weeks it already published. Those rewrites are
the signal the nowcast learns from — so if prior weeks never move between pulls,
the revision lane has nothing to model. This is brief §7, gate 1.

    python -m phoms.extract.verify_nndss discover   # find current dataset id
    python -m phoms.extract.verify_nndss schema     # column names (never assume)
    python -m phoms.extract.verify_nndss pull       # snapshot; rerun in 3-4 days

Then diff two snapshots on (states, year, week). Rows where m1 moved = revisions.

Gotchas:
  m1 is the current-week count; m2-m4 are cumulative/prior-year comparatives.
  m1_flag non-null = suppressed, not zero. Diff must treat flag changes
  separately from count changes.
  `states` mixes national / census-division / state grains. Staging needs a
  grain column; the anomaly mart filters to state or rollups double-count.

See docs/adr/005-snapshot-keys.md.
"""

import csv
import datetime
import pathlib
import sys

import pandas as pd
import requests
import yaml

from phoms import quality

CATALOG = "https://api.us.socrata.com/api/catalog/v1"
DATASET_ID = "x9gk-5huc"  # NNDSS Weekly Data; rerun `discover` if pulls break
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def discover():
    """List NNDSS datasets on data.cdc.gov with ids and last-updated dates."""
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
    """Print DATASET_ID's columns."""
    meta = requests.get(
        f"https://data.cdc.gov/api/views/{DATASET_ID}.json", headers=UA, timeout=30
    ).json()
    for c in meta["columns"]:
        print(f"{c['fieldName']:<30} {c['dataTypeName']}")


def pull(disease_col="label"):
    """Snapshot cyclosporiasis rows to a date-stamped CSV. Never overwrites (ADR 5)."""
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
    print(f"{len(rows)} rows → {out}\n")

    # Validate on arrival. Prior snapshots give volume and freshness a baseline.
    with open("config/diseases.yml") as f:
        cfg = yaml.safe_load(f)
    labels = cfg["cyclosporiasis"]["nndss_labels"]
    prior = sorted(snap.glob("nndss_cyclospora_*.csv"))[:-1]
    prior_rows, prior_week = None, None
    if prior:
        pdf = pd.read_csv(prior[-1])
        prior_rows = len(pdf)
        py = pd.to_numeric(pdf["year"], errors="coerce")
        pw = pd.to_numeric(pdf["week"], errors="coerce")
        v = pd.DataFrame({"year": py, "week": pw}).dropna()
        if not v.empty:
            my = int(v["year"].max())
            prior_week = (my, int(v[v["year"] == my]["week"].max()))
        print(f"(comparing against {prior[-1].name})")
    quality.report(
        quality.run_all(pd.DataFrame(rows), labels, prior_rows, prior_week)
    )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    {"discover": discover, "schema": schema, "pull": pull}[cmd]()
