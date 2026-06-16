"""Tests for the Adjudicator.

Covers EE-ADJ-001..007. Encodes the E1 + E2 resolutions:
  * insufficient-evidence takes precedence over veto (E1).
  * `not-applicable` is NOT testable; only PASS/FAIL count toward floor (E2).
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import adjudicator
from phantom_census.existence_engine.types import TestName, TestResult, Verdict


def _outcome(name: TestName, result: TestResult, ev: dict | None = None) -> dict:
    return {"test_name": name.value, "result": result.value, "evidence_ref": ev}


# @spec EE-ADJ-002
def test_veto_pin_fail_with_enough_evidence_yields_phantom():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.FAIL, {"distance_km": 800}),
        _outcome(TestName.MINHASH, TestResult.PASS),
        _outcome(TestName.SPATIAL, TestResult.PASS),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.PASS),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-002
def test_veto_spatial_fail_with_enough_evidence_yields_phantom():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.PASS),
        _outcome(TestName.MINHASH, TestResult.PASS),
        _outcome(TestName.SPATIAL, TestResult.FAIL, {"a": "b"}),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.PASS),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-003
def test_two_non_veto_fails_yields_phantom():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.PASS),
        _outcome(TestName.MINHASH, TestResult.FAIL),
        _outcome(TestName.SPATIAL, TestResult.PASS),
        _outcome(TestName.NFHS, TestResult.FAIL),
        _outcome(TestName.TEMPORAL, TestResult.PASS),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-004
def test_single_non_veto_fail_yields_contested():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.PASS),
        _outcome(TestName.MINHASH, TestResult.FAIL),
        _outcome(TestName.SPATIAL, TestResult.PASS),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.PASS),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.CONTESTED.value


# @spec EE-ADJ-005 (E1: insufficient evidence > veto)
def test_insufficient_evidence_takes_precedence_over_veto():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.FAIL, {"distance_km": 800}),  # veto
        _outcome(TestName.MINHASH, TestResult.INDETERMINATE),
        _outcome(TestName.SPATIAL, TestResult.INDETERMINATE),
        _outcome(TestName.NFHS, TestResult.INDETERMINATE),
        _outcome(TestName.TEMPORAL, TestResult.INDETERMINATE),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.CONTESTED.value
    assert out["reason"] == "insufficient-evidence"


# @spec EE-ADJ-005 (E2: not-applicable does not count as testable)
def test_not_applicable_does_not_count_toward_testable_floor():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.PASS),  # 1 testable
        _outcome(TestName.MINHASH, TestResult.INDETERMINATE),
        _outcome(TestName.SPATIAL, TestResult.INDETERMINATE),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.INDETERMINATE),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.CONTESTED.value
    assert out["reason"] == "insufficient-evidence"


# @spec EE-ADJ-006
def test_zero_fails_two_pass_yields_real():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.PASS),
        _outcome(TestName.MINHASH, TestResult.PASS),
        _outcome(TestName.SPATIAL, TestResult.PASS),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.INDETERMINATE),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    assert out["verdict"] == Verdict.REAL.value


# @spec EE-ADJ-007
def test_full_outcome_vector_preserved_in_result():
    outcomes = [
        _outcome(TestName.PIN_LOOKUP, TestResult.FAIL, {"distance_km": 800}),
        _outcome(TestName.MINHASH, TestResult.PASS),
        _outcome(TestName.SPATIAL, TestResult.PASS),
        _outcome(TestName.NFHS, TestResult.NOT_APPLICABLE),
        _outcome(TestName.TEMPORAL, TestResult.PASS),
    ]
    out = adjudicator.adjudicate_one(outcomes)
    vec = out["test_outcome_vector"]
    assert len(vec) == 5
    names = {o["test_name"] for o in vec}
    assert names == {n.value for n in (
        TestName.PIN_LOOKUP, TestName.MINHASH, TestName.SPATIAL,
        TestName.NFHS, TestName.TEMPORAL)}


# @spec EE-ADJ-001, EE-ADJ-007
def test_run_adjudicator_pivots_long_results_to_one_row_per_facility():
    long_results = pd.DataFrame(
        [
            {"facility_id": "F1", "test_name": TestName.PIN_LOOKUP.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F1", "test_name": TestName.MINHASH.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F1", "test_name": TestName.SPATIAL.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F1", "test_name": TestName.NFHS.value,
             "result": TestResult.NOT_APPLICABLE.value, "evidence_ref": None},
            {"facility_id": "F1", "test_name": TestName.TEMPORAL.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F2", "test_name": TestName.PIN_LOOKUP.value,
             "result": TestResult.FAIL.value, "evidence_ref": {"d": 800}},
            {"facility_id": "F2", "test_name": TestName.MINHASH.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F2", "test_name": TestName.SPATIAL.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
            {"facility_id": "F2", "test_name": TestName.NFHS.value,
             "result": TestResult.NOT_APPLICABLE.value, "evidence_ref": None},
            {"facility_id": "F2", "test_name": TestName.TEMPORAL.value,
             "result": TestResult.PASS.value, "evidence_ref": None},
        ]
    )
    out = adjudicator.run_adjudicator(long_results)
    by_fac = out.set_index("facility_id")
    assert by_fac.loc["F1", "verdict"] == Verdict.REAL.value
    assert by_fac.loc["F2", "verdict"] == Verdict.PHANTOM.value
