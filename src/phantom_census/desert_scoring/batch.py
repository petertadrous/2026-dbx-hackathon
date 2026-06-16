"""Batch run — read from Lakebase, compute scores, write back desert_scores.

The choropleth render is owned by the Planner Workspace's pydeck GeoJsonLayer
reading `operational.desert_scores` directly (DS-MAP-003); no Folium tile
pre-rendering happens here.

@spec DS-SCORE-001, DS-SCORE-002, DS-SCORE-003, DS-SCORE-004, DS-SCORE-005,
@spec DS-SCORE-006, DS-MAP-001, DS-MAP-002, DS-MAP-003
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import Engine, text

from .density import compute_max_density_per_km2
from .formula import compute_district_scores

# Real NFHS-5 exports use a variety of column names; normalize on read so the
# rest of the segment can rely on the canonical {district_id, state_name,
# institutional_delivery_rate} schema.
_NFHS_COLUMN_ALIASES: dict[str, str] = {
    "district": "district_id",
    "District": "district_id",
    "district_name": "district_id",
    "state": "state_name",
    "State": "state_name",
    "State Name": "state_name",
    "STATE": "state_name",
    "Institutional Delivery Rate": "institutional_delivery_rate",
    "institutional_delivery_rate (%)": "institutional_delivery_rate",
}


def normalize_nfhs_columns(nfhs: pd.DataFrame) -> pd.DataFrame:
    rename = {raw: canon for raw, canon in _NFHS_COLUMN_ALIASES.items()
              if raw in nfhs.columns and canon not in nfhs.columns}
    if rename:
        nfhs = nfhs.rename(columns=rename)
    return nfhs


def _load_districts(districts_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(districts_path)
    if "district_id" not in gdf.columns and "shapeName" in gdf.columns:
        gdf = gdf.rename(columns={"shapeName": "district_id"})
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def run_desert_scoring(
    engine: Engine,
    *,
    capability: str = "maternity",
    districts_path: Path,
    nfhs: pd.DataFrame,
    state_filter: str | None = None,
    ran_at: datetime | None = None,
) -> int:
    """Read facilities + verdicts from Lakebase, compute scores, write back.

    Returns the count of district rows written.

    `state_filter` restricts both the score computation and the rendered tile
    layer to one state (e.g., ``"Maharashtra"``). NFHS rows outside the state
    are dropped before computation so the burden weights are state-relative.
    """
    ran_at = ran_at or datetime.now(tz=timezone.utc)
    nfhs = normalize_nfhs_columns(nfhs)
    if state_filter is not None:
        nfhs = nfhs[nfhs.get("state_name") == state_filter].copy()

    with engine.connect() as conn:
        facilities = pd.DataFrame(conn.execute(text(
            "SELECT facility_id, district_id FROM operational.facility_district_xref"
        )).mappings().all())
        verdicts = pd.DataFrame(conn.execute(text(
            "SELECT facility_id, verdict FROM operational.phantom_verdicts"
        )).mappings().all())

    if facilities.empty or verdicts.empty:
        return 0

    # DS-SCORE-006: compute the per-state max_facility_count_per_km2 once and
    # pass it as the formula denominator so overrides preserve normalization.
    districts_gdf_full = _load_districts(Path(districts_path))
    max_density = compute_max_density_per_km2(
        facilities_with_district=facilities,
        verdicts=verdicts,
        districts=districts_gdf_full,
        state_name=state_filter or "",
    )

    scores = compute_district_scores(
        facilities_with_district=facilities,
        verdicts=verdicts,
        nfhs=nfhs,
        capability=capability,
        max_density=max_density if max_density > 0 else None,
    )

    rows = scores.to_dict(orient="records")
    with engine.begin() as conn:
        for r in rows:
            conn.execute(
                text("""
                    INSERT INTO operational.desert_scores
                        (district_id, district_name, state_name, capability,
                         raw_desert_score, adjusted_desert_score,
                         verified_facility_count, phantom_count,
                         burden_imputed, nfhs_missing,
                         burden_weight, max_density, updated_at)
                    VALUES
                        (:district_id, :district_name, :state_name, :capability,
                         :raw, :adj, :ver, :ph, :imp, :nfhs_missing,
                         :weight, :max_density, :ts)
                    ON CONFLICT (district_id, capability) DO UPDATE SET
                        district_name = EXCLUDED.district_name,
                        state_name = EXCLUDED.state_name,
                        raw_desert_score = EXCLUDED.raw_desert_score,
                        adjusted_desert_score = EXCLUDED.adjusted_desert_score,
                        verified_facility_count = EXCLUDED.verified_facility_count,
                        phantom_count = EXCLUDED.phantom_count,
                        burden_imputed = EXCLUDED.burden_imputed,
                        nfhs_missing = EXCLUDED.nfhs_missing,
                        burden_weight = EXCLUDED.burden_weight,
                        max_density = EXCLUDED.max_density,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "district_id": r["district_id"],
                    "district_name": r["district_name"],
                    "state_name": r["state_name"],
                    "capability": capability,
                    "raw": float(r["raw_desert_score"]),
                    "adj": float(r["adjusted_desert_score"]),
                    "ver": int(r["verified_facility_count"]),
                    "ph": int(r["phantom_count"]),
                    "imp": bool(r["burden_imputed"]),
                    "nfhs_missing": bool(r["nfhs_missing"]),
                    "weight": float(r["burden_weight"]),
                    "max_density": float(r["max_density"]),
                    "ts": ran_at,
                },
            )

    return len(rows)
