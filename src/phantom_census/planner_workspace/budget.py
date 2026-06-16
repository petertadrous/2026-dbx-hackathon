"""Deterministic budget re-allocation recommendation.

@spec PW-BUDGET-001, PW-BUDGET-002, PW-BUDGET-003, PW-BUDGET-004,
@spec PW-BUDGET-005, PW-BUDGET-007

PW-BUDGET-007: this module is LLM-free. The source-inspection test in
test_budget_recommendation.py asserts no Foundation Model imports or
adapter references appear in this file.
"""
from __future__ import annotations

import csv
import io

import pandas as pd

CAP_MULTIPLIER = 2.5


# @spec PW-BUDGET-002
def compute_recommended_allocation(
    districts: pd.DataFrame,
    allocations: pd.DataFrame,
    *,
    total_budget_inr: int | None = None,
) -> pd.DataFrame:
    """Compute the recommended quarterly re-allocation per district.

    Algorithm:
      1. Score(d) = adjusted_desert_score × burden_weight × verified_facility_count
         (`verified_facility_count` is the population_proxy stand-in per LP-Q2).
      2. fair_share(d) = total_budget × Score(d) / sum(Score)
      3. recommended(d) = min(fair_share(d), prior_allocation(d) × CAP_MULTIPLIER)
      4. delta(d) = recommended(d) − prior_allocation(d)

    Inputs are not mutated.
    """
    districts = districts.copy()
    allocations_copy = allocations.copy()

    score = (
        districts["adjusted_desert_score"]
        * districts["burden_weight"]
        * districts["verified_facility_count"].clip(lower=1)
    )
    districts["score"] = score

    merged = districts.merge(
        allocations_copy[["district_id", "allocated_inr"]],
        on="district_id", how="inner",
    )

    if total_budget_inr is None:
        total_budget_inr = int(merged["allocated_inr"].sum())

    sum_score = float(merged["score"].sum())
    if sum_score <= 0:
        merged["recommended_inr"] = merged["allocated_inr"]
    else:
        fair_share = total_budget_inr * (merged["score"] / sum_score)
        cap = merged["allocated_inr"] * CAP_MULTIPLIER
        merged["recommended_inr"] = (
            pd.concat([fair_share, cap], axis=1).min(axis=1).round().astype(int)
        )

    # Re-distribute the unallocated remainder proportionally to uncapped districts
    # so the total preserves the budget envelope (best-effort; minor rounding gap
    # is acceptable per the test tolerance).
    leftover = total_budget_inr - int(merged["recommended_inr"].sum())
    if leftover > 0 and (~_is_capped(merged)).any():
        uncapped_mask = ~_is_capped(merged)
        uncapped_sum_score = float(merged.loc[uncapped_mask, "score"].sum())
        if uncapped_sum_score > 0:
            distrib = (
                leftover * (merged.loc[uncapped_mask, "score"] / uncapped_sum_score)
            ).round().astype(int)
            merged.loc[uncapped_mask, "recommended_inr"] += distrib

    merged["current_inr"] = merged["allocated_inr"]
    merged["delta_inr"] = merged["recommended_inr"] - merged["current_inr"]
    merged["justification"] = merged.apply(_justification_text, axis=1)

    cols = ["district_id", "district_name", "current_inr",
            "recommended_inr", "delta_inr", "justification"]
    return merged[cols].sort_values("recommended_inr", ascending=False).reset_index(drop=True)


def _is_capped(merged: pd.DataFrame) -> pd.Series:
    cap = merged["allocated_inr"] * CAP_MULTIPLIER
    return merged["recommended_inr"] >= cap - 0.5  # tolerance for rounding


def _justification_text(row: pd.Series) -> str:
    return (
        f"adjusted_desert_score={row['adjusted_desert_score']:.2f}; "
        f"burden_weight={row['burden_weight']:.2f}"
    )


# @spec PW-BUDGET-004
def serialize_recommendation_csv(rec: pd.DataFrame) -> str:
    """Serialize the recommendation frame to CSV with the spec-required columns."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "district_id", "district_name", "current_inr",
        "recommended_inr", "delta_inr", "justification",
    ])
    for _, r in rec.iterrows():
        writer.writerow([
            r["district_id"], r["district_name"],
            int(r["current_inr"]), int(r["recommended_inr"]),
            int(r["delta_inr"]), r["justification"],
        ])
    return buf.getvalue()
