"""Unit tests for quality checks. Synthetic frames only — no network."""

import pandas as pd

from phoms import quality as q


def frame(**overrides):
    base = {
        "states": ["Michigan", "Ohio", "East North Central", "Total"],
        "year": ["2026", "2026", "2026", "2026"],
        "week": [27, 27, 27, 27],
        "label": ["Cyclosporiasis"] * 4,
        "m1": [10, 15, 25, 25],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_classify_grain():
    assert q.classify_grain("Total") == "national"
    assert q.classify_grain("East North Central") == "region"
    assert q.classify_grain("Michigan") == "state"


def test_schema_passes_and_fails():
    assert q.check_schema(frame()).passed
    assert not q.check_schema(frame().drop(columns=["m1"])).passed


def test_not_empty():
    assert q.check_not_empty(frame()).passed
    assert not q.check_not_empty(frame().iloc[0:0]).passed


def test_labels_flags_unexpected():
    assert q.check_labels(frame(), ["Cyclosporiasis"]).passed
    bad = frame(label=["Cyclosporiasis", "Malaria", "Cyclosporiasis", "Total"])
    r = q.check_labels(bad, ["Cyclosporiasis"])
    assert not r.passed and "Malaria" in r.detail["unexpected"]


def test_week_range():
    assert q.check_week_range(frame()).passed
    assert not q.check_week_range(frame(week=[0, 27, 54, 27])).passed


def test_grain_coverage_flags_unknown_state():
    r = q.check_grain_coverage(frame(), known_states={"Michigan", "Ohio"})
    assert r.passed
    r = q.check_grain_coverage(frame(), known_states={"Michigan"})
    assert not r.passed and "Ohio" in r.detail["unknown"]


def test_rollup_consistency():
    assert q.check_rollup_consistency(frame()).passed
    off = frame(m1=[10, 15, 25, 100])
    assert not q.check_rollup_consistency(off).passed


def test_rollup_skips_without_total():
    no_total = frame(states=["Michigan", "Ohio", "East North Central", "Florida"])
    assert q.check_rollup_consistency(no_total).passed


def test_volume():
    assert q.check_volume(frame(), prior_rows=None).passed
    assert q.check_volume(frame(), prior_rows=4).passed
    assert not q.check_volume(frame(), prior_rows=100).passed


def test_freshness():
    assert q.check_freshness(frame(), prior_max_week=None).passed
    assert q.check_freshness(frame(), prior_max_week=(2026, 26)).passed
    assert not q.check_freshness(frame(), prior_max_week=(2026, 27)).passed
    assert not q.check_freshness(frame(), prior_max_week=(2026, 30)).passed


def test_run_all_and_report(capsys):
    results = q.run_all(frame(), ["Cyclosporiasis"])
    assert len(results) == 8
    assert q.report(results)
    assert "8/8 checks passed" in capsys.readouterr().out


def test_classify_grain_is_case_insensitive():
    """NNDSS uses Title Case in some years, UPPERCASE in others."""
    for variant in ["Total", "TOTAL", "total"]:
        assert q.classify_grain(variant) == "national"
    for variant in ["East North Central", "EAST NORTH CENTRAL"]:
        assert q.classify_grain(variant) == "region"
    for variant in ["U.S. Residents", "US RESIDENTS", "Non-U.S. Residents"]:
        assert q.classify_grain(variant) == "national"
    for variant in ["Michigan", "MICHIGAN", "New York City", "NEW YORK CITY"]:
        assert q.classify_grain(variant) == "state"


def test_rollup_consistency_uppercase_total():
    upper = frame(states=["MICHIGAN", "OHIO", "EAST NORTH CENTRAL", "TOTAL"])
    assert q.check_rollup_consistency(upper).passed


def test_jurisdiction_aliases_collapse():
    """NNDSS names the same territory two ways across years."""
    assert q.normalize_jurisdiction(
        "Commonwealth of Northern Mariana Islands"
    ) == q.normalize_jurisdiction("Northern Mariana Islands")


def periods(**overrides):
    """Two periods, each internally consistent: states + non_us == total."""
    base = {
        "states": ["Michigan", "Ohio", "Non-U.S. Residents", "Total"] * 2,
        "year": ["2026"] * 8,
        "week": [10] * 4 + [11] * 4,
        "label": ["Cyclosporiasis"] * 8,
        "m1": [10, 15, 1, 26, 20, 30, 2, 52],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_rollup_counts_non_us_residents():
    """TOTAL includes non-US residents, who have no state."""
    assert q.check_rollup_consistency(periods()).passed


def test_rollup_compares_per_period_not_aggregate():
    """One broken period must fail even when the file-wide sum balances."""
    # wk10 total inflated by 10, wk11 deflated by 10: aggregate nets to zero.
    broken = periods(m1=[10, 15, 1, 36, 20, 30, 2, 42])
    r = q.check_rollup_consistency(broken)
    assert not r.passed
    assert r.detail["periods_failing"] == 2


def test_rollup_min_gap_floor():
    """A one-case gap at tiny counts is 33% drift and means nothing."""
    tiny = pd.DataFrame(
        {
            "states": ["Tennessee", "Arkansas", "Total"],
            "year": ["2022"] * 3,
            "week": [50] * 3,
            "label": ["Cyclosporiasis"] * 3,
            "m1": [1, 1, 3],
        }
    )
    assert q.check_rollup_consistency(tiny).passed  # gap of 1, under floor
    assert not q.check_rollup_consistency(tiny, min_gap=0).passed
