/**
 * CapacityPlanningModule — Phase 2 P0: Rule-based Factory Capacity Planning
 *
 * Fitur:
 * - Snapshot kapasitas pabrik (WO backlog vs kapasitas harian)
 * - Check feasibility WO baru
 * - Trend utilisasi (grafik batang sederhana)
 * - Bottleneck mesin berdasarkan downtime
 * - Simulasi estimasi penyelesaian WO baru
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  BarChart3, RefreshCw, AlertTriangle, CheckCircle2,
  XCircle, Factory, Cpu, Clock, Wrench, TrendingUp,
  PlayCircle, ChevronDown, ChevronUp,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { useToast } from '../../hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_CONFIG = {
  normal:   { color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30', icon: CheckCircle2,  label: 'Normal' },
  warning:  { color: 'text-amber-700 dark:text-amber-400',   bg: 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30',     icon: AlertTriangle, label: 'Perhatian' },
  critical: { color: 'text-red-700 dark:text-red-400',     bg: 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30',         icon: XCircle,       label: 'Kritis' },
};

function UtilBar({ pct, status }) {
  const colors = { normal: 'bg-emerald-500', warning: 'bg-amber-500', critical: 'bg-red-500' };
  return (
    <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${colors[status] || 'bg-muted'}`}
        style={{ width: `${Math.min(pct, 100)}%` }}
      />
    </div>
  );
}

function UtilTrendChart({ data, capacity }) {
  if (!data || data.length === 0) return (
    <div className="flex items-center justify-center h-32 text-muted-foreground/60 dark:text-zinc-500 text-sm">
      Belum ada data output
    </div>
  );
  const maxPcs = Math.max(...data.map(d => d.output_pcs), capacity, 1);
  return (
    <div className="flex items-end gap-1 h-32 px-2">
      {data.map(d => {
        const heightPct = (d.output_pcs / maxPcs) * 100;
        const cfg = STATUS_CONFIG[d.status] || STATUS_CONFIG.normal;
        const barColor = d.status === 'critical' ? 'bg-red-500' : d.status === 'warning' ? 'bg-amber-500' : 'bg-emerald-500';
        return (
          <div key={d.date} className="flex-1 flex flex-col items-center group relative">
            <div
              className={`w-full ${barColor} rounded-sm transition-all opacity-80 hover:opacity-100`}
              style={{ height: `${heightPct}%` }}
            />
            <div className="text-xs text-muted-foreground/60 mt-1 truncate w-full text-center" title={d.date}>
              {d.date?.slice(5)}
            </div>
            <div className="absolute bottom-full mb-1 bg-muted border border-border rounded px-2 py-1 text-xs text-foreground whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-10">
              {d.date}: {d.output_pcs.toLocaleString()} pcs ({d.utilization_pct}%)
            </div>
          </div>
        );
      })}
      {/* Capacity reference line placeholder */}
    </div>
  );
}

export default function CapacityPlanningModule({ user, headers }) {
  const [overview, setOverview] = useState(null);
  const [utilTrend, setUtilTrend] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [loading, setLoading] = useState(false);

  // Check WO form
  const [checkForm, setCheckForm] = useState({ quantity: 500, target_days: 7, priority: 'normal' });
  const [checkResult, setCheckResult] = useState(null);
  const [checking, setChecking] = useState(false);

  // Simulate form
  const [simForm, setSimForm] = useState({ quantity: 500, product_name: '', start_date: '', priority: 'normal' });
  const [simResult, setSimResult] = useState(null);
  const [simulating, setSimulating] = useState(false);

  const [showBottlenecks, setShowBottlenecks] = useState(false);
  const { toast } = useToast();
  const authH = useMemo(() => headers || {}, [headers]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, utilRes, bnRes] = await Promise.all([
        axios.get(`${API}/api/capacity/overview`, { headers: authH }),
        axios.get(`${API}/api/capacity/utilization`, { headers: authH, params: { days: 7 } }),
        axios.get(`${API}/api/capacity/bottlenecks`, { headers: authH }),
      ]);
      setOverview(ovRes.data);
      setUtilTrend(utilRes.data?.data || []);
      setBottlenecks(bnRes.data?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal load data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [authH, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleCheckWO = async () => {
    setChecking(true);
    try {
      const res = await axios.post(`${API}/api/capacity/check-wo`, checkForm, { headers: authH });
      setCheckResult(res.data);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal check', variant: 'destructive' });
    } finally {
      setChecking(false);
    }
  };

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      const res = await axios.post(`${API}/api/capacity/simulate`, simForm, { headers: authH });
      setSimResult(res.data);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal simulasi', variant: 'destructive' });
    } finally {
      setSimulating(false);
    }
  };

  const util = overview?.utilization;
  const statusCfg = util ? (STATUS_CONFIG[util.status] || STATUS_CONFIG.normal) : null;
  const StatusIcon = statusCfg?.icon || CheckCircle2;

  return (
    <div className="p-4 md:p-6 space-y-6 text-foreground">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="text-blue-600 dark:text-blue-400" /> Perencanaan Kapasitas
          </h2>
          <p className="text-sm text-muted-foreground/60 dark:text-zinc-400 mt-1">Analisis kapasitas produksi berbasis rule & data historis</p>
        </div>
        <Button
          variant="outline" size="sm"
          onClick={fetchAll} disabled={loading}
          className="border-border text-foreground/80 hover:bg-muted"
          data-testid="btn-refresh-capacity"
        >
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">WO Aktif</div>
            <div className="text-2xl font-bold text-foreground">
              {loading ? '…' : (overview?.load?.active_count ?? '—')}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">
              {overview?.load?.overdue_count > 0 && (
                <span className="text-red-700 dark:text-red-400">{overview.load.overdue_count} overdue</span>
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Backlog (pcs)</div>
            <div className="text-2xl font-bold text-foreground">
              {loading ? '…' : (overview?.load?.total_remaining_pcs?.toLocaleString('id') ?? '—')}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">sisa produksi</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Output Rata-rata/hari</div>
            <div className="text-2xl font-bold text-foreground">
              {loading ? '…' : `${overview?.avg_daily_output_pcs?.toLocaleString('id') ?? '—'} pcs`}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">7 hari terakhir</div>
          </CardContent>
        </Card>
        <Card className={`border ${statusCfg?.bg || 'bg-card border-border'}`}>
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Status Kapasitas</div>
            <div className={`text-2xl font-bold flex items-center gap-1 ${statusCfg?.color || 'text-foreground'}`}>
              {!loading && <StatusIcon className="w-5 h-5" />}
              {loading ? '…' : (util?.utilization_pct != null ? `${util.utilization_pct}%` : '—')}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">
              {util ? `${util.days_to_clear} hari untuk selesai` : ''}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Utilization Bar */}
      {overview && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-foreground/80">Utilisasi Kapasitas</CardTitle>
          </CardHeader>
          <CardContent>
            <UtilBar pct={util?.utilization_pct || 0} status={util?.status || 'normal'} />
            <div className="flex justify-between text-xs text-muted-foreground/60 dark:text-zinc-500 mt-1">
              <span>0%</span>
              <span className={statusCfg?.color}>{util?.utilization_pct}%</span>
              <span>100%</span>
            </div>
            {overview.downtime_today_min > 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-400 mt-2">
                ⚠ Downtime hari ini: {overview.downtime_today_min} menit
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Utilization Trend */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-foreground/80 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Output Harian (7 Hari Terakhir)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UtilTrendChart data={utilTrend} capacity={overview?.config?.daily_capacity_pcs || 1000} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Check WO Feasibility */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-foreground/80 flex items-center gap-2">
              <Factory className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Cek Kelayakan WO Baru
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Jumlah (pcs)</label>
                <Input
                  type="number"
                  value={checkForm.quantity}
                  onChange={e => setCheckForm(f => ({ ...f, quantity: parseInt(e.target.value) || 0 }))}
                  className="bg-muted border-border text-sm"
                  data-testid="input-check-qty"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Target Hari</label>
                <Input
                  type="number"
                  value={checkForm.target_days}
                  onChange={e => setCheckForm(f => ({ ...f, target_days: parseInt(e.target.value) || 1 }))}
                  className="bg-muted border-border text-sm"
                  data-testid="input-check-days"
                />
              </div>
            </div>
            <Button
              onClick={handleCheckWO} disabled={checking}
              className="w-full bg-blue-600 hover:bg-blue-700"
              data-testid="btn-check-wo"
            >
              {checking ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Factory className="w-4 h-4 mr-1" />}
              Cek Kapasitas
            </Button>
            {checkResult && (
              <div className={`rounded-lg p-3 border ${checkResult.feasible ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30' : 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30'}`}>
                <div className={`font-semibold flex items-center gap-1 mb-2 ${checkResult.feasible ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                  {checkResult.feasible ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                  {checkResult.feasible ? 'Layak' : 'Tidak Layak dalam Target'}
                </div>
                <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 space-y-1">
                  <div>Butuh: <span className="text-foreground">{checkResult.days_needed} hari</span> (kapasitas {checkResult.effective_daily_capacity} pcs/hari)</div>
                  <div>Utilisasi proyeksi: <span className={checkResult.projected_utilization?.status === 'critical' ? 'text-red-700 dark:text-red-400' : 'text-foreground'}>{checkResult.projected_utilization?.utilization_pct}%</span></div>
                  {!checkResult.feasible && (
                    <div>Mulai disarankan: <span className="text-amber-700 dark:text-amber-400">{checkResult.recommended_start_date}</span></div>
                  )}
                </div>
                {checkResult.warnings?.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {checkResult.warnings.map((w, i) => (
                      <li key={i} className="text-xs text-amber-600 dark:text-amber-300 flex gap-1">
                        <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /> {w}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Simulate Schedule */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-foreground/80 flex items-center gap-2">
              <PlayCircle className="w-4 h-4 text-purple-600 dark:text-purple-400" /> Simulasi Jadwal WO
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Nama Produk</label>
                <Input
                  value={simForm.product_name}
                  onChange={e => setSimForm(f => ({ ...f, product_name: e.target.value }))}
                  placeholder="Kaos Polo..."
                  className="bg-muted border-border text-sm"
                  data-testid="input-sim-product"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Jumlah (pcs)</label>
                <Input
                  type="number"
                  value={simForm.quantity}
                  onChange={e => setSimForm(f => ({ ...f, quantity: parseInt(e.target.value) || 0 }))}
                  className="bg-muted border-border text-sm"
                  data-testid="input-sim-qty"
                />
              </div>
            </div>
            <Button
              onClick={handleSimulate} disabled={simulating}
              className="w-full bg-purple-600 hover:bg-purple-700"
              data-testid="btn-simulate"
            >
              {simulating ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-1" />}
              Simulasi
            </Button>
            {simResult && (
              <div className="rounded-lg p-3 bg-purple-100 dark:bg-purple-500/10 border border-purple-400 dark:border-purple-500/30">
                <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 space-y-1">
                  <div>Produk: <span className="text-foreground">{simResult.product_name || '—'}</span></div>
                  <div>Mulai: <span className="text-foreground">{simResult.start_date}</span></div>
                  <div>Estimasi selesai: <span className="text-purple-600 dark:text-purple-300 font-medium">{simResult.estimated_completion}</span></div>
                  <div>Hari dibutuhkan: <span className="text-foreground">{simResult.days_needed} + {simResult.buffer_days} buffer</span></div>
                  <div className="mt-1 text-muted-foreground/60 dark:text-zinc-500">{simResult.note}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bottlenecks */}
      <Card className="bg-card border-border">
        <CardHeader
          className="pb-2 cursor-pointer"
          onClick={() => setShowBottlenecks(b => !b)}
        >
          <CardTitle className="text-sm font-medium text-foreground/80 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Wrench className="w-4 h-4 text-orange-600 dark:text-orange-400" />
              Bottleneck Mesin (7 Hari Terakhir) {bottlenecks.length > 0 && <Badge variant="outline" className="text-orange-600 dark:text-orange-400 border-orange-400 dark:border-orange-500/30">{bottlenecks.length}</Badge>}
            </span>
            {showBottlenecks ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </CardTitle>
        </CardHeader>
        {showBottlenecks && (
          <CardContent>
            {bottlenecks.length === 0 ? (
              <p className="text-sm text-muted-foreground/60 dark:text-zinc-500">Tidak ada data downtime 7 hari terakhir.</p>
            ) : (
              <div className="space-y-2">
                {bottlenecks.map((b, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-border">
                    <div>
                      <p className="text-sm text-foreground">{b.machine_name}</p>
                      <p className="text-xs text-muted-foreground/60 dark:text-zinc-500">{b.event_count} kejadian</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-medium ${
                        b.severity === 'high' ? 'text-red-700 dark:text-red-400' :
                        b.severity === 'medium' ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}>{b.total_downtime_min} menit</p>
                      <Badge
                        variant="outline"
                        className={`text-xs ${
                          b.severity === 'high' ? 'text-red-700 dark:text-red-400 border-red-400 dark:border-red-500/30' :
                          b.severity === 'medium' ? 'text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-500/30' :
                          'text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30'
                        }`}
                      >{b.severity}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
