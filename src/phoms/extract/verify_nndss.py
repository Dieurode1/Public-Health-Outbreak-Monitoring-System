"""Pull #1 — discover the current NNDSS weekly dataset and snapshot cyclosporiasis rows."""
import csv
import datetime
import pathlib
import sys

import requests

CATALOG = "https://api.us.socrata.com/api/catalog/v1"
DATASET_ID = "x9gk-5huc"  # fill in after step 1


def discover():
    r = requests.get(
        CATALOG,
        params={"domains": "data.cdc.gov", "q": "NNDSS weekly notifiable", "limit": 10},
        timeout=30,
    )
    r.raise_for_status()
    for res in r.json()["results"]:
        rs = res["resource"]
        print(f"{rs['id']}  {rs['updatedAt'][:10]}  {rs['name']}")


def schema():
    meta = requests.get(f"https://data.cdc.gov/api/views/{DATASET_ID}.json", timeout=30).json()
    for c in meta["columns"]:
        print(f"{c['fieldName']:<30} {c['dataTypeName']}")


def pull(disease_col="label"):
    rows = requests.get(
        f"https://data.cdc.gov/resource/{DATASET_ID}.json",
        params={"$where": f"lower({disease_col}) like '%cyclospor%'", "$limit": 50000},
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
