"""Tests for DS-SCORE-001..004."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.formula import compute_district_scores


# @spec DS-SCORE-001, DS-SCORE-002
def test_adjusted_score_strictly_greater_than_raw_when_phantoms_present(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    """LLD line 32: subtracting phantoms RAISES the desert score."""
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    beed = scores[scores["district_id"] == "BEED"].iloc[0]
    assert beed["phantom_count"] == 1
    assert beed["adjusted_desert_score"] > beed["raw_desert_score"]


# @spec DS-SCORE-001
def test_raw_score_normalized_zero_to_one(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    assert (scores["raw_desert_score"] >= 0).all()
    assert (scores["raw_desert_score"] <= 1).all()
    assert (scores["adjusted_desert_score"] >= 0).all()
    assert (scores["adjusted_desert_score"] <= 1).all()


# @spec DS-SCORE-003
def test_scores_table_carries_required_columns(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    required = {
        "district_id", "district_name", "state_name", "capability",
        "raw_desert_score", "adjusted_desert_score",
        "verified_facility_count", "phantom_count", "burden_imputed",
    }
    assert required <= set(scores.columns)


# @spec DS-SCORE-003
def test_counts_match_inputs(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    beed = scores[scores["district_id"] == "BEED"].iloc[0]
    # BEED has F1, F2 real + F4 phantom → verified=2, phantom=1
    assert beed["verified_facility_count"] == 2
    assert beed["phantom_count"] == 1


# @spec DS-SCORE-004
def test_state_filter_drops_out_of_state_nfhs_rows():
    """The batch.run_desert_scoring state_filter restricts NFHS to one state
    before computing burden weights. Smoke-test the filter at the data layer."""
    nfhs = pd.DataFrame([
        {"district_id": "BEED", "district_name": "Beed", "state_name": "Maharashtra",
         "institutional_delivery_rate": 70.0},
        {"district_id": "MUM",  "district_name": "Mumbai", "state_name": "Maharashtra",
         "institutional_delivery_rate": 95.0},
        {"district_id": "PAT",  "district_name": "Patna", "state_name": "Bihar",
         "institutional_delivery_rate": 60.0},
    ])
    filtered = nfhs[nfhs["state_name"] == "Maharashtra"]
    assert set(filtered["district_id"]) == {"BEED", "MUM"}
    # State medians computed only on Maharashtra rows.
    from phantom_census.desert_scoring.burden import state_medians_from_nfhs
    medians = state_medians_from_nfhs(filtered, capability="maternity")
    assert "Bihar" not in medians
    assert medians["Maharashtra"] == 82.5  # median of [70, 95]


# @spec DS-SCORE-004
def test_maternity_capability_uses_institutional_delivery_rate(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    """Two NFHS rows with very different rates produce different burden weights."""
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    # Beed institutional delivery rate=70 → burden_weight = 0.30
    # Mumbai = 95 → burden_weight = 0.05
    # For same denominator, Beed's adjusted score should be much higher than Mumbai's.
    beed = scores[scores["district_id"] == "BEED"].iloc[0]
    mum = scores[scores["district_id"] == "MUM"].iloc[0]
    assert beed["adjusted_desert_score"] > mum["adjusted_desert_score"]
