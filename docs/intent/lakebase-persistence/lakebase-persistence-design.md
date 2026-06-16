---
parent: high-level-design
prefix: LP
---

# Lakebase Persistence

## Context and Design Philosophy

Lakebase is the operational spine of Phantom Census. It holds all mutable state: phantom verdicts, AI recommendations, planner overrides, planner budget allocations, saved scenarios, desert scores, MinHash cache, and the description-embedding cache that powers Test 6. The batch pipeline writes to it; the Streamlit app reads and writes to it live; the AI Evidence Layer reads-and-writes the `ai_recommendation` column lazily on planner-open.

Lakebase is chosen over Delta-only because per-district override-triggered recomputes require sub-second mutable OLTP writes. Delta's merge semantics are too slow for live demo feedback. Lakebase's Postgres-compatible wire protocol enables a straightforward SQLAlchemy connection from the Streamlit app, and the pgvector extension on `cache.description_embeddings` powers the cosine-drift query Test 6 issues at app start.

The schema deliberately co-locates each verdict's full state — Adjudicator output, Defender rescue trace, AI recommendation, planner override — on a single `phantom_verdicts` row. The side panel renders from one read; the audit trail is uniform; the cache key for the AI recommendation is computable from columns already on the row.

## Schema

### `operational.phantom_verdicts`

The central verdict row for each facility. Co-locates the deterministic Adjudicator output, the Defender Layer A rescue trace, the AI Evidence Layer recommendation, and the planner override, so the side-panel render is a single read.

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR PK | Matches VF dataset `facility_id` |
| `adjudicator_verdict` | VARCHAR | The deterministic Adjudicator's output: `phantom` \| `real` \| `contested`. Never mutated by Defender Layer A or planner overrides. |
| `verdict` | VARCHAR | The final, mutable verdict: `phantom` \| `real` \| `contested` \| `force-real-planner` \| `force-phantom-planner`. Equal to `adjudicator_verdict` when no rescue and no override; mutated by Layer A rescue (`phantom → contested`) and by planner overrides. |
| `rescue_applied` | JSONB | Layer A rescue trace; null if no rescue fired. Shape: `{signals: [<signal_name>], evidence_refs: [<row_id or url>]}`. `signal_name` enum: `url-mentions` (≥2 distinct non-self-published URLs in description), `hfr-match` (HFR pre-cached snapshot match), `nfhs-named-staff` (named staff overlap with NFHS-5 district denominator data). One or more signals may fire on a single rescue. |
| `test_outcome_vector` | JSONB | All 6 test results + their `evidence_ref` values, snapshot at Adjudicator-run time. |
| `ai_recommendation` | JSONB | AI Evidence Layer output. Null until first planner-open of a contested facility; populated lazily. Shape: `{recommendation, confidence, reasoning, cited_evidence_rows, source}` where `source` is `"fma"` or `"template-fallback"`. |
| `ai_recommendation_evidence_state` | VARCHAR(64) | sha256 hex of the cache key under which `ai_recommendation` was generated. Computed as `sha256(canonical_json(test_outcome_vector) + adjudicator_verdict + canonical_json(rescue_applied or null))`. Null when `ai_recommendation` is null. |
| `override_id` | VARCHAR FK | NULL until the planner overrides; FK to `team.planner_overrides`. Stores the **most recent** override row's `override_id` for this `facility_id`. When the planner overrides, then changes their mind and overrides again, this column is updated to point to the new row; older rows remain in `team.planner_overrides` for audit. Once non-null, the AI Evidence Layer's lookup gate skips FMA on subsequent opens. |
| `ran_at` | TIMESTAMP | Batch run timestamp |

CDC enabled on this table — changes trigger the desert-score recompute callback (which is a Streamlit callback, not a CDC subscription, but the CDC log is preserved for audit and re-batch verification).

**Verdict mutation paths (in order of precedence):**
1. Batch run sets `adjudicator_verdict` and (if no Layer A rescue) `verdict` to the same value. **Re-batch UPSERTs only the batch-owned columns** (`adjudicator_verdict`, `verdict`, `rescue_applied`, `test_outcome_vector`, `ran_at`); `ai_recommendation`, `ai_recommendation_evidence_state`, and `override_id` are preserved across batch runs. The AI Evidence Layer's hash-mismatch path handles invalidation when a re-batch shifts the test outcome vector — stale recommendations are recomputed lazily on next planner-open, not eagerly cleared.
2. Defender Layer A may patch `verdict` from `phantom` to `contested`, populating `rescue_applied`.
3. AI Evidence Layer populates `ai_recommendation` + `ai_recommendation_evidence_state` on planner-open of a contested facility. Does not change `verdict`. The persistence write is guarded by an `override_id IS NULL` re-read in the same transaction — a recommendation arriving after a planner overrode is discarded, not persisted.
4. Planner override sets `verdict` to `force-real-planner` or `force-phantom-planner` and populates `override_id`. `adjudicator_verdict` and `rescue_applied` are preserved unchanged for audit.

### `operational.facility_existence_tests`

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR | |
| `test_name` | VARCHAR | One of: `pin-lookup`, `minhash-duplicate`, `spatial-mismatch`, `nfhs-consistency`, `temporal-implausibility`, `embedding-drift`, `layer-b-override-pin`, `layer-b-override-spatial` |
| `result` | VARCHAR | `pass` \| `fail` \| `indeterminate` \| `not-applicable` |
| `evidence_ref` | JSONB | Source row(s) driving the result |
| `ran_at` | TIMESTAMP | |

Composite PK on `(facility_id, test_name, ran_at)`. Liquid-clustered on `facility_id` in the Delta mirror for analytical scans.

**Test 6 (`embedding-drift`)** is one of the six core tests. Its `evidence_ref` carries `{prior_snapshot_id, current_snapshot_id, cosine_drift, threshold}`.

**Layer B override rows (`layer-b-override-pin` / `layer-b-override-spatial`)** are written before the Adjudicator runs. Per the existence-engine LLD's Adjudicator input contract, when an override row exists for a `(facility_id, test_family)`, it supersedes the original `pin-lookup` or `spatial-mismatch` row. The Adjudicator consumes the corrected outcome; both rows are preserved for audit. `evidence_ref` cites the specific reorganization or spelling variant matched (e.g., `{reorg: "Bapatla→Prakasam", source: "post-2022-district-table"}`).

**Layer A rescues do NOT write rows here.** Layer A's rescue trace lives in `phantom_verdicts.rescue_applied` (JSONB). This is a deliberate asymmetry — Layer B *corrects test inputs* (a per-test mutation, naturally a row), while Layer A *adds outside corroboration that doesn't change tests* (a per-verdict mutation, naturally a column). See existence-engine LLD § Defender for the rationale.

### `operational.desert_scores`

| Column | Type | Notes |
|---|---|---|
| `district_id` | VARCHAR | Normalized district key. **Source of truth: the geoBoundaries ADM2 shapefile's `shapeID` column** (e.g., `IND-ADM2-3344892981B92345567`). The same `shapeID` is used as the join key throughout the pipeline — point-in-polygon spatial join in the Existence Engine writes it onto `vf_facilities`; `desert_scores` aggregates over it; the Planner Workspace's `GeoJsonLayer` reads it from the same shapefile. NFHS-5 district names and PIN-derived district names are mapped to `shapeID` via a one-time normalization table built from the spatial join, never used as join keys themselves. |
| `district_name` | VARCHAR | |
| `state_name` | VARCHAR | |
| `capability` | VARCHAR | e.g. `maternity`, `icu` |
| `raw_desert_score` | FLOAT | 0–1 |
| `adjusted_desert_score` | FLOAT | 0–1 |
| `verified_facility_count` | INT | |
| `phantom_count` | INT | |
| `burden_imputed` | BOOLEAN | True if NFHS indicator was imputed from state median |
| `updated_at` | TIMESTAMP | |

Composite PK on `(district_id, capability)`. A facility claiming multiple capabilities (e.g., maternity + ICU) participates in multiple rows — see desert-scoring LLD § Multi-capability facilities for the override-recompute contract.

Updated by the batch pipeline and by the single-district override-recompute callback.

### `cache.claim_minhash`

128-permutation MinHash signatures computed on concatenated `capability` + `procedure` + `equipment` text per Test 2.

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR PK | |
| `signature` | BYTEA | 128-permutation MinHash signature |
| `computed_at` | TIMESTAMP | |

Written once at batch time. Never updated unless the batch is re-run.

### `cache.description_embeddings`

384-dimensional sentence embeddings computed on each facility's `description` text per Test 6 (embedding-drift cosine).

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR | |
| `snapshot_id` | VARCHAR | Monotonic batch-run identifier; format `YYYY-MM-DD-batch-NNN` (e.g., `2026-06-15-batch-001`). Always-present from snapshot 1. |
| `embedding` | BYTEA | 384-dim float vector serialized as bytes; loaded into a numpy array (~30 MB at 10k facilities) at app start for sub-millisecond cosine drift queries. |
| `computed_at` | TIMESTAMP | |

Composite PK on `(facility_id, snapshot_id)`. **pgvector cosine index** on the deserialized vector representation (Postgres pgvector extension; index name `idx_description_embeddings_cosine`). Written once per snapshot at batch time. The first snapshot's rows produce `indeterminate` for Test 6 (no prior snapshot to drift from); subsequent snapshots populate Test 6 results in `facility_existence_tests`.

### `team.planner_overrides`

| Column | Type | Notes |
|---|---|---|
| `override_id` | VARCHAR PK | UUID |
| `facility_id` | VARCHAR FK | |
| `override_type` | VARCHAR | `force-real` \| `force-phantom` |
| `reason_note` | TEXT | Required non-empty |
| `planner_id` | VARCHAR | Session identifier |
| `overridden_at` | TIMESTAMP | |

Append-only. Overrides are never deleted; they are superseded by newer overrides on the same `facility_id`.

### `team.saved_scenarios`

| Column | Type | Notes |
|---|---|---|
| `scenario_id` | VARCHAR PK | UUID |
| `scenario_name` | VARCHAR | Planner-provided |
| `capability` | VARCHAR | |
| `region_filter` | VARCHAR | State or district filter applied |
| `override_set` | JSONB | Array of `override_id` values |
| `planner_notes` | TEXT | |
| `planner_id` | VARCHAR | |
| `saved_at` | TIMESTAMP | |

### `team.budget_allocations`

The planner's prior-quarter ₹ allocation per district. Read by the Budget Reallocation view to render the before/after pie and compute recommended ₹ shifts. The table is loaded from a hand-curated CSV at demo time; in production it would be populated from the planner's actual allocation system.

| Column | Type | Notes |
|---|---|---|
| `district_id` | VARCHAR | FK to `desert_scores.district_id` |
| `state_name` | VARCHAR | |
| `capability` | VARCHAR | The capability the allocation funds (e.g. `maternity`); same enum as `desert_scores.capability` |
| `quarter` | VARCHAR | e.g. `2026-Q3` |
| `allocated_inr` | BIGINT | ₹ allocated for this quarter |
| `loaded_at` | TIMESTAMP | |

Composite PK on `(district_id, capability, quarter)`. Read-only from the app's perspective during the demo (the *recommended* re-allocation is computed in-process from `desert_scores` + this table; the recommendation is exported to CSV, not written back to this table). Multi-quarter data lets a future enhancement compare allocations over time without schema change.

## Platform Sync

The existence engine runs offline as a Databricks notebook against the
Virtue Foundation bronze tables, computes all six tests and the dual-verdict
outputs, and writes gold Delta tables to `workspace.phantom_census.*`. The
gold tables are then mirrored into Lakebase as **synced tables** in the
`phantom_census_lakebase.public.*` schema via the Autoscaling
`databricks postgres create-synced-table` API.

**Why synced tables, not the engine writer:** the engine writer in
`lakebase/writer.py` is the path used by per-batch incremental updates and
by integration tests against a local Postgres. The synced-tables pipeline
is the platform-managed bulk-mirror used to seed Lakebase from gold Delta
on a fresh deploy without round-tripping through the writer. Both paths
target the same Lakebase schema; the synced-tables snapshot is the
authoritative read source the Streamlit app sees.

**Gold-table set (LP-SYNC-001):**

| Gold table | Primary key | Read by |
|---|---|---|
| `facilities` | `facility_id` | map_view, side_panel, audit_view |
| `phantom_verdicts` | `facility_id` | every view |
| `facility_existence_tests` | `(facility_id, test_name, ran_at)` | side_panel evidence expand |
| `desert_scores` | `(district_id, capability)` | map_view, budget_view |
| `description_embeddings` | `(facility_id, snapshot_id)` | embedding-drift Test 6 + EE-AI-007 |
| `facility_capabilities` | `(facility_id, capability)` | desert-scoring multi-cap recompute |
| `budget_allocations` | `(district_id, capability, quarter)` | budget_view |

**Sync mode (LP-SYNC-003):** `SNAPSHOT`. Re-running the notebook + the
setup script refreshes the snapshot — no CDF dependency. `TRIGGERED` mode
is a future option once the gold tables enable CDF.

**Cuts (LP-SYNC-004):** `cache.tile_layers` is not synced — the table was
deleted per LP-INIT-004's inversion. `cache.claim_minhash` is not synced
either — the engine's `writer.py` is the canonical write path for MinHash
signatures, used by integration tests against a local Postgres; in the
deployed app the engine notebook itself uses `writer.py` against the
Lakebase synced-table endpoint for the minhash cache.

**Grants (LP-SYNC-005):** the synced-tables pipeline creates schemas
owned by the project owner (`databricks_superuser`). The app's service
principal needs an explicit `GRANT USAGE` on the `public` schema plus
`GRANT SELECT` on all current AND future tables (via `ALTER DEFAULT
PRIVILEGES`) so subsequent sync refreshes are readable without
re-granting.

## Connection Pattern

The Streamlit app connects to Lakebase via SQLAlchemy using the Databricks Postgres-compatible endpoint. Read queries use a read-only connection pool; write operations (overrides, scenario saves) use a write connection with explicit transaction management.

On Free Edition, Lakebase connection credentials are injected via Databricks App environment variables — no hardcoded secrets.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Override table is append-only | Yes | In-place update | Append-only preserves the full audit trail of what a planner changed and when. The most-recent override per `facility_id` is the effective verdict; older rows are the history. Required for defensibility. |
| CDC on `phantom_verdicts` | Enabled | Poll-based refresh | CDC is preserved for audit and re-batch verification. The desert-score recompute itself is a Streamlit callback fired explicitly after the override UPDATE commits — not a CDC subscription — to guarantee post-commit reads. CDC availability on Free Edition will be confirmed on Day 1. |
| MinHash signatures in Lakebase | Yes | Recompute on demand | MinHash is slow on 10k records (minutes for 128-perm). Pre-storing in Lakebase means the existence engine can re-run a subset without recomputing signatures for the whole corpus. Signatures are computed on concatenated capability+procedure+equipment text. |
| Description embeddings in Lakebase + pgvector | Yes (`cache.description_embeddings`) | Re-encode at app start each session; Vector Search service | Re-encoding 10k descriptions per session takes ~2 minutes and burns tokens — defeats the activation-gate posture. Vector Search is a separate Databricks service with its own latency profile and indexing flow; for a single similarity query (Test 6 cosine drift, planner's prior-override similarity lookup) on 10k rows, an in-process numpy load from Lakebase BYTEA is faster and simpler. pgvector index supports the future case of larger corpora. |
| AI recommendation co-located on `phantom_verdicts` | Two new columns (`ai_recommendation`, `ai_recommendation_evidence_state`) | Separate `ai_recommendations` table joined on `facility_id` | Co-locating means the side-panel render is a single read on `phantom_verdicts`. The recommendation is 1:1 with the verdict (cardinality matches), and lifecycle-coupled (a new batch invalidates both the verdict and any prior recommendation). A separate table would require a join on every render and offers no flexibility we'd use. |
| Adjudicator output preserved separately from final verdict | `adjudicator_verdict` + `verdict` columns on `phantom_verdicts` | Single `verdict` column; reconstruct Adjudicator output from `test_outcome_vector` on demand | Two columns make the rescue trace a one-read query for the side panel. Reconstructing on demand requires re-running the Adjudicator rule against the stored test vector — workable but adds CPU per render and couples the schema to the rule definition. The two-column shape is cheap (one VARCHAR per row) and makes the audit trail uniform across rescue and override flows. |
| Defender Layer A rescue trace as JSONB column, not row | `phantom_verdicts.rescue_applied` JSONB | Separate row in `facility_existence_tests` with `test_name = defender-rescue` | Layer A rescues are per-verdict (1:1 with `phantom_verdicts`), not per-test. Encoding them as a row in `facility_existence_tests` puts a verdict-level mutation in a test-results table — semantic mismatch. Layer B's test-input corrections *are* per-test and correctly live as rows. The two layers' shapes follow their semantics. |
| Tile-layer pre-rendering cache | None (cut) | `cache.tile_layers` with pre-rendered Folium HTML | Pydeck reads `desert_scores` directly. The cache table would hold a stale duplicate of `desert_scores`; every override would force a re-render of both layers. Cutting the table simplifies the schema and removes a source of stale state. |
| Budget allocation source | Hand-curated CSV loaded into `team.budget_allocations` at demo time | Live integration with state finance system; static dict in code | A CSV is honest about what the demo has — *we have a plausible Q3 Maharashtra allocation, hand-curated*. Live integration is out of scope (network, auth, schema-drift risk). A static dict in code couples the demo data to the codebase and prevents future swaps. The table shape is production-honest while the row population is demo-honest. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Overrides are append-only; active verdict is the most-recent override per `facility_id`. Rationale: audit trail preservation and ACID compliance.
2. ✅ Desert-score recompute on override is a Streamlit callback explicitly scheduled after the UPDATE commits, not a CDC trigger. Rationale: guarantees post-commit reads, avoids stale-read race window. CDC log is preserved for audit only.
3. ✅ Tile-layer pre-rendering cache cut. Rationale: pydeck reads `desert_scores` directly; the cache duplicated state with no benefit.

### Deferred
1. Whether to migrate `team.budget_allocations` from CSV-loaded static rows to a live planner-finance-system integration — deferred to post-hackathon. The schema is shaped for production; only the row source is demo-only.
2. Whether to add bitemporal columns `(valid_from, valid_to)` on `phantom_verdicts` and `facility_existence_tests` for the time-slider replay stretch feature — deferred per the proposal's stretch list.

### Day-1 implementation details to confirm
*Not blocking; reasonable defaults work. Listed so they don't get lost.*

1. **Read-then-write transaction shape for the AI Evidence Layer.** Lookup-and-write on a contested-facility open is one logical operation; current default is one write connection per open. Alternative: separate read pool + write connection, two round-trips. Both work; the difference matters under high concurrent load (not a demo concern).
2. **`burden_imputed` write ownership.** Default: batch pipeline only. The flag captures NFHS-5 indicator imputation, which is a per-district property of the data, not affected by override-driven count changes. Override recomputes preserve the existing `burden_imputed` value.
3. **CDC log consumption.** CDC on `phantom_verdicts` is enabled and produces a log on every UPDATE (including `ai_recommendation`-only writes). The log is consumed by audit / batch verification only; the recompute path is the Streamlit callback per the LLD. No CDC subscriber processes the log at demo time.
4. **Schema DDL ownership.** Default: a single Python migration script run once at project setup, idempotent (`CREATE TABLE IF NOT EXISTS`). To be authored on Day 1.
5. **Connection auth env var naming.** To be confirmed against Databricks Apps' actual injection convention on Day 1; no pre-specified names committed here.

## References

- `docs/high-level-design.md` — Lakebase role in the system architecture
- `docs/intent/existence-engine/existence-engine-design.md` — upstream writer
- `docs/intent/desert-scoring/desert-scoring-design.md` — downstream reader + recompute trigger
- `docs/intent/planner-workspace/planner-workspace-design.md` — override + scenario writer
