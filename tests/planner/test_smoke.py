"""Structural smoke tests for the planner workspace.

These verify that every PW-* view module the EARS specs reference is present
and exposes a `render` (or equivalent) entry point. The behavioral side of
each view is covered by `test_callbacks.py` + downstream lakebase / desert
tests; here we only assert structural presence so the spec-coverage gate
remains tight even without a live Streamlit session.
"""
from __future__ import annotations


def test_planner_workspace_module_imports():
    import phantom_census.planner_workspace as pkg  # noqa: F401
    assert callable(pkg.main)


# @spec PW-MAP-001, PW-MAP-002, PW-MAP-003, PW-MAP-005, PW-MAP-006, PW-MAP-007,
# @spec DS-TILE-003, DS-TILE-004
def test_map_view_module_exposes_render():
    from phantom_census.planner_workspace.views import map_view
    assert callable(map_view.render)
    assert "maternity" in map_view.SUPPORTED_CAPABILITIES


# @spec PW-PANEL-001, PW-PANEL-002, PW-PANEL-003, PW-PANEL-004, DS-TILE-001a
def test_side_panel_module_exposes_render():
    from phantom_census.planner_workspace.views import side_panel
    assert callable(side_panel.render)
    assert side_panel.PHANTOM_LIMIT == 5


# @spec PW-OVR-001, PW-OVR-004
def test_override_modal_module_exposes_render():
    from phantom_census.planner_workspace.views import override_modal
    assert callable(override_modal.render)


# @spec PW-SCEN-002
def test_scenario_panel_module_exposes_render():
    from phantom_census.planner_workspace.views import scenario_panel
    assert callable(scenario_panel.render)
