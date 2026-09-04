/**
 * VariantOnboardingPanel — **Onboarding Produk Platform → Master** (Sesi #28)
 * ═══════════════════════════════════════════════════════════════════════════
 * MASALAH YANG DITUTUP LAYAR INI (diukur, bukan ditebak)
 * ───────────────────────────────────────────────────────────────────────────
 * Sesi #20 membangun Jembatan SKU dan gate-nya hijau — tetapi **tidak satu
 * barang pun pernah dijembatani**. Laporan audit sistem sendiri berkata MERAH:
 *
 *   A1 CRITICAL  NOL dari 601 baris pesanan menunjuk master gudang
 *   A5 HIGH      553 pesanan di antrean gudang, TIDAK SATU PUN siap dialokasikan
 *   A3 HIGH      83 SKU platform dipesan pembeli tetapi belum dikenal master
 *
 * Dua sebab yang diukur:
 *  1. 83 SKU itu berasal dari **8 produk nyata** yang benar-benar belum punya
 *     master (pencarian `Jennifer/Rachel/Victoria/ONA/BIEL/AISAR/RASHA` = 0).
 *  2. Mesin identitas lama **menabrakkan** 65 dari 83 SKU (489 pcs) menjadi
 *     identitas yang sama, karena `POLKA` dibuang dan `PAKAI/TANPA KARET`
 *     tidak dibaca sama sekali. Delapan SKU berbeda jatuh ke satu `hitam/XL`.
 *
 * Kenapa layar ini bekerja PER PRODUK, bukan per SKU: 83 baris satu per satu
 * adalah cara paling pasti membuat fitur sinkronisasi tidak dipakai. Per produk
 * = 8 keputusan.
 *
 * Aturan yang dijaga layar ini:
 *  · **Pratinjau dulu, selalu.** Tidak ada tombol yang menulis tanpa pemilik
 *    melihat lebih dulu daftar varian + SKU yang akan lahir. Kode model pun
 *    dipratinjau dengan MENGINTIP counter, bukan menaikkannya.
 *  · **Nama model tidak diketik** (gate INV-F14). Ia diturunkan server dari
 *    judul platform dan hanya DITAMPILKAN; kalau produknya sudah ada di master,
 *    pemilik MENUNJUKNYA dari pemilih model.
 *  · Backend: `/api/variant-onboarding/*` (core/variant_identity.py). Layar ini
 *    tidak pernah menulis dokumen sendiri.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Sparkles, Loader2, Eye, CheckCircle2, AlertTriangle, RefreshCw, Boxes,
  Palette, Ruler, SlidersHorizontal, Info, Package, Plus, Pencil, Ban, Layers,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apiGet, apiPost, apiDelete } from '@/lib/api';
import { downloadCsv } from '@/lib/csv';
import { CategorySelect, ModelSelect } from './masters/MasterSelects';

const fmt = (v) => Number(v || 0).toLocaleString('id-ID');
const rp = (v) => `Rp ${fmt(Math.round(Number(v || 0)))}`;

/* ─── Chip kecil yang selalu punya LATAR (kontrak INV-F15) ─────────────────── */
function Chip({ icon: Icon, children, tone = 'slate', testId }) {
  const tones = {
    slate: 'bg-foreground/[0.06] text-foreground border-foreground/15',
    emerald: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-800 dark:text-emerald-200 border-emerald-400/40',
    blue: 'bg-blue-100 dark:bg-blue-500/15 text-blue-800 dark:text-blue-200 border-blue-400/40',
    amber: 'bg-amber-100 dark:bg-amber-500/15 text-amber-900 dark:text-amber-200 border-amber-400/40',
    rose: 'bg-rose-100 dark:bg-rose-500/15 text-rose-800 dark:text-rose-200 border-rose-400/40',
  };
  return (
    <span data-testid={testId}
          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {Icon ? <Icon className="w-3 h-3" /> : null}{children}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Dialog: RENCANA onboarding satu produk
   ═══════════════════════════════════════════════════════════════════════════ */
function PlanDialog({ product, onClose, onDone }) {
  const [modelId, setModelId] = useState('');
  const [categoryCode, setCategoryCode] = useState('');
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const qs = new URLSearchParams({ product_key: product.product_key });
      if (modelId) qs.set('model_id', modelId);
      if (categoryCode) qs.set('category_code', categoryCode);
      setPlan(await apiGet(`/variant-onboarding/plan?${qs.toString()}`));
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  }, [product.product_key, modelId, categoryCode]);

  useEffect(() => { load(); }, [load]);

  const apply = async () => {
    setBusy(true);
    try {
      const res = await apiPost('/variant-onboarding/apply', {
        product_key: product.product_key,
        model_id: modelId || undefined,
        category_code: categoryCode || undefined,
      });
      setApplied(res);
      if (res.failures?.length) toast.warning(res.message);
      else toast.success(res.message);
      await load();
      onDone?.();
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  const t = plan?.totals || {};
  const newColors = (plan?.colors || []).filter((c) => !c.exists);
  const newSizes = (plan?.sizes || []).filter((s) => !s.exists);

  return (
    <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto" data-testid="onboarding-plan-dialog">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          Rencana onboarding — {plan?.model?.name || product.proposed_model_name}
        </DialogTitle>
        <DialogDescription>
          Rantai yang dibangun: model → warna/ukuran/<b>opsi</b> → varian → master FG →
          item katalog toko → pemetaan SKU → seluruh pesanan lama ikut tertaut.
          {' '}<b>Belum ada yang ditulis sampai Anda menekan Terapkan.</b>
        </DialogDescription>
      </DialogHeader>

      {/* Judul asli dari platform */}
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.03] p-3 text-xs space-y-1">
        <div className="text-muted-foreground">Judul dari platform</div>
        <div className="font-medium">{product.product_name || '(tanpa nama)'}</div>
        <div className="text-muted-foreground">
          Toko <b>{product.account_name || '—'}</b> · {fmt(product.sku_count)} SKU ·{' '}
          {fmt(product.pcs)} pcs · {rp(product.value)}
        </div>
      </div>

      {/* Pilihan pemilik — TANPA kolom ketik nama model (gate INV-F14) */}
      <div className="grid md:grid-cols-2 gap-3">
        <ModelSelect
          value={modelId} onChange={setModelId}
          label="Tautkan ke model master yang sudah ada (opsional)"
          hint="Biarkan kosong untuk membuat model BARU — namanya diturunkan dari judul platform (lihat di bawah). Nama model sengaja tidak bisa diketik di sini supaya model kembar tidak lahir."
          testId="onb-model-select" />
        <CategorySelect
          value={categoryCode} onChange={setCategoryCode}
          hint="Kategori menentukan prefix kode model. Kosong = pakai usulan sistem."
          testId="onb-category-select" />
      </div>

      {busy && !plan ? (
        <div className="p-10 text-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Menyusun rencana…
        </div>
      ) : null}

      {plan ? (
        <>
          {/* Ringkasan rencana */}
          <div className="rounded-lg border border-blue-400/30 bg-blue-500/[0.07] p-3 text-sm"
               data-testid="onb-plan-summary">
            <div className="flex items-center gap-1.5 font-semibold text-blue-800 dark:text-blue-200 mb-1.5">
              <Eye className="w-4 h-4" />Pratinjau
            </div>
            <div className="text-foreground">{plan.message}</div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              <Chip icon={Package} tone={plan.model.exists ? 'emerald' : 'blue'} testId="onb-chip-model">
                Model {plan.model.exists ? 'sudah ada' : 'baru'}: {plan.model.name} ({plan.model.code})
              </Chip>
              <Chip icon={Layers} tone="slate">Kategori: {plan.model.category_name}</Chip>
              <Chip icon={Boxes} tone="blue" testId="onb-chip-variants">
                {fmt(t.variants_new)} varian baru · {fmt(t.variants_existing)} sudah ada
              </Chip>
              <Chip icon={Palette} tone={newColors.length ? 'amber' : 'slate'}>
                {fmt(t.colors_new)} warna baru
              </Chip>
              <Chip icon={Ruler} tone={newSizes.length ? 'amber' : 'slate'}>
                {fmt(t.sizes_new)} ukuran baru
              </Chip>
              <Chip icon={SlidersHorizontal} tone="slate">
                {fmt((plan.options || []).length)} opsi dipakai
              </Chip>
              <Chip icon={CheckCircle2} tone="emerald" testId="onb-chip-skus">
                {fmt(t.skus_to_map)} SKU akan ditautkan
              </Chip>
              <Chip icon={CheckCircle2} tone="emerald">
                ± {fmt(t.order_lines_to_link)} baris pesanan
              </Chip>
              <Chip icon={t.collisions ? AlertTriangle : CheckCircle2}
                    tone={t.collisions ? 'rose' : 'emerald'} testId="onb-chip-collisions">
                {t.collisions ? `${fmt(t.collisions)} TABRAKAN identitas` : 'tanpa tabrakan identitas'}
              </Chip>
            </div>
          </div>

          {/* Master baru yang akan lahir */}
          {(newColors.length || newSizes.length) ? (
            <div className="rounded-lg border border-amber-400/30 bg-amber-500/[0.07] p-3 text-xs"
                 data-testid="onb-new-masters">
              <div className="font-semibold text-amber-900 dark:text-amber-200 mb-1.5">
                Master baru yang akan dibuat (disalin apa adanya dari variasi platform — tidak ditebak)
              </div>
              <div className="flex flex-wrap gap-1.5">
                {newColors.map((c) => (
                  <Chip key={c.code} icon={Palette} tone="amber">{c.name} → {c.code}</Chip>
                ))}
                {newSizes.map((s) => (
                  <Chip key={s.code} icon={Ruler} tone="amber">{s.code}</Chip>
                ))}
              </div>
            </div>
          ) : null}

          {/* Peringatan bagian variasi yang tidak terbaca */}
          {plan.warnings?.length ? (
            <div className="rounded-lg border border-rose-400/30 bg-rose-500/[0.07] p-3 text-xs"
                 data-testid="onb-warnings">
              <div className="font-semibold text-rose-800 dark:text-rose-200 mb-1 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                {plan.warnings.length} variasi punya bagian yang tidak dikenali
              </div>
              {plan.warnings.slice(0, 5).map((w) => (
                <div key={w.platform_sku_id} className="text-muted-foreground">
                  <span className="font-mono">{w.platform_sku_id}</span> — {w.variation} →{' '}
                  <b>{(w.unreadable || []).join(', ')}</b>
                </div>
              ))}
            </div>
          ) : null}

          {/* Tabel varian yang akan lahir */}
          <div className="rounded-lg border border-foreground/10 overflow-hidden"
               data-testid="onb-variants-table">
            <div className="max-h-[38vh] overflow-auto">
              <table className="w-full text-sm">
                <thead className="bg-foreground/[0.06] sticky top-0">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-semibold">SKU yang akan lahir</th>
                    <th className="px-3 py-2 font-semibold">Warna</th>
                    <th className="px-3 py-2 font-semibold">Ukuran</th>
                    <th className="px-3 py-2 font-semibold">Opsi (dimensi ke-3)</th>
                    <th className="px-3 py-2 font-semibold text-right">Pcs</th>
                    <th className="px-3 py-2 font-semibold text-right">SKU platform</th>
                    <th className="px-3 py-2 font-semibold">Variasi asli</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-foreground/5">
                  {(plan.variants || []).map((v) => (
                    <tr key={v.identity_key} className="hover:bg-foreground/[0.03]">
                      <td className="px-3 py-2 font-mono text-xs font-medium">{v.sku}</td>
                      <td className="px-3 py-2">{v.color_name}</td>
                      <td className="px-3 py-2">{v.size_code}</td>
                      <td className="px-3 py-2">
                        <Chip tone={v.option_code === 'NA' ? 'slate' : 'blue'}>{v.option_name}</Chip>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmt(v.pcs)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmt(v.sku_count)}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground max-w-[18rem] truncate"
                          title={(v.variations || []).join(' | ')}>
                        {(v.variations || []).join(' | ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {applied ? (
            <div className={`rounded-lg border p-3 text-sm ${applied.failures?.length
              ? 'border-amber-400/30 bg-amber-500/[0.07]'
              : 'border-emerald-400/30 bg-emerald-500/[0.07]'}`}
                 data-testid="onb-apply-result">
              <div className="font-semibold text-foreground mb-1 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" />Hasil penerapan
              </div>
              <div className="text-foreground">{applied.message}</div>
              <div className="text-xs text-muted-foreground mt-1">
                Varian dibuat: <b>{fmt(applied.created?.variants)}</b> ·
                {' '}warna baru: <b>{fmt(applied.created?.colors)}</b> ·
                {' '}SKU ditautkan: <b>{fmt(applied.skus_mapped)}</b> ·
                {' '}baris pesanan tertaut: <b>{fmt(applied.order_lines_linked)}</b>
              </div>
              {applied.failures?.length ? (
                <div className="text-xs text-amber-900 dark:text-amber-200 mt-1">
                  {applied.failures.length} gagal: {applied.failures.slice(0, 3)
                    .map((f) => `${f.platform_sku_id} (${f.message})`).join('; ')}
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}

      <DialogFooter>
        <Button variant="outline" onClick={onClose} data-testid="onb-close">Tutup</Button>
        <Button variant="outline" onClick={load} disabled={busy} className="border-foreground/10"
                data-testid="onb-refresh-plan">
          <Eye className="w-4 h-4 mr-1.5" />Susun ulang rencana
        </Button>
        <Button onClick={apply} disabled={busy || !plan} data-testid="onb-apply">
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <CheckCircle2 className="w-4 h-4 mr-1.5" />}
          Terapkan
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB: Onboarding per Produk
   ═══════════════════════════════════════════════════════════════════════════ */
export function ProductOnboardingTab({ onDone }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await apiGet('/variant-onboarding/products')); }
    catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const products = data?.products || [];

  return (
    <div className="space-y-4" data-testid="onboarding-tab">
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.03] p-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
          <Info className="w-3.5 h-3.5" />Kenapa per produk, bukan per SKU
        </div>
        Pada data Anda <b>{fmt(data?.total_skus)} SKU platform</b> hanya berasal dari{' '}
        <b>{fmt(data?.total_products)} produk</b>. Satu keputusan per produk membuat seluruh
        variannya (warna × ukuran × <b>opsi</b>) lahir sekaligus, lalu SKU dan seluruh baris
        pesanan lamanya ikut tertaut. Setiap tombol menampilkan <b>rencana lebih dulu</b>.
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={load} className="border-foreground/10"
                data-testid="onb-reload">
          <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Muat ulang
        </Button>
        <Button variant="outline" size="sm" className="border-foreground/10"
                data-testid="onb-export"
                onClick={() => {
                  const n = downloadCsv('produk-belum-dikenal-gudang',
                    ['Produk', 'Toko', 'Usulan Model', 'Kategori', 'SKU', 'Pcs', 'Nilai',
                     'Identitas', 'Warna', 'Ukuran', 'Opsi', 'Tabrakan'],
                    products.map((p) => [
                      p.product_name, p.account_name, p.proposed_model_name,
                      p.proposed_category_name, p.sku_count, p.pcs, p.value,
                      p.identity_count, (p.colors || []).join(' / '),
                      (p.sizes || []).join(' / '), (p.options || []).join(' / '),
                      p.collisions]));
                  toast.success(`${n} baris diunduh`);
                }}>
          Unduh CSV
        </Button>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <Chip icon={Package} tone="amber" testId="onb-stat-products">
            {fmt(data?.total_products)} produk belum dikenal
          </Chip>
          <Chip icon={Boxes} tone="amber" testId="onb-stat-skus">{fmt(data?.total_skus)} SKU</Chip>
          <Chip icon={Boxes} tone="slate">{fmt(data?.pcs_total)} pcs</Chip>
          <Chip icon={data?.collisions_total ? AlertTriangle : CheckCircle2}
                tone={data?.collisions_total ? 'rose' : 'emerald'} testId="onb-stat-collisions">
            {data?.collisions_total ? `${fmt(data.collisions_total)} tabrakan` : '0 tabrakan identitas'}
          </Chip>
        </div>
      </div>

      {loading ? (
        <div className="p-10 text-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Memuat produk…
        </div>
      ) : products.length === 0 ? (
        <div className="p-10 text-center" data-testid="onb-empty">
          <CheckCircle2 className="w-10 h-10 mx-auto mb-3 text-emerald-600 dark:text-emerald-300" />
          <div className="font-semibold">Semua produk sudah dikenal gudang</div>
          <p className="text-sm text-muted-foreground mt-1">
            Tidak ada SKU platform yang belum tertaut master. Antrean gudang bisa bekerja.
          </p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3" data-testid="onb-product-grid">
          {products.map((p) => (
            <GlassCard key={p.product_key} className="p-4 flex flex-col gap-2.5"
                       data-testid={`onb-card-${p.product_key}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold truncate" title={p.proposed_model_name}>
                    {p.proposed_model_name}
                  </div>
                  <div className="text-[11px] text-muted-foreground line-clamp-2"
                       title={p.product_name}>
                    {p.product_name}
                  </div>
                </div>
                <Badge variant="outline" className="shrink-0 border-foreground/20">
                  {p.proposed_category_name}
                </Badge>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-md bg-foreground/[0.05] py-1.5">
                  <div className="text-lg font-bold tabular-nums">{fmt(p.sku_count)}</div>
                  <div className="text-[10px] text-muted-foreground">SKU</div>
                </div>
                <div className="rounded-md bg-foreground/[0.05] py-1.5">
                  <div className="text-lg font-bold tabular-nums">{fmt(p.pcs)}</div>
                  <div className="text-[10px] text-muted-foreground">pcs dipesan</div>
                </div>
                <div className="rounded-md bg-foreground/[0.05] py-1.5">
                  <div className="text-lg font-bold tabular-nums">{fmt(p.identity_count)}</div>
                  <div className="text-[10px] text-muted-foreground">varian</div>
                </div>
              </div>

              <div className="text-[11px] text-muted-foreground">{rp(p.value)} nilai pesanan</div>

              <div className="flex flex-wrap gap-1">
                <Chip icon={Palette} tone="slate">{(p.colors || []).length} warna</Chip>
                <Chip icon={Ruler} tone="slate">{(p.sizes || []).join(' · ')}</Chip>
                {(p.options || []).length > 1 ? (
                  <Chip icon={SlidersHorizontal} tone="blue">
                    {(p.options || []).length} opsi
                  </Chip>
                ) : null}
                {p.model_exists ? (
                  <Chip icon={CheckCircle2} tone="emerald">model sudah ada</Chip>
                ) : null}
                {p.collisions ? (
                  <Chip icon={AlertTriangle} tone="rose">{p.collisions} tabrakan</Chip>
                ) : null}
                {(p.unreadable || []).length ? (
                  <Chip icon={AlertTriangle} tone="amber">
                    {p.unreadable.length} tak terbaca
                  </Chip>
                ) : null}
              </div>

              <Button size="sm" className="mt-auto" onClick={() => setPicked(p)}
                      data-testid={`onb-plan-${p.product_key}`}>
                <Sparkles className="w-4 h-4 mr-1.5" />Susun Rencana
              </Button>
            </GlassCard>
          ))}
        </div>
      )}

      <Dialog open={Boolean(picked)} onOpenChange={(o) => !o && setPicked(null)}>
        {picked ? (
          <PlanDialog product={picked} onClose={() => setPicked(null)}
                      onDone={() => { load(); onDone?.(); }} />
        ) : null}
      </Dialog>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB: master OPSI VARIAN (dimensi ke-3)
   ═══════════════════════════════════════════════════════════════════════════ */
function OptionDialog({ option, onClose, onDone }) {
  const isNew = !option?.code;
  const [form, setForm] = useState({
    code: option?.code || '', name: option?.name || '',
    order_seq: option?.order_seq ?? 50, notes: option?.notes || '',
    active: option?.active !== false,
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) {
      toast.error('Kode dan nama opsi wajib diisi.');
      return;
    }
    setBusy(true);
    try {
      const res = await apiPost('/variant-onboarding/options', {
        code: form.code.trim().toUpperCase(), name: form.name.trim(),
        order_seq: Number(form.order_seq || 50), notes: form.notes,
        active: Boolean(form.active),
      });
      toast.success(res.message);
      onDone();
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  return (
    <DialogContent className="max-w-lg" data-testid="option-dialog">
      <DialogHeader>
        <DialogTitle>{isNew ? 'Tambah opsi varian' : `Ubah opsi ${option.code}`}</DialogTitle>
        <DialogDescription>
          Opsi adalah <b>dimensi ke-3</b> identitas barang (setelah warna &amp; ukuran).
          Kodenya masuk ke akhir SKU — contoh <span className="font-mono">BLS-0001-PBL-XL-KRT</span>.
          Kode <span className="font-mono">NA</span> berarti listing tidak menyebut opsi dan
          sengaja <b>tidak</b> menambah akhiran SKU.
        </DialogDescription>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Kode (maks 8 huruf)</Label>
          <Input value={form.code} disabled={!isNew} maxLength={8}
                 onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                 placeholder="KRT" data-testid="opt-code" />
        </div>
        <div>
          <Label className="text-xs">Urutan tampil</Label>
          <Input type="number" value={form.order_seq}
                 onChange={(e) => setForm({ ...form, order_seq: e.target.value })}
                 data-testid="opt-order" />
        </div>
        <div className="col-span-2">
          <Label className="text-xs">Nama opsi</Label>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                 placeholder="Pakai Karet" data-testid="opt-name" />
        </div>
        <div className="col-span-2">
          <Label className="text-xs">Keterangan (opsional)</Label>
          <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                 placeholder="Pinggang/lengan memakai karet." data-testid="opt-notes" />
        </div>
        <label className="col-span-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.active}
                 onChange={(e) => setForm({ ...form, active: e.target.checked })}
                 data-testid="opt-active" />
          Aktif (bisa dipakai varian baru)
        </label>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={submit} disabled={busy} data-testid="opt-submit">
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <CheckCircle2 className="w-4 h-4 mr-1.5" />}Simpan
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

export function VariantOptionsTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiGet('/variant-onboarding/options?include_inactive=true');
      setRows(d.rows || []);
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const deactivate = async (code) => {
    try {
      const res = await apiDelete(`/variant-onboarding/options/${code}`);
      toast.success(res.message); load();
    } catch (e) { toast.error(e.message); }
  };

  const totalVariants = useMemo(
    () => rows.reduce((a, r) => a + Number(r.variant_count || 0), 0), [rows]);

  return (
    <div className="space-y-4" data-testid="variant-options-tab">
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.03] p-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
          <SlidersHorizontal className="w-3.5 h-3.5" />Dimensi ke-3: Opsi varian
        </div>
        Sebelum dimensi ini ada, identitas barang hanya <b>warna × ukuran</b> — sehingga{' '}
        <span className="font-mono">BLACK, XL, PAKAI KARET</span> dan{' '}
        <span className="font-mono">BLACK, XL, TANPA KARET</span> tertimpa menjadi satu barang.
        Pada data nyata <b>8 SKU berbeda</b> pernah jatuh ke satu identitas{' '}
        <span className="font-mono">hitam/XL</span>. Sekarang keduanya punya SKU sendiri:{' '}
        <span className="font-mono">…-XL-KRT</span> dan <span className="font-mono">…-XL-NOK</span>.
      </div>

      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={load} className="border-foreground/10"
                data-testid="opt-reload">
          <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Muat ulang
        </Button>
        <Button size="sm" onClick={() => setEdit({})} data-testid="opt-add">
          <Plus className="w-4 h-4 mr-1.5" />Tambah opsi
        </Button>
        <div className="ml-auto text-xs text-muted-foreground">
          {rows.length} opsi · {fmt(totalVariants)} varian memakainya
        </div>
      </div>

      <div className="rounded-lg border border-foreground/10 overflow-hidden"
           data-testid="options-table">
        <table className="w-full text-sm">
          <thead className="bg-foreground/[0.06]">
            <tr className="text-left">
              <th className="px-3 py-2 font-semibold">Kode</th>
              <th className="px-3 py-2 font-semibold">Nama</th>
              <th className="px-3 py-2 font-semibold">Keterangan</th>
              <th className="px-3 py-2 font-semibold text-right">Dipakai varian</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 font-semibold text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-foreground/5">
            {loading ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mx-auto" /></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                Belum ada opsi.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.code} className="hover:bg-foreground/[0.03]"
                  data-testid={`option-row-${r.code}`}>
                <td className="px-3 py-2 font-mono text-xs font-semibold">{r.code}</td>
                <td className="px-3 py-2">{r.name}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground max-w-[22rem]">{r.notes}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(r.variant_count)}</td>
                <td className="px-3 py-2">
                  {r.active === false
                    ? <Chip tone="slate">nonaktif</Chip>
                    : <Chip tone="emerald">aktif</Chip>}
                  {r.is_default ? <Chip tone="blue">bawaan</Chip> : null}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" onClick={() => setEdit(r)}
                          data-testid={`option-edit-${r.code}`}>
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                  {r.code !== 'NA' && r.active !== false ? (
                    <Button variant="ghost" size="sm" onClick={() => deactivate(r.code)}
                            data-testid={`option-off-${r.code}`}>
                      <Ban className="w-3.5 h-3.5 text-rose-600 dark:text-rose-300" />
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(edit)} onOpenChange={(o) => !o && setEdit(null)}>
        {edit ? (
          <OptionDialog option={edit} onClose={() => setEdit(null)}
                        onDone={() => { setEdit(null); load(); }} />
        ) : null}
      </Dialog>
    </div>
  );
}
