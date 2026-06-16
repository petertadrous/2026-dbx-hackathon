---
parent: high-level-design
prefix: EE
---

# Existence Engine

## Context and Design Philosophy

The Existence Engine is the detection core of Phantom Census. It takes the 10,000-record VF facility dataset and produces a verdict — `phantom`, `real`, or `contested` — for each facility, with the specific test evidence that drove the verdict.

The engine runs as an offline batch job before the app starts. The live app reads cached verdicts from Lakebase; nothing in the engine runs at query time. This is the "boring over clever" tenet applied: pre-computation eliminates latency risk during the live demo.

The engine is structured as an adversarial Prosecutor/Defender pair resolved by a deterministic Adjudicator. The Prosecutor defaults to "fake until proven real" and runs five independent existence tests. The Defender looks for corroborating signals that rescue facilities the Prosecutor flagged. The Adjudicator applies a majority-with-veto rule with no LLM involvement.

## Five Existence Tests

### Test 1: PIN Reverse-Lookup (veto-capable)

Compare the facility's claimed 6-digit PIN code against the India Post PIN Code Directory. For each facility with a parseable PIN, look up the India Post `latitude`/`longitude` for that PIN's primary post office. Compute the haversine distance between the facility's `latitude`/`longitude` and the India Post centroid for that PIN. Flag if distance > 50 km.

**Veto rule:** This test is the hardest signal. A facility claiming to be in Bihar with GPS coordinates placing it in Rajasthan is a hard contradiction. PIN-fail is a veto — it alone triggers `phantom` without needing supporting evidence.

**Absent-data behavior:** If the facility has no parseable PIN, this test returns `indeterminate`. If the PIN maps to multiple districts in India Post (fan-out), use the median of all post-office centroids for that PIN. If the facility has no lat/lon, this test returns `indeterminate`.

**India Post fan-out handling:** Row grain in India Post is post office, not PIN. Dedup to `(pincode, district)` pairs before joining; use the weighted centroid of post offices sharing a PIN.

### Test 2: MinHash Near-Duplicate Detection (supporting)

Compute 128-permutation MinHash signatures on the **concatenated `capability` + `procedure` + `equipment` JSON-array fields** (shingle size 5, character-level). These fields are 99.7% populated and contain the exact claim payload (procedures, equipment, capability statements) — far richer per facility than `description` (p50 = 16 tokens, too short for Jaccard 0.9 + shingle 5). Cluster at Jaccard ≥ 0.9. Flag any facility whose claim-array fingerprint is a near-duplicate of ≥2 other facilities.

**Why not `description`:** Day-0 validation showed description p50 = 16 tokens. MinHash @ Jaccard 0.9 + shingle-5 won't produce meaningful signatures on text that short. The structured-claim arrays are 10–20× richer per facility. Exact-match dedup on `capability` alone already groups 250 facilities into 92 near-identical clusters — non-trivial baseline before MinHash runs.

**Supporting signal:** Description similarity alone does not veto — chain hospital boilerplate is a known false-positive source. This test contributes to the majority count but cannot veto alone.

**Absent-data behavior:** If the concatenated claim-array text (`capability` + `procedure` + `equipment`) is absent or < 30 tokens, this test returns `indeterminate`. **This guard fires unconditionally — even when cluster membership is pre-computed externally.** A facility with a description shorter than 30 tokens will never receive a `fail` verdict from this test, regardless of whether it appears in a large duplicate cluster. The rationale: a description too short to generate reliable MinHash shingles cannot be considered meaningful evidence of duplication. If a facility's description is suspiciously short *and* it appears in a duplicate cluster, the short description itself may be evidence of tampering — capture that observation in a manual review note rather than in this test's verdict.

**Threshold rationale:** Jaccard 0.9 at 128 perms corresponds to ~95% similar text. This is deliberately aggressive — a lower threshold produces more false positives from legitimate chain boilerplate. Jaccard can be relaxed to 0.85 post-validation if signal is too sparse.

### Test 3: Spatial District Mismatch (veto-capable)

Assign each facility to a district using a point-in-polygon spatial join (facility lat/lon → geoBoundaries ADM2 district polygons). Look up the district associated with the facility's PIN in India Post. Flag if the spatial-join district ≠ India Post PIN district.

**Veto rule:** A systematic disagreement between GPS-derived district and PIN-derived district is hard geographic evidence of data error. This test is veto-capable.

**Free Edition fallback:** `ST_Contains` / `ST_Point` via Databricks geospatial functions preferred. If unavailable on Free Edition, fall back to GeoPandas point-in-polygon in-process (10k facilities × ~700 polygons fits a single worker in <30 seconds).

**Absent-data behavior:** If the facility has no lat/lon, this test returns `indeterminate`. If the facility has no parseable PIN, this test returns `indeterminate`. If the PIN maps to multiple India Post districts, use the modal district; flag as `ambiguous-pin` when modal is not >50% of mappings.

### Test 4: NFHS-5 Outcome Inconsistency (supporting)

For facilities claiming maternity-related capabilities (maternity, NICU, institutional delivery, C-section), look up the NFHS-5 institutional-delivery rate for the spatially-joined district. Flag if the facility claims a high-acuity maternity capability but the district's NFHS-5 institutional-delivery rate sits in the **bottom quartile for the state**.

**Re-spec rationale:** The original draft required "indicator didn't move between NFHS-4 and NFHS-5." That is a longitudinal delta requiring NFHS-6 (2023–24), which is listed as optional/stretch only. NFHS-5 alone is a 2019–21 cross-section. The replacement — bottom-quartile snapshot inconsistency — preserves the same narrative beat ("claims maternity but the district indicator says otherwise") with implementable math on data already in hand. Bihar institutional-delivery range: 21.4–93.2%; Maharashtra: 76.3–100%. Bottom-quartile cutoffs produce real contrast in both states.

**Supporting signal:** A district with bottom-quartile institutional-delivery despite many claimed maternity facilities is anomalous. This test is supporting-only — it cannot veto because the causal chain is indirect.

**Absent-data behavior:** If `capability` / `description` contains no maternity signal, this test returns `not-applicable`. If NFHS-5 district join fails, this test returns `indeterminate`. If the NFHS-5 indicator is suppressed (`*`), this test returns `indeterminate`.

**Scope:** This test applies only to facilities with maternity-related capability claims. For non-maternity capabilities, this test is `not-applicable`.

### Test 5: Temporal Implausibility (supporting)

Parse the `yearEstablished` field. Flag if: (a) `yearEstablished` is in the future, (b) `yearEstablished` is before 1900, or (c) `yearEstablished` is after 2020 combined with claims of high-acuity services (ICU, trauma, NICU) that typically require years of operational ramp-up.

**Supporting signal:** Temporal implausibility alone does not prove non-existence — new facilities can claim high acuity on opening. This test is supporting-only.

**Absent-data behavior:** If `yearEstablished` is absent or non-parseable, this test returns `indeterminate`.

## Adjudicator Logic

The Adjudicator is a pure deterministic function — no LLM, no probabilistic model. It reads the test outcome vector for each facility and applies this rule:

```
verdict = phantom   IF any veto-capable test = FAIL
                    OR count(non-veto FAIL) >= 2

verdict = contested IF count(non-veto FAIL) == 1
                    OR count(tests with result != indeterminate) < 2

verdict = real      IF count(FAIL) == 0
                    AND count(PASS) >= 2
```

**Precedence is explicit:** the `< 2 testable results` condition (insufficient evidence → `contested`) is evaluated **before** the veto condition. This means a facility with a hard PIN veto but fewer than two testable results gets `contested/insufficient-evidence`, not `phantom`. This is intentional — the "absent data abstains" tenet means we do not amplify a single signal into a definitive verdict when the evidence base is too thin to be trustworthy. Implementers must evaluate `len(testable) < 2` first; the veto check runs only when there are enough testable results to support a phantom verdict.

**Evidence record:** Every verdict row in Lakebase includes the full test outcome vector — which test returned what result, and the supporting data row (India Post row, NFHS-5 district value, MinHash collision set) for each failure.

## Existence Defender

The Defender runs after the Prosecutor produces its initial verdict set. For facilities initially marked `phantom`, the Defender looks for corroborating evidence that rescues them:

- Matching entry in the Health Facility Registry (HFR) pre-cached snapshot — this is the sixth existence test (add-on per differentiation strategy)
- Multiple distinct registrable domains (eTLD+1) referenced in the description, indicating multiple independent external sources

Both signals are evaluated for every `phantom`-verdicted facility; when either fires, the verdict is upgraded to `contested` and the evidence record captures every signal that fired (not only the first). A Defender rescue upgrades a `phantom` verdict to `contested`.

It cannot upgrade to `real` — only `real` when all Prosecutor tests pass.

## Data Flow

```
Bronze (raw ingestion) → Silver (existence tests + verdicts) → Lakebase (operational)
```

**Bronze:** Append-only raw tables for VF records, India Post, NFHS-5, geoBoundaries. No transforms.

**Silver:**
1. `facility_existence_tests` — one row per `(facility_id, test_name)` with `result`, `evidence_ref`, `ran_at`
2. `phantom_verdicts` — one row per `facility_id` with `verdict`, `test_outcome_vector` (JSONB), `ran_at`

**Lakebase operational tables:**
- `operational.phantom_verdicts` — the CDC source for map redraw; mutable (Defender can update)
- `operational.facility_existence_tests` — detail view for the side panel
- `cache.claim_minhash` — MinHash signatures stored as BYTEA; computed once. Named for the claim-array text the signature represents (capability + procedure + equipment), not the `description` field — see EE-HASH-001 and the Day-0 validation rationale.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Duplicate detection algorithm | MinHash (128 perms, shingle 5) | TF-IDF cosine similarity; embedding distance | MinHash is O(n), token-free, and deterministic. Embedding distance requires LLM inference on 10k descriptions — violates the deterministic-core tenet. TF-IDF is viable but requires an IDF corpus that doesn't travel to a fresh notebook. MinHash is self-contained. |
| Veto architecture | PIN-mismatch and spatial-district-mismatch as hard vetoes | Weighted scoring | Hard veto makes the logic auditable — a judge or planner can follow the rule without statistical background. Weighted scoring hides its reasoning in coefficient values that can be reverse-engineered to favor any outcome. Note: the insufficient-evidence guard (< 2 testable results) takes precedence over the veto — a veto signal alone is not sufficient when the data is too sparse to support a confident verdict. |
| `build_pin_centroids` data guards | Explicit column-presence check + empty-DataFrame guard before `apply()` filters | No guard / crash on missing data | Day-0 validation (T0.2) catches column drift, but the implementation must not crash if called with an empty or differently-shaped DataFrame. Two separate guards are needed: (1) column existence — return `{}` if required columns are missing; (2) post-`dropna` empty check — skip `isinstance` filters if the DataFrame is already empty, since `apply()` on an empty object-typed column raises KeyError. |
| Batch vs. streaming | Offline batch before app starts | Streaming / CDC-driven live inference | Batch eliminates latency at query time and avoids Free Edition streaming limitations. The app reads a snapshot; verdicts are immutable until the batch re-runs. |
| HFR integration | Pre-loaded snapshot in Lakebase | Live API at query time | Live API is blocked on Free Edition (network restrictions). Pre-loaded snapshot achieves the same test with zero runtime dependency. |
| Jaccard threshold | 0.9 (strict) | 0.75–0.85 (lenient) | At 0.9 the test is conservative — it will miss some phantoms but avoids false-positives on chain boilerplate. Threshold is a config value tunable per Day-0 validation results. |
| MinHash input field | `capability` + `procedure` + `equipment` concatenated | `description` field | Day-0: description p50 = 16 tokens — too short for Jaccard 0.9 + shingle-5. Structured-claim arrays are 99.7% populated, 10–20× richer, and contain the actual claim payload. Exact-match dedup on `capability` alone already groups 250 facilities into 92 near-identical clusters. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Defender can only upgrade `phantom → contested`, not `phantom → real`. Rationale: the Defender improves recall without creating a path for a facility to bypass all Prosecutor tests.

### Deferred
1. Whether to expose Jaccard threshold as a planner-configurable slider in the UI — deferred to post-MVP if Day-0 validation reveals threshold sensitivity.
2. Whether NFHS-5 Test 4 should also apply to ICU/trauma capability claims using an NCD indicator — deferred pending Tier 3 validation results.
3. **Dataset-version reconciliation in the Defender.** A PIN-vs-spatial disagreement caused by post-2022 district carve-outs (Bapatla from Prakasam, NTR from Krishna) or true spelling drift (Mysore↔Mysuru, Ahmadnagar↔Ahmednagar) should ultimately be rescued by the Defender rather than flagged as a phantom. Day-0 validation showed ~9pp of the raw 24.5% disagreement falls into this bucket. Deferred for the hackathon; case- and punctuation-level normalization in Test 4 (NFHS join) is in scope; rename and carve-out maps are out of scope.

## References

- `phantom_census_validation.md` — Day-0 tests that validate this component's data preconditions
- `docs/high-level-design.md` — system architecture and Adjudicator overview
- HFR public API: https://facility.abdm.gov.in (snapshot to be cached on Day 1)
