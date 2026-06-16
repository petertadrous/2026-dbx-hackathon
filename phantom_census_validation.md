# Phantom Census — Day-0 Data Validation Suite

Run these tests **before writing any product code**. The goal is to prove the idea is even possible against the real (messy) data. Stop and pivot at the first hard failure.

---

## Datasets you need

### Required (idea is dead without these)

1. **Virtue Foundation facility records** (the hackathon dataset)
   - Expected columns: `facility_id`, `description`, `capability` / `procedure`, `latitude`, `longitude`, `pincode`, `state`, `district` (names will vary — confirm on load)
   - Expected size: ~10k rows (hackathon brief implies this order of magnitude)
   - Source: provided by hackathon organizers

2. **India Post PIN Code Directory** — `india_post_pincode_directory.csv`
   - 165,627 rows, 11 columns: `circlename, regionname, divisionname, officename, pincode, officetype, delivery, district, statename, latitude, longitude`
   - ~19,586 unique PINs, 750 districts, 37 states/UTs
   - ~12,600 rows have NA lat/lon
   - **Row grain is post office, not PIN** — a single PIN can map to multiple districts. Always dedup or aggregate before joining.
   - Source: https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month
   - License: Government Open Data License – India

3. **NFHS-5 District Health Indicators** — `nfhs5_district_health_indicators.csv`
   - 706 district rows × 109 columns
   - Indicators include institutional-delivery rate, ANC visits, C-section rate, vaccination, nutrition, anaemia, NCDs
   - `*` values = suppressed → treat as NULL. Parenthesized values like `(29.5)` = low-confidence estimates.
   - Source: https://www.data.gov.in/catalog/national-family-health-survey-5-nfhs-5-india-districts-factsheet-data-provisional
   - License: Government Open Data License – India

4. **District boundary shapefiles** (for point-in-polygon spatial join)
   - geoBoundaries: https://www.geoboundaries.org (India, ADM2 level)
   - Or DataMeet India Maps: https://datameet.org
   - Required because string-matching district names across datasets is unreliable.

### Optional / stretch
- NFHS-6 (2023–24) for indicator drift comparison — only if you do longitudinal analysis.
- Alternate boundary source as fallback if the primary shapefile mismatches NFHS-5 districts.

### Tooling
- **Python**: pandas, geopandas, shapely, datasketch (for MinHash), pyproj
- **Databricks**: `ST_Contains`, `ST_Point` (validate availability on Free Edition; fall back to GeoPandas in-process — 10k facilities × ~700 polygons fits a single worker)

---

## Tier 0 — Existence checks (15 min)

Confirm the data files even loaded correctly.

### T0.1 — VF rows load
- **Compute:** row count; non-null counts for `facility_id`, `description`, `pincode`, `latitude`, `longitude`
- **Pass:** ≥5,000 rows with non-null `facility_id` and `description`, and at least one of `{pincode, lat, lon}` populated
- **Fail action:** product is dead — pick a different idea

### T0.2 — India Post loads with expected shape
- **Compute:** row count, column count, `nunique(pincode)`, count of NA `latitude`
- **Pass:** ~165k rows, 11 columns, ~19,586 unique PINs, ~12,600 NA lat/lon (±10%)
- **Fail action:** column drift or row count off by >10% → re-pull source

### T0.3 — NFHS-5 loads
- **Compute:** row count, column count; confirm institutional-delivery-rate column exists; coerce to numeric after stripping `*` and `(...)` characters
- **Pass:** 706 rows × 109 columns; institutional-delivery column parses to numeric for ≥600 districts
- **Fail action:** indicator missing or unparseable → drop NFHS-consistency test from MVP

---

## Tier 1 — Coverage gates

The product is impossible below these thresholds. **Run T1.1 first** — it's the biggest single risk.

### T1.1 — Facility geocoding rate ★ KILL-SWITCH
- **Compute:** `% facilities with non-null lat AND lon`, broken down by state
- **Green:** ≥70% nationally OR ≥70% in at least one state with ≥500 facilities → demo region locked
- **Yellow (40–70%):** MVP works but demo must be scoped to best-coverage state
- **Red (<40% in every state):** spatial-join tests die → idea collapses to MinHash-only
- **Fail action:** if red, kill the proposal

### T1.2 — PIN presence rate
- **Compute:** `% facilities with a parseable 6-digit pincode` (regex `^\d{6}$` after stripping whitespace)
- **Pass:** ≥60%
- **Fail action:** drop PIN reverse-lookup test from core demo

### T1.3 — Both PIN AND lat/lon present
- **Compute:** `% facilities with both a parseable PIN and non-null lat/lon`
- **Pass:** ≥30%
- **Fail action:** PIN reverse-lookup is the most visceral test — if <30%, it cannot be the headline test; lead with MinHash + NFHS

### T1.4 — Description length distribution
- **Compute:** token count per description; report median, p25, p75; `% with ≥50 tokens`
- **Pass:** ≥50% have ≥50 tokens
- **Fail action:** raise MinHash Jaccard threshold or drop the test

---

## Tier 2 — Join feasibility

Do the three datasets actually talk to each other?

### T2.1 — PIN cardinality audit
- **Compute:** for each PIN in India Post, count distinct districts; after deduping on `(pincode, district)`, report `% PINs that map to exactly one district` and `% to 2+ districts`
- **Pass:** ≥80% one-to-one after dedup
- **Fail action:** PIN→district join is ambiguous; reverse-lookup test must use lat/lon-of-post-office (not district name)

### T2.2 — Spatial join coverage
- **Compute:** point-in-polygon join (facility lat/lon → district shapefile); report `% assigned to a district`, `% assigned to >1 district (boundary edge cases)`, `% unassigned (outside India / offshore)`
- **Pass:** ≥85% assigned, ≤2% multi-assigned
- **Fail action:** try alternate boundary source (geoBoundaries ↔ DataMeet)

### T2.3 — Spatially-joined district ↔ NFHS-5 name match
- **Compute:** after spatial join produces a district name, `% that match an NFHS-5 row` after lowercasing and stripping punctuation
- **Pass:** ≥90%
- **Fail action:** build a district-name normalization layer before MVP (manual mapping for the demo state is fine)

### T2.4 — PIN-claimed district vs spatial-joined district disagreement rate ★ KILL-SWITCH
- **Compute:** among facilities with both a parseable PIN and a successful spatial join, `% where India-Post-PIN-district ≠ spatial-join-district`
- **This is the signal itself — it's the headline test.**
- **Pass:** 5–25%
- **Fail (<5%):** no phantoms detectable — product has nothing to subtract → kill the idea
- **Fail (>40%):** either the join is broken or data is so noisy the test is meaningless → calibrate or pick a different test

---

## Tier 3 — Signal strength

Do phantoms actually exist in detectable quantity?

### T3.1 — MinHash duplicate cluster distribution
- **Compute:** MinHash signatures on descriptions (128 perms, shingle size 5); cluster at Jaccard ≥0.9; report cluster-size histogram
- **Pass:** clusters of size ≥3 cover 1–10% of facilities
- **Fail (too few):** signal absent — drop the test
- **Fail (too many, >30% in mega-clusters):** boilerplate dominates → raise threshold or require corroborating signals

### T3.2 — Phantom yield estimate per demo state
- **Compute:** for the candidate demo state, count facilities failing ≥2 of `{PIN-mismatch, MinHash-duplicate, NFHS-inconsistency}`
- **Pass:** ≥50 phantoms spread across ≥3 districts (visible choropleth shift)
- **Fail action:** redraw won't be visually dramatic → pick a different state or relax thresholds (document the trade-off in the verdict receipt)

### T3.3 — NFHS indicator variance across districts
- **Compute:** std-dev and range of institutional-delivery rate across districts in the demo state
- **Pass:** range >20 percentage points
- **Fail action:** "claims maternity but rate didn't move" has no contrast → drop NFHS-consistency from MVP

### T3.4 — Ranking shuffle magnitude ★ DEMO-CRITICAL
- **Compute:** raw desert score and phantom-adjusted desert score per district in demo state; report top-10 ranking changes
- **Pass:** at least 3 districts move ≥3 positions
- **Fail action:** product works analytically but the demo has no wow — reconsider

---

## Tier 4 — False-positive sanity

Don't subtract real clinics.

### T4.1 — Known-good spot checks
- **Compute:** pick 10 well-known facilities (large urban hospitals — AIIMS Delhi, Apollo Chennai, etc.); run the full pipeline
- **Pass:** 0 of 10 flagged phantom
- **Fail action:** tune Adjudicator veto rules; MinHash threshold likely too aggressive on chain boilerplate

### T4.2 — MinHash false-positive audit on chain clinics
- **Compute:** identify any branded chain in the data (Apollo, Fortis, Manipal, etc. by description keyword); report `% of chain facilities flagged as MinHash-duplicate`
- **Pass:** <30% (chains share boilerplate but shouldn't all be phantoms)
- **Fail action:** require MinHash + at least one geographic test before flagging — never let MinHash veto alone

---

## Decision matrix

| Outcome | Action |
|---|---|
| All Tier 1 + T2.4 + T3.2 + T3.4 pass | Green-light; lock demo state by hour 4 |
| T1.1 fails everywhere | Kill the idea, switch proposal |
| T2.4 <5% | Kill the idea — no phantoms to find |
| T3.4 fails | Works analytically but no demo wow — reconsider |
| T1.2 / T1.3 / T1.4 fail individually | Drop affected test from MVP, lead with survivors |
| T4.1 fails | Tunable — adjust Adjudicator, don't kill |

**Two kill-switches: T1.1 (no coordinates → no spatial product) and T2.4 (no PIN-vs-GPS disagreement → nothing to detect). Run those two first; everything else is tunable.**

---

## Suggested execution order (Day 1, ~4 hours)

1. **Hour 0:00–0:30** — T0.1, T0.2, T0.3 (load all three datasets)
2. **Hour 0:30–1:00** — T1.1 (geocoding rate per state); pick candidate demo state
3. **Hour 1:00–1:30** — T1.2, T1.3, T1.4 (per-test population checks)
4. **Hour 1:30–2:30** — T2.1, T2.2, T2.3 (joins + shapefile)
5. **Hour 2:30–3:00** — T2.4 (the headline disagreement rate) ★
6. **Hour 3:00–3:30** — T3.1, T3.2, T3.3 (signal strength on demo state)
7. **Hour 3:30–4:00** — T3.4 (ranking shuffle), T4.1, T4.2 (false-positive sanity)
8. **Hour 4:00** — Lock demo state. Commit verdict.
