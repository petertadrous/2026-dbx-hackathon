"""Per-state max-density constant used as the score formula denominator.

@spec DS-SCORE-006
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd


# @spec DS-SCORE-006
def compute_max_density_per_km2(
    *,
    facilities_with_district: pd.DataFrame,
    verdicts: pd.DataFrame,
    districts: gpd.GeoDataFrame,
    state_name: str,
) -> float:
    """Compute `max_facility_count_per_km2` for a single state.

    For each district `d` in the state, density = verified_count(d) /
    area_km2(d). The returned value is the max over all districts in the state.
    Persisted at batch time onto `operational.desert_scores.max_density` and
    NOT recomputed on planner overrides (DS-OVR-002).

    `verified_count(d)` counts facilities spatially joined to `d` whose
    `verdict != phantom`.

    Returns 0.0 when no facilities or no districts in the requested state.
    """
    if "state_name" not in districts.columns:
        return 0.0
    in_state = districts[districts["state_name"] == state_name]
    if in_state.empty or "area_km2" not in in_state.columns:
        return 0.0

    fac_verdict = facilities_with_district.merge(
        verdicts[["facility_id", "verdict"]], on="facility_id", how="left",
    )
    verified = fac_verdict[fac_verdict["verdict"] != "phantom"]
    counts = (
        verified.groupby("district_id").size()
        .rename("verified_facility_count").reset_index()
    )
    joined = in_state[["district_id", "area_km2"]].merge(
        counts, on="district_id", how="left",
    )
    joined["verified_facility_count"] = joined["verified_facility_count"].fillna(0)
    joined["density"] = joined["verified_facility_count"] / joined["area_km2"]
    max_density = float(joined["density"].max())
    return max_density if max_density > 0 else 0.0
