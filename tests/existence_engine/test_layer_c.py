"""Tests for Defender Layer C — FMA corroboration synthesis (activation-gated).

Covers EE-LAYER-C-001..005. Layer C fires only when the final verdict (after
Layer A patching) is `contested`. Output is advisory and does NOT mutate the
verdict; it feeds the AI Evidence Layer's escalation package.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import layer_c
from phantom_census.existence_engine.types import Verdict


def _must_not_call(**kwargs):
    raise AssertionError("Layer C should not have invoked ai_query")


def _verdicts(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "facility_id": r["facility_id"],
            "adjudicator_verdict": r["adjudicator_verdict"],
            "verdict": r["verdict"],
            "rescue_applied": r.get("rescue_applied"),
            "test_outcome_vector": r.get("test_outcome_vector", []),
            "layer_c_synthesis": None,
        }
        for r in rows
    ])


def _facility_rows() -> pd.DataFrame:
    return pd.DataFrame([{
        "facility_id": "F1", "facility_name": "Disputed Clinic",
        "description": "Some claim", "capability": [], "equipment": [],
    }])


def _layer_b_results() -> pd.DataFrame:
    return pd.DataFrame(columns=["facility_id", "matched", "reason"])


# @spec EE-LAYER-C-001
def test_layer_c_does_not_fire_on_real_verdict():
    verdicts = _verdicts([{
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.REAL.value,
        "verdict": Verdict.REAL.value,
    }])
    out = layer_c.run_layer_c(
        verdicts, _facility_rows(), _layer_b_results(),
        ai_query=_must_not_call,
    )
    assert out.iloc[0]["layer_c_synthesis"] is None


# @spec EE-LAYER-C-001
def test_layer_c_does_not_fire_on_phantom_verdict():
    verdicts = _verdicts([{
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.PHANTOM.value,
        "verdict": Verdict.PHANTOM.value,
    }])
    out = layer_c.run_layer_c(verdicts, _facility_rows(), _layer_b_results(),
                               ai_query=lambda **kwargs: None)
    assert out.iloc[0]["layer_c_synthesis"] is None


# @spec EE-LAYER-C-002, EE-LAYER-C-003
def test_layer_c_fires_on_contested_and_emits_structured_payload():
    verdicts = _verdicts([{
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.CONTESTED.value,
        "verdict": Verdict.CONTESTED.value,
    }])

    def fake_ai_query(**kwargs):
        return {
            "strength": "medium",
            "supporting_rows": ["test-row-1", "layer-a-hfr"],
            "reasoning": "Evidence is mixed; HFR match contradicts spatial fail.",
        }

    out = layer_c.run_layer_c(verdicts, _facility_rows(), _layer_b_results(),
                               ai_query=fake_ai_query)
    syn = out.iloc[0]["layer_c_synthesis"]
    assert syn is not None
    assert syn["strength"] in {"weak", "medium", "strong"}
    assert isinstance(syn["supporting_rows"], list)
    assert isinstance(syn["reasoning"], str)


# @spec EE-LAYER-C-004
def test_layer_c_template_fallback_when_ai_query_raises():
    verdicts = _verdicts([{
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.CONTESTED.value,
        "verdict": Verdict.CONTESTED.value,
    }])

    def raising_ai_query(**kwargs):
        raise TimeoutError("FMA unavailable")

    out = layer_c.run_layer_c(verdicts, _facility_rows(), _layer_b_results(),
                               ai_query=raising_ai_query)
    syn = out.iloc[0]["layer_c_synthesis"]
    assert syn["strength"] == "weak"
    assert "reasoning" in syn
    assert isinstance(syn["supporting_rows"], list)


# @spec EE-LAYER-C-005
def test_layer_c_does_not_modify_verdict_columns():
    verdicts = _verdicts([{
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.PHANTOM.value,
        "verdict": Verdict.CONTESTED.value,  # Layer A patched
        "rescue_applied": {"signals": [{"signal": "hfr-match"}]},
    }])

    def fake_ai_query(**kwargs):
        return {
            "strength": "strong", "supporting_rows": [],
            "reasoning": "ok",
        }

    out = layer_c.run_layer_c(verdicts, _facility_rows(), _layer_b_results(),
                               ai_query=fake_ai_query)
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.PHANTOM.value
    assert out.iloc[0]["verdict"] == Verdict.CONTESTED.value
