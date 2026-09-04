/**
 * Return & Refund — Portal Gudang (Blueprint §3.7)
 *
 * Tipe 1: Expedition Return   — paket kembali dari ekspedisi
 * Tipe 2: Customer Refund     — customer request refund marketplace
 *
 * Workflow: Pending → Received (unboxing) → Inspected → Resolved
 *
 * Tabs:
 *   Dashboard  — stats + action-needed list
 *   Tipe 1     — expedition_return view
 *   Tipe 2     — customer_refund view
 *   Semua      — all returns tabel
 */

import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  Package, Plus, Search, X, RefreshCw, Eye, CheckCircle,
  Clock, AlertTriangle, Truck, RotateCcw, ChevronRight,
  ChevronDown, FileText, ArrowRight, PackageOpen, CheckSquare,
  XCircle, ShieldAlert, Star, Send, Trash2, MoreVertical,
  ClipboardCheck, PackageCheck, DownloadCloud, Link2, Store, Zap, MapPin
} from 'lucide-react';
import OnwardCTA from './OnwardCTA';
import { formatRupiah } from '@/lib/format';
// F15-B — kelas Tailwind tidak boleh dirakit saat berjalan; lihat lib/tone.js
import { tone } from '@/lib/tone';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';
// W4 (sesi #29) — barang retur WAJIB dipilih dari master produk jadi (INV-F14).
import { FGMaterialSelect } from './masters/MasterSelects';

const API = process.env.REACT_APP_BACKEND_URL || '';

const CHANNELS   = ['Shopee', 'Tokopedia', 'TikTok Shop', 'Lazada', 'Instagram', 'WhatsApp', 'Lainnya'];
// W4 — kondisi 'Rusak' ditambah supaya pilihan pemilik (Baik/Rusak) ada apa adanya.
const CONDITIONS = ['Baik', 'Rusak', 'Rusak Ringan', 'Rusak Berat', 'Tidak Layak Jual'];
const CAUSES     = ['Kesalahan Gudang', 'Kesalahan Customer', 'Kesalahan Ekspedisi', 'Lainnya'];
const ACTIONS    = ['Restock ke Gudang', 'Karantina (Rusak)', 'Reshipment', 'Appeal Platform', 'Dibuang / Dispose', 'Donasi'];
const APPEAL_STATUSES = ['Pending', 'Success', 'Fail'];
// Kondisi yang boleh masuk stok JUAL. Sisanya ditahan di karantina (K-6a).
const SELLABLE_CONDITIONS = ['Baik'];

const TYPE_LABELS = {
  expedition_return: 'Tipe 1 — Ekspedisi',
  customer_refund:   'Tipe 2 — Customer',
};
const TYPE_COLORS = {
  expedition_return: 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-500/10',
  customer_refund:   'text-violet-600 dark:text-violet-400 bg-violet-100 dark:bg-violet-500/10',
};
const STATUS_COLORS = {
  Pending:   'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10',
  Received:  'text-sky-600 dark:text-sky-400 bg-sky-100 dark:bg-sky-500/10',
  Inspected: 'text-violet-600 dark:text-violet-400 bg-violet-100 dark:bg-violet-500/10',
  Resolved:  'text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10',
  Cancelled: 'text-muted-foreground bg-muted dark:bg-slate-500/10',
};
const CONDITION_COLORS = {
  'Baik':              'text-emerald-600 dark:text-emerald-400',
  'Rusak':             'text-red-700 dark:text-red-400',
  'Rusak Ringan':      'text-amber-700 dark:text-amber-400',
  'Rusak Berat':       'text-orange-600 dark:text-orange-400',
  'Tidak Layak Jual':  'text-red-700 dark:text-red-400',
};
const CAUSE_COLORS = {
  'Kesalahan Gudang':     'text-red-700 dark:text-red-400',
  'Kesalahan Customer':   'text-amber-700 dark:text-amber-400',
  'Kesalahan Ekspedisi':  'text-orange-600 dark:text-orange-400',
  'Lainnya':              'text-muted-foreground',
};

function Badge({ label, colorClass }) {
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colorClass || 'text-muted-foreground bg-secondary'}`}>{label}</span>;
}

// ─── W4 — LENCANA "APA YANG TERJADI PADA STOK" ────────────────────────────────
// Pemilik harus bisa melihat, tanpa membuka detail, apakah barang retur sudah
// benar-benar masuk stok (dan stok mana: jual atau karantina). Sebelum ini layar
// hanya menampilkan status alur kerja, sehingga "Resolved" terlihat sama saja
// walau stoknya tidak pernah bergerak.
function StockBadge({ ret }) {
  if (ret.restocked) {
    const sellable = ret.stock_effect === 'sellable';
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium inline-flex items-center gap-1 ${
        sellable ? 'text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10'
                 : 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10'}`}
        data-testid={`stock-badge-${ret.id}`}>
        <Package className="w-3 h-3" />
        {sellable ? `+${ret.restock_qty} stok jual` : `+${ret.restock_qty} karantina`}
      </span>
    );
  }
  if (ret.link_status && ret.link_status !== 'linked') {
    return (
      <span className="px-2 py-0.5 rounded-full text-xs font-medium text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 inline-flex items-center gap-1"
        data-testid={`stock-badge-${ret.id}`}>
        <Link2 className="w-3 h-3" /> belum tertaut master
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-full text-xs font-medium text-muted-foreground bg-secondary inline-flex items-center gap-1"
      data-testid={`stock-badge-${ret.id}`}>
      <Clock className="w-3 h-3" /> belum masuk stok
    </span>
  );
}

function SourceBadge({ ret }) {
  const fromMkt = !!ret.source_marketing_return_id;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium inline-flex items-center gap-1 ${
      fromMkt ? 'text-sky-600 dark:text-sky-400 bg-sky-100 dark:bg-sky-500/10'
              : 'text-muted-foreground bg-secondary'}`}
      data-testid={`source-badge-${ret.id}`}>
      {fromMkt ? <><Store className="w-3 h-3" /> Marketing</> : <>Manual</>}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso?.slice(0, 16) || '-'; }
}
function fmtDateShort(iso) {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return iso?.slice(0, 10) || '-'; }
}
const fmtCurrency = formatRupiah;

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

// ─── WORKFLOW PROGRESS BAR ────────────────────────────────────────────────────
const STEPS = ['Pending', 'Received', 'Inspected', 'Resolved'];
function WorkflowBar({ status }) {
  const idx = STEPS.indexOf(status);
  if (status === 'Cancelled') return <span className="text-xs text-muted-foreground">Dibatalkan</span>;
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((s, i) => (
        <div key={s} className="flex items-center gap-1">
          <div className={`w-2 h-2 rounded-full ${i <= idx ? 'bg-primary' : 'bg-foreground/10'}`} />
          {i < STEPS.length - 1 && <div className={`w-6 h-px ${i < idx ? 'bg-primary' : 'bg-foreground/10'}`} />}
        </div>
      ))}
      <span className="text-xs ml-1 text-muted-foreground">{status}</span>
    </div>
  );
}

// ─── RETURN CARD (list row) ───────────────────────────────────────────────────
function ReturnRow({ ret, onView, onDelete, onQuickRestock }) {
  const canQuick = !ret.restocked && ret.status !== 'Cancelled'
    && (ret.material_id || ret.fg_material_id);
  return (
    <tr className="border-b border-border hover:bg-foreground/[0.02] cursor-pointer" onClick={() => onView(ret)} data-testid={`ret-row-${ret.id}`}>
      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{ret.return_code}</td>
      <td className="px-4 py-3"><SourceBadge ret={ret} /></td>
      <td className="px-4 py-3 font-medium text-sm">{ret.order_number || ret.resi_number || '-'}</td>
      <td className="px-4 py-3 text-sm">
        <div className="font-medium">{ret.product_name || '-'}</div>
        <div className="text-xs text-muted-foreground font-mono">{ret.sku_code || '—'}</div>
      </td>
      <td className="px-4 py-3 text-sm text-center">{ret.qty || 0}</td>
      <td className="px-4 py-3"><Badge label={ret.status} colorClass={STATUS_COLORS[ret.status]} /></td>
      <td className="px-4 py-3"><StockBadge ret={ret} /></td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{fmtDateShort(ret.created_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1">
          {canQuick && onQuickRestock && (
            <button onClick={e => { e.stopPropagation(); onQuickRestock(ret); }}
              className="px-2 py-1 rounded-lg text-xs font-medium bg-emerald-600/10 border border-emerald-400 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-600/20 inline-flex items-center gap-1"
              data-testid={`quick-restock-${ret.id}`} title="Terima & masukkan ke stok">
              <Zap className="w-3 h-3" /> Terima &amp; Restock
            </button>
          )}
          <button onClick={e => { e.stopPropagation(); onView(ret); }} className="p-1 hover:bg-foreground/5 rounded" data-testid={`view-ret-${ret.id}`}>
            <Eye className="w-4 h-4 text-muted-foreground" />
          </button>
          {ret.status === 'Pending' && !ret.restocked && (
            <button onClick={e => { e.stopPropagation(); onDelete(ret); }} className="p-1 hover:bg-red-100 dark:bg-red-500/10 rounded" data-testid={`del-ret-${ret.id}`}>
              <Trash2 className="w-4 h-4 text-red-700 dark:text-red-400" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── CREATE FORM MODAL ────────────────────────────────────────────────────────
function CreateModal({ onClose, onSaved, token, defaultType }) {
  const [form, setForm] = useState({
    return_type: defaultType || 'expedition_return',
    order_number: '', resi_number: '', channel: '',
    customer_name: '', customer_contact: '',
    material_id: '', sku_code: '', product_name: '', qty: 1,
    order_value: 0, initial_reason: '', notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  // SESI #19 — kebijakan penomoran Retur Gudang (Otomatis/Manual).
  const numPolicy = useDocNumberPolicy('wh_returns.return_code', token);
  const [returnCode, setReturnCode] = useState('');

  const submit = async () => {
    if (!form.order_number && !form.resi_number) { setErr('Nomor order atau resi wajib diisi'); return; }
    if (!form.material_id) { setErr('Barang jadi wajib dipilih dari master — tanpa itu stok tidak bisa bertambah.'); return; }
    if (numPolicy?.mode === 'manual' && !returnCode.trim()) {
      setErr(`Nomor retur wajib diisi (pola ${numPolicy.format}).`); return;
    }
    setSaving(true); setErr('');
    try {
      const ret = await api('POST', '/api/wh/returns', token, {
        ...form, ...docNumberPayload(numPolicy, 'return_code', returnCode),
      });
      onSaved(ret);
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-foreground/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-bold mb-4">Catat Return Baru</h3>
        <div className="space-y-3">
          <DocNumberField
            policy={numPolicy}
            value={returnCode}
            onChange={setReturnCode}
            label="Nomor Retur"
            testId="whret-number"
          />
          {/* Type */}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Tipe Return *</label>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(TYPE_LABELS).map(([v, l]) => (
                <button key={v} onClick={() => setForm({ ...form, return_type: v })}
                  className={`py-2 px-3 rounded-lg border text-sm transition ${form.return_type === v ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-foreground/5 text-muted-foreground'}`}
                  data-testid={`type-btn-${v}`}>
                  {l}
                </button>
              ))}
            </div>
          </div>

          {/* Info identifikasi */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">No. Order</label>
              <input value={form.order_number} onChange={e => setForm({ ...form, order_number: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="SPX-00001" data-testid="ret-order-number" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">No. Resi</label>
              <input value={form.resi_number} onChange={e => setForm({ ...form, resi_number: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="JNE-123456" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Channel</label>
              <select value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="ret-channel">
                <option value="">Pilih...</option>
                {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Nama Customer</label>
              <input value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="Nama customer" />
            </div>
          </div>
          {/* W4 — BARANG DARI MASTER (bukan ketikan). Sebelumnya kolom ini teks
              bebas "SKU / Kode Produk"; karena tidak pernah cocok dengan master,
              tombol Restock tidak pernah menemukan barangnya ⇒ stok tak bergerak. */}
          <div className="grid grid-cols-1 gap-3">
            <FGMaterialSelect
              value={form.material_id}
              onChange={(v) => setForm({ ...form, material_id: v })}
              label="Barang Jadi yang Kembali *"
              hint="Wajib dari Master Produk Jadi — inilah yang membuat stok bisa bertambah tepat sasaran."
              testId="ret-material-select"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Qty Retur</label>
              <input type="number" min="1" value={form.qty} onChange={e => setForm({ ...form, qty: +e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="ret-qty" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Nilai Order</label>
              <input type="number" min="0" value={form.order_value} onChange={e => setForm({ ...form, order_value: +e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="0" data-testid="ret-order-value" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Alasan Return (Awal)</label>
            <textarea value={form.initial_reason} onChange={e => setForm({ ...form, initial_reason: e.target.value })} rows="2"
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] resize-none"
              placeholder="Barang tidak sampai / ukuran tidak sesuai / dll..." data-testid="ret-reason" />
          </div>
          {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
        </div>
        <div className="flex gap-3 mt-5">
          <button onClick={onClose} className="flex-1 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5" data-testid="cancel-create-return">Batal</button>
          <button onClick={submit} disabled={saving} className="flex-1 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="save-return-btn">
            {saving ? 'Menyimpan...' : 'Catat Return'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── DETAIL PANEL (full workflow) ─────────────────────────────────────────────
function DetailPanel({ ret, token, onClose, onRefresh, onNavigate }) {
  const [data, setData] = useState(ret);
  const [step, setStep] = useState(null); // 'receive' | 'inspect' | 'resolve' | 'cancel' | 'quick'
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [info, setInfo] = useState('');

  // Aksi cepat dari tabel membuka detail LANGSUNG pada langkah restock.
  useEffect(() => {
    if (ret && ret._openQuick) { setStep('quick'); setForm({}); setErr(''); setInfo(''); }
  }, [ret]);

  const reload = async () => {
    try {
      const d = await api('GET', `/api/wh/returns/${ret.id}`, token);
      setData(d);
    } catch (e) { /* muat ulang gagal — detail yang sudah tampil dibiarkan apa adanya */ }
  };

  const openStep = (s) => { setStep(s); setForm({}); setErr(''); setInfo(''); };

  const doReceive = async () => {
    if (!form.unboxing_condition_notes) { setErr('Catatan unboxing wajib diisi'); return; }
    setSaving(true); setErr('');
    try {
      const d = await api('POST', `/api/wh/returns/${data.id}/receive`, token, form);
      setData(d); setStep(null); onRefresh();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const doInspect = async () => {
    if (!form.item_condition || !form.return_cause) { setErr('Kondisi item dan penyebab wajib diisi'); return; }
    setSaving(true); setErr('');
    try {
      const d = await api('POST', `/api/wh/returns/${data.id}/inspect`, token, form);
      setData(d); setStep(null); onRefresh();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const doResolve = async () => {
    if (!form.action_taken) { setErr('Aksi wajib dipilih'); return; }
    setSaving(true); setErr('');
    try {
      const d = await api('POST', `/api/wh/returns/${data.id}/resolve`, token, form);
      setData(d); setStep(null); onRefresh();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const doCancel = async () => {
    if (!window.confirm('Batalkan return ini?')) return;
    setSaving(true);
    try {
      const d = await api('POST', `/api/wh/returns/${data.id}/cancel`, token, { reason: form.reason || 'Dibatalkan manual' });
      setData(d); setStep(null); onRefresh();
    } catch (e) { alert(e.message); }
    finally { setSaving(false); }
  };

  // ── W4 (sesi #29) — SATU KLIK: terima + inspeksi + selesai + masuk stok ────
  // Kondisi menentukan lokasi: Baik → ZNA-FG (ikut stok jual), Rusak →
  // ZNA-KARANTINA (tidak boleh dijual). Backend yang memutuskan lokasinya
  // supaya tidak ada dua versi aturan.
  const doQuickRestock = async () => {
    setSaving(true); setErr('');
    try {
      const res = await api('POST', `/api/wh/returns/${data.id}/quick-restock`, token, {
        condition: form.condition || 'Baik',
        qty: form.restock_qty ?? data.qty,
        note: form.action_notes || '',
      });
      setData(res.data || data);
      setStep(null);
      setInfo(res.message || 'Stok diperbarui');
      onRefresh();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const doRelink = async () => {
    setSaving(true); setErr('');
    try {
      const res = await api('POST', `/api/wh/returns/${data.id}/relink`, token, {});
      setData(res.data || data);
      setInfo(res.link_status === 'linked'
        ? 'Berhasil ditautkan ke master barang — sekarang bisa di-restock.'
        : (res.reason || 'Masih belum bisa ditautkan.'));
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const linked = !!(data.material_id || data.fg_material_id);

  const isEditable = !['Resolved', 'Cancelled'].includes(data.status);

  return (
    <div className="fixed inset-0 bg-foreground/40 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-t-2xl sm:rounded-2xl shadow-xl w-full sm:max-w-2xl max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="sticky top-0 bg-[var(--card-surface)] border-b border-border px-6 py-4 flex items-start justify-between z-10 rounded-t-2xl">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-bold">{data.return_code}</h3>
              <Badge label={TYPE_LABELS[data.return_type]} colorClass={TYPE_COLORS[data.return_type]} />
              <Badge label={data.status} colorClass={STATUS_COLORS[data.status]} />
            </div>
            <WorkflowBar status={data.status} />
          </div>
          <button onClick={onClose} className="p-2 hover:bg-foreground/5 rounded-lg" data-testid="close-detail" aria-label="Tutup detail retur"><X className="w-5 h-5" /></button>
        </div>

        <div className="px-6 py-4 space-y-5">
          {/* Info Utama */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            {[
              { label: 'No. Order', val: data.order_number || '-' },
              { label: 'No. Resi', val: data.resi_number || '-' },
              { label: 'Channel', val: data.channel || '-' },
              { label: 'Customer', val: data.customer_name || '-' },
              { label: 'Produk', val: data.product_name || data.sku_code || '-' },
              { label: 'Qty', val: `${data.qty} pcs` },
              { label: 'Nilai Order', val: fmtCurrency(data.order_value) },
              { label: 'Dicatat Tgl', val: fmtDateShort(data.created_at) },
              { label: 'Oleh', val: data.created_by },
            ].map(f => (
              <div key={f.label}>
                <div className="text-xs text-muted-foreground">{f.label}</div>
                <div className="font-medium mt-0.5">{f.val}</div>
              </div>
            ))}
          </div>
          {data.initial_reason && (
            <div className="bg-foreground/[0.03] rounded-xl p-3">
              <div className="text-xs text-muted-foreground mb-1">Alasan Awal</div>
              <div className="text-sm">{data.initial_reason}</div>
            </div>
          )}

          {/* ── W4 — TAUTAN MASTER BARANG & EFEK STOK ─────────────────────────
              Blok ini menjawab pertanyaan yang dulu tidak bisa dijawab layar ini:
              "barang apa persisnya yang kembali, dan apakah stoknya sudah masuk?" */}
          <div className="rounded-xl border border-border p-4 space-y-3" data-testid="ret-master-link">
            <div className="flex items-center gap-2">
              <Link2 className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold">Tautan Master Barang &amp; Stok</span>
              <span className="ml-auto"><StockBadge ret={data} /></span>
            </div>
            {linked ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                <div><span className="text-muted-foreground">Kode master:</span> <span className="ml-1 font-mono" data-testid="ret-sku-code">{data.sku_code || '—'}</span></div>
                <div><span className="text-muted-foreground">Nama:</span> <span className="ml-1">{data.product_name || '—'}</span></div>
                <div><span className="text-muted-foreground">Kategori:</span> <span className="ml-1">{data.material_category || '—'}</span></div>
                <div><span className="text-muted-foreground">Warna / Opsi:</span> <span className="ml-1">{[data.material_color, data.material_option].filter(Boolean).join(' · ') || '—'}</span></div>
                {data.restocked && (
                  <>
                    <div><span className="text-muted-foreground">Masuk lokasi:</span>
                      <span className="ml-1 inline-flex items-center gap-1" data-testid="ret-restock-location">
                        <MapPin className="w-3 h-3" />{data.restock_location_name || data.restock_location_code || '—'}
                      </span>
                    </div>
                    <div><span className="text-muted-foreground">Kondisi:</span>
                      <span className={`ml-1 font-medium ${CONDITION_COLORS[data.restock_condition] || ''}`}>{data.restock_condition || '—'}</span>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-start gap-2 text-sm text-amber-800 dark:text-amber-300">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span data-testid="ret-link-reason">{data.link_reason || 'Barang retur ini belum tertaut ke master produk jadi, jadi stok tidak bisa ditambah.'}</span>
                </div>
                {(data.link_candidates || []).length > 0 && (
                  <div className="text-xs text-muted-foreground">
                    Kandidat barang di pesanan ini:
                    <ul className="list-disc ml-5 mt-1 space-y-0.5">
                      {data.link_candidates.map((c, i) => (
                        <li key={i}>{c.product_name} {c.variation ? `· ${c.variation}` : ''} ({c.quantity} pcs)</li>
                      ))}
                    </ul>
                  </div>
                )}
                {data.source_marketing_return_id && (
                  <button onClick={doRelink} disabled={saving}
                    className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5 inline-flex items-center gap-1 disabled:opacity-50"
                    data-testid="btn-relink">
                    <RefreshCw className="w-3.5 h-3.5" /> Coba tautkan ulang ke master
                  </button>
                )}
              </div>
            )}
            {data.restock_error && (
              <div className="text-xs text-red-700 dark:text-red-400">Gagal restock: {data.restock_error}</div>
            )}
            {info && <div className="text-xs text-emerald-700 dark:text-emerald-400" data-testid="ret-info">{info}</div>}
          </div>

          {/* Step: Received */}
          {data.status !== 'Pending' && (
            <div className="bg-sky-100 dark:bg-sky-500/5 border border-sky-300 dark:border-sky-500/20 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <PackageOpen className="w-4 h-4 text-sky-600 dark:text-sky-400" />
                <span className="text-sm font-semibold text-sky-600 dark:text-sky-400">Penerimaan & Unboxing</span>
                <span className="text-xs text-muted-foreground ml-auto">{fmtDate(data.received_at)} · {data.received_by}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                <div><span className="text-muted-foreground">Kondisi Kemasan:</span> <span className="ml-1">{data.package_condition || '-'}</span></div>
                <div><span className="text-muted-foreground">Bukti Foto/Video:</span> <span className="ml-1">{data.unboxing_photo_notes || '-'}</span></div>
                <div className="sm:col-span-2"><span className="text-muted-foreground">Catatan Unboxing:</span> <span className="ml-1">{data.unboxing_condition_notes}</span></div>
              </div>
            </div>
          )}

          {/* Step: Inspected */}
          {['Inspected', 'Resolved'].includes(data.status) && (
            <div className="bg-violet-100 dark:bg-violet-500/5 border border-violet-300 dark:border-violet-500/20 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <ClipboardCheck className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                <span className="text-sm font-semibold text-violet-600 dark:text-violet-400">Hasil Inspeksi</span>
                <span className="text-xs text-muted-foreground ml-auto">{fmtDate(data.inspected_at)} · {data.inspected_by}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Kondisi Item:</span>
                  <span className={`ml-1 font-medium ${CONDITION_COLORS[data.item_condition] || ''}`}>{data.item_condition || '-'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Penyebab:</span>
                  <span className={`ml-1 font-medium ${CAUSE_COLORS[data.return_cause] || ''}`}>{data.return_cause || '-'}</span>
                </div>
                {data.cause_detail && <div className="sm:col-span-2"><span className="text-muted-foreground">Detail:</span> <span className="ml-1">{data.cause_detail}</span></div>}
                <div><span className="text-muted-foreground">Rekomendasi:</span> <span className="ml-1 font-medium">{data.recommended_action || '-'}</span></div>
              </div>
            </div>
          )}

          {/* Step: Resolved */}
          {data.status === 'Resolved' && (
            <div className="bg-emerald-100 dark:bg-emerald-500/5 border border-emerald-300 dark:border-emerald-500/20 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <PackageCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">Resolusi</span>
                <span className="text-xs text-muted-foreground ml-auto">{fmtDate(data.resolved_at)} · {data.resolved_by}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                <div><span className="text-muted-foreground">Aksi:</span> <span className="ml-1 font-medium">{data.action_taken}</span></div>
                {data.reshipment_resi && <div><span className="text-muted-foreground">Resi Reshipment:</span> <span className="ml-1 font-mono">{data.reshipment_resi}</span></div>}
                {data.appeal_status && <div><span className="text-muted-foreground">Status Appeal:</span> <span className="ml-1">{data.appeal_status}</span></div>}
                {data.restock_qty > 0 && <div><span className="text-muted-foreground">Qty Restock:</span> <span className="ml-1">{data.restock_qty} pcs</span></div>}
                {data.action_notes && <div className="sm:col-span-2"><span className="text-muted-foreground">Catatan:</span> <span className="ml-1">{data.action_notes}</span></div>}
                {data.source_marketing_return_id && (
                  <div className="sm:col-span-2 pt-1">
                    <span className="text-muted-foreground">Retur Toko asal:</span>
                    <span className="ml-1 font-mono text-xs">{data.source_marketing_return_id.slice(0, 8)}…</span>
                  </div>
                )}
              </div>

              {/* RC-FLOW-UX-11b: retur asal Toko selesai di-restock → CTA balik ke Marketing untuk credit note */}
              {data.source_marketing_return_id && onNavigate && (
                <div className="mt-3">
                  <OnwardCTA
                    onNavigate={onNavigate}
                    title="Barang Sudah di Restock — Langkah Berikutnya"
                    actions={[
                      {
                        module: 'marketing-after-sales',
                        params: { tab: 'returns', return_id: data.source_marketing_return_id },
                        label: 'Terbitkan Credit Note & Refund',
                        primary: true,
                        hint: 'Kembali ke portal Toko untuk menerbitkan credit note',
                        testId: 'onward-issue-credit-note',
                      },
                      {
                        module: 'wms-stock-hub',
                        params: { tab: 'stock' },
                        label: 'Cek Stok FG',
                        hint: 'Verifikasi stok setelah restock',
                        testId: 'onward-check-stock',
                      },
                    ]}
                  />
                </div>
              )}
            </div>
          )}

          {/* Timeline */}
          {(data.timeline || []).length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Timeline</h4>
              <div className="relative pl-4 space-y-3">
                <div className="absolute left-1.5 top-0 bottom-0 w-px bg-foreground/10" />
                {[...(data.timeline || [])].reverse().map((t, i) => (
                  <div key={i} className="relative flex gap-3">
                    <div className="absolute -left-3 top-1 w-2 h-2 rounded-full bg-primary/60" />
                    <div className="ml-3">
                      <div className="flex items-center gap-2">
                        <Badge label={t.status} colorClass={STATUS_COLORS[t.status]} />
                        <span className="text-xs text-muted-foreground">oleh {t.by} · {fmtDate(t.at)}</span>
                      </div>
                      {t.note && <p className="text-xs text-muted-foreground mt-0.5">{t.note}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          {isEditable && (
            <div className="border-t border-border pt-4">
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Lanjutkan Proses</h4>
              <div className="flex flex-wrap gap-2">
                {!data.restocked && linked && (
                  <button onClick={() => openStep('quick')} className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:brightness-110" data-testid="btn-quick-restock">
                    <Zap className="w-4 h-4" /> Terima &amp; Restock (1 klik)
                  </button>
                )}
                {data.status === 'Pending' && (
                  <button onClick={() => openStep('receive')} className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-foreground rounded-lg text-sm hover:brightness-110" data-testid="btn-receive">
                    <PackageOpen className="w-4 h-4" /> Terima Barang (Unboxing)
                  </button>
                )}
                {data.status === 'Received' && (
                  <button onClick={() => openStep('inspect')} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-foreground rounded-lg text-sm hover:brightness-110" data-testid="btn-inspect">
                    <ClipboardCheck className="w-4 h-4" /> Inspeksi Kondisi
                  </button>
                )}
                {data.status === 'Inspected' && (
                  <button onClick={() => openStep('resolve')} className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-foreground rounded-lg text-sm hover:brightness-110" data-testid="btn-resolve">
                    <CheckCircle className="w-4 h-4" /> Selesaikan (Resolusi)
                  </button>
                )}
                <button onClick={() => openStep('cancel')} className="flex items-center gap-2 px-3 py-2 border border-red-400 dark:border-red-500/30 text-red-700 dark:text-red-400 rounded-lg text-sm hover:bg-red-100 dark:bg-red-500/10">
                  <XCircle className="w-4 h-4" /> Batalkan
                </button>
              </div>
            </div>
          )}

          {/* QUICK RESTOCK form (W4) */}
          {step === 'quick' && (
            <div className="bg-emerald-100 dark:bg-emerald-500/5 border border-emerald-300 dark:border-emerald-500/20 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-2">
                <Zap className="w-4 h-4" /> Terima &amp; Masukkan ke Stok
              </h4>
              <p className="text-xs text-muted-foreground">
                Satu langkah: barang dinyatakan diterima, diinspeksi, lalu stoknya bertambah.
                Kondisi <strong>Baik</strong> masuk <strong>Area Produk Jadi</strong> (ikut stok jual);
                kondisi <strong>Rusak</strong> masuk <strong>Area Karantina</strong> (tidak dijual).
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Kondisi Barang *</label>
                  <select value={form.condition || 'Baik'} onChange={e => setForm({ ...form, condition: e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quick-condition">
                    {CONDITIONS.map(c => <option key={c} value={c}>{c}{SELLABLE_CONDITIONS.includes(c) ? ' — masuk stok jual' : ' — masuk karantina'}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Qty Masuk *</label>
                  <input type="number" min="1" value={form.restock_qty ?? data.qty}
                    onChange={e => setForm({ ...form, restock_qty: +e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quick-qty" />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Catatan</label>
                <input value={form.action_notes || ''} onChange={e => setForm({ ...form, action_notes: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="Opsional" data-testid="quick-note" />
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400" data-testid="quick-err">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => setStep(null)} className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
                <button onClick={doQuickRestock} disabled={saving} className="px-4 py-1.5 bg-emerald-600 text-white rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="confirm-quick-restock-btn">
                  {saving ? '...' : 'Masukkan ke Stok'}
                </button>
              </div>
            </div>
          )}

          {/* Inline Step Forms */}

          {/* RECEIVE form */}
          {step === 'receive' && (
            <div className="bg-sky-100 dark:bg-sky-500/5 border border-sky-300 dark:border-sky-500/20 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-sky-600 dark:text-sky-400 flex items-center gap-2"><PackageOpen className="w-4 h-4" /> Terima & Unboxing</h4>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Kondisi Kemasan Luar</label>
                <input value={form.package_condition || ''} onChange={e => setForm({ ...form, package_condition: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="Segel utuh / basah / sobek / dll" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Kode / Link Bukti Foto/Video Unboxing</label>
                <input value={form.unboxing_photo_notes || ''} onChange={e => setForm({ ...form, unboxing_photo_notes: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="IMG_001 / Google Drive link / dll" data-testid="unboxing-photo" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Catatan Kondisi Saat Unboxing *</label>
                <textarea value={form.unboxing_condition_notes || ''} onChange={e => setForm({ ...form, unboxing_condition_notes: e.target.value })} rows="3"
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] resize-none"
                  placeholder="Barang tampak normal, bungkus dalam sobek, item masih berplastik..." data-testid="unboxing-notes" />
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => setStep(null)} className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
                <button onClick={doReceive} disabled={saving} className="px-4 py-1.5 bg-sky-600 text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="confirm-receive-btn">
                  {saving ? '...' : 'Konfirmasi Terima'}
                </button>
              </div>
            </div>
          )}

          {/* INSPECT form */}
          {step === 'inspect' && (
            <div className="bg-violet-100 dark:bg-violet-500/5 border border-violet-300 dark:border-violet-500/20 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-violet-600 dark:text-violet-400 flex items-center gap-2"><ClipboardCheck className="w-4 h-4" /> Inspeksi Kondisi Item</h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Kondisi Item *</label>
                  <select value={form.item_condition || ''} onChange={e => setForm({ ...form, item_condition: e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="inspect-condition">
                    <option value="">Pilih...</option>
                    {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Penyebab Return *</label>
                  <select value={form.return_cause || ''} onChange={e => setForm({ ...form, return_cause: e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="inspect-cause">
                    <option value="">Pilih...</option>
                    {CAUSES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Detail Penyebab</label>
                <input value={form.cause_detail || ''} onChange={e => setForm({ ...form, cause_detail: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="Jelaskan lebih detail..." />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Rekomendasi Tindakan</label>
                <select value={form.recommended_action || ''} onChange={e => setForm({ ...form, recommended_action: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="inspect-action">
                  <option value="">Auto (dari penyebab)</option>
                  {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => setStep(null)} className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
                <button onClick={doInspect} disabled={saving} className="px-4 py-1.5 bg-violet-600 text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="confirm-inspect-btn">
                  {saving ? '...' : 'Simpan Inspeksi'}
                </button>
              </div>
            </div>
          )}

          {/* RESOLVE form */}
          {step === 'resolve' && (
            <div className="bg-emerald-100 dark:bg-emerald-500/5 border border-emerald-300 dark:border-emerald-500/20 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-2"><CheckCircle className="w-4 h-4" /> Resolusi Return</h4>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Tindakan yang Diambil *</label>
                <select value={form.action_taken || data.recommended_action || ''} onChange={e => setForm({ ...form, action_taken: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="resolve-action">
                  <option value="">Pilih tindakan...</option>
                  {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>

              {/* Conditional extra fields */}
              {(form.action_taken || data.recommended_action) === 'Reshipment' && (
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">No. Resi Reshipment</label>
                  <input value={form.reshipment_resi || ''} onChange={e => setForm({ ...form, reshipment_resi: e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" placeholder="Masukkan resi pengiriman ulang..." data-testid="reshipment-resi" />
                </div>
              )}
              {(form.action_taken || data.recommended_action) === 'Appeal Platform' && (
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Status Appeal</label>
                  <select value={form.appeal_status || ''} onChange={e => setForm({ ...form, appeal_status: e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="appeal-status">
                    <option value="">Pilih...</option>
                    {APPEAL_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              )}
              {(form.action_taken || data.recommended_action) === 'Restock ke Gudang' && (
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Qty Restock</label>
                  <input type="number" min="1" value={form.restock_qty ?? data.qty} onChange={e => setForm({ ...form, restock_qty: +e.target.value })}
                    className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="restock-qty" />
                </div>
              )}
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Catatan Resolusi</label>
                <textarea value={form.action_notes || ''} onChange={e => setForm({ ...form, action_notes: e.target.value })} rows="2"
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] resize-none"
                  placeholder="Catatan tambahan tindakan yang diambil..." />
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => setStep(null)} className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
                <button onClick={doResolve} disabled={saving} className="px-4 py-1.5 bg-emerald-600 text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="confirm-resolve-btn">
                  {saving ? '...' : 'Selesaikan'}
                </button>
              </div>
            </div>
          )}

          {/* CANCEL form */}
          {step === 'cancel' && (
            <div className="bg-red-100 dark:bg-red-500/5 border border-red-300 dark:border-red-500/20 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-red-700 dark:text-red-400 flex items-center gap-2"><XCircle className="w-4 h-4" /> Batalkan Return</h4>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Alasan Pembatalan</label>
                <textarea value={form.reason || ''} onChange={e => setForm({ ...form, reason: e.target.value })} rows="2"
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] resize-none"
                  placeholder="Kenapa return ini dibatalkan?..." />
              </div>
              <div className="flex gap-2">
                <button onClick={() => setStep(null)} className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
                <button onClick={doCancel} disabled={saving} className="px-4 py-1.5 bg-red-600 text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="confirm-cancel-btn">
                  {saving ? '...' : 'Ya, Batalkan'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── RETURNS TABLE ────────────────────────────────────────────────────────────
function ReturnsTable({ returns, loading, onView, onDelete, onQuickRestock }) {
  const { page, setPage, totalPages, total, paged } = useClientPagination(returns, 10);
  if (loading) return <div className="text-center py-10 text-muted-foreground">Memuat...</div>;
  if (!returns.length) {
    return (
      <div className="text-center py-12 text-muted-foreground" data-testid="wh-ret-empty">
        <RotateCcw className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p className="font-medium">Belum ada retur fisik di daftar ini</p>
        <p className="text-sm">Retur pembeli dari Marketing masuk ke sini otomatis. Bila ada yang tertinggal, tekan <strong>Tarik Retur dari Marketing</strong> di atas.</p>
      </div>
    );
  }
  return (
    <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
      <table className="w-full text-sm min-w-[900px]">
        <thead className="bg-[var(--glass-bg)] border-b border-border">
          <tr>
            <th className="text-left px-4 py-3 text-muted-foreground font-medium">Kode</th>
            <th className="text-left px-4 py-3 text-muted-foreground font-medium">Asal</th>
            <th className="text-left px-4 py-3 text-muted-foreground font-medium">No. Order/Resi</th>
            <th className="text-left px-4 py-3 text-muted-foreground font-medium">Barang (master)</th>
            <th className="text-center px-4 py-3 text-muted-foreground font-medium">Qty</th>
            <th className="text-center px-4 py-3 text-muted-foreground font-medium">Status</th>
            <th className="text-left px-4 py-3 text-muted-foreground font-medium">Efek Stok</th>
            <th className="text-right px-4 py-3 text-muted-foreground font-medium">Tanggal</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {paged.map(r => <ReturnRow key={r.id} ret={r} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />)}
        </tbody>
      </table>
      <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
    </div>
  );
}

// ─── DASHBOARD TAB ────────────────────────────────────────────────────────────
function DashboardTab({ token, onView, onDelete, onQuickRestock }) {
  const [summary, setSummary] = useState(null);
  const [actionItems, setActionItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, items] = await Promise.all([
        api('GET', '/api/wh/returns/summary', token),
        // Items yang perlu aksi (Pending + Received + Inspected)
        api('GET', '/api/wh/returns?status=Pending', token).then(d =>
          api('GET', '/api/wh/returns?status=Received', token).then(d2 =>
            api('GET', '/api/wh/returns?status=Inspected', token).then(d3 =>
              [...(Array.isArray(d) ? d : []), ...(Array.isArray(d2) ? d2 : []), ...(Array.isArray(d3) ? d3 : [])]
            )
          )
        )
      ]);
      setSummary(s);
      setActionItems(items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 20));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5">
      {/* Stat cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Total Return', val: summary.total, color: 'slate', icon: Package },
            { label: 'Pending', val: summary.pending, color: 'amber', icon: Clock },
            { label: 'Diterima', val: summary.received, color: 'sky', icon: PackageOpen },
            { label: 'Diinspeksi', val: summary.inspected, color: 'violet', icon: ClipboardCheck },
            { label: 'Selesai', val: summary.resolved, color: 'emerald', icon: CheckCircle },
            { label: 'Perlu Aksi', val: summary.action_needed, color: 'red', icon: AlertTriangle },
          ].map(s => (
            <div key={s.label} className={`border rounded-xl p-3 ${tone(s.color).surface}`}>
              <div className="flex items-center gap-1.5 mb-1">
                <s.icon className={`w-3.5 h-3.5 ${tone(s.color).text}`} />
                <span className="text-xs text-muted-foreground">{s.label}</span>
              </div>
              <div className={`text-2xl font-bold ${tone(s.color).text}`}>{s.val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Type breakdown */}
      {summary && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-orange-100 dark:bg-orange-500/5 border border-orange-300 dark:border-orange-500/20 rounded-xl p-4 flex items-center gap-3">
            <Truck className="w-8 h-8 text-orange-600 dark:text-orange-400" />
            <div>
              <div className="text-xs text-muted-foreground">Tipe 1 — Ekspedisi</div>
              <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">{summary.expedition_returns}</div>
              <div className="text-xs text-muted-foreground">paket kembali dari ekspedisi</div>
            </div>
          </div>
          <div className="bg-violet-100 dark:bg-violet-500/5 border border-violet-300 dark:border-violet-500/20 rounded-xl p-4 flex items-center gap-3">
            <RotateCcw className="w-8 h-8 text-violet-600 dark:text-violet-400" />
            <div>
              <div className="text-xs text-muted-foreground">Tipe 2 — Customer</div>
              <div className="text-2xl font-bold text-violet-600 dark:text-violet-400">{summary.customer_refunds}</div>
              <div className="text-xs text-muted-foreground">customer request refund</div>
            </div>
          </div>
        </div>
      )}

      {/* Perlu Aksi */}
      {actionItems.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
            Perlu Tindakan Segera ({actionItems.length})
          </h3>
          <ReturnsTable returns={actionItems} loading={loading} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />
        </div>
      )}

      {!loading && actionItems.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <CheckCircle className="w-12 h-12 mx-auto mb-3 text-emerald-600 dark:text-emerald-400 opacity-50" />
          <p className="font-medium">Semua return sudah ditangani!</p>
          <p className="text-sm">Tidak ada yang perlu tindakan saat ini.</p>
        </div>
      )}
    </div>
  );
}

// ─── ROOT COMPONENT ───────────────────────────────────────────────────────────
export default function WHReturnsModule({ token, onNavigate }) {
  const [tab, setTab]         = useState('dashboard');
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch]   = useState('');
  const [statusF, setStatusF] = useState('');
  const [selected, setSelected] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createType, setCreateType] = useState(null);
  // W4 (sesi #29) — jembatan Marketing → Gudang
  const [gap, setGap] = useState(null);
  const [pulling, setPulling] = useState(false);
  const [pullMsg, setPullMsg] = useState('');

  const loadGap = useCallback(async () => {
    try { setGap(await api('GET', '/api/wh/returns/marketing-gap', token)); }
    catch (e) { /* spanduk jembatan bersifat informatif — jangan matikan layar */ }
  }, [token]);

  useEffect(() => { loadGap(); }, [loadGap]);

  const load = useCallback(async (type, extra = {}) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (type)           params.set('return_type', type);
      if (extra.status)   params.set('status', extra.status);
      if (extra.search)   params.set('search', extra.search);
      const data = await api('GET', `/api/wh/returns?${params}`, token);
      setReturns(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    if (tab === 'expedition') load('expedition_return', { status: statusF, search });
    if (tab === 'customer')   load('customer_refund',   { status: statusF, search });
    if (tab === 'all')        load('', { status: statusF, search });
  }, [tab, statusF, search, load]);

  const onView = (ret) => setSelected(ret);
  const onDelete = async (ret) => {
    if (!window.confirm(`Hapus return ${ret.return_code}?`)) return;
    try { await api('DELETE', `/api/wh/returns/${ret.id}`, token); refreshCurrent(); }
    catch (e) { alert(e.message); }
  };

  const refreshCurrent = () => {
    loadGap();
    if (tab === 'expedition') load('expedition_return', { status: statusF, search });
    if (tab === 'customer')   load('customer_refund',   { status: statusF, search });
    if (tab === 'all')        load('', { status: statusF, search });
  };

  // Aksi cepat dari baris tabel: buka detail langsung pada langkah restock supaya
  // kondisi (Baik/Rusak) & qty tetap DIPILIH manusia — bukan diam-diam ditebak.
  const onQuickRestock = (ret) => setSelected({ ...ret, _openQuick: true });

  // Tarik retur pembeli dari Marketing (idempoten; aman ditekan berulang).
  const pullFromMarketing = async () => {
    setPulling(true); setPullMsg('');
    try {
      const res = await api('POST', '/api/wh/returns/sync-marketing', token,
        { dry_run: false, auto_restock: true });
      const d = res.data || {};
      setPullMsg(`Diperiksa ${d.scanned} retur Marketing · ${d.created} pekerjaan baru dibuat · `
        + `${d.restocked} langsung masuk stok · ${d.skipped} perlu dipilih produknya`
        + (d.failed ? ` · ${d.failed} gagal` : ''));
      refreshCurrent();
    } catch (e) { setPullMsg(`Gagal menarik retur: ${e.message}`); }
    finally { setPulling(false); }
  };

  const TABS = [
    { id: 'dashboard',  label: 'Dashboard',         icon: BarChartIcon },
    { id: 'expedition', label: 'Tipe 1 — Ekspedisi', icon: Truck },
    { id: 'customer',   label: 'Tipe 2 — Customer',  icon: RotateCcw },
    { id: 'all',        label: 'Semua Return',        icon: Package },
  ];

  // Quick create shortcuts
  const quickCreate = (type) => { setCreateType(type); setShowCreate(true); };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold">Retur Fisik & Restock (Gudang)</h2>
          <p className="text-muted-foreground text-sm mt-1">Proses fisik: penerimaan barang, inspeksi kondisi, dan resolusi (restock / karantina / reshipment / dispose)</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={pullFromMarketing} disabled={pulling}
            className="flex items-center gap-2 px-3 py-2 bg-sky-600/10 border border-sky-400 dark:border-sky-500/30 text-sky-700 dark:text-sky-400 rounded-lg text-sm hover:bg-sky-600/20 disabled:opacity-50"
            data-testid="btn-pull-marketing">
            <DownloadCloud className={`w-4 h-4 ${pulling ? 'animate-pulse' : ''}`} />
            {pulling ? 'Menarik...' : 'Tarik Retur dari Marketing'}
          </button>
          <button onClick={() => quickCreate('expedition_return')}
            className="flex items-center gap-2 px-3 py-2 bg-orange-600/10 border border-orange-400 dark:border-orange-500/30 text-orange-600 dark:text-orange-400 rounded-lg text-sm hover:bg-orange-600/20" data-testid="btn-add-expedition">
            <Truck className="w-4 h-4" /> + Tipe 1
          </button>
          <button onClick={() => quickCreate('customer_refund')}
            className="flex items-center gap-2 px-3 py-2 bg-violet-600/10 border border-violet-400 dark:border-violet-500/30 text-violet-600 dark:text-violet-400 rounded-lg text-sm hover:bg-violet-600/20" data-testid="btn-add-customer">
            <RotateCcw className="w-4 h-4" /> + Tipe 2
          </button>
          <button onClick={() => { setCreateType(null); setShowCreate(true); }}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-foreground rounded-lg text-sm font-medium hover:brightness-110" data-testid="btn-add-return">
            <Plus className="w-4 h-4" /> Catat Return
          </button>
        </div>
      </div>

      {/* ── W4 — SPANDUK JEMBATAN MARKETING → GUDANG ───────────────────────────
          Angka-angka ini dulu tidak pernah terlihat siapa pun: retur pembeli
          menumpuk di Marketing sementara antrean gudang kosong permanen. */}
      {gap && (
        <div className="rounded-xl border border-border p-4 bg-[var(--card-surface)]" data-testid="mkt-bridge-banner">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Store className="w-4 h-4 text-sky-600 dark:text-sky-400" />
              <span className="text-sm font-semibold">Jembatan Retur Marketing → Gudang</span>
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <span><span className="text-muted-foreground">Retur pembeli:</span> <strong data-testid="gap-mkt-total">{gap.marketing_returns_total}</strong></span>
              <span><span className="text-muted-foreground">Sudah terhubung:</span> <strong data-testid="gap-bridged">{gap.already_bridged}</strong></span>
              <span><span className="text-muted-foreground">Belum ditarik:</span>
                <strong className={gap.pending_bridge > 0 ? 'text-amber-700 dark:text-amber-400 ml-1' : 'text-emerald-700 dark:text-emerald-400 ml-1'}
                  data-testid="gap-pending">{gap.pending_bridge}</strong>
              </span>
              <span><span className="text-muted-foreground">Sudah masuk stok:</span> <strong className="text-emerald-700 dark:text-emerald-400" data-testid="gap-restocked">{gap.restocked}</strong></span>
              {gap.needs_link > 0 && (
                <span><span className="text-muted-foreground">Perlu dipilih produknya:</span> <strong className="text-red-700 dark:text-red-400" data-testid="gap-needs-link">{gap.needs_link}</strong></span>
              )}
            </div>
          </div>
          {pullMsg && <p className="text-xs text-muted-foreground mt-2" data-testid="pull-msg">{pullMsg}</p>}
        </div>
      )}

      {/* RC-FLOW-UX — onward CTA: setelah barang retur diterima → cek/perbarui stok (Alur 8 selesai) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Setelah Barang Retur Diterima"
        actions={[
          { module: 'wms-stock-hub', label: 'Lihat & Sesuaikan Stok', icon: Package, primary: true, hint: 'Barang retur layak jual masuk kembali ke stok' },
        ]}
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto pb-0">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            data-testid={`wh-ret-tab-${t.id}`}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition whitespace-nowrap -mb-px ${
              tab === t.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}>
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Toolbar (only for non-dashboard tabs) */}
      {tab !== 'dashboard' && (
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] flex-1 min-w-48">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari kode, no. order, resi, customer..."
              className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="wh-ret-search" />
            {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-muted-foreground" /></button>}
          </div>
          <SmartNativeSelect value={statusF} onChange={e => setStatusF(e.target.value)} className="border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] text-sm" data-testid="wh-ret-status-filter">
            <option value="">Semua Status</option>
            {['Pending', 'Received', 'Inspected', 'Resolved', 'Cancelled'].map(s => <option key={s} value={s}>{s}</option>)}
          </SmartNativeSelect>
          <button onClick={refreshCurrent} className="p-2 border border-border rounded-lg hover:bg-foreground/5"><RefreshCw className="w-4 h-4" /></button>
        </div>
      )}

      {/* Tab Content */}
      {tab === 'dashboard'  && <DashboardTab token={token} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />}
      {tab === 'expedition' && <ReturnsTable returns={returns} loading={loading} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />}
      {tab === 'customer'   && <ReturnsTable returns={returns} loading={loading} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />}
      {tab === 'all'        && <ReturnsTable returns={returns} loading={loading} onView={onView} onDelete={onDelete} onQuickRestock={onQuickRestock} />}

      {/* Detail Panel */}
      {selected && (
        <DetailPanel ret={selected} token={token} onClose={() => setSelected(null)}
          onRefresh={() => { setSelected(null); refreshCurrent(); }} onNavigate={onNavigate} />
      )}

      {/* Create Modal */}
      {showCreate && (
        <CreateModal token={token} defaultType={createType}
          onClose={() => setShowCreate(false)}
          onSaved={(ret) => { setShowCreate(false); setSelected(ret); refreshCurrent(); }} />
      )}
    </div>
  );
}

// Inline icon
function BarChartIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="12" width="4" height="8" /><rect x="10" y="8" width="4" height="12" /><rect x="17" y="4" width="4" height="16" />
    </svg>
  );
}
