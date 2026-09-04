/**
 * MaklonPOModule — Portal Maklon PO (Production-Maklon Overhaul)
 * 
 * Fitur:
 * - CRUD Maklon PO dengan items/seri grid
 * - Confirm PO → auto WO + draft AR Invoice
 * - Multi-dispatch dengan history (bebas urutan, partial)
 * - Material receive dari klien (kain sudah di-cutting)
 * - BOM Maklon (estimasi + aktual)
 * - Finance: post AR ke GL, advance payment (DP)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Plus, Eye, Edit2, CheckCircle2, Clock, RefreshCw, Ban,
  Truck, FileText, DollarSign, ChevronDown, ChevronUp, Trash2,
  ArrowRight, BarChart3, AlertCircle, BoxesIcon, Send, BookOpen,
  ShieldAlert, AlertTriangle
} from 'lucide-react';
import { OnwardCTA } from '../OnwardCTA';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { EmptyState } from '../EmptyState';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from '../moduleAtoms';
import MaklonBuyerCatalogPicker from '../MaklonBuyerCatalogPicker';
import MaklonArtikelAutocomplete from './MaklonArtikelAutocomplete';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CONFIG = {
  draft:              { label: 'Draft',            color: 'bg-muted text-foreground border-border dark:bg-slate-500/15 dark:text-foreground/70 dark:border-slate-400/30' },
  confirmed:          { label: 'Dikonfirmasi',     color: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400/30' },
  in_production:      { label: 'Produksi',         color: 'bg-violet-100 text-violet-700 border-violet-300 dark:bg-violet-500/15 dark:text-violet-300 dark:border-violet-400/30' },
  partial_delivered:  { label: 'Sebagian Terkirim',color: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/30' },
  completed:          { label: 'Selesai',          color: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-500/15 dark:text-green-300 dark:border-green-400/30' },
  invoiced:           { label: 'Ditagih',          color: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400/30' },
  cancelled:          { label: 'Dibatalkan',       color: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-400/30' },
};

const DISPATCH_STATUS = {
  draft:              { label: 'Draft',            color: 'bg-muted text-foreground dark:bg-slate-500/15 dark:text-foreground/70' },
  packed:             { label: 'Dikemas',          color: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  dispatched:         { label: 'Terkirim',         color: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300' },
  received_by_client: { label: 'Diterima Klien',  color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  cancelled:          { label: 'Dibatalkan',       color: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' },
};

function StatusBadge({ status, config = STATUS_CONFIG }) {
  const c = config[status] || config.draft;
  return <span className={`inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>{c.label}</span>;
}

const fmtRp = (v) => (!v && v !== 0) ? '—' : formatRupiah(v);

function fmtNum(v) {
  return Number(v || 0).toLocaleString('id-ID');
}

// ─── ITEM ROW (grid editable) ────────────────────────────────────────────────
// FASE 3 (audit 2026-07-31, cacat MK-2 + keluhan #1 owner):
//   "ketika buat po dan pilih varian, tidak ada show varianya hanya yang
//    diinputkan di awal" — dulu kolom Warna & Size di sini adalah INPUT TEKS
//   BEBAS dan `variants[]` milik Buyer Catalog tidak pernah ditampilkan, sehingga
//   identitas varian master hilang saat disimpan (SKU/FG/stok tak bisa ditautkan).
//   Sekarang: setelah artikel dipilih, muncul DROPDOWN VARIAN (Warna · Size · SKU)
//   yang diambil dari `variants[]` artikel tersebut, dan `maklon_variant_id`
//   + `sku_code` ikut tersimpan.
function ItemRow({ item, idx, onChange, onRemove, readOnly, onOpenPicker, clientId, headers, catalogMap }) {
  const upd = (field, val) => onChange(idx, { ...item, [field]: val });
  const clearCatalogLink = () => onChange(idx, { ...item, buyer_catalog_id: null, maklon_variant_id: null, sku_code: '' });
  const cat = item.buyer_catalog_id ? catalogMap[item.buyer_catalog_id] : null;
  const variants = useMemo(
    () => (cat?.variants || []).filter(v => v.active !== false), [cat]);

  const handlePickFromAutocomplete = (picked) => {
    const vs = (picked.variants || []).filter(v => v.active !== false);
    const only = vs.length === 1 ? vs[0] : null;
    onChange(idx, {
      ...item,
      artikel: picked.artikel_code || item.artikel,
      // Jangan tebak warna/size lagi: varian dipilih eksplisit di dropdown.
      maklon_variant_id: only ? (only.id || only.sku) : null,
      sku_code: only ? (only.sku || '') : '',
      color: only ? (only.color || '') : '',
      size: only ? (only.size || '') : '',
      buyer_ref_code: only ? (only.buyer_ref_code || '') : '',
      cmt_rate_per_pcs: Number(picked.default_cmt_price || item.cmt_rate_per_pcs || 0),
      buyer_catalog_id: picked.id,
    });
  };

  const pickVariant = (variantKey) => {
    const v = variants.find(x => (x.id || x.sku) === variantKey);
    if (!v) {
      onChange(idx, { ...item, maklon_variant_id: null, sku_code: '', color: '', size: '', buyer_ref_code: '' });
      return;
    }
    onChange(idx, {
      ...item,
      maklon_variant_id: v.id || v.sku,
      sku_code: v.sku || '',
      color: v.color || '',
      size: v.size || '',
      buyer_ref_code: v.buyer_ref_code || '',
    });
  };

  return (
    <tr className="border-b border-foreground/5 hover:bg-foreground/[0.03] transition-colors align-top">
      <td className="py-2 px-2">
        <Input value={item.seri_no} onChange={e => upd('seri_no', e.target.value)}
          className="h-7 text-xs bg-foreground/5 border-border w-16" placeholder="S01" disabled={readOnly} data-testid={`po-item-${idx}-seri`} />
      </td>
      <td className="py-2 px-2">
        {readOnly ? (
          <Input value={item.artikel} className="h-7 text-xs bg-foreground/5 border-border w-32" disabled />
        ) : (
          <MaklonArtikelAutocomplete
            value={item.artikel}
            onChange={(v) => upd('artikel', v)}
            onPick={handlePickFromAutocomplete}
            clientId={clientId}
            currentRate={item.cmt_rate_per_pcs}
            currentCatalogId={item.buyer_catalog_id}
            headers={headers}
            disabled={readOnly}
            onClearCatalogLink={clearCatalogLink}
            testIdPrefix={`po-item-${idx}-artikel`}
          />
        )}
      </td>
      {/* ── VARIAN (Warna · Size · SKU) dari master artikel ── */}
      <td className="py-2 px-2" colSpan={2}>
        {readOnly ? (
          <div className="text-xs text-foreground">
            <div>{[item.color, item.size].filter(Boolean).join(' · ') || '—'}</div>
            {item.sku_code && <div className="font-mono text-[10px] text-muted-foreground">{item.sku_code}</div>}
          </div>
        ) : !item.buyer_catalog_id ? (
          <div className="text-[11px] text-muted-foreground w-44">
            Pilih artikel dulu untuk memuat varian
          </div>
        ) : variants.length === 0 ? (
          <div className="text-[11px] text-amber-700 w-56 leading-snug">
            Artikel ini belum punya varian.{' '}
            <span className="font-semibold">Buat varian</span> di Katalog Buyer → Varian, lalu pilih di sini.
          </div>
        ) : (
          <div className="w-56">
            <select
              value={item.maklon_variant_id || ''}
              onChange={e => pickVariant(e.target.value)}
              data-testid={`po-item-${idx}-variant`}
              className="h-7 w-full text-xs rounded-md bg-foreground/5 border border-border px-1.5 text-foreground outline-none focus:border-[hsl(var(--primary))]">
              <option value="">— pilih varian —</option>
              {variants.map(v => (
                <option key={v.id || v.sku} value={v.id || v.sku}>
                  {v.color} · {v.size} — {v.sku}
                </option>
              ))}
            </select>
            {item.sku_code && (
              <div className="font-mono text-[10px] text-emerald-700 mt-0.5">{item.sku_code}</div>
            )}
          </div>
        )}
      </td>
      <td className="py-2 px-2">
        <Input type="number" value={item.qty} onChange={e => upd('qty', parseInt(e.target.value) || 0)}
          className="h-7 text-xs bg-foreground/5 border-border w-20" min={1} disabled={readOnly} data-testid={`po-item-${idx}-qty`} />
      </td>
      <td className="py-2 px-2">
        <Input type="number" value={item.cmt_rate_per_pcs} onChange={e => upd('cmt_rate_per_pcs', parseFloat(e.target.value) || 0)}
          className="h-7 text-xs bg-foreground/5 border-border w-28" min={0} disabled={readOnly} data-testid={`po-item-${idx}-rate`} />
      </td>
      <td className="py-2 px-2 text-right text-xs text-foreground/70">
        {fmtRp((item.qty || 0) * (item.cmt_rate_per_pcs || 0))}
      </td>
      {!readOnly && (
        <td className="py-2 px-2">
          <Button variant="ghost" size="icon" className="h-7 w-7 text-red-400 hover:bg-red-500/20" onClick={() => onRemove(idx)}>
            <Trash2 className="w-3 h-3" />
          </Button>
        </td>
      )}
    </tr>
  );
}

// ─── PO FORM (Create/Edit) ────────────────────────────────────────────────────
function POForm({ po, clients, onSave, onClose }) {
  const isEdit = !!po;
  const [form, setForm] = useState({
    client_id: po?.client_id || '',
    po_date: po?.po_date || new Date().toISOString().split('T')[0],
    deadline: po?.deadline || '',
    payment_terms: po?.payment_terms || 'net_30',
    notes: po?.notes || '',
    vendor_id: po?.vendor_id || '',
    items: po?.items?.map(i => ({
      seri_no: i.seri_no, artikel: i.artikel, sku_code: i.sku_code || '',
      color: i.color || '', size: i.size || '', qty: i.qty,
      cmt_rate_per_pcs: i.cmt_rate_per_pcs || 0,
      buyer_catalog_id: i.buyer_catalog_id || null,
      maklon_variant_id: i.maklon_variant_id || null,
      buyer_ref_code: i.buyer_ref_code || '',
    })) || [{ seri_no: 'S01', artikel: '', color: '', size: '', qty: 0, cmt_rate_per_pcs: 0, buyer_catalog_id: null, maklon_variant_id: null, sku_code: '', buyer_ref_code: '' }],
  });
  // FASE 3: katalog artikel klien (untuk dropdown VARIAN per baris item)
  const [catalogMap, setCatalogMap] = useState({});
  const [saving, setSaving] = useState(false);
  // Phase M1: Buyer Catalog picker state
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerIdx, setPickerIdx] = useState(null);

  const token = window._authToken;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  // Muat katalog artikel + variants[] milik klien terpilih → sumber dropdown varian.
  useEffect(() => {
    if (!form.client_id) { setCatalogMap({}); return; }
    let alive = true;
    (async () => {
      try {
        const r = await fetch(`${API}/api/dewi/maklon/buyer-catalog?client_id=${form.client_id}`, { headers });
        if (!r.ok) return;
        const data = await r.json();
        const list = Array.isArray(data) ? data : (data.items || []);
        if (!alive) return;
        setCatalogMap(Object.fromEntries(list.map(c => [c.id, c])));
      } catch (_e) { /* dropdown varian akan menampilkan pesan bila katalog gagal dimuat */ }
    })();
    return () => { alive = false; };
  }, [form.client_id, headers]);

  const totalQty = form.items.reduce((s, i) => s + (parseInt(i.qty) || 0), 0);
  const totalValue = form.items.reduce((s, i) => s + ((parseInt(i.qty) || 0) * (parseFloat(i.cmt_rate_per_pcs) || 0)), 0);

  const addItem = () => setForm(f => ({
    ...f,
    items: [...f.items, { seri_no: `S${String(f.items.length + 1).padStart(2, '0')}`, artikel: '', color: '', size: '', qty: 0, cmt_rate_per_pcs: 0, buyer_catalog_id: null, maklon_variant_id: null, sku_code: '', buyer_ref_code: '' }]
  }));

  const updateItem = (idx, updated) => setForm(f => ({
    ...f, items: f.items.map((it, i) => i === idx ? updated : it)
  }));

  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));

  // Phase M1: open Buyer Catalog picker for specific row idx
  const handleOpenPicker = (idx) => {
    if (!form.client_id) {
      toast.error('Pilih klien (buyer) dulu sebelum memilih dari Buyer Catalog');
      return;
    }
    setPickerIdx(idx);
    setPickerOpen(true);
  };

  // Phase M1: handle pick from catalog → auto-fill row
  const handlePickCatalog = (catalogItem) => {
    if (pickerIdx === null || !catalogItem) return;
    setForm(f => ({
      ...f,
      items: f.items.map((it, i) => {
        if (i !== pickerIdx) return it;
        return {
          ...it,
          artikel: catalogItem.artikel_code || it.artikel,
          // Pilih warna default pertama jika kosong & catalog punya opsi
          color: it.color || (catalogItem.color_options?.[0] || ''),
          size: it.size || (catalogItem.size_options?.[0] || ''),
          // Snap default CMT price; user masih bisa override
          cmt_rate_per_pcs: Number(catalogItem.default_cmt_price || it.cmt_rate_per_pcs || 0),
          buyer_catalog_id: catalogItem.id,
        };
      }),
    }));
    toast.success(`Artikel "${catalogItem.artikel_code}" diisi dari Buyer Catalog`);
    setPickerOpen(false);
    setPickerIdx(null);
  };

  const handleSave = async (forceDrift = false) => {
    if (!form.client_id) return toast.error('Pilih klien terlebih dahulu');
    if (form.items.length === 0) return toast.error('Tambah minimal 1 item');
    if (form.items.some(i => !i.artikel.trim())) return toast.error('Semua item harus punya artikel');
    // FASE 3: varian WAJIB dipilih bila artikelnya punya varian master — supaya
    // SKU/FG/stok bisa ditautkan (cacat MK-2: identitas varian hilang saat simpan).
    for (let i = 0; i < form.items.length; i++) {
      const it = form.items[i];
      const cat = it.buyer_catalog_id ? catalogMap[it.buyer_catalog_id] : null;
      const vs = (cat?.variants || []).filter(v => v.active !== false);
      if (vs.length > 0 && !it.maklon_variant_id) {
        return toast.error(`Item #${i + 1}: pilih Varian (Warna · Size · SKU) dari master artikel terlebih dahulu`);
      }
    }
    setSaving(true);
    try {
      const url = isEdit ? `${API}/api/dewi/maklon/pos/${po.id}` : `${API}/api/dewi/maklon/pos`;
      const method = isEdit ? 'PUT' : 'POST';
      const body = JSON.stringify({ ...form, force_price_drift: !!forceDrift });
      const r = await fetch(url, { method, headers, body });
      if (r.status === 422) {
        // Phase M2.3: Price drift block — minta konfirmasi force
        const err = await r.json();
        let detail = err.detail;
        if (typeof detail === 'string') {
          try { detail = JSON.parse(detail.replace(/'/g, '"')); } catch (_e) { /* keep string */ }
        }
        if (detail && detail.error === 'PRICE_DRIFT_BLOCK') {
          const events = detail.drift_events || [];
          const lines = events.map(e =>
            `  • Item ${e.seri_no} (${e.artikel_code}): ${e.drift_pct > 0 ? '+' : ''}${e.drift_pct}% — ${e.severity.toUpperCase()}`
          ).join('\n');
          const msg = `⚠️ HARGA MELEBIHI BATAS APPROVAL\n\n${detail.message}\n\nDetail item:\n${lines}\n\nLanjutkan dengan FORCE? (Aktivitas akan tercatat di audit log)`;
          if (window.confirm(msg)) {
            await handleSave(true);
            return;
          }
          setSaving(false);
          return;
        }
        throw new Error((typeof detail === 'string') ? detail : (detail?.message || 'Gagal'));
      }
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal'); }
      const d = await r.json();
      // Phase M2.3: tampilkan warning toast kalau ada drift_events level 'warning'
      if (d._drift_events?.length) {
        const warnings = d._drift_events.filter(e => e.severity === 'warning');
        if (warnings.length) {
          toast.warning(`${warnings.length} item memiliki drift harga ≥10% (warning, masih boleh)`, { duration: 5000 });
        }
      }
      toast.success(isEdit ? 'PO berhasil diupdate' : `PO ${d.po_number} berhasil dibuat`);
      onSave();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label className="text-xs">Klien *</Label>
          <Select value={form.client_id} onValueChange={v => setForm(f => ({ ...f, client_id: v }))}
            disabled={isEdit}>
            <SelectTrigger className="bg-foreground/5 border-border text-sm" data-testid="maklon-po-form-client-select">
              <SelectValue placeholder="Pilih klien" />
            </SelectTrigger>
            <SelectContent>
              {clients.map(c => <SelectItem key={c.id} value={c.id}>{c.name} ({c.code})</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Payment Terms</Label>
          <Select value={form.payment_terms} onValueChange={v => setForm(f => ({ ...f, payment_terms: v }))}>
            <SelectTrigger className="bg-foreground/5 border-border text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="cod">COD</SelectItem>
              <SelectItem value="net_14">Net 14</SelectItem>
              <SelectItem value="net_30">Net 30</SelectItem>
              <SelectItem value="net_60">Net 60</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Tanggal PO</Label>
          <Input type="date" value={form.po_date} onChange={e => setForm(f => ({ ...f, po_date: e.target.value }))}
            className="bg-foreground/5 border-border text-sm" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Deadline Target</Label>
          <Input type="date" value={form.deadline} onChange={e => setForm(f => ({ ...f, deadline: e.target.value }))}
            className="bg-foreground/5 border-border text-sm" />
        </div>
      </div>

      {/* Items Grid */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-xs">Items / Seri *</Label>
            <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1 flex-wrap">
              <BookOpen className="w-3 h-3 text-violet-600 dark:text-violet-300" />
              Ketik artikel → muncul saran dari Buyer Catalog
              <span className="text-foreground/30">·</span>
              <AlertTriangle className="w-3 h-3 text-amber-300" />
              Warning auto jika harga ≠ default catalog
            </div>
          </div>
          <Button type="button" size="sm" variant="outline" className="h-7 text-xs border-border hover:bg-foreground/10"
            onClick={addItem} data-testid="maklon-po-add-item-btn">
            <Plus className="w-3 h-3 mr-1" /> Tambah Baris
          </Button>
        </div>
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-foreground/5">
              <tr>
                {['Seri', 'Artikel', 'Varian (Warna · Size · SKU)', '', 'Qty', 'Rate CMT (Rp)', 'Subtotal', ''].map(h => (
                  <th key={h} className="text-left py-2 px-2 text-muted-foreground font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {form.items.map((item, idx) => (
                <ItemRow key={idx} item={item} idx={idx} onChange={updateItem} onRemove={removeItem} onOpenPicker={handleOpenPicker} clientId={form.client_id} headers={headers} catalogMap={catalogMap} />
              ))}
            </tbody>
            <tfoot className="border-t border-border bg-foreground/[0.03]">
              <tr>
                <td colSpan={4} className="py-2 px-2 text-xs text-muted-foreground">Total</td>
                <td className="py-2 px-2 text-xs font-bold text-foreground">{fmtNum(totalQty)} pcs</td>
                <td></td>
                <td className="py-2 px-2 text-xs font-bold text-green-600 dark:text-green-300 text-right">{fmtRp(totalValue)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Catatan</Label>
        <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
          rows={2} className="bg-foreground/5 border-border text-sm resize-none" placeholder="Catatan tambahan..." />
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button onClick={handleSave} disabled={saving} data-testid="maklon-po-form-save-btn">
          {saving ? 'Menyimpan...' : (isEdit ? 'Update PO' : 'Buat PO')}
        </Button>
      </DialogFooter>

      {/* Phase M1: Buyer Catalog Picker */}
      <MaklonBuyerCatalogPicker
        open={pickerOpen}
        clientId={form.client_id}
        headers={headers}
        onClose={() => { setPickerOpen(false); setPickerIdx(null); }}
        onPick={handlePickCatalog}
      />
    </div>
  );
}

// ─── DISPATCH FORM ────────────────────────────────────────────────────────────
function DispatchForm({ po, onSave, onClose }) {
  const token = window._authToken;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [form, setForm] = useState({
    dispatch_date: new Date().toISOString().split('T')[0],
    driver_name: '', vehicle_no: '', notes: '',
    items: (po?.items || []).map(i => ({
      item_id: i.item_id,
      seri_no: i.seri_no,
      artikel: i.artikel,
      color: i.color,
      size: i.size,
      qty_po: i.qty,
      qty_dispatched_before: i.qty_dispatched || 0,
      qty_remaining: (i.qty - (i.qty_dispatched || 0)),
      qty_to_dispatch: 0,
      included: false,
    }))
  });
  const [saving, setSaving] = useState(false);

  const toggleItem = (idx) => setForm(f => ({
    ...f, items: f.items.map((it, i) => i === idx ? { ...it, included: !it.included, qty_to_dispatch: !it.included ? it.qty_remaining : 0 } : it)
  }));

  const setQty = (idx, qty) => setForm(f => ({
    ...f, items: f.items.map((it, i) => i === idx ? { ...it, qty_to_dispatch: Math.min(parseInt(qty) || 0, it.qty_remaining) } : it)
  }));

  const selectedItems = form.items.filter(i => i.included && i.qty_to_dispatch > 0);

  const handleDispatch = async () => {
    if (selectedItems.length === 0) return toast.error('Pilih minimal 1 item untuk dispatch');
    setSaving(true);
    try {
      const payload = {
        po_id: po.id,
        dispatch_date: form.dispatch_date,
        driver_name: form.driver_name,
        vehicle_no: form.vehicle_no,
        notes: form.notes,
        items: selectedItems.map(i => ({
          item_id: i.item_id, seri_no: i.seri_no,
          artikel: i.artikel, color: i.color, size: i.size,
          qty_dispatched: i.qty_to_dispatch,
        }))
      };
      const r = await fetch(`${API}/api/dewi/maklon/dispatches`, { method: 'POST', headers, body: JSON.stringify(payload) });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal'); }
      toast.success('Dispatch berhasil dibuat');
      onSave();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Tanggal Dispatch</Label>
          <Input type="date" value={form.dispatch_date} onChange={e => setForm(f => ({ ...f, dispatch_date: e.target.value }))}
            className="bg-foreground/5 border-border text-sm" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Nama Driver</Label>
          <Input value={form.driver_name} onChange={e => setForm(f => ({ ...f, driver_name: e.target.value }))}
            className="bg-foreground/5 border-border text-sm" placeholder="Opsional" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">No. Kendaraan</Label>
          <Input value={form.vehicle_no} onChange={e => setForm(f => ({ ...f, vehicle_no: e.target.value }))}
            className="bg-foreground/5 border-border text-sm" placeholder="B 1234 XY" />
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs">Pilih Items untuk Dispatch (bebas urutan, boleh partial)</Label>
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-foreground/5">
              <tr>
                <th className="py-2 px-2 text-left text-muted-foreground">Seri</th>
                <th className="py-2 px-2 text-left text-muted-foreground">Artikel</th>
                <th className="py-2 px-2 text-left text-muted-foreground">Warna/Size</th>
                <th className="py-2 px-2 text-right text-muted-foreground">Total PO</th>
                <th className="py-2 px-2 text-right text-muted-foreground">Sisa</th>
                <th className="py-2 px-2 text-center text-muted-foreground">Kirim</th>
                <th className="py-2 px-2 text-center text-muted-foreground">Qty</th>
              </tr>
            </thead>
            <tbody>
              {form.items.map((item, idx) => (
                <tr key={idx} className={`border-b border-foreground/5 ${item.included ? 'bg-violet-500/5' : ''}`}>
                  <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{item.seri_no}</td>
                  <td className="py-2 px-2">{item.artikel}</td>
                  <td className="py-2 px-2 text-muted-foreground">{[item.color, item.size].filter(Boolean).join(' / ')}</td>
                  <td className="py-2 px-2 text-right">{fmtNum(item.qty_po)}</td>
                  <td className={`py-2 px-2 text-right font-semibold ${item.qty_remaining === 0 ? 'text-green-400' : 'text-amber-600 dark:text-amber-300'}`}>
                    {item.qty_remaining === 0 ? '✓ Lunas' : fmtNum(item.qty_remaining)}
                  </td>
                  <td className="py-2 px-2 text-center">
                    {item.qty_remaining > 0 && (
                      <input type="checkbox" checked={item.included} onChange={() => toggleItem(idx)}
                        className="accent-violet-500" data-testid={`dispatch-item-${idx}-check`} />
                    )}
                  </td>
                  <td className="py-2 px-2">
                    {item.included && (
                      <Input type="number" value={item.qty_to_dispatch}
                        onChange={e => setQty(idx, e.target.value)}
                        max={item.qty_remaining} min={1}
                        className="h-7 text-xs bg-foreground/5 border-border w-20 text-center" data-testid={`dispatch-item-${idx}-qty`} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selectedItems.length > 0 && (
          <div className="bg-violet-500/10 border border-violet-400/20 rounded-lg px-3 py-2 text-xs text-violet-600 dark:text-violet-300">
            <strong>Total dispatch ini:</strong> {selectedItems.reduce((s, i) => s + i.qty_to_dispatch, 0)} pcs
            ({selectedItems.length} item)
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Catatan</Label>
        <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
          rows={2} className="bg-foreground/5 border-border text-sm resize-none" />
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button onClick={handleDispatch} disabled={saving || selectedItems.length === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-foreground/5 text-sm transition-colors" data-testid="maklon-dispatch-submit-btn">
          <Truck className="w-4 h-4 mr-2" />
          {saving ? 'Membuat...' : `Buat Dispatch (${selectedItems.length} item)`}
        </Button>
      </DialogFooter>
    </div>
  );
}

// ─── PO DETAIL (Full detail view) ────────────────────────────────────────────
function PODetail({ po, onClose, onRefresh, clients }) {
  const token = window._authToken;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dispatchDialog, setDispatchDialog] = useState(false);
  const [materialDialog, setMaterialDialog] = useState(false);
  const [bomDialog, setBomDialog] = useState(false);
  const [postingAR, setPostingAR] = useState(false);
  const [expandedDispatch, setExpandedDispatch] = useState(null);
  const [dpDialog, setDpDialog] = useState(false);
  const [savingDP, setSavingDP] = useState(false);
  const [dpForm, setDpForm] = useState({ amount: '', payment_date: new Date().toISOString().split('T')[0], bank_account: '', notes: '' });

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos/${po.id}`, { headers });
      if (r.ok) setDetail(await r.json());
    } catch (e) { toast.error('Gagal memuat detail'); }
    finally { setLoading(false); }
  }, [po.id, headers]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  const confirmPO = async () => {
    const r = await fetch(`${API}/api/dewi/maklon/pos/${po.id}/confirm`, { method: 'POST', headers });
    if (r.ok) { const d = await r.json(); toast.success(`PO dikonfirmasi! ${d.work_orders_created?.length || 0} WO dibuat`); fetchDetail(); onRefresh(); }
    else { const e = await r.json(); toast.error(e.detail || 'Gagal konfirmasi'); }
  };

  const confirmDispatch = async (dispatchId) => {
    const r = await fetch(`${API}/api/dewi/maklon/dispatches/${dispatchId}/confirm`, { method: 'PUT', headers });
    if (r.ok) { toast.success('Dispatch dikonfirmasi'); fetchDetail(); onRefresh(); }
    else { const e = await r.json(); toast.error(e.detail || 'Gagal'); }
  };

  const postAR = async () => {
    setPostingAR(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/finance/pos/${po.id}/post-ar`, { method: 'POST', headers });
      const d = await r.json();
      if (r.ok) { toast.success(d.already_posted ? 'Sudah pernah dipost sebelumnya' : `AR berhasil dipost ke Finance (${d.je_number})`); fetchDetail(); onRefresh(); }
      else throw new Error(d.detail || 'Gagal post AR');
    } catch (e) { toast.error(e.message); }
    finally { setPostingAR(false); }
  };

  const recordDP = async () => {
    const amt = parseFloat(dpForm.amount);
    if (!amt || amt <= 0) { toast.error('Jumlah DP harus lebih dari 0'); return; }
    setSavingDP(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/finance/pos/${po.id}/advance-payment`, {
        method: 'POST', headers,
        body: JSON.stringify({
          amount: amt,
          payment_date: dpForm.payment_date || null,
          bank_account: dpForm.bank_account || null,
          notes: dpForm.notes || null,
        }),
      });
      const d = await r.json();
      if (r.ok) {
        toast.success(`DP Rp ${amt.toLocaleString('id-ID')} tercatat${d.gl_je_number ? ` — GL ${d.gl_je_number}` : ''}`);
        setDpDialog(false);
        setDpForm({ amount: '', payment_date: new Date().toISOString().split('T')[0], bank_account: '', notes: '' });
        fetchDetail(); onRefresh();
      } else throw new Error(d.detail || 'Gagal mencatat DP');
    } catch (e) { toast.error(e.message); }
    finally { setSavingDP(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-muted-foreground">Memuat...</div>;
  if (!detail) return null;

  const qtyDispatchedTotal = detail.qty_dispatched || 0;
  const qtyRemaining = detail.qty_remaining || 0;
  const progressPct = detail.total_qty > 0 ? Math.round((qtyDispatchedTotal / detail.total_qty) * 100) : 0;

  return (
    <div className="space-y-4 max-h-[80vh] overflow-y-auto pr-1">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-foreground font-mono">{detail.po_number}</h3>
            <StatusBadge status={detail.status} />
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">{detail.client_name} — {detail.po_date}</p>
        </div>
        <div className="text-right">
          <div className="text-xl font-bold text-green-300">{fmtRp(detail.total_value)}</div>
          <div className="text-xs text-muted-foreground">{fmtNum(detail.total_qty)} pcs total</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-foreground/5 rounded-lg p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Progress Pengiriman</span>
          <span className="text-foreground font-semibold">{progressPct}% ({fmtNum(qtyDispatchedTotal)} / {fmtNum(detail.total_qty)} pcs)</span>
        </div>
        <div className="h-2 rounded-full bg-foreground/10 overflow-hidden">
          <motion.div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-green-500"
            initial={{ width: 0 }} animate={{ width: `${progressPct}%` }} transition={{ duration: 0.6 }} />
        </div>
        <div className="flex gap-4 text-xs">
          <span className="text-green-600 dark:text-green-300">✓ Terkirim: {fmtNum(qtyDispatchedTotal)}</span>
          <span className="text-amber-600 dark:text-amber-300">⋯ Sisa: {fmtNum(qtyRemaining)}</span>
          {detail.deadline && <span className="text-muted-foreground">📅 Deadline: {detail.deadline}</span>}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {detail.status === 'draft' && (
          <Button size="sm" onClick={confirmPO} className="bg-blue-600 hover:bg-blue-500 text-xs" data-testid="maklon-po-confirm-btn">
            <CheckCircle2 className="w-3 h-3 mr-1.5" /> Konfirmasi PO
          </Button>
        )}
        {['confirmed', 'in_production', 'partial_delivered'].includes(detail.status) && (
          <Button size="sm" onClick={() => setDispatchDialog(true)} className="bg-violet-600 hover:bg-violet-500 text-xs" data-testid="maklon-po-dispatch-open-btn">
            <Truck className="w-3 h-3 mr-1.5" /> Buat Dispatch
          </Button>
        )}
        {['confirmed', 'in_production', 'partial_delivered'].includes(detail.status) && (
          <Button size="sm" variant="outline" onClick={() => setMaterialDialog(true)} className="border-border hover:bg-foreground/10 text-xs" data-testid="maklon-po-material-btn">
            <BoxesIcon className="w-3 h-3 mr-1.5" /> Terima Material
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => setBomDialog(true)} className="border-border hover:bg-foreground/10 text-xs" data-testid="maklon-po-bom-btn">
          <FileText className="w-3 h-3 mr-1.5" /> BOM Maklon
        </Button>
        {detail.ar_invoice_number && !detail.gl_je_id && detail.status !== 'draft' && (
          <Button size="sm" variant="outline" onClick={postAR} disabled={postingAR}
            className="border-green-500/30 text-green-600 dark:text-green-300 hover:bg-green-500/10 text-xs" data-testid="maklon-po-postar-btn">
            <DollarSign className="w-3 h-3 mr-1.5" />
            {postingAR ? 'Posting...' : 'Post ke Finance GL'}
          </Button>
        )}
        {detail.status !== 'draft' && (
          <Button size="sm" variant="outline" onClick={() => setDpDialog(true)}
            className="border-amber-500/30 text-amber-600 dark:text-amber-300 hover:bg-amber-500/10 text-xs" data-testid="maklon-po-dp-btn">
            <DollarSign className="w-3 h-3 mr-1.5" /> Catat DP
          </Button>
        )}
        {detail.gl_je_id && (
          <div className="flex items-center gap-1 text-xs text-green-700 dark:text-green-400 bg-green-500/10 border border-green-400/20 rounded-md px-2 py-1">
            <CheckCircle2 className="w-3 h-3" /> GL Posted ({detail.gl_je_number})
          </div>
        )}
      </div>

      {/* AR Invoice badge */}
      {detail.ar_invoice_number && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 flex items-center justify-between dark:bg-blue-500/10 dark:border-blue-400/20">
          <div className="text-xs">
            <span className="text-blue-300 font-semibold">AR Invoice: {detail.ar_invoice_number}</span>
            <span className="text-muted-foreground ml-2">— Auto-generated saat PO dikonfirmasi</span>
          </div>
          <StatusBadge status={detail.ar_invoice_detail?.status || 'draft'} />
        </div>
      )}

      {/* Uang Muka (DP) & Pembayaran */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 dark:bg-amber-500/10 dark:border-amber-400/20" data-testid="maklon-po-dp-panel">
        <div className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-2">Uang Muka (DP) &amp; Pembayaran</div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <div className="text-muted-foreground">Nilai PO</div>
            <div className="font-bold text-foreground">{fmtRp(detail.total_value || 0)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">DP Diterima</div>
            <div className="font-bold text-green-600 dark:text-green-300" data-testid="maklon-po-dp-total">{fmtRp(detail.advance_payment || 0)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Sisa Tagihan</div>
            <div className="font-bold text-amber-600 dark:text-amber-300">
              {fmtRp(Math.max(0, (detail.total_value || 0) - (detail.advance_payment || 0) - (detail.amount_paid || 0)))}
            </div>
          </div>
        </div>
        {(detail.advance_payments || []).length > 0 && (
          <div className="mt-2 border-t border-amber-200 dark:border-amber-400/20 pt-2 space-y-1">
            <div className="text-[11px] text-muted-foreground mb-1">Riwayat DP</div>
            {detail.advance_payments.map(dp => (
              <div key={dp.id} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  {dp.payment_date}{dp.bank_account ? ` · ${dp.bank_account}` : ''}{dp.gl_je_number ? ` · GL ${dp.gl_je_number}` : ''}
                  {dp.notes ? ` · ${dp.notes}` : ''}
                </span>
                <span className="font-semibold text-green-600 dark:text-green-300">{fmtRp(dp.amount)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Items table */}
      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground/70">Items / Seri</h4>
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-foreground/5">
              <tr>
                {['Seri', 'Artikel', 'Warna', 'Size', 'Qty PO', 'Tdk Terkirim', 'Sisa', 'Rate', 'Subtotal'].map(h => (
                  <th key={h} className="py-2 px-2 text-left text-muted-foreground font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detail.items?.map((item, idx) => {
                const dispatched = item.qty_dispatched || 0;
                const remaining = item.qty - dispatched;
                return (
                  <tr key={idx} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                    <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{item.seri_no}</td>
                    <td className="py-2 px-2 font-medium">{item.artikel}</td>
                    <td className="py-2 px-2 text-muted-foreground">{item.color || '—'}</td>
                    <td className="py-2 px-2 text-muted-foreground">{item.size || '—'}</td>
                    <td className="py-2 px-2 font-semibold">{fmtNum(item.qty)}</td>
                    <td className="py-2 px-2 text-green-300">{fmtNum(dispatched)}</td>
                    <td className={`py-2 px-2 font-semibold ${remaining === 0 ? 'text-green-400' : 'text-amber-600 dark:text-amber-300'}`}>
                      {remaining === 0 ? '✓' : fmtNum(remaining)}
                    </td>
                    <td className="py-2 px-2 text-muted-foreground">{fmtRp(item.cmt_rate_per_pcs)}</td>
                    <td className="py-2 px-2 text-right">{fmtRp(item.subtotal)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dispatch history */}
      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground/70">History Dispatch ({detail.dispatches?.length || 0})</h4>
        {detail.dispatches?.length === 0 ? (
          <p className="text-xs text-muted-foreground italic py-2">Belum ada dispatch untuk PO ini.</p>
        ) : (
          <div className="space-y-2">
            {detail.dispatches?.map(d => (
              <div key={d.id} className="bg-foreground/5 rounded-lg border border-border overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 cursor-pointer"
                  onClick={() => setExpandedDispatch(expandedDispatch === d.id ? null : d.id)}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-violet-600 dark:text-violet-300">{d.dispatch_number}</span>
                    <StatusBadge status={d.status} config={DISPATCH_STATUS} />
                    <span className="text-xs text-muted-foreground">{d.dispatch_date}</span>
                    <span className="text-xs text-foreground/70">{fmtNum(d.total_qty_dispatched)} pcs</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {d.status === 'draft' && (
                      <Button size="sm" onClick={e => { e.stopPropagation(); confirmDispatch(d.id); }}
                        className="h-6 text-xs bg-green-600 hover:bg-green-500" data-testid={`maklon-dispatch-confirm-${d.id}`}>
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Konfirmasi
                      </Button>
                    )}
                    {expandedDispatch === d.id ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                  </div>
                </div>
                <AnimatePresence>
                  {expandedDispatch === d.id && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                      <div className="rounded-xl border px-3 pb-3 border-t border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                        <table className="w-full text-xs mt-2">
                          <thead>
                            <tr className="text-muted-foreground">
                              <th className="text-left py-1">Seri</th>
                              <th className="text-left py-1">Artikel</th>
                              <th className="text-left py-1">Warna/Size</th>
                              <th className="text-right py-1">Qty</th>
                            </tr>
                          </thead>
                          <tbody>
                            {d.items?.map((di, i) => (
                              <tr key={i} className="border-b border-foreground/5">
                                <td className="py-1 font-mono text-violet-600 dark:text-violet-300">{di.seri_no}</td>
                                <td className="py-1">{di.artikel}</td>
                                <td className="py-1 text-muted-foreground">{[di.color, di.size].filter(Boolean).join(' / ')}</td>
                                <td className="py-1 text-right font-semibold">{fmtNum(di.qty_dispatched)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {d.driver_name && <p className="text-xs text-muted-foreground mt-2">Driver: {d.driver_name} {d.vehicle_no ? `| ${d.vehicle_no}` : ''}</p>}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Material receives */}
      {detail.material_receives?.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-foreground/70">Material dari Klien</h4>
          <div className="space-y-1">
            {detail.material_receives.map(r => (
              <div key={r.id} className="bg-foreground/5 rounded-lg px-3 py-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-foreground/70">{r.receive_date}</span>
                  <span className="text-muted-foreground">{r.items?.length} item</span>
                </div>
                <div className="flex flex-wrap gap-2 mt-1">
                  {r.items?.map((it, i) => (
                    <span key={i} className="bg-cyan-500/10 border border-cyan-400/20 text-cyan-600 dark:text-cyan-300 rounded px-1.5 py-0.5">
                      {it.material_name}: {fmtNum(it.qty)} {it.unit}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dialogs */}
      <Dialog open={dispatchDialog} onOpenChange={setDispatchDialog}>
        <DialogContent className="max-w-3xl bg-card border-border">
          <DialogHeader><DialogTitle>Buat Dispatch — {detail.po_number}</DialogTitle></DialogHeader>
          <DispatchForm po={detail} onSave={() => { setDispatchDialog(false); fetchDetail(); onRefresh(); }} onClose={() => setDispatchDialog(false)} />
        </DialogContent>
      </Dialog>

      <Dialog open={materialDialog} onOpenChange={setMaterialDialog}>
        <DialogContent className="max-w-xl bg-card border-border">
          <DialogHeader><DialogTitle>Terima Material dari Klien</DialogTitle></DialogHeader>
          <MaterialReceiveForm po={detail} headers={headers} onSave={() => { setMaterialDialog(false); fetchDetail(); }} onClose={() => setMaterialDialog(false)} />
        </DialogContent>
      </Dialog>

      <Dialog open={bomDialog} onOpenChange={setBomDialog}>
        <DialogContent className="max-w-2xl bg-card border-border">
          <DialogHeader><DialogTitle>BOM Maklon — {detail.po_number}</DialogTitle></DialogHeader>
          <BOMForm po={detail} headers={headers} onSave={() => setBomDialog(false)} onClose={() => setBomDialog(false)} />
        </DialogContent>
      </Dialog>

      <Dialog open={dpDialog} onOpenChange={setDpDialog}>
        <DialogContent className="max-w-md bg-card border-border">
          <DialogHeader><DialogTitle>Catat DP / Uang Muka — {detail.po_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Jumlah DP (Rp) *</Label>
              <Input type="number" min="0" value={dpForm.amount}
                onChange={e => setDpForm(f => ({ ...f, amount: e.target.value }))}
                placeholder="0" data-testid="dp-amount-input" />
            </div>
            <div>
              <Label className="text-xs">Tanggal Pembayaran</Label>
              <Input type="date" value={dpForm.payment_date}
                onChange={e => setDpForm(f => ({ ...f, payment_date: e.target.value }))}
                data-testid="dp-date-input" />
            </div>
            <div>
              <Label className="text-xs">Rekening / Bank</Label>
              <Input value={dpForm.bank_account}
                onChange={e => setDpForm(f => ({ ...f, bank_account: e.target.value }))}
                placeholder="mis. BCA 1234567890" data-testid="dp-bank-input" />
            </div>
            <div>
              <Label className="text-xs">Catatan</Label>
              <Textarea value={dpForm.notes} rows={2}
                onChange={e => setDpForm(f => ({ ...f, notes: e.target.value }))} />
            </div>
            <div className="text-[11px] text-muted-foreground bg-foreground/5 rounded p-2">
              Otomatis posting jurnal: <b>Dr Bank / Cr Uang Muka Pelanggan (2-1300)</b>.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDpDialog(false)}>Batal</Button>
            <Button size="sm" onClick={recordDP} disabled={savingDP}
              className="bg-amber-600 hover:bg-amber-500" data-testid="dp-submit-btn">
              {savingDP ? 'Menyimpan...' : 'Simpan DP'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── MATERIAL RECEIVE FORM ────────────────────────────────────────────────────
function MaterialReceiveForm({ po, headers, onSave, onClose }) {
  const [items, setItems] = useState([{ material_name: '', material_category: 'fabric', qty: 0, unit: 'pcs', notes: '' }]);
  const [receiveDate, setReceiveDate] = useState(new Date().toISOString().split('T')[0]);
  const [saving, setSaving] = useState(false);

  const addItem = () => setItems(i => [...i, { material_name: '', material_category: 'fabric', qty: 0, unit: 'pcs', notes: '' }]);
  const upd = (idx, field, val) => setItems(i => i.map((it, j) => j === idx ? { ...it, [field]: val } : it));

  const handleSave = async () => {
    if (items.some(i => !i.material_name.trim())) return toast.error('Semua item harus punya nama material');
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/material-receive`, {
        method: 'POST', headers,
        body: JSON.stringify({ po_id: po.id, receive_date: receiveDate, items })
      });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal'); }
      toast.success('Material berhasil dicatat');
      onSave();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs">Tanggal Terima</Label>
        <Input type="date" value={receiveDate} onChange={e => setReceiveDate(e.target.value)} className="bg-foreground/5 border-border text-sm" />
      </div>
      <div className="space-y-2">
        {items.map((it, idx) => (
          <div key={idx} className="grid grid-cols-5 gap-2 items-end">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">Nama Material</Label>
              <Input value={it.material_name} onChange={e => upd(idx, 'material_name', e.target.value)}
                className="bg-foreground/5 border-border text-sm" placeholder="Kain Katun Cut" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Kategori</Label>
              <Select value={it.material_category} onValueChange={v => upd(idx, 'material_category', v)}>
                <SelectTrigger className="bg-foreground/5 border-border text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="fabric">Kain</SelectItem>
                  <SelectItem value="accessories">Aksesoris</SelectItem>
                  <SelectItem value="packaging">Packaging</SelectItem>
                  <SelectItem value="other">Lainnya</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Qty</Label>
              <Input type="number" value={it.qty} onChange={e => upd(idx, 'qty', parseFloat(e.target.value) || 0)}
                className="bg-foreground/5 border-border text-sm" min={0} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Unit</Label>
              <Select value={it.unit} onValueChange={v => upd(idx, 'unit', v)}>
                <SelectTrigger className="bg-foreground/5 border-border text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pcs">pcs</SelectItem>
                  <SelectItem value="yard">yard</SelectItem>
                  <SelectItem value="kg">kg</SelectItem>
                  <SelectItem value="roll">roll</SelectItem>
                  <SelectItem value="lusin">lusin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={addItem} className="border-border hover:bg-foreground/10 text-xs">
          <Plus className="w-3 h-3 mr-1" /> Tambah Item
        </Button>
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button onClick={handleSave} disabled={saving} className="bg-cyan-600 hover:bg-cyan-500">
          {saving ? 'Menyimpan...' : 'Simpan Penerimaan'}
        </Button>
      </DialogFooter>
    </div>
  );
}

// ─── BOM FORM ─────────────────────────────────────────────────────────────────
function BOMForm({ po, headers, onSave, onClose }) {
  const [existingBom, setExistingBom] = useState(null);
  const [loading, setLoading] = useState(true);
  const [materials, setMaterials] = useState([
    { material_name: '', material_category: 'fabric', ownership: 'client_provided', unit: 'yard', qty_estimated: 0, qty_actual: null }
  ]);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/dewi/maklon/bom/${po.id}`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setExistingBom(d);
          setMaterials(d.materials || []);
          setNotes(d.notes || '');
        }
      })
      .finally(() => setLoading(false));
  }, [po.id, headers]);

  const addMat = () => setMaterials(m => [...m, { material_name: '', material_category: 'fabric', ownership: 'client_provided', unit: 'yard', qty_estimated: 0, qty_actual: null }]);
  const upd = (idx, field, val) => setMaterials(m => m.map((it, i) => i === idx ? { ...it, [field]: val } : it));

  const totalQty = po.total_qty || 1;

  const handleSave = async () => {
    if (materials.some(m => !m.material_name.trim())) return toast.error('Semua material harus punya nama');
    setSaving(true);
    try {
      const url = existingBom ? `${API}/api/dewi/maklon/bom/${po.id}` : `${API}/api/dewi/maklon/bom`;
      const method = existingBom ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify({ po_id: po.id, materials, notes }) });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal'); }
      toast.success(existingBom ? 'BOM diupdate' : 'BOM dibuat');
      onSave();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="text-center py-8 text-muted-foreground text-sm">Memuat BOM...</div>;

  // Phase M2.2: Apply BOM Template button
  const hasCatalogLink = (po.items || []).some(it => it.buyer_catalog_id);

  const applyTemplate = async () => {
    if (!window.confirm('Replace materials saat ini dengan BOM Template aktif dari artikel? Pastikan sudah simpan yang manual sebelum lanjut.')) return;
    try {
      const r = await fetch(`${API}/api/dewi/maklon/bom-templates/apply-to-po`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ po_id: po.id }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal apply template');
      }
      const d = await r.json();
      toast.success(d.message || `${d.material_count} material di-apply dari template`);
      // Reload current BOM
      const r2 = await fetch(`${API}/api/dewi/maklon/bom/${po.id}`, { headers });
      if (r2.ok) {
        const data = await r2.json();
        setExistingBom(data);
        // Map template materials ke format BOM existing (preserve compat)
        const mappedMats = (data.materials || []).map(m => ({
          material_name: m.material_name || '',
          material_category: m.category || 'fabric',
          ownership: m.ownership || 'client_provided',
          unit: m.unit || 'pcs',
          qty_estimated: Number(m.qty_total_est || (m.qty_per_pcs || 0) * (po.total_qty || 0)) || 0,
          qty_actual: null,
        }));
        if (mappedMats.length) setMaterials(mappedMats);
      }
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-violet-500/10 border border-violet-400/20 rounded-lg px-3 py-2 text-xs text-violet-600 dark:text-violet-300 flex items-center justify-between gap-3 flex-wrap">
        <div>
          Total PO: <strong>{fmtNum(totalQty)} pcs</strong> — qty/pcs = total_estimasi ÷ {totalQty}
        </div>
        {hasCatalogLink && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs border-violet-400/40 bg-violet-500/15 text-violet-700 dark:text-violet-200 hover:bg-violet-500/25"
            onClick={applyTemplate}
            data-testid="po-bom-apply-template"
          >
            <BookOpen className="w-3 h-3 mr-1" /> Apply BOM Template
          </Button>
        )}
      </div>

      <div className="space-y-2">
        <div className="grid grid-cols-7 gap-1 text-xs text-muted-foreground px-1 font-medium">
          <span className="col-span-2">Material</span>
          <span>Kategori</span>
          <span>Sumber</span>
          <span>Unit</span>
          <span>Total Est.</span>
          <span>per pcs (auto)</span>
        </div>
        {materials.map((m, idx) => (
          <div key={idx} className="grid grid-cols-7 gap-1 items-center">
            <Input value={m.material_name} onChange={e => upd(idx, 'material_name', e.target.value)}
              className="col-span-2 h-7 text-xs bg-foreground/5 border-border" placeholder="Kain Voile" />
            <Select value={m.material_category} onValueChange={v => upd(idx, 'material_category', v)}>
              <SelectTrigger className="h-7 text-xs bg-foreground/5 border-border"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="fabric">Kain</SelectItem>
                <SelectItem value="accessories">Aksesoris</SelectItem>
                <SelectItem value="packaging">Packaging</SelectItem>
              </SelectContent>
            </Select>
            <Select value={m.ownership} onValueChange={v => upd(idx, 'ownership', v)}>
              <SelectTrigger className="h-7 text-xs bg-foreground/5 border-border"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="client_provided">Klien</SelectItem>
                <SelectItem value="cv_da_stock">CV.DA</SelectItem>
              </SelectContent>
            </Select>
            <Select value={m.unit} onValueChange={v => upd(idx, 'unit', v)}>
              <SelectTrigger className="h-7 text-xs bg-foreground/5 border-border"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['yard', 'kg', 'pcs', 'meter', 'lusin', 'roll'].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input type="number" value={m.qty_estimated} onChange={e => upd(idx, 'qty_estimated', parseFloat(e.target.value) || 0)}
              className="h-7 text-xs bg-foreground/5 border-border" min={0} />
            <div className="h-7 flex items-center px-2 text-xs text-muted-foreground bg-foreground/[0.03] rounded border border-foreground/5">
              {totalQty > 0 ? (m.qty_estimated / totalQty).toFixed(4) : '—'}
            </div>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={addMat} className="border-border hover:bg-foreground/10 text-xs">
          <Plus className="w-3 h-3 mr-1" /> Tambah Material
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Catatan</Label>
        <Textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className="bg-foreground/5 border-border text-sm resize-none" />
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? 'Menyimpan...' : (existingBom ? 'Update BOM' : 'Buat BOM')}
        </Button>
      </DialogFooter>
    </div>
  );
}

// ─── MAIN MODULE ──────────────────────────────────────────────────────────────
export default function MaklonPOModule({ token, onNavigate }) {
  window._authToken = token;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [pos, setPos] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('all');
  const [createDialog, setCreateDialog] = useState(false);
  const [detailPO, setDetailPO] = useState(null);
  const [search, setSearch] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [posR, clientsR] = await Promise.all([
        fetch(`${API}/api/dewi/maklon/pos`, { headers }),
        fetch(`${API}/api/dewi/maklon/clients?status=active`, { headers }),
      ]);
      if (posR.ok) setPos(await posR.json());
      if (clientsR.ok) setClients(await clientsR.json());
    } catch (e) { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = useMemo(() => {
    let list = pos;
    if (tab === 'active') list = list.filter(p => ['confirmed', 'in_production', 'partial_delivered'].includes(p.status));
    else if (tab !== 'all') list = list.filter(p => p.status === tab);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(p => p.po_number?.toLowerCase().includes(q) || p.client_name?.toLowerCase().includes(q));
    }
    return list;
  }, [pos, tab, search]);

  const stats = useMemo(() => ({
    total: pos.length,
    active: pos.filter(p => ['confirmed', 'in_production', 'partial_delivered'].includes(p.status)).length,
    draft: pos.filter(p => p.status === 'draft').length,
    totalValue: pos.filter(p => p.status !== 'cancelled').reduce((s, p) => s + (p.total_value || 0), 0),
  }), [pos]);

  return (
    <div className="space-y-6" data-testid="maklon-po-page">
      <PageHeader
        title="Portal Maklon — Purchase Order"
        subtitle="Manajemen PO Maklon dengan Seri, Multi-Dispatch, dan Finance Integration"
        icon={Package}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={fetchData} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="maklon-po-refresh-btn">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size="sm" onClick={() => setCreateDialog(true)} data-testid="maklon-po-create-btn">
              <Plus className="w-4 h-4 mr-2" /> Buat PO Baru
            </Button>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total PO', value: stats.total, color: 'text-foreground' },
          { label: 'Aktif', value: stats.active, color: 'text-blue-700 dark:text-blue-300' },
          { label: 'Draft', value: stats.draft, color: 'text-amber-600 dark:text-amber-300' },
          { label: 'Total Nilai (aktif)', value: fmtRp(stats.totalValue), color: 'text-green-600 dark:text-green-300', small: true },
        ].map(s => (
          <GlassCard key={s.label} className="p-4">
            <div className="text-xs text-muted-foreground mb-1">{s.label}</div>
            <div className={`${s.small ? 'text-lg' : 'text-2xl'} font-bold ${s.color}`}>{s.value}</div>
          </GlassCard>
        ))}
      </div>

      {/* Onward CTA — Alur 10: PO dibuat → pantau progress 360 & billing */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Setelah PO dibuat / dikonfirmasi"
        actions={[
          { module: 'maklon-po-360', label: 'Pantau Progress 360°', icon: BarChart3, primary: true },
        ]}
      />

      {/* Tabs + search */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-foreground/5">
              <TabsTrigger value="all">Semua</TabsTrigger>
              <TabsTrigger value="draft">Draft</TabsTrigger>
              <TabsTrigger value="active">Aktif</TabsTrigger>
              <TabsTrigger value="partial_delivered">Sebagian</TabsTrigger>
              <TabsTrigger value="completed">Selesai</TabsTrigger>
            </TabsList>
          </Tabs>
          <Input placeholder="Cari PO / klien..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-56 bg-foreground/5 border-border text-sm" data-testid="maklon-po-search-input" />
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground">Memuat...</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Package}
            title="Tidak ada PO ditemukan"
            description="Coba ubah filter status atau kata kunci pencarian."
            action={{ label: 'Buat PO Pertama', onClick: () => setCreateDialog(true) }}
          />
        ) : (
          <div className="space-y-2">
            {filtered.map(po => {
              const progressPct = po.total_qty > 0 ? Math.round(((po.qty_dispatched || 0) / po.total_qty) * 100) : 0;
              return (
                <motion.div key={po.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                  className="flex items-center justify-between p-3 rounded-lg bg-foreground/[0.03] border border-border/60 hover:bg-foreground/[0.06] hover:border-border transition-all cursor-pointer group"
                  data-testid={`maklon-po-card-${po.id}`}
                  onClick={() => setDetailPO(po)}>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-500/20 flex items-center justify-center">
                      <Package className="w-5 h-5 text-violet-600 dark:text-violet-300" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-bold text-foreground">{po.po_number}</span>
                        <StatusBadge status={po.status} />
                        {po.dispatch_count > 0 && (
                          <span className="text-xs bg-violet-500/15 text-violet-600 dark:text-violet-300 px-1.5 rounded">{po.dispatch_count} dispatch</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-muted-foreground">{po.client_name}</span>
                        <span className="text-xs text-muted-foreground/60">{po.po_date}</span>
                        {po.deadline && <span className="text-xs text-amber-700 dark:text-amber-400">📅 {po.deadline}</span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    {/* Progress mini */}
                    <div className="hidden md:block w-32">
                      <div className="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>{fmtNum(po.qty_dispatched || 0)} / {fmtNum(po.total_qty)}</span>
                        <span>{progressPct}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-green-400"
                          style={{ width: `${progressPct}%` }} />
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-sm font-bold text-green-300">{fmtRp(po.total_value)}</div>
                      <div className="text-xs text-muted-foreground">{fmtNum(po.total_qty)} pcs</div>
                    </div>
                    {onNavigate && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-violet-400/30 text-violet-700 dark:text-violet-200 hover:bg-violet-500/10 hover:border-violet-400/50 text-[10px] h-7 px-2"
                        data-testid={`po-view-360-${po.id}`}
                        onClick={(e) => { e.stopPropagation(); onNavigate('maklon-po-360', { po_id: po.id }); }}
                      >
                        <BarChart3 className="w-3 h-3 mr-1" /> 360°
                      </Button>
                    )}
                    <ArrowRight className="w-4 h-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </GlassCard>

      {/* Create Dialog */}
      <Dialog open={createDialog} onOpenChange={setCreateDialog}>
        <DialogContent className="max-w-4xl bg-card border-border">
          <DialogHeader><DialogTitle>Buat PO Maklon Baru</DialogTitle></DialogHeader>
          <POForm clients={clients} onSave={() => { setCreateDialog(false); fetchData(); }} onClose={() => setCreateDialog(false)} />
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detailPO} onOpenChange={() => setDetailPO(null)}>
        <DialogContent className="max-w-4xl bg-card border-border">
          <DialogHeader>
            <DialogTitle>Detail PO — {detailPO?.po_number}</DialogTitle>
          </DialogHeader>
          {detailPO && <PODetail po={detailPO} onClose={() => setDetailPO(null)} onRefresh={fetchData} clients={clients} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

