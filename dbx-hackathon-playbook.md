# Databricks Hackathon Playbook

A token-efficient handoff for a fresh Claude session pivoting to a new "Apps & Agents Hackathon for Good 2026" track. Distilled from the SupplyShield project's design docs, journey log, and proposal scorecard. Source pointers are in §22.

Source-of-truth confidence keys used throughout:
- ✅ Confirmed by official rules or runnable preflight
- ⚠️ Verified by team observation during SupplyShield build
- ❓ Assumed on prior reading — verify on the day-of

---

## 1. TL;DR — The 10 Things You Cannot Forget

1. **Lakebase is mandatory.** Rules §4.2(b): *"Create a Databricks App built on Lakebase and using one or more additional Databricks tools."* No Lakebase = disqualification risk. ✅
2. **Free Edition only.** No paid tiers, no external GPU endpoints. Total spend should be $0–$3. ✅
3. **30.5-hour build window.** Project Period only — no pre-built code allowed. ✅
4. **5 judging criteria, equally weighted:** Applicability, Data Relevance, Creativity, Thoroughness, Well-Architected. ✅
5. **Applicability is the official tiebreaker (Rules §6).** Universal/cross-industry beats narrow-vertical when scores tie. ✅
6. **Mosaic AI Agent Framework and Vector Search managed endpoints are locked on Free Edition.** Use `concurrent.futures` + `ai_query()` and in-memory numpy/co-occurrence instead. ⚠️
7. **Ship ONE workflow flawlessly. Demo it in ≤ 60 seconds.** Polish > feature-completeness. ⚠️
8. **LLM is a narrator, not a reasoner.** Compute deterministically; LLM polishes string templates only. Default `llm_narration: false` so the pipeline cannot fail due to LLM unavailability. ⚠️
9. **Mandatory deliverables:** public GitHub repo with OSS license, 3-min demo video on YouTube/Vimeo/Facebook/Youku, Devpost submission. ✅
10. **"For Good" theme.** The track must produce a public-good outcome. ✅

---

## 2. Hard Rules (Cannot Violate)

| # | Rule | Source |
|---|------|--------|
| H1 | Databricks App built on Lakebase, architecturally central — not a checkbox | Rules §4.2(b) ✅ |
| H2 | At least 1 additional Databricks tool used meaningfully | Rules §4.2(b) ✅ |
| H3 | New project built only inside the Project Period (June 15 8am PT → June 16 2:30pm PT) | Rules §4.2(a) ✅ |
| H4 | Public GitHub repo with an open-source license | Rules ✅ |
| H5 | 3-minute demo video hosted on YouTube, Vimeo, Facebook, or Youku | Rules ✅ |
| H6 | Devpost submission | Rules ✅ |
| H7 | "For Good" theme | Rules ✅ |
| H8 | Free Edition must be sufficient — no paid-tier dependencies | Rules ✅ |

Violating any of H1–H8 risks disqualification. None of them are stylistic — all are checkable.

---

## 3. Official Judging Criteria (Equally Weighted)

| # | Criterion | What judges actually look for |
|---|-----------|-------------------------------|
| 1 | **Applicability** | Solves a real business/industry problem. Universal > vertical. **This is the tiebreaker.** |
| 2 | **Data Relevance** | Creative, idiomatic use of Databricks datasets and tools. Lakebase as spine, Delta with Liquid Clustering, Unity Catalog lineage, real public data at scale. |
| 3 | **Creativity** | Novel angle. Not commonly seen in the hackathon space. Has a falsifiable or visceral demo claim. |
| 4 | **Thoroughness** | End user can understand the value in seconds. Workflow is clear and complete. Zero training needed for a judge to grasp the demo. |
| 5 | **Well-Architected** | Scales linearly. Adding a new ecosystem/source/region requires no rewrite. Stateless agents, CDC-driven, pluggable scoring. |

Each criterion scored 1–10 → max 50. Per the SupplyShield scorecard, 42+/50 was the realistic competitive threshold across the top 6 proposals.

**Tiebreaker (Rules §6):** when official scores tie, the **Applicability** criterion (criterion 1) decides the winner. This favors solutions whose target market is *every company* over solutions for one industry.

---

## 4. 2026 Internal Rubric (Trends from Recent Winners)

These are not in the official rubric but predict winning patterns observed across LORE, Gitdefender, Quipu, GraphDev, Coactive, NimbusIQ, ASTRA. Treat as a checklist on top of the official 5.

| Pattern | Why it scores |
|---------|---------------|
| **Carbon / token efficiency** | Tiered LLM activation; deterministic core; visible token counter. Shows discipline. +6–8 internal pts. |
| **Hands-free workflow integration** | GitHub Action / Slack / Jira / FHIR native — the Gitdefender pattern that won Google Cloud Grand Prize. +10–15 pts. |
| **Multi-agent reasoning trace visibility** | `@mlflow.trace` waterfall the judge can click through (LORE/GraphDev pattern). +2–3 pts. |
| **Polish / shipped discipline** | Unit tests, Docker, YAML config (Gitdefender 43-test discipline). +6–8 pts. |
| **Multi-agent network with guardrails** | LORE-style coordinator + specialist agents + visible loop detection. +9–12 pts. |
| **Real data at scale** | 10K+ rows minimum, 200K+ ideal. Synthetic-only data hurts Data Relevance. |

Threshold for a competitive 2026 proposal: **75/100** on this internal rubric. SupplyShield scored 84.

---

## 5. Free Edition Tooling — What Works, What's Locked

| Tool | Free Edition status | Fallback if locked |
|------|---------------------|--------------------|
| **Lakebase (Serverless Postgres)** | ✅ Confirmed in rules §4.2(a). Mandatory. | None — disqualifying if absent |
| **Delta Lake** (write/read/time-travel) | ✅ Standard | n/a |
| **Liquid Clustering** | ✅ Standard | Standard partitioning (degrades Well-Architected score) |
| **Unity Catalog** | ✅ Standard | Hive metastore (loses governance narrative) |
| **PySpark** | ✅ Standard | n/a |
| **Databricks Apps (Gradio/Streamlit)** | ✅ **1 app included on Free Edition** ⚠️ | None — external hosting violates "built on Databricks Apps" expectation |
| **Serverless Compute** | ✅ Standard (30–60s cold start) | n/a |
| **Databricks Jobs (Serverless)** | ✅ Standard | Manual notebook runs |
| **MLflow Tracing (`@mlflow.trace`)** | ✅ Free, built-in | Custom logging (loses interactive waterfall judges can see) |
| **Foundation Model API (`ai_query`)** | ✅ Llama 3 70B and Mixtral 8x7B confirmed working | n/a |
| **Mosaic AI Agent Framework / AgentBricks** | ❌ **Locked** — requires custom GPU serverless endpoints | `concurrent.futures.ThreadPoolExecutor` + `ai_query()` directly |
| **Vector Search (managed endpoints)** | ❌ **Locked** | (a) Pre-computed embeddings stored as numpy bytes in Lakebase BYTEA, loaded into memory at app startup, cosine via numpy. (b) Co-occurrence over Delta tables (collaborative filtering pattern). |
| **External network egress** (OpenAI/Anthropic API, arbitrary HTTP) | ❌ Locked from notebook runtime | `ai_query()` against Databricks-hosted models only; for local dev `claude -p` subprocess works |
| **BigQuery connector (`spark-bigquery-connector`)** | ⚠️ Works but verify on workspace | Pre-stage CSV exports in workspace volumes |
| **Structured Streaming** | ✅ Standard | n/a (only needed for streaming-first tracks) |
| **Databricks SDK (`databricks.sdk.WorkspaceClient`)** | ✅ Available | n/a |

**Critical:** Confirm Mosaic AI Agent Framework status on the actual workspace before designing around it. SupplyShield assumed locked and the assumption held — but the design doc explicitly notes it should be re-verified each event because Free Edition entitlements drift.

---

## 6. Lakebase Centrality Test

The rules say *"built on Lakebase"* — not "uses Lakebase." Architectural centrality is judged.

**Lakebase as spine (high score):** Lakebase holds the canonical operational state. CDC events from Lakebase trigger agent re-evaluation. Removing Lakebase requires redesigning the system. Example: patient-state-change → CDC event → re-score → push notification. RelapseRadar archetype.

**Lakebase as cache (lower score):** Delta is the primary store; Lakebase is a write-through cache for fast point lookups during a live demo. Removing Lakebase means slower queries but the system still functions. SupplyShield archetype.

**Verdict:** spine usage scores higher on Data Relevance. If your new track has any operational state that mutates during the demo (scan requests, remediation status, alert acknowledgments, user-uploaded manifests), put it in Lakebase as the source of truth — not in Delta.

**Practical Lakebase patterns from SupplyShield's `lakebase-schema.md`:**
- `operational.*` schema — live state CDC-synced from Delta
- `cache.*` schema — precomputed results with TTL (alternatives, embeddings)
- `team.*` schema — cross-session persistent state (uploaded artifacts, remediation tracking)
- `data_freshness_days INT GENERATED ALWAYS AS (CURRENT_DATE - last_scored_date) STORED` — Postgres generated column, free freshness tracking
- Use `JSONB` for flexible per-record bags (signal scores, alternatives lists)

---

## 7. The Databricks Hackathon Filter (4-Question Gate)

Apply to every feature before building it. Verbatim from `proposals/00-proposal-scorecard.md`:

1. Is the data actually hard to process or organize? *(If not, judges won't be impressed.)*
2. Are we using Lakebase / Delta / Unity Catalog to power this? *(If not, why Databricks?)*
3. Is the AI doing something autonomous? *(If it's just summarizing text, it's a chatbot.)*
4. Can we demo this in under 60 seconds? *(If not, simplify.)*

Any "no" answer = cut the feature.

---

## 8. Winning Patterns

| Pattern | Example winner | How to apply |
|---------|----------------|--------------|
| **Agentic Orchestration** — LLM as runtime decision-maker, not summarizer | SurgAgent (Google Cloud AI, 1st) | Agent visibly chooses which tool to use and explains why. Show reasoning chain in UI. |
| **Data Agent, Not Chatbot** — reason over complex structured data | GreenLight AdaptiveFilters (Databricks GenAI World Cup) | LLM processes hard data joins (SBOM × CVE, clinical timelines, dependency graphs) — not free-text Q&A. |
| **Polish & Shipped > Feature-Complete** | Brick-by-Brick winners (V4C Lakeflow Legends) | One end-to-end workflow flawless. Add layers only with remaining time. |
| **Native Tooling** — idiomatic platform use | Coactive, RadiantGraph (Databricks Startup Challenge) | Delta + Unity Catalog + Lakebase + Apps all meaningfully used, not just checked. |
| **Data Scale** — show the platform handling volume | Coactive (Structured Streaming over massive visual content) | Demo against 200K+ records, not toy datasets. Scale is the demo. |
| **Falsifiable / visceral demo claim** | Quipu — "we caught this patient 3 days before relapse"; SupplyShield — "we would have flagged event-stream 117 days before the 2018 compromise" | Pre-compute the proof against real historical events; replay on demand. |

---

## 9. Anti-Patterns (Score Killers)

- Chatbot UI over a single API call (no data complexity)
- Databricks as a dumb host for code that could run anywhere
- Feature creep with a buggy demo at presentation time
- Static pipelines without autonomous agent decision-making
- Calling an external LLM API directly (Free Edition egress is locked, and it breaks the "Databricks-native" narrative)
- Hosting the web app externally instead of via Databricks Apps
- LLM on the critical path of the demo (unreliable; if the model API is slow or returns an empty response, your demo dies)
- Synthetic data without a real-data anchor — kills Data Relevance score
- Adding a new feature in the last 4 hours

---

## 10. Demo Strategy

- **One golden-path workflow, ≤ 60 seconds.** Anything longer loses the judges.
- **Lead with a wow moment.** Three archetypes that work:
  - *Falsifiable historical claim* — replay a real past event and show the system would have caught it (SupplyShield)
  - *Visible cost/carbon counter* — token-usage dashboard at zero by default proves the LLM-free claim structurally
  - *Emotional hook* — "we caught this patient 3 days before relapse" (Quipu)
- **Audience attention ranking** (per SupplyShield team consensus, validated against Quipu pattern):
  1. Emotional gut-punch ("we saved a life")
  2. Universal experience ("every org has been hacked")
  3. Technically visceral ("we predicted XZ Utils 4 months early") — requires domain context
- **Pre-record the intro segment** — saves ~10 minutes of day-of stress.
- **Stub UI + demo recording dry-run before build day** — learn OBS/Loom workflow before it's the critical path.
- **Have 3 sample inputs ready** — different shapes, all known to produce a clean demo result.

---

## 11. Build-Day Time Budget

| Window | Goal | Forbidden |
|--------|------|-----------|
| First 6h | ONE workflow end-to-end. Ugly is fine. | Polish, secondary features |
| Next 6h | Polish that workflow until flawless. | New features |
| Next ~12h | Secondary features OR record the demo video early. | Architecture changes |
| Last 4h | Recording, Devpost, repo cleanup, README. | **Any new feature.** No exceptions. |

MVP must be demo-able inside the first 12 hours. If it isn't, cut scope.

---

## 12. Architecture That Works (4-Layer Databricks-Native)

```
Source data
    ↓
PySpark + Delta Lake     ← Analytics layer (historical, reproducible)
    ↓ (CDC sync)
Lakebase (Serverless PG) ← Operational layer (live state, low-latency)
    ↓
Multi-agent network      ← Reasoning layer (concurrent.futures + ai_query)
    ↓
Databricks App (Gradio)  ← UI layer
    + Workflow hooks     ← Slack / GitHub Action / Jira / EHR / etc.

Cross-cutting:
  Vector Search (or numpy fallback)  → knowledge retrieval
  Unity Catalog                      → lineage + governance narrative
  MLflow Tracing                     → multi-agent waterfall observability
```

This is the same shape that worked across SupplyShield, ThreatHorizon, RelapseRadar, DisasterLens, EcoTrace, and CyberSentinel. Differ only in **what flows through each layer** and **which layer Lakebase anchors**.

---

## 13. LLM-as-Narrator Pattern (Carbon Efficiency Win)

Default `llm_narration: false`. The pipeline is 100% deterministic via string templates; the LLM is an opt-in polish layer.

**Why this wins:**
- Pipeline cannot fail due to LLM unavailability ⇒ the demo cannot fail on stage
- Carbon/token counter visible in UI proves the LLM-free claim structurally to judges
- Token gating (only High/Critical findings, not every record) keeps cost near $0
- Eliminates hallucination — LLM only refines a template that already contains all factual content

**Implementation skeleton:**

```python
def generate_explanation(data) -> str:
    template_output = render_template(data)             # always computed
    if not config.llm_narration:
        return template_output
    try:
        polished = ai_query(model, prompt(template_output))
        return polished if polished and len(polished) >= 20 else template_output
    except Exception:
        return template_output                          # never fail the scan
```

**Token budget calibration (from SupplyShield):**
- ~360 tokens per narration call (alternatives finder)
- ~630 tokens per narration call (historical narrative)
- ~5,000 tokens per typical scan (50 deps, 5 High/Critical)
- `ai_query()` on Free Edition: free; full hackathon spend ≈ $1–3 even with narration on.

**Surface in the UI:** show `token_usage: 0` and `carbon_estimate_g_co2e: 0` by default. When narration toggles on, these climb visibly. Judges see the trade-off in real time.

---

## 14. Data Accessibility Rules (P3 from Scorecard)

- All datasets must be fetchable with a single `curl`, `wget`, or public API call. No login, no OAuth, no manual download.
- **Real public data > synthetic.** Synthetic counts against Data Relevance (criterion 2).
- Pre-stage everything in workspace volumes before the build window opens.
- **10K+ rows minimum** for a credible demo. **200K+ rows** to show platform-handling-scale (Coactive pattern).
- Avoid datasets behind paid API keys, rate limits, or institutional access walls.
- BigQuery public datasets are gold for Free Edition: single SQL pull, no rate limits, auth-free. Examples used by SupplyShield: `openssf:scorecardcron.scorecard-v2_latest`, `bigquery-public-data.deps_dev_v1`.
- Other proven sources from SupplyShield's neighbors: NVD, EPSS (`first.org/epss`), CISA KEV, OSV.dev, FEMA, NOAA, EPA, EIA, Synthea CLI (synthetic but generates fast), public DEFRA / World Bank.

---

## 15. Synthetic + Scripted-Package Fallback Pattern

When real data is unreachable on build day (BigQuery hiccup, network restriction), have a synthetic mode with the **same schema** so downstream components don't change.

| Category | Purpose | Generation strategy |
|----------|---------|---------------------|
| **A — Scripted** (~5–10 records) | Anchor the demo to a falsifiable real-world event | Hand-crafted signal values reproducing real timelines (e.g., event-stream at `2018-08-01` must score HIGH/CRITICAL to validate the predictive claim) |
| **B — Random** (~90–4990 records) | Realistic background distribution | Zipf for counts (most rows have 1–2), normal for scores (mean 5.5, std 2.0, clamped), log-normal for downloads, 5% chance of "ownership change" simulation between baseline and current |

The demo must hit a **falsifiable claim** that comes from Category A — judges should be able to ask "what about <real package/incident X>?" and see the system get it right.

Implementation: `ingestion.mode = "synthetic" | "bigquery"` config flag. Same `MERGE INTO` semantics on both paths. Downstream code is unaware which mode produced the rows.

---

## 16. Parallel Build Pattern (3 Engineers, ~30h)

| Step | Owner | Output |
|------|-------|--------|
| 0–30 min | All | `models.py` shared contracts: dataclasses for every cross-component type |
| 30 min onward, parallel | E1 (data) | Ingestion + Delta scoring pipeline |
| 30 min onward, parallel | E2 (agents) | Coordinator + specialist agents, stubbed against E1 with fixtures |
| 30 min onward, parallel | E3 (UI) | Gradio app, hardcoded `ScanReport` fixture until E2 is live |
| ~12h | All | Integration: swap stubs for real implementations |

**Key insight from SupplyShield Session 9:** `models.py` is the handshake. Once `PackageRiskResult`, `PackageReport`, `ScanReport` (or your track's analogues) are agreed, all three tracks are unblocked simultaneously.

**Stub pattern that works:** specialist functions raise `NotImplementedError` in source files; tests stub them via `pytest-mock`; the coordinator is fully tested via mocks. Real implementations land later without changing test surface.

---

## 17. Doc Audit + Edge Audit (Catches Gaps Before Code)

**Doc audit (20 minutes, before any code):** read every LLD and spec end-to-end and check for:
- Missing API specs (request/response shapes, especially for any HTTP boundary)
- Missing schemas (any table referenced without DDL)
- Contract drift (one doc says `composite_risk`, another says `risk_score`)
- Cross-cutting concerns that "fall between the cracks" of component LLDs (Lakebase, config, error handling) — promote to their own LLD

**Edge audit (the "what does the system do when..." pass):** for every workflow, ask explicitly:
- What does the UI show when the input is unknown / not in the dataset?
- What does the system do when a cache entry is stale?
- What does the system do when the dependency graph contains a cycle?
- What does the system do when the LLM returns empty / errors / times out?
- What does the GitHub Action do when there are zero findings?

Both audits found **8 issues across SupplyShield (3 blocking, 5 minor)** before code started. The pattern is: HLD → LLDs → EARS specs → edge audit → tests-first → implementation.

---

## 18. Cost Reality Check

Actual SupplyShield numbers (use as sanity check on any new track):

| Resource | Usage | Cost |
|----------|-------|------|
| Lakebase, Delta, Compute, Apps, UC, MLflow | Core pipeline | **$0 (Free Edition)** |
| `ai_query()` LLM narration | ~5K tokens/scan when enabled | **~$0.01/scan** |
| **Hackathon total** | | **$1–3** |

If your new track's cost projection is materially higher than this, you've probably wandered onto a paid endpoint (custom GPU, Mosaic AI managed, external API). Re-anchor.

---

## 19. Local Dev Gotchas (Spark-Heavy Tracks)

Skip if your track is purely Lakebase + a Databricks-hosted notebook. If you're running PySpark locally:

- **`JAVA_HOME` must point to Java 17.** Amazon Corretto 17 is known-working at `/Library/Java/JavaVirtualMachines/amazon-corretto-17.jdk/Contents/Home`. PySpark 3.5 fails on Java 8.
- **`PYSPARK_PYTHON` and `PYSPARK_DRIVER_PYTHON` must be `sys.executable`** — the venv Python. Without this, Spark workers spawn with system Python and fail on `import` of any venv-installed package.
- Use `configure_spark_with_delta_pip()` builder pattern — it handles Delta JAR wiring automatically. Manual `.config("spark.sql.extensions", ...)` is fragile.
- **Pin `delta-spark ~= 3.3`** for PySpark 3.5 (matches `onedefense-datapipeline-parser-library-2`).
- C1 Artifactory `pypi-internalfacing` doesn't mirror all of PyPI. Pin transitive deps explicitly when they're missing (SupplyShield needed `aiohappyeyeballs = "*"` and `aiofiles`).
- **DuckDB Python binding is not fully thread-safe** even with `threading.Lock`. If you use DuckDB for local Lakebase emulation, provide a `parallel=False` mode for tests; let production use the real Postgres-backed Lakebase under threads.

---

## 20. Preflight Checklist (Minimum to Proceed = Checks 1–9)

Run before committing build time. Full runnable code is in `supplyshield/docs/databricks-preflight.md`.

| # | Check | Pass criterion |
|---|-------|----------------|
| 1 | Workspace Access | Home page loads, no upgrade banner |
| 2 | Serverless Compute | `print("hello")` + `spark.version` runs (30–60s cold start ok) |
| 3 | Unity Catalog | `SHOW CATALOGS` works; `CREATE CATALOG` + `CREATE SCHEMA` succeed |
| 4 | Delta Lake (write/read/time-travel) | `df.write.format("delta")` + `DESCRIBE HISTORY` returns ≥1 version |
| 5 | Liquid Clustering | `ALTER TABLE … CLUSTER BY (col)` + `OPTIMIZE` succeed |
| 6 | Lakebase | `WorkspaceClient().database_instances.list()` returns ≥1; `CREATE TABLE … USING LAKEBASE` + INSERT + SELECT succeed |
| 7 | Foundation Model API | `SELECT ai_query('databricks-meta-llama-3-1-70b-instruct', 'Reply with exactly: ok')` returns non-empty |
| 8 | MLflow Tracing | `@mlflow.trace` decorated function logs a run; trace waterfall visible in Experiments UI |
| 9 | Databricks Apps (Gradio) | hello-world Gradio app deploys; URL serves greeting |
| 10 | Databricks Jobs (Serverless) | scheduled notebook job runs green |
| 11 | BigQuery connector | `spark.read.format("bigquery")` returns rows from a public dataset (optional — fallback exists) |

**Minimum to proceed:** 1–9 all pass. 10 needed for scheduled batch. 11 optional.

---

## 21. Day-Of Survival Kit

- Workspace URL + admin credentials in shared password manager (NOT in repo)
- Pre-staged data in workspace volumes (every dataset already uploaded before 8am PT)
- Click-path doc for every Databricks UI interaction (Apps deploy, Lakebase provision, Job create) — so build-day = code-only
- Pre-recorded "intro" video segment (saves 10 min on day-of)
- 3 sample inputs ready to demo (3 different shapes, all known-good)
- `models.py` skeleton with dataclasses pre-drafted (counts as design, not code — verify against rules)
- Devpost submission template pre-written (description, inspiration, what-it-does, how-built, challenges, accomplishments — fill in code/repo links day-of)
- Demo recording workflow tested (OBS or Loom) on a stub UI before the event

---

## 22. Canonical Sources for Deeper Detail

When this playbook is too thin on a topic, read:

| Source | Best for |
|--------|----------|
| `proposals/00-proposal-scorecard.md` | Judging rubric line-by-line, P1–P4 personal criteria, lessons from real recent winners (SurgAgent, Coactive, Quipu, LORE, Gitdefender, GraphDev), Lakebase centrality factor, emotional/data-authenticity tiebreakers |
| `proposals/07-needs-document.md` | Per-archetype data risk, Free Edition tooling verification table, pre-event action items, data prep checklists, decision matrix by judge composition |
| `supplyshield/docs/databricks-preflight.md` | Runnable preflight code for all 11 checks |
| `supplyshield/docs/JOURNEY.md` | Session-by-session design pivots forced by Free Edition (Mosaic AI lockout, Vector Search lockout, two-snapshot ingestion, LLM-as-narrator, parallel build with `models.py`, doc audit, edge audit, local Spark wiring) |
| `supplyshield/docs/SESSION_SUMMARY.md` | Phase artifacts, test counts, Databricks cost breakdown ($1–3), exact bug patterns found and fixed in Phase 6 |
| `supplyshield/docs/llds/lakebase-schema.md` | Concrete Lakebase DDL patterns: `operational.*` / `cache.*` / `team.*` schemas, generated columns, JSONB fields, CDC flow Delta→Lakebase |
| `supplyshield/docs/llds/agent-network.md` | Multi-agent pattern: Coordinator + specialists, `concurrent.futures` orchestration, `@mlflow.trace` decoration, template-first / LLM-optional structure |
| `supplyshield/docs/llds/ingestion-pipeline.md` | Synthetic mode design (Category A scripted + Category B random), MERGE-on-(key, snapshot_date) idempotency |
| `proposals/08-new-ideas-brainstorm.md` | Five additional "for good" archetypes (AccessLens, FoodChain, WageGuard, HousingLine) with multi-agent + Lakebase patterns — useful pattern bank for new tracks |
| `DAIS Apps & Agents Hackathon for Good 26 Official Rules.docx.md` | The actual rules. Section 4.2 (hard requirements) and Section 6 (tiebreaker) are load-bearing. |

All paths relative to repo root `mzj897-dbx-hackathon/`.

---

## 23. Quick Adapter Checklist for the New Track

When the new track is announced, walk this list in order — should take ≤ 30 minutes:

1. **Identify the public-good outcome.** One sentence. Check it satisfies "for Good."
2. **Pick the falsifiable demo claim.** One real historical event the system must reproduce, OR one emotional outcome ("we caught X").
3. **Pick the operational state that mutates during the demo.** That goes in Lakebase as the spine.
4. **Pick 1+ additional Databricks tool that is architecturally central.** Run it through the 4-question Filter (§7).
5. **Sketch the 4-layer architecture (§12).** What flows through each layer for this track?
6. **Identify data sources.** All public, auth-free, single-fetch. Aim for 10K+ rows; 200K+ if available.
7. **Decide synthetic fallback.** Define Category A scripted records anchored to real events.
8. **Define `models.py` shared contracts.** Dataclasses for every cross-component type. (May only design these in your head until the build window opens — code is gated to the Project Period.)
9. **Plan the ≤ 60-second demo walk.** Lead with the wow moment.
10. **Run the doc audit + edge audit (§17)** against your sketch before writing any code in the build window.
