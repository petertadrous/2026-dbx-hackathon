# Proposal: Entity Resolution, Per-(Entity, Capability) Trust Grade, and Intra-Row Coherence (Test 7)

**Status:** draft for team review
**Date drafted:** 2026-06-16
**Branch:** `proposal/entity-resolution-trust-grade-test7` (off `updated-specs`)
**Scope:** new backend segment + LID updates; **explicitly preserves Kai's React UI, Folium map, and psycopg2 Lakebase path from `main`**; no code lands until the doc changes are approved.

---

## Context

The current pipeline has three correctness gaps surfaced while investigating a runaway loop in the engine-run notebook (cell 10, "desert score capability") that enumerates ~10,000 distinct "capabilities" because the bronze `capability` column is LLM-extracted freetext (full sentences, locations, statistics fragments) split on commas.

The investigation surfaced three connected issues:

1. **Wrong normalization source.** Bronze data contains a controlled clinical taxonomy in the `specialties` column (camelCase codes: `internalMedicine`, `cardiology`, `medicalOncology`, ~2,900 distinct codes with the top 50 covering ~90% of mentions). The current pipeline ignores `specialties` and parses the noisy `capability` freetext instead.

2. **No entity-level grouping.** Bronze rows that describe the same real-world facility (e.g., four directory snapshots of "St Anne Hospital" with different `numberDoctors`/`capacity`/`specialties`) are judged independently. Test 2 (MinHash near-duplicate) records `cluster_member_ids` in evidence, but no downstream code reads it — the cluster link is dead-letter data. Verdict counts double-count the same real entity, and the planner can't see the other directory snapshots when viewing a facility.

3. **No row-internal coherence check.** Tests 1, 3, and 5 catch *specific* intra-row contradictions (PIN↔GPS, year↔acuity), but there's no general check for contradictions like `0 doctors + 500 beds`, `50 specialties on a 5-bed clinic`, `"X Eye Hospital" tagged with cardiacSurgery`, or `recency_of_page_update = 2027-07-20` (future-dated).

This proposal addresses all three at the HLD/LLD level. **No code lands until the doc changes are approved.**

### Merge context — main vs updated-specs

This branch was opened off `updated-specs`. Since then, `main` advanced significantly (Kai's work: React UI fixes, Folium map upgrades, AI Field Verification Brief, psycopg2 Lakebase migration). **Kai's app on `main` works end-to-end; the `updated-specs` Streamlit refactor is broken.** This proposal is explicitly scoped to compose cleanly on top of `main` so the merge outcome is *Kai's working UI over the backend changes here*.

What that means in practice:

- Frontend: **React/TypeScript** at `phantom-census-app/client/PlannerWorkspace.tsx`. Map = server-rendered **Folium HTML** embedded via `dangerouslySetInnerHTML` with Leaflet click/focus injected via `postMessage`. **No pydeck. No Streamlit.** The proposal's earlier pydeck data-prop swap and three-tab Streamlit structure are dropped.
- Map visualization: the Raw/Adjusted toggle has been replaced (commit `f4aaf8a`) with a single phantom-adjusted choropleth + orange `CircleMarker` overlay on top-30 districts by `rank_shift = raw_rank - adjusted_rank`. The "ghosts stay visible" tenet is now realized by the orange markers, not by a green/grey/yellow ScatterplotLayer.
- Lakebase: **direct psycopg2 writes** via `notebooks/lakebase_load.py` and `src/phantom_census/lakebase/writer.py`. Synced-table specs (LP-SYNC-001..005) on `updated-specs` are retired by this proposal as deferred/post-hackathon.
- AI advisory: Kai's new "AI Field Verification Brief" (Llama 3.3 70B via FMA, SSE-streamed to React) is district-grain, advisory-only, and stays as-is. The "AI Evidence Layer" (per-contested-facility FMA escalation) referenced in `updated-specs` LID specs is **out of scope for this proposal**; that work is independent and can land separately if pursued.
- Existence engine code: keep `updated-specs`'s Layer A/B/C split (`layer_a.py`, `layer_b.py`, `layer_c.py`) and `embedding_drift.py`. Kai's `defender.py` is replaced by these on merge.
- CI/CD: GitHub Actions (`.github/workflows/databricks-deploy.yml`) stays on this branch. **Deploy target switches** from the root `databricks.yml` (Streamlit, broken) to `phantom-census-app/databricks.yml` (React, working). Root `app.yaml` and root `databricks.yml` are retired.

A summary table of the reconciliation is in the [Merge plan](#merge-plan) section.

---

## Proposed decisions

| # | Decision | Why |
|---|---|---|
| 1 | Test 1 algorithm + role: **nearest-post-office** distance algorithm, **demote to supporting** (was veto), 50 km threshold | Centroid distance over-flags 13.5–19% of facilities at 50 km (centroid noise from 16,388 of 19,561 PINs having multi-post-office fan-out with p50 internal spread of 15 km). Test 3 (district polygon mismatch) is the geographically correct veto — threshold-free, robust to PIN fan-out. Nearest-PO algorithm tightens precision (p75 distance drops from 23 km to 4.6 km); supporting role lets it contribute evidence without amplifying threshold noise into auto-phantom verdicts. |
| 2 | Test 3 INDETERMINATE behavior: unchanged (does **not** veto) | Already correct in code; "absent data abstains" tenet preserved. |
| 3 | Test 4 framework: **generalize** to a `(capability_slug → indicator-check)` config; **register maternity only** for the demo | Engineering is cheap (~50 LOC config + loop). Real blocker is data: NFHS-5 measures household-level health outcomes, not facility supply. Maternity is uniquely well-served because institutional-delivery is a direct facility-use signal. For ICU, oncology, dialysis the available NFHS indicators are demand proxies, not supply signals. Framework hooks exist for when better indicators are added (HMIS, RHS). |
| 4 | Test 5 floor: lower to **1600**; replace hardcoded `HIGH_ACUITY_FOUNDING_CEILING = 2020` with `ran_at.year - 5` | Madras General Hospital was founded 1664; SSKM Kolkata 1707; the pre-1900 floor false-positives real old hospitals. 1600 is a defensive floor that no real Indian healthcare facility predates. The relative high-acuity ceiling stays meaningful as time passes (a 2030 batch run shouldn't treat 2025-founded ICUs as suspect). |
| 5 | Test 6: keep in schema/code, returns INDETERMINATE for all in single-snapshot demo | The hackathon dataset is one snapshot. Test 6 contributes nothing today but the schema (`snapshot_id`, `description_embeddings`) is correctly shaped for the multi-snapshot future. Leaving it in costs zero and demonstrates the architecture is forward-looking. **Note:** `main` does not yet have `embedding_drift.py` in code; merging `updated-specs`'s module brings it in, where it returns INDETERMINATE naturally. |
| 6 | **NEW: Test 7 (intra-row coherence)**, supporting-only | The row-integrity gap. Multi-field checks: `numberDoctors`/`capacity` ratio plausibility, specialty cardinality vs facility size, name-token vs specialty cluster, `recency_of_page_update` future-dated or absent. Same shape as Tests 4/5 — non-veto, no LLM, contributes a vote and feeds the per-(entity, capability) trust grade. |
| 7 | Adjudicator: **leave unchanged**. Communicate correlated-FAIL noise via side-panel `reason` field surfaced in React | The "≥2 supporting FAILs assumes independence" concern is real (Test 1 + Test 3 are correlated, Test 2 + chain boilerplate, etc.), but explicit test-grouping adds complexity for marginal demo gain. Surfacing each test's reason in the React `PlannerWorkspace.tsx` side panel lets the planner judge correlation themselves. Defer test-grouping to post-hackathon. |
| 8 | **NEW: Entity Resolution segment** — blocked deterministic record linkage | The MinHash cluster_member_ids data is dead-letter today, and MinHash is the wrong tool for entity identity anyway (chain boilerplate creates false positives). Source bronze data has the signals: lat/lon proximity, pincode, source_ids array overlap, phone, email, website, normalized name. Blocked deterministic record linkage (lat/lon grid + pincode + source-id overlap blockers; name JW + phone + website + geo distance + address matchers) clusters in seconds on 10k rows, no LLM, ~200 LOC. Writes `operational.facility_entities (entity_id, facility_id, match_confidence)` via **the same psycopg2 writer path Kai uses**. |
| 9 | **NEW: Entity Verdict Rollup** rule (post-Adjudicator) | After per-row Adjudicator verdicts: entity-verdict = REAL if any cluster member's row-verdict is `real`; PHANTOM if all are `phantom`; CONTESTED otherwise. Per-row verdicts persist for audit; the entity-level rollup is the unit consumed by desert scoring. The React side panel surfaces both grains. |
| 10 | Capability normalization source: bronze **`specialties`** column with hand-curated `code → canonical_slug` map for top 50 codes | The 10K-distinct-capabilities runaway loop's root cause. `specialties` is already a clinical controlled vocab; top 50 codes cover ~90% of mentions. Hand-curated map is reviewable by a clinical SME, deterministic, no LLM. Drops long-tail codes (`Lifestyle Diseases`, OCR noise) to `other`. Replaces the substring-match approach previously sketched at `src/phantom_census/existence_engine/capability_taxonomy.py` (uncommitted on `updated-specs`; discarded). |
| 11 | **NEW: Per-(entity, capability) trust grade** at the normalization layer | Each capability claim independently evaluated. Grades STRONG / PARTIAL / WEAK / NO_CLAIM computed from: (a) how many cluster members tag the capability, (b) Test 7 coherence outcome, (c) entity verdict. Matches Hackathon Track 1's "for each facility and capability, produce a trust signal" framing. Stored on `operational.facility_capabilities` as new columns. Desert scoring counts an entity for a capability only when entity-verdict ≥ CONTESTED AND trust-grade ≥ PARTIAL. |
| 12 | Cluster traceability in the React side panel: **entity timeline** | Surfaces the previously-dead-letter cluster_member_ids data. For an entity, the side panel shows all cluster members sorted by `recency_of_page_update`, each row's verdict + source URLs. Satisfies the hackathon's "cite the underlying text" requirement. Renders inside `PlannerWorkspace.tsx`'s existing district side panel — no new tab, no separate view. |
| 13 | Source-freshness as Test 7 input | Bronze has `recency_of_page_update` (date the source page was last updated) and `post_metrics_most_recent_social_media_post_date` (proxy for "facility is still active"). Currently unused. Test 7 flags future-dated/absent recency as a coherence failure; feeds the trust grade. |
| 14 | No row merging | Per-row Lakebase writes preserved. Aggregation happens at read time in scoring + UI. Merging would mask intra-row contradictions before Test 7 can catch them. |
| 15 | LLM usage unchanged from `main`: Kai's AI Field Verification Brief (district-grain, Llama 3.3 70B via FMA, advisory-only) stays | This proposal does **not** add the per-contested-facility "AI Evidence Layer" referenced in `updated-specs` LID specs — that work is out of scope here. The verdict/scoring path remains LLM-free (`token_usage: 0`); the Field Brief is district-grain advisory only and does not touch verdicts. |

---

## Tenets (new, to be added to HLD)

Three load-bearing decisions whose opposites are defensible:

### Linkage signals over text signals for entity identity

When deciding whether two rows describe the same real-world entity, the system uses identity signals — geographic coordinates, phone, website, source-id overlap, normalized name + address — not text-similarity signals. Text similarity catches chain hospital boilerplate as false positives that would collapse distinct facilities into one entity.

### Per-row verdicts roll up to per-entity verdicts; the row trail is preserved

When multiple rows describe one entity, each row receives its own existence verdict. The entity-level verdict is the rollup: REAL if any row is REAL; PHANTOM if all rows are PHANTOM; CONTESTED otherwise. Per-row verdicts persist for audit so the planner can see which directory snapshot was the bad one.

### Trust grade per (entity, capability); existence verdict per entity

Whether an entity exists and whether each of its capability claims is supported are two questions at two grains. The existence engine answers the first per entity; the normalization layer answers the second per (entity, capability) tuple, emitting STRONG / PARTIAL / WEAK / NO_CLAIM. Desert scoring counts an entity for a capability only when both grains pass.

---

## HLD edits (proposed prose)

### Approach §1 — replace

> **1. Multi-signal existence detection.** Each facility is tested against six independent existence signals plus one intra-row coherence signal — PIN-to-coordinates disagreement, near-duplicate detection on the structured-claim arrays (`capability` / `procedure` / `equipment`) via MinHash, spatial-join district inconsistency, NFHS-5 bottom-quartile inconsistency (scoped to maternity, extensible via a capability-indicator config), temporal footprint implausibility, embedding-cosine drift on `description` between snapshots, and intra-row coherence (multi-field consistency checks — `numberDoctors`/`capacity` ratio plausibility, specialty cardinality vs facility size, name-token vs specialty-cluster agreement, source-page freshness). Tests run per row under a deterministic Adjudicator with majority-with-veto logic; per-row verdicts roll up to per-entity verdicts before downstream scoring. **No LLM at the verdict or scoring layer.**

### Approach — add new §5

> **5. Per-(entity, capability) trust grade.** Each capability an entity claims is independently evaluated. Trust grades — STRONG / PARTIAL / WEAK / NO_CLAIM — are computed at the normalization layer from three inputs: how many cluster members tag the capability, the per-row coherence test outcome, and the per-entity existence verdict. Desert scoring counts an entity for a capability only when its existence verdict is REAL or CONTESTED **and** its per-(entity, capability) trust grade is ≥ PARTIAL. This matches the Hackathon brief's "for each facility and capability, produce a trust signal" framing and lets a planner asking *"where are oncology gaps?"* see a real entity absent from oncology coverage when its oncology claim is unsupported.

### System Design — replace ASCII diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION (Bronze)                          │
│  VF facility records · India Post PIN dir · NFHS-5 indicators           │
│  District shapefiles (geoBoundaries ADM2) · HFR pre-cached snapshot     │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ENTITY RESOLUTION (Silver, pre-engine)               │
│  Blocked deterministic record linkage on identity signals:              │
│  blockers (lat/lon grid · pincode · source_ids overlap) →               │
│  matchers (name JW · phone · website · geo distance · address)          │
│  → operational.facility_entities (entity_id, facility_id,               │
│    match_confidence, cluster_size) — written via psycopg2               │
└─────────────┬───────────────────────────────────────────────────────────┘
              │ entity_id joined onto facilities
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     EXISTENCE ENGINE (Silver)                           │
│  Prosecutor runs 7 tests per row:                                       │
│   1. PIN reverse-lookup (nearest-PO; supporting, no veto)               │
│   2. MinHash near-duplicate (supporting)                                │
│   3. Spatial district mismatch (veto-capable)                           │
│   4. NFHS-5 bottom-quartile (maternity-only; supporting)                │
│   5. Temporal implausibility (supporting)                               │
│   6. Embedding-drift cosine (supporting; INDETERMINATE in single-       │
│      snapshot demo)                                                     │
│   7. Intra-row coherence (NEW; supporting)                              │
│  Defender Layer B (pre-Adjudicator): dataset-version reconciliation     │
│  Defender Layer A (post-Adjudicator): structured-field corroboration    │
│           ↓                                                             │
│   Deterministic Adjudicator → per-row verdict                           │
│   (phantom / real / contested)                                          │
│           ↓                                                             │
│   Entity Verdict Rollup                                                 │
│   entity = REAL if any row REAL; PHANTOM if all rows PHANTOM;           │
│   CONTESTED otherwise                                                   │
└─────────────┬───────────────────────────────────────────────────────────┘
              │ phantom_verdicts (per row) +                              │
              │ facility_entity_verdicts (per entity) +                   │
              │ facility_capabilities (per entity, capability, trust)     │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DESERT SCORING (Gold)                                │
│  Per-district recompute via incremental override callback (psycopg2)    │
│  Counts entities (not rows) where entity_verdict ≥ contested AND        │
│  per-(entity, capability) trust grade ≥ PARTIAL                         │
│  desert_scores: raw_desert_score, adjusted_desert_score, rank_shift     │
│  Leverage weights: mortality_burden × population × phantom_density      │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│            PLANNER WORKSPACE (Databricks App — React/TS)                │
│  phantom-census-app/client/PlannerWorkspace.tsx                         │
│  • Folium-rendered choropleth (server-side HTML, iframe-embedded)       │
│    Single phantom-adjusted view with red intensity by                   │
│    adjusted_desert_score                                                │
│  • Orange CircleMarker overlay: top-30 districts by rank_shift          │
│    (radius ∝ rank shift; "ghosts stay visible" tenet)                   │
│  • District side panel shows: per-entity verdict · per-(entity,         │
│    capability) trust grade badge · entity timeline (cluster members     │
│    sorted by recency_of_page_update) · evidence chips                   │
│  • AI Field Verification Brief (Llama 3.3 70B via FMA; SSE-streamed     │
│    from phantom-census-app/server/routes/) per-district advisory        │
│  • Override panel writes team.planner_overrides via API route           │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       LAKEBASE (Operational State)                      │
│  Postgres-compatible; written via psycopg2 from notebooks               │
│  operational.facility_entities · operational.phantom_verdicts ·         │
│  operational.facility_entity_verdicts · operational.desert_scores ·     │
│  operational.facility_existence_tests · operational.facility_capabilities│
│  cache.claim_minhash · cache.description_embeddings                     │
│  team.planner_overrides · team.saved_scenarios · team.budget_allocations│
└─────────────────────────────────────────────────────────────────────────┘
```

### "Existence tests" table — replace with 7 rows

| Test | Signal | Veto-capable | LLM? |
|---|---|---|---|
| PIN reverse-lookup | Facility GPS-to-nearest-post-office distance for its claimed PIN exceeds 50 km | No (supporting) | No |
| MinHash near-duplicate | `capability` / `procedure` / `equipment` (concatenated) Jaccard ≥ 0.9 with ≥2 other facilities | No (supporting) | No |
| Spatial district mismatch | PIN-claimed district ≠ spatial-join-assigned district | **Yes (hard veto)** | No |
| NFHS-5 bottom-quartile inconsistency | Claimed maternity capability but district NFHS-5 institutional-delivery rate in bottom quartile for state. Framework registers one indicator-check per canonical capability; demo registers maternity only. | No (supporting) | No |
| Temporal implausibility | `yearEstablished` outside `[1600, current_year]`, combined with high-acuity claims when founded within the last 5 years | No (supporting) | No |
| Embedding-drift cosine | `description` embedding cosine drifts ≥ threshold from prior snapshot. INDETERMINATE for all facilities in the single-snapshot demo. | No (supporting) | Embeddings precomputed; verdict-time math is cosine only |
| **Intra-row coherence** | Multi-field consistency: `numberDoctors`/`capacity` ratio plausibility, specialty cardinality vs facility size, name-token vs specialty cluster, `recency_of_page_update` not future-dated or absent | No (supporting) | No |

### Adjudicator rule paragraph — replace

> **Per-row Adjudicator rule:** row-verdict = `phantom` when any veto-capable test fails OR ≥2 non-veto tests fail (insufficient-evidence guard takes precedence; see existence-engine LLD). Row-verdict = `contested` when exactly 1 non-veto test fails. Row-verdict = `real` when 0 tests fail and ≥2 tests pass.
>
> **Entity Verdict Rollup:** entity-verdict = `REAL` if any cluster member's row-verdict is `real`; `PHANTOM` if all cluster members' row-verdicts are `phantom`; `CONTESTED` otherwise. Per-row verdicts are preserved in `phantom_verdicts`; the entity-level verdict is materialized to `facility_entity_verdicts`. The React side panel renders both grains.

### Key Design Decisions table — add five rows

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Entity resolution mechanism | Blocked deterministic record linkage on identity signals (lat/lon grid + pincode + source-id overlap blockers; name JW + phone + website + geo distance + address matchers) | MinHash text-similarity on claim arrays (reuse Test 2 clusters); probabilistic Splink; LLM pairwise judgment | Identity signals distinguish chain facilities that share boilerplate marketing text. MinHash collapses them. Blocked deterministic linkage runs in seconds on 10k rows, requires no LLM dependency, and is ~200 LOC. Splink is the off-the-shelf alternative if probabilistic calibration is later needed. |
| Verdict grain | Per-row verdict from the Adjudicator; per-entity rollup before downstream scoring | Single per-entity verdict from row-merge at ingest; per-row only (no rollup) | Per-row verdicts preserve audit trail and let some-real-some-phantom clusters be diagnosed at the side panel. Entity rollup is required for scoring to avoid double-counting one real-world entity. Row-merge at ingest masks intra-row contradictions before Test 7 can catch them. |
| Capability evidence grain | Per-(entity, capability) trust grade (STRONG / PARTIAL / WEAK / NO_CLAIM) | Per-facility existence verdict only; per-row trust grade | Matches the Hackathon brief's "for each facility and capability, produce a trust signal." Per-row is too granular for scoring; per-entity is the planner's actual unit. Existence-verdict-only conflates "facility exists" with "facility actually does X." |
| Capability normalization source | Bronze `specialties` controlled-vocabulary column (camelCase clinical codes) | Bronze `capability` freetext (split on commas); LLM classification; substring matching against canonical terms | Bronze already includes a clinical taxonomy in `specialties`; the top 50 codes cover ~90% of mentions. The `capability` freetext is LLM-extracted prose containing full sentences, locations, and statistics fragments — splitting yields tens of thousands of junk strings. Substring matching on freetext false-positives on phrases like "no maternity wing." LLM classification adds a dependency where a reviewed code → canonical-slug map serves life-safety better. |
| Test 1 verdict weight | Supporting (non-veto), with nearest-post-office distance algorithm (per facility's claimed PIN) | Veto, with PIN centroid distance (original); two-tier (supporting at 50 km, veto at 500 km) | Centroid distance over-flags 16,388 of 19,561 PINs with multiple post offices and a p50 internal spread of 15 km, producing 13.5–19% facility flag rates at 50 km — well above the baseline ~3% phantom rate. Test 3 (polygon mismatch) is the geographically correct veto: point-in-polygon is threshold-free. Test 1 with nearest-PO distance contributes evidence and a per-row distance value for the React side panel but cannot alone determine a verdict. |

### References — add one line

> - `docs/intent/entity-resolution/entity-resolution-design.md` — record linkage, entity_id, facility_entities table

### CLAUDE.md `## LID` block — add segment

> - `entity-resolution` — blocked deterministic record linkage; clusters bronze rows into real-world entities; writes `operational.facility_entities` consumed by the existence engine's verdict rollup and by desert scoring.

---

## Empirical evidence underpinning the decisions

### Capability normalization source (decision #10)

Query against `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities`:

- **`specialties` column** parses as JSON array, 9,973 of 10,088 rows populated (99%), 2,928 distinct codes.
  - Top 60 codes (camelCase): `internalMedicine` (68k), `familyMedicine` (24k), `dentistry` (13k), `gynecologyAndObstetrics` (11k), `ophthalmology` (7.6k), `orthopedicSurgery` (7.3k), `pediatrics` (6.8k), `cardiology` (6.1k), `generalSurgery` (5.7k), `radiology` (5.5k), …
  - Long tail at the bottom: single-occurrence labels like `Lifestyle Diseases`, `attachment-partial-dentures`, `surgery` — OCR noise or directory-specific labels safe to drop.
- **`capability` column** is JSON array of LLM-extracted prose claims. Each row contains ~50 freetext sentences like *"Houses Gurgaon's first stroke centre"*, *"100% painless dental treatments"*, *"located in maternity road"*. Average length 1,248 characters per row. Splitting on commas (the current pipeline behavior) produces the runaway 10K+ distinct "capabilities" output.

### Test 1 algorithm (decision #1)

Same query against the India Post PIN directory + facilities table:

- **India Post fan-out:** 16,388 of 19,561 distinct PINs have more than one post office (84% multi-PO). Median internal spread (centroid to farthest post office) is 15.4 km; p95 is 476 km (India-coordinate-filtered to remove garbage rows).
- **Facility distance distribution (centroid algorithm — current):** p50 = 3.75 km, p75 = 23 km, **p90 = 171 km**, p95 = 305 km, max = 2,349 km. **At 50 km threshold: 19.0% of facilities flagged.**
- **Facility distance distribution (nearest-PO algorithm — proposed):** p50 = 1.18 km, p75 = 4.61 km, p90 = 116 km, p95 = 247 km. **At 50 km threshold: 13.5% flagged.**

Either algorithm flags far above the baseline ~3% phantom rate, supporting the decision to demote Test 1 from veto to supporting regardless of which distance variant is used.

### Source provenance and freshness (decisions #6, #12, #13)

Each bronze row carries:
- `source_types` (JSON array, ~30–50 entries: `["dynamic","overture","constant","mongo_facility",…]`)
- `source_ids` (parallel array, e.g. Overture hex IDs `08f42d99986e2b6d…`)
- `source_urls` (parallel array, one URL per claim)
- `recency_of_page_update` (date the source page was last updated — observed values from 2024 to 2027 inclusive; the latter is a coherence-failure signal)
- `post_metrics_most_recent_social_media_post_date`
- `yearEstablished`
- `snapshot_id` / `ran_at` (engine batch — added by the existence engine, not bronze)

The first three give us multi-source provenance for the entity timeline in the React side panel. The next two give us source freshness signals for Test 7. The bronze row is already a merge — the array shape proves the upstream aggregator already linked multiple sources per facility; the entity-resolution stage we propose runs *on top of* that pre-existing aggregation to link across facility_ids.

---

## Merge plan

The merge of `main` into this branch (or this branch into `main`) reconciles two divergent histories. The intended outcome: **Kai's working React UI + Folium map + psycopg2 Lakebase, layered with the backend engine work from `updated-specs` and the new additions from this proposal.**

### What comes from `main` (Kai — kept as-is)

| File / area | Status |
|---|---|
| `phantom-census-app/client/**` (React/TS UI) | **Kept verbatim.** The working frontend. |
| `phantom-census-app/server/routes/phantom-census-routes.ts` | **Kept verbatim.** Hosts the AI Field Verification Brief SSE route. |
| `phantom-census-app/{app,databricks}.yml` | **Kept verbatim.** Canonical deploy bundle. |
| `notebooks/lakebase_load.py` | **Kept verbatim.** Canonical Lakebase write path (psycopg2). |
| `notebooks/existence_engine.py` (Kai's circle markers + Folium tile generation) | **Kept verbatim.** Note: the runaway-loop cell 10 that triggered this investigation is in this file on both branches and will need to be replaced with the `specialties`-based normalization on top of Kai's version. |
| `src/phantom_census/desert_scoring/tiles.py` | **Kept.** Folium tile generation + DS-TILE-005 completeness guard. |
| `src/phantom_census/lakebase/writer.py` (Kai's null-byte stripping + psycopg2 path) | **Kept.** Extended to write new `facility_entities` and trust-grade columns. |
| `docs/intent/desert-scoring/desert-scoring-{design,specs}.md` (Kai's DS-TILE-005 addition) | **Kept.** This proposal does not modify these — DS-TILE-005 stands. |
| `docs/data-quality-notes.md`, `docs/user-guide.md` | **Kept.** |

### What comes from `updated-specs` (yours — kept)

| File / area | Status |
|---|---|
| `src/phantom_census/existence_engine/layer_a.py`, `layer_b.py`, `layer_c.py` | **Kept.** Replaces Kai's single `defender.py`. |
| `src/phantom_census/existence_engine/embedding_drift.py` | **Kept.** Test 6 module (returns INDETERMINATE in single-snapshot demo). |
| `src/phantom_census/existence_engine/ai_evidence_layer.py` | **Kept as code** but **not featured in this proposal**. Out-of-scope for the spec updates here; if pursued separately, it lives alongside Kai's Field Verification Brief at a different grain. |
| Other `existence_engine/` updates (adjudicator dual-verdict, types, pipeline) | **Kept.** Backend engine improvements compose cleanly. |
| `docs/intent/existence-engine/existence-engine-{design,specs}.md` (Defender Layer A/B/C, EE-EMBED-*, EE-LAYER-*, adjudicator dual-verdict) | **Kept**, with this proposal layering ER + Test 7 + verdict rollup + capability source change + Test 1 demotion + Test 5 floor on top. AI Evidence Layer specs (EE-AI-*) remain in the file but are not advanced by this proposal. |
| `docs/intent/lakebase-persistence/lakebase-persistence-{design,specs}.md` (Adjudicator dual-verdict columns, rescue_applied, override_id schema, facility_capabilities, budget_allocations) | **Kept**, this proposal adds `facility_entities` + trust-grade columns on top. |
| `docs/intent/planner-workspae/planner-workspace-{design,specs}.md` | **Materially revised by this proposal**: the three-tab Streamlit + pydeck architecture is retired; the LLD is rewritten to describe the React/Folium frontend on `main` (with the entity timeline + trust-grade badge additions from this proposal). |
| `.github/workflows/databricks-deploy.yml` | **Kept** — your CI stays canonical. **Deploy target retargeted** from root `databricks.yml` to `phantom-census-app/databricks.yml`. |

### What gets discarded from `updated-specs` (yours — dropped)

| File / area | Reason |
|---|---|
| `src/phantom_census/planner_workspace/shell.py`, `views/{audit_view,budget_view,ai_advisory,genie_sidebar,geometry_loader,...}.py`, `activation_gate.py`, `ai_advisory_render.py`, `budget.py`, `exports.py`, `fma_adapter.py`, `genie_scope.py` | The Streamlit refactor that doesn't work end-to-end. The React app on `main` is the canonical UI. |
| Root `app.yaml` | Targets Streamlit; replaced by `phantom-census-app/app.yaml`. |
| Root `databricks.yml` | Targets Streamlit bundle; replaced by `phantom-census-app/databricks.yml`. |
| `src/phantom_census/existence_engine/capability_taxonomy.py` (uncommitted) | The substring-match approach this proposal replaces with the `specialties`-based map. |
| LP-SYNC-001..005 specs in `lakebase-persistence-specs.md` | Synced-tables architecture retired. Note as "deferred / post-hackathon" in the spec rather than deleted, since the gold Delta tables still exist (they're just not synced to Lakebase). Lakebase writes go through `writer.py` (psycopg2). |
| Streamlit-era LLD content in `docs/intent/planner-workspae/planner-workspace-design.md` (three-tab structure, pydeck `GeoJsonLayer` / `ScatterplotLayer`, `st.session_state['view']` toggle) | Replaced by the React/Folium architecture description on `main`. |

### What gets added (this proposal)

| Artifact | Where | Status after this proposal |
|---|---|---|
| HLD prose changes (Approach §1 rewrite, new §5, system diagram, 7-row test table, Adjudicator rule, five Key Design Decisions rows, References, three tenets) | `docs/high-level-design.md` | Replaces the existing HLD on `main` content equivalents. |
| `entity-resolution` segment | `docs/intent/entity-resolution/entity-resolution-design.md` + `entity-resolution-specs.md` | New segment; `ER` prefix. |
| Test 7 (intra-row coherence) | New section in `docs/intent/existence-engine/existence-engine-design.md` + new `EE-COHERE-*` specs | Adds to existing 6-test structure. |
| Test 1 nearest-PO + demote; Test 5 floor 1600 + dynamic ceiling; Test 4 capability-indicator config | Updates to `EE-PIN-*`, `EE-TEMP-*`, `EE-NFHS-*` | Mutate existing specs in place. |
| Verdict rollup rule | New section in existence-engine LLD + new `EE-ROLLUP-*` specs | Materializes `operational.facility_entity_verdicts` table. |
| `operational.facility_entities` table | Schema in `lakebase-persistence-design.md` + new `LP-SCHEMA-ENTITY-*` specs | Written via psycopg2 by entity-resolution stage. |
| Trust-grade columns on `facility_capabilities` (`trust_grade`, `supporting_facility_ids`, `evidence_recency_date`) | Schema in `lakebase-persistence-design.md` + new specs | Written via psycopg2 by normalization stage. |
| Capability normalization source change (specialties not freetext) | Pipeline section in existence-engine LLD + updated spec | The notebook cell 10 stops being a runaway loop. |
| Entity timeline + trust-grade badge in React side panel | New section in `planner-workspace-design.md` + new `PW-PANEL-*` specs | Describes the new content in the existing React side panel — not a new view. |
| CLAUDE.md `## LID` block | Add `entity-resolution` line | Already drafted above. |

### CI/CD retarget

After merge, the deploy chain is:

```
GitHub push → .github/workflows/databricks-deploy.yml
   → databricks bundle deploy --bundle-config-file phantom-census-app/databricks.yml
      → deploys the React app (Kai's working bundle)
```

Concretely, the workflow's `databricks bundle deploy` invocation should be updated to point at `phantom-census-app/databricks.yml` instead of the root `databricks.yml`. This is one line in the workflow YAML.

---

## What lands when this proposal is approved

1. HLD prose changes committed to `docs/high-level-design.md`
2. `## LID` block update in `CLAUDE.md`
3. New segment LLD drafted: `docs/intent/entity-resolution/entity-resolution-design.md` + `entity-resolution-specs.md`
4. Existence-engine LLD + specs updated for Test 1 demotion, Test 4 framework, Test 5 floor/ceiling, Test 6 noted as INDETERMINATE-in-demo, new Test 7, entity verdict rollup, capability normalization source change
5. Lakebase-persistence LLD + specs updated for `facility_entities` table, `facility_entity_verdicts`, trust-grade columns on `facility_capabilities`; LP-SYNC-001..005 marked deferred/post-hackathon
6. Desert-scoring LLD + specs updated for entity-level counts + trust-grade filter (DS-TILE-005 from Kai preserved)
7. Planner-workspace LLD + specs rewritten to describe the React/Folium frontend on `main`, with the entity timeline + trust-grade badge additions
8. CI workflow YAML updated to deploy `phantom-census-app/databricks.yml`
9. Cross-segment edge audit run; findings surfaced for triage

No code changes ship until all the above are reviewed and accepted.

## What gets discarded as part of this proposal

- The substring-matching `src/phantom_census/existence_engine/capability_taxonomy.py` file (currently uncommitted on `updated-specs`) — replaced by the `specialties`-based code → canonical slug mapping approach.
- The Streamlit refactor in `src/phantom_census/planner_workspace/` (shell.py, audit_view.py, budget_view.py, ai_advisory.py, genie_sidebar.py, etc.) — superseded by Kai's React app on `main`.
- Root `app.yaml` and root `databricks.yml` (Streamlit deploy targets) — superseded by `phantom-census-app/`'s bundle.
- LP-SYNC-001..005 specs (synced-tables architecture) — retired in favor of Kai's psycopg2 path.

## Open questions for the team

1. Branch / PR strategy after approval: does this proposal merge into `updated-specs` first (and then `updated-specs` → `main`), or are we collapsing both onto `main` in one go?
2. Should the `planner-workspae` directory typo be renamed to `planner-workspace` as part of the LLD rewrite for that segment, or left as-is to keep this proposal focused?
3. Empirical validation of the parameters inherited from the existing design (MinHash 128 perms / shingle 5 / Jaccard 0.9 / cluster ≥3 / 30-token guard; embedding-drift threshold 0.4) is currently absent from the docs — surfaced earlier but deferred. Should the spec updates include a section flagging which existing parameters lack documented empirical justification?
4. The AI Evidence Layer specs (`EE-AI-*`) on `updated-specs` describe a per-contested-facility FMA escalation that hasn't shipped to `main` and is out of scope for this proposal. Should those specs be deleted, marked deferred, or left in place pending a separate proposal?

---

## References

- `docs/high-level-design.md` — current HLD this proposal modifies
- `docs/intent/existence-engine/existence-engine-design.md`
- `docs/intent/desert-scoring/desert-scoring-design.md`
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md`
- `docs/intent/planner-workspae/planner-workspace-design.md` (to be substantially rewritten for the React/Folium frontend)
- `phantom-census-app/client/src/pages/PlannerWorkspace.tsx` (canonical React UI on `main`)
- `phantom-census-app/server/routes/phantom-census-routes.ts` (AI Field Verification Brief route)
- `notebooks/lakebase_load.py` (canonical Lakebase write path on `main`)
- `Hackathon Instructions.md` — the four tracks and trust-signal framing this proposal aligns to
