"""Tests for PW-SHELL-004 — activation-gate badge."""
from __future__ import annotations

from phantom_census.planner_workspace.activation_gate import (
    PER_FMA_COST_USD,
    format_activation_gate_label,
)


# @spec PW-SHELL-004
def test_activation_gate_label_shape():
    label = format_activation_gate_label(contested_count=9)
    assert "Activation gate: 9 contested" in label
    assert "est. cost ≤" in label


# @spec PW-SHELL-004
def test_activation_gate_cost_two_decimals():
    label = format_activation_gate_label(contested_count=9)
    # 9 × 0.005 = 0.045 → formatted to two decimals → 0.05 (or 0.04 if truncated).
    expected = 9 * PER_FMA_COST_USD
    assert f"${expected:.2f}" in label
