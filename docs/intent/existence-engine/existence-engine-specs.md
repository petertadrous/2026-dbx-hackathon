---
parent: high-level-design
prefix: EE
---

## Existence Engine — EARS Specs

### Batch Pipeline

- [ ] **EE-PIPE-001**: The system shall process all VF facility records through the five existence tests before the Databricks App is started.
- [ ] **EE-PIPE-002**: The system shall store one row per `(facility_id, test_name)` in `operational.facility_existence_tests` with fields `result`, `evidence_ref` (JSONB), and `ran_at`.
- [ ] **EE-PIPE-003**: The system shall store one row per `facility_id` in `operational.phantom_verdicts` with fields `verdict` (`phantom` | `real` | `contested`), `test_outcome_vector` (JSONB), and `ran_at`.
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

- [ ] **EE-SPATIAL-001**: The system shall assign each facility with non-null `latitude`/`longitude` to a district via point-in-polygon spatial join against geoBoundaries ADM2 India district polygons.
- [ ] **EE-SPATIAL-002**: When `ST_Contains` / `ST_Point` is unavailable on Free Edition, the system shall fall back to GeoPandas `sjoin` in-process.
- [ ] **EE-SPATIAL-003**: For each facility with both a successful spatial-join district and a parseable PIN, the system shall look up the modal India Post district for that PIN (after `(pincode, district)` dedup) and compare to the spatial-join district after lowercase-and-strip normalization. When the modal district holds ≤ 50% of mappings for that PIN ("ambiguous-pin"), the system shall record Test 3 as `indeterminate` with `evidence_ref = {"ambiguous_pin": true, "modal_share": <share>}`.
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

### Adjudicator

- [ ] **EE-ADJ-001**: The system shall apply the Adjudicator to each facility after all five tests have been recorded, using only the test results stored in `operational.facility_existence_tests`.
- [ ] **EE-ADJ-002**: When any veto-capable test (Test 1 or Test 3) result is `fail`, the system shall record `verdict = phantom` regardless of other test results.
- [ ] **EE-ADJ-003**: When no veto-capable test is `fail` AND count of tests with `result = fail` among non-veto tests is ≥ 2, the system shall record `verdict = phantom`.
- [ ] **EE-ADJ-004**: When exactly one non-veto test result is `fail` AND no veto-capable test is `fail` AND count of tests with `result != indeterminate` is ≥ 2, the system shall record `verdict = contested`.
- [ ] **EE-ADJ-005**: When the count of tests with `result` in {`pass`, `fail`} is < 2 (evaluated before any other Adjudicator rule), the system shall record `verdict = contested` with `reason = insufficient-evidence` in `test_outcome_vector`; EE-ADJ-005 takes precedence over EE-ADJ-002, EE-ADJ-003, and EE-ADJ-004 when both conditions hold. `not-applicable` and `indeterminate` do not count toward the testable floor.
- [ ] **EE-ADJ-006**: When count of `fail` results is 0 AND count of `pass` results is ≥ 2, the system shall record `verdict = real`.
- [ ] **EE-ADJ-007**: The system shall store the full test outcome vector (all five test results and their `evidence_ref` values) as JSONB in `operational.phantom_verdicts.test_outcome_vector`.

### Existence Defender

- [ ] **EE-DEF-001**: After the initial Adjudicator pass, the Defender shall evaluate each facility with `verdict = phantom` for corroborating real-existence signals.
- [ ] **EE-DEF-002**: When a phantom-verdicted facility has a matching entry in the pre-loaded HFR snapshot (matched on facility name + district after normalization), the Defender shall upgrade the verdict to `contested`.
- [ ] **EE-DEF-003**: When a phantom-verdicted facility has ≥2 distinct external URL references in its `description`, the Defender shall upgrade the verdict to `contested`.
- [ ] **EE-DEF-004**: The Defender shall not upgrade any verdict to `real`; maximum upgrade is `contested`.
- [ ] **EE-DEF-005**: The system shall log each Defender upgrade as a new row in `operational.facility_existence_tests` with `test_name = defender-rescue` and the rescue signal as `evidence_ref`.
