"""Tests for the Adjudicator.

Covers EE-ADJ-001..009. Encodes:
  * Precedence: insufficient-evidence (< 2 testable) is evaluated BEFORE veto.
  * `not-applicable` and `indeterminate` are NOT testable; only PASS/FAIL count.
  * Six tests in the outcome vector: PIN, MinHash, Spatial, NFHS, Temporal, Embedding-Drift.
  * EE-ADJ-002: Adjudicator consumes `layer-b-override-*` rows in place of the originals.
  * EE-ADJ-008: writes both `adjudicator_verdict` (immutable) and `verdict` (mutable).
  * EE-ADJ-009: persists the full 6-test outcome vector as JSONB.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import adjudicator
from phantom_census.existence_engine.types import TestName, TestResult, Verdict


def _outcome(name: TestName, result: TestResult, ev: dict | None = None) -> dict:
    return {"test_name": name.value, "result": result.value, "evidence_ref": ev}


def _six_outcomes(
    pin: TestResult, minhash: TestResult, spatial: TestResult,
    nfhs: TestResult, temporal: TestResult, embedding: TestResult,
) -> list[dict]:
    return [
        _outcome(TestName.PIN_LOOKUP, pin),
        _outcome(TestName.MINHASH, minhash),
        _outcome(TestName.SPATIAL, spatial),
        _outcome(TestName.NFHS, nfhs),
        _outcome(TestName.TEMPORAL, temporal),
        _outcome(TestName.EMBEDDING, embedding),
    ]


# @spec EE-ADJ-004
def test_veto_pin_fail_with_enough_evidence_yields_phantom():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.FAIL, TestResult.PASS, TestResult.PASS,
        TestResult.NOT_APPLICABLE, TestResult.PASS, TestResult.PASS,
    ))
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-004
def test_veto_spatial_fail_with_enough_evidence_yields_phantom():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS, TestResult.PASS, TestResult.FAIL,
        TestResult.NOT_APPLICABLE, TestResult.PASS, TestResult.PASS,
    ))
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-005
def test_two_non_veto_fails_yields_phantom():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS, TestResult.FAIL, TestResult.PASS,
        TestResult.FAIL, TestResult.PASS, TestResult.PASS,
    ))
    assert out["verdict"] == Verdict.PHANTOM.value


# @spec EE-ADJ-006
def test_single_non_veto_fail_yields_contested():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS, TestResult.FAIL, TestResult.PASS,
        TestResult.NOT_APPLICABLE, TestResult.PASS, TestResult.PASS,
    ))
    assert out["verdict"] == Verdict.CONTESTED.value


# @spec EE-ADJ-003
def test_insufficient_evidence_takes_precedence_over_veto():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.FAIL,  # veto-capable fail
        TestResult.INDETERMINATE, TestResult.INDETERMINATE,
        TestResult.INDETERMINATE, TestResult.INDETERMINATE,
        TestResult.INDETERMINATE,
    ))
    assert out["verdict"] == Verdict.CONTESTED.value
    assert out["reason"] == "insufficient-evidence"


# @spec EE-ADJ-003
def test_not_applicable_does_not_count_toward_testable_floor():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS,  # only testable result
        TestResult.INDETERMINATE, TestResult.INDETERMINATE,
        TestResult.NOT_APPLICABLE, TestResult.INDETERMINATE,
        TestResult.INDETERMINATE,
    ))
    assert out["verdict"] == Verdict.CONTESTED.value
    assert out["reason"] == "insufficient-evidence"


# @spec EE-ADJ-007
def test_zero_fails_two_pass_yields_real():
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS, TestResult.PASS, TestResult.PASS,
        TestResult.NOT_APPLICABLE, TestResult.INDETERMINATE,
        TestResult.INDETERMINATE,
    ))
    assert out["verdict"] == Verdict.REAL.value


# @spec EE-ADJ-007
def test_first_batch_embedding_indeterminate_still_allows_real():
    """EE-EMBED-007: first batch produces indeterminate for Test 6; EE-ADJ-007
    only requires ≥2 PASS across all tests — embedding indeterminate is fine."""
    out = adjudicator.adjudicate_one(_six_outcomes(
        TestResult.PASS, TestResult.PASS, TestResult.PASS,
        TestResult.NOT_APPLICABLE, TestResult.PASS, TestResult.INDETERMINATE,
    ))
    assert out["verdict"] == Verdict.REAL.value


# @spec EE-ADJ-009
def test_full_six_test_outcome_vector_preserved_in_result():
    outcomes = _six_outcomes(
        TestResult.FAIL, TestResult.PASS, TestResult.PASS,
        TestResult.NOT_APPLICABLE, TestResult.PASS, TestResult.PASS,
    )
    out = adjudicator.adjudicate_one(outcomes)
    vec = out["test_outcome_vector"]
    assert len(vec) == 6
    names = {o["test_name"] for o in vec}
    assert names == {
        TestName.PIN_LOOKUP.value, TestName.MINHASH.value, TestName.SPATIAL.value,
        TestName.NFHS.value, TestName.TEMPORAL.value, TestName.EMBEDDING.value,
    }


# @spec EE-ADJ-002
def test_layer_b_override_pin_supersedes_original_pin_row():
    """Layer B writes a `layer-b-override-pin` row with result=pass that the
    Adjudicator consumes in place of the original `pin-reverse-lookup` row."""
    long_results = pd.DataFrame([
        # Original failing PIN row + Layer B override that rescues it
        {"facility_id": "F1", "test_name": TestName.PIN_LOOKUP.value,
         "result": TestResult.FAIL.value, "evidence_ref": {"distance_km": 800}},
        {"facility_id": "F1", "test_name": "layer-b-override-pin",
         "result": TestResult.PASS.value,
         "evidence_ref": {"matched": "Bapatla-from-Prakasam-reorganization"}},
        # 5 more tests pass; without the override this would be a PIN veto phantom
        {"facility_id": "F1", "test_name": TestName.MINHASH.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.SPATIAL.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.NFHS.value,
         "result": TestResult.NOT_APPLICABLE.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.TEMPORAL.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None},
    ])
    out = adjudicator.run_adjudicator(long_results)
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.REAL.value


# @spec EE-ADJ-002
def test_layer_b_override_spatial_supersedes_original_spatial_row():
    long_results = pd.DataFrame([
        {"facility_id": "F1", "test_name": TestName.PIN_LOOKUP.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.SPATIAL.value,
         "result": TestResult.FAIL.value, "evidence_ref": {"a": "b"}},
        {"facility_id": "F1", "test_name": "layer-b-override-spatial",
         "result": TestResult.PASS.value,
         "evidence_ref": {"matched": "Mysore-Mysuru-spelling"}},
        {"facility_id": "F1", "test_name": TestName.MINHASH.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.NFHS.value,
         "result": TestResult.NOT_APPLICABLE.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.TEMPORAL.value,
         "result": TestResult.PASS.value, "evidence_ref": None},
        {"facility_id": "F1", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None},
    ])
    out = adjudicator.run_adjudicator(long_results)
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.REAL.value


# @spec EE-ADJ-002
def test_layer_b_override_picks_latest_by_ran_at():
    """When multiple override rows share (facility_id, test_name), Adjudicator
    reads the row with MAX(ran_at) — per EE-Q1 resolution."""
    import datetime as dt
    long_results = pd.DataFrame([
        {"facility_id": "F1", "test_name": TestName.PIN_LOOKUP.value,
         "result": TestResult.FAIL.value, "evidence_ref": {"distance_km": 800},
         "ran_at": dt.datetime(2026, 6, 1)},
        # Earlier override that wouldn't rescue
        {"facility_id": "F1", "test_name": "layer-b-override-pin",
         "result": TestResult.FAIL.value, "evidence_ref": {"matched": "no"},
         "ran_at": dt.datetime(2026, 6, 10)},
        # Latest override that rescues
        {"facility_id": "F1", "test_name": "layer-b-override-pin",
         "result": TestResult.PASS.value, "evidence_ref": {"matched": "yes"},
         "ran_at": dt.datetime(2026, 6, 15)},
        {"facility_id": "F1", "test_name": TestName.MINHASH.value,
         "result": TestResult.PASS.value, "evidence_ref": None,
         "ran_at": dt.datetime(2026, 6, 15)},
        {"facility_id": "F1", "test_name": TestName.SPATIAL.value,
         "result": TestResult.PASS.value, "evidence_ref": None,
         "ran_at": dt.datetime(2026, 6, 15)},
        {"facility_id": "F1", "test_name": TestName.NFHS.value,
         "result": TestResult.NOT_APPLICABLE.value, "evidence_ref": None,
         "ran_at": dt.datetime(2026, 6, 15)},
        {"facility_id": "F1", "test_name": TestName.TEMPORAL.value,
         "result": TestResult.PASS.value, "evidence_ref": None,
         "ran_at": dt.datetime(2026, 6, 15)},
        {"facility_id": "F1", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None,
         "ran_at": dt.datetime(2026, 6, 15)},
    ])
    out = adjudicator.run_adjudicator(long_results)
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.REAL.value


# @spec EE-ADJ-008
def test_adjudicator_writes_both_adjudicator_verdict_and_verdict_columns():
    """At Adjudicator-write time, verdict == adjudicator_verdict. Later mutations
    by Layer A (rescue patch) or planner override are out-of-scope here."""
    long_results = pd.DataFrame([
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
        {"facility_id": "F1", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None},
    ])
    out = adjudicator.run_adjudicator(long_results)
    assert "adjudicator_verdict" in out.columns
    assert "verdict" in out.columns
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.REAL.value
    assert out.iloc[0]["verdict"] == Verdict.REAL.value


# @spec EE-ADJ-001, EE-ADJ-007
def test_run_adjudicator_pivots_long_results_to_one_row_per_facility():
    long_results = pd.DataFrame([
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
        {"facility_id": "F1", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None},
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
        {"facility_id": "F2", "test_name": TestName.EMBEDDING.value,
         "result": TestResult.INDETERMINATE.value, "evidence_ref": None},
    ])
    out = adjudicator.run_adjudicator(long_results)
    by_fac = out.set_index("facility_id")
    assert by_fac.loc["F1", "adjudicator_verdict"] == Verdict.REAL.value
    assert by_fac.loc["F2", "adjudicator_verdict"] == Verdict.PHANTOM.value
