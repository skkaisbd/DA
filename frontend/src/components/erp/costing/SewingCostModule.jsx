/**
 * SewingCostModule — **Biaya Jahit SPK & HPP Batch (FIFO)**.
 *
 * Kenapa layar ini ada (diukur sesi #34): `po_items.cmt_price_snapshot` dipakai
 * Monitoring CMT, tagihan CMT, dan kalkulator HPP — tetapi untuk SPK produksi
 * INTERNAL nilainya selalu 0 dan tidak ada satu pun layar yang bisa mengisinya.
 * Jadi HPP produk = biaya bahan saja, dan margin di Katalog Marketing terlihat
 * lebih bagus daripada kenyataan.
 *
 * Aturan pemilik: yang DIKETIK adalah tarif **per SKU per pcs**; sistem yang
 * mengalikan dengan qty (total baris + total SPK). Setelah tarif terisi, HPP
 * batch = bahan (BOM) + jahit (SPK) + permak + upah internal, dan angka itulah
 * yang menjadi lapisan FIFO saat barang jadi masuk gudang.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Scissors, RefreshCw, Search, Save, Wand2, AlertTriangle, CheckCircle2,
  Loader2, Layers, ArrowRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { apiGet, apiPut, apiPost } from '@/lib/api';

const rp = (v) => `Rp ${Math.round(Number(v || 0)).toLocaleString('id-ID')}`;
const num = (v) => Number(v || 0).toLocaleString('id-ID');

function SummaryCard({ label, value, hint, tone = 'default', testId }) {
  const tones = {
    default: 'text-foreground',
    good: 'text-emerald-600 dark:text-emerald-300',
    warn: 'text-amber-600 dark:text-amber-300',
  };
  return (
    <GlassCard className="p-4" data-testid={testId}>
      <div className="text-xs uppercase tracking-wide text-foreground/50">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-foreground/50">{hint}</div> : null}
    </GlassCard>
  );
}

export default function SewingCostModule({ onNavigate }) {
  const [pos, setPos] = useState([]);
  const [q, setQ] = useState('');
  const [onlyMissing, setOnlyMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [draft, setDraft] = useState({});
  const [applySameSku, setApplySameSku] = useState(true);
  const [saving, setSaving] = useState(false);
  // SESI #34 — baris SPK yang SKU-nya tidak ada di master: selama belum
  // ditautkan, ongkos jahit yang diisi di layar ini TIDAK akan pernah masuk HPP.
  // Karena itu usulan pasangannya dibawa ke layar yang sama, bukan layar lain.
  const [unlinked, setUnlinked] = useState({});
  const [linking, setLinking] = useState('');

  const loadUnlinked = useCallback(async () => {
    try {
      const res = await apiGet('/production/sewing-cost/unlinked?limit=300');
      const map = {};
      (res?.data || []).forEach((r) => { map[r.po_item_id] = r; });
      setUnlinked(map);
    } catch { /* daftar usulan bersifat tambahan — kegagalannya tidak menutup layar */ }
  }, []);

  const linkToMaster = async (poItemId, cand) => {
    setLinking(poItemId);
    try {
      await apiPost(`/production/sewing-cost/link/${poItemId}`,
        { material_id: cand.material_id, note: (cand.reasons || []).join(' · ') });
      toast.success(`Ditautkan ke master ${cand.code}`);
      await loadUnlinked();
      if (detail?.po?.id) await loadDetail(detail.po.id);
    } catch (e) {
      toast.error(e.message || 'Gagal menautkan');
    } finally {
      setLinking('');
    }
  };

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet(
        `/production/sewing-cost/pos?limit=100${onlyMissing ? '&only_missing=true' : ''}${q ? `&q=${encodeURIComponent(q)}` : ''}`,
      );
      setPos(res?.data || []);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat daftar SPK');
    } finally {
      setLoading(false);
    }
  }, [onlyMissing, q]);

  const loadDetail = useCallback(async (poId) => {
    setSelected(poId);
    setDetail(null);
    setDraft({});
    try {
      const res = await apiGet(`/production/sewing-cost/pos/${poId}`);
      setDetail(res);
      const d = {};
      (res?.items || []).forEach((it) => { d[it.po_item_id] = it.rate_per_pcs || ''; });
      setDraft(d);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat detail SPK');
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadUnlinked(); }, [loadUnlinked]);

  const totals = useMemo(() => {
    const items = detail?.items || [];
    let qty = 0; let sewing = 0; let hpp = 0; let missing = 0;
    items.forEach((it) => {
      const rate = Number(draft[it.po_item_id] || 0);
      qty += it.qty;
      sewing += rate * it.qty;
      const base = (it.hpp_preview?.unit_cost || 0) - (it.hpp_preview?.sewing_cost || 0);
      hpp += (base + rate) * it.qty;
      if (!rate) missing += 1;
    });
    return { qty, sewing, hpp, missing, avgSewing: qty ? sewing / qty : 0, avgHpp: qty ? hpp / qty : 0 };
  }, [detail, draft]);

  const save = async () => {
    if (!detail) return;
    const items = Object.entries(draft)
      .filter(([, v]) => v !== '' && v !== null)
      .map(([po_item_id, v]) => ({ po_item_id, rate_per_pcs: Number(v) }));
    if (!items.length) { toast.error('Belum ada tarif yang diisi'); return; }
    setSaving(true);
    try {
      const res = await apiPut(`/production/sewing-cost/pos/${detail.po.id}`,
        { items, apply_same_sku: applySameSku });
      toast.success(`${res.updated} tarif jahit tersimpan${res.also_updated_same_sku ? ` (+${res.also_updated_same_sku} baris SKU sama)` : ''}`);
      await loadDetail(detail.po.id);
      await loadList();
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan tarif');
    } finally {
      setSaving(false);
    }
  };

  const useSuggestions = () => {
    const d = { ...draft };
    let n = 0;
    (detail?.items || []).forEach((it) => {
      const s = Number(it.suggestion?.rate || 0);
      if (s > 0 && !Number(d[it.po_item_id] || 0)) { d[it.po_item_id] = s; n += 1; }
    });
    setDraft(d);
    toast.success(n ? `${n} baris memakai usulan tarif` : 'Tidak ada usulan tarif yang bisa dipakai');
  };

  return (
    <div className="space-y-6" data-testid="sewing-cost-module">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Scissors className="w-6 h-6" /> Biaya Jahit SPK &amp; HPP Batch
          </h1>
          <p className="text-sm text-foreground/60 mt-1">
            Isi tarif jahit <b>per SKU per pcs</b>; total dihitung sistem. Tarif ini masuk HPP batch
            (bahan + jahit + permak + upah internal) saat barang jadi diterima gudang.
          </p>
        </div>
        <button data-testid="sewing-refresh-btn" onClick={loadList}
          className="px-3 py-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> Muat ulang
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="p-4 lg:col-span-1">
          <div className="flex items-center gap-2 mb-3">
            <Search className="w-4 h-4 text-foreground/40" />
            <input data-testid="sewing-search-input" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Cari nomor SPK…"
              className="flex-1 bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-1.5 text-sm" />
          </div>
          <label className="flex items-center gap-2 text-xs text-foreground/60 mb-3">
            <input data-testid="sewing-only-missing" type="checkbox" checked={onlyMissing}
              onChange={(e) => setOnlyMissing(e.target.checked)} />
            hanya SPK yang tarifnya belum lengkap
          </label>
          <div className="space-y-1.5 max-h-[520px] overflow-auto pr-1" data-testid="sewing-po-list">
            {loading ? (
              <div className="py-8 text-center text-foreground/50 text-sm flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> memuat…
              </div>
            ) : pos.length === 0 ? (
              <div className="py-8 text-center text-foreground/50 text-sm">Tidak ada SPK yang cocok.</div>
            ) : pos.map((p) => (
              <button key={p.po_id} data-testid={`sewing-po-${p.po_number}`}
                onClick={() => loadDetail(p.po_id)}
                className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                  selected === p.po_id
                    ? 'border-primary/40 bg-primary/10'
                    : 'border-foreground/10 hover:bg-foreground/5'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{p.po_number}</span>
                  {p.complete
                    ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    : <AlertTriangle className="w-4 h-4 text-amber-500" />}
                </div>
                <div className="text-xs text-foreground/50 mt-0.5">
                  {p.business_type === 'internal' ? 'Internal' : p.vendor_name} · {num(p.qty_total)} pcs ·{' '}
                  {p.items_with_rate}/{p.item_count} tarif
                </div>
                <div className="text-xs text-foreground/60 mt-0.5">
                  ongkos jahit {rp(p.sewing_total)}{p.sewing_avg_per_pcs ? ` · ${rp(p.sewing_avg_per_pcs)}/pcs` : ''}
                </div>
              </button>
            ))}
          </div>
        </GlassCard>

        <div className="lg:col-span-2 space-y-4">
          {!detail ? (
            <GlassCard className="p-10 text-center text-foreground/50 text-sm" data-testid="sewing-empty">
              Pilih satu SPK di kiri untuk mengisi tarif jahit per SKU.
            </GlassCard>
          ) : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <SummaryCard testId="sewing-total-qty" label="Qty SPK" value={`${num(totals.qty)} pcs`} />
                <SummaryCard testId="sewing-total-cost" label="Total ongkos jahit" value={rp(totals.sewing)}
                  hint={totals.qty ? `${rp(totals.avgSewing)} / pcs` : ''} tone="good" />
                <SummaryCard testId="sewing-total-hpp" label="HPP batch (total)" value={rp(totals.hpp)}
                  hint={totals.qty ? `${rp(totals.avgHpp)} / pcs` : ''} />
                <SummaryCard testId="sewing-missing" label="Tarif belum diisi"
                  value={`${totals.missing} baris`} tone={totals.missing ? 'warn' : 'good'}
                  hint={detail?.totals?.items_broken_ssot
                    ? `${detail.totals.items_broken_ssot} baris belum tertaut master`
                    : 'semua baris tertaut master'} />
              </div>

              <GlassCard className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="text-sm font-medium">
                    {detail.po.po_number}
                    <span className="text-foreground/50 font-normal"> · {detail.po.vendor_name} · {detail.po.status}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button data-testid="sewing-use-suggestion" onClick={useSuggestions}
                      className="px-3 py-1.5 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-xs flex items-center gap-1.5">
                      <Wand2 className="w-3.5 h-3.5" /> Pakai usulan tarif
                    </button>
                    <label className="flex items-center gap-1.5 text-xs text-foreground/60">
                      <input data-testid="sewing-apply-same-sku" type="checkbox" checked={applySameSku}
                        onChange={(e) => setApplySameSku(e.target.checked)} />
                      SKU sama ikut terisi
                    </label>
                    <button data-testid="sewing-save-btn" onClick={save} disabled={saving}
                      className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs flex items-center gap-1.5 disabled:opacity-50">
                      {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Simpan tarif
                    </button>
                  </div>
                </div>

                <div className="overflow-auto">
                  <table className="w-full text-sm" data-testid="sewing-items-table">
                    <thead>
                      <tr className="text-xs uppercase tracking-wide text-foreground/50 border-b border-foreground/10">
                        <th className="text-left py-2 px-2">SKU / Produk</th>
                        <th className="text-right py-2 px-2">Qty</th>
                        <th className="text-right py-2 px-2">Jahit / pcs</th>
                        <th className="text-right py-2 px-2">Total jahit</th>
                        <th className="text-right py-2 px-2">Bahan / pcs</th>
                        <th className="text-right py-2 px-2">HPP / pcs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detail.items || []).map((it) => {
                        const rate = Number(draft[it.po_item_id] || 0);
                        const base = (it.hpp_preview?.unit_cost || 0) - (it.hpp_preview?.sewing_cost || 0);
                        return (
                          <tr key={it.po_item_id} className="border-b border-foreground/5"
                            data-testid={`sewing-row-${it.sku}`}>
                            <td className="py-2 px-2">
                              <div className="font-medium">{it.sku || '—'}</div>
                              <div className="text-xs text-foreground/50">
                                {it.product_name} {it.size ? `· ${it.size}` : ''} {it.color ? `· ${it.color}` : ''}
                              </div>
                              {it.suggestion?.rate > 0 && !rate ? (
                                <button className="text-xs text-primary hover:underline mt-0.5"
                                  data-testid={`sewing-suggest-${it.sku}`}
                                  onClick={() => setDraft((d) => ({ ...d, [it.po_item_id]: it.suggestion.rate }))}>
                                  usulan {rp(it.suggestion.rate)} — {it.suggestion.note}
                                </button>
                              ) : null}
                              {/* SSOT: kalau item SPK tidak menunjuk master, biaya
                                  jahit yang diisi TIDAK akan sampai ke HPP produk.
                                  Ini dikatakan di baris itu sendiri. */}
                              {/* Usulan pasangan master — SEKALI KLIK, tetapi
                                  tetap keputusan manusia, dan alasannya disebut. */}
                              {(unlinked[it.po_item_id]?.candidates || []).slice(0, 2).map((c) => (
                                <button key={c.material_id} type="button"
                                  disabled={linking === it.po_item_id}
                                  data-testid={`sewing-link-${it.sku}-${c.code}`}
                                  onClick={() => linkToMaster(it.po_item_id, c)}
                                  className={`mt-1 mr-1 px-1.5 py-0.5 rounded border text-[11px] disabled:opacity-50 ${
                                    c.confident
                                      ? 'border-emerald-500/50 text-emerald-600 hover:bg-emerald-500/10'
                                      : 'border-foreground/20 text-foreground/60 hover:bg-foreground/5'}`}>
                                  tautkan ke {c.code} ({Math.round(c.score * 100)}%) — {(c.reasons || []).join(', ')}
                                </button>
                              ))}
                              {unlinked[it.po_item_id] && !(unlinked[it.po_item_id].candidates || []).length ? (
                                <div className="text-[11px] text-foreground/50 mt-0.5">
                                  Tidak ada kandidat master yang mirip — buat SKU-nya dulu di Master Produk / RnD.
                                </div>
                              ) : null}
                              {(it.ssot?.messages || []).map((m) => (
                                <div key={m} data-testid={`sewing-ssot-${it.sku}`}
                                  className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                                  {m}
                                </div>
                              ))}
                              {/* Kekurangan yang SUDAH disebut baris SSOT tidak
                                  diulang — pesan kembar membuat orang berhenti
                                  membaca peringatan sama sekali. */}
                              {(it.hpp_preview?.gaps || [])
                                .filter((g) => !g.includes('biaya jahit'))
                                .filter((g) => !(it.ssot?.messages || []).length
                                  || !(g.includes('model') || g.includes('BOM')))
                                .map((g) => (
                                <div key={g} className="text-xs text-amber-600 dark:text-amber-300 mt-0.5">{g}</div>
                              ))}
                            </td>
                            <td className="text-right py-2 px-2">{num(it.qty)}</td>
                            <td className="text-right py-2 px-2">
                              <input data-testid={`sewing-rate-${it.sku}`} type="number" min="0" step="100"
                                value={draft[it.po_item_id] ?? ''}
                                onChange={(e) => setDraft((d) => ({ ...d, [it.po_item_id]: e.target.value }))}
                                className="w-28 text-right bg-foreground/5 border border-foreground/10 rounded-md px-2 py-1" />
                            </td>
                            <td className="text-right py-2 px-2">{rp(rate * it.qty)}</td>
                            <td className="text-right py-2 px-2 text-foreground/60">
                              {rp(it.hpp_preview?.material_cost)}
                            </td>
                            <td className="text-right py-2 px-2 font-medium">{rp(base + rate)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 text-xs text-foreground/50 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  HPP/pcs = bahan (BOM × harga pembelian) + jahit (baris ini) + permak + upah internal.
                  Angka ini menjadi lapisan HPP batch (FIFO) begitu barang jadi lolos QC masuk gudang.
                  {onNavigate ? (
                    <button className="text-primary hover:underline inline-flex items-center gap-1"
                      data-testid="sewing-goto-hpp" onClick={() => onNavigate('fin-hpp-produk')}>
                      lihat kalkulator HPP <ArrowRight className="w-3 h-3" />
                    </button>
                  ) : null}
                </div>
              </GlassCard>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
