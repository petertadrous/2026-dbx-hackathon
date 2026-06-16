---
parent: high-level-design
prefix: EE
---

# Existence Engine

## Context and Design Philosophy

The Existence Engine is the detection core of Phantom Census. It takes the 10,000-record VF facility dataset and produces a verdict — `phantom`, `real`, or `contested` — for each facility, with the specific test evidence that drove the verdict.

The engine runs as an offline batch job before the app starts. The live app reads cached verdicts from Lakebase; nothing in the engine runs at query time except the AI Evidence Layer's contested-case escalation, which is activation-gated to the ~3% of facilities the deterministic Adjudicator marks `contested` and is only invoked when a planner opens a contested facility's side panel.

The engine is structured as an adversarial Prosecutor/Defender pair resolved by a deterministic Adjudicator. The Prosecutor defaults to "fake until proven real" and runs six independent existence tests. The Defender looks for corroborating signals that rescue facilities the Prosecutor flagged. The Adjudicator applies a majority-with-veto rule with no LLM involvement at the verdict layer.

**AI is load-bearing in three narrow places**, all outside the verdict-layer math:
1. **Embedding-drift cosine (Test 6)** — pgvector cosine over precomputed description embeddings between snapshots; verdict-time math is cosine only, no LLM call at verdict time.
2. **Defender corroboration synthesis (Foundation Model API `ai_query`)** — weighs the deterministic test-outcome rows + the dataset-version reconciliation result and emits structured `{strength, supporting_rows, reasoning}`. Activation-gated to contested cases.
3. **Adjudicator-contested escalation (Foundation Model API `ai_query`)** — when majority-with-veto outputs `contested`, reads all evidence rows + the planner's prior override notes for similar facilities and emits an advisory recommendation with reasoning. The planner makes the deciding click.

**No PDF or document mining.** All evidence the Defender and FMA reason over comes from data already in Lakebase: the six test-outcome rows, the dataset-version reconciliation lookup table, the description-URL mentions inside `vf_facilities.description`, the HFR pre-cached snapshot match, and the planner's prior override notes. External-document IE was scoped out as out-of-bounds for the L bucket and at risk of network restrictions on Free Edition.

**Determinism owns the math; AI owns the reasoning over evidence; the human owns the decision.** The activation gate keeps a full national scan ≤ $1; template-first generation is the fallback when the model is unavailable, so the pipeline cannot fail on LLM availability.

## Six Existence Tests

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

### Test 6: Embedding-Drift Cosine (supporting)

Compute a sentence-embedding for each facility's `description` at ingest using a 384-dimensional encoder (e.g., `all-MiniLM-L6-v2` via the Databricks Foundation Model API or a local model loaded once at batch time). Store as BYTEA in `cache.description_embeddings` with a `snapshot_id` discriminator. When a new snapshot lands, compute the cosine similarity between the facility's current-snapshot embedding and its prior-snapshot embedding for the same `facility_id`. Flag if cosine drift exceeds the configured threshold.

**What it detects:** Silent phantom emergence — a facility whose description morphed from substantive clinical detail to template boilerplate, or vice versa, between snapshots. This is a real fraud pattern (stuff a real description, harvest the empanelment, blank it; or spin up a template description on a previously-blank record). MinHash detects near-duplicates *now*; embedding-drift detects facilities silently *becoming* phantoms over time. The two signals are orthogonal.

**Why this is the only test using embeddings:** All other tests have a deterministic structural alternative. Embedding-drift does not — semantic decay is not a structural property. Embeddings are precomputed at ingest; the verdict-time math is a single cosine call against a numpy array loaded into process at app start (~30 MB at 384 dims for 10k facilities). No LLM call at verdict time.

**Threshold:** Cosine drift ≥ 0.4 (i.e., similarity ≤ 0.6) is `fail`. The threshold is conservative; a description rewrite that changes meaningful clinical claims typically produces drift > 0.5. Tunable per Day-0 validation against held-out gold-set pairs.

**Supporting signal:** A description rewrite is not by itself proof of fraud — facilities legitimately update their descriptions. This test is supporting-only and cannot veto.

**Absent-data behavior:** If a facility has no prior-snapshot embedding (first appearance) OR has no current-snapshot embedding (description absent or non-parseable), this test returns `indeterminate`. If a facility's description is < 30 tokens in either snapshot, this test returns `indeterminate` — the embedding signal is unreliable on text that short.

**`snapshot_id` schema:** every `description_embeddings` row carries a `snapshot_id` from snapshot 1 onwards (format: `YYYY-MM-DD-batch-NNN`, e.g. `2026-06-15-batch-001`, monotonic batch-run identifier, stored as VARCHAR). Always-present rather than lazy-created on the second snapshot — the schema stays simple and re-runs of the first batch produce new rows with fresh `snapshot_id` values without migration. The first batch run produces embedding rows that Test 6 reads as "no prior snapshot" — every facility receives `indeterminate` for Test 6 on the first run.

**LLM use disclosure:** The encoder that produces the embeddings is an ML model, but it runs once per snapshot at batch time, not at verdict time. Verdict-time math is deterministic cosine. The Tokens-axis cost of this test is the one-time ingest pass; full national scan ≤ $1 even with this test active.

## Adjudicator Logic

The Adjudicator is a pure deterministic function — no LLM, no probabilistic model. It reads the test outcome vector for each facility (now 6 tests, with any Layer B override rows superseding the originals) and applies this rule:

```
verdict = phantom   IF any veto-capable test = FAIL
                    OR count(non-veto FAIL) >= 2

verdict = contested IF count(non-veto FAIL) == 1
                    OR count(tests with result != indeterminate) < 2

verdict = real      IF count(FAIL) == 0
                    AND count(PASS) >= 2
```

**Adjudicator input contract:** when reading test rows for a facility, if a row exists with `test_name = layer-b-override-pin` or `layer-b-override-spatial`, that row supersedes the original Test 1 or Test 3 row respectively. The original row is retained for audit but is not consumed by the Adjudicator. There is at most one override row per `(facility_id, test_family)` and Layer B writes them before the Adjudicator runs.

**Precedence is explicit:** the `< 2 testable results` condition (insufficient evidence → `contested`) is evaluated **before** the veto condition. This means a facility with a hard PIN veto but fewer than two testable results gets `contested/insufficient-evidence`, not `phantom`. This is intentional — the "absent data abstains" tenet means we do not amplify a single signal into a definitive verdict when the evidence base is too thin to be trustworthy. Implementers must evaluate `len(testable) < 2` first; the veto check runs only when there are enough testable results to support a phantom verdict.

**Evidence record:** Every verdict row in Lakebase includes the full test outcome vector — which test returned what result, and the supporting data row (India Post row, NFHS-5 district value, MinHash collision set, embedding-drift cosine value) for each failure.

**Adjudicator output is preserved separately from final verdict.** The Adjudicator's own output is written to `phantom_verdicts.adjudicator_verdict`. After the Adjudicator runs, Layer A may patch a `phantom` to `contested`; the post-Layer-A value is written to `phantom_verdicts.verdict`. When no Layer A patch occurs, `verdict` and `adjudicator_verdict` are equal. The dual-column shape preserves the rescue audit trail without losing the deterministic Adjudicator output.

**Contested verdicts trigger the AI Evidence Layer.** When the final verdict (after Layer A patching) is `contested`, the engine does *not* invoke the FMA escalation path inline. Instead, the contested verdict is persisted with `ai_recommendation = NULL` in `operational.phantom_verdicts`. The FMA call is deferred until the planner opens that facility's side panel in the Planner Workspace — at which point the AI Evidence Layer fires, the recommendation is generated, persisted, and rendered. This deferral keeps the batch pipeline LLM-free and concentrates all FMA cost on facilities the planner actually reviews.

## Existence Defender

The Defender runs after the Prosecutor produces its initial verdict set. For facilities initially marked `phantom`, the Defender looks for corroborating evidence that rescues them. The Defender owns three layers, all operating on data already in Lakebase — no external document mining, no network calls at runtime.

### Layer A: Structured-field corroboration (deterministic, post-Adjudicator)

Layer A runs **after** the Adjudicator has produced its verdict. It does not change test results; it adds external evidence the Adjudicator never saw and may patch the verdict from `phantom` down to `contested` if the evidence justifies softening. Layer A is the "outside corroboration" mechanic — it doesn't dispute what the tests showed; it adds context the tests can't see.

For each facility the Adjudicator marked `phantom`, check three deterministic rescue signals:
- **URL mentions in `description`** — count distinct external `http(s)://` URLs in the facility's `description` field. ≥2 distinct URLs to non-self-published domains is a rescue signal. (Self-published = the facility's own website, identified by the URL's domain matching tokens in the facility name; this is heuristic and tunable.)
- **HFR pre-cached snapshot match** — the facility name + spatial-join district match an entry in the pre-loaded Health Facility Registry snapshot (after lowercase + strip + Levenshtein ≤ 2 for minor spelling variance). HFR is a national government registry; a match is a strong rescue signal.
- **NFHS named-staff overlap** — if the facility's `description` lists named doctors or staff and one of those names also appears in the NFHS-5 district denominator data for the spatially-joined district, that is a corroborating signal.

Layer A rescue rule: patch verdict `phantom → contested` if (a) ≥2 distinct non-self-published URLs in description, OR (b) HFR snapshot match, OR (c) NFHS named-staff overlap. Layer A cannot upgrade to `real`.

Layer A records its action in `phantom_verdicts.rescue_applied` (JSONB) — a structured record of which signals fired. The Adjudicator's pre-rescue verdict is preserved separately in `phantom_verdicts.adjudicator_verdict`. This dual-column shape lets the side panel show the full rescue trace: *Adjudicator said phantom · Layer A signal X fired · final verdict: contested.*

This entire layer is deterministic Python. No LLM, no IE agent, no document parsing. The signals are rule-based pattern checks against fields already in Lakebase.

### Layer B: Dataset-version reconciliation (deterministic, pre-Adjudicator)

Layer B runs **before** the Adjudicator. It corrects wrong test inputs caused by data-currency mismatches: post-2022 district reorganization (Bapatla carved from Prakasam, NTR from Krishna) or spelling drift (Mysore↔Mysuru, Ahmadnagar↔Ahmednagar). Day-0 validation showed ~9pp of the raw 24.5% PIN-vs-spatial disagreement falls into this bucket — these are data errors, not phantom signals. Layer B is the "test was wrong, fix it" mechanic — distinct from Layer A's "test was right, but here's outside evidence" mechanic.

For each Test 1 (PIN reverse-lookup) or Test 3 (spatial district mismatch) failure, look up the facility's PIN-derived district and spatial-join district in a deterministic reconciliation table. If the disagreement is explained by a known reorganization or spelling variant, write an override row to `facility_existence_tests` with `test_name = layer-b-override-pin` or `test_name = layer-b-override-spatial`, with `result = pass` and `evidence_ref` citing the specific reorganization or variant matched. The Adjudicator's contract: when computing the test outcome vector, an override row supersedes the original test row for the same `(facility_id, test_name)` family. The original row is preserved for audit.

This layer is a deterministic lookup table. No LLM. The reconciliation table is loaded at batch start and applied before the Adjudicator runs.

### Layer C: FMA corroboration synthesis (Foundation Model API, activation-gated)

Layer C runs after the deterministic Adjudicator has produced its verdict. If that verdict is `contested` (and only then), the Defender invokes the Foundation Model API (`ai_query`) to synthesize a structured corroboration verdict. The FMA call's inputs are the data already in Lakebase:
- The six test outcome rows from `operational.facility_existence_tests` (each with its `evidence_ref` JSONB)
- The dataset-version reconciliation result from Layer B (matched / not-matched + matched-against)
- The structured-field corroboration result from Layer A (which signals fired, which didn't)
- The facility's `vf_facilities` row (description, capability, equipment, year established)

The FMA emits:
```
{
  "strength": "weak" | "medium" | "strong",
  "supporting_rows": [<test_outcome_row_ids and the layer-A signals that fired>],
  "reasoning": "<one paragraph natural-language reasoning>"
}
```

Models: `databricks-meta-llama-3-1-70b-instruct` primary, `databricks-mixtral-8x7b-instruct` fallback. Template-first generation as a fallback path so the pipeline cannot fail on LLM unavailability — the template emits `{strength: "weak", supporting_rows: <all row IDs>, reasoning: "<deterministic summary of which Layer A signals fired and what the test outcomes showed>"}`.

Activation gate: this layer fires when the final verdict (`phantom_verdicts.verdict`, post-Layer-A patching) is `contested`. This includes both facilities the Adjudicator alone marked `contested` AND facilities Layer A patched from `phantom` to `contested`. Expected hit rate: ~3% of all facilities. Cost gate: ≤ $1 for a full national scan. The Defender does not invoke FMA on `real` or `phantom` facilities.

### Layer ordering

The Defender's three layers run in a fixed order: **Layer B → Adjudicator → Layer A → Layer C**.
1. **Layer B** (pre-Adjudicator) writes test-result override rows for any PIN-vs-spatial disagreements explained by known district reorganizations or spelling variants. The Adjudicator sees a corrected test outcome vector.
2. The deterministic **Adjudicator** consumes the (possibly Layer-B-overridden) test outcome vector and emits its verdict. This verdict is written to `phantom_verdicts.adjudicator_verdict`.
3. **Layer A** (post-Adjudicator) evaluates structured-field corroboration on facilities the Adjudicator marked `phantom`. If a rescue signal fires, Layer A patches the final verdict to `contested` and records which signals fired in `phantom_verdicts.rescue_applied`. The Adjudicator's pre-rescue verdict is preserved in `adjudicator_verdict`.
4. **Layer C** fires only when the final verdict (after Layer A patching) is `contested`. Its output is advisory and feeds the AI Evidence Layer; it does not change the verdict.

The two mechanics are intentionally different because they serve different roles. Layer B says *"the test was wrong, here's the corrected result";* Layer A says *"the test was right, but here's outside evidence the test couldn't see."* Forcing both into one mechanic would muddy one or the other.

### Defender output rules

- **Layer B** writes test-result override rows; the Adjudicator consumes the corrected outcome vector. Original test rows are preserved.
- **Layer A** patches the verdict from `phantom → contested` post-Adjudicator if rescue signals fire; records the patch in `phantom_verdicts.rescue_applied`. The pre-rescue verdict is preserved in `phantom_verdicts.adjudicator_verdict`. Layer A never upgrades to `real`.
- **Layer C** does not change the verdict. It produces an advisory recommendation that becomes part of the AI Evidence Layer's escalation payload. The deciding action remains the planner's override.
- Only the deterministic Adjudicator's "all tests pass" path produces `real`.

## AI Evidence Layer (activation-gated)

The AI Evidence Layer is the contested-case escalation path. It is invoked only when:
1. The deterministic Adjudicator has produced `verdict = contested` for the facility, AND
2. A planner has opened that facility's side panel in the Planner Workspace.

Both conditions must hold. The first concentrates AI cost on the genuinely ambiguous ~3%. The second concentrates AI cost on facilities the planner actually reviews (avoiding paying to reason about contested facilities the planner never opens).

### What the layer produces

The layer assembles all evidence available for the facility:
- Six test outcome rows from `operational.facility_existence_tests`
- The Defender's Layer A structured-field corroboration result
- The Defender's Layer B dataset-version reconciliation result
- The Defender's Layer C corroboration synthesis (if produced)
- The planner's prior `force-real` / `force-phantom` notes for *similar* facilities (similarity defined as ≥0.8 cosine on description embeddings — uses the same embedding cache Test 6 reads)

It calls the Foundation Model API (`ai_query`) with this evidence package and emits an advisory recommendation:

```
{
  "recommendation": "force-real" | "force-phantom" | "evidence-too-thin",
  "confidence": "low" | "medium" | "high",
  "reasoning": "<one paragraph>",
  "cited_evidence_rows": [<test_outcome_row_ids and Layer A/B/C signal IDs>]
}
```

This is **advisory only**. The planner still clicks `force-real` or `force-phantom`. The recommendation is persisted in `operational.phantom_verdicts.ai_recommendation` (JSONB) so the same recommendation surfaces on reload — the layer never re-runs FMA on the same `(facility_id, evidence_state)` tuple.

### Fallback when FMA is unavailable

If `ai_query` returns an error or times out, the layer emits a **template fallback** with the same JSON shape:
- `recommendation`: `"evidence-too-thin"` if fewer than 3 testable signals; `"force-phantom"` if any veto-capable signal is present (PIN or spatial); `"evidence-too-thin"` otherwise
- `confidence`: always `"low"`
- `reasoning`: a deterministic summary of which tests fired and which Layer A signals fired
- `cited_evidence_rows`: all available row IDs

The Planner Workspace renders the recommendation identically whether it came from FMA or from the template — but stamps `source: "template-fallback"` in the side panel so the planner sees that AI was unavailable. The pipeline cannot fail on LLM availability.

### Cache key and lookup logic

The recommendation is keyed by an `evidence_state` content hash so the layer can detect when underlying evidence has shifted and a stale recommendation must be replaced. The cache key is:

```
evidence_state = sha256(
    canonical_json(test_outcome_vector)
    + adjudicator_verdict
    + canonical_json(rescue_applied or null)
)
```

Three fields, in fixed order. `verdict` is **deliberately excluded** from the hash because `verdict` mutates on planner override and we do not want the override path to invalidate the cache and trigger a fresh FMA call — once the planner has decided, the recommendation is historical context, not a live advisory.

When the planner opens a contested facility's side panel, the layer applies this lookup logic:

```
if phantom_verdicts.override_id IS NOT NULL:
    # Planner has already decided — never re-pay FMA after an override
    if ai_recommendation IS NOT NULL:
        render(ai_recommendation, marked "historical advisory")
    else:
        render(no recommendation panel; planner overrode without consulting AI)

elif ai_recommendation IS NULL:
    # First open of this contested facility
    rec = call_fma(evidence_package)
    UPDATE phantom_verdicts SET
        ai_recommendation = rec,
        ai_recommendation_evidence_state = current_evidence_state
    render(rec)

elif ai_recommendation_evidence_state == current_evidence_state:
    # Cache hit — render without FMA call
    render(ai_recommendation)

else:
    # Evidence has shifted (batch re-run, Layer B/A change) — recompute
    rec = call_fma(evidence_package)
    UPDATE phantom_verdicts SET
        ai_recommendation = rec,
        ai_recommendation_evidence_state = current_evidence_state
    render(rec)
```

The override gate is the topmost branch and dominates. The hash equality check is the cache-hit path; a hash mismatch is the only condition that triggers re-computation. Together they bound FMA cost at ≤ $0.50 per planner session in the demo profile (Maharashtra, ~9 contested facilities the planner is likely to open, each computed at most once).

**Concurrent writers:** if two planners open the same contested facility simultaneously, both may miss cache and both invoke FMA. Last-write-wins on the plain UPDATE — no advisory lock, no optimistic concurrency control. The race wastes ~$0.05 per collision (one duplicate FMA call) and the two recommendations are substantively equivalent given identical evidence. Adding lock contention would risk demo-time stalls (FMA timeout ~30s) for a $0.05 saving; not worth it.

**Override-races-FMA guard:** the FMA-result write re-reads `override_id` within the same transaction before committing the `ai_recommendation` UPDATE. If `override_id IS NOT NULL` at write time, the UPDATE is skipped — the planner overrode while the FMA call was in flight, so persisting the recommendation now would surface it on next reload as "historical advisory" even though it was computed *after* the override. The FMA call's cost is absorbed; the result is discarded. This is a one-line guard on the write, not a lock; it costs nothing in the no-race case.

**Similar-facility note scope:** the evidence package's similar-facility lookup (≥0.8 cosine) reads from `team.planner_overrides` across all `planner_id` values and all capabilities — not filtered to the current session. The override notes are institutional knowledge; one planner's reasoning on a similar facility is legitimate input for another's recommendation. Capability-scoping would miss cross-capability patterns (a force-real on a multi-capability facility informs both maternity and ICU views).

## Data Flow

```
Bronze (raw ingestion) → Silver (existence tests + verdicts) → Lakebase (operational)
                                                                    │
                                       ┌────────────────────────────┘
                                       │ contested verdicts (lazy)
                                       ▼
                            AI Evidence Layer (FMA, on planner open)
                                       │
                                       ▼
                            phantom_verdicts.ai_recommendation
```

**Bronze:** Append-only raw tables for VF records, India Post, NFHS-5, geoBoundaries, and the HFR pre-cached snapshot. No transforms.

**Silver:**
1. `facility_existence_tests` — one row per `(facility_id, test_name)` with `result`, `evidence_ref`, `ran_at`. Six test rows per facility (PIN, MinHash, spatial, NFHS, temporal, embedding-drift). Layer B may write override rows with `test_name = layer-b-override-pin` or `layer-b-override-spatial`; these supersede the originals when consumed by the Adjudicator.
2. `phantom_verdicts` — one row per `facility_id` with `adjudicator_verdict` (the deterministic Adjudicator's output), `verdict` (the final value after Layer A patching, mutable by planner override), `rescue_applied` (JSONB; which Layer A signals fired, null if none), `test_outcome_vector` (JSONB), `ai_recommendation` (JSONB, populated lazily for contested cases), `ai_recommendation_evidence_state` (VARCHAR, sha256 hex; the cache key under which `ai_recommendation` was generated), `override_id` (FK to `team.planner_overrides`, null until the planner overrides), `ran_at`.
3. `description_embeddings` — one row per `(facility_id, snapshot_id)` with the 384-dim sentence embedding as BYTEA + a pgvector index. Read at app start to power Test 6 cosine drift queries.

**Lakebase operational tables:**
- `operational.phantom_verdicts` — the CDC source for map redraw; mutable (Defender can update; AI Evidence Layer can populate `ai_recommendation`)
- `operational.facility_existence_tests` — detail view for the side panel
- `cache.claim_minhash` — MinHash signatures stored as BYTEA; computed once
- `cache.description_embeddings` — sentence embeddings stored as BYTEA + pgvector index; computed once per snapshot

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Duplicate detection algorithm | MinHash (128 perms, shingle 5) | TF-IDF cosine similarity; embedding distance | MinHash is O(n), token-free, and deterministic. Embedding distance requires LLM inference on 10k descriptions — violates the deterministic-core tenet. TF-IDF is viable but requires an IDF corpus that doesn't travel to a fresh notebook. MinHash is self-contained. |
| Veto architecture | PIN-mismatch and spatial-district-mismatch as hard vetoes | Weighted scoring | Hard veto makes the logic auditable — a judge or planner can follow the rule without statistical background. Weighted scoring hides its reasoning in coefficient values that can be reverse-engineered to favor any outcome. Note: the insufficient-evidence guard (< 2 testable results) takes precedence over the veto — a veto signal alone is not sufficient when the data is too sparse to support a confident verdict. |
| `build_pin_centroids` data guards | Explicit column-presence check + empty-DataFrame guard before `apply()` filters | No guard / crash on missing data | Day-0 validation (T0.2) catches column drift, but the implementation must not crash if called with an empty or differently-shaped DataFrame. Two separate guards are needed: (1) column existence — return `{}` if required columns are missing; (2) post-`dropna` empty check — skip `isinstance` filters if the DataFrame is already empty, since `apply()` on an empty object-typed column raises KeyError. |
| Batch vs. streaming | Offline batch before app starts (verdict layer); on-demand on planner open (AI Evidence Layer) | Streaming / CDC-driven live inference; LLM on every facility | Batch eliminates latency at query time and avoids Free Edition streaming limitations. The verdict layer reads a snapshot. The AI Evidence Layer escalation is on-demand — only when a planner opens a contested facility — concentrating LLM cost on facilities the planner actually reviews. |
| HFR integration | Pre-loaded snapshot in Lakebase | Live API at query time | Live API is blocked on Free Edition (network restrictions). Pre-loaded snapshot achieves the same test with zero runtime dependency. |
| Jaccard threshold | 0.9 (strict) | 0.75–0.85 (lenient) | At 0.9 the test is conservative — it will miss some phantoms but avoids false-positives on chain boilerplate. Threshold is a config value tunable per Day-0 validation results. |
| MinHash input field | `capability` + `procedure` + `equipment` concatenated | `description` field | Day-0: description p50 = 16 tokens — too short for Jaccard 0.9 + shingle-5. Structured-claim arrays are 99.7% populated, 10–20× richer, and contain the actual claim payload. Exact-match dedup on `capability` alone already groups 250 facilities into 92 near-identical clusters. |
| Test 6 mechanism | Embedding-drift cosine between snapshots (precomputed embeddings, cosine at verdict time) | Verdict-time embedding similarity (recompute on every batch); LLM-as-judge on each facility | Embedding-drift detects facilities silently *becoming* phantoms — a temporal pattern MinHash cannot see. Verdict-time embedding similarity would re-encode 10k descriptions on every batch (~2 min on CPU) for no signal gain over precomputed-and-cached. LLM-as-judge per facility would cost > $50 per scan and violate the activation-gate budget. Cosine on cached embeddings is O(n) and adds negligible batch time. |
| AI on contested verdicts | Foundation Model API `ai_query`, activation-gated to ~3% contested cases, on planner open | LLM-as-judge on every facility; LLM never (deterministic only); Information Extraction over external documents | Determinism handles the 97% obvious cases. AI earns its keep on the contested tail where reasoning over heterogeneous deterministic signals is required. Activation gate keeps full national scan ≤ $1; planner-open gate keeps demo cost ≤ $0.50 per session. The pipeline survives LLM unavailability via template fallback (same JSON shape, deterministic content). External-document IE was scoped out — no document-acquisition pipeline, no network calls at runtime, simpler build. |
| AI Evidence Layer write target | `phantom_verdicts.ai_recommendation` JSONB column | Separate table; in-memory only | Co-locating the recommendation with the verdict means the side-panel render is a single read. Cache key is `(facility_id, evidence_state)` — recomputed when underlying evidence changes. Separate table would be a join on every render. In-memory only would re-pay FMA cost on every page reload. |
| Defender Layer C output role | Advisory recommendation feeding the AI Evidence Layer's escalation payload | Layer C directly upgrades verdict | Verdict changes are the planner's job — the deterministic Adjudicator + planner override is the audit trail. Layer C as advisory keeps the override the deciding signal; the recommendation joins the evidence package the planner sees, rather than mutating the verdict invisibly. |
| Defender evidence sources | Already-loaded Lakebase data only (description URLs, HFR snapshot, NFHS named-staff overlap, dataset-version reconciliation table) | External document mining (district bulletins, RTI replies, news media) via Information Extraction | Document mining requires a data-acquisition pipeline (downloads, OCR, mention extraction across languages) that doesn't fit the L bucket and risks Free-Edition network restrictions. Already-loaded sources still give the Defender three deterministic rescue signals + the FMA Layer C call rich structured input — sufficient for the contested-case story without the build cost. |
| Defender rescue mechanic | Two mechanics, semantically asymmetric: Layer B writes test-result override rows pre-Adjudicator; Layer A patches the verdict post-Adjudicator | Single mechanic — both layers pre-Adjudicator (rescue rows treated as `pass`) OR both layers post-Adjudicator (verdict patches recorded in their own table) | The two layers do different things and forcing them into one mechanic muddies one or the other. Layer B *corrects wrong test inputs* (data-currency mismatches) — the honest fix is to overwrite the test result. Layer A *adds outside corroboration* the tests can't see (HFR match, etc.) — encoding that as a fake `pass` would be a semantic lie. Two columns on `phantom_verdicts` (`adjudicator_verdict` + `verdict`) preserve the rescue audit trail without losing the deterministic Adjudicator's output. |
| AI recommendation cache key | `sha256(test_outcome_vector + adjudicator_verdict + rescue_applied)`; override gate is a separate top-priority branch | Include `verdict` in the hash; cache in-memory only; recompute eagerly at batch time | Excluding `verdict` from the hash dodges the override-invalidation problem cleanly — once the planner overrides, `override_id IS NOT NULL` is checked first and skips FMA regardless of hash state. The two responsibilities (cache freshness vs. override authority) become two explicit lines instead of one tangled hash function. In-memory cache loses on reload. Eager batch computation wastes ~70% of FMA calls (most contested facilities never get opened in a 3-min demo). |

## Open Questions & Future Decisions

### Resolved
1. ✅ Defender can only upgrade `phantom → contested`, not `phantom → real`. Rationale: the Defender improves recall without creating a path for a facility to bypass all Prosecutor tests.

### Deferred
1. Whether to expose Jaccard threshold as a planner-configurable slider in the UI — deferred to post-MVP if Day-0 validation reveals threshold sensitivity.
2. Whether NFHS-5 Test 4 should also apply to ICU/trauma capability claims using an NCD indicator — deferred pending Tier 3 validation results.
3. **AI recommendation freshness w.r.t. recent similar-facility overrides.** The AI Evidence Layer cites the planner's prior `force-real` / `force-phantom` notes for *similar* facilities (≥0.8 cosine on description embeddings) as input to its recommendation. When the planner makes a new override on a similar facility mid-session, existing cached recommendations on other facilities don't refresh to incorporate it — the cache key intentionally excludes similar-facility notes because including them would invalidate every cached recommendation on every override (quadratic in similar-facility set size, breaks the cost gate). Acceptable for the 3-minute demo with one planner; revisit if used in a multi-session production setting where mid-session note staleness becomes user-visible.

## References

- `phantom_census_validation.md` — Day-0 tests that validate this component's data preconditions
- `docs/high-level-design.md` — system architecture and Adjudicator overview
- HFR public API: https://facility.abdm.gov.in (snapshot to be cached on Day 1)
