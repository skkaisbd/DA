import { useState, useEffect } from 'react';
import { ClipboardCheck, Clipboard, X, CheckCircle, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import AdditionalRequestModal from './AdditionalRequestModal';
import { apiGet, apiPost, apiFetch } from '../../../lib/api';

export default function VendorMaterialInspection({ user }) {
  const [shipments, setShipments] = useState([]);
  const [inspections, setInspections] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ inspection_date: new Date().toISOString().split('T')[0], overall_notes: '', items: [], accessory_items: [] });
  // Phase 16: state untuk modal Permintaan Tambahan
  const [showReqModal, setShowReqModal] = useState(false);
  const [reqModalData, setReqModalData] = useState(null);

  useEffect(() => { fetchShipments(); fetchInspections(); }, []);

  const fetchShipments = async () => {
    try {
      const data = await apiGet('/vendor-shipments');
      const received = Array.isArray(data) ? data.filter(s => s.status === 'Received') : [];
      setShipments(received);
    } catch (e) { setShipments([]); }
  };

  const fetchInspections = async () => {
    try {
      const data = await apiGet('/vendor-material-inspections');
      setInspections(Array.isArray(data) ? data : []);
    } catch (e) { setInspections([]); }
  };

  const openInspect = async (shipment) => {
    setSelectedShipment(shipment);
    const data = await apiGet(`/vendor-shipments/${shipment.id}`);
    const items = (data.items || []).map(si => ({
      shipment_item_id: si.id,
      po_item_id: si.po_item_id || '',
      po_id: si.po_id || data.po_id || '',
      sku: si.sku || '',
      product_name: si.product_name || '',
      size: si.size || '',
      color: si.color || '',
      serial_number: si.serial_number || '',
      ordered_qty: si.qty_sent || 0,
      received_qty: si.qty_sent || 0,
      missing_qty: 0,
      condition_notes: ''
    }));
    
    // Load accessories for inspection
    // For additional accessory shipments, use accessory_items from shipment
    // For normal shipments, use po_accessories from linked PO
    let accessory_items = [];
    if (data.accessory_items && data.accessory_items.length > 0) {
      // This is an additional accessory shipment
      accessory_items = data.accessory_items.map(asi => ({
        accessory_id: asi.accessory_id || '',
        accessory_name: asi.accessory_name || '',
        accessory_code: asi.accessory_code || '',
        unit: asi.unit || 'pcs',
        ordered_qty: asi.qty_sent || 0,
        received_qty: asi.qty_sent || 0,
        missing_qty: 0,
        condition_notes: ''
      }));
    } else if (data.po_accessories && data.po_accessories.length > 0) {
      // Normal shipment with PO accessories
      accessory_items = data.po_accessories.map(acc => ({
        accessory_id: acc.accessory_id || acc.id || '',
        accessory_name: acc.accessory_name || '',
        accessory_code: acc.accessory_code || '',
        unit: acc.unit || 'pcs',
        ordered_qty: acc.qty_needed || 0,
        received_qty: acc.qty_needed || 0,
        missing_qty: 0,
        condition_notes: ''
      }));
    }
    
    setForm({ inspection_date: new Date().toISOString().split('T')[0], overall_notes: '', items, accessory_items });
    setShowModal(true);
  };

  const updateItem = (idx, field, value) => {
    const newItems = [...form.items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'received_qty') {
      newItems[idx].missing_qty = Math.max(0, (newItems[idx].ordered_qty || 0) - (Number(value) || 0));
    }
    setForm(f => ({ ...f, items: newItems }));
  };

  const updateAccItem = (idx, field, value) => {
    const newItems = [...form.accessory_items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'received_qty') {
      newItems[idx].missing_qty = Math.max(0, (newItems[idx].ordered_qty || 0) - (Number(value) || 0));
    }
    setForm(f => ({ ...f, accessory_items: newItems }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      let inspectionData;
      try {
        inspectionData = await apiPost('/vendor-material-inspections', { shipment_id: selectedShipment.id, ...form });
      } catch (err) {
        toast.error(err.message || 'Gagal menyimpan inspeksi');
        return;
      }
      setShowModal(false);
      fetchShipments();
      fetchInspections();

      // Phase 16: jika ada missing item, buka AdditionalRequestModal (bukan window.confirm)
      const totalMissingMaterial = form.items.reduce((s, i) => s + (i.missing_qty || 0), 0);
      const totalMissingAccessory = (form.accessory_items || []).reduce((s, a) => s + (a.missing_qty || 0), 0);
      const totalMissing = totalMissingMaterial + totalMissingAccessory;

      if (totalMissingMaterial > 0) {
        // Build defaultItems untuk modal (per-item dengan max_qty = missing_qty)
        const shipNumber = selectedShipment.shipment_number;
        const defaultItems = form.items
          .filter(i => (i.missing_qty || 0) > 0)
          .map(i => ({
            shipment_item_id: i.shipment_item_id,
            po_item_id: i.po_item_id || '',
            sku: i.sku,
            product_name: i.product_name,
            size: i.size,
            color: i.color,
            serial_number: i.serial_number || '',
            requested_qty: i.missing_qty,
            max_qty: i.missing_qty, // tidak boleh minta lebih dari yang missing
            reason: `Missing dari inspeksi shipment ${shipNumber}`
          }));

        setReqModalData({
          shipment: {
            id: selectedShipment.id,
            shipment_number: shipNumber,
            vendor_name: selectedShipment.vendor_name,
            po_id: selectedShipment.po_id || (form.items[0]?.po_id || ''),
            po_number: selectedShipment.po_number || '',
          },
          defaultItems,
          defaultReason: `Material missing setelah inspeksi shipment ${shipNumber}`,
          inspectionId: inspectionData.id,
          mode: 'inspection',
        });
        setShowReqModal(true);
      }
      if (totalMissing === 0) {
        toast.success('Inspeksi berhasil disimpan! Material & aksesoris lengkap — Anda dapat memulai produksi.');
      } else if (totalMissingMaterial === 0 && totalMissingAccessory > 0) {
        toast.info(`Inspeksi disimpan. Terdeteksi ${totalMissingAccessory} pcs aksesoris missing — sistem membuat permintaan otomatis.`);
      } else {
        toast.success('Inspeksi disimpan. Silakan lengkapi permintaan material tambahan.');
      }
    } finally {
      setLoading(false);
    }
  };

  const openDetail = (insp) => {
    setDetailData(insp);
    setShowDetail(true);
  };

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  // Check if inspection is overdue (>3 days from shipment received)
  const isOverdue = (shipment) => {
    if (!shipment.updated_at) return false;
    const receivedDate = new Date(shipment.updated_at);
    const threeDaysLater = new Date(receivedDate.getTime() + 3 * 24 * 60 * 60 * 1000);
    return new Date() > threeDaysLater;
  };

  // Already inspected shipment IDs
  const inspectedShipmentIds = new Set(inspections.map(i => i.shipment_id));

  const pendingShipments = shipments.filter(s => !inspectedShipmentIds.has(s.id));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <ClipboardCheck className="w-6 h-6 text-emerald-600" />
          Inspeksi Material
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Laporkan hasil inspeksi material yang diterima (wajib dalam 3 hari)</p>
      </div>

      {pendingShipments.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4">
          <p className="text-amber-800 font-semibold text-sm mb-2">⏰ Shipment Menunggu Inspeksi ({pendingShipments.length})</p>
          <div className="space-y-2">
            {pendingShipments.map(s => {
              const overdue = isOverdue(s);
              return (
                <div key={s.id} className={`flex items-center justify-between p-3 rounded-lg border ${overdue ? 'bg-red-50 border-red-200' : 'bg-card border-border'}`}>
                  <div>
                    <p className={`font-semibold text-sm ${overdue ? 'text-red-700' : 'text-foreground'}`}>
                      {s.shipment_number} {overdue && '⚠️ TERLAMBAT'}
                    </p>
                    <p className="text-xs text-muted-foreground">Diterima: {fmtDate(s.updated_at)} • Tipe: {s.shipment_type || 'NORMAL'}</p>
                  </div>
                  <button onClick={() => openInspect(s)} className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-medium hover:bg-emerald-700">
                    Inspeksi Sekarang
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Inspection History */}
      <div>
        <h3 className="font-semibold text-foreground/90 mb-3">Riwayat Inspeksi ({inspections.length})</h3>
        {inspections.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground/70 text-sm">Belum ada inspeksi yang dilakukan</div>
        ) : (
          <div className="space-y-2">
            {inspections.map(insp => (
              <div key={insp.id} className="bg-card border border-border rounded-xl p-4 flex items-center justify-between">
                <div>
                  <p className="font-semibold text-sm text-foreground">{insp.shipment_number}</p>
                  <p className="text-xs text-muted-foreground">
                    Inspeksi: {fmtDate(insp.inspection_date)} •
                    Diterima: <span className="text-emerald-700 font-medium">{insp.total_received}</span> pcs •
                    Missing: <span className={`font-medium ${insp.total_missing > 0 ? 'text-red-600' : 'text-muted-foreground'}`}>{insp.total_missing}</span> pcs
                  </p>
                </div>
                <button onClick={() => openDetail(insp)} className="px-3 py-1.5 bg-muted text-foreground/90 rounded-lg text-xs font-medium hover:bg-muted">
                  Lihat Detail
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Inspection Form Modal */}
      {showModal && selectedShipment && (
        <Modal title={`Inspeksi: ${selectedShipment.shipment_number}`} onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-800">
              Periksa setiap item material yang diterima. Isi jumlah yang benar-benar diterima dan jumlah yang missing/kurang.
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal Inspeksi</label>
              <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.inspection_date} onChange={e => setForm(f => ({ ...f, inspection_date: e.target.value }))} />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted">
                    <th className="text-left px-3 py-2 text-xs">Produk / SKU</th>
                    <th className="text-right px-3 py-2 text-xs">Dikirim</th>
                    <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima *</th>
                    <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                    <th className="text-left px-3 py-2 text-xs">Kondisi / Catatan</th>
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, idx) => (
                    <tr key={idx} className="border-t border-border/60">
                      <td className="px-3 py-2">
                        <p className="font-medium text-xs">{item.product_name}</p>
                        <p className="text-xs text-muted-foreground/70 font-mono">{item.sku} {item.size}/{item.color}</p>
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground font-medium">{item.ordered_qty}</td>
                      <td className="px-3 py-2 text-right">
                        <input type="number" min="0" max={item.ordered_qty}
                          className="w-20 border border-emerald-200 rounded px-2 py-1 text-sm text-right focus:outline-none focus:ring-1 focus:ring-emerald-500"
                          value={item.received_qty}
                          onChange={e => updateItem(idx, 'received_qty', e.target.value)} />
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${item.missing_qty > 0 ? 'text-red-600' : 'text-muted-foreground/70'}`}>
                        {item.missing_qty}
                      </td>
                      <td className="px-3 py-2">
                        <input className="w-full border border-border rounded px-2 py-1 text-xs" value={item.condition_notes} onChange={e => updateItem(idx, 'condition_notes', e.target.value)} placeholder="Kondisi barang..." />
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-muted/40 font-bold border-t-2 border-border">
                  <tr>
                    <td className="px-3 py-2 text-sm">Total</td>
                    <td className="px-3 py-2 text-right">{form.items.reduce((s, i) => s + (i.ordered_qty || 0), 0)}</td>
                    <td className="px-3 py-2 text-right text-emerald-700">{form.items.reduce((s, i) => s + (Number(i.received_qty) || 0), 0)}</td>
                    <td className="px-3 py-2 text-right text-red-600">{form.items.reduce((s, i) => s + (i.missing_qty || 0), 0)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan Umum</label>
              <textarea rows="2" className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.overall_notes} onChange={e => setForm(f => ({ ...f, overall_notes: e.target.value }))} placeholder="Catatan kondisi material secara umum..." />
            </div>

            {/* Accessories Inspection */}
            {form.accessory_items.length > 0 && (
              <div className="mt-3" data-testid="inspection-accessories">
                <label className="block text-sm font-semibold text-emerald-700 mb-2">Inspeksi Aksesoris ({form.accessory_items.length} item)</label>
                <div className="overflow-x-auto border border-emerald-200 rounded-xl">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-emerald-50">
                        <th className="text-left px-3 py-2 text-xs text-emerald-700">Aksesoris</th>
                        <th className="text-left px-3 py-2 text-xs text-emerald-700">Kode</th>
                        <th className="text-right px-3 py-2 text-xs text-muted-foreground">Qty Dibutuhkan</th>
                        <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima *</th>
                        <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                        <th className="text-left px-3 py-2 text-xs">Catatan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.accessory_items.map((acc, idx) => (
                        <tr key={idx} className="border-t border-emerald-100">
                          <td className="px-3 py-2 font-medium text-xs text-foreground/90">{acc.accessory_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-emerald-600">{acc.accessory_code}</td>
                          <td className="px-3 py-2 text-right text-muted-foreground font-medium">{acc.ordered_qty} {acc.unit}</td>
                          <td className="px-3 py-2 text-right">
                            <input type="number" min="0" className="w-20 border border-emerald-200 rounded px-2 py-1 text-sm text-right focus:outline-none focus:ring-1 focus:ring-emerald-500" value={acc.received_qty} onChange={e => updateAccItem(idx, 'received_qty', e.target.value)} />
                          </td>
                          <td className={`px-3 py-2 text-right font-semibold ${acc.missing_qty > 0 ? 'text-red-600' : 'text-muted-foreground/70'}`}>{acc.missing_qty}</td>
                          <td className="px-3 py-2">
                            <input className="w-full border border-border rounded px-2 py-1 text-xs" value={acc.condition_notes} onChange={e => updateAccItem(idx, 'condition_notes', e.target.value)} placeholder="Kondisi aksesoris..." />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-emerald-50 font-bold border-t-2 border-emerald-200">
                      <tr>
                        <td className="px-3 py-2 text-sm" colSpan="2">Total Aksesoris</td>
                        <td className="px-3 py-2 text-right">{form.accessory_items.reduce((s, i) => s + (i.ordered_qty || 0), 0)}</td>
                        <td className="px-3 py-2 text-right text-emerald-700">{form.accessory_items.reduce((s, i) => s + (Number(i.received_qty) || 0), 0)}</td>
                        <td className="px-3 py-2 text-right text-red-600">{form.accessory_items.reduce((s, i) => s + (i.missing_qty || 0), 0)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button type="submit" disabled={loading} className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
                {loading ? 'Menyimpan...' : 'Kirim Laporan Inspeksi'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailData && (
        <Modal title={`Detail Inspeksi: ${detailData.shipment_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="grid grid-cols-3 gap-3 flex-1">
                <div className="bg-emerald-50 rounded-lg p-3 text-center">
                  <p className="text-xs text-emerald-600">Total Diterima</p>
                  <p className="text-2xl font-bold text-emerald-700">{detailData.total_received}</p>
                </div>
                <div className={`rounded-lg p-3 text-center ${detailData.total_missing > 0 ? 'bg-red-50' : 'bg-muted/40'}`}>
                  <p className={`text-xs ${detailData.total_missing > 0 ? 'text-red-600' : 'text-muted-foreground'}`}>Total Missing</p>
                  <p className={`text-2xl font-bold ${detailData.total_missing > 0 ? 'text-red-700' : 'text-muted-foreground'}`}>{detailData.total_missing}</p>
                </div>
                <div className="bg-muted/40 rounded-lg p-3 text-center">
                  <p className="text-xs text-muted-foreground">Tanggal Inspeksi</p>
                  <p className="text-sm font-bold text-foreground/90">{fmtDate(detailData.inspection_date)}</p>
                </div>
              </div>
              <a href="#" onClick={async (e) => {
                e.preventDefault();
                try {
                  const res = await apiFetch(`/export-pdf?type=vendor-inspection&id=${detailData.id}`);
                  if (!res.ok) throw new Error('Export gagal');
                  const blob = await res.blob();
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `Inspeksi-${detailData.shipment_number || 'unknown'}.pdf`;
                  a.click();
                  window.URL.revokeObjectURL(url);
                } catch (err) { toast.error('Error: ' + err.message); }
              }}
                className="ml-3 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 flex items-center gap-1.5 flex-shrink-0 cursor-pointer" data-testid="export-inspection-pdf">
                PDF Export
              </a>
            </div>
            {detailData.overall_notes && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                <strong>Catatan:</strong> {detailData.overall_notes}
              </div>
            )}
            {detailData.items?.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted">
                      <th className="text-left px-3 py-2 text-xs">Produk / SKU</th>
                      <th className="text-right px-3 py-2 text-xs">Dikirim</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima</th>
                      <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                      <th className="text-left px-3 py-2 text-xs">Catatan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.items.map(item => (
                      <tr key={item.id} className="border-t border-border/60">
                        <td className="px-3 py-2">
                          <p className="font-medium text-xs">{item.product_name}</p>
                          <p className="text-xs text-muted-foreground/70 font-mono">{item.sku} {item.size}/{item.color}</p>
                        </td>
                        <td className="px-3 py-2 text-right">{item.ordered_qty}</td>
                        <td className="px-3 py-2 text-right text-emerald-700 font-medium">{item.received_qty}</td>
                        <td className={`px-3 py-2 text-right font-medium ${item.missing_qty > 0 ? 'text-red-600' : 'text-muted-foreground/70'}`}>{item.missing_qty}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{item.condition_notes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {/* Accessory items in detail */}
            {(detailData.accessory_items || []).length > 0 && (
              <div className="overflow-x-auto">
                <h5 className="text-sm font-semibold text-emerald-700 mb-2">Aksesoris ({detailData.accessory_items.length} item)</h5>
                <table className="w-full text-sm">
                  <thead><tr className="bg-emerald-50">
                    <th className="text-left px-3 py-2 text-xs text-emerald-700">Aksesoris</th>
                    <th className="text-left px-3 py-2 text-xs text-emerald-700">Kode</th>
                    <th className="text-right px-3 py-2 text-xs">Dibutuhkan</th>
                    <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima</th>
                    <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                    <th className="text-left px-3 py-2 text-xs">Catatan</th>
                  </tr></thead>
                  <tbody>{detailData.accessory_items.map(acc => (
                    <tr key={acc.id} className="border-t border-emerald-100">
                      <td className="px-3 py-2 font-medium text-xs">{acc.accessory_name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-emerald-600">{acc.accessory_code || '-'}</td>
                      <td className="px-3 py-2 text-right">{acc.ordered_qty} {acc.unit || 'pcs'}</td>
                      <td className="px-3 py-2 text-right text-emerald-700 font-medium">{acc.received_qty}</td>
                      <td className={`px-3 py-2 text-right font-medium ${acc.missing_qty > 0 ? 'text-red-600' : 'text-muted-foreground/70'}`}>{acc.missing_qty}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">{acc.condition_notes || '-'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Phase 16: Modal Permintaan Material Tambahan (auto-prompt setelah inspeksi missing) */}
      {showReqModal && reqModalData && (
        <AdditionalRequestModal
          shipment={reqModalData.shipment}
          defaultItems={reqModalData.defaultItems}
          defaultReason={reqModalData.defaultReason}
          inspectionId={reqModalData.inspectionId}
          mode={reqModalData.mode}
          onClose={() => { setShowReqModal(false); setReqModalData(null); }}
          onSuccess={() => { setShowReqModal(false); setReqModalData(null); }}
        />
      )}
    </div>
  );
}

// ─── VENDOR DEFECT REPORTS ─────────────────────────────────────────────────────


