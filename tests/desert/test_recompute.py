"""Tests for DS-OVR-001..004 — single-district recompute."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.formula import compute_district_scores
from phantom_census.desert_scoring.recompute import recompute_in_memory


# @spec DS-OVR-001
def test_recompute_single_district_updates_only_that_row(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    """Drive an override through recompute_in_memory and confirm BEED's row
    matches what a from-scratch recompute on the new inputs would produce,
    while MUM + PUN match the from-scratch recompute on the OLD inputs.

    The prior version of this test compared a copied MUM row to itself, so it
    passed trivially even if the recompute were broken.
    """
    old_scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )

    updated_verdicts = small_verdicts.copy()
    updated_verdicts.loc[updated_verdicts["facility_id"] == "F4", "verdict"] = "real"

    # Independent reference: full recompute on the updated inputs with the
    # same global max_density that the override path will replay.
    max_density = float(old_scores["max_density"].iloc[0])
    full_after = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=updated_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
        max_density=max_density,
    )

    new_scores = recompute_in_memory(
        previous_scores=old_scores,
        facilities_with_district=small_facilities_with_district,
        verdicts=updated_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
        district_id="BEED",
        max_density=max_density,
    )

    beed = new_scores[new_scores["district_id"] == "BEED"].iloc[0]
    beed_full = full_after[full_after["district_id"] == "BEED"].iloc[0]
    assert beed["phantom_count"] == 0
    assert beed["adjusted_desert_score"] == beed_full["adjusted_desert_score"]
    assert beed["raw_desert_score"] == beed_full["raw_desert_score"]

    # MUM is unaffected by the override; its row should match the OLD compute.
    mum_old = old_scores[old_scores["district_id"] == "MUM"].iloc[0]
    mum_new = new_scores[new_scores["district_id"] == "MUM"].iloc[0]
    assert mum_new["raw_desert_score"] == mum_old["raw_desert_score"]
    assert mum_new["adjusted_desert_score"] == mum_old["adjusted_desert_score"]


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
