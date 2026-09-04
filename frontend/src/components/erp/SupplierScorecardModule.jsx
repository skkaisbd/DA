/**
 * SupplierScorecardModule — Penilaian Supplier (Portal Pengadaan)
 *
 * 2026-08-06 — DIPINDAH KE SSOT MASTER SUPPLIER.
 * Sebelumnya modul ini memanggil `/api/rahaza/grn-qc/supplier-scorecard` yang
 * MENGELOMPOKKAN BERDASARKAN TEKS `supplier_name`. Akibat nyatanya: satu
 * perusahaan yang ditulis "PT. Benang Jaya" dan "PT Benang Jaya" muncul sebagai
 * DUA baris dengan nilai terbelah — penilaian supplier jadi tidak bisa dipakai
 * untuk keputusan (user story 5 Phase 2).
 *
 * Sekarang memakai:
 *   · GET /api/procurement/supplier-scorecard          → dikelompokkan `supplier_id`
 *   · GET /api/procurement/suppliers/{id}/scorecard     → detail (tren, alasan
 *     reject, inspeksi terbaru, rekap PO) termasuk riwayat ejaan nama lama.
 * Baris yang BELUM tertaut master ditandai jelas + diarahkan ke migrasi, bukan
 * disembunyikan, supaya data lama tidak "hilang diam-diam".
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Shield, ShieldCheck, ShieldAlert, ShieldX, Search, RefreshCw,
  Award, Calendar, BarChart3, Target,
  Calculator, Package, AlertCircle, CheckCircle2, XCircle,
  ChevronRight, Activity, Users, Building2, Link2Off, Clock, FileText,
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const GRADE_STYLE = {
  'A+': { bg: 'bg-emerald-500/15', border: 'border-emerald-400/40', text: 'text-emerald-600 dark:text-emerald-300', icon: ShieldCheck, label: 'Sangat Baik' },
  'A':  { bg: 'bg-emerald-500/10', border: 'border-emerald-400/30', text: 'text-emerald-600 dark:text-emerald-300', icon: ShieldCheck, label: 'Baik' },
  'B':  { bg: 'bg-blue-500/10',    border: 'border-blue-400/30',    text: 'text-blue-600 dark:text-blue-300',       icon: Shield,      label: 'Cukup' },
  'C':  { bg: 'bg-amber-500/10',   border: 'border-amber-400/30',   text: 'text-amber-600 dark:text-amber-300',     icon: ShieldAlert, label: 'Di Bawah Target' },
  'D':  { bg: 'bg-rose-500/10',    border: 'border-rose-400/30',    text: 'text-rose-600 dark:text-rose-300',       icon: ShieldX,     label: 'Kritis' },
  '-':  { bg: 'bg-foreground/5',   border: 'border-foreground/15',  text: 'text-muted-foreground',                  icon: Shield,      label: 'Belum dinilai' },
};

const SEVERITY_BADGE = {
  critical: 'text-rose-600 dark:text-rose-300 border-rose-300/40 bg-rose-500/10',
  major:    'text-amber-600 dark:text-amber-300 border-amber-300/40 bg-amber-500/10',
  minor:    'text-blue-600 dark:text-blue-300 border-blue-300/40 bg-blue-500/10',
};

const PO_STATUS_LABEL = {
  draft: 'Draf', pending_approval: 'Menunggu Persetujuan', approved: 'Disetujui',
  sent: 'Terkirim', partially_received: 'Diterima Sebagian', fully_received: 'Diterima Penuh',
  completed: 'Selesai', cancelled: 'Dibatalkan', rejected: 'Ditolak',
};

const num = (n, max = 2) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: max });
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 })}`;

export default function SupplierScorecardModule({ token, onNavigate }) {
  const { toast } = useToast();
  const [scorecards, setScorecards] = useState([]);
  const [summary, setSummary] = useState(null);
  const [periodDays, setPeriodDays] = useState(90);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState('scorecard');
  const [detailSupplier, setDetailSupplier] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // AQL Tool state
  const [aqlLot, setAqlLot] = useState(500);
  const [aqlValue, setAqlValue] = useState(2.5);
  const [aqlResult, setAqlResult] = useState(null);
  const [aqlLoading, setAqlLoading] = useState(false);

  const h = useMemo(() => ({
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }), [token]);

  const fetchScorecards = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const res = await fetch(`/api/procurement/supplier-scorecard?period_days=${periodDays}`, { headers: h });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setScorecards(Array.isArray(data?.items) ? data.items : []);
      setSummary(data?.summary || null);
    } catch (e) {
      setScorecards([]);
      setSummary(null);
      setLoadError(e.message);
      toast({ title: 'Gagal memuat penilaian supplier', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [h, periodDays, toast]);

  useEffect(() => { fetchScorecards(); }, [fetchScorecards]);

  const openDetail = async (row) => {
    if (!row.supplier_id) {
      toast({
        title: 'Supplier ini belum tertaut Master Supplier',
        description: 'Jalankan "Migrasi Data Lama" di modul Master Supplier agar riwayatnya menyatu.',
      });
      return;
    }
    setDetailSupplier(row);
    setDetailLoading(true);
    setDetailData(null);
    try {
      const res = await fetch(
        `/api/procurement/suppliers/${row.supplier_id}/scorecard?period_days=180`,
        { headers: h },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setDetailData(data);
    } catch (e) {
      toast({ title: 'Gagal memuat detail', description: e.message, variant: 'destructive' });
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAqlCalc = async () => {
    setAqlLoading(true);
    try {
      const res = await fetch('/api/rahaza/grn-qc/aql/calculate', {
        method: 'POST', headers: h,
        body: JSON.stringify({ lot_size: parseInt(aqlLot, 10), aql: parseFloat(aqlValue) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Perhitungan AQL gagal');
      setAqlResult(data);
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setAqlLoading(false);
    }
  };

  const filteredScorecards = useMemo(() => {
    if (!search) return scorecards;
    const q = search.toLowerCase();
    return scorecards.filter(s =>
      (s.supplier_name || '').toLowerCase().includes(q) ||
      (s.supplier_code || '').toLowerCase().includes(q));
  }, [scorecards, search]);
  const { page, setPage, totalPages, total, paged } = useClientPagination(filteredScorecards, 10);

  // KPIs
  const kpi = useMemo(() => {
    const totalSup = scorecards.length;
    const aGrade = scorecards.filter(s => s.quality_grade === 'A+' || s.quality_grade === 'A').length;
    const cdGrade = scorecards.filter(s => s.quality_grade === 'C' || s.quality_grade === 'D').length;
    const totalGRNs = scorecards.reduce((a, s) => a + (s.total_grns || 0), 0);
    const totalRejected = scorecards.reduce((a, s) => a + (s.total_rejected || 0), 0);
    const totalReceived = scorecards.reduce((a, s) => a + (s.total_received || 0), 0);
    const avgDefect = totalReceived > 0 ? (totalRejected / totalReceived * 100) : 0;
    const unlinked = summary?.unlinked ?? scorecards.filter(s => !s.linked).length;
    return { totalSup, aGrade, cdGrade, totalGRNs, avgDefect, unlinked };
  }, [scorecards, summary]);

  return (
    <div className="space-y-5" data-testid="supplier-scorecard-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Award className="w-6 h-6 text-amber-500" />
            Penilaian Supplier
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Performa supplier dari hasil inspeksi penerimaan barang — dikelompokkan per
            <strong> Master Supplier</strong>, jadi perbedaan penulisan nama tidak memecah nilai.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={String(periodDays)} onValueChange={v => setPeriodDays(parseInt(v, 10))}>
            <SelectTrigger className="w-36 h-8 text-xs" data-testid="period-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">30 hari terakhir</SelectItem>
              <SelectItem value="90">90 hari terakhir</SelectItem>
              <SelectItem value="180">180 hari terakhir</SelectItem>
              <SelectItem value="365">1 tahun terakhir</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="ghost" onClick={fetchScorecards} className="gap-1.5 text-xs" data-testid="scorecard-refresh-btn">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Muat Ulang</span>
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm"
             data-testid="scorecard-error">
          {loadError}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Supplier Dinilai</div>
          <div className="text-2xl font-bold text-foreground" data-testid="kpi-total-suppliers">{kpi.totalSup}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1 flex items-center justify-center gap-0.5">
            <ShieldCheck className="w-3 h-3 text-emerald-500" /> Grade A
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{kpi.aGrade}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1 flex items-center justify-center gap-0.5">
            <ShieldX className="w-3 h-3 text-rose-500" /> Grade C/D
          </div>
          <div className="text-2xl font-bold text-rose-600 dark:text-rose-400">{kpi.cdGrade}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total Inspeksi</div>
          <div className="text-2xl font-bold text-[hsl(var(--primary))]">{kpi.totalGRNs}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Rata-rata Cacat</div>
          <div className={`text-2xl font-bold ${kpi.avgDefect > 5 ? 'text-rose-500' : kpi.avgDefect > 2 ? 'text-amber-500' : 'text-emerald-600 dark:text-emerald-400'}`}>
            {kpi.avgDefect.toFixed(2)}%
          </div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1 flex items-center justify-center gap-0.5">
            <Link2Off className="w-3 h-3 text-amber-500" /> Tanpa Master
          </div>
          <div className={`text-2xl font-bold ${kpi.unlinked > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-foreground'}`}
               data-testid="kpi-unlinked">{kpi.unlinked}</div>
        </GlassPanel>
      </div>

      {kpi.unlinked > 0 && (
        <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-400/10 border border-amber-300 dark:border-amber-400/30 text-sm flex items-start gap-2"
             data-testid="scorecard-unlinked-hint">
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="text-amber-800 dark:text-amber-200">
            <strong>{kpi.unlinked} nama supplier</strong> pada riwayat inspeksi belum tertaut Master Supplier,
            sehingga nilainya berdiri sendiri.{' '}
            {onNavigate && (
              <button className="underline font-medium" onClick={() => onNavigate('proc-suppliers')}
                      data-testid="scorecard-goto-migration">
                Buka Master Supplier → Migrasi Data Lama
              </button>
            )}
          </div>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="scorecard" data-testid="tab-scorecard">
            <Award className="w-3.5 h-3.5 mr-1.5" /> Penilaian
          </TabsTrigger>
          <TabsTrigger value="aql" data-testid="tab-aql">
            <Calculator className="w-3.5 h-3.5 mr-1.5" /> Alat Sampling AQL
          </TabsTrigger>
        </TabsList>

        {/* ── SCORECARD TAB ── */}
        <TabsContent value="scorecard">
          <GlassCard className="p-0 overflow-hidden">
            <div className="flex items-center gap-3 p-3 border-b border-[var(--glass-border)]">
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <GlassInput
                  placeholder="Cari nama atau kode supplier…"
                  className="pl-8 h-8 text-sm"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  data-testid="scorecard-search"
                />
              </div>
              {summary && (
                <div className="text-xs text-muted-foreground hidden sm:block">
                  {summary.linked} tertaut master · rata-rata terima {num(summary.avg_accept_rate)}%
                </div>
              )}
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
              </div>
            ) : filteredScorecards.length === 0 ? (
              <div className="text-center py-16">
                <Users className="w-12 h-12 mx-auto text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground mb-1">
                  {scorecards.length === 0 ? 'Belum ada inspeksi penerimaan pada periode ini.' : 'Tidak ada supplier yang cocok.'}
                </p>
                {scorecards.length === 0 && (
                  <p className="text-xs text-muted-foreground/70">
                    Nilai muncul otomatis setelah barang diterima &amp; diinspeksi di
                    Portal Gudang → <strong>Penerimaan Barang</strong>.
                  </p>
                )}
              </div>
            ) : (
              <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[11px] text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
                      <th className="px-4 py-2.5 text-left font-medium">Supplier</th>
                      <th className="px-4 py-2.5 text-center font-medium">Grade</th>
                      <th className="px-4 py-2.5 text-right font-medium">Tingkat Terima</th>
                      <th className="px-4 py-2.5 text-right font-medium">Tingkat Cacat</th>
                      <th className="px-4 py-2.5 text-right font-medium">Tepat Waktu</th>
                      <th className="px-4 py-2.5 text-right font-medium">Inspeksi</th>
                      <th className="px-4 py-2.5 text-right font-medium">Diterima</th>
                      <th className="px-4 py-2.5 text-right font-medium">Ditolak</th>
                      <th className="px-4 py-2.5 text-center font-medium">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paged.map(s => {
                      const grade = GRADE_STYLE[s.quality_grade] || GRADE_STYLE['-'];
                      const GradeIcon = grade.icon;
                      const key = s.supplier_id || `unlinked-${s.supplier_name}`;
                      return (
                        <tr key={key}
                            className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]"
                            data-testid={`scorecard-row-${s.supplier_code || s.supplier_name}`}>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <Building2 className="w-4 h-4 text-muted-foreground shrink-0" />
                              <div className="min-w-0">
                                <div className="font-medium text-foreground truncate">{s.supplier_name}</div>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                  {s.supplier_code ? (
                                    <span className="text-[10px] font-mono text-muted-foreground">{s.supplier_code}</span>
                                  ) : null}
                                  {!s.linked && (
                                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-amber-600 dark:text-amber-300 border-amber-400/40 bg-amber-500/10 gap-0.5">
                                      <Link2Off className="w-2.5 h-2.5" /> belum tertaut master
                                    </Badge>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Badge variant="outline" className={`text-xs font-bold ${grade.bg} ${grade.border} ${grade.text} gap-1`}>
                              <GradeIcon className="w-3 h-3" />
                              {s.quality_grade}
                            </Badge>
                            <div className="text-[9px] text-muted-foreground mt-0.5">{grade.label}</div>
                          </td>
                          <td className={`px-4 py-3 text-right font-bold ${s.accept_rate >= 95 ? 'text-emerald-600 dark:text-emerald-400' : s.accept_rate >= 85 ? 'text-amber-600 dark:text-amber-400' : 'text-rose-600 dark:text-rose-400'}`}>
                            {num(s.accept_rate)}%
                          </td>
                          <td className={`px-4 py-3 text-right font-medium ${s.defect_rate <= 2 ? 'text-emerald-600 dark:text-emerald-400' : s.defect_rate <= 5 ? 'text-amber-600 dark:text-amber-400' : 'text-rose-600 dark:text-rose-400'}`}>
                            {num(s.defect_rate)}%
                          </td>
                          <td className="px-4 py-3 text-right text-foreground">
                            {s.on_time_rate == null ? (
                              <span className="text-muted-foreground text-xs">—</span>
                            ) : (
                              <span className={s.on_time_rate >= 90 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                                {num(s.on_time_rate)}%
                                <span className="text-[10px] text-muted-foreground ml-1">({s.on_time_samples})</span>
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right text-foreground font-mono">{s.total_grns}</td>
                          <td className="px-4 py-3 text-right text-emerald-600 dark:text-emerald-300 font-mono">{num(s.total_accepted)}</td>
                          <td className="px-4 py-3 text-right text-rose-600 dark:text-rose-300 font-mono">{num(s.total_rejected)}</td>
                          <td className="px-4 py-3 text-center">
                            <button
                              onClick={() => openDetail(s)}
                              className={`inline-flex items-center gap-0.5 text-xs ${s.supplier_id ? 'text-[hsl(var(--primary))] hover:brightness-110' : 'text-muted-foreground/60 cursor-not-allowed'}`}
                              data-testid={`scorecard-detail-${s.supplier_code || s.supplier_name}`}
                            >
                              Detail <ChevronRight className="w-3 h-3" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-4" />
              </>
            )}
          </GlassCard>
        </TabsContent>

        {/* ── AQL TAB ── */}
        <TabsContent value="aql">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Input */}
            <GlassCard className="p-5 lg:col-span-1">
              <h3 className="text-base font-semibold text-foreground mb-1 flex items-center gap-2">
                <Calculator className="w-4 h-4 text-[hsl(var(--primary))]" />
                Kalkulator Sampling AQL
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Hitung ukuran sample dan batas terima/tolak berdasarkan{' '}
                <strong>ANSI/ASQ Z1.4 General Inspection Level II</strong>.
              </p>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Ukuran Lot (Total Qty Diterima)</label>
                  <GlassInput
                    type="number" min="1"
                    value={aqlLot}
                    onChange={e => setAqlLot(e.target.value)}
                    placeholder="Contoh: 500"
                    data-testid="aql-lot-input"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">AQL (Batas Mutu yang Diterima %)</label>
                  <Select value={String(aqlValue)} onValueChange={v => setAqlValue(parseFloat(v))}>
                    <SelectTrigger data-testid="aql-value-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0.65">0.65% — Kritis</SelectItem>
                      <SelectItem value="1.0">1.0% — Mayor</SelectItem>
                      <SelectItem value="2.5">2.5% — Standar (disarankan)</SelectItem>
                      <SelectItem value="4.0">4.0% — Minor</SelectItem>
                      <SelectItem value="6.5">6.5% — Kosmetik</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  onClick={handleAqlCalc}
                  disabled={aqlLoading || !aqlLot || parseInt(aqlLot, 10) <= 0}
                  className="w-full gap-2"
                  data-testid="aql-calc-btn"
                >
                  {aqlLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Calculator className="w-4 h-4" />}
                  Hitung Rencana Sample
                </Button>
              </div>
            </GlassCard>

            {/* Result */}
            <GlassCard className="p-5 lg:col-span-2">
              <h3 className="text-base font-semibold text-foreground mb-4 flex items-center gap-2">
                <Target className="w-4 h-4 text-[hsl(var(--primary))]" />
                Hasil Rencana Sample
              </h3>
              {aqlResult ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Ukuran Lot</div>
                      <div className="text-2xl font-bold text-foreground mt-1">{Number(aqlResult.lot_size).toLocaleString('id-ID')}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-[hsl(var(--primary)/0.10)] border border-[hsl(var(--primary)/0.30)] text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Ukuran Sample</div>
                      <div className="text-2xl font-bold text-[hsl(var(--primary))] mt-1">{aqlResult.sample_size}</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">pcs untuk diperiksa</div>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-400/30 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase flex items-center justify-center gap-0.5">
                        <CheckCircle2 className="w-2.5 h-2.5" /> Terima
                      </div>
                      <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">≤ {aqlResult.accept_limit}</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">cacat → TERIMA</div>
                    </div>
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-400/30 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase flex items-center justify-center gap-0.5">
                        <XCircle className="w-2.5 h-2.5" /> Tolak
                      </div>
                      <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1">≥ {aqlResult.reject_limit}</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">cacat → TOLAK</div>
                    </div>
                  </div>

                  <GlassPanel className="p-3 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Kode Huruf:</span>
                      <span className="font-mono font-bold text-foreground">{aqlResult.code_letter}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Level AQL:</span>
                      <span className="font-bold text-foreground">{aqlResult.aql}%</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Level Inspeksi:</span>
                      <span className="text-foreground">{aqlResult.inspection_level}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Standar:</span>
                      <span className="text-foreground">{aqlResult.standard}</span>
                    </div>
                  </GlassPanel>

                  <div className="text-xs text-muted-foreground p-3 rounded-lg bg-blue-500/5 border border-blue-400/20 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-foreground">Cara pakai:</strong> Ambil acak{' '}
                      <strong className="text-[hsl(var(--primary))]">{aqlResult.sample_size} pcs</strong> dari lot{' '}
                      {Number(aqlResult.lot_size).toLocaleString('id-ID')} pcs, lalu periksa cacatnya. Bila ditemukan{' '}
                      <strong className="text-emerald-600 dark:text-emerald-300">≤ {aqlResult.accept_limit}</strong> cacat → terima
                      seluruh lot. Bila <strong className="text-rose-600 dark:text-rose-300">≥ {aqlResult.reject_limit}</strong>{' '}
                      cacat → tolak seluruh lot.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12">
                  <Calculator className="w-12 h-12 mx-auto text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground">
                    Masukkan ukuran lot lalu klik <strong>Hitung Rencana Sample</strong>.
                  </p>
                </div>
              )}
            </GlassCard>
          </div>
        </TabsContent>
      </Tabs>

      {/* Detail Modal */}
      {detailSupplier && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-0 md:p-4"
             onClick={() => setDetailSupplier(null)}>
          <div
            className="bg-[var(--card-surface)] border border-[var(--glass-border)] rounded-t-2xl md:rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
            onClick={e => e.stopPropagation()}
            data-testid="scorecard-detail-modal"
          >
            <div className="px-5 py-4 border-b border-[var(--glass-border)] flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-xs text-muted-foreground mb-1">Detail Penilaian Supplier (180 hari)</div>
                <div className="text-lg font-bold text-foreground flex items-center gap-2 min-w-0">
                  <Building2 className="w-5 h-5 text-[hsl(var(--primary))] shrink-0" />
                  <span className="truncate">{detailSupplier.supplier_name}</span>
                  {detailSupplier.supplier_code && (
                    <span className="text-xs font-mono text-muted-foreground shrink-0">{detailSupplier.supplier_code}</span>
                  )}
                </div>
              </div>
              <button onClick={() => setDetailSupplier(null)} className="text-muted-foreground hover:text-foreground p-1"
                      data-testid="scorecard-detail-close">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {detailLoading && (
                <div className="flex items-center justify-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
                </div>
              )}
              {!detailLoading && detailData?.scorecard && (
                <>
                  {/* Summary cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    <GlassPanel className="p-3 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Grade</div>
                      <div className={`text-xl font-bold ${(GRADE_STYLE[detailData.scorecard.quality_grade] || GRADE_STYLE['-']).text}`}>
                        {detailData.scorecard.quality_grade}
                      </div>
                    </GlassPanel>
                    <GlassPanel className="p-3 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Tingkat Terima</div>
                      <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{num(detailData.scorecard.accept_rate)}%</div>
                    </GlassPanel>
                    <GlassPanel className="p-3 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Tingkat Cacat</div>
                      <div className="text-xl font-bold text-rose-600 dark:text-rose-400">{num(detailData.scorecard.defect_rate)}%</div>
                    </GlassPanel>
                    <GlassPanel className="p-3 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase">Inspeksi</div>
                      <div className="text-xl font-bold text-foreground">{detailData.scorecard.total_grns}</div>
                    </GlassPanel>
                    <GlassPanel className="p-3 text-center">
                      <div className="text-[10px] text-muted-foreground uppercase flex items-center justify-center gap-0.5">
                        <Clock className="w-2.5 h-2.5" /> Tepat Waktu
                      </div>
                      <div className="text-xl font-bold text-foreground">
                        {detailData.scorecard.on_time_rate == null ? '—' : `${num(detailData.scorecard.on_time_rate)}%`}
                      </div>
                    </GlassPanel>
                  </div>

                  {/* Nama yang disatukan */}
                  {(detailData.name_variants_merged || []).length > 1 && (
                    <div className="p-3 rounded-lg bg-[hsl(var(--primary)/0.06)] border border-[hsl(var(--primary)/0.20)] text-xs"
                         data-testid="scorecard-name-variants">
                      <div className="font-medium text-foreground mb-1">Ejaan nama yang disatukan menjadi satu penilaian:</div>
                      <div className="flex flex-wrap gap-1.5">
                        {detailData.name_variants_merged.map(n => (
                          <span key={n} className="px-2 py-0.5 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)] text-muted-foreground">
                            {n}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* PO per status */}
                  {Object.keys(detailData.po_by_status || {}).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5">
                        <FileText className="w-4 h-4 text-[hsl(var(--primary))]" /> Purchase Order per Status
                      </h4>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                        {Object.entries(detailData.po_by_status).map(([st, v]) => (
                          <div key={st} className="px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                            <div className="text-[10px] text-muted-foreground">{PO_STATUS_LABEL[st] || st}</div>
                            <div className="text-sm font-semibold text-foreground">{v.count} PO</div>
                            <div className="text-[11px] text-muted-foreground tabular-nums">{rp(v.value)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Monthly trend */}
                  {(detailData.monthly_trend || []).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5">
                        <Activity className="w-4 h-4 text-[hsl(var(--primary))]" /> Tren Bulanan
                      </h4>
                      <div className="space-y-1.5">
                        {detailData.monthly_trend.map(m => (
                          <div key={m.month} className="flex items-center gap-3 text-xs px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                            <Calendar className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                            <div className="font-mono text-foreground w-16">{m.month}</div>
                            <div className="flex-1 flex items-center gap-2">
                              <div className="flex-1 h-2 rounded-full bg-[hsl(var(--muted)/0.7)] overflow-hidden">
                                <div
                                  className={`h-full transition-all ${m.accept_rate >= 95 ? 'bg-emerald-500' : m.accept_rate >= 85 ? 'bg-amber-500' : 'bg-rose-500'}`}
                                  style={{ width: `${Math.min(100, m.accept_rate)}%` }}
                                />
                              </div>
                              <div className="w-14 text-right font-bold text-foreground">{num(m.accept_rate)}%</div>
                            </div>
                            <div className="text-muted-foreground w-20 text-right">{m.grns} inspeksi</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Top reject reasons */}
                  {(detailData.top_reject_reasons || []).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5">
                        <ShieldAlert className="w-4 h-4 text-amber-500" /> Alasan Penolakan Terbanyak
                      </h4>
                      <div className="space-y-1.5">
                        {detailData.top_reject_reasons.map(r => (
                          <div key={r.code} className="flex items-center gap-3 text-xs px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                            <Badge variant="outline" className={`text-[10px] ${SEVERITY_BADGE[r.severity] || ''}`}>
                              {(r.severity || '').toUpperCase()}
                            </Badge>
                            <div className="flex-1 text-foreground">{r.label}</div>
                            <div className="font-mono font-bold text-rose-600 dark:text-rose-300">{num(r.total_qty)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recent inspections */}
                  {(detailData.recent_inspections || []).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5">
                        <Package className="w-4 h-4 text-[hsl(var(--primary))]" /> Inspeksi Terbaru
                      </h4>
                      <div className="space-y-1">
                        {detailData.recent_inspections.slice(0, 8).map(i => (
                          <div key={i.id} className="flex items-center gap-2 text-xs px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                            <div className="font-mono text-[hsl(var(--primary))]">{i.inspection_no || '—'}</div>
                            <div className="text-muted-foreground">·</div>
                            <div className="flex-1 text-foreground truncate">
                              {i.receipt_number || i.supplier_name_recorded || '—'}
                              {i.legacy_unlinked && (
                                <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-400">(riwayat lama)</span>
                              )}
                            </div>
                            <Badge variant="outline" className={`text-[10px] ${
                              i.overall_result === 'accepted' ? 'text-emerald-600 dark:text-emerald-300 border-emerald-300/30' :
                              i.overall_result === 'partial'  ? 'text-amber-600 dark:text-amber-300 border-amber-300/30' :
                              'text-rose-600 dark:text-rose-300 border-rose-300/30'
                            }`}>
                              {(i.overall_result || '-').toUpperCase()}
                            </Badge>
                            <span className="font-mono text-muted-foreground">{num(i.defect_rate)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {!detailLoading && detailData && !detailData.scorecard && (
                <div className="text-center py-12">
                  <BarChart3 className="w-12 h-12 mx-auto text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground">Tidak ada data inspeksi untuk supplier ini.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { SupplierScorecardModule };
