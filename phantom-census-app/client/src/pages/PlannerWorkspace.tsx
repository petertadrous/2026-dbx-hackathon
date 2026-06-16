import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
} from '@databricks/appkit-ui/react';
import { Activity, BookmarkPlus, CheckCircle2, Database, FileText, MapPinned, RefreshCw, ShieldAlert, XCircle } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { GIT_HASH } from '../git-hash';

type Capability = 'maternity' | 'icu' | 'emergency' | 'trauma' | 'nicu';

interface Summary {
  total_facilities: number | string;
  phantom_count: number | string;
  contested_count: number | string;
  override_count: number | string;
}

interface DistrictScore {
  district_id: string;
  district_name: string;
  state_name: string;
  raw_desert_score: number | string;
  adjusted_desert_score: number | string;
  verified_facility_count: number | string;
  phantom_count: number | string;
  burden_imputed: boolean;
  raw_rank: number | string;
  adjusted_rank: number | string;
}

interface TileLayer {
  layer_type: string;
  html: string;
  rendered_at: string;
}

interface Scenario {
  scenario_id: string;
  scenario_name: string;
  capability: Capability;
  region_filter: string;
  planner_notes: string;
  saved_at: string;
}

interface SummaryResponse {
  capability: Capability;
  summary: Summary;
  scenarios: Scenario[];
}

interface ScoresResponse {
  capability: Capability;
  scores: DistrictScore[];
}

interface TilesResponse {
  tileLayers: TileLayer[];
}

interface PhantomFacility {
  facility_id: string;
  facility_name: string | null;
  verdict: 'phantom' | 'real' | 'contested';
  override_id: string | null;
  primary_failed_test: string | null;
  evidence_ref: unknown;
}

interface TestEvidence {
  test_name: string;
  result: 'pass' | 'fail' | 'indeterminate' | 'not-applicable';
  evidence_ref: unknown;
  ran_at: string;
}

const capabilities: { value: Capability; label: string }[] = [
  { value: 'maternity', label: 'Maternity' },
  { value: 'icu', label: 'ICU' },
  { value: 'emergency', label: 'Emergency' },
  { value: 'trauma', label: 'Trauma' },
  { value: 'nicu', label: 'NICU' },
];

const plannerId = 'local-planner';

function asNumber(value: number | string | null | undefined) {
  const numberValue = Number(value ?? 0);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

function formatScore(value: number | string) {
  return asNumber(value).toFixed(2);
}

function formatCount(value: number | string) {
  return new Intl.NumberFormat().format(asNumber(value));
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function PlannerWorkspace() {
  const [capability, setCapability] = useState<Capability>('maternity');

  // Split into three independent data streams for parallel loading
  const [summary, setSummary] = useState<Summary | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scores, setScores] = useState<DistrictScore[] | null>(null);
  const [tiles, setTiles] = useState<TileLayer[] | null>(null);

  const [summaryLoading, setSummaryLoading] = useState(true);
  const [scoresLoading, setScoresLoading] = useState(true);
  const [tilesLoading, setTilesLoading] = useState(true);
  const [districtLoading, setDistrictLoading] = useState(false);

  const [selectedDistrictId, setSelectedDistrictId] = useState<string | null>(null);
  const [phantoms, setPhantoms] = useState<PhantomFacility[]>([]);
  const [selectedFacilityId, setSelectedFacilityId] = useState<string | null>(null);
  const [facilityTests, setFacilityTests] = useState<TestEvidence[] | null>(null);

  const [brief, setBrief] = useState('');
  const [briefLoading, setBriefLoading] = useState(false);

  const [reasonNote, setReasonNote] = useState('');
  const [scenarioName, setScenarioName] = useState('');
  const [scenarioNotes, setScenarioNotes] = useState('');
  const [savingScenario, setSavingScenario] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInitiatedClickRef = useRef(false);

  // Phase 1 — fast (~300 ms): summary stats + scenarios
  useEffect(() => {
    setSummaryLoading(true);
    setError(null);
    fetchJson<SummaryResponse>(`/api/planner/summary?capability=${capability}&plannerId=${plannerId}`)
      .then((d) => { setSummary(d.summary); setScenarios(d.scenarios); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load summary'))
      .finally(() => setSummaryLoading(false));
  }, [capability]);

  // Phase 2 — medium (~500 ms): district scores (precomputed ranks, simple SELECT)
  useEffect(() => {
    setScoresLoading(true);
    fetchJson<ScoresResponse>(`/api/planner/bootstrap?capability=${capability}`)
      .then((d) => setScores(d.scores))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load district scores'))
      .finally(() => setScoresLoading(false));
  }, [capability]);

  // Phase 3 — independent: tile HTML (can be large, loads in background)
  useEffect(() => {
    setTilesLoading(true);
    fetchJson<TilesResponse>(`/api/planner/tiles?capability=${capability}`)
      .then((d) => setTiles(d.tileLayers))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load map tiles'))
      .finally(() => setTilesLoading(false));
  }, [capability]);

  // District phantom list — fetched on demand when district is selected
  useEffect(() => {
    if (!selectedDistrictId) { setPhantoms([]); return; }
    setDistrictLoading(true);
    fetchJson<PhantomFacility[]>(
      `/api/planner/districts/${encodeURIComponent(selectedDistrictId)}/phantoms`,
    )
      .then(setPhantoms)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load district evidence'))
      .finally(() => setDistrictLoading(false));
  }, [capability, selectedDistrictId]);

  // Facility test evidence — fetched on demand
  useEffect(() => {
    if (!selectedFacilityId) { setFacilityTests(null); return; }
    fetchJson<TestEvidence[]>(`/api/planner/facilities/${encodeURIComponent(selectedFacilityId)}/tests`)
      .then(setFacilityTests)
      .catch(() => setFacilityTests([]));
  }, [selectedFacilityId]);

  const activeTile = useMemo(
    () => tiles?.find((t) => t.layer_type === 'adjusted'),
    [tiles],
  );

  // Map → React: receive district click from Folium iframe
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'phantom-census-district-click' && event.data.districtId) {
        mapInitiatedClickRef.current = true; // map already zoomed — skip round-trip postMessage
        setSelectedDistrictId(event.data.districtId as string);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  // React → Map: focus + highlight district when selected from table or after tile swap (capability change)
  useEffect(() => {
    if (!selectedDistrictId) return;
    if (mapInitiatedClickRef.current) {
      mapInitiatedClickRef.current = false; // map already zoomed from its own click — no round-trip
      return;
    }
    const timer = setTimeout(() => {
      const iframe = mapContainerRef.current?.querySelector('iframe');
      iframe?.contentWindow?.postMessage(
        { type: 'phantom-census-focus-district', districtId: selectedDistrictId },
        '*',
      );
    }, 500); // 500ms: new iframes need time to initialise after a tile swap
    return () => clearTimeout(timer);
  }, [selectedDistrictId, activeTile]);

  const selectedDistrict = useMemo(
    () => scores?.find((s) => s.district_id === selectedDistrictId) ?? null,
    [scores, selectedDistrictId],
  );

  const rankedScores = useMemo(
    () =>
      [...(scores ?? [])].sort(
        (a, b) => asNumber(b.adjusted_desert_score) - asNumber(a.adjusted_desert_score),
      ),
    [scores],
  );

  // Clear brief when district or capability changes
  useEffect(() => { setBrief(''); }, [selectedDistrictId, capability]);

  const generateBrief = async () => {
    if (!selectedDistrictId) return;
    setBrief('');
    setBriefLoading(true);
    try {
      const response = await fetch(
        `/api/planner/districts/${encodeURIComponent(selectedDistrictId)}/brief?capability=${capability}`,
      );
      if (!response.ok || !response.body) throw new Error(`${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const parsed = JSON.parse(payload) as { text?: string; error?: string };
            if (parsed.text) setBrief((prev) => prev + parsed.text);
          } catch { /* partial chunk */ }
        }
      }
    } catch (err) {
      setBrief(`Error: ${err instanceof Error ? err.message : 'Failed to generate brief'}`);
    } finally {
      setBriefLoading(false);
    }
  };

  const saveScenario = async () => {
    if (!scenarioName.trim()) return;
    setSavingScenario(true);
    setError(null);
    try {
      await fetchJson('/api/planner/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenarioName: scenarioName.trim(),
          capability,
          regionFilter: selectedDistrict?.state_name ?? 'all',
          overrideSet: [],
          plannerNotes: scenarioNotes.trim(),
          plannerId,
        }),
      });
      // Refresh only scenarios via the fast summary endpoint
      const refreshed = await fetchJson<SummaryResponse>(
        `/api/planner/summary?capability=${capability}&plannerId=${plannerId}`,
      );
      setScenarios(refreshed.scenarios);
      setScenarioName('');
      setScenarioNotes('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save scenario');
    } finally {
      setSavingScenario(false);
    }
  };

  const saveOverride = async (overrideType: 'force-real' | 'force-phantom') => {
    if (!selectedFacilityId || !reasonNote.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await fetchJson('/api/planner/overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ facilityId: selectedFacilityId, overrideType, reasonNote, plannerId, capability }),
      });
      setReasonNote('');
      setSelectedFacilityId(null);
      // Re-fetch phantom list for the current district to reflect the override immediately
      if (selectedDistrictId) {
        setDistrictLoading(true);
        fetchJson<PhantomFacility[]>(
          `/api/planner/districts/${encodeURIComponent(selectedDistrictId)}/phantoms`,
        )
          .then(setPhantoms)
          .finally(() => setDistrictLoading(false));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save override');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:justify-between md:px-6">
          <div>
            <div className="flex items-center gap-2">
              <MapPinned className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold">Phantom Census</h1>
            </div>
            <p className="text-sm text-muted-foreground">
              Subtract questionable facilities before ranking healthcare deserts.
            </p>
            <p className="font-mono text-xs text-muted-foreground/60">{GIT_HASH}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-medium" htmlFor="capability">
              Capability
            </label>
            <select
              id="capability"
              value={capability}
              onChange={(event) => setCapability(event.target.value as Capability)}
              className="h-9 rounded-md border bg-background px-3 text-sm"
            >
              {capabilities.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-4 px-4 py-4 md:grid-cols-[minmax(0,1fr)_380px] md:px-6">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive md:col-span-2">
            {error}
          </div>
        )}

        <section className="space-y-4">
          {/* Summary cards — appear as soon as fast /summary call returns */}
          <div className="grid gap-3 sm:grid-cols-4">
            <Metric
              label="Facilities scored"
              value={summaryLoading ? '…' : formatCount(summary?.total_facilities ?? 0)}
              icon={<Database />}
            />
            <Metric
              label="Phantoms removed"
              value={summaryLoading ? '…' : formatCount(summary?.phantom_count ?? 0)}
              icon={<ShieldAlert />}
            />
            <Metric
              label="Contested"
              value={summaryLoading ? '…' : formatCount(summary?.contested_count ?? 0)}
              icon={<Activity />}
            />
            <Metric label="token_usage" value="0" icon={<RefreshCw />} />
          </div>

          {/* Map — loads independently; shows skeleton until tiles arrive */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>India Healthcare Desert Map</CardTitle>
              <Badge variant="secondary">Phantom-adjusted · orange circles = rank movers</Badge>
            </CardHeader>
            <CardContent>
              <MapTile loading={tilesLoading} html={activeTile?.html} innerRef={mapContainerRef} />
            </CardContent>
          </Card>

          {/* District ranking table — loads independently */}
          <Card>
            <CardHeader>
              <CardTitle>District Ranking</CardTitle>
            </CardHeader>
            <CardContent>
              {scoresLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }, (_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : rankedScores.length === 0 ? (
                <EmptyState
                  title="No desert scores loaded"
                  detail="Run the offline pipeline and load public.desert_scores before using the planner workflow."
                />
              ) : (
                <div className="overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-muted-foreground">
                      <tr className="border-b">
                        <th className="py-2 pr-3">District</th>
                        <th className="py-2 pr-3">State</th>
                        <th className="py-2 pr-3 text-right">Score</th>
                        <th className="py-2 pr-3 text-right">Rank shift</th>
                        <th className="py-2 text-right">Phantoms</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankedScores.map((score) => {
                        const activeScore = score.adjusted_desert_score;
                        const rankDelta = asNumber(score.raw_rank) - asNumber(score.adjusted_rank);
                        return (
                          <tr
                            key={score.district_id}
                            className={`cursor-pointer border-b hover:bg-muted/50 ${
                              score.district_id === selectedDistrictId ? 'bg-primary/5 font-medium' : ''
                            }`}
                            onClick={() => setSelectedDistrictId(score.district_id)}
                          >
                            <td className="py-2 pr-3 font-medium">{score.district_name}</td>
                            <td className="py-2 pr-3 text-muted-foreground">{score.state_name}</td>
                            <td className="py-2 pr-3 text-right">{formatScore(activeScore)}</td>
                            <td className="py-2 pr-3 text-right">{rankDelta > 0 ? `+${rankDelta}` : rankDelta}</td>
                            <td className="py-2 text-right">{formatCount(score.phantom_count)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{selectedDistrict ? selectedDistrict.district_name : 'District detail'}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedDistrict ? (
                <>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <Detail label="Raw score" value={formatScore(selectedDistrict.raw_desert_score)} />
                    <Detail label="Adjusted score" value={formatScore(selectedDistrict.adjusted_desert_score)} />
                    <Detail label="Raw rank" value={String(selectedDistrict.raw_rank)} />
                    <Detail label="Adjusted rank" value={String(selectedDistrict.adjusted_rank)} />
                  </div>

                  <div>
                    <h3 className="mb-2 text-sm font-semibold">Phantom examples</h3>
                    {districtLoading ? (
                      <div className="space-y-2">
                        <Skeleton className="h-16 w-full" />
                        <Skeleton className="h-16 w-full" />
                      </div>
                    ) : phantoms.length === 0 ? (
                      <p className="rounded-md border p-3 text-sm text-muted-foreground">
                        No phantom examples are available for this district yet.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {phantoms.map((facility) => (
                          <button
                            type="button"
                            key={facility.facility_id}
                            onClick={() =>
                              setSelectedFacilityId(
                                selectedFacilityId === facility.facility_id ? null : facility.facility_id,
                              )
                            }
                            className={`w-full rounded-md border p-3 text-left text-sm transition-colors ${
                              selectedFacilityId === facility.facility_id
                                ? 'border-primary bg-primary/5'
                                : 'hover:bg-muted/50'
                            }`}
                          >
                            <div className="font-medium">{facility.facility_name ?? facility.facility_id}</div>
                            <div className="text-muted-foreground">
                              {facility.primary_failed_test ?? 'evidence pending'}
                              {facility.override_id ? ' · overridden' : ''}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <EmptyState
                  title="No district selected"
                  detail="Click a district on the map or in the ranking table to explore phantom evidence."
                />
              )}
            </CardContent>
          </Card>

          {selectedDistrict && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm">AI Verification Brief</CardTitle>
                <Button
                  size="sm"
                  variant={brief ? 'ghost' : 'default'}
                  onClick={generateBrief}
                  disabled={briefLoading}
                >
                  {briefLoading ? 'Generating…' : brief ? 'Regenerate' : 'Generate Brief'}
                </Button>
              </CardHeader>
              <CardContent>
                {briefLoading && !brief && (
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-4 w-4/6" />
                  </div>
                )}
                {brief ? (
                  <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {brief}
                  </div>
                ) : !briefLoading ? (
                  <p className="text-sm text-muted-foreground">
                    Click "Generate Brief" to get an AI-powered field verification plan for this district.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          )}

          {selectedFacilityId && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Test evidence</CardTitle>
              </CardHeader>
              <CardContent>
                {facilityTests === null ? (
                  <div className="space-y-1">
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-8 w-full" />
                  </div>
                ) : facilityTests.length === 0 ? (
                  <EmptyState title="No tests found" detail="Tests run offline — may not be loaded yet." />
                ) : (
                  <div className="space-y-1">
                    {facilityTests.map((t) => (
                      <div key={t.test_name} className="flex items-center justify-between rounded border px-3 py-2 text-xs">
                        <span className="font-mono">{t.test_name}</span>
                        <span
                          className={`flex items-center gap-1 font-medium ${
                            t.result === 'fail'
                              ? 'text-destructive'
                              : t.result === 'pass'
                                ? 'text-green-600 dark:text-green-400'
                                : 'text-muted-foreground'
                          }`}
                        >
                          {t.result === 'fail' ? (
                            <XCircle className="h-3 w-3" />
                          ) : t.result === 'pass' ? (
                            <CheckCircle2 className="h-3 w-3" />
                          ) : null}
                          {t.result}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Override verdict</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Overrides are append-only and require a reason note for the audit trail.
              </p>
              <Input
                value={selectedFacilityId ?? ''}
                onChange={(event) => setSelectedFacilityId(event.target.value)}
                placeholder="facility_id"
              />
              <textarea
                value={reasonNote}
                onChange={(event) => setReasonNote(event.target.value)}
                placeholder="Reason note"
                className="min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
              <div className="flex gap-2">
                <Button
                  type="button"
                  disabled={!selectedFacilityId || !reasonNote.trim() || saving}
                  onClick={() => void saveOverride('force-real')}
                >
                  Force Real
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={!selectedFacilityId || !reasonNote.trim() || saving}
                  onClick={() => void saveOverride('force-phantom')}
                >
                  Force Phantom
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Saved scenarios</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {scenarios.length ? (
                <div className="space-y-2">
                  {scenarios.map((scenario) => (
                    <div key={scenario.scenario_id} className="rounded-md border p-3 text-sm">
                      <div className="font-medium">{scenario.scenario_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {scenario.region_filter} · {scenario.capability}
                      </div>
                      {scenario.planner_notes && (
                        <div className="mt-1 text-xs text-muted-foreground line-clamp-2">{scenario.planner_notes}</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No saved scenarios" detail="Save your current view to resume it later." />
              )}
              <div className="space-y-2 border-t pt-3">
                <Input
                  value={scenarioName}
                  onChange={(e) => setScenarioName(e.target.value)}
                  placeholder="Scenario name"
                />
                <textarea
                  value={scenarioNotes}
                  onChange={(e) => setScenarioNotes(e.target.value)}
                  placeholder="Optional notes"
                  className="min-h-14 w-full rounded-md border bg-background px-3 py-2 text-sm"
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={!scenarioName.trim() || savingScenario}
                  onClick={() => void saveScenario()}
                  className="w-full gap-2"
                >
                  <BookmarkPlus className="h-4 w-4" />
                  {savingScenario ? 'Saving…' : 'Save scenario'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </aside>
      </main>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactElement }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="text-primary [&_svg]:h-5 [&_svg]:w-5">{icon}</div>
        <div>
          <div className="text-xl font-semibold">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

const MapTile = React.memo(function MapTile({
  loading,
  html,
  innerRef,
}: {
  loading: boolean;
  html: string | undefined;
  innerRef: React.RefObject<HTMLDivElement | null>;
}) {
  if (loading) return <Skeleton className="h-[420px] w-full" />;
  if (html)
    return (
      <div
        ref={innerRef}
        className="h-[420px] overflow-hidden rounded-md border"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  return <EmptyMap />;
});

function EmptyMap() {
  return (
    <div className="flex h-[420px] items-center justify-center rounded-md border border-dashed bg-muted/30 p-6">
      <div className="max-w-md text-center">
        <FileText className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Tile layers are not loaded yet</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The app expects curated Folium HTML in public.tile_layers. Run the pipeline to generate them.
        </p>
      </div>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-md border border-dashed p-4 text-sm">
      <div className="font-medium">{title}</div>
      <div className="mt-1 text-muted-foreground">{detail}</div>
    </div>
  );
}
