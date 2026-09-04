/**
 * ExecutiveReportModule — Phase 3 P1
 *
 * Cross-module consolidated executive dashboard.
 * Fitur: KPI summary semua domain, month-on-month comparison chart,
 *        finance/produksi/HR/marketing snapshots, trend multi-KPI.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  BarChart3, RefreshCw, TrendingUp, TrendingDown,
  DollarSign, Factory, Users, Zap, ChevronUp,
  ChevronDown, Calendar, ArrowRight, Sparkles, Loader2,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { useToast } from '../../hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL || '';
const FMT_IDR = v => `Rp ${(+v || 0).toLocaleString('id-ID')}`;
const FMT_NUM = v => (+v || 0).toLocaleString('id-ID');
const FMT_PCT = v => `${(+v || 0).toFixed(1)}%`;

function Delta({ pct, invert = false }) {
  if (pct == null) return <span className="text-muted-foreground/60 text-xs">n/a</span>;
  const positive = invert ? pct <= 0 : pct >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${
      positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'
    }`}>
      {pct >= 0 ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      {Math.abs(pct)}%
    </span>
  );
}

function KpiCard({ icon: Icon, iconColor, label, value, sub, delta, invertDelta }) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="pt-4 pb-3">
        <div className="flex justify-between items-start mb-1">
          <span className="text-xs text-muted-foreground/60 dark:text-zinc-400">{label}</span>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
        <div className="text-xl font-bold text-foreground">{value}</div>
        <div className="flex items-center gap-2 mt-0.5">
          {sub && <span className="text-xs text-muted-foreground/60 dark:text-zinc-500">{sub}</span>}
          {delta !== undefined && <Delta pct={delta} invert={invertDelta} />}
        </div>
      </CardContent>
    </Card>
  );
}

function TrendChart({ data, keys }) {
  if (!data || data.length === 0) return (
    <div className="flex items-center justify-center h-40 text-muted-foreground/60 dark:text-zinc-500 text-sm">Belum ada data</div>
  );
  const colorMap = {
    revenue_rp:           'bg-blue-500',
    net_income_rp:        'bg-emerald-500',
    ar_overdue_rp:        'bg-red-500',
    payroll_total_rp:     'bg-purple-500',
  };
  const labelMap = {
    revenue_rp:       'Revenue',
    net_income_rp:    'Net Income',
    ar_overdue_rp:    'AR Overdue',
    payroll_total_rp: 'Payroll',
  };
  const activeKey = keys[0];
  const maxVal = Math.max(...data.map(d => d[activeKey] || 0), 1);
  return (
    <div>
      <div className="flex gap-3 mb-2 flex-wrap">
        {keys.map(k => (
          <span key={k} className="flex items-center gap-1 text-xs text-muted-foreground/60 dark:text-zinc-400">
            <span className={`w-2 h-2 rounded-full ${colorMap[k] || 'bg-muted'}`} />
            {labelMap[k] || k}
          </span>
        ))}
      </div>
      <div className="flex items-end gap-1 h-32">
        {data.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center group relative">
            <div
              className={`w-full ${colorMap[activeKey] || 'bg-blue-500'} rounded-sm opacity-70 hover:opacity-100`}
              style={{ height: `${((d[activeKey] || 0) / maxVal) * 100}%` }}
            />
            <div className="text-xs text-muted-foreground/60 mt-1 truncate w-full text-center">{d.period?.slice(5)}</div>
            <div className="absolute bottom-full mb-1 bg-muted border border-border rounded px-2 py-1 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 z-10">
              {d.period}: {FMT_IDR(d[activeKey])}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Lightweight markdown renderer (no external deps) — handles #/##/### headings,
// bullet lists, and **bold** inline. Good enough for AI narrative output.
function renderInline(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <strong key={i} className="font-semibold text-foreground">{p.slice(2, -2)}</strong>
      : <span key={i}>{p}</span>
  );
}

function MarkdownLite({ text }) {
  const lines = String(text || '').split('\n');
  const blocks = [];
  let list = [];
  const flush = (key) => {
    if (list.length) {
      blocks.push(<ul key={`ul-${key}`} className="list-disc pl-5 space-y-1 my-2">{list}</ul>);
      list = [];
    }
  };
  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    if (/^###\s+/.test(line)) { flush(idx); blocks.push(<h4 key={idx} className="text-sm font-bold text-foreground mt-3 mb-1">{renderInline(line.replace(/^###\s+/, ''))}</h4>); }
    else if (/^##\s+/.test(line)) { flush(idx); blocks.push(<h3 key={idx} className="text-base font-bold text-indigo-700 dark:text-indigo-300 mt-4 mb-1">{renderInline(line.replace(/^##\s+/, ''))}</h3>); }
    else if (/^#\s+/.test(line)) { flush(idx); blocks.push(<h2 key={idx} className="text-lg font-bold text-foreground mt-2 mb-1">{renderInline(line.replace(/^#\s+/, ''))}</h2>); }
    else if (/^[-*]\s+/.test(line)) { list.push(<li key={idx} className="text-sm text-foreground/90 leading-relaxed">{renderInline(line.replace(/^[-*]\s+/, ''))}</li>); }
    else if (line.trim() === '') { flush(idx); }
    else { flush(idx); blocks.push(<p key={idx} className="text-sm text-foreground/90 leading-relaxed my-1">{renderInline(line)}</p>); }
  });
  flush('end');
  return <div>{blocks}</div>;
}

export default function ExecutiveReportModule({ user, headers }) {
  const [summary, setSummary] = useState(null);
  const [kpiComparison, setKpiComparison] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedYear, setSelectedYear] = useState(String(new Date().getFullYear()));
  const [selectedMonth, setSelectedMonth] = useState(String(new Date().getMonth() + 1));
  const [trendMonths, setTrendMonths] = useState('6');
  const [activeSection, setActiveSection] = useState('summary');
  const [aiNarrative, setAiNarrative] = useState('');
  const [aiMeta, setAiMeta] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const { toast } = useToast();
  const authH = useMemo(() => headers || {}, [headers]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = { year: parseInt(selectedYear), month: parseInt(selectedMonth) };
      const [sumRes, cmpRes, trendRes] = await Promise.all([
        axios.get(`${API}/api/reports/executive/summary`, { headers: authH, params }),
        axios.get(`${API}/api/reports/executive/kpi-comparison`, { headers: authH, params: { months: 6 } }),
        axios.get(`${API}/api/reports/executive/trend`, { headers: authH, params: { months: parseInt(trendMonths) } }),
      ]);
      setSummary(sumRes.data);
      setKpiComparison(cmpRes.data?.data || []);
      setTrend(trendRes.data?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal load laporan', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedMonth, trendMonths, authH, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const generateNarrative = useCallback(async (refresh = false) => {
    setAiLoading(true);
    try {
      const params = { year: parseInt(selectedYear), month: parseInt(selectedMonth), refresh };
      const res = await axios.get(`${API}/api/reports/executive/ai-narrative`, { headers: authH, params });
      if (res.data?.ok) {
        setAiNarrative(res.data.narrative || '');
        setAiMeta({ cache_hit: res.data.cache_hit, generated_at: res.data.generated_at });
        if (refresh) toast({ title: 'Analisis AI diperbarui' });
      } else {
        toast({ title: 'AI tidak tersedia', description: res.data?.error || 'Gagal generate', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal generate analisis AI', variant: 'destructive' });
    } finally {
      setAiLoading(false);
    }
  }, [selectedYear, selectedMonth, authH, toast]);

  // Reset AI narrative saat periode berubah (hindari tampil data periode lain)
  useEffect(() => { setAiNarrative(''); setAiMeta(null); }, [selectedYear, selectedMonth]);

  const fin = summary?.finance || {};
  const prod = summary?.production || {};
  const hr = summary?.hr || {};
  const mkt = summary?.marketing || {};

  const MONTHS = [
    { v: '1', l: 'Januari' }, { v: '2', l: 'Februari' }, { v: '3', l: 'Maret' },
    { v: '4', l: 'April' }, { v: '5', l: 'Mei' }, { v: '6', l: 'Juni' },
    { v: '7', l: 'Juli' }, { v: '8', l: 'Agustus' }, { v: '9', l: 'September' },
    { v: '10', l: 'Oktober' }, { v: '11', l: 'November' }, { v: '12', l: 'Desember' },
  ];
  const CY = new Date().getFullYear();
  const YEARS = [String(CY - 1), String(CY)];

  const SECTIONS = [
    { id: 'summary',    label: 'Executive Summary' },
    { id: 'ai',         label: 'Analisis AI' },
    { id: 'finance',    label: 'Keuangan' },
    { id: 'production', label: 'Produksi' },
    { id: 'hr',         label: 'SDM' },
    { id: 'trend',      label: 'Trend Multi-KPI' },
  ];

  return (
    <div className="p-4 md:p-6 space-y-5 text-foreground">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="text-indigo-600 dark:text-indigo-400" /> Executive Report Hub
          </h2>
          <p className="text-sm text-muted-foreground/60 dark:text-zinc-400 mt-1">Laporan konsolidat cross-module untuk manajemen</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Select value={selectedMonth} onValueChange={setSelectedMonth}>
            <SelectTrigger className="w-32 bg-card border-border text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {MONTHS.map(m => <SelectItem key={m.v} value={m.v}>{m.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={selectedYear} onValueChange={setSelectedYear}>
            <SelectTrigger className="w-24 bg-card border-border text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {YEARS.map(y => <SelectItem key={y} value={y}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}
            className="border-border text-foreground/80 hover:bg-muted" data-testid="btn-refresh-exec">
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* Period label */}
      {summary && (
        <div className="text-sm text-muted-foreground/60 dark:text-zinc-400">
          Laporan periode: <span className="text-foreground font-medium">{summary.period?.label}</span>
          <span className="text-muted-foreground/60 ml-2">({summary.period?.range?.from} s/d {summary.period?.range?.to})</span>
        </div>
      )}

      {/* Sections nav */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {SECTIONS.map(s => (
          <button key={s.id} onClick={() => setActiveSection(s.id)}
            className={`px-4 py-2 text-sm whitespace-nowrap transition-colors ${
              activeSection === s.id
                ? 'text-foreground border-b-2 border-indigo-500'
                : 'text-muted-foreground/60 dark:text-zinc-400 hover:text-foreground'
            }`}
            data-testid={`tab-exec-${s.id}`}>{s.label}</button>
        ))}
      </div>

      {/* AI Analysis Section (WS-B a) */}
      {activeSection === 'ai' && (
        <div className="space-y-4">
          <Card className="border-indigo-200 dark:border-indigo-900 bg-indigo-50/40 dark:bg-indigo-950/20">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                  <div>
                    <p className="text-sm font-semibold text-foreground">Analisis Eksekutif AI</p>
                    <p className="text-xs text-muted-foreground/70">Ringkasan naratif &amp; rekomendasi strategis (model executive). Periode {selectedMonth}/{selectedYear}.</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {aiMeta?.generated_at && (
                    <span className="text-[11px] text-muted-foreground/70" data-testid="exec-ai-meta">
                      {aiMeta.cache_hit ? 'cache' : 'baru'} · {new Date(aiMeta.generated_at).toLocaleString('id-ID')}
                    </span>
                  )}
                  <Button size="sm" onClick={() => generateNarrative(!!aiNarrative)} disabled={aiLoading}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white" data-testid="btn-generate-exec-ai">
                    {aiLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Sparkles className="w-4 h-4 mr-1" />}
                    {aiLoading ? 'Menganalisis…' : (aiNarrative ? 'Regenerate' : 'Generate Analisis')}
                  </Button>
                </div>
              </div>

              {aiLoading && !aiNarrative && (
                <div className="space-y-2 animate-pulse" data-testid="exec-ai-loading">
                  <div className="h-4 bg-muted rounded w-1/3" />
                  <div className="h-3 bg-muted rounded w-full" />
                  <div className="h-3 bg-muted rounded w-5/6" />
                  <div className="h-3 bg-muted rounded w-4/6" />
                  <div className="h-3 bg-muted rounded w-3/6" />
                </div>
              )}

              {!aiLoading && !aiNarrative && (
                <div className="text-center py-8 text-sm text-muted-foreground/70" data-testid="exec-ai-empty">
                  Klik <strong className="text-foreground">Generate Analisis</strong> untuk membuat ringkasan eksekutif berbasis AI dari KPI periode ini.
                </div>
              )}

              {aiNarrative && (
                <div className="bg-card border border-border rounded-lg p-4" data-testid="exec-ai-narrative">
                  <MarkdownLite text={aiNarrative} />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Summary Section */}
      {activeSection === 'summary' && (
        <div className="space-y-5">
          {/* Revenue headline */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon={DollarSign} iconColor="text-emerald-600 dark:text-emerald-400" label="Revenue Bulan Ini"
              value={loading ? '…' : FMT_IDR(fin.revenue_rp)}
              sub={`${fin.invoice_count || 0} invoice`}
              delta={fin.revenue_delta_vs_prev_pct} />
            <KpiCard icon={TrendingUp} iconColor="text-blue-600 dark:text-blue-400" label="Net Income"
              value={loading ? '…' : FMT_IDR(fin.net_income_rp)}
              sub={`Margin ${FMT_PCT(fin.profit_margin_pct)}`} />
            <KpiCard icon={Factory} iconColor="text-orange-600 dark:text-orange-400" label="WO Selesai"
              value={loading ? '…' : FMT_NUM(prod.completed_wo)}
              sub={`dari ${prod.total_wo || 0} total`} />
            <KpiCard icon={Users} iconColor="text-purple-600 dark:text-purple-400" label="Karyawan Aktif"
              value={loading ? '…' : FMT_NUM(hr.total_active_employees)}
              sub={`Absen ${hr.absent_count || 0} hari ini`} />
          </div>

          {/* Domain rows */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Finance */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> Keuangan
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {[
                  ['Revenue', FMT_IDR(fin.revenue_rp)],
                  ['Revenue Terbayar', FMT_IDR(fin.paid_revenue_rp)],
                  ['Total Biaya', FMT_IDR(fin.total_expenses_rp)],
                  ['Net Income', FMT_IDR(fin.net_income_rp)],
                  ['AR Overdue', `${FMT_IDR(fin.ar_overdue_rp)} (${fin.ar_overdue_count || 0} inv)`],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">{k}</span>
                    <span className="text-foreground">{loading ? '…' : v}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Production */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
                  <Factory className="w-4 h-4 text-orange-600 dark:text-orange-400" /> Produksi
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {[
                  ['Total WO', FMT_NUM(prod.total_wo)],
                  ['WO Selesai', `${prod.completed_wo} (${FMT_PCT(prod.completion_rate_pct)})`],
                  ['WO Aktif', FMT_NUM(prod.active_wo)],
                  ['Qty Ordered', FMT_NUM(prod.total_qty_ordered)],
                  ['Defect Rate', FMT_PCT(prod.defect_rate_pct)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">{k}</span>
                    <span className="text-foreground">{loading ? '…' : v}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* HR */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
                  <Users className="w-4 h-4 text-purple-600 dark:text-purple-400" /> SDM
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {[
                  ['Karyawan Aktif', FMT_NUM(hr.total_active_employees)],
                  ['Karyawan Baru', FMT_NUM(hr.new_hires)],
                  ['Attendance Rate', FMT_PCT(hr.attendance_rate_pct)],
                  ['Overtime Jam', `${hr.overtime_hours || 0} jam`],
                  ['Total Payroll', FMT_IDR(hr.payroll_total_rp)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">{k}</span>
                    <span className="text-foreground">{loading ? '…' : v}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Marketing */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-700 dark:text-amber-400" /> Marketing
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {[
                  ['Live Sessions', FMT_NUM(mkt.live_sessions)],
                  ['Revenue Live', FMT_IDR(mkt.live_revenue_rp)],
                  ['Live Orders', FMT_NUM(mkt.live_orders)],
                  ['Marketplace Orders', FMT_NUM(mkt.marketplace_orders_via_webhook)],
                  /* F10 — menggantikan metrik mati "kampanye KOL" (koleksi yang tak
                     pernah ditulis ⇒ selalu 0). Sumbernya kini kalender konten F7. */
                  ['Konten Terbit', FMT_NUM(mkt.content_posted)],
                  ['Kreator Aktif', FMT_NUM(mkt.active_creators)],
                  ['GMV KPI Konten*', FMT_IDR(mkt.content_gmv_kpi_rp)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">{k}</span>
                    <span className="text-foreground">{loading ? '…' : v}</span>
                  </div>
                ))}
                <p className="text-[10px] text-muted-foreground pt-1 border-t border-border">
                  *GMV KPI Konten adalah angka <strong>platform</strong> per konten —
                  jangan dijumlah dengan omzet pesanan (menghitung satu penjualan dua kali).
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Finance Section */}
      {activeSection === 'finance' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard icon={DollarSign} iconColor="text-emerald-600 dark:text-emerald-400" label="Revenue"
              value={loading ? '…' : FMT_IDR(fin.revenue_rp)}
              sub={`${fin.invoice_count || 0} invoice`}
              delta={fin.revenue_delta_vs_prev_pct} />
            <KpiCard icon={TrendingUp} iconColor="text-blue-600 dark:text-blue-400" label="Net Income"
              value={loading ? '…' : FMT_IDR(fin.net_income_rp)}
              sub={`${FMT_PCT(fin.profit_margin_pct)} margin`} />
            <KpiCard icon={TrendingDown} iconColor="text-red-700 dark:text-red-400" label="AR Overdue"
              value={loading ? '…' : FMT_IDR(fin.ar_overdue_rp)}
              sub={`${fin.ar_overdue_count || 0} invoice`} invertDelta />
          </div>
          {/* KPI Comparison Table */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-foreground/80">Perbandingan 6 Bulan</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground/60 dark:text-zinc-400">
                    <th className="text-left px-4 py-2">Periode</th>
                    <th className="text-right px-4 py-2">Revenue</th>
                    <th className="text-right px-4 py-2">Net Income</th>
                    <th className="text-right px-4 py-2">AR Overdue</th>
                    <th className="text-right px-4 py-2">WO Selesai</th>
                  </tr>
                </thead>
                <tbody>
                  {kpiComparison.map(r => (
                    <tr key={r.period} className="border-b border-border/40">
                      <td className="px-4 py-2 text-foreground/80">{r.period}</td>
                      <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">{FMT_IDR(r.revenue_rp)}</td>
                      <td className="px-4 py-2 text-right text-blue-600 dark:text-blue-400">{FMT_IDR(r.net_income_rp)}</td>
                      <td className="px-4 py-2 text-right text-red-700 dark:text-red-400">{FMT_IDR(r.ar_overdue_rp)}</td>
                      <td className="px-4 py-2 text-right text-foreground/80">{r.wo_completed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Production Section */}
      {activeSection === 'production' && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { label: 'Total WO', value: FMT_NUM(prod.total_wo), icon: Factory, color: 'text-orange-600 dark:text-orange-400' },
            { label: 'WO Selesai', value: `${prod.completed_wo} (${FMT_PCT(prod.completion_rate_pct)})`, icon: Factory, color: 'text-emerald-600 dark:text-emerald-400' },
            { label: 'WO Aktif', value: FMT_NUM(prod.active_wo), icon: Factory, color: 'text-blue-600 dark:text-blue-400' },
            { label: 'Qty Ordered', value: FMT_NUM(prod.total_qty_ordered), icon: BarChart3, color: 'text-muted-foreground/60 dark:text-zinc-400' },
            { label: 'Qty Selesai', value: `${FMT_NUM(prod.total_qty_completed)} (${FMT_PCT(prod.fulfillment_rate_pct)})`, icon: BarChart3, color: 'text-emerald-600 dark:text-emerald-400' },
            { label: 'Defect Rate', value: FMT_PCT(prod.defect_rate_pct), icon: TrendingDown, color: prod.defect_rate_pct > 2 ? 'text-red-700 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <KpiCard key={label} icon={Icon} iconColor={color} label={label} value={loading ? '…' : value} />
          ))}
        </div>
      )}

      {/* HR Section */}
      {activeSection === 'hr' && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { label: 'Karyawan Aktif', value: FMT_NUM(hr.total_active_employees), icon: Users, color: 'text-purple-600 dark:text-purple-400' },
            { label: 'Karyawan Baru', value: FMT_NUM(hr.new_hires), icon: Users, color: 'text-blue-600 dark:text-blue-400' },
            { label: 'Attendance Rate', value: FMT_PCT(hr.attendance_rate_pct), icon: TrendingUp, color: hr.attendance_rate_pct < 90 ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400' },
            { label: 'Absen (hari ini)', value: FMT_NUM(hr.absent_count), icon: Users, color: 'text-red-700 dark:text-red-400' },
            { label: 'Overtime Hours', value: `${hr.overtime_hours || 0} jam`, icon: TrendingUp, color: 'text-muted-foreground/60 dark:text-zinc-400' },
            { label: 'Total Payroll', value: FMT_IDR(hr.payroll_total_rp), icon: DollarSign, color: 'text-emerald-600 dark:text-emerald-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <KpiCard key={label} icon={Icon} iconColor={color} label={label} value={loading ? '…' : value} />
          ))}
        </div>
      )}

      {/* Trend Section */}
      {activeSection === 'trend' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground/60 dark:text-zinc-400">Periode:</label>
            <Select value={trendMonths} onValueChange={setTrendMonths}>
              <SelectTrigger className="w-24 bg-card border-border text-xs h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-card border-border">
                <SelectItem value="3">3 Bulan</SelectItem>
                <SelectItem value="6">6 Bulan</SelectItem>
                <SelectItem value="12">12 Bulan</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-foreground/80">Revenue vs Net Income Trend</CardTitle>
            </CardHeader>
            <CardContent>
              <TrendChart data={trend} keys={['revenue_rp', 'net_income_rp']} />
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-foreground/80">Data Trend</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground/60 dark:text-zinc-400">
                    <th className="text-left px-4 py-2">Periode</th>
                    <th className="text-right px-4 py-2">Revenue</th>
                    <th className="text-right px-4 py-2">Net Income</th>
                    <th className="text-right px-4 py-2">AR Overdue</th>
                    <th className="text-right px-4 py-2">Attd%</th>
                    <th className="text-right px-4 py-2">Payroll</th>
                  </tr>
                </thead>
                <tbody>
                  {trend.map(r => (
                    <tr key={r.period} className="border-b border-border/40">
                      <td className="px-4 py-2 text-foreground/80">{r.period}</td>
                      <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">{FMT_IDR(r.revenue_rp)}</td>
                      <td className="px-4 py-2 text-right text-blue-600 dark:text-blue-400">{FMT_IDR(r.net_income_rp)}</td>
                      <td className="px-4 py-2 text-right text-red-700 dark:text-red-400">{FMT_IDR(r.ar_overdue_rp)}</td>
                      <td className="px-4 py-2 text-right text-foreground/80">{FMT_PCT(r.attendance_rate_pct)}</td>
                      <td className="px-4 py-2 text-right text-purple-600 dark:text-purple-400">{FMT_IDR(r.payroll_total_rp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
