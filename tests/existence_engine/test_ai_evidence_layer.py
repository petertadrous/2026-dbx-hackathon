"""Tests for the AI Evidence Layer (activation-gated, planner-open).

Covers EE-AI-001..012. Lazy invocation at planner-open time only; cache key
is sha256 of (test_outcome_vector + adjudicator_verdict + rescue_applied);
override_id is the top-priority gate.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from phantom_census.existence_engine import ai_evidence_layer as ai
from phantom_census.existence_engine.types import Verdict


def _canonical_evidence_state(
    test_outcome_vector: list,
    adjudicator_verdict: str,
    rescue_applied: dict | None,
) -> str:
    payload = (
        json.dumps(test_outcome_vector, sort_keys=True, separators=(",", ":"))
        + adjudicator_verdict
        + json.dumps(rescue_applied, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _must_not_call(**kwargs):
    raise AssertionError("FMA should not have been invoked")


def _verdict_row(**kwargs) -> pd.Series:
    base = {
        "facility_id": "F1",
        "adjudicator_verdict": Verdict.CONTESTED.value,
        "verdict": Verdict.CONTESTED.value,
        "rescue_applied": None,
        "test_outcome_vector": [
            {"test_name": "pin", "result": "pass", "evidence_ref": None},
            {"test_name": "spatial", "result": "pass", "evidence_ref": None},
        ],
        "ai_recommendation": None,
        "ai_recommendation_evidence_state": None,
        "override_id": None,
        "layer_c_synthesis": None,
    }
    base.update(kwargs)
    return pd.Series(base)


# @spec EE-AI-001
def test_ai_evidence_layer_does_not_fire_on_non_contested_verdict():
    row = _verdict_row(verdict=Verdict.REAL.value)
    rec = ai.maybe_render(row, ai_query=_must_not_call)
    assert rec is None


# @spec EE-AI-002
def test_evidence_state_hash_excludes_verdict_column():
    """The verdict column changes on override; evidence_state must not."""
    row = _verdict_row()
    s1 = ai.compute_evidence_state(row)
    row2 = _verdict_row(verdict="force-real-planner")
    s2 = ai.compute_evidence_state(row2)
    assert s1 == s2

    expected = _canonical_evidence_state(
        row["test_outcome_vector"], row["adjudicator_verdict"], row["rescue_applied"],
    )
    assert s1 == expected


# @spec EE-AI-002
def test_evidence_state_hash_includes_adjudicator_verdict_and_rescue():
    base = _verdict_row()
    s_base = ai.compute_evidence_state(base)
    different_adj = _verdict_row(adjudicator_verdict=Verdict.PHANTOM.value)
    s_diff_adj = ai.compute_evidence_state(different_adj)
    assert s_base != s_diff_adj

    different_rescue = _verdict_row(rescue_applied={"signals": [{"signal": "hfr-match"}]})
    s_diff_rescue = ai.compute_evidence_state(different_rescue)
    assert s_base != s_diff_rescue


# @spec EE-AI-003
def test_existing_override_with_existing_recommendation_renders_historical():
    rec_payload = {
        "recommendation": "force-phantom", "confidence": "high",
        "reasoning": "ok", "cited_evidence_rows": [], "source": "fma",
    }
    row = _verdict_row(
        override_id="ovr-1",
        ai_recommendation=rec_payload,
    )
    rendered = ai.maybe_render(row, ai_query=_must_not_call)
    assert rendered is not None
    assert rendered["mark"] == "historical-advisory"
    assert rendered["payload"]["recommendation"] == "force-phantom"


# @spec EE-AI-003
def test_existing_override_without_recommendation_renders_nothing():
    row = _verdict_row(override_id="ovr-1", ai_recommendation=None)
    rendered = ai.maybe_render(row, ai_query=_must_not_call)
    assert rendered is None


# @spec EE-AI-004
def test_first_open_invokes_ai_query_persists_and_renders():
    calls = []

    def fake_ai(**kwargs):
        calls.append(kwargs)
        return {
            "recommendation": "force-phantom",
            "confidence": "medium",
            "reasoning": "Insufficient corroboration.",
            "cited_evidence_rows": ["test-row-1"],
            "source": "fma",
        }

    row = _verdict_row()
    rendered = ai.maybe_render(row, ai_query=fake_ai)
    assert rendered is not None
    assert len(calls) == 1
    assert rendered["persist"]["ai_recommendation"]["recommendation"] == "force-phantom"
    expected_state = ai.compute_evidence_state(row)
    assert rendered["persist"]["ai_recommendation_evidence_state"] == expected_state


# @spec EE-AI-005
def test_cache_hit_renders_without_ai_query_call():
    row = _verdict_row()
    state = ai.compute_evidence_state(row)
    cached_rec = {
        "recommendation": "evidence-too-thin", "confidence": "low",
        "reasoning": "thin", "cited_evidence_rows": [], "source": "fma",
    }
    row["ai_recommendation"] = cached_rec
    row["ai_recommendation_evidence_state"] = state

    def must_not_call(**kwargs):
        raise AssertionError("FMA should not be called on cache hit")

    rendered = ai.maybe_render(row, ai_query=must_not_call)
    assert rendered is not None
    assert rendered["persist"] is None
    assert rendered["payload"]["recommendation"] == "evidence-too-thin"


# @spec EE-AI-006
def test_evidence_state_mismatch_recomputes_and_overwrites():
    row = _verdict_row()
    row["ai_recommendation"] = {
        "recommendation": "force-phantom", "confidence": "low",
        "reasoning": "stale", "cited_evidence_rows": [], "source": "fma",
    }
    row["ai_recommendation_evidence_state"] = "deadbeef" * 8

    def fresh_ai(**kwargs):
        return {
            "recommendation": "force-real", "confidence": "high",
            "reasoning": "fresh", "cited_evidence_rows": [], "source": "fma",
        }

    rendered = ai.maybe_render(row, ai_query=fresh_ai)
    assert rendered["payload"]["recommendation"] == "force-real"
    expected_state = ai.compute_evidence_state(row)
    assert rendered["persist"]["ai_recommendation_evidence_state"] == expected_state


# @spec EE-AI-008
def test_ai_evidence_layer_output_shape():
    row = _verdict_row()

    def fake_ai(**kwargs):
        return {
            "recommendation": "force-phantom", "confidence": "high",
            "reasoning": "p", "cited_evidence_rows": ["a"], "source": "fma",
        }

    rendered = ai.maybe_render(row, ai_query=fake_ai)
    payload = rendered["payload"]
    assert set(payload.keys()) >= {
        "recommendation", "confidence", "reasoning", "cited_evidence_rows", "source",
    }
    assert payload["recommendation"] in {"force-real", "force-phantom", "evidence-too-thin"}
    assert payload["confidence"] in {"low", "medium", "high"}


# @spec EE-AI-009
def test_template_fallback_when_ai_query_raises():
    row = _verdict_row(
        test_outcome_vector=[
            {"test_name": "pin-reverse-lookup", "result": "fail", "evidence_ref": None},
            {"test_name": "spatial-district-mismatch", "result": "pass", "evidence_ref": None},
        ],
    )

    def raising_ai(**kwargs):
        raise RuntimeError("FMA timeout")

    rendered = ai.maybe_render(row, ai_query=raising_ai)
    payload = rendered["payload"]
    # Veto-capable PIN fail → force-phantom per EE-AI-009
    assert payload["recommendation"] == "force-phantom"
    assert payload["confidence"] == "low"
    assert payload["source"] == "template-fallback"
    # Still persists
    assert rendered["persist"]["ai_recommendation"]["source"] == "template-fallback"


# @spec EE-AI-009
def test_template_fallback_returns_evidence_too_thin_when_no_veto_fail():
    row = _verdict_row(test_outcome_vector=[
        {"test_name": "minhash-near-duplicate", "result": "fail", "evidence_ref": None},
    ])

    def raising_ai(**kwargs):
        raise RuntimeError("FMA timeout")

    rendered = ai.maybe_render(row, ai_query=raising_ai)
    assert rendered["payload"]["recommendation"] == "evidence-too-thin"


# @spec EE-AI-011
def test_ai_evidence_layer_never_modifies_verdict():
    """Recommendation is rendered; verdict mutation is reserved for Adjudicator,
    Layer A, and planner override."""
    row = _verdict_row()
    original_verdict = row["verdict"]

    def fake_ai(**kwargs):
        return {
            "recommendation": "force-phantom", "confidence": "high",
            "reasoning": "p", "cited_evidence_rows": [], "source": "fma",
        }

    ai.maybe_render(row, ai_query=fake_ai)
    assert row["verdict"] == original_verdict


# @spec EE-AI-012
def test_override_races_fma_guard_discards_result_when_override_present_at_write_time():
    """If an override lands while FMA is in flight, the persist payload must be
    suppressed so the result never appears as historical advisory."""
    row = _verdict_row()

    def fake_ai(**kwargs):
        return {
            "recommendation": "force-real", "confidence": "high",
            "reasoning": "p", "cited_evidence_rows": [], "source": "fma",
        }

    rendered = ai.maybe_render(
        row, ai_query=fake_ai,
        reread_override_id=lambda fac_id: "ovr-late-arriving",
    )
    # Either the persist is suppressed, or the rendered itself is None.
    assert rendered is None or rendered.get("persist") is None
