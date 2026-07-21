"""
Turn consecutive snapshots into an append-only log of change events.

This is the revision lane. Every source lands snapshot-dated in S3 (ADR 5);
comparing consecutive vintages of the same period produces the log that the
nowcast learns its lag profile from. The log records only what MOVED, not every
row of every pull — Michigan's 79 snapshots hold 46,038 rows but yield ~4,500
change events, and that ratio holds as history grows.

Source-agnostic by design. Any frame in long form works:

    entity   obs_year  obs_week  count  suppressed
    -------  --------  --------  -----  ----------
    Michigan     2026        25   79.0       False

`entity_cols` names the columns that identify a series (disease, jurisdiction,
whatever the source provides); the module never assumes NNDSS or Michigan shape.

EVENT TYPES (ADR 5, decision A)
-------------------------------
  first_seen           period appears in a vintage for the first time.
                       prior_count is null. Emitted, not skipped — the lag
                       profile needs the starting point to measure movement from.
  count_change         a reported number changed. The core signal.
  suppression_lifted   was withheld, now reported. NOT a count change: the cases
                       were always there, the agency just started saying so.
  suppression_applied  was reported, now withheld. Rare, usually a correction.

Suppressed cells are NEVER imputed as zero. A withheld 4 read as 0 becomes a
phantom +4 revision the moment it is published, which would teach the lag model
a revision that never happened.

USAGE
-----
    from phoms.diff import diff_snapshots, build_log

    events = diff_snapshots(prior_df, current_df, entity_cols=["condition"],
                            vintage="2026-07-19")
    log = build_log(frames_by_vintage, entity_cols=["condition"])
"""

from __future__ import annotations

import pandas as pd

# Column order for the emitted log. Fixed so appends from different sources and
# different runs always line up.
EVENT_COLUMNS = [
    "source",
    "measure_type",
    "entity_key",
    "jurisdiction_grain",
    "obs_year",
    "obs_week",
    "event_type",
    "prior_count",
    "new_count",
    "delta",
    "direction",
    "prior_vintage",
    "vintage",
    "age_weeks",
]

EVENT_TYPES = frozenset({"first_seen", "count_change", "suppression_lifted", "suppression_applied"})


def _key(df: pd.DataFrame, entity_cols: list[str]) -> pd.Series:
    """Collapse the entity columns into one string key, so joins stay simple."""
    return df[entity_cols].astype(str).agg(" | ".join, axis=1)


def _age_weeks(obs_year: int, obs_week: int, vintage_year: int, vintage_week: int) -> int:
    """
    Weeks between an observation period and the vintage that reported it.

    Approximate: 53 weeks per year rather than a true MMWR calendar. Good enough
    for bucketing a lag profile, and it never goes negative within a source.
    """
    return (vintage_year * 53 + vintage_week) - (obs_year * 53 + obs_week)


def _prepare(
    df: pd.DataFrame,
    entity_cols: list[str],
    count_col: str,
    suppressed_col: str | None,
) -> pd.DataFrame:
    """Normalize an input frame to the internal shape. Does not mutate the input."""
    missing = set(entity_cols + ["obs_year", "obs_week", count_col]) - set(df.columns)
    if missing:
        raise ValueError(f"frame is missing required columns: {sorted(missing)}")

    out = pd.DataFrame(
        {
            "entity_key": _key(df, entity_cols),
            "obs_year": pd.to_numeric(df["obs_year"], errors="coerce").astype("Int64"),
            "obs_week": pd.to_numeric(df["obs_week"], errors="coerce").astype("Int64"),
            "count": pd.to_numeric(df[count_col], errors="coerce"),
        }
    )
    out["suppressed"] = (
        df[suppressed_col].fillna(False).astype(bool)
        if suppressed_col and suppressed_col in df.columns
        else out["count"].isna()
    )
    # A suppressed cell has no number. Enforce it so no downstream step can read
    # a stale value out of a withheld cell.
    out.loc[out["suppressed"], "count"] = pd.NA
    return out.dropna(subset=["obs_year", "obs_week"]).drop_duplicates(
        subset=["entity_key", "obs_year", "obs_week"], keep="last"
    )


def diff_snapshots(
    prior: pd.DataFrame | None,
    current: pd.DataFrame,
    entity_cols: list[str],
    vintage: str,
    prior_vintage: str | None = None,
    count_col: str = "count",
    suppressed_col: str | None = None,
    source: str = "unknown",
    measure_type: str = "routine_surveillance",
    grain_fn=None,
    vintage_period: tuple[int, int] | None = None,
) -> pd.DataFrame:
    """
    Compare two vintages of the same source and emit change events.

    prior=None emits first_seen for every period in `current` — the correct
    behavior for the first snapshot ever taken, not an error case.

    grain_fn maps an entity key to a jurisdiction grain (ADR 8). Left unset, the
    column is null and the mart is responsible for filtering.
    """
    cur = _prepare(current, entity_cols, count_col, suppressed_col)

    if prior is None or prior.empty:
        pri = cur.iloc[0:0].copy()
    else:
        pri = _prepare(prior, entity_cols, count_col, suppressed_col)

    merged = cur.merge(
        pri,
        on=["entity_key", "obs_year", "obs_week"],
        how="left",
        suffixes=("_new", "_prior"),
        indicator=True,
    )
    # itertuples mangles names starting with an underscore, so _merge must be
    # renamed before iterating.
    merged = merged.rename(columns={"_merge": "merge_side"})

    rows = []
    for r in merged.itertuples(index=False):
        new_sup = bool(r.suppressed_new)
        is_new_period = r.merge_side == "left_only"
        prior_sup = False if is_new_period else bool(r.suppressed_prior)
        new_val = None if new_sup or pd.isna(r.count_new) else float(r.count_new)
        prior_val = (
            None if is_new_period or prior_sup or pd.isna(r.count_prior) else float(r.count_prior)
        )

        if is_new_period:
            event_type = "first_seen"
        elif prior_sup and not new_sup:
            event_type = "suppression_lifted"
        elif new_sup and not prior_sup:
            event_type = "suppression_applied"
        elif new_sup and prior_sup:
            continue  # withheld in both vintages — nothing happened
        elif new_val == prior_val:
            continue  # unchanged, the common case
        else:
            event_type = "count_change"

        # A delta is only meaningful between two reported numbers. Suppression
        # transitions have no arithmetic difference, by definition.
        if event_type == "count_change":
            delta = new_val - prior_val
            direction = "up" if delta > 0 else "down"
        else:
            delta, direction = None, None

        rows.append(
            {
                "source": source,
                "measure_type": measure_type,
                "entity_key": r.entity_key,
                "jurisdiction_grain": grain_fn(r.entity_key) if grain_fn else None,
                "obs_year": int(r.obs_year),
                "obs_week": int(r.obs_week),
                "event_type": event_type,
                "prior_count": prior_val,
                "new_count": new_val,
                "delta": delta,
                "direction": direction,
                "prior_vintage": prior_vintage,
                "vintage": vintage,
                "age_weeks": (
                    _age_weeks(int(r.obs_year), int(r.obs_week), *vintage_period)
                    if vintage_period
                    else None
                ),
            }
        )

    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def build_log(
    frames: dict[str, pd.DataFrame],
    entity_cols: list[str],
    vintage_periods: dict[str, tuple[int, int]] | None = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Walk vintages in order, diffing each against the one before it.

    `frames` maps a vintage label to that vintage's frame. Labels sort
    chronologically (ISO dates, or "2026-27" style year-week).
    """
    log = []
    prior_label, prior_df = None, None
    for label in sorted(frames):
        events = diff_snapshots(
            prior_df,
            frames[label],
            entity_cols=entity_cols,
            vintage=label,
            prior_vintage=prior_label,
            vintage_period=(vintage_periods or {}).get(label),
            **kwargs,
        )
        log.append(events)
        prior_label, prior_df = label, frames[label]
    return pd.concat(log, ignore_index=True) if log else pd.DataFrame(columns=EVENT_COLUMNS)


def lag_profile(log: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize movement by observation age — the nowcast's input.

    Reports median alongside mean because the distribution is zero-inflated with
    a heavy tail: most periods never move, a few move enormously. Fitting to the
    mean alone would be wrong for both groups.
    """
    changes = log[log.event_type == "count_change"].copy()
    if changes.empty or changes["age_weeks"].isna().all():
        return pd.DataFrame()
    return (
        changes.groupby("age_weeks")
        .agg(
            events=("delta", "size"),
            median_delta=("delta", "median"),
            mean_delta=("delta", "mean"),
            up=("direction", lambda s: (s == "up").sum()),
            down=("direction", lambda s: (s == "down").sum()),
        )
        .reset_index()
    )
