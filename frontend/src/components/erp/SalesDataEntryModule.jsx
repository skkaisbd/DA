import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  TrendingUp, Plus, RefreshCw, Loader2, Calendar, Lock, Calculator,
  AlertTriangle, ShieldAlert,
} from 'lucide-react';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './marketing/ActiveAccountBar';
import { AccountBadge, getPlatformConfig } from './marketing/AccountBadge';
// F10 (sesi #10) — angka omzet harian wajib bisa dibawa keluar layar (rapat/akuntansi).
import ExportCsvButton from '@/components/ui/export-csv-button';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PageHeader } from './moduleAtoms';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;
const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID');

function SalesDataEntryDialog({ open, onOpenChange, onSaved, token, accounts, preSelectedAccountId }) {
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState('total');
  // F2 (2026-08-12) — JALAN KELUAR SPV. Backend sudah punya jalur
  // `POST /sales-data?override=true&override_reason=…` sejak F2, tetapi TIDAK ADA
  // satu pun layar yang memanggilnya: staf hanya melihat penolakan 409 dan
  // kebuntuan. Tiga state di bawah membuat kuncinya bisa dijelaskan DAN dibuka
  // oleh yang berwenang, dengan alasan yang tercatat.
  const [existingRow, setExistingRow] = useState(null);   // baris rekap yang sudah ada
  const [checkingLock, setCheckingLock] = useState(false);
  const [overrideMode, setOverrideMode] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [saveError, setSaveError] = useState('');          // pesan galat yang MENETAP
  const [form, setForm] = useState({
    account_id: '',
    date: new Date().toISOString().slice(0, 10),
    revenue: '',
    orders: '',
    aov: '',
    gmv: '',
    conversion_rate: '',
    fulfillment_rate: '',
    cancellation_rate: '',
    return_rate: '',
    late_shipment_rate: '',
    rating: '',
    review_count: '',
    response_rate: '',
    response_time_hours: '',
    // live-only
    viewers: '',
    avg_viewers: '',
    likes: '',
    shares: '',
    comments: '',
    new_followers: '',
    live_sessions: '',
  });

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => {
    if (!open) {
      // reset form on close
      setActiveTab('total');
      setForm({
        account_id: preSelectedAccountId || '',
        date: new Date().toISOString().slice(0, 10),
        revenue: '',
        orders: '',
        aov: '',
        gmv: '',
        conversion_rate: '',
        fulfillment_rate: '',
        cancellation_rate: '',
        return_rate: '',
        late_shipment_rate: '',
        rating: '',
        review_count: '',
        response_rate: '',
        response_time_hours: '',
        viewers: '',
        avg_viewers: '',
        likes: '',
        shares: '',
        comments: '',
        new_followers: '',
        live_sessions: '',
      });
    } else if (open && preSelectedAccountId) {
      setForm(f => ({ ...f, account_id: preSelectedAccountId }));
    }
  }, [open, preSelectedAccountId]);

  const num = (v) => v === '' || v === null ? null : parseFloat(v);

  /* ── F2 — apakah (toko, tanggal, tipe) ini angkanya TURUNAN? ──────────────
     Diperiksa SEBELUM tombol simpan ditekan supaya staf tahu kuncinya lebih
     dulu, bukan setelah formnya diisi penuh lalu ditolak 409.                */
  useEffect(() => {
    if (!open || !form.account_id || !form.date) { setExistingRow(null); return; }
    let alive = true;
    (async () => {
      setCheckingLock(true);
      try {
        const qs = new URLSearchParams({
          date_from: form.date, date_to: form.date, revenue_type: activeTab,
        });
        const r = await fetch(
          `/api/marketing/accounts/${form.account_id}/sales?${qs.toString()}`, { headers });
        const list = r.ok ? await r.json().catch(() => []) : [];
        if (alive) setExistingRow(Array.isArray(list) && list.length ? list[0] : null);
      } catch (e) {
        if (alive) setExistingRow(null);
      } finally {
        if (alive) setCheckingLock(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, form.account_id, form.date, activeTab]);

  const derivedRow = !!existingRow
    && (existingRow.locked_source === true || existingRow.source === 'orders_auto');
  const lockedMetrics = derivedRow && !overrideMode;
  const existingMetrics = existingRow?.metrics || {};

  useEffect(() => {
    // ganti tanggal / toko / tipe ⇒ mode override & galat lama tidak boleh menempel
    setOverrideMode(false);
    setOverrideReason('');
    setSaveError('');
  }, [form.account_id, form.date, activeTab]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaveError('');
    if (!form.account_id) {
      toast.error('Pilih akun terlebih dahulu');
      return;
    }
    if (!form.date) {
      toast.error('Tanggal wajib diisi');
      return;
    }
    if (overrideMode && overrideReason.trim().length < 5) {
      const msg = 'Alasan penggantian wajib diisi (minimal 5 huruf) — inilah yang '
        + 'membuat perubahan angka bisa dipertanggungjawabkan.';
      setSaveError(msg);
      toast.error(msg, { duration: 9000 });
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        account_id: form.account_id,
        date: form.date,
        revenue_type: activeTab,
        revenue: num(form.revenue) || 0,
        orders: num(form.orders) || 0,
        aov: num(form.aov),
        gmv: num(form.gmv),
        conversion_rate: num(form.conversion_rate),
        fulfillment_rate: num(form.fulfillment_rate),
        cancellation_rate: num(form.cancellation_rate),
        return_rate: num(form.return_rate),
        late_shipment_rate: num(form.late_shipment_rate),
        rating: num(form.rating),
        review_count: num(form.review_count),
        response_rate: num(form.response_rate),
        response_time_hours: num(form.response_time_hours),
      };

      if (activeTab === 'live') {
        payload.viewers = num(form.viewers);
        payload.avg_viewers = num(form.avg_viewers);
        payload.likes = num(form.likes);
        payload.shares = num(form.shares);
        payload.comments = num(form.comments);
        payload.new_followers = num(form.new_followers);
        payload.live_sessions = num(form.live_sessions);
      }

      const url = overrideMode
        ? `/api/marketing/sales-data?override=true&override_reason=${encodeURIComponent(overrideReason.trim())}`
        : '/api/marketing/sales-data';
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = err.detail || `Gagal menyimpan data (HTTP ${res.status})`;
        const e2 = new Error(detail);
        e2.status = res.status;
        throw e2;
      }

      toast.success(overrideMode
        ? 'Angka diganti (override SPV) dan alasannya dicatat'
        : `Data ${activeTab === 'total' ? 'Total Revenue' : 'Live Revenue'} berhasil disimpan`);
      setOverrideMode(false);
      setOverrideReason('');
      onOpenChange(false);
      if (onSaved) onSaved();
    } catch (err) {
      // Pesan 409/403/400 dari F2 panjang dan berisi JALAN KELUAR — kalau hanya
      // lewat toast 4 detik, staf tidak pernah selesai membacanya. Karena itu
      // pesan yang sama juga DITAHAN di dalam form sampai datanya diubah.
      setSaveError(err.message);
      toast.error(err.message, { duration: 12000 });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="sales-data-dialog">
        <DialogHeader>
          <DialogTitle>Input Sales Harian</DialogTitle>
          <DialogDescription>
            Pilih akun dan tab Total/Live, lalu masukkan metrics. Health score akan otomatis di-recalculate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Akun <span className="text-red-400">*</span></Label>
              <Select value={form.account_id} onValueChange={v => setForm(f => ({ ...f, account_id: v }))}>
                <SelectTrigger data-testid="sd-account-select"><SelectValue placeholder="Pilih akun" /></SelectTrigger>
                <SelectContent>
                  {accounts?.map(a => (
                    <SelectItem key={a.id} value={a.id}>{a.account_name} ({a.platform})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* Visual confirmation: akun yang dipilih */}
              {form.account_id && (() => {
                const acc = accounts?.find(a => a.id === form.account_id);
                const cfg = acc ? getPlatformConfig(acc.platform) : null;
                return acc ? (
                  <div className={`mt-1.5 flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs ${cfg.bg} ${cfg.border} ${cfg.text}`}>
                    <span>{cfg.icon}</span>
                    <span className="font-medium">Input ke: {acc.account_name}</span>
                  </div>
                ) : null;
              })()}
            </div>
            <div>
              <Label htmlFor="sd-date">Tanggal <span className="text-red-400">*</span></Label>
              <GlassInput
                id="sd-date"
                type="date"
                value={form.date}
                onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                data-testid="sd-date-input"
                required
              />
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="total" data-testid="tab-total">📊 Total Revenue</TabsTrigger>
              <TabsTrigger value="live" data-testid="tab-live">🎥 Live Revenue</TabsTrigger>
            </TabsList>

            {/* F2 — KUNCI ANGKA TURUNAN + jalan keluar SPV */}
            {checkingLock && (
              <p className="mt-3 text-xs text-muted-foreground flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" /> memeriksa sumber angka tanggal ini…
              </p>
            )}
            {derivedRow && (
              <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 space-y-2"
                data-testid="sd-locked-notice">
                <p className="text-xs flex items-start gap-2">
                  <Lock size={13} className="mt-0.5 shrink-0 text-amber-500" />
                  <span>
                    <b>Angka {form.date} diturunkan dari pesanan toko ini</b> — omzet{' '}
                    <b>{fmt(existingMetrics.revenue)}</b> dari{' '}
                    <b>{fmtNum(existingMetrics.orders)} pesanan</b>. Kolom <b>Revenue</b> dan{' '}
                    <b>Orders</b> dikunci supaya tidak ada dua angka omzet untuk satu hari.
                    Kalau angkanya salah, perbaiki <b>pesanannya</b> (menu Impor Data /
                    Order Terpadu) — bukan diketik ulang di sini.
                  </span>
                </p>
                {!overrideMode ? (
                  <Button type="button" size="sm" variant="outline"
                    className="border-amber-500/50 text-amber-600 dark:text-amber-400"
                    onClick={() => {
                      // Angka turunan dipakai sebagai TITIK AWAL: SPV hampir selalu
                      // hanya mengoreksi sebagian, dan mengetik ulang 7 angka dari
                      // nol adalah cara paling mudah membuat kesalahan baru.
                      setForm(f => ({
                        ...f,
                        revenue: f.revenue || String(existingMetrics.revenue ?? ''),
                        orders: f.orders || String(existingMetrics.orders ?? ''),
                      }));
                      setOverrideMode(true);
                    }} data-testid="sd-override-btn">
                    <ShieldAlert size={13} className="mr-1.5" /> Ganti Angka (Override SPV)
                  </Button>
                ) : (
                  <div className="space-y-1.5">
                    <Label className="text-xs">
                      Alasan penggantian <span className="text-red-400">*</span>
                    </Label>
                    <textarea
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                      rows={2}
                      placeholder="mis. ekspor Seller Center hari itu belum lengkap, angka dari dashboard platform"
                      data-testid="sd-override-reason"
                      className="w-full rounded-md border border-border bg-[hsl(var(--background))]
                        px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground
                        focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                    <p className="text-[11px] text-muted-foreground">
                      Alasan ini tercatat beserta nama & waktu, dan angka hasil override
                      TIDAK akan ditimpa perhitungan otomatis berikutnya.
                    </p>
                    <Button type="button" size="sm" variant="ghost"
                      onClick={() => { setOverrideMode(false); setOverrideReason(''); }}
                      data-testid="sd-override-cancel">
                      Batalkan override
                    </Button>
                  </div>
                )}
              </div>
            )}
            {saveError && (
              <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs
                flex items-start gap-2" data-testid="sd-save-error">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-red-500" />
                <span>{saveError}</span>
              </div>
            )}

            <TabsContent value="total" className="space-y-3 mt-4">
              <div className="text-xs text-muted-foreground">Total penjualan dari semua channel (regular + live).</div>
              <CommonMetricsForm form={form} setForm={setForm} lockedMetrics={lockedMetrics} />
            </TabsContent>

            <TabsContent value="live" className="space-y-3 mt-4">
              <div className="text-xs text-muted-foreground">Khusus penjualan dari live streaming.</div>
              <CommonMetricsForm form={form} setForm={setForm} lockedMetrics={lockedMetrics} />
              <div className="pt-3 border-t border-[var(--glass-border)]">
                <div className="text-sm font-semibold mb-2">Engagement Metrics (Live Only)</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <NumField label="Viewers" testId="sd-viewers" value={form.viewers} onChange={v => setForm(f => ({ ...f, viewers: v }))} />
                  <NumField label="Avg Viewers" testId="sd-avg-viewers" value={form.avg_viewers} onChange={v => setForm(f => ({ ...f, avg_viewers: v }))} />
                  <NumField label="Likes" testId="sd-likes" value={form.likes} onChange={v => setForm(f => ({ ...f, likes: v }))} />
                  <NumField label="Shares" testId="sd-shares" value={form.shares} onChange={v => setForm(f => ({ ...f, shares: v }))} />
                  <NumField label="Comments" testId="sd-comments" value={form.comments} onChange={v => setForm(f => ({ ...f, comments: v }))} />
                  <NumField label="New Followers" testId="sd-followers" value={form.new_followers} onChange={v => setForm(f => ({ ...f, new_followers: v }))} />
                  <NumField label="Live Sessions" testId="sd-sessions" value={form.live_sessions} onChange={v => setForm(f => ({ ...f, live_sessions: v }))} />
                </div>
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              Batal
            </Button>
            <Button type="submit"
              disabled={submitting}
              title={derivedRow && !overrideMode
                ? 'Angka tanggal ini diturunkan dari pesanan — pakai "Ganti Angka (Override SPV)"'
                : undefined}
              data-testid="sd-submit-btn">
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {overrideMode ? 'Simpan Override' : 'Simpan'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NumField({ label, value, onChange, testId, step = '0.01', disabled = false, hint }) {
  return (
    <div>
      <Label className="text-xs flex items-center gap-1">
        {label}
        {disabled && <Lock size={9} className="text-amber-500" />}
      </Label>
      <GlassInput
        type="number"
        step={step}
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        readOnly={disabled}
        className={disabled ? 'opacity-60 cursor-not-allowed' : undefined}
        data-testid={testId}
      />
      {disabled && hint && (
        <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">{hint}</p>
      )}
    </div>
  );
}

function CommonMetricsForm({ form, setForm, lockedMetrics = false }) {
  // F2 — hanya Revenue & Orders yang DITURUNKAN dari pesanan; sisanya (AOV/GMV/CR
  // dan grup fulfillment/kepuasan) tetap boleh diisi manusia karena tidak ada di
  // ekspor pesanan. Mengunci semuanya akan membuat staf tidak bisa melengkapi
  // data yang memang hanya dia punya.
  const lockHint = 'diturunkan dari pesanan';
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <NumField label="Revenue (Rp)" testId="sd-revenue" value={form.revenue} onChange={v => setForm(f => ({ ...f, revenue: v }))} disabled={lockedMetrics} hint={lockHint} />
        <NumField label="Orders" testId="sd-orders" value={form.orders} onChange={v => setForm(f => ({ ...f, orders: v }))} disabled={lockedMetrics} hint={lockHint} />
        <NumField label="AOV" testId="sd-aov" value={form.aov} onChange={v => setForm(f => ({ ...f, aov: v }))} />
        <NumField label="GMV" testId="sd-gmv" value={form.gmv} onChange={v => setForm(f => ({ ...f, gmv: v }))} />
          <NumField label="Conversion Rate (%)" testId="sd-cr" value={form.conversion_rate} onChange={v => setForm(f => ({ ...f, conversion_rate: v }))} />
      </div>
      <details className="rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)] px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium">Fulfillment & Customer Satisfaction (opsional)</summary>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-3">
          <NumField label="Fulfillment Rate (%)" testId="sd-fr" value={form.fulfillment_rate} onChange={v => setForm(f => ({ ...f, fulfillment_rate: v }))} />
          <NumField label="Cancellation Rate (%)" testId="sd-canc" value={form.cancellation_rate} onChange={v => setForm(f => ({ ...f, cancellation_rate: v }))} />
          <NumField label="Return Rate (%)" testId="sd-ret" value={form.return_rate} onChange={v => setForm(f => ({ ...f, return_rate: v }))} />
          <NumField label="Late Shipment Rate (%)" testId="sd-late" value={form.late_shipment_rate} onChange={v => setForm(f => ({ ...f, late_shipment_rate: v }))} />
          <NumField label="Rating (0-5)" testId="sd-rating" value={form.rating} onChange={v => setForm(f => ({ ...f, rating: v }))} />
          <NumField label="Review Count" testId="sd-review-count" value={form.review_count} onChange={v => setForm(f => ({ ...f, review_count: v }))} />
          <NumField label="Response Rate (%)" testId="sd-resp-rate" value={form.response_rate} onChange={v => setForm(f => ({ ...f, response_rate: v }))} />
          <NumField label="Response Time (hours)" testId="sd-resp-time" value={form.response_time_hours} onChange={v => setForm(f => ({ ...f, response_time_hours: v }))} />
        </div>
      </details>
    </div>
  );
}


/**
 * F2 — dari mana angka baris ini datang. Ini yang mencegah "dua dunia omzet":
 * baris turunan TIDAK boleh diketik ulang; kalau salah, perbaiki pesanannya.
 */
const SOURCE_META = {
  orders_auto:     { label: 'Turunan dari pesanan', tone: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30' },
  manual_override: { label: 'Diganti SPV',          tone: 'bg-amber-500/10 text-amber-500 border-amber-500/30' },
  manual:          { label: 'Manual',               tone: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  import:          { label: 'Impor rekap',          tone: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  import_kpi:      { label: 'Impor KPI',            tone: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  livehost_creator_auto: { label: 'Live otomatis',  tone: 'bg-pink-500/10 text-pink-400 border-pink-500/30' },
  task_action:     { label: 'Dari tugas',           tone: 'bg-muted/20 text-muted-foreground border-border/40' },
};

function SourceBadge({ row }) {
  const meta = SOURCE_META[row.source] || { label: row.source || 'manual', tone: 'bg-muted/20 text-muted-foreground border-border/40' };
  const locked = row.locked_source === true;
  return (
    <div className="min-w-[130px]">
      <Badge variant="outline" className={meta.tone} data-testid={`sd-source-${row.id || ''}`}>
        {meta.label}
      </Badge>
      {locked && (
        <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1">
          <Lock size={9} /> tak bisa diketik
        </div>
      )}
      {row.override_reason && (
        <div className="text-[10px] text-amber-500 mt-0.5 max-w-[160px] truncate"
          title={`${row.override_reason} — oleh ${row.override_by || '-'}`}>
          alasan: {row.override_reason}
        </div>
      )}
    </div>
  );
}

export default function SalesDataEntryModule({ token }) {
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const [accounts, setAccounts] = useState([]);
  const [salesData, setSalesData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ account_id: 'all', revenue_type: 'all' });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const accRes = await fetch('/api/marketing/accounts', { headers });
      const accs = accRes.ok ? await accRes.json() : [];
      setAccounts(accs);

      // Fetch sales data per account or for chosen account
      const targetAccs = filter.account_id === 'all' ? accs : accs.filter(a => a.id === filter.account_id);
      const allSales = [];
      for (const acc of targetAccs.slice(0, 10)) {
        const params = new URLSearchParams();
        if (filter.revenue_type !== 'all') params.append('revenue_type', filter.revenue_type);
        const r = await fetch(`/api/marketing/accounts/${acc.id}/sales?${params.toString()}`, { headers });
        if (r.ok) {
          const list = await r.json();
          list.forEach(item => {
            allSales.push({ ...item, _account_name: acc.account_name, _platform: acc.platform });
          });
        }
      }
      // sort by date desc
      allSales.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
      setSalesData(allSales);
    } catch (e) {
      toast.error('Gagal memuat data sales');
    } finally {
      setLoading(false);
    }
  }, [filter, headers]);

  /** F2 — hitung ulang rekap harian dari pesanan (60 hari terakhir) untuk toko terpilih. */
  const recompute = async (force = false) => {
    if (filter.account_id === 'all') {
      toast.info('Pilih satu toko dulu — hitung ulang dilakukan per toko');
      return;
    }
    setRecomputing(true);
    try {
      const to = new Date();
      const from = new Date(Date.now() - 60 * 864e5);
      const iso = (d) => d.toISOString().slice(0, 10);
      const res = await fetch(
        `/api/marketing/sales/recompute?account_id=${filter.account_id}`
        + `&date_from=${iso(from)}&date_to=${iso(to)}&force=${force}`,
        { method: 'POST', headers });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'Gagal menghitung ulang');
      toast.success(body.message || 'Rekap harian dihitung ulang', { duration: 7000 });
      fetchData();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setRecomputing(false);
    }
  };

  useEffect(() => { fetchData(); }, [fetchData]);

  const { page, setPage, totalPages, total, paged } = useClientPagination(salesData, 10);
  return (
    <div className="space-y-5" data-testid="sales-data-entry-module">
      <PageHeader
        icon={TrendingUp}
        eyebrow="Portal Marketing · Sales Data"
        title="Input Sales Harian"
        subtitle="Catat penjualan harian (regular vs live) per akun marketplace"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={fetchData} variant="outline" size="sm" data-testid="refresh-sales-btn">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button onClick={() => recompute(false)} variant="outline" size="sm"
              disabled={recomputing} data-testid="recompute-sales-btn">
              {recomputing ? <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                : <Calculator className="w-3.5 h-3.5 mr-1.5" />} Hitung Ulang dari Pesanan
            </Button>
            <Button onClick={() => setDialogOpen(true)} size="sm" data-testid="input-sales-btn">
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Input Sales
            </Button>
          </div>
        }
      />

      {/* Active Account Bar */}
      <ActiveAccountBar
        accounts={accounts}
        activeAccount={activeAccount}
        onAccountChange={(acc) => {
          setActiveAccount(acc);
          setFilter(f => ({ ...f, account_id: acc ? acc.id : 'all' }));
        }}
        hint="Filter & input otomatis ke akun:"
      />

      <GlassPanel className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[180px]">
            <Label className="text-xs">Filter Akun</Label>
            <Select value={filter.account_id} onValueChange={v => setFilter(f => ({ ...f, account_id: v }))}>
              <SelectTrigger data-testid="sd-filter-account"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Akun</SelectItem>
                {accounts.map(a => (
                  <SelectItem key={a.id} value={a.id}>{a.account_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1 min-w-[180px]">
            <Label className="text-xs">Filter Type</Label>
            <Select value={filter.revenue_type} onValueChange={v => setFilter(f => ({ ...f, revenue_type: v }))}>
              <SelectTrigger data-testid="sd-filter-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua</SelectItem>
                <SelectItem value="total">Total Revenue</SelectItem>
                <SelectItem value="live">Live Revenue</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="text-sm text-muted-foreground">
            Total entries: <span className="text-foreground font-semibold">{salesData.length}</span>
          </div>
          <ExportCsvButton
            filename="input-sales-harian"
            testId="sales-export-csv"
            className="h-9"
            note="seluruh baris yang cocok filter"
            head={['Tanggal', 'Akun', 'Platform', 'Jenis', 'Sumber angka', 'Revenue',
              'Orders', 'AOV', 'Conversion rate (%)']}
            rows={(salesData || []).map((r) => [r.date, r._account_name, r._platform,
              r.revenue_type, r.source || r.input_source || '', r.metrics?.revenue ?? '',
              r.metrics?.orders ?? '', r.metrics?.aov ?? '',
              r.metrics?.conversion_rate ?? ''])}
          />
        </div>
      </GlassPanel>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-16" />)}
        </div>
      ) : salesData.length === 0 ? (
        <GlassCard className="p-12 text-center">
          <Calendar className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <p className="text-muted-foreground mb-4">Belum ada data sales</p>
          <Button size="sm" onClick={() => setDialogOpen(true)} data-testid="input-first-sales-btn">
            <Plus className="w-4 h-4 mr-2" /> Input Sales Pertama
          </Button>
        </GlassCard>
      ) : (
        <GlassCard className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--glass-bg)] border-b border-[var(--glass-border)]">
                <tr>
                  <th className="text-left px-4 py-2.5 font-semibold">Tanggal</th>
                  <th className="text-left px-4 py-2.5 font-semibold">Akun</th>
                  <th className="text-left px-4 py-2.5 font-semibold">Type</th>
                  <th className="text-left px-4 py-2.5 font-semibold">Sumber Angka</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Revenue</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Orders</th>
                  <th className="text-right px-4 py-2.5 font-semibold">AOV</th>
                  <th className="text-right px-4 py-2.5 font-semibold">CR</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((row, i) => (
                  <tr key={row.id || i} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg)]" data-testid={`sd-row-${i}`}>
                    <td className="px-4 py-2.5 font-mono text-xs">{row.date}</td>
                    <td className="px-4 py-2.5">
                      <AccountBadge
                        account={{ account_name: row._account_name, platform: row._platform }}
                        size="xs"
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant="outline" className={row.revenue_type === 'live' ? 'bg-pink-500/10 text-pink-400 border-pink-500/30' : 'bg-blue-500/10 text-blue-400 border-blue-500/30'}>
                        {row.revenue_type}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5"><SourceBadge row={row} /></td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{fmt(row.metrics?.revenue)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{fmtNum(row.metrics?.orders)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{fmt(row.metrics?.aov)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs">
                      {/* F0: satuan kanonik = PERSEN 0–100, jadi TIDAK dikali 100 lagi */}
                      {row.metrics?.conversion_rate ? `${Number(row.metrics.conversion_rate).toFixed(2)}%` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        </GlassCard>
      )}

      <SalesDataEntryDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        accounts={accounts}
        onSaved={fetchData}
        token={token}
        preSelectedAccountId={activeAccount?.id || ''}
      />
    </div>
  );
}
