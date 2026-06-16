import type { Application } from 'express';
import { z } from 'zod';

interface AppKitWithLakebase {
  lakebase: {
    query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
  };
  server: {
    extend(fn: (app: Application) => void): void;
  };
}

const SUPPORTED_CAPABILITIES = ['maternity', 'icu', 'emergency', 'trauma', 'nicu'] as const;

const Capability = z.enum(SUPPORTED_CAPABILITIES).catch('maternity');
const OverrideBody = z.object({
  facilityId: z.string().min(1),
  overrideType: z.enum(['force-real', 'force-phantom']),
  reasonNote: z.string().trim().min(1),
  plannerId: z.string().trim().min(1).default('local-planner'),
  capability: Capability,
});

const SaveScenarioBody = z.object({
  scenarioName: z.string().trim().min(1),
  capability: Capability,
  regionFilter: z.string().trim().default('all'),
  overrideSet: z.array(z.string()).default([]),
  plannerNotes: z.string().default(''),
  plannerId: z.string().trim().min(1).default('local-planner'),
});

// Only create tables the app owns — synced tables (public.*) are read-only
// and were created by `databricks postgres create-synced-table`.
const setupSql = `
CREATE SCHEMA IF NOT EXISTS team;

CREATE TABLE IF NOT EXISTS team.planner_overrides (
  override_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  facility_id TEXT NOT NULL,
  override_type TEXT NOT NULL CHECK (override_type IN ('force-real', 'force-phantom')),
  reason_note TEXT NOT NULL,
  planner_id TEXT NOT NULL,
  overridden_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team.saved_scenarios (
  scenario_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_name TEXT NOT NULL,
  capability TEXT NOT NULL,
  region_filter TEXT NOT NULL DEFAULT 'all',
  override_set JSONB NOT NULL DEFAULT '[]'::jsonb,
  planner_notes TEXT NOT NULL DEFAULT '',
  planner_id TEXT NOT NULL,
  saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_overrides_planner
  ON team.planner_overrides (planner_id, overridden_at DESC);
CREATE INDEX IF NOT EXISTS idx_overrides_facility
  ON team.planner_overrides (facility_id, overridden_at DESC);
CREATE INDEX IF NOT EXISTS idx_scenarios_planner
  ON team.saved_scenarios (planner_id, saved_at DESC);
`;

function getCapability(value: unknown) {
  return Capability.parse(value);
}

function getPlannerId(value: unknown) {
  return z.string().trim().min(1).catch('local-planner').parse(value);
}

export async function setupPhantomCensusRoutes(appkit: AppKitWithLakebase) {
  try {
    await appkit.lakebase.query(setupSql);
    console.log('[phantom-census] Team schema ready');
  } catch (err) {
    console.warn('[phantom-census] Schema setup failed:', (err as Error).message);
    console.warn('[phantom-census] Routes registered — run the notebook and sync tables first');
  }

  appkit.server.extend((app) => {

    // ── Summary: fast — stats + scenarios only (no expensive CTE) ─────────────
    app.get('/api/planner/summary', async (req, res) => {
      const capability = getCapability(req.query.capability);
      const plannerId = getPlannerId(req.query.plannerId);

      try {
        const [summary, scenarios] = await Promise.all([
          appkit.lakebase.query(
            `
            SELECT
              COALESCE(SUM(ds.total_count), 0)::INT    AS total_facilities,
              COALESCE(SUM(ds.phantom_count), 0)::INT   AS phantom_count,
              COALESCE(SUM(ds.contested_count), 0)::INT AS contested_count,
              (SELECT COUNT(DISTINCT facility_id)::INT
               FROM team.planner_overrides)             AS override_count
            FROM public.desert_scores ds
            WHERE ds.capability = $1
            `,
            [capability],
          ),
          appkit.lakebase.query(
            `
            SELECT scenario_id, scenario_name, capability, region_filter, planner_notes, saved_at
            FROM team.saved_scenarios
            WHERE planner_id = $1
            ORDER BY saved_at DESC
            LIMIT 10
            `,
            [plannerId],
          ),
        ]);

        res.json({
          capability,
          summary: summary.rows[0] ?? { total_facilities: 0, phantom_count: 0, contested_count: 0, override_count: 0 },
          scenarios: scenarios.rows,
        });
      } catch (err) {
        console.error('Failed to load planner summary:', err);
        res.status(500).json({ error: 'Failed to load summary' });
      }
    });

    // ── Tiles: pre-rendered Folium HTML (loaded independently for parallel fetch)
    app.get('/api/planner/tiles', async (req, res) => {
      const capability = getCapability(req.query.capability);

      try {
        const tiles = await appkit.lakebase.query(
          `SELECT layer_type, html, rendered_at FROM public.tile_layers WHERE capability = $1`,
          [capability],
        );
        res.json({ tileLayers: tiles.rows });
      } catch (err) {
        console.error('Failed to load tile layers:', err);
        res.status(500).json({ error: 'Failed to load tiles' });
      }
    });

    // ── Bootstrap: district scores only — simple SELECT on precomputed ranks ───
    app.get('/api/planner/bootstrap', async (req, res) => {
      const capability = getCapability(req.query.capability);

      try {
        const scores = await appkit.lakebase.query(
          `
          SELECT
            district_id,
            district_name,
            state_name,
            raw_desert_score,
            adjusted_desert_score,
            verified_facility_count,
            phantom_count,
            contested_count,
            total_count,
            burden_imputed,
            raw_rank,
            adjusted_rank
          FROM public.desert_scores
          WHERE capability = $1
          ORDER BY adjusted_desert_score DESC, district_name
          LIMIT 200
          `,
          [capability],
        );

        res.json({ capability, scores: scores.rows });
      } catch (err) {
        console.error('Failed to load district scores:', err);
        res.status(500).json({ error: 'Failed to load district scores' });
      }
    });

    // ── District phantom evidence panel ─────────────────────────────────────────
    app.get('/api/planner/districts/:districtId/phantoms', async (req, res) => {
      try {
        const result = await appkit.lakebase.query(
          `
          WITH latest_overrides AS (
            SELECT DISTINCT ON (facility_id) facility_id, override_id, override_type
            FROM team.planner_overrides
            ORDER BY facility_id, overridden_at DESC
          )
          SELECT
            pv.facility_id,
            pv.facility_name,
            CASE
              WHEN lo.override_type = 'force-real'    THEN 'real'
              WHEN lo.override_type = 'force-phantom' THEN 'phantom'
              ELSE pv.verdict
            END                                     AS verdict,
            lo.override_id,
            t.test_name                             AS primary_failed_test,
            t.evidence_ref
          FROM public.phantom_verdicts pv
          LEFT JOIN latest_overrides lo ON lo.facility_id = pv.facility_id
          LEFT JOIN LATERAL (
            SELECT test_name, evidence_ref
            FROM public.facility_existence_tests
            WHERE facility_id = pv.facility_id AND result = 'fail'
            ORDER BY ran_at DESC, test_name
            LIMIT 1
          ) t ON true
          WHERE pv.district_id = $1
            AND COALESCE(
              CASE lo.override_type
                WHEN 'force-phantom' THEN 'phantom'
                WHEN 'force-real'    THEN 'real'
              END,
              pv.verdict
            ) = 'phantom'
          ORDER BY pv.ran_at DESC
          LIMIT 10
          `,
          [req.params.districtId],
        );
        res.json(result.rows);
      } catch (err) {
        console.error('Failed to load district phantoms:', err);
        res.status(500).json({ error: 'Failed to load district phantoms' });
      }
    });

    // ── Facility test detail (evidence panel) ───────────────────────────────────
    app.get('/api/planner/facilities/:facilityId/tests', async (req, res) => {
      try {
        const result = await appkit.lakebase.query(
          `
          SELECT test_name, result, evidence_ref, ran_at
          FROM public.facility_existence_tests
          WHERE facility_id = $1
          ORDER BY ran_at DESC, test_name
          `,
          [req.params.facilityId],
        );
        res.json(result.rows);
      } catch (err) {
        console.error('Failed to load facility tests:', err);
        res.status(500).json({ error: 'Failed to load facility tests' });
      }
    });

    // ── Planner override (append-only; does NOT mutate synced tables) ───────────
    app.post('/api/planner/overrides', async (req, res) => {
      const parsed = OverrideBody.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({ error: 'Invalid override request' });
        return;
      }

      const { facilityId, overrideType, reasonNote, plannerId } = parsed.data;

      try {
        const result = await appkit.lakebase.query(
          `
          INSERT INTO team.planner_overrides (facility_id, override_type, reason_note, planner_id)
          VALUES ($1, $2, $3, $4)
          RETURNING override_id, facility_id, override_type, reason_note, planner_id, overridden_at
          `,
          [facilityId, overrideType, reasonNote, plannerId],
        );
        res.status(201).json(result.rows[0]);
      } catch (err) {
        console.error('Failed to save override:', err);
        res.status(500).json({ error: 'Failed to save override' });
      }
    });

    // ── Save scenario ────────────────────────────────────────────────────────────
    app.post('/api/planner/scenarios', async (req, res) => {
      const parsed = SaveScenarioBody.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({ error: 'Invalid scenario request' });
        return;
      }

      const input = parsed.data;
      try {
        const result = await appkit.lakebase.query(
          `
          INSERT INTO team.saved_scenarios
            (scenario_name, capability, region_filter, override_set, planner_notes, planner_id)
          VALUES ($1, $2, $3, $4::jsonb, $5, $6)
          RETURNING scenario_id, scenario_name, capability, region_filter, planner_notes, saved_at
          `,
          [
            input.scenarioName,
            input.capability,
            input.regionFilter,
            JSON.stringify(input.overrideSet),
            input.plannerNotes,
            input.plannerId,
          ],
        );
        res.status(201).json(result.rows[0]);
      } catch (err) {
        console.error('Failed to save scenario:', err);
        res.status(500).json({ error: 'Failed to save scenario' });
      }
    });
  });
}
