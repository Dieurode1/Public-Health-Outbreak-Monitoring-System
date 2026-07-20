"""
Michigan Weekly Disease Report — fetch and snapshot.

MDHHS publishes a weekly PDF of MDSS surveillance counts: statewide totals by
condition, county-level Current/YTD tables, and epi-curve series by disease
group. Counts are provisional and revised as cases are investigated, confirmed,
or ruled out — the same premise the NNDSS revision lane rests on, at county grain.

    python -m phoms.extract.michigan_wsr fetch 15 2026   # one week
    python -m phoms.extract.michigan_wsr backfill 2026   # all available weeks

Snapshots land in snapshots/mi_wsr/ and are never overwritten (ADR 5).
Do not ingest Current_WSR.pdf — it is a rolling URL that overwrites weekly.

See docs/adr/010-michigan-pdf-extraction.md.
"""

import pathlib
import sys
import time

from phoms.http import session

BASE = "https://www.michigan.gov/mdhhs/-/media/Project/Websites/mdhhs/CDINFO/WSR"
OUT = pathlib.Path("snapshots/mi_wsr")


def url_for(week: int, year: int) -> str:
    return f"{BASE}/WSR-{week:02d}-{year}.pdf"


def fetch(week: int, year: int, quiet: bool = False) -> pathlib.Path | None:
    """Download one week's report. Returns the path, or None if unavailable."""
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"WSR-{week:02d}-{year}.pdf"
    if dest.exists():
        if not quiet:
            print(f"{dest.name} already held")
        return dest
    r = session().get(url_for(week, year), timeout=60)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        if not quiet:
            print(f"WSR-{week:02d}-{year}: unavailable ({r.status_code})")
        return None
    dest.write_bytes(r.content)
    if not quiet:
        print(f"WSR-{week:02d}-{year}: {len(r.content):,} bytes -> {dest}")
    return dest


def backfill(year: int) -> None:
    """Walk weeks 1-53 for a year. Missing weeks are expected, not errors."""
    got = 0
    for wk in range(1, 54):
        if fetch(wk, year, quiet=True):
            got += 1
            print(f"  WSR-{wk:02d}-{year}")
        time.sleep(1)  # courtesy to a state health department's web server
    print(f"\n{got}/53 weeks retrieved for {year}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "fetch":
        fetch(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "backfill":
        backfill(int(sys.argv[2]))
    else:
        print(__doc__)
