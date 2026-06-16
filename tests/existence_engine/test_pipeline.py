"""Tests for the end-to-end engine pipeline.

Covers EE-PIPE-001..004.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from phantom_census.existence_engine.pipeline import EngineInputs, run_engine
from phantom_census.existence_engine.types import TestName, TestResult, Verdict


def _inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
            districts_minimal, hfr_minimal, district_to_state) -> EngineInputs:
    return EngineInputs(
        facilities=facilities_minimal,
        india_post=india_post_minimal,
        nfhs=nfhs_minimal,
        districts=districts_minimal,
        hfr=hfr_minimal,
        district_to_state=district_to_state,
        current_year=2026,
        snapshot_id="2026-06-15-batch-001",
    )


# @spec EE-PIPE-001
def test_pipeline_processes_all_facilities(facilities_minimal, india_post_minimal,
                                            nfhs_minimal, districts_minimal,
                                            hfr_minimal, district_to_state):
    out = run_engine(_inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
                             districts_minimal, hfr_minimal, district_to_state))
    assert len(out.phantom_verdicts) == len(facilities_minimal)


# @spec EE-PIPE-001
def test_pipeline_runs_all_six_tests_per_facility(facilities_minimal, india_post_minimal,
                                                    nfhs_minimal, districts_minimal,
                                                    hfr_minimal, district_to_state):
    out = run_engine(_inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
                             districts_minimal, hfr_minimal, district_to_state))
    expected_tests = {
        TestName.PIN_LOOKUP.value, TestName.MINHASH.value, TestName.SPATIAL.value,
        TestName.NFHS.value, TestName.TEMPORAL.value, TestName.EMBEDDING.value,
    }
    by_fac = out.facility_existence_tests.groupby("facility_id")["test_name"].apply(set)
    for tests in by_fac:
        assert expected_tests.issubset(tests)


# @spec EE-PIPE-002
def test_pipeline_test_rows_carry_ran_at(facilities_minimal, india_post_minimal,
                                          nfhs_minimal, districts_minimal,
                                          hfr_minimal, district_to_state):
    ts = datetime(2026, 6, 15, 12, 0, 0)
    out = run_engine(
        _inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
                districts_minimal, hfr_minimal, district_to_state),
        ran_at=ts,
    )
    assert (out.facility_existence_tests["ran_at"] == ts).all()
    assert (out.phantom_verdicts["ran_at"] == ts).all()


# @spec EE-PIPE-003
def test_pipeline_verdict_table_carries_dual_verdict_and_rescue_columns(
    facilities_minimal, india_post_minimal, nfhs_minimal, districts_minimal,
    hfr_minimal, district_to_state,
):
    out = run_engine(_inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
                             districts_minimal, hfr_minimal, district_to_state))
    cols = set(out.phantom_verdicts.columns)
    required = {
        "facility_id", "adjudicator_verdict", "verdict",
        "rescue_applied", "test_outcome_vector", "ran_at",
    }
    assert required <= cols, f"missing: {required - cols}"
    row = out.phantom_verdicts.iloc[0]
    assert row["adjudicator_verdict"] in {v.value for v in Verdict}
    assert row["verdict"] in {v.value for v in Verdict} or row["verdict"] in {
        "force-real-planner", "force-phantom-planner",
    }


# @spec EE-PIPE-003
def test_pipeline_test_outcome_vector_has_six_entries(
    facilities_minimal, india_post_minimal, nfhs_minimal, districts_minimal,
    hfr_minimal, district_to_state,
):
    out = run_engine(_inputs(facilities_minimal, india_post_minimal, nfhs_minimal,
                             districts_minimal, hfr_minimal, district_to_state))
    vec = out.phantom_verdicts.iloc[0]["test_outcome_vector"]
    assert len(vec) == 6
    names = {o["test_name"] for o in vec}
    assert TestName.EMBEDDING.value in names


# @spec EE-PIPE-001, EE-NFHS-003
def test_pipeline_auto_builds_district_to_state_when_omitted(
    facilities_minimal, india_post_minimal, nfhs_minimal, districts_minimal,
    hfr_minimal,
):
    out = run_engine(EngineInputs(
        facilities=facilities_minimal,
        india_post=india_post_minimal,
        nfhs=nfhs_minimal,
        districts=districts_minimal,
        hfr=hfr_minimal,
        district_to_state=None,
        current_year=None,
        snapshot_id="2026-06-15-batch-001",
    ))
    assert len(out.phantom_verdicts) == len(facilities_minimal)


# @spec EE-PIPE-004
def test_pipeline_uses_indeterminate_on_absent_data(india_post_minimal, nfhs_minimal,
                                                     districts_minimal, hfr_minimal,
                                                     district_to_state):
    facilities = pd.DataFrame(
        [
            {
                "facility_id": "EMPTY",
                "latitude": None,
                "longitude": None,
                "pincode": None,
                "yearEstablished": None,
                "capability": [],
                "procedure": [],
                "equipment": [],
                "description": "",
                "address_stateOrRegion": "",
            }
        ]
    )
    out = run_engine(EngineInputs(
        facilities=facilities,
        india_post=india_post_minimal,
        nfhs=nfhs_minimal,
        districts=districts_minimal,
        hfr=hfr_minimal,
        district_to_state=district_to_state,
        current_year=2026,
        snapshot_id="2026-06-15-batch-001",
    ))
    by_test = out.facility_existence_tests.set_index("test_name")
    for tname in (TestName.PIN_LOOKUP, TestName.SPATIAL, TestName.TEMPORAL):
        assert by_test.loc[tname.value, "result"] == TestResult.INDETERMINATE.value
