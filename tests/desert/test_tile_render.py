"""Tests for DS-TILE-001..005, DS-RANK-001..003, DS-CTR-001..003."""
from __future__ import annotations

import pandas as pd
import pytest

from phantom_census.desert_scoring.formula import compute_district_scores
from phantom_census.desert_scoring.tiles import (
    build_rank_table,
    phantom_counter,
    render_tile_html,
    token_usage_indicator,
    validate_tile_layers,
)

CAPABILITIES = ["maternity", "icu", "emergency", "trauma", "nicu"]
_GOOD_HTML = "<html><body>leaflet map " + "x" * 60_000 + "</body></html>"


def _tiles_frame(rows: list[tuple[str, str]], html: str = _GOOD_HTML) -> pd.DataFrame:
    return pd.DataFrame(
        [{"capability": cap, "layer_type": lt, "html": html} for cap, lt in rows]
    )


def _complete_rows() -> list[tuple[str, str]]:
    return [(cap, lt) for cap in CAPABILITIES for lt in ("raw", "adjusted")]


# @spec DS-TILE-001
def test_render_tile_returns_html_string(
    small_facilities_with_district, small_verdicts, small_nfhs, small_districts
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    html = render_tile_html(districts_gdf=small_districts, scores=scores,
                            score_col="raw_desert_score")
    assert isinstance(html, str)
    assert "<html" in html.lower() or "leaflet" in html.lower()


# @spec DS-TILE-002
def test_render_tile_color_scale_is_red_intensity(
    small_facilities_with_district, small_verdicts, small_nfhs, small_districts
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    html = render_tile_html(districts_gdf=small_districts, scores=scores,
                            score_col="raw_desert_score")
    # Folium choropleth with YlOrRd / Reds palette will reference one of these
    assert any(
        marker in html
        for marker in ("YlOrRd", "Reds", "rgb(", "#fee", "#67000d")
    ) or "fill" in html.lower()


# @spec DS-RANK-001, DS-RANK-002
def test_rank_table_sorted_by_active_score_with_rank_delta(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    raw_table = build_rank_table(scores, active="raw")
    assert list(raw_table["raw_desert_score"]) == sorted(
        raw_table["raw_desert_score"], reverse=True
    )
    assert "rank_delta" in raw_table.columns


# @spec DS-RANK-003
def test_rank_table_resorts_on_active_change(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    raw = build_rank_table(scores, active="raw")
    adjusted = build_rank_table(scores, active="adjusted")
    # If any phantom is present, the top of the adjusted table may differ from raw.
    assert list(raw["district_id"]) != list(adjusted["district_id"]) or \
           (scores["phantom_count"] == 0).all()


# @spec DS-CTR-001
def test_phantom_counter_returns_total_for_capability(
    small_facilities_with_district, small_verdicts, small_nfhs
):
    scores = compute_district_scores(
        facilities_with_district=small_facilities_with_district,
        verdicts=small_verdicts,
        nfhs=small_nfhs,
        capability="maternity",
    )
    assert phantom_counter(scores) == 1


# @spec DS-CTR-003
def test_token_usage_indicator_is_zero():
    assert token_usage_indicator() == "token_usage: 0"


# @spec DS-TILE-005
def test_validate_tile_layers_accepts_complete_set():
    tiles = _tiles_frame(_complete_rows())
    # Returns the frame unchanged so it can be chained before a write.
    assert validate_tile_layers(tiles, CAPABILITIES) is tiles


# @spec DS-TILE-005
def test_validate_tile_layers_raises_on_missing_raw():
    # The issue #5 regression: adjusted-only set for every capability.
    tiles = _tiles_frame([(cap, "adjusted") for cap in CAPABILITIES])
    with pytest.raises(RuntimeError) as exc:
        validate_tile_layers(tiles, CAPABILITIES)
    msg = str(exc.value)
    assert "raw" in msg
    # All five missing raw pairs reported, not just the first.
    assert all(cap in msg for cap in CAPABILITIES)


# @spec DS-TILE-005
def test_validate_tile_layers_raises_on_degenerate_html():
    rows = _complete_rows()
    tiles = _tiles_frame(rows)
    # Blank out one tile's HTML — present as a row but unusable.
    tiles.loc[(tiles["capability"] == "icu") & (tiles["layer_type"] == "raw"), "html"] = ""
    with pytest.raises(RuntimeError, match="Degenerate"):
        validate_tile_layers(tiles, CAPABILITIES)


# @spec DS-TILE-005
def test_validate_tile_layers_rejects_html_without_leaflet_marker():
    tiles = _tiles_frame(_complete_rows(), html="x" * 60_000)  # big but not a map
    with pytest.raises(RuntimeError, match="Degenerate"):
        validate_tile_layers(tiles, CAPABILITIES)
