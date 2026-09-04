/**
 * ProductionWorkspaceMaster.jsx
 * Consolidation #13: 4 master produksi → 1 hub dengan 5 tabs
 * Replaces: prod-locations + prod-lines + prod-machines + prod-shifts
 * Effort: 10h | Risk: Low
 */
import React, { useState, useEffect } from 'react';
import { Map, Factory, Wrench, Timer, LayoutDashboard, Loader2, RefreshCw } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import RahazaLocationsModule from './RahazaLocationsModule';
import RahazaLinesModule from './RahazaLinesModule';
import RahazaMachinesModule from './RahazaMachinesModule';
import RahazaShiftsModule from './RahazaShiftsModule';

// ── Ringkasan Tab ─────────────────────────────────────────────────────────────
const STATUS_MACHINE_COLOR = {
  idle:        'bg-muted text-muted-foreground dark:bg-gray-800/50 dark:text-gray-400',
  active:      'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  maintenance: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
};

function WorkspaceSummaryTab({ token }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchSummary = () => {
    setLoading(true);
    const h = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };
    Promise.all([
      fetch('/api/rahaza/locations', { headers: h }).then(r => r.ok ? r.json() : []).catch(() => []),
      fetch('/api/rahaza/lines',     { headers: h }).then(r => r.ok ? r.json() : []).catch(() => []),
      fetch('/api/rahaza/machines',  { headers: h }).then(r => r.ok ? r.json() : []).catch(() => []),
      fetch('/api/rahaza/shifts',    { headers: h }).then(r => r.ok ? r.json() : []).catch(() => []),
    ]).then(([locs, lines, machines, shifts]) => {
      const locArr = Array.isArray(locs) ? locs : (locs?.items || []);
      const lineArr = Array.isArray(lines) ? lines : (lines?.items || []);
      const machArr = Array.isArray(machines) ? machines : (machines?.items || []);
      const shiftArr = Array.isArray(shifts) ? shifts : (shifts?.items || []);

      setSummary({
        locations: {
          total: locArr.length,
          gedung: locArr.filter(l => l.type === 'gedung' && l.active !== false).length,
          zona:   locArr.filter(l => l.type === 'zona'   && l.active !== false).length,
        },
        lines: {
          total:  lineArr.length,
          active: lineArr.filter(l => l.active !== false).length,
        },
        machines: {
          total:       machArr.length,
          idle:        machArr.filter(m => m.status === 'idle').length,
          active:      machArr.filter(m => m.status === 'active').length,
          maintenance: machArr.filter(m => m.status === 'maintenance').length,
        },
        shifts: { total: shiftArr.length },
      });
    }).finally(() => setLoading(false));
  };

  useEffect(() => { fetchSummary(); }, [token]); // eslint-disable-line

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <Loader2 className="animate-spin text-muted-foreground" size={24} />
    </div>
  );

  if (!summary) return null;

  const kpis = [
    {
      icon: Map,       title: 'Lokasi',       color: 'text-blue-600',    bg: 'bg-blue-50 dark:bg-blue-900/20',
      value: summary.locations.total,
      sub: `${summary.locations.gedung} gedung · ${summary.locations.zona} zona`,
    },
    {
      icon: Factory,   title: 'Lini Produksi', color: 'text-indigo-600',  bg: 'bg-indigo-50 dark:bg-indigo-900/20',
      value: summary.lines.active,
      sub: `dari ${summary.lines.total} total lini`,
    },
    {
      icon: Wrench,    title: 'Mesin',          color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20',
      value: summary.machines.total,
      sub: `${summary.machines.active} aktif · ${summary.machines.maintenance} maintenance`,
    },
    {
      icon: Timer,     title: 'Shift Kerja',    color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20',
      value: summary.shifts.total,
      sub: 'shift terkonfigurasi',
    },
  ];

  return (
    <div className="p-4 md:p-6 space-y-6" data-testid="workspace-summary">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Ringkasan Workspace</h2>
          <p className="text-sm text-muted-foreground">Overview semua master data produksi</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchSummary}>
          <RefreshCw size={13} className="mr-1" /> Refresh
        </Button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map(kpi => (
          <div key={kpi.title} className={`rounded-xl border p-4 ${kpi.bg}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{kpi.title}</span>
              <kpi.icon size={16} className={kpi.color} />
            </div>
            <p className={`text-3xl font-bold tabular-nums ${kpi.color}`}>{kpi.value}</p>
            <p className="text-xs text-muted-foreground mt-1">{kpi.sub}</p>
          </div>
        ))}
      </div>

      {/* Machine Status Breakdown */}
      {summary.machines.total > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wrench size={14} /> Status Mesin
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {[
                { label: 'Idle',        count: summary.machines.idle,        key: 'idle' },
                { label: 'Aktif',       count: summary.machines.active,      key: 'active' },
                { label: 'Maintenance', count: summary.machines.maintenance,  key: 'maintenance' },
              ].map(s => (
                <div key={s.key}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                    STATUS_MACHINE_COLOR[s.key]
                  }`}
                >
                  <span className="text-xl font-bold tabular-nums">{s.count}</span>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>

            {/* Machine Status Bar */}
            {summary.machines.total > 0 && (
              <div className="mt-4">
                <div className="flex rounded-full overflow-hidden h-3">
                  {summary.machines.active > 0 && (
                    <div
                      className="bg-emerald-500 transition-all"
                      style={{ width: `${(summary.machines.active / summary.machines.total) * 100}%` }}
                      title={`Aktif: ${summary.machines.active}`}
                    />
                  )}
                  {summary.machines.idle > 0 && (
                    <div
                      className="bg-muted dark:bg-gray-600 transition-all"
                      style={{ width: `${(summary.machines.idle / summary.machines.total) * 100}%` }}
                      title={`Idle: ${summary.machines.idle}`}
                    />
                  )}
                  {summary.machines.maintenance > 0 && (
                    <div
                      className="bg-amber-400 transition-all"
                      style={{ width: `${(summary.machines.maintenance / summary.machines.total) * 100}%` }}
                      title={`Maintenance: ${summary.machines.maintenance}`}
                    />
                  )}
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-xs flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Aktif</span>
                  <span className="text-xs flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-muted dark:bg-gray-600 inline-block" /> Idle</span>
                  <span className="text-xs flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Maintenance</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Main Hub Component ────────────────────────────────────────────────────────
export default function ProductionWorkspaceMaster({ token }) {
  const [activeTab, setActiveTab] = useState('summary');

  return (
    <div className="h-full" data-testid="production-workspace-master">
      {/* Hub Header */}
      <div className="px-4 md:px-6 py-4 border-b bg-background">
        <h1 className="text-xl font-bold tracking-tight">Master Workspace Produksi</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Kelola lokasi, lini, mesin, dan shift produksi dalam satu tampilan terpadu
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
        <div className="px-4 md:px-6 pt-4 border-b bg-background">
          <TabsList className="h-9">
            <TabsTrigger value="summary" className="gap-1.5" data-testid="tab-workspace-summary">
              <LayoutDashboard size={13} /> Ringkasan
            </TabsTrigger>
            <TabsTrigger value="locations" className="gap-1.5" data-testid="tab-locations">
              <Map size={13} /> Lokasi &amp; Zona
            </TabsTrigger>
            <TabsTrigger value="lines" className="gap-1.5" data-testid="tab-lines">
              <Factory size={13} /> Lini Produksi
            </TabsTrigger>
            <TabsTrigger value="machines" className="gap-1.5" data-testid="tab-machines">
              <Wrench size={13} /> Mesin
            </TabsTrigger>
            <TabsTrigger value="shifts" className="gap-1.5" data-testid="tab-shifts">
              <Timer size={13} /> Shift Kerja
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="summary"   className="flex-1 overflow-auto m-0">
          <WorkspaceSummaryTab token={token} />
        </TabsContent>
        <TabsContent value="locations" className="flex-1 overflow-auto m-0">
          <RahazaLocationsModule token={token} />
        </TabsContent>
        <TabsContent value="lines"     className="flex-1 overflow-auto m-0">
          <RahazaLinesModule token={token} />
        </TabsContent>
        <TabsContent value="machines"  className="flex-1 overflow-auto m-0">
          <RahazaMachinesModule token={token} />
        </TabsContent>
        <TabsContent value="shifts"    className="flex-1 overflow-auto m-0">
          <RahazaShiftsModule token={token} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
