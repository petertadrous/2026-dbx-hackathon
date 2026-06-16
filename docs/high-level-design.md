# High-Level Design: Phantom Census

## Problem

India's district-level healthcare desert maps are built by counting facilities — but a non-trivial share of those facilities do not physically exist. They appear in datasets as self-reported entries that have never been independently verified: coordinates that contradict their own postal codes, descriptions copy-pasted verbatim across dozens of records, claimed clinical indicators that disagree with district-level public-health survey data. When planners use these maps to allocate PMJAY empanelment slots or infrastructure budgets, they fund districts that look underserved on paper while the real deserts — those with low verified supply — receive less attention. India's PMJAY scheme has publicly reported recovery of hundreds of crores annually from ghost and misrepresented facilities; each phantom that enters a planning directory is a direct fraud-risk vector. The structured claim fields (`capability`, `procedure`, `equipment`) — each 99.7% populated — are the primary evidence surface; the free-text `description` field (median 16 tokens) is too short for reliable duplicate detection.

No current planning tool subtracts before it aggregates. All existing desert maps add up everything claimable and call the remainder underserved.

## Approach

Phantom Census inverts the standard desert-mapping workflow: **subtract phantoms first, then score deserts on what remains.** And once subtracted, turn the cleaned map into the planner's actual Monday-morning artefacts — a revised budget allocation and an inspector audit queue — not just a stat.

Four sub-approaches work together:

**1. Multi-signal existence detection.** Each facility is tested against six independent, deterministic existence signals — PIN-to-coordinates disagreement, near-duplicate detection on the structured-claim arrays (`capability` / `procedure` / `equipment`) via MinHash, spatial-join district inconsistency, NFHS-5 bottom-quartile snapshot inconsistency, temporal footprint implausibility, and embedding-cosine drift on `description` between snapshots. Tests run as a Prosecutor/Defender pair under a deterministic Adjudicator with majority-with-veto logic. **No LLM at the verdict layer.**

**2. Activation-gated AI on the ~3% of contested cases.** AI is load-bearing in three places where determinism fails: (a) the embedding-drift 6th existence test (precomputed pgvector cosine, read at app start); (b) Defender corroboration synthesis on contested cases via the Foundation Model API (`ai_query`), which weighs the deterministic test-outcome rows + the dataset-version reconciliation result and emits structured `{strength, supporting_rows, reasoning}`; (c) Adjudicator-contested escalation, which reads all evidence rows + the planner's prior override notes and emits an advisory recommendation with reasoning. The activation gate fires on the ~3% contested verdicts only, keeping a full national scan ≤ $1. The math stays deterministic; AI owns the *reasoning over evidence*; the human owns the *decision*. **No PDF or document mining** — all evidence comes from data already in Lakebase.

**3. Per-district incremental rescoring with override cascade.** Each phantom verdict — or planner override — triggers an incremental recompute of the affected district's desert score via Lakebase CDC. The choropleth re-colors, the ranking shuffles, and the audit queue rebuilds without re-batching the full 706-district aggregate.

**4. Three planner deliverables in one app.** The cleaned map is infrastructure; the deliverables are what the planner walks away with: (a) a **Budget Reallocation view** with a before/after pie of the planner's quarterly allocation and a one-click `Export revised allocation CSV`; (b) an **Audit Queue view** with a leverage-weighted top-50 inspector worksheet (`mortality_burden × population × phantom_density`) and a one-click `Export inspector worksheet PDF`; (c) the saveable scenario itself, exported as CKAN-compatible CSV to S3 + a mock HMIS webhook. Overrides persist in Lakebase, all three deliverables refresh deterministically from persistent state.

## Target Users

**State planning commissioner** preparing a quarterly PMJAY empanelment or capital allocation plan. Has a budget, a map, a deadline, and no time to manually audit 10,000 facilities. Needs a defensible answer: "which districts are real deserts once we subtract what doesn't exist?"

**NGO program officer** allocating field team resources to underserved districts. Needs confidence that a high-burden district is underserved by real supply — not just by missing records.

Neither user is technical. Both need the map to speak for itself without narration.

## Goals

- A planner can toggle "include phantoms in score" off and see the choropleth re-color with ≥3 district rank changes in the demo state within 3 seconds. **Ghost (👻) facility dots stay visible on the map after the toggle** — the dataset's claims are still shown, they just stop counting toward "coverage."
- Every phantom verdict surfaces exactly which tests failed and the supporting evidence row from the source dataset — no claim without a cited row.
- Contested verdicts surface a Foundation Model API recommendation with cited IE-extracted evidence rows; planner override remains the deciding action.
- A planner override persists across page reload and propagates to the district desert score, the Budget Reallocation table, and the Audit Queue worksheet within 1 second.
- LLM activation gate fires on ≤5% of facilities (contested cases only); full national scan cost ≤ $1; verdict-layer math has zero LLM calls.
- Three deliverables export cleanly with one click each: revised-allocation CSV, inspector-worksheet PDF, CKAN-compatible scenario CSV (S3 + mock HMIS webhook).
- The Day-0 validation suite (phantom_census_validation.md) runs cleanly against the real data before any product code is written.

## Non-Goals

- Live web validation of facility addresses (would require external network calls in the demo environment).
- Routing or referral logic — this is a macro desert planner, not a patient navigator.
- Fixing wrong data in place — verdicts are read on top of the source dataset; the source is never mutated.
- Predicting future phantom risk or modeling supply elasticity.
- Non-India geographies or non-healthcare facility types.
- String-matching district names across datasets — spatial join only; the brief explicitly recommends this.
- Resurrecting flagged phantoms via NLP or external lookup during the demo.

## Tenets

- **Determinism owns the math; AI owns the evidence; the human owns the decision.** The verdict adjudication rule is deterministic by design — auditability requirement, not a posture. AI is load-bearing only where determinism fails: free-text Information Extraction for corroborating evidence, embedding-cosine drift for silent-emergence detection, Defender corroboration synthesis on contested cases, and Adjudicator escalation that emits an advisory recommendation. The planner makes the call.
- **Activation gate, not a kill switch.** LLM fires on the ~3% contested cases, not on every facility. A full national scan costs ≤ $1. Template-first generation is the fallback when the model is unavailable, so the pipeline cannot fail on LLM availability.
- **Absent data abstains; it does not vote.** When a facility lacks the fields needed for a test, that test returns `indeterminate`, not `pass` or `fail`. The Adjudicator works with what it has. A facility with no testable signals gets verdict `contested/insufficient-evidence`, not `real`. This prevents the system from asserting false confidence on data-poor records.
- **Ghosts stay visible after subtraction.** Most teams will hide phantoms in the adjusted view. We keep the lie on screen — facility dots remain on the map as 👻 ghosts even after the toggle — so judges and planners both see what the dataset was claiming and what we no longer believe.
- **Boring over clever for infrastructure.** Streamlit + pydeck (deck.gl) over reactive websockets or React+FastAPI; layer-composable map (toggle = data-prop swap, not re-render) over CSS opacity hacks; Lakebase CDC over multi-writer cascades; pre-loaded HFR snapshots over live API calls during the demo.
- **Phantom counts are falsifiable, not authoritative.** The app reports what the tests found; it does not claim a facility is definitely fake. `phantom | real | contested` are probability labels, not legal conclusions. Users see the evidence; they decide.

## System Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION (Bronze)                          │
│  VF facility records · India Post PIN dir · NFHS-5 indicators           │
│  District shapefiles (geoBoundaries ADM2) · HFR pre-cached snapshot     │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     EXISTENCE ENGINE (Silver)                           │
│                                                                         │
│  ┌─────────────────┐      ┌─────────────────────────────────────────┐  │
│  │ Existence        │      │ Existence Defender                      │  │
│  │ Prosecutor       │      │ ┌─────────────────────────────────────┐ │  │
│  │ Runs 6 tests;    │◄────►│ │ Structured-field corroboration       │ │  │
│  │ defaults "fake   │      │ │ (URL mentions, HFR match, NFHS       │ │  │
│  │ until proven"    │      │ │  named-staff overlap) — deterministic│ │  │
│  │                  │      │ └─────────────────────────────────────┘ │  │
│  │ 6th test:        │      │ ┌─────────────────────────────────────┐ │  │
│  │ embedding-drift  │      │ │ Dataset-version reconciliation      │ │  │
│  │ (pgvector cos.)  │      │ │ (district splits, spelling drift)   │ │  │
│  │                  │      │ └─────────────────────────────────────┘ │  │
│  └────────┬────────┘      └────────────────────┬────────────────────┘  │
│           └───────────────┬────────────────────┘                        │
│                           ▼                                             │
│               ┌───────────────────────────┐                             │
│               │  Deterministic Adjudicator │                            │
│               │  Majority-with-veto:       │                            │
│               │  PIN-fail = hard veto      │                            │
│               │  Output: phantom/real/     │                            │
│               │  contested                 │                            │
│               └─────────────┬─────────────┘                             │
│                             │ contested ~3%                             │
│                             ▼                                           │
│       ┌───────────────────────────────────────────────────┐             │
│       │  AI EVIDENCE LAYER (activation-gated)             │             │
│       │  Foundation Model API (`ai_query`)                │             │
│       │  • Defender corroboration synthesis               │             │
│       │    {strength, supporting_rows, reasoning}         │             │
│       │  • Adjudicator-contested advisory recommendation  │             │
│       │  Cost gate: ~3% of facilities → ≤ $1 / full scan  │             │
│       │  Template-first fallback if model unavailable     │             │
│       └─────────────┬─────────────────────────────────────┘             │
└─────────────────────┼───────────────────────────────────────────────────┘
                      │ phantom_verdicts (CDC source) + ai_recommendations
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DESERT SCORING (Gold)                                │
│  Per-district incremental recompute via Lakebase CDC trigger            │
│  desert_scores (raw) + desert_scores_adjusted (phantom-subtracted)      │
│  Leverage weights: mortality_burden × population × phantom_density       │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  PLANNER WORKSPACE (Databricks App)                     │
│  Streamlit + pydeck (deck.gl) — GPU-rendered, layer-composable          │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Map view  (the wow toggle)                                     │    │
│  │  • GeoJsonLayer: 706 districts, fill = raw OR adjusted score    │    │
│  │  • ScatterplotLayer: 10k facilities — ✅ green / 👻 ghost / ⚠️    │    │
│  │  • Toggle: choropleth fill swap; ghosts STAY visible            │    │
│  │  • Side panel: phantom evidence chips + AI recommendation       │    │
│  │  • Override: force-real / force-phantom + required reason       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Budget Reallocation view                                       │    │
│  │  Before/after pie · ₹ shifts · Export revised allocation CSV    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Audit Queue view                                               │    │
│  │  Leverage-weighted top-50 inspector worksheet · Export PDF      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Genie sidebar (NL chat over Lakebase + Delta)                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Export: CKAN-compatible CSV → S3 watched prefix + mock HMIS webhook    │
│  Scenario persistence: save/reload via Lakebase                         │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       LAKEBASE (Operational State)                      │
│  operational.phantom_verdicts · operational.desert_scores               │
│  operational.facility_existence_tests                                    │
│  cache.description_minhash · cache.description_embeddings (pgvector)    │
│  team.planner_overrides · team.saved_scenarios · team.budget_allocations│
└─────────────────────────────────────────────────────────────────────────┘
```

**Six existence tests run by the Prosecutor:**

| Test | Signal | Veto-capable | LLM? |
|---|---|---|---|
| PIN reverse-lookup | Claimed PIN's India Post coordinates disagree with facility lat/lon | Yes (hard veto) | No |
| MinHash near-duplicate | `capability` / `procedure` / `equipment` (concatenated) Jaccard ≥ 0.9 with ≥2 other facilities | No (supporting) | No |
| Spatial district mismatch | PIN-claimed district ≠ spatial-join-assigned district | Yes (hard veto) | No |
| NFHS-5 bottom-quartile inconsistency | Claimed maternity capability but district NFHS-5 institutional-delivery rate in bottom quartile for state | No (supporting) | No |
| Temporal implausibility | `yearEstablished` in future or before plausible founding year, combined with high-acuity claims | No (supporting) | No |
| **Embedding-drift cosine** *(new, MVP)* | `description` embedding cosine drifts ≥ threshold from prior snapshot — silent phantom emergence (real desc → template, or vice versa) | No (supporting) | Embeddings precomputed; verdict-time math is cosine only |

Adjudicator rule: verdict = `phantom` when ≥2 tests fail OR any veto-capable test fails. Verdict = `contested` when exactly 1 non-veto test fails OR insufficient testable signals — *contested verdicts trigger the AI evidence layer*. Verdict = `real` when 0 tests fail and ≥2 tests pass.

## Key Design Decisions

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Frontend stack | Streamlit + pydeck (deck.gl) | Streamlit + Folium; Gradio; React + FastAPI | pydeck is GPU-rendered (10k facility scatter without lag), layer-composable (toggle = data-prop swap, not re-render), and has first-class click handlers via `st.session_state`. Folium hits Leaflet-DOM perf walls; Gradio has no first-class map; React+FastAPI is ~10–15h overhead that doesn't fit the L bucket. |
| Choropleth redraw mechanism | Data-prop swap on GeoJsonLayer | Pre-rendered tile layers + CSS opacity swap; live SSE/websocket push | Data-prop swap is sub-second on pydeck without the Free-Edition SSE/websocket dependency. Tile-and-CSS would also work but loses click-into-region. |
| Phantom visibility on toggle | Ghost dots stay visible (filter NOT applied) | Hide phantoms in adjusted view | Keeping the lie on screen is the single sentence-free way to convey the thesis. Subtraction is invisible; ghosts are presence-with-verdict. Cost is zero (one fewer line). |
| Verdict layer | Deterministic Adjudicator (no LLM) | LLM-as-judge | Reproducibility, speed, cost. The adjudication rule must be reproducible from the same data with no model call — auditability requirement, not posture. |
| AI activation policy | Activation-gated to ~3% contested cases | LLM on every facility; LLM never | Determinism handles the 97% obvious cases. AI earns its keep on the contested tail where evidence is heterogeneous and reasoning is required. Full national scan ≤ $1; pipeline survives LLM unavailability via template fallback. |
| Agent framing | Prosecutor / Defender / Adjudicator + FMA evidence layer | Single extraction agent | Adversarial framing differentiates vs. median Track 2; the Defender's deterministic structured-field corroboration plus FMA contested-case synthesis is what rescues legitimate chain clinics. |
| Duplicate detection | MinHash on `capability`+`procedure`+`equipment` (128 perms, shingle 5, Jaccard ≥ 0.9) | MinHash on `description`; TF-IDF cosine; embeddings only | Description p50 is 16 tokens — too short for Jaccard 0.9 + shingle 5. Structured-claim arrays are 99.7% populated and 10–20× richer per facility. MinHash stays O(n), deterministic, and verdict-time-token-free. |
| 6th test (embedding-drift) | pgvector cosine on description embeddings between snapshots | None; embedding similarity at verdict time | Detects facilities silently *becoming* phantoms (a real fraud pattern: stuff a real description, harvest empanelment, blank). Embeddings are precomputed at ingest; verdict-time math is cosine only — keeps the deterministic-core claim. |
| District join | Spatial (ST_Contains / GeoPandas) | String name matching | Brief explicitly recommends spatial join; string matching across NFHS-5 / India Post / VF is unreliable due to transliteration variance. |
| Lakebase role | Operational OLTP: verdicts, evidence, overrides, scores, scenarios, budget allocations, embedding cache | Delta-only | Per-district incremental recompute requires mutable OLTP writes with CDC. Delta lacks the sub-second OLTP write path needed for live override → score → audit-queue cascade. |
| User-facing artefacts | Three deliverables (revised allocation CSV, inspector worksheet PDF, scenario CSV → S3 + HMIS webhook) | Single export | The cleaned map is infrastructure; the deliverables are the planner's actual Monday morning. One export = one stat. Three deliverables = a workflow. |
| NL ad-hoc queries | Genie sidebar over Lakebase + Delta | Pre-baked dashboards only; no NL surface | A non-technical commissioner asks questions the pre-baked views don't cover ("which 5 districts gain the most rank?"). Genie writes SQL inline. Doesn't touch the verdict path so the deterministic-core claim survives. |
| HFR/HPR integration | Offline cache snapshot pre-loaded to Lakebase | Live API at query time | Live API would require external network calls blocked on Free Edition. A pre-loaded snapshot achieves the same test with no runtime dependency. |

## Success Metrics

- T2.4 (phantom_census_validation.md) returns 5–25% PIN-vs-GPS disagreement rate in the demo state — confirming real phantoms exist in detectable quantity.
- T3.4 returns ≥3 districts moving ≥3 positions on rank-flip after phantom subtraction — confirming the choropleth redraw has visible impact.
- At least 10 "Known-good" spot checks (T4.1) pass with 0 false-phantom verdicts on large urban hospitals.
- Live demo achieves the toggle beat in ≤3 seconds; ghost facility dots remain visible after the toggle (filter is NOT applied to ScatterplotLayer).
- LLM activation gate fires on ≤5% of facilities (contested cases only); full national scan cost ≤ $1 displayed live.
- Planner override persists, district score recomputes, Budget Reallocation table refreshes, and Audit Queue rebuilds within 1 second of save.
- Three deliverables export cleanly with one click each: revised allocation CSV, inspector worksheet PDF, scenario CSV → S3 + mock HMIS webhook firing in the same demo turn.
- Day-0 validation cleared both kill-switches: facility geocoding 98.8% (T1.1 ✅); PIN-vs-spatial disagreement rate 24.5% after normalization — well within the 5–25% target band (T2.4 ✅). Demo state locked: Maharashtra (304 phantom candidates, 33 districts, BEED rank shift 10→2).

## References

- `proposal/idea_phantom_census.md` — base proposal (Track 2, rubric 21/25 after AI-centrality patch; one point off the green band, recoverable via real CKAN endpoint)
- `proposal/amendment_phantom_census.md` — AI-centrality + frontend-stack patch (merged into base proposal)
- `proposal/phantom_census_validation.md` — Day-0 data validation suite (run before writing product code)
- `dbx-hackathon-playbook.md` — hackathon hard rules, judging criteria, Free Edition constraints
- `hackathon.md` — official brief, track definitions, required app capabilities
- `Virtue Foundation Dataset (DAIS 2026).md` — dataset field coverage, supplemental sources
