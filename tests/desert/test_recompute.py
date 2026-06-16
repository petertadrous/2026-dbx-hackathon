"""Tests for DS-OVR-001..004 — single-district recompute."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.formula import compute_district_scores
from phantom_census.desert_scoring.recompute import recompute_in_memory


# @spec DS-OVR-001
def test_recompute_single_district_updates_only_that_row(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    # Override: force-real on F4 — Beed's phantom_count goes from 1 to 0
    updated_verdicts = small_verdicts.copy()
    updated_verdicts.loc[updated_verdicts["facility_id"] == "F4", "verdict"] = "real"

    new_scores = recompute_in_memory(
        previous_scores=scores,
        facilities_with_district=small_facilities_with_district,
        verdicts=updated_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
        district_id="BEED",
    )
    # BEED row updated; MUM + PUN rows untouched
    beed = new_scores[new_scores["district_id"] == "BEED"].iloc[0]
    assert beed["phantom_count"] == 0
    mum_before = scores[scores["district_id"] == "MUM"].iloc[0]
    mum_after = new_scores[new_scores["district_id"] == "MUM"].iloc[0]
    assert mum_after["adjusted_desert_score"] == mum_before["adjusted_desert_score"]


# @spec DS-OVR-003
def test_recompute_is_fast(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    """Smoke: recompute returns in well under a second on the synthetic frame."""
    import time
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    t0 = time.perf_counter()
    recompute_in_memory(
        previous_scores=scores,
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
        district_id="BEED",
    )
    assert (time.perf_counter() - t0) < 1.0


# @spec DS-OVR-004
def test_rank_table_reflects_recomputed_score(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    from phantom_census.desert_scoring.tiles import build_rank_table
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    updated_verdicts = small_verdicts.copy()
    updated_verdicts.loc[updated_verdicts["facility_id"] == "F4", "verdict"] = "real"

    new_scores = recompute_in_memory(
        previous_scores=scores,
        facilities_with_district=small_facilities_with_district,
        verdicts=updated_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
        district_id="BEED",
    )
    rank = build_rank_table(new_scores, active="adjusted")
    # Beed's adjusted score should now match its raw (since phantom_count=0)
    beed_rank = rank[rank["district_id"] == "BEED"].iloc[0]
    assert beed_rank["adjusted_desert_score"] == beed_rank["raw_desert_score"]
