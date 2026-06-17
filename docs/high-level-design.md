# High-Level Design: Phantom Census

## Problem

India's district-level healthcare desert maps are built by counting facilities — but a non-trivial share of those facilities do not physically exist. They appear in datasets as self-reported entries that have never been independently verified: coordinates that contradict their own postal codes, descriptions copy-pasted verbatim across dozens of records, claimed clinical indicators that disagree with district-level public-health survey data. When planners use these maps to allocate PMJAY empanelment slots or infrastructure budgets, they fund districts that look underserved on paper while the real deserts — those with low verified supply — receive less attention. India's PMJAY scheme has publicly reported recovery of hundreds of crores annually from ghost and misrepresented facilities; each phantom that enters a planning directory is a direct fraud-risk vector. The structured claim fields (`capability`, `procedure`, `equipment`) — each 99.7% populated — are the primary evidence surface; the free-text `description` field (median 16 tokens) is too short for reliable duplicate detection.

No current planning tool subtracts before it aggregates. All existing desert maps add up everything claimable and call the remainder underserved.

## Approach

Phantom Census inverts the standard desert-mapping workflow: **subtract phantoms first, then score deserts on what remains.**

Three sub-approaches work together:

**1. Multi-signal existence detection.** Each facility is tested against five independent, deterministic existence signals — PIN-to-coordinates disagreement, near-duplicate description fingerprinting (MinHash), spatial-join district inconsistency, NFHS-5 outcome-consistency mismatch, and temporal footprint implausibility. Tests run independently as a Prosecutor/Defender pair under a deterministic Adjudicator with majority-with-veto logic. No LLM at the verdict layer.

**2. Per-district incremental rescoring.** Each phantom verdict triggers an incremental recompute of the affected district's desert score via Lakebase CDC. The choropleth reflects the current verdict state without re-batching the full 706-district aggregate on every toggle.

**3. Human-in-the-loop override and scenario persistence.** Planners can force-real or force-phantom any facility with a required reason note. Overrides persist in Lakebase, recompute district scores live, and survive page reload. Full planning sessions are saveable and resumable.

## Target Users

**State planning commissioner** preparing a quarterly PMJAY empanelment or capital allocation plan. Has a budget, a map, a deadline, and no time to manually audit 10,000 facilities. Needs a defensible answer: "which districts are real deserts once we subtract what doesn't exist?"

**NGO program officer** allocating field team resources to underserved districts. Needs confidence that a high-burden district is underserved by real supply — not just by missing records.

Neither user is technical. Both need the map to speak for itself without narration.

## Goals

- A planner can see the phantom-adjusted choropleth with orange CircleMarkers on the top-30 rank-shift districts; selecting a district reveals a district score with ≥3 rank changes visible in the ranking table.
- Every phantom verdict surfaces exactly which tests failed and the supporting evidence row from the source dataset — no claim without a cited row.
- A planner override persists across page reload and propagates to the district desert score within 1 second.
- Verdict pipeline token usage: zero LLM calls at verdict or scoring time. LLM (Llama 3.3 70B via Databricks Foundation Model API) is activated only for the opt-in AI Verification Brief per district.
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

- **Deterministic core; LLM is narrator only.** Every verdict that drives the map, score, or ranking must be reproducible from the same data with no LLM call. LLM is activated only to polish human-readable narratives, and only when the user opts in. When two approaches achieve the same result — one with an LLM, one without — prefer the one without.
- **Absent data abstains; it does not vote.** When a facility lacks the fields needed for a test, that test returns `indeterminate`, not `pass` or `fail`. The Adjudicator works with what it has. A facility with no testable signals gets verdict `contested/insufficient-evidence`, not `real`. This prevents the system from asserting false confidence on data-poor records.
- **Boring over clever for infrastructure.** Lakebase CDC + Streamlit + pre-rendered tile layers over reactive websockets or multi-writer cascades. The demo's visual effect (choropleth redraw) is achieved via CSS opacity swap of pre-computed tile layers, not a live recompute per click.
- **Phantom counts are falsifiable, not authoritative.** The app reports what the tests found; it does not claim a facility is definitely fake. `phantom | real | contested` are probability labels, not legal conclusions. Users see the evidence; they decide.

## System Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION (Bronze)                          │
│  VF facility records · India Post PIN dir · NFHS-5 indicators           │
│  District shapefiles (geoBoundaries ADM2)                               │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     EXISTENCE ENGINE (Silver)                           │
│                                                                         │
│  ┌─────────────────┐      ┌─────────────────────────────────────────┐  │
│  │ Existence        │      │ Existence Defender                      │  │
│  │ Prosecutor       │      │ Looks for corroborating signals         │  │
│  │ Runs 5 tests;    │◄────►│ (distinct URLs, govt registration,      │  │
│  │ defaults "fake   │      │  named staff in NFHS denominators)      │  │
│  │ until proven"    │      └─────────────────────────────────────────┘  │
│  └────────┬────────┘                       │                            │
│           └───────────────┬────────────────┘                            │
│                           ▼                                             │
│               ┌───────────────────────────┐                             │
│               │  Deterministic Adjudicator │                            │
│               │  Majority-with-veto:       │                            │
│               │  PIN-fail = hard veto      │                            │
│               │  Output: phantom/real/     │                            │
│               │  contested                 │                            │
│               └───────────────────────────┘                             │
└─────────────┬───────────────────────────────────────────────────────────┘
              │ phantom_verdicts (CDC source)
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DESERT SCORING (Gold)                                │
│  Per-district incremental recompute via Lakebase CDC trigger           │
│  desert_scores: raw + adjusted scores, raw_rank, adjusted_rank,        │
│  rank_shift (raw_rank − adjusted_rank), phantom_count                  │
│  Pre-rendered adjusted tile layer with phantom-impact CircleMarkers    │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  PLANNER WORKSPACE (Databricks App)                    │
│  React + AppKit + Folium choropleth (phantom-adjusted view only)       │
│  Orange CircleMarkers on top-30 districts by rank_shift                │
│  AI Verification Brief: on-demand per-district analysis (Llama 3.3 70B)│
│  Side panel: example phantoms per district with test evidence rows     │
│  Override panel: force-real / force-phantom with required reason note  │
│  Export: CKAN-compatible CSV to S3 watched prefix + mock HMIS webhook  │
│  Scenario persistence: save/reload via Lakebase                        │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       LAKEBASE (Operational State)                     │
│  phantom_verdicts · desert_scores · planner_overrides · saved_scenarios│
│  description_minhash · facility_existence_tests                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Five existence tests run by the Prosecutor:**

| Test | Signal | Veto-capable |
|---|---|---|
| PIN reverse-lookup | Claimed PIN's India Post coordinates disagree with facility lat/lon | Yes (hard veto) |
| MinHash near-duplicate | capability / procedure / equipment (concatenated) Jaccard ≥ 0.9 with ≥2 other facilities | No (supporting) |
| Spatial district mismatch | PIN-claimed district ≠ spatial-join-assigned district | Yes (hard veto) |
| NFHS-5 outcome inconsistency | Claimed maternity capability but district NFHS-5 institutional-delivery rate in bottom quartile for state | No (supporting) |
| Temporal implausibility | `yearEstablished` in future or before plausible founding year, combined with high-acuity claims | No (supporting) |

Adjudicator rule: verdict = `phantom` when ≥2 tests fail OR any veto-capable test fails. Verdict = `contested` when exactly 1 non-veto test fails OR insufficient testable signals. Verdict = `real` when 0 tests fail and ≥2 tests pass.

## Key Design Decisions

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Choropleth redraw mechanism | Pre-rendered tile layers; CSS opacity swap | Live Lakebase CDC → Streamlit reactive push | CSS swap achieves same visual effect without Free Edition SSE/websocket dependency. Avoids the demo's single biggest live-failure risk. |
| Verdict layer | Deterministic Adjudicator (no LLM) | LLM-as-judge | Reproducibility, speed, token-efficiency (0 LLM calls at verdict time), and the demo's "token usage: 0" differentiator. |
| Agent framing | Prosecutor / Defender / Adjudicator | Single extraction agent | Adversarial framing is the differentiator vs. median Track 2. Technically: the Defender improves recall (rescues legitimate chain clinics). Narratively: the courtroom metaphor lands in 10 seconds. |
| Duplicate detection | MinHash (128 perms, shingle 5, Jaccard ≥ 0.9) | TF-IDF cosine similarity, embedding distance | MinHash is O(n) to build, deterministic, and token-free. Embedding distance would require LLM inference on 10k descriptions. |
| District join | Spatial (ST_Contains / GeoPandas) | String name matching | Brief explicitly recommends spatial join; string matching across NFHS-5 / India Post / VF is unreliable due to transliteration variance. |
| Lakebase role | Operational OLTP: verdicts, overrides, scores, scenarios | Delta-only | Per-district incremental recompute requires mutable OLTP writes with CDC. Delta lacks the sub-second OLTP write path needed for live override → score update. |
| HFR/HPR integration | Offline cache snapshot pre-loaded to Lakebase | Live API at query time | Live API would require external network calls blocked on Free Edition. A pre-loaded snapshot achieves the same test with no runtime dependency. |

## Success Metrics

- T2.4 (phantom_census_validation.md) returns 5–25% PIN-vs-GPS disagreement rate in the demo state — confirming real phantoms exist in detectable quantity.
- T3.4 returns ≥3 districts moving ≥3 positions on rank-flip after phantom subtraction — confirming the choropleth redraw has visible impact.
- At least 10 "Known-good" spot checks (T4.1) pass with 0 false-phantom verdicts on large urban hospitals.
- Live demo achieves the toggle-and-redraw beat in ≤3 seconds with `token_usage: 0` displayed on screen.
- Planner override persists and district score recomputes within 1 second of save.
- Day-0 validation cleared both kill-switches: facility geocoding 98.8% (T1.1 ✅); PIN-vs-spatial disagreement rate 24.5% after normalization — well within the 5–25% target band (T2.4 ✅). Demo state locked: Maharashtra (304 phantom candidates, 33 districts, BEED rank shift 10→2).

## References

- `proposal/idea_phantom_census.md` — original proposal (Track 2, rubric 23/25)
- `proposal/phantom_census_validation.md` — Day-0 data validation suite (run before writing product code)
- `dbx-hackathon-playbook.md` — hackathon hard rules, judging criteria, Free Edition constraints
- `hackathon.md` — official brief, track definitions, required app capabilities
- `Virtue Foundation Dataset (DAIS 2026).md` — dataset field coverage, supplemental sources
