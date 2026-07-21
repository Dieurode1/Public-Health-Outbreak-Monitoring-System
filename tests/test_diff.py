"""Unit tests for the revision-diff module. Synthetic frames only."""

import pandas as pd

from phoms import diff


def frame(rows):
    """rows: list of (entity, year, week, count). None count = suppressed."""
    return pd.DataFrame(
        [{"condition": e, "obs_year": y, "obs_week": w, "count": c} for e, y, w, c in rows]
    )


def test_no_prior_emits_first_seen():
    cur = frame([("Cyclosporiasis", 2026, 25, 79)])
    ev = diff.diff_snapshots(None, cur, ["condition"], vintage="v1")
    assert len(ev) == 1
    assert ev.iloc[0].event_type == "first_seen"
    assert pd.isna(ev.iloc[0].prior_count)
    assert ev.iloc[0].new_count == 79


def test_unchanged_emits_nothing():
    f = frame([("Cyclosporiasis", 2026, 25, 79)])
    ev = diff.diff_snapshots(f, f, ["condition"], vintage="v2", prior_vintage="v1")
    assert ev.empty


def test_count_change_up_and_down():
    prior = frame([("A", 2026, 25, 79), ("B", 2026, 25, 50)])
    cur = frame([("A", 2026, 25, 812), ("B", 2026, 25, 40)])
    ev = diff.diff_snapshots(prior, cur, ["condition"], vintage="v2", prior_vintage="v1")
    assert set(ev.event_type) == {"count_change"}
    a = ev[ev.entity_key == "A"].iloc[0]
    b = ev[ev.entity_key == "B"].iloc[0]
    assert a.delta == 733 and a.direction == "up"
    assert b.delta == -10 and b.direction == "down"


def test_new_period_in_later_vintage_is_first_seen():
    prior = frame([("A", 2026, 25, 79)])
    cur = frame([("A", 2026, 25, 79), ("A", 2026, 26, 12)])
    ev = diff.diff_snapshots(prior, cur, ["condition"], vintage="v2", prior_vintage="v1")
    assert len(ev) == 1
    assert ev.iloc[0].event_type == "first_seen"
    assert ev.iloc[0].obs_week == 26


def test_suppression_lifted_is_not_a_count_change():
    """A withheld cell becoming reported is disclosure, not new cases."""
    prior = frame([("A", 2026, 25, None)])
    cur = frame([("A", 2026, 25, 4)])
    ev = diff.diff_snapshots(prior, cur, ["condition"], vintage="v2", prior_vintage="v1")
    r = ev.iloc[0]
    assert r.event_type == "suppression_lifted"
    assert pd.isna(r.delta)  # no arithmetic difference exists
    assert pd.isna(r.direction)
    assert pd.isna(r.prior_count)  # never imputed as zero
    assert r.new_count == 4


def test_suppression_applied():
    prior = frame([("A", 2026, 25, 4)])
    cur = frame([("A", 2026, 25, None)])
    ev = diff.diff_snapshots(prior, cur, ["condition"], vintage="v2", prior_vintage="v1")
    r = ev.iloc[0]
    assert r.event_type == "suppression_applied"
    assert r.prior_count == 4
    assert pd.isna(r.new_count)


def test_suppressed_in_both_emits_nothing():
    f = frame([("A", 2026, 25, None)])
    ev = diff.diff_snapshots(f, f, ["condition"], vintage="v2", prior_vintage="v1")
    assert ev.empty


def test_explicit_suppressed_column_beats_null_count():
    """A source may report 0 alongside a suppression flag; the flag wins."""
    prior = pd.DataFrame(
        [{"condition": "A", "obs_year": 2026, "obs_week": 25, "count": 0, "sup": True}]
    )
    cur = pd.DataFrame(
        [{"condition": "A", "obs_year": 2026, "obs_week": 25, "count": 4, "sup": False}]
    )
    ev = diff.diff_snapshots(
        prior, cur, ["condition"], vintage="v2", prior_vintage="v1", suppressed_col="sup"
    )
    assert ev.iloc[0].event_type == "suppression_lifted"
    assert pd.isna(ev.iloc[0].prior_count)


def test_multi_column_entity_key():
    prior = pd.DataFrame(
        [{"disease": "Cyclo", "state": "MI", "obs_year": 2026, "obs_week": 25, "count": 79}]
    )
    cur = pd.DataFrame(
        [{"disease": "Cyclo", "state": "MI", "obs_year": 2026, "obs_week": 25, "count": 812}]
    )
    ev = diff.diff_snapshots(prior, cur, ["disease", "state"], vintage="v2")
    assert ev.iloc[0].entity_key == "Cyclo | MI"


def test_age_weeks_and_year_boundary():
    cur = frame([("A", 2025, 52, 10)])
    ev = diff.diff_snapshots(None, cur, ["condition"], vintage="v1", vintage_period=(2026, 2))
    assert ev.iloc[0].age_weeks == 3  # 2026w2 is three weeks after 2025w52


def test_build_log_walks_vintages_in_order():
    frames = {
        "2026-01": frame([("A", 2026, 25, 79)]),
        "2026-02": frame([("A", 2026, 25, 200)]),
        "2026-03": frame([("A", 2026, 25, 812)]),
    }
    log = diff.build_log(frames, ["condition"])
    assert list(log.event_type) == ["first_seen", "count_change", "count_change"]
    assert list(log.prior_vintage) == [None, "2026-01", "2026-02"]
    assert list(log.delta.dropna()) == [121.0, 612.0]


def test_grain_fn_populates_jurisdiction():
    cur = frame([("Michigan", 2026, 25, 79)])
    ev = diff.diff_snapshots(None, cur, ["condition"], vintage="v1", grain_fn=lambda k: "state")
    assert ev.iloc[0].jurisdiction_grain == "state"


def test_lag_profile_reports_median_and_direction_split():
    frames = {
        "v1": frame([("A", 2026, 20, 10), ("B", 2026, 20, 10)]),
        "v2": frame([("A", 2026, 20, 100), ("B", 2026, 20, 5)]),
    }
    log = diff.build_log(
        frames, ["condition"], vintage_periods={"v1": (2026, 21), "v2": (2026, 22)}
    )
    prof = diff.lag_profile(log)
    row = prof[prof.age_weeks == 2].iloc[0]
    assert row.events == 2
    assert row.up == 1 and row.down == 1


def test_missing_required_column_raises():
    bad = pd.DataFrame([{"condition": "A", "obs_year": 2026}])
    try:
        diff.diff_snapshots(None, bad, ["condition"], vintage="v1")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "obs_week" in str(e)
