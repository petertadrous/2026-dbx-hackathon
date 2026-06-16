"""Phantom Census — Lakebase persistence segment."""
from __future__ import annotations

from .ai_cache_writes import persist_ai_recommendation
from .engine import build_engine_from_env, build_engine_pair, get_engine
from .migrate import init_schema
from .overrides import apply_override, save_override, submit_override
from .readers import (
    get_available_capabilities,
    get_desert_scores,
    get_district_phantoms,
    get_facility_tests,
    get_saved_scenarios,
)
from .rescue_writes import apply_layer_a_rescue
from .scenarios import restore_scenario, save_scenario
from .writer import WriteStats, load_engine_outputs

__all__ = [
    "get_engine", "build_engine_from_env", "build_engine_pair",
    "init_schema",
    "load_engine_outputs", "WriteStats",
    "get_desert_scores", "get_district_phantoms", "get_facility_tests",
    "get_available_capabilities", "get_saved_scenarios",
    "save_override", "apply_override", "submit_override",
    "save_scenario", "restore_scenario",
    "apply_layer_a_rescue", "persist_ai_recommendation",
]
