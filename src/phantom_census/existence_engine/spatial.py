"""Test 3 — Spatial district mismatch (veto-capable).

Implements EE-SPATIAL-001..006.
"""
from __future__ import annotations

import math
import re

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from .pin_lookup import parse_pincode
from .types import TestName, TestResult

AMBIGUOUS_PIN_MODAL_THRESHOLD = 0.5
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def _has_latlon(lat: object, lon: object) -> bool:
    if lat is None or lon is None:
        return False
    try:
        latf, lonf = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(latf) or math.isnan(lonf))


# @spec EE-SPATIAL-001, EE-SPATIAL-002
def assign_districts(facilities: pd.DataFrame, districts: gpd.GeoDataFrame) -> pd.DataFrame:
    """Point-in-polygon assignment per EE-SPATIAL-001.

    Uses `gpd.sjoin` (R-tree-backed) to do the join in a single vectorized
    pass — O(n log m) vs the per-facility Python loop's O(n × m). Predicate
    is `within`, the inverse of `polygon.contains(point)` per shapely's API;
    output is identical for non-overlapping ADM2 districts. When a point
    lies on a shared edge (rare; the predicate is closed on shared boundaries),
    the first matching polygon in the districts frame wins, matching the
    pre-vectorization `iloc[0]` semantics.

    Writes two columns on the facility row:
      * `spatial_district` — geoBoundaries `shapeName` (human-readable district),
        used by the NFHS join and the side-panel render.
      * `district_id` — geoBoundaries `shapeID`, the canonical identifier per
        EE-SPATIAL-001. Travels downstream into Lakebase + desert-scoring as the
        district key.
    """
    out = facilities.copy()
    out["spatial_district"] = None
    out["district_id"] = None
    has_shape_id = "shapeID" in districts.columns

    lat = pd.to_numeric(facilities.get("latitude"), errors="coerce")
    lon = pd.to_numeric(facilities.get("longitude"), errors="coerce")
    has_latlon_mask = lat.notna() & lon.notna()
    if not has_latlon_mask.any():
        return out

    fac_subset = facilities.loc[has_latlon_mask].copy()
    points = gpd.points_from_xy(lon[has_latlon_mask], lat[has_latlon_mask])
    fac_gdf = gpd.GeoDataFrame(
        fac_subset, geometry=points, crs=districts.crs or "EPSG:4326",
    )

    cols = ["district", "geometry"] + (["shapeID"] if has_shape_id else [])
    joined = gpd.sjoin(
        fac_gdf, districts[cols], predicate="within", how="left",
    ).drop_duplicates(subset=["facility_id"], keep="first")

    fid_to_dist = joined.set_index("facility_id")["district"]
    out["spatial_district"] = out["facility_id"].map(fid_to_dist)
    if has_shape_id:
        fid_to_shape = joined.set_index("facility_id")["shapeID"]
        out["district_id"] = out["facility_id"].map(fid_to_shape)
    return out


# @spec EE-SPATIAL-003
def modal_pin_district(india_post_df: pd.DataFrame) -> pd.DataFrame:
    if india_post_df.empty:
        return pd.DataFrame(columns=["pincode", "district", "modal_share"])

    counts = (
        india_post_df.groupby(["pincode", "district"]).size().reset_index(name="n")
    )
    totals = counts.groupby("pincode")["n"].sum().rename("total")
    counts = counts.merge(totals, on="pincode")
    counts["share"] = counts["n"] / counts["total"]
    idx = counts.groupby("pincode")["n"].idxmax()
    modal = counts.loc[idx, ["pincode", "district", "share"]].rename(
        columns={"share": "modal_share"}
    )
    return modal.reset_index(drop=True)


# @spec EE-SPATIAL-003
def normalize_district_name(name: str) -> str:
    if name is None:
        return ""
    return _PUNCT_RE.sub("", str(name).lower()).strip()


# @spec EE-SPATIAL-001..006
def run_spatial_test(
    facilities: pd.DataFrame,
    districts: gpd.GeoDataFrame,
    india_post_df: pd.DataFrame,
    assigned: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Run Test 3.

    When the caller has already produced a `facilities_with_district` frame
    (e.g. via `assign_districts` upstream in `pipeline.run_engine`), pass it in
    via `assigned=` to avoid re-running the R-tree spatial join. The frame
    must carry `spatial_district` and `district_id` columns alongside the
    original facility data.
    """
    assigned = assigned if assigned is not None else assign_districts(facilities, districts)
    modal = modal_pin_district(india_post_df).set_index("pincode")

    rows: list[dict] = []
    for _, fac in assigned.iterrows():
        fac_id = fac["facility_id"]
        pin = parse_pincode(fac.get("pincode"))
        sp_district = fac.get("spatial_district")
        has_latlon = _has_latlon(fac.get("latitude"), fac.get("longitude"))

        if not has_latlon or pin is None or sp_district is None:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue
        if pin not in modal.index:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        pin_row = modal.loc[pin]
        if pin_row["modal_share"] <= AMBIGUOUS_PIN_MODAL_THRESHOLD:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, {
                "ambiguous_pin": True, "modal_share": float(pin_row["modal_share"]),
            }))
            continue

        pin_district = pin_row["district"]
        if normalize_district_name(sp_district) == normalize_district_name(pin_district):
            rows.append(_row(fac_id, TestResult.PASS, None))
        else:
            rows.append(_row(fac_id, TestResult.FAIL, {
                "spatial_district": sp_district, "pin_district": pin_district,
            }))

    return pd.DataFrame(rows)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.SPATIAL.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }
