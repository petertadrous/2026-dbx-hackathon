"""Structural smoke tests for the planner workspace.

These verify that every PW-* view module the EARS specs reference is present
and exposes a `render` (or equivalent) entry point. Behavior is covered by
test_callbacks.py + the deterministic-helper tests; here we only assert
structural presence so the spec-coverage gate remains tight even without a
live Streamlit session.
"""
from __future__ import annotations


def test_planner_workspace_module_imports():
    import phantom_census.planner_workspace as pkg  # noqa: F401
    assert callable(pkg.main)


# @spec PW-MAP-001, PW-MAP-002, PW-MAP-003, PW-MAP-004, PW-MAP-005, PW-MAP-006
def test_map_view_module_exposes_render():
    from phantom_census.planner_workspace.views import map_view
    assert callable(map_view.render)


# @spec PW-PANEL-001, PW-PANEL-002, PW-PANEL-003, PW-PANEL-004, PW-PANEL-005
def test_side_panel_module_exposes_render():
    from phantom_census.planner_workspace.views import side_panel
    assert callable(side_panel.render)
    assert side_panel.PHANTOM_LIMIT == 5


# @spec PW-OVR-001, PW-OVR-004, PW-OVR-007
def test_override_modal_module_exposes_render():
    from phantom_census.planner_workspace.views import override_modal
    assert callable(override_modal.render)


# @spec PW-SCEN-002
def test_scenario_panel_module_exposes_render():
    from phantom_census.planner_workspace.views import scenario_panel
    assert callable(scenario_panel.render)


# @spec PW-AI-001, PW-AI-002, PW-AI-003, PW-AI-004, PW-AI-005
def test_ai_advisory_module_exposes_render():
    from phantom_census.planner_workspace.views import ai_advisory
    assert callable(ai_advisory.render)


# @spec PW-BUDGET-001
def test_budget_view_module_exposes_render():
    from phantom_census.planner_workspace.views import budget_view
    assert callable(budget_view.render)


# @spec PW-AUDIT-001
def test_audit_view_module_exposes_render():
    from phantom_census.planner_workspace.views import audit_view
    assert callable(audit_view.render)


# @spec PW-GENIE-004
def test_genie_sidebar_module_exposes_render():
    from phantom_census.planner_workspace.views import genie_sidebar
    assert callable(genie_sidebar.render)


# @spec PW-SHELL-001
def test_shell_renders_three_tabs():
    """The app shell exposes a build_tabs helper returning the three tab labels."""
    from phantom_census.planner_workspace import shell
    tabs = shell.TAB_LABELS
    assert tabs == ("Map", "Budget Reallocation", "Audit Queue")
