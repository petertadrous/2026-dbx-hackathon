---
parent: high-level-design
prefix: LP
---

# Lakebase Persistence

## Context and Design Philosophy

Lakebase is the operational spine of Phantom Census. It holds all mutable state: phantom verdicts, planner overrides, saved scenarios, desert scores, and MinHash cache. The batch pipeline writes to it; the Streamlit app reads and writes to it live.

Lakebase is chosen over Delta-only because per-district override-triggered recomputes require sub-second mutable OLTP writes. Delta's merge semantics are too slow for live demo feedback. Lakebase's Postgres-compatible wire protocol enables a straightforward SQLAlchemy connection from the Streamlit app.

## Schema

### `operational.phantom_verdicts`

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR PK | Matches VF dataset `facility_id` |
| `verdict` | VARCHAR | `phantom` \| `real` \| `contested` |
| `test_outcome_vector` | JSONB | All 5 test results + evidence refs |
| `ran_at` | TIMESTAMP | Batch run timestamp |
| `override_id` | VARCHAR FK | NULL if no override; FK to `team.planner_overrides` |

CDC enabled on this table — changes trigger the desert score recompute.

### `operational.facility_existence_tests`

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR | |
| `test_name` | VARCHAR | `pin-lookup` \| `minhash-duplicate` \| `spatial-mismatch` \| `nfhs-consistency` \| `temporal-implausibility` \| `defender-rescue` |
| `result` | VARCHAR | `pass` \| `fail` \| `indeterminate` \| `not-applicable` |
| `evidence_ref` | JSONB | Source row(s) driving the result |
| `ran_at` | TIMESTAMP | |

Composite PK on `(facility_id, test_name, ran_at)`. Liquid-clustered on `facility_id` in the Delta mirror for analytical scans.

### `operational.desert_scores`

| Column | Type | Notes |
|---|---|---|
| `district_id` | VARCHAR PK | Normalized district key |
| `district_name` | VARCHAR | |
| `state_name` | VARCHAR | |
| `capability` | VARCHAR | e.g. `maternity`, `icu` |
| `raw_desert_score` | FLOAT | 0–1 |
| `adjusted_desert_score` | FLOAT | 0–1 |
| `verified_facility_count` | INT | |
| `phantom_count` | INT | |
| `burden_imputed` | BOOLEAN | True if NFHS indicator was imputed from state median |
| `updated_at` | TIMESTAMP | |

Updated by the batch pipeline and by single-district override recomputes.

### `cache.claim_minhash`

128-permutation MinHash signatures computed on concatenated capability+procedure+equipment text

| Column | Type | Notes |
|---|---|---|
| `facility_id` | VARCHAR PK | |
| `signature` | BYTEA | 128-permutation MinHash signature on concatenated capability+procedure+equipment text |
| `computed_at` | TIMESTAMP | |

Written once at batch time. Never updated unless the batch is re-run.

### `cache.tile_layers`

| Column | Type | Notes |
|---|---|---|
| `capability` | VARCHAR | e.g. `maternity`, `icu` |
| `layer_type` | VARCHAR | `raw` \| `adjusted` |
| `html` | TEXT | Pre-rendered Folium choropleth HTML string |
| `rendered_at` | TIMESTAMP | |

Composite PK on `(capability, layer_type)`. Written at batch time; overwritten on each batch re-run. The Streamlit app reads one `(capability, layer_type)` pair per active view state.

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

## Connection Pattern

The Streamlit app connects to Lakebase via SQLAlchemy using the Databricks Postgres-compatible endpoint. Read queries use a read-only connection pool; write operations (overrides, scenario saves) use a write connection with explicit transaction management.

On Free Edition, Lakebase connection credentials are injected via Databricks App environment variables — no hardcoded secrets.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Override table is append-only | Yes | In-place update | Append-only preserves the full audit trail of what a planner changed and when. The most-recent override per `facility_id` is the effective verdict; older rows are the history. Required for defensibility. |
| CDC on `phantom_verdicts` | Enabled | Poll-based refresh | CDC is the signal source for single-district recompute. Without it, the app must poll the whole table on every override. CDC is the tighter, more professional pattern — and its availability on Free Edition will be confirmed on Day 1. |
| MinHash signatures in Lakebase | Yes | Recompute on demand | MinHash is slow on 10k records (minutes for 128-perm). Pre-storing in Lakebase means the existence engine can re-run a subset without recomputing signatures for the whole corpus. Signatures are computed on concatenated capability+procedure+equipment text. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Overrides are append-only; active verdict is the most-recent override per `facility_id`. Rationale: audit trail preservation and ACID compliance.

### Deferred
1. Whether `operational.desert_scores` should be a Lakebase materialized view auto-refreshed from `phantom_verdicts` CDC, or updated by explicit Python callback. Currently: explicit Python callback in Streamlit on override save. If CDC supports materialized views on Free Edition, migrate the callback to a materialized view.

## References

- `docs/high-level-design.md` — Lakebase role in the system architecture
- `docs/intent/existence-engine/existence-engine-design.md` — upstream writer
- `docs/intent/desert-scoring/desert-scoring-design.md` — downstream reader + recompute trigger
- `docs/intent/planner-workspace/planner-workspace-design.md` — override + scenario writer
