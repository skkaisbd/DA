/**
 * RnDProductViewer — **Katalog produk final RnD + status SSOT** (sesi #34).
 *
 * Pemilik: "di portal ini tidak memperlihatkan viewer product internal … sesuai
 * dengan hasil final RND menjadi master data ini sama saja menjadi catalog …
 * perlihatkan juga apakah ini sudah di sync dengan catalog marketing … pastikan
 * SSOT master data ini tidak broken dan link ke produksinya juga benar."
 *
 * Layar ini TIDAK memperbaiki data; ia memperlihatkan apa adanya — termasuk yang
 * rusak. Tiap kartu menyebut kekurangannya (BOM belum ada, belum masuk katalog
 * marketing, biaya jahit SPK belum diisi, HPP masih perkiraan BOM). Jadi viewer
 * ini sekaligus pemeriksa sambungan RnD → Produksi → Marketing.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Boxes, Search, RefreshCw, CheckCircle2, AlertTriangle, Store, Factory, Loader2, X,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { formatRupiah } from '@/lib/format';
import { apiGet } from '@/lib/api';

const rp = formatRupiah;

export default function RnDProductViewer() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [q, setQ] = useState('');
  const [onlyBroken, setOnlyBroken] = useState(false);
  // SESI #34 — papan margin: produk paling tipis/merugi muncul lebih dulu.
  // Produk yang HPP atau harga jualnya belum ada TIDAK dihitung bermargin 0
  // (itu menutupi masalahnya) — jumlahnya disebut terpisah.
  const [sort, setSort] = useState('');
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiGet(`/rnd/product-viewer?limit=60${q ? `&q=${encodeURIComponent(q)}` : ''}${sort ? `&sort=${sort}` : ''}`);
      setRows(d?.data || []);
      setSummary(d?.summary || null);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat produk RnD');
    } finally { setLoading(false); }
  }, [q, sort]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    setDetail({ loading: true });
    try {
      setDetail(await apiGet(`/rnd/product-viewer/${id}`));
    } catch (e) {
      toast.error(e.message); setDetail(null);
    }
  };

  const shown = onlyBroken ? rows.filter((r) => !r.ssot_ok) : rows;

  return (
    <div className="space-y-5" data-testid="rnd-product-viewer">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Boxes className="w-6 h-6" /> Produk Final RnD
          </h1>
          <p className="text-sm text-foreground/60 mt-1">
            Hasil akhir RnD yang sudah menjadi <b>master data</b> barang jadi — beserta status
            sambungannya ke Katalog Marketing dan ke SPK Produksi.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-foreground/5 border border-foreground/10 rounded-lg px-2">
            <Search className="w-4 h-4 text-foreground/40" />
            <input data-testid="rnd-viewer-search" value={q}
              onChange={(e) => setQ(e.target.value)} placeholder="cari SKU / nama / model…"
              className="bg-transparent py-2 text-sm outline-none w-56" />
          </div>
          <select data-testid="rnd-viewer-sort" value={sort} onChange={(e) => setSort(e.target.value)}
            className="h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm">
            <option value="">Urut: nama model</option>
            <option value="margin_asc">Urut: margin paling tipis dulu</option>
            <option value="margin_desc">Urut: margin paling tebal dulu</option>
          </select>
          <label className="flex items-center gap-1.5 text-xs text-foreground/60">
            <input data-testid="rnd-viewer-only-broken" type="checkbox" checked={onlyBroken}
              onChange={(e) => setOnlyBroken(e.target.checked)} />
            hanya yang belum lengkap
          </label>
          <button data-testid="rnd-viewer-refresh" onClick={load}
            className="h-9 px-3 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4" /> Muat ulang
          </button>
        </div>
      </div>

      {summary ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <Kpi testId="rnd-kpi-total" label="Produk final" value={summary.total} />
          <Kpi testId="rnd-kpi-synced" label="Sudah di katalog" value={summary.synced}
            tone="good" hint={`${summary.shown - summary.synced} belum`} />
          <Kpi testId="rnd-kpi-hpp" label="HPP dari batch nyata" value={summary.hpp_real}
            hint="sisanya masih perkiraan BOM" />
          <Kpi testId="rnd-kpi-nobom" label="Tanpa BOM" value={summary.no_bom} tone="warn" />
          <Kpi testId="rnd-kpi-ssot" label="Lengkap (SSOT OK)" value={summary.ssot_ok}
            tone={summary.ssot_ok ? 'good' : 'warn'} />
          <Kpi testId="rnd-kpi-margin" label="Margin rata-rata"
            value={`${summary.margin_avg_pct || 0}%`}
            hint={`dari ${summary.margin_measurable || 0} produk yang HPP & harganya ada`} />
          <Kpi testId="rnd-kpi-margin-risk" label="Margin tipis / minus"
            value={`${(summary.margin_thin || 0) + (summary.margin_negative || 0)}`}
            tone={(summary.margin_negative || 0) ? 'warn' : 'good'}
            hint={`${summary.margin_unmeasurable || 0} produk belum bisa dihitung`} />
        </div>
      ) : null}

      {loading ? (
        <div className="py-16 text-center text-sm text-foreground/50 flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> memuat produk…
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {shown.map((r) => (
            <GlassCard key={r.material_id} className="p-4 space-y-3"
              data-testid={`rnd-product-${r.sku}`}>
              <div className="flex gap-3">
                <div className="w-20 h-20 rounded-lg bg-foreground/5 overflow-hidden flex items-center justify-center shrink-0">
                  {r.images?.[0]
                    ? <img src={r.images[0]} alt={r.name} className="w-full h-full object-cover" />
                    : <Boxes className="w-6 h-6 text-foreground/25" />}
                </div>
                <div className="min-w-0">
                  <div className="font-medium truncate">{r.name}</div>
                  <div className="text-xs font-mono text-foreground/50">{r.sku}</div>
                  <div className="text-xs text-foreground/50 mt-0.5">
                    {[r.category, r.color, r.size].filter(Boolean).join(' · ') || '—'}
                  </div>
                  <div className="text-xs mt-1">
                    <span className="text-foreground/50">HPP </span>
                    <b>{rp(r.hpp.fifo_avg || r.hpp.master)}</b>
                    <span className="text-foreground/40">
                      {' '}({r.hpp.layer_count ? `${r.hpp.layer_count} batch` : 'perkiraan BOM'})
                    </span>
                    {r.price.selling ? (
                      <>
                        <span className="text-foreground/50"> · jual </span>
                        <b>{rp(r.price.selling)}</b>
                        {(r.hpp.fifo_avg || r.hpp.master) ? (
                          <span className={r.price.margin < 0
                            ? 'text-red-600 dark:text-red-400'
                            : (r.price.margin < 0.15 * r.price.selling
                              ? 'text-amber-600 dark:text-amber-300'
                              : 'text-emerald-600 dark:text-emerald-300')}
                            data-testid={`rnd-margin-${r.sku}`}>
                            {' '}· margin {rp(r.price.margin)}
                            {` (${Math.round(r.price.margin / r.price.selling * 100)}%)`}
                          </span>
                        ) : (
                          // SESI #37 — HPP belum ada ⇒ katakan "belum bisa diukur".
                          // Dulu bagian ini hanya KOSONG, dan pembaca menyimpulkan
                          // sendiri (biasanya: marginnya bagus).
                          <span data-testid={`rnd-margin-unknown-${r.sku}`}
                            title="HPP belum ada (BOM / biaya jahit belum tercatat)"
                            className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300">
                            margin belum bisa diukur
                          </span>
                        )}
                      </>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5 text-[10px]">
                <span className={`px-1.5 py-0.5 rounded-full flex items-center gap-1 ${
                  r.marketing_sync.synced
                    ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}>
                  <Store className="w-3 h-3" />
                  {r.marketing_sync.synced
                    ? `katalog ${r.marketing_sync.item_count} toko` : 'belum di katalog'}
                </span>
                <span className={`px-1.5 py-0.5 rounded-full flex items-center gap-1 ${
                  r.production.qty_ordered
                    ? 'bg-sky-500/10 text-sky-600' : 'bg-foreground/5 text-foreground/50'}`}>
                  <Factory className="w-3 h-3" />
                  {r.production.qty_ordered
                    ? `SPK ${r.production.qty_ordered} pcs` : 'belum diproduksi'}
                </span>
                <span className="px-1.5 py-0.5 rounded-full bg-foreground/5 text-foreground/60">
                  stok {r.stock_qty}
                </span>
              </div>

              {r.gaps.length ? (
                <ul className="text-[11px] text-amber-600 dark:text-amber-300 space-y-0.5"
                  data-testid={`rnd-gaps-${r.sku}`}>
                  {r.gaps.slice(0, 3).map((g) => (
                    <li key={g} className="flex gap-1.5">
                      <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /> {g}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[11px] text-emerald-600 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Lengkap: BOM, HPP batch, katalog, produksi
                </div>
              )}

              <button data-testid={`rnd-detail-btn-${r.sku}`} onClick={() => openDetail(r.material_id)}
                className="w-full text-xs py-1.5 rounded-lg border border-foreground/10 hover:bg-foreground/5">
                Lihat detail penuh
              </button>
            </GlassCard>
          ))}
          {!shown.length ? (
            <div className="col-span-full py-12 text-center text-sm text-foreground/50">
              Tidak ada produk yang cocok.
            </div>
          ) : null}
        </div>
      )}

      {detail ? (
        <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center p-4"
          data-testid="rnd-detail-modal">
          <div className="bg-[hsl(var(--card))] border border-foreground/10 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-auto">
            <div className="p-5 border-b border-foreground/10 flex items-center justify-between">
              <h2 className="font-semibold">
                {detail.loading ? 'Memuat…' : `${detail.material?.name} · ${detail.material?.code}`}
              </h2>
              <button onClick={() => setDetail(null)} data-testid="rnd-detail-close"
                className="text-foreground/50 hover:text-foreground"><X className="w-5 h-5" /></button>
            </div>
            {detail.loading ? (
              <div className="p-10 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></div>
            ) : (
              <div className="p-5 space-y-4 text-sm">
                <Section title="HPP batch (FIFO)">
                  <div className="text-xs text-foreground/60 mb-1">
                    sumber: {detail.hpp_layers?.source} · rata-rata lapisan bersisa{' '}
                    <b>{rp(detail.hpp_layers?.hpp_fifo_avg)}</b> · batch terakhir{' '}
                    {rp(detail.hpp_layers?.hpp_last_batch)}
                  </div>
                  {(detail.hpp_layers?.layers || []).slice(0, 6).map((l) => (
                    <div key={l.id} className="text-xs flex justify-between border-t border-foreground/5 py-1">
                      <span>{l.batch?.po_number || '—'} · sisa {l.qty_remaining}/{l.qty_in} pcs</span>
                      <span className="font-medium">{rp(l.unit_cost)}</span>
                    </div>
                  ))}
                  {!(detail.hpp_layers?.layers || []).length ? (
                    <p className="text-xs text-amber-600">
                      Belum ada batch masuk gudang — HPP yang terlihat masih perkiraan BOM.
                    </p>
                  ) : null}
                </Section>
                <Section title={`Katalog marketing (${detail.catalog_items?.length || 0} item)`}>
                  {(detail.catalog_items || []).length ? detail.catalog_items.map((c) => (
                    <div key={c.id} className="text-xs flex justify-between border-t border-foreground/5 py-1">
                      <span>{c.name || c.sku}</span>
                      <span>{rp(c.harga_jual || c.unit_price)}</span>
                    </div>
                  )) : (
                    <p className="text-xs text-amber-600">
                      Belum pernah dimasukkan ke katalog toko mana pun.
                    </p>
                  )}
                </Section>
                <Section title="BOM & produksi">
                  <p className="text-xs">
                    BOM: {detail.bom?.exists
                      ? `ada (${detail.bom.line_count} baris bahan)`
                      : 'BELUM ADA — HPP bahan tidak bisa dihitung'}
                  </p>
                  <p className="text-xs text-foreground/60">
                    Model: {detail.model?.name || '—'} ({detail.model?.code || 'tanpa kode'})
                  </p>
                </Section>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ label, value, hint, tone = 'default', testId }) {
  const tones = { default: '', good: 'text-emerald-600 dark:text-emerald-300',
    warn: 'text-amber-600 dark:text-amber-300' };
  return (
    <GlassCard className="p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wide text-foreground/50">{label}</div>
      <div className={`text-xl font-semibold mt-0.5 ${tones[tone]}`}>{value}</div>
      {hint ? <div className="text-[10px] text-foreground/50">{hint}</div> : null}
    </GlassCard>
  );
}

function Section({ title, children }) {
  return (
    <div className="rounded-xl border border-foreground/10 p-3">
      <div className="text-xs font-semibold mb-1.5">{title}</div>
      {children}
    </div>
  );
}
