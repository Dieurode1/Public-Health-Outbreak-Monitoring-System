"""
Data quality checks for NNDSS snapshots.

Pure functions over a DataFrame — no knowledge of where the data came from.
Called by the verification scripts today, by Dagster asset checks in session 2.
Nothing here gets rewritten when the landing zone moves to S3.

Each check returns a CheckResult(passed, message, detail). None of them raise;
callers decide what is fatal. `run_all` gives the summary.

Scope: these validate that the pull ARRIVED correctly. Prior-week counts moving
between pulls is the project's signal, not a defect — that belongs in the diff
module, never here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# Jurisdiction grains (ADR 8). NNDSS mixes all three in one `states` column;
# unclassified values are how rollup double-counting gets back in.
# NNDSS is case-inconsistent across years: "Total" in some, "TOTAL" in others,
# and it drops punctuation ("U.S. Residents" vs "US RESIDENTS"). Membership is
# tested against a normalized key, never the raw string — otherwise rollups fall
# through to `state` and get summed as if they were jurisdictions.
NATIONAL = {"us residents", "total", "non us residents"}
REGIONS = {
    "new england",
    "middle atlantic",
    "east north central",
    "west north central",
    "south atlantic",
    "east south central",
    "west south central",
    "mountain",
    "pacific",
    "us territories",
}

# Same jurisdiction under two names across years. Left unmapped, the diff
# treats them as separate jurisdictions and the revision log splits in two.
JURISDICTION_ALIASES = {
    "commonwealth of northern mariana islands": "northern mariana islands",
}

REQUIRED_COLUMNS = {"states", "year", "week", "label", "m1"}


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.message}"


def normalize_jurisdiction(state: str) -> str:
    """
    Lowercase, strip punctuation, collapse whitespace and split initialisms.

    "U.S. Residents" and "US RESIDENTS" must land on the same key, so dotted
    initialisms are rejoined after punctuation removal ("u s" -> "us").
    """
    key = re.sub(r"[.,\-]", " ", str(state)).lower()
    key = re.sub(r"\s+", " ", key).strip()
    key = re.sub(r"\b([a-z])\s+(?=[a-z]\b)", r"\1", key)
    return JURISDICTION_ALIASES.get(key, key)


def classify_grain(state: str) -> str:
    """Map a `states` value to national | region | state, case-insensitively."""
    key = normalize_jurisdiction(state)
    if key in NATIONAL:
        return "national"
    if key in REGIONS:
        return "region"
    return "state"


def check_schema(df: pd.DataFrame) -> CheckResult:
    """Required columns present. Catches an upstream schema change."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    return CheckResult(
        "schema",
        not missing,
        "all required columns present" if not missing else f"missing: {sorted(missing)}",
        {"missing": sorted(missing), "found": sorted(df.columns)},
    )


def check_not_empty(df: pd.DataFrame) -> CheckResult:
    """A pull returning nothing usually means a bad filter, not a quiet week."""
    n = len(df)
    return CheckResult("not_empty", n > 0, f"{n} rows", {"rows": n})


def check_labels(df: pd.DataFrame, expected: list[str]) -> CheckResult:
    """Every label matches config. An unexpected label means the filter widened."""
    if "label" not in df.columns:
        return CheckResult("labels", False, "no label column", {})
    found = set(df["label"].dropna().unique())
    unexpected = found - set(expected)
    return CheckResult(
        "labels",
        not unexpected,
        f"{len(found)} label(s) as configured"
        if not unexpected
        else f"unexpected: {sorted(unexpected)}",
        {"found": sorted(found), "unexpected": sorted(unexpected)},
    )


def check_week_range(df: pd.DataFrame) -> CheckResult:
    """Weeks are 1-53. Out-of-range values mean a parse or source problem."""
    if "week" not in df.columns:
        return CheckResult("week_range", False, "no week column", {})
    wk = pd.to_numeric(df["week"], errors="coerce")
    bad = df[wk.isna() | (wk < 1) | (wk > 53)]
    return CheckResult(
        "week_range",
        bad.empty,
        "all weeks in 1-53" if bad.empty else f"{len(bad)} rows out of range",
        {"bad_rows": len(bad)},
    )


def check_grain_coverage(df: pd.DataFrame, known_states: set[str] | None = None) -> CheckResult:
    """
    Every jurisdiction classifies into a known grain (ADR 8).

    Pass `known_states` to catch new jurisdiction strings that would otherwise
    fall through to `state` by default and silently join the alerting path.
    """
    if "states" not in df.columns:
        return CheckResult("grain_coverage", False, "no states column", {})
    values = set(df["states"].dropna().unique())
    counts = {"national": 0, "region": 0, "state": 0}
    for v in values:
        counts[classify_grain(v)] += 1
    unknown = (
        sorted({v for v in values if classify_grain(v) == "state"} - known_states)
        if known_states
        else []
    )
    return CheckResult(
        "grain_coverage",
        not unknown,
        f"{len(values)} jurisdictions: {counts}"
        if not unknown
        else f"{len(unknown)} unrecognized: {unknown[:5]}",
        {"counts": counts, "unknown": unknown},
    )


def check_rollup_consistency(
    df: pd.DataFrame, tolerance: float = 0.05, min_gap: float = 2
) -> CheckResult:
    """
    State-grain rows sum to roughly the national Total, WITHIN each (year, week).

    Compared per period, not in aggregate. An aggregate comparison passes
    whenever both sides happen to span the same years, which hides two real
    failures: a partial year on one side only, and a single week where a
    jurisdiction's rows went missing (invisible inside a five-year sum).

    Tolerance is loose by design: territories and reporting-jurisdiction quirks
    (NY vs NYC) make exact equality unrealistic. Reports the worst period.
    """
    if not {"states", "year", "week", "m1"} <= set(df.columns):
        return CheckResult("rollup_consistency", False, "missing states/year/week/m1", {})

    work = pd.DataFrame(
        {
            "year": pd.to_numeric(df["year"], errors="coerce"),
            "week": pd.to_numeric(df["week"], errors="coerce"),
            "m1": pd.to_numeric(df["m1"], errors="coerce").fillna(0),
            "grain": df["states"].map(classify_grain),
            "norm": df["states"].map(normalize_jurisdiction),
        }
    ).dropna(subset=["year", "week"])

    # TOTAL includes non-US residents, who have no state. Add them to the state
    # side or every period with a foreign-acquired case reads as a shortfall.
    states = work[work.grain == "state"].groupby(["year", "week"])["m1"].sum()
    non_us = work[work.norm == "non us residents"].groupby(["year", "week"])["m1"].sum()
    totals = work[work.norm == "total"].groupby(["year", "week"])["m1"].sum()

    both = pd.DataFrame({"states": states, "non_us": non_us, "total": totals})
    both["states"] = both["states"].fillna(0)
    both["non_us"] = both["non_us"].fillna(0)
    both = both.dropna(subset=["total"])
    both = both[both["total"] > 0]

    if both.empty:
        return CheckResult("rollup_consistency", True, "no comparable periods (skipped)", {})

    both["expected"] = both["states"] + both["non_us"]
    both["gap"] = (both["expected"] - both["total"]).abs()
    both["drift"] = both["gap"] / both["total"]

    # A percentage is meaningless at single-digit counts: one case against a
    # total of 3 is 33% drift and means nothing. Require BOTH a relative and an
    # absolute miss before failing.
    both["fails"] = (both["drift"] > tolerance) & (both["gap"] > min_gap)
    worst = both["drift"].idxmax()
    worst_drift = float(both.loc[worst, "drift"])
    worst_gap = float(both.loc[worst, "gap"])
    failing = both[both["fails"]]

    return CheckResult(
        "rollup_consistency",
        failing.empty,
        f"{len(both)} periods checked, worst {worst_drift:.1%} "
        f"({worst_gap:.0f} cases) at {int(worst[0])}w{int(worst[1])}"
        if failing.empty
        else f"{len(failing)}/{len(both)} periods over tolerance, worst {worst_drift:.1%} "
        f"({worst_gap:.0f} cases) at {int(worst[0])}w{int(worst[1])}",
        {
            "periods_checked": len(both),
            "periods_failing": len(failing),
            "worst_period": [int(worst[0]), int(worst[1])],
            "worst_drift": worst_drift,
            "worst_gap": worst_gap,
        },
    )


def check_volume(df: pd.DataFrame, prior_rows: int | None, tolerance: float = 0.20) -> CheckResult:
    """
    Row count within tolerance of the prior snapshot.

    A truncated response looks like valid data downstream, so this is the check
    most likely to catch a silent failure.
    """
    n = len(df)
    if prior_rows is None:
        return CheckResult("volume", True, f"{n} rows (no prior snapshot)", {"rows": n})
    drift = abs(n - prior_rows) / prior_rows if prior_rows else 0
    return CheckResult(
        "volume",
        drift <= tolerance,
        f"{n} rows vs {prior_rows} prior ({drift:+.1%})",
        {"rows": n, "prior_rows": prior_rows, "drift": float(drift)},
    )


def check_freshness(df: pd.DataFrame, prior_max_week: tuple[int, int] | None) -> CheckResult:
    """
    Max (year, week) advanced since the prior pull.

    Not advancing is not always an error — CDC may not have published — but it
    also looks exactly like a cached response, so it warrants a look.
    """
    if not {"year", "week"} <= set(df.columns):
        return CheckResult("freshness", False, "missing year or week", {})
    yr = pd.to_numeric(df["year"], errors="coerce")
    wk = pd.to_numeric(df["week"], errors="coerce")
    valid = pd.DataFrame({"year": yr, "week": wk}).dropna()
    if valid.empty:
        return CheckResult("freshness", False, "no parseable year/week", {})
    max_yr = int(valid["year"].max())
    current = (max_yr, int(valid[valid["year"] == max_yr]["week"].max()))
    if prior_max_week is None:
        return CheckResult("freshness", True, f"latest {current} (no prior)", {"current": current})
    return CheckResult(
        "freshness",
        current > prior_max_week,
        f"latest {current} vs {prior_max_week} prior",
        {"current": current, "prior": prior_max_week},
    )


def run_all(
    df: pd.DataFrame,
    expected_labels: list[str],
    prior_rows: int | None = None,
    prior_max_week: tuple[int, int] | None = None,
    known_states: set[str] | None = None,
) -> list[CheckResult]:
    """Run every check. Returns results in report order; nothing raises."""
    return [
        check_schema(df),
        check_not_empty(df),
        check_labels(df, expected_labels),
        check_week_range(df),
        check_grain_coverage(df, known_states),
        check_rollup_consistency(df),
        check_volume(df, prior_rows),
        check_freshness(df, prior_max_week),
    ]


def report(results: list[CheckResult]) -> bool:
    """Print results, return True if all passed."""
    for r in results:
        print(r)
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return not failed
