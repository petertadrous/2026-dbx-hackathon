# Phantom Census — Proposal Changes (Day-0 Validation Patch)

**Source:** `idea_phantom_census.md`
**Patch date:** 2026-06-15
**Basis:** `phantom_census_validation_results.md` + `phantom_census_schema_audit.md`
**Net verdict:** Green-light. Three locked changes, two non-blocking gotchas. Rubric score and robustness verdict unchanged.

This file is a **delta-only changelog** intended for downstream systems already working off the original proposal. Each change block names the section, quotes the original passage, and gives the replacement.

---

## Change 1 — Demo state pivots Bihar → Maharashtra

**Why:** Bihar fails T3.2 phantom-yield gate (24 single-flag facilities across 15 districts, threshold ≥50). Maharashtra yields 304 phantom candidates across 33 districts; BEED ranking shifts 10→2 between raw and phantom-adjusted desert scores — the headline shuffle for the demo's wow moment.

### 1a. Workflow step 3 example district
**Section:** `## 1. High-Level Design` → `Primary workflow (≤5 steps)` → step 3

**Was:**
> 3. Click a district (e.g. Nalanda) → side panel with example phantoms, each rendered with three failed existence tests + supporting public-dataset rows.

**Now:**
> 3. Click a district (e.g. BEED, Maharashtra) → side panel with example phantoms, each rendered with three failed existence tests + supporting public-dataset rows.

### 1b. Demo arc table (full replacement)
**Section:** `## 3. Presentation & Wow Factor` → `3-minute demo arc` table

**Was:**
> | Time | What's on screen | What the presenter says |
> |------|------------------|-------------------------|
> | 0:00–0:20 | India choropleth, official desert score by district. | "Every desert map you've seen is wrong. Most maps add up the facilities they can find. We're going to *subtract* the ones that don't actually exist — because today's planners fund the loud districts, not the sick ones." |
> | 0:20–0:50 | Toggle **subtract phantoms** → map redraws; ranking visibly shuffles; counter ticks "1,247 phantoms removed." | "One toggle. Five existence tests fired against ten thousand records. The map redraws, the rank shuffles. Some districts you thought were fine just got worse — their facility counts were inflated by phantoms." |
> | 0:50–1:50 | Click a now-redder district (Nalanda) → side panel with three example phantoms; each shows three failed test rows with supporting evidence. | "Phantom A: PIN says Patna, lat/lon says Gaya — fails India Post reverse-lookup. Phantom B: description is a 0.97-Jaccard near-duplicate of 14 others. Phantom C: claims maternity in a district where NFHS-5 says institutional-delivery rate didn't move. Three independent failures. Not one expert opinion — three deterministic tests." |
> | 1:50–2:20 | Override panel — planner forces Phantom A back to "real" with a required reason note; district score recomputes live; saved to Lakebase. | "I just visited this one personally. Override force-real, with a required note. District score updates in under a second. The override is part of the scenario." |
> | 2:20–2:50 | Click **export plan**: CKAN-compatible CSV lands in S3 watched prefix; HMIS webhook fires. Save scenario "Q3 Bihar Maternity Audit"; reload page; map and overrides survive. | "CKAN-compatible CSV in the S3 prefix. Webhook fires the mock state HMIS with the priority delta. Two integrations, one click. Save the scenario. Reload — survives." |
> | 2:50–3:00 | `token_usage: 0` panel; Bihar headline ranking diff "7th → 2nd"; differentiation hook on screen. | "Nalanda is the second-worst desert in Bihar, not the seventh. Token usage: zero. Every other desert map will *add* facilities to find gaps. We *subtract* fictional ones to expose deserts hiding in plain sight." |

**Now:**
> | Time | What's on screen | What the presenter says |
> |------|------------------|-------------------------|
> | 0:00–0:20 | Maharashtra choropleth, official desert score by district. | "Every desert map you've seen is wrong. Most maps add up the facilities they can find. We're going to *subtract* the ones that don't actually exist — because today's planners fund the loud districts, not the sick ones." |
> | 0:20–0:50 | Toggle **subtract phantoms** → map redraws; ranking visibly shuffles; counter ticks "304 phantoms removed across 33 districts." | "One toggle. Five existence tests fired against ten thousand records. The map redraws, the rank shuffles. Some districts you thought were fine just got worse — their facility counts were inflated by phantoms." |
> | 0:50–1:50 | Click a now-redder district (BEED) → side panel with three example phantoms; each shows three failed test rows with supporting evidence. | "Phantom A: PIN says Aurangabad, lat/lon says Solapur — fails India Post reverse-lookup. Phantom B: capability and procedure claims are a near-duplicate of 14 other facilities scraped from the same source page. Phantom C: claims maternity in a district where NFHS-5 institutional-delivery rate sits in the bottom quartile. Three independent failures. Not one expert opinion — three deterministic tests." |
> | 1:50–2:20 | Override panel — planner forces Phantom A back to "real" with a required reason note; district score recomputes live; saved to Lakebase. | "I just visited this one personally. Override force-real, with a required note. District score updates in under a second. The override is part of the scenario." |
> | 2:20–2:50 | Click **export plan**: CKAN-compatible CSV lands in S3 watched prefix; HMIS webhook fires. Save scenario "Q3 Maharashtra Maternity Audit"; reload page; map and overrides survive. | "CKAN-compatible CSV in the S3 prefix. Webhook fires the mock state HMIS with the priority delta. Two integrations, one click. Save the scenario. Reload — survives." |
> | 2:50–3:00 | `token_usage: 0` panel; Maharashtra headline ranking diff "BEED: 10th → 2nd-worst desert"; differentiation hook on screen. | "BEED is the second-worst desert in Maharashtra, not the tenth. Token usage: zero. Every other desert map will *add* facilities to find gaps. We *subtract* fictional ones to expose deserts hiding in plain sight." |

---

## Change 2 — Uniqueness test moves off `description` onto `capability` + `procedure` + `equipment`

**Why:** Description p50 = 16 tokens (T1.4 fails ≥50 token threshold). MinHash @ Jaccard 0.9 + shingle 5 won't produce useful signatures on text that short. The structured-claim JSON-array fields are 99.7% populated each, 10–20× richer per facility, and contain the exact claim payload the proposal cares about (procedures, equipment, capability statements).

### 2a. Inputs paragraph
**Section:** `## 1. High-Level Design` → `Inputs:`

**Was:**
> - **Inputs:** VF facility records (description / capability / procedure / lat-long / postcode), India Post PIN directory (165k rows; cardinality-aware: PIN→post-office is one-to-many), NFHS-5 district indicators (706 × 109), district shapefiles for spatial join, planner overrides, threshold configs (Jaccard, NFHS-consistency).

**Now:**
> - **Inputs:** VF facility records (rich `capability` / `procedure` / `equipment` JSON-array fields are 99.7% populated and used as the primary claim text; `description` is supporting context only — p50 = 16 tokens, too short for the uniqueness test); India Post PIN directory (165k rows; cardinality-aware: PIN→post-office is one-to-many); NFHS-5 district indicators (706 × 109, already snake_cased + numeric in the marketplace share); geoBoundaries India ADM2 shapefile (735 polygons, downloaded — geoboundaries.org direct is sandbox-blocked, use GitHub LFS media endpoint) for spatial join; planner overrides; threshold configs (Jaccard, NFHS bottom-quartile cutoff).
> - **Fields explicitly NOT trusted as input:** `address_stateOrRegion` (contaminated — 254 distinct values vs. 36 real states; contains JSON fragments and city names; state is derived from coordinates via spatial join instead); `source_content_id` (per-source-page ID, NOT entity-level — used only as a citation back-reference, never as a join key or facility identifier).

### 2b. Fragility correlation block
**Section:** `## 4. Fragility to Dataset Issues` → `Dataset correlations this idea depends on` → third bullet

**Was:**
> - Correlation: VF description text ↔ MinHash near-duplicate fingerprints
>   - Depends on: descriptions long enough that MinHash signatures are meaningful.
>   - Breaks if: descriptions dominated by very short or template-headered text, or legitimate template text (chain hospital boilerplate) produces false positives. Mitigation: tune Jaccard threshold offline against held-out set; document trade-off in the verdict receipt.

**Now:**
> - Correlation: VF structured-claim arrays (`capability` / `procedure` / `equipment`) ↔ MinHash near-duplicate fingerprints
>   - Depends on: the structured-claim fields being populated and rich enough that MinHash signatures are meaningful.
>   - Day-0 validation: 99.7% population rate on each; content is dense and unambiguous (procedures, equipment lists, capability statements). Exact-match dedup alone already groups 250 facilities into 92 near-identical clusters — non-trivial baseline before MinHash even runs.
>   - **Note: original draft used `description` as the uniqueness signal — abandoned.** Description p50 = 16 tokens; Jaccard 0.9 + shingle 5 won't survive. The structured-claim arrays are 10–20× richer per facility.
>   - Breaks if: structured claims dominated by short template phrases ("OPD services", "24x7 Emergency"), or legitimate template text from chain hospitals (Apollo, Fortis, Manipal) produces false positives. Day-0 false-positive check on Apollo (n=48): only 2 facilities (4%) duplicate-flagged — well under 30% threshold. Mitigation: tune Jaccard threshold offline; document trade-off in the verdict receipt.

### 2c. Worst-case failure mode (Apollo callout)
**Section:** `## 4. Fragility to Dataset Issues` → `Worst-case demo failure mode`

**Was (final sentence):**
> Misleading-result risk: high MinHash false-positive rate could subtract real facilities (e.g. franchised clinic chains using template descriptions) — mitigated by treating MinHash alone as supporting evidence, never as the veto.

**Now (final sentence):**
> Misleading-result risk: high MinHash false-positive rate could subtract real facilities (e.g. franchised clinic chains using template `capability` arrays) — mitigated by treating MinHash alone as supporting evidence, never as the veto. Day-0 chain audit: 4% on Apollo (n=48).

### 2d. Information Extraction agent description
**Section:** `## 2. Databricks Technologies & Centrality` → `Agent Bricks` → bullet for Information Extraction

**Was:**
> - **Information Extraction** also runs offline to pull staff/equipment claims from free text for the Defender.

**Now:**
> - **Information Extraction** runs offline to pull staff/equipment/procedure claims from the `capability`/`procedure`/`equipment` JSON-array fields (already structured, just need `from_json` cast) for the Defender; description free-text is supporting context only.

---

## Change 3 — NFHS consistency test re-spec: "indicator didn't move" → "bottom-quartile snapshot inconsistency"

**Why:** "Didn't move" implies a delta against a prior snapshot — that requires NFHS-6 (2023–24), which the proposal lists as optional/stretch only. NFHS-5 alone is a single 2019–21 cross-section. Re-spec preserves the same narrative beat ("claims maternity but the district indicator says otherwise") with implementable math against the data on hand. Bihar institutional-birth range 21.4–93.2%; Maharashtra range 76.3–100%; bottom-quartile cutoffs produce real contrast.

### 3a. Phantom C in demo arc
*(already covered by Change 1b — the demo arc table replacement.)*

### 3b. Adjudicator and Defender descriptions
**Section:** `## 2. Databricks Technologies & Centrality` → `Agent Bricks` → agent roles

**Was:**
> - **Existence Defender** — looks for corroborating signals (multiple distinct source URLs, government registration matches, named staff in NFHS denominators) to **rescue** accused phantoms.
> - **Adjudicator** — deterministic majority-with-veto rule (PIN failure = hard veto; description-uniqueness alone is not). **No LLM.**

**Now:**
> - **Existence Defender** — looks for corroborating signals (multiple distinct source URLs, government registration matches, named staff in NFHS denominators) to **rescue** accused phantoms. Critically, the Defender owns the **dataset-version reconciliation layer**: a PIN-vs-spatial disagreement caused by post-2022 district reorganization (Bapatla carved from Prakasam, NTR from Krishna) or spelling drift (Mysore↔Mysuru, Ahmadnagar↔Ahmednagar) must be rescued, not flagged. Day-0 validation showed ~9pp of the 24.5% raw PIN-vs-spatial disagreement is in this bucket.
> - **Adjudicator** — deterministic majority-with-veto rule (PIN failure = hard veto; claim-uniqueness alone is not). **No LLM.**

---

## Change 4 — Add a "Day-0 audit outcomes" section to Fragility

**Why:** Records the resolved mitigations from the Day-0 validation run so downstream readers (and reviewers) can verify the proposal isn't still ducking the open questions it raised.

**Section:** `## 4. Fragility to Dataset Issues` → replaces the `Mitigation if Day-1 data audit reveals a problem` block

**Was:**
> ### Mitigation if Day-1 data audit reveals a problem
> - If India Post coverage too thin for demo region: drop PIN test from *core demo path* (still computed for side panel) and lead the redraw with MinHash + NFHS consistency tests.
> - If lat/lon coverage too thin: scope demo to states with >70% facility geocoding (likely Maharashtra, Karnataka, Tamil Nadu) and explicitly mark this as the audited region in the dashboard.
> - If MinHash false-positive rate too high: raise Jaccard threshold and/or require 5+ near-duplicate matches (not 2+); document visibly in the verdict receipt.
> - If NFHS-5 spatial join unreliable: drop NFHS-consistency test from MVP and lean on PIN reverse-lookup + uniqueness.
> - Pre-decide a single demo state where coverage and data quality are best by hour 4 and lock it.

**Now:**
> ### Day-0 audit outcomes (resolved)
> *All mitigations below were either triggered or pre-emptively applied based on the 2026-06-15 validation run. Recorded here for the record.*
> - ✅ **Demo state locked: Maharashtra.** Bihar fails T3.2 (24 single-flag facilities, 15 districts). Maharashtra: 304 phantom candidates, 33 districts, BEED rank shift 10→2.
> - ✅ **NFHS-5 consistency test re-spec'd.** Original "indicator didn't move" requires NFHS-6 longitudinal comparison and is out of scope. Replacement: "facility claims capability X in a district whose NFHS-5 indicator for X sits in the bottom quartile of the state." Snapshot inconsistency, same story, implementable today.
> - ✅ **Uniqueness test moved off `description` onto `capability`+`procedure`+`equipment`.** Description p50 = 16 tokens — too short for Jaccard 0.9 + shingle 5. Structured-claim arrays are 99.7% populated and far richer per facility.
> - ✅ **`address_stateOrRegion` excluded from the input contract.** 254 distinct values vs. 36 real states; contains JSON fragments, city names, multi-state strings. State is derived from coordinates via the ADM2 spatial join.
> - ✅ **`source_content_id` re-classified as page-level, not facility-level.** 27 different hospitals can share one scid. Used only as a citation back-reference. `phantom_verdicts` keys on `unique_id` (with the 11 row-twin duplicates dropped via `SELECT DISTINCT` at ingest).
> - ✅ **Spatial join data sourced.** geoBoundaries India ADM2 (735 polygons, 48 MB GeoJSON) downloaded via GitHub LFS media endpoint — geoboundaries.org direct hits sandbox firewall.
>
> ### Open mitigations (not yet triggered)
> - If MinHash false-positive rate on `capability` arrays turns out higher than 4% chain baseline once tuned: raise Jaccard threshold and/or require 5+ near-duplicate matches; document visibly in the verdict receipt.

---

## Change 5 — Augment per-correlation Day-0 numbers

**Why:** Records the empirical pass/fail evidence beside each correlation claim so the proposal's risk story is grounded in measurements, not assertions.

**Section:** `## 4. Fragility to Dataset Issues` → `Dataset correlations this idea depends on` → first two bullets

**Was:**
> - Correlation: VF claimed PIN ↔ India Post PIN-and-coordinate directory
>   - Depends on: clean dedup of post-office fan-out before joining on `pincode`; enough facilities have both a claimed postcode and lat/long so the reverse-lookup test returns a usable signal.
>   - Breaks if: lat/long missing for the demo region, or PIN maps to multiple districts. Mitigation: the test is *"PIN inconsistent"*, not *"PIN missing"* — missing data does not fail this test.
> - Correlation: VF facility lat/long ↔ NFHS-5 district indicators (via spatial join)
>   - Depends on: high enough share of facilities geocode into districts so the NFHS outcome consistency test has signal; point-in-polygon spatial join (per the brief's recommendation).
>   - Breaks if: spatial join coverage low or fanned out; pivot the demo to one or two states with strong coverage. Mitigation: skip the NFHS-consistency test when the join is ambiguous (don't fail it falsely).

**Now (add a Day-0 line under each):**
> - Correlation: VF claimed PIN ↔ India Post PIN-and-coordinate directory
>   - Depends on: clean dedup of post-office fan-out before joining on `pincode`; enough facilities have both a claimed postcode and lat/long so the reverse-lookup test returns a usable signal.
>   - **Day-0 validation: 95.5% of facility PINs resolve to India Post; 96.6% of facilities have both PIN and lat/lon. Strong.**
>   - Breaks if: lat/long missing for the demo region, or PIN maps to multiple districts. Mitigation: the test is *"PIN inconsistent"*, not *"PIN missing"* — missing data does not fail this test.
> - Correlation: VF facility lat/long ↔ NFHS-5 district indicators (via spatial join)
>   - Depends on: high enough share of facilities geocode into districts so the NFHS outcome consistency test has signal; point-in-polygon spatial join (per the brief's recommendation).
>   - **Day-0 validation: 99.9% of facilities point-in-polygon to an ADM2 district, 0% multi-assigned. 93.8% of spatial districts exact-match an NFHS row. Strong.**
>   - Breaks if: spatial join coverage low or fanned out; pivot the demo to one or two states with strong coverage. Mitigation: skip the NFHS-consistency test when the join is ambiguous (don't fail it falsely).

---

## Change 6 — Day-0 validation callout at the top of the doc

**Why:** Single-screen summary so any reader knows the proposal has been audited and what shifted, without reading the full diff.

**Section:** Insert **between the one-liner block and the `## Snapshot` header**.

**Insert:**
> > **Day-0 Validation Update (2026-06-15).** Full validation suite (`phantom_census_validation_results.md`) and schema audit (`phantom_census_schema_audit.md`) executed against the live Databricks Marketplace share. Both kill-switches cleared (geocoding 98.8%; PIN-vs-spatial 24.5% disagreement after light normalization). Three locked-in changes vs. the original draft below: (1) **demo state pivots Bihar → Maharashtra**, Bihar yields only 24 single-flag phantoms (fails T3.2 ≥50); Maharashtra yields 304 phantoms across 33 districts with BEED rank 10→2 as the headline shuffle. (2) **Uniqueness test moves off `description` onto `capability`+`procedure`+`equipment`** — description p50 is 16 tokens, MinHash@Jaccard 0.9 + shingle-5 won't work; the structured-claim arrays are 99.7% populated and far richer. (3) **NFHS-consistency test re-spec'd from "indicator didn't move" → "claims capability X in a bottom-quartile NFHS district for X"** — NFHS-5 is a snapshot, "didn't move" requires NFHS-6 longitudinal which is out of scope. Two additional non-blocking gotchas the implementation must respect: `address_stateOrRegion` is contaminated (254 distinct values vs. 36 real states — derive from coordinates) and `source_content_id` is a per-source-page ID (NOT an entity key — 27 different hospitals can share one).

---

## Things that did NOT change

- **Track** — still Track 2 Medical Desert with a Track 1 twist.
- **One-liner** — "Subtract statistically nonexistent facilities first — every desert map is wrong until you do."
- **Rubric score** — 23/25 unchanged; the Day-0 audit confirmed the components, didn't move them.
- **MVP effort estimate** — still M (20–35h), ~30.5h + 6h buffer across 3 engineers.
- **Lakebase / Agent Bricks / Apps centrality** — load-bearing / supporting / load-bearing respectively, unchanged.
- **CKAN CSV + mock HMIS webhook** export contract — unchanged.
- **Wow moment** — "the toggle and the redraw" — unchanged.
- **Out-of-scope list** — unchanged.
- **Robustness verdict** — still "Mixed" (the geographic-join edges are exactly where Day-0 confirmed there's reconciliation work).

---

## How to apply (for a downstream system)

If you maintain a parsed/structured copy of `idea_phantom_census.md`:

1. Apply Changes 1a, 1b, 2a, 2b, 2c, 2d, 3b, 4, 5 as straight text replacements (each block above shows the exact old → new strings).
2. Insert Change 6's callout between the one-liner block and the `## Snapshot` header.
3. Change 3a is **already subsumed by Change 1b** (the demo arc table replacement). Don't apply twice.
4. After applying, the only remaining mentions of "Bihar" / "Nalanda" / "description … Jaccard" / "didn't move" should be in the Day-0 callout and the resolved-mitigations section — those are intentional.

A reference copy of the fully-patched proposal is in `idea_phantom_census.md` in the same repo, patched in-place at the same time as this delta file.
