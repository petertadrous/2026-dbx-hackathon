# Phantom Census — Schema & Business-Key Audit

**Date:** 2026-06-15
**Scope:** Are the schemas the proposal plans to build on real? Is `unique_id` a real business key? What's the join-feasibility floor *without* normalization heroics?

---

## 1. Business key on `facilities`

| Question | Answer |
|---|---|
| Is `unique_id` unique? | **No** — 11 rows are exact-row twins of another row (same name, lat/lon, source_content_id). After `SELECT DISTINCT`, the 10,077 surviving rows each have a unique `unique_id`. |
| Is `source_content_id` an entity key? | **Hard NO.** It's a per-source-page ID. **27 distinct hospitals** (different names, different lat/lon, different addresses) can share one `source_content_id` — they were all on the same scraped list page. 406 scid values are shared across 1,345 rows. Do not use as join key, do not use for entity resolution, do not surface in UI as "facility ID". |
| Real entity duplicates across different `unique_id`? | At least 118 rows share `(name, lat, lon)` with another `unique_id`. Bounds the "same hospital scraped twice" rate at ~1%. The 939 `source_content_id` collisions (different hospitals on same source page) are NOT duplicates — they're co-located scrapes. |
| Practical PK | `DISTINCT *` → `unique_id`. Drop the 11 row-twins in ingest. |

**Implication for the proposal:** the `phantom_verdicts` table can key on `unique_id`. Do NOT key on `source_content_id`. Do NOT trust it for entity-level joins.

---

## 2. Per-table schema sanity

### facilities (10,088 rows raw → 10,077 distinct)

| Field | Null/empty | Bad value | Notes |
|---|---|---|---|
| `unique_id` | 0 | — | 11 row twins; otherwise PK after `DISTINCT` |
| `name` | **54 empty** | 5 NULL in state `kie` | Will break MinHash / Adjudicator on those rows; abstain rather than fail |
| `description` | 80 empty | — | 99.2% populated; **p50 = 16 tokens** (T1.4 fails as written in validation suite) |
| `latitude/longitude` | 118 NULL | **6 outside India** (lat∉[6,38] or lon∉[67,98]) | Spatial join must drop OOB |
| `address_zipOrPostcode` | 58 NULL | **104 don't match `^\d{6}$`** (incl. `560 052` with whitespace) | Strip whitespace before regex |
| `address_stateOrRegion` | 58 empty | **254 distinct values vs 36 real states.** Contains city names ("Bhatinda", "Howrah"), neighborhoods ("Annanagar East"), JSON fragments (`{"coordinates":[…]}`), multi-state strings (`"Tamil Nadu; Tamil Nadu; Karnataka; Telangana"`). Only **31/254** facility-state strings exact-match a real NFHS state. | **DO NOT trust this field for filtering or claims.** Derive state from coordinates via spatial join. |
| `capability` / `procedure` / `equipment` | ~27 NULL each (99.7%) | Each is a **JSON-array-shaped STRING**, not a Spark ARRAY | Will need `from_json(..., ARRAY<STRING>)` cast. Content is **rich** — the heart of the trust-signal evidence the proposal needs. |
| `source_urls` | populated | **STRING (JSON array literal)**, content noisy: PubMed, MakeMyTrip hotel pages, generic PMNRF list pages | Citation evidence requires URL-relevance filtering, not just URL presence |

### india_post_pincode_directory (165,627 rows)
| Field | Status |
|---|---|
| `pincode` | 100% populated, BIGINT, 19,586 unique. **Clean PK candidate (one-to-many on rows).** |
| `district` / `statename` | 100% populated |
| `latitude` / `longitude` | STRING — 12,007 rows = `NA`; must `TRY_CAST(... AS DOUBLE)` and drop OOB |
| Row grain | post office, not PIN — 92.5% of PINs map to one district, 7.5% map to 2–4 — **dedup before join** |

### nfhs_5_district_health_indicators (706 rows × 109 cols)
| Field | Status |
|---|---|
| Indicator columns | Already snake_case + numeric DOUBLE in this Databricks share. **No `*` or `(...)` parsing needed.** |
| `district_name` | 100% populated; 698 unique → 8 names repeat across states (e.g. "Aurangabad" in MH & BR). **PK = (state_ut, district_name)**, not district_name alone. |
| `state_ut` | 36 distinct (one spelt `Maharastra`) |

---

## 3. Cross-table join compatibility (without heroics)

| Join | Strict-match rate | Comment |
|---|---|---|
| facility PIN → india_post PIN (parseable PINs) | **95.5%** (2,866 / 3,021 distinct facility PINs resolve) | After whitespace strip. 4.5% are issued PINs not in directory. Clean. |
| facility state string → NFHS state string (exact, no normalization) | **31 / 254 = 12%** | Confirms facility state field is unusable as-is. Must derive state from coords. |
| facility lat/lon → ADM2 polygon (geoBoundaries, point-in-polygon) | **99.9%** assigned | 13 facilities offshore/outside. **0% multi-assigned.** ★ This is the clean path. |
| spatial-joined district → NFHS district (exact, no normalization) | **93.8%** | Already passes T2.3's 90% threshold without fuzzy match. The remaining 6% is real district reorg/spelling drift, not garbage. |
| PIN-claimed district vs spatial-joined district (RAW, no normalization) | **33.7%** disagree | High because: (a) genuine PIN-vs-GPS mismatches (real phantom signal), (b) shapefile predates 2022 AP/Telangana district reorgs (Bapatla, NTR, etc. – not real phantoms), (c) spelling drift (Mysore↔Mysuru, Hydrabad↔Hyderabad, Ahmadnagar↔Ahmednagar). The proposal MUST classify which is which — that's the Adjudicator's job. |

---

## 4. What the proposal must do differently

1. **Ingest cleanup before any joins:**
   - `SELECT DISTINCT *` to kill 11 row twins
   - Reject lat/lon outside India bounding box (6 rows)
   - Reject empty `name` (54) or empty `description` (80) — Adjudicator should output `evidence too thin to verdict` for these, never a phantom verdict
   - Strip whitespace from PIN before regex

2. **Do NOT use `address_stateOrRegion` for filtering.** It contains city names and JSON blobs. Filter by spatial-joined state instead.

3. **Do NOT use `source_content_id` as an entity key.** It's a source-page ID. The proposal's `team.planner_overrides` table should key on `unique_id`. Citations to "source content" should not surface this field as a facility identifier.

4. **District-name reconciliation is the Adjudicator's real job.** The 33.7% PIN-vs-spatial disagreement decomposes into 3 buckets:
   - **Real phantoms** — facility lat/lon points to a totally different state than its PIN
   - **Dataset-version drift** — new districts post-2022 (Bapatla, NTR, etc.) — should NOT count as phantom
   - **Spelling drift** — Mysore/Mysuru, Ahmadnagar/Ahmednagar — should NOT count as phantom
   The proposal's pitch *already* claims the Adjudicator "reconciles opposed signals by deterministic math" — this is exactly that math.

5. **The MinHash/uniqueness test needs a rethink** given p50 description = 16 tokens. Cheaper alternatives:
   - Exact-match (after strip) already finds 250 facilities in 92 clusters — non-trivial signal
   - Char-shingles + low Jaccard for short text
   - Use the rich `capability` / `procedure` / `equipment` fields (mostly 99.7% populated, very rich) instead of `description`. These have the actual claim payload the proposal cares about.

---

## 5. Verdict on dataset readiness

The data is **messy as advertised**, but every join the proposal needs is **structurally feasible**:

- ✅ Facility-level PK exists (`unique_id` after row dedup)
- ✅ Facility → India Post PIN: 95.5% strict resolve
- ✅ Facility → ADM2 polygon: 99.9% spatial assignment, 0% boundary ambiguity
- ✅ ADM2 polygon → NFHS row: 93.8% exact, 98.7% fuzzy
- ⚠ Facility state field is contaminated — derive from coords, do not trust string
- ⚠ `source_content_id` is NOT entity-level — do not key on it
- ⚠ Description tokens are short — MinHash recipe needs adjustment

The messiness is the **product input**, not the blocker. The dataset is ready.
