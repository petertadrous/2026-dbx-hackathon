# Proposal: Entity Resolution, Per-(Entity, Capability) Trust Grade, and Intra-Row Coherence (Test 7)

**Status:** draft for team review
**Date drafted:** 2026-06-16
**Branch:** `proposal/entity-resolution-trust-grade-test7` (off `updated-specs`)
**Scope:** **only** the net-new changes layered on top of `main`. Anything not listed here is preserved from `main` as-is.

---

## Context

A runaway loop in the engine-run notebook (cell 10, "desert score capability") was enumerating ~10,000 distinct "capabilities" because the bronze `capability` column is LLM-extracted freetext (full sentences, locations, statistics fragments) split on commas. Investigating that surfaced three connected correctness gaps that this proposal addresses:

1. **Wrong normalization source.** Bronze data contains a controlled clinical taxonomy in the `specialties` column (camelCase codes: `internalMedicine`, `cardiology`, `medicalOncology`, ~2,900 distinct codes with the top 50 covering ~90% of mentions). The current pipeline ignores `specialties` and parses the noisy `capability` freetext instead.

2. **No entity-level grouping.** Bronze rows that describe the same real-world facility (e.g., four directory snapshots of "St Anne Hospital" with different `numberDoctors`/`capacity`/`specialties`) are judged independently. Test 2 (MinHash near-duplicate) records `cluster_member_ids` in evidence, but no downstream code reads it — the cluster link is dead-letter data. Verdict counts double-count the same real entity, and the planner can't see the other directory snapshots when viewing a facility.

3. **No row-internal coherence check.** Tests 1, 3, and 5 catch *specific* intra-row contradictions (PIN↔GPS, year↔acuity), but there's no general check for contradictions like `0 doctors + 500 beds`, `50 specialties on a 5-bed clinic`, `"X Eye Hospital" tagged with cardiacSurgery`, or `recency_of_page_update = 2027-07-20` (future-dated).

### Status quo (already on `main`, not proposed)

Frontend is React/TS at `phantom-census-app/client/PlannerWorkspace.tsx`; the choropleth is a Folium HTML iframe with orange `CircleMarker` overlay on top-30 districts by `rank_shift` (the Raw/Adjusted toggle is already gone). Lakebase writes are direct psycopg2 via `notebooks/lakebase_load.py`. An "AI Field Verification Brief" (Llama 3.3 70B via FMA) is SSE-streamed to a per-district card. The existence engine has five tests in code (PIN, MinHash, spatial, NFHS, temporal) and a single `defender.py`. **All of this stays.**

---

## What this proposal proposes (the only net-new changes)

| # | Change | Layer | Why |
|---|---|---|---|
| 1 | **NEW segment: Entity Resolution** — blocked deterministic record linkage (lat/lon grid + pincode + source-id overlap blockers; name Jaro-Winkler + phone + website + geo distance + address matchers). Writes `operational.facility_entities (entity_id, facility_id, match_confidence, cluster_size)` via the same psycopg2 path Kai uses for the other tables. | HLD + new LLD | The MinHash `cluster_member_ids` from Test 2 is dead-letter today and is the wrong tool for entity identity anyway (chain hospital boilerplate creates false positives). Bronze data already carries identity signals; blocked deterministic linkage clusters in seconds on 10k rows with no LLM, ~200 LOC. |
| 2 | **NEW: Entity Verdict Rollup** rule, applied post-Adjudicator. entity-verdict = `REAL` if any cluster member is `real`; `PHANTOM` if all are `phantom`; `CONTESTED` otherwise. Materialized to `operational.facility_entity_verdicts`. Per-row verdicts stay in `phantom_verdicts` for audit. | existence-engine LLD | Without rollup, the same real-world entity is double-counted in desert scoring, and the React side panel can't surface "this entity has 4 directory snapshots; here's which one was the bad one." |
| 3 | **NEW: Test 7 (intra-row coherence)**, supporting-only, deterministic. Multi-field checks: `numberDoctors`/`capacity` ratio plausibility, specialty cardinality vs facility size, name-token vs specialty cluster, `recency_of_page_update` not future-dated or absent. Adds a vote to the Adjudicator and feeds the per-(entity, capability) trust grade. | existence-engine LLD | The row-integrity gap. Tests 1, 3, 5 catch specific intra-row contradictions but no general coherence check exists. |
| 4 | **CHANGE: Test 1 algorithm + role.** Replace centroid distance with **distance to nearest post office in the claimed PIN**. **Demote from veto to supporting** at the 50 km threshold. | existence-engine LLD | Centroid distance over-flags 13.5–19% of facilities at 50 km on the bronze data (16,388 of 19,561 PINs have multi-PO fan-out, p50 internal spread 15 km). Test 3 (district polygon mismatch) is the geographically correct veto — threshold-free, robust to fan-out. Nearest-PO tightens precision (p75 distance drops from 23 km to 4.6 km); supporting role prevents threshold noise from auto-condemning real facilities. |
| 5 | **CHANGE: Test 5 floor** lower to 1600; **replace hardcoded `HIGH_ACUITY_FOUNDING_CEILING = 2020`** with `ran_at.year - 5`. | existence-engine LLD | Madras General Hospital was founded 1664; SSKM Kolkata 1707; the pre-1900 floor false-positives real old hospitals. The relative high-acuity ceiling stays meaningful as time passes (a 2030 batch shouldn't treat 2025-founded ICUs as suspect). |
| 6 | **CHANGE: Test 4 framework.** Generalize from hardcoded maternity classifier to a `(capability_slug → indicator-check)` config registry. **Register maternity only** for the demo. | existence-engine LLD | Engineering is cheap (~50 LOC config + loop). NFHS-5 measures household-level outcomes, not facility supply, so non-maternity capabilities lack good NFHS indicators today. Framework hooks exist for when HMIS/RHS indicators are added. |
| 7 | **NEW: Capability normalization source change.** Switch the pipeline's capability extraction from the bronze `capability` freetext column (split on commas) to the bronze `specialties` controlled-vocabulary column, mapped through a hand-curated `code → canonical_slug` table for the top 50 codes. Long-tail codes drop to `other`. | existence-engine LLD + capability_taxonomy module | The runaway-loop root cause. `specialties` is already a clinical controlled vocab; top 50 codes cover ~90% of mentions. Hand-curated map is reviewable by a clinical SME, deterministic, no LLM. Substring matching on freetext (an earlier sketch) false-positives on phrases like *"no maternity wing."* |
| 8 | **NEW: Per-(entity, capability) trust grade** at the normalization layer. Grades STRONG / PARTIAL / WEAK / NO_CLAIM computed from (a) how many cluster members tag the capability, (b) Test 7 coherence outcome, (c) entity verdict. Stored as new columns on `operational.facility_capabilities`. | existence-engine + lakebase-persistence LLDs | Matches Hackathon Track 1's *"for each facility and capability, produce a trust signal"* framing. Lets a planner asking *"where are oncology gaps?"* see a real entity absent from oncology coverage when its oncology claim is weak. |
| 9 | **CHANGE: Desert-score counting.** Count `entity_id`s (not raw `facility_id`s) where `entity_verdict ≥ contested` AND per-(entity, capability) trust grade ≥ PARTIAL. | desert-scoring LLD + specs | Without entity-level counting, the same real-world entity is double-counted across its duplicate bronze rows. Without trust-grade filtering, a facility's weak claim contaminates the supply count for capabilities it doesn't really provide. |
| 10 | **NEW: Entity timeline + trust-grade badge** in the existing React `PlannerWorkspace.tsx` district side panel. Renders cluster members sorted by `recency_of_page_update`, each with verdict + source URLs, plus a trust-grade chip per (entity, capability) shown for the active capability. | planner-workspace LLD | Surfaces the previously-dead-letter cluster_member_ids data. Satisfies the hackathon's "cite the underlying text" requirement. No new view, no new tab — fits inside the existing side panel. |
| 11 | **NEW tenets** (3) added to HLD: *Linkage signals over text signals for entity identity*; *Per-row verdicts roll up to per-entity verdicts; the row trail is preserved*; *Trust grade per (entity, capability); existence verdict per entity*. | HLD | Each is a class-of-decisions tie-breaker whose opposite is defensible. Bodies in the [Tenets](#tenets-new-to-be-added-to-hld) section. |

Nothing else is proposed. The five existing tests (1–5) are unchanged for items not called out above. The Adjudicator rule is unchanged. The HLD frontend section needs a separate alignment pass to match main's React/Folium reality, but that's not this proposal's scope.

---

## Tenets (new, to be added to HLD)

### Linkage signals over text signals for entity identity

When deciding whether two rows describe the same real-world entity, the system uses identity signals — geographic coordinates, phone, website, source-id overlap, normalized name + address — not text-similarity signals. Text similarity catches chain hospital boilerplate as false positives that would collapse distinct facilities into one entity.

### Per-row verdicts roll up to per-entity verdicts; the row trail is preserved

When multiple rows describe one entity, each row receives its own existence verdict. The entity-level verdict is the rollup: REAL if any row is REAL; PHANTOM if all rows are PHANTOM; CONTESTED otherwise. Per-row verdicts persist for audit so the planner can see which directory snapshot was the bad one.

### Trust grade per (entity, capability); existence verdict per entity

Whether an entity exists and whether each of its capability claims is supported are two questions at two grains. The existence engine answers the first per entity; the normalization layer answers the second per (entity, capability) tuple, emitting STRONG / PARTIAL / WEAK / NO_CLAIM. Desert scoring counts an entity for a capability only when both grains pass.

---

## HLD additions (proposed prose — additions only, no alignment edits)

These additions land on top of whatever the HLD currently says. Separate from this proposal, the HLD's frontend / Lakebase / test-count sections need a sync pass with `main`'s current code — out of scope here.

### Approach — add new §5

> **5. Per-(entity, capability) trust grade.** Each capability an entity claims is independently evaluated. Trust grades — STRONG / PARTIAL / WEAK / NO_CLAIM — are computed at the normalization layer from three inputs: how many cluster members tag the capability, the per-row coherence test outcome, and the per-entity existence verdict. Desert scoring counts an entity for a capability only when its existence verdict is REAL or CONTESTED **and** its per-(entity, capability) trust grade is ≥ PARTIAL. This matches the Hackathon brief's "for each facility and capability, produce a trust signal" framing and lets a planner asking *"where are oncology gaps?"* see a real entity absent from oncology coverage when its oncology claim is unsupported.

### System Design diagram — insert two new boxes

Insert an Entity Resolution box between Bronze and the Existence Engine; insert an Entity Verdict Rollup step inside the Existence Engine box, after the Adjudicator. **(NEW)** marks the additions; everything else is the diagram already on main / branch.

```
                  ┌─ DATA INGESTION (Bronze) ─┐
                  └─────────────┬─────────────┘
                                ▼
              ┌─ ENTITY RESOLUTION (NEW; pre-engine) ─┐
              │ Blocked deterministic record linkage   │
              │ on identity signals → writes           │
              │ operational.facility_entities          │
              │ (entity_id, facility_id,               │
              │  match_confidence, cluster_size)       │
              └─────────────┬─────────────────────────┘
                                │ entity_id joined onto facilities
                                ▼
                  ┌─ EXISTENCE ENGINE ─────────────────────┐
                  │ Prosecutor: Tests 1–6 + NEW Test 7     │
                  │ (intra-row coherence). Defender.       │
                  │ Adjudicator → per-row verdict.         │
                  │                                        │
                  │ ┌─ Entity Verdict Rollup (NEW) ────┐   │
                  │ │ entity = REAL if any row REAL;   │   │
                  │ │ PHANTOM if all rows PHANTOM;     │   │
                  │ │ else CONTESTED                   │   │
                  │ └──────────────────────────────────┘   │
                  └─────────────┬─────────────────────────┘
                                │ phantom_verdicts (existing) +
                                │ facility_entity_verdicts (NEW) +
                                │ facility_capabilities (existing + NEW
                                │  trust_grade column)
                                ▼
                  ┌─ DESERT SCORING ──────────────────────┐
                  │ CHANGE: counts entities (not rows)    │
                  │ where entity_verdict ≥ contested AND  │
                  │ per-(entity, capability) trust grade  │
                  │ ≥ PARTIAL. raw + adjusted scores      │
                  │ otherwise unchanged.                  │
                  └─────────────┬─────────────────────────┘
                                ▼
                  ┌─ PLANNER WORKSPACE (React + Folium) ──┐
                  │ ADD inside existing side panel:       │
                  │ • Entity timeline (cluster members    │
                  │   sorted by recency_of_page_update)   │
                  │ • Trust-grade chip per (entity,       │
                  │   capability) for active capability   │
                  │ Everything else unchanged.            │
                  └───────────────────────────────────────┘
```

### Existence tests table — add row 7 and amend rows 1, 4, 5

Only the rows below land in the HLD. Rows for unchanged tests (MinHash, spatial-district-mismatch, embedding-drift) are not part of this proposal.

| Test | Proposed signal/behavior | Veto-capable | LLM? |
|---|---|---|---|
| PIN reverse-lookup | **CHANGE:** distance from facility GPS to **nearest** post office in its claimed PIN exceeds 50 km. | **CHANGE: No (supporting)** — was veto | No |
| NFHS-5 bottom-quartile | **CHANGE:** framework generalized to `(capability_slug → indicator-check)` config; demo registers maternity only. | No (supporting) | No |
| Temporal implausibility | **CHANGE:** `yearEstablished` outside `[1600, current_year]`; high-acuity check uses `ran_at.year - 5` as the founding ceiling instead of hardcoded 2020. | No (supporting) | No |
| **Intra-row coherence (NEW)** | Multi-field consistency: `numberDoctors`/`capacity` ratio plausibility, specialty cardinality vs facility size, name-token vs specialty cluster, `recency_of_page_update` not future-dated or absent | No (supporting) | No |

### Adjudicator section — add Entity Verdict Rollup paragraph

The existing per-row Adjudicator rule is unchanged. Add this paragraph below it:

> **Entity Verdict Rollup.** After the Adjudicator produces per-row verdicts: entity-verdict = `REAL` if any cluster member's row-verdict is `real`; `PHANTOM` if all cluster members' row-verdicts are `phantom`; `CONTESTED` otherwise. Per-row verdicts are preserved in `phantom_verdicts`; the entity-level verdict is materialized to `facility_entity_verdicts`.

### Key Design Decisions table — add 5 rows

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Entity resolution mechanism | Blocked deterministic record linkage on identity signals (lat/lon grid + pincode + source-id overlap blockers; name JW + phone + website + geo distance + address matchers) | MinHash text-similarity on claim arrays (reuse Test 2 clusters); probabilistic Splink; LLM pairwise judgment | Identity signals distinguish chain facilities that share boilerplate marketing text. MinHash collapses them. Blocked deterministic linkage runs in seconds on 10k rows, requires no LLM dependency, and is ~200 LOC. Splink is the off-the-shelf alternative if probabilistic calibration is later needed. |
| Verdict grain | Per-row verdict from the Adjudicator; per-entity rollup before downstream scoring | Single per-entity verdict from row-merge at ingest; per-row only (no rollup) | Per-row verdicts preserve audit trail and let some-real-some-phantom clusters be diagnosed at the side panel. Entity rollup is required for scoring to avoid double-counting one real-world entity. Row-merge at ingest masks intra-row contradictions before Test 7 can catch them. |
| Capability evidence grain | Per-(entity, capability) trust grade (STRONG / PARTIAL / WEAK / NO_CLAIM) | Per-facility existence verdict only; per-row trust grade | Matches the Hackathon brief's "for each facility and capability, produce a trust signal." Per-row is too granular for scoring; per-entity is the planner's actual unit. Existence-verdict-only conflates "facility exists" with "facility actually does X." |
| Capability normalization source | Bronze `specialties` controlled-vocabulary column (camelCase clinical codes) | Bronze `capability` freetext (split on commas); LLM classification; substring matching against canonical terms | Bronze already includes a clinical taxonomy in `specialties`; the top 50 codes cover ~90% of mentions. The `capability` freetext is LLM-extracted prose containing full sentences, locations, and statistics fragments — splitting yields tens of thousands of junk strings. Substring matching on freetext false-positives on phrases like "no maternity wing." LLM classification adds a dependency where a reviewed code → canonical-slug map serves life-safety better. |
| Test 1 verdict weight | Supporting (non-veto), with nearest-post-office distance algorithm (per facility's claimed PIN) | Veto, with PIN centroid distance (status quo on main); two-tier (supporting at 50 km, veto at 500 km) | Centroid distance over-flags 16,388 of 19,561 PINs with multiple post offices and a p50 internal spread of 15 km, producing 13.5–19% facility flag rates at 50 km — well above the baseline ~3% phantom rate. Test 3 (polygon mismatch) is the geographically correct veto: point-in-polygon is threshold-free. Test 1 with nearest-PO distance contributes evidence and a per-row distance value for the React side panel but cannot alone determine a verdict. |

### References — add one line

> - `docs/intent/entity-resolution/entity-resolution-design.md` — record linkage, entity_id, facility_entities table

### CLAUDE.md `## LID` block — add segment

> - `entity-resolution` — blocked deterministic record linkage; clusters bronze rows into real-world entities; writes `operational.facility_entities` consumed by the existence engine's verdict rollup and by desert scoring.

---

## Empirical evidence underpinning the decisions

### Capability normalization source (change #7)

Query against `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities`:

- **`specialties` column** parses as JSON array, 9,973 of 10,088 rows populated (99%), 2,928 distinct codes.
  - Top 60 codes (camelCase): `internalMedicine` (68k), `familyMedicine` (24k), `dentistry` (13k), `gynecologyAndObstetrics` (11k), `ophthalmology` (7.6k), `orthopedicSurgery` (7.3k), `pediatrics` (6.8k), `cardiology` (6.1k), `generalSurgery` (5.7k), `radiology` (5.5k), …
  - Long tail at the bottom: single-occurrence labels like `Lifestyle Diseases`, `attachment-partial-dentures`, `surgery` — OCR noise or directory-specific labels safe to drop.
- **`capability` column** is JSON array of LLM-extracted prose claims. Each row contains ~50 freetext sentences like *"Houses Gurgaon's first stroke centre"*, *"100% painless dental treatments"*, *"located in maternity road"*. Average length 1,248 characters per row. Splitting on commas (the current pipeline behavior) produces the runaway 10K+ distinct "capabilities" output.

### Test 1 algorithm (change #4)

Same query against the India Post PIN directory + facilities table:

- **India Post fan-out:** 16,388 of 19,561 distinct PINs have more than one post office (84% multi-PO). Median internal spread (centroid to farthest post office) is 15.4 km; p95 is 476 km (India-coordinate-filtered to remove garbage rows).
- **Facility distance distribution (centroid algorithm — current on main):** p50 = 3.75 km, p75 = 23 km, **p90 = 171 km**, p95 = 305 km, max = 2,349 km. **At 50 km threshold: 19.0% of facilities flagged.**
- **Facility distance distribution (nearest-PO algorithm — proposed):** p50 = 1.18 km, p75 = 4.61 km, p90 = 116 km, p95 = 247 km. **At 50 km threshold: 13.5% flagged.**

Either algorithm flags far above the baseline ~3% phantom rate, supporting the decision to demote Test 1 from veto to supporting regardless of which distance variant is used.

### Source provenance and freshness (change #3 and #10)

Each bronze row carries `source_ids`, `source_urls`, `recency_of_page_update` (date the source page was last updated — observed values from 2024 to 2027 inclusive; future dates are coherence-failure signals), and `post_metrics_most_recent_social_media_post_date`. These fields are currently unread. Test 7 uses `recency_of_page_update` plausibility; the entity timeline uses `source_urls` + `recency_of_page_update` to order cluster members.

---

## Merge mechanics

This branch will need a merge with `main` before the proposal can be implemented. The merge keeps everything `main` ships and layers in only the changes above. Concretely:

**Conflicts with `main` to resolve in favor of `main`:**
- `notebooks/existence_engine.py` — Kai's version has the circle-marker tile generation and recent fixes. The cell-10 capability extraction gets re-modified separately as part of change #7.
- `docs/intent/desert-scoring/desert-scoring-{design,specs}.md` — Kai added DS-TILE-005; this proposal does not touch desert-scoring's design beyond the entity-level counting change.
- `src/phantom_census/lakebase/writer.py` — Kai's psycopg2 path stays; new tables (`facility_entities`, `facility_capabilities` trust columns) extend it.
- `src/phantom_census/desert_scoring/tiles.py` — kept.

**Discarded from `updated-specs` (not in `main`, not part of this proposal):**
- `src/phantom_census/planner_workspace/shell.py`, `views/audit_view.py`, `views/budget_view.py`, `views/ai_advisory.py`, `views/genie_sidebar.py`, `geometry_loader.py`, `activation_gate.py`, `ai_advisory_render.py`, `budget.py`, `exports.py`, `fma_adapter.py`, `genie_scope.py` — the broken Streamlit refactor.
- Root `app.yaml` and root `databricks.yml` — Streamlit deploy targets; superseded by `phantom-census-app/{app,databricks}.yml` on main.
- `src/phantom_census/existence_engine/capability_taxonomy.py` (uncommitted) — substring-match sketch replaced by the `specialties`-based code → slug map.
- LP-SYNC-001..005 specs (synced-tables architecture) on `updated-specs` — Kai's psycopg2 path is canonical; these specs are marked deferred/post-hackathon.
- The AI Evidence Layer LID specs (`EE-AI-*`) on `updated-specs` — out of scope for this proposal; kept in the spec file but marked deferred. A separate proposal can advance them later.

**Kept from `updated-specs` to support this proposal:**
- `src/phantom_census/existence_engine/{layer_a,layer_b,layer_c,embedding_drift}.py` — backend engine improvements that compose cleanly under the new ER + Test 7 + rollup additions.
- The existence-engine + lakebase-persistence LID file updates that describe the Layer A/B/C split, embedding-drift Test 6, and the dual `adjudicator_verdict` / `verdict` schema. The new ER + Test 7 + trust grade specs layer on top.

**CI/CD:**
- `.github/workflows/databricks-deploy.yml` stays on this branch.
- Its deploy step is updated to point at `phantom-census-app/databricks.yml` (the working React bundle) instead of the root `databricks.yml` (the broken Streamlit bundle). One-line change in the workflow.

---

## What lands in code if this proposal is approved

1. HLD additions (Approach §5, system-diagram inserts, 4 amended test-table rows, Adjudicator rollup paragraph, 5 Key Design Decisions rows, 3 tenets, References, CLAUDE.md LID line)
2. New segment LLD + specs: `docs/intent/entity-resolution/entity-resolution-{design,specs}.md` (`ER` prefix)
3. Existence-engine LLD + specs updated for Test 1 nearest-PO + demote, Test 4 framework, Test 5 floor/ceiling, new Test 7, Entity Verdict Rollup, capability normalization source
4. Lakebase-persistence LLD + specs updated for `facility_entities` table, `facility_entity_verdicts`, trust-grade columns on `facility_capabilities`
5. Desert-scoring LLD + specs updated for entity-level counting + trust-grade filter
6. Planner-workspace LLD + specs updated to describe the entity timeline + trust-grade badge addition to the existing React side panel
7. CI workflow YAML one-line retarget to `phantom-census-app/databricks.yml`
8. Cross-segment edge audit run; findings surfaced for triage

No code changes ship until all the above are reviewed and accepted.

---

## Open questions for the team

1. Branch / PR strategy after approval: does this proposal merge into `updated-specs` first (and then `updated-specs` → `main`), or are we collapsing both onto `main` in one go?
2. Should the `planner-workspae` directory typo be renamed to `planner-workspace` as part of the LLD touch-up for that segment, or left as-is?
3. The HLD on `main` describes a Streamlit + Folium frontend with pre-rendered tile layers and CSS opacity swap, but the actual React app + circle-marker overlay diverges from that. This proposal does **not** include the HLD-alignment work for that divergence. Should a separate PR handle the alignment, or fold it in here?
4. The AI Evidence Layer specs (`EE-AI-*`) on `updated-specs` describe a per-contested-facility FMA escalation that hasn't shipped to `main`. Keep them as `[deferred]` in the existence-engine LLD or delete them outright?

---

## References

- `docs/high-level-design.md` — current HLD this proposal adds to
- `docs/intent/existence-engine/existence-engine-design.md`
- `docs/intent/desert-scoring/desert-scoring-design.md`
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md`
- `docs/intent/planner-workspae/planner-workspace-design.md`
- `phantom-census-app/client/src/pages/PlannerWorkspace.tsx` (canonical React UI on `main`)
- `phantom-census-app/server/routes/phantom-census-routes.ts` (AI Field Verification Brief route)
- `notebooks/lakebase_load.py` (canonical Lakebase write path on `main`)
- `Hackathon Instructions.md` — the four tracks and trust-signal framing this proposal aligns to
