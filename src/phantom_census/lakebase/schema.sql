-- Phantom Census operational schema (Postgres dialect).
--
-- @spec LP-INIT-001, LP-INIT-002, LP-INIT-003, LP-INIT-004

CREATE SCHEMA IF NOT EXISTS operational;
CREATE SCHEMA IF NOT EXISTS cache;
CREATE SCHEMA IF NOT EXISTS team;

-- ─────────────────────────── operational ──────────────────────────────────

CREATE TABLE IF NOT EXISTS operational.phantom_verdicts (
    facility_id          VARCHAR(64)  PRIMARY KEY,
    verdict              VARCHAR(16)  NOT NULL,
    reason               VARCHAR(64),
    test_outcome_vector  JSONB        NOT NULL,
    ran_at               TIMESTAMPTZ  NOT NULL,
    override_id          VARCHAR(64)
);

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

-- LP-Phase-2 addendum: the engine's spatial district assignment is published
-- here so the side panel can list phantoms per district without rejoining the
-- ADM2 GeoDataFrame in the request path. Written by the engine writer.
CREATE TABLE IF NOT EXISTS operational.facility_district_xref (
    facility_id  VARCHAR(64)  PRIMARY KEY,
    district_id  VARCHAR(64)  NOT NULL
);
CREATE INDEX IF NOT EXISTS facility_district_xref_district_idx
    ON operational.facility_district_xref (district_id);

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
    updated_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (district_id, capability)
);

-- ────────────────────────────── cache ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS cache.claim_minhash (
    facility_id  VARCHAR(64) PRIMARY KEY,
    signature    BYTEA NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS cache.tile_layers (
    capability   VARCHAR(64) NOT NULL,
    layer_type   VARCHAR(16) NOT NULL,
    html         TEXT NOT NULL,
    rendered_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (capability, layer_type)
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
