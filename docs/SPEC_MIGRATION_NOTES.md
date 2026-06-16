# Spec Migration Notes — code review required

This note accompanies the spec updates. It lists exactly which existing `@spec` annotations in the codebase point at requirements whose **meaning changed** or whose **ID was deleted**. Read top to bottom before merging the spec changes into a code-update PR.

The companion commit "specs: revert wording-only churn" already removed ~25 cosmetic edits, so the only spec text changes you'll see here are real behavior changes.

## Annotations that changed meaning under a stable ID

These IDs still exist but the requirement text was rewritten. Code annotated with these IDs needs a re-read against the new spec text to confirm the implementation still satisfies it.

### Critical — ID kept, meaning *inverted*

The most dangerous case: `git blame` on the annotation gives no signal that the underlying spec was rewritten to a different requirement.

| ID | Old meaning | New meaning | File |
|---|---|---|---|
| **LP-INIT-004** | Create `cache.tile_layers` with composite PK on `(capability, layer_type)` | Create pgvector cosine index `idx_description_embeddings_cosine` on `cache.description_embeddings.embedding` | `persistence/schema.py:47` |
| **LP-OVR-003** | UPDATE `desert_scores` for affected district (recompute path) | Preserve `adjudicator_verdict`, `rescue_applied`, `ai_recommendation`, `ai_recommendation_evidence_state` unchanged when LP-OVR-002 executes | `persistence/override_writes.py:34` |
| **PW-OVR-003** | Write the override row to `team.planner_overrides` (single INSERT) | Execute the full 3-step write sequence in order: INSERT planner_overrides → UPDATE phantom_verdicts → fire desert-score recompute callback | `workspace/override.py:16` |

For the LP-OVR re-shuffle, the requirement that *was* LP-OVR-003 is now **LP-OVR-004**. If the existing code at `persistence/override_writes.py:34` updates `desert_scores`, change the annotation to `LP-OVR-004` and add a separate function (or assertion) that satisfies the new LP-OVR-003 (preservation of the AI/rescue columns).

### Same ID, refined behavior — verify implementation still matches

| ID | Change | File |
|---|---|---|
| **EE-HASH-001** | Cache table renamed `cache.description_minhash` → `cache.claim_minhash` | `existence_engine/minhash.py` — rename the table reference |
| **EE-SPATIAL-001** | Adds contract: write the matched `shapeID` as canonical `district_id` onto the facility row | `existence_engine/spatial.py` — confirm the spatial join writes `shapeID` to a column the rest of the pipeline reads as `district_id` |
| **EE-PIPE-001** | "five existence tests" → "six existence tests" | pipeline orchestration — wire in the new Test 6 (embedding-drift) |
| **EE-PIPE-002** | PK changes to `(facility_id, test_name, ran_at)` | schema + writes — add `ran_at` to the PK tuple |
| **EE-PIPE-003** | `phantom_verdicts` columns expanded to dual-verdict shape (`adjudicator_verdict`, `verdict`, `rescue_applied`, `test_outcome_vector`, …) | schema — add the new columns; writes — populate `adjudicator_verdict` separately from `verdict` |
| **EE-ADJ-001..007** | Restructured for six tests, dual-column writes, Layer B input contract. EE-ADJ-008/009 added (write `adjudicator_verdict` separately; persist 6-test outcome vector) | `existence_engine/adjudicator.py` — re-read text, confirm: (a) reads any `layer-b-override-*` rows in place of originals, (b) writes both `adjudicator_verdict` and `verdict` columns, (c) handles 6 tests not 5 |
| **DS-SCORE-001/002/003** | Composite PK `(district_id, capability)`; `district_id` = geoBoundaries `shapeID` | `desert_scoring/scoring.py` — change keying from `district_id`-only to composite |
| **DS-OVR-001..004** | Mechanism inverted: Folium tile re-render → pydeck data-prop swap. Callback ownership flipped to desert-scoring module (called *by* the workspace, not embedded in it) | `desert_scoring/override_recompute.py` — re-read; the function may need to expose itself as a callback the workspace imports rather than a side effect |
| **LP-EE-002** | `overwrite any prior row` → `UPSERT batch-owned columns only; preserve ai_recommendation, ai_recommendation_evidence_state, override_id across re-batch` | `persistence/existence_writes.py:20` — the write must explicitly skip the AI/override columns on re-batch |
| **LP-EE-003** | Cache table renamed (same as EE-HASH-001) | `persistence/existence_writes.py:30` — change target table to `cache.claim_minhash` |
| **LP-APP-002** | Row ordering: "ordered by `adjusted_desert_score` descending" → "ranked by leverage (mortality_burden × population × phantom_density)"; also reads more columns (`adjudicator_verdict`, `verdict`, `rescue_applied`, `ai_recommendation`, `override_id`) | `persistence/app_reads.py:18` — change ORDER BY clause and SELECT list |
| **PW-PANEL-002** | "5 example phantom facilities" → "5 phantom-verdicted *or contested* facilities, leverage-ranked, collapsed-by-default" | `workspace/panel.py` — broaden the filter from phantom-only to phantom-or-contested; add leverage sort; default rows to collapsed |
| **PW-OVR-001** | Panel content list expanded: now also shows `adjudicator_verdict`, `rescue_applied` summary, AI advisory summary | `workspace/override.py:9` — extend the panel render |
| **PW-OVR-002** | Reason note required (unchanged behavior, wording polish) | `workspace/override.py` — no code change required |
| **PW-OVR-004** | Verdict badge update (unchanged behavior; now references `force-real-planner`/`force-phantom-planner` enum values from LP-SCHEMA-VERDICT-002) | `workspace/override.py` — confirm enum values used in the badge match new schema |

## Deleted IDs — annotations are stranded

These IDs are removed from the spec files. Code annotations citing them no longer resolve. Each row tells you what to do.

### Stranded annotations and migration

| Deleted ID(s) | Code annotated with them | Migration |
|---|---|---|
| **DS-TILE-001, DS-TILE-001a, DS-TILE-002, DS-TILE-003, DS-TILE-004** | `desert_scoring/tiles.py` (entire file: module-level `@spec` block + 3 inline annotations) | The Folium tile-pre-rendering mechanism is replaced by pydeck data-prop swap (DS-MAP-001..003). The `tiles.py` module is **obsolete** — delete it. The new pydeck render lives in the planner-workspace segment, not desert-scoring. Tests citing `DS-TILE-*` should be deleted alongside. |
| **EE-DEF-001, EE-DEF-002, EE-DEF-003, EE-DEF-004, EE-DEF-005** | `existence_engine/defender.py` (module-level `@spec` block + inline annotation) | The single-mechanism Defender is replaced by three layers with different mechanics. Migrate as follows: (1) if the existing `defender.py` patches `phantom_verdicts.verdict` from `phantom` to `contested` based on URL count or HFR match → rename annotations to **EE-LAYER-A-001..008** (Layer A: post-Adjudicator structured-field corroboration, JSONB rescue trace). (2) If `defender.py` writes a `defender-rescue` row to `facility_existence_tests` → **delete that write per EE-LAYER-A-008**; the rescue trace now lives only in `phantom_verdicts.rescue_applied` JSONB. (3) Add new modules `existence_engine/layer_b.py` (dataset-version reconciliation, pre-Adjudicator, writes test-row overrides) and `existence_engine/layer_c.py` (FMA corroboration synthesis, activation-gated) for the new EE-LAYER-B-* and EE-LAYER-C-* specs. |

### Tests citing deleted IDs

`grep -rn "@spec.*DS-TILE\|@spec.*EE-DEF" phantom_census/tests/` — delete those test cases (the behavior is replaced, not refactored). New tests for DS-MAP-*, EE-LAYER-A/B/C-*, and EE-EMBED-* will be written in Phase 5.

## Net-new IDs — no conflicts; new modules pick these up

These IDs are wholly additive. No existing `@spec` annotation in the codebase clashes with them. Treat them as work-to-do for new modules.

- **EE-EMBED-001..007** — new module `existence_engine/embedding_drift.py` (Test 6)
- **EE-LAYER-B-001..006** — new module `existence_engine/layer_b.py`
- **EE-LAYER-C-001..005** — new module `existence_engine/layer_c.py`
- **EE-AI-001..012** — new module `existence_engine/ai_evidence_layer.py`
- **EE-ADJ-008, EE-ADJ-009** — extend existing `existence_engine/adjudicator.py`
- **DS-SCORE-006** — `max_facility_count_per_km2` constant computation; in `desert_scoring/scoring.py`
- **DS-MAP-001..003** — pydeck data-prop swap contract; rendered in planner-workspace, not desert-scoring
- **DS-OVR-005, DS-OVR-006** — additive guards; extend `desert_scoring/override_recompute.py`
- **DS-MULTICAP-001..003** — new function in `desert_scoring/override_recompute.py` for multi-capability iteration
- **DS-RANK-004, DS-RANK-005** — additive; extend `desert_scoring/ranking.py`
- **LP-INIT-005, LP-INIT-006** — new tables (`cache.description_embeddings`, `team.budget_allocations`)
- **LP-SCHEMA-VERDICT/TEST/DESERT/EMBED/BUDGET-*** — schema contracts; extend `persistence/schema.py`
- **LP-EE-005** — atomic-commit contract; extend `persistence/existence_writes.py`
- **LP-RESCUE-001/002** — new write path; new module `persistence/rescue_writes.py`
- **LP-AI-CACHE-001..005** — new write path; new module `persistence/ai_cache_writes.py`
- **LP-APP-004/005/006** — additive; extend `persistence/app_reads.py`
- **LP-OVR-005/006** — additive guards; extend `persistence/override_writes.py`
- **LP-SCEN-005** — additive; extend `persistence/scenario_writes.py`
- **PW-SHELL-001..006**, **PW-TAB-001..003** — new app-shell layout
- **PW-MAP-001..006** — new pydeck render module (replaces the old Folium-tile-driven render)
- **PW-PANEL-005** — additive (AI trigger gate)
- **PW-AI-001..005** — new AI Advisory block component
- **PW-OVR-006/007** — additive
- **PW-BUDGET-001..007** — new view; new module
- **PW-AUDIT-001..005** — new view; new module
- **PW-GENIE-001..004** — new sidebar component
- **PW-EXP-004/005** — additive

## Recommended order of operations for the code-update PR

1. **Apply the spec commits** (this set, including this migration note).
2. **Run a coverage check** on the existing `@spec` annotations:
   ```bash
   grep -rEho "@spec [A-Z]+-[A-Z]+-[0-9a-z]+" phantom_census/src phantom_census/tests \
     | sort -u | while read tag id; do
         grep -q "\\*\\*$id\\*\\*" phantom_census/docs/intent/*/*-specs.md || echo "STRANDED: $id"
       done
   ```
   Expected stranded set: `DS-TILE-001, DS-TILE-001a, DS-TILE-002, DS-TILE-003, DS-TILE-004, EE-DEF-001..005`.
3. **Walk the "Critical — meaning inverted" table** (LP-INIT-004, LP-OVR-003, PW-OVR-003). Re-read the new spec text and adjust the implementation.
4. **Walk the "Same ID, refined behavior" table.** Each row has a one-line file pointer.
5. **Walk the deletions** (DS-TILE-*, EE-DEF-*) and apply the migrations above.
6. **Implement the net-new IDs** in new modules (Phase 5/6 work).
