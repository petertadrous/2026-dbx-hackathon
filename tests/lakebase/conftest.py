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


@pytest.fixture(scope="session")
def pg_url():
    env = os.environ.get("LAKEBASE_TEST_URL")
    if env:
        yield env
        return
    if not _can_use_docker():
        pytest.skip("LAKEBASE_TEST_URL unset and Docker daemon unreachable.")
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:16-alpine") as pg:
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


@pytest.fixture()
def sample_facility_tests() -> pd.DataFrame:
    ran_at = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for facility_id in ("F1", "F2"):
        for tn, res in [
            ("pin-reverse-lookup", "pass"),
            ("minhash-near-duplicate", "pass"),
            ("spatial-district-mismatch", "pass"),
            ("nfhs-outcome-inconsistency", "not-applicable"),
            ("temporal-implausibility", "pass"),
        ]:
            rows.append({
                "facility_id": facility_id,
                "test_name": tn,
                "result": res,
                "evidence_ref": {"d_km": 5.2} if res == "pass" else None,
                "ran_at": ran_at,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def sample_verdicts() -> pd.DataFrame:
    ran_at = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    return pd.DataFrame([
        {"facility_id": "F1", "verdict": "real",
         "reason": None,
         "test_outcome_vector": [{"test_name": "pin-reverse-lookup", "result": "pass"}],
         "ran_at": ran_at},
        {"facility_id": "F2", "verdict": "phantom",
         "reason": "veto-fail",
         "test_outcome_vector": [{"test_name": "spatial-district-mismatch", "result": "fail"}],
         "ran_at": ran_at},
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
def sample_engine_outputs(sample_facility_tests, sample_verdicts, sample_signatures):
    from phantom_census.existence_engine.pipeline import EngineOutputs
    return EngineOutputs(
        facility_existence_tests=sample_facility_tests,
        phantom_verdicts=sample_verdicts,
        claim_minhash_signatures=sample_signatures,
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
