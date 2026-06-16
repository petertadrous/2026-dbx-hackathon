"""Tests for Defender Layer B — dataset-version reconciliation (pre-Adjudicator).

Covers EE-LAYER-B-001..006. Layer B writes `layer-b-override-pin` /
`layer-b-override-spatial` rows to `facility_existence_tests` when a Test 1
or Test 3 failure is explained by a known district reorganization or
spelling drift. Originals are preserved.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import layer_b
from phantom_census.existence_engine.types import TestName, TestResult


def _test_rows(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _facilities(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _reconciliation_table() -> pd.DataFrame:
    """Two example entries: a post-2022 district carve-out + a spelling variant."""
    return pd.DataFrame([
        {"pin_district": "Prakasam", "spatial_district": "Bapatla",
         "reason": "bapatla-from-prakasam-2022-carveout"},
        {"pin_district": "Mysore", "spatial_district": "Mysuru",
         "reason": "mysore-mysuru-spelling-drift"},
    ])


# @spec EE-LAYER-B-002
def test_pin_failure_explained_by_reconciliation_writes_override_pin_row():
    tests = _test_rows([{
        "facility_id": "F1",
        "test_name": TestName.PIN_LOOKUP.value,
        "result": TestResult.FAIL.value,
        "evidence_ref": {"pin_district": "Prakasam", "spatial_district": "Bapatla"},
    }])
    facilities = _facilities([{"facility_id": "F1"}])
    out = layer_b.run_layer_b(tests, facilities, _reconciliation_table())
    override = out[out["test_name"] == "layer-b-override-pin"]
    assert len(override) == 1
    row = override.iloc[0]
    assert row["facility_id"] == "F1"
    assert row["result"] == TestResult.PASS.value
    assert "matched" in row["evidence_ref"] or "reason" in row["evidence_ref"]


# @spec EE-LAYER-B-003
def test_spatial_failure_explained_by_reconciliation_writes_override_spatial_row():
    tests = _test_rows([{
        "facility_id": "F1",
        "test_name": TestName.SPATIAL.value,
        "result": TestResult.FAIL.value,
        "evidence_ref": {"pin_district": "Mysore", "spatial_district": "Mysuru"},
    }])
    facilities = _facilities([{"facility_id": "F1"}])
    out = layer_b.run_layer_b(tests, facilities, _reconciliation_table())
    override = out[out["test_name"] == "layer-b-override-spatial"]
    assert len(override) == 1
    assert override.iloc[0]["result"] == TestResult.PASS.value


# @spec EE-LAYER-B-004
def test_original_failing_rows_preserved_after_layer_b():
    original = _test_rows([{
        "facility_id": "F1",
        "test_name": TestName.PIN_LOOKUP.value,
        "result": TestResult.FAIL.value,
        "evidence_ref": {"pin_district": "Prakasam", "spatial_district": "Bapatla"},
    }])
    out = layer_b.run_layer_b(original, _facilities([{"facility_id": "F1"}]),
                               _reconciliation_table())
    pin_rows = out[(out["facility_id"] == "F1") &
                   (out["test_name"] == TestName.PIN_LOOKUP.value)]
    assert len(pin_rows) == 1
    assert pin_rows.iloc[0]["result"] == TestResult.FAIL.value


# @spec EE-LAYER-B-005
def test_at_most_one_override_per_facility_test_family():
    tests = _test_rows([
        {"facility_id": "F1", "test_name": TestName.PIN_LOOKUP.value,
         "result": TestResult.FAIL.value,
         "evidence_ref": {"pin_district": "Prakasam", "spatial_district": "Bapatla"}},
        {"facility_id": "F1", "test_name": TestName.SPATIAL.value,
         "result": TestResult.FAIL.value,
         "evidence_ref": {"pin_district": "Mysore", "spatial_district": "Mysuru"}},
    ])
    out = layer_b.run_layer_b(tests, _facilities([{"facility_id": "F1"}]),
                               _reconciliation_table())
    pin_override = out[out["test_name"] == "layer-b-override-pin"]
    spatial_override = out[out["test_name"] == "layer-b-override-spatial"]
    assert len(pin_override) == 1
    assert len(spatial_override) == 1


# @spec EE-LAYER-B-006
def test_no_override_when_no_reconciliation_match():
    tests = _test_rows([{
        "facility_id": "F1",
        "test_name": TestName.PIN_LOOKUP.value,
        "result": TestResult.FAIL.value,
        "evidence_ref": {"pin_district": "Mumbai", "spatial_district": "Pune"},
    }])
    out = layer_b.run_layer_b(tests, _facilities([{"facility_id": "F1"}]),
                               _reconciliation_table())
    override = out[out["test_name"].str.startswith("layer-b-override")]
    assert override.empty


# @spec EE-LAYER-B-001
def test_layer_b_only_evaluates_test1_and_test3_failures():
    """A Test 2 (MinHash) or Test 5 (Temporal) failure must not produce an override."""
    tests = _test_rows([{
        "facility_id": "F1",
        "test_name": TestName.MINHASH.value,
        "result": TestResult.FAIL.value,
        "evidence_ref": {"cluster_size": 4},
    }])
    out = layer_b.run_layer_b(tests, _facilities([{"facility_id": "F1"}]),
                               _reconciliation_table())
    override = out[out["test_name"].str.startswith("layer-b-override")]
    assert override.empty
