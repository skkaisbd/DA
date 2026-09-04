import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import axios from 'axios';
import { AlertTriangle, Package, MapPin, TrendingDown, RefreshCw, ArrowRight, Thermometer, Building2, ArrowDownToLine, ArrowUpFromLine } from 'lucide-react';
import { toast } from '../ui/sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const KPI = ({ label, value, sub, icon: Icon, color }) => (
  <div className="bg-white dark:bg-[var(--card-surface)] border border-border rounded-xl p-4 flex items-start gap-4 shadow-sm">
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
      <Icon size={18} className="text-foreground" />
    </div>
    <div>
      <p className="text-2xl font-bold text-foreground dark:text-foreground">{value}</p>
      <p className="text-xs font-medium text-muted-foreground/60 dark:text-foreground/75 mt-0.5">{label}</p>
      {sub && <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">{sub}</p>}
    </div>
  </div>
);

const ZONE_COLORS = [
  'bg-emerald-500', 'bg-teal-500', 'bg-cyan-500', 'bg-sky-500',
  'bg-violet-500', 'bg-purple-500', 'bg-rose-500', 'bg-orange-500',
];

function utilColor(pct) {
  if (pct >= 85) return 'bg-red-500/80 border-red-400';
  if (pct >= 55) return 'bg-amber-500/80 border-amber-400';
  return 'bg-emerald-500/80 border-emerald-400';
}

export default function WarehouseDashboard({ token }) {
  const [kpi, setKpi] = useState({ total_items: 0, total_locations: 0, pending_gr: 0, pending_putaway: 0 });
  const [lowStock, setLowStock] = useState([]);
  const [reorderAlerts, setReorderAlerts] = useState([]);
  const [stockSummary, setStockSummary] = useState(null);
  const [stockByLoc, setStockByLoc] = useState([]);
  const [loading, setLoading] = useState(true);
  // ── WMS multi-warehouse extension ──────────────────────────────────────────
  const [wmsBuildings, setWmsBuildings] = useState([]);
  const [selectedBldg, setSelectedBldg] = useState('');
  const [wmsPending, setWmsPending] = useState({ pending_inbound: 0, pending_outbound_rm: 0, pending_outbound_fg: 0, total_pending: 0 });
  const [occupancyAlerts, setOccupancyAlerts] = useState({ critical: [], warning: [], total_alerts: 0, critical_count: 0, warning_count: 0 });
  const hdrs = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const loadWMS = useCallback(async () => {
    try {
      const buildingFilter = selectedBldg ? `?building_id=${selectedBldg}` : '';
      const [bRes, pRes, aRes] = await Promise.all([
        fetch(`${API}/api/wms/buildings`, { headers: hdrs }).then(r => r.json()),
        fetch(`${API}/api/wms/pending/summary${buildingFilter}`, { headers: hdrs }).then(r => r.json()),
        fetch(`${API}/api/wms/alerts/occupancy?threshold=90${selectedBldg ? `&building_id=${selectedBldg}` : ''}`, { headers: hdrs }).then(r => r.json()),
      ]);
      const buildings = Array.isArray(bRes) ? bRes : [];
      setWmsBuildings(buildings);
      setWmsPending(pRes || {});
      setOccupancyAlerts(aRes || { critical: [], warning: [], total_alerts: 0 });

      // Heatmap kanonik (SSOT wh_*): utilisasi bin per zona dari /api/wms/map/{building}
      const targets = selectedBldg ? buildings.filter(b => b.id === selectedBldg) : buildings;
      const maps = await Promise.all(
        targets.map(b =>
          fetch(`${API}/api/wms/map/${b.id}`, { headers: hdrs })
            .then(r => (r.ok ? r.json() : null))
            .catch(() => null)
        )
      );
      const tiles = [];
      for (const m of maps) {
        if (!m || !Array.isArray(m.zones)) continue;
        for (const z of m.zones) {
          tiles.push({
            location_id: z.id,
            name: `${m.code || m.name || ''}·${z.code || z.name || ''}`,
            total_positions: z.total_positions || 0,
            occupied: z.occupied_positions || 0,
            pct: z.occupancy_pct || 0,
          });
        }
      }
      tiles.sort((a, b) => b.pct - a.pct);
      setStockByLoc(tiles);
    } catch { /* silent */ }
  }, [hdrs, selectedBldg]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kpiRes, lowRes, reorderRes, sumRes] = await Promise.allSettled([
        axios.get(`${API}/api/wms/legacy/dashboard-kpi`, { headers: hdrs }),
        axios.get(`${API}/api/rahaza/materials?low_stock=true`, { headers: hdrs }),
        axios.get(`${API}/api/rahaza/materials/reorder-alerts`, { headers: hdrs }),
        axios.get(`${API}/api/rahaza/material-stock/summary`, { headers: hdrs }),
      ]);
      if (kpiRes.status === 'fulfilled') setKpi(kpiRes.value.data || {});
      if (lowRes.status === 'fulfilled') setLowStock(lowRes.value.data || []);
      if (reorderRes.status === 'fulfilled') setReorderAlerts(reorderRes.value.data || []);
      if (sumRes.status === 'fulfilled') setStockSummary(sumRes.value.data || null);
      // Heatmap stok/lokasi dibangun di loadWMS() dari sumber kanonik wh_*.
    } catch (err) {
      toast.error('Gagal memuat data dashboard');
    } finally {
      setLoading(false);
    }
  }, [hdrs]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadWMS(); }, [loadWMS]);

  const criticalCount = lowStock.length + reorderAlerts.length;
  // Total SKU kanonik: jumlah baris stok ber-SKU dari SSOT rahaza_material_stock (bukan legacy warehouse_stock kosong).
  const stockedSkuCount = stockSummary?.by_category
    ? Object.values(stockSummary.by_category).reduce((s, c) => s + (c?.row_count || 0), 0)
    : null;

  return (
    <div className="space-y-6 p-1" data-testid="warehouse-dashboard">
      {/* Header with Multi-Warehouse Selector */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-foreground">Dashboard Gudang</h2>
          <p className="text-sm text-foreground/55 mt-0.5">Ringkasan real-time Portal Gudang</p>
        </div>
        <div className="flex items-center gap-2">
          {wmsBuildings.length > 0 && (
            <SmartNativeSelect
              data-testid="warehouse-building-selector"
              value={selectedBldg}
              onChange={e => setSelectedBldg(e.target.value)}
              className="bg-[var(--card-surface)] border border-border rounded-lg px-3 py-1.5 text-xs text-foreground"
              title="Filter berdasarkan gedung WMS"
            >
              <option value="">📦 Semua Gedung</option>
              {wmsBuildings.map(b => <option key={b.id} value={b.id}>🏢 {b.name}</option>)}
            </SmartNativeSelect>
          )}
          <button
            onClick={() => { load(); loadWMS(); }}
            className="flex items-center gap-2 text-xs text-foreground/65 hover:text-foreground px-3 py-1.5 bg-[var(--card-surface)] hover:bg-[var(--card-surface-hover)] rounded-lg border border-border transition-colors"
            data-testid="dashboard-refresh-btn"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* WMS Occupancy Alert Banner */}
      {occupancyAlerts.total_alerts > 0 && (
        <div data-testid="dashboard-occupancy-alert" className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-red-700 dark:text-red-500" />
            <span className="text-sm font-semibold text-red-600 dark:text-red-300">
              Peringatan Kapasitas Rak — {occupancyAlerts.total_alerts} rak ≥ 90% terisi
            </span>
            {occupancyAlerts.critical_count > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 ml-2">
                ⚠ {occupancyAlerts.critical_count} kritis (≥95%)
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {[...(occupancyAlerts.critical || []), ...(occupancyAlerts.warning || [])].slice(0, 6).map(r => (
              <div key={r.rack_id} className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg border ${r.severity === 'critical' ? 'bg-red-100 dark:bg-red-500/15 border-red-500/40' : 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30'}`}>
                <div className="min-w-0">
                  <div className="text-xs font-mono font-bold truncate text-foreground">{r.building_code}-{r.zone_code}-{r.rack_code}</div>
                  <div className="text-[10px] text-foreground/55 truncate">{r.rack_name}</div>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-bold ${r.severity === 'critical' ? 'text-red-700 dark:text-red-500' : 'text-amber-700 dark:text-amber-500'}`}>{r.occupancy_pct}%</div>
                  <div className="text-[10px] text-foreground/55">{r.free_slots} kosong</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* WMS Pending Movements Strip */}
      {wmsBuildings.length > 0 && (
        <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4" data-testid="wms-pending-strip">
          <div className="flex items-center gap-2 mb-3">
            <Building2 size={14} className="text-violet-500" />
            <span className="text-sm font-semibold text-foreground">WMS — Pending Movements{selectedBldg ? ` (${wmsBuildings.find(b => b.id === selectedBldg)?.name})` : ' (Semua Gedung)'}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg p-3">
              <ArrowDownToLine size={14} className="text-emerald-500 mb-1" />
              <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{wmsPending.pending_inbound ?? 0}</div>
              <div className="text-[10px] text-foreground/55">Pending Inbound</div>
            </div>
            <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20 rounded-lg p-3">
              <ArrowUpFromLine size={14} className="text-amber-700 dark:text-amber-500 mb-1" />
              <div className="text-lg font-bold text-amber-600 dark:text-amber-400">{wmsPending.pending_outbound_rm ?? 0}</div>
              <div className="text-[10px] text-foreground/55">Outbound RM (Issue)</div>
            </div>
            <div className="bg-orange-100 dark:bg-orange-500/10 border border-orange-300 dark:border-orange-500/20 rounded-lg p-3">
              <ArrowUpFromLine size={14} className="text-orange-500 mb-1" />
              <div className="text-lg font-bold text-orange-600 dark:text-orange-400">{wmsPending.pending_outbound_fg ?? 0}</div>
              <div className="text-[10px] text-foreground/55">Outbound FG (Ship)</div>
            </div>
            <div className="bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-500/20 rounded-lg p-3">
              <Package size={14} className="text-violet-500 mb-1" />
              <div className="text-lg font-bold text-violet-600 dark:text-violet-400">{wmsPending.total_pending ?? 0}</div>
              <div className="text-[10px] text-foreground/55">Total Pending</div>
            </div>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Total SKU" value={stockedSkuCount ?? kpi.total_items ?? '–'} icon={Package} color="bg-blue-500/80" />
        <KPI label="Lokasi Aktif" value={stockByLoc.length || kpi.total_locations || 0} icon={MapPin} color="bg-teal-500/80" />
        <KPI label="GR Pending" value={kpi.pending_gr ?? '–'} icon={RefreshCw} color="bg-violet-500/80" />
        <KPI
          label="Stok Kritis"
          value={criticalCount}
          sub={criticalCount > 0 ? `${criticalCount} material perlu perhatian` : 'Semua aman'}
          icon={AlertTriangle}
          color={criticalCount > 0 ? 'bg-red-500/80' : 'bg-emerald-500/80'}
        />
      </div>

      {/* U1 — Low-stock & Reorder Alert Panel */}
      {criticalCount > 0 && (
        <div className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded-xl p-4" data-testid="low-stock-panel">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-red-700 dark:text-red-500" />
            <span className="text-sm font-semibold text-red-600 dark:text-red-300">Stok Kritis & Reorder Alert ({criticalCount})</span>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {[...lowStock.map(m => ({ ...m, _type: 'low' })), ...reorderAlerts.map(m => ({ ...m, _type: 'reorder' }))]
              .slice(0, 12)
              .map((m, i) => (
              <div key={`${m._type}-${m.code || m.id || i}`} className="flex items-center justify-between bg-[var(--card-surface)] border border-border rounded-lg px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${m._type === 'low' ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300' : 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300'}`}>
                    {m._type === 'low' ? 'LOW' : 'REORDER'}
                  </span>
                  <span className="text-xs text-foreground truncate font-medium">{m.code}</span>
                  <span className="text-xs text-foreground/55 truncate hidden sm:block">{m.name}</span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-xs font-mono text-red-600 dark:text-red-300">
                    {m.current_qty ?? 0} {m.unit}
                  </span>
                  <TrendingDown size={13} className="text-red-700 dark:text-red-500" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* U6 — Stock Heatmap by Location */}
      <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4" data-testid="stock-heatmap">
        <div className="flex items-center gap-2 mb-4">
          <Thermometer size={16} className="text-cyan-500" />
          <span className="text-sm font-semibold text-foreground">Heatmap Stok per Lokasi</span>
          <span className="ml-auto text-xs text-foreground/45">{stockByLoc.length} zona</span>
        </div>
        {stockByLoc.length === 0 ? (
          <div className="text-center py-8 text-foreground/40 text-sm">Belum ada zona/rak terisi</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {stockByLoc.map((loc, i) => {
              const pct = loc.pct || 0;
              return (
                <div
                  key={loc.location_id}
                  className={`border rounded-xl p-3 transition-all hover:scale-105 cursor-default ${utilColor(pct)}`}
                  title={`${loc.name}: ${loc.occupied}/${loc.total_positions} bin terisi (${pct}%)`}
                  data-testid={`heatmap-loc-${i}`}
                >
                  <div className="text-xs font-bold text-foreground truncate">{loc.name}</div>
                  <div className="text-lg font-bold text-foreground mt-1">
                    {loc.occupied}<span className="text-xs font-normal text-foreground/70">/{loc.total_positions}</span>
                  </div>
                  <div className="text-[10px] text-foreground/85">bin terisi · {pct}%</div>
                  <div className="mt-2 h-1.5 rounded-full bg-foreground/20">
                    <div className="h-full rounded-full bg-white/70" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {/* Legend */}
        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-border">
          <span className="text-[10px] font-medium text-foreground dark:text-foreground/75">Utilisasi:</span>
          {[['bg-emerald-500/80', '< 55%'], ['bg-amber-500/80', '55–85%'], ['bg-red-500/80', '> 85%']].map(([c, l]) => (
            <div key={l} className="flex items-center gap-1">
              <div className={`w-2.5 h-2.5 rounded-sm ${c}`} />
              <span className="text-[10px] font-medium text-foreground dark:text-foreground/80">{l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
