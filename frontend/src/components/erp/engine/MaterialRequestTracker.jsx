/**
 * MaterialRequestTracker — pelacak rantai permintaan material (TAMBAHAN/PENGGANTI).
 *
 * Keluhan pemilik 2026-06: setelah admin menyetujui, permintaan "hilang" dari
 * pandangan. Padahal backend sudah menerbitkan surat jalan anak (`…-R1`) dan
 * mencatat statusnya. Komponen ini menggambar rantainya dalam satu baris supaya
 * vendor maupun admin tahu persis di mana barang penggantinya berada:
 *
 *   Diajukan → Disetujui → SJ pengganti terbit → Diterima vendor → Diinspeksi
 *
 * Angkanya TIDAK dihitung di layar: semua dari `GET /api/material-requests`
 * (`child_shipment_status`, `child_inspected`) — dijaga gate INV-F28.
 */
import { Check, Clock, X, Truck, ClipboardCheck, FileText } from 'lucide-react';

const DONE = 'bg-emerald-100 text-emerald-700 border-emerald-200';
const NOW = 'bg-blue-100 text-blue-700 border-blue-200';
const WAIT = 'bg-muted text-muted-foreground border-border';
const STOP = 'bg-red-100 text-red-700 border-red-200';

export const MaterialRequestTracker = ({ req, compact = true }) => {
  if (!req) return null;
  const rejected = req.status === 'Rejected';
  const approved = req.status === 'Approved';
  const issued = !!req.child_shipment_number;
  const received = ['Received', 'Inspected', 'Completed'].includes(req.child_shipment_status)
    || !!req.child_received_at;
  const inspected = !!req.child_inspected;

  const steps = [
    { key: 'ajukan', label: 'Diajukan', icon: FileText, cls: DONE },
    rejected
      ? { key: 'tolak', label: 'Ditolak', icon: X, cls: STOP }
      : { key: 'setuju', label: 'Disetujui', icon: Check, cls: approved ? DONE : NOW },
  ];
  if (!rejected) {
    steps.push(
      { key: 'terbit', label: issued ? req.child_shipment_number : 'SJ pengganti', icon: FileText,
        cls: issued ? DONE : WAIT, mono: true },
      { key: 'terima', label: received ? 'Diterima vendor' : 'Belum diterima', icon: Truck,
        cls: received ? DONE : (issued ? NOW : WAIT) },
      { key: 'inspeksi', label: inspected ? 'Diinspeksi' : 'Belum diinspeksi', icon: ClipboardCheck,
        cls: inspected ? DONE : (received ? NOW : WAIT) },
    );
  }

  return (
    <div className={`flex items-center flex-wrap ${compact ? 'gap-1' : 'gap-1.5'}`}
      data-testid={`mr-tracker-${req.id}`}>
      {steps.map((s, i) => {
        const Icon = s.icon || Clock;
        return (
          <span key={s.key} className="flex items-center">
            {i > 0 && <span className="w-2 h-px bg-border mx-0.5" />}
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[10px] font-medium whitespace-nowrap ${s.cls} ${s.mono ? 'font-mono' : ''}`}
              data-testid={`mr-tracker-${req.id}-${s.key}`}>
              <Icon className="w-2.5 h-2.5" />{s.label}
            </span>
          </span>
        );
      })}
    </div>
  );
};

export default MaterialRequestTracker;
