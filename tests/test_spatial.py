"""Tests for Test 3 — Spatial district mismatch.

Covers EE-SPATIAL-001..006.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import spatial
from phantom_census.existence_engine.types import TestName, TestResult


# @spec EE-SPATIAL-001, EE-SPATIAL-002
def test_assign_districts_returns_matching_district(facilities_minimal, districts_minimal):
    out = spatial.assign_districts(facilities_minimal, districts_minimal)
    assert out.iloc[0]["spatial_district"] == "Mumbai"


# @spec EE-SPATIAL-001
def test_assign_districts_nan_when_no_latlon(districts_minimal):
    facilities = pd.DataFrame(
        [{"facility_id": "X1", "latitude": None, "longitude": None}]
    )
    out = spatial.assign_districts(facilities, districts_minimal)
    assert pd.isna(out.iloc[0]["spatial_district"])


# @spec EE-SPATIAL-003
def test_modal_pin_district_picks_dominant():
    df = pd.DataFrame(
        [
            {"pincode": "400001", "district": "Mumbai"},
            {"pincode": "400001", "district": "Mumbai"},
            {"pincode": "400001", "district": "Mumbai"},
            {"pincode": "400001", "district": "Thane"},
        ]
    )
    out = spatial.modal_pin_district(df)
    row = out[out["pincode"] == "400001"].iloc[0]
    assert row["district"] == "Mumbai"
    assert row["modal_share"] == 0.75


# @spec EE-SPATIAL-003
def test_normalize_lowercase_and_strip():
    assert spatial.normalize_district_name(" Mumbai  ") == "mumbai"
    assert spatial.normalize_district_name("MUMBAI") == "mumbai"


# @spec EE-SPATIAL-004
def test_spatial_fail_when_pin_district_disagrees(
    facilities_minimal, districts_minimal, india_post_minimal
):
    # Facility claims PIN 800001 (Bihar/Patna) but sits in Mumbai polygon
    fac = facilities_minimal.copy()
    fac.loc[:, "pincode"] = "800001"
    out = spatial.run_spatial_test(fac, districts_minimal, india_post_minimal)
    row = out.iloc[0]
    assert row["test_name"] == TestName.SPATIAL.value
    assert row["result"] == TestResult.FAIL.value
    assert row["evidence_ref"]["spatial_district"].lower() == "mumbai"
    assert row["evidence_ref"]["pin_district"].lower() == "patna"


# @spec EE-SPATIAL-005
def test_spatial_pass_when_districts_agree(
    facilities_minimal, districts_minimal, india_post_minimal
):
    out = spatial.run_spatial_test(
        facilities_minimal, districts_minimal, india_post_minimal
    )
    assert out.iloc[0]["result"] == TestResult.PASS.value


# @spec EE-SPATIAL-006
def test_spatial_indeterminate_when_no_latlon(districts_minimal, india_post_minimal):
    facilities = pd.DataFrame(
        [{"facility_id": "X", "latitude": None, "longitude": None, "pincode": "400001"}]
    )
    out = spatial.run_spatial_test(facilities, districts_minimal, india_post_minimal)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-SPATIAL-006
def test_spatial_indeterminate_when_no_pin(districts_minimal, india_post_minimal):
    facilities = pd.DataFrame(
        [{"facility_id": "X", "latitude": 19.0, "longitude": 72.88, "pincode": None}]
    )
    out = spatial.run_spatial_test(facilities, districts_minimal, india_post_minimal)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-SPATIAL-003 (E4 resolution: ambiguous-PIN modal ≤ 0.5 → indeterminate)
def test_spatial_indeterminate_when_pin_ambiguous(districts_minimal):
    india_post = pd.DataFrame(
        [
            {"pincode": "999999", "district": "Mumbai",
             "latitude": 19.0, "longitude": 72.88},
            {"pincode": "999999", "district": "Thane",
             "latitude": 19.0, "longitude": 72.88},
        ]
    )
    facilities = pd.DataFrame(
        [{"facility_id": "Y", "latitude": 19.0, "longitude": 72.88, "pincode": "999999"}]
    )
    out = spatial.run_spatial_test(facilities, districts_minimal, india_post)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value
