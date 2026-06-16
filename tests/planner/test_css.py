"""Tests for the CSS-opacity-swap toggle (PW-MAP-004)."""
from __future__ import annotations

from phantom_census.planner_workspace.css import (
    base_styles,
    layer_visibility_block,
)


# @spec PW-MAP-004
def test_layer_visibility_block_hides_inactive():
    style = layer_visibility_block("raw")
    assert "pc-layer-adjusted" in style
    assert "display: none" in style


# @spec PW-MAP-004
def test_layer_visibility_block_inverts():
    style = layer_visibility_block("adjusted")
    assert "pc-layer-raw" in style
    assert "display: none" in style


def test_base_styles_has_transition():
    assert ".pc-tile-layer" in base_styles()
