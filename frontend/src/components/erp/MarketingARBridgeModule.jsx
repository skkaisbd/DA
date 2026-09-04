/**
 * MarketingARBridgeModule — **PENCAIRAN & REKONSILIASI** (F9, sesi #12)
 *
 * KENAPA HALAMAN INI MENGGANTI HALAMAN "DINONAKTIFKAN"
 * ----------------------------------------------------
 * Sebelumnya modul ini hanya memuat pesan "fitur Buat Invoice AR dari Sales
 * dinonaktifkan" — pintu yang masih ada di navigasi tetapi tidak mengerjakan
 * apa pun. Keputusan #1 memang benar (omzet harian TIDAK boleh otomatis jadi
 * piutang), tapi akibatnya ada lubang nyata: **uang yang benar-benar masuk dari
 * marketplace tidak punya tempat untuk dicatat.**
 *
 * Rencana F9 aslinya IMPOR berkas pencairan; aturan proyek (blokir data BD-2)
 * melarangnya sampai ada contoh berkas asli — *"pemetaan kolom uang tidak boleh
 * ditebak"*. Keputusan pemilik (2026-08-14): **input MANUAL dulu**. Itu
 * MENGHAPUS blokirnya, bukan menghindarinya: kalau staf mengisi field yang
 * namanya jelas, tidak ada kolom yang perlu ditebak siapa pun.
 *
 * TIGA aturan yang membuat angkanya bisa dipercaya:
 *  1. **Net payout DIISI STAF dari mutasi bank**, bukan dihitung layar. Server
 *     menghitung nilai *yang seharusnya* lalu menampilkan SELISIH-nya. Kalau
 *     layar yang menghitung net, setiap potongan yang belum dikenal akan HILANG
 *     diam-diam — angkanya "cocok" karena kita sendiri yang membuatnya cocok.
 *  2. **Selisih ≠ 0 ⇒ tombol Jurnal MATI** sampai selisihnya DINAMAI di
 *     "Potongan lain"/"Penyesuaian". Jadi biaya tak dikenal punya NAMA.
 *  3. **Jurnalnya DRAFT** — Keuangan yang memasukkannya ke buku besar.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Banknote, Plus, RefreshCw, AlertTriangle, CheckCircle2, Table2,
  LayoutGrid, ArrowUpDown, Scale, X, Loader2, FileText, Trash2, Pencil,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite from '@/components/ui/pagination-lite';
import { MarketingAccountSelect } from './marketing/pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;
const VIEW_KEY = 'settlement_view';
const PLATFORMS = ['shopee', 'tiktok', 'tokopedia', 'lazada', 'website'];

// SATU daftar field uang dipakai form, tabel, DAN CSV ⇒ istilah & urutannya
// mustahil berbeda antar ketiganya.
const MONEY = [
  ['gross_sales', 'Omzet bruto', '+', 'Penjualan sebelum potongan apa pun'],
  ['refunds', 'Refund / retur', '\u2212', 'Pesanan yang dikembalikan'],
  ['seller_discount', 'Diskon penjual', '\u2212', 'Diskon yang kita tanggung'],
  ['shipping_subsidy', 'Subsidi ongkir platform', '+', 'Ongkir ditanggung platform'],
  ['platform_commission', 'Komisi platform', '\u2212', 'Komisi penjualan'],
  ['platform_service_fee', 'Fee layanan', '\u2212', 'Biaya layanan / admin'],
  ['affiliate_commission', 'Komisi afiliasi', '\u2212', 'Komisi affiliator / KOL'],
  ['ads_deduction', 'Potongan iklan', '\u2212', 'Iklan dipotong dari pencairan'],
  ['other_deductions', 'Potongan lain', '\u2212', 'Beri NAMA di catatan di bawah'],
  ['adjustments', 'Penyesuaian', '\u00b1', 'Boleh negatif (koreksi platform)'],
];
const CSV_HEAD = ['ID Pencairan', 'Platform', 'Toko', 'Tanggal cair',
  ...MONEY.map(([, l]) => l), 'Net payout', 'Net seharusnya', 'Selisih',
  'Cocok', 'Total potongan', '% potongan', 'No. Jurnal', 'Status jurnal'];

const EMPTY = {
  account_id: '', platform: 'shopee', settlement_id: '', settlement_date: '',
  period_from: '', period_to: '', net_payout: '', other_deductions_note: '', notes: '',
  ...Object.fromEntries(MONEY.map(([f]) => [f, ''])),
};
const rp = (n) => formatRupiah(Number(n || 0));
const num = (v) => (v === '' || v == null ? 0 : Number(v) || 0);

export default function MarketingARBridgeModule({ token }) {
  const authH = useMemo(() => ({
    Authorization: `Bearer ${token || localStorage.getItem('erp_token') || ''}`,
  }), [token]);

  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [pg, setPg] = useState(null);
  const [recon, setRecon] = useState(null);
  const [coaMissing, setCoaMissing] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [fAcc, setFAcc] = useState('');
  const [fPlat, setFPlat] = useState('');
  const [sort, setSort] = useState({ key: 'settlement_date', dir: 'desc' });
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => { try { localStorage.setItem(VIEW_KEY, view); } catch { /* diblokir */ } }, [view]);

  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 15, sort_by: sort.key, sort_dir: sort.dir };
      if (fAcc) params.account_id = fAcc;
      if (fPlat) params.platform = fPlat;
      const [l, r, c] = await Promise.all([
        axios.get(`${API}/api/marketing/settlements`, { params, headers: authH }),
        axios.get(`${API}/api/marketing/settlements/reconcile`,
          { params: fAcc ? { account_id: fAcc } : {}, headers: authH }),
        axios.get(`${API}/api/marketing/settlements/coa-map`, { headers: authH }),
      ]);
      setRows(l.data?.data || []); setSummary(l.data?.summary || null);
      setPg(l.data?.pagination || null); setRecon(r.data || null);
      setCoaMissing(c.data?.missing || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal memuat data pencairan');
    } finally { setLoading(false); }
  }, [authH, page, sort, fAcc, fPlat]);
  useEffect(() => { load(); }, [load]);

  const toggleSort = (k) => { setPage(1); setSort((s) => (s.key === k
    ? { key: k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: k, dir: 'desc' })); };

  // Selisih dihitung di layar HANYA untuk umpan balik seketika saat mengetik;
  // yang disimpan & dipercaya tetap hitungan server (satu penulis).
  const expectedNet = MONEY.reduce((a, [f, , sg]) => (sg === '\u2212' ? a - num(form[f]) : a + num(form[f])), 0);
  const diff = Math.round((num(form.net_payout) - expectedNet) * 100) / 100;
  const balanced = Math.abs(diff) < 0.01;

  const openCreate = () => { setEditId(null); setForm(EMPTY); setShowForm(true); };
  const openEdit = (r) => {
    setEditId(r.id);
    setForm({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, r[k] ?? ''])) });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.account_id) { toast.error('Pilih toko dulu'); return; }
    if (!String(form.settlement_id).trim()) { toast.error('ID pencairan wajib diisi (nomor dari platform)'); return; }
    if (!form.settlement_date) { toast.error('Tanggal uang masuk wajib diisi'); return; }
    setSaving(true);
    try {
      const payload = {
        account_id: form.account_id, platform: form.platform,
        settlement_id: String(form.settlement_id).trim(),
        settlement_date: form.settlement_date,
        period_from: form.period_from || null, period_to: form.period_to || null,
        notes: form.notes, other_deductions_note: form.other_deductions_note,
        net_payout: num(form.net_payout),
        ...Object.fromEntries(MONEY.map(([f]) => [f, num(form[f])])),
      };
      if (editId) await axios.put(`${API}/api/marketing/settlements/${editId}`, payload, { headers: authH });
      else await axios.post(`${API}/api/marketing/settlements`, payload, { headers: authH });
      toast.success(editId ? 'Pencairan diperbarui' : 'Pencairan dicatat');
      setShowForm(false); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal menyimpan', { duration: 9000 });
    } finally { setSaving(false); }
  };

  const makeJournal = async (r) => {
    setBusy(r.id);
    try {
      const res = await axios.post(`${API}/api/marketing/settlements/${r.id}/journal`, {}, { headers: authH });
      toast.success(res.data?.message || 'Jurnal draft dibuat', { duration: 8000 });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal membuat jurnal', { duration: 12000 });
    } finally { setBusy(''); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Hapus pencairan ${r.settlement_id}?`)) return;
    try {
      await axios.delete(`${API}/api/marketing/settlements/${r.id}`, { headers: authH });
      toast.success('Dihapus'); load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Gagal hapus', { duration: 9000 }); }
  };

  const csvRows = rows.map((r) => [r.settlement_id, r.platform, r.account_name || '',
    String(r.settlement_date).slice(0, 10), ...MONEY.map(([f]) => r[f] ?? 0),
    r.net_payout ?? 0, r.expected_net_payout ?? 0, r.net_payout_diff ?? 0,
    r.math_verified ? 'ya' : 'BELUM', r.total_deductions ?? 0, r.deduction_pct ?? 0,
    r.je_number || '', r.je_status || '']);

  const COLS = [['settlement_id', 'ID Pencairan'], ['platform', 'Platform'],
    ['settlement_date', 'Tanggal cair'], ['gross_sales', 'Omzet bruto'],
    ['total_deductions', 'Total potongan'], ['deduction_pct', '% potongan'],
    ['net_payout', 'Net payout'], ['math_verified', 'Cocok'], ['je_number', 'Jurnal']];

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto" data-testid="settlement-module">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Banknote className="w-5 h-5 text-emerald-600" />Pencairan &amp; Rekonsiliasi
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Catat uang yang benar-benar masuk dari marketplace, lalu cocokkan dengan omzet marketing
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="settle-refresh">
            <RefreshCw size={14} className="mr-1" />Muat ulang
          </Button>
          <Button size="sm" onClick={openCreate} data-testid="settle-add">
            <Plus size={14} className="mr-1" />Catat Pencairan
          </Button>
        </div>
      </div>

      {coaMissing.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 dark:border-red-700 dark:bg-red-900/25"
             data-testid="settle-coa-missing">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-600" />
          <p className="text-xs text-red-900 dark:text-red-200">
            <b>Akun COA belum ada: {coaMissing.join(', ')}.</b> Jurnal pencairan tidak bisa
            dibuat sebelum akun ini ada di Bagan Akun (Portal Finance).
          </p>
        </div>
      )}

      {/* Ringkasan — dihitung SERVER atas SELURUH data, bukan halaman ini */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[['Omzet bruto (pencairan)', rp(summary?.gross_sales), 'bg-blue-50 dark:bg-blue-900/20', ''],
          ['Total potongan', rp(summary?.total_deductions), 'bg-amber-50 dark:bg-amber-900/20',
            summary?.deduction_pct ? `${summary.deduction_pct}% dari bruto` : ''],
          ['Uang masuk (net payout)', rp(summary?.net_payout), 'bg-emerald-50 dark:bg-emerald-900/20', ''],
          ['Belum seimbang', String(summary?.unverified_count ?? 0), 'bg-red-50 dark:bg-red-900/20',
            'selisihnya harus dinamai dulu']].map(([label, value, bg, sub]) => (
          <Card key={label} className={`border-border ${bg}`}><CardContent className="p-4">
            <p className="text-lg font-bold leading-tight">{value}</p>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
          </CardContent></Card>
        ))}
      </div>

      {recon && (
        <Card className="border-border bg-card" data-testid="settle-reconcile"><CardContent className="p-4">
          <h3 className="text-sm font-semibold flex items-center gap-2 mb-2">
            <Scale className="w-4 h-4 text-muted-foreground" />
            Rekonsiliasi — omzet marketing vs pencairan platform
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div><p className="text-muted-foreground">Pesanan marketing</p>
              <p className="font-semibold">{recon.marketing?.order_count} pesanan</p></div>
            <div><p className="text-muted-foreground">Omzet bruto marketing</p>
              <p className="font-semibold">{rp(recon.marketing?.revenue_gross)}</p>
              <p className="text-[10px] text-muted-foreground">{recon.marketing?.labels?.revenue_gross}</p></div>
            <div><p className="text-muted-foreground">Omzet produk marketing</p>
              <p className="font-semibold">{rp(recon.marketing?.revenue_product)}</p>
              <p className="text-[10px] text-muted-foreground">{recon.marketing?.labels?.revenue_product}</p></div>
            <div><p className="text-muted-foreground">Selisih bruto vs pencairan</p>
              <p className="font-semibold">{rp(recon.gap?.gross_vs_revenue_gross)}</p></div>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">{recon.gap?.why}</p>
        </CardContent></Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-52">
          <MarketingAccountSelect token={token} value={fAcc}
            onChange={(v) => { setFAcc(v); setPage(1); }} label="" includeAll
            allLabel="Semua Toko" required={false} testId="settle-filter-account" />
        </div>
        <Select value={fPlat || 'all'} onValueChange={(v) => { setFPlat(v === 'all' ? '' : v); setPage(1); }}>
          <SelectTrigger className="w-36 h-9 text-xs bg-background" data-testid="settle-filter-platform">
            <SelectValue placeholder="Platform" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Platform</SelectItem>
            {PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="inline-flex rounded-lg border border-border overflow-hidden">
          <button type="button" onClick={() => setView('table')} data-testid="settle-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="settle-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
        <ExportCsvButton filename="pencairan-marketplace" testId="settle-export-csv"
          head={CSV_HEAD} rows={csvRows} note={`halaman ${page}/${pg?.total_pages ?? 1}`} />
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>
      ) : rows.length === 0 ? (
        <Card className="border-border bg-card"><CardContent className="p-10 text-center">
          <Banknote className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm font-medium">Belum ada pencairan yang dicatat</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
            Buka laporan pencairan di Seller Center (atau mutasi bank), lalu catat angkanya
            di sini. Nomor pencairan dipakai mencegah satu pencairan tercatat dua kali.
          </p>
          <Button size="sm" className="mt-4" onClick={openCreate}>
            <Plus size={13} className="mr-1" />Catat Pencairan
          </Button>
        </CardContent></Card>
      ) : view === 'table' ? (
        <Card className="border-border bg-card"><CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="settle-table">
              <thead className="bg-muted/50"><tr className="text-left">
                {COLS.map(([k, label]) => (
                  <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                    <button type="button" onClick={() => toggleSort(k)}
                      data-testid={`settle-sort-${k}`}
                      className="inline-flex items-center gap-1 hover:text-primary">
                      {label}<ArrowUpDown size={10} className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                    </button>
                  </th>
                ))}
                <th className="px-2.5 py-2 font-semibold text-right">Aksi</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border hover:bg-muted/40"
                      data-testid={`settle-row-${r.settlement_id}`}>
                    <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.settlement_id}</td>
                    <td className="px-2.5 py-2">{r.platform}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{String(r.settlement_date).slice(0, 10)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{rp(r.gross_sales)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{rp(r.total_deductions)}</td>
                    <td className="px-2.5 py-2 text-right">{r.deduction_pct}%</td>
                    <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{rp(r.net_payout)}</td>
                    <td className="px-2.5 py-2">
                      {r.math_verified ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 size={11} /> ya</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded border border-amber-400 bg-amber-100 px-1.5 py-0.5 font-medium text-amber-900 dark:border-amber-600 dark:bg-amber-900/40 dark:text-amber-200"
                              title="Selisih belum dinamai — jurnal belum bisa dibuat">
                          <AlertTriangle size={9} /> selisih {rp(r.net_payout_diff)}</span>
                      )}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {r.je_number ? (
                        <span className="font-mono text-[11px]">{r.je_number}
                          <span className="ml-1 text-muted-foreground">({r.je_status})</span></span>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">
                      {!r.je_number && (
                        <div className="inline-flex gap-1">
                          <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]"
                            disabled={!r.math_verified || busy === r.id}
                            title={r.math_verified ? 'Buat jurnal draft'
                              : 'Selisihnya harus dinamai dulu — jurnal dari angka yang belum seimbang mustahil seimbang'}
                            onClick={() => makeJournal(r)}
                            data-testid={`settle-journal-${r.settlement_id}`}>
                            {busy === r.id ? <Loader2 size={11} className="animate-spin" />
                              : <><FileText size={11} className="mr-1" />Jurnal</>}
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7"
                            onClick={() => openEdit(r)} data-testid={`settle-edit-${r.settlement_id}`}>
                            <Pencil size={12} /></Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-500"
                            onClick={() => remove(r)} data-testid={`settle-del-${r.settlement_id}`}>
                            <Trash2 size={12} /></Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={pg?.total_pages ?? 1}
            total={pg?.total ?? rows.length} pageSize={15} onPageChange={setPage} className="px-3" />
        </CardContent></Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {rows.map((r) => (
              <Card key={r.id} className="border-border bg-card" data-testid={`settle-card-${r.settlement_id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div><p className="font-mono text-xs text-muted-foreground">{r.settlement_id}</p>
                      <p className="text-sm font-semibold">{r.platform} · {String(r.settlement_date).slice(0, 10)}</p></div>
                    {!r.math_verified && <AlertTriangle size={14} className="text-amber-600 shrink-0" />}
                  </div>
                  <div className="mt-2 space-y-0.5 text-xs">
                    <div className="flex justify-between"><span className="text-muted-foreground">Omzet bruto</span><b>{rp(r.gross_sales)}</b></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Total potongan</span><b>{rp(r.total_deductions)} ({r.deduction_pct}%)</b></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Net payout</span><b>{rp(r.net_payout)}</b></div>
                    {r.je_number && <div className="flex justify-between"><span className="text-muted-foreground">Jurnal</span><b className="font-mono">{r.je_number} ({r.je_status})</b></div>}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <PaginationLite page={page} totalPages={pg?.total_pages ?? 1}
            total={pg?.total ?? rows.length} pageSize={15} onPageChange={setPage} />
        </>
      )}

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-3xl bg-background">
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <Banknote size={18} className="text-emerald-600" />
            {editId ? 'Ubah Pencairan' : 'Catat Pencairan Marketplace'}
          </DialogTitle></DialogHeader>

          <div className="max-h-[65vh] overflow-y-auto pr-1 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <MarketingAccountSelect token={token} value={form.account_id}
                onChange={(v) => setForm((f) => ({ ...f, account_id: v }))}
                testId="settle-form-account" className="col-span-2" />
              <div><Label className="text-xs">Platform *</Label>
                <Select value={form.platform} onValueChange={(v) => setForm((f) => ({ ...f, platform: v }))}>
                  <SelectTrigger className="mt-1 h-9 bg-background" data-testid="settle-form-platform"><SelectValue /></SelectTrigger>
                  <SelectContent>{PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                </Select></div>
              <div><Label className="text-xs">ID / No. Pencairan *</Label>
                <Input className="mt-1 h-9 bg-background font-mono" value={form.settlement_id}
                  onChange={(e) => setForm((f) => ({ ...f, settlement_id: e.target.value }))}
                  placeholder="mis. 202608100001" data-testid="settle-form-id" />
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Nomor dari platform — mencegah satu pencairan tercatat dua kali.</p></div>
              <div><Label className="text-xs">Tanggal uang masuk *</Label>
                <Input type="date" className="mt-1 h-9 bg-background" value={form.settlement_date}
                  onChange={(e) => setForm((f) => ({ ...f, settlement_date: e.target.value }))}
                  data-testid="settle-form-date" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label className="text-xs">Periode dari</Label>
                  <Input type="date" className="mt-1 h-9 bg-background" value={form.period_from}
                    onChange={(e) => setForm((f) => ({ ...f, period_from: e.target.value }))} /></div>
                <div><Label className="text-xs">sampai</Label>
                  <Input type="date" className="mt-1 h-9 bg-background" value={form.period_to}
                    onChange={(e) => setForm((f) => ({ ...f, period_to: e.target.value }))} /></div>
              </div>
            </div>

            <div className="rounded-lg border border-border p-3">
              <p className="text-xs font-semibold mb-2">Rincian dari laporan pencairan</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {MONEY.map(([f, label, sg, hint]) => (
                  <div key={f}>
                    <Label className="text-xs flex items-center gap-1">
                      <span className={sg === '\u2212' ? 'text-red-600' : sg === '+' ? 'text-emerald-600' : 'text-muted-foreground'}>{sg}</span>
                      {label}
                    </Label>
                    <Input type="number" className="mt-1 h-9 bg-background text-right"
                      value={form[f]} placeholder="0"
                      onChange={(e) => setForm((p) => ({ ...p, [f]: e.target.value }))}
                      data-testid={`settle-form-${f}`} />
                    <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3"><Label className="text-xs">Catatan untuk &quot;Potongan lain&quot;</Label>
                <Input className="mt-1 h-9 bg-background" value={form.other_deductions_note}
                  onChange={(e) => setForm((f) => ({ ...f, other_deductions_note: e.target.value }))}
                  placeholder="mis. Biaya program Gratis Ongkir XTRA"
                  data-testid="settle-form-other-note" /></div>
            </div>

            <div className={`rounded-lg border p-3 ${balanced
              ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-900/20'
              : 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/25'}`}>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">Net payout (dari mutasi bank) *</Label>
                  <Input type="number" className="mt-1 h-9 bg-background text-right font-semibold"
                    value={form.net_payout}
                    onChange={(e) => setForm((f) => ({ ...f, net_payout: e.target.value }))}
                    data-testid="settle-form-net" />
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    Angka yang BENAR-BENAR masuk rekening — bukan hasil hitungan.</p></div>
                <div className="text-xs">
                  <p className="text-muted-foreground">Seharusnya (dari rincian di atas)</p>
                  <p className="font-semibold text-sm">{rp(expectedNet)}</p>
                  <p className="mt-1 text-muted-foreground">Selisih</p>
                  <p className={`font-bold text-sm ${balanced ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-800 dark:text-amber-300'}`}
                     data-testid="settle-form-diff">{rp(diff)}</p></div>
              </div>
              {!balanced && (
                <p className="mt-2 text-[11px] text-amber-900 dark:text-amber-200" data-testid="settle-form-diff-hint">
                  <b>Belum seimbang.</b> Selisih ini bukan gangguan — biasanya ia potongan
                  yang belum kita kenal. Catat di <b>Potongan lain</b> atau <b>Penyesuaian</b>
                  beserta keterangannya. Selama belum dinamai, pencairan ini <b>tetap bisa
                  disimpan</b> tetapi <b>belum bisa dijurnal</b>.
                </p>
              )}
            </div>

            <div><Label className="text-xs">Catatan</Label>
              <Textarea rows={2} className="mt-1 bg-background" value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} /></div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)}>
              <X size={14} className="mr-1" />Batal</Button>
            <Button onClick={save} disabled={saving} data-testid="settle-form-save">
              {saving && <Loader2 size={14} className="mr-1 animate-spin" />}
              {editId ? 'Simpan Perubahan' : 'Simpan Pencairan'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
