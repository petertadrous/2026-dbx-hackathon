---
parent: high-level-design
prefix: PW
---

# Planner Workspace

## Context and Design Philosophy

The Planner Workspace is the Databricks App (Streamlit + pydeck) that state planning commissioners and NGO program officers interact with. It presents the choropleth, the facility scatter, the district drill-down with AI advisory, the override panel, the Budget Reallocation view, the Audit Queue view, the Genie NL sidebar, and the export controls.

The design constraint is: **zero training needed for a non-technical user to grasp the demo in 3 minutes.** The cleaned phantom-adjusted map is *infrastructure*; what the planner walks away with is three deliverables — a revised allocation CSV, an inspector worksheet PDF, and a saveable scenario. Three views, three deliverables, one workflow.

The workspace has no analysis-mode navigation, no configuration panels, no settings tabs. It is a workflow split into three named views, navigable by tabs.

**AI is on screen but never in the verdict math.** When the planner opens a `contested` facility's side panel, the AI Evidence Layer fires (lazy, on-demand) and renders an advisory recommendation with reasoning. The planner still clicks `force-real` or `force-phantom`. *Determinism owns the math; AI owns the reasoning over evidence; the human owns the decision* — that line is shown, verbatim, in the closing footer.

The frontend stack is **Streamlit + pydeck (deck.gl)**, locked Day-1. Pydeck's GPU-rendered layers handle 706 districts + 10k facility scatter without lag, the toggle is a data-prop swap not a re-render, and click handlers route into `st.session_state` cleanly. Folium was rejected because Leaflet-DOM can't carry the facility scatter density; Gradio was rejected because it has no first-class map. See HLD § Decisions for full rationale.

## Three-View Structure

The app is one Streamlit page with three tabs. The state-shared elements (capability dropdown, sidebar) sit above the tabs; each view renders below.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Phantom Census    Capability: [Maternity ▼]                                  │
│  Activation gate: 9 contested · est. cost ≤ $0.04                              │
│  ─────────────────────────────────────────────────────────────────────────── │
│  [Map]  [Budget Reallocation]  [Audit Queue]                                  │
│  ═══════════════════════════════════════════════════════════════════════════ │
│  ┌─ active view content ───────────────────────────────────┐  ┌─ Genie ─────┐│
│  │                                                          │  │  NL chat    ││
│  │                                                          │  │  over       ││
│  │                                                          │  │  Lakebase   ││
│  │                                                          │  │             ││
│  └──────────────────────────────────────────────────────────┘  └─────────────┘│
│  Footer: "Determinism owns the math; AI owns the evidence; human owns the decision."
└──────────────────────────────────────────────────────────────────────────────┘
```

Tab content is exclusive (only one view rendered at a time). The Genie sidebar persists across all three tabs. The activation-gate badge in the header reads from `phantom_verdicts` and counts facilities with `verdict = contested`; cost estimate is `count × $0.005` (per-FMA-call estimate).

**Tab-switch state preservation.** Per-tab state (e.g., the Map view's `selected_district` and `selected_facility`; the Audit Queue's scroll position and pagination cursor; the Budget Reallocation view's any in-progress edits) is keyed by tab name in `st.session_state` (`st.session_state['map']`, `st.session_state['audit_queue']`, `st.session_state['budget']`). Switching away from a tab and back restores the prior state. Shared state — `view`, `capability`, override side effects on `phantom_verdicts` and `desert_scores` — is keyed at the top level and visible to all tabs.

**Capability dropdown enum source.** The dropdown's options are populated dynamically from `SELECT DISTINCT capability FROM operational.desert_scores` at app load and cached in `st.session_state['available_capabilities']`. This means the enum reflects what the batch pipeline actually scored — adding a new capability (e.g., `icu`) to the batch automatically surfaces it in the dropdown without app code changes. For the demo, the only capability scored is `maternity`; the dropdown displays one option and is disabled when only one capability is available.

## View 1 — Map

The wow toggle. Choropleth + facility scatter + side panel.

```
┌────────────────────────────────────────────┬─────────────────────────────────┐
│  [Raw] [Adjusted ●]                         │  BEED District                  │
│                                             │  Adjusted desert score: 0.84    │
│  MAHARASHTRA CHOROPLETH (pydeck             │  Raw score: 0.61 → Rank: 10→2   │
│   GeoJsonLayer, fill = active score)        │                                 │
│                                             │  PHANTOM EXAMPLES (3 shown,     │
│  10K FACILITY SCATTER (pydeck               │  leverage-weighted)             │
│   ScatterplotLayer):                        │  ● Phantom A (force-phantom):   │
│   ✅ green dot = real                        │    PIN says Aurangabad,         │
│   👻 grey ghost = phantom                    │    GPS says Solapur (148km off) │
│   ⚠️ yellow = contested                      │    [India Post row ↗]           │
│                                             │  ● Phantom B (force-phantom):   │
│  [click any district →]                     │    capability cluster of 14     │
│                                             │  ● Phantom C (CONTESTED):       │
│                                             │    NFHS bottom-quartile fail    │
│                                             │    ┌─ AI Advisory ────────────┐ │
│                                             │    │ Rec: force-phantom        │ │
│                                             │    │ Confidence: medium        │ │
│                                             │    │ Reasoning: "PIN mismatch  │ │
│                                             │    │   survives, no HFR match, │ │
│                                             │    │   embedding cosine 0.71." │ │
│                                             │    │ [cited rows ↗]            │ │
│                                             │    └───────────────────────────┘ │
│                                             │                                 │
│                                             │  [Override] [Save Scenario]     │
└────────────────────────────────────────────┴─────────────────────────────────┘
```

**Toggle behavior:** the `[Raw] [Adjusted]` toggle changes `st.session_state['view']`, which the `GeoJsonLayer.get_fill_color` callback reads. The `ScatterplotLayer.get_fill_color` is *unchanged* by the toggle — facility dots keep their verdict-derived color in both views. The dataset's claimed facilities don't disappear; the scoring just stops counting phantoms.

**Phantom ordering in the side panel:** facilities are listed by leverage-weighted ranking — `mortality_burden_percentile × population_proxy × phantom_density` — so the most-impactful phantoms surface first (per cross-pollinated mechanism #5 from the proposal).

**AI Advisory block:** rendered only for facilities whose `verdict = contested`. **Triggers the AI Evidence Layer on row-expand, not on side-panel open** — when a planner clicks a district on the choropleth, the side panel opens with all 3 phantom rows collapsed (each row showing only the facility name, verdict badge, and top-failed-test summary). The AI Evidence Layer fires only when a planner expands a contested row to see its full detail. This per-row-expand trigger keeps cost discipline tight: a district with 3 contested phantoms doesn't burn 3× FMA cost on side-panel open; it pays one FMA call when (and if) the planner actually expands a row. Per-row expansion follows the existence-engine LLD's lookup logic (cache hit, override gate, evidence_state hash). Shows the recommendation, confidence, reasoning, and cited evidence rows. If FMA was unavailable, the block displays the template-fallback output identically but stamps `(template fallback)` next to the confidence label.

## View 2 — Budget Reallocation

The "so where does the money actually go?" deliverable. Reads `team.budget_allocations` (planner's prior-quarter ₹ allocation per district) joined to `desert_scores` (current adjusted ranking) and shows the gap as a re-allocation recommendation.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Q3 2026 · Maternity · ₹50 Cr quarterly budget                              │
│                                                                             │
│  ┌─ Before ───────────┐    ┌─ Recommended ──────┐                           │
│  │   (pie chart of    │ →  │   (pie chart of    │                           │
│  │    current ₹       │    │    re-allocated ₹  │                           │
│  │    by district)    │    │    by district)    │                           │
│  └───────────────────-┘    └────────────────────┘                           │
│                                                                             │
│  RECOMMENDED ₹ SHIFTS (sorted by mortality burden × phantom_density)        │
│  ──────────────────────────────────────────────────────────────────         │
│   District       Current     →   Recommended    Δ                           │
│   ──────────     ───────         ───────────    ────                        │
│   BEED           ₹2.0 Cr     →   ₹4.5 Cr        +₹2.5 Cr                    │
│   Latur          ₹1.8 Cr     →   ₹3.6 Cr        +₹1.8 Cr                    │
│   Osmanabad      ₹1.5 Cr     →   ₹3.2 Cr        +₹1.7 Cr                    │
│   Ahmadnagar     ₹6.0 Cr     →   ₹3.5 Cr        −₹2.5 Cr                    │
│   …                                                                         │
│                                                                             │
│  [Export revised allocation CSV]                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Recommendation algorithm (deterministic, in-process):** sort districts by current `adjusted_desert_score × NFHS-5 burden weight × population_proxy`, descending. Compute each district's *fair share* of the total quarterly ₹ as `total_budget × normalized_score / sum(normalized_scores)`. The recommended ₹ for each district is `min(fair_share, prior_allocation × 2.5)` — capped at 2.5× the prior allocation to avoid politically-implausible swings. The delta column shows the ₹ shift from prior to recommended. No LLM in this view.

**Export:** `Export revised allocation CSV` writes a CSV to a configured S3 prefix with columns `district_id, district_name, current_inr, recommended_inr, delta_inr, justification` where `justification` is a one-line string referencing the adjusted desert score and current rank. The CSV is the deliverable; the recommendation is *not* written back to `team.budget_allocations` (that table holds historical allocations only).

**Refresh on override:** when a planner override mutates `desert_scores` for a district in scope of the recommendation, the recommendation table re-sorts in real time. The pie charts re-render. If the override changes a district's recommended-allocation rank by ≥3 positions, that row briefly highlights to draw attention.

## View 3 — Audit Queue

The "who do my inspectors visit Monday?" deliverable. Reads `phantom_verdicts` filtered to `verdict = phantom`, joined to `desert_scores` for the leverage weight, and presents the top-50 inspector worksheet.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Top-50 facilities to audit — Q3 2026 · Maternity                           │
│  Sorted by leverage = mortality_burden × population × phantom_density       │
│                                                                             │
│  Rank  Facility                District   PIN      GPS         Failed tests│
│  ────  ─────────────────────   ────────   ──────   ──────────   ──────────  │
│  1     Beed Maternity #4       BEED       431122   18.99,75.76  PIN, MNH, NFHS │
│  2     Latur Memorial Hosp.    Latur      413512   18.41,76.58  PIN, SPA      │
│  3     Yedshi PHC              Osmanabad  413710   18.13,75.94  MNH, NFHS, TMP│
│  …                                                                          │
│  [Export inspector worksheet PDF]                                           │
└────────────────────────────────────────────────────────────────────────────┘
```

**Leverage formula (per cross-pollinated mechanism #5):** `leverage = mortality_burden_percentile × population_proxy × phantom_density(district)`, where `mortality_burden_percentile` comes from NFHS-5, `population_proxy` is the district's facility count baseline, and `phantom_density` is `phantom_count / district_area_km2` from `desert_scores`. A facility's leverage is its district's leverage — same value across all phantoms in the same district. Tie-breaks by `phantom_verdicts.test_outcome_vector` count of failed tests (more fails = higher rank).

**Why leverage-weighted, not detection-time-sorted:** generic implementations sort the audit queue alphabetically or by detection time. That sends inspectors to convenient phantoms, not to the phantoms whose verification matters most. Leverage-weighting ensures the top of the queue is the highest mortality-impact gap.

**Export:** `Export inspector worksheet PDF` produces a print-ready PDF: one row per facility with the district, PIN, GPS coordinates, and a checkbox list of the failed tests (so an inspector on the ground can mark off what they verified physically). The PDF is generated in-process via `reportlab` or similar; no external service calls.

**Live refresh on override:** when the planner overrides a facility (Map view), the audit queue rebuilds — overridden-to-real facilities drop out of the queue, overridden-to-phantom facilities are inserted. The queue rebuild is one SQL query against `phantom_verdicts.verdict = phantom`; sub-second on the demo dataset.

## Genie Sidebar

**Rendered as Streamlit's left-rail `st.sidebar`** (not the right-edge column shown in the structure diagram, which is illustrative). The diagram is laid out for spatial clarity; in the actual app, `st.sidebar` is the standard Streamlit convention and persists across tabs natively without custom CSS. The sidebar is collapsible per Streamlit's default behavior.

Always-visible NL chat over `desert_scores`, `phantom_verdicts`, `team.budget_allocations`, and `team.planner_overrides`. Lets a non-technical commissioner ask ad-hoc questions that no pre-baked view will cover ("which 5 districts gain the most rank from subtraction?", "show me budget shifts > ₹5 Cr", "what overrides did I make today?"). Genie writes SQL inline and renders a chart.

**SQL access scope** (an explicit allowlist, not a database-wide grant):
- READ on `operational.desert_scores` — the planner's primary lens
- READ on `operational.phantom_verdicts` (all columns including `verdict`, `adjudicator_verdict`, `rescue_applied`, `ai_recommendation`, `override_id`)
- READ on `operational.facility_existence_tests` — for "show me facilities that failed test X" type questions
- READ on `team.budget_allocations` — for budget-shift questions
- READ on `team.planner_overrides` — for "what did I override today?" questions
- READ on `vf_facilities` (description, capability, lat/lon, name) — for facility-attribute lookups

**NOT in scope:** WRITE access to any table; READ on `cache.claim_minhash` or `cache.description_embeddings` (binary, not useful for NL); READ on `team.saved_scenarios` (audit-only, not exposed for NL).

This is the one place an LLM owns the user-facing experience. It does not touch the verdict path; it is read-only against the operational tables. The deterministic-core claim is unaffected.

## Cross-segment data contracts

What the Planner Workspace owns vs. consumes:

**Owned (assembled in this segment, in the Streamlit app load path):**
- `districts_df` — the join of `geoBoundaries` (geometry) + `desert_scores` (scores) keyed on the geoBoundaries `shapeID`. Loaded once at app open into `st.session_state['districts_df']`. Mutated in-place on override-recompute callbacks (one row, scoped to the affected district).
- `facilities_df` — the join of `vf_facilities` (lat/lon, name, capability) + `phantom_verdicts.verdict` (verdict, override_id) keyed on `facility_id`. Loaded once at app open. Used by `ScatterplotLayer` to render the green/ghost/yellow dots. Mutated in-place on override save (one row, the affected facility).
- The `st.session_state` keys for view (`'view'` ∈ {`raw`, `adjusted`}), capability (`'capability'`), and active tab (`'tab'`).
- The AI Evidence Layer trigger logic — the click handler on a contested facility's side panel checks `phantom_verdicts.override_id` and `phantom_verdicts.ai_recommendation_evidence_state`, then fires FMA per the existence-engine LLD's lookup logic.

**Consumed (read from upstream segments):**
- `operational.phantom_verdicts` (existence engine writes; this segment reads in five fields per row: `adjudicator_verdict`, `verdict`, `rescue_applied`, `ai_recommendation`, `override_id`)
- `operational.facility_existence_tests` (existence engine writes; this segment reads on side-panel evidence-chip expansion)
- `operational.desert_scores` (desert-scoring writes; this segment reads at app load for `districts_df` and on every override-recompute)
- `team.budget_allocations` (Lakebase persistence loads from CSV at setup; this segment reads at Budget Reallocation view render)
- `cache.description_embeddings` (existence engine writes once per snapshot; this segment reads at app start to power the AI Evidence Layer's similar-facility lookup)

**Written (writes back to upstream segments):**
- `team.planner_overrides` (this segment INSERTs on override save)
- `operational.phantom_verdicts.verdict` + `override_id` (this segment UPDATEs on override save)
- `operational.phantom_verdicts.ai_recommendation` + `ai_recommendation_evidence_state` (this segment writes on first contested-open per cache miss)
- `team.saved_scenarios` (this segment INSERTs on save-scenario click)

The Planner Workspace is the only segment that writes to `team.planner_overrides`, `phantom_verdicts.ai_recommendation`, and `team.saved_scenarios`. The Existence Engine and Desert Scoring own all other writes.

## Override Panel

When the planner clicks "Override" on a specific facility in the Map view side panel:

```
┌──────────────────────────────────────────────────┐
│  Override Verdict: Phantom A (facility_id: F1234) │
│                                                   │
│  Current verdict: phantom                         │
│  Adjudicator output: phantom                      │
│  Layer A rescue: none                             │
│  AI advisory: (n/a — verdict is not contested)    │
│                                                   │
│  Reason note (required): [                      ] │
│                                                   │
│  [Force Real]  [Force Phantom]  [Cancel]          │
└──────────────────────────────────────────────────┘
```

For contested facilities, the override panel additionally surfaces the AI advisory recommendation so the planner can override *with* or *against* the model:

```
│  AI advisory: force-phantom (medium confidence)   │
│  Reasoning: "PIN mismatch survives, no HFR match" │
│  [cited rows ↗]                                    │
```

**Opening the override panel does not invoke the AI Evidence Layer.** The panel reads only what is already persisted in `phantom_verdicts.ai_recommendation`. If the planner clicks "Override" on a contested facility whose row was never expanded (so `ai_recommendation IS NULL`), the panel displays "AI advisory: not yet computed (expand row to fetch)" rather than firing FMA. The row-expand-triggers-FMA contract is what bounds cost; letting Override-click also trigger erodes the bound.

- Reason note is required before either button is enabled.
- On save, the write sequence is:
  1. INSERT into `team.planner_overrides`, returning new `override_id`
  2. UPDATE `phantom_verdicts` for the affected `facility_id`: set `verdict` to `force-real-planner` or `force-phantom-planner`, set `override_id` to the new row
  3. Streamlit recompute callback fires (per desert-scoring LLD § Incremental Recompute on Override)
- After save: the district's adjusted score updates in the choropleth within 1 second; the facility's verdict badge in the side panel changes to "force-real (overridden, with note: ...)" or "force-phantom (overridden, with note: ...)"; the audit queue rebuilds; the budget reallocation re-ranks.

## Export Controls

The workspace produces **three deliverables**, each owned by a different view:

1. **Revised allocation CSV** (Budget Reallocation view) — `district_id, district_name, current_inr, recommended_inr, delta_inr, justification`. Written to a configured S3 prefix on `Export revised allocation CSV` click. The deliverable for the planner's actual quarterly budget submission.

2. **Inspector worksheet PDF** (Audit Queue view) — print-ready, one row per top-50 facility, with PIN, GPS, district, and failed-test checkboxes. Generated in-process via `reportlab` on `Export inspector worksheet PDF` click. The deliverable for the inspector's Monday field visit.

3. **Scenario CSV + HMIS webhook** (Map view, via `Export Plan` button) — CKAN-compatible CSV containing the district ranking table with `raw_desert_score`, `adjusted_desert_score`, `phantom_count`, and any session overrides; written to the same S3 prefix. Also fires a POST to the mock HMIS webhook with a structured payload containing the top-5 priority districts. This is the "save the planning session for downstream systems" deliverable.

All three exports are independent — clicking one does not invalidate the others. All three preserve the audit trail (the override_set and reason notes from `team.planner_overrides` flow into each deliverable's row-justification text).

## Scenario Persistence

On page load, the app checks for saved scenarios associated with the current planner session. If one is found, it offers to restore it ("Resume scenario: Q3 Bihar Maternity Audit?"). Restored scenarios replay the same override set and region filters, producing an identical choropleth state.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Frontend stack | Streamlit + pydeck (deck.gl) | Streamlit + Folium; Gradio; React + FastAPI | Pydeck is GPU-rendered (10k facility scatter without lag), layer-composable (toggle = data-prop swap, not re-render), first-class click handlers via `st.session_state`. Folium hits Leaflet-DOM perf walls; Gradio has no first-class map; React+FastAPI is ~10–15h overhead that doesn't fit the L bucket. |
| Workspace structure | Three tabs (Map, Budget Reallocation, Audit Queue) in one Streamlit app | Single map view with overlays; separate apps per view; sub-HLD with child segments | Three deliverables = three views. Tabs keep state shared (capability dropdown, sidebar) without duplicating sidebars per page. Sub-HLD promotion was rejected as premature — current scope fits one leaf LLD; promote post-hackathon if facets outgrow. |
| Phantom visibility on toggle | Ghost dots stay visible (ScatterplotLayer color-by-verdict; toggle does NOT filter) | Hide phantoms in adjusted view; opacity dim; tooltip-only | Keeping the lie on screen is the single sentence-free way to convey the thesis. Subtraction is invisible; ghosts are presence-with-verdict. Cost is zero (one fewer line of layer-config code). |
| AI advisory rendering | Inline block in side panel for contested verdicts only; lazy fetch on first open per cache logic | Always render (eager FMA on every contested verdict at batch); modal popup; separate "AI" tab | Inline block keeps the planner's eyeline on the same panel that has the failed-test evidence; modal/tab adds clicks. Lazy fetch concentrates FMA cost on facilities the planner actually opens (~70% saving vs. eager). |
| Override panel surfacing AI advisory | Yes (for contested verdicts) — show the recommendation alongside override buttons | Hide the AI block in override mode; require separate click to reveal | The override is the planner's deciding action; it should happen with the AI advisory in full view, not after dismissing it. The "override against the model" path is a feature, not a corner case. |
| Override requires reason note | Mandatory text field | Optional note | Required note is the human-in-the-loop mechanism the hackathon brief explicitly requires. It also creates a defensible audit trail for a planning commissioner who may be questioned about their decisions. |
| Single-capability view at a time | Capability dropdown selects one | Multi-capability overlay | Multi-capability overlay complicates the choropleth color encoding beyond what a 3-minute demo can explain. Single capability keeps the thesis visible: "we subtracted X phantoms from maternity, and here's what changed." |
| Three deliverables vs. single export | Three (revised allocation CSV, inspector worksheet PDF, scenario CSV+webhook) | Single "export plan" button covering all | One export = one stat. Three deliverables = a workflow. The planner walks away with the artifacts they actually use Monday morning, not a generic dump. |
| Audit queue ordering | Leverage-weighted (`mortality_burden × population × phantom_density`) | Detection-time-sorted; alphabetical | Generic implementations sort by detection time or alphabetically — sends inspectors to convenient phantoms, not the highest-impact ones. Leverage-weighted ensures the top of the queue is the highest mortality-impact gap. |
| Budget recommendation cap | 2.5× prior allocation | No cap; 1.5× cap; 5× cap | An uncapped recommendation can produce politically-implausible swings (a district going from ₹0.5 Cr to ₹15 Cr) that the planner will reject wholesale. 2.5× is the empirical sweet spot — meaningful re-allocation, plausible swing. Tunable per Day-1 review. |
| Genie sidebar | Always-visible across all three tabs | Map-tab-only; hidden behind a toggle; separate page | Persistence across tabs lets ad-hoc questions stay in context as the planner navigates between deliverables. Hidden behind a toggle makes it discoverable but unused. |
| Activation-gate badge in header | Yes ("9 contested · est. cost ≤ $0.04") | `token_usage: 0`; hidden cost; no header indicator | The original `token_usage: 0` framing is dishonest now that FMA is load-bearing on contested cases. Showing the gate metric explicitly is the correct posture: AI is being used, here's the bound, here's the cost. Aligns with the "Determinism owns the math; AI owns the evidence" tenet. |
| Export triggers mock HMIS webhook | Yes, on Export Plan click | User-configurable webhook endpoint | A hard-coded mock endpoint fires reliably in the demo; a user-configurable one introduces a setup step that wastes demo time. |
| Scenario naming | Planner provides name | Auto-generated timestamp | Named scenarios are visually recognizable in the reload list; timestamps require the planner to remember what they did when. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Override reason note is mandatory (cannot save without it). Rationale: matches the "human-in-the-loop with audit trail" requirement of the hackathon brief.
2. ✅ Header activation-gate badge replaces the original `token_usage: 0` indicator. Rationale: FMA is load-bearing on contested cases; `0 tokens` would be dishonest. The gate metric ("N contested · cost ≤ $X") is the correct posture.
3. ✅ Three tabs (Map, Budget Reallocation, Audit Queue) instead of a single map view. Rationale: three deliverables = three views; tabs share state without duplicating sidebars.
4. ✅ AI advisory rendered inline in the side panel (not modal/separate-tab). Rationale: keeps the planner's eyeline on the failed-test evidence and the override buttons in one frame.

### Deferred
1. Multi-region comparison view (show two states side-by-side) — deferred to stretch.
2. Planner-configurable Jaccard threshold slider — deferred; adds UI complexity with low demo value.
3. Bitemporal time-slider replay (cross-pollinated stretch from Counterfactual Witness) — deferred per the proposal's stretch list; would require Lakebase bitemporal columns and a slider widget feeding the GeoJsonLayer's data prop with historical snapshots.
4. Cross-track ASHA referral cascade overlay (cross-pollinated stretch from Regional Cascade) — deferred per the proposal's stretch list; would require an ArcLayer rendering corridor re-routes on toggle.
5. Live model card (gold-set F1, precision, recall) in the sidebar — deferred per the proposal's cross-pollinated stretches; cheap to add later (3–5h).

### Day-1 implementation details to confirm
*Not blocking; reasonable defaults work. Listed so they don't get lost.*

1. **Override panel widget shape.** Default: one widget rendered with conditional content — non-contested verdicts hide the AI advisory section; contested verdicts show it. Two separate widgets duplicates the reason-note + override buttons logic for no benefit.
2. **Activation-gate badge counter semantics.** Default: shows total contested verdicts in the current capability/region scope as the *potential* cost ceiling, with a smaller "spent: $X" tally below tracking actual FMA calls made this session. Both readings are useful; the badge surfaces the ceiling first because that's the cost discipline claim.
3. **Override-against-AI-advisory audit story.** No new column or enum value needed. The data is queryable from the existing schema by joining `team.planner_overrides.override_id` to `phantom_verdicts.ai_recommendation` — when `override_type` disagrees with `ai_recommendation.recommendation`, that's the override-against-AI case. Surface in a future post-hackathon analytics view if needed.
4. **Scenario restore + AI recommendations.** When a saved scenario is restored, the existing `ai_recommendation` rows on `phantom_verdicts` are honored if their `evidence_state` still matches current `(test_outcome_vector, adjudicator_verdict, rescue_applied)` — handled entirely by the existence-engine LLD's lookup logic. No special scenario-restore handling needed for AI recommendations.
5. **Deliverable invalidation on subsequent overrides.** Default: each export click produces a new file with the current state at that instant; previous files are not tracked or invalidated. The planner is responsible for re-exporting after additional overrides if the prior file no longer reflects desired state. UI shows a small `(last exported: HH:MM)` timestamp next to each export button so the planner can see staleness.

## References

- `docs/high-level-design.md` — target user definitions and non-goals; the four AI-load-bearing places; the three-deliverables story
- `docs/intent/existence-engine/existence-engine-design.md` — verdict/recommendation source; AI Evidence Layer lookup logic; cache-key shape
- `docs/intent/desert-scoring/desert-scoring-design.md` — `desert_scores` table; pydeck data-prop swap; override-recompute callback
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md` — `phantom_verdicts` schema (incl. `adjudicator_verdict`, `rescue_applied`, `ai_recommendation`, `override_id`); `team.planner_overrides`, `team.saved_scenarios`, `team.budget_allocations` schemas
