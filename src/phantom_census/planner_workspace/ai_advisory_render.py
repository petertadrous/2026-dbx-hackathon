"""AI Advisory block render-decision logic.

@spec PW-AI-001, PW-AI-002, PW-AI-003, PW-AI-004, PW-AI-005

This is a thin wrapper around `existence_engine.ai_evidence_layer.maybe_render`
that adds PW-side render flags (`template_fallback`, `historical-advisory`
mark) so the Streamlit view can branch on a single dict instead of inspecting
the raw payload.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from phantom_census.existence_engine.ai_evidence_layer import (
    HISTORICAL_ADVISORY,
    maybe_render,
)


# @spec PW-AI-001, PW-AI-002, PW-AI-003, PW-AI-004, PW-AI-005
def decide_advisory_render(
    row: pd.Series, *, ai_query: Callable[..., dict],
) -> dict | None:
    """Return the render decision for a side-panel facility row.

    Returns:
        None — render nothing (PW-AI-004 / PW-AI-005).
        dict — render the AI Advisory block with shape:
            {
              "mark": "historical-advisory" | "live",
              "payload": <ai_recommendation dict>,
              "template_fallback": bool,
              "persist": <dict|None>,   # passed through from maybe_render
            }
    """
    rendered = maybe_render(row, ai_query=ai_query)
    if rendered is None:
        return None

    payload = rendered.get("payload") or {}
    template_fallback = payload.get("source") == "template-fallback"

    return {
        "mark": rendered.get("mark"),
        "payload": payload,
        "template_fallback": template_fallback,
        "persist": rendered.get("persist"),
    }


def is_historical_advisory(rendered: dict) -> bool:
    return rendered.get("mark") == HISTORICAL_ADVISORY
