"""Defender Layer C — FMA corroboration synthesis (activation-gated).

Implements EE-LAYER-C-001..005.

Layer C fires only when the final `verdict` (after Layer A patching) is
`contested`. It calls the Foundation Model API (`ai_query`) to synthesize a
structured corroboration payload `{strength, supporting_rows, reasoning}`,
template-falling-back to a deterministic summary on FMA error. The payload is
stored in `phantom_verdicts.layer_c_synthesis` (JSONB) and feeds the AI
Evidence Layer's escalation package at planner-open time. Layer C never
mutates the `verdict` or `adjudicator_verdict` columns (EE-LAYER-C-005).
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from .types import Verdict


# @spec EE-LAYER-C-001, EE-LAYER-C-002, EE-LAYER-C-003, EE-LAYER-C-004,
# @spec EE-LAYER-C-005
def run_layer_c(
    verdicts: pd.DataFrame,
    facilities: pd.DataFrame,
    layer_b_results: pd.DataFrame,
    ai_query: Callable[..., dict],
) -> pd.DataFrame:
    """Synthesize corroboration payloads for contested facilities only.

    `ai_query` is the FMA invocation; callers can inject a mock or the
    Databricks `databricks-meta-llama-3-1-70b-instruct` adapter. On exception,
    Layer C emits a deterministic template payload (EE-LAYER-C-004).
    """
    out = verdicts.copy()
    if "layer_c_synthesis" not in out.columns:
        out["layer_c_synthesis"] = None
    fac_by_id = facilities.set_index("facility_id") if not facilities.empty else None

    for idx, row in out.iterrows():
        # EE-LAYER-C-001 — fire only on contested final verdict.
        if row["verdict"] != Verdict.CONTESTED.value:
            continue

        fac_id = row["facility_id"]
        fac_dict = {}
        if fac_by_id is not None and fac_id in fac_by_id.index:
            fac_dict = fac_by_id.loc[fac_id].to_dict()

        layer_b_match = None
        if not layer_b_results.empty and "facility_id" in layer_b_results.columns:
            sub = layer_b_results[layer_b_results["facility_id"] == fac_id]
            if not sub.empty:
                layer_b_match = sub.iloc[0].to_dict()

        payload = _invoke_or_fallback(
            ai_query=ai_query,
            facility=fac_dict,
            test_outcome_vector=row.get("test_outcome_vector") or [],
            rescue_applied=row.get("rescue_applied"),
            layer_b_result=layer_b_match,
        )
        out.at[idx, "layer_c_synthesis"] = payload

    return out


def _invoke_or_fallback(
    *,
    ai_query: Callable[..., dict],
    facility: dict,
    test_outcome_vector: list,
    rescue_applied: dict | None,
    layer_b_result: dict | None,
) -> dict:
    try:
        result = ai_query(
            facility=facility,
            test_outcome_vector=test_outcome_vector,
            rescue_applied=rescue_applied,
            layer_b_result=layer_b_result,
        )
    except Exception:  # noqa: BLE001 — EE-LAYER-C-004 covers all errors.
        return _template_fallback(test_outcome_vector, rescue_applied)

    if not isinstance(result, dict):
        return _template_fallback(test_outcome_vector, rescue_applied)

    strength = result.get("strength")
    if strength not in {"weak", "medium", "strong"}:
        return _template_fallback(test_outcome_vector, rescue_applied)
    return {
        "strength": strength,
        "supporting_rows": list(result.get("supporting_rows") or []),
        "reasoning": str(result.get("reasoning") or ""),
        "source": "fma",
    }


# @spec EE-LAYER-C-004
def _template_fallback(
    test_outcome_vector: list, rescue_applied: dict | None,
) -> dict:
    """Deterministic summary used when FMA is unavailable."""
    all_rows = [o.get("test_name") for o in (test_outcome_vector or [])
                if o.get("test_name")]
    signals_fired = []
    if isinstance(rescue_applied, dict):
        signals_fired = [s.get("signal") for s in rescue_applied.get("signals", [])
                         if s.get("signal")]
    reasoning_parts = []
    if signals_fired:
        reasoning_parts.append(
            "Layer A signals fired: " + ", ".join(sorted(signals_fired))
        )
    failing = [o.get("test_name") for o in (test_outcome_vector or [])
               if o.get("result") == "fail"]
    if failing:
        reasoning_parts.append("Failing tests: " + ", ".join(sorted(failing)))
    if not reasoning_parts:
        reasoning_parts.append("No specific signals; insufficient corroboration.")
    return {
        "strength": "weak",
        "supporting_rows": all_rows,
        "reasoning": " | ".join(reasoning_parts),
        "source": "template-fallback",
    }
