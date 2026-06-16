"""Tests for DS-MULTICAP-001..003 — multi-capability override recompute (integration).

Per LP cascade (DS-Q2): the engine writer populates
`operational.facility_capabilities (facility_id, capability)`; the recompute
callback reads from that table to enumerate the capabilities the facility
participates in and updates every `(district_id, capability)` row.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from phantom_census.desert_scoring.recompute import recompute_district


def _seed_two_capabilities(engine, sample_engine_outputs, *, f2_caps: list[str]):
    """Seed phantom_verdicts + desert_scores + facility_capabilities + xref."""
    sample_engine_outputs.facility_capabilities = {"F2": f2_caps}
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        for cap, raw, adj in [("maternity", 0.6, 0.8), ("icu", 0.5, 0.7)]:
            conn.execute(text("""
                INSERT INTO operational.desert_scores
                (district_id, district_name, state_name, capability,
                 raw_desert_score, adjusted_desert_score,
                 verified_facility_count, phantom_count, burden_imputed,
                 nfhs_missing, burden_weight, max_density, updated_at)
                VALUES ('BEED', 'Beed', 'Maharashtra', :cap, :raw, :adj,
                        10, 2, FALSE, FALSE, 0.3, 0.002, NOW())
            """), {"cap": cap, "raw": raw, "adj": adj})
        conn.execute(text("""
            INSERT INTO operational.facility_district_xref (facility_id, district_id)
            VALUES ('F2', 'BEED')
        """))


# @spec DS-MULTICAP-001
def test_recompute_updates_every_capability_row_for_facility(
    engine, sample_engine_outputs,
):
    _seed_two_capabilities(engine, sample_engine_outputs,
                           f2_caps=["maternity", "icu"])
    with engine.begin() as conn:
        # Override flips F2 from phantom to real.
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET verdict = 'real'
            WHERE facility_id = 'F2'
        """))
        recompute_district(conn, district_id="BEED", capability="maternity",
                           facility_id="F2")

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT capability, phantom_count "
            "FROM operational.desert_scores WHERE district_id = 'BEED' "
            "ORDER BY capability"
        )).fetchall()
    by_cap = {r.capability: r.phantom_count for r in rows}
    assert by_cap["maternity"] == 0
    assert by_cap["icu"] == 0


# @spec DS-MULTICAP-001
def test_recompute_single_capability_facility_updates_only_one_row(
    engine, sample_engine_outputs,
):
    _seed_two_capabilities(engine, sample_engine_outputs,
                           f2_caps=["maternity"])
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET verdict = 'real'
            WHERE facility_id = 'F2'
        """))
        recompute_district(conn, district_id="BEED", capability="maternity",
                           facility_id="F2")

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT capability, phantom_count "
            "FROM operational.desert_scores WHERE district_id = 'BEED' "
            "ORDER BY capability"
        )).fetchall()
    by_cap = {r.capability: r.phantom_count for r in rows}
    assert by_cap["maternity"] == 0
    # ICU row untouched — F2 doesn't claim icu, so the recompute leaves the seed.
    assert by_cap["icu"] == 2


# @spec DS-OVR-006
def test_ai_cache_write_does_not_recompute_desert_scores(
    engine, sample_engine_outputs,
):
    """LP-AI-CACHE-003 + DS-OVR-006: persisting an ai_recommendation does not
    mutate desert_scores. The recompute_fn is never invoked from the AI write."""
    _seed_two_capabilities(engine, sample_engine_outputs,
                           f2_caps=["maternity"])
    with engine.begin() as conn:
        before = conn.execute(text(
            "SELECT phantom_count FROM operational.desert_scores "
            "WHERE district_id = 'BEED' AND capability = 'maternity'"
        )).scalar_one()

    from phantom_census.lakebase.ai_cache_writes import persist_ai_recommendation
    persist_ai_recommendation(
        engine, facility_id="F2",
        recommendation={
            "recommendation": "force-real", "confidence": "medium",
            "reasoning": "ok", "cited_evidence_rows": [], "source": "fma",
        },
        evidence_state="cafef00d" * 8,
    )

    with engine.begin() as conn:
        after = conn.execute(text(
            "SELECT phantom_count FROM operational.desert_scores "
            "WHERE district_id = 'BEED' AND capability = 'maternity'"
        )).scalar_one()
    assert before == after
