"""Shared fixtures for the lakebase-persistence test suite.

Connection strategy:
  1. If the env var LAKEBASE_TEST_URL is set, use it as the test Postgres DSN.
  2. Else, spin up an ephemeral container via testcontainers[postgres]
     (requires Docker daemon running).
  3. Else (Docker unavailable AND no env var), skip the entire suite.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from datasketch import MinHash
from sqlalchemy import Engine, create_engine, text


def _can_use_docker() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _container_image() -> str:
    """Pick the Postgres image for the integration test container.

    When `TESTCONTAINERS_PGVECTOR=1`, use the `pgvector/pgvector:pg16` image
    so LP-INIT-004's cosine index creation can be exercised end-to-end. The
    default `postgres:16-alpine` is lighter (~50MB vs ~250MB) and matches the
    `_create_pgvector_index_best_effort` fallback path.
    """
    if os.environ.get("TESTCONTAINERS_PGVECTOR") == "1":
        return "pgvector/pgvector:pg16"
    return "postgres:16-alpine"


@pytest.fixture(scope="session")
def pg_url():
    env = os.environ.get("LAKEBASE_TEST_URL")
    if env:
        yield env
        return
    if not _can_use_docker():
        pytest.skip("LAKEBASE_TEST_URL unset and Docker daemon unreachable.")
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer(_container_image()) as pg:
        yield pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")


@pytest.fixture(scope="session")
def shared_engine(pg_url):
    eng = create_engine(pg_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def engine(shared_engine, request):
    """Per-test engine that drops + recreates schemas for isolation."""
    from phantom_census.lakebase.migrate import init_schema

    with shared_engine.begin() as conn:
        for sch in ("operational", "cache", "team"):
            conn.execute(text(f'DROP SCHEMA IF EXISTS {sch} CASCADE'))
    init_schema(shared_engine)
    return shared_engine


_RAN_AT = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_SNAPSHOT_ID = "2026-06-15-batch-001"


def _six_test_rows(facility_id: str, results: dict[str, str]) -> list[dict]:
    rows = []
    for tn in (
        "pin-reverse-lookup", "minhash-near-duplicate",
        "spatial-district-mismatch", "nfhs-outcome-inconsistency",
        "temporal-implausibility", "embedding-drift",
    ):
        res = results.get(tn, "pass")
        rows.append({
            "facility_id": facility_id,
            "test_name": tn,
            "result": res,
            "evidence_ref": {"d_km": 5.2} if res == "pass" else None,
            "ran_at": _RAN_AT,
        })
    return rows


@pytest.fixture()
def sample_facility_tests() -> pd.DataFrame:
    rows = (
        _six_test_rows("F1", {})
        + _six_test_rows("F2", {
            "nfhs-outcome-inconsistency": "not-applicable",
            "spatial-district-mismatch": "fail",
            "embedding-drift": "indeterminate",
        })
    )
    return pd.DataFrame(rows)


@pytest.fixture()
def sample_verdicts() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "facility_id": "F1",
            "adjudicator_verdict": "real",
            "verdict": "real",
            "reason": None,
            "rescue_applied": None,
            "test_outcome_vector": [
                {"test_name": "pin-reverse-lookup", "result": "pass"},
                {"test_name": "minhash-near-duplicate", "result": "pass"},
                {"test_name": "spatial-district-mismatch", "result": "pass"},
                {"test_name": "nfhs-outcome-inconsistency", "result": "not-applicable"},
                {"test_name": "temporal-implausibility", "result": "pass"},
                {"test_name": "embedding-drift", "result": "indeterminate"},
            ],
            "layer_c_synthesis": None,
            "ran_at": _RAN_AT,
        },
        {
            "facility_id": "F2",
            "adjudicator_verdict": "phantom",
            "verdict": "phantom",
            "reason": "veto-fail",
            "rescue_applied": None,
            "test_outcome_vector": [
                {"test_name": "spatial-district-mismatch", "result": "fail"},
            ],
            "layer_c_synthesis": None,
            "ran_at": _RAN_AT,
        },
    ])


@pytest.fixture()
def sample_signatures() -> dict[str, MinHash]:
    out: dict[str, MinHash] = {}
    for fid, seed in [("F1", "alpha"), ("F2", "beta")]:
        m = MinHash(num_perm=128)
        for tok in (seed, "ward", "icu", "trauma", "delivery"):
            m.update(tok.encode())
        out[fid] = m
    return out


@pytest.fixture()
def sample_embeddings() -> dict[str, bytes]:
    """Deterministic 384-dim BYTEA per facility, matching EE-EMBED-001."""
    out: dict[str, bytes] = {}
    for fid, seed in (("F1", 11), ("F2", 17)):
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(384).astype(np.float32)
        v = v / np.linalg.norm(v)
        out[fid] = v.tobytes()
    return out


@pytest.fixture()
def sample_engine_outputs(
    sample_facility_tests, sample_verdicts, sample_signatures, sample_embeddings,
):
    from phantom_census.existence_engine.pipeline import EngineOutputs
    return EngineOutputs(
        facility_existence_tests=sample_facility_tests,
        phantom_verdicts=sample_verdicts,
        claim_minhash_signatures=sample_signatures,
        description_embeddings=sample_embeddings,
        facility_district_map={},
        snapshot_id=_SNAPSHOT_ID,
    )


@pytest.fixture()
def maharashtra_districts(engine):
    """Seed `operational.desert_scores` with two MH districts for app-reader tests."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operational.desert_scores
            (district_id, district_name, state_name, capability,
             raw_desert_score, adjusted_desert_score,
             verified_facility_count, phantom_count, burden_imputed,
             nfhs_missing, burden_weight, max_density, updated_at)
            VALUES
            ('BEED', 'Beed', 'Maharashtra', 'maternity', 0.60, 0.78, 12, 4,
             FALSE, FALSE, 0.3, 80, NOW()),
            ('MUM',  'Mumbai', 'Maharashtra', 'maternity', 0.30, 0.32, 80, 2,
             FALSE, FALSE, 0.05, 80, NOW())
        """))
    yield engine


@pytest.fixture()
def fresh_planner_id() -> str:
    return f"planner-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def snapshot_id() -> str:
    return _SNAPSHOT_ID
