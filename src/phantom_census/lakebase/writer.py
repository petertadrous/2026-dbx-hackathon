"""Load EngineOutputs into Lakebase atomically per facility.

@spec LP-EE-001, LP-EE-002, LP-EE-003, LP-EE-004, LP-EE-005
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import Engine, text

if TYPE_CHECKING:
    from phantom_census.existence_engine.pipeline import EngineOutputs

from phantom_census.existence_engine.minhash import serialize_signature


@dataclass
class WriteStats:
    facilities: int
    test_rows: int
    verdict_rows: int
    signature_rows: int
    embedding_rows: int
    capability_rows: int = 0


def _jsonify(v: object) -> str | None:
    """Return JSON string for JSONB columns. None → None (NULL)."""
    if v is None:
        return None
    if hasattr(v, "tolist"):
        v = v.tolist()
    return json.dumps(v, default=str)


# @spec LP-EE-001, LP-EE-002, LP-EE-003, LP-EE-004, LP-EE-005
def load_engine_outputs(
    outputs: "EngineOutputs",
    engine: Engine,
    *,
    ran_at: datetime,
    facility_district_map: dict[str, str] | None = None,
) -> WriteStats:
    """Write existence-engine outputs to Lakebase in one transaction.

    LP-EE-005 atomicity: the entire batch commits or rolls back as one
    transaction (single SQLAlchemy ``engine.begin()`` block) — which trivially
    satisfies the per-facility atomicity contract since every row for every
    facility is in the same transaction.

    LP-EE-002 preservation: the verdict UPSERT writes only batch-owned
    columns. On a re-batch the columns ``ai_recommendation``,
    ``ai_recommendation_evidence_state``, and ``override_id`` are preserved
    unchanged from the prior row. The AI Evidence Layer's hash-mismatch path
    handles invalidation when subsequent test outcomes shift the cache key.
    """
    tests_df = outputs.facility_existence_tests
    verdicts_df = outputs.phantom_verdicts
    signatures = outputs.claim_minhash_signatures
    embeddings = getattr(outputs, "description_embeddings", {}) or {}
    snapshot_id = getattr(outputs, "snapshot_id", "") or ""

    test_facility_ids = set(tests_df["facility_id"])
    verdict_facility_ids = set(verdicts_df["facility_id"])
    if test_facility_ids != verdict_facility_ids:
        raise ValueError(
            "Engine outputs are inconsistent: every facility with test rows "
            "must have a verdict row and vice versa."
        )

    facility_district_map = facility_district_map or getattr(
        outputs, "facility_district_map", {}
    ) or {}

    facility_capabilities = getattr(outputs, "facility_capabilities", {}) or {}

    with engine.begin() as conn:
        _upsert_tests(conn, tests_df)
        _upsert_verdicts(conn, verdicts_df)
        _upsert_signatures(conn, signatures, ran_at)
        _upsert_embeddings(conn, embeddings, snapshot_id, ran_at)
        _upsert_xref(conn, facility_district_map)
        cap_rows = _replace_facility_capabilities(conn, facility_capabilities)

    return WriteStats(
        facilities=len(verdict_facility_ids),
        test_rows=len(tests_df),
        verdict_rows=len(verdicts_df),
        signature_rows=len(signatures),
        embedding_rows=len(embeddings),
        capability_rows=cap_rows,
    )


def _upsert_tests(conn, df: pd.DataFrame) -> None:
    """LP-SCHEMA-TEST-001: PK is (facility_id, test_name, ran_at). Layer B's
    override rows coexist with originals."""
    if df.empty:
        return
    rows = [
        {
            "facility_id": r["facility_id"],
            "test_name": r["test_name"],
            "result": r["result"],
            "evidence_ref": _jsonify(r.get("evidence_ref")),
            "ran_at": r["ran_at"],
        }
        for _, r in df.iterrows()
    ]
    conn.execute(
        text("""
            INSERT INTO operational.facility_existence_tests
                (facility_id, test_name, result, evidence_ref, ran_at)
            VALUES
                (:facility_id, :test_name, :result, CAST(:evidence_ref AS JSONB), :ran_at)
            ON CONFLICT (facility_id, test_name, ran_at)
            DO UPDATE SET
                result = EXCLUDED.result,
                evidence_ref = EXCLUDED.evidence_ref
        """),
        rows,
    )


# @spec LP-EE-002
def _upsert_verdicts(conn, df: pd.DataFrame) -> None:
    """Write only batch-owned columns; preserve AI cache + override_id on re-batch.

    Per LP-EE-002, the UPSERT writes:
      * adjudicator_verdict, verdict, reason, rescue_applied,
        test_outcome_vector, layer_c_synthesis, ran_at
    and on ON CONFLICT it updates only those — leaving:
      * ai_recommendation, ai_recommendation_evidence_state, override_id
    untouched. First INSERT sets the preserved columns to NULL via the
    DEFAULT-clause shape.
    """
    if df.empty:
        return
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "facility_id": r["facility_id"],
            "adjudicator_verdict": r.get("adjudicator_verdict") or r.get("verdict"),
            "verdict": r["verdict"],
            "reason": r.get("reason"),
            "rescue_applied": _jsonify(r.get("rescue_applied")),
            "test_outcome_vector": _jsonify(r.get("test_outcome_vector") or []),
            "layer_c_synthesis": _jsonify(r.get("layer_c_synthesis")),
            "ran_at": r["ran_at"],
        })
    conn.execute(
        text("""
            INSERT INTO operational.phantom_verdicts
                (facility_id, adjudicator_verdict, verdict, reason,
                 rescue_applied, test_outcome_vector, layer_c_synthesis,
                 ai_recommendation, ai_recommendation_evidence_state,
                 override_id, ran_at)
            VALUES
                (:facility_id, :adjudicator_verdict, :verdict, :reason,
                 CAST(:rescue_applied AS JSONB),
                 CAST(:test_outcome_vector AS JSONB),
                 CAST(:layer_c_synthesis AS JSONB),
                 NULL, NULL, NULL,
                 :ran_at)
            ON CONFLICT (facility_id)
            DO UPDATE SET
                adjudicator_verdict = EXCLUDED.adjudicator_verdict,
                verdict             = EXCLUDED.verdict,
                reason              = EXCLUDED.reason,
                rescue_applied      = EXCLUDED.rescue_applied,
                test_outcome_vector = EXCLUDED.test_outcome_vector,
                layer_c_synthesis   = EXCLUDED.layer_c_synthesis,
                ran_at              = EXCLUDED.ran_at
                -- ai_recommendation, ai_recommendation_evidence_state, and
                -- override_id are deliberately NOT in the SET list — LP-EE-002
                -- requires they survive re-batches unchanged.
        """),
        rows,
    )


def _upsert_signatures(conn, signatures: dict, ran_at: datetime) -> None:
    if not signatures:
        return
    rows = [
        {
            "facility_id": fid,
            "signature": serialize_signature(sig),
            "computed_at": ran_at,
        }
        for fid, sig in signatures.items()
    ]
    conn.execute(
        text("""
            INSERT INTO cache.claim_minhash (facility_id, signature, computed_at)
            VALUES (:facility_id, :signature, :computed_at)
            ON CONFLICT (facility_id)
            DO UPDATE SET signature = EXCLUDED.signature,
                          computed_at = EXCLUDED.computed_at
        """),
        rows,
    )


# @spec LP-EE-004
def _upsert_embeddings(
    conn, embeddings: dict, snapshot_id: str, computed_at: datetime,
) -> None:
    """LP-EE-004: one row per (facility_id, snapshot_id) with 384-dim BYTEA."""
    if not embeddings or not snapshot_id:
        return
    rows = [
        {
            "facility_id": fid,
            "snapshot_id": snapshot_id,
            "embedding": blob,
            "computed_at": computed_at,
        }
        for fid, blob in embeddings.items()
    ]
    conn.execute(
        text("""
            INSERT INTO cache.description_embeddings
                (facility_id, snapshot_id, embedding, computed_at)
            VALUES (:facility_id, :snapshot_id, :embedding, :computed_at)
            ON CONFLICT (facility_id, snapshot_id)
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          computed_at = EXCLUDED.computed_at
        """),
        rows,
    )


def _upsert_xref(conn, mapping: dict[str, str]) -> None:
    if not mapping:
        return
    rows = [{"facility_id": fid, "district_id": did} for fid, did in mapping.items()]
    conn.execute(
        text("""
            INSERT INTO operational.facility_district_xref (facility_id, district_id)
            VALUES (:facility_id, :district_id)
            ON CONFLICT (facility_id)
            DO UPDATE SET district_id = EXCLUDED.district_id
        """),
        rows,
    )


# DS-MULTICAP-001 cascade.
def _replace_facility_capabilities(
    conn, capabilities: dict[str, list[str]],
) -> int:
    """Mirror the engine's per-facility capability claims into Lakebase.

    Drop-and-replace per facility so a re-batch where a facility's capability
    set has changed (added/removed) leaves no stale rows that would mislead
    the desert-scoring recompute callback.
    """
    if not capabilities:
        return 0
    facility_ids = list(capabilities.keys())
    conn.execute(
        text(
            "DELETE FROM operational.facility_capabilities "
            "WHERE facility_id = ANY(:fids)"
        ),
        {"fids": facility_ids},
    )
    rows = [
        {"facility_id": fid, "capability": cap}
        for fid, caps in capabilities.items()
        for cap in (caps or [])
    ]
    if rows:
        conn.execute(
            text(
                "INSERT INTO operational.facility_capabilities "
                "(facility_id, capability) VALUES (:facility_id, :capability)"
            ),
            rows,
        )
    return len(rows)
