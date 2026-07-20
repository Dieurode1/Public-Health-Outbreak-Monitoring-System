"""
Parse the statewide summary table out of a Michigan Weekly Disease Report.

Each WSR PDF carries a four-week window (W-3..W) of per-condition counts plus
five annual totals. Because snapshots overlap, most weeks are observed at
several vintages — that overlap is the revision signal, and it comes from the
summary table alone without touching the ~30 pages of county tables.

    python -m phoms.extract.michigan_parse one WSR-15-2026.pdf
    python -m phoms.extract.michigan_parse all

`all` writes snapshots/mi_wsr_parsed.csv with one row per
(pull_week, pull_year, condition, obs_year, obs_week, count).

Layout notes, verified across 2025 w1..w53 and 2026 w1..w27:
  * header row is ['Disease Group', 'Reportable Condition', <4 week labels>,
    <5 year labels>] and is stable in shape and position
  * week labels are "W-YYYY", NOT zero-padded inside the PDF even though the
    filename is; the window rolls back across year boundaries
    (WSR-01-2026 covers 51-2025..1-2026), so weeks must be read from the
    header, never derived from the filename
  * disease group is a sparse leading column — appears once per group, then
    None; forward-fill it
  * Subtotal rows collapse four cells into one ('0 0 0 0') and are skipped;
    subtotals are recomputable
"""

from __future__ import annotations

import pathlib
import re
import sys

import pandas as pd
import pdfplumber

SNAP = pathlib.Path("snapshots/mi_wsr")
OUT = pathlib.Path("snapshots/mi_wsr_parsed.csv")
WEEK_LABEL = re.compile(r"^(\d{1,2})-(\d{4})$")


def _find_header(table: list[list]) -> int | None:
    for i, row in enumerate(table):
        if row and row[0] == "Disease Group":
            return i
    return None


def parse_pdf(path: pathlib.Path) -> pd.DataFrame:
    """Return long-form weekly counts for one report. Annual columns are dropped."""
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        weeks: list[tuple[int, int]] = []
        group = None
        for page in pdf.pages:
            for table in page.extract_tables():
                h = _find_header(table)
                if h is not None:
                    weeks = []
                    for cell in table[h][2:6]:
                        m = WEEK_LABEL.match((cell or "").strip())
                        if m:
                            weeks.append((int(m.group(2)), int(m.group(1))))
                    body = table[h + 1 :]
                else:
                    body = table
                if not weeks:
                    continue

                for row in body:
                    if not row or len(row) < 6:
                        continue
                    if row[0]:
                        group = row[0].strip()
                    cond = (row[1] or "").strip()
                    if not cond or cond == "Subtotal":
                        continue
                    for (yr, wk), cell in zip(weeks, row[2:6], strict=False):
                        val = (cell or "").strip()
                        if not val.isdigit():
                            continue
                        rows.append(
                            {
                                "disease_group": group,
                                "condition": cond,
                                "obs_year": yr,
                                "obs_week": wk,
                                "count": int(val),
                            }
                        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # A condition can appear on more than one page fragment; keep one row per key.
    return df.drop_duplicates(subset=["condition", "obs_year", "obs_week"], keep="first")


def parse_all() -> pd.DataFrame:
    frames = []
    for p in sorted(SNAP.glob("WSR-*.pdf")):
        wk, yr = int(p.stem.split("-")[1]), int(p.stem.split("-")[2])
        df = parse_pdf(p)
        if df.empty:
            print(f"{p.name}: no rows")
            continue
        df["pull_year"], df["pull_week"] = yr, wk
        frames.append(df)
        print(f"{p.name}: {len(df)} rows")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT, index=False)
    print(f"\n{len(out):,} rows -> {OUT}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "one"
    if cmd == "one":
        name = sys.argv[2] if len(sys.argv) > 2 else "WSR-15-2026.pdf"
        d = parse_pdf(SNAP / name)
        print(f"{len(d)} rows, {d.condition.nunique()} conditions")
        print(d[d.condition.str.contains("Cyclospor", case=False)].to_string(index=False))
    elif cmd == "all":
        parse_all()
