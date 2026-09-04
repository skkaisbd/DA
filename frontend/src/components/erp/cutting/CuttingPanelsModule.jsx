/**
 * CuttingPanelsModule — Master Potongan (kain pola) hasil cutting.
 *
 * Ini BUKAN master material baru yang terpisah: isinya adalah dokumen
 * `rahaza_materials` bertanda `is_cut_panel`, jadi item yang tampil di sini
 * juga tampil di Master Item Gudang, dropdown BOM, dan Pengeluaran Material.
 * Layar ini hanya menyaringnya supaya tim cutting/gudang mudah melihat
 * stok potongan per style/warna/size beserta kain asalnya.
 *
 * SESI #32 — DUA HAL YANG DITAMBAHKAN (keluhan pemilik)
 * ----------------------------------------------------
 * 1. **NILAI, bukan cuma qty.** Tiap baris kini menampilkan HPP/pcs, NILAI
 *    persediaan (stok × HPP), dan STATUS nilainya. Potongan yang belum bernilai
 *    (karena harga kain asalnya belum ada) MENGATAKANNYA beserta jalan keluarnya
 *    — dulu ia hanya tampil "-" sehingga tampak seperti barang gratis.
 * 2. **Potongan YATIM bisa dilihat & dibersihkan.** Master potongan dibuat
 *    otomatis saat order cutting dimulai; bila order/kain asalnya sudah tidak
 *    ada, masternya tertinggal jadi sampah di Master Item. Kartu "Potongan
 *    yatim" menampilkan daftarnya + alasannya, dan tombol Bersihkan HANYA
 *    menghapus yang terbukti belum pernah dipakai (0 stok, tanpa kartu stok,
 *    tidak dirujuk dokumen apa pun). Yang masih berstok dipertahankan dan
 *    alasannya disebut — menghapusnya akan membuat stok jadi hantu.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Package, RefreshCw, Search, Scissors, ArrowRight, AlertCircle,
  AlertTriangle, Trash2, CheckCircle2, Loader2, ShieldAlert,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { cuttingApi, fmtNum, fmtRp, fmtDate } from './cuttingApi';

const VALUE_BADGE = {
  valued: { text: 'bernilai', cls: 'text-emerald-600 dark:text-emerald-300' },
  unvalued: { text: 'belum bernilai', cls: 'text-amber-600 dark:text-amber-300' },
};

export default function CuttingPanelsModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');
  const [health, setHealth] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr('');
    try {
      const [list, h] = await Promise.all([
        cuttingApi('GET', '/output-materials', token),
        cuttingApi('GET', '/panels/health', token).catch(() => null),
      ]);
      setRows(Array.isArray(list) ? list : []);
      setHealth(h);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) =>
      [r.code, r.name, r.color, r.style_name, r.style_sku, r.source_material_code,
        r.cutting_order_number]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(s)));
  }, [rows, q]);

  const totalStock = filtered.reduce((a, r) => a + Number(r.stock_qty || 0), 0);
  const totalValue = filtered.reduce(
    (a, r) => a + Number(r.stock_value ?? (Number(r.stock_qty || 0) * Number(r.unit_cost || 0))), 0);
  const unvaluedCount = filtered.filter(
    (r) => (r.value_status || (Number(r.unit_cost || 0) > 0 ? 'valued' : 'unvalued')) === 'unvalued').length;

  const orphans = useMemo(() => (health?.items || []).filter((r) => r.orphan), [health]);
  const cleanable = orphans.filter((r) => r.cleanable);

  const runCleanup = async () => {
    setCleaning(true);
    try {
      const res = await cuttingApi('POST', '/panels/cleanup', token,
        { ids: cleanable.map((r) => r.id) });
      if (res.removed) {
        toast.success(`${res.removed} master potongan yatim dibersihkan.`);
      } else {
        toast.info('Tidak ada yang bisa dibersihkan — semuanya masih dipakai.');
      }
      if (res.kept) {
        toast.warning(`${res.kept} dipertahankan karena masih dipakai (lihat alasannya).`);
      }
      setConfirming(false);
      await load();
    } catch (e) {
      toast.error(`Gagal membersihkan: ${e.message}`);
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="cutting-panels-module">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-emerald-500/12 border border-emerald-500/25 grid place-items-center">
            <Package className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-foreground">Master Potongan</h2>
            <p className="text-sm text-muted-foreground">
              Item material hasil cutting (kain pola). Nilainya lahir dari kain yang dipotong —
              siap dipakai sebagai BOM produksi &amp; dikirim ke CMT.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load}
            className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-sm text-foreground hover:bg-[var(--nav-pill-active)]"
            data-testid="cutting-panels-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Muat Ulang
          </button>
          <button onClick={() => onNavigate?.('cutting-orders')}
            className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm"
            data-testid="cutting-panels-goto-orders">
            <Scissors className="w-4 h-4" /> Order Cutting
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Jenis Potongan</p>
          <p className="text-2xl font-bold text-foreground mt-1">{fmtNum(filtered.length)}</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Total Stok Potongan</p>
          <p className="text-2xl font-bold text-foreground mt-1">{fmtNum(totalStock)} pcs</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Nilai Persediaan</p>
          <p className="text-2xl font-bold text-foreground mt-1"
            data-testid="cutting-panels-total-value">{fmtRp(totalValue)}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">stok × HPP hasil potong</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Belum Bernilai</p>
          <p className={`text-2xl font-bold mt-1 ${unvaluedCount ? 'text-amber-600 dark:text-amber-300' : 'text-foreground'}`}
            data-testid="cutting-panels-unvalued-count">{fmtNum(unvaluedCount)}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">harga kain asalnya belum ada</p>
        </GlassCard>
      </div>

      {/* ── POTONGAN YATIM ─────────────────────────────────────────────────── */}
      {orphans.length > 0 && (
        <GlassCard className="p-4 border-amber-400/50 bg-amber-50/70 dark:bg-amber-500/10"
          data-testid="cutting-panels-orphan-card">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-300 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {orphans.length} master potongan YATIM
                </p>
                <p className="text-xs text-muted-foreground max-w-3xl">
                  Master potongan dibuat otomatis saat order cutting dimulai. Baris di bawah
                  sudah kehilangan induknya (order cutting dan/atau kain asalnya tidak ada lagi)
                  — biasanya sisa alat uji atau order yang dibatalkan.{' '}
                  <strong className="text-foreground">
                    Yang masih berstok TIDAK akan dihapus
                  </strong>{' '}
                  supaya stok tidak jadi hantu; alasannya disebut per baris.
                </p>
              </div>
            </div>
            {confirming ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-foreground">
                  Bersihkan {cleanable.length} master?
                </span>
                <button onClick={runCleanup} disabled={cleaning || !cleanable.length}
                  className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg bg-red-600 text-white text-sm disabled:opacity-50"
                  data-testid="cutting-panels-cleanup-confirm">
                  {cleaning ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <CheckCircle2 className="w-4 h-4" />} Ya, bersihkan
                </button>
                <button onClick={() => setConfirming(false)}
                  className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-sm text-foreground"
                  data-testid="cutting-panels-cleanup-cancel">Batal</button>
              </div>
            ) : (
              <button onClick={() => setConfirming(true)} disabled={!cleanable.length}
                className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-amber-600 text-white text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                title={cleanable.length ? 'Hapus master potongan yang belum pernah dipakai'
                  : 'Tidak ada yang bisa dibersihkan — semuanya masih dipakai'}
                data-testid="cutting-panels-cleanup-btn">
                <Trash2 className="w-4 h-4" /> Bersihkan yang aman ({cleanable.length})
              </button>
            )}
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs" data-testid="cutting-panels-orphan-table">
              <thead>
                <tr className="text-left text-[11px] text-muted-foreground border-b border-amber-400/40">
                  <th className="py-1.5 pr-3 font-medium">Kode</th>
                  <th className="py-1.5 pr-3 font-medium">Alasan yatim</th>
                  <th className="py-1.5 pr-3 font-medium">Kain asal</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Stok</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Nilai</th>
                  <th className="py-1.5 font-medium">Bisa dibersihkan?</th>
                </tr>
              </thead>
              <tbody>
                {orphans.map((r) => (
                  <tr key={r.id} className="border-b border-amber-400/20 last:border-0"
                    data-testid={`cutting-panels-orphan-row-${r.code}`}>
                    <td className="py-1.5 pr-3 font-mono text-foreground">{r.code}</td>
                    <td className="py-1.5 pr-3 text-foreground/90">{r.reason_text}</td>
                    <td className="py-1.5 pr-3 font-mono text-muted-foreground">
                      {r.source_material_code || '—'}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-foreground">
                      {fmtNum(r.stock_qty)} {r.unit || 'pcs'}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-foreground">
                      {fmtRp(r.stock_value)}
                    </td>
                    <td className="py-1.5">
                      {r.cleanable ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300">
                          <CheckCircle2 className="w-3 h-3" /> aman dihapus
                        </span>
                      ) : (
                        <span className="inline-flex items-start gap-1 text-amber-700 dark:text-amber-300">
                          <ShieldAlert className="w-3 h-3 mt-0.5 shrink-0" />
                          <span>{r.block_reason || 'masih dipakai'}</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Cari kode / style / warna / kain asal / nomor order…"
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.35)]"
            data-testid="cutting-panels-search" />
        </div>
      </GlassCard>

      {err && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4" /> {err}
        </div>
      )}

      <GlassCard className="p-0 overflow-hidden">
        {loading && rows.length === 0 ? (
          <div className="p-6 space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="h-9 rounded-lg bg-foreground/5 animate-pulse" />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center" data-testid="cutting-panels-empty">
            <Package className="w-10 h-10 mx-auto text-muted-foreground/40" />
            <p className="mt-3 font-medium text-foreground">Belum ada master potongan</p>
            <p className="text-sm text-muted-foreground">
              Item potongan otomatis dibuat saat sebuah order cutting dimulai.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="cutting-panels-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--nav-pill-bg)]">
                  <th className="px-4 py-2.5 font-medium">Kode Potongan</th>
                  <th className="px-4 py-2.5 font-medium">Nama</th>
                  <th className="px-4 py-2.5 font-medium">Warna / Size</th>
                  <th className="px-4 py-2.5 font-medium">Kain Asal</th>
                  <th className="px-4 py-2.5 font-medium">Order Cutting</th>
                  <th className="px-4 py-2.5 font-medium text-right">Stok</th>
                  <th className="px-4 py-2.5 font-medium text-right">HPP / pcs</th>
                  <th className="px-4 py-2.5 font-medium text-right">Nilai</th>
                  <th className="px-4 py-2.5 font-medium">Status Nilai</th>
                  <th className="px-4 py-2.5 font-medium">Dibuat</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => {
                  const status = m.value_status
                    || (Number(m.unit_cost || 0) > 0 ? 'valued' : 'unvalued');
                  const badge = VALUE_BADGE[status] || VALUE_BADGE.unvalued;
                  return (
                    <tr key={m.id} className="border-b border-[var(--glass-border)] last:border-0 hover:bg-[var(--nav-pill-active)]/40"
                      data-testid={`cutting-panels-row-${m.code}`}>
                      <td className="px-4 py-2.5 font-mono text-xs text-foreground">
                        {m.code}
                        {m.orphan && (
                          <span className="ml-1.5 inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-300"
                            title={m.orphan_reason_text || 'yatim'}>
                            <AlertTriangle className="w-3 h-3" /> yatim
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-foreground">{m.name}</td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">
                        {m.color || '-'}{m.size ? ` · ${m.size}` : ''}
                      </td>
                      <td className="px-4 py-2.5 text-xs">
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          <span className="font-mono">{m.source_material_code || '-'}</span>
                          <ArrowRight className="w-3 h-3" />
                          <span className="font-mono text-foreground">{m.code}</span>
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground">
                        {m.cutting_order_number || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-medium text-foreground">
                        {fmtNum(m.stock_qty)} pcs
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                        {Number(m.unit_cost || 0) > 0 ? fmtRp(m.unit_cost)
                          : <span className="text-muted-foreground text-xs">belum ada</span>}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-foreground"
                        data-testid={`cutting-panels-value-${m.code}`}>
                        {fmtRp(m.stock_value ?? (Number(m.stock_qty || 0) * Number(m.unit_cost || 0)))}
                      </td>
                      <td className="px-4 py-2.5 text-xs">
                        <span className={badge.cls}>{badge.text}</span>
                        {status === 'unvalued' && (
                          <span className="block text-[10px] text-muted-foreground max-w-[260px]">
                            {m.value_note || 'harga kain asalnya belum ada — nilai belum bisa dihitung'}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{fmtDate(m.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
