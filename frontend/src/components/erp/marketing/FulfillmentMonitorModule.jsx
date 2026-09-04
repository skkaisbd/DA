/**
 * FulfillmentMonitorModule — MONITORING PENGIRIMAN (F3).
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * Ekspor "Untuk Dikirim" memberi tahu pesanan mana yang menunggu, tetapi daftar
 * 559 baris tidak memberi tahu apa pun tentang PRIORITAS. Yang dibutuhkan tim
 * setiap pagi cuma tiga angka: berapa yang belum dikirim, berapa yang sudah
 * LEWAT BATAS (ini yang berubah menjadi penalti platform & pembatalan otomatis),
 * dan berapa yang batal.
 *
 * Batas kirim TIDAK dikarang di kode: ia tersimpan per toko dan bisa diubah dari
 * layar ini (tombol "Batas kirim"). Layar selalu menyebut batas yang dipakai —
 * daftar "merah" tanpa aturan yang bisa ditunjuk akan diabaikan staf.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Truck, AlertTriangle, XCircle, RotateCcw, RefreshCw, Loader2, Clock,
  Info, Settings2, Download, PackageCheck, Search,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { GlassInput } from '@/components/ui/glass';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '../moduleAtoms';
import { toast } from 'sonner';
import PaginationLite from '@/components/ui/pagination-lite';
// F10 (sesi #10) — satu pembuat CSV untuk semua layar daftar (escaping + BOM Excel).
import { downloadCsv } from '@/lib/csv';

const API = process.env.REACT_APP_BACKEND_URL || '';
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const num = (n) => Number(n || 0).toLocaleString('id-ID');

const BUCKETS = [
  { key: 'lewat_batas', label: 'Lewat batas kirim', icon: AlertTriangle, tone: 'text-red-500' },
  { key: 'belum_dikirim', label: 'Belum dikirim', icon: Truck, tone: 'text-amber-500' },
  { key: 'batal', label: 'Batal', icon: XCircle, tone: 'text-muted-foreground' },
  { key: 'retur', label: 'Retur', icon: RotateCcw, tone: 'text-muted-foreground' },
];

function Tile({ label, value, sub, tone = '', testId }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3"
      data-testid={testId}>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function SlaDialog({ open, onOpenChange, store, token, onSaved }) {
  const [normal, setNormal] = useState('2');
  const [pre, setPre] = useState('7');
  const [busy, setBusy] = useState(false);
  // Penolakan backend (mis. "pre-order tidak boleh lebih pendek…") DITAHAN di dalam
  // dialog. Uji layar 2026-08-12: dengan toast saja, penolakan itu tidak terlihat —
  // dialog tetap terbuka tanpa satu pun keterangan, jadi tampak seperti tombol
  // Simpan yang tidak berfungsi dan staf akan menekannya berulang kali.
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open && store) {
      setNormal(String(store.sla_days ?? 2));
      setPre(String(store.sla_days_preorder ?? 7));
      setErr('');
    }
  }, [open, store]);

  const nNormal = parseFloat(normal);
  const nPre = parseFloat(pre);
  const localInvalid = !Number.isFinite(nNormal) || !Number.isFinite(nPre)
    || nNormal < 0.25 || nPre < 0.25 || nPre < nNormal;

  const save = async () => {
    setErr('');
    if (localInvalid) {
      setErr(!Number.isFinite(nNormal) || !Number.isFinite(nPre)
        ? 'Kedua batas harus berupa angka hari (minimal 0,25 hari = 6 jam).'
        : (nPre < nNormal
          ? `Batas pre-order (${nPre} hari) tidak boleh lebih pendek daripada batas pesanan `
            + `normal (${nNormal} hari) — pre-order justru butuh waktu lebih panjang.`
          : 'Batas minimal 0,25 hari (6 jam).'));
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/marketing/accounts/${store.account_id}/ship-sla`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ship_sla_days: nNormal,
          ship_sla_days_preorder: nPre,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        const detail = typeof body.detail === 'string' ? body.detail
          : (Array.isArray(body.detail) ? body.detail.map((d) => d.msg || '').join(' · ')
            : 'Gagal menyimpan batas kirim');
        throw new Error(detail);
      }
      toast.success(body.message || 'Batas kirim disimpan', { duration: 7000 });
      onOpenChange(false);
      onSaved?.();
    } catch (e) {
      setErr(e.message);
      toast.error(e.message, { duration: 9000 });
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="sla-dialog">
        <DialogHeader>
          <DialogTitle>Batas kirim — {store?.account_name}</DialogTitle>
          <DialogDescription>
            Pesanan yang melewati batas ini dihitung <b>lewat batas</b> di layar ini.
            Setiap platform punya tenggat berbeda, jadi batasnya disimpan per toko —
            bukan aturan tetap di dalam sistem.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Pesanan normal (hari)</Label>
            <GlassInput type="number" step="0.5" min="0.25" value={normal}
              onChange={(e) => { setNormal(e.target.value); setErr(''); }}
              data-testid="sla-normal" />
          </div>
          <div>
            <Label className="text-xs">Pre-order (hari)</Label>
            <GlassInput type="number" step="0.5" min="0.25" value={pre}
              onChange={(e) => { setPre(e.target.value); setErr(''); }}
              data-testid="sla-preorder" />
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Pre-order tidak boleh lebih pendek daripada pesanan normal.
        </p>
        {err && (
          <div className="rounded-[var(--radius-sm)] border border-red-500/40 bg-red-500/10
            p-2.5 text-xs text-red-700 dark:text-red-300 flex items-start gap-2"
            data-testid="sla-error">
            <XCircle className="w-4 h-4 mt-px shrink-0" /><span>{err}</span>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}
            data-testid="sla-cancel">Batal</Button>
          <Button onClick={save} disabled={busy} data-testid="sla-save">
            {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function FulfillmentMonitorModule({ token }) {
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState('');
  const [bucket, setBucket] = useState('lewat_batas');
  // F10 — kebutuhan harian yang paling sering: "pesanan NOMOR ini kenapa belum
  // terkirim?". Tanpa pencarian, staf menggulir 500 baris.
  const [q, setQ] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [slaStore, setSlaStore] = useState(null);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);

  const selectedAccount = useMemo(
    () => accounts.find((a) => a.id === accountId) || null, [accounts, accountId]);

  const loadAccounts = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/marketing/accounts?status=active`, { headers });
      const b = await r.json().catch(() => ({}));
      setAccounts(Array.isArray(b) ? b : (b.accounts || b.data || []));
    } catch { setAccounts([]); }
  }, [headers]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ bucket, page: String(page), page_size: '50' });
      if (accountId) qs.set('account_id', accountId);
      const r = await fetch(`${API}/api/marketing/orders/fulfillment-monitor?${qs}`, { headers });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal memuat monitoring pengiriman');
      setData(b);
    } catch (e) {
      toast.error(e.message, { duration: 9000 });
      setData(null);
    } finally { setLoading(false); }
  }, [headers, accountId, bucket, page]);

  useEffect(() => { load(); }, [load]);

  const t = data?.totals || {};
  const allRows = data?.rows || [];
  const needle = q.trim().toLowerCase();
  const rows = needle
    ? allRows.filter((r) => [r.order_id, r.account_name, r.courier, r.order_channel,
      r.status_raw, r.status].some((v) => String(v || '').toLowerCase().includes(needle)))
    : allRows;
  const isOpenBucket = bucket === 'lewat_batas' || bucket === 'belum_dikirim';

  const exportCsv = () => {
    if (!rows.length) { toast.info('Tidak ada baris untuk diunduh'); return; }
    const head = isOpenBucket
      ? ['No. Pesanan', 'Toko', 'Status', 'Pre-order', 'Dibayar', 'Umur (hari)',
         'Batas (hari)', 'Lewat (hari)', 'Tenggat', 'Kurir', 'Kanal', 'Pcs', 'Nilai']
      : ['No. Pesanan', 'Toko', 'Status', 'Tanggal', 'Alasan', 'Pcs', 'Nilai'];
    const body = rows.map((r) => (isOpenBucket
      ? [r.order_id, r.account_name, r.status_raw || r.status, r.is_preorder ? 'ya' : 'tidak',
         (r.paid_at || '').slice(0, 16), r.age_days, r.sla_days, r.over_by_days,
         (r.deadline || '').slice(0, 16), r.courier, r.order_channel, r.quantity, r.value]
      : [r.order_id, r.account_name, r.status_raw || r.status,
         (r.order_date || '').slice(0, 16), r.cancel_reason, r.quantity, r.value]));
    const n = downloadCsv(`monitoring-pengiriman-${bucket}`, head, body);
    toast.success(`CSV terunduh — ${n} baris (persis yang terlihat di layar)`);
  };

  return (
    <div className="space-y-5" data-testid="fulfillment-monitor-module">
      <PageHeader
        eyebrow="PORTAL MARKETING · PENGIRIMAN"
        title="Monitoring Pengiriman"
        subtitle="Apa yang harus dikejar hari ini — pesanan belum dikirim, lewat batas kirim, batal & retur"
        icon={Truck}
        actions={(
          <>
            <Button variant="outline" size="sm" onClick={load} data-testid="monitor-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
            </Button>
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <GlassInput className="h-8 pl-8 w-56 text-xs" placeholder="cari no. pesanan / toko / kurir"
                value={q} onChange={(e) => setQ(e.target.value)}
                data-testid="monitor-search" />
            </div>
            <Button variant="outline" size="sm" onClick={exportCsv} data-testid="monitor-export">
              <Download className="w-3.5 h-3.5 mr-1.5" /> Unduh CSV
            </Button>
          </>
        )}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Tile label="Lewat batas kirim" value={num(t.lewat_batas)} tone="text-red-500"
          sub={rp(t.nilai_lewat_batas)} testId="tile-lewat-batas" />
        <Tile label="Belum dikirim" value={num(t.belum_dikirim)} tone="text-amber-500"
          sub={rp(t.nilai_belum_dikirim)} testId="tile-belum-dikirim" />
        <Tile label="Menunggu terlama" value={`${Number(t.umur_tertua_hari || 0).toFixed(1)} hari`}
          sub="sejak dibayar" testId="tile-tertua" />
        <Tile label="Batal / Retur" value={`${num(t.batal)} / ${num(t.retur)}`}
          sub="perlu Ekspor Batal-Retur" testId="tile-batal" />
        <Tile label="Sudah dikirim" value={num(t.sudah_dikirim)} tone="text-emerald-500"
          sub={`${num(t.pesanan_dibaca)} pesanan dibaca`} testId="tile-dikirim" />
      </div>

      {(data?.data_notes || []).length > 0 && (
        <div className="rounded-[var(--radius-md)] border border-blue-500/30 bg-blue-500/5 p-3 space-y-1"
          data-testid="monitor-data-notes">
          {data.data_notes.map((n, i) => (
            <p key={i} className="text-xs flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 mt-px shrink-0 text-blue-500" /><span>{n}</span>
            </p>
          ))}
        </div>
      )}

      <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3
        flex flex-wrap items-end gap-3">
        <div className="min-w-[220px]">
          <Label className="text-xs">Toko</Label>
          <Select value={accountId || '__all__'}
            onValueChange={(v) => { setAccountId(v === '__all__' ? '' : v); setPage(1); }}>
            <SelectTrigger data-testid="monitor-account" className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua Toko</SelectItem>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={a.id}>{a.account_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {/* Toko yang belum punya pesanan sama sekali tidak muncul di rekap per toko,
            jadi batas kirimnya tidak akan pernah bisa disetel dari tabel itu —
            padahal justru toko baru yang perlu disetel SEBELUM impor pertamanya. */}
        {accountId && selectedAccount
          && !(data?.per_store || []).some((s) => s.account_id === accountId) && (
          <Button size="sm" variant="outline" data-testid="monitor-sla-selected"
            onClick={() => setSlaStore({
              account_id: selectedAccount.id,
              account_code: selectedAccount.account_code,
              account_name: selectedAccount.account_name,
              sla_days: selectedAccount.ship_sla_days ?? data?.sla_default?.normal ?? 2,
              sla_days_preorder: selectedAccount.ship_sla_days_preorder
                ?? data?.sla_default?.preorder ?? 7,
            })}>
            <Settings2 className="w-3.5 h-3.5 mr-1.5" /> Batas kirim toko ini
          </Button>
        )}
        <div className="flex flex-wrap gap-1.5">
          {BUCKETS.map((b) => (
            <Button key={b.key} size="sm"
              variant={bucket === b.key ? 'default' : 'outline'}
              onClick={() => { setBucket(b.key); setPage(1); }}
              data-testid={`monitor-bucket-${b.key}`}>
              <b.icon className={`w-3.5 h-3.5 mr-1.5 ${bucket === b.key ? '' : b.tone}`} />
              {b.label} ({num(t[b.key])})
            </Button>
          ))}
        </div>
      </div>

      {/* REKAP PER TOKO — ditampilkan walau hanya SATU toko yang berdata.
          Dulu tabel ini disembunyikan bila `per_store.length <= 1`, dan karena
          tombol "Batas kirim" HANYA ada di baris tabel ini, batas kirim justru
          tidak bisa diubah pada keadaan yang paling sering terjadi: menyaring
          satu toko, atau baru satu toko yang datanya diimpor. */}
      {(data?.per_store || []).length > 0 && (
        <div className="rounded-[var(--radius-md)] border border-border overflow-x-auto">
          <table className="w-full text-xs" data-testid="monitor-per-store">
            <thead className="bg-muted/60"><tr>
              {['Toko', 'Platform', 'Lewat batas', 'Belum dikirim', 'Nilai tertahan',
                'Terlama (hari)', 'Batas normal/pre-order', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>))}
            </tr></thead>
            <tbody>
              {data.per_store.map((s) => (
                <tr key={s.account_id} className="border-t border-border">
                  <td className="px-3 py-2 font-medium">{s.account_name}</td>
                  <td className="px-3 py-2"><Badge variant="outline" className="text-[10px]">{s.platform}</Badge></td>
                  <td className="px-3 py-2 tabular-nums text-red-500 font-semibold">{num(s.lewat_batas)}</td>
                  <td className="px-3 py-2 tabular-nums">{num(s.belum_dikirim)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(s.nilai_belum_dikirim)}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(s.umur_tertua_hari || 0).toFixed(1)}</td>
                  <td className="px-3 py-2 tabular-nums">{s.sla_days} / {s.sla_days_preorder}</td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => setSlaStore(s)}
                      data-testid={`monitor-sla-${s.account_code}`}>
                      <Settings2 className="w-3.5 h-3.5 mr-1" /> Batas kirim
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* daftar pesanan */}
      <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))]">
        {loading ? (
          <div className="p-4 space-y-2">{[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-8" />)}</div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center" data-testid="monitor-empty">
            <PackageCheck className="w-8 h-8 mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-medium">Tidak ada pesanan pada kategori ini.</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t.pesanan_dibaca ? 'Bagus — tidak ada yang perlu dikejar di kategori ini.'
                : 'Belum ada pesanan sama sekali. Impor ekspor Seller Center dulu di menu Impor Data.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="monitor-table">
              <thead className="bg-muted/60"><tr>
                {(isOpenBucket
                  ? ['No. Pesanan', 'Toko', 'Status', 'Dibayar', 'Menunggu', 'Batas',
                     'Lewat', 'Tenggat', 'Kurir', 'Kanal', 'Pcs', 'Nilai']
                  : ['No. Pesanan', 'Toko', 'Status', 'Tanggal', 'Alasan', 'Pcs', 'Nilai']
                ).map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>))}
              </tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.id || i} className="border-t border-border hover:bg-muted/30"
                    data-testid={`monitor-row-${i}`}>
                    <td className="px-3 py-2 font-mono">{r.order_id}</td>
                    <td className="px-3 py-2">{r.account_name}</td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className="text-[10px]">{r.status_raw || r.status}</Badge>
                      {r.is_preorder && (
                        <Badge className="ml-1 text-[10px] bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300">
                          pre-order
                        </Badge>
                      )}
                    </td>
                    {isOpenBucket ? (
                      <>
                        <td className="px-3 py-2 whitespace-nowrap">{(r.paid_at || '').slice(0, 10)}</td>
                        <td className="px-3 py-2 tabular-nums whitespace-nowrap">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-muted-foreground" />
                            {r.age_days == null ? '—' : `${r.age_days} hari`}
                          </span>
                        </td>
                        <td className="px-3 py-2 tabular-nums">{r.sla_days} hari</td>
                        <td className="px-3 py-2 tabular-nums">
                          {r.late ? (
                            <span className="text-red-500 font-semibold">+{r.over_by_days} hari</span>
                          ) : <span className="text-muted-foreground">—</span>}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">
                          {(r.deadline || '').slice(0, 10)}
                        </td>
                        <td className="px-3 py-2">{r.courier || '—'}</td>
                        <td className="px-3 py-2">{r.order_channel || '—'}</td>
                        <td className="px-3 py-2 tabular-nums">{r.quantity}</td>
                        <td className="px-3 py-2 tabular-nums">{rp(r.value)}</td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-2">{(r.order_date || '').slice(0, 10)}</td>
                        <td className="px-3 py-2">{r.cancel_reason || '—'}</td>
                        <td className="px-3 py-2 tabular-nums">{r.quantity}</td>
                        <td className="px-3 py-2 tabular-nums">{rp(r.value)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data?.total_pages > 1 && (
          <div className="p-3 border-t border-border">
            <PaginationLite page={page} totalPages={data.total_pages}
              onPageChange={setPage} total={data.total} pageSize={50} />
          </div>
        )}
      </div>

      <SlaDialog open={!!slaStore} onOpenChange={(o) => !o && setSlaStore(null)}
        store={slaStore} token={token}
        onSaved={() => { load(); loadAccounts(); }} />
    </div>
  );
}
