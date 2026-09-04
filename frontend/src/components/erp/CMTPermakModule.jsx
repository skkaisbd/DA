/**
 * CMTPermakModule — Maklon → Permak / Perbaikan (rework barang cacat).
 *
 * Barang cacat dari QC (cmt_receipt_lines.reject_qty) atau Barang Jadi yang ternyata
 * perlu perbaikan dikirim ke PERMAK. Permak open/in_progress MENGURANGI FG. Hasil:
 *   selesai_berhasil (qty_fixed + qty_scrap) atau gagal_buang (semua scrap).
 *
 * API: /api/dewi/cmt-permak/* (routes/dewi_cmt_permak.py)
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Wrench, RefreshCw, Search, Plus, Play, CheckCircle2, XCircle,
  Trash2, Loader2, Package, AlertTriangle, ClipboardList,
} from 'lucide-react';
import { toast } from 'sonner';
import Modal from './engine/Modal';
import ConfirmDialog from './engine/ConfirmDialog';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_META = {
  open: { label: 'Menunggu', cls: 'bg-slate-100 text-slate-700' },
  in_progress: { label: 'Dikerjakan', cls: 'bg-blue-100 text-blue-700' },
  selesai_berhasil: { label: 'Selesai (Berhasil)', cls: 'bg-emerald-100 text-emerald-700' },
  gagal_buang: { label: 'Gagal (Dibuang)', cls: 'bg-zinc-200 text-zinc-700' },
};
const SOURCE_LABEL = { reject: 'Dari Reject QC', good: 'Dari Barang Jadi' };
const TABS = [
  { key: 'all', label: 'Semua' },
  { key: 'open', label: 'Menunggu' },
  { key: 'in_progress', label: 'Dikerjakan' },
  { key: 'selesai_berhasil', label: 'Selesai' },
  { key: 'gagal_buang', label: 'Dibuang' },
];

const fmt = (n) => Number(n || 0).toLocaleString('id-ID');
const fmtRp = (n) => 'Rp' + Number(n || 0).toLocaleString('id-ID');
const PERMAK_TYPE_META = {
  permak_sendiri: { label: 'Permak Sendiri', cls: 'bg-indigo-100 text-indigo-700' },
  retur_ke_cmt: { label: 'Retur ke CMT', cls: 'bg-orange-100 text-orange-700' },
};
const PROBLEM_OPTS = ['jahitan', 'noda', 'ukuran', 'bahan', 'aksesoris', 'lainnya'];
const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }); }
  catch { return String(iso).slice(0, 10); }
};

function PermakStatusBadge({ status }) {
  const m = STATUS_META[status] || { label: status, cls: 'bg-muted text-foreground/80' };
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${m.cls}`}>{m.label}</span>;
}

function KpiCard({ label, value, sub, tone = 'default', icon: Icon }) {
  const tones = {
    default: 'text-foreground',
    amber: 'text-amber-600',
    emerald: 'text-emerald-600',
    zinc: 'text-zinc-600',
    blue: 'text-blue-600',
  };
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {Icon && <Icon size={16} className="text-muted-foreground/60" />}
      </div>
      <div className={`mt-1 text-2xl font-bold ${tones[tone]}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function CMTPermakModule() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [statusTarget, setStatusTarget] = useState(null);   // { record, action }
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = tab && tab !== 'all' ? `?status=${tab}&limit=300` : '?limit=300';
      const [list, sum] = await Promise.all([
        apiGet(`/dewi/cmt-permak${params}`),
        apiGet('/dewi/cmt-permak/summary'),
      ]);
      setRows(Array.isArray(list.items) ? list.items : []);
      setSummary(sum);
    } catch (e) {
      toast.error(`Gagal memuat permak: ${e.message || e}`);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (r.permak_number || '').toLowerCase().includes(q) ||
      (r.sku || '').toLowerCase().includes(q) ||
      (r.product_name || '').toLowerCase().includes(q) ||
      (r.po_number || '').toLowerCase().includes(q)
    );
  }, [rows, search]);

  const doDelete = async () => {
    const rec = confirmDelete;
    setConfirmDelete(null);
    try {
      await apiDelete(`/dewi/cmt-permak/${rec.id}`);
      toast.success('Permak dihapus');
      load();
    } catch (e) {
      toast.error(`Gagal hapus: ${e.message || e}`);
    }
  };

  return (
    <div className="p-6 space-y-4" data-testid="cmt-permak-module">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Wrench size={26} className="text-amber-600" />
            Permak / Perbaikan
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Kelola perbaikan barang cacat dari CMT. Permak yang belum selesai <strong>mengurangi Barang Jadi</strong>;
            berhasil = kembali jadi barang bagus, gagal = scrap.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-input bg-background hover:bg-muted"
            data-testid="btn-refresh-permak"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md bg-amber-600 text-white hover:bg-amber-700"
            data-testid="btn-open-create-permak"
          >
            <Plus size={14} /> Buat Permak
          </button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <KpiCard label="Total Permak" value={fmt(summary?.total_records)} sub={`${fmt(summary?.distinct_pos)} PO`} icon={ClipboardList} />
        <KpiCard label="Menunggu" value={fmt(summary?.open)} sub={`${fmt(summary?.qty_open)} pcs`} tone="amber" />
        <KpiCard label="Dikerjakan" value={fmt(summary?.in_progress)} sub={`${fmt(summary?.qty_in_progress)} pcs`} tone="blue" icon={Play} />
        <KpiCard label="Berhasil" value={fmt(summary?.selesai_berhasil)} sub={`${fmt(summary?.qty_fixed)} pcs fixed`} tone="emerald" icon={CheckCircle2} />
        <KpiCard label="Dibuang" value={fmt(summary?.gagal_buang)} sub={`${fmt(summary?.qty_scrap)} pcs scrap`} tone="zinc" icon={XCircle} />
        <KpiCard label="Perlu Tindakan" value={fmt(summary?.h3_alert)} sub="lewat deadline (H+N)" tone="amber" icon={AlertTriangle} />
        <KpiCard label="Biaya Permak" value={fmtRp(summary?.total_cost)} sub={`sendiri ${fmt(summary?.permak_sendiri)} · retur ${fmt(summary?.retur_ke_cmt)}`} tone="blue" icon={Package} />
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-border flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition ${
              tab === t.key ? 'border-amber-600 text-amber-700' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`tab-permak-${t.key}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Cari no. permak / SKU / produk / PO..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          data-testid="input-search-permak"
        />
      </div>

      {/* Table */}
      <div className="rounded-md border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">No. Permak</th>
              <th className="px-3 py-2 text-left">Produk / SKU</th>
              <th className="px-3 py-2 text-left">PO</th>
              <th className="px-3 py-2 text-left whitespace-nowrap">Vendor CMT / SJ Rework</th>
              <th className="px-3 py-2 text-left">Tipe</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2 text-right">Fixed / Scrap</th>
              <th className="px-3 py-2 text-right">Biaya</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Dibuat</th>
              <th className="px-3 py-2 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody data-testid="permak-table-body">
            {loading ? (
              <tr><td colSpan={10} className="px-3 py-10 text-center text-muted-foreground">
                <Loader2 className="inline animate-spin mr-2" size={16} /> Memuat...
              </td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={10} className="px-3 py-10 text-center text-muted-foreground">
                Belum ada data permak. Klik <strong>Buat Permak</strong> atau kirim dari "Terima FG dari CMT".
              </td></tr>
            ) : filtered.map((r) => {
              const terminal = r.status === 'selesai_berhasil' || r.status === 'gagal_buang';
              return (
                <tr key={r.id} className="border-t border-border hover:bg-muted/30" data-testid={`permak-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono text-xs">{r.permak_number}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-foreground">{r.product_name || r.sku || '—'}</div>
                    <div className="text-xs text-muted-foreground">{r.sku} · {r.color} · {r.size}</div>
                  </td>
                  <td className="px-3 py-2 text-xs">{r.po_number || '—'}</td>
                  {/* FASE 2: tautan vendor + Surat Jalan REWORK — dulu permak tidak
                      punya vendor_id sehingga retur ke CMT tidak pernah terlacak. */}
                  <td className="px-3 py-2 text-xs">
                    <div className="text-foreground truncate max-w-[160px]">{r.vendor_name || r.vendor_permak || '—'}</div>
                    {r.rework_shipment_number ? (
                      <div className="font-mono text-[11px] text-orange-700 whitespace-nowrap" title="Surat jalan rework ke vendor">
                        {r.rework_shipment_number}
                      </div>
                    ) : r.permak_type === 'retur_ke_cmt' ? (
                      <div className="text-[11px] text-red-600">SJ rework belum terbentuk</div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1">
                      <span className={`inline-flex w-fit items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${(PERMAK_TYPE_META[r.permak_type] || {}).cls || 'bg-muted text-foreground/70'}`}>
                        {(PERMAK_TYPE_META[r.permak_type] || {}).label || (r.source === 'good' ? 'Dari FG' : 'Dari Reject')}
                      </span>
                      {r.h3_flag && (
                        <span className="inline-flex w-fit items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-100 text-red-700" title={`Lewat deadline ${Math.abs(r.days_to_deadline)} hari`}>
                          <AlertTriangle size={10} /> Perlu tindakan
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{fmt(r.qty)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {terminal ? (
                      <span><span className="text-emerald-600">{fmt(r.qty_fixed)}</span> / <span className="text-zinc-500">{fmt(r.qty_scrap)}</span></span>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.total_cost ? fmtRp(r.total_cost) : '—'}</td>
                  <td className="px-3 py-2"><PermakStatusBadge status={r.status} /></td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{fmtDate(r.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      {r.status === 'open' && (
                        <button
                          onClick={() => setStatusTarget({ record: r, action: 'in_progress' })}
                          className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                          data-testid={`btn-start-${r.id}`}
                          title="Mulai kerjakan"
                        ><Play size={12} /></button>
                      )}
                      {!terminal && (
                        <>
                          <button
                            onClick={() => setStatusTarget({ record: r, action: 'selesai_berhasil' })}
                            className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                            data-testid={`btn-complete-${r.id}`}
                            title="Selesai (berhasil)"
                          ><CheckCircle2 size={12} /></button>
                          <button
                            onClick={() => setStatusTarget({ record: r, action: 'gagal_buang' })}
                            className="text-xs px-2 py-1 rounded bg-zinc-600 text-white hover:bg-zinc-700"
                            data-testid={`btn-scrap-${r.id}`}
                            title="Gagal / buang"
                          ><XCircle size={12} /></button>
                        </>
                      )}
                      {r.status === 'open' && (
                        <button
                          onClick={() => setConfirmDelete(r)}
                          className="text-xs px-2 py-1 rounded border border-border text-red-600 hover:bg-red-50"
                          data-testid={`btn-delete-${r.id}`}
                          title="Hapus"
                        ><Trash2 size={12} /></button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreatePermakDialog onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />
      )}
      {statusTarget && (
        <StatusDialog
          target={statusTarget}
          onClose={() => setStatusTarget(null)}
          onDone={() => { setStatusTarget(null); load(); }}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Permak?"
          message={`Hapus ${confirmDelete.permak_number}? Hanya permak berstatus "Menunggu" yang bisa dihapus.`}
          onConfirm={doDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}

/* ─── Create dialog ─────────────────────────────────────────────────────── */
function CreatePermakDialog({ onClose, onCreated }) {
  const [pos, setPos] = useState([]);
  const [poId, setPoId] = useState('');
  const [items, setItems] = useState([]);
  const [itemId, setItemId] = useState('');
  const [qty, setQty] = useState('');
  const [source, setSource] = useState('good');
  const [permakType, setPermakType] = useState('permak_sendiri');
  const [problemType, setProblemType] = useState('jahitan');
  const [costPerPcs, setCostPerPcs] = useState('');
  const [returnDeadline, setReturnDeadline] = useState('');
  const [vendor, setVendor] = useState('');
  const [reason, setReason] = useState('');
  const [loadingItems, setLoadingItems] = useState(false);
  const [saving, setSaving] = useState(false);
  // SESI #27 — kebijakan penomoran Permak (Otomatis/Manual) milik owner.
  const numPolicy = useDocNumberPolicy('dewi_cmt_permak.permak_number',
                                       localStorage.getItem('erp_token'));
  const [permakNumber, setPermakNumber] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet('/maklon-client/pos');
        setPos(Array.isArray(data) ? data : []);
      } catch (e) { toast.error(`Gagal memuat PO: ${e.message || e}`); }
    })();
  }, []);

  useEffect(() => {
    if (!poId) { setItems([]); setItemId(''); return; }
    (async () => {
      setLoadingItems(true);
      try {
        const prog = await apiGet(`/maklon-client/pos/${poId}/progress`);
        setItems(Array.isArray(prog.items) ? prog.items : []);
      } catch (e) {
        toast.error(`Gagal memuat item PO: ${e.message || e}`);
        setItems([]);
      } finally { setLoadingItems(false); }
    })();
  }, [poId]);

  const selectedItem = items.find((i) => i.po_item_id === itemId);

  const submit = async () => {
    if (!poId || !itemId) return toast.error('Pilih PO & item terlebih dahulu');
    const q = Number(qty);
    if (!q || q <= 0) return toast.error('Qty harus lebih dari 0');
    setSaving(true);
    try {
      await apiPost('/dewi/cmt-permak', {
        po_id: poId, po_item_id: itemId, qty: q, source,
        permak_type: permakType, problem_type: problemType,
        cost_per_pcs: Number(costPerPcs || 0),
        return_deadline: returnDeadline || null,
        vendor_permak: vendor, reason,
        ...docNumberPayload(numPolicy, 'permak_number', permakNumber),
      });
      toast.success('Permak dibuat');
      onCreated();
    } catch (e) {
      toast.error(`Gagal membuat permak: ${e.message || e}`);
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Buat Permak Baru" onClose={onClose} size="lg">
      <div className="space-y-4" data-testid="create-permak-dialog">
        <div>
          <label className="text-xs font-medium text-muted-foreground">PO Maklon</label>
          <select
            value={poId}
            onChange={(e) => setPoId(e.target.value)}
            className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
            data-testid="select-permak-po"
          >
            <option value="">— Pilih PO —</option>
            {pos.map((p) => (
              <option key={p.po_id} value={p.po_id}>{p.po_number} — {p.status}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground">Item / SKU</label>
          <select
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            disabled={!poId || loadingItems}
            className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background disabled:opacity-60"
            data-testid="select-permak-item"
          >
            <option value="">{loadingItems ? 'Memuat item...' : '— Pilih item —'}</option>
            {items.map((i) => (
              <option key={i.po_item_id} value={i.po_item_id}>
                {i.product_name || i.sku} ({i.sku} · {i.color} · {i.size}) — bagus {fmt(i.qty_good)} / reject {fmt(i.qty_reject_qc)}
              </option>
            ))}
          </select>
        </div>

        {selectedItem && (
          <div className="grid grid-cols-3 gap-2 text-xs rounded-md bg-muted/40 p-3">
            <div><span className="text-muted-foreground">Barang Jadi</span><div className="font-semibold text-emerald-600">{fmt(selectedItem.qty_good)}</div></div>
            <div><span className="text-muted-foreground">Reject QC</span><div className="font-semibold text-red-600">{fmt(selectedItem.qty_reject_qc)}</div></div>
            <div><span className="text-muted-foreground">Sedang Permak</span><div className="font-semibold text-amber-600">{fmt(selectedItem.qty_rework_open)}</div></div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Sumber</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="select-permak-source"
            >
              <option value="good">Dari Barang Jadi (mengurangi FG)</option>
              <option value="reject">Dari Reject QC</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Qty</label>
            <input
              type="number" min="1"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="input-permak-qty"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Tipe Permak</label>
            <select
              value={permakType}
              onChange={(e) => setPermakType(e.target.value)}
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="select-permak-type"
            >
              <option value="permak_sendiri">Permak Sendiri (workshop DA)</option>
              <option value="retur_ke_cmt">Retur ke CMT (dikembalikan)</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Jenis Masalah</label>
            <select
              value={problemType}
              onChange={(e) => setProblemType(e.target.value)}
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="select-permak-problem"
            >
              {PROBLEM_OPTS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Ongkos Permak / pcs (Rp)</label>
            <input
              type="number" min="0"
              value={costPerPcs}
              onChange={(e) => setCostPerPcs(e.target.value)}
              placeholder="0"
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="input-permak-cost"
            />
            {Number(costPerPcs) > 0 && Number(qty) > 0 && (
              <div className="mt-1 text-[11px] text-muted-foreground">Total: {fmtRp(Number(costPerPcs) * Number(qty))}</div>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Target Kembali (deadline)</label>
            <input
              type="date"
              value={returnDeadline}
              onChange={(e) => setReturnDeadline(e.target.value)}
              className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
              data-testid="input-permak-deadline"
            />
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground">Vendor / Workshop Permak (opsional)</label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="Nama vendor/tukang permak"
            className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
            data-testid="input-permak-vendor"
          />
        </div>

        {/* SESI #27 — nomor dokumen mengikuti kebijakan Otomatis/Manual milik owner */}
        <DocNumberField
          policy={numPolicy} value={permakNumber} onChange={setPermakNumber}
          testId="permak-docnum" label="Nomor Permak" />
        {numPolicy?.mode === 'manual' && (
          <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="permak-docnum-warn">
            Catatan: bila qty yang diminta harus dipecah ke beberapa baris reject,
            satu pengajuan bisa melahirkan lebih dari satu dokumen permak — nomor
            ketikan hanya bisa dipakai untuk pengajuan yang menghasilkan SATU dokumen.
          </p>
        )}
        <div>
          <label className="text-xs font-medium text-muted-foreground">Alasan / Catatan</label>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Contoh: jahitan lepas, noda, salah ukuran..."
            className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
            data-testid="input-permak-reason"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-md border border-border hover:bg-muted">Batal</button>
          <button
            onClick={submit}
            disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
            data-testid="btn-submit-create-permak"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Simpan
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ─── Status transition dialog ──────────────────────────────────────────── */
function StatusDialog({ target, onClose, onDone }) {
  const { record, action } = target;
  const qty = Number(record.qty || 0);
  const [qtyFixed, setQtyFixed] = useState(qty);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const qtyScrap = Math.max(0, qty - Number(qtyFixed || 0));

  const titles = {
    in_progress: 'Mulai Kerjakan Permak',
    selesai_berhasil: 'Selesaikan Permak (Berhasil)',
    gagal_buang: 'Tandai Gagal / Buang',
  };

  const submit = async () => {
    setSaving(true);
    try {
      const body = { status: action, note };
      if (action === 'selesai_berhasil') {
        const qf = Number(qtyFixed || 0);
        if (qf < 0 || qf > qty) { setSaving(false); return toast.error(`Qty fixed harus 0..${qty}`); }
        body.qty_fixed = qf;
        body.qty_scrap = qty - qf;
      }
      await apiPost(`/dewi/cmt-permak/${record.id}/status`, body);
      toast.success('Status permak diperbarui');
      onDone();
    } catch (e) {
      toast.error(`Gagal ubah status: ${e.message || e}`);
    } finally { setSaving(false); }
  };

  return (
    <Modal title={titles[action] || 'Ubah Status'} onClose={onClose} size="sm">
      <div className="space-y-4" data-testid="permak-status-dialog">
        <div className="text-sm text-muted-foreground">
          {record.permak_number} — {record.product_name || record.sku} ({fmt(qty)} pcs)
        </div>

        {action === 'selesai_berhasil' && (
          <div className="space-y-3 rounded-md bg-muted/40 p-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Qty Berhasil Diperbaiki</label>
              <input
                type="number" min="0" max={qty}
                value={qtyFixed}
                onChange={(e) => setQtyFixed(e.target.value)}
                className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
                data-testid="input-status-qty-fixed"
              />
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-emerald-600">Fixed: {fmt(qtyFixed)}</span>
              <span className="text-zinc-500">Scrap: {fmt(qtyScrap)}</span>
            </div>
            <div className="text-[11px] text-muted-foreground flex items-start gap-1">
              <AlertTriangle size={12} className="mt-0.5" />
              Fixed + Scrap harus = {fmt(qty)}. Fixed akan menambah Barang Jadi.
            </div>
          </div>
        )}

        {action === 'gagal_buang' && (
          <div className="rounded-md bg-zinc-50 border border-zinc-200 p-3 text-xs text-zinc-700 flex items-start gap-1">
            <AlertTriangle size={14} className="mt-0.5" />
            Seluruh {fmt(qty)} pcs akan ditandai <strong>scrap</strong> (dibuang permanen).
          </div>
        )}

        <div>
          <label className="text-xs font-medium text-muted-foreground">Catatan (opsional)</label>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="mt-1 w-full text-sm px-3 py-2 rounded-md border border-input bg-background"
            data-testid="input-status-note"
          />
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-md border border-border hover:bg-muted">Batal</button>
          <button
            onClick={submit}
            disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50"
            data-testid="btn-submit-status"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Konfirmasi
          </button>
        </div>
      </div>
    </Modal>
  );
}
