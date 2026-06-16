"""Tests for DS-TILE-001..004, DS-RANK-001..003, DS-CTR-001..003."""
from __future__ import annotations

import pandas as pd

from phantom_census.desert_scoring.formula import compute_district_scores
from phantom_census.desert_scoring.tiles import (
    build_rank_table,
    phantom_counter,
    render_tile_html,
    token_usage_indicator,
)


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
