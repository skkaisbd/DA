/**
 * SkuBridgeModule — **Jembatan SKU: Marketing ⇄ Gudang** (Sesi #20)
 * ═══════════════════════════════════════════════════════════════════════════
 * MASALAH YANG DITUTUP LAYAR INI (diukur, bukan ditebak)
 * ───────────────────────────────────────────────────────────────────────────
 * Keluhan pemilik: "list barang dari marketing untuk dikirimkan oleh tim gudang
 * tidak ada yang sama, id-nya antara gudang dan marketing tidak sinkron".
 *
 * Terukur pada data hidup: **0 dari 601** baris pesanan marketing menunjuk
 * master gudang, dan **83 SKU platform** tidak dikenal master. Penyebabnya dua
 * semesta identitas — marketing memakai `platform_sku_id` (angka milik
 * TikTok/Shopee), gudang memakai UUID + kode FG. Jembatannya ada di kode, tetapi
 * pintunya hanya di dalam sesi impor ⇒ begitu sesi dihapus, SKU itu mustahil
 * dipetakan.
 *
 * Layar ini memberi pintu yang berdiri sendiri, dengan tiga aksi yang mengikuti
 * keadaan master (bukan satu tombol "cocokkan" yang menebak):
 *   · **Tautkan**            — varian (model+warna+ukuran) SUDAH ada di master.
 *   · **Buat Varian**        — modelnya ada, warna/ukuran ini belum.
 *   · **Buat Master**        — belum ada yang mirip; model + varian baru dibuat.
 *
 * Backend: `/api/sku-bridge/*` (core/sku_bridge.py). Semua penulisan tautan
 * lewat SSOT itu; layar ini tidak pernah menulis dokumen sendiri.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Link2, Search, RefreshCw, Loader2, AlertTriangle, CheckCircle2, Plus,
  Wand2, Trash2, PackageSearch, Store, ArrowRight, Info, Eye, Layers,
  ShoppingBag, Boxes, Sparkles, ShieldCheck, Download,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apiGet, apiPost, apiDelete } from '@/lib/api';
import { downloadCsv } from '@/lib/csv';
import { ColorSelect, SizeSelect, ModelSelect } from './masters/MasterSelects';
// Sesi #28 — onboarding PER PRODUK + master Opsi (dimensi ke-3). Jembatan #20
// benar tetapi 0 dari 601 baris pesanan pernah tertaut: 83 SKU dari 8 produk
// nyata tidak punya master, dan mesin identitas lama menabrakkan 65 di antaranya.
import { ProductOnboardingTab, VariantOptionsTab } from './VariantOnboardingPanel';

const fmt = (v) => Number(v || 0).toLocaleString('id-ID');
const rp = (v) => `Rp ${fmt(Math.round(Number(v || 0)))}`;

const ACTION_META = {
  map: {
    label: 'Tautkan', tone: 'text-emerald-700 dark:text-emerald-300',
    chip: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/40',
    icon: Link2, hint: 'Varian sudah ada di master — cukup ditautkan',
  },
  create_variant: {
    label: 'Buat Varian', tone: 'text-blue-700 dark:text-blue-300',
    chip: 'bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400/40',
    icon: Plus, hint: 'Model sudah ada, warna/ukuran ini belum',
  },
  create_master: {
    label: 'Buat Master', tone: 'text-amber-700 dark:text-amber-300',
    chip: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/40',
    icon: Sparkles, hint: 'Belum ada master yang mirip — buat model + varian baru',
  },
};

/* ─── Kartu KPI ────────────────────────────────────────────────────────────── */
function Kpi({ icon: Icon, label, value, sub, tone = 'text-foreground', testId }) {
  return (
    <GlassCard className="p-4" data-testid={testId}>
      <div className="flex items-center justify-between mb-2">
        <Icon className={`w-5 h-5 ${tone}`} />
      </div>
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
      {sub ? <div className="text-[11px] text-muted-foreground/70 mt-1">{sub}</div> : null}
    </GlassCard>
  );
}

/* ─── Bar kemajuan tautan ──────────────────────────────────────────────────── */
function LinkageBar({ health }) {
  const pct = Number(health?.lines_linked_pct || 0);
  const tone = pct >= 90 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <GlassCard className="p-5" hover={false} data-testid="linkage-progress">
      <div className="flex items-end justify-between mb-2">
        <div>
          <div className="text-sm font-semibold">Kesiapan barang untuk dikirim gudang</div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {fmt(health?.lines_linked)} dari {fmt(health?.lines)} baris pesanan sudah menunjuk
            barang gudang. Baris yang belum tertaut TIDAK bisa dialokasikan.
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold tabular-nums">{pct}%</div>
          <div className="text-[11px] text-muted-foreground">tertaut</div>
        </div>
      </div>
      <div className="h-2.5 w-full rounded-full bg-foreground/10 overflow-hidden">
        <div className={`h-full ${tone} rounded-full transition-[width] duration-500`}
             style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs text-muted-foreground">
        <span>Pesanan siap dikerjakan: <b className="text-emerald-700 dark:text-emerald-300">{fmt(health?.orders_ready)}</b></span>
        <span>Sebagian tertaut: <b className="text-amber-700 dark:text-amber-300">{fmt(health?.orders_partial)}</b></span>
        <span>Belum bisa dikerjakan: <b className="text-rose-700 dark:text-rose-300">{fmt(health?.orders_blocked)}</b></span>
        <span>Pemetaan aktif: <b>{fmt(health?.bridge_mappings)}</b></span>
      </div>
    </GlassCard>
  );
}

/* ─── Dialog: pilih sasaran manual ─────────────────────────────────────────── */
function ManualPickDialog({ row, onClose, onDone }) {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiGet(`/sku-bridge/targets?q=${encodeURIComponent(q)}&limit=60`);
      setRows(d.rows || []);
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, [q]);

  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const pick = async (c) => {
    setSaving(c.target_id);
    try {
      const body = {
        platform_sku_id: row.platform_sku_id,
        account_id: row.account_id,
        product_name: row.product_name,
        variation: row.variation,
      };
      if (c.kind === 'catalog_item') body.catalog_item_id = c.target_id;
      else body.variant_id = c.target_id;
      const res = await apiPost('/sku-bridge/map', body);
      toast.success(res.message || 'SKU ditautkan');
      onDone();
    } catch (e) { toast.error(e.message); } finally { setSaving(''); }
  };

  return (
    <DialogContent className="max-w-3xl" data-testid="manual-pick-dialog">
      <DialogHeader>
        <DialogTitle>Pilih barang gudang untuk SKU ini</DialogTitle>
        <DialogDescription>
          {row.product_name || '(tanpa nama)'} · variasi <b>{row.variation || '—'}</b> ·
          {' '}{fmt(row.pcs)} pcs di {fmt(row.orders)} pesanan
        </DialogDescription>
      </DialogHeader>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} className="pl-9"
               placeholder="Cari nama produk / SKU master…" data-testid="manual-pick-search" />
      </div>
      <div className="max-h-[46vh] overflow-auto rounded-lg border border-foreground/10 divide-y divide-foreground/5">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Mencari…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground/70">
            <PackageSearch className="w-10 h-10 mx-auto opacity-20 mb-2" />
            Tidak ada master yang cocok. Pakai tombol <b>Buat Master</b> di daftar utama.
          </div>
        ) : rows.map((c) => (
          <div key={`${c.kind}-${c.target_id}`}
               className="flex items-center justify-between gap-3 p-3 hover:bg-foreground/5">
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">{c.label || '(tanpa nama)'}</div>
              <div className="text-xs text-muted-foreground">
                <span className="font-mono">{c.sku || '—'}</span>
                {' · '}
                {c.kind === 'catalog_item' ? 'item katalog jual' : 'varian model internal'}
                {c.stock != null ? ` · stok ${fmt(c.stock)}` : ''}
              </div>
            </div>
            <Button size="sm" disabled={saving === c.target_id} onClick={() => pick(c)}
                    data-testid={`manual-pick-${c.sku || c.target_id}`}>
              {saving === c.target_id
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <><Link2 className="w-4 h-4 mr-1.5" />Tautkan</>}
            </Button>
          </div>
        ))}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Tutup</Button>
      </DialogFooter>
    </DialogContent>
  );
}

/* ─── Dialog: buat master / varian dari SKU ────────────────────────────────── */
function CreateMasterDialog({ row, onClose, onDone }) {
  const mm = row.model_match || {};
  const suggestedModelId = row.recommended_action === 'create_variant' ? (mm.model_id || '') : '';
  // Nama model TIDAK diketik: kalau produknya sudah ada, model dipilih dari master;
  // kalau benar-benar baru, namanya DITURUNKAN server dari judul platform (lihat
  // `core.sku_bridge.clean_product_name`) dan hanya ditampilkan. Mengetik nama di
  // sini adalah cara paling pasti melahirkan model kembar — persis cacat yang
  // dijaga gate INV-F14.
  const [form, setForm] = useState({
    model_id: suggestedModelId,
    color_name: row.parsed?.color || '',
    size_code: row.parsed?.size || '',
    retail_price: '',
    hpp: '',
  });
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const useExistingModel = Boolean(form.model_id);

  const payload = (apply) => ({
    platform_sku_id: row.platform_sku_id,
    product_name: row.product_name,
    variation: row.variation,
    account_id: row.account_id,
    model_id: form.model_id || undefined,
    color_name: form.color_name || undefined,
    size_code: form.size_code || undefined,
    retail_price: Number(form.retail_price || 0),
    hpp: Number(form.hpp || 0),
    apply,
  });

  const preview = async () => {
    setBusy(true);
    try { setPlan(await apiPost('/sku-bridge/create-master', payload(false))); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  useEffect(() => { preview(); /* eslint-disable-next-line */ }, [form.model_id, form.color_name, form.size_code]);

  const submit = async () => {
    setBusy(true);
    try {
      const res = await apiPost('/sku-bridge/create-master', payload(true));
      toast.success(res.message || 'Master dibuat & SKU ditautkan');
      onDone();
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  return (
    <DialogContent className="max-w-2xl" data-testid="create-master-dialog">
      <DialogHeader>
        <DialogTitle>
          {useExistingModel ? 'Buat varian baru & tautkan' : 'Buat master produk & tautkan'}
        </DialogTitle>
        <DialogDescription>
          Rantai yang dibuat: {useExistingModel ? '' : 'model → '}varian → master FG →
          item katalog toko → pemetaan SKU → seluruh pesanan lama ikut tertaut.
        </DialogDescription>
      </DialogHeader>

      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.03] p-3 text-xs space-y-1">
        <div className="text-muted-foreground">Judul dari platform</div>
        <div className="font-medium">{row.product_name || '(tanpa nama)'}</div>
        <div className="text-muted-foreground">
          Variasi: <b>{row.variation || '—'}</b> · SKU platform:{' '}
          <span className="font-mono">{row.platform_sku_id}</span> ·{' '}
          {fmt(row.pcs)} pcs di {fmt(row.orders)} pesanan
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <ModelSelect
            value={form.model_id}
            onChange={(v) => setForm({ ...form, model_id: v })}
            label="Model produk di master"
            hint={useExistingModel
              ? 'Hanya variannya yang dibuat — model tidak digandakan.'
              : 'Biarkan kosong untuk membuat model BARU; namanya diambil dari judul platform (lihat pratinjau) dan bisa diubah nanti di Master Produk.'}
            testId="cm-model-select" />
        </div>
        <ColorSelect value={form.color_name}
                     onChange={(v) => setForm({ ...form, color_name: v })}
                     hint="Terbaca dari variasi platform bila cocok dengan master."
                     testId="cm-color-select" />
        <SizeSelect value={form.size_code}
                    onChange={(v) => setForm({ ...form, size_code: v })}
                    hint="Kosong ⇒ dipakai ALLSIZE."
                    testId="cm-size-select" />
        {!useExistingModel && (
          <>
            <div>
              <Label className="text-xs">Harga jual resmi (opsional)</Label>
              <Input type="number" value={form.retail_price}
                     onChange={(e) => setForm({ ...form, retail_price: e.target.value })}
                     placeholder="0" data-testid="cm-price" />
            </div>
            <div>
              <Label className="text-xs">HPP (opsional)</Label>
              <Input type="number" value={form.hpp}
                     onChange={(e) => setForm({ ...form, hpp: e.target.value })}
                     placeholder="0" data-testid="cm-hpp" />
            </div>
          </>
        )}
      </div>

      {plan?.plan && (
        <div className="rounded-lg border border-blue-400/30 bg-blue-500/[0.06] p-3 text-xs"
             data-testid="cm-plan">
          <div className="flex items-center gap-1.5 font-semibold text-blue-700 dark:text-blue-300 mb-1">
            <Eye className="w-3.5 h-3.5" />Pratinjau
          </div>
          <div>{plan.message}</div>
        </div>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button variant="outline" onClick={preview} disabled={busy} data-testid="cm-preview">
          <Eye className="w-4 h-4 mr-1.5" />Pratinjau ulang
        </Button>
        <Button onClick={submit} disabled={busy} data-testid="cm-submit">
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1.5" />}
          Buat &amp; Tautkan
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

/* ─── Tab: penyelesaian massal ─────────────────────────────────────────────── */
function BulkPanel({ onDone }) {
  const [actions, setActions] = useState({ map: true, create_variant: true, create_master: false });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (apply) => {
    const chosen = Object.entries(actions).filter(([, v]) => v).map(([k]) => k);
    if (!chosen.length) { toast.error('Pilih minimal satu jenis aksi.'); return; }
    setBusy(true);
    try {
      const d = await apiPost('/sku-bridge/bulk-resolve', { actions: chosen, limit: 300, apply });
      setRes(d);
      if (apply) { toast.success(d.message); onDone(); }
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  const boxes = [
    { key: 'map', title: 'Tautkan yang sudah ada', desc: 'Varian model+warna+ukuran sudah ada di master. Paling aman.' },
    { key: 'create_variant', title: 'Buat varian di model yang cocok', desc: 'Model dikenali, hanya warna/ukuran ini yang belum ada.' },
    { key: 'create_master', title: 'Buat model produk BARU', desc: 'Menambah master produk baru. Pilih sadar — periksa pratinjaunya.' },
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.03] p-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
          <Info className="w-3.5 h-3.5" />Cara kerjanya
        </div>
        Mesin memeriksa setiap SKU yang belum dikenal, lalu mengerjakan aksi yang sesuai
        keadaan masternya. Yang keyakinannya kurang <b>tidak</b> dikerjakan otomatis — ia
        dikembalikan ke daftar supaya Anda yang memutuskan. Jalankan <b>Pratinjau</b> dulu:
        pratinjau tidak menulis apa pun.
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {boxes.map((b) => (
          <button key={b.key} type="button" onClick={() => setActions({ ...actions, [b.key]: !actions[b.key] })}
                  data-testid={`bulk-toggle-${b.key}`}
                  className={`text-left rounded-lg border p-3 transition-[background-color,border-color] ${
                    actions[b.key]
                      ? 'border-primary/50 bg-primary/[0.08]'
                      : 'border-foreground/10 bg-foreground/[0.02] hover:bg-foreground/[0.05]'}`}>
            <div className="flex items-center gap-2 text-sm font-medium">
              <span className={`w-4 h-4 rounded border flex items-center justify-center ${
                actions[b.key] ? 'bg-primary border-primary' : 'border-foreground/30'}`}>
                {actions[b.key] && <CheckCircle2 className="w-3 h-3 text-primary-foreground" />}
              </span>
              {b.title}
            </div>
            <p className="text-xs text-muted-foreground mt-1.5">{b.desc}</p>
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <Button variant="outline" onClick={() => run(false)} disabled={busy} data-testid="bulk-preview">
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Eye className="w-4 h-4 mr-1.5" />}
          Pratinjau
        </Button>
        <Button onClick={() => run(true)} disabled={busy || !res} data-testid="bulk-apply">
          <Wand2 className="w-4 h-4 mr-1.5" />Terapkan
        </Button>
        {!res && <span className="text-xs text-muted-foreground self-center">Pratinjau dulu sebelum menerapkan.</span>}
      </div>

      {res && (
        <div className="space-y-3" data-testid="bulk-result">
          <div className="rounded-lg border border-emerald-400/30 bg-emerald-500/[0.07] p-3 text-sm">
            <b>{res.message}</b>
            {!res.dry_run && (
              <div className="text-xs text-muted-foreground mt-1">
                Model baru: {fmt(res.created_models)} · Varian baru: {fmt(res.created_variants)} ·
                {' '}Pesanan tertaut: {fmt(res.orders_updated)}
              </div>
            )}
          </div>
          <div className="grid lg:grid-cols-2 gap-3">
            <div className="rounded-lg border border-foreground/10 overflow-hidden">
              <div className="px-3 py-2 text-xs font-semibold bg-foreground/[0.04]">
                Akan dikerjakan ({fmt(res.applied_count)})
              </div>
              <div className="max-h-72 overflow-auto divide-y divide-foreground/5">
                {(res.applied || []).map((a, i) => (
                  <div key={i} className="px-3 py-2 text-xs">
                    <Badge variant="outline" className={ACTION_META[a.action]?.chip}>
                      {ACTION_META[a.action]?.label || a.action}
                    </Badge>
                    <span className="ml-2">{a.will_create || a.target_sku}</span>
                    <span className="text-muted-foreground"> · {fmt(a.pcs)} pcs</span>
                  </div>
                ))}
                {!(res.applied || []).length && (
                  <div className="px-3 py-6 text-center text-xs text-muted-foreground">Tidak ada.</div>
                )}
              </div>
            </div>
            <div className="rounded-lg border border-foreground/10 overflow-hidden">
              <div className="px-3 py-2 text-xs font-semibold bg-foreground/[0.04]">
                Disisakan untuk Anda ({fmt(res.skipped_count)})
              </div>
              <div className="max-h-72 overflow-auto divide-y divide-foreground/5">
                {(res.skipped || []).map((s, i) => (
                  <div key={i} className="px-3 py-2 text-xs">
                    <div className="font-medium truncate">{s.product_name || s.platform_sku_id}</div>
                    <div className="text-muted-foreground">{s.reason}</div>
                  </div>
                ))}
                {!(res.skipped || []).length && (
                  <div className="px-3 py-6 text-center text-xs text-muted-foreground">Tidak ada.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Tab: pemetaan yang sudah ada ─────────────────────────────────────────── */
function MappedPanel({ reloadKey, onChanged }) {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiGet(`/sku-bridge/mappings?limit=300${q ? `&q=${encodeURIComponent(q)}` : ''}`);
      setRows(d.rows || []);
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, [q]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load, reloadKey]);

  const unmap = async (psid) => {
    try {
      const res = await apiDelete(`/sku-bridge/mappings/${psid}`);
      toast.success(res.message || 'Pemetaan dilepas');
      load(); onChanged();
    } catch (e) { toast.error(e.message); }
  };

  return (
    <div className="space-y-3">
      <div className="relative max-w-md">
        <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} className="pl-9"
               placeholder="Cari SKU platform / nama master…" data-testid="mapped-search" />
      </div>
      {loading ? (
        <div className="py-12 text-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Memuat…
        </div>
      ) : rows.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground/70" data-testid="mapped-empty">
          <Link2 className="w-10 h-10 mx-auto opacity-20 mb-2" />
          Belum ada pemetaan. Tautkan SKU di tab <b>Belum Tertaut</b>.
        </div>
      ) : (
        <div className="rounded-lg border border-foreground/10 overflow-hidden" data-testid="mapped-table">
          <table className="w-full text-sm">
            <thead className="bg-foreground/[0.04] text-xs text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2 font-medium">SKU Platform</th>
                <th className="text-left px-3 py-2 font-medium">Barang Gudang</th>
                <th className="text-left px-3 py-2 font-medium">Kode FG</th>
                <th className="text-right px-3 py-2 font-medium">Pesanan</th>
                <th className="text-left px-3 py-2 font-medium">Cara</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/5">
              {rows.map((r) => (
                <tr key={r.platform_sku_id} className="hover:bg-foreground/[0.03]">
                  <td className="px-3 py-2 font-mono text-xs">{r.platform_sku_id}</td>
                  <td className="px-3 py-2">
                    <div className="truncate max-w-[22rem]">{r.target_name || '—'}</div>
                    <div className="text-[11px] text-muted-foreground truncate max-w-[22rem]">
                      {r.product_name_sample}
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{r.fg_code || '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.orders_using)}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="text-[10px]">{r.method || 'manual'}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => unmap(r.platform_sku_id)}
                            data-testid={`unmap-${r.platform_sku_id}`}
                            className="text-rose-600 dark:text-rose-300">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─── Modul utama ──────────────────────────────────────────────────────────── */
export default function SkuBridgeModule({ onNavigate }) {
  const [health, setHealth] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState('onboarding');
  const [loading, setLoading] = useState(true);
  const [busyRow, setBusyRow] = useState('');
  const [manualRow, setManualRow] = useState(null);
  const [createRow, setCreateRow] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const loadHealth = useCallback(async () => {
    try { setHealth(await apiGet('/sku-bridge/health')); }
    catch (e) { toast.error(`Gagal memuat kesehatan tautan: ${e.message}`); }
  }, []);

  const loadUnmapped = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiGet(`/sku-bridge/unmapped?limit=120&with_suggestion=true${q ? `&q=${encodeURIComponent(q)}` : ''}`);
      setRows(d.rows || []); setTotal(d.total || 0);
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, [q]);

  useEffect(() => { loadHealth(); }, [loadHealth, reloadKey]);
  useEffect(() => {
    if (tab !== 'unmapped') return;
    const t = setTimeout(loadUnmapped, 250);
    return () => clearTimeout(t);
  }, [loadUnmapped, tab, reloadKey]);

  const refreshAll = () => setReloadKey((k) => k + 1);

  const quickAction = async (row) => {
    const act = row.recommended_action;
    if (act === 'create_master' || act === 'create_variant') { setCreateRow(row); return; }
    const mm = row.model_match || {};
    if (!mm.variant_id) { setManualRow(row); return; }
    setBusyRow(row.platform_sku_id);
    try {
      const res = await apiPost('/sku-bridge/map', {
        platform_sku_id: row.platform_sku_id,
        variant_id: mm.variant_id,
        account_id: row.account_id,
        product_name: row.product_name,
        variation: row.variation,
        confidence: mm.match_confidence,
      });
      toast.success(res.message || 'SKU ditautkan');
      refreshAll();
    } catch (e) { toast.error(e.message); } finally { setBusyRow(''); }
  };

  const kpis = useMemo(() => ([
    { icon: ShoppingBag, label: 'Pesanan marketing', value: fmt(health?.orders), tone: 'text-foreground', testId: 'kpi-orders' },
    { icon: CheckCircle2, label: 'Siap dikerjakan gudang', value: fmt(health?.orders_ready), tone: 'text-emerald-600 dark:text-emerald-300', testId: 'kpi-ready' },
    { icon: AlertTriangle, label: 'Belum bisa dikerjakan', value: fmt(health?.orders_blocked), tone: 'text-rose-600 dark:text-rose-300', testId: 'kpi-blocked' },
    { icon: PackageSearch, label: 'SKU belum dikenal', value: fmt(health?.unmapped_sku_count), tone: 'text-amber-600 dark:text-amber-300', testId: 'kpi-unmapped' },
    { icon: Link2, label: 'Pemetaan aktif', value: fmt(health?.bridge_mappings), tone: 'text-blue-600 dark:text-blue-300', testId: 'kpi-mappings' },
  ]), [health]);

  return (
    <div className="space-y-5" data-testid="sku-bridge-module">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Link2 className="w-6 h-6 text-primary" />Jembatan SKU
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Menyamakan identitas barang antara <b>Marketing</b> (SKU milik TikTok/Shopee) dan
            {' '}<b>Gudang</b> (kode FG + master produk). Selama SKU belum tertaut, tim gudang
            tidak bisa mengalokasikan barang untuk pesanan itu.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refreshAll} className="border-foreground/10"
                data-testid="refresh-bridge">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />Muat ulang
        </Button>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {kpis.map((k) => <Kpi key={k.label} {...k} />)}
      </div>

      <LinkageBar health={health} />

      {/* Pintu lanjutan */}
      {onNavigate && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="border-foreground/10"
                  onClick={() => onNavigate('fulfillment')} data-testid="goto-fulfillment">
            <Boxes className="w-4 h-4 mr-1.5" />Antrean Gudang<ArrowRight className="w-3.5 h-3.5 ml-1.5" />
          </Button>
          <Button variant="outline" size="sm" className="border-foreground/10"
                  onClick={() => onNavigate('sync-audit')} data-testid="goto-sync-audit">
            <ShieldCheck className="w-4 h-4 mr-1.5" />Kesehatan Sinkronisasi<ArrowRight className="w-3.5 h-3.5 ml-1.5" />
          </Button>
          <Button variant="outline" size="sm" className="border-foreground/10"
                  onClick={() => onNavigate('marketing-catalog')} data-testid="goto-catalog">
            <Layers className="w-4 h-4 mr-1.5" />Manajemen Katalog<ArrowRight className="w-3.5 h-3.5 ml-1.5" />
          </Button>
        </div>
      )}

      <GlassCard className="p-5" hover={false}>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-foreground/5 mb-4">
            <TabsTrigger value="onboarding" data-testid="tab-onboarding">
              Onboarding Produk
            </TabsTrigger>
            <TabsTrigger value="unmapped" data-testid="tab-unmapped">
              Belum Tertaut {total ? `(${fmt(total)})` : ''}
            </TabsTrigger>
            <TabsTrigger value="mapped" data-testid="tab-mapped">Sudah Dipetakan</TabsTrigger>
            <TabsTrigger value="bulk" data-testid="tab-bulk">Selesaikan Massal</TabsTrigger>
            <TabsTrigger value="options" data-testid="tab-options">Opsi Varian</TabsTrigger>
          </TabsList>
        </Tabs>

        {tab === 'unmapped' && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative max-w-md flex-1 min-w-[16rem]">
                <Search className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <Input value={q} onChange={(e) => setQ(e.target.value)} className="pl-9"
                       placeholder="Cari nama produk / SKU platform…" data-testid="unmapped-search" />
              </div>
              {/* Daftar ini dipakai untuk membagi pekerjaan ke staf & dibawa ke rapat —
                  jadi ia harus bisa keluar dari layar (kontrak INV-F10 A-3). */}
              <Button variant="outline" size="sm" className="border-foreground/10"
                      data-testid="unmapped-export"
                      onClick={() => {
                        const n = downloadCsv(
                          'sku-belum-tertaut',
                          ['SKU Platform', 'Toko', 'Nama Produk', 'Variasi', 'Warna',
                           'Ukuran', 'Pcs', 'Pesanan', 'Nilai', 'Aksi Disarankan',
                           'Model Terdekat', 'Alasan'],
                          rows.map((r) => [
                            r.platform_sku_id, r.account_name, r.product_name, r.variation,
                            r.parsed?.color || '', r.parsed?.size || '', r.pcs, r.orders,
                            r.value, ACTION_META[r.recommended_action]?.label || r.recommended_action,
                            r.model_match?.model_name || '', r.action_reason || '',
                          ]));
                        toast.success(`${n} baris diunduh`);
                      }}>
                <Download className="w-4 h-4 mr-1.5" />Unduh CSV
              </Button>
            </div>

            {loading ? (
              <div className="py-14 text-center text-muted-foreground">
                <Loader2 className="w-7 h-7 animate-spin mx-auto mb-3" />
                Memeriksa pesanan &amp; master…
              </div>
            ) : rows.length === 0 ? (
              <div className="py-14 text-center" data-testid="unmapped-empty">
                <CheckCircle2 className="w-12 h-12 mx-auto text-emerald-500/50 mb-3" />
                <p className="font-medium">Semua SKU marketing sudah dikenal gudang.</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Tidak ada barang yang menggantung tanpa identitas.
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-foreground/10 overflow-hidden" data-testid="unmapped-table">
                <table className="w-full text-sm">
                  <thead className="bg-foreground/[0.04] text-xs text-muted-foreground">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Barang dipesan pembeli</th>
                      <th className="text-left px-3 py-2 font-medium">Warna / Ukuran</th>
                      <th className="text-right px-3 py-2 font-medium">Pcs</th>
                      <th className="text-right px-3 py-2 font-medium">Nilai</th>
                      <th className="text-left px-3 py-2 font-medium">Keadaan master</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {rows.map((r) => {
                      const meta = ACTION_META[r.recommended_action] || ACTION_META.create_master;
                      const Icon = meta.icon;
                      return (
                        <tr key={r.platform_sku_id} className="hover:bg-foreground/[0.03] align-top">
                          <td className="px-3 py-2.5">
                            <div className="font-medium truncate max-w-[26rem]">
                              {r.product_name || '(tanpa nama)'}
                            </div>
                            <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                              <Store className="w-3 h-3" />{r.account_name || '—'}
                              <span className="font-mono ml-1">{r.platform_sku_id}</span>
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex flex-wrap gap-1">
                              <Badge variant="outline" className="text-[10px]">
                                {r.parsed?.color || 'warna?'}
                              </Badge>
                              <Badge variant="outline" className="text-[10px]">
                                {r.parsed?.size || 'ukuran?'}
                              </Badge>
                            </div>
                            <div className="text-[11px] text-muted-foreground mt-1 truncate max-w-[12rem]">
                              {r.variation || '—'}
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums font-medium">{fmt(r.pcs)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-xs">{rp(r.value)}</td>
                          <td className="px-3 py-2.5">
                            <Badge variant="outline" className={`${meta.chip} text-[10px]`}>
                              <Icon className="w-3 h-3 mr-1" />{meta.label}
                            </Badge>
                            <div className="text-[11px] text-muted-foreground mt-1 max-w-[18rem]">
                              {r.action_reason || meta.hint}
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right whitespace-nowrap">
                            <Button size="sm" onClick={() => quickAction(r)}
                                    disabled={busyRow === r.platform_sku_id}
                                    data-testid={`act-${r.platform_sku_id}`}>
                              {busyRow === r.platform_sku_id
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <><Icon className="w-4 h-4 mr-1.5" />{meta.label}</>}
                            </Button>
                            <Button size="sm" variant="ghost" className="ml-1"
                                    onClick={() => setManualRow(r)}
                                    data-testid={`manual-${r.platform_sku_id}`}>
                              Pilih manual
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'mapped' && <MappedPanel reloadKey={reloadKey} onChanged={refreshAll} />}
        {tab === 'bulk' && <BulkPanel onDone={refreshAll} />}
        {tab === 'onboarding' && <ProductOnboardingTab onDone={refreshAll} />}
        {tab === 'options' && <VariantOptionsTab />}
      </GlassCard>

      {manualRow && (
        <Dialog open onOpenChange={() => setManualRow(null)}>
          <ManualPickDialog row={manualRow} onClose={() => setManualRow(null)}
                            onDone={() => { setManualRow(null); refreshAll(); }} />
        </Dialog>
      )}
      {createRow && (
        <Dialog open onOpenChange={() => setCreateRow(null)}>
          <CreateMasterDialog row={createRow} onClose={() => setCreateRow(null)}
                              onDone={() => { setCreateRow(null); refreshAll(); }} />
        </Dialog>
      )}
    </div>
  );
}
