"""Config labels must exist in NNDSS. Catches upstream label renames."""

import pytest
import yaml

from phoms.http import session

DATASET = "https://data.cdc.gov/resource/x9gk-5huc.json"


@pytest.fixture(scope="module")
def cfg():
    with open("config/diseases.yml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def live_labels():
    r = session().get(DATASET, params={"$select": "distinct label", "$limit": 5000}, timeout=60)
    r.raise_for_status()
    return {x["label"] for x in r.json()}


def test_every_configured_label_exists(cfg, live_labels):
    missing = [
        (d, lab)
        for d, meta in cfg.items()
        for lab in meta["nndss_labels"]
        if lab not in live_labels
    ]
    assert not missing, f"labels not found in NNDSS: {missing}"


def test_required_fields_present(cfg):
    required = {"nndss_labels", "seasonality", "expected_lag_wks", "alert_eligible"}
    for name, meta in cfg.items():
        assert required <= meta.keys(), f"{name} missing {required - meta.keys()}"
