# Phantom Census — Day-0 Validation Results

**Date:** 2026-06-15
**Catalog:** `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset`
**Compute:** Serverless Starter Warehouse (`46a168f6f4dcf2a4`)
**Verdict:** ✅ **GREEN-LIGHT** — both kill-switches pass; T1.4 (description length) and Bihar-as-demo-state need adjustments.

---

## Dataset availability

| Dataset | Source | Status | Notes |
|---|---|---|---|
| Virtue Foundation facilities | `…virtue_foundation_dataset.facilities` | ✅ | 10,088 rows × 51 cols (matches brief 10k) |
| India Post PIN directory | `…india_post_pincode_directory` | ✅ | 165,627 rows / 19,586 PINs / 750 districts / 37 states — **matches spec exactly** |
| NFHS-5 indicators | `…nfhs_5_district_health_indicators` | ✅ | 706 rows × 109 cols; already snake_cased + numeric (no `*` parsing needed) |
| District shapefile (ADM2) | geoBoundaries / DataMeet | ❌ **MISSING** | Required for T2.2 / T2.3 / true T2.4. Currently using **nearest-PO of claimed PIN** as district proxy. |

**Action needed from you:** confirm we can pull geoBoundaries India ADM2 shapefile (~5 MB GeoJSON). Without it we lose the true spatial join and have to approximate with PIN-PO centroids.

---

## Tier 0 — Existence checks

| Test | Result | Verdict |
|---|---|---|
| T0.1 VF rows | 10,088 rows; 100% non-null `unique_id`; 99.2% description; 99.4% PIN; 98.8% lat/lon | ✅ |
| T0.2 India Post | 165,627 rows / 19,586 PINs / 750 districts / 37 states / 12,007 lat NA | ✅ within ±10% |
| T0.3 NFHS-5 | 706 rows × 109 cols; `institutional_birth_5y_pct` numeric for 706/706 (range 21.4–100, mean 88.7) | ✅ |

---

## Tier 1 — Coverage gates

| Test | Result | Threshold | Verdict |
|---|---|---|---|
| **T1.1 geocoding ★** | 98.8% national; ≥99% in every top-20 state | ≥70% | ✅ **GREEN — kill-switch cleared** |
| T1.2 PIN presence | 96.9% parseable 6-digit PIN | ≥60% | ✅ |
| T1.3 PIN + lat/lon | 96.6% have both | ≥30% | ✅ |
| T1.4 description ≥50 tokens | **12.0%** (p25=10, p50=16, p75=31) | ≥50% | ❌ **FAIL** |

**T1.4 mitigation:** Descriptions are much shorter than the validation suite assumed. Raise MinHash threshold or move to character-shingles + lower-Jaccard, or run exact-match dedup as the primary uniqueness test (already detects 250 facilities in 92 duplicate clusters — see T3.1).

---

## Tier 2 — Join feasibility

| Test | Result | Threshold | Verdict |
|---|---|---|---|
| T2.1 PIN→district one-to-one | 92.5% (max 4 districts per PIN) | ≥80% | ✅ |
| T2.2 spatial-join coverage | **deferred — no shapefile** | ≥85% | ⏸ |
| T2.3 spatial→NFHS name match | **deferred — no shapefile** | ≥90% | ⏸ |
| **T2.4 PIN-vs-GPS disagreement ★ (proxy)** | **10.8%** facilities >100 km from claimed-PIN PO centroid; **4.6%** in a different state than claimed PIN | 5–25% | ✅ **GREEN — kill-switch cleared (proxy)** |

T2.4 used distance from facility (lat/lon) to the nearest post-office centroid of its claimed PIN (in lieu of true point-in-polygon). True signal once we have the shapefile is expected to be similar order — the inputs to both methods are the same coords.

---

## Tier 3 — Signal strength

| Test | Result | Threshold | Verdict |
|---|---|---|---|
| T3.1 dup clusters (exact match only) | 92 clusters / 250 facilities (2.5%); 124 in clusters ≥3 (1.2%); biggest cluster = 22 | ≥3-clusters cover 1–10% | ✅ (lower bound; MinHash will lift) |
| T3.2 phantom yield per state (PIN + dup, 2-of-2) | **see table below** | ≥50 phantoms / ≥3 districts | ✅ for 9 states; ❌ for Bihar |
| T3.3 NFHS institutional-birth variance | Bihar 38.6pp, UP 33pp, MP 29.5pp range | range >20pp | ✅ |
| **T3.4 ranking shuffle ★** | Maharashtra: ≥6 districts shift ≥3; BEED 10→2, OSMANABAD 9→2; UP: FARRUKHABAD 41→1 | ≥3 districts shift ≥3 | ✅ |

### T3.2 phantom yield per state (top)

| State | Facilities | PIN-mm | Dups | Any flag | Districts flagged | T3.2 |
|---|---:|---:|---:|---:|---:|---|
| Maharashtra | 1,573 | 264 | 54 | **304** | 33 | ✅ |
| Uttar Pradesh | 913 | 174 | 26 | 194 | 43 | ✅ |
| Gujarat | 978 | 162 | 11 | 171 | 26 | ✅ |
| Tamil Nadu | 774 | 128 | 15 | 138 | 27 | ✅ |
| Karnataka | 525 | 69 | 13 | 81 | 24 | ✅ |
| Andhra Pradesh | 329 | 55 | 9 | 63 | 18 | ✅ |
| Rajasthan | 406 | 50 | 11 | 60 | 18 | ✅ |
| Punjab | 467 | 46 | 12 | 56 | 16 | ✅ |
| Madhya Pradesh | 301 | 42 | 5 | 47 | 18 | ⚠ (close) |
| Bihar | 256 | 20 | 4 | **24** | 15 | ❌ **fail** |

**Demo-state pivot recommended: Maharashtra (best density) or Uttar Pradesh (most dramatic shuffles).** The proposal's Bihar/Nalanda narrative does not have the headline phantom count for the wow moment.

---

## Tier 4 — False-positive sanity (partial)

| Test | Result | Verdict |
|---|---|---|
| T4.2 chain clinic dup rate (Apollo, n=48) | 2/48 = 4.2% duplicate-flagged | ✅ (<30%) |
| T4.1 known-good spot checks | not yet — needs full pipeline | ⏸ |

---

## Decision matrix outcome

| Required gate | Status |
|---|---|
| All Tier 1 pass | ⚠ T1.4 fails, T1.1/T1.2/T1.3 pass — recoverable (tune MinHash) |
| T2.4 5–25% (kill-switch) | ✅ 10.8% (proxy) |
| T3.2 yield (≥50 phantoms in ≥3 districts) | ✅ for Maharashtra/UP, ❌ for Bihar |
| T3.4 ranking shuffle (3 districts ≥3) | ✅ |

**Net:** Green-light the proposal. Two changes required vs. current `idea_phantom_census.md`:
1. **Switch demo state from Bihar to Maharashtra** (or UP). Bihar fails T3.2 — 24 phantoms in 15 districts is not enough for the visceral redraw.
2. **Replace MinHash @ Jaccard 0.9 + shingle-5** with either exact-match dedup or character-shingles at lower Jaccard. Descriptions are too short (p50=16 tokens) for the original recipe.

---

## Datasets still needed

1. **India ADM2 (district) shapefile** — geoBoundaries or DataMeet. Required to convert the T2.4 *proxy* into the real spatial-join test and to enable T2.2 / T2.3 / true T3.2 with NFHS-consistency.
2. *(Optional)* NFHS-6 (2023–24) — only if we want longitudinal drift in the verdict receipt. Skip for MVP.

Everything else (VF facilities, India Post, NFHS-5) is in the Databricks marketplace catalog already.

---

## Methodology notes / caveats

- **PIN parsing**: stripped internal whitespace before regex (`560 052` style PINs need cleanup before `^\d{6}$`).
- **India Post lat/lon**: 12,007 rows have NA. Restricted to lat∈[6,38], lon∈[67,98] to drop bad coords.
- **District proxy**: PIN-claimed district = district of nearest post office of that PIN. Real shapefile join will give cleaner edges (PIN boundaries don't follow district boundaries cleanly).
- **NFHS column names**: dataset arrives already snake_cased + numeric in this Databricks share. No `*` / `(...)` parsing needed against this delivery.
- **Maharashtra spelling**: NFHS row reads `Maharastra` (one *h*) — district-name normalization layer still needed before joining.
