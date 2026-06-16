---
parent: high-level-design
prefix: LP
---

## Lakebase Persistence — EARS Specs

### Table Initialization

- [ ] **LP-INIT-001**: The system shall create all Lakebase tables listed in the schema section of lakebase-persistence-design.md before the batch pipeline runs.
- [ ] **LP-INIT-002**: The system shall enable CDC on `operational.phantom_verdicts` during table creation.
- [ ] **LP-INIT-003**: The system shall create a Delta mirror of `operational.facility_existence_tests` with Liquid Clustering on `facility_id` for analytical batch scans.
- [ ] **LP-INIT-004**: The system shall create a pgvector cosine index named `idx_description_embeddings_cosine` on the deserialized vector representation of `cache.description_embeddings.embedding` during table creation.
- [ ] **LP-INIT-005**: The system shall create `cache.claim_minhash` with primary key `facility_id` and `cache.description_embeddings` with composite primary key `(facility_id, snapshot_id)` before the batch pipeline runs.
- [ ] **LP-INIT-006**: The system shall create `team.budget_allocations` with composite primary key `(district_id, capability, quarter)` and shall load demo-time rows from a hand-curated CSV at project setup; rows in this table shall not be mutated by the Streamlit app at runtime.

### Schema — phantom_verdicts

- [ ] **LP-SCHEMA-VERDICT-001**: `operational.phantom_verdicts` shall include columns `facility_id` (PK), `adjudicator_verdict`, `verdict`, `rescue_applied` (JSONB, nullable), `test_outcome_vector` (JSONB), `ai_recommendation` (JSONB, nullable), `ai_recommendation_evidence_state` (VARCHAR(64), nullable), `override_id` (FK to `team.planner_overrides.override_id`, nullable), and `ran_at` (TIMESTAMP).
- [ ] **LP-SCHEMA-VERDICT-002**: The `adjudicator_verdict` column shall hold values from the enum `{phantom, real, contested}`. The `verdict` column shall hold values from the enum `{phantom, real, contested, force-real-planner, force-phantom-planner}`.
- [ ] **LP-SCHEMA-VERDICT-003**: The `rescue_applied` JSONB shape shall be `{signals: [<signal_name>], evidence_refs: [<row_id_or_url>]}` where `signal_name` is one of `{url-mentions, hfr-match, nfhs-named-staff}`; `rescue_applied` shall be null when no Layer A rescue fired.
- [ ] **LP-SCHEMA-VERDICT-004**: The `ai_recommendation` JSONB shape shall be `{recommendation, confidence, reasoning, cited_evidence_rows, source}` where `source ∈ {"fma", "template-fallback"}`; `ai_recommendation` shall be null until the AI Evidence Layer first writes for the facility.
- [ ] **LP-SCHEMA-VERDICT-005**: The `ai_recommendation_evidence_state` column shall be null whenever `ai_recommendation` is null, and shall be a sha256 hex string whenever `ai_recommendation` is non-null.
- [ ] **LP-SCHEMA-VERDICT-006**: The `override_id` column shall point to the most recent override row in `team.planner_overrides` for the given `facility_id`; on subsequent overrides, the column shall be updated in place to the new `override_id`, while older `team.planner_overrides` rows shall remain in place for audit.

### Schema — facility_existence_tests

- [ ] **LP-SCHEMA-TEST-001**: `operational.facility_existence_tests` shall use the composite primary key `(facility_id, test_name, ran_at)`.
- [ ] **LP-SCHEMA-TEST-002**: The `test_name` column shall hold values from the enum `{pin-lookup, minhash-duplicate, spatial-mismatch, nfhs-consistency, temporal-implausibility, embedding-drift, layer-b-override-pin, layer-b-override-spatial}`.
- [ ] **LP-SCHEMA-TEST-003**: The `result` column shall hold values from the enum `{pass, fail, indeterminate, not-applicable}`.
- [ ] **LP-SCHEMA-TEST-004**: When a Layer B override row exists for a `(facility_id, test_family)` where `test_family ∈ {pin, spatial}`, the original `pin-lookup` or `spatial-mismatch` row shall remain in the table and shall not be deleted or updated; the Adjudicator's input contract (per existence-engine LLD) determines which row is consumed.

### Schema — desert_scores

- [ ] **LP-SCHEMA-DESERT-001**: `operational.desert_scores` shall use the composite primary key `(district_id, capability)` where `district_id` is the geoBoundaries ADM2 `shapeID`.
- [ ] **LP-SCHEMA-DESERT-002**: A facility claiming multiple capabilities shall participate in one row per claimed capability, all sharing the same `district_id` resolved from the facility's spatial-join district.

### Schema — cache.description_embeddings

- [ ] **LP-SCHEMA-EMBED-001**: `cache.description_embeddings` shall use the composite primary key `(facility_id, snapshot_id)`; `snapshot_id` shall follow the format `YYYY-MM-DD-batch-NNN` and shall be present from the first snapshot.
- [ ] **LP-SCHEMA-EMBED-002**: The `embedding` column shall be BYTEA holding the serialized 384-dimensional float vector.
- [ ] **LP-SCHEMA-EMBED-003**: At Streamlit app start, the system shall load the most-recent-snapshot embeddings for all facilities into an in-process numpy array for sub-millisecond cosine similarity queries.

### Schema — team.budget_allocations

- [ ] **LP-SCHEMA-BUDGET-001**: `team.budget_allocations` shall use the composite primary key `(district_id, capability, quarter)` where `district_id` is a foreign key to `operational.desert_scores.district_id` (the geoBoundaries `shapeID`).
- [ ] **LP-SCHEMA-BUDGET-002**: The `team.budget_allocations` table shall be read-only from the Streamlit app's perspective; the recommended re-allocation computed by the Budget Reallocation view shall be exported to CSV and shall not be written back to this table.

### Writes from Existence Engine

- [ ] **LP-EE-001**: The existence engine batch shall write one row per `(facility_id, test_name)` to `operational.facility_existence_tests` for each test executed, including `result`, `evidence_ref` (JSONB), and `ran_at`.
- [ ] **LP-EE-002**: The existence engine batch shall UPSERT one row per `facility_id` to `operational.phantom_verdicts` writing only the batch-owned columns (`adjudicator_verdict`, `verdict`, `rescue_applied`, `test_outcome_vector`, `ran_at`); on a re-batch the columns `ai_recommendation`, `ai_recommendation_evidence_state`, and `override_id` shall be preserved unchanged from the prior row, and the AI Evidence Layer's hash-mismatch path (per existence-engine LLD) shall handle invalidation when subsequent test outcomes shift the cache key.
- [ ] **LP-EE-003**: The existence engine batch shall write one row per `facility_id` to `cache.claim_minhash` with the 128-permutation MinHash signature, overwriting any prior row.
- [ ] **LP-EE-004**: The existence engine batch shall write one row per `(facility_id, snapshot_id)` to `cache.description_embeddings` with the 384-dim sentence embedding as BYTEA.
- [ ] **LP-EE-005**: All existence engine writes for a single facility shall commit atomically per facility — either all rows for that facility commit together, or none do.

### Writes from Defender Layer A

- [ ] **LP-RESCUE-001**: When Layer A patches a verdict from `phantom` to `contested`, the system shall UPDATE `phantom_verdicts.verdict = "contested"` and `phantom_verdicts.rescue_applied = {signals, evidence_refs}` for the affected `facility_id`; `phantom_verdicts.adjudicator_verdict` shall remain unchanged.
- [ ] **LP-RESCUE-002**: Layer A shall not write rows to `operational.facility_existence_tests`; the rescue trace lives only in `phantom_verdicts.rescue_applied` JSONB.

### Writes from AI Evidence Layer

- [ ] **LP-AI-CACHE-001**: When the AI Evidence Layer computes a recommendation for a facility, the system shall UPDATE `phantom_verdicts.ai_recommendation` (JSONB) and `phantom_verdicts.ai_recommendation_evidence_state` (sha256 hex) for that `facility_id` in a single statement.
- [ ] **LP-AI-CACHE-002**: The `ai_recommendation_evidence_state` value persisted in LP-AI-CACHE-001 shall equal `sha256(canonical_json(test_outcome_vector) + adjudicator_verdict + canonical_json(rescue_applied or null))` computed at the time of the FMA invocation.
- [ ] **LP-AI-CACHE-003**: An AI Evidence Layer write that updates `ai_recommendation` and `ai_recommendation_evidence_state` shall not modify `verdict`, `adjudicator_verdict`, `rescue_applied`, `test_outcome_vector`, or `override_id`.
- [ ] **LP-AI-CACHE-004**: When two concurrent sessions write to `phantom_verdicts.ai_recommendation` for the same `facility_id`, the system shall use a plain UPDATE with last-write-wins semantics; no advisory lock or optimistic concurrency control shall be applied.
- [ ] **LP-AI-CACHE-005**: The AI Evidence Layer's persistence write shall be guarded by an `override_id IS NULL` predicate read within the same write transaction; if `override_id` was set between FMA invocation and write commit, the write shall be skipped (no UPDATE issued) so a planner override that races the FMA call wins.

### Reads from App

- [ ] **LP-APP-001**: The Streamlit app shall read `operational.desert_scores` for the selected capability on page load to populate the choropleth color data.
- [ ] **LP-APP-002**: When a planner clicks a district on the choropleth, the Streamlit app shall read `operational.phantom_verdicts` filtered to that district's facility IDs and shall return up to 5 facilities ranked by leverage (mortality_burden × population × phantom_density), reading `adjudicator_verdict`, `verdict`, `rescue_applied`, `ai_recommendation`, and `override_id` for each.
- [ ] **LP-APP-003**: When a planner expands a phantom facility's evidence row, the Streamlit app shall read `operational.facility_existence_tests` for that `facility_id` and return all test rows.
- [ ] **LP-APP-004**: At app start the Streamlit app shall query `SELECT DISTINCT capability FROM operational.desert_scores` to populate the capability dropdown; the result shall be cached in `st.session_state['available_capabilities']`.
- [ ] **LP-APP-005**: The Streamlit app shall connect to Lakebase via SQLAlchemy using credentials injected from Databricks App environment variables; no Lakebase credentials shall be hardcoded in the application source.
- [ ] **LP-APP-006**: Read queries from the Streamlit app shall use a read-only connection pool; write operations (overrides, scenario saves, AI Evidence Layer writes) shall use a write connection with explicit transaction management.

### Override Writes

- [ ] **LP-OVR-001**: When a planner submits an override, the Streamlit app shall INSERT a new row into `team.planner_overrides` with `facility_id`, `override_type ∈ {force-real, force-phantom}`, non-empty `reason_note`, `planner_id`, and `overridden_at`; this insert shall return the new `override_id`.
- [ ] **LP-OVR-002**: After LP-OVR-001 commits, the Streamlit app shall UPDATE `operational.phantom_verdicts` for the affected `facility_id`: set `verdict` to `force-real-planner` (when `override_type = force-real`) or `force-phantom-planner` (when `override_type = force-phantom`), and set `override_id` to the new override row's `override_id`.
- [ ] **LP-OVR-003**: The override write path shall preserve `phantom_verdicts.adjudicator_verdict`, `phantom_verdicts.rescue_applied`, `phantom_verdicts.ai_recommendation`, and `phantom_verdicts.ai_recommendation_evidence_state` unchanged when LP-OVR-002 executes.
- [ ] **LP-OVR-004**: After LP-OVR-002 commits, the Streamlit app shall fire the desert-score override-recompute callback (per desert-scoring LLD) which UPDATEs `operational.desert_scores` for every `(district_id, capability)` row the affected facility participates in.
- [ ] **LP-OVR-005**: If LP-OVR-001 or LP-OVR-002 fails, the system shall rollback the failed transaction and shall display an error message to the planner; LP-OVR-004 shall not fire when LP-OVR-001 or LP-OVR-002 has not committed.
- [ ] **LP-OVR-006**: `team.planner_overrides` is append-only — when the planner overrides the same `facility_id` more than once, each override INSERT shall create a new row; older override rows shall remain in the table; only `phantom_verdicts.override_id` shall be updated to point to the most recent row.

### Scenario Persistence

- [ ] **LP-SCEN-001**: When a planner saves a scenario, the Streamlit app shall INSERT a row to `team.saved_scenarios` with `scenario_name`, `capability`, `region_filter`, `override_set` (JSONB array of current session's `override_id` values), `planner_notes`, `planner_id`, and `saved_at`.
- [ ] **LP-SCEN-002**: On app load, the Streamlit app shall query `team.saved_scenarios` for the current `planner_id` and display matching scenarios ordered by `saved_at` descending.
- [ ] **LP-SCEN-003**: When a planner selects a saved scenario to restore, the Streamlit app shall read each `override_id` from `team.planner_overrides` and re-assert (not re-insert) the corresponding `verdict` and `override_id` values onto `operational.phantom_verdicts` for each affected `facility_id`, then recompute `operational.desert_scores` for the affected districts; if a row in `phantom_verdicts` already carries the correct `override_id`, the re-assert is a no-op for that row.
- [ ] **LP-SCEN-004**: The scenario restore operation (LP-SCEN-003) shall produce the same `operational.phantom_verdicts` state as the session had when the scenario was saved, assuming the underlying batch verdicts have not changed.
- [ ] **LP-SCEN-005**: A scenario restore shall not modify `phantom_verdicts.ai_recommendation` or `phantom_verdicts.ai_recommendation_evidence_state`; cached AI recommendations remain valid if their `evidence_state` still matches the post-restore `(test_outcome_vector, adjudicator_verdict, rescue_applied)` tuple, and the AI Evidence Layer's lookup logic governs render behavior.

### Platform Sync (Gold → Lakebase)

- [ ] **LP-SYNC-001**: The system shall write the following gold Delta tables to the Unity Catalog schema `workspace.phantom_census`: `facilities`, `phantom_verdicts`, `facility_existence_tests`, `desert_scores`, `description_embeddings`, `facility_capabilities`, `budget_allocations`. These are the synced-table sources.
- [ ] **LP-SYNC-002**: The system shall register a Lakebase-backed Unity Catalog catalog named `phantom_census_lakebase` whose `postgres_database` is `databricks_postgres` and whose `branch` is `projects/phantom-census/branches/production`.
- [ ] **LP-SYNC-003**: For each table in LP-SYNC-001 the system shall create a synced table at `phantom_census_lakebase.public.<table>` with `scheduling_policy = SNAPSHOT` and `primary_key_columns` matching the corresponding `operational.*` / `cache.*` / `team.*` schema primary key (e.g. `phantom_verdicts → [facility_id]`; `facility_existence_tests → [facility_id, test_name, ran_at]`; `desert_scores → [district_id, capability]`; `description_embeddings → [facility_id, snapshot_id]`; `facility_capabilities → [facility_id, capability]`; `budget_allocations → [district_id, capability, quarter]`).
- [ ] **LP-SYNC-004**: The synced tables shall not include `cache.tile_layers` (the table was cut per LP-INIT-004) nor `cache.claim_minhash` (the engine writes minhash signatures into Lakebase via `writer.py`, not via the synced-tables pipeline).
- [ ] **LP-SYNC-005**: After all synced tables reach the `ONLINE` state, the system shall grant the app service principal `USAGE` on `public`, `SELECT` on all tables in `public`, and `ALTER DEFAULT PRIVILEGES … GRANT SELECT … TO <SP_CLIENT_ID>` on `public` so subsequent sync refreshes are readable without re-granting.
- [ ] **LP-SYNC-006**: The platform-sync runbook shall be non-interactive — re-running the script shall be idempotent and shall not require human input between steps.
