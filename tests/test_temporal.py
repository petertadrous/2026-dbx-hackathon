"""Tests for Test 5 — Temporal implausibility.

Covers EE-TEMP-001..005.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import temporal
from phantom_census.existence_engine.types import TestName, TestResult


CURRENT_YEAR = 2026


# @spec EE-TEMP-001
def test_parse_year_accepts_int():
    assert temporal.parse_year(1995) == 1995


# @spec EE-TEMP-001
def test_parse_year_accepts_string():
    assert temporal.parse_year("1995") == 1995


# @spec EE-TEMP-001
def test_parse_year_returns_none_on_garbage():
    assert temporal.parse_year("ninety-five") is None
    assert temporal.parse_year(None) is None
    assert temporal.parse_year("") is None


# @spec EE-TEMP-001
def test_temporal_indeterminate_when_year_unparseable():
    facilities = pd.DataFrame(
        [{"facility_id": "T1", "yearEstablished": "n/a",
          "capability": [], "description": ""}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-TEMP-002
def test_temporal_fail_when_year_in_future():
    facilities = pd.DataFrame(
        [{"facility_id": "T2", "yearEstablished": 2030,
          "capability": [], "description": ""}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    row = out.iloc[0]
    assert row["result"] == TestResult.FAIL.value
    assert row["evidence_ref"]["year"] == 2030


# @spec EE-TEMP-003
def test_temporal_fail_when_year_before_1900():
    facilities = pd.DataFrame(
        [{"facility_id": "T3", "yearEstablished": 1800,
          "capability": [], "description": ""}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    assert out.iloc[0]["result"] == TestResult.FAIL.value


# @spec EE-TEMP-004
def test_temporal_fail_when_post_2020_and_high_acuity_claim():
    facilities = pd.DataFrame(
        [{"facility_id": "T4", "yearEstablished": 2023,
          "capability": ["ICU"], "description": "Trauma services."}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    row = out.iloc[0]
    assert row["result"] == TestResult.FAIL.value
    assert row["evidence_ref"]["matched_term"] in {"icu", "trauma"}


# @spec EE-TEMP-004
def test_temporal_pass_when_post_2020_but_no_high_acuity():
    facilities = pd.DataFrame(
        [{"facility_id": "T5", "yearEstablished": 2023,
          "capability": ["Dental"], "description": "Outpatient dentistry."}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    assert out.iloc[0]["result"] == TestResult.PASS.value


# @spec EE-TEMP-005
def test_temporal_pass_when_year_plausible():
    facilities = pd.DataFrame(
        [{"facility_id": "T6", "yearEstablished": 1995,
          "capability": ["ICU"], "description": "Trauma center"}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    assert out.iloc[0]["result"] == TestResult.PASS.value


# @spec EE-TEMP-004
def test_high_acuity_token_bounded():
    """Substring 'icu' should not match within 'sicumber' or similar."""
    assert temporal.claims_high_acuity([], "icu present") in {"icu"}
    assert temporal.claims_high_acuity([], "I prefer cucumbers") is None


# @spec EE-TEMP-005
def test_temporal_test_name():
    facilities = pd.DataFrame(
        [{"facility_id": "T7", "yearEstablished": 2000,
          "capability": [], "description": ""}]
    )
    out = temporal.run_temporal_test(facilities, CURRENT_YEAR)
    assert out.iloc[0]["test_name"] == TestName.TEMPORAL.value
