"""Tests for Test 4 — NFHS-5 outcome inconsistency.

Covers EE-NFHS-001..005.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import nfhs
from phantom_census.existence_engine.types import TestName, TestResult


# @spec EE-NFHS-001
def test_claims_maternity_matches_capability_keyword():
    assert nfhs.claims_maternity(["Maternity", "Surgery"], "")
    assert nfhs.claims_maternity(["NICU"], "")
    assert nfhs.claims_maternity([], "Provides antenatal and postnatal care.")


# @spec EE-NFHS-001
def test_claims_maternity_token_bounded_no_substring_false_positives():
    # "delivery" should match; "deliveryless" should not
    assert nfhs.claims_maternity([], "Delivery suite available")
    assert not nfhs.claims_maternity([], "Pizza deliveryless system")


# @spec EE-NFHS-001
def test_claims_maternity_false_when_no_terms():
    assert not nfhs.claims_maternity(["Cardiology"], "Cardiac arrhythmia care.")


# @spec EE-NFHS-002
def test_quartile_cutoffs_computed_per_state(nfhs_minimal):
    cutoffs = nfhs.state_quartile_cutoffs(nfhs_minimal)
    assert "Maharashtra" in cutoffs and "Bihar" in cutoffs
    # Bihar rates 80, 60, 50, 25 → Q25 = 43.75
    assert 40 < cutoffs["Bihar"] < 50
    # Maharashtra 95, 92, 88, 70 → Q25 = 83.5
    assert 80 < cutoffs["Maharashtra"] < 90


# @spec EE-NFHS-002
def test_quartile_drops_suppressed_values():
    df = pd.DataFrame(
        [
            {"district": "A", "state": "X", "institutional_delivery_rate": "*"},
            {"district": "B", "state": "X", "institutional_delivery_rate": 80.0},
            {"district": "C", "state": "X", "institutional_delivery_rate": 60.0},
            {"district": "D", "state": "X", "institutional_delivery_rate": 40.0},
            {"district": "E", "state": "X", "institutional_delivery_rate": 20.0},
        ]
    )
    cutoffs = nfhs.state_quartile_cutoffs(df)
    # Only 4 numeric rows → Q25 of [20,40,60,80] = 35
    assert 30 < cutoffs["X"] < 40


# @spec EE-NFHS-003
def test_nfhs_fail_when_maternity_claim_and_bottom_quartile_district(
    nfhs_minimal, district_to_state
):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "M1",
                "capability": ["Maternity", "NICU"],
                "description": "",
                "spatial_district": "Araria",  # rate 25 — below Bihar Q25 ~44
            }
        ]
    )
    out = nfhs.run_nfhs_test(facilities, nfhs_minimal, district_to_state)
    row = out.iloc[0]
    assert row["result"] == TestResult.FAIL.value
    assert row["evidence_ref"]["state"] == "Bihar"
    assert row["evidence_ref"]["district_rate"] == 25.0
    assert "state_cutoff" in row["evidence_ref"]


# @spec EE-NFHS-003
def test_nfhs_pass_when_maternity_and_district_above_cutoff(
    nfhs_minimal, district_to_state
):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "M2",
                "capability": ["Maternity"],
                "description": "",
                "spatial_district": "Mumbai",  # 95 — well above MH Q25 ~83
            }
        ]
    )
    out = nfhs.run_nfhs_test(facilities, nfhs_minimal, district_to_state)
    assert out.iloc[0]["result"] == TestResult.PASS.value


# @spec EE-NFHS-004
def test_nfhs_indeterminate_when_district_not_in_nfhs(nfhs_minimal, district_to_state):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "M3",
                "capability": ["Maternity"],
                "description": "",
                "spatial_district": "DistrictNotInNFHS",
            }
        ]
    )
    out = nfhs.run_nfhs_test(facilities, nfhs_minimal, district_to_state)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-NFHS-005
def test_nfhs_not_applicable_when_no_maternity_signal(nfhs_minimal, district_to_state):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "M4",
                "capability": ["Cardiology"],
                "description": "Heart disease clinic.",
                "spatial_district": "Araria",
            }
        ]
    )
    out = nfhs.run_nfhs_test(facilities, nfhs_minimal, district_to_state)
    assert out.iloc[0]["result"] == TestResult.NOT_APPLICABLE.value


# @spec EE-NFHS-002, EE-NFHS-003
def test_nfhs_normalizes_case_and_punctuation_across_sources():
    """Case + punctuation drift between sources should not break the join.

    True spelling drift (Mysore↔Mysuru, post-2022 carve-outs) is deferred
    to the Defender's reconciliation layer per E8.
    """
    nfhs_df = pd.DataFrame(
        [
            {"district": "BENGALURU URBAN", "state": "Karnataka",
             "institutional_delivery_rate": 30.0},
            {"district": "Mysuru", "state": "Karnataka",
             "institutional_delivery_rate": 95.0},
            {"district": "Hassan", "state": "Karnataka",
             "institutional_delivery_rate": 70.0},
            {"district": "Bidar", "state": "Karnataka",
             "institutional_delivery_rate": 50.0},
        ]
    )
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "DRIFT",
                "capability": ["Maternity"],
                "description": "",
                "spatial_district": "Bengaluru-Urban",  # ADM2 variant
            }
        ]
    )
    out = nfhs.run_nfhs_test(
        facilities, nfhs_df,
        {"Bengaluru-Urban": "Karnataka", "Mysuru": "Karnataka",
         "Hassan": "Karnataka", "Bidar": "Karnataka"},
    )
    # 30.0 is below Karnataka Q25 — should fail, not indeterminate
    assert out.iloc[0]["result"] == TestResult.FAIL.value
    assert out.iloc[0]["evidence_ref"]["state"] == "Karnataka"


# @spec EE-NFHS-001
def test_nfhs_test_name(nfhs_minimal, district_to_state):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "M5",
                "capability": ["Maternity"],
                "description": "",
                "spatial_district": "Mumbai",
            }
        ]
    )
    out = nfhs.run_nfhs_test(facilities, nfhs_minimal, district_to_state)
    assert out.iloc[0]["test_name"] == TestName.NFHS.value
