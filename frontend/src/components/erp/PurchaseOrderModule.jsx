import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Eye, Trash2, CheckCircle2, XCircle, AlertTriangle, Send, Package, FileText, TruckIcon, Upload, Download, Building2, Tag } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_META = {
  draft:               { label: 'Draft',               bg: 'bg-muted dark:bg-slate-400/15',   border: 'border-border/25',   text: 'text-foreground/70', icon: FileText },
  pending_approval:    { label: 'Menunggu Approval',   bg: 'bg-amber-50 dark:bg-amber-400/15',   border: 'border-amber-300/25',   text: 'text-amber-600 dark:text-amber-300', icon: AlertTriangle },
  approved:            { label: 'Disetujui',           bg: 'bg-emerald-50 dark:bg-emerald-400/15', border: 'border-emerald-300/25', text: 'text-emerald-600 dark:text-emerald-300', icon: CheckCircle2 },
  partially_received:  { label: 'Diterima Sebagian',   bg: 'bg-blue-50 dark:bg-blue-400/15',    border: 'border-blue-300/25',    text: 'text-blue-600 dark:text-blue-300', icon: Package },
  fully_received:      { label: 'Diterima Penuh',      bg: 'bg-green-50 dark:bg-green-400/15',   border: 'border-green-300/25',   text: 'text-green-600 dark:text-green-300', icon: CheckCircle2 },
  rejected:            { label: 'Ditolak',             bg: 'bg-red-50 dark:bg-red-400/15',     border: 'border-red-300/25',     text: 'text-red-600 dark:text-red-300', icon: XCircle },
  cancelled:           { label: 'Dibatalkan',          bg: 'bg-muted dark:bg-gray-400/15',    border: 'border-border/25',    text: 'text-foreground/80', icon: XCircle },
};

function StatusBadge({ status }) {
  const s = STATUS_META[status] || STATUS_META.draft;
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${s.bg} ${s.border} border ${s.text}`}>
      <Icon className="w-3 h-3" />
      {s.label}
    </span>
  );
}

export default function PurchaseOrderModule({ token, onNavigate }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [materials, setMaterials] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [uomMap, setUomMap] = useState({});      // material_id -> {base_unit, units[]}
  const [priceHint, setPriceHint] = useState({}); // item_id -> {price, uom, supplier_name}
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSupplier, setFilterSupplier] = useState('');
  const [createModal, setCreateModal] = useState(false);
  const [detailModal, setDetailModal] = useState(false);
  const [submitModal, setSubmitModal] = useState(false);
  const [approveModal, setApproveModal] = useState(false);
  const [rejectModal, setRejectModal] = useState(false);
  const [cancelModal, setCancelModal] = useState(false);
  const [selectedPO, setSelectedPO] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [approveNote, setApproveNote] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  // SESI #19 — kebijakan penomoran PO Pembelian (Otomatis/Manual) dari Administrasi
  // Sistem → Penomoran Dokumen. PO adalah komitmen UANG: nomor bebas tidak bisa
  // diurutkan maupun dicari di arsip, jadi mode manual pun wajib mengikuti pola.
  const numPolicy = useDocNumberPolicy('rahaza_purchase_orders.po_number', token);
  const [poNumber, setPoNumber] = useState('');
  const [bulkModal, setBulkModal] = useState(false);
  const [bulkRows, setBulkRows] = useState([]);
  const [bulkVendor, setBulkVendor] = useState('');
  const [bulkErrors, setBulkErrors] = useState([]);
  const csvRef = useRef(null);

  const [poForm, setPOForm] = useState({
    supplier_id: '',
    vendor_name: '',
    vendor_contact: '',
    vendor_address: '',
    po_date: new Date().toISOString().split('T')[0],
    expected_delivery_date: '',
    notes: '',
    items: [],
  });

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStatus) qs.set('status', filterStatus);
      if (filterSupplier) qs.set('supplier_id', filterSupplier);
      const r = await fetch(`/api/rahaza/purchase-orders${qs.toString() ? `?${qs}` : ''}`, { headers });
      if (r.ok) setList(await r.json());
      else toast.error(`Gagal memuat PO (HTTP ${r.status})`);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterStatus, filterSupplier]);

  useEffect(() => { fetchList(); }, [fetchList]);

  useEffect(() => {
    const h = { Authorization: `Bearer ${token}` };
    fetch('/api/rahaza/materials', { headers: h })
      .then(r => r.ok ? r.json() : [])
      .then(m => setMaterials((Array.isArray(m) ? m : m?.items || []).filter(x => x.active)));
    // Master Supplier (SSOT) — pengganti input nama vendor teks bebas
    fetch('/api/procurement/suppliers/options', { headers: h })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setSuppliers(d?.items || []));
  }, [token]);

  /** Ambil daftar satuan SAH + faktornya untuk material (server yang menentukan). */
  const ensureUom = useCallback(async (materialId) => {
    if (!materialId || uomMap[materialId]) return uomMap[materialId];
    try {
      const r = await fetch(`/api/rahaza/materials/uom-options?material_ids=${materialId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) return null;
      const d = await r.json();
      const o = (d?.options || {})[materialId] || null;
      if (o) setUomMap(prev => ({ ...prev, [materialId]: o }));
      return o;
    } catch { return null; }
  }, [token, uomMap]);

  /** Harga berlaku dari daftar harga supplier → auto-isi harga PO. */
  const fetchPriceHint = useCallback(async (itemId, materialId, supplierId) => {
    if (!materialId) return null;
    try {
      const qs = `material_id=${materialId}${supplierId ? `&supplier_id=${supplierId}` : ''}`;
      const r = await fetch(`/api/procurement/price-lookup?${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) return null;
      const d = await r.json();
      const best = d?.best || null;
      setPriceHint(prev => ({ ...prev, [itemId]: best }));
      return best;
    } catch { return null; }
  }, [token]);

  const resetForm = () => {
    setPOForm({
      supplier_id: '',
      vendor_name: '',
      vendor_contact: '',
      vendor_address: '',
      po_date: new Date().toISOString().split('T')[0],
      expected_delivery_date: '',
      notes: '',
      items: [],
    });
    setPriceHint({});
    setFormError('');
  };

  const openCreate = () => {
    resetForm();
    setCreateModal(true);
  };

  const addItem = () => {
    setPOForm(prev => ({
      ...prev,
      items: [...prev.items, {
        id: crypto.randomUUID(), material_id: '', description: '',
        uom: '', qty_input: 0, unit_cost_input: 0, notes: '',
      }],
    }));
  };

  const updateItem = (itemId, field, value) => {
    setPOForm(prev => ({
      ...prev,
      items: prev.items.map(it => it.id === itemId ? { ...it, [field]: value } : it),
    }));
  };

  /** Pilih material → muat satuan sah, set satuan beli default, auto-isi harga. */
  const pickMaterial = async (itemId, materialId) => {
    updateItem(itemId, 'material_id', materialId);
    if (!materialId) {
      updateItem(itemId, 'uom', '');
      return;
    }
    const opt = await ensureUom(materialId);
    const mat = materials.find(m => m.id === materialId);
    const best = await fetchPriceHint(itemId, materialId, poForm.supplier_id);
    // Satuan beli default: dari daftar harga supplier → purchase_uom master → satuan dasar
    const defaultUom = best?.uom || mat?.purchase_uom || opt?.base_unit || mat?.unit || '';
    const known = (opt?.units || []).some(u => u.unit === defaultUom);
    updateItem(itemId, 'uom', known ? defaultUom : (opt?.base_unit || ''));
    if (best?.price) updateItem(itemId, 'unit_cost_input', Number(best.price));
  };

  const removeItem = (itemId) => {
    setPOForm(prev => ({
      ...prev,
      items: prev.items.filter(it => it.id !== itemId),
    }));
  };

  /** Faktor satuan terpilih → satuan dasar (untuk pratinjau konversi). */
  const factorOf = useCallback((item) => {
    const opt = uomMap[item.material_id];
    if (!opt) return 1;
    if (!item.uom || item.uom === opt.base_unit) return 1;
    const row = (opt.units || []).find(u => u.unit === item.uom);
    return row ? Number(row.factor_to_base) : 1;
  }, [uomMap]);

  const formTotal = useMemo(
    () => poForm.items.reduce((s, it) => s + (Number(it.qty_input) || 0) * (Number(it.unit_cost_input) || 0), 0),
    [poForm.items],
  );

  const selectedSupplier = useMemo(
    () => suppliers.find(s => s.id === poForm.supplier_id) || null,
    [suppliers, poForm.supplier_id],
  );

  const createPO = async () => {
    setSaving(true);
    setFormError('');
    try {
      if (!poForm.supplier_id && !poForm.vendor_name.trim()) {
        throw new Error('Pilih supplier dari Master Supplier terlebih dahulu.');
      }
      if (poForm.items.length === 0) throw new Error('Tambahkan minimal 1 item.');

      const validItems = poForm.items.filter(
        it => (it.material_id || (it.description || '').trim()) && Number(it.qty_input) > 0,
      );
      if (validItems.length === 0) {
        throw new Error('Tidak ada item valid (pilih material atau tulis keterangan, dan qty > 0).');
      }

      const r = await fetch('/api/rahaza/purchase-orders', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          ...poForm,
          ...docNumberPayload(numPolicy, 'po_number', poNumber),
          items: validItems.map(it => ({
            material_id: it.material_id || undefined,
            description: it.description || undefined,
            uom: it.uom || undefined,
            qty_input: Number(it.qty_input) || 0,
            unit_cost_input: Number(it.unit_cost_input) || 0,
            notes: it.notes || '',
          })),
        }),
      });

      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(typeof err.detail === 'string' ? err.detail : `Gagal membuat PO (HTTP ${r.status})`);
      }

      toast.success('Purchase Order berhasil dibuat');
      setCreateModal(false);
      resetForm();
      fetchList();
    } catch (e) {
      setFormError(e.message);
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (po) => {
    const r = await fetch(`/api/rahaza/purchase-orders/${po.id}`, { headers });
    if (r.ok) {
      const detail = await r.json();
      // P1.C: also fetch GR audit trail in parallel
      try {
        const gr_r = await fetch(`/api/rahaza/purchase-orders/${po.id}/grs`, { headers });
        if (gr_r.ok) {
          detail._grs = await gr_r.json();
        }
      } catch {
        // non-fatal: audit trail GR opsional
      }
      setSelectedPO(detail);
      setDetailModal(true);
    }
  };

  const openSubmitModal = (po) => {
    setSelectedPO(po);
    setSubmitModal(true);
  };

  // 2026-08-07 — pesan galat dari SERVER harus DITAMPILKAN.
  // Sebelumnya ketiga aksi ini membuang isi respons dan menampilkan teks generik
  // ("Gagal menyetujui PO"), padahal backend mengirim alasan yang tepat dan
  // berbahasa Indonesia (mis. "Anda pembuat permintaan ini…", "Tahap saat ini
  // Persetujuan Keuangan — hanya keuangan yang berhak memutuskan."). Tanpa ini
  // pengguna hanya tahu "gagal" tanpa pernah tahu APA yang harus dilakukan.
  const serverError = async (r, fallback) => {
    try {
      const b = await r.json();
      return b?.detail || b?.message || fallback;
    } catch { return fallback; }
  };

  const submitPO = async () => {
    if (!selectedPO) return;
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/purchase-orders/${selectedPO.id}/submit`, { method: 'POST', headers });
      if (r.ok) {
        const d = await r.json().catch(() => ({}));
        toast.success(
          d?.total_stages > 1
            ? `PO diajukan — butuh ${d.total_stages} tahap persetujuan, sekarang menunggu ${d.stage_label || 'tahap pertama'}`
            : `PO diajukan — menunggu ${d?.stage_label || 'persetujuan'}`
        );
        setSubmitModal(false);
        await fetchList();
      } else {
        throw new Error(await serverError(r, 'Gagal mengajukan PO'));
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const openApproveModal = (po) => {
    setSelectedPO(po);
    setApproveNote('');
    setApproveModal(true);
  };

  const approvePO = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/purchase-orders/${selectedPO.id}/approve`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ comment: approveNote }),
      });
      if (r.ok) {
        const d = await r.json().catch(() => ({}));
        toast.success(
          d?.next_stage
            ? `${selectedPO.po_number} disetujui — lanjut ke ${d.next_stage_label}`
            : `${selectedPO.po_number} disetujui penuh — siap dikirim ke supplier`
        );
        setApproveModal(false);
        fetchList();
        if (detailModal) openDetail(selectedPO);
      } else {
        throw new Error(await serverError(r, 'Gagal menyetujui PO'));
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const openRejectModal = (po) => {
    setSelectedPO(po);
    setRejectReason('');
    setRejectModal(true);
  };

  const rejectPO = async () => {
    // Alasan WAJIB. Dulu frontend mengirim "Tidak ada alasan" secara otomatis,
    // sehingga aturan "penolakan harus beralasan" tidak ada artinya dan pembuat
    // PO tidak pernah tahu apa yang harus diperbaiki.
    if (!rejectReason.trim()) {
      toast.error('Alasan penolakan wajib diisi agar pembuat PO tahu apa yang harus diperbaiki.');
      return;
    }
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/purchase-orders/${selectedPO.id}/reject`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reason: rejectReason.trim() }),
      });
      if (r.ok) {
        toast.success(`PO ${selectedPO.po_number} ditolak`);
        setRejectModal(false);
        fetchList();
        if (detailModal) openDetail(selectedPO);
      } else {
        throw new Error(await serverError(r, 'Gagal menolak PO'));
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const openCancelModal = (po) => {
    setSelectedPO(po);
    setCancelReason('');
    setCancelModal(true);
  };

  const cancelPO = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/purchase-orders/${selectedPO.id}/cancel`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reason: cancelReason || 'Tidak ada alasan' }),
      });
      if (r.ok) {
        toast.success(`PO ${selectedPO.po_number} dibatalkan`);
        setCancelModal(false);
        fetchList();
        if (detailModal) openDetail(selectedPO);
      } else {
        throw new Error('Gagal membatalkan PO');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const deletePO = async (po) => {
    if (!window.confirm(`Hapus PO ${po.po_number}?`)) return;
    const r = await fetch(`/api/rahaza/purchase-orders/${po.id}`, { method: 'DELETE', headers });
    if (r.ok) {
      toast.success('PO berhasil dihapus');
      fetchList();
      setDetailModal(false);
    } else {
      toast.error('Gagal menghapus PO');
    }
  };

  const createGRFromPO = async (po) => {
    // P1.C: Call backend create-gr endpoint then navigate to receiving
    try {
      const r = await fetch(`/api/rahaza/purchase-orders/${po.id}/create-gr`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: `Auto-created from PO ${po.po_number}` }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: 'Gagal membuat GR' }));
        toast.error(err.detail || 'Gagal membuat GR dari PO');
        return;
      }
      const gr = await r.json();
      toast.success(`GR ${gr.receipt_number} berhasil dibuat dari PO ${po.po_number}. ${gr.items.length} item siap diterima.`);
      // Navigate to ReceivingModule with the new GR id (let module handle the deep link)
      onNavigate?.('wh-receiving', { receipt_id: gr.id, po_id: po.id, po_number: po.po_number });
      fetchList();
      setDetailModal(false);
    } catch (e) {
      toast.error('Gagal membuat GR: ' + (e?.message || ''));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="purchase-order-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Purchase Order (PO)</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Kelola pembelian material dari vendor. PO harus disetujui sebelum bisa diterima di Gudang.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
            data-testid="po-filter-status"
          >
            <option value="">Semua Status</option>
            <option value="draft">Draft</option>
            <option value="pending_approval">Menunggu Approval</option>
            <option value="approved">Disetujui</option>
            <option value="partially_received">Diterima Sebagian</option>
            <option value="fully_received">Diterima Penuh</option>
            <option value="rejected">Ditolak</option>
            <option value="cancelled">Dibatalkan</option>
          </select>
          <select
            value={filterSupplier}
            onChange={e => setFilterSupplier(e.target.value)}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground max-w-[220px]"
            data-testid="po-filter-supplier"
          >
            <option value="">Semua Supplier</option>
            {suppliers.map(s => (
              <option key={s.id} value={s.id}>{`${s.code} — ${s.name}`}</option>
            ))}
          </select>
          <Button onClick={openCreate} data-testid="po-create-btn">
            <Plus className="w-4 h-4 mr-1.5" /> Buat PO
          </Button>
          {/* U2 — Bulk CSV Import */}
          <button
            onClick={() => setBulkModal(true)}
            className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 hover:text-emerald-600 dark:text-emerald-300 px-3 py-1.5 bg-emerald-100 dark:bg-emerald-500/10 rounded-lg border border-emerald-300 dark:border-emerald-500/20 transition-colors"
            data-testid="po-bulk-import-btn"
          >
            <Upload size={13} /> Import CSV
          </button>
        </div>
      </div>

      {/* PO List */}
      <GlassCard>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--glass-border)]">
              <tr className="text-left text-muted-foreground">
                <th className="pb-3 pl-4 font-semibold">No. PO</th>
                <th className="pb-3 font-semibold">Tanggal</th>
                <th className="pb-3 font-semibold">Supplier</th>
                <th className="pb-3 font-semibold">Items</th>
                <th className="pb-3 font-semibold">Total Nilai</th>
                <th className="pb-3 font-semibold">Status</th>
                <th className="pb-3 pr-4 font-semibold text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="text-foreground">
              {list.length === 0 && (
                <tr>
                  <td colSpan="7" className="py-12 text-center text-muted-foreground">
                    <Package className="w-12 h-12 mx-auto mb-2 opacity-30" />
                    <p>Belum ada Purchase Order</p>
                  </td>
                </tr>
              )}
              {list.map((po, idx) => (
                <tr key={po.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`} data-testid={`po-row-${po.id}`}>
                  <td className="py-3 pl-4 font-mono text-xs">{po.po_number}</td>
                  <td className="py-3 text-xs">{new Date(po.po_date).toLocaleDateString('id-ID')}</td>
                  <td className="py-3">
                    <div className="font-medium">{po.supplier_name || po.vendor_name}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                      {po.supplier_code
                        ? <span className="font-mono">{po.supplier_code}</span>
                        : <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                            <AlertTriangle className="w-3 h-3" /> belum tertaut master
                          </span>}
                      {po.vendor_contact && <span>· {po.vendor_contact}</span>}
                    </div>
                  </td>
                  <td className="py-3 text-xs">{po.item_count} item</td>
                  <td className="py-3 font-mono text-xs">Rp {(po.total_value || 0).toLocaleString('id-ID')}</td>
                  <td className="py-3">
                    <StatusBadge status={po.status} />
                    {/* Tahap aktif dari SERVER — dulu kolom ini hanya menampilkan
                        "Menunggu Persetujuan" tanpa memberi tahu tahap ke berapa
                        dari berapa, sehingga tidak ada yang tahu siapa gilirannya. */}
                    {po.status === 'pending_approval' && po.stage_label && (
                      <div className="mt-1 text-[10px] text-muted-foreground" data-testid={`po-stage-${po.id}`}>
                        {po.stage_label}{po.total_stages ? ` (${po.stage_order}/${po.total_stages})` : ''}
                      </div>
                    )}
                    {po.exceeds_pr_value && (
                      <div className="mt-1 text-[10px] font-medium text-amber-700 dark:text-amber-400"
                           data-testid={`po-exceeds-${po.id}`}>
                        Melebihi nilai PR yang disetujui
                      </div>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openDetail(po)} data-testid={`po-view-${po.id}`}>
                        <Eye className="w-4 h-4" />
                      </Button>
                      {(po.status === 'draft' || po.status === 'rejected') && po.can_submit !== false && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => openSubmitModal(po)} data-testid={`po-submit-${po.id}`}>
                            <Send className="w-4 h-4" />
                          </Button>
                          {po.status === 'draft' && (
                            <Button variant="ghost" size="sm" onClick={() => deletePO(po)} data-testid={`po-delete-${po.id}`}>
                              <Trash2 className="w-4 h-4 text-red-700 dark:text-red-400" />
                            </Button>
                          )}
                        </>
                      )}
                      {/* 2026-08-07 — tombol Setujui/Tolak mengikuti FLAG SERVER
                          (`can_approve`/`can_reject`), bukan sekadar status.
                          Dulu digating hanya `status === 'pending_approval'`
                          sehingga SIAPA PUN yang login melihat tombolnya lalu
                          backend membalas 403 — tombol yang tampak bisa dipakai
                          tapi selalu gagal. Kalau tidak berhak, alasannya
                          DITAMPILKAN, bukan tombolnya hilang tanpa penjelasan. */}
                      {po.status === 'pending_approval' && po.can_approve && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => openApproveModal(po)}
                                  title={po.stage_label ? `Setujui — ${po.stage_label}` : 'Setujui'}
                                  data-testid={`po-approve-${po.id}`}>
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => openRejectModal(po)} data-testid={`po-reject-${po.id}`}>
                            <XCircle className="w-4 h-4 text-red-700 dark:text-red-400" />
                          </Button>
                        </>
                      )}
                      {po.status === 'pending_approval' && !po.can_approve && (
                        <span className="max-w-[260px] text-[10px] leading-snug text-muted-foreground text-right"
                              data-testid={`po-blocked-${po.id}`}>
                          {po.blocked_reason || 'Menunggu approver yang berhak.'}
                        </span>
                      )}
                      {(po.status === 'approved' || po.status === 'partially_received') && (
                        <Button variant="ghost" size="sm" onClick={() => createGRFromPO(po)} data-testid={`po-create-gr-${po.id}`}>
                          <TruckIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        </Button>
                      )}
                      {po.status !== 'fully_received' && po.status !== 'cancelled' && (
                        <Button variant="ghost" size="sm" onClick={() => openCancelModal(po)} data-testid={`po-cancel-${po.id}`}>
                          <XCircle className="w-4 h-4 text-muted-foreground" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Create PO Modal */}
      {createModal && (
        <Modal onClose={() => setCreateModal(false)} title="Buat Purchase Order Baru" size="2xl">
          <div className="space-y-4">
            {formError && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-400 dark:border-red-400/30 text-red-600 dark:text-red-300 text-sm">
                {formError}
              </div>
            )}
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1.5 flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5" /> Supplier *
                </label>
                <SmartNativeSelect
                  value={poForm.supplier_id}
                  onChange={(e) => {
                    const sid = e.target.value;
                    const s = suppliers.find(x => x.id === sid);
                    setPOForm(prev => ({
                      ...prev,
                      supplier_id: sid,
                      vendor_name: s?.name || '',
                      vendor_contact: s?.phone || prev.vendor_contact,
                      vendor_address: s?.address || prev.vendor_address,
                    }));
                    // Harga bisa berbeda per supplier → segarkan saran harga
                    poForm.items.forEach(it => {
                      if (it.material_id) fetchPriceHint(it.id, it.material_id, sid);
                    });
                  }}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="po-form-supplier"
                >
                  <option value="">Pilih supplier dari master</option>
                  {suppliers.map(s => (
                    <option key={s.id} value={s.id}>{`${s.code} — ${s.name}`}</option>
                  ))}
                </SmartNativeSelect>
                {suppliers.length === 0 && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
                    Master Supplier masih kosong. Buka menu Master Supplier untuk menambah
                    atau menarik data supplier dari dokumen lama.
                  </p>
                )}
                {selectedSupplier && (
                  <p className="text-[11px] text-muted-foreground mt-1" data-testid="po-form-supplier-info">
                    Termin {selectedSupplier.payment_terms || '-'} · {selectedSupplier.currency || 'IDR'}
                    {selectedSupplier.lead_time_days ? ` · lead time ${selectedSupplier.lead_time_days} hari` : ''}
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">Kontak Supplier</label>
                <GlassInput
                  value={poForm.vendor_contact}
                  onChange={e => setPOForm({ ...poForm, vendor_contact: e.target.value })}
                  placeholder="0812-3456-7890"
                  data-testid="po-form-vendor-contact"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5">Alamat Supplier</label>
              <textarea
                value={poForm.vendor_address}
                onChange={e => setPOForm({ ...poForm, vendor_address: e.target.value })}
                placeholder="Jl. Raya Industri No. 123, Bandung"
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
                rows="2"
                data-testid="po-form-vendor-address"
              />
            </div>

            <DocNumberField
              policy={numPolicy}
              value={poNumber}
              onChange={setPoNumber}
              label="Nomor PO"
              testId="po-number"
              className="mb-3"
            />

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Tanggal PO</label>
                <GlassInput
                  type="date"
                  value={poForm.po_date}
                  onChange={e => setPOForm({ ...poForm, po_date: e.target.value })}
                  data-testid="po-form-date"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">Estimasi Terima</label>
                <GlassInput
                  type="date"
                  value={poForm.expected_delivery_date}
                  onChange={e => setPOForm({ ...poForm, expected_delivery_date: e.target.value })}
                  data-testid="po-form-expected-delivery"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5">Catatan</label>
              <textarea
                value={poForm.notes}
                onChange={e => setPOForm({ ...poForm, notes: e.target.value })}
                placeholder="Catatan tambahan..."
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
                rows="2"
                data-testid="po-form-notes"
              />
            </div>

            <div className="border-t border-[var(--glass-border)] pt-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="font-semibold">Item Pesanan</h3>
                  <p className="text-[11px] text-muted-foreground">
                    Pilih satuan beli (mis. karton). Qty & harga otomatis dikonversi ke satuan dasar
                    untuk stok dan jurnal.
                  </p>
                </div>
                <Button size="sm" onClick={addItem} data-testid="po-form-add-item">
                  <Plus className="w-3 h-3 mr-1" /> Tambah Item
                </Button>
              </div>

              {poForm.items.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">Belum ada item. Klik &quot;Tambah Item&quot; untuk menambahkan.</p>
              )}

              {poForm.items.map((item, idx) => {
                const opt = uomMap[item.material_id];
                const f = factorOf(item);
                const hint = priceHint[item.id];
                const qtyBase = (Number(item.qty_input) || 0) * f;
                const costBase = f ? (Number(item.unit_cost_input) || 0) / f : Number(item.unit_cost_input) || 0;
                return (
                  <div key={item.id} className="mb-3 pb-3 border-b border-[var(--glass-border)] last:border-0">
                    <div className="grid grid-cols-12 gap-2 items-end">
                      <div className="col-span-12 md:col-span-4">
                        {idx === 0 && <label className="block text-xs font-medium mb-1">Material / Keterangan</label>}
                        <SmartNativeSelect
                          value={item.material_id}
                          onChange={e => pickMaterial(item.id, e.target.value)}
                          className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                          data-testid={`po-form-item-material-${idx}`}
                        >
                          <option value="">Item bebas (jasa / non-master)</option>
                          {materials.map(m => (
                            <option key={m.id} value={m.id}>{`${m.code} - ${m.name}`}</option>
                          ))}
                        </SmartNativeSelect>
                        {!item.material_id && (
                          <GlassInput
                            className="mt-1"
                            value={item.description}
                            onChange={e => updateItem(item.id, 'description', e.target.value)}
                            placeholder="Keterangan item, mis. Jasa kirim ekspedisi"
                            data-testid={`po-form-item-desc-${idx}`}
                          />
                        )}
                      </div>
                      <div className="col-span-4 md:col-span-2">
                        {idx === 0 && <label className="block text-xs font-medium mb-1">Satuan Beli</label>}
                        {item.material_id && opt ? (
                          <SmartNativeSelect
                            value={item.uom}
                            onChange={e => updateItem(item.id, 'uom', e.target.value)}
                            className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                            data-testid={`po-form-item-uom-${idx}`}
                          >
                            {(opt.units || []).map(u => (
                              <option key={u.unit} value={u.unit}>{u.unit}</option>
                            ))}
                          </SmartNativeSelect>
                        ) : (
                          <GlassInput
                            value={item.uom}
                            onChange={e => updateItem(item.id, 'uom', e.target.value)}
                            placeholder="pcs"
                            data-testid={`po-form-item-uom-${idx}`}
                          />
                        )}
                      </div>
                      <div className="col-span-4 md:col-span-2">
                        {idx === 0 && <label className="block text-xs font-medium mb-1">Qty</label>}
                        <GlassInput
                          type="number"
                          step="0.01"
                          value={item.qty_input}
                          onChange={e => updateItem(item.id, 'qty_input', parseFloat(e.target.value) || 0)}
                          placeholder="0"
                          className="text-right"
                          data-testid={`po-form-item-qty-${idx}`}
                        />
                      </div>
                      <div className="col-span-4 md:col-span-2">
                        {idx === 0 && <label className="block text-xs font-medium mb-1">Harga / satuan</label>}
                        <GlassInput
                          type="number"
                          step="0.01"
                          value={item.unit_cost_input}
                          onChange={e => updateItem(item.id, 'unit_cost_input', parseFloat(e.target.value) || 0)}
                          placeholder="0"
                          className="text-right"
                          data-testid={`po-form-item-cost-${idx}`}
                        />
                      </div>
                      <div className="col-span-8 md:col-span-1">
                        {idx === 0 && <label className="block text-xs font-medium mb-1">Total</label>}
                        <div className="h-10 flex items-center justify-end px-1 text-xs font-mono text-muted-foreground"
                             data-testid={`po-form-item-total-${idx}`}>
                          {((Number(item.qty_input) || 0) * (Number(item.unit_cost_input) || 0)).toLocaleString('id-ID', { maximumFractionDigits: 0 })}
                        </div>
                      </div>
                      <div className="col-span-4 md:col-span-1">
                        {idx === 0 && <div className="h-4 mb-1" />}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeItem(item.id)}
                          data-testid={`po-form-item-remove-${idx}`}
                        >
                          <Trash2 className="w-4 h-4 text-red-700 dark:text-red-400" />
                        </Button>
                      </div>
                    </div>

                    {/* Pratinjau konversi + saran harga dari daftar harga supplier */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5">
                      {item.material_id && opt && item.uom && item.uom !== opt.base_unit && (
                        <span className="text-[11px] text-muted-foreground" data-testid={`po-form-item-preview-${idx}`}>
                          1 {item.uom} = {f.toLocaleString('id-ID', { maximumFractionDigits: 4 })} {opt.base_unit} ⇒{' '}
                          <span className="font-semibold text-foreground">
                            {qtyBase.toLocaleString('id-ID', { maximumFractionDigits: 4 })} {opt.base_unit}
                          </span>{' '}
                          @ Rp {costBase.toLocaleString('id-ID', { maximumFractionDigits: 2 })}/{opt.base_unit}
                        </span>
                      )}
                      {hint && (
                        <button
                          type="button"
                          onClick={() => {
                            updateItem(item.id, 'unit_cost_input', Number(hint.price));
                            if ((uomMap[item.material_id]?.units || []).some(u => u.unit === hint.uom)) {
                              updateItem(item.id, 'uom', hint.uom);
                            }
                            toast.success(`Harga diisi dari daftar harga ${hint.supplier_name}`);
                          }}
                          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-[hsl(var(--primary)/0.3)] bg-[hsl(var(--primary)/0.1)] text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary)/0.18)]"
                          data-testid={`po-form-item-price-hint-${idx}`}
                        >
                          <Tag className="w-3 h-3" />
                          Harga {hint.supplier_name}: Rp {Number(hint.price).toLocaleString('id-ID')} / {hint.uom}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}

              {poForm.items.length > 0 && (
                <div className="flex justify-end items-baseline gap-3 pt-2">
                  <span className="text-sm text-muted-foreground">Total nilai PO</span>
                  <span className="text-lg font-bold tabular-nums" data-testid="po-form-grand-total">
                    Rp {formTotal.toLocaleString('id-ID', { maximumFractionDigits: 0 })}
                  </span>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-[var(--glass-border)]">
              <Button variant="secondary" onClick={() => setCreateModal(false)}>Batal</Button>
              <Button onClick={createPO} disabled={saving} data-testid="po-form-submit">
                {saving ? 'Menyimpan...' : 'Simpan Draft PO'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Detail PO Modal */}
      {detailModal && selectedPO && (
        <Modal onClose={() => setDetailModal(false)} title={`Detail PO: ${selectedPO.po_number}`} size="2xl">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--glass-border)]">
              <div>
                <StatusBadge status={selectedPO.status} />
                {selectedPO.rejected_reason && (
                  <p className="text-xs text-red-600 dark:text-red-300 mt-1">Alasan ditolak: {selectedPO.rejected_reason}</p>
                )}
                {selectedPO.cancelled_reason && (
                  <p className="text-xs text-foreground/80 mt-1">Alasan dibatalkan: {selectedPO.cancelled_reason}</p>
                )}
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <div>Dibuat: {new Date(selectedPO.created_at).toLocaleString('id-ID')}</div>
                <div>Oleh: {selectedPO.created_by_name}</div>
              </div>
            </div>

            {/* ── Rantai persetujuan PO (2026-08-07) ───────────────────────
                Dulu tidak ada apa pun di sini: PO hanya punya satu langkah
                "approve" tanpa tahap, tanpa siapa & kapan. Sekarang approver
                bisa melihat tahap ke berapa dari berapa, siapa yang sudah
                memutuskan, dan siapa giliran berikutnya. */}
            {Array.isArray(selectedPO.chain) && selectedPO.chain.length > 0 && (
              <div className="rounded-xl border border-[var(--glass-border)] p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-semibold text-foreground">Rantai Persetujuan</div>
                  <div className="text-xs text-muted-foreground">
                    {selectedPO.total_stages} tahap untuk nilai Rp {(selectedPO.total_value || 0).toLocaleString('id-ID')}
                  </div>
                </div>
                <div className="space-y-2" data-testid="po-approval-stepper">
                  {selectedPO.chain.map((s) => (
                    <div key={s.stage}
                         className={`flex items-start gap-3 rounded-lg px-3 py-2 border ${
                           s.done ? 'bg-emerald-50 dark:bg-emerald-400/10 border-emerald-300/30'
                           : s.current ? 'bg-amber-50 dark:bg-amber-400/10 border-amber-300/40'
                           : 'bg-foreground/5 border-transparent'}`}>
                      <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                        s.done ? 'bg-emerald-600 text-white'
                        : s.current ? 'bg-amber-500 text-white' : 'bg-foreground/15 text-muted-foreground'}`}>
                        {s.order}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-foreground">
                          {s.label}
                          {s.current && (
                            <span className="ml-2 text-[10px] font-normal text-amber-700 dark:text-amber-400">
                              Menunggu sekarang
                            </span>
                          )}
                          {s.override && (
                            <span className="ml-2 text-[10px] font-normal text-violet-700 dark:text-violet-400">
                              override admin
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {s.done
                            ? `${s.actor_name}${s.timestamp ? ` — ${new Date(s.timestamp).toLocaleString('id-ID')}` : ''}`
                            : `Menunggu ${s.role_hint}`}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {selectedPO.next_approver_label && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Berikutnya setelah tahap ini: {selectedPO.next_approver_label}
                  </p>
                )}
                {selectedPO.status === 'pending_approval' && !selectedPO.can_approve && selectedPO.blocked_reason && (
                  <p className="mt-2 rounded-lg bg-amber-50 dark:bg-amber-400/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300"
                     data-testid="po-detail-blocked">
                    {selectedPO.blocked_reason}
                  </p>
                )}
                {selectedPO.exceeds_pr_value && (
                  <p className="mt-2 rounded-lg bg-red-50 dark:bg-red-400/10 px-3 py-2 text-xs text-red-700 dark:text-red-300"
                     data-testid="po-detail-exceeds">
                    Nilai PO ini <strong>Rp {(selectedPO.total_value || 0).toLocaleString('id-ID')}</strong> melebihi
                    nilai permintaan yang sudah disetujui
                    (<strong>Rp {(selectedPO.pr_approved_value || 0).toLocaleString('id-ID')}</strong>
                    {selectedPO.from_pr_number ? ` pada ${selectedPO.from_pr_number}` : ''}).
                    Karena itu PO ini wajib melewati rantai persetujuan penuh.
                  </p>
                )}
                {Array.isArray(selectedPO.approval_steps) && selectedPO.approval_steps.length > 0 && (
                  <div className="mt-3 border-t border-[var(--glass-border)] pt-2">
                    <div className="text-xs font-semibold text-foreground mb-1">Riwayat</div>
                    {selectedPO.approval_steps.map((s, i) => (
                      <div key={s.id || i} className="flex flex-wrap items-baseline gap-2 text-xs py-0.5">
                        <span className="text-muted-foreground tabular-nums">
                          {s.timestamp ? new Date(s.timestamp).toLocaleString('id-ID') : '-'}
                        </span>
                        <span className="font-medium text-foreground">{s.action_label || s.action}</span>
                        <span className="text-muted-foreground">— {s.actor_name}</span>
                        {s.comment && <span className="text-muted-foreground/80 italic">“{s.comment}”</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-muted-foreground mb-1">Supplier</div>
                <div className="font-medium">{selectedPO.supplier_name || selectedPO.vendor_name}</div>
                {selectedPO.supplier_code && (
                  <div className="text-xs font-mono text-muted-foreground">{selectedPO.supplier_code}</div>
                )}
                {selectedPO.vendor_contact && <div className="text-xs text-muted-foreground">{selectedPO.vendor_contact}</div>}
                {selectedPO.vendor_address && <div className="text-xs text-muted-foreground mt-1">{selectedPO.vendor_address}</div>}
                {selectedPO.supplier?.npwp && (
                  <div className="text-xs text-muted-foreground mt-1">NPWP: {selectedPO.supplier.npwp}</div>
                )}
                {selectedPO.payment_terms && (
                  <div className="text-xs text-muted-foreground mt-1">
                    Termin: {selectedPO.payment_terms} · {selectedPO.currency || 'IDR'}
                  </div>
                )}
                {selectedPO.supplier?.bank_accounts?.[0] && (
                  <div className="text-xs font-mono text-muted-foreground mt-1">
                    {selectedPO.supplier.bank_accounts[0].bank_name} {selectedPO.supplier.bank_accounts[0].account_number}
                  </div>
                )}
              </div>
              <div>
                <div className="text-muted-foreground mb-1">Tanggal</div>
                <div>PO: {new Date(selectedPO.po_date).toLocaleDateString('id-ID')}</div>
                {selectedPO.expected_delivery_date && (
                  <div className="text-xs">Estimasi Terima: {new Date(selectedPO.expected_delivery_date).toLocaleDateString('id-ID')}</div>
                )}
                {selectedPO.from_pr_number && (
                  <div className="text-xs mt-1">Dari permintaan: <span className="font-mono">{selectedPO.from_pr_number}</span></div>
                )}
              </div>
            </div>

            {selectedPO.notes && (
              <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <div className="text-xs text-muted-foreground mb-1">Catatan</div>
                <div className="text-sm">{selectedPO.notes}</div>
              </div>
            )}

            <div>
              <h3 className="font-semibold mb-2">Items ({selectedPO.items?.length || 0})</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr className="text-left text-muted-foreground text-xs">
                      <th className="pb-2">Item</th>
                      <th className="pb-2 text-right">Dipesan</th>
                      <th className="pb-2 text-right">Diterima</th>
                      <th className="pb-2 text-right">Harga</th>
                      <th className="pb-2 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody data-testid="po-detail-items">
                    {selectedPO.items?.map((it, idx) => {
                      const f = Number(it.uom_factor || 1) || 1;
                      const hasPack = it.uom && it.base_uom && it.uom !== it.base_uom && f !== 1;
                      return (
                        <tr key={it.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                          <td className="py-2">
                            {/* 2026-08-07 — dulu baris utama adalah KODE material,
                                sehingga item bebas (jasa / non-master) tampil
                                berjudul "Item bebas" dan nama barangnya turun ke
                                baris kecil. Approver yang memutuskan uang perlu
                                melihat APA yang dibeli lebih dulu, baru kodenya. */}
                            <div className="font-medium">
                              {it.material_name || it.description || 'Item tanpa nama'}
                            </div>
                            <div className="text-xs text-muted-foreground font-mono">
                              {it.material_code || (it.material_linked === false ? 'Item bebas (non-master)' : '')}
                            </div>
                            {hasPack && (
                              <div className="text-[11px] text-[hsl(var(--primary))]">
                                1 {it.uom} = {Number(f).toLocaleString('id-ID', { maximumFractionDigits: 4 })} {it.base_uom}
                              </div>
                            )}
                          </td>
                          <td className="py-2 text-right font-mono">
                            <div>{Number(it.qty_ordered || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 })} {it.base_uom || it.unit}</div>
                            {hasPack && (
                              <div className="text-[11px] text-muted-foreground">
                                ({Number(it.qty_input || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 })} {it.uom})
                              </div>
                            )}
                          </td>
                          <td className="py-2 text-right font-mono">
                            <span className={Number(it.qty_received) >= Number(it.qty_ordered) ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}>
                              {Number(it.qty_received || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 })} {it.base_uom || it.unit}
                            </span>
                            {Number(it.qty_remaining) > 0 && (
                              <div className="text-[11px] text-muted-foreground">
                                sisa {Number(it.qty_remaining).toLocaleString('id-ID', { maximumFractionDigits: 4 })}
                              </div>
                            )}
                          </td>
                          <td className="py-2 text-right font-mono">
                            <div>Rp {Number(it.unit_cost || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 })}</div>
                            <div className="text-[11px] text-muted-foreground">/ {it.base_uom || it.unit}</div>
                            {hasPack && (
                              <div className="text-[11px] text-muted-foreground">
                                (Rp {Number(it.unit_cost_input || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 })} / {it.uom})
                              </div>
                            )}
                          </td>
                          <td className="py-2 text-right font-mono">
                            Rp {Number(it.subtotal ?? (it.qty_ordered * it.unit_cost)).toLocaleString('id-ID', { maximumFractionDigits: 0 })}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot className="border-t-2 border-[var(--glass-border)] font-semibold">
                    <tr>
                      <td colSpan="4" className="pt-2 text-right">Total Nilai PO:</td>
                      <td className="pt-2 text-right font-mono">
                        Rp {(selectedPO.items?.reduce((sum, it) => sum + (it.qty_ordered * it.unit_cost), 0) || 0).toLocaleString('id-ID')}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* P1.C: GR Audit Trail (Goods Receipts linked to this PO) */}
            {(selectedPO._grs?.length || 0) > 0 && (
              <div data-testid="po-detail-grs">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <TruckIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  Goods Receipts ({selectedPO._grs.length})
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-[var(--glass-border)]">
                      <tr className="text-left text-muted-foreground text-xs">
                        <th className="pb-2">No. GR</th>
                        <th className="pb-2">Tanggal</th>
                        <th className="pb-2">Penerima</th>
                        <th className="pb-2 text-right">Total Items</th>
                        <th className="pb-2 text-right">Net Diterima</th>
                        <th className="pb-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPO._grs.map((gr, idx) => (
                        <tr key={gr.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`} data-testid={`po-gr-row-${gr.id}`}>
                          <td className="py-2 font-mono text-xs">{gr.receipt_number}</td>
                          <td className="py-2 text-xs">{gr.created_at ? new Date(gr.created_at).toLocaleString('id-ID') : '-'}</td>
                          <td className="py-2 text-xs">{gr.received_by || '-'}</td>
                          <td className="py-2 text-right">{gr.items_count}</td>
                          <td className="py-2 text-right font-mono text-emerald-600 dark:text-emerald-400">{gr.total_net}</td>
                          <td className="py-2">
                            <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                              gr.status === 'received' ? 'bg-green-50 dark:bg-green-400/15 border-green-300/25 text-green-600 dark:text-green-300' :
                              gr.status === 'draft' ? 'bg-muted dark:bg-slate-400/15 border-border/25 text-foreground/70' :
                              'bg-amber-50 dark:bg-amber-400/15 border-amber-300/25 text-amber-600 dark:text-amber-300'
                            } border`}>
                              {gr.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="flex justify-between gap-2 pt-4 border-t border-[var(--glass-border)]">
              <div>
                {(selectedPO.status === 'draft' || selectedPO.status === 'rejected') && selectedPO.can_submit !== false && (
                  <Button onClick={() => { setDetailModal(false); openSubmitModal(selectedPO); }}
                          data-testid="po-detail-submit">
                    <Send className="w-4 h-4 mr-1.5" />
                    {selectedPO.status === 'rejected' ? 'Ajukan Ulang' : 'Ajukan Approval'}
                  </Button>
                )}
                {selectedPO.status === 'pending_approval' && selectedPO.can_approve && (
                  <>
                    <Button onClick={() => { setDetailModal(false); openApproveModal(selectedPO); }}
                            className="mr-2" data-testid="po-detail-approve">
                      <CheckCircle2 className="w-4 h-4 mr-1.5" />
                      {selectedPO.stage_label ? `Setujui — ${selectedPO.stage_label}` : 'Setujui'}
                    </Button>
                    <Button variant="secondary" onClick={() => { setDetailModal(false); openRejectModal(selectedPO); }}
                            data-testid="po-detail-reject">
                      <XCircle className="w-4 h-4 mr-1.5" /> Tolak
                    </Button>
                  </>
                )}
                {(selectedPO.status === 'approved' || selectedPO.status === 'partially_received') && (
                  <Button onClick={() => createGRFromPO(selectedPO)}>
                    <TruckIcon className="w-4 h-4 mr-1.5" /> Buat Goods Receipt
                  </Button>
                )}
              </div>
              <Button variant="secondary" onClick={() => setDetailModal(false)}>Tutup</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Submit Modal */}
      {submitModal && selectedPO && (
        <Modal onClose={() => setSubmitModal(false)} title="Ajukan PO untuk Approval">
          <div className="space-y-4">
            <p>Ajukan PO <strong>{selectedPO.po_number}</strong> untuk persetujuan?</p>
            <p className="text-sm text-muted-foreground">
              Setelah diajukan, status PO menjadi <strong>Menunggu Persetujuan</strong> dan menunggu approver menyetujui sebelum dapat dibuatkan Goods Receipt.
            </p>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="secondary" onClick={() => setSubmitModal(false)} data-testid="po-submit-cancel-btn">Batal</Button>
              <Button onClick={submitPO} disabled={saving} data-testid="po-submit-confirm-btn">
                {saving ? 'Memproses...' : 'Ya, Ajukan'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Approve Modal */}
      {approveModal && selectedPO && (
        <Modal onClose={() => setApproveModal(false)} title="Konfirmasi Persetujuan">
          <div className="space-y-4">
            <p>
              Setujui PO <strong>{selectedPO.po_number}</strong> senilai{' '}
              <strong>Rp {(selectedPO.total_value || 0).toLocaleString('id-ID')}</strong>?
            </p>
            {/* Tahap yang SEDANG disetujui harus jelas — approver perlu tahu ini
                langkah ke berapa dan siapa yang harus memutuskan setelahnya. */}
            {selectedPO.stage_label && (
              <div className="rounded-lg bg-amber-50 dark:bg-amber-400/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">
                Anda menyetujui tahap <strong>{selectedPO.stage_label}</strong>
                {selectedPO.total_stages ? ` (${selectedPO.stage_order} dari ${selectedPO.total_stages})` : ''}.
                {selectedPO.next_stage
                  ? ` Setelah ini masih menunggu ${selectedPO.next_approver_label}.`
                  : ' Ini tahap terakhir — PO langsung disetujui penuh.'}
              </div>
            )}
            {selectedPO.is_override && selectedPO.override_note && (
              <div className="rounded-lg bg-violet-50 dark:bg-violet-400/10 px-3 py-2 text-sm text-violet-800 dark:text-violet-300"
                   data-testid="po-override-note">
                {selectedPO.override_note}
              </div>
            )}
            {selectedPO.exceeds_pr_value && (
              <div className="rounded-lg bg-red-50 dark:bg-red-400/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                Perhatian: nilai PO ini melebihi nilai permintaan yang sudah disetujui
                (Rp {(selectedPO.pr_approved_value || 0).toLocaleString('id-ID')}).
              </div>
            )}
            <div>
              <label className="block text-sm font-medium mb-1.5">Catatan persetujuan (opsional)</label>
              <textarea
                value={approveNote}
                onChange={e => setApproveNote(e.target.value)}
                placeholder="Mis. harga sudah dicek terhadap daftar harga supplier"
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
                rows="2"
                data-testid="po-approve-note"
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="secondary" onClick={() => setApproveModal(false)}>Batal</Button>
              <Button onClick={approvePO} disabled={saving} data-testid="po-approve-confirm-btn">
                {saving ? 'Memproses...' : (selectedPO.stage_label ? `Setujui — ${selectedPO.stage_label}` : 'Ya, Setujui')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reject Modal */}
      {rejectModal && selectedPO && (
        <Modal onClose={() => setRejectModal(false)} title="Tolak Purchase Order">
          <div className="space-y-4">
            <p>Anda akan menolak PO <strong>{selectedPO.po_number}</strong>.</p>
            <div>
              <label className="block text-sm font-medium mb-1.5">Alasan Penolakan *</label>
              <textarea
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                placeholder="Masukkan alasan penolakan..."
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
                rows="3"
                data-testid="po-reject-reason"
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="secondary" onClick={() => setRejectModal(false)}>Batal</Button>
              <Button variant="destructive" onClick={rejectPO} disabled={saving || !rejectReason.trim()}>
                {saving ? 'Memproses...' : 'Tolak PO'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Cancel Modal */}
      {cancelModal && selectedPO && (
        <Modal onClose={() => setCancelModal(false)} title="Batalkan Purchase Order">
          <div className="space-y-4">
            <p>Anda akan membatalkan PO <strong>{selectedPO.po_number}</strong>.</p>
            <div>
              <label className="block text-sm font-medium mb-1.5">Alasan Pembatalan *</label>
              <textarea
                value={cancelReason}
                onChange={e => setCancelReason(e.target.value)}
                placeholder="Masukkan alasan pembatalan..."
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
                rows="3"
                data-testid="po-cancel-reason"
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="secondary" onClick={() => setCancelModal(false)}>Batal</Button>
              <Button variant="destructive" onClick={cancelPO} disabled={saving || !cancelReason.trim()}>
                {saving ? 'Memproses...' : 'Batalkan PO'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* U2 — Bulk PO CSV Import Modal */}
      {bulkModal && (
        <Modal onClose={() => { setBulkModal(false); setBulkRows([]); setBulkErrors([]); }} title="Import PO dari CSV" size="lg">
          <div className="space-y-4" data-testid="bulk-po-modal">
            {/* Template download */}
            <div className="flex items-center gap-2 p-3 bg-sky-100 dark:bg-sky-500/10 rounded-lg border border-sky-300 dark:border-sky-500/20">
              <Download size={14} className="text-sky-600 dark:text-sky-400 flex-shrink-0" />
              <span className="text-xs text-sky-600 dark:text-sky-300 flex-1">Download template CSV untuk format yang benar</span>
              <button
                onClick={() => {
                  const ws = XLSX.utils.json_to_sheet([
                    { vendor_name: 'PT Supplier A', material_code: 'ACC-BTN-001', qty_ordered: 100, unit_cost: 500, unit: 'pcs' },
                    { vendor_name: 'PT Supplier A', material_code: 'YRN-W-001',   qty_ordered: 50,  unit_cost: 12000, unit: 'kg' },
                  ]);
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Template PO');
                  XLSX.writeFile(wb, 'template-bulk-po.xlsx');
                }}
                className="text-xs text-sky-600 dark:text-sky-400 hover:text-sky-600 dark:text-sky-300 px-2 py-1 bg-sky-100 dark:bg-sky-500/20 rounded border border-sky-400 dark:border-sky-500/30"
                data-testid="po-template-download"
              >
                <Download size={12} className="inline mr-1" /> Template Excel
              </button>
            </div>

            {/* Default vendor */}
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Vendor Default (opsional — bisa di-override per baris CSV)</label>
              <input
                value={bulkVendor}
                onChange={e => setBulkVendor(e.target.value)}
                placeholder="Nama vendor..."
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="bulk-vendor-input"
              />
            </div>

            {/* File picker */}
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Upload File Excel/CSV</label>
              <input
                ref={csvRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const buf = await file.arrayBuffer();
                  const wb = XLSX.read(buf);
                  const ws = wb.Sheets[wb.SheetNames[0]];
                  const rows = XLSX.utils.sheet_to_json(ws, { defval: '' });
                  setBulkRows(rows);
                  setBulkErrors([]);
                }}
              />
              <button
                onClick={() => csvRef.current?.click()}
                className="flex items-center gap-2 text-sm text-foreground/70 hover:text-foreground px-4 py-2 bg-foreground/5 rounded-lg border border-dashed border-foreground/20 hover:border-foreground/40 transition-colors w-full justify-center"
                data-testid="bulk-file-picker"
              >
                <Upload size={15} /> Pilih file Excel/CSV
              </button>
            </div>

            {/* Preview */}
            {bulkRows.length > 0 && (
              <div>
                <p className="text-xs text-foreground/60 mb-2">{bulkRows.length} baris terdeteksi:</p>
                <div className="overflow-x-auto max-h-40 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                  <table className="w-full text-xs">
                    <thead className="bg-foreground/5 sticky top-0">
                      <tr>{Object.keys(bulkRows[0]).map(k => <th key={k} className="px-2 py-1.5 text-left text-foreground/50 font-medium">{k}</th>)}</tr>
                    </thead>
                    <tbody>
                      {bulkRows.slice(0, 8).map((r, i) => (
                        <tr key={i} className="border-t border-foreground/5">
                          {Object.values(r).map((v, j) => <td key={j} className="px-2 py-1 text-foreground/70">{String(v)}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {bulkErrors.length > 0 && (
                  <div className="mt-2 p-2 bg-red-100 dark:bg-red-500/10 rounded-lg border border-red-300 dark:border-red-500/20 text-xs text-red-600 dark:text-red-300 space-y-0.5">
                    {bulkErrors.map((e, i) => <div key={i}>{e}</div>)}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => { setBulkModal(false); setBulkRows([]); setBulkErrors([]); }}>Batal</Button>
              <Button
                disabled={bulkRows.length === 0 || saving}
                onClick={async () => {
                  setSaving(true);
                  try {
                    const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/rahaza/purchase-orders/bulk-import`, {
                      method: 'POST',
                      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                      body: JSON.stringify({ vendor_name: bulkVendor, rows: bulkRows }),
                    });
                    const d = await r.json();
                    if (!r.ok) {
                      setBulkErrors(d.errors || [d.detail || 'Import gagal']);
                    } else {
                      toast.success(`${d.created} PO berhasil dibuat`);
                      if (d.row_errors?.length) setBulkErrors(d.row_errors);
                      else { setBulkModal(false); setBulkRows([]); setBulkErrors([]); }
                      // BUG-FIX 2026-07-25: dulu memanggil `loadList()` yang TIDAK ADA
                      // ⇒ ReferenceError setelah import sukses ⇒ tertangkap catch di
                      // bawah sehingga user melihat toast "Gagal import PO" padahal PO
                      // BERHASIL dibuat, dan daftar tidak pernah ter-refresh.
                      fetchList();
                    }
                  } catch {
                    toast.error('Gagal import PO');
                  } finally {
                    setSaving(false);
                  }
                }}
                data-testid="bulk-import-submit"
              >
                {saving ? 'Importing...' : `Import ${bulkRows.length} Baris`}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
