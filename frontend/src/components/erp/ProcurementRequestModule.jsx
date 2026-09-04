/**
 * ProcurementRequestModule — Pengadaan Barang/Jasa (Purchase Requests)
 * CV. Dewi Aditya — P1.C Procure-to-Pay
 *
 * Backend: /api/procurement/*
 * Flows: Draft → Submit → Approve/Reject → Complete
 */
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import axios from 'axios';
import OnwardCTA from './OnwardCTA';
import {
  Plus, RefreshCw, ChevronRight, Search, AlertTriangle,
  CheckCircle2, XCircle, Clock, ShoppingCart, FileText,
  Send, Trash2, History, Inbox, ShieldAlert, Info,
  Check, Circle, Layers, Loader2, Package,
  Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite from '@/components/ui/pagination-lite';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL;

// F13-B (sesi #12) — pengalih Tabel/Kartu yang DIINGAT + kolom CSV.
// PR adalah komitmen UANG: "PR mana yang paling besar & menunggu siapa" harus
// bisa dijawab tanpa menggulir, dan bisa dibawa ke rapat sebagai berkas.
const PR_VIEW_KEY = 'procurement_pr_view';
const PR_CSV_HEAD = ['No. PR', 'Judul', 'Jenis', 'Departemen', 'Prioritas',
  'Status', 'Nilai (Rp)', 'Pemohon', 'Dibutuhkan', 'Dibuat', 'Menunggu',
  'No. PO'];

// Label pendek tiap tahap untuk stepper ringkas di kartu daftar.
// Label panjangnya datang dari server (`chain[].label`) — SATU sumber kebenaran.
const STAGE_SHORT = { dept: 'Dept', finance: 'Keuangan', final: 'Final' };

/** Tanggal + jam ringkas (id-ID). Aman untuk nilai kosong / rusak. */
function fmtDT(v) {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('id-ID', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const PRIORITY_CFG = {
  low:    { label: 'Rendah',   color: 'text-muted-foreground bg-muted dark:bg-slate-400/10 border-border dark:border-slate-400/20' },
  medium: { label: 'Sedang',  color: 'text-blue-600 dark:text-blue-400  bg-blue-50 dark:bg-blue-400/10  border-blue-300 dark:border-blue-400/20'  },
  high:   { label: 'Tinggi',  color: 'text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-400/10 border-amber-300 dark:border-amber-400/20' },
  urgent: { label: 'Urgent',  color: 'text-red-700 dark:text-red-400   bg-red-50 dark:bg-red-400/10   border-red-300 dark:border-red-400/20'   },
};

const STATUS_CFG = {
  draft:            { label: 'Draft',                      icon: FileText,    color: 'text-muted-foreground bg-muted border-border dark:text-muted-foreground dark:bg-slate-400/10 dark:border-slate-400/20' },
  submitted:        { label: 'Menunggu Persetujuan Dept',  icon: Clock,       color: 'text-amber-700 bg-amber-100 border-amber-300 dark:text-amber-400 dark:bg-amber-400/10 dark:border-amber-400/20' },
  dept_approved:    { label: 'Menunggu Persetujuan Keuangan', icon: Clock,    color: 'text-orange-700 bg-orange-100 border-orange-300 dark:text-orange-400 dark:bg-orange-400/10 dark:border-orange-400/20' },
  finance_approved: { label: 'Menunggu Persetujuan Final',  icon: Clock,      color: 'text-yellow-700 bg-yellow-100 border-yellow-300 dark:text-yellow-400 dark:bg-yellow-400/10 dark:border-yellow-400/20' },
  approved:         { label: 'Disetujui',                  icon: CheckCircle2,color: 'text-emerald-700 bg-emerald-100 border-emerald-300 dark:text-emerald-400 dark:bg-emerald-400/10 dark:border-emerald-400/20' },
  in_procurement:   { label: 'Sedang Pengadaan',           icon: ShoppingCart,color: 'text-blue-700 bg-blue-100 border-blue-300 dark:text-blue-400 dark:bg-blue-400/10 dark:border-blue-400/20' },
  rejected:         { label: 'Ditolak',                    icon: XCircle,     color: 'text-red-700 bg-red-100 border-red-300 dark:text-red-400 dark:bg-red-400/10 dark:border-red-400/20' },
  completed:        { label: 'Selesai',                    icon: CheckCircle2,color: 'text-sky-700 bg-sky-100 border-sky-300 dark:text-sky-400 dark:bg-sky-400/10 dark:border-sky-400/20' },
  cancelled:        { label: 'Dibatalkan',                 icon: XCircle,     color: 'text-muted-foreground bg-muted border-border dark:text-zinc-500 dark:bg-zinc-500/10 dark:border-zinc-500/20' },
};

const TYPE_LABELS = {
  asset: 'Aset Tetap', consumable: 'Barang Habis Pakai',
  service: 'Jasa', subscription: 'Langganan / SaaS',
  maintenance: 'Kontrak Maintenance', rental: 'Sewa Alat/Fasilitas',
  project: 'Berbasis Proyek', other: 'Lainnya',
};

/**
 * TabButton — DI LUAR komponen induk dengan sengaja.
 *
 * Sebelumnya komponen ini didefinisikan DI DALAM `ProcurementRequestModule`.
 * Akibatnya React melihat TIPE komponen yang BARU pada setiap render, lalu
 * membongkar-pasang seluruh subtree-nya: fokus keyboard hilang dan state di
 * dalamnya ter-reset — persis saat pemakai sedang mengetik di penyaring.
 * Gejalanya terasa seperti "kadang-kadang aplikasinya nge-lag", jadi hampir
 * tidak pernah dilaporkan sebagai bug.
 */
function TabButton({ id, label, count, testId, active, onSelect }) {
  return (
    <button
      onClick={() => onSelect(id)}
      className={`relative -mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
          : 'border-transparent text-muted-foreground hover:text-foreground'
      }`}
      data-testid={testId}
    >
      {label}
      {count > 0 && (
        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
          id === 'inbox'
            ? 'bg-amber-500 text-white'
            : 'bg-foreground/10 text-foreground/70'
        }`}>
          {count}
        </span>
      )}
    </button>
  );
}

const fmtRp = formatRupiah;

function StatusBadge({ status }) {
  const c = STATUS_CFG[status] || STATUS_CFG.draft;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>
      <Icon size={10} /> {c.label}
    </span>
  );
}

function PriorityBadge({ priority }) {
  const c = PRIORITY_CFG[priority] || PRIORITY_CFG.medium;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>
      {c.label}
    </span>
  );
}

// ── Stats Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = 'text-foreground' }) {
  return (
    <div className="bg-foreground/5 border border-foreground/10 rounded-xl p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

// ── Create PR Modal ───────────────────────────────────────────────────────────
function CreatePRModal({ onClose, onCreated, token }) {
  const [form, setForm] = useState({
    title: '', description: '', justification: '',
    priority: 'medium', request_type: 'consumable', department: '',
    request_number: '',
  });
  // SESI #19 — kebijakan penomoran PR (Otomatis/Manual) dibaca dari Administrasi
  // Sistem → Penomoran Dokumen. Tanpa ini, setelan MANUAL membuat PR tidak bisa
  // dibuat (backend menolak "nomor wajib diisi" atas setelan yang tak terlihat).
  const numPolicy = useDocNumberPolicy('dewi_procurement_requests.request_number', token);
  const [items, setItems] = useState([{ material_id: '', name: '', specification: '', qty: 1, unit: 'pcs', estimated_price: 0, notes: '' }]);
  const [materials, setMaterials] = useState([]);
  const [uomMap, setUomMap] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const [requestTypes, setRequestTypes] = useState(Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label })));

  // Fetch request types dari API (Phase 5B)
  useEffect(() => {
    const fetchTypes = async () => {
      try {
        const res = await fetch(`${API}/api/procurement/request-types`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data.items?.length > 0) {
            setRequestTypes(data.items);
          }
        }
      } catch {
        // fallback ke TYPE_LABELS jika fetch gagal
      }
    };
    fetchTypes();
  }, [token]);

  // Master material + daftar satuan sah (Portal Pengadaan 2026-08-06):
  // item PR kini boleh menunjuk material master supaya PO hasilnya bisa masuk
  // stok kanonik, dan satuan beli dikonversi otomatis ke satuan dasar.
  useEffect(() => {
    const h = { Authorization: `Bearer ${token}` };
    fetch(`${API}/api/rahaza/materials`, { headers: h })
      .then((r) => (r.ok ? r.json() : []))
      .then((m) => setMaterials((Array.isArray(m) ? m : m?.items || []).filter((x) => x.active !== false)))
      .catch(() => {});
  }, [token]);

  const loadUom = async (materialId) => {
    if (!materialId || uomMap[materialId]) return uomMap[materialId];
    try {
      const r = await fetch(`${API}/api/rahaza/materials/uom-options?material_ids=${materialId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) return null;
      const d = await r.json();
      const o = (d?.options || {})[materialId] || null;
      if (o) setUomMap((p) => ({ ...p, [materialId]: o }));
      return o;
    } catch { return null; }
  };

  const pickMaterial = async (i, materialId) => {
    const mat = materials.find((m) => m.id === materialId);
    setItem(i, 'material_id', materialId);
    if (!materialId) return;
    const opt = await loadUom(materialId);
    setItems((p) => p.map((it, idx) => (idx === i ? {
      ...it,
      material_id: materialId,
      name: it.name?.trim() ? it.name : (mat?.name || ''),
      unit: opt?.base_unit || mat?.unit || it.unit,
    } : it)));
    // Saran harga dari daftar harga supplier (harga per satuan beli)
    try {
      const r = await fetch(`${API}/api/procurement/price-lookup?material_id=${materialId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) {
        const d = await r.json();
        if (d?.best?.price) {
          setItems((p) => p.map((it, idx) => (idx === i ? {
            ...it, unit: d.best.uom || it.unit, estimated_price: Number(d.best.price),
          } : it)));
        }
      }
    } catch { /* saran harga opsional */ }
  };

  const addItem = () => setItems(p => [...p, { material_id: '', name: '', specification: '', qty: 1, unit: 'pcs', estimated_price: 0, notes: '' }]);
  const rmItem  = (i) => setItems(p => p.filter((_, idx) => idx !== i));
  const setItem = (i, k, v) => setItems(p => p.map((it, idx) => idx === i ? { ...it, [k]: v } : it));

  const factorOf = (it) => {
    const opt = uomMap[it.material_id];
    if (!opt || !it.unit || it.unit === opt.base_unit) return 1;
    const row = (opt.units || []).find((u) => u.unit === it.unit);
    return row ? Number(row.factor_to_base) : 1;
  };

  const totalEst = items.reduce((s, it) => s + Number(it.qty||0) * Number(it.estimated_price||0), 0);

  const submit = async () => {
    if (!form.title.trim()) return setError('Judul wajib diisi');
    if (!items[0].name.trim()) return setError('Minimal 1 item harus diisi');
    if (numPolicy?.mode === 'manual' && !form.request_number.trim()) {
      return setError(`Nomor PR wajib diisi (pola ${numPolicy.format}).`);
    }
    setSaving(true); setError('');
    try {
      const { request_number: _rn, ...rest } = form;
      await axios.post(`${API}/api/procurement/requests`, {
        ...rest,
        ...docNumberPayload(numPolicy, 'request_number', form.request_number),
        items: items.map((it) => ({
          material_id: it.material_id || undefined,
          name: it.name,
          specification: it.specification,
          qty: Number(it.qty) || 0,
          uom: it.unit,
          estimated_price: Number(it.estimated_price) || 0,
          notes: it.notes,
        })),
      }, { headers: { Authorization: `Bearer ${token}` } });
      onCreated();
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal membuat PR');
    } finally { setSaving(false); }
  };

  const inp = 'w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:border-blue-600 dark:border-blue-500/50';
  const sel = inp + ' appearance-none';

  return (
    <div className="fixed inset-0 bg-foreground/50 z-50 flex items-center justify-center p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-card border border-foreground/10 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-foreground/10">
          <h2 className="text-base font-semibold text-foreground">Buat Permintaan Pengadaan</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <div className="p-5 space-y-4">
          {error && <div className="text-red-700 dark:text-red-400 text-sm bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 rounded-lg px-3 py-2">{error}</div>}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <DocNumberField
                policy={numPolicy}
                value={form.request_number}
                onChange={(v) => setForm(p => ({ ...p, request_number: v }))}
                label="Nomor PR"
                testId="pr-number"
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Judul Permintaan *</label>
              <input className={inp} placeholder="mis. Pembelian Laptop Karyawan Baru" value={form.title} onChange={e => setForm(p=>({...p,title:e.target.value}))} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tipe Pengadaan</label>
              <SmartNativeSelect className={sel} value={form.request_type} onChange={e => setForm(p=>({...p,request_type:e.target.value}))}>
                {requestTypes.map(rt => <option key={rt.value} value={rt.value}>{rt.label}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Prioritas</label>
              <SmartNativeSelect className={sel} value={form.priority} onChange={e => setForm(p=>({...p,priority:e.target.value}))}>
                {Object.entries(PRIORITY_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
              </SmartNativeSelect>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Departemen</label>
              <input className={inp} placeholder="mis. Produksi, HR, IT" value={form.department} onChange={e => setForm(p=>({...p,department:e.target.value}))} />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Justifikasi / Alasan</label>
              <textarea className={inp} rows={2} placeholder="Jelaskan mengapa pengadaan ini diperlukan" value={form.justification} onChange={e => setForm(p=>({...p,justification:e.target.value}))} />
            </div>
          </div>

          <div className="border-t border-foreground/10 pt-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-foreground">Items ({items.length})</span>
              <button onClick={addItem} className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-600 dark:text-blue-300">
                <Plus size={12} /> Tambah Item
              </button>
            </div>
            {items.map((it, i) => {
              const opt = uomMap[it.material_id];
              const f = factorOf(it);
              const qtyBase = (Number(it.qty) || 0) * f;
              return (
                <div key={i} className="bg-foreground/5 border border-foreground/10 rounded-xl p-3 mb-2 space-y-2">
                  <div className="flex gap-2">
                    <SmartNativeSelect
                      className={sel}
                      value={it.material_id}
                      onChange={e => pickMaterial(i, e.target.value)}
                      data-testid={`pr-item-material-${i}`}
                    >
                      <option value="">Item bebas / non-master</option>
                      {materials.map(m => (
                        <option key={m.id} value={m.id}>{`${m.code} - ${m.name}`}</option>
                      ))}
                    </SmartNativeSelect>
                    {items.length > 1 && (
                      <button onClick={() => rmItem(i)} className="p-2 text-red-700 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 flex-shrink-0"
                              data-testid={`pr-item-remove-${i}`}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                  <input className={inp} placeholder="Nama item *" value={it.name}
                         onChange={e => setItem(i, 'name', e.target.value)}
                         data-testid={`pr-item-name-${i}`} />
                  <input className={inp} placeholder="Spesifikasi" value={it.specification} onChange={e => setItem(i,'specification',e.target.value)} />
                  <div className="grid grid-cols-3 gap-2">
                    <input type="number" min="0" step="0.01" className={inp} placeholder="Qty" value={it.qty}
                           onChange={e => setItem(i,'qty',e.target.value)} data-testid={`pr-item-qty-${i}`} />
                    {it.material_id && opt ? (
                      <SmartNativeSelect className={sel} value={it.unit}
                                         onChange={e => setItem(i, 'unit', e.target.value)}
                                         data-testid={`pr-item-uom-${i}`}>
                        {(opt.units || []).map(u => <option key={u.unit} value={u.unit}>{u.unit}</option>)}
                      </SmartNativeSelect>
                    ) : (
                      <input className={inp} placeholder="Satuan" value={it.unit}
                             onChange={e => setItem(i,'unit',e.target.value)}
                             data-testid={`pr-item-uom-${i}`} />
                    )}
                    <input type="number" min="0" className={inp} placeholder="Estimasi Harga" value={it.estimated_price}
                           onChange={e => setItem(i,'estimated_price',e.target.value)}
                           data-testid={`pr-item-price-${i}`} />
                  </div>
                  {it.material_id && opt && it.unit && it.unit !== opt.base_unit && (
                    <p className="text-[11px] text-muted-foreground" data-testid={`pr-item-preview-${i}`}>
                      1 {it.unit} = {f.toLocaleString('id-ID', { maximumFractionDigits: 4 })} {opt.base_unit} ⇒{' '}
                      <span className="font-semibold text-foreground">
                        {qtyBase.toLocaleString('id-ID', { maximumFractionDigits: 4 })} {opt.base_unit}
                      </span>{' '}
                      · harga per {opt.base_unit}: {fmtRp((Number(it.estimated_price) || 0) / (f || 1))}
                    </p>
                  )}
                </div>
              );
            })}
            <div className="text-right text-sm font-semibold text-foreground mt-2">
              Total Estimasi: <span className="text-emerald-600 dark:text-emerald-400">{fmtRp(totalEst)}</span>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 p-5 border-t border-foreground/10">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">Batal</button>
          <button onClick={submit} disabled={saving} className="px-5 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-foreground rounded-xl disabled:opacity-50">
            {saving ? 'Menyimpan...' : 'Simpan Draft'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Create PO from PR Modal ───────────────────────────────────────────────────
function CreatePOFromPRModal({ pr, token, onClose, onCreated }) {
  const [form, setForm] = useState({
    supplier_id: '', vendor_name: '', vendor_contact: '', vendor_address: '',
    expected_delivery_date: '', notes: '',
  });
  const [suppliers, setSuppliers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const inp = 'w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:border-blue-600 dark:border-blue-500/50';
  const sel = inp + ' appearance-none';

  useEffect(() => {
    fetch(`${API}/api/procurement/suppliers/options`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((d) => setSuppliers(d?.items || []))
      .catch(() => {});
  }, [token]);

  const submit = async () => {
    if (!form.supplier_id && !form.vendor_name.trim()) {
      return setError('Pilih supplier dari Master Supplier terlebih dahulu');
    }
    setSaving(true); setError('');
    try {
      await axios.post(`${API}/api/procurement/requests/${pr.id}/create-po`, form, {
        headers: { Authorization: `Bearer ${token}` }
      });
      onCreated();
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal membuat PO');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-foreground/60 z-[60] flex items-center justify-center p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-card border border-foreground/10 rounded-2xl w-full max-w-lg" data-testid="create-po-from-pr-modal">
        <div className="flex items-center justify-between p-5 border-b border-foreground/10">
          <div>
            <h2 className="text-base font-semibold text-foreground">Buat Purchase Order</h2>
            <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">Dari PR: {pr.request_number} — {pr.title}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <div className="p-5 space-y-3">
          {error && <div className="text-red-700 dark:text-red-400 text-sm bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 rounded-lg px-3 py-2">{error}</div>}
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Supplier (Master) *</label>
            <SmartNativeSelect
              className={sel}
              value={form.supplier_id}
              onChange={(e) => {
                const sid = e.target.value;
                const s = suppliers.find((x) => x.id === sid);
                setForm((p) => ({
                  ...p,
                  supplier_id: sid,
                  vendor_name: s?.name || '',
                  vendor_contact: s?.phone || p.vendor_contact,
                  vendor_address: s?.address || p.vendor_address,
                }));
              }}
              data-testid="po-vendor-name"
            >
              <option value="">Pilih supplier dari master</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{`${s.code} — ${s.name}`}</option>
              ))}
            </SmartNativeSelect>
            {suppliers.length === 0 && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
                Master Supplier masih kosong. Tambahkan supplier di menu Master Supplier.
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Kontak Vendor</label>
              <input className={inp} placeholder="Telepon / Email" value={form.vendor_contact}
                onChange={e => setForm(p=>({...p,vendor_contact:e.target.value}))} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tgl. Pengiriman Diharapkan</label>
              <input type="date" className={inp} value={form.expected_delivery_date}
                onChange={e => setForm(p=>({...p,expected_delivery_date:e.target.value}))} />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Alamat Vendor</label>
            <input className={inp} placeholder="Alamat lengkap vendor" value={form.vendor_address}
              onChange={e => setForm(p=>({...p,vendor_address:e.target.value}))} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Catatan</label>
            <textarea className={inp} rows={2} placeholder="Instruksi tambahan untuk vendor" value={form.notes}
              onChange={e => setForm(p=>({...p,notes:e.target.value}))} />
          </div>
          {/* Item preview */}
          <div className="bg-foreground/5 border border-foreground/10 rounded-xl p-3">
            <p className="text-xs text-muted-foreground mb-2">Item dari PR ({(pr.items||[]).length} item):</p>
            <div className="space-y-1">
              {(pr.items||[]).map((it,i) => (
                <div key={i} className="flex justify-between text-xs">
                  <span className="text-foreground/80">{it.name} <span className="text-muted-foreground/60 dark:text-zinc-500">× {it.qty} {it.unit}</span></span>
                  <span className="text-emerald-600 dark:text-emerald-400">{fmtRp(it.total_price)}</span>
                </div>
              ))}
            </div>
            <div className="flex justify-between text-sm font-semibold mt-2 pt-2 border-t border-foreground/10">
              <span className="text-foreground/80">Total Estimasi</span>
              <span className="text-emerald-600 dark:text-emerald-400">{fmtRp(pr.total_estimated)}</span>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 p-5 border-t border-foreground/10">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground">Batal</button>
          <button onClick={submit} disabled={saving}
            className="px-5 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-foreground rounded-xl disabled:opacity-50"
            data-testid="btn-confirm-create-po">
            {saving ? 'Membuat PO...' : 'Buat PO'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Rantai persetujuan (stepper) ─────────────────────────────────────────────
// Menampilkan tahap yang WAJIB dilalui PR ini. Jumlah tahap TIDAK tetap: ia
// mengikuti nilai PR dan ambang yang diatur owner di Ringkasan Bisnis, lalu
// DIBEKUKAN saat PR diajukan. Semua data (`chain`) datang dari server.
function ApprovalStepper({ chain, compact = false }) {
  if (!Array.isArray(chain) || chain.length === 0) return null;

  if (compact) {
    return (
      <span className="inline-flex flex-wrap items-center gap-1" data-testid="pr-stepper-compact">
        {chain.map((s, i) => (
          <span key={s.stage} className="inline-flex items-center gap-1">
            <span
              className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${
                s.done
                  ? 'text-emerald-700 bg-emerald-100 border-emerald-300 dark:text-emerald-400 dark:bg-emerald-400/10 dark:border-emerald-400/20'
                  : s.current
                    ? 'text-amber-700 bg-amber-100 border-amber-300 dark:text-amber-400 dark:bg-amber-400/10 dark:border-amber-400/20'
                    : 'text-muted-foreground bg-muted border-border'
              }`}
            >
              {s.done ? <Check size={9} /> : s.current ? <Clock size={9} /> : <Circle size={9} />}
              {STAGE_SHORT[s.stage] || s.label}
            </span>
            {i < chain.length - 1 && <ChevronRight size={10} className="text-muted-foreground/60" />}
          </span>
        ))}
      </span>
    );
  }

  return (
    <div className="space-y-2" data-testid="pr-approval-stepper">
      {chain.map((s) => (
        <div
          key={s.stage}
          data-testid={`pr-stage-${s.stage}`}
          className={`flex items-start gap-3 rounded-xl border px-3 py-2 ${
            s.done
              ? 'border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10'
              : s.current
                ? 'border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10'
                : 'border-foreground/10 bg-foreground/5'
          }`}
        >
          <div
            className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
              s.done
                ? 'bg-emerald-600 text-white'
                : s.current
                  ? 'bg-amber-500 text-white'
                  : 'bg-muted text-muted-foreground'
            }`}
          >
            {s.done ? <Check size={11} /> : s.order}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">{s.label}</span>
              {s.done && (
                <span className="text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">Selesai</span>
              )}
              {s.current && (
                <span className="text-[10px] font-semibold text-amber-700 dark:text-amber-400">
                  Menunggu sekarang
                </span>
              )}
              {s.override && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-300">
                  <ShieldAlert size={9} /> Override admin
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {s.done
                ? `Oleh ${s.actor_name || '—'}${s.timestamp ? ` · ${fmtDT(s.timestamp)}` : ''}`
                : `Menunggu ${s.role_hint || 'approver'}`}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Penjelasan hak: kenapa tombol muncul / tidak muncul ──────────────────────
// Kalau approver tidak berhak, ia harus TAHU alasannya — bukan sekadar melihat
// tombol hilang (itu yang dulu terjadi dan membuat rantai persetujuan "mati").
function GateNotice({ item }) {
  if (item?.can_approve && item?.is_override) {
    return (
      <div
        className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-500/30 dark:bg-amber-500/10"
        data-testid="pr-override-notice"
      >
        <ShieldAlert size={14} className="mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
        <p className="text-xs text-amber-800 dark:text-amber-300">
          {item.override_note
            || 'Anda menembus aturan pemisahan wewenang sebagai admin/owner — tindakan ini dicatat di riwayat.'}
        </p>
      </div>
    );
  }
  if (!item?.can_approve && item?.blocked_reason) {
    // Hanya berguna saat masih ADA tahap yang menunggu. Pada PR yang sudah
    // selesai/ditolak, "tidak ada persetujuan yang menunggu" cuma kebisingan.
    if (!item?.stage) return null;
    return (
      <div
        className="flex items-start gap-2 rounded-xl border border-border bg-muted px-3 py-2"
        data-testid="pr-blocked-reason"
      >
        <Info size={14} className="mt-0.5 flex-shrink-0 text-muted-foreground" />
        <p className="text-xs text-foreground/70">{item.blocked_reason}</p>
      </div>
    );
  }
  return null;
}

// ── Detail Modal ──────────────────────────────────────────────────────────────
function DetailModal({ item, onClose, onAction, token, focusReject = false }) {
  const [pr, setPr] = useState(item);
  const [note, setNote] = useState('');
  const [acting, setActing] = useState('');
  const [err, setErr] = useState('');
  const [okMsg, setOkMsg] = useState('');
  const [timeline, setTimeline] = useState([]);
  const [loadTL, setLoadTL] = useState(true);
  const [showCreatePO, setShowCreatePO] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  // Basis endpoint datang dari SERVER (`api_base`): satu dialog melayani
  // Permintaan Pengadaan (/api/procurement/requests) DAN Request Pembelian
  // Aksesoris (/api/acc/purchase-requests) — keduanya kini memakai mesin
  // persetujuan yang sama, jadi UI-nya tidak perlu dua cabang.
  const base = item.api_base || '/api/procurement/requests';

  const reload = useCallback(async () => {
    setLoadTL(true);
    try {
      const [d, t] = await Promise.all([
        axios.get(`${API}${base}/${item.id}`, { headers }),
        axios.get(`${API}${base}/${item.id}/timeline`, { headers }),
      ]);
      setPr(d.data);
      setTimeline(t.data?.steps || []);
    } catch {
      /* tetap pakai data dari daftar bila detail gagal dimuat */
    } finally {
      setLoadTL(false);
    }
  }, [item.id, headers, base]);

  useEffect(() => { reload(); }, [reload]);

  const doAction = async (action) => {
    setErr(''); setOkMsg('');
    if (action === 'reject' && !note.trim()) {
      setErr('Alasan penolakan wajib diisi agar pemohon tahu apa yang harus diperbaiki.');
      return;
    }
    setActing(action);
    try {
      const res = await axios.post(
        `${API}${base}/${item.id}/${action}`,
        { comment: note, reason: note },
        { headers },
      );
      const d = res.data || {};
      if (action === 'approve') {
        setOkMsg(d.next_stage_label
          ? `Disetujui. Lanjut ke ${d.next_stage_label}.`
          : 'Disetujui penuh — permintaan siap dijadikan Purchase Order.');
      }
      setNote('');
      await reload();
      onAction(d);
    } catch (e) {
      setErr(e.response?.data?.detail || `Gagal ${action === 'approve' ? 'menyetujui' : action === 'reject' ? 'menolak' : action}`);
    } finally {
      setActing('');
    }
  };

  // SEMUA keputusan tombol datang dari SERVER (`can_approve` / `can_reject`).
  // Modul ini SENGAJA tidak punya daftar peran sendiri: daftar peran kembar di
  // frontend inilah yang dulu menyembunyikan tombol Setujui/Tolak dari approver
  // ASLI (accounting / supervisor_produksi / admin_gudang) sehingga rantai
  // persetujuan mati di layar walau backend mengizinkan.
  const canApprove = !!pr.can_approve;
  const canReject = !!pr.can_reject;
  const canSubmit = pr.status === 'draft';
  const canComplete = pr.status === 'in_procurement';
  const canCreatePO = pr.status === 'approved' && !pr.linked_po_number
    && (item.kind || 'pr') === 'pr';
  const hasActions = canApprove || canReject || canSubmit || canComplete || canCreatePO;

  return (
    <div
      className="fixed inset-0 bg-foreground/50 z-50 flex items-start justify-center p-4 pt-16"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-card border border-foreground/10 rounded-2xl w-full max-w-2xl max-h-[82vh] overflow-y-auto"
           data-testid="pr-detail-modal">
        <div className="flex items-start justify-between p-5 border-b border-foreground/10">
          <div>
            <h2 className="text-base font-semibold text-foreground">{pr.title}</h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className="text-xs text-muted-foreground/60 dark:text-zinc-500">{pr.request_number}</span>
              <StatusBadge status={pr.status} />
              <PriorityBadge priority={pr.priority} />
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" data-testid="pr-detail-close">✕</button>
        </div>

        <div className="p-5 space-y-4">
          {okMsg && (
            <div className="flex items-start gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 dark:border-emerald-500/30 dark:bg-emerald-500/10"
                 data-testid="pr-action-success">
              <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0 text-emerald-600 dark:text-emerald-400" />
              <p className="text-xs text-emerald-800 dark:text-emerald-300">{okMsg}</p>
            </div>
          )}
          {err && (
            <div className="flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 px-3 py-2 dark:border-red-500/30 dark:bg-red-500/10"
                 data-testid="pr-action-error">
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-red-600 dark:text-red-400" />
              <p className="text-xs text-red-700 dark:text-red-300">{err}</p>
            </div>
          )}

          {pr.linked_po_number && (
            <div className="flex items-center gap-2 bg-blue-50 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-500/20 rounded-xl px-3 py-2 text-sm">
              <FileText size={13} className="text-blue-600 dark:text-blue-400" />
              <span className="text-foreground/80">Purchase Order terhubung:</span>
              <span className="text-blue-600 dark:text-blue-400 font-semibold">{pr.linked_po_number}</span>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><div className="text-xs text-muted-foreground">Tipe</div><div className="text-foreground">{TYPE_LABELS[pr.request_type] || pr.request_type}</div></div>
            <div><div className="text-xs text-muted-foreground">Departemen</div><div className="text-foreground">{pr.department || '-'}</div></div>
            <div><div className="text-xs text-muted-foreground">Total Estimasi</div><div className="text-emerald-600 dark:text-emerald-400 font-semibold">{fmtRp(pr.total_estimated)}</div></div>
          </div>

          {/* Rantai persetujuan — jumlah tahap mengikuti nilai PR */}
          {Array.isArray(pr.chain) && pr.chain.length > 0 && (
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                  <Layers size={13} /> Rantai Persetujuan
                </span>
                <span className="text-[11px] text-muted-foreground" data-testid="pr-chain-summary">
                  {pr.total_stages} tahap untuk nilai {fmtRp(pr.total_estimated)}
                  {pr.status === 'draft' ? ' (perkiraan — dibekukan saat diajukan)' : ''}
                </span>
              </div>
              <ApprovalStepper chain={pr.chain} />
              {pr.stage && (
                <p className="mt-2 text-[11px] text-muted-foreground" data-testid="pr-next-approver">
                  Berikutnya setelah tahap ini: {pr.next_approver_label}
                </p>
              )}
            </div>
          )}

          {pr.justification && (
            <div className="bg-foreground/5 border border-foreground/10 rounded-xl p-3">
              <div className="text-xs text-muted-foreground mb-1">Justifikasi</div>
              <p className="text-sm text-foreground/80">{pr.justification}</p>
            </div>
          )}

          {pr.status === 'rejected' && pr.rejection_reason && (
            <div className="rounded-xl border border-red-300 bg-red-50 p-3 dark:border-red-500/30 dark:bg-red-500/10"
                 data-testid="pr-rejection-reason">
              <div className="mb-1 text-xs font-semibold text-red-700 dark:text-red-400">Alasan Penolakan</div>
              <p className="text-sm text-red-800 dark:text-red-300">{pr.rejection_reason}</p>
            </div>
          )}

          <div>
            <div className="text-sm font-semibold text-foreground mb-2">Items ({(pr.items || []).length})</div>
            <div className="space-y-1">
              {(pr.items || []).map((it, i) => (
                <div key={i} className="flex items-center justify-between bg-foreground/5 rounded-lg px-3 py-2 text-sm">
                  <div>
                    <span className="text-foreground">{it.name}</span>
                    {it.specification && <span className="text-muted-foreground/60 dark:text-zinc-500 text-xs ml-2">{it.specification}</span>}
                  </div>
                  <div className="text-right">
                    <span className="text-foreground/80">{it.qty} {it.unit}</span>
                    <span className="text-emerald-600 dark:text-emerald-400 ml-3">{fmtRp(it.total_price)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Riwayat keputusan */}
          <div>
            <div className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <History size={13} /> Riwayat
            </div>
            {loadTL ? (
              <p className="text-xs text-muted-foreground">Memuat riwayat…</p>
            ) : timeline.length === 0 ? (
              <p className="text-xs text-muted-foreground">Belum ada langkah — permintaan masih draft.</p>
            ) : (
              <div className="space-y-1" data-testid="pr-timeline">
                {timeline.map((t, i) => (
                  <div key={i} className="flex flex-wrap gap-2 text-xs">
                    <span className="text-muted-foreground/60 dark:text-zinc-500 w-32 flex-shrink-0">{fmtDT(t.timestamp)}</span>
                    <span className="text-foreground/80">{t.action_label || t.action}</span>
                    {t.actor_name && <span className="text-muted-foreground/60 dark:text-zinc-500">— {t.actor_name}</span>}
                    {t.override && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-300">
                        <ShieldAlert size={9} /> override
                      </span>
                    )}
                    {t.comment && <span className="text-muted-foreground italic">“{t.comment}”</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <GateNotice item={pr} />

          {hasActions && (
            <div className="border-t border-foreground/10 pt-4 space-y-2">
              {(canApprove || canReject) && (
                <textarea
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:outline-none"
                  rows={2}
                  autoFocus={focusReject}
                  placeholder={canReject ? 'Catatan persetujuan / alasan penolakan (wajib bila menolak)' : 'Catatan (opsional)'}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  data-testid="pr-decision-note"
                />
              )}
              <div className="flex gap-2 justify-end flex-wrap">
                {canSubmit && (
                  <button onClick={() => doAction('submit')} disabled={!!acting}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-xl disabled:opacity-50"
                    data-testid="btn-submit-pr">
                    <Send size={13} /> {acting === 'submit' ? 'Mengirim...' : 'Ajukan ke Approver'}
                  </button>
                )}
                {canReject && (
                  <button onClick={() => doAction('reject')} disabled={!!acting}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-red-600/20 hover:bg-red-600/40 text-red-700 dark:text-red-400 border border-red-300 dark:border-red-500/20 rounded-xl disabled:opacity-50"
                    data-testid="btn-reject-pr">
                    <XCircle size={13} /> {acting === 'reject' ? 'Menolak...' : 'Tolak'}
                  </button>
                )}
                {canApprove && (
                  <button onClick={() => doAction('approve')} disabled={!!acting}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl disabled:opacity-50"
                    data-testid="btn-approve-pr">
                    <CheckCircle2 size={13} />
                    {acting === 'approve' ? 'Menyetujui...' : `Setujui — ${pr.stage_label || 'tahap ini'}`}
                  </button>
                )}
                {canCreatePO && (
                  <button onClick={() => setShowCreatePO(true)} disabled={!!acting}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl disabled:opacity-50"
                    data-testid="btn-create-po-from-pr">
                    <FileText size={13} /> Buat Purchase Order
                  </button>
                )}
                {canComplete && (
                  <button onClick={() => doAction('complete')} disabled={!!acting}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-xl disabled:opacity-50"
                    data-testid="btn-complete-pr">
                    <CheckCircle2 size={13} /> {acting === 'complete' ? 'Menyelesaikan...' : 'Tandai Selesai'}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {showCreatePO && (
        <CreatePOFromPRModal
          pr={pr}
          token={token}
          onClose={() => setShowCreatePO(false)}
          onCreated={async () => {
            // Muat ulang detailnya: tanpa ini dialog tetap menampilkan data lama
            // (nomor PO tidak muncul dan tombol "Buat Purchase Order" masih ada,
            // padahal PO-nya sudah terbentuk) — bug staleness yang terlihat saat
            // verifikasi UI 2026-08-07.
            setShowCreatePO(false);
            setOkMsg('Purchase Order berhasil dibuat dari permintaan ini.');
            await reload();
            onAction({});
          }}
        />
      )}
    </div>
  );
}

// ── Kartu PR (dipakai daftar & kotak persetujuan) ────────────────────────────
function PRCard({ it, onOpen, onQuickApprove, quickBusy, showChain = true }) {
  return (
    <div
      onClick={() => onOpen(it)}
      className="bg-foreground/5 border border-foreground/10 hover:border-foreground/20 rounded-xl p-4 cursor-pointer transition-all group"
      data-testid={`pr-card-${it.request_number}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={it.status} />
            <PriorityBadge priority={it.priority} />
            <span className="text-[10px] text-muted-foreground/60 dark:text-zinc-500">{it.request_number}</span>
            {it.department && (
              <span className="text-[10px] text-muted-foreground dark:text-zinc-500 bg-muted px-1.5 py-0.5 rounded">
                {it.department}
              </span>
            )}
            {it.kind === 'acc_pr' && (
              <span className="inline-flex items-center gap-1 rounded-full border border-violet-300 bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700 dark:border-violet-400/30 dark:bg-violet-400/10 dark:text-violet-400">
                <Package size={9} /> Aksesoris
              </span>
            )}
            {/* 2026-08-07 — Purchase Order ikut ke kotak persetujuan gabungan.
                PO adalah KOMITMEN UANG ke supplier, jadi harus mudah dikenali. */}
            {it.kind === 'po' && (
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-300 bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-700 dark:border-sky-400/30 dark:bg-sky-400/10 dark:text-sky-400">
                <ShoppingCart size={9} /> Purchase Order
              </span>
            )}
            {it.exceeds_pr_value && (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-300 bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-400">
                Melebihi nilai PR
              </span>
            )}
            {it.can_approve && (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-400">
                <CheckCircle2 size={9} /> Perlu keputusan Anda
              </span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-foreground mt-1.5 leading-snug">{it.title}</h3>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground/60 dark:text-zinc-500 flex-wrap">
            <span>{it.requested_by_name || 'Admin'}</span>
            <span>{it.created_at ? new Date(it.created_at).toLocaleDateString('id-ID') : '-'}</span>
            <span className="text-emerald-600 dark:text-emerald-400 font-medium">{fmtRp(it.total_estimated)}</span>
            <span>{(it.items || []).length} item</span>
          </div>
          {showChain && Array.isArray(it.chain) && it.chain.length > 0 && (
            <div className="mt-2">
              <ApprovalStepper chain={it.chain} compact />
            </div>
          )}
          {!it.can_approve && it.blocked_reason && it.stage && (
            <p className="mt-1.5 text-[11px] text-muted-foreground" data-testid={`pr-blocked-${it.request_number}`}>
              {it.blocked_reason}
            </p>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          {onQuickApprove && it.can_approve && (
            <button
              onClick={(e) => { e.stopPropagation(); onQuickApprove(it); }}
              disabled={quickBusy === it.id}
              className="flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              data-testid={`btn-quick-approve-${it.request_number}`}
            >
              {quickBusy === it.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Setujui
            </button>
          )}
          <ChevronRight size={16} className="text-muted-foreground/60 group-hover:text-muted-foreground mt-1" />
        </div>
      </div>
    </div>
  );
}

// ── Main Module ───────────────────────────────────────────────────────────────
export default function ProcurementRequestModule({ token, user, onNavigate }) {
  const [tab, setTab] = useState('all');            // all | inbox | mine
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [quickBusy, setQuickBusy] = useState('');
  const [banner, setBanner] = useState(null);       // {type, text}
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRows, setTotalRows] = useState(0);
  // F13-B (sesi #12) — PR adalah KOMITMEN UANG. Sebelum ini layarnya kartu
  // saja: tidak ada kolom nilai yang bisa diurutkan, tidak ada unduhan.
  // "PR mana yang menunggu persetujuan saya, urut dari nilai terbesar?" hanya
  // bisa dijawab dengan menggulir. Pengurutan sengaja dikerjakan SERVER
  // (`sort_by`/`sort_dir`) supaya urutannya berlaku untuk SELURUH data, bukan
  // 15 baris yang kebetulan sedang terbuka.
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(PR_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem(PR_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [sort, setSort] = useState({ key: 'created_at', dir: 'desc' });
  const toggleSort = (key) => {
    setPage(1);
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'desc' }));
  };

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  // Sekali saja: kalau approver punya pekerjaan menunggu, buka langsung di
  // kotak persetujuan (itu yang ia cari saat masuk lewat lencana/notifikasi).
  // Begitu ia memilih tab sendiri, pilihannya tidak diganggu lagi.
  const tabTouched = useRef(false);
  const autoTabDone = useRef(false);

  const loadInbox = useCallback(async () => {
    setInboxLoading(true);
    try {
      const r = await axios.get(`${API}/api/procurement/inbox`, { headers });
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setInbox(list);
      if (!autoTabDone.current && !tabTouched.current && list.length > 0) {
        autoTabDone.current = true;
        setTab('inbox');
      }
    } catch {
      setInbox([]);
    } finally {
      setInboxLoading(false);
    }
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit: 15, sort_by: sort.key, sort_dir: sort.dir };
      if (filterStatus) params.status = filterStatus;
      if (filterPriority) params.priority = filterPriority;
      if (search) params.search = search;
      if (tab === 'mine') params.my_only = true;
      const [listRes, dashRes] = await Promise.all([
        axios.get(`${API}/api/procurement/requests`, { headers, params }),
        axios.get(`${API}/api/procurement/dashboard`, { headers }),
      ]);
      setItems(listRes.data?.items || []);
      setTotalPages(listRes.data?.pagination?.total_pages || 1);
      setTotalRows(listRes.data?.pagination?.total ?? (listRes.data?.items || []).length);
      setStats(dashRes.data?.summary || null);
    } catch (e) {
      console.error('Procurement load error', e);
    } finally {
      setLoading(false);
    }
  }, [headers, page, filterStatus, filterPriority, search, tab, sort]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadInbox(); }, [loadInbox]);

  const refreshAll = useCallback(() => { load(); loadInbox(); }, [load, loadInbox]);

  const quickApprove = async (it) => {
    setQuickBusy(it.id); setBanner(null);
    // Basis endpoint dari server: PR pengadaan dan Request Pembelian Aksesoris
    // memakai mesin persetujuan yang sama tapi endpoint-nya berbeda.
    const apiBase = it.api_base || '/api/procurement/requests';
    try {
      const res = await axios.post(
        `${API}${apiBase}/${it.id}/approve`,
        { comment: '' },
        { headers },
      );
      const d = res.data || {};
      setBanner({
        type: 'ok',
        text: d.next_stage_label
          ? `${it.request_number} disetujui — lanjut ke ${d.next_stage_label}.`
          : `${it.request_number} disetujui penuh — siap dijadikan Purchase Order.`,
      });
      refreshAll();
    } catch (e) {
      setBanner({ type: 'err', text: e.response?.data?.detail || `Gagal menyetujui ${it.request_number}` });
    } finally {
      setQuickBusy('');
    }
  };

  const inboxValue = inbox.reduce((s, i) => s + Number(i.total_estimated || 0), 0);

  // Yang diunduh = yang TERLIHAT. Karena halaman diambil dari server (dan sudah
  // DIURUTKAN server), baris CSV adalah persis baris di layar — bukan kueri
  // ulang yang bisa menghasilkan berkas berbeda dari layarnya.
  const prRows = items || [];
  const csvRows = prRows.map((it) => [
    it.request_number, it.title, TYPE_LABELS[it.request_type] || it.request_type,
    it.department || '', PRIORITY_CFG[it.priority]?.label || it.priority,
    STATUS_CFG[it.status]?.label || it.status, it.total_estimated ?? 0,
    it.requested_by_name || '', it.needed_by ? String(it.needed_by).slice(0, 10) : '',
    String(it.created_at || '').slice(0, 10), it.next_approver_label || '',
    it.linked_po_number || '',
  ]);

  // Dipakai langsung (bukan dibungkus komponen dalam-render) — lihat komentar
  // pada `TabButton` di atas berkas ini.
  const selectTab = (v) => { tabTouched.current = true; setTab(v); setPage(1); };

  return (
    <div className="p-4 space-y-4 max-w-7xl mx-auto" data-testid="procurement-module">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <ShoppingCart size={20} className="text-blue-600 dark:text-blue-400" /> Permintaan Pengadaan
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Ajukan, setujui, dan pantau permintaan pembelian (PR) — jumlah tahap persetujuan
            mengikuti nilai permintaan
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={refreshAll} className="p-2 text-muted-foreground hover:text-foreground rounded-lg hover:bg-foreground/5"
                  data-testid="pr-refresh">
            <RefreshCw size={16} className={loading || inboxLoading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-xl shadow-sm"
            data-testid="btn-open-create-pr">
            <Plus size={14} /> Buat PR
          </button>
        </div>
      </div>

      {banner && (
        <div className={`flex items-start gap-2 rounded-xl border px-3 py-2 ${
          banner.type === 'ok'
            ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10'
            : 'border-red-300 bg-red-50 dark:border-red-500/30 dark:bg-red-500/10'
        }`} data-testid="pr-banner">
          {banner.type === 'ok'
            ? <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0 text-emerald-600 dark:text-emerald-400" />
            : <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-red-600 dark:text-red-400" />}
          <p className={`text-xs ${banner.type === 'ok' ? 'text-emerald-800 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}`}>
            {banner.text}
          </p>
          <button onClick={() => setBanner(null)} className="ml-auto text-xs text-muted-foreground hover:text-foreground">✕</button>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Total PR" value={stats.total} />
          <StatCard label="Menunggu Keputusan Saya" value={stats.my_pending_approval}
                    color="text-amber-700 dark:text-amber-400" sub="hanya yang benar-benar hak Anda" />
          <StatCard label="Disetujui" value={stats.approved} color="text-emerald-600 dark:text-emerald-400" />
          <StatCard label="Nilai Disetujui" value={fmtRp(stats.total_value_approved_this_month)}
                    color="text-sky-600 dark:text-sky-400" sub="bulan ini" />
        </div>
      )}

      {/* Tabs — kotak persetujuan ada DI DALAM menu ini (permintaan owner) */}
      <div className="flex items-center gap-1 border-b border-foreground/10 overflow-x-auto" data-testid="pr-tabs">
        <TabButton id="all" label="Semua Permintaan" testId="pr-tab-all"
          active={tab === 'all'} onSelect={selectTab} />
        <TabButton id="inbox" label="Menunggu Persetujuan Saya" count={inbox.length}
          testId="pr-tab-inbox" active={tab === 'inbox'} onSelect={selectTab} />
        <TabButton id="mine" label="Permintaan Saya" count={stats?.my_requests}
          testId="pr-tab-mine" active={tab === 'mine'} onSelect={selectTab} />
      </div>

      {tab === 'inbox' ? (
        <div className="space-y-3" data-testid="pr-inbox-panel">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-foreground/10 bg-foreground/5 px-3 py-2">
            <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <Inbox size={14} className="text-amber-600 dark:text-amber-400" />
              {inbox.length} permintaan menunggu keputusan Anda
            </span>
            <span className="text-xs text-muted-foreground">
              Total nilai: <span className="font-semibold text-emerald-600 dark:text-emerald-400">{fmtRp(inboxValue)}</span>
            </span>
          </div>

          {inboxLoading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground/60">
              <RefreshCw size={20} className="animate-spin mr-2" /> Memuat kotak persetujuan...
            </div>
          ) : inbox.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center" data-testid="pr-inbox-empty">
              <Inbox size={36} className="mb-3 opacity-40 text-muted-foreground" />
              <p className="text-sm text-foreground/70">Tidak ada permintaan yang menunggu keputusan Anda</p>
              <p className="mt-1 max-w-md text-xs text-muted-foreground">
                Kotak ini menggabungkan Permintaan Pengadaan dan Request Pembelian Aksesoris.
                Permintaan muncul hanya saat memang giliran Anda: tahap yang aktif cocok dengan
                peran Anda, bukan permintaan buatan Anda sendiri, dan Anda belum menyetujui
                permintaan itu di tahap sebelumnya.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {inbox.map((it) => (
                <PRCard key={it.id} it={it} onOpen={setDetail}
                        onQuickApprove={quickApprove} quickBusy={quickBusy} />
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* RC-FLOW-UX: onward — PR → Purchase Order → GRN. */}
          <OnwardCTA
            onNavigate={onNavigate}
            title="Langkah Berikutnya"
            actions={[
              { module: 'proc-purchase-orders', label: 'Buat Purchase Order', icon: ShoppingCart, primary: true, hint: 'PR disetujui → terbitkan PO ke supplier' },
              { module: 'wh-receiving', label: 'Penerimaan Barang (GRN)', hint: 'Setelah barang datang, catat penerimaan (Portal Gudang)' },
            ]}
          />

          {/* Filters */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[180px]">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/60 dark:text-zinc-500" />
              <input
                className="w-full bg-foreground/5 border border-foreground/10 rounded-lg pl-8 pr-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:outline-none"
                placeholder="Cari judul atau nomor PR..."
                value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                data-testid="pr-search"
              />
            </div>
            <select
              className="bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none"
              value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
              data-testid="pr-filter-status"
            >
              <option value="">Semua Status</option>
              <option value="draft">Draft</option>
              <option value="submitted">Menunggu Persetujuan Dept</option>
              <option value="dept_approved">Menunggu Persetujuan Keuangan</option>
              <option value="finance_approved">Menunggu Persetujuan Final</option>
              <option value="approved">Disetujui</option>
              <option value="in_procurement">Sedang Pengadaan</option>
              <option value="rejected">Ditolak</option>
              <option value="completed">Selesai</option>
              <option value="cancelled">Dibatalkan</option>
            </select>
            <SmartNativeSelect
              className="bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none"
              value={filterPriority} onChange={(e) => { setFilterPriority(e.target.value); setPage(1); }}
            >
              <option value="">Semua Prioritas</option>
              {Object.entries(PRIORITY_CFG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </SmartNativeSelect>
            <div className="inline-flex rounded-lg border border-foreground/10 overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="pr-view-table"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <Table2 size={12} /> Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="pr-view-grid"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <LayoutGrid size={12} /> Kartu
              </button>
            </div>
            <ExportCsvButton filename="permintaan-pengadaan" testId="pr-export-csv"
              head={PR_CSV_HEAD} rows={csvRows}
              note={`halaman ${page}/${totalPages} · Rp ${(items.reduce((s, r) => s + Number(r.total_estimated || 0), 0)).toLocaleString('id-ID')}`} />
          </div>

          {/* List */}
          {loading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground/60 dark:text-zinc-500">
              <RefreshCw size={20} className="animate-spin mr-2" /> Memuat...
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground/60 dark:text-zinc-500">
              <ShoppingCart size={36} className="mb-3 opacity-40" />
              <p className="text-sm">
                {tab === 'mine' ? 'Anda belum pernah membuat permintaan pengadaan' : 'Belum ada permintaan pengadaan'}
              </p>
              <button onClick={() => setShowCreate(true)}
                className="mt-4 flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600/20 hover:bg-blue-600/40 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-500/20 rounded-xl">
                <Plus size={13} /> Buat Permintaan Pertama
              </button>
            </div>
          ) : view === 'table' ? (
            <div className="rounded-xl border border-foreground/10 bg-card">
              <div className="overflow-x-auto">
                <table className="w-full text-xs" data-testid="pr-table">
                  <thead className="bg-muted/50">
                    <tr className="text-left">
                      {[['request_number', 'No. PR'], ['title', 'Judul'],
                        ['request_type', 'Jenis'], ['department', 'Departemen'],
                        ['priority', 'Prioritas'], ['status', 'Status'],
                        ['total_estimated', 'Nilai (Rp)'],
                        ['requested_by_name', 'Pemohon'],
                        ['needed_by', 'Dibutuhkan'],
                        ['created_at', 'Dibuat']].map(([k, label]) => (
                        <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                          <button type="button" onClick={() => toggleSort(k)}
                            data-testid={`pr-sort-${k}`}
                            className="inline-flex items-center gap-1 hover:text-primary">
                            {label}
                            <ArrowUpDown size={10}
                              className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                          </button>
                        </th>
                      ))}
                      <th className="px-2.5 py-2 font-semibold text-right">Persetujuan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id}
                          className="border-t border-foreground/10 hover:bg-muted/40 cursor-pointer"
                          onClick={() => setDetail(it)}
                          data-testid={`pr-row-${it.request_number}`}>
                        <td className="px-2.5 py-2 font-mono whitespace-nowrap">{it.request_number}</td>
                        <td className="px-2.5 py-2 max-w-[240px] truncate" title={it.title}>{it.title}</td>
                        <td className="px-2.5 py-2">{TYPE_LABELS[it.request_type] || it.request_type}</td>
                        <td className="px-2.5 py-2">{it.department || '—'}</td>
                        <td className="px-2.5 py-2">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${PRIORITY_CFG[it.priority]?.color || ''}`}>
                            {PRIORITY_CFG[it.priority]?.label || it.priority}
                          </span>
                        </td>
                        <td className="px-2.5 py-2">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium border whitespace-nowrap ${STATUS_CFG[it.status]?.color || ''}`}>
                            {STATUS_CFG[it.status]?.label || it.status}
                          </span>
                        </td>
                        <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">
                          {formatRupiah(it.total_estimated || 0)}
                        </td>
                        <td className="px-2.5 py-2">{it.requested_by_name || '—'}</td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{it.needed_by ? String(it.needed_by).slice(0, 10) : '—'}</td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{String(it.created_at || '').slice(0, 10)}</td>
                        <td className="px-2.5 py-2 text-right whitespace-nowrap">
                          {/* Kolom ini menjawab "siapa yang ditunggu" — pertanyaan
                              yang paling sering ditanyakan tentang PR yang mandek. */}
                          {it.can_approve ? (
                            <button
                              onClick={(e) => { e.stopPropagation(); quickApprove(it); }}
                              disabled={quickBusy === it.id}
                              data-testid={`pr-quick-approve-${it.request_number}`}
                              className="h-7 px-2.5 rounded-lg bg-emerald-600 text-white text-[11px] font-medium disabled:opacity-50">
                              {quickBusy === it.id ? '...' : 'Setujui'}
                            </button>
                          ) : (
                            <span className="text-muted-foreground text-[11px]">
                              {it.next_approver_label || '—'}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-3 py-2 text-[11px] text-muted-foreground border-t border-foreground/10">
                Menampilkan {items.length} dari {totalRows} permintaan · urut{' '}
                <b>{sort.key}</b> {sort.dir === 'desc' ? 'terbesar dulu' : 'terkecil dulu'}{' '}
                (diurutkan server, berlaku untuk seluruh data — bukan hanya halaman ini)
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((it) => (
                <PRCard key={it.id} it={it} onOpen={setDetail}
                        onQuickApprove={quickApprove} quickBusy={quickBusy} />
              ))}
            </div>
          )}

          {/* Pagination — SATU kontrol paginasi yang sama dengan layar lain
              (`PaginationLite`). Halaman diambil dari server, jadi `total` dan
              `totalPages` datang dari server juga: label "Menampilkan a–b dari
              N" menyebut jumlah SEBENARNYA, bukan jumlah baris yang kebetulan
              sedang dirender. */}
          <PaginationLite
            page={page}
            totalPages={totalPages}
            total={totalRows}
            pageSize={15}
            onPageChange={setPage}
          />
        </>
      )}

      {/* Modals */}
      {showCreate && (
        <CreatePRModal token={token} onClose={() => setShowCreate(false)}
                       onCreated={() => { setShowCreate(false); refreshAll(); }} />
      )}
      {detail && (
        <DetailModal
          item={detail}
          token={token}
          onClose={() => { setDetail(null); refreshAll(); }}
          onAction={() => refreshAll()}
        />
      )}
    </div>
  );
}
