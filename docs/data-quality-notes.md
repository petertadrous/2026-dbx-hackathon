# VF Dataset — Data Quality Notes

Source: `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities`  
Approximate size: ~10,000 rows (0.5% sample of the full national dataset)

---

## Issue 1 — `unique_id` is not unique

**Observed:** Multiple rows share the same `unique_id` value. After renaming to `facility_id`, the facilities DataFrame contains duplicate IDs.

**Impact:** The existence engine iterates facilities row-by-row. Duplicate `facility_id` rows cause each signal test (`pin-reverse-lookup`, `minhash-near-duplicate`, etc.) to emit more than one result row per facility, producing duplicate `(facility_id, test_name)` pairs in `facility_existence_tests` — which violates the primary key.

**Root cause hypothesis:** `unique_id` is a catalog identifier that was not enforced as a primary key in the source system. The same physical facility appears multiple times with minor spelling or address variations (e.g. different transliterations of the facility name, slightly different pincode entries).

**Fix:** Deduplicate on `facility_id` at ingestion, before the engine runs (`notebooks/existence_engine.py`, Cell 2). The dedup keeps the first occurrence; no signal about which row is canonical.

**Residual risk:** Deduping keeps one address variant arbitrarily. If the dropped row held the correct lat/lon and the kept row held a wrong one, the pin-reverse-lookup test result could flip. At 0.5% sample size this is acceptable for the hackathon; a production pipeline should merge/reconcile duplicate rows rather than drop.

---

## Issue 2 — Null bytes (`\x00`) in string fields

**Observed:** `facility_name` (and potentially other text fields) contains embedded ASCII NUL characters (`0x00`).

**Impact:** Two independent failures:
- `psycopg2` raises `ValueError: A string literal cannot contain NUL (0x00) characters` on any INSERT that includes the value.
- Delta/Parquet write via SparkSQL raises `CHARACTER_NOT_IN_REPERTOIRE` when attempting to persist the column.

**Root cause hypothesis:** The source data was likely exported from a system that stores facility names in a non-UTF-8 encoding (possibly ISO-8859-1 or a Windows code page). NUL bytes can appear as padding in fixed-width fields or as a byproduct of a lossy encoding conversion.

**Fix:** `_strip_null_bytes()` (notebook `write_gold`) and `_strip_nul()` (`src/phantom_census/lakebase/writer.py`) strip `\x00` from all string columns before any write. Applied to both the Unity Catalog path and the direct Lakebase psycopg2 path.

**Residual risk:** Silent data mutation — the stored name differs from the source. Acceptable for phantom detection (the name is used only for display and MinHash tokenisation; a missing NUL doesn't change the token set meaningfully).

---

## Issue 3 — `unique_id` not a safe deduplication key

Related to Issue 1: even facilities with distinct `unique_id` values can represent the same physical location (near-duplicate names, same pincode, coordinates within 1 km). This is precisely what the MinHash near-duplicate signal (`minhash-near-duplicate`) is designed to detect and surface as a `contested` verdict rather than `real`.

---

## Mitigations in place

| Layer | Mitigation |
|-------|-----------|
| Notebook ingestion | `drop_duplicates(subset=["facility_id"])` on raw facilities before `run_engine()` |
| Engine output | `drop_duplicates(subset=["facility_id", "test_name"], keep="last")` on `facility_existence_tests` as safety net |
| Lakebase INSERT | `ON CONFLICT (facility_id, test_name) DO NOTHING` on `facility_existence_tests` table |
| UC + Lakebase write | `_strip_null_bytes()` / `_strip_nul()` on all string fields before any write |
| Unit tests | `tests/lakebase/test_writer_unit.py` — mock-based, no Docker required, catches null byte regressions |
