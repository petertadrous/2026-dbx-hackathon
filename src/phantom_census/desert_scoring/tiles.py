"""Folium tile pre-rendering + ranking + counter helpers.

@spec DS-TILE-001, DS-TILE-002, DS-TILE-003, DS-TILE-004, DS-TILE-005,
      DS-RANK-001, DS-RANK-002, DS-RANK-003,
      DS-CTR-001, DS-CTR-002, DS-CTR-003
"""
from __future__ import annotations

from typing import Iterable, Literal

import folium
import geopandas as gpd
import pandas as pd

INDIA_CENTER = (22.0, 78.5)


# @spec DS-TILE-001, DS-TILE-002
def render_tile_html(
    districts_gdf: gpd.GeoDataFrame,
    scores: pd.DataFrame,
    *,
    score_col: Literal["raw_desert_score", "adjusted_desert_score"],
    capability: str = "maternity",
) -> str:
    """Render a Folium choropleth as an HTML string.

    Both `raw` and `adjusted` calls must produce HTML on the same red-intensity
    color scale (0..1) so toggling between them is interpretable as relative
    change rather than scale change.
    """
    merged = districts_gdf.merge(
        scores[["district_id", "raw_desert_score", "adjusted_desert_score",
                "phantom_count", "verified_facility_count"]],
        on="district_id", how="left",
    )
    merged[score_col] = merged[score_col].fillna(0.0)

    m = folium.Map(location=list(INDIA_CENTER), zoom_start=5,
                   tiles="cartodbpositron")

    folium.Choropleth(
        geo_data=merged.__geo_interface__,
        data=merged,
        columns=["district_id", score_col],
        key_on="feature.properties.district_id",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.2,
        nan_fill_color="#eeeeee",
        bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        legend_name=f"{capability} desert score ({score_col})",
    ).add_to(m)

    return m.get_root().render()


# @spec DS-RANK-001, DS-RANK-002, DS-RANK-003
def build_rank_table(
    scores: pd.DataFrame,
    *,
    active: Literal["raw", "adjusted"],
) -> pd.DataFrame:
    """Return a ranking table sorted by the active score; carries rank_delta.

    rank_delta = raw_rank - adjusted_rank (positive = district moved up in the
    adjusted view; negative = moved down). Sort direction: highest score first.
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


# @spec DS-TILE-005
def validate_tile_layers(
    tiles_df: pd.DataFrame,
    capabilities: Iterable[str],
    *,
    layer_types: tuple[str, ...] = ("raw", "adjusted"),
    min_html_len: int = 50_000,
) -> pd.DataFrame:
    """Fail loudly unless every (capability, layer_type) has one usable tile.

    Guards the batch tile-render and Lakebase-load paths so a stale or partial
    notebook can never silently ship an incomplete `tile_layers` set (e.g. the
    adjusted-only regression from issue #5). Returns `tiles_df` unchanged on
    success so callers can chain it before a write.

    A tile is "usable" when its HTML is present, at least `min_html_len` chars,
    and contains a Folium/Leaflet structural marker — a size floor alone is not
    enough to prove the choropleth actually rendered.
    """
    expected = {(cap, lt) for cap in capabilities for lt in layer_types}

    present_pairs = set(
        map(tuple, tiles_df[["capability", "layer_type"]].drop_duplicates().to_numpy())
    )
    missing = sorted(expected - present_pairs)
    if missing:
        raise RuntimeError(
            f"Missing tile layers for {len(missing)} (capability, layer_type) "
            f"pair(s): {missing}"
        )

    html = tiles_df["html"].fillna("")
    too_small = html.str.len() < min_html_len
    no_marker = ~html.str.contains("leaflet", case=False) & ~html.str.contains(
        "<html", case=False
    )
    degenerate = tiles_df[too_small | no_marker]
    if not degenerate.empty:
        bad = sorted(
            map(tuple, degenerate[["capability", "layer_type"]].to_numpy())
        )
        raise RuntimeError(
            f"Degenerate tile HTML (empty, < {min_html_len} chars, or missing "
            f"Leaflet marker) for: {bad}"
        )

    return tiles_df
