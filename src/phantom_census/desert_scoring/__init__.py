"""Phantom Census — desert scoring segment."""
from __future__ import annotations

from .burden import burden_weight, state_medians_from_nfhs
from .formula import compute_district_scores
from .recompute import recompute_district, recompute_in_memory
from .tiles import (
    build_rank_table,
    phantom_counter,
    render_tile_html,
    token_usage_indicator,
)

__all__ = [
    "compute_district_scores",
    "burden_weight", "state_medians_from_nfhs",
    "render_tile_html", "build_rank_table",
    "phantom_counter", "token_usage_indicator",
    "recompute_in_memory", "recompute_district",
]
