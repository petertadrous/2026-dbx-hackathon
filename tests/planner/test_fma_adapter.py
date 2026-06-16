"""Tests for the Foundation Model API adapter scaffold."""
from __future__ import annotations

import pytest

from phantom_census.planner_workspace.fma_adapter import (
    FMANotConfiguredError,
    build_ai_evidence_adapter,
    build_genie_sql_adapter,
)


def test_evidence_adapter_raises_when_env_not_configured(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    adapter = build_ai_evidence_adapter()
    with pytest.raises(FMANotConfiguredError):
        adapter(facility_id="F1")


def test_genie_adapter_raises_when_env_not_configured(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    adapter = build_genie_sql_adapter()
    with pytest.raises(FMANotConfiguredError):
        adapter("which 5 districts gain the most rank?")


def test_evidence_adapter_calls_serving_endpoint_when_configured(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://fake.databricks.example")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-fake")

    calls: list[dict] = []

    def fake_call(*, model, prompt, response_shape):
        calls.append({"model": model, "prompt": prompt})
        return {
            "recommendation": "force-phantom",
            "confidence": "medium",
            "reasoning": "ok",
            "cited_evidence_rows": [],
            "source": "fma",
        }

    monkeypatch.setattr(
        "phantom_census.planner_workspace.fma_adapter._call_serving_endpoint",
        fake_call,
    )

    adapter = build_ai_evidence_adapter()
    rec = adapter(facility_id="F1", test_outcome_vector=[],
                  adjudicator_verdict="contested",
                  rescue_applied=None, layer_c_synthesis=None)
    assert rec["recommendation"] == "force-phantom"
    assert len(calls) == 1


def test_genie_adapter_extracts_sql_string_from_serving_response(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://fake.databricks.example")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-fake")

    def fake_call(*, model, prompt, response_shape):
        return {"sql": "SELECT district_id FROM operational.desert_scores"}

    monkeypatch.setattr(
        "phantom_census.planner_workspace.fma_adapter._call_serving_endpoint",
        fake_call,
    )

    adapter = build_genie_sql_adapter()
    sql = adapter("top 5 districts?")
    assert sql.startswith("SELECT")
    assert "operational.desert_scores" in sql


def test_evidence_adapter_raising_failure_falls_through_to_maybe_render_template():
    """The raising adapter integrates with ai_evidence_layer.maybe_render's
    EE-AI-009 template-fallback path: exception → template payload."""
    import pandas as pd
    from phantom_census.existence_engine.ai_evidence_layer import maybe_render

    adapter = build_ai_evidence_adapter()
    # Default-configured (no env) → raising adapter.
    row = pd.Series({
        "facility_id": "F1",
        "verdict": "contested",
        "adjudicator_verdict": "contested",
        "rescue_applied": None,
        "test_outcome_vector": [
            {"test_name": "pin-reverse-lookup", "result": "fail", "evidence_ref": None},
            {"test_name": "minhash-near-duplicate", "result": "pass", "evidence_ref": None},
        ],
        "ai_recommendation": None,
        "ai_recommendation_evidence_state": None,
        "override_id": None,
        "layer_c_synthesis": None,
    })
    rendered = maybe_render(row, ai_query=adapter)
    assert rendered is not None
    assert rendered["payload"]["source"] == "template-fallback"
    # Veto-capable fail → force-phantom per EE-AI-009.
    assert rendered["payload"]["recommendation"] == "force-phantom"
