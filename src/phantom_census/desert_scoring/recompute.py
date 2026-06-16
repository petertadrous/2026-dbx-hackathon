"""Single-district incremental recompute.

@spec DS-OVR-001, DS-OVR-002, DS-OVR-003, DS-OVR-004, DS-OVR-005, DS-OVR-006,
@spec DS-MULTICAP-001, DS-MULTICAP-002, DS-MULTICAP-003
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

    DS-OVR-005: `burden_imputed` and `nfhs_missing` are recomputed from
    the same NFHS frame used at batch time, so they carry through unchanged
    when the NFHS row hasn't moved.
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


def _lookup_facility_capabilities(
    conn: Connection, facility_id: str | None, default_capability: str,
) -> list[str]:
    """Return the capabilities a facility claims, per DS-MULTICAP-001.

    Reads `operational.facility_capabilities` populated by the LP engine writer.
    Falls back to `[default_capability]` when no facility_id is given or no
    capability rows exist for that facility (a defensive default that matches
    the workspace's actively-viewed capability).
    """
    if facility_id is None:
        return [default_capability]
    rows = conn.execute(
        text(
            "SELECT capability FROM operational.facility_capabilities "
            "WHERE facility_id = :fid ORDER BY capability"
        ),
        {"fid": facility_id},
    ).fetchall()
    caps = [r.capability for r in rows]
    return caps or [default_capability]


def _recompute_one_row(
    conn: Connection, *, district_id: str, capability: str, ran_at: datetime,
) -> None:
    """Update a single `(district_id, capability)` row in desert_scores.

    Preserves `burden_imputed`, `burden_weight`, `max_density`, `nfhs_missing`
    (DS-OVR-005) — they're per-district NFHS properties unaffected by
    count-driven mutations.
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

    # Count verified vs phantom across the district's facilities AND restrict
    # to facilities claiming this capability — multi-cap facilities only
    # count toward the capability rows they participate in.
    facilities = pd.DataFrame(
        conn.execute(
            text(
                "SELECT x.facility_id "
                "FROM operational.facility_district_xref x "
                "JOIN operational.facility_capabilities fc USING (facility_id) "
                "WHERE x.district_id = :did AND fc.capability = :cap"
            ),
            {"did": district_id, "cap": capability},
        ).mappings().all()
    )
    if facilities.empty:
        # No capability rows yet — fall back to counting every facility in the
        # district (the original single-capability batch behavior).
        facilities = pd.DataFrame(
            conn.execute(
                text(
                    "SELECT facility_id FROM operational.facility_district_xref "
                    "WHERE district_id = :did"
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

    # DS-OVR-005: burden_imputed, burden_weight, max_density, nfhs_missing
    # are deliberately omitted from the UPDATE.
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
            "ts": ran_at,
            "did": district_id,
            "cap": capability,
        },
    )


# @spec DS-OVR-001, DS-OVR-002, DS-OVR-005, DS-MULTICAP-001
def recompute_district(
    conn: Connection,
    district_id: str,
    capability: str,
    *,
    facility_id: str | None = None,
) -> list[str]:
    """Recompute every desert_scores row a facility participates in.

    Called by ``lakebase.overrides.submit_override`` as the ``recompute_fn``
    callback; runs on the caller's already-open Connection so the update
    participates in the same transaction as the override + verdict update
    (LP-OVR-005).

    When `facility_id` is supplied, the function reads
    ``operational.facility_capabilities`` to enumerate every capability the
    facility claims (DS-MULTICAP-001) and updates each
    ``(district_id, capability)`` row. `capability` is treated as the planner's
    currently-active view and is used as the fallback when the facility has no
    capability rows (defensive).

    DS-OVR-002: ``max_facility_count_per_km2`` is NOT recomputed — the existing
    `desert_scores.max_density` is read back and reused.
    """
    ran_at = datetime.now(tz=timezone.utc)
    capabilities = _lookup_facility_capabilities(
        conn, facility_id, default_capability=capability,
    )

    affected: list[str] = []
    for cap in capabilities:
        _recompute_one_row(
            conn, district_id=district_id, capability=cap, ran_at=ran_at,
        )
        affected.append(cap)
    return affected
