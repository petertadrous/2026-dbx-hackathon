"""Tests for PW-AI-001..005 — AI Advisory block render decisions."""
from __future__ import annotations

import pandas as pd

from phantom_census.planner_workspace.ai_advisory_render import (
    decide_advisory_render,
)


def _row(**overrides) -> pd.Series:
    base = {
        "facility_id": "F1",
        "adjudicator_verdict": "contested",
        "verdict": "contested",
        "rescue_applied": None,
        "test_outcome_vector": [],
        "ai_recommendation": None,
        "ai_recommendation_evidence_state": None,
        "override_id": None,
        "layer_c_synthesis": None,
    }
    base.update(overrides)
    return pd.Series(base)


# @spec PW-AI-005
def test_no_block_for_non_contested_verdict():
    row = _row(verdict="phantom")
    rendered = decide_advisory_render(row, ai_query=lambda **kw: {})
    assert rendered is None

    row2 = _row(verdict="real")
    rendered2 = decide_advisory_render(row2, ai_query=lambda **kw: {})
    assert rendered2 is None


# @spec PW-AI-001
def test_block_renders_with_recommendation_for_contested_verdict():
    def fake_ai(**kwargs):
        return {
            "recommendation": "force-phantom",
            "confidence": "medium",
            "reasoning": "PIN mismatch survives, no HFR match.",
            "cited_evidence_rows": ["row-1"],
            "source": "fma",
        }
    rendered = decide_advisory_render(_row(), ai_query=fake_ai)
    assert rendered is not None
    assert rendered["payload"]["recommendation"] == "force-phantom"


# @spec PW-AI-002
def test_template_fallback_appends_marker():
    def raising_ai(**kwargs):
        raise RuntimeError("FMA unavailable")
    rendered = decide_advisory_render(_row(), ai_query=raising_ai)
    assert rendered is not None
    assert rendered["payload"]["source"] == "template-fallback"
    # The block-level marker exposed to callers as a flag.
    assert rendered["template_fallback"] is True


# @spec PW-AI-003
def test_historical_advisory_when_override_present_and_recommendation_cached():
    row = _row(
        override_id="ovr-1",
        ai_recommendation={
            "recommendation": "force-phantom", "confidence": "high",
            "reasoning": "x", "cited_evidence_rows": [], "source": "fma",
        },
    )
    rendered = decide_advisory_render(row, ai_query=lambda **kw: {})
    assert rendered is not None
    assert rendered["mark"] == "historical-advisory"


# @spec PW-AI-004
def test_no_block_when_override_present_and_no_recommendation():
    row = _row(override_id="ovr-1", ai_recommendation=None)
    rendered = decide_advisory_render(row, ai_query=lambda **kw: {})
    assert rendered is None
