"""Phantom Census — desert scoring segment."""
from __future__ import annotations

from .burden import burden_weight, state_medians_from_nfhs
from .density import compute_max_density_per_km2
from .formula import compute_district_scores
from .ranking import build_rank_table, phantom_counter, token_usage_indicator
from .recompute import recompute_district, recompute_in_memory

__all__ = [
    "compute_district_scores",
    "compute_max_density_per_km2",
    "burden_weight", "state_medians_from_nfhs",
    "build_rank_table", "phantom_counter", "token_usage_indicator",
    "recompute_in_memory", "recompute_district",
]
