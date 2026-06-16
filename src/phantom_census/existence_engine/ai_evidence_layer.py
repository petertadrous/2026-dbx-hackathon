"""AI Evidence Layer — activation-gated, planner-open.

Implements EE-AI-001..012.

Lazy: fires only when (a) `phantom_verdicts.verdict == 'contested'` and
(b) a planner has opened that facility's side panel. The `maybe_render`
entry point is what the planner-workspace calls per side-panel open;
the layer decides whether to invoke FMA, use the cache, or render
historical advisory, applying the override gate and the evidence-state
cache key.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

import pandas as pd

from .types import Verdict


HISTORICAL_ADVISORY = "historical-advisory"
LIVE_RECOMMENDATION = "live"


# @spec EE-AI-002
def compute_evidence_state(row: pd.Series) -> str:
    """sha256(canonical_json(test_outcome_vector) + adjudicator_verdict
              + canonical_json(rescue_applied or null))

    `verdict` is deliberately excluded so a planner override does not
    invalidate the cache.
    """
    tov = row.get("test_outcome_vector") or []
    adj = row.get("adjudicator_verdict") or ""
    rescue = row.get("rescue_applied")
    payload = (
        json.dumps(tov, sort_keys=True, separators=(",", ":"), default=str)
        + str(adj)
        + json.dumps(rescue, sort_keys=True, separators=(",", ":"), default=str)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# @spec EE-AI-001, EE-AI-003, EE-AI-004, EE-AI-005, EE-AI-006, EE-AI-008,
# @spec EE-AI-009, EE-AI-011, EE-AI-012
def maybe_render(
    row: pd.Series,
    *,
    ai_query: Callable[..., dict],
    reread_override_id: Callable[[str], object | None] | None = None,
) -> dict | None:
    """Decide whether to invoke FMA / use cache / render historical / render none.

    Returns one of:
      * None — render no AI advisory panel.
      * {"mark": ..., "payload": <recommendation>, "persist": <dict|None>}
        — render the recommendation; if `persist` is non-None the caller is
        expected to UPDATE phantom_verdicts with the named columns.

    Verdict mutation is reserved for the Adjudicator, Layer A, and planner
    override (EE-AI-011).
    """
    # EE-AI-001 — fire only on contested verdict.
    if row.get("verdict") != Verdict.CONTESTED.value:
        return None

    override_id = row.get("override_id")
    cached_rec = row.get("ai_recommendation")
    cached_state = row.get("ai_recommendation_evidence_state")

    # EE-AI-003 — override gate dominates.
    if override_id is not None and not _is_null(override_id):
        if cached_rec is not None and not _is_null(cached_rec):
            return {
                "mark": HISTORICAL_ADVISORY,
                "payload": cached_rec,
                "persist": None,
            }
        return None

    current_state = compute_evidence_state(row)

    if cached_rec is not None and not _is_null(cached_rec) and cached_state == current_state:
        # EE-AI-005 — cache hit; no FMA call.
        return {
            "mark": LIVE_RECOMMENDATION,
            "payload": cached_rec,
            "persist": None,
        }

    # EE-AI-004 / EE-AI-006 — first open or evidence-state mismatch; invoke FMA.
    try:
        rec = ai_query(
            facility_id=row.get("facility_id"),
            test_outcome_vector=row.get("test_outcome_vector") or [],
            adjudicator_verdict=row.get("adjudicator_verdict"),
            rescue_applied=row.get("rescue_applied"),
            layer_c_synthesis=row.get("layer_c_synthesis"),
        )
    except Exception:  # noqa: BLE001 — EE-AI-009 covers all errors.
        rec = _template_fallback(row)

    rec = _validate_or_fallback(rec, row)

    # EE-AI-012 — re-read override_id within the write transaction. If a
    # planner override has landed while FMA was in flight, suppress the persist
    # and the render so the result doesn't show up as historical advisory.
    if reread_override_id is not None:
        late_override = reread_override_id(row.get("facility_id"))
        if late_override is not None and not _is_null(late_override):
            return None

    return {
        "mark": LIVE_RECOMMENDATION,
        "payload": rec,
        "persist": {
            "ai_recommendation": rec,
            "ai_recommendation_evidence_state": current_state,
        },
    }


def _is_null(v: object) -> bool:
    try:
        return pd.isna(v)
    except (TypeError, ValueError):
        return False


# @spec EE-AI-008
_REQUIRED_KEYS = {
    "recommendation", "confidence", "reasoning", "cited_evidence_rows", "source",
}
_VALID_RECOMMENDATIONS = {"force-real", "force-phantom", "evidence-too-thin"}
_VALID_CONFIDENCE = {"low", "medium", "high"}


def _validate_or_fallback(rec: object, row: pd.Series) -> dict:
    if not isinstance(rec, dict) or not _REQUIRED_KEYS <= set(rec.keys()):
        return _template_fallback(row)
    if rec["recommendation"] not in _VALID_RECOMMENDATIONS:
        return _template_fallback(row)
    if rec["confidence"] not in _VALID_CONFIDENCE:
        return _template_fallback(row)
    return rec


# @spec EE-AI-009
def _template_fallback(row: pd.Series) -> dict:
    """Deterministic template payload used when FMA is unavailable.

    Recommendation:
      * "force-phantom" if any veto-capable test (PIN or spatial) result == fail
      * "evidence-too-thin" otherwise
    """
    tov = row.get("test_outcome_vector") or []
    veto_fail = any(
        o.get("test_name") in {"pin-reverse-lookup", "spatial-district-mismatch"}
        and o.get("result") == "fail"
        for o in tov
    )
    recommendation = "force-phantom" if veto_fail else "evidence-too-thin"
    fired_signals: list[str] = []
    rescue = row.get("rescue_applied")
    if isinstance(rescue, dict):
        fired_signals = [s.get("signal") for s in rescue.get("signals", [])
                         if s.get("signal")]
    reasoning_parts: list[str] = []
    if veto_fail:
        reasoning_parts.append("Veto-capable test failed.")
    if fired_signals:
        reasoning_parts.append("Layer A signals fired: " + ", ".join(sorted(fired_signals)))
    if not reasoning_parts:
        reasoning_parts.append("No corroborating signal; evidence is thin.")
    return {
        "recommendation": recommendation,
        "confidence": "low",
        "reasoning": " ".join(reasoning_parts),
        "cited_evidence_rows": [o.get("test_name") for o in tov if o.get("test_name")],
        "source": "template-fallback",
    }
