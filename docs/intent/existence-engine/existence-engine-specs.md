---
parent: high-level-design
prefix: EE
---

## Existence Engine — EARS Specs

### Batch Pipeline

- [ ] **EE-PIPE-001**: The system shall process all VF facility records through the six existence tests before the Databricks App is started.
- [ ] **EE-PIPE-002**: The system shall store one row per `(facility_id, test_name, ran_at)` in `operational.facility_existence_tests` with fields `result`, `evidence_ref` (JSONB), and `ran_at`.
- [ ] **EE-PIPE-003**: The system shall store one row per `facility_id` in `operational.phantom_verdicts` with fields `adjudicator_verdict` (`phantom` | `real` | `contested`), `verdict` (`phantom` | `real` | `contested` | `force-real-planner` | `force-phantom-planner`), `rescue_applied` (JSONB, null if no Layer A rescue fired), `test_outcome_vector` (JSONB), and `ran_at`.
- [ ] **EE-PIPE-004**: If a test cannot evaluate a facility due to absent required fields, the system shall record `result = indeterminate` for that test rather than `pass` or `fail`.

### Test 1 — PIN Reverse-Lookup

- [ ] **EE-PIN-001**: The system shall parse each facility's `pincode` field using regex `^\d{6}$` after stripping whitespace; facilities failing this parse shall receive `indeterminate` for Test 1.
- [ ] **EE-PIN-002**: The system shall deduplicate the India Post PIN Code Directory to `(pincode, district)` pairs and compute a weighted centroid per PIN before joining to facility records.
- [ ] **EE-PIN-003**: When a facility has a parseable PIN and non-null `latitude`/`longitude`, the system shall compute the haversine distance between the facility's coordinates and the India Post centroid for that PIN.
- [ ] **EE-PIN-004**: When the haversine distance computed in EE-PIN-003 exceeds 50 km, the system shall record Test 1 result as `fail` with the India Post centroid and computed distance as `evidence_ref`.
- [ ] **EE-PIN-005**: When the haversine distance is ≤50 km, the system shall record Test 1 result as `pass`.
- [ ] **EE-PIN-006**: If a facility has no `latitude`/`longitude`, the system shall record Test 1 as `indeterminate`.

### Test 2 — MinHash Near-Duplicate Detection

- [ ] **EE-HASH-001**: The system shall compute 128-permutation MinHash signatures for each facility using the concatenated text of the `capability`, `procedure`, and `equipment` fields (shingle size 5, character-level), storing the signature as BYTEA in `cache.claim_minhash`.
- [ ] **EE-HASH-002**: When the concatenated `capability` + `procedure` + `equipment` text is absent or contains fewer than 30 tokens, the system shall record Test 2 as `indeterminate`.
- [ ] **EE-HASH-003**: The system shall compute connected-component clusters of facilities using flood-fill: two facilities are in the same cluster if their pairwise Jaccard similarity is ≥ 0.9; clustering is transitive (if A~B and B~C then A, B, C are one cluster even if A~C < 0.9).
- [ ] **EE-HASH-004**: When a facility belongs to a connected-component cluster of size ≥ 3 (i.e., the facility plus ≥ 2 others), the system shall record Test 2 as `fail` with the cluster's facility IDs as `evidence_ref`.
- [ ] **EE-HASH-005**: When a facility's description is unique or belongs to a cluster of size < 3, the system shall record Test 2 as `pass`.

### Test 3 — Spatial District Mismatch

- [ ] **EE-SPATIAL-001**: The system shall assign each facility with non-null `latitude`/`longitude` to a district via point-in-polygon spatial join against the geoBoundaries ADM2 India shapefile, writing the matched `shapeID` as the canonical `district_id` onto the facility row.
- [ ] **EE-SPATIAL-002**: When `ST_Contains` / `ST_Point` is unavailable on Free Edition, the system shall fall back to GeoPandas `sjoin` in-process.
- [ ] **EE-SPATIAL-003**: For each facility with both a successful spatial-join district and a parseable PIN, the system shall look up the modal India Post district for that PIN (after `(pincode, district)` dedup) and compare to the spatial-join district after lowercase-and-strip normalization.
- [ ] **EE-SPATIAL-004**: When the spatial-join district and PIN-derived district disagree after normalization, the system shall record Test 3 as `fail` with both district values as `evidence_ref`.
- [ ] **EE-SPATIAL-005**: When the comparison in EE-SPATIAL-003 agrees, the system shall record Test 3 as `pass`.
- [ ] **EE-SPATIAL-006**: If a facility has no `latitude`/`longitude` or no parseable PIN, the system shall record Test 3 as `indeterminate`.

### Test 4 — NFHS-5 Outcome Inconsistency

- [ ] **EE-NFHS-001**: The system shall apply Test 4 only to facilities whose `capability` or `description` contains at least one of: "maternity", "nicu", "delivery", "obstetric", "antenatal", "postnatal", "c-section", "caesarean".
- [ ] **EE-NFHS-002**: For facilities in scope of Test 4 (per EE-NFHS-001), the system shall look up the NFHS-5 institutional-delivery rate for the spatially-joined district, treating `*`-suppressed values as `indeterminate`.
- [ ] **EE-NFHS-003**: When a facility claims maternity capability (EE-NFHS-001) AND its district's NFHS-5 institutional-delivery rate falls in the bottom quartile for the state (i.e., below the 25th percentile of all districts in that state), the system shall record Test 4 as `fail` with the district's rate, the state's 25th-percentile cutoff, and the state name as `evidence_ref`.
- [ ] **EE-NFHS-004**: If the NFHS-5 district join yields no match for the facility's spatial-join district, the system shall record Test 4 as `indeterminate`.
- [ ] **EE-NFHS-005**: For facilities outside the scope of Test 4 (no maternity signal), the system shall record Test 4 as `not-applicable`.

### Test 5 — Temporal Implausibility

- [ ] **EE-TEMP-001**: The system shall parse `yearEstablished` as a 4-digit integer; if absent or non-parseable, the system shall record Test 5 as `indeterminate`.
- [ ] **EE-TEMP-002**: When `yearEstablished` is greater than the current year, the system shall record Test 5 as `fail` with the parsed year as `evidence_ref`.
- [ ] **EE-TEMP-003**: When `yearEstablished` is less than 1900, the system shall record Test 5 as `fail`.
- [ ] **EE-TEMP-004**: When `yearEstablished` is after 2020 AND the facility's `capability` or `description` claims ICU, trauma, NICU, or transplant services, the system shall record Test 5 as `fail` with `yearEstablished` and the matched capability term as `evidence_ref`.
- [ ] **EE-TEMP-005**: When none of the conditions in EE-TEMP-002 through EE-TEMP-004 apply, the system shall record Test 5 as `pass`.

### Test 6 — Embedding-Drift Cosine

- [ ] **EE-EMBED-001**: The system shall compute a 384-dimensional sentence embedding for each facility's `description` once per snapshot using a fixed encoder (e.g., `all-MiniLM-L6-v2`), storing the embedding as BYTEA in `cache.description_embeddings` keyed `(facility_id, snapshot_id)` where `snapshot_id` is the monotonic batch-run identifier in format `YYYY-MM-DD-batch-NNN`.
- [ ] **EE-EMBED-002**: When the current snapshot has a `description_embeddings` row for a `facility_id` AND a prior snapshot also has a row for the same `facility_id`, the system shall compute the cosine similarity between the two snapshot embeddings.
- [ ] **EE-EMBED-003**: When the cosine drift (1 − cosine similarity) computed in EE-EMBED-002 is ≥ 0.4, the system shall record Test 6 as `fail` with `evidence_ref` carrying `{prior_snapshot_id, current_snapshot_id, cosine_drift, threshold}`.
- [ ] **EE-EMBED-004**: When the cosine drift computed in EE-EMBED-002 is < 0.4, the system shall record Test 6 as `pass`.
- [ ] **EE-EMBED-005**: When a facility has no prior-snapshot embedding (first appearance in any snapshot) OR no current-snapshot embedding (description absent or non-parseable), the system shall record Test 6 as `indeterminate`.
- [ ] **EE-EMBED-006**: When a facility's `description` is fewer than 30 tokens in either the current or the prior snapshot, the system shall record Test 6 as `indeterminate` regardless of computed cosine drift.
- [ ] **EE-EMBED-007**: On the first batch run (no prior snapshot exists for any `facility_id`), the system shall produce `indeterminate` for Test 6 for every facility.

### Adjudicator

- [ ] **EE-ADJ-001**: The system shall apply the Adjudicator to each facility after all six tests have been recorded AND after Layer B has written any test-result override rows, reading the final test outcome vector from `operational.facility_existence_tests`.
- [ ] **EE-ADJ-002**: When a row exists in `operational.facility_existence_tests` with `test_name = layer-b-override-pin` for a `facility_id`, the Adjudicator shall consume that row in place of the original `test_name = pin-lookup` row for the same `facility_id`; the original row shall remain in the table for audit but shall not be consumed by the Adjudicator. Equivalent contract for `layer-b-override-spatial` superseding `spatial-mismatch`.
- [ ] **EE-ADJ-003**: When the count of tests with `result != indeterminate` for a facility is < 2, the Adjudicator shall record `verdict = contested` with `reason = insufficient-evidence` in `test_outcome_vector`; this insufficient-evidence check is evaluated before the veto check in EE-ADJ-004.
- [ ] **EE-ADJ-004**: When EE-ADJ-003 does not apply AND any veto-capable test (Test 1 PIN-lookup or Test 3 spatial-mismatch) has `result = fail`, the Adjudicator shall record `verdict = phantom`.
- [ ] **EE-ADJ-005**: When EE-ADJ-003 and EE-ADJ-004 do not apply AND the count of `fail` results among non-veto tests (Tests 2, 4, 5, 6) is ≥ 2, the Adjudicator shall record `verdict = phantom`.
- [ ] **EE-ADJ-006**: When EE-ADJ-003 through EE-ADJ-005 do not apply AND exactly one non-veto test result is `fail`, the Adjudicator shall record `verdict = contested`.
- [ ] **EE-ADJ-007**: When the count of `fail` results across all tests is 0 AND the count of `pass` results is ≥ 2, the Adjudicator shall record `verdict = real`.
- [ ] **EE-ADJ-008**: The Adjudicator shall write its output to `operational.phantom_verdicts.adjudicator_verdict` and shall additionally write the same value to `operational.phantom_verdicts.verdict`; the `verdict` column may be subsequently mutated by Layer A or by planner override, while `adjudicator_verdict` shall remain immutable for audit.
- [ ] **EE-ADJ-009**: The Adjudicator shall store the full test outcome vector (all six test results and their `evidence_ref` values) as JSONB in `operational.phantom_verdicts.test_outcome_vector`.

### Defender — Layer B (Dataset-Version Reconciliation, Pre-Adjudicator)

- [ ] **EE-LAYER-B-001**: Before the Adjudicator runs, Layer B shall evaluate each facility with a Test 1 (`pin-lookup`) or Test 3 (`spatial-mismatch`) `result = fail` against a deterministic dataset-version reconciliation lookup table covering post-2022 district reorganizations and known spelling variants.
- [ ] **EE-LAYER-B-002**: When a Test 1 failure for a facility is explained by an entry in the reconciliation table, Layer B shall write a new row to `operational.facility_existence_tests` with `test_name = layer-b-override-pin`, `result = pass`, and `evidence_ref` citing the specific reorganization or variant matched.
- [ ] **EE-LAYER-B-003**: When a Test 3 failure for a facility is explained by an entry in the reconciliation table, Layer B shall write a new row to `operational.facility_existence_tests` with `test_name = layer-b-override-spatial`, `result = pass`, and `evidence_ref` citing the specific reorganization or variant matched.
- [ ] **EE-LAYER-B-004**: Layer B shall not modify or delete the original `pin-lookup` or `spatial-mismatch` rows; the original rows shall remain in `operational.facility_existence_tests` for audit.
- [ ] **EE-LAYER-B-005**: Layer B shall write at most one override row per `(facility_id, test_family)` where `test_family ∈ {pin, spatial}`.
- [ ] **EE-LAYER-B-006**: When the dataset-version reconciliation table contains no matching entry for a Test 1 or Test 3 failure, Layer B shall write no row to `operational.facility_existence_tests`; the original failure row stands and is consumed by the Adjudicator unchanged.

### Defender — Layer A (Structured-Field Corroboration, Post-Adjudicator)

- [ ] **EE-LAYER-A-001**: After the Adjudicator runs, Layer A shall evaluate each facility with `phantom_verdicts.adjudicator_verdict = phantom` for three deterministic rescue signals: URL mentions in `description`, HFR pre-cached snapshot match, and NFHS-5 named-staff overlap.
- [ ] **EE-LAYER-A-002**: The URL-mentions signal (`url-mentions`) shall fire when the facility's `description` contains ≥ 2 distinct external `http(s)://` URLs to non-self-published domains, where self-published is identified heuristically by URL domain tokens overlapping with the facility name.
- [ ] **EE-LAYER-A-003**: The HFR-match signal (`hfr-match`) shall fire when the facility's name + spatial-join district matches an entry in the pre-loaded HFR snapshot after lowercase normalization, whitespace stripping, and Levenshtein distance ≤ 2 on the name.
- [ ] **EE-LAYER-A-004**: The NFHS named-staff signal (`nfhs-named-staff`) shall fire when the facility's `description` lists named staff and at least one of those names appears in the NFHS-5 district denominator data for the spatially-joined district.
- [ ] **EE-LAYER-A-005**: When at least one Layer A signal fires for a phantom-verdicted facility, Layer A shall patch `phantom_verdicts.verdict` from `phantom` to `contested` and shall write `phantom_verdicts.rescue_applied = {signals: [<signal_names>], evidence_refs: [<row_ids_or_urls>]}`; `phantom_verdicts.adjudicator_verdict` shall be preserved unchanged.
- [ ] **EE-LAYER-A-006**: Layer A shall never patch a verdict to `real`; the maximum upgrade is `phantom → contested`.
- [ ] **EE-LAYER-A-007**: When no Layer A signal fires for a phantom-verdicted facility, `phantom_verdicts.verdict` shall remain `phantom` and `phantom_verdicts.rescue_applied` shall remain `null`.
- [ ] **EE-LAYER-A-008**: Layer A shall not write rows to `operational.facility_existence_tests`; the rescue trace lives only in `phantom_verdicts.rescue_applied` JSONB.

### Defender — Layer C (FMA Corroboration Synthesis, Activation-Gated)

- [ ] **EE-LAYER-C-001**: Layer C shall fire only when `phantom_verdicts.verdict = contested` after Layer A patching; Layer C shall not fire on `real` or `phantom` final verdicts.
- [ ] **EE-LAYER-C-002**: When Layer C fires, the system shall invoke the Foundation Model API (`ai_query`) using `databricks-meta-llama-3-1-70b-instruct` as the primary model and `databricks-mixtral-8x7b-instruct` as the fallback, passing as input: the six test outcome rows, the Layer B reconciliation result, the Layer A signals that fired, and the facility's `vf_facilities` row.
- [ ] **EE-LAYER-C-003**: Layer C shall emit a structured payload `{strength: "weak" | "medium" | "strong", supporting_rows: [<row_ids>], reasoning: <one_paragraph>}`.
- [ ] **EE-LAYER-C-004**: If `ai_query` returns an error or times out, Layer C shall emit a deterministic template payload with `strength = "weak"`, `supporting_rows` listing all available row IDs, and `reasoning` summarizing which Layer A signals fired and which test outcomes were observed.
- [ ] **EE-LAYER-C-005**: Layer C output shall not modify `phantom_verdicts.verdict` or `phantom_verdicts.adjudicator_verdict`; the Layer C payload shall feed only the AI Evidence Layer's escalation package consumed at planner-open time.

### AI Evidence Layer (activation-gated, planner-open)

- [ ] **EE-AI-001**: The AI Evidence Layer shall fire only when both of the following hold for a facility: (1) `phantom_verdicts.verdict = contested`, and (2) a planner has expanded that facility's row in the Planner Workspace's Map view side panel.
- [ ] **EE-AI-002**: The AI Evidence Layer cache key `evidence_state` shall be computed as `sha256(canonical_json(test_outcome_vector) + adjudicator_verdict + canonical_json(rescue_applied or null))` in fixed field order; `verdict` shall be excluded from the hash.
- [ ] **EE-AI-003**: When the AI Evidence Layer fires AND `phantom_verdicts.override_id IS NOT NULL`, the system shall not invoke `ai_query`; if `phantom_verdicts.ai_recommendation IS NOT NULL`, the system shall render the existing recommendation marked as "historical advisory"; otherwise the system shall render no recommendation panel.
- [ ] **EE-AI-004**: When the AI Evidence Layer fires AND `phantom_verdicts.override_id IS NULL` AND `phantom_verdicts.ai_recommendation IS NULL`, the system shall invoke `ai_query` with the evidence package, persist the result to `phantom_verdicts.ai_recommendation` and the current `evidence_state` to `phantom_verdicts.ai_recommendation_evidence_state`, and render the recommendation.
- [ ] **EE-AI-005**: When the AI Evidence Layer fires AND `phantom_verdicts.override_id IS NULL` AND `phantom_verdicts.ai_recommendation IS NOT NULL` AND `phantom_verdicts.ai_recommendation_evidence_state` equals the current computed `evidence_state`, the system shall render the existing `ai_recommendation` without invoking `ai_query`.
- [ ] **EE-AI-006**: When the AI Evidence Layer fires AND `phantom_verdicts.override_id IS NULL` AND `phantom_verdicts.ai_recommendation IS NOT NULL` AND `phantom_verdicts.ai_recommendation_evidence_state` does not equal the current computed `evidence_state`, the system shall recompute the recommendation by invoking `ai_query`, overwrite `ai_recommendation` and `ai_recommendation_evidence_state` with the new values, and render the recomputed recommendation.
- [ ] **EE-AI-007**: The AI Evidence Layer's evidence package passed to `ai_query` shall include the six test outcome rows, the Layer A signals that fired, the Layer B reconciliation result, the Layer C payload (if produced), and the prior `force-real` / `force-phantom` reason notes from `team.planner_overrides` for facilities whose description embedding has cosine similarity ≥ 0.8 to the current facility's embedding (read from `cache.description_embeddings`); the similar-facility note set shall include all overrides ever written, across all `planner_id` values and all capabilities — not filtered to the current session.
- [ ] **EE-AI-008**: The AI Evidence Layer output shall conform to the shape `{recommendation: "force-real" | "force-phantom" | "evidence-too-thin", confidence: "low" | "medium" | "high", reasoning: <one_paragraph>, cited_evidence_rows: [<row_ids>], source: "fma" | "template-fallback"}`.
- [ ] **EE-AI-009**: If `ai_query` returns an error or times out during the AI Evidence Layer call, the system shall emit a template-fallback recommendation: `recommendation = "force-phantom"` if any veto-capable test result is `fail`, otherwise `"evidence-too-thin"`; `confidence = "low"`; `reasoning` is a deterministic summary; `source = "template-fallback"`. The template-fallback payload shall be persisted to `phantom_verdicts.ai_recommendation` identically to a successful FMA payload.
- [ ] **EE-AI-010**: When two concurrent planner sessions invoke the AI Evidence Layer for the same `facility_id` and the same `evidence_state` simultaneously, both invocations may proceed; the persisted `ai_recommendation` shall reflect the last UPDATE to commit.
- [ ] **EE-AI-011**: The AI Evidence Layer shall not modify `phantom_verdicts.verdict`; verdict mutations are reserved for the Adjudicator (initial), Layer A (rescue patch), and the planner override path.
- [ ] **EE-AI-012**: When the FMA call returns and the system is about to persist `ai_recommendation` and `ai_recommendation_evidence_state`, the system shall re-read `phantom_verdicts.override_id` for the same `facility_id` within the same write transaction and shall skip the persistence write if `override_id IS NOT NULL`; the FMA call's cost is absorbed but the result is discarded so a recommendation arriving after a planner override does not retroactively appear as historical advisory.
