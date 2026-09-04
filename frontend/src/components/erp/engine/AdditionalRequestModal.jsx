/**
 * AdditionalRequestModal — Phase 16
 *
 * Reusable modal untuk membuat permintaan material ADDITIONAL (tambahan).
 * Digunakan di 3 entry point:
 *   1) Auto-prompt setelah Inspeksi Material (jika ada missing qty)
 *   2) "Ajukan Ulang" dari permintaan yang Rejected
 *   3) "Buat Permintaan Manual" pada shipment yang sudah ter-inspeksi
 *
 * Props:
 *   - shipment: { id, shipment_number, vendor_name, po_id, po_number, ... }
 *   - defaultItems: array of items dengan field
 *       { shipment_item_id?, po_item_id?, sku, product_name, size, color,
 *         serial_number, requested_qty, reason, max_qty? }
 *   - defaultReason: string (alasan overall default, optional)
 *   - previousRequestId: string optional (untuk mode "Ajukan Ulang")
 *   - previousRequestNumber: string optional (untuk display)
 *   - inspectionId: string optional (link ke inspeksi)
 *   - mode: 'inspection' | 'resubmit' | 'manual'
 *   - onClose: () => void
 *   - onSuccess: (newRequest) => void
 */
import { useState } from 'react';
import { Send, X, AlertCircle, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import { apiPost } from '../../../lib/api';

const MODE_LABELS = {
  inspection: {
    title: 'Ajukan Permintaan Material Tambahan',
    subtitle: 'Material yang hilang/kurang saat inspeksi akan diajukan ke ERP untuk dikirim ulang.',
    submitLabel: 'Ajukan ke ERP',
    badge: 'DARI INSPEKSI',
    badgeColor: 'bg-amber-100 text-amber-800',
  },
  resubmit: {
    title: 'Ajukan Ulang Permintaan',
    subtitle: 'Permintaan sebelumnya ditolak. Anda dapat merevisi qty/alasan dan mengajukan ulang.',
    submitLabel: 'Kirim Permintaan Baru',
    badge: 'AJUKAN ULANG',
    badgeColor: 'bg-blue-100 text-blue-800',
  },
  manual: {
    title: 'Buat Permintaan Material Tambahan',
    subtitle: 'Buat permintaan tambahan secara manual untuk shipment yang sudah ter-inspeksi.',
    submitLabel: 'Kirim Permintaan',
    badge: 'MANUAL',
    badgeColor: 'bg-emerald-100 text-emerald-800',
  },
};

// ── PERMINTAAN PENGGANTI (REPLACEMENT) — 2026-06 ────────────────────────────
// Jenis permintaan ini SUDAH didukung backend (`POST /api/material-requests`
// request_type='REPLACEMENT' → approval membuat surat jalan anak "-R1"), tetapi
// tidak punya satu pun pintu di layar: tombol buat hanya dirender untuk tab
// TAMBAHAN, dan jalur lamanya (Laporan Cacat Material) sudah dimatikan backend
// dengan HTTP 410. Label dipisah supaya vendor tahu ini untuk barang CACAT/RUSAK
// (bukan kurang kirim) — dua hal yang penanganannya berbeda.
const REPLACEMENT_LABELS = {
  inspection: {
    title: 'Ajukan Permintaan Material Pengganti',
    subtitle: 'Material cacat/rusak diajukan ke ERP untuk DIGANTI dengan kiriman baru.',
    submitLabel: 'Ajukan ke ERP',
    badge: 'PENGGANTI',
    badgeColor: 'bg-red-100 text-red-800',
  },
  resubmit: {
    title: 'Ajukan Ulang Permintaan Pengganti',
    subtitle: 'Permintaan sebelumnya ditolak. Anda dapat merevisi qty/alasan dan mengajukan ulang.',
    submitLabel: 'Kirim Permintaan Baru',
    badge: 'PENGGANTI · AJUKAN ULANG',
    badgeColor: 'bg-red-100 text-red-800',
  },
  manual: {
    title: 'Buat Permintaan Material Pengganti',
    subtitle: 'Untuk material yang CACAT/RUSAK (bukan kurang kirim). Sebutkan cacatnya pada alasan per-item.',
    submitLabel: 'Kirim Permintaan',
    badge: 'PENGGANTI',
    badgeColor: 'bg-red-100 text-red-800',
  },
};

export default function AdditionalRequestModal({
  shipment,
  defaultItems = [],
  defaultReason = '',
  previousRequestId = '',
  previousRequestNumber = '',
  inspectionId = '',
  mode = 'inspection',
  requestType = 'ADDITIONAL',
  onClose,
  onSuccess,
}) {
  const isReplacement = requestType === 'REPLACEMENT';
  const cfg = (isReplacement ? REPLACEMENT_LABELS : MODE_LABELS)[mode]
    || (isReplacement ? REPLACEMENT_LABELS.manual : MODE_LABELS.manual);
  const [overallReason, setOverallReason] = useState(
    defaultReason || (isReplacement
      ? `Material cacat/rusak pada shipment ${shipment?.shipment_number || ''} — mohon diganti`
      : `Material missing/kurang dari shipment ${shipment?.shipment_number || ''}`)
  );
  const [items, setItems] = useState(
    (defaultItems || []).map((it) => ({
      shipment_item_id: it.shipment_item_id || '',
      po_item_id: it.po_item_id || '',
      sku: it.sku || '',
      product_name: it.product_name || '',
      size: it.size || '',
      color: it.color || '',
      serial_number: it.serial_number || '',
      requested_qty: Number(it.requested_qty || 0),
      max_qty: it.max_qty != null ? Number(it.max_qty) : null,
      reason: it.reason || '',
    }))
  );
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const updateItem = (idx, field, value) => {
    const next = [...items];
    next[idx] = { ...next[idx], [field]: value };
    setItems(next);
    // Clear field-level error when user types
    if (errors[`item-${idx}-${field}`]) {
      const e = { ...errors };
      delete e[`item-${idx}-${field}`];
      setErrors(e);
    }
  };

  const removeItem = (idx) => {
    setItems(items.filter((_, i) => i !== idx));
  };

  const validate = () => {
    const e = {};
    if (!overallReason.trim()) {
      e.overallReason = 'Alasan keseluruhan wajib diisi';
    }
    const validItems = items.filter((it) => Number(it.requested_qty) > 0);
    if (validItems.length === 0) {
      e.items = 'Minimal harus ada 1 item dengan qty > 0';
    }
    items.forEach((it, idx) => {
      if (Number(it.requested_qty) <= 0) return; // skip 0-qty rows (treated as removed)
      if (it.max_qty != null && Number(it.requested_qty) > it.max_qty) {
        e[`item-${idx}-requested_qty`] = `Maks. ${it.max_qty} pcs`;
      }
      if (!it.reason || !it.reason.trim()) {
        e[`item-${idx}-reason`] = 'Alasan per-item wajib diisi';
      }
    });
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) {
      toast.error('Mohon perbaiki kolom yang ditandai');
      return;
    }
    setLoading(true);
    try {
      const payloadItems = items
        .filter((it) => Number(it.requested_qty) > 0)
        .map((it) => ({
          shipment_item_id: it.shipment_item_id,
          po_item_id: it.po_item_id,
          sku: it.sku,
          product_name: it.product_name,
          size: it.size,
          color: it.color,
          serial_number: it.serial_number,
          requested_qty: Number(it.requested_qty),
          reason: it.reason.trim(),
        }));
      const body = {
        request_type: requestType,
        original_shipment_id: shipment.id,
        po_id: shipment.po_id || '',
        po_number: shipment.po_number || '',
        reason: overallReason.trim(),
        items: payloadItems,
        inspection_id: inspectionId,
        previous_request_id: previousRequestId,
      };
      const data = await apiPost('/material-requests', body);
      toast.success(`Permintaan ${data.request_number} berhasil diajukan ke ERP`);
      if (onSuccess) onSuccess(data);
      onClose();
    } catch (err) {
      toast.error(err.message || 'Gagal mengajukan permintaan');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={cfg.title} onClose={onClose} size="xl">
      <div className="space-y-4" data-testid="additional-request-modal">
        {/* Header info */}
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`px-2.5 py-1 rounded-full text-xs font-semibold ${cfg.badgeColor}`}
            data-testid="additional-request-mode-badge"
          >
            {cfg.badge}
          </span>
          {previousRequestNumber && (
            <span className="text-xs text-muted-foreground">
              Asal dari permintaan: <span className="font-mono font-semibold text-foreground/90">{previousRequestNumber}</span>
            </span>
          )}
        </div>

        <p className="text-sm text-muted-foreground">{cfg.subtitle}</p>

        {/* Shipment summary */}
        <div className="bg-muted/40 border border-border rounded-lg p-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Shipment Asal</p>
            <p className="font-mono font-semibold text-blue-700">{shipment?.shipment_number || '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Vendor</p>
            <p className="font-medium text-foreground">{shipment?.vendor_name || '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">PO Number</p>
            <p className="font-mono text-foreground/90">{shipment?.po_number || '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total Qty Diminta</p>
            <p className="font-bold text-foreground">
              {items.reduce((s, it) => s + Number(it.requested_qty || 0), 0).toLocaleString('id-ID')} pcs
            </p>
          </div>
        </div>

        {/* Overall reason */}
        <div>
          <label className="block text-sm font-medium text-foreground/90 mb-1">
            Alasan Keseluruhan <span className="text-red-500">*</span>
          </label>
          <textarea
            rows={2}
            className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
              errors.overallReason
                ? 'border-red-300 focus:ring-red-300'
                : 'border-border focus:ring-blue-300'
            }`}
            value={overallReason}
            onChange={(e) => {
              setOverallReason(e.target.value);
              if (errors.overallReason) {
                const ne = { ...errors };
                delete ne.overallReason;
                setErrors(ne);
              }
            }}
            placeholder="Jelaskan alasan utama permintaan material tambahan..."
            data-testid="additional-request-overall-reason"
          />
          {errors.overallReason && (
            <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> {errors.overallReason}
            </p>
          )}
        </div>

        {/* Items table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-foreground/90 text-sm">
              Item yang Diminta ({items.filter((i) => Number(i.requested_qty) > 0).length})
            </h4>
            {errors.items && (
              <p className="text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> {errors.items}
              </p>
            )}
          </div>

          <div className="overflow-x-auto border border-border rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 border-b border-border">
                <tr>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Produk</th>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">SKU</th>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-amber-700">No. Seri</th>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Size/Warna</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Qty Diminta</th>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">
                    Alasan <span className="text-red-500">*</span>
                  </th>
                  <th className="px-2 py-2 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-muted-foreground/70 text-sm">
                      Tidak ada item. Tambahkan item dari shipment asal.
                    </td>
                  </tr>
                )}
                {items.map((it, idx) => {
                  const qtyErr = errors[`item-${idx}-requested_qty`];
                  const reasonErr = errors[`item-${idx}-reason`];
                  return (
                    <tr key={idx} className="border-t border-border/60 hover:bg-muted/60/50">
                      <td className="px-3 py-2">
                        <div className="font-medium text-foreground text-sm">{it.product_name || '-'}</div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-blue-700">{it.sku || '-'}</td>
                      <td className="px-3 py-2 font-mono text-xs text-amber-700 font-semibold">
                        {it.serial_number || <span className="text-muted-foreground/50">—</span>}
                      </td>
                      <td className="px-3 py-2 text-xs text-foreground/90">
                        {it.size || '-'}/{it.color || '-'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <input
                          type="number"
                          min={0}
                          max={it.max_qty != null ? it.max_qty : undefined}
                          className={`w-20 text-right border rounded px-2 py-1 text-sm font-semibold focus:outline-none focus:ring-2 ${
                            qtyErr
                              ? 'border-red-300 focus:ring-red-300'
                              : 'border-border focus:ring-blue-300'
                          }`}
                          value={it.requested_qty}
                          onChange={(e) => updateItem(idx, 'requested_qty', e.target.value)}
                          data-testid={`additional-request-item-qty-${idx}`}
                        />
                        {it.max_qty != null && (
                          <p className="text-[10px] text-muted-foreground/70 mt-0.5">maks {it.max_qty}</p>
                        )}
                        {qtyErr && <p className="text-[10px] text-red-600 mt-0.5">{qtyErr}</p>}
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          className={`w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 ${
                            reasonErr
                              ? 'border-red-300 focus:ring-red-300'
                              : 'border-border focus:ring-blue-300'
                          }`}
                          value={it.reason}
                          onChange={(e) => updateItem(idx, 'reason', e.target.value)}
                          placeholder="Alasan spesifik untuk item ini..."
                          data-testid={`additional-request-item-reason-${idx}`}
                        />
                        {reasonErr && <p className="text-[10px] text-red-600 mt-0.5">{reasonErr}</p>}
                      </td>
                      <td className="px-2 py-2 text-center">
                        <button
                          type="button"
                          onClick={() => removeItem(idx)}
                          className="p-1 rounded text-muted-foreground/70 hover:text-red-600 hover:bg-red-50"
                          title="Hapus baris"
                          data-testid={`additional-request-item-remove-${idx}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground/70 mt-2">
            💡 Setel qty ke 0 atau hapus baris untuk mengeluarkan item dari permintaan ini.
          </p>
        </div>

        {/* Footer actions */}
        <div className="flex gap-3 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-muted text-foreground/90 py-2.5 rounded-lg text-sm font-medium hover:bg-muted disabled:opacity-50"
            data-testid="additional-request-cancel-btn"
          >
            <X className="w-4 h-4" /> Batal
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-amber-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-amber-700 disabled:opacity-50"
            data-testid="additional-request-submit-btn"
          >
            <Send className="w-4 h-4" /> {loading ? 'Mengirim...' : cfg.submitLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
