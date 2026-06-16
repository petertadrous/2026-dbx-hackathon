-- Phantom Census operational schema (Postgres dialect).
--
-- @spec LP-INIT-001, LP-INIT-002, LP-INIT-003, LP-INIT-004, LP-INIT-005, LP-INIT-006

CREATE SCHEMA IF NOT EXISTS operational;
CREATE SCHEMA IF NOT EXISTS cache;
CREATE SCHEMA IF NOT EXISTS team;

-- ─────────────────────────── operational ──────────────────────────────────

-- LP-SCHEMA-VERDICT-001..006: dual-verdict columns + Layer A rescue trace +
-- AI Evidence Layer cache columns + EE-cascade layer_c_synthesis.
CREATE TABLE IF NOT EXISTS operational.phantom_verdicts (
    facility_id                       VARCHAR(64)  PRIMARY KEY,
    adjudicator_verdict               VARCHAR(16)  NOT NULL,
    verdict                           VARCHAR(32)  NOT NULL,
    reason                            VARCHAR(64),
    rescue_applied                    JSONB,
    test_outcome_vector               JSONB        NOT NULL,
    layer_c_synthesis                 JSONB,
    ai_recommendation                 JSONB,
    ai_recommendation_evidence_state  VARCHAR(64),
    ran_at                            TIMESTAMPTZ  NOT NULL,
    override_id                       VARCHAR(64)
);

-- LP-SCHEMA-TEST-001: composite PK on (facility_id, test_name, ran_at) so a
-- re-batch preserves the prior batch's rows for audit and Layer B's override
-- rows coexist with the originals.
CREATE TABLE IF NOT EXISTS operational.facility_existence_tests (
    facility_id    VARCHAR(64)  NOT NULL,
    test_name      VARCHAR(64)  NOT NULL,
    result         VARCHAR(16)  NOT NULL,
    evidence_ref   JSONB,
    ran_at         TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (facility_id, test_name, ran_at)
);

CREATE INDEX IF NOT EXISTS facility_existence_tests_fid_idx
    ON operational.facility_existence_tests (facility_id);

-- The engine's spatial district assignment is published here so the side panel
-- can list phantoms per district without rejoining the ADM2 GeoDataFrame.
-- `district_id` is the geoBoundaries `shapeID` per EE-SPATIAL-001.
CREATE TABLE IF NOT EXISTS operational.facility_district_xref (
    facility_id  VARCHAR(64)  PRIMARY KEY,
    district_id  VARCHAR(64)  NOT NULL
);
CREATE INDEX IF NOT EXISTS facility_district_xref_district_idx
    ON operational.facility_district_xref (district_id);

-- DS-MULTICAP-001 cascade: the per-facility capability claims, populated by
-- the engine writer. The desert-scoring override-recompute callback reads from
-- this table to enumerate the (district_id, capability) rows a facility
-- participates in.
CREATE TABLE IF NOT EXISTS operational.facility_capabilities (
    facility_id  VARCHAR(64)  NOT NULL,
    capability   VARCHAR(64)  NOT NULL,
    PRIMARY KEY (facility_id, capability)
);
CREATE INDEX IF NOT EXISTS facility_capabilities_capability_idx
    ON operational.facility_capabilities (capability);

-- LP-SCHEMA-DESERT-001: composite PK (district_id, capability) where
-- district_id is the geoBoundaries ADM2 shapeID.
CREATE TABLE IF NOT EXISTS operational.desert_scores (
    district_id              VARCHAR(64) NOT NULL,
    district_name            VARCHAR(128) NOT NULL,
    state_name               VARCHAR(64) NOT NULL,
    capability               VARCHAR(64) NOT NULL,
    raw_desert_score         DOUBLE PRECISION NOT NULL,
    adjusted_desert_score    DOUBLE PRECISION NOT NULL,
    verified_facility_count  INTEGER NOT NULL,
    phantom_count            INTEGER NOT NULL,
    burden_imputed           BOOLEAN NOT NULL,
    nfhs_missing             BOOLEAN NOT NULL DEFAULT FALSE,
    burden_weight            DOUBLE PRECISION NOT NULL,
    max_density              DOUBLE PRECISION NOT NULL,
    updated_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (district_id, capability)
);

-- ────────────────────────────── cache ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS cache.claim_minhash (
    facility_id  VARCHAR(64) PRIMARY KEY,
    signature    BYTEA NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL
);

-- LP-SCHEMA-EMBED-001/002: (facility_id, snapshot_id) PK; 384-dim float vector
-- serialized as BYTEA. pgvector cosine index created best-effort by
-- migrate.py per LP-INIT-004.
CREATE TABLE IF NOT EXISTS cache.description_embeddings (
    facility_id   VARCHAR(64)  NOT NULL,
    snapshot_id   VARCHAR(32)  NOT NULL,
    embedding     BYTEA        NOT NULL,
    computed_at   TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (facility_id, snapshot_id)
);

-- ────────────────────────────── team ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS team.planner_overrides (
    override_id    VARCHAR(64) PRIMARY KEY,
    facility_id    VARCHAR(64) NOT NULL,
    override_type  VARCHAR(32) NOT NULL,
    reason_note    TEXT NOT NULL CHECK (length(reason_note) > 0),
    planner_id     VARCHAR(128) NOT NULL,
    overridden_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS planner_overrides_facility_idx
    ON team.planner_overrides (facility_id);

CREATE TABLE IF NOT EXISTS team.saved_scenarios (
    scenario_id     VARCHAR(64) PRIMARY KEY,
    scenario_name   VARCHAR(256) NOT NULL,
    capability      VARCHAR(64) NOT NULL,
    region_filter   VARCHAR(128),
    override_set    JSONB NOT NULL,
    planner_notes   TEXT,
    planner_id      VARCHAR(128) NOT NULL,
    saved_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS saved_scenarios_planner_idx
    ON team.saved_scenarios (planner_id);

-- LP-SCHEMA-BUDGET-001/002: hand-curated quarterly allocation; read-only from
-- the app's perspective during the demo.
CREATE TABLE IF NOT EXISTS team.budget_allocations (
    district_id     VARCHAR(64)  NOT NULL,
    state_name      VARCHAR(64)  NOT NULL,
    capability      VARCHAR(64)  NOT NULL,
    quarter         VARCHAR(16)  NOT NULL,
    allocated_inr   BIGINT       NOT NULL,
    loaded_at       TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (district_id, capability, quarter)
);
