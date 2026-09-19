"""Regression cases for the September 19 causality/configuration audit."""
from copy import deepcopy

import pytest

from pc.experiment.preprocessing.config import validate_preprocessing_config
from pc.experiment.tests.test_stage25_builder import (
    _build, _builder_config, _records,
)


def test_bias_initialization_rows_cannot_be_published_as_causal_output():
    config = _builder_config()
    result = _build(config=config)
    assert result["common_grid_rows"]
    assert all(row["grid_pc_time_ns"] > 114_000_000
               for row in result["common_grid_rows"])


def test_bias_window_covering_entire_recording_fails_closed():
    config = _builder_config()
    config["bias_correction"]["window_end_pc_ns"] = 140_000_000
    with pytest.raises(ValueError, match="after.*bias|bias.*output"):
        _build(config=config)


def test_future_motion_cannot_change_preceding_post_initialization_output():
    before = _records()
    after = deepcopy(before)
    for row in after:
        if row["pc_mapped_ts_ns"] > 120_000_000:
            row["x"] += 100
            row["y"] -= 37
    original = _build(records=before)["common_grid_rows"]
    changed = _build(records=after)["common_grid_rows"]
    assert [row for row in original if row["grid_pc_time_ns"] <= 120_000_000] == [
        row for row in changed if row["grid_pc_time_ns"] <= 120_000_000
    ]


@pytest.mark.parametrize("field", ["grid", "filter"])
def test_contradictory_sample_rates_are_rejected(field):
    config = _builder_config()
    if field == "grid":
        config["grid_frequency_hz"] = 1000.0
    else:
        config["low_pass_filter"]["grid_frequency_hz"] = 50.0
    with pytest.raises(ValueError, match="frequency|interval"):
        validate_preprocessing_config(config)


def test_arbitrary_hash_role_cannot_replace_required_sources():
    config = _builder_config()
    config["source_artifact_paths"] = {"unrelated": "missing.txt"}
    config["source_artifact_hashes"] = {"unrelated": "0" * 64}
    with pytest.raises(ValueError, match="required.*source|source.*required"):
        validate_preprocessing_config(config)
