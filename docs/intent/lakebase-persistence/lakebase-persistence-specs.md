---
parent: high-level-design
prefix: LP
---

## Lakebase Persistence — EARS Specs

### Table Initialization

- [ ] **LP-INIT-001**: The system shall create all Lakebase tables listed in the schema section of lakebase-persistence-design.md before the batch pipeline runs.
- [ ] **LP-INIT-002**: The system shall enable CDC on `operational.phantom_verdicts` during table creation.
- [ ] **LP-INIT-003**: The system shall create a Delta mirror of `operational.facility_existence_tests` with Liquid Clustering on `facility_id` for analytical batch scans.
- [ ] **LP-INIT-004**: The system shall create `cache.tile_layers` with composite PK on `(capability, layer_type)` before the batch pipeline runs.

### Writes from Existence Engine

- [ ] **LP-EE-001**: The existence engine batch shall write one row per `(facility_id, test_name)` to `operational.facility_existence_tests` for each test executed, including `result`, `evidence_ref` (JSONB), and `ran_at`.
- [ ] **LP-EE-002**: The existence engine batch shall write one row per `facility_id` to `operational.phantom_verdicts` with `verdict`, `test_outcome_vector`, and `ran_at`, overwriting any prior row for the same `facility_id`.
- [ ] **LP-EE-003**: The existence engine batch shall write one row per `facility_id` (with a non-null signature) to `cache.claim_minhash` with the 128-permutation MinHash signature as BYTEA, overwriting any prior row. The cache key is named for the claim-array text (capability + procedure + equipment) the signature represents — see EE-HASH-001.
- [ ] **LP-EE-004**: All existence engine writes shall commit atomically per facility — either all five test rows and the verdict row commit together, or none do.

### Reads from App

- [ ] **LP-APP-001**: The Streamlit app shall read `operational.desert_scores` for the selected capability on page load to populate the choropleth color data.
- [ ] **LP-APP-002**: When a planner clicks a district, the Streamlit app shall read `operational.phantom_verdicts` filtered to that district's facility IDs and return up to 5 phantom-verdicted facilities ordered by `adjusted_desert_score` descending.
- [ ] **LP-APP-003**: When a planner expands a phantom facility's evidence row, the Streamlit app shall read `operational.facility_existence_tests` for that `facility_id` and return all test rows.

### Override Writes

- [ ] **LP-OVR-001**: When a planner submits an override, the Streamlit app shall INSERT a new row to `team.planner_overrides` with `facility_id`, `override_type`, `reason_note`, `planner_id`, and `overridden_at`; this insert shall be atomic and return the new `override_id`.
- [ ] **LP-OVR-002**: After LP-OVR-001 commits, the Streamlit app shall UPDATE `operational.phantom_verdicts` for the affected `facility_id` to set `override_id` = the new `override_id` and `verdict` = the planner-directed verdict (not the Adjudicator's original output); `phantom_verdicts.verdict` stores the effective verdict which may be override-derived.
- [ ] **LP-OVR-003**: After LP-OVR-002 commits, the Streamlit app shall UPDATE `operational.desert_scores` for the affected district to recompute `adjusted_desert_score` and `phantom_count` using the updated `phantom_verdicts`.
- [ ] **LP-OVR-004**: If any step in LP-OVR-001 through LP-OVR-003 fails, the system shall rollback all changes for that override and display an error message to the planner.

### Scenario Persistence

- [ ] **LP-SCEN-001**: When a planner saves a scenario, the Streamlit app shall INSERT a row to `team.saved_scenarios` with `scenario_name`, `capability`, `region_filter`, `override_set` (JSONB array of current session's `override_id` values), `planner_notes`, `planner_id`, and `saved_at`.
- [ ] **LP-SCEN-002**: On app load, the Streamlit app shall query `team.saved_scenarios` for the current `planner_id` and display matching scenarios ordered by `saved_at` descending.
- [ ] **LP-SCEN-003**: When a planner selects a saved scenario to restore, the Streamlit app shall read each `override_id` from `team.planner_overrides` and re-assert (not re-insert) the corresponding `verdict` and `override_id` values onto `operational.phantom_verdicts` for each affected `facility_id`, then recompute `operational.desert_scores` for the affected districts; if a row in `phantom_verdicts` already carries the correct `override_id`, the re-assert is a no-op for that row.
- [ ] **LP-SCEN-004**: The scenario restore operation (LP-SCEN-003) shall produce the same `operational.phantom_verdicts` state as the session had when the scenario was saved, assuming the underlying batch verdicts have not changed.
