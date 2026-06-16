# Idea: Phantom Census

**Track:** 2 Medical Desert (with a Track 1 twist)
**One-liner:** Subtract statistically nonexistent facilities first — every desert map is wrong until you do.

> **Day-0 Validation Update (2026-06-15).** Full validation suite (`phantom_census_validation_results.md`) and schema audit (`phantom_census_schema_audit.md`) executed against the live Databricks Marketplace share. Both kill-switches cleared (geocoding 98.8%; PIN-vs-spatial 24.5% disagreement after light normalization). Three locked-in changes vs. the original draft below: (1) **demo state pivots Bihar → Maharashtra**, Bihar yields only 24 single-flag phantoms (fails T3.2 ≥50); Maharashtra yields 304 phantoms across 33 districts with BEED rank 10→2 as the headline shuffle. (2) **Uniqueness test moves off `description` onto `capability`+`procedure`+`equipment`** — description p50 is 16 tokens, MinHash@Jaccard 0.9 + shingle-5 won't work; the structured-claim arrays are 99.7% populated and far richer. (3) **NFHS-consistency test re-spec'd from "indicator didn't move" → "claims capability X in a bottom-quartile NFHS district for X"** — NFHS-5 is a snapshot, "didn't move" requires NFHS-6 longitudinal which is out of scope. Two additional non-blocking gotchas the implementation must respect: `address_stateOrRegion` is contaminated (254 distinct values vs. 36 real states — derive from coordinates) and `source_content_id` is a per-source-page ID (NOT an entity key — 27 different hospitals can share one).

---

## Snapshot

- **Estimated MVP effort:** ☐ S (≤20h) ☑ M (20–35h) ☐ L (35–55h) ☐ XL (>55h) — ~30.5h + 6h buffer across 3 engineers; promote to L if Day-1 audit forces multi-region scope.
- **Stretch features beyond MVP:** S3 watch prefix dropping CKAN-compatible CSV when district scores cross threshold; mock state HMIS webhook receiving structured priority deltas; pluggable existence-test enum (add tests as new rows, not code); planner-override veto rule with required reason; secondary indicator overlay (e.g. NFHS institutional-delivery rate) on hover.
- **Rubric score (out of 25):** *Filled by AI applying strict 1pt/3pt/5pt anchors per `Hackathon Topic Prioritization Rubric.md`; team should re-score.* Decoupling **5/5** (Existence Prosecutor + Existence Defender + deterministic Adjudicator + offline Information Extraction — matches 5pt anchor "complex network of parallel cooperating specialized agents") · Integration **3/5** (S3 watched prefix is a real write; HMIS webhook is *mocked*, not a real state system — 3pt anchor "standard REST APIs but writes require custom workarounds" is the strict read) · Testability **5/5** (PIN reverse-lookup, MinHash Jaccard threshold, spatial join consistency are all binary/deterministic; Adjudicator is majority-with-veto, no LLM — exact match to 5pt anchor "binary and deterministic") · Pain **5/5** (misallocated PMJAY-empanelment funding to phantom-inflated districts is a massive financial leak with direct ROI metric — 5pt anchor) · Tokens **5/5** (existence tests are non-LLM; IE agent is offline batch only; demo runtime `token_usage: 0` — 5pt anchor "optimized low-token structured inputs") · **Total 23/25 — green light per rubric (22–25 band).**
- **Rubric calibration note:** Integration loses two points because the HMIS webhook is mocked; if the team can wire a real CKAN endpoint (S3 prefix already counts), Integration moves to 4. Source draft scored Decoupling 4 and Integration 4 for a same total of 23; redistribution here reflects strict anchor reading.

---

## 1. High-Level Design

- **User & moment of use:** A state planning commissioner deciding where to place the next 50 PMJAY-empanelled facilities for the quarter. Has a budget, a map, a deadline; cannot afford to ignore a truly underserved district while funding one with inflated coverage.
- **Core question the app answers:** *Which districts are real medical deserts once we subtract facilities that fail multiple independent existence tests?*
- **Primary workflow (≤5 steps):**
  1. Pick clinical capability (e.g. maternity); view the official ("raw") desert choropleth.
  2. Toggle **subtract phantoms** → map redraws; ranking shuffles; counter shows "N phantom facilities removed."
  3. Click a district (e.g. BEED, Maharashtra) → side panel with example phantoms, each rendered with three failed existence tests + supporting public-dataset rows.
  4. Drill into a specific facility's failed tests; optionally override (force-real / force-phantom) with a required reason; district score recomputes live.
  5. Click **export plan**: CKAN-compatible CSV lands in a watched S3 prefix; mock state HMIS webhook fires with the priority delta. Save scenario in Lakebase; reload survives.
- **Inputs:** VF facility records (rich `capability` / `procedure` / `equipment` JSON-array fields are 99.7% populated and used as the primary claim text; `description` is supporting context only — p50 = 16 tokens, too short for the uniqueness test); India Post PIN directory (165k rows; cardinality-aware: PIN→post-office is one-to-many); NFHS-5 district indicators (706 × 109, already snake_cased + numeric in the marketplace share); geoBoundaries India ADM2 shapefile (735 polygons, downloaded — geoboundaries.org direct is sandbox-blocked, use GitHub LFS media endpoint) for spatial join; planner overrides; threshold configs (Jaccard, NFHS bottom-quartile cutoff).
- **Fields explicitly NOT trusted as input:** `address_stateOrRegion` (contaminated — 254 distinct values vs. 36 real states; contains JSON fragments and city names; state is derived from coordinates via spatial join instead); `source_content_id` (per-source-page ID, NOT entity-level — used only as a citation back-reference, never as a join key or facility identifier).
- **Outputs:** UI = two-state choropleth (raw vs phantom-adjusted) + phantom side panel; Lakebase = `phantom_verdicts`, `desert_scores` (raw and adjusted, with delta), `team.planner_overrides`, saved scenarios; CKAN-compatible CSV in S3; structured webhook payload to mock HMIS; planner override audit trail.
- **Out of scope:** Live web validation of facility addresses; supply-elasticity / building-decision modeling; non-spatial deserts; resurrecting flagged phantoms via NLP; predicting *future* phantom risk; routing / referral logic; modifying source datasets in place; fixing wrong NFHS-5 district names via string matching (spatial join only).

---

## 2. Databricks Technologies & Centrality

### Lakebase
- Used for: per-district incremental recompute of `desert_scores` triggered by `phantom_verdicts` writes; mutable state for verdicts, planner overrides, saved scenarios; pre-computed MinHash signatures stored as BYTEA; serves the live UI redraw without re-batching the full 706-district aggregate per click.
- Specific tables / indexes / pgvector use: `operational.facility_existence_tests` (composite PK on `(facility_id, test_name, ran_at)`, liquid-clustered on `facility_id` in Delta mirror), `operational.phantom_verdicts` (CDC source for map redraw), `operational.desert_scores` (materialized view via trigger), `cache.description_minhash` (BYTEA), `team.planner_overrides`, `team.saved_scenarios`. No pgvector in MVP — MinHash is the chosen near-duplicate detection.
- Centrality: ☑ **Load-bearing** ☐ Supporting ☐ Nice-to-have
- Removal cost: The toggle's visible-redraw effect *is* per-district incremental recompute on CDC. With Delta-only you'd re-batch the full 706-district aggregate per click; the toggle freezes and the demo's "shuffle the ranking live" beat collapses. Override + scenario persistence also requires multi-writer mutable state. Removing Lakebase costs the *demo*, not just a feature.

### Agent Bricks
- Agent types used: ☑ Information Extraction ☐ Knowledge Assistant ☑ Multi-Agent Supervisor ☐ Custom LLM
- Specific agent roles & responsibilities:
  - **Existence Prosecutor** — runs the five existence tests; defaults "fake until proven real"; emits failed-test rows.
  - **Existence Defender** — looks for corroborating signals (multiple distinct source URLs, government registration matches, named staff in NFHS denominators) to **rescue** accused phantoms. Critically, the Defender owns the **dataset-version reconciliation layer**: a PIN-vs-spatial disagreement caused by post-2022 district reorganization (Bapatla carved from Prakasam, NTR from Krishna) or spelling drift (Mysore↔Mysuru, Ahmadnagar↔Ahmednagar) must be rescued, not flagged. Day-0 validation showed ~9pp of the 24.5% raw PIN-vs-spatial disagreement is in this bucket.
  - **Adjudicator** — deterministic majority-with-veto rule (PIN failure = hard veto; claim-uniqueness alone is not). **No LLM.**
  - **Information Extraction** runs offline to pull staff/equipment/procedure claims from the `capability`/`procedure`/`equipment` JSON-array fields (already structured, just need `from_json` cast) for the Defender; description free-text is supporting context only.
- Centrality: ☐ Load-bearing ☑ **Supporting** ☐ Nice-to-have
- Removal cost: The five tests can run as plain Python — agentic framing is the narrative differentiator, not strictly required for the math. Without prosecutor/defender split you lose the "opposed reward functions reconciled by deterministic math" creativity story; underlying tests still run as undifferentiated rules. The toggle still works.

### Databricks Apps
- Frontend framework: Streamlit + Folium / Plotly choropleth (pre-rendered tile layers; toggle is a CSS opacity swap, not a recompute). *Confirm during Day-1 — choropleth performance is the gating factor; team to choose between Streamlit + Folium and a richer React-based map if needed.*
- How it reads/writes Lakebase live: Subscribes to `desert_scores` for the choropleth; subscribes to `phantom_verdicts` + `facility_existence_tests` for the side panel; writes planner overrides to `team.planner_overrides` and saved scenarios; export triggers fire S3 + webhook hooks.
- Auth / multi-user considerations: Single planner persona for the demo; scenario name is user-provided so multiple saves co-exist; multi-planner concurrency on the same district is a stretch goal.

### Other Databricks tech (optional)
- **Geospatial functions** (`ST_Contains`, `ST_Point`) load-bearing for the NFHS-5 spatial join (string-matching district names is unreliable). *Marker to validate on Free Edition; fallback to GeoPandas in-process if unavailable* (10k facilities × 700 polygons fits a single worker). Delta mirror of Lakebase tables for analytical scans. **Liquid clustering on `facility_id`** in Delta mirror. MLflow `@mlflow.trace` decorators on each existence test / agent run.

---

## 3. Presentation & Wow Factor

### 3-minute demo arc
| Time | What's on screen | What the presenter says |
|------|------------------|-------------------------|
| 0:00–0:20 | Maharashtra choropleth, official desert score by district. | "Every desert map you've seen is wrong. Most maps add up the facilities they can find. We're going to *subtract* the ones that don't actually exist — because today's planners fund the loud districts, not the sick ones." |
| 0:20–0:50 | Toggle **subtract phantoms** → map redraws; ranking visibly shuffles; counter ticks "304 phantoms removed across 33 districts." | "One toggle. Five existence tests fired against ten thousand records. The map redraws, the rank shuffles. Some districts you thought were fine just got worse — their facility counts were inflated by phantoms." |
| 0:50–1:50 | Click a now-redder district (BEED) → side panel with three example phantoms; each shows three failed test rows with supporting evidence. | "Phantom A: PIN says Aurangabad, lat/lon says Solapur — fails India Post reverse-lookup. Phantom B: capability and procedure claims are a near-duplicate of 14 other facilities scraped from the same source page. Phantom C: claims maternity in a district where NFHS-5 institutional-delivery rate sits in the bottom quartile. Three independent failures. Not one expert opinion — three deterministic tests." |
| 1:50–2:20 | Override panel — planner forces Phantom A back to "real" with a required reason note; district score recomputes live; saved to Lakebase. | "I just visited this one personally. Override force-real, with a required note. District score updates in under a second. The override is part of the scenario." |
| 2:20–2:50 | Click **export plan**: CKAN-compatible CSV lands in S3 watched prefix; HMIS webhook fires. Save scenario "Q3 Maharashtra Maternity Audit"; reload page; map and overrides survive. | "CKAN-compatible CSV in the S3 prefix. Webhook fires the mock state HMIS with the priority delta. Two integrations, one click. Save the scenario. Reload — survives." |
| 2:50–3:00 | `token_usage: 0` panel; Maharashtra headline ranking diff "BEED: 10th → 2nd-worst desert"; differentiation hook on screen. | "BEED is the second-worst desert in Maharashtra, not the tenth. Token usage: zero. Every other desert map will *add* facilities to find gaps. We *subtract* fictional ones to expose deserts hiding in plain sight." |

### The wow moment
**The toggle and the redraw.** ~10 seconds: planner clicks, half the choropleth shifts, a couple of districts go from beige to red, the `phantoms removed` counter ticks up — all in one frame, a visceral subtraction. The visual tells the entire thesis without a sentence of narration.

### How the demo proves the four required capabilities
- **Strict citations:** Each phantom verdict in the side panel cites the exact India Post row (PIN, lat/long), the MinHash collision set (with duplicate facility IDs), and the NFHS-5 indicator value with district code — all clickable. No claim without a row reference.
- **Uncertainty mitigation:** Three test outcomes are independent → verdict is `phantom | real | contested`; "contested" is a first-class verdict explicitly flagged in the side panel; one-test failures don't trigger phantom status (Adjudicator's veto-aware rule); side panel labels which test acted as veto vs supporting. Records with too few testable signals show a "evidence too thin to verdict" state, not a forced verdict.
- **State persistence:** Phantom verdicts persist across refresh; planner overrides persist; saved scenarios survive reload — desert configuration, override set, planner reason notes all reload identically; district scores recompute deterministically from persistent state.
- **Human-in-the-loop override:** `team.planner_overrides` writes; `force_real` / `force_phantom` with required reason; the override flips the verdict and visibly recomputes the district score on the next toggle.

### Ambition signal
Beyond Track 2's minimum workflow ("select region → aggregate → drill down → save scenario"), this proposal ships a **subtraction-driven rescoring engine** with five pluggable existence tests, two adversarial agents reconciled by a deterministic majority-with-veto adjudicator, per-district incremental recompute via CDC (rather than full re-batch), a third dataset (India Post) used in a load-bearing way, and **dual hands-free exports (S3 watched prefix + mock HMIS webhook) firing in the same demo turn** — combinations most teams will not bother with.

---

## 4. Fragility to Dataset Issues

### Dataset correlations this idea depends on
- Correlation: VF claimed PIN ↔ India Post PIN-and-coordinate directory
  - Depends on: clean dedup of post-office fan-out before joining on `pincode`; enough facilities have both a claimed postcode and lat/long so the reverse-lookup test returns a usable signal.
  - Day-0 validation: 95.5% of facility PINs resolve to India Post; 96.6% of facilities have both PIN and lat/lon. Strong.
  - Breaks if: lat/long missing for the demo region, or PIN maps to multiple districts. Mitigation: the test is *"PIN inconsistent"*, not *"PIN missing"* — missing data does not fail this test.
- Correlation: VF facility lat/long ↔ NFHS-5 district indicators (via spatial join)
  - Depends on: high enough share of facilities geocode into districts so the NFHS outcome consistency test has signal; point-in-polygon spatial join (per the brief's recommendation).
  - Day-0 validation: 99.9% of facilities point-in-polygon to an ADM2 district, 0% multi-assigned. 93.8% of spatial districts exact-match an NFHS row. Strong.
  - Breaks if: spatial join coverage low or fanned out; pivot the demo to one or two states with strong coverage. Mitigation: skip the NFHS-consistency test when the join is ambiguous (don't fail it falsely).
- Correlation: VF structured-claim arrays (`capability` / `procedure` / `equipment`) ↔ MinHash near-duplicate fingerprints
  - Depends on: the structured-claim fields being populated and rich enough that MinHash signatures are meaningful.
  - Day-0 validation: 99.7% population rate on each; content is dense and unambiguous (procedures, equipment lists, capability statements). Exact-match dedup alone already groups 250 facilities into 92 near-identical clusters — non-trivial baseline before MinHash even runs.
  - **Note: original draft used `description` as the uniqueness signal — abandoned.** Description p50 = 16 tokens; Jaccard 0.9 + shingle 5 won't survive. The structured-claim arrays are 10–20× richer per facility.
  - Breaks if: structured claims dominated by short template phrases ("OPD services", "24x7 Emergency"), or legitimate template text from chain hospitals (Apollo, Fortis, Manipal) produces false positives. Day-0 false-positive check on Apollo (n=48): only 2 facilities (4%) duplicate-flagged — well under 30% threshold. Mitigation: tune Jaccard threshold offline; document trade-off in the verdict receipt.

### External dependencies
- **Facility coordinates required?** ☑ Yes ☐ Only as fallback ☐ No — load-bearing for spatial join and PIN reverse-lookup test (reduced demo region if necessary).
- **PIN→district join required?** ☑ Yes ☐ No — used as a load-bearing verification test, not just enrichment; via spatial join with PIN directory as the geocoding source.
- **NFHS-5 dependency?** ☑ Required ☐ Optional/contextual ☐ None — outcome consistency is one of the three core tests; story degrades materially without it.
- **Free-text quality dependency?** ☐ High (semantic parsing) ☑ Medium ☐ Low — MinHash on descriptions for the uniqueness test; very low text quality degrades the duplicate-detection signal.

### Worst-case demo failure mode
On a sparse district, all five existence tests return "indeterminate" → Adjudicator verdict is "contested" → district sees no phantom subtraction and the desert score is unchanged. **Graceful caveat:** side panel shows "0 phantoms detected — too little geographic data to test (district sparsity flag)" rather than a misleading "0 phantoms = real coverage" verdict. Users see *why* the district is data-poor — itself a planning insight. Misleading-result risk: high MinHash false-positive rate could subtract real facilities (e.g. franchised clinic chains using template `capability` arrays) — mitigated by treating MinHash alone as supporting evidence, never as the veto. Day-0 chain audit: 4% on Apollo (n=48).

### Day-0 audit outcomes (resolved)
*All mitigations below were either triggered or pre-emptively applied based on the 2026-06-15 validation run. Recorded here for the record.*
- ✅ **Demo state locked: Maharashtra.** Bihar fails T3.2 (24 single-flag facilities, 15 districts). Maharashtra: 304 phantom candidates, 33 districts, BEED rank shift 10→2.
- ✅ **NFHS-5 consistency test re-spec'd.** Original "indicator didn't move" requires NFHS-6 longitudinal comparison and is out of scope. Replacement: "facility claims capability X in a district whose NFHS-5 indicator for X sits in the bottom quartile of the state." Snapshot inconsistency, same story, implementable today.
- ✅ **Uniqueness test moved off `description` onto `capability`+`procedure`+`equipment`.** Description p50 = 16 tokens — too short for Jaccard 0.9 + shingle 5. Structured-claim arrays are 99.7% populated and far richer per facility.
- ✅ **`address_stateOrRegion` excluded from the input contract.** 254 distinct values vs. 36 real states; contains JSON fragments, city names, multi-state strings. State is derived from coordinates via the ADM2 spatial join.
- ✅ **`source_content_id` re-classified as page-level, not facility-level.** 27 different hospitals can share one scid. Used only as a citation back-reference. `phantom_verdicts` keys on `unique_id` (with the 11 row-twin duplicates dropped via `SELECT DISTINCT` at ingest).
- ✅ **Spatial join data sourced.** geoBoundaries India ADM2 (735 polygons, 48 MB GeoJSON) downloaded via GitHub LFS media endpoint — geoboundaries.org direct hits sandbox firewall.

### Open mitigations (not yet triggered)
- If MinHash false-positive rate on `capability` arrays turns out higher than 4% chain baseline once tuned: raise Jaccard threshold and/or require 5+ near-duplicate matches; document visibly in the verdict receipt.

### Robustness verdict
☐ Fragile — relies on sparse fields; missing data → broken UX
☑ **Mixed** — has a plan for sparsity but bleeds at edges (e.g., geographic joins)
☐ Robust — depends on highly-populated fields; sparsity → graceful degradation
☐ Anti-fragile — sparsity *is* the input; missing data increases value

**Justification:** The five-test architecture tolerates per-facility sparsity (any test can abstain) and the toggle-and-redraw mechanic degrades cleanly when test signals are missing (verdict = contested, no subtraction); but the *spatial joins* — central to two of the most visceral tests — bleed at the edges where coordinates and PINs disagree, and the demo's dramatic redraw moment requires enough phantoms in the demo region to be visible, which requires a deliberate state choice and coverage check on day one.
