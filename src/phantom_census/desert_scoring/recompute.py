"""Single-district incremental recompute.

@spec DS-OVR-001, DS-OVR-002, DS-OVR-003, DS-OVR-004
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Connection, text

from .formula import compute_district_scores


# @spec DS-OVR-001
def recompute_in_memory(
    *,
    previous_scores: pd.DataFrame,
    facilities_with_district: pd.DataFrame,
    verdicts: pd.DataFrame,
    nfhs: pd.DataFrame,
    capability: str,
    district_id: str,
    max_density: float | None = None,
) -> pd.DataFrame:
    """Pure-Python single-district recompute.

    Recomputes the full input slice using the shared `max_density` denominator,
    then patches only the affected row into `previous_scores`. Callers MUST
    supply the same `max_density` that was used to build `previous_scores`
    (otherwise the affected district's new score is no longer comparable to
    the untouched siblings).
    """
    fresh = compute_district_scores(
        facilities_with_district=facilities_with_district,
        verdicts=verdicts,
        nfhs=nfhs,
        capability=capability,
        max_density=max_density,
    )
    new_row = fresh[fresh["district_id"] == district_id]
    if new_row.empty:
        return previous_scores

    out = previous_scores.copy()
    mask = out["district_id"] == district_id
    if mask.any():
        for col in new_row.columns:
            if col in out.columns:
                out.loc[mask, col] = new_row.iloc[0][col]
    else:
        out = pd.concat([out, new_row], ignore_index=True)
    return out


# @spec DS-OVR-001, DS-OVR-003
def recompute_district(
    conn: Connection, district_id: str, capability: str
) -> None:
    """Recompute a single district's row in `operational.desert_scores`.

    Called by `lakebase.overrides.apply_override` as the `recompute_fn` callback;
    runs on the caller's already-open Connection so the update participates in
    the same transaction as the override + verdict update (LP-OVR-004).

    Reads the existing `desert_scores` row to recover `max_density` and
    `burden_weight` (persisted by the batch run) so the recomputed score stays
    comparable to the other rows in the table — no fake NFHS placeholders.
    """
    existing = conn.execute(
        text(
            "SELECT district_id, district_name, state_name, "
            "       burden_weight, burden_imputed, nfhs_missing, max_density "
            "FROM operational.desert_scores "
            "WHERE district_id = :did AND capability = :cap"
        ),
        {"did": district_id, "cap": capability},
    ).first()
    if existing is None:
        return

    facilities = pd.DataFrame(
        conn.execute(
            text(
                "SELECT x.facility_id, x.district_id "
                "FROM operational.facility_district_xref x "
                "WHERE x.district_id = :did"
            ),
            {"did": district_id},
        ).mappings().all()
    )
    if facilities.empty:
        return

    verdicts = pd.DataFrame(
        conn.execute(
            text(
                "SELECT facility_id, verdict "
                "FROM operational.phantom_verdicts "
                "WHERE facility_id = ANY(:fids)"
            ),
            {"fids": facilities["facility_id"].tolist()},
        ).mappings().all()
    )

    weight = float(existing.burden_weight)
    denom = float(existing.max_density) or 1.0
    verified = int((verdicts["verdict"] != "phantom").sum())
    phantom = int((verdicts["verdict"] == "phantom").sum())
    raw = max(0.0, min(1.0, (1.0 - verified / denom) * weight))
    adjusted = max(0.0, min(1.0,
                            (1.0 - (verified - phantom) / denom) * weight))

    conn.execute(
        text("""
            UPDATE operational.desert_scores
            SET raw_desert_score = :raw,
                adjusted_desert_score = :adj,
                verified_facility_count = :ver,
                phantom_count = :ph,
                updated_at = :ts
            WHERE district_id = :did AND capability = :cap
        """),
        {
            "raw": raw,
            "adj": adjusted,
            "ver": verified,
            "ph": phantom,
            "ts": datetime.now(tz=timezone.utc),
            "did": district_id,
            "cap": capability,
        },
    )
