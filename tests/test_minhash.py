"""Tests for Test 2 — MinHash near-duplicate.

Covers EE-HASH-001..005.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import minhash
from phantom_census.existence_engine.types import TestName, TestResult


# @spec EE-HASH-001
def test_claim_text_concatenates_three_arrays():
    row = pd.Series(
        {
            "capability": ["Maternity", "NICU"],
            "procedure": ["C-section"],
            "equipment": ["Ventilator"],
        }
    )
    text = minhash.build_claim_text(row)
    assert "Maternity" in text and "NICU" in text
    assert "C-section" in text
    assert "Ventilator" in text


# @spec EE-HASH-002
def test_minhash_indeterminate_when_text_too_short():
    facilities = pd.DataFrame(
        [
            {"facility_id": "S1", "capability": [], "procedure": [], "equipment": ["x"]},
        ]
    )
    out = minhash.run_minhash_test(facilities)
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-HASH-002
def test_minhash_indeterminate_overrides_cluster_membership():
    """A facility with short text and 5 identical short-text twins
    still receives indeterminate, not fail. Guard is unconditional."""
    short_row = {
        "capability": ["X"],
        "procedure": ["Y"],
        "equipment": ["Z"],
    }
    facilities = pd.DataFrame(
        [{"facility_id": f"T{i}", **short_row} for i in range(5)]
    )
    out = minhash.run_minhash_test(facilities)
    assert (out["result"] == TestResult.INDETERMINATE.value).all()


def _long_claim(seed: str) -> dict:
    """Build a long, claim-rich record (≥30 whitespace tokens to clear EE-HASH-002).
    Same seed → identical content, so any pair sharing a seed is a near-duplicate.
    """
    return {
        "capability": [
            f"Maternity ward {seed}", f"NICU level three {seed}",
            f"Obstetrics {seed}", f"Pediatric ICU {seed}",
            f"General surgery {seed}", f"Cardiology unit {seed}",
            f"Emergency dept {seed}", f"Internal medicine {seed}",
        ],
        "procedure": [
            f"Cesarean section {seed}", f"Vaginal delivery {seed}",
            f"Hysterectomy {seed}", f"Appendectomy {seed}",
            f"Tonsillectomy {seed}", f"Hernia repair {seed}",
        ],
        "equipment": [
            f"Mechanical ventilator {seed}", f"Ultrasound machine {seed}",
            f"MRI scanner {seed}", f"CT scanner {seed}",
            f"Incubator {seed}", f"Defibrillator {seed}",
        ],
    }


# @spec EE-HASH-003, EE-HASH-004
def test_minhash_fail_when_cluster_size_at_least_three():
    facilities = pd.DataFrame(
        [
            {"facility_id": "D1", **_long_claim("alpha")},
            {"facility_id": "D2", **_long_claim("alpha")},  # exact duplicate
            {"facility_id": "D3", **_long_claim("alpha")},  # exact duplicate
            {"facility_id": "U1", **_long_claim("beta")},   # unique
        ]
    )
    out = minhash.run_minhash_test(facilities)
    by_fac = out.set_index("facility_id")
    assert by_fac.loc["D1", "result"] == TestResult.FAIL.value
    assert by_fac.loc["D2", "result"] == TestResult.FAIL.value
    assert by_fac.loc["D3", "result"] == TestResult.FAIL.value
    assert by_fac.loc["U1", "result"] == TestResult.PASS.value


# @spec EE-HASH-004
def test_minhash_fail_evidence_includes_cluster_members():
    facilities = pd.DataFrame(
        [
            {"facility_id": "E1", **_long_claim("gamma")},
            {"facility_id": "E2", **_long_claim("gamma")},
            {"facility_id": "E3", **_long_claim("gamma")},
        ]
    )
    out = minhash.run_minhash_test(facilities)
    ev = out.iloc[0]["evidence_ref"]
    assert ev["cluster_size"] >= 3
    assert set(ev["cluster_member_ids"]) == {"E1", "E2", "E3"}


# @spec EE-HASH-005
def test_minhash_pass_when_cluster_size_below_three():
    facilities = pd.DataFrame(
        [
            {"facility_id": "P1", **_long_claim("delta")},
            {"facility_id": "P2", **_long_claim("delta")},  # only 2 — below threshold
            {"facility_id": "P3", **_long_claim("epsilon")},  # unique
        ]
    )
    out = minhash.run_minhash_test(facilities)
    by_fac = out.set_index("facility_id")
    assert by_fac.loc["P1", "result"] == TestResult.PASS.value
    assert by_fac.loc["P2", "result"] == TestResult.PASS.value
    assert by_fac.loc["P3", "result"] == TestResult.PASS.value


# @spec EE-HASH-001
def test_minhash_test_name_set_correctly():
    facilities = pd.DataFrame(
        [{"facility_id": "T", **_long_claim("zeta")}]
    )
    out = minhash.run_minhash_test(facilities)
    assert (out["test_name"] == TestName.MINHASH.value).all()
