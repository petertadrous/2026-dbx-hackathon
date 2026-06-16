"""Desert score formula.

@spec DS-SCORE-001, DS-SCORE-002, DS-SCORE-003, DS-SCORE-004, DS-SCORE-005
"""
from __future__ import annotations

import logging

import pandas as pd

from .burden import burden_weight, state_medians_from_nfhs

log = logging.getLogger(__name__)


# @spec DS-SCORE-001, DS-SCORE-002, DS-SCORE-003, DS-SCORE-004, DS-SCORE-005
def compute_district_scores(
    *,
    facilities_with_district: pd.DataFrame,
    verdicts: pd.DataFrame,
    nfhs: pd.DataFrame,
    capability: str,
    max_density: float | None = None,
) -> pd.DataFrame:
    """Compute per-district raw + phantom-adjusted desert scores.

    `max_density` is the global normalization denominator (max verified-facility
    count observed in the full slice). When None, it's derived from the supplied
    facilities frame; for single-district recomputes pass the value persisted
    on `operational.desert_scores.max_density` so the recomputed row remains
    comparable to the rest of the table.
    """
    fac_verdict = facilities_with_district.merge(
        verdicts[["facility_id", "verdict"]], on="facility_id", how="left"
    )

    counts = (
        fac_verdict.groupby("district_id")
        .agg(
            verified_facility_count=("verdict",
                                     lambda s: (s != "phantom").sum()),
            phantom_count=("verdict", lambda s: (s == "phantom").sum()),
        )
        .reset_index()
    )

    denom = max_density or max(counts["verified_facility_count"].max(), 1)

    state_medians = state_medians_from_nfhs(nfhs, capability=capability)
    nfhs_indexed = nfhs.set_index("district_id") if "district_id" in nfhs.columns else nfhs.iloc[0:0]

    rows = []
    for _, row in counts.iterrows():
        district_id = row["district_id"]
        if district_id in nfhs_indexed.index:
            nfhs_row = nfhs_indexed.loc[district_id]
            nfhs_missing = False
        else:
            nfhs_row = pd.Series(dtype=object)
            nfhs_missing = True
            log.warning(
                "DS-SCORE-005: district %r has no NFHS row; scoring with "
                "0.0 weight and flagging nfhs_missing=True.", district_id
            )
        weight, imputed = burden_weight(nfhs_row, capability=capability,
                                        state_medians=state_medians)
        verified = int(row["verified_facility_count"])
        phantom = int(row["phantom_count"])
        raw = max(0.0, min(1.0, (1.0 - verified / denom) * weight))
        adjusted = max(0.0, min(1.0,
                                (1.0 - (verified - phantom) / denom) * weight))
        rows.append({
            "district_id": district_id,
            "district_name": nfhs_row.get("district_name", district_id),
            "state_name": nfhs_row.get("state_name", "Unknown"),
            "capability": capability,
            "raw_desert_score": raw,
            "adjusted_desert_score": adjusted,
            "verified_facility_count": verified,
            "phantom_count": phantom,
            "burden_imputed": bool(imputed),
            "nfhs_missing": bool(nfhs_missing),
            "burden_weight": float(weight),
            "max_density": float(denom),
        })
    return pd.DataFrame(rows)
