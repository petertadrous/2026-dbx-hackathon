"""Tests for Test 1 — PIN reverse-lookup.

Covers EE-PIN-001..006.
"""
from __future__ import annotations

import pandas as pd
import pytest

from phantom_census.existence_engine import pin_lookup
from phantom_census.existence_engine.types import TestName, TestResult


# @spec EE-PIN-001
def test_pincode_parser_accepts_six_digit_string():
    assert pin_lookup.parse_pincode("400001") == "400001"


# @spec EE-PIN-001
def test_pincode_parser_strips_whitespace():
    assert pin_lookup.parse_pincode("  400001  ") == "400001"


# @spec EE-PIN-001
@pytest.mark.parametrize("bad", ["", None, "40000", "4000001", "abc123", "40000A"])
def test_pincode_parser_returns_none_on_bad_input(bad):
    assert pin_lookup.parse_pincode(bad) is None


def test_haversine_zero_when_identical():
    assert pin_lookup.haversine_km(19.0, 72.8, 19.0, 72.8) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance_mumbai_delhi():
    d = pin_lookup.haversine_km(19.0760, 72.8777, 28.6139, 77.2090)
    assert 1100 < d < 1200  # ~1150 km


# @spec EE-PIN-002
def test_pin_centroids_dedups_to_pincode(india_post_minimal):
    out = pin_lookup.build_pin_centroids(india_post_minimal)
    assert set(out["pincode"]) == {"400001", "800001"}
    mumbai = out[out["pincode"] == "400001"].iloc[0]
    assert 18.93 <= mumbai["latitude"] <= 18.97
    assert 72.81 <= mumbai["longitude"] <= 72.85


# @spec EE-PIN-002
def test_pin_centroids_returns_empty_when_columns_missing():
    df = pd.DataFrame({"foo": [1, 2]})
    out = pin_lookup.build_pin_centroids(df)
    assert out.empty


# @spec EE-PIN-002
def test_pin_centroids_returns_empty_when_dataframe_empty():
    df = pd.DataFrame(columns=["pincode", "district", "latitude", "longitude"])
    out = pin_lookup.build_pin_centroids(df)
    assert out.empty


# @spec EE-PIN-003, EE-PIN-005
def test_pin_pass_when_facility_within_50km(india_post_minimal):
    centroids = pin_lookup.build_pin_centroids(india_post_minimal)
    facilities = pd.DataFrame(
        [
            {"facility_id": "F1", "latitude": 19.00, "longitude": 72.85, "pincode": "400001"},
        ]
    )
    out = pin_lookup.run_pin_test(facilities, centroids)
    row = out.iloc[0]
    assert row["test_name"] == TestName.PIN_LOOKUP.value
    assert row["result"] == TestResult.PASS.value


# @spec EE-PIN-003, EE-PIN-004
def test_pin_fail_when_gps_far_from_pin_centroid(india_post_minimal):
    centroids = pin_lookup.build_pin_centroids(india_post_minimal)
    # Claim Mumbai PIN, GPS in Delhi
    facilities = pd.DataFrame(
        [
            {"facility_id": "F2", "latitude": 28.61, "longitude": 77.21, "pincode": "400001"},
        ]
    )
    out = pin_lookup.run_pin_test(facilities, centroids)
    row = out.iloc[0]
    assert row["result"] == TestResult.FAIL.value
    assert row["evidence_ref"]["distance_km"] > 50
    assert "pin_lat" in row["evidence_ref"]
    assert "pin_lon" in row["evidence_ref"]


# @spec EE-PIN-001
def test_pin_indeterminate_when_pin_unparseable(india_post_minimal):
    centroids = pin_lookup.build_pin_centroids(india_post_minimal)
    facilities = pd.DataFrame(
        [
            {"facility_id": "F3", "latitude": 19.0, "longitude": 72.8, "pincode": "abc"},
        ]
    )
    out = pin_lookup.run_pin_test(facilities, centroids)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-PIN-006
def test_pin_indeterminate_when_no_latlon(india_post_minimal):
    centroids = pin_lookup.build_pin_centroids(india_post_minimal)
    facilities = pd.DataFrame(
        [
            {"facility_id": "F4", "latitude": None, "longitude": None, "pincode": "400001"},
        ]
    )
    out = pin_lookup.run_pin_test(facilities, centroids)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# Boundary: 50 km exactly is pass (E5 resolution)
# @spec EE-PIN-005
def test_pin_boundary_exactly_50km_is_pass(monkeypatch):
    monkeypatch.setattr(pin_lookup, "haversine_km", lambda *a, **kw: 50.0)
    centroids = pd.DataFrame(
        [{"pincode": "400001", "latitude": 19.0, "longitude": 72.8}]
    )
    facilities = pd.DataFrame(
        [{"facility_id": "F5", "latitude": 19.5, "longitude": 72.8, "pincode": "400001"}]
    )
    out = pin_lookup.run_pin_test(facilities, centroids)
    assert out.iloc[0]["result"] == TestResult.PASS.value
