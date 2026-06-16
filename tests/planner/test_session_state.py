"""Tests for planner session state + identity resolution."""
from __future__ import annotations

import pytest

from phantom_census.planner_workspace.session import (
    LOCAL_DEV_PLANNER_ID,
    WorkspaceState,
    init_session_state,
    resolve_planner_id,
)


# @spec PW-OVR-003, PW-SCEN-001
def test_resolve_planner_id_from_apps_header():
    assert resolve_planner_id({"X-Forwarded-Email": "planner@example.com"}) == (
        "planner@example.com"
    )


# @spec PW-OVR-003
def test_resolve_planner_id_from_env_when_header_absent(monkeypatch):
    monkeypatch.setenv("PLANNER_ID", "env-user")
    assert resolve_planner_id({}) == "env-user"


def test_resolve_planner_id_falls_back_to_local_dev(monkeypatch):
    monkeypatch.delenv("PLANNER_ID", raising=False)
    assert resolve_planner_id({}) == LOCAL_DEV_PLANNER_ID


def test_init_session_state_is_idempotent():
    session: dict = {}
    s1 = init_session_state(session, planner_id="x@y.com")
    s2 = init_session_state(session, planner_id="x@y.com")
    assert s1 is s2
    assert isinstance(s1, WorkspaceState)
    assert session["planner_id"] == "x@y.com"


def test_workspace_state_defaults():
    s = WorkspaceState()
    assert s.capability == "maternity"
    assert s.view == "raw"
    assert s.selected_district is None
    assert s.override_set == []
