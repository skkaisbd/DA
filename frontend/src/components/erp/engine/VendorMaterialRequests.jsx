/**
 * VendorMaterialRequests — Phase 16 (Vendor Portal)
 *
 * Modul khusus vendor untuk mengelola Permintaan Material:
 *   • Lihat daftar permintaan ADDITIONAL & REPLACEMENT milik vendor
 *   • Lihat detail + alasan penolakan admin
 *   • Ajukan Ulang permintaan yang Rejected
 *   • Buat Permintaan Manual untuk shipment yang sudah ter-inspeksi
 */
import { useState, useEffect } from 'react';
import {
  Plus, Eye, RotateCcw, ClipboardList, CheckCircle, XCircle, Clock,
  AlertTriangle, Truck, FileText, AlertCircle
} from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import AdditionalRequestModal from './AdditionalRequestModal';
import MaterialRequestTracker from './MaterialRequestTracker';
import { apiGet, apiFetch } from '../../../lib/api';
// F15-B — kelas Tailwind tidak boleh dirakit saat berjalan; lihat lib/tone.js
import { tone } from '@/lib/tone';

const TABS = [
  { id: 'ADDITIONAL', label: 'Permintaan Tambahan', icon: Plus, color: 'amber' },
  { id: 'REPLACEMENT', label: 'Permintaan Pengganti', icon: AlertTriangle, color: 'red' },
];

const STATUS_COLORS = {
  Pending: 'bg-amber-100 text-amber-700 border-amber-200',
  Approved: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  Rejected: 'bg-red-100 text-red-700 border-red-200',
};

const STATUS_ICONS = {
  Pending: Clock,
  Approved: CheckCircle,
  Rejected: XCircle,
};

export default function VendorMaterialRequests({ user }) {
  const [activeTab, setActiveTab] = useState('ADDITIONAL');
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Detail modal
  const [showDetail, setShowDetail] = useState(false);
  const [selectedReq, setSelectedReq] = useState(null);

  // Resubmit modal
  const [resubmitData, setResubmitData] = useState(null);

  // Manual request: shipment picker + modal
  const [showShipmentPicker, setShowShipmentPicker] = useState(false);
  const [inspectedShipments, setInspectedShipments] = useState([]);
  const [manualReqShipment, setManualReqShipment] = useState(null);
  const [manualReqItems, setManualReqItems] = useState([]);
  const [loadingShipPicker, setLoadingShipPicker] = useState(false);
  // Jenis permintaan yang sedang dibuat lewat picker: ADDITIONAL | REPLACEMENT.
  // 2026-06 — tombol buat DULU hanya dirender di tab ADDITIONAL, sementara jalur
  // lama untuk PENGGANTI (Laporan Cacat Material) sudah dimatikan backend
  // (HTTP 410). Akibatnya vendor CMT benar-benar TIDAK BISA mengajukan material
  // pengganti sama sekali — permintaannya harus dititipkan lewat telepon/chat
  // dan tidak pernah tercatat di ERP.
  const [createType, setCreateType] = useState('ADDITIONAL');

  useEffect(() => {
    fetchRequests();
  }, [activeTab]);

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const data = await apiGet(`/material-requests?request_type=${activeTab}`);
      setRequests(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error('Gagal memuat permintaan');
      setRequests([]);
    } finally {
      setLoading(false);
    }
  };

  const openDetail = (req) => {
    setSelectedReq(req);
    setShowDetail(true);
  };

  const openResubmit = async (req) => {
    // Phase 16 Fix: Fetch shipment items untuk mengisi serial_number yang hilang
    // (penting untuk request lama yang dibuat sebelum mapping serial diperbaiki)
    let shipItemsMap = {}; // key: sku|size|color → si
    let shipItemsByIdMap = {}; // key: shipment_item_id → si
    if (req.original_shipment_id) {
      try {
        const fullShip = await apiGet(`/vendor-shipments/${req.original_shipment_id}`);
        for (const si of (fullShip.items || [])) {
          const k = `${si.sku || ''}|${si.size || ''}|${si.color || ''}`;
          if (!shipItemsMap[k] || (si.serial_number && !shipItemsMap[k].serial_number)) {
            shipItemsMap[k] = si;
          }
          if (si.id) shipItemsByIdMap[si.id] = si;
        }
      } catch (e) {
        // Silent fail — backend juga punya defensive lookup
      }
    }
    const items = (req.items || []).map((it) => {
      // Resolve serial_number dari shipment item jika item request tidak punya
      let serial = it.serial_number || '';
      let poItemId = it.po_item_id || '';
      let shipmentItemId = it.shipment_item_id || '';
      if (!serial || !poItemId) {
        let matched = null;
        if (shipmentItemId && shipItemsByIdMap[shipmentItemId]) {
          matched = shipItemsByIdMap[shipmentItemId];
        } else {
          const k = `${it.sku || ''}|${it.size || ''}|${it.color || ''}`;
          matched = shipItemsMap[k];
        }
        if (matched) {
          if (!serial) serial = matched.serial_number || '';
          if (!poItemId) poItemId = matched.po_item_id || '';
          if (!shipmentItemId) shipmentItemId = matched.id || '';
        }
      }
      return {
        shipment_item_id: shipmentItemId,
        po_item_id: poItemId,
        sku: it.sku || '',
        product_name: it.product_name || '',
        size: it.size || '',
        color: it.color || '',
        serial_number: serial,
        requested_qty: Number(it.requested_qty || 0),
        reason: it.reason || req.reason || '',
      };
    });
    setResubmitData({
      shipment: {
        id: req.original_shipment_id,
        shipment_number: req.original_shipment_number || '-',
        vendor_name: req.vendor_name,
        po_id: req.po_id,
        po_number: req.po_number,
      },
      defaultItems: items,
      defaultReason: req.reason || '',
      previousRequestId: req.id,
      previousRequestNumber: req.request_number,
      // ajukan ulang WAJIB memakai jenis yang sama (tambahan vs pengganti)
      requestType: req.request_type || 'ADDITIONAL',
    });
    setShowDetail(false);
  };

  // ─── Manual Request: pilih shipment yang sudah ter-inspeksi ────────────────
  const openShipmentPicker = async (type = 'ADDITIONAL') => {
    setCreateType(type);
    setLoadingShipPicker(true);
    setShowShipmentPicker(true);
    try {
      const data = await apiGet('/vendor-shipments');
      // Filter: shipment milik vendor ini, sudah Received & sudah Inspected
      const list = Array.isArray(data) ? data : [];
      const filtered = list.filter(
        (s) => s.inspection_status === 'Inspected'
      );
      setInspectedShipments(filtered);
    } catch (e) {
      toast.error('Gagal memuat daftar shipment');
      setInspectedShipments([]);
    } finally {
      setLoadingShipPicker(false);
    }
  };

  const pickShipmentForManual = async (shipment) => {
    try {
      const fullShip = await apiGet(`/vendor-shipments/${shipment.id}`);
      const items = (fullShip.items || []).map((si) => ({
        shipment_item_id: si.id,
        po_item_id: si.po_item_id || '',
        sku: si.sku || '',
        product_name: si.product_name || '',
        size: si.size || '',
        color: si.color || '',
        serial_number: si.serial_number || '',
        requested_qty: 0,
        reason: '',
      }));
      setManualReqShipment({
        id: shipment.id,
        shipment_number: shipment.shipment_number,
        vendor_name: shipment.vendor_name,
        po_id: fullShip.po_id || (fullShip.items?.[0]?.po_id || ''),
        po_number: fullShip.po_number || (fullShip.items?.[0]?.po_number || ''),
      });
      setManualReqItems(items);
      setShowShipmentPicker(false);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat detail shipment');
    }
  };

  const downloadPDF = async (req) => {
    try {
      const res = await apiFetch(`/export-pdf?type=material-request&id=${req.id}`);
      if (!res.ok) {
        toast.error('Gagal export PDF');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Permohonan-${req.request_number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Gagal export PDF: ' + e.message);
    }
  };

  const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('id-ID') : '-');

  // Filter local
  const filtered = requests.filter((r) => {
    if (statusFilter !== 'all' && r.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const hay = `${r.request_number || ''} ${r.original_shipment_number || ''} ${r.po_number || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const currentTab = TABS.find((t) => t.id === activeTab);
  const isAdditional = activeTab === 'ADDITIONAL';

  // Stats per tab
  const stats = {
    total: requests.length,
    pending: requests.filter((r) => r.status === 'Pending').length,
    approved: requests.filter((r) => r.status === 'Approved').length,
    rejected: requests.filter((r) => r.status === 'Rejected').length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-emerald-600" />
            Permintaan Material
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Kelola permintaan material tambahan (missing) dan pengganti (cacat) ke ERP.
          </p>
        </div>
        {isAdditional ? (
          <button
            onClick={() => openShipmentPicker('ADDITIONAL')}
            className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 shadow-sm"
            data-testid="vendor-create-manual-request-btn"
          >
            <Plus className="w-4 h-4" /> Buat Permintaan Manual
          </button>
        ) : (
          <button
            onClick={() => openShipmentPicker('REPLACEMENT')}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 shadow-sm"
            data-testid="vendor-create-replacement-request-btn"
          >
            <Plus className="w-4 h-4" /> Buat Permintaan Pengganti
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
                active
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground/90'
              }`}
              data-testid={`vendor-mr-tab-${tab.id.toLowerCase()}`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total', value: stats.total, color: 'slate' },
          { label: 'Pending', value: stats.pending, color: 'amber', icon: Clock },
          { label: 'Disetujui', value: stats.approved, color: 'emerald', icon: CheckCircle },
          { label: 'Ditolak', value: stats.rejected, color: 'red', icon: XCircle },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <div
              key={s.label}
              className={`bg-card border border-border rounded-xl p-3 flex items-center gap-3`}
              data-testid={`vendor-mr-stat-${s.label.toLowerCase()}`}
            >
              {Icon && (
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center border ${tone(s.color).chip}`}
                >
                  <Icon className={`w-4 h-4 ${tone(s.color).text}`} />
                </div>
              )}
              <div>
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <p className="font-bold text-foreground">{s.value}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Info banner */}
      <div
        className={`border rounded-xl p-3 text-sm ${
          isAdditional
            ? 'bg-amber-50 border-amber-200 text-amber-800'
            : 'bg-red-50 border-red-200 text-red-800'
        }`}
      >
        {isAdditional
          ? '➕ Permintaan tambahan dibuat saat ada material missing/kurang dari inspeksi. Anda dapat mengajukan ulang jika ditolak admin, atau membuat permintaan manual untuk shipment yang sudah ter-inspeksi.'
          : '🔄 Permintaan pengganti untuk material CACAT/RUSAK (bukan kurang kirim). Klik "Buat Permintaan Pengganti", pilih surat jalan yang sudah ter-inspeksi, lalu isi qty + cacatnya per item. Setelah disetujui ERP, terbit surat jalan pengganti (kode "-R1") yang muncul di Penerimaan Material Anda.'}
      </div>

      {/* Filter row */}
      <div className="flex gap-2 flex-wrap">
        <input
          type="text"
          placeholder="Cari nomor permintaan, shipment, atau PO..."
          className="flex-1 min-w-64 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="vendor-mr-search"
        />
        <select
          className="border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          data-testid="vendor-mr-status-filter"
        >
          <option value="all">Semua Status</option>
          <option value="Pending">Pending</option>
          <option value="Approved">Disetujui</option>
          <option value="Rejected">Ditolak</option>
        </select>
      </div>

      {/* List */}
      <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground/70 text-sm">Memuat data...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <ClipboardList className="w-12 h-12 text-muted-foreground/50 mx-auto mb-3" />
            <p className="text-muted-foreground text-sm">Belum ada {currentTab.label.toLowerCase()}</p>
            {isAdditional && (
              <p className="text-muted-foreground/70 text-xs mt-1">
                Permintaan otomatis terbuat saat ada missing material di inspeksi, atau klik "Buat Permintaan Manual".
              </p>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">No. Permintaan</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Shipment Asal</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">PO</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-muted-foreground">Total Qty</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Tanggal</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Child Shipment</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {filtered.map((row) => {
                  const StatusIcon = STATUS_ICONS[row.status] || Clock;
                  const canResubmit = isAdditional && row.status === 'Rejected' && !row.resubmitted_as_id;
                  return (
                    <tr key={row.id} className="hover:bg-muted/60 transition-colors">
                      <td className="px-4 py-3">
                        <div className="font-bold font-mono text-sm text-emerald-700">
                          {row.request_number}
                        </div>
                        {row.previous_request_number && (
                          <div className="text-xs text-blue-600 flex items-center gap-1 mt-0.5">
                            <RotateCcw className="w-3 h-3" />
                            <span className="font-mono">resubmit dari {row.previous_request_number}</span>
                          </div>
                        )}
                        {row.resubmitted_as_number && (
                          <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                            <RotateCcw className="w-3 h-3" />
                            <span className="font-mono">→ {row.resubmitted_as_number}</span>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-blue-700">
                        {row.original_shipment_number || '-'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{row.po_number || '-'}</td>
                      <td className="px-4 py-3 text-right font-semibold">
                        {Number(row.total_requested_qty || 0).toLocaleString('id-ID')} pcs
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{fmtDate(row.created_at)}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
                            STATUS_COLORS[row.status] || 'bg-muted text-muted-foreground'
                          }`}
                        >
                          <StatusIcon className="w-3 h-3" />
                          {row.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {/* Rantai pengganti terlacak sampai diinspeksi (INV-F28) */}
                        <MaterialRequestTracker req={row} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => openDetail(row)}
                            className="p-1.5 rounded hover:bg-blue-50 text-blue-600"
                            title="Detail"
                            data-testid={`vendor-mr-detail-btn-${row.id}`}
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          {canResubmit && (
                            <button
                              onClick={() => openResubmit(row)}
                              className="p-1.5 rounded hover:bg-amber-50 text-amber-600"
                              title="Ajukan Ulang"
                              data-testid={`vendor-mr-resubmit-btn-${row.id}`}
                            >
                              <RotateCcw className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {showDetail && selectedReq && (
        <Modal
          title={`Detail Permintaan: ${selectedReq.request_number}`}
          onClose={() => setShowDetail(false)}
          size="xl"
        >
          <div className="space-y-4">
            {/* PDF Export */}
            <div className="flex justify-end">
              <button
                onClick={() => downloadPDF(selectedReq)}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 font-medium"
                data-testid="vendor-mr-pdf-btn"
              >
                <FileText className="w-4 h-4" /> Export PDF
              </button>
            </div>

            {/* Header info */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[
                { l: 'No. Permintaan', v: <span className="font-bold font-mono">{selectedReq.request_number}</span> },
                {
                  l: 'Tipe',
                  v: (
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-bold ${
                        isAdditional ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {selectedReq.request_type}
                    </span>
                  ),
                },
                {
                  l: 'Status',
                  v: (
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-bold ${STATUS_COLORS[selectedReq.status]}`}
                    >
                      {selectedReq.status}
                    </span>
                  ),
                },
                { l: 'Shipment Asal', v: <span className="font-mono text-blue-700">{selectedReq.original_shipment_number}</span> },
                { l: 'PO Number', v: selectedReq.po_number || '-' },
                { l: 'Total Qty', v: <span className="font-bold">{Number(selectedReq.total_requested_qty || 0).toLocaleString('id-ID')} pcs</span> },
                { l: 'Tanggal', v: fmtDate(selectedReq.created_at) },
                { l: 'Alasan', v: <span className="text-xs">{selectedReq.reason || '-'}</span> },
                { l: 'Dibuat Oleh', v: selectedReq.created_by },
              ].map((it) => (
                <div key={it.l} className="bg-muted/40 rounded-lg p-3">
                  <p className="text-xs text-muted-foreground">{it.l}</p>
                  <div className="font-medium text-sm mt-0.5">{it.v}</div>
                </div>
              ))}
            </div>

            {/* Items table */}
            {selectedReq.items?.length > 0 && (
              <div>
                <h4 className="font-semibold text-foreground/90 mb-2">Item yang Diminta</h4>
                <div className="overflow-x-auto border border-border rounded-lg">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/40">
                      <tr>
                        <th className="text-left px-3 py-2 text-xs">Produk</th>
                        <th className="text-left px-3 py-2 text-xs">SKU</th>
                        <th className="text-left px-3 py-2 text-xs text-amber-700">No. Seri</th>
                        <th className="text-left px-3 py-2 text-xs">Size/Warna</th>
                        <th className="text-right px-3 py-2 text-xs">Qty</th>
                        <th className="text-left px-3 py-2 text-xs">Alasan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedReq.items.map((item, idx) => (
                        <tr key={idx} className="border-t border-border/60">
                          <td className="px-3 py-2 font-medium">{item.product_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                          <td className="px-3 py-2 font-mono text-xs text-amber-700 font-semibold">
                            {item.serial_number || <span className="text-muted-foreground/50">—</span>}
                          </td>
                          <td className="px-3 py-2 text-xs">{item.size}/{item.color}</td>
                          <td className="px-3 py-2 text-right font-bold">
                            {Number(item.requested_qty)?.toLocaleString('id-ID')} pcs
                          </td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">{item.reason || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Status banners */}
            {selectedReq.child_shipment_number && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-800">
                ✅ Disetujui! Child shipment <strong className="font-mono">{selectedReq.child_shipment_number}</strong> sudah dibuat oleh {selectedReq.approved_by} pada {fmtDate(selectedReq.approved_at)}.
              </div>
            )}

            {selectedReq.status === 'Rejected' && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                <p className="font-semibold text-red-800 flex items-center gap-2">
                  <XCircle className="w-4 h-4" /> Permintaan Ditolak
                </p>
                {selectedReq.admin_notes && (
                  <p className="text-red-700 mt-1.5">
                    <span className="font-medium">Alasan admin:</span> {selectedReq.admin_notes}
                  </p>
                )}
                {selectedReq.rejected_by && (
                  <p className="text-red-600 text-xs mt-1">
                    Ditolak oleh {selectedReq.rejected_by} pada {fmtDate(selectedReq.rejected_at)}
                  </p>
                )}
                {isAdditional && !selectedReq.resubmitted_as_id && (
                  <button
                    onClick={() => openResubmit(selectedReq)}
                    className="mt-3 flex items-center gap-2 bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-700"
                    data-testid="vendor-mr-resubmit-detail-btn"
                  >
                    <RotateCcw className="w-4 h-4" /> Ajukan Ulang dengan Revisi
                  </button>
                )}
              </div>
            )}

            {selectedReq.resubmitted_as_number && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                ↻ Permintaan ini sudah diajukan ulang sebagai{' '}
                <strong className="font-mono">{selectedReq.resubmitted_as_number}</strong>
              </div>
            )}

            {selectedReq.previous_request_number && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                ↻ Permintaan ini merupakan resubmit dari{' '}
                <strong className="font-mono">{selectedReq.previous_request_number}</strong>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Shipment Picker Modal */}
      {showShipmentPicker && (
        <Modal
          title={createType === 'REPLACEMENT'
            ? 'Pilih Surat Jalan untuk Permintaan Pengganti'
            : 'Pilih Shipment untuk Permintaan Manual'}
          onClose={() => setShowShipmentPicker(false)}
          size="lg"
        >
          <div className="space-y-3">
            <div className={`border rounded-lg p-3 text-sm ${createType === 'REPLACEMENT'
              ? 'bg-red-50 border-red-200 text-red-800'
              : 'bg-amber-50 border-amber-200 text-amber-800'}`}
              data-testid="ship-picker-hint">
              <AlertCircle className="w-4 h-4 inline mr-1.5" />
              {createType === 'REPLACEMENT'
                ? 'Pilih surat jalan yang sudah ter-inspeksi, lalu tandai item yang CACAT/RUSAK beserta qty penggantinya.'
                : 'Pilih shipment yang sudah ter-inspeksi untuk membuat permintaan material tambahan secara manual.'}
            </div>
            {loadingShipPicker ? (
              <div className="p-8 text-center text-muted-foreground/70 text-sm">Memuat shipment...</div>
            ) : inspectedShipments.length === 0 ? (
              <div className="p-8 text-center">
                <Truck className="w-10 h-10 text-muted-foreground/50 mx-auto mb-2" />
                <p className="text-muted-foreground text-sm">Belum ada shipment yang ter-inspeksi.</p>
                <p className="text-muted-foreground/70 text-xs mt-1">Lakukan inspeksi material terlebih dahulu di menu "Inspeksi Material".</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {inspectedShipments.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => pickShipmentForManual(s)}
                    className="w-full text-left p-3 border border-border rounded-lg hover:bg-emerald-50 hover:border-emerald-300 transition-colors"
                    data-testid={`vendor-pick-shipment-${s.id}`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-bold font-mono text-sm text-blue-700">{s.shipment_number}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {(s.items || []).length} item • Tanggal: {fmtDate(s.shipment_date)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                          Inspected
                        </span>
                        {s.shipment_type && s.shipment_type !== 'NORMAL' && (
                          <span
                            className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                              s.shipment_type === 'ADDITIONAL'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-red-100 text-red-700'
                            }`}
                          >
                            {s.shipment_type}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Resubmit modal */}
      {resubmitData && (
        <AdditionalRequestModal
          shipment={resubmitData.shipment}
          defaultItems={resubmitData.defaultItems}
          defaultReason={resubmitData.defaultReason}
          previousRequestId={resubmitData.previousRequestId}
          previousRequestNumber={resubmitData.previousRequestNumber}
          mode="resubmit"
          requestType={resubmitData.requestType || 'ADDITIONAL'}
          onClose={() => setResubmitData(null)}
          onSuccess={() => {
            setResubmitData(null);
            fetchRequests();
          }}
        />
      )}

      {/* Manual request modal */}
      {manualReqShipment && (
        <AdditionalRequestModal
          shipment={manualReqShipment}
          defaultItems={manualReqItems}
          defaultReason={createType === 'REPLACEMENT'
            ? `Material cacat/rusak pada shipment ${manualReqShipment.shipment_number} — mohon diganti`
            : `Permintaan tambahan manual untuk shipment ${manualReqShipment.shipment_number}`}
          mode="manual"
          requestType={createType}
          onClose={() => {
            setManualReqShipment(null);
            setManualReqItems([]);
          }}
          onSuccess={() => {
            setManualReqShipment(null);
            setManualReqItems([]);
            fetchRequests();
          }}
        />
      )}
    </div>
  );
}
