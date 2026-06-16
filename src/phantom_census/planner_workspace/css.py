"""Inline CSS for the CSS-opacity-swap toggle (PW-MAP-004)."""
from __future__ import annotations

_BASE = """
<style>
.pc-tile-layer { transition: opacity 0.2s ease-in-out; }
.pc-tile-layer.hidden { display: none; }
.pc-counter { font-variant-numeric: tabular-nums; }
</style>
"""


def base_styles() -> str:
    return _BASE


def layer_visibility_block(active: str) -> str:
    """Return a `<style>` block that hides the inactive layer.

    `active` is one of {"raw", "adjusted"}.
    """
    hide = "adjusted" if active == "raw" else "raw"
    return (
        "<style>"
        f"#pc-layer-{hide} {{ display: none; }} "
        f"#pc-layer-{active} {{ display: block; }}"
        "</style>"
    )
