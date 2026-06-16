"""Tests for PW-BUDGET-002 — deterministic re-allocation algorithm.

Pure-function tests for the recommendation math; UI render is a smoke test
elsewhere.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.planner_workspace.budget import (
    compute_recommended_allocation,
    serialize_recommendation_csv,
)


def _districts() -> pd.DataFrame:
    return pd.DataFrame([
        {"district_id": "BEED", "district_name": "Beed", "state_name": "Maharashtra",
         "adjusted_desert_score": 0.80, "burden_weight": 0.30,
         "verified_facility_count": 12, "phantom_count": 4},
        {"district_id": "LAT",  "district_name": "Latur", "state_name": "Maharashtra",
         "adjusted_desert_score": 0.70, "burden_weight": 0.25,
         "verified_facility_count": 10, "phantom_count": 3},
        {"district_id": "MUM",  "district_name": "Mumbai", "state_name": "Maharashtra",
         "adjusted_desert_score": 0.20, "burden_weight": 0.05,
         "verified_facility_count": 80, "phantom_count": 1},
    ])


def _allocations() -> pd.DataFrame:
    return pd.DataFrame([
        {"district_id": "BEED", "allocated_inr": 20_000_000},
        {"district_id": "LAT",  "allocated_inr": 18_000_000},
        {"district_id": "MUM",  "allocated_inr": 60_000_000},
    ])


# @spec PW-BUDGET-002
def test_recommendation_sums_to_total_budget():
    rec = compute_recommended_allocation(_districts(), _allocations())
    total_budget = int(_allocations()["allocated_inr"].sum())
    assert abs(rec["recommended_inr"].sum() - total_budget) <= 2


# @spec PW-BUDGET-002
def test_recommendation_higher_score_gets_more_money():
    rec = compute_recommended_allocation(_districts(), _allocations())
    by_id = rec.set_index("district_id")
    # BEED scores 0.8 × 0.3; MUM scores 0.2 × 0.05 — BEED's share must
    # be larger relative to its prior allocation than MUM's.
    beed_delta = by_id.loc["BEED", "delta_inr"]
    mum_delta = by_id.loc["MUM", "delta_inr"]
    assert beed_delta > 0
    assert mum_delta < 0


# @spec PW-BUDGET-002
def test_recommendation_caps_at_2_5x_prior():
    """A district with a very low prior cannot receive more than 2.5× back."""
    districts = pd.DataFrame([
        {"district_id": "TINY", "district_name": "Tiny", "state_name": "X",
         "adjusted_desert_score": 0.99, "burden_weight": 0.99,
         "verified_facility_count": 1, "phantom_count": 0},
        {"district_id": "BIG", "district_name": "Big", "state_name": "X",
         "adjusted_desert_score": 0.01, "burden_weight": 0.01,
         "verified_facility_count": 100, "phantom_count": 0},
    ])
    allocations = pd.DataFrame([
        {"district_id": "TINY", "allocated_inr": 1_000_000},
        {"district_id": "BIG",  "allocated_inr": 99_000_000},
    ])
    rec = compute_recommended_allocation(districts, allocations)
    by_id = rec.set_index("district_id")
    assert by_id.loc["TINY", "recommended_inr"] <= 1_000_000 * 2.5


# @spec PW-BUDGET-004
def test_csv_export_has_required_columns():
    rec = compute_recommended_allocation(_districts(), _allocations())
    csv = serialize_recommendation_csv(rec)
    header = csv.splitlines()[0]
    for col in ("district_id", "district_name", "current_inr",
                "recommended_inr", "delta_inr", "justification"):
        assert col in header


# @spec PW-BUDGET-005
def test_recommendation_does_not_mutate_allocations_frame():
    """PW-BUDGET-005: recommendation is read-only with respect to
    team.budget_allocations. The input frame must not be touched."""
    allocations = _allocations()
    before = allocations.copy()
    compute_recommended_allocation(_districts(), allocations)
    pd.testing.assert_frame_equal(allocations, before)


# @spec PW-BUDGET-007
def test_budget_module_does_not_call_ai_query():
    """PW-BUDGET-007: this view is LLM-free. Source must not reference ai_query
    or any FMA-call adapter."""
    import inspect
    from phantom_census.planner_workspace import budget
    src = inspect.getsource(budget)
    assert "ai_query" not in src
    assert "ai_evidence_layer" not in src
