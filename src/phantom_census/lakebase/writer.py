"""Load EngineOutputs into Lakebase atomically per facility.

@spec LP-EE-001, LP-EE-002, LP-EE-003, LP-EE-004
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


# @spec LP-EE-001, LP-EE-002, LP-EE-003, LP-EE-004
def load_engine_outputs(
    outputs: "EngineOutputs",
    engine: Engine,
    *,
    ran_at: datetime,
    facility_district_map: dict[str, str] | None = None,
) -> WriteStats:
    """Write existence-engine outputs to Lakebase in one transaction.

    LP-EE-004 atomicity is enforced by wrapping all per-facility writes in a
    single SQLAlchemy ``engine.begin()`` block — any error rolls back the
    entire batch.

    `facility_district_map` populates operational.facility_district_xref so
    LP-APP-002 (district → phantoms) and LP-OVR-003 (district affected by
    override) can resolve without rejoining the spatial layer at request time.
    """
    tests_df = outputs.facility_existence_tests
    verdicts_df = outputs.phantom_verdicts
    signatures = outputs.claim_minhash_signatures

    test_facility_ids = set(tests_df["facility_id"])
    verdict_facility_ids = set(verdicts_df["facility_id"])
    if test_facility_ids != verdict_facility_ids:
        raise ValueError(
            "Engine outputs are inconsistent: every facility with test rows "
            "must have a verdict row and vice versa."
        )

    facility_district_map = facility_district_map or {}

    with engine.begin() as conn:
        _upsert_tests(conn, tests_df)
        _upsert_verdicts(conn, verdicts_df)
        _upsert_signatures(conn, signatures, ran_at)
        _upsert_xref(conn, facility_district_map)

    return WriteStats(
        facilities=len(verdict_facility_ids),
        test_rows=len(tests_df),
        verdict_rows=len(verdicts_df),
        signature_rows=len(signatures),
    )


def _strip_nul(s: str | None) -> str | None:
    return s.replace("\x00", "") if isinstance(s, str) else s


def _upsert_tests(conn, df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows = [
        {
            "facility_id": _strip_nul(r["facility_id"]),
            "test_name": _strip_nul(r["test_name"]),
            "result": _strip_nul(r["result"]),
            "evidence_ref": json.dumps(r["evidence_ref"]) if r.get("evidence_ref") is not None else None,
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
            ON CONFLICT (facility_id, test_name)
            DO UPDATE SET
                result = EXCLUDED.result,
                evidence_ref = EXCLUDED.evidence_ref,
                ran_at = EXCLUDED.ran_at
        """),
        rows,
    )


def _upsert_verdicts(conn, df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows = []
    for _, r in df.iterrows():
        tov = r["test_outcome_vector"]
        if hasattr(tov, "tolist"):
            tov = tov.tolist()
        rows.append({
            "facility_id": _strip_nul(r["facility_id"]),
            "verdict": _strip_nul(r["verdict"]),
            "reason": _strip_nul(r.get("reason")),
            "test_outcome_vector": json.dumps(tov, default=str),
            "ran_at": r["ran_at"],
        })
    conn.execute(
        text("""
            INSERT INTO operational.phantom_verdicts
                (facility_id, verdict, reason, test_outcome_vector, ran_at, override_id)
            VALUES
                (:facility_id, :verdict, :reason, CAST(:test_outcome_vector AS JSONB),
                 :ran_at, NULL)
            ON CONFLICT (facility_id)
            DO UPDATE SET
                verdict = EXCLUDED.verdict,
                reason = EXCLUDED.reason,
                test_outcome_vector = EXCLUDED.test_outcome_vector,
                ran_at = EXCLUDED.ran_at,
                override_id = NULL
        """),
        rows,
    )


def _upsert_signatures(conn, signatures: dict, ran_at: datetime) -> None:
    if not signatures:
        return
    rows = [
        {
            "facility_id": _strip_nul(fid),
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


def _upsert_xref(conn, mapping: dict[str, str]) -> None:
    if not mapping:
        return
    rows = [{"facility_id": _strip_nul(fid), "district_id": _strip_nul(did)} for fid, did in mapping.items()]
    conn.execute(
        text("""
            INSERT INTO operational.facility_district_xref (facility_id, district_id)
            VALUES (:facility_id, :district_id)
            ON CONFLICT (facility_id)
            DO UPDATE SET district_id = EXCLUDED.district_id
        """),
        rows,
    )
