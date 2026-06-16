"""Tests for the callback contract that the views call.

These exercise the Python side without spinning up Streamlit; the views are
thin shells around these callbacks per the design.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from phantom_census.planner_workspace.callbacks import (
    restore,
    submit_override,
    submit_scenario_save,
)


# @spec PW-OVR-002
def test_submit_override_rejects_empty_reason():
    with pytest.raises(ValueError):
        submit_override(
            engine=None,
            facility_id="F1",
            override_type="force-real",
            reason_note="",
            planner_id="p",
            capability="maternity",
        )


# @spec PW-OVR-003, PW-OVR-005
def test_submit_override_invokes_single_tx_entry():
    with patch("phantom_census.planner_workspace.callbacks._submit_override") as inner:
        inner.return_value = ("OID-123", "BEED")
        out = submit_override(
            engine=object(),
            facility_id="F1",
            override_type="force-real",
            reason_note="ok",
            planner_id="p",
            capability="maternity",
        )
    assert out == "OID-123"
    inner.assert_called_once()
    kwargs = inner.call_args.kwargs
    assert callable(kwargs.get("recompute_fn"))


# @spec PW-SCEN-001
def test_submit_scenario_save_passes_through():
    with patch("phantom_census.planner_workspace.callbacks.save_scenario") as save_:
        save_.return_value = "SID-A"
        out = submit_scenario_save(
            engine=object(),
            scenario_name="snap",
            capability="maternity",
            region_filter="Maharashtra",
            override_ids=["OID-1"],
            planner_notes="",
            planner_id="p",
        )
    assert out == "SID-A"
    save_.assert_called_once()


# @spec PW-SCEN-003, PW-SCEN-004
def test_restore_passes_recompute_callback():
    with patch("phantom_census.planner_workspace.callbacks.restore_scenario") as r_:
        r_.return_value = ["BEED"]
        out = restore(engine=object(), scenario_id="SID-A")
    assert out == ["BEED"]
    kwargs = r_.call_args.kwargs
    assert kwargs.get("scenario_id") == "SID-A"
    assert callable(kwargs.get("recompute_fn"))
