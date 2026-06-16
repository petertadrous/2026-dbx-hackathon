"""Disease-burden weights for the desert formula.

@spec DS-SCORE-004, DS-SCORE-005
"""
from __future__ import annotations

import pandas as pd

CAPABILITY_INDICATOR_COLUMN: dict[str, str] = {
    "maternity": "institutional_delivery_rate",
}


def _indicator_column_for(capability: str) -> str:
    if capability not in CAPABILITY_INDICATOR_COLUMN:
        raise ValueError(
            f"No NFHS indicator mapped for capability={capability!r}. "
            f"Edit CAPABILITY_INDICATOR_COLUMN to add support."
        )
    return CAPABILITY_INDICATOR_COLUMN[capability]


# @spec DS-SCORE-004, DS-SCORE-005
def burden_weight(
    nfhs_row: pd.Series,
    *,
    capability: str,
    state_medians: dict[str, float],
) -> tuple[float, bool]:
    """Return (weight, imputed). Weight is `1 - rate/100`.

    `*`-suppressed or NaN rates trigger imputation from the state median.
    """
    col = _indicator_column_for(capability)
    raw = nfhs_row.get(col)
    try:
        rate = float(raw)
        suppressed = False
    except (TypeError, ValueError):
        rate = float("nan")
        suppressed = True
    if pd.isna(rate) or suppressed or raw == "*":
        state = nfhs_row.get("state_name")
        median = state_medians.get(state)
        if median is None:
            return 0.0, True
        return 1.0 - median / 100.0, True
    return 1.0 - rate / 100.0, False


def state_medians_from_nfhs(nfhs_df: pd.DataFrame, *, capability: str) -> dict[str, float]:
    col = _indicator_column_for(capability)
    df = nfhs_df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce")
    return {
        state: float(group[col].dropna().median())
        for state, group in df.groupby("state_name")
        if not group[col].dropna().empty
    }
