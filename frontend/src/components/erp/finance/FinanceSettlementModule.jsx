/**
 * FinanceSettlementModule — **Pencairan Marketplace (input & jurnal)** di Portal Keuangan.
 *
 * Kenapa layar ini ada di FINANCE, bukan di Marketing (keputusan pemilik, sesi #37):
 * angka pencairan berasal dari MUTASI BANK dan laporan platform — dua dokumen yang
 * hanya dipegang Keuangan. Marketing memang perlu MELIHAT nominalnya (layar
 * `marketing/MarketingSettlementsView.jsx`), tetapi yang mengetik, mencocokkan, dan
 * menjurnal adalah Keuangan. Backend menegakkan hal yang sama: GET boleh siapa saja
 * yang berhak atas toko itu, POST/PUT/journal/post hanya portal `finance`.
 *
 * Tiga hal yang layar ini SENGAJA tidak sembunyikan:
 *  1. `net_payout` DIISI TANGAN dari mutasi bank — server menghitung "seharusnya
 *     berapa" lalu menampilkan SELISIH-nya. Selisih ≠ 0 ⇒ jurnal ditolak, supaya
 *     potongan yang belum kita kenal terpaksa diberi NAMA, bukan hilang.
 *  2. Rekonsiliasi menampilkan selisih omzet vs pencairan BESERTA NAMANYA
 *     ("pesanan belum cair" / "cair tanpa pesanan") — bukan satu angka gelap.
 *  3. Jurnal memakai akun kas & pendapatan MILIK TOKO. Kalau tokonya belum punya,
 *     tombolnya menolak dengan alasan yang bisa ditindaklanjuti — tidak diam-diam
 *     memakai rekening bawaan.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Banknote, RefreshCw, AlertTriangle, CheckCircle2, Loader2, Store, Percent,
  Plus, Scale, BookCheck, Send, X, Trash2, Pencil, Upload, Landmark,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import { SettlementImportPanel, computeValues } from './SettlementImportPanel';
import { SettlementByStoreCards } from './SettlementByStoreCards';

const API = process.env.REACT_APP_BACKEND_URL;
const BASE = `${API}/api/marketing/settlements`;
const rp = formatRupiah;

function token() { return localStorage.getItem('erp_token'); }

async function call(path, opts = {}) {
  const r = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token()}`,
      ...(opts.headers || {}),
    },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || d.message || `Gagal (HTTP ${r.status})`);
  return d;
}

// Field uang + arahnya terhadap net payout — DISAMAKAN dengan `MONEY_FIELDS`
// di backend. Tandanya ikut ditampilkan supaya staf tahu mana yang menambah dan
// mana yang mengurangi TANPA harus menebak dari namanya.
const MONEY_FIELDS = [
  ['gross_sales', 'Omzet bruto', +1],
  ['refunds', 'Refund / retur', -1],
  ['seller_discount', 'Diskon penjual', -1],
  ['shipping_subsidy', 'Subsidi ongkir platform', +1],
  ['platform_commission', 'Komisi platform', -1],
  ['platform_service_fee', 'Fee layanan platform', -1],
  ['affiliate_commission', 'Komisi afiliasi', -1],
  ['ads_deduction', 'Potongan iklan', -1],
  ['other_deductions', 'Potongan lain', -1],
  ['adjustments', 'Penyesuaian (boleh minus)', +1],
];

const EMPTY = {
  account_id: '', platform: '', settlement_id: '', settlement_date: '',
  period_from: '', period_to: '',
  gross_sales: '', refunds: '', seller_discount: '', shipping_subsidy: '',
  platform_commission: '', platform_service_fee: '', affiliate_commission: '',
  ads_deduction: '', other_deductions: '', adjustments: '',
  net_payout: '', notes: '', other_deductions_note: '',
};

function Kpi({ label, value, hint, tone = 'default', testId, icon: Icon }) {
  const tones = {
    default: 'text-foreground',
    good: 'text-emerald-600 dark:text-emerald-300',
    warn: 'text-amber-600 dark:text-amber-300',
    bad: 'text-red-600 dark:text-red-300',
  };
  return (
    <GlassCard className="p-4" data-testid={testId}>
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-foreground/50">
        {Icon ? <Icon className="w-3.5 h-3.5" /> : null}{label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-foreground/50">{hint}</div> : null}
    </GlassCard>
  );
}

export default function FinanceSettlementModule() {
  const [accounts, setAccounts] = useState([]);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accountId, setAccountId] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState('');

  const [recon, setRecon] = useState(null);
  const [reconFor, setReconFor] = useState('');

  const [importRes, setImportRes] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const fileRef = useRef(null);

  // Filter periode: satu bulan (YYYY-MM) ATAU rentang tanggal bebas. Kosong = semua.
  const [period, setPeriod] = useState({ month: '', from: '', to: '' });
  const range = useMemo(() => {
    if (period.month) {
      const [y, m] = period.month.split('-').map(Number);
      const last = new Date(y, m, 0).getDate();
      return { from: `${period.month}-01`, to: `${period.month}-${String(last).padStart(2, '0')}` };
    }
    return { from: period.from, to: period.to };
  }, [period]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page_size: '50' });
      if (accountId) qs.set('account_id', accountId);
      if (range.from) qs.set('date_from', range.from);
      if (range.to) qs.set('date_to', range.to);
      const d = await call(`?${qs}`);
      setRows(d.data || []);
      setSummary(d.summary || null);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [accountId, range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetch(`${API}/api/marketing/accounts?limit=200`,
      { headers: { Authorization: `Bearer ${token()}` } })
      .then((r) => r.json())
      .then((d) => setAccounts(Array.isArray(d) ? d : (d?.accounts || d?.data || [])))
      .catch(() => {});
  }, []);

  const accName = (id) => (accounts.find((a) => a.id === id)?.account_name) || id || '—';
  const accOf = (id) => accounts.find((a) => a.id === id) || {};

  // Angka "seharusnya" dihitung ULANG DI LAYAR saat staf mengetik — bukan supaya
  // menggantikan server, tetapi supaya selisihnya terlihat SEBELUM disimpan.
  // Menunggu server untuk tahu ada selisih berarti staf harus menyimpan dulu
  // angka yang sudah dia tahu salah.
  const expected = useMemo(() => MONEY_FIELDS.reduce(
    (t, [f, , sign]) => t + sign * (parseFloat(form[f]) || 0), 0), [form]);
  const diff = useMemo(
    () => Math.round(((parseFloat(form.net_payout) || 0) - expected) * 100) / 100,
    [form.net_payout, expected]);

  const openCreate = () => { setForm(EMPTY); setEditId(''); setFormOpen(true); };

  const previewCall = async (file, acc) => {
    const fd = new FormData();
    fd.append('file', file);
    if (acc) fd.append('account_id', acc);
    const r = await fetch(`${BASE}/import/preview`, {
      method: 'POST', headers: { Authorization: `Bearer ${token()}` }, body: fd,
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || `Gagal membaca berkas (HTTP ${r.status})`);
    return d;
  };

  const applyImport = (d, account_id) => {
    const f = { ...EMPTY, account_id };
    MONEY_FIELDS.forEach(([k]) => { f[k] = d.values?.[k] ? String(d.values[k]) : ''; });
    f.net_payout = d.values?.net_payout ? String(d.values.net_payout) : '';
    f.settlement_id = d.settlement_id || '';
    f.settlement_date = d.settlement_date || '';
    f.period_from = d.period_from || '';
    f.period_to = d.period_to || '';
    f.notes = `Diimpor dari ${d.filename} (${d.row_count} baris)`;
    setForm(f); setEditId(''); setFormOpen(true); setImportRes(d);
  };

  const importFile = async (file) => {
    if (!file) return;
    setBusy('import');
    try {
      const hint = accountId || form.account_id || '';
      let d = await previewCall(file, hint);
      const guess = d.platform_guess || '';
      const fits = (id) => id && (!guess || accOf(id).platform === guess);
      // Toko dipilih ULANG tiap impor dari platform yang terdeteksi — jangan mewarisi
      // pilihan impor sebelumnya, karena laporan TikTok bisa diam-diam tersimpan ke toko Shopee.
      let account_id = '';
      if (fits(accountId)) account_id = accountId;
      else if (fits(form.account_id)) account_id = form.account_id;
      else if (guess) {
        const cand = accounts.filter((a) => a.platform === guess);
        if (cand.length === 1) account_id = cand[0].id;
      }
      // Pemetaan tersimpan milik TOKO; bila toko akhirnya berbeda dari petunjuk awal, baca ulang.
      if (account_id && account_id !== hint) d = await previewCall(file, account_id);
      applyImport(d, account_id);
      if (!account_id) toast.warning(`Toko belum dipilih — laporan terdeteksi ${guess || 'tanpa platform'}; pilih toko yang benar sebelum menyimpan.`);
      toast.success(d.mapping_source === 'saved'
        ? 'Format laporan dikenali — pemetaan tersimpan dipakai. Periksa sekilas lalu simpan.'
        : `${Object.keys(d.mapping || {}).length} field terisi dari tebakan otomatis — periksa pemetaan kolom lalu simpan.`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy('');
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  // Staf mengubah tujuan kolom → angka form dihitung ulang dengan rumus yang sama seperti server.
  const changeMapping = (mapping) => {
    if (!importRes) return;
    const values = computeValues(mapping, importRes.column_totals || {});
    setImportRes({ ...importRes, mapping, values, mapping_source: 'edited' });
    setForm((prev) => {
      const f = { ...prev };
      MONEY_FIELDS.forEach(([k]) => { f[k] = values[k] ? String(values[k]) : ''; });
      f.net_payout = values.net_payout ? String(values.net_payout) : '';
      return f;
    });
  };

  const rememberMapping = async (account_id) => {
    if (!importRes?.mapping) return;
    try {
      await call('/import/mapping', {
        method: 'POST',
        body: JSON.stringify({
          account_id, headers: importRes.headers || importRes.numeric_columns || [], mapping: importRes.mapping,
          meta_columns: importRes.meta_columns || {}, filename: importRes.filename || '',
        }),
      });
      toast.message('Pemetaan kolom diingat untuk toko & format laporan ini.');
    } catch (e) {
      toast.warning(`Pencairan tersimpan, tetapi pemetaan kolom gagal diingat: ${e.message}`);
    }
  };
  const openEdit = (r) => {
    const f = { ...EMPTY };
    Object.keys(EMPTY).forEach((k) => { f[k] = r[k] ?? ''; });
    setForm(f); setEditId(r.id); setFormOpen(true);
  };

  const save = async () => {
    if (!form.account_id) { toast.error('Pilih toko dulu.'); return; }
    if (!form.settlement_id.trim()) { toast.error('Nomor pencairan wajib diisi.'); return; }
    if (!form.settlement_date) { toast.error('Tanggal uang masuk wajib diisi.'); return; }
    if (importRes?.platform_guess && accOf(form.account_id).platform
        && accOf(form.account_id).platform !== importRes.platform_guess) {
      toast.error(`Laporan terdeteksi ${importRes.platform_guess}, tetapi toko yang dipilih ada di ${accOf(form.account_id).platform}. Pilih toko yang sesuai.`);
      return;
    }
    const body = { ...form, platform: accOf(form.account_id).platform || form.platform || '' };
    MONEY_FIELDS.forEach(([f]) => { body[f] = parseFloat(form[f]) || 0; });
    body.net_payout = parseFloat(form.net_payout) || 0;
    setBusy('save');
    try {
      const d = editId
        ? await call(`/${editId}`, { method: 'PUT', body: JSON.stringify(body) })
        : await call('', { method: 'POST', body: JSON.stringify(body) });
      toast.success(d.data?.math_verified
        ? 'Pencairan tersimpan dan angkanya seimbang.'
        : `Tersimpan, tetapi masih ada selisih ${rp(d.data?.net_payout_diff || 0)} — beri nama dulu sebelum dijurnal.`);
      setFormOpen(false);
      if (!editId && importRes) await rememberMapping(form.account_id);
      setImportRes(null);
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally { setBusy(''); }
  };

  const act = async (r, kind) => {
    setBusy(`${kind}:${r.id}`);
    try {
      if (kind === 'journal') {
        const d = await call(`/${r.id}/journal`, { method: 'POST' });
        toast.success(d.message || `Jurnal ${d.je_number} dibuat.`);
      } else if (kind === 'post') {
        const d = await call(`/${r.id}/post`, { method: 'POST' });
        toast.success(d.message || `Jurnal ${d.je_number} diposting.`);
      } else if (kind === 'delete') {
        await call(`/${r.id}`, { method: 'DELETE' });
        toast.success('Pencairan dihapus.');
      }
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally { setBusy(''); }
  };

  const reconcile = async (r) => {
    setBusy(`recon:${r.id}`);
    try {
      const d = await call(`/reconcile?settlement_id=${encodeURIComponent(r.settlement_id)}`);
      setRecon(d); setReconFor(r.settlement_id);
    } catch (e) {
      toast.error(e.message);
    } finally { setBusy(''); }
  };

  return (
    <div className="space-y-4" data-testid="finance-settlement-module">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Banknote className="w-5 h-5" /> Pencairan Marketplace
          </h2>
          <p className="text-xs text-foreground/60 mt-0.5 max-w-3xl">
            Catat uang yang benar-benar masuk rekening dari Shopee/TikTok beserta potongan
            platformnya. <b>Nominal dicairkan diambil dari mutasi bank</b> — bukan dihitung
            sistem; sistem justru menampilkan selisihnya supaya potongan yang belum dikenal
            terpaksa diberi nama. Marketing hanya melihat hasilnya.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select data-testid="fin-settlement-account-filter" value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm">
            <option value="">Semua toko</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.account_name} · {a.platform}</option>
            ))}
          </select>
          <div className="flex items-center gap-1 h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-xs"
            data-testid="fin-settlement-period-filter">
            <input type="month" data-testid="fin-settlement-filter-month" value={period.month}
              title="Filter satu bulan"
              onChange={(e) => setPeriod({ month: e.target.value, from: '', to: '' })}
              className="h-7 bg-transparent text-xs" />
            <span className="text-foreground/40">atau</span>
            <input type="date" data-testid="fin-settlement-filter-from" value={period.from}
              title="Dari tanggal"
              onChange={(e) => setPeriod({ month: '', from: e.target.value, to: period.to })}
              className="h-7 bg-transparent text-xs" />
            <span className="text-foreground/40">–</span>
            <input type="date" data-testid="fin-settlement-filter-to" value={period.to}
              title="Sampai tanggal"
              onChange={(e) => setPeriod({ month: '', from: period.from, to: e.target.value })}
              className="h-7 bg-transparent text-xs" />
            {(period.month || period.from || period.to) ? (
              <button data-testid="fin-settlement-filter-clear" title="Hapus filter periode"
                onClick={() => setPeriod({ month: '', from: '', to: '' })}
                className="p-1 rounded hover:bg-foreground/10"><X className="w-3.5 h-3.5" /></button>
            ) : null}
          </div>
          <button data-testid="fin-settlement-refresh" onClick={load}
            className="h-9 px-3 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4" /> Muat ulang
          </button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.tsv" className="hidden"
            data-testid="fin-settlement-import-file"
            onChange={(e) => importFile(e.target.files?.[0])} />
          <button data-testid="fin-settlement-import" disabled={busy === 'import'}
            onClick={() => fileRef.current?.click()}
            title="Unggah laporan Penghasilan (Shopee) / Settlement (TikTok) untuk mengisi form"
            className="h-9 px-3 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm flex items-center gap-1.5 disabled:opacity-50">
            {busy === 'import' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Impor laporan
          </button>
          <button data-testid="fin-settlement-new" onClick={openCreate}
            className="h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Catat pencairan
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi testId="fin-settlement-kpi-net" icon={Banknote} label="Total dicairkan"
          value={rp(summary?.net_payout || 0)} tone="good"
          hint={`${rows.length} pencairan tercatat${range.from || range.to ? ` · ${range.from || '…'} → ${range.to || '…'}` : ''} · ${summary?.bank_linked_count || 0} tertaut mutasi bank`} />
        <Kpi testId="fin-settlement-kpi-gross" icon={Store} label="Omzet bruto terkait"
          value={rp(summary?.gross_sales || 0)} />
        <Kpi testId="fin-settlement-kpi-ded" icon={Percent} label="Potongan platform"
          value={rp(summary?.total_deductions || 0)}
          hint={`${summary?.deduction_pct || 0}% dari bruto`} tone="warn" />
        <Kpi testId="fin-settlement-kpi-unverified" icon={AlertTriangle} label="Belum seimbang"
          value={`${summary?.unverified_count || 0} dokumen`}
          tone={(summary?.unverified_count || 0) > 0 ? 'bad' : 'good'}
          hint="selisih belum diberi nama — belum boleh dijurnal" />
      </div>

      {/* ── HASIL IMPOR ── */}
      <SettlementImportPanel result={importRes} onClose={() => setImportRes(null)}
        onMappingChange={changeMapping} />

      {/* ── FORM ── */}
      {formOpen ? (
        <GlassCard className="p-4 space-y-3" data-testid="fin-settlement-form">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-sm">
              {editId ? 'Koreksi pencairan' : 'Catat pencairan baru'}
            </h3>
            <button data-testid="fin-settlement-form-close" onClick={() => setFormOpen(false)}
              className="p-1 rounded hover:bg-foreground/10"><X className="w-4 h-4" /></button>
          </div>

          <div className="grid md:grid-cols-4 gap-3">
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">Toko</span>
              <select data-testid="fin-settlement-input-account" value={form.account_id}
                onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm">
                <option value="">— pilih toko —</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.account_name} · {a.platform}</option>
                ))}
              </select>
            </label>
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">No. pencairan (dari platform)</span>
              <input data-testid="fin-settlement-input-settlement-id" value={form.settlement_id}
                onChange={(e) => setForm({ ...form, settlement_id: e.target.value })}
                placeholder="mis. 2026081512345"
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm font-mono" />
            </label>
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">Tanggal uang masuk</span>
              <input type="date" data-testid="fin-settlement-input-date" value={form.settlement_date}
                onChange={(e) => setForm({ ...form, settlement_date: e.target.value })}
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm" />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs space-y-1">
                <span className="text-foreground/60">Periode dari</span>
                <input type="date" data-testid="fin-settlement-input-period-from" value={form.period_from}
                  onChange={(e) => setForm({ ...form, period_from: e.target.value })}
                  className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm" />
              </label>
              <label className="text-xs space-y-1">
                <span className="text-foreground/60">sampai</span>
                <input type="date" data-testid="fin-settlement-input-period-to" value={form.period_to}
                  onChange={(e) => setForm({ ...form, period_to: e.target.value })}
                  className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm" />
              </label>
            </div>
          </div>

          <div className="grid md:grid-cols-5 gap-3">
            {MONEY_FIELDS.map(([f, label, sign]) => (
              <label key={f} className="text-xs space-y-1">
                <span className="text-foreground/60">
                  {label} <span className={sign > 0 ? 'text-emerald-600' : 'text-red-500'}>
                    ({sign > 0 ? '+' : '−'})</span>
                </span>
                <input type="number" step="1" data-testid={`fin-settlement-input-${f}`}
                  value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })}
                  className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm text-right tabular-nums" />
              </label>
            ))}
          </div>

          <div className="grid md:grid-cols-3 gap-3">
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">
                Nominal dicairkan <b>menurut mutasi bank</b>
              </span>
              <input type="number" step="1" data-testid="fin-settlement-input-net-payout"
                value={form.net_payout}
                onChange={(e) => setForm({ ...form, net_payout: e.target.value })}
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm text-right tabular-nums font-semibold" />
            </label>
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">Keterangan "potongan lain"</span>
              <input data-testid="fin-settlement-input-other-note" value={form.other_deductions_note}
                onChange={(e) => setForm({ ...form, other_deductions_note: e.target.value })}
                placeholder="wajib bila ada potongan lain"
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm" />
            </label>
            <label className="text-xs space-y-1">
              <span className="text-foreground/60">Catatan</span>
              <input data-testid="fin-settlement-input-notes" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="w-full h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm" />
            </label>
          </div>

          <div className={`text-xs rounded-lg px-3 py-2 ${Math.abs(diff) < 0.01
            ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
            : 'bg-red-500/10 text-red-700 dark:text-red-300'}`}
            data-testid="fin-settlement-diff">
            Hasil hitung dari rincian: <b>{rp(expected)}</b> · yang diisi:{' '}
            <b>{rp(parseFloat(form.net_payout) || 0)}</b> · selisih: <b>{rp(diff)}</b>
            {Math.abs(diff) < 0.01
              ? ' — seimbang, boleh dijurnal.'
              : ' — beri nama dulu di "Potongan lain" atau "Penyesuaian"; jurnal akan ditolak selama masih ada selisih.'}
          </div>

          <div className="flex gap-2">
            <button data-testid="fin-settlement-save" disabled={busy === 'save'} onClick={save}
              className="h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm flex items-center gap-1.5 disabled:opacity-50">
              {busy === 'save' ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              Simpan
            </button>
            <button data-testid="fin-settlement-cancel" onClick={() => setFormOpen(false)}
              className="h-9 px-4 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm">Batal</button>
          </div>
        </GlassCard>
      ) : null}

      {/* ── HASIL COCOK ── */}
      {recon ? (
        <GlassCard className="p-4 space-y-2" data-testid="fin-settlement-recon">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-sm flex items-center gap-2">
              <Scale className="w-4 h-4" /> Pencocokan {reconFor}
              <span className="text-xs text-foreground/50">
                periode {recon.period?.from || '—'} → {recon.period?.to || '—'}
              </span>
            </h3>
            <button data-testid="fin-settlement-recon-close" onClick={() => setRecon(null)}
              className="p-1 rounded hover:bg-foreground/10"><X className="w-4 h-4" /></button>
          </div>
          <div className="grid md:grid-cols-3 gap-3 text-xs">
            <div className="rounded-lg bg-foreground/5 p-3">
              <div className="text-foreground/50 uppercase tracking-wide">Pencairan</div>
              <div className="mt-1">bruto <b>{rp(recon.settlement?.gross_sales || 0)}</b></div>
              <div>dicairkan <b>{rp(recon.settlement?.net_payout || 0)}</b></div>
              <div>potongan <b>{rp(recon.settlement?.total_deductions || 0)}</b>{' '}
                ({recon.settlement?.deduction_pct || 0}%)</div>
            </div>
            <div className="rounded-lg bg-foreground/5 p-3">
              <div className="text-foreground/50 uppercase tracking-wide">
                Omzet pesanan periode ({recon.marketing?.order_count || 0} pesanan)
              </div>
              <div className="mt-1">bruto <b>{rp(recon.marketing?.revenue_gross || 0)}</b></div>
              <div>setelah diskon <b>{rp(recon.marketing?.revenue_product || 0)}</b></div>
              <div>dibayar pembeli <b>{rp(recon.marketing?.order_amount || 0)}</b></div>
            </div>
            <div className="rounded-lg bg-foreground/5 p-3">
              <div className="text-foreground/50 uppercase tracking-wide">Selisih bruto</div>
              <div className="mt-1 text-lg font-semibold">
                {rp(recon.gap?.gross_vs_revenue_gross || 0)}
              </div>
              <div className="text-foreground/50">
                {recon.gap?.cancelled_orders_excluded || 0} pesanan batal dikecualikan
              </div>
            </div>
          </div>
          <ul className="space-y-1.5" data-testid="fin-settlement-recon-named">
            {(recon.gap?.named || []).map((g) => (
              <li key={g.name} className="text-xs rounded-lg bg-foreground/5 px-3 py-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">{g.name}</Badge>
                  {g.amount ? <b>{rp(g.amount)}</b> : null}
                </div>
                <div className="mt-0.5 text-foreground/70">{g.label}</div>
                <div className="text-foreground/50">{g.action}</div>
              </li>
            ))}
          </ul>
        </GlassCard>
      ) : null}

      {/* ── PER TOKO ── */}
      <SettlementByStoreCards refreshKey={refreshKey} month={period.month} />

      {/* ── DAFTAR ── */}
      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="py-12 text-center text-sm text-foreground/50 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> memuat pencairan…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-sm text-foreground/60 px-6" data-testid="fin-settlement-empty">
            Belum ada pencairan tercatat{accountId ? ' untuk toko ini' : ''}{range.from || range.to ? ' pada periode ini' : ''}.
            <div className="mt-1 text-xs text-foreground/50">
              Buka mutasi bank, lalu tekan “Catat pencairan”.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="fin-settlement-table">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-foreground/50 border-b border-foreground/10">
                  <th className="text-left py-2 px-3">Tanggal</th>
                  <th className="text-left py-2 px-3">No. Pencairan</th>
                  <th className="text-left py-2 px-3">Toko / Platform</th>
                  <th className="text-right py-2 px-3">Bruto</th>
                  <th className="text-right py-2 px-3">Potongan</th>
                  <th className="text-right py-2 px-3">Dicairkan</th>
                  <th className="text-left py-2 px-3">Status</th>
                  <th className="text-left py-2 px-3">Jurnal</th>
                  <th className="text-right py-2 px-3">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-foreground/5"
                    data-testid={`fin-settlement-row-${r.settlement_id}`}>
                    <td className="py-2 px-3">{r.settlement_date || '—'}</td>
                    <td className="py-2 px-3 font-mono text-xs">{r.settlement_id}</td>
                    <td className="py-2 px-3">
                      {accName(r.account_id)}
                      <span className="ml-1 text-xs text-foreground/50 uppercase">{r.platform}</span>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">{rp(r.gross_sales || 0)}</td>
                    <td className="py-2 px-3 text-right tabular-nums text-amber-600 dark:text-amber-300">
                      {rp(r.total_deductions || 0)}
                      {r.deduction_pct ? (
                        <span className="text-xs text-foreground/50"> ({r.deduction_pct}%)</span>
                      ) : null}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-medium">
                      {rp(r.net_payout || 0)}
                      {r.bank_txn_id ? (
                        <div className="text-[10px] text-emerald-600 flex items-center justify-end gap-0.5"
                          title={`Tertaut ke mutasi bank tanggal ${r.bank_txn_date}`}
                          data-testid={`fin-settlement-bank-linked-${r.settlement_id}`}>
                          <Landmark className="w-3 h-3" /> mutasi {r.bank_txn_date}
                        </div>
                      ) : (
                        <div className="text-[10px] text-foreground/40" data-testid={`fin-settlement-bank-unlinked-${r.settlement_id}`}>
                          belum tertaut bank
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {r.math_verified ? (
                        <Badge variant="outline" className="text-[10px] text-emerald-600">
                          <CheckCircle2 className="w-3 h-3 mr-1" /> seimbang
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-red-600">
                          <AlertTriangle className="w-3 h-3 mr-1" /> selisih {rp(r.net_payout_diff || 0)}
                        </Badge>
                      )}
                    </td>
                    <td className="py-2 px-3 text-xs">
                      {r.je_number
                        ? <span className="font-mono">{r.je_number}
                          <span className="ml-1 text-foreground/50">({r.je_status})</span></span>
                        : <span className="text-foreground/40">belum</span>}
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center justify-end gap-1">
                        <button title="Cocokkan dengan omzet periode"
                          data-testid={`fin-settlement-reconcile-${r.settlement_id}`}
                          disabled={busy === `recon:${r.id}`} onClick={() => reconcile(r)}
                          className="p-1.5 rounded hover:bg-foreground/10 disabled:opacity-40">
                          <Scale className="w-4 h-4" />
                        </button>
                        {!r.je_id ? (
                          <button title="Buat jurnal draf"
                            data-testid={`fin-settlement-journal-${r.settlement_id}`}
                            disabled={busy === `journal:${r.id}`} onClick={() => act(r, 'journal')}
                            className="p-1.5 rounded hover:bg-foreground/10 disabled:opacity-40">
                            <BookCheck className="w-4 h-4" />
                          </button>
                        ) : null}
                        {r.je_status === 'draft' ? (
                          <button title="Posting jurnal ke buku besar"
                            data-testid={`fin-settlement-post-${r.settlement_id}`}
                            disabled={busy === `post:${r.id}`} onClick={() => act(r, 'post')}
                            className="p-1.5 rounded hover:bg-foreground/10 text-emerald-600 disabled:opacity-40">
                            <Send className="w-4 h-4" />
                          </button>
                        ) : null}
                        {!r.je_id ? (
                          <>
                            <button title={r.bank_txn_id ? 'Koreksi angka (nominal dicairkan terkunci oleh tautan bank)' : 'Koreksi angka'}
                              data-testid={`fin-settlement-edit-${r.settlement_id}`}
                              onClick={() => openEdit(r)}
                              className="p-1.5 rounded hover:bg-foreground/10">
                              <Pencil className="w-4 h-4" />
                            </button>
                            {!r.bank_txn_id ? (
                              <button title="Hapus"
                                data-testid={`fin-settlement-delete-${r.settlement_id}`}
                                disabled={busy === `delete:${r.id}`} onClick={() => act(r, 'delete')}
                                className="p-1.5 rounded hover:bg-foreground/10 text-red-600 disabled:opacity-40">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
