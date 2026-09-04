import { useState, useEffect } from 'react';
import { Package, CheckCircle, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import StatusBadge from './StatusBadge';
import { apiGet, apiPut } from '../../../lib/api';

function VendorAccessoriesPanel({ shipmentId, token, count }) {
  const [accessories, setAccessories] = useState([]);
  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const loadAccessories = async () => {
    if (loaded) { setExpanded(!expanded); return; }
    try {
      const data = await apiGet(`/vendor-shipments/${shipmentId}`);
      setAccessories(data.po_accessories || []);
      setLoaded(true);
      setExpanded(true);
    } catch (e) { console.error(e); }
  };

  return (
    <div className="mt-3 border-t border-emerald-100 pt-3">
      <button onClick={loadAccessories}
        className="flex items-center gap-2 text-xs font-semibold text-emerald-700 hover:text-emerald-800 transition-colors"
        data-testid="vendor-accessories-toggle">
        <span className="w-4 h-4 bg-emerald-100 rounded-full flex items-center justify-center text-[10px]">{expanded ? '▼' : '▶'}</span>
        🧷 Aksesoris PO ({count} item)
      </button>
      {expanded && accessories.length > 0 && (
        <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-2">
          {accessories.map((acc, idx) => (
            <div key={acc.id || idx} className="bg-emerald-50 rounded-lg p-2.5 border border-emerald-100">
              <p className="text-sm font-medium text-foreground/90">{acc.accessory_name}</p>
              <p className="text-xs text-emerald-600 font-mono">{acc.accessory_code || '-'}</p>
              <p className="text-sm font-bold text-emerald-700 mt-1">{(acc.qty_needed || 0).toLocaleString('id-ID')} {acc.unit || 'pcs'}</p>
              {acc.notes && <p className="text-xs text-muted-foreground/70 mt-0.5">{acc.notes}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── VENDOR RECEIVING ─────────────────────────────────────────────────────────



export default function VendorReceiving({ token, user }) {
  const [shipments, setShipments] = useState([]);

  useEffect(() => { fetchShipments(); }, []);

  const fetchShipments = async () => {
    try {
      const data = await apiGet('/vendor-shipments');
      setShipments(Array.isArray(data) ? data : []);
    } catch (e) { setShipments([]); }
  };

  const confirmReceive = async (shipment) => {
    if (!confirm(`Konfirmasi penerimaan shipment ${shipment.shipment_number}?\nSetelah dikonfirmasi, selesaikan inspeksi material sebelum memulai produksi.`)) return;
    try {
      await apiPut(`/vendor-shipments/${shipment.id}`, { status: 'Received', received_at: new Date() });
      fetchShipments();
    } catch (e) { toast.error(e.message || 'Gagal mengkonfirmasi'); }
  };

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  // Build parent-child tree
  const parentShipments = shipments.filter(s => !s.parent_shipment_id);
  const childMap = {};
  shipments.filter(s => s.parent_shipment_id).forEach(s => {
    if (!childMap[s.parent_shipment_id]) childMap[s.parent_shipment_id] = [];
    childMap[s.parent_shipment_id].push(s);
  });

  const getTypeLabel = (type) => {
    if (type === 'ADDITIONAL') return { label: 'Pengiriman Tambahan', color: 'bg-amber-100 text-amber-700' };
    if (type === 'REPLACEMENT') return { label: 'Pengiriman Pengganti', color: 'bg-red-100 text-red-700' };
    // FASE 22 — surat jalan REWORK (barang reject dikembalikan untuk diperbaiki)
    // dulu ikut berlabel "Pengiriman Awal", jadi vendor tidak tahu ini pekerjaan
    // ULANG dari reject QC — padahal justru ini yang harus diprioritaskan.
    if (type === 'REWORK') return { label: '🔄 Retur Perbaikan (Rework)', color: 'bg-orange-100 text-orange-700' };
    return { label: 'Pengiriman Awal', color: 'bg-blue-100 text-blue-700' };
  };

  const getStatusConfig = (s) => {
    if (s.status === 'Sent') return { label: 'Belum Diterima', color: 'border-amber-200 bg-amber-50/30' };
    if (s.status === 'Received' && s.inspection_status !== 'Inspected') return { label: 'Diterima – Menunggu Inspeksi', color: 'border-blue-200 bg-blue-50/20' };
    if (s.status === 'Received' && s.inspection_status === 'Inspected') return { label: 'Diterima & Diinspeksi', color: 'border-emerald-200 bg-emerald-50/20' };
    return { label: s.status, color: 'border-border' };
  };

  const renderShipment = (s, isChild = false) => {
    const typeConf = getTypeLabel(s.shipment_type);
    const statusConf = getStatusConfig(s);
    const children = childMap[s.id] || [];
    return (
      <div key={s.id} className={`rounded-xl border p-4 shadow-sm ${statusConf.color} ${isChild ? 'ml-6 border-dashed' : ''}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {isChild && <ChevronRight className="w-4 h-4 text-muted-foreground/70 flex-shrink-0" />}
              <span className="font-bold text-foreground font-mono">{s.shipment_number}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${typeConf.color}`}>{typeConf.label}</span>
              <StatusBadge status={s.status} />
              {s.inspection_status === 'Inspected' && <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">✓ Diinspeksi</span>}
            </div>
            {s.delivery_note_number && <p className="text-xs text-muted-foreground font-mono mt-0.5">SJ: {s.delivery_note_number}</p>}
            <p className="text-sm text-muted-foreground mt-1">{fmtDate(s.shipment_date)} • {s.vendor_name}</p>
            <div className="flex items-center gap-2 mt-1 flex-wrap text-xs text-muted-foreground">
              <span>{(s.items || []).length} item</span>
              {s.total_received != null && <span>• Diterima: <strong className="text-emerald-700">{s.total_received} pcs</strong></span>}
              {(s.total_missing || 0) > 0 && <span>• Missing: <strong className="text-red-600">{s.total_missing} pcs</strong></span>}
            </div>
            {(s.notes_for_vendor || s.notes) && (
              <div className="mt-2 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800">
                <span className="font-semibold">Catatan Admin:</span> {s.notes_for_vendor || s.notes}
              </div>
            )}
          </div>
          <div className="flex flex-col gap-2 items-end flex-shrink-0">
            {s.status === 'Sent' && (
              <button onClick={() => confirmReceive(s)} className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700">
                <CheckCircle className="w-4 h-4" /> Konfirmasi Terima
              </button>
            )}
            {s.status === 'Received' && s.inspection_status !== 'Inspected' && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 text-center">
                ⏰ Wajib inspeksi dalam 3 hari
              </div>
            )}
            {s.status === 'Received' && s.inspection_status === 'Inspected' && (
              <span className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-sm border border-emerald-200">
                <CheckCircle className="w-4 h-4" /> Selesai
              </span>
            )}
          </div>
        </div>

        {/* Items */}
        {(s.items || []).length > 0 && (
          <div className="mt-3 border-t border-border/60 pt-3">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {s.items.map(item => (
                <div key={item.id} className="bg-card rounded-lg p-2.5 border border-border/60">
                  <p className="text-sm font-medium">{item.product_name}</p>
                  <p className="text-xs text-muted-foreground font-mono">{item.sku || '-'} • {item.size}/{item.color}</p>
                  {item.serial_number && <p className="text-xs text-amber-700 font-mono mt-0.5">SN: {item.serial_number}</p>}
                  <p className="text-sm font-bold text-blue-700 mt-1">{(item.qty_sent || 0).toLocaleString('id-ID')} pcs</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* PO Accessories */}
        {(s.po_accessories_count > 0) && (
          <VendorAccessoriesPanel shipmentId={s.id} token={token} count={s.po_accessories_count} />
        )}

        {/* Child Shipments */}
        {children.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-semibold text-muted-foreground">Child Shipments ({children.length})</p>
            {children.map(child => renderShipment(child, true))}
          </div>
        )}
      </div>
    );
  };

  const pendingCount = shipments.filter(s => s.status === 'Sent').length;
  const needsInspection = shipments.filter(s => s.status === 'Received' && s.inspection_status !== 'Inspected').length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Penerimaan Material</h1>
        <p className="text-muted-foreground text-sm mt-1">Konfirmasi penerimaan material dan lihat hierarki shipment (awal, tambahan, pengganti).</p>
      </div>

      {pendingCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
          <p className="text-sm font-semibold text-amber-700">⚠️ {pendingCount} Shipment Menunggu Konfirmasi</p>
          <p className="text-xs text-amber-600 mt-0.5">Konfirmasi penerimaan sebelum melakukan inspeksi material</p>
        </div>
      )}
      {needsInspection > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3">
          <p className="text-sm font-semibold text-red-700">🔍 {needsInspection} Shipment Menunggu Inspeksi Material</p>
          <p className="text-xs text-red-600 mt-0.5">Inspeksi wajib diselesaikan dalam 3 hari. Produksi tidak dapat dimulai sebelum inspeksi selesai.</p>
        </div>
      )}

      <div className="space-y-4">
        {parentShipments.length === 0 ? (
          <div className="bg-card rounded-xl border border-border p-12 text-center">
            <Package className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
            <p className="text-muted-foreground/70">Tidak ada shipment masuk</p>
          </div>
        ) : parentShipments.map(s => renderShipment(s, false))}
      </div>
    </div>
  );
}

// ─── VENDOR PRODUCTION JOBS ───────────────────────────────────────────────────


