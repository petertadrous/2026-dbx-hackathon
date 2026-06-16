"""Ranking + counter helpers consumed by the planner workspace.

@spec DS-RANK-001, DS-RANK-002, DS-RANK-003, DS-RANK-004, DS-RANK-005,
@spec DS-CTR-001, DS-CTR-003
"""
from __future__ import annotations

from typing import Literal

import pandas as pd


# @spec DS-RANK-001, DS-RANK-002, DS-RANK-003, DS-RANK-004
def build_rank_table(
    scores: pd.DataFrame,
    *,
    active: Literal["raw", "adjusted"],
) -> pd.DataFrame:
    """Return a ranking table sorted by the active score; carries rank_delta.

    rank_delta = raw_rank - adjusted_rank (positive = district moved up in the
    adjusted view; negative = moved down). Sort direction: highest score first.

    DS-RANK-004 cascade: this function is pure — the workspace calls it again
    after an override-driven recompute and the table re-sorts on the new scores
    within the same window as DS-OVR-004.

    DS-RANK-005 cascade: AI Evidence Layer writes do not mutate verdict /
    phantom_count / adjusted_desert_score, so calling this function after an AI
    write produces an identical ordering.
    """
    df = scores.copy()
    df["raw_rank"] = df["raw_desert_score"].rank(method="min", ascending=False).astype(int)
    df["adjusted_rank"] = df["adjusted_desert_score"].rank(method="min", ascending=False).astype(int)
    df["rank_delta"] = df["raw_rank"] - df["adjusted_rank"]

    sort_col = "raw_desert_score" if active == "raw" else "adjusted_desert_score"
    return df.sort_values(sort_col, ascending=False).reset_index(drop=True)


# @spec DS-CTR-001
def phantom_counter(scores: pd.DataFrame) -> int:
    """Total phantom facilities across all districts in this scores frame."""
    return int(scores["phantom_count"].sum())


# @spec DS-CTR-003
def token_usage_indicator() -> str:
    """Constant indicator surfaced in the planner header."""
    return "token_usage: 0"
