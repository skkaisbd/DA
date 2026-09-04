/**
 * DailyReportModule — Laporan Harian PIC Portal Marketing (F10, sesi #10)
 *
 * KENAPA LAYAR INI DIUBAH
 * -----------------------
 * Sebelumnya layar ini satu-satunya pintu Portal Marketing yang menampilkan
 * DAFTAR (9 toko × status input harian) sebagai **tumpukan baris kartu**: tidak
 * bisa diurutkan, tidak bisa dicari, tidak bisa diunduh, dan — yang paling mahal —
 * **menyembunyikan satu field yang dikirim backend**: `sales_status.entered_live`.
 * Akibatnya toko yang sudah mengisi omzet TOTAL tetapi belum mengisi omzet LIVE
 * tampak "sudah beres" (centang hijau), padahal justru angka live-lah yang dipakai
 * menilai sesi live host. Pertanyaan harian SPV ("siapa yang belum input hari
 * ini?") hanya bisa dijawab dengan menggulir dan menghitung sendiri.
 *
 * Sekarang: **tabel nyata** (7 kolom, bisa diurutkan tiap kolom), pencarian,
 * pengalih Tabel/Kartu, unduh CSV, dan kolom "Live" yang memisahkan dua jenis
 * input. Tombol **Eksekusi** (input sales cepat) dipertahankan persis.
 *
 * YANG WAJIB TETAP ADA (jangan dihapus saat merapikan tampilan):
 *  · pembeda input TOTAL vs LIVE — dua pertanyaan berbeda, dua kolom berbeda;
 *  · keadaan kosong yang MENJELASKAN diri (staf tanpa toko ⇒ panel
 *    `NoStoreScopeNotice`, bukan tabel kosong tanpa sebab);
 *  · tombol Eksekusi hanya muncul bila memang ada task input sales yang pending.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  CalendarCheck, RefreshCw, CheckCircle2, XCircle, AlertTriangle,
  ChevronLeft, ChevronRight, Zap, Loader2, TrendingUp, ClipboardList,
  Search, Download, Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { GlassPanel } from '@/components/ui/glass';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AccountBadge } from './AccountBadge';
import NoStoreScopeNotice from './NoStoreScopeNotice';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import { downloadCsv } from '@/lib/csv';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(n || 0);

// ─── Quick Sales Dialog ────────────────────────────────────────────────────────
function QuickSalesDialog({ open, onClose, account, task, date, token, onSuccess }) {
  const [form, setForm] = useState({ revenue: '', orders: '' });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    const revenue = parseFloat(form.revenue);
    const orders  = parseInt(form.orders, 10);
    if (!revenue || revenue <= 0) { toast.error('Revenue wajib diisi'); return; }
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/tasks/${task.id}/complete-action`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_data: { revenue, orders: orders || 0, date },
          completion_notes: `Input via Laporan Harian — ${date}`,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal eksekusi');
      toast.success(`Sales ${account.account_name} berhasil diinput`);
      onSuccess();
      onClose();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm" data-testid="quick-sales-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Zap size={15} className="text-blue-500" /> Input Sales Cepat
          </DialogTitle>
          <div className="mt-1">
            <AccountBadge account={account} size="sm" />
            <p className="text-xs text-muted-foreground mt-1">Tanggal: {date}</p>
          </div>
        </DialogHeader>
        <div className="space-y-3 mt-1">
          <div>
            <Label className="text-xs">Revenue (Rp) <span className="text-red-700 dark:text-red-400">*</span></Label>
            <Input type="number" min={0} step={1000} value={form.revenue}
              onChange={(e) => setForm((f) => ({ ...f, revenue: e.target.value }))}
              placeholder="Contoh: 4500000" className="mt-1 h-9"
              data-testid="quick-revenue-input" autoFocus />
          </div>
          <div>
            <Label className="text-xs">Orders</Label>
            <Input type="number" min={0} value={form.orders}
              onChange={(e) => setForm((f) => ({ ...f, orders: e.target.value }))}
              placeholder="Contoh: 42" className="mt-1 h-9"
              data-testid="quick-orders-input" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={handleSubmit} disabled={saving} data-testid="quick-sales-submit">
            {saving ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Zap size={13} className="mr-1" />}
            Simpan &amp; Selesaikan Task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── KPI Card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, color = 'text-primary', highlight = false, testId }) {
  return (
    <GlassPanel className={`p-4 ${highlight ? 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5' : ''}`}
      data-testid={testId}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon size={14} className={color} />}
      </div>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </GlassPanel>
  );
}

function YesNo({ ok, yes = 'sudah', no = 'belum' }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 size={12} /> {yes}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
      <XCircle size={12} /> {no}
    </span>
  );
}

/* Kolom tabel = kontrak layar ini. `get` dipakai untuk mengurutkan DAN menyusun
   CSV, jadi angka di berkas unduhan tidak mungkin berbeda dari yang di layar. */
const COLUMNS = [
  { key: 'account', label: 'Toko', get: (a) => (a.account_name || '').toLowerCase() },
  { key: 'total', label: 'Input harian', get: (a) => (a.sales_status?.entered_total ? 1 : 0) },
  { key: 'revenue', label: 'Omzet diinput', get: (a) => Number(a.sales_status?.revenue || 0), num: true },
  { key: 'orders', label: 'Pesanan', get: (a) => Number(a.sales_status?.orders || 0), num: true },
  { key: 'live', label: 'Input live', get: (a) => (a.sales_status?.entered_live ? 1 : 0) },
  { key: 'health', label: 'Skor kesehatan', get: (a) => (a.health_score == null ? -1 : Number(a.health_score)), num: true },
  { key: 'tasks', label: 'Tugas menunggu', get: (a) => (a.pending_action_tasks || []).length, num: true },
  { key: 'overdue', label: 'Terlambat', get: (a) => Number(a.overdue_count || 0), num: true },
];

export default function DailyReportModule({ token }) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const yestStr = yesterday.toISOString().slice(0, 10);

  const [date, setDate]       = useState(yestStr);
  const [report, setReport]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [eksekusiTarget, setEksekusiTarget] = useState(null); // { account, task }

  // F10 — daftar yang bisa DIPAKAI: cari, urutkan, unduh, dan dua tipe tampilan.
  const [q, setQ] = useState('');
  const [sortKey, setSortKey] = useState('account');
  const [sortDir, setSortDir] = useState(1);
  const [view, setView] = useState('table');   // 'table' | 'cards'
  const [onlyMissing, setOnlyMissing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/reports/daily?date=${date}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Gagal memuat laporan (HTTP ${res.status})`);
      setReport(await res.json());
    } catch (e) { toast.error(e.message); setReport(null); }
    finally { setLoading(false); }
  }, [date, token]);

  useEffect(() => { load(); }, [load]);

  const prevDay = () => { const d = new Date(date); d.setDate(d.getDate() - 1); setDate(d.toISOString().slice(0, 10)); };
  const nextDay = () => { const d = new Date(date); d.setDate(d.getDate() + 1); setDate(d.toISOString().slice(0, 10)); };

  const s = report?.summary || {};
  const accounts = report?.accounts || [];
  const criticals = accounts.filter((a) => a.health_score != null && a.health_score < 60);
  const allPendingTasks = accounts.flatMap((a) =>
    (a.pending_action_tasks || []).map((t) => ({ ...t, _account: a })));

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = accounts.filter((a) => {
      if (onlyMissing && a.sales_status?.entered_total) return false;
      if (!needle) return true;
      return [a.account_name, a.account_code, a.platform]
        .some((v) => String(v || '').toLowerCase().includes(needle));
    });
    const col = COLUMNS.find((c) => c.key === sortKey) || COLUMNS[0];
    out = [...out].sort((x, y) => {
      const a = col.get(x); const b = col.get(y);
      if (a === b) return (x.account_name || '').localeCompare(y.account_name || '');
      return (a > b ? 1 : -1) * sortDir;
    });
    return out;
  }, [accounts, q, onlyMissing, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (key === sortKey) setSortDir((d) => -d);
    else { setSortKey(key); setSortDir(key === 'account' ? 1 : -1); }
  };

  const exportCsv = () => {
    const head = ['Tanggal', 'Toko', 'Kode', 'Platform', 'Input harian', 'Omzet diinput',
      'Pesanan', 'Input live', 'Skor kesehatan', 'Tugas menunggu', 'Terlambat'];
    const lines = rows.map((a) => [
      date, a.account_name, a.account_code, a.platform,
      a.sales_status?.entered_total ? 'sudah' : 'belum',
      Number(a.sales_status?.revenue || 0),
      Number(a.sales_status?.orders || 0),
      a.sales_status?.entered_live ? 'sudah' : 'belum',
      a.health_score == null ? 'belum ada' : a.health_score,
      (a.pending_action_tasks || []).length,
      Number(a.overdue_count || 0),
    ]);
    const n = downloadCsv(`laporan-harian-marketing-${date}`, head, lines);
    toast.success(`CSV terunduh — ${n} toko (persis yang terlihat di layar)`);
  };

  return (
    <div className="space-y-5 p-4 lg:p-6" data-testid="daily-report-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarCheck size={22} className="text-primary" /> Laporan Harian
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Siapa sudah / belum mengisi angka hari itu — per toko, bisa diurutkan &amp; diunduh
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prevDay} data-testid="daily-prev-day"><ChevronLeft size={14} /></Button>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="h-9 text-sm border rounded-md px-3 bg-background"
            data-testid="daily-date-picker" />
          <Button variant="outline" size="sm" onClick={nextDay} data-testid="daily-next-day"><ChevronRight size={14} /></Button>
          <Button variant="outline" size="sm" onClick={load} data-testid="daily-refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      <NoStoreScopeNotice token={token} what="Daftar toko & angka di laporan ini" />

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 size={28} className="animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {/* KPI Strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="daily-kpi">
            <KpiCard label="Sales Input Rate" value={`${s.sales_input_rate || 0}%`}
              sub={`${s.accounts_sales_entered || 0}/${s.accounts_total || 0} akun`}
              icon={TrendingUp} testId="daily-kpi-rate"
              color={s.sales_input_rate >= 80 ? 'text-emerald-600' : 'text-amber-600'} />
            <KpiCard label="Akun Sudah Input" value={s.accounts_sales_entered || 0}
              icon={CheckCircle2} color="text-emerald-600" />
            <KpiCard label="Akun Belum Input" value={s.accounts_sales_missing || 0}
              icon={XCircle} color={s.accounts_sales_missing > 0 ? 'text-red-600' : 'text-muted-foreground'}
              highlight={s.accounts_sales_missing > 0} testId="daily-kpi-missing" />
            <KpiCard label="Task Selesai Hari Ini" value={s.tasks_done_today || 0}
              icon={ClipboardList} color="text-blue-600" />
            <KpiCard label="Task Overdue" value={s.tasks_overdue || 0}
              icon={AlertTriangle} color={s.tasks_overdue > 0 ? 'text-red-600' : 'text-muted-foreground'}
              highlight={s.tasks_overdue > 0} />
            <KpiCard label="Menunggu Approval" value={s.tasks_pending_approval || 0}
              icon={ClipboardList} color="text-amber-600" />
          </div>

          {/* Health Alerts */}
          {criticals.length > 0 && (
            <Card className="border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2 text-red-600">
                  <AlertTriangle size={14} /> Health Alert — {criticals.length} akun kritis
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2 pt-0">
                {criticals.map((a) => (
                  <div key={a.account_id} className="flex items-center gap-1.5 text-xs">
                    <AccountBadge account={a} size="xs" />
                    <span className="text-red-600 font-bold">{a.health_score}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* ── Daftar per toko: cari · urutkan · unduh · Tabel/Kartu ─────── */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-sm">Status input per toko — {date}</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input className="h-8 pl-8 w-52 text-xs" placeholder="cari toko / kode / platform"
                      value={q} onChange={(e) => setQ(e.target.value)} data-testid="daily-search" />
                  </div>
                  <label className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                    <input type="checkbox" checked={onlyMissing}
                      onChange={(e) => setOnlyMissing(e.target.checked)}
                      data-testid="daily-only-missing" />
                    hanya yang <b>belum input</b>
                  </label>
                  <Button size="sm" variant="outline" className="h-8" onClick={exportCsv}
                    disabled={!rows.length} data-testid="daily-export-csv">
                    <Download size={12} className="mr-1" /> CSV
                  </Button>
                  <div className="flex rounded-md border border-border overflow-hidden">
                    <button className={`px-2 py-1 text-[11px] flex items-center gap-1 ${view === 'table' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                      onClick={() => setView('table')} data-testid="daily-view-table">
                      <Table2 size={11} /> Tabel
                    </button>
                    <button className={`px-2 py-1 text-[11px] flex items-center gap-1 ${view === 'cards' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                      onClick={() => setView('cards')} data-testid="daily-view-cards">
                      <LayoutGrid size={11} /> Kartu
                    </button>
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">
                <b>Input harian</b> = omzet total toko hari itu · <b>Input live</b> = omzet dari sesi
                live. Keduanya dipisah karena dinilai orang yang berbeda — toko bisa "sudah input"
                harian tetapi live-nya belum.
                {' '}<span data-testid="daily-count">{rows.length} toko ditampilkan</span>
                {accounts.length !== rows.length ? ` dari ${accounts.length}` : ''}.
              </p>
            </CardHeader>
            <CardContent className={view === 'table' ? 'p-0' : 'p-0'}>
              {!rows.length ? (
                <div className="py-10 text-center text-sm text-muted-foreground" data-testid="daily-empty">
                  {accounts.length
                    ? 'Tidak ada toko yang cocok dengan pencarian/filter ini.'
                    : 'Belum ada toko yang bisa ditampilkan untuk tanggal ini.'}
                </div>
              ) : view === 'table' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs" data-testid="daily-table">
                    <thead className="bg-muted/60">
                      <tr>
                        {COLUMNS.map((c) => (
                          <th key={c.key}
                            className={`px-3 py-2 font-semibold whitespace-nowrap cursor-pointer select-none ${c.num ? 'text-right' : 'text-left'}`}
                            onClick={() => toggleSort(c.key)}
                            data-testid={`daily-sort-${c.key}`}>
                            <span className="inline-flex items-center gap-1">
                              {c.label}
                              <ArrowUpDown size={9} className={sortKey === c.key ? 'text-primary' : 'text-muted-foreground/40'} />
                            </span>
                          </th>
                        ))}
                        <th className="px-3 py-2 text-right font-semibold">Aksi</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {rows.map((acc) => {
                        const st = acc.sales_status || {};
                        const salesTask = (acc.pending_action_tasks || []).find(
                          (t) => t.action_type === 'submit_form' || t.action_type === 'input_sales'
                            || t.related_entity === 'sales_data');
                        return (
                          <tr key={acc.account_id} className="hover:bg-muted/30"
                            data-testid={`daily-acc-${acc.account_code}`}>
                            <td className="px-3 py-2">
                              <div className="font-semibold text-foreground">{acc.account_name}</div>
                              <div className="text-[10px] text-muted-foreground">
                                {acc.account_code} · {acc.platform}
                              </div>
                            </td>
                            <td className="px-3 py-2"><YesNo ok={!!st.entered_total} /></td>
                            <td className="px-3 py-2 text-right whitespace-nowrap">
                              {st.entered_total ? fmtRp(st.revenue) : <span className="text-muted-foreground">—</span>}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {st.entered_total ? fmtNum(st.orders) : <span className="text-muted-foreground">—</span>}
                            </td>
                            <td className="px-3 py-2" data-testid={`daily-live-${acc.account_code}`}>
                              <YesNo ok={!!st.entered_live} />
                            </td>
                            <td className="px-3 py-2 text-right">
                              {acc.health_score == null ? (
                                <span className="text-muted-foreground italic">belum ada</span>
                              ) : (
                                <span className={`font-bold ${acc.health_score >= 80 ? 'text-emerald-600' : acc.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                                  {acc.health_score}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {(acc.pending_action_tasks || []).length || <span className="text-muted-foreground">0</span>}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {acc.overdue_count > 0 ? (
                                <Badge variant="outline" className="text-[9px] bg-red-100 dark:bg-red-500/10 text-red-500 border-red-400 dark:border-red-500/30">
                                  {acc.overdue_count}
                                </Badge>
                              ) : <span className="text-muted-foreground">0</span>}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {!st.entered_total && salesTask ? (
                                <Button size="sm" className="h-6 px-2 text-[10px] bg-blue-600 hover:bg-blue-700"
                                  onClick={() => setEksekusiTarget({ account: acc, task: salesTask })}
                                  data-testid={`eksekusi-btn-${acc.account_code}`}>
                                  <Zap size={10} className="mr-1" /> Eksekusi
                                </Button>
                              ) : <span className="text-muted-foreground text-[10px]">—</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="divide-y" data-testid="daily-cards">
                  {rows.map((acc) => {
                    const st = acc.sales_status || {};
                    const salesTask = (acc.pending_action_tasks || []).find(
                      (t) => t.action_type === 'submit_form' || t.action_type === 'input_sales'
                        || t.related_entity === 'sales_data');
                    return (
                      <div key={acc.account_id} className="flex items-center gap-3 px-4 py-3"
                        data-testid={`daily-card-${acc.account_code}`}>
                        <AccountBadge account={acc} size="sm" />
                        <div className="flex-1 min-w-0 text-xs space-y-0.5">
                          <div className="flex items-center gap-3">
                            <span>harian: <YesNo ok={!!st.entered_total} /></span>
                            <span>live: <YesNo ok={!!st.entered_live} /></span>
                          </div>
                          {st.entered_total && (
                            <div className="text-emerald-700 dark:text-emerald-400 font-medium">
                              {fmtRp(st.revenue)} · {fmtNum(st.orders)} pesanan
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {!st.entered_total && salesTask && (
                            <Button size="sm" className="h-7 text-xs bg-blue-600 hover:bg-blue-700"
                              onClick={() => setEksekusiTarget({ account: acc, task: salesTask })}>
                              <Zap size={11} className="mr-1" /> Eksekusi
                            </Button>
                          )}
                          {acc.overdue_count > 0 && (
                            <Badge variant="outline" className="text-[10px] bg-red-100 dark:bg-red-500/10 text-red-500 border-red-400 dark:border-red-500/30">
                              {acc.overdue_count} overdue
                            </Badge>
                          )}
                          {acc.health_score != null && (
                            <span className={`text-xs font-bold ${acc.health_score >= 80 ? 'text-emerald-600' : acc.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                              {acc.health_score}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Pending Action Tasks */}
          {allPendingTasks.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Zap size={14} className="text-blue-500" />
                  Task Menunggu Aksi ({allPendingTasks.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y">
                  {allPendingTasks.map((t) => (
                    <div key={t.id} className="flex items-center gap-3 px-4 py-2.5"
                      data-testid={`pending-task-${t.task_code}`}>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{t.title}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs font-mono text-muted-foreground">{t.task_code}</span>
                          <AccountBadge account={t._account} size="xs" />
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge variant="outline" className={`text-[10px] ${
                          t.priority === 'high' ? 'bg-red-100 dark:bg-red-500/10 text-red-500 border-red-400 dark:border-red-500/30'
                            : t.priority === 'medium' ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-500 border-amber-400 dark:border-amber-500/30'
                              : 'bg-muted dark:bg-gray-500/10 text-muted-foreground'}`}>{t.priority}</Badge>
                        <Badge variant="outline" className="text-[10px] bg-blue-100 dark:bg-blue-500/10 text-blue-500 border-blue-400 dark:border-blue-500/30">
                          <Zap size={9} className="mr-0.5" />{t.action_type}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Quick Sales Eksekusi Dialog */}
      {eksekusiTarget && (
        <QuickSalesDialog
          open={!!eksekusiTarget}
          onClose={() => setEksekusiTarget(null)}
          account={eksekusiTarget.account}
          task={eksekusiTarget.task}
          date={date}
          token={token}
          onSuccess={() => { setEksekusiTarget(null); load(); }}
        />
      )}
    </div>
  );
}
