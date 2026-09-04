/**
 * CreatorScorecardView — **SCORECARD KREATOR** (F7.4 · F8): target vs pencapaian.
 *
 * Kenapa layar ini ada: target kreator (`marketing_creator_targets`) sudah bisa
 * ditetapkan, dan angka pencapaiannya ada di tiga tempat berbeda — tetapi tidak ada
 * satu layar pun yang mempertemukannya. Akibatnya rapat kreator memakai angka yang
 * dipilih manual oleh siapa pun yang membuat slide.
 *
 * Yang WAJIB terlihat di layar (bukan hanya di API):
 *   · tiga sumber uang DIPISAH: omzet pesanan · omzet sesi live · GMV KPI konten;
 *   · BASIS penilaian tertulis pada setiap baris (kolom “Basis”);
 *   · kreator tanpa target ditandai “belum ada target”, bukan 0%.
 *
 * DILENGKAPI 2026-08-14 (F8) — **angka yang bisa DITELUSURI**. Scorecard menjawab
 * “berapa”, tetapi angka yang dibantah di rapat selalu menuntut “dari mana”. Klik
 * satu baris ⇒ dialog rincian: konten mana yang membawa GMV itu, pesanan mana yang
 * dihitung (termasuk yang TIDAK dihitung beserta sebabnya), sesi mana yang dicatat
 * staf. Total rincian dijamin sama dengan baris scorecard (gate `INV-MKTOPS`).
 * Ditambah paginasi 10/hal (standar RC-UI-03) dan unduh CSV untuk bahan rapat.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, Loader2, Info, Target, AlertTriangle, Table2, LayoutGrid, Search,
  Download, X, ShoppingCart, Video, Radio,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import { MarketingAccountSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));
const MONTHS = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus',
  'September', 'Oktober', 'November', 'Desember'];
const BASIS_LABEL = {
  orders: 'Pesanan (SSOT uang)', sessions: 'Sesi live (input staf)',
  gmv_kpi: 'GMV KPI konten (platform)', none: 'Belum ada angka',
};
const STATUS_STYLE = {
  on_track: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
  warning: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
  behind: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30',
  no_target: 'bg-muted text-muted-foreground border-border',
};
const STATUS_LABEL = {
  on_track: 'On track', warning: 'Perlu dikejar', behind: 'Di bawah target',
  no_target: 'Belum ada target',
};
const HEADS = ['Kreator', 'Target omzet', 'Basis penilaian', 'Pencapaian', 'Omzet pesanan',
  'Retur', 'Pesanan setelah retur',
  'Omzet sesi', 'GMV KPI konten', 'Konten', 'Terbit', 'Cakupan KPI', 'Views',
  'Engagement', 'Sesi', 'Penonton', 'Status', 'Rincian'];

export default function CreatorScorecardView({ token, onNavigate }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [accountId, setAccountId] = useState('');
  const [view, setView] = useState('table');
  const [query, setQuery] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // F8 — rincian satu kreator (dari mana angkanya)
  const [detailOf, setDetailOf] = useState(null);      // baris scorecard
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailTab, setDetailTab] = useState('konten');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (accountId) qs.set('account_id', accountId);
      const res = await fetch(`${API}/api/marketing/targets/creator/scorecard?${qs}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      toast.error(`Gagal memuat scorecard kreator: ${e.message}`);
      setData(null);
    } finally { setLoading(false); }
  }, [year, month, accountId, token]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    setDetailOf(row);
    setDetail(null);
    setDetailTab('konten');
    setDetailLoading(true);
    try {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (accountId) qs.set('account_id', accountId);
      const res = await fetch(
        `${API}/api/marketing/targets/creator/${row.creator_id}/detail?${qs}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDetail(await res.json());
    } catch (e) {
      toast.error(`Gagal memuat rincian kreator: ${e.message}`);
      setDetail({ error: e.message });
    } finally { setDetailLoading(false); }
  };

  const rowsAll = data?.rows || [];
  const t = data?.totals || {};
  const noTarget = data?.creators_without_target || [];
  const rows = rowsAll.filter((r) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return `${r.creator_name} ${r.creator_code}`.toLowerCase().includes(q);
  });
  const pg = useClientPagination(rows, 10);

  /* Unduh CSV — bahan rapat. Sengaja memuat KETIGA angka uang sebagai kolom
     terpisah (tanpa kolom “total”) supaya berkas yang keluar dari sini tidak bisa
     dipakai menjumlahkan satu penjualan beberapa kali di spreadsheet. */
  const downloadCsv = () => {
    const head = ['Kreator', 'Kode', 'Target omzet', 'Basis penilaian', 'Pencapaian %',
      'Omzet pesanan (bruto)', 'Nilai retur', 'Pesanan retur',
      'Omzet pesanan setelah retur',
      'Omzet sesi live', 'GMV KPI konten', 'Konten', 'Terbit',
      'Cakupan KPI %', 'Views', 'Engagement', 'Sesi', 'Penonton', 'Status'];
    const lines = rows.map((r) => {
      const a = r.actual; const ach = r.achievement;
      return [r.creator_name, r.creator_code || '', r.target.revenue ?? '',
        BASIS_LABEL[ach.primary_basis] || ach.primary_basis, ach.primary_pct ?? '',
        a.order_revenue, a.order_revenue_returned, a.orders_returned,
        a.order_revenue_net_returns,
        a.session_revenue, a.gmv_kpi, a.contents, a.posted,
        a.kpi_coverage_pct, a.views, a.engagement, a.sessions, a.viewers,
        STATUS_LABEL[ach.status] || ach.status];
    });
    const csv = [head, ...lines]
      .map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `scorecard-kreator-${year}-${String(month).padStart(2, '0')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const gotoTarget = () => {
    if (typeof onNavigate === 'function') onNavigate('marketing-targets');
    else window.location.hash = 'marketing-targets';
  };

  return (
    <div className="space-y-4" data-testid="creator-scorecard-view">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="text-[11px] text-muted-foreground block">Bulan</label>
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}
            data-testid="scorecard-month"
            className="h-9 rounded-md border border-border bg-background text-foreground px-2 text-xs">
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block">Tahun</label>
          <input type="number" value={year} min={2020} max={2100}
            onChange={(e) => setYear(Number(e.target.value))} data-testid="scorecard-year"
            className="h-9 w-24 rounded-md border border-border bg-background text-foreground px-2 text-xs" />
        </div>
        <MarketingAccountSelect token={token} value={accountId} onChange={setAccountId}
          includeAll allLabel="Semua Toko" required={false} label="Toko"
          testId="scorecard-account-select" className="min-w-[220px]" />
        <div className="relative min-w-[180px]">
          <label className="text-[11px] text-muted-foreground block">Cari kreator</label>
          <Search size={13} className="absolute left-2.5 top-[30px] text-muted-foreground" />
          <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="nama atau kode…" data-testid="scorecard-search"
            className="h-9 w-full pl-8 pr-2 rounded-md border border-border bg-background
              text-foreground text-xs placeholder:text-muted-foreground focus:outline-none
              focus:ring-2 focus:ring-primary" />
        </div>
        <div className="flex rounded-md border border-border overflow-hidden ml-auto">
          <button type="button" onClick={() => setView('table')} data-testid="scorecard-view-table"
            className={`px-2 py-2 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="scorecard-view-grid"
            className={`px-2 py-2 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
        <Button size="sm" variant="outline" className="h-9" onClick={downloadCsv}
          disabled={!rows.length} data-testid="scorecard-export-csv">
          <Download size={13} className="mr-1.5" /> CSV
        </Button>
        <Button size="sm" variant="outline" className="h-9" onClick={load} disabled={loading}
          data-testid="scorecard-refresh">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3" data-testid="scorecard-kpi">
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Target omzet</p>
          <p className="text-base font-bold">{fmtRp(t.revenue_target)}</p>
          <p className="text-[10px] text-muted-foreground">{rowsAll.length} kreator</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Omzet pesanan</p>
          <p className="text-base font-bold">{fmtRp(t.order_revenue)}</p>
          <p className="text-[10px] text-muted-foreground">
            {t.revenue_pct_orders == null ? 'tanpa target' : `${t.revenue_pct_orders}% target`}</p>
          {/* SESI #9 — angka kedua yang diminta pemilik, TIDAK menggantikan bruto */}
          <p className="text-[10px] text-muted-foreground" data-testid="scorecard-kpi-returns">
            {(t.orders_returned || 0) > 0
              ? <>setelah retur <b>{fmtRp(t.order_revenue_net_returns)}</b> · retur {fmtNum(t.orders_returned)} pesanan ({fmtRp(t.order_revenue_returned)})</>
              : 'tidak ada pesanan retur'}
          </p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Omzet sesi live</p>
          <p className="text-base font-bold">{fmtRp(t.session_revenue)}</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">GMV KPI konten</p>
          <p className="text-base font-bold">{fmtRp(t.gmv_kpi)}</p>
          <p className="text-[10px] text-muted-foreground">cakupan KPI {t.kpi_coverage_pct || 0}%</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Konten</p>
          <p className="text-base font-bold">{fmtNum(t.contents)}</p>
          <p className="text-[10px] text-muted-foreground">{fmtNum(t.posted)} terbit</p></GlassCard>
      </div>

      {noTarget.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3"
          data-testid="scorecard-no-target">
          <p className="text-xs font-semibold flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
            <AlertTriangle size={12} /> {noTarget.length} kreator belum punya target {MONTHS[month - 1]} {year}
          </p>
          <p className="text-[11px] text-muted-foreground mt-1">
            {noTarget.slice(0, 8).join(' · ')}{noTarget.length > 8 ? ' …' : ''} — pencapaiannya
            ditandai “belum ada target”, bukan 0%.
          </p>
          <Button size="sm" variant="outline" className="h-7 mt-2 text-[11px]"
            onClick={gotoTarget} data-testid="scorecard-goto-target">
            <Target size={11} className="mr-1" /> Tetapkan target kreator
          </Button>
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-muted-foreground text-sm">
          <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Menghitung pencapaian kreator…
        </div>
      ) : !rows.length ? (
        <div className="py-10 text-center text-muted-foreground text-sm" data-testid="scorecard-empty">
          {rowsAll.length === 0
            ? 'Belum ada kreator yang bisa dinilai pada bulan ini.'
            : `Tidak ada kreator yang cocok dengan “${query}”.`}
        </div>
      ) : view === 'table' ? (
        <div className="rounded-lg border border-border overflow-x-auto bg-background">
          <table className="w-full text-xs" data-testid="scorecard-table">
            <thead className="bg-muted/60"><tr>{HEADS.map((h) => (
              <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
            ))}</tr></thead>
            <tbody className="divide-y">
              {pg.paged.map((r) => {
                const a = r.actual; const ach = r.achievement;
                return (
                  <tr key={r.creator_id} className="hover:bg-muted/30"
                    data-testid={`scorecard-row-${r.creator_id}`}>
                    <td className="px-2.5 py-2">
                      <div className="font-semibold text-foreground">{r.creator_name}</div>
                      {r.creator_code ? (
                        <div className="text-[10px] text-muted-foreground">{r.creator_code}</div>
                      ) : null}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {r.target.revenue == null ? <span className="text-muted-foreground">—</span>
                        : fmtRp(r.target.revenue)}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap text-muted-foreground">
                      {BASIS_LABEL[ach.primary_basis]}
                    </td>
                    <td className="px-2.5 py-2 min-w-[110px]">
                      {ach.primary_pct == null ? <span className="text-muted-foreground">—</span> : (
                        <div className="space-y-1">
                          <span className="font-semibold">{ach.primary_pct}%</span>
                          <Progress value={Math.min(100, ach.primary_pct)} className="h-1.5" />
                        </div>
                      )}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap font-semibold">{fmtRp(a.order_revenue)}</td>
                    {/* SESI #9 — retur & omzet pesanan setelah retur */}
                    <td className="px-2.5 py-2 whitespace-nowrap"
                      data-testid={`scorecard-returned-${r.creator_id}`}>
                      {(a.orders_returned || 0) > 0
                        ? <span className="text-amber-700 dark:text-amber-300">
                          {fmtRp(a.order_revenue_returned)}
                          <span className="text-[10px] text-muted-foreground"> · {fmtNum(a.orders_returned)} pesanan</span>
                        </span>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap font-semibold"
                      data-testid={`scorecard-net-${r.creator_id}`}>
                      {fmtRp(a.order_revenue_net_returns)}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(a.session_revenue)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(a.gmv_kpi)}</td>
                    <td className="px-2.5 py-2">{fmtNum(a.contents)}</td>
                    <td className="px-2.5 py-2">{fmtNum(a.posted)}</td>
                    <td className="px-2.5 py-2">
                      <span className={a.kpi_coverage_pct >= 80 ? 'text-emerald-600' : 'text-amber-600'}>
                        {Number(a.kpi_coverage_pct || 0).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-2.5 py-2">{fmtNum(a.views)}</td>
                    <td className="px-2.5 py-2">{fmtNum(a.engagement)}</td>
                    <td className="px-2.5 py-2">{fmtNum(a.sessions)}</td>
                    <td className="px-2.5 py-2">{fmtNum(a.viewers)}</td>
                    <td className="px-2.5 py-2">
                      <Badge variant="outline" className={`text-[9px] ${STATUS_STYLE[ach.status]}`}>
                        {STATUS_LABEL[ach.status]}
                      </Badge>
                    </td>
                    <td className="px-2.5 py-2">
                      <Button size="sm" variant="outline" className="h-7 text-[11px]"
                        onClick={() => openDetail(r)}
                        data-testid={`scorecard-detail-btn-${r.creator_id}`}>
                        Lihat asalnya
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
            pageSize={pg.pageSize} onPageChange={pg.setPage} />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="scorecard-grid">
          {pg.paged.map((r) => {
            const a = r.actual; const ach = r.achievement;
            return (
              <Card key={r.creator_id} data-testid={`scorecard-card-${r.creator_id}`}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-sm flex items-center gap-1.5">
                      <Target size={13} className="text-primary" /> {r.creator_name}
                    </CardTitle>
                    <Badge variant="outline" className={`text-[9px] ${STATUS_STYLE[ach.status]}`}>
                      {STATUS_LABEL[ach.status]}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between"><span className="text-muted-foreground">Target</span>
                    <span>{r.target.revenue == null ? '—' : fmtRp(r.target.revenue)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Basis</span>
                    <span>{BASIS_LABEL[ach.primary_basis]}</span></div>
                  {ach.primary_pct != null && (
                    <Progress value={Math.min(100, ach.primary_pct)} className="h-1.5" />
                  )}
                  <div className="flex justify-between"><span className="text-muted-foreground">Omzet pesanan</span>
                    <span className="font-semibold">{fmtRp(a.order_revenue)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Setelah retur</span>
                    <span className="font-semibold">
                      {fmtRp(a.order_revenue_net_returns)}
                      {(a.orders_returned || 0) > 0 && (
                        <span className="text-[10px] text-amber-700 dark:text-amber-300">
                          {' '}(retur {fmtNum(a.orders_returned)})
                        </span>
                      )}
                    </span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Omzet sesi</span>
                    <span>{fmtRp(a.session_revenue)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">GMV KPI konten</span>
                    <span>{fmtRp(a.gmv_kpi)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Konten / terbit</span>
                    <span>{fmtNum(a.contents)} / {fmtNum(a.posted)}</span></div>
                  <Button size="sm" variant="outline" className="h-7 w-full mt-1 text-[11px]"
                    onClick={() => openDetail(r)}
                    data-testid={`scorecard-detail-card-btn-${r.creator_id}`}>
                    Lihat asal angkanya
                  </Button>
                </CardContent>
              </Card>
            );
          })}
          <div className="sm:col-span-2 xl:col-span-3">
            <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
              pageSize={pg.pageSize} onPageChange={pg.setPage} />
          </div>
        </div>
      )}

      {(data?.data_notes || []).length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="scorecard-notes">
          <p className="text-xs font-semibold mb-1 flex items-center gap-1 text-foreground">
            <Info size={12} /> Catatan kejujuran data
          </p>
          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
            {(data.data_notes || []).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}

      {/* ══════ RINCIAN: DARI MANA ANGKA SATU BARIS BERASAL ══════ */}
      <Dialog open={Boolean(detailOf)}
        onOpenChange={(o) => { if (!o) { setDetailOf(null); setDetail(null); } }}>
        <DialogContent className="max-w-4xl" data-testid="scorecard-detail-dialog">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-1.5">
              <Target size={15} className="text-primary" />
              Rincian {detailOf?.creator_name} · {MONTHS[month - 1]} {year}
            </DialogTitle>
            <DialogDescription className="text-[11px]">
              Tiga daftar di bawah adalah TIGA SUMBER ANGKA yang berbeda dan <b>tidak
              dijumlah</b>. Totalnya sama dengan baris di tabel Scorecard.
            </DialogDescription>
          </DialogHeader>

          {detailLoading ? (
            <div className="py-10 text-center text-muted-foreground text-sm">
              <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Menelusuri asal angka…
            </div>
          ) : detail?.error ? (
            <p className="text-xs text-rose-600 dark:text-rose-400 py-6 text-center">
              {detail.error}
            </p>
          ) : detail ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="scorecard-detail-totals">
                {[['Omzet pesanan', fmtRp(detail.totals?.order_revenue),
                  `${detail.totals?.order_count || 0} pesanan dihitung`],
                ['Setelah retur', fmtRp(detail.totals?.order_revenue_net_returns),
                  `${detail.totals?.orders_returned_counted || 0} retur · ${fmtRp(detail.totals?.orders_returned_counted_revenue)}`],
                ['Omzet sesi live', fmtRp(detail.totals?.session_revenue),
                  `${detail.totals?.sessions || 0} sesi`],
                ['GMV KPI konten', fmtRp(detail.totals?.gmv_kpi),
                  `${detail.totals?.with_kpi || 0}/${detail.totals?.contents || 0} konten ber-KPI`],
                ['Target omzet', detail.target?.revenue == null ? '—'
                  : fmtRp(detail.target.revenue),
                detail.target?.has_target ? 'ditetapkan SPV' : 'belum ada target']]
                  .map(([l, v, s]) => (
                    <div key={l} className="rounded-md border border-border p-2">
                      <p className="text-[10px] text-muted-foreground">{l}</p>
                      <p className="text-sm font-bold text-foreground">{v}</p>
                      <p className="text-[10px] text-muted-foreground">{s}</p>
                    </div>
                  ))}
              </div>

              {(detail.data_notes || []).filter((n) => n.startsWith('PERLU KEPUTUSAN')).map((n, i) => (
                <p key={i} className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2
                  text-[11px] text-amber-800 dark:text-amber-200"
                  data-testid="scorecard-detail-decision">
                  <AlertTriangle size={11} className="inline mr-1" /> {n}
                </p>
              ))}

              <div className="flex flex-wrap gap-1.5">
                {[['konten', `Konten (${(detail.contents || []).length})`, Video],
                  ['pesanan', `Pesanan (${(detail.orders || []).length})`, ShoppingCart],
                  ['sesi', `Sesi live (${(detail.sessions || []).length})`, Radio]]
                  .map(([v, l, Icon]) => (
                    <button key={v} type="button" onClick={() => setDetailTab(v)}
                      data-testid={`scorecard-detail-tab-${v}`}
                      className={`px-2.5 py-1.5 rounded-md text-xs font-semibold border
                        flex items-center gap-1 ${detailTab === v
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-background text-foreground border-border hover:bg-muted/50'}`}>
                      <Icon size={11} /> {l}
                    </button>
                  ))}
              </div>

              <div className="rounded-md border border-border overflow-x-auto max-h-[46vh]">
                {detailTab === 'konten' && (
                  <table className="w-full text-[11px]" data-testid="scorecard-detail-contents">
                    <thead className="bg-muted/60 sticky top-0"><tr>
                      {['Tanggal', 'Judul', 'Jenis', 'Status', 'KPI', 'Views',
                        'Engagement', 'GMV KPI', 'Order (KPI)'].map((h) => (
                          <th key={h} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>
                        ))}
                    </tr></thead>
                    <tbody className="divide-y">
                      {(detail.contents || []).length === 0 ? (
                        <tr><td colSpan={9} className="px-2 py-4 text-center text-muted-foreground">
                          Tidak ada konten pada bulan ini.
                        </td></tr>
                      ) : detail.contents.map((c) => (
                        <tr key={c.id} className="hover:bg-muted/30">
                          <td className="px-2 py-1.5 whitespace-nowrap">{String(c.date || '').slice(0, 10)}</td>
                          <td className="px-2 py-1.5 max-w-[240px] truncate" title={c.title}>
                            {c.published_url ? (
                              <a href={c.published_url} target="_blank" rel="noreferrer"
                                className="text-primary hover:underline">{c.title}</a>
                            ) : c.title}
                          </td>
                          <td className="px-2 py-1.5">{c.content_type || '—'}</td>
                          <td className="px-2 py-1.5">{c.status || '—'}</td>
                          <td className="px-2 py-1.5">
                            {c.has_kpi
                              ? <Badge variant="outline" className="text-[9px] bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30">ada</Badge>
                              : <Badge variant="outline" className="text-[9px]">belum</Badge>}
                          </td>
                          <td className="px-2 py-1.5">{fmtNum(c.views)}</td>
                          <td className="px-2 py-1.5">{fmtNum(c.engagement)}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{fmtRp(c.gmv_kpi)}</td>
                          <td className="px-2 py-1.5">{fmtNum(c.orders)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {detailTab === 'pesanan' && (
                  <table className="w-full text-[11px]" data-testid="scorecard-detail-orders">
                    <thead className="bg-muted/60 sticky top-0"><tr>
                      {['No. Pesanan', 'Tanggal', 'Toko', 'Status', 'Omzet produk',
                        'Dihitung?'].map((h) => (
                          <th key={h} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>
                        ))}
                    </tr></thead>
                    <tbody className="divide-y">
                      {(detail.orders || []).length === 0 ? (
                        <tr><td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">
                          Tidak ada pesanan yang membawa kreator ini pada bulan ini.
                        </td></tr>
                      ) : detail.orders.map((o) => (
                        <tr key={o.id} className="hover:bg-muted/30">
                          <td className="px-2 py-1.5 font-mono">{o.order_id}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{String(o.order_date || '').slice(0, 10)}</td>
                          <td className="px-2 py-1.5">{o.account_name || '—'}</td>
                          <td className="px-2 py-1.5">{o.status}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{fmtRp(o.revenue_product)}</td>
                          <td className="px-2 py-1.5">
                            {o.counted ? (
                              <span className="text-emerald-700 dark:text-emerald-400">
                                ya{o.note ? ' · ' : ''}
                                {o.note ? <span className="text-amber-700 dark:text-amber-400">{o.note}</span> : null}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">tidak — {o.why_not_counted}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {detailTab === 'sesi' && (
                  <table className="w-full text-[11px]" data-testid="scorecard-detail-sessions">
                    <thead className="bg-muted/60 sticky top-0"><tr>
                      {['Tanggal', 'Sesi', 'Toko', 'Omzet sesi', 'Penonton', 'Puncak',
                        'Order', 'Durasi'].map((h) => (
                          <th key={h} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>
                        ))}
                    </tr></thead>
                    <tbody className="divide-y">
                      {(detail.sessions || []).length === 0 ? (
                        <tr><td colSpan={8} className="px-2 py-4 text-center text-muted-foreground">
                          Tidak ada sesi live yang dicatat untuk kreator ini.
                        </td></tr>
                      ) : detail.sessions.map((s) => (
                        <tr key={s.id} className="hover:bg-muted/30">
                          <td className="px-2 py-1.5 whitespace-nowrap">{String(s.date || '').slice(0, 10)}</td>
                          <td className="px-2 py-1.5 max-w-[220px] truncate" title={s.title}>{s.title || '—'}</td>
                          <td className="px-2 py-1.5">{s.account_name || '—'}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{fmtRp(s.revenue)}</td>
                          <td className="px-2 py-1.5">{fmtNum(s.viewers)}</td>
                          <td className="px-2 py-1.5">{fmtNum(s.peak_viewers)}</td>
                          <td className="px-2 py-1.5">{fmtNum(s.orders)}</td>
                          <td className="px-2 py-1.5">{s.duration_minutes ? `${s.duration_minutes} mnt` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {detail.truncated && (
                <p className="text-[11px] text-amber-700 dark:text-amber-400">
                  Daftar dipotong pada batas aman. Persempit dengan filter toko/bulan untuk
                  melihat sisanya.
                </p>
              )}
              <ul className="list-disc pl-4 space-y-0.5 text-[10px] text-muted-foreground">
                {(detail.data_notes || []).filter((n) => !n.startsWith('PERLU KEPUTUSAN'))
                  .map((n, i) => <li key={i}>{n}</li>)}
              </ul>
              <div className="flex justify-end">
                <Button size="sm" variant="outline" className="h-8 text-[11px]"
                  onClick={() => { setDetailOf(null); setDetail(null); }}
                  data-testid="scorecard-detail-close">
                  <X size={12} className="mr-1" /> Tutup
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
