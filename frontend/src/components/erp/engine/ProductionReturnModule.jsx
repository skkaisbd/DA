
import { useState, useEffect } from 'react';
import { Plus, Eye, Pencil, Trash2, X, RotateCcw, Download } from 'lucide-react';
import { toast } from 'sonner';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import SearchableSelect from './SearchableSelect';
import { apiGet, apiPost, apiPut, apiDelete, apiFetch } from '../../../lib/api';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from '../docnum/DocNumberField';

const STATUS_OPTIONS = ['Repair Needed', 'In Repair', 'Completed', 'Shipped Back'];
const DEFECT_TYPES = ['Jahitan Longgar', 'Warna Pudar', 'Ukuran Tidak Sesuai', 'Material Rusak', 'Kancing Copot', 'Resleting Rusak', 'Noda/Kotor', 'Lainnya'];
const RETURN_REASONS = ['Produk Cacat', 'Ukuran Tidak Sesuai', 'Warna Tidak Sesuai', 'Kualitas Tidak Memenuhi Standar', 'Kerusakan Pengiriman', 'Lainnya'];

const STATUS_COLORS = {
  'Repair Needed': 'bg-red-100 text-red-700',
  'In Repair': 'bg-amber-100 text-amber-700',
  'Completed': 'bg-blue-100 text-blue-700',
  'Shipped Back': 'bg-emerald-100 text-emerald-700',
};

export default function ProductionReturnModule({ userRole }) {
  const [returns, setReturns] = useState([]);
  const [pos, setPOs] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [statusTarget, setStatusTarget] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  // SESI #27 — nomor retur mengikuti kebijakan Otomatis/Manual milik owner. Jenis
  // dokumen ini sebelumnya TIDAK ADA di katalog Penomoran Dokumen sama sekali.
  const numPolicy = useDocNumberPolicy('production_returns.return_number',
                                       localStorage.getItem('erp_token'));
  const [returnNumber, setReturnNumber] = useState('');
  const [form, setForm] = useState({
    customer_name: '',
    buyer_name: '',
    reference_po_id: '',
    return_date: new Date().toISOString().split('T')[0],
    return_reason: RETURN_REASONS[0],
    notes: '',
    items: []
  });

  const isSuperAdmin = userRole === 'superadmin';
  const canEdit = ['superadmin', 'admin'].includes(userRole);

  useEffect(() => { fetchReturns(); fetchPOs(); }, []);

  const fetchReturns = async () => {
    try {
      const url = filterStatus ? `/production-returns?status=${filterStatus}` : '/production-returns';
      const data = await apiGet(url);
      setReturns(Array.isArray(data) ? data : []);
    } catch (e) { setReturns([]); }
  };

  const fetchPOs = async () => {
    try {
      const data = await apiGet('/production-pos');
      setPOs(Array.isArray(data) ? data : []);
    } catch (e) { setPOs([]); }
  };

  const openCreate = () => {
    setForm({
      customer_name: '', buyer_name: '',
      reference_po_id: '',
      return_date: new Date().toISOString().split('T')[0],
      return_reason: RETURN_REASONS[0],
      notes: '',
      items: []
    });
    setShowModal(true);
  };

  const addItem = () => {
    setForm(f => ({
      ...f,
      items: [...f.items, { sku: '', product_name: '', size: '', color: '', serial_number: '', return_qty: '', defect_type: DEFECT_TYPES[0], repair_notes: '' }]
    }));
  };

  const removeItem = (idx) => {
    setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  };

  const updateItem = (idx, field, value) => {
    const newItems = [...form.items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    setForm(f => ({ ...f, items: newItems }));
  };

  const [poItems, setPoItems] = useState([]);
  const [loadingPoItems, setLoadingPoItems] = useState(false);

  const handlePOSelect = async (poId) => {
    const po = pos.find(p => p.id === poId);
    setForm(f => ({
      ...f,
      reference_po_id: poId,
      customer_name: po?.customer_name || f.customer_name,
      items: []
    }));
    
    if (!poId) { setPoItems([]); return; }
    
    // Fetch PO items with production data
    setLoadingPoItems(true);
    try {
      const data = await apiGet(`/po-items-produced?po_id=${poId}`);
      setPoItems(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch PO items:', e);
      setPoItems([]);
    } finally {
      setLoadingPoItems(false);
    }
  };

  const addItemFromPO = (poItem) => {
    // Check if item already added
    if (form.items.some(i => i.po_item_id === poItem.id)) {
      toast.warning('Item ini sudah ditambahkan ke daftar retur');
      return;
    }
    setForm(f => ({
      ...f,
      items: [...f.items, {
        po_item_id: poItem.id,
        sku: poItem.sku || '',
        product_name: poItem.product_name || '',
        size: poItem.size || '',
        color: poItem.color || '',
        serial_number: poItem.serial_number || '',
        return_qty: '',
        max_returnable: poItem.max_returnable || 0,
        total_produced: poItem.total_produced || 0,
        total_shipped: poItem.total_shipped || 0,
        defect_type: DEFECT_TYPES[0],
        repair_notes: ''
      }]
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.items.length === 0) { toast.error('Tambahkan minimal 1 item retur'); return; }
    const payload = {
      ...form,
      ...docNumberPayload(numPolicy, 'return_number', returnNumber),
      items: form.items.map(it => ({ ...it, return_qty: Number(it.return_qty) || 0 }))
    };
    try {
      const data = await apiPost('/production-returns', payload);
      toast.success(`Retur ${data.return_number || ''} berhasil dibuat`);
      setShowModal(false);
      fetchReturns();
    } catch (err) { toast.error(err.message || 'Gagal membuat retur'); }
  };

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/production-returns/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
    } catch (e) { toast.error(e.message || 'Gagal memuat detail'); }
  };

  const openStatusUpdate = (row) => {
    setStatusTarget({ ...row });
    setShowStatusModal(true);
  };

  const handleStatusUpdate = async (e) => {
    e.preventDefault();
    try {
      await apiPut(`/production-returns/${statusTarget.id}`, { status: statusTarget.status, notes: statusTarget.notes });
      setShowStatusModal(false);
      fetchReturns();
      if (showDetail && detailData?.id === statusTarget.id) {
        openDetail(statusTarget);
      }
    } catch (e) { toast.error(e.message || 'Gagal update status'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/production-returns/${confirmDelete.id}`);
      setConfirmDelete(null);
      fetchReturns();
    } catch (e) { toast.error(e.message || 'Gagal menghapus retur'); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  const poOptions = pos.map(p => ({
    value: p.id,
    label: `${p.po_number} – ${p.vendor_name || 'No Vendor'} – ${fmtDate(p.po_date)}`,
    sub: p.customer_name
  }));

  const downloadPDF = async (row) => {
    try {
      const res = await apiFetch(`/export-pdf?type=production-return&id=${row.id}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Retur-${row.return_number || row.id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } else { toast.error('Gagal mengunduh PDF'); }
    } catch (e) { toast.error('Error: ' + e.message); }
  };

  const [expandedRows, setExpandedRows] = useState({});
  const toggleExpand = (id) => setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));

  const columns = [
    { key: 'return_number', label: 'No. Retur', render: v => <span className="font-bold text-red-700 font-mono">{v}</span> },
    { key: 'customer_name', label: 'Customer / Pembeli' },
    { key: 'reference_po_number', label: 'Ref. PO', render: v => v ? <span className="text-xs text-blue-700 font-medium">{v}</span> : <span className="text-muted-foreground/70">-</span> },
    { key: 'total_return_qty', label: 'Detail Item', render: (v, row) => (
      <button onClick={(e) => { e.stopPropagation(); toggleExpand(row.id); }}
        className="flex items-center gap-1 px-2 py-0.5 bg-red-50 text-red-700 text-xs rounded-full font-medium hover:bg-red-100 transition-colors border border-red-200">
        {expandedRows[row.id] ? '▼' : '▶'} {v?.toLocaleString('id-ID')} pcs
      </button>
    )},
    { key: 'return_date', label: 'Tgl. Retur', render: v => fmtDate(v) },
    { key: 'return_reason', label: 'Alasan', render: v => <span className="text-xs">{v}</span> },
    { key: 'status', label: 'Status', render: v => (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[v] || 'bg-muted text-foreground/90'}`}>{v}</span>
    )},
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openDetail(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail"><Eye className="w-4 h-4" /></button>
        <button onClick={() => downloadPDF(row)} className="p-1.5 rounded hover:bg-emerald-50 text-emerald-600" title="Download PDF"><Download className="w-4 h-4" /></button>
        {canEdit && row.status !== 'Shipped Back' && (
          <button onClick={() => openStatusUpdate(row)} className="p-1.5 rounded hover:bg-amber-50 text-amber-600" title="Update Status"><Pencil className="w-4 h-4" /></button>
        )}
        {isSuperAdmin && (
          <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus"><Trash2 className="w-4 h-4" /></button>
        )}
      </div>
    )}
  ];

  const expandedRow = (row) => {
    if (!expandedRows[row.id] || !row.items || row.items.length === 0) return null;
    return (
      <div className="bg-red-50/30 border-t border-red-100 px-6 py-3">
        <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Detail Item Retur</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-red-200">
                <th className="text-left py-1.5 pr-3 text-amber-700 font-semibold">Serial/Batch</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">SKU</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">Produk</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">Size/Warna</th>
                <th className="text-right py-1.5 pr-3 text-muted-foreground font-semibold">Qty Retur</th>
                <th className="text-left py-1.5 text-muted-foreground font-semibold">Jenis Cacat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-red-100">
              {row.items.map((item, idx) => (
                <tr key={item.id || idx} className="hover:bg-red-50">
                  <td className="py-1.5 pr-3 font-mono text-amber-700 font-semibold">{item.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                  <td className="py-1.5 pr-3 font-mono text-blue-700">{item.sku || '-'}</td>
                  <td className="py-1.5 pr-3 text-foreground/90">{item.product_name}</td>
                  <td className="py-1.5 pr-3 text-muted-foreground">{item.size || '-'} / {item.color || '-'}</td>
                  <td className="py-1.5 pr-3 text-right font-bold text-red-700">{(item.return_qty || 0).toLocaleString('id-ID')} pcs</td>
                  <td className="py-1.5 text-muted-foreground">{item.defect_type || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <RotateCcw className="w-6 h-6 text-red-500" />
            Production Return
          </h1>
          <p className="text-muted-foreground text-sm mt-1">Kelola retur barang dari buyer untuk perbaikan (repair)</p>
        </div>
        {canEdit && (
          <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700">
            <Plus className="w-4 h-4" /> Catat Retur Baru
          </button>
        )}
      </div>

      {/* Info box */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <strong>ℹ️ Catatan Penting:</strong> Modul ini mencatat barang retur dari buyer untuk diperbaiki (repair). 
        Retur ini <strong>tidak mempengaruhi</strong> data PO asli atau laporan keuangan yang ada.
        Setiap retur membuat <strong>job perbaikan baru</strong> yang terpisah dari produksi normal.
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        {['', ...STATUS_OPTIONS].map(s => (
          <button key={s} onClick={() => { setFilterStatus(s); setTimeout(fetchReturns, 0); }}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${filterStatus === s ? 'bg-red-600 text-white border-red-600' : 'border-border text-muted-foreground hover:bg-muted/60'}`}>
            {s || 'Semua'}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        data={returns}
        searchKeys={['return_number', 'customer_name']}
        expandedRow={expandedRow}
        storageKey="productionReturns"
      />

      {/* Create Modal */}
      {showModal && (
        <Modal title="Catat Retur Baru" onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              ⚠️ Retur ini akan membuat catatan perbaikan baru. Data PO original tidak akan berubah.
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Nama Pembeli / Customer *</label>
                <input required className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400" value={form.customer_name} onChange={e => setForm({...form, customer_name: e.target.value})} placeholder="PT. Nama Customer" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal Retur</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400" value={form.return_date} onChange={e => setForm({...form, return_date: e.target.value})} />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Referensi PO <span className="text-xs text-muted-foreground/70">(opsional, hanya untuk referensi)</span></label>
              <SearchableSelect
                options={poOptions}
                value={form.reference_po_id}
                onChange={handlePOSelect}
                placeholder="— Pilih PO Referensi (opsional) —"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Alasan Retur *</label>
              <select required className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400" value={form.return_reason} onChange={e => setForm({...form, return_reason: e.target.value})}>
                {RETURN_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            {/* Items from PO */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-foreground/90">Item Retur *</label>
              </div>
              
              {/* PO Items available for return */}
              {form.reference_po_id && (
                <div className="mb-3">
                  {loadingPoItems ? (
                    <p className="text-sm text-muted-foreground/70 text-center py-3">Memuat item PO...</p>
                  ) : poItems.length === 0 ? (
                    <p className="text-sm text-muted-foreground/70 text-center py-3 border border-dashed border-border rounded-lg">Tidak ada item yang bisa diretur dari PO ini</p>
                  ) : (
                    <div className="border border-blue-200 rounded-lg overflow-hidden bg-blue-50/30">
                      <div className="px-3 py-2 bg-blue-100 border-b border-blue-200">
                        <p className="text-xs font-semibold text-blue-800">Pilih item dari PO untuk diretur:</p>
                      </div>
                      <div className="max-h-48 overflow-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="bg-blue-50 border-b border-blue-200">
                              <th className="text-left py-1.5 px-2 font-semibold text-blue-700">No. Seri</th>
                              <th className="text-left py-1.5 px-2 font-semibold text-blue-700">SKU</th>
                              <th className="text-left py-1.5 px-2 font-semibold text-blue-700">Produk</th>
                              <th className="text-right py-1.5 px-2 font-semibold text-blue-700">Diproduksi</th>
                              <th className="text-right py-1.5 px-2 font-semibold text-blue-700">Dikirim</th>
                              <th className="text-right py-1.5 px-2 font-semibold text-blue-700">Maks Retur</th>
                              <th className="text-center py-1.5 px-2 font-semibold text-blue-700">Aksi</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-blue-100">
                            {poItems.filter(pi => pi.total_shipped > 0).map((pi, idx) => {
                              const alreadyAdded = form.items.some(i => i.po_item_id === pi.id);
                              return (
                                <tr key={pi.id || idx} className={`hover:bg-blue-50 ${alreadyAdded ? 'opacity-50' : ''}`}>
                                  <td className="py-1.5 px-2 font-mono text-amber-700">{pi.serial_number || '-'}</td>
                                  <td className="py-1.5 px-2 font-mono text-blue-600">{pi.sku || '-'}</td>
                                  <td className="py-1.5 px-2 text-foreground/90">{pi.product_name} <span className="text-muted-foreground/70">{pi.size}/{pi.color}</span></td>
                                  <td className="py-1.5 px-2 text-right text-emerald-700 font-medium">{pi.total_produced}</td>
                                  <td className="py-1.5 px-2 text-right text-blue-700 font-medium">{pi.total_shipped}</td>
                                  <td className="py-1.5 px-2 text-right text-red-700 font-bold">{pi.max_returnable}</td>
                                  <td className="py-1.5 px-2 text-center">
                                    <button type="button" disabled={alreadyAdded || pi.max_returnable <= 0}
                                      onClick={() => addItemFromPO(pi)}
                                      className="px-2 py-0.5 text-xs rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-30 disabled:cursor-not-allowed">
                                      {alreadyAdded ? '✓' : '+ Retur'}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                            {poItems.filter(pi => pi.total_shipped > 0).length === 0 && (
                              <tr><td colSpan={7} className="py-3 text-center text-muted-foreground/70">Belum ada item yang dikirim dari PO ini</td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
              
              {!form.reference_po_id && (
                <p className="text-sm text-amber-600 italic text-center py-4 border border-dashed border-amber-200 rounded-lg bg-amber-50/30 mb-3">
                  ⬆️ Pilih PO Referensi terlebih dahulu untuk menampilkan item yang bisa diretur
                </p>
              )}

              {/* Selected return items */}
              {form.items.length === 0 && form.reference_po_id && !loadingPoItems && (
                <p className="text-sm text-muted-foreground/70 italic text-center py-4 border border-dashed border-border rounded-lg">
                  Klik tombol "+ Retur" di tabel atas untuk memilih item yang diretur
                </p>
              )}
              <div className="space-y-3">
                {form.items.map((item, idx) => (
                  <div key={idx} className="border border-red-100 rounded-xl p-3 bg-red-50/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-muted-foreground">
                        Item #{idx + 1}: <span className="text-amber-700 font-mono">{item.serial_number || '-'}</span> / <span className="text-blue-600 font-mono">{item.sku || '-'}</span> — {item.product_name}
                        <span className="text-muted-foreground/70 ml-1">({item.size}/{item.color})</span>
                      </span>
                      <button type="button" onClick={() => removeItem(idx)} className="text-red-400 hover:text-red-600"><X className="w-4 h-4" /></button>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Qty Retur * <span className="text-muted-foreground/70">(maks: {item.max_returnable || '∞'})</span></label>
                        <input required type="number" min="1" max={item.max_returnable || undefined}
                          className="w-full border border-border rounded px-2 py-1.5 text-xs" 
                          value={item.return_qty} 
                          onChange={e => updateItem(idx, 'return_qty', e.target.value)} 
                          placeholder={`1 – ${item.max_returnable || '?'}`} />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Jenis Cacat</label>
                        <select className="w-full border border-border rounded px-2 py-1.5 text-xs bg-card" value={item.defect_type} onChange={e => updateItem(idx, 'defect_type', e.target.value)}>
                          {DEFECT_TYPES.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Catatan Perbaikan</label>
                        <input className="w-full border border-border rounded px-2 py-1.5 text-xs" value={item.repair_notes} onChange={e => updateItem(idx, 'repair_notes', e.target.value)} placeholder="Deskripsi perbaikan..." />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {form.items.length > 0 && (
              <div className="bg-red-50 rounded-lg p-3 text-sm border border-red-200">
                <div className="flex justify-between text-red-700">
                  <span>Total Item: <strong>{form.items.length}</strong></span>
                  <span>Total Qty Retur: <strong>{form.items.reduce((s, i) => s + (Number(i.return_qty) || 0), 0).toLocaleString('id-ID')} pcs</strong></span>
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan Umum</label>
              <textarea rows="2" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} placeholder="Catatan tambahan..." />
            </div>

            <DocNumberField
              policy={numPolicy} value={returnNumber} onChange={setReturnNumber}
              testId="prod-return-docnum" label="Nomor Retur" />

            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700">Buat Retur</button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Status Update Modal */}
      {showStatusModal && statusTarget && (
        <Modal title={`Update Status: ${statusTarget.return_number}`} onClose={() => setShowStatusModal(false)}>
          <form onSubmit={handleStatusUpdate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Status Baru</label>
              <select required className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={statusTarget.status}
                onChange={e => setStatusTarget({...statusTarget, status: e.target.value})}>
                {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan Update</label>
              <textarea rows="3" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={statusTarget.notes || ''}
                onChange={e => setStatusTarget({...statusTarget, notes: e.target.value})}
                placeholder="Keterangan update status..." />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">Simpan</button>
              <button type="button" onClick={() => setShowStatusModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailData && (
        <Modal title={`Detail Retur: ${detailData.return_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[
                { l: 'No. Retur', v: <span className="font-bold text-red-700 font-mono">{detailData.return_number}</span> },
                { l: 'Status', v: <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[detailData.status] || ''}`}>{detailData.status}</span> },
                { l: 'Tgl. Retur', v: fmtDate(detailData.return_date) },
                { l: 'Customer/Pembeli', v: detailData.customer_name },
                { l: 'Ref. PO', v: detailData.reference_po_number || '-' },
                { l: 'Alasan Retur', v: detailData.return_reason },
                { l: 'Total Qty Retur', v: <span className="font-bold text-red-700">{detailData.total_return_qty?.toLocaleString('id-ID')} pcs</span> },
                { l: 'Dibuat Oleh', v: detailData.created_by },
              ].map(it => (
                <div key={it.l} className="bg-muted/40 rounded-lg p-3">
                  <p className="text-xs text-muted-foreground">{it.l}</p>
                  <div className="font-medium text-sm mt-0.5">{it.v}</div>
                </div>
              ))}
            </div>

            {detailData.notes && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                <strong>Catatan:</strong> {detailData.notes}
              </div>
            )}

            {detailData.items?.length > 0 && (
              <div>
                <h4 className="font-semibold text-foreground/90 mb-2">Item Retur ({detailData.items.length})</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted">
                        <th className="text-left px-3 py-2 text-xs">Produk</th>
                        <th className="text-left px-3 py-2 text-xs">SKU</th>
                        <th className="text-left px-3 py-2 text-xs text-amber-700">No. Seri</th>
                        <th className="text-left px-3 py-2 text-xs">Size/Warna</th>
                        <th className="text-right px-3 py-2 text-xs">Qty Retur</th>
                        <th className="text-right px-3 py-2 text-xs">Qty Diperbaiki</th>
                        <th className="text-left px-3 py-2 text-xs">Jenis Cacat</th>
                        <th className="text-left px-3 py-2 text-xs">Catatan Perbaikan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.items.map(item => (
                        <tr key={item.id} className="border-t border-border/60">
                          <td className="px-3 py-2">{item.product_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                          <td className="px-3 py-2 font-mono text-xs text-amber-700 font-semibold">{item.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                          <td className="px-3 py-2 text-xs">{item.size || '-'} / {item.color || '-'}</td>
                          <td className="px-3 py-2 text-right font-bold text-red-700">{item.return_qty?.toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-emerald-700">{item.repaired_qty?.toLocaleString('id-ID') || 0}</td>
                          <td className="px-3 py-2 text-xs">{item.defect_type || '-'}</td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">{item.repair_notes || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {canEdit && detailData.status !== 'Shipped Back' && (
              <button
                onClick={() => { setShowDetail(false); openStatusUpdate(detailData); }}
                className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
              >
                Update Status Perbaikan
              </button>
            )}
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Data Retur?"
          message={`Retur "${confirmDelete.return_number}" akan dihapus permanen.`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
