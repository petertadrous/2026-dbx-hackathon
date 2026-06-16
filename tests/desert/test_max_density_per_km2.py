"""Tests for DS-SCORE-006 — max_facility_count_per_km2 per state."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.density import compute_max_density_per_km2


# @spec DS-SCORE-006
def test_max_density_per_km2_is_max_over_districts_in_state(
    small_facilities_with_district, small_verdicts, small_districts,
):
    """For Maharashtra, density per district equals verified_count / area_km2.
    BEED: 2 / 7000 ≈ 2.86e-4; MUM: 1 / 500 = 2.0e-3; PUN: 1 / 1500 ≈ 6.67e-4.
    Max → MUM density."""
    out = compute_max_density_per_km2(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        districts=small_districts,
        state_name="Maharashtra",
    )
    assert out > 0
    # MUM dominates at 1/500 = 0.002
    assert abs(out - (1.0 / 500.0)) < 1e-9


# @spec DS-SCORE-006
def test_max_density_per_km2_is_per_state(
    small_facilities_with_district, small_verdicts, small_districts,
):
    """If we asked for a state with no facilities, return 0 (no normalization)."""
    out = compute_max_density_per_km2(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        districts=small_districts,
        state_name="Bihar",
    )
    assert out == 0.0


# @spec DS-SCORE-006
def test_max_density_excludes_phantom_facilities_from_numerator(
    small_facilities_with_district, small_districts,
):
    """Numerator is verified count (verdict != phantom), not total facilities."""
    verdicts_all_phantom = pd.DataFrame([
        {"facility_id": fid, "verdict": "phantom"}
        for fid in ("F1", "F2", "F3", "F4", "F5")
    ])
    out = compute_max_density_per_km2(
        facilities_with_district=small_facilities_with_district,
        verdicts=verdicts_all_phantom,
        districts=small_districts,
        state_name="Maharashtra",
    )
    # All facilities phantom → zero verified → zero density
    assert out == 0.0
