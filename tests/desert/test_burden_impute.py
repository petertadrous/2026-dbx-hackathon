"""Tests for DS-SCORE-005 — state-median imputation when NFHS suppressed."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.burden import burden_weight
from phantom_census.desert_scoring.formula import compute_district_scores


# @spec DS-SCORE-005
def test_burden_weight_signals_imputation(small_nfhs):
    state_median = pd.to_numeric(
        small_nfhs["institutional_delivery_rate"], errors="coerce"
    ).median()
    pun = small_nfhs[small_nfhs["district_id"] == "PUN"].iloc[0]
    weight, imputed = burden_weight(pun, capability="maternity",
                                    state_medians={"Maharashtra": state_median})
    assert imputed is True
    assert weight == pytest.approx(1 - state_median / 100)


# @spec DS-SCORE-005
def test_burden_imputed_flag_propagates_to_scores(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    pun_row = scores[scores["district_id"] == "PUN"].iloc[0]
    assert pun_row["burden_imputed"] is True or pun_row["burden_imputed"] == True  # noqa


# Avoid an import-time NameError if pytest.approx isn't imported above.
import pytest  # noqa: E402
