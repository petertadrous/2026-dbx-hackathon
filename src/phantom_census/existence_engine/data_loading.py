"""Bronze readers for the five engine input sources + builders.

Provides:
  load_facilities       — VF facility dataset (Parquet or CSV).
  load_india_post       — India Post PIN Code Directory (CSV).
  load_nfhs5            — NFHS-5 district indicator table (CSV).
  load_districts        — geoBoundaries India ADM2 polygons (GeoJSON).
  load_hfr              — pre-cached Health Facility Registry snapshot (CSV).
  build_district_to_state — district → state map derived from India Post modal.

The ADM2 GeoJSON has only `shapeName` (district), no state attribute, so
state is sourced from India Post and used as a sidecar lookup.

These readers do not transform claim arrays / coordinate types; the engine
modules normalize at use.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


def load_facilities(path: Path) -> pd.DataFrame:
    """Load the VF facility dataset.

    Required columns: facility_id, latitude, longitude, pincode, yearEstablished,
    capability, procedure, equipment, description.
    """
    p = Path(path)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    return pd.read_csv(p)


def load_india_post(path: Path) -> pd.DataFrame:
    """Load the India Post PIN Code Directory.

    Required columns (mapped to canonical names):
      pincode, district, state, latitude, longitude.

    Accepts upstream variants (`statename`, `Latitude`, etc.) and maps them.
    """
    df = pd.read_csv(path)
    rename = {}
    for raw, canon in [
        ("StateName", "state"), ("statename", "state"), ("State", "state"),
        ("District", "district"), ("Districtname", "district"),
        ("Pincode", "pincode"), ("PINCODE", "pincode"), ("Pin Code", "pincode"),
        ("Latitude", "latitude"), ("Longitude", "longitude"),
    ]:
        if raw in df.columns and canon not in df.columns:
            rename[raw] = canon
    if rename:
        df = df.rename(columns=rename)
    return df


def load_nfhs5(path: Path) -> pd.DataFrame:
    """Load the NFHS-5 district indicator table.

    Required columns: district, state, institutional_delivery_rate.
    """
    return pd.read_csv(path)


def load_districts(path: Path) -> gpd.GeoDataFrame:
    """Load geoBoundaries India ADM2 polygons.

    geoBoundaries exposes the district name as `shapeName`; this loader renames
    it to `district` so the engine modules can join uniformly.
    """
    gdf = gpd.read_file(path)
    if "district" not in gdf.columns and "shapeName" in gdf.columns:
        gdf = gdf.rename(columns={"shapeName": "district"})
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def load_hfr(path: Path | None) -> pd.DataFrame:
    """Load the HFR snapshot. Returns an empty frame when no path is given.

    Required columns: facility_name, district.
    """
    if path is None:
        return pd.DataFrame(columns=["facility_name", "district"])
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["facility_name", "district"])
    return pd.read_csv(p)


def build_district_to_state(
    india_post_df: pd.DataFrame,
    nfhs_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Build a district → state lookup.

    Primary source: India Post — group by district and take the modal state
    (resolves PINs straddling state borders).
    Secondary source: NFHS-5 — augments districts India Post does not list.
    """
    mapping: dict[str, str] = {}

    if not india_post_df.empty and {"district", "state"}.issubset(india_post_df.columns):
        modal = (
            india_post_df.dropna(subset=["district", "state"])
            .groupby("district")["state"]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
        )
        for district, state in modal.items():
            if state is not None:
                mapping[district] = state

    if nfhs_df is not None and {"district", "state"}.issubset(nfhs_df.columns):
        for _, row in nfhs_df.dropna(subset=["district", "state"]).iterrows():
            mapping.setdefault(row["district"], row["state"])

    return mapping
