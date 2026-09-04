/**
 * DAReceiveFromCMTModule — "Terima FG dari CMT"
 * ─────────────────────────────────────────────────────────────────────────────
 * DITULIS ULANG (FASE 1+4, audit 2026-07-31 — docs/AUDIT_PRODUKSI_MAKLON_CMT.md)
 *
 * KELUHAN OWNER yang diperbaiki:
 *   • "terlalu banyak step yang tidak perlu, ngapain ada draft, submitted,
 *      approved" → sekarang HANYA 2 status: **Sedang QC** → **Selesai QC**,
 *      diselesaikan dengan SATU tombol (`complete-qc`).
 *   • "buat halaman dalam yang terpisah bodoh sekali, cukup satu table" →
 *      tidak ada modal editor lagi. Baris penerimaan bisa dibuka INLINE
 *      (expand) dan qty lolos / reject diisi langsung di tabel.
 *   • "jika aktualnya ada yang reject bagaimana data di portal vendor?" →
 *      kolom **Produksi vendor tetap** ditampilkan apa adanya (100), lalu
 *      **Lolos** dan **Reject** dipisah, plus badge "Reject belum diputuskan".
 *   • "kalau di-rework kembalikan ke vendor maka harus lewat pipeline yang
 *      benar" → aksi per baris reject: **Permak sendiri** atau
 *      **Retur ke CMT** (membuat Surat Jalan REWORK ke vendor).
 *
 * SSOT backend: `/api/prod/cmt-receipts*` + `/api/prod/cmt-reject-queue`
 *   (routes/dewi_cmt_packing.py, core/production_qty_ledger.py)
 */
import { Fragment, useEffect, useMemo, useState, useCallback } from 'react';
import {
  ClipboardCheck, RefreshCw, Search, AlertTriangle, CheckCircle2,
  ChevronDown, ChevronRight, Package, Info, Loader2, Wrench, Undo2, Ban,
  PackageSearch, Pencil, FileWarning, FileText,
} from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import StaffEntryBadge from './StaffEntryBadge';
import { PdfColumnPicker } from '../pdf/PdfColumnPicker';
import { apiGet, apiPost, apiPut, apiFetch } from '../../../lib/api';

// W5 — kolom yang tercentang saat dialog pertama kali dibuka: VERSI KIRIM MURNI.
// Kolom hasil QC (Qty Terima / Qty Reject) tetap tersedia tapi harus dicentang
// sendiri, sesuai keputusan pemilik 2026-08-20.
const SJ_DEFAULT_COLS = ['no', 'serial', 'sku', 'product', 'size', 'color', 'qty_sent'];

const TABS = [
  { id: 'on_qc', label: 'Sedang QC' },
  { id: 'completed_qc', label: 'Selesai QC' },
  { id: 'all', label: 'Semua' },
];

// Penyelesaian selisih kirim (SSOT: core/short_shipment.CMT_RESOLUTIONS)
const SHORT_RESOLUTIONS = [
  { id: 'dikirim_ulang', label: 'Barang ditemukan & sudah dikirim ulang' },
  { id: 'hilang_tanggungan_vendor', label: 'Dinyatakan hilang — ditanggung vendor CMT' },
  { id: 'hilang_tanggungan_da', label: 'Dinyatakan hilang — ditanggung DA' },
  { id: 'salah_input_dikoreksi', label: 'Ternyata salah input — batalkan selisih' },
];

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID');
const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('id-ID', { dateStyle: 'medium' }); }
  catch { return String(iso).slice(0, 10); }
};

function StatusPill({ status, label }) {
  const map = {
    on_qc: 'bg-amber-100 text-amber-800 border-amber-300',
    completed_qc: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    cancelled: 'bg-slate-200 text-slate-700 border-slate-300',
  };
  return (
    <span className={`inline-flex whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full border ${map[status] || map.cancelled}`}>
      {label || status}
    </span>
  );
}

function NumBox({ value, onChange, disabled, max, testId, tone = 'default' }) {
  const toneCls = tone === 'reject'
    ? 'border-red-300 focus:border-red-500 text-red-700'
    : 'border-border focus:border-[hsl(var(--primary))] text-foreground';
  return (
    <input
      type="number" min={0} max={max}
      value={value === null || value === undefined ? '' : value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      data-testid={testId}
      className={`w-20 h-8 px-2 rounded-md bg-[var(--card-surface,#fff)] border text-xs text-right
                  disabled:opacity-60 disabled:cursor-not-allowed outline-none ${toneCls}`}
    />
  );
}

export default function DAReceiveFromCMTModule() {
  const [receipts, setReceipts] = useState([]);
  const [rejectQueue, setRejectQueue] = useState({ items: [], total_qty_undecided: 0 });
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('on_qc');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState({});          // {receipt_id: true}
  const [draft, setDraft] = useState({});                // {line_id: {qty_actual, reject_qty, reject_reason}}
  const [savingLine, setSavingLine] = useState({});
  const [finishing, setFinishing] = useState({});

  // dialog rework
  const [rework, setRework] = useState(null);            // {line, receipt}
  const [rwQty, setRwQty] = useState('');
  const [rwType, setRwType] = useState('permak_sendiri');
  const [rwCost, setRwCost] = useState('');
  const [rwDeadline, setRwDeadline] = useState('');
  const [rwReason, setRwReason] = useState('');
  const [rwSaving, setRwSaving] = useState(false);

  // ── SELISIH KIRIM (barang belum sampai) ──────────────────────────────────
  const [shorts, setShorts] = useState({ items: [], total_qty_open: 0 });
  const [koreksi, setKoreksi] = useState(null);   // {mode:'qc'|'deklarasi', line, receipt}
  const [korQty, setKorQty] = useState('');
  const [korReject, setKorReject] = useState('');
  const [korReason, setKorReason] = useState('');
  const [korSaving, setKorSaving] = useState(false);
  const [resolveShort, setResolveShort] = useState(null);  // dokumen selisih
  const [resType, setResType] = useState('hilang_tanggungan_vendor');
  const [resNotes, setResNotes] = useState('');
  const [resSaving, setResSaving] = useState(false);

  // ── SURAT JALAN CMT → DA (W5) ────────────────────────────────────────────
  const [sjReceipt, setSjReceipt] = useState(null);   // penerimaan yang dicetak

  const downloadSuratJalan = async (receipt, cols) => {
    try {
      const q = cols?.length ? `&cols=${encodeURIComponent(cols.join(','))}` : '';
      const res = await apiFetch(`/export-pdf?type=cmt-delivery-note&id=${receipt.id}${q}`);
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        toast.error(`Gagal membuat surat jalan: ${d.detail || d.error || res.status}`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `SJ-CMT-${receipt.receipt_code}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Surat jalan ${receipt.receipt_code} diunduh`);
    } catch (e) {
      toast.error(`Gagal membuat surat jalan: ${e.message || e}`);
    }
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      // KPI diambil dari `summary` (SELALU global / semua status) supaya angkanya
      // tidak berubah mengikuti tab yang dibuka — dulu kartu "Lolos QC"/"Reject"
      // menunjukkan 0 saat tab "Sedang QC" aktif walau ada reject di antrean.
      const [list, rq, sum, sh] = await Promise.all([
        apiGet(`/prod/cmt-receipts${tab !== 'all' ? `?status=${tab}` : ''}`),
        apiGet('/prod/cmt-reject-queue'),
        apiGet('/prod/cmt-receipts/summary').catch(() => null),
        apiGet('/prod/short-shipments?status=open').catch(() => null),
      ]);
      setReceipts(Array.isArray(list) ? list : []);
      setRejectQueue(rq && typeof rq === 'object' ? rq : { items: [] });
      setSummary(sum && typeof sum === 'object' ? sum : null);
      setShorts(sh && typeof sh === 'object' ? sh : { items: [], total_qty_open: 0 });
    } catch (e) {
      toast.error(`Gagal memuat penerimaan: ${e.message || e}`);
      setReceipts([]);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return receipts;
    return receipts.filter(r =>
      [r.receipt_code, r.cmt_name, r.po_number, r.delivery_note].some(v =>
        String(v || '').toLowerCase().includes(q)));
  }, [receipts, search]);

  const kpi = useMemo(() => {
    const onQc = receipts.filter(r => r.status === 'on_qc');
    const localAccepted = receipts.reduce((s, r) => s + Number(r.total_qty_actual || 0), 0);
    const localReject = receipts.reduce((s, r) => s + Number(r.total_qty_reject || 0), 0);
    return {
      on_qc: summary ? Number(summary.on_qc || 0) : onQc.length,
      uncounted: summary ? Number(summary.uncounted_lines || 0)
        : onQc.reduce((s, r) => s + Number(r.uncounted_lines || 0), 0),
      reject_undecided: Number(rejectQueue.total_qty_undecided || summary?.reject_pending_decision || 0),
      accepted: summary ? Number(summary.pcs_accepted_total || 0) : localAccepted,
      reject: summary ? Number(summary.pcs_reject_total || 0) : localReject,
      short_open: Number(shorts.total_qty_open || 0),
    };
  }, [receipts, rejectQueue, summary, shorts]);

  const completeQcSummary = (receipt, res) => {
    const led = res?.qty_ledger;
    const shortPcs = Number(led?.short || 0);
    const parts = [`QC selesai. Stok FG +${fmtNum(receipt.total_qty_actual)} pcs`];
    if (led?.quarantined) parts.push(`${fmtNum(led.quarantined)} pcs reject masuk karantina`);
    if (shortPcs > 0) {
      parts.push(`${fmtNum(shortPcs)} pcs BELUM SAMPAI → dokumen selisih ` +
        `${(led.shorts || []).map(s => s.short_number).join(', ')} dibuka & vendor diberi tahu`);
    }
    if (Number(led?.short_resolved || 0) > 0) {
      parts.push(`${fmtNum(led.short_resolved)} pcs selisih lama tertutup (kirim ulang)`);
    }
    if (res?.ap_mature?.payment_code) parts.push(`Tagihan CMT ${res.ap_mature.payment_code}`);
    return parts.join(' · ');
  };

  const lineValue = (line, field) => {
    const d = draft[line.id];
    if (d && d[field] !== undefined) return d[field];
    return line[field];
  };

  const setLineDraft = (line, field, val) => {
    setDraft(p => ({ ...p, [line.id]: { ...(p[line.id] || {}), [field]: val } }));
  };

  const saveLine = async (receipt, line) => {
    const d = draft[line.id];
    if (!d) return;
    const declared = Number(line.qty_shipped_by_cmt || 0);
    const qa = d.qty_actual !== undefined ? Number(d.qty_actual || 0) : Number(line.qty_actual || 0);
    const rj = d.reject_qty !== undefined ? Number(d.reject_qty || 0) : Number(line.reject_qty || 0);
    if (declared && qa + rj > declared) {
      toast.error(`Lolos (${qa}) + Reject (${rj}) melebihi kiriman vendor (${declared})`);
      return;
    }
    setSavingLine(p => ({ ...p, [line.id]: true }));
    try {
      await apiPut(`/prod/cmt-receipts/${receipt.id}/lines/${line.id}`, {
        qty_actual: qa, reject_qty: rj,
        reject_reason: d.reject_reason !== undefined ? d.reject_reason : (line.reject_reason || ''),
      });
      setDraft(p => { const n = { ...p }; delete n[line.id]; return n; });
      await fetchAll();
      toast.success('Angka QC disimpan');
    } catch (e) {
      toast.error(`Gagal simpan: ${e.message || e}`);
    } finally {
      setSavingLine(p => ({ ...p, [line.id]: false }));
    }
  };

  const completeQc = async (receipt) => {
    setFinishing(p => ({ ...p, [receipt.id]: true }));
    try {
      const res = await apiPost(`/prod/cmt-receipts/${receipt.id}/complete-qc`, {});
      const led = res?.qty_ledger;
      toast.success(completeQcSummary(receipt, res), { duration: 9000 });
      if (led?.errors?.length) toast.warning(led.errors[0], { duration: 9000 });
      await fetchAll();
    } catch (e) {
      toast.error(`Gagal menyelesaikan QC: ${e.message || e}`);
    } finally {
      setFinishing(p => ({ ...p, [receipt.id]: false }));
    }
  };

  // ── KOREKSI RESMI (setelah QC selesai) ──────────────────────────────────
  const openKoreksi = (mode, line, receipt) => {
    setKoreksi({ mode, line, receipt });
    setKorQty(String(mode === 'qc' ? Number(line.qty_actual || 0)
      : Number(line.qty_claimed_by_cmt || line.qty_shipped_by_cmt || 0)));
    setKorReject(String(Number(line.reject_qty || 0)));
    setKorReason('');
  };

  const submitKoreksi = async () => {
    if (!koreksi) return;
    if (!korReason.trim()) { toast.error('Alasan koreksi wajib diisi'); return; }
    setKorSaving(true);
    try {
      const { mode, line, receipt } = koreksi;
      if (mode === 'qc') {
        const res = await apiPost(
          `/prod/cmt-receipts/${receipt.id}/lines/${line.id}/koreksi-hasil-qc`,
          { qty_actual: Number(korQty || 0), reject_qty: Number(korReject || 0), reason: korReason });
        const d = res?.stock?.delta;
        toast.success('Koreksi hasil QC tersimpan'
          + (d ? ` · stok FG ${d > 0 ? '+' : ''}${d} pcs` : '')
          + (res?.short ? ` · selisih ${res.short.short_number} = ${res.short.qty_short} pcs`
            : ' · tidak ada selisih'), { duration: 8000 });
      } else {
        const res = await apiPost(
          `/prod/cmt-receipts/${receipt.id}/lines/${line.id}/koreksi-deklarasi`,
          { qty_claimed: Number(korQty || 0), reason: korReason });
        toast.success('Klaim vendor dikoreksi & dokumen deklarasi dirambatkan'
          + (res?.short ? ` · selisih ${res.short.short_number} = ${res.short.qty_short} pcs`
            : ' · selisih dibatalkan'), { duration: 8000 });
      }
      setKoreksi(null);
      await fetchAll();
    } catch (e) {
      toast.error(`Gagal koreksi: ${e.message || e}`);
    } finally {
      setKorSaving(false);
    }
  };

  // ── PENYELESAIAN SELISIH KIRIM ──────────────────────────────────────────
  const submitResolveShort = async () => {
    if (!resolveShort) return;
    setResSaving(true);
    try {
      await apiPost(`/prod/short-shipments/${resolveShort.id}/resolve`,
        { resolution: resType, notes: resNotes });
      toast.success(`Selisih ${resolveShort.short_number} diselesaikan`, { duration: 6000 });
      setResolveShort(null); setResNotes('');
      await fetchAll();
    } catch (e) {
      toast.error(`Gagal menyelesaikan selisih: ${e.message || e}`);
    } finally {
      setResSaving(false);
    }
  };

  const cancelReceipt = async (receipt) => {
    if (!window.confirm(`Batalkan penerimaan ${receipt.receipt_code}? (dipakai bila salah input)`)) return;
    try {
      await apiPost(`/prod/cmt-receipts/${receipt.id}/reject`, { reason: 'Dibatalkan oleh admin' });
      toast.success('Penerimaan dibatalkan');
      await fetchAll();
    } catch (e) {
      toast.error(`Gagal batalkan: ${e.message || e}`);
    }
  };

  const openRework = (line, receipt, defaultType = 'permak_sendiri') => {
    const undecided = rejectQueue.items.find(x => x.receipt_line_id === line.id);
    setRework({ line, receipt });
    setRwQty(String(undecided ? undecided.qty_undecided : Number(line.reject_qty || 0)));
    setRwType(defaultType);
    setRwCost('');
    setRwDeadline('');
    setRwReason(line.reject_reason || '');
  };

  const submitRework = async () => {
    if (!rework) return;
    const q = Number(rwQty);
    if (!q || q <= 0) { toast.error('Qty harus > 0'); return; }
    setRwSaving(true);
    try {
      const res = await apiPost('/dewi/cmt-permak/from-receipt-line', {
        receipt_line_id: rework.line.id,
        qty: q,
        permak_type: rwType,
        cost_per_pcs: Number(rwCost || 0),
        return_deadline: rwDeadline || null,
        reason: rwReason,
      });
      if (rwType === 'retur_ke_cmt') {
        const sj = res?.rework?.shipment_number;
        toast.success(sj
          ? `Retur ke CMT dibuat. Surat Jalan REWORK ${sj} kini muncul di Portal Vendor.`
          : 'Retur ke CMT dibuat.', { duration: 8000 });
        if (res?.rework && res.rework.ok === false) {
          toast.warning(res.rework.error || 'SJ rework gagal dibuat', { duration: 9000 });
        }
      } else {
        toast.success(`Permak sendiri ${q} pcs dibuat (${res?.permak_number || ''}). ` +
          'Saat ditandai berhasil, stok FG & qty diterima PO otomatis bertambah.',
          { duration: 8000 });
      }
      setRework(null);
      await fetchAll();
    } catch (e) {
      toast.error(`Gagal: ${e.message || e}`);
    } finally {
      setRwSaving(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="da-receive-cmt-module">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <ClipboardCheck className="w-5 h-5 text-[hsl(var(--primary))] shrink-0" />
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-foreground truncate">Terima FG dari CMT</h2>
            <p className="text-xs text-muted-foreground">
              Hitung fisik lalu selesaikan QC — satu tabel, dua status.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Cari kode / CMT / PO…"
              data-testid="receipt-search"
              className="h-9 pl-8 pr-3 w-56 rounded-lg bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground outline-none focus:border-[hsl(var(--primary))]"
            />
          </div>
          <button onClick={fetchAll} disabled={loading} data-testid="receipt-refresh"
            className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-foreground/5 inline-flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
          </button>
        </div>
      </div>

      {/* ── KPI ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          { k: 'on_qc', label: 'Sedang QC', val: kpi.on_qc, sub: `${fmtNum(kpi.uncounted)} baris belum dihitung`, icon: Package, cls: 'text-amber-700' },
          { k: 'accepted', label: 'Lolos QC (pcs)', val: kpi.accepted, sub: 'total masuk stok FG', icon: CheckCircle2, cls: 'text-emerald-700' },
          { k: 'reject', label: 'Reject (pcs)', val: kpi.reject, sub: 'total masuk karantina', icon: AlertTriangle, cls: 'text-red-700' },
          { k: 'undecided', label: 'Reject belum diputuskan', val: kpi.reject_undecided, sub: 'perlu permak / retur CMT', icon: Wrench, cls: 'text-orange-700' },
          { k: 'short', label: 'Belum sampai (pcs)', val: kpi.short_open, sub: 'kewajiban vendor — harus dikirim ulang', icon: PackageSearch, cls: 'text-rose-700' },
        ].map(c => (
          <div key={c.k} data-testid={`receipt-kpi-${c.k}`}
            className="rounded-xl bg-[var(--card-surface,#fff)] border border-[var(--glass-border,rgba(0,0,0,0.08))] shadow-[var(--shadow-card,0_1px_2px_rgba(0,0,0,0.06))] p-3 min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <c.icon className={`w-3.5 h-3.5 ${c.cls} shrink-0`} />
              <span className="text-[11px] font-semibold text-muted-foreground truncate">{c.label}</span>
            </div>
            <div className={`text-2xl font-bold ${c.cls} leading-tight`}>{fmtNum(c.val)}</div>
            <div className="text-[11px] text-muted-foreground mt-0.5 break-words">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* ── Antrean reject (supaya reject TIDAK PERNAH hilang) ─────────── */}
      {rejectQueue.items?.length > 0 && (
        <div className="rounded-xl bg-[var(--card-surface,#fff)] border border-orange-300 shadow-[var(--shadow-card,0_1px_2px_rgba(0,0,0,0.06))] overflow-hidden"
          data-testid="reject-queue-panel">
          <div className="px-3 py-2 bg-orange-50 border-b border-orange-200 flex items-center gap-2">
            <Wrench className="w-4 h-4 text-orange-700 shrink-0" />
            <span className="text-xs font-bold text-orange-900">
              Antrean Reject — {fmtNum(rejectQueue.total_qty_undecided)} pcs belum diputuskan
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[820px]">
              <thead className="bg-foreground/[0.04]">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2 font-semibold">Penerimaan</th>
                  <th className="px-3 py-2 font-semibold">PO / Vendor</th>
                  <th className="px-3 py-2 font-semibold">SKU</th>
                  <th className="px-3 py-2 font-semibold text-right">Reject</th>
                  <th className="px-3 py-2 font-semibold text-right">Belum diputuskan</th>
                  <th className="px-3 py-2 font-semibold">Alasan</th>
                  <th className="px-3 py-2 font-semibold text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rejectQueue.items.map(r => (
                  <tr key={r.receipt_line_id} className="border-t border-foreground/5">
                    <td className="px-3 py-2 font-mono text-[11px] text-foreground whitespace-nowrap">{r.receipt_code}</td>
                    <td className="px-3 py-2 text-foreground">
                      <div className="font-medium truncate max-w-[180px]">{r.po_number || '—'}</div>
                      <div className="text-[11px] text-muted-foreground truncate max-w-[180px]">{r.vendor_name || '—'}</div>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-foreground whitespace-nowrap">{r.sku || '—'}</td>
                    <td className="px-3 py-2 text-right font-semibold text-red-700">{fmtNum(r.qty_reject)}</td>
                    <td className="px-3 py-2 text-right font-bold text-orange-700">{fmtNum(r.qty_undecided)}</td>
                    <td className="px-3 py-2 text-muted-foreground max-w-[160px] truncate">{r.reject_reason || '—'}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1.5 flex-wrap">
                        <button data-testid={`rq-permak-${r.receipt_line_id}`}
                          onClick={() => openRework({ id: r.receipt_line_id, reject_qty: r.qty_reject, reject_reason: r.reject_reason },
                            { id: r.receipt_id, receipt_code: r.receipt_code }, 'permak_sendiri')}
                          className="h-7 px-2 rounded-md border border-border text-[11px] font-medium text-foreground hover:bg-foreground/5 whitespace-nowrap">
                          Permak sendiri
                        </button>
                        <button data-testid={`rq-retur-${r.receipt_line_id}`}
                          onClick={() => openRework({ id: r.receipt_line_id, reject_qty: r.qty_reject, reject_reason: r.reject_reason },
                            { id: r.receipt_id, receipt_code: r.receipt_code }, 'retur_ke_cmt')}
                          className="h-7 px-2 rounded-md bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-[11px] font-semibold hover:opacity-90 whitespace-nowrap inline-flex items-center gap-1">
                          <Undo2 className="w-3 h-3" /> Retur ke CMT
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Selisih kirim: barang BELUM SAMPAI (kewajiban vendor) ───────── */}
      {shorts.items?.length > 0 && (
        <div className="rounded-xl bg-[var(--card-surface,#fff)] border border-rose-300 shadow-[var(--shadow-card,0_1px_2px_rgba(0,0,0,0.06))] overflow-hidden"
          data-testid="short-shipment-panel">
          <div className="px-3 py-2 bg-rose-50 border-b border-rose-200 flex items-center gap-2 flex-wrap">
            <PackageSearch className="w-4 h-4 text-rose-700 shrink-0" />
            <span className="text-xs font-bold text-rose-900">
              Selisih Kirim — {fmtNum(shorts.total_qty_open)} pcs BELUM SAMPAI dari vendor
            </span>
            <span className="text-[11px] text-rose-700">
              Dokumen sudah dikoreksi ke qty yang diterima; sisa kirim vendor terbuka kembali.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[900px]">
              <thead className="bg-foreground/[0.04]">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2 font-semibold">No. Selisih</th>
                  <th className="px-3 py-2 font-semibold">PO / Vendor</th>
                  <th className="px-3 py-2 font-semibold">SKU</th>
                  <th className="px-3 py-2 font-semibold text-right">Klaim</th>
                  <th className="px-3 py-2 font-semibold text-right">Sampai</th>
                  <th className="px-3 py-2 font-semibold text-right">Belum sampai</th>
                  <th className="px-3 py-2 font-semibold">Penerimaan</th>
                  <th className="px-3 py-2 font-semibold text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {shorts.items.map(s => (
                  <tr key={s.id} className="border-t border-foreground/5">
                    <td className="px-3 py-2 font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">{s.short_number}</td>
                    <td className="px-3 py-2 text-foreground">
                      <div className="font-medium truncate max-w-[170px]">{s.po_number || '—'}</div>
                      <div className="text-[11px] text-muted-foreground truncate max-w-[170px]">{s.vendor_name || '—'}</div>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-foreground whitespace-nowrap">{s.sku || '—'}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{fmtNum(s.qty_claimed)}</td>
                    <td className="px-3 py-2 text-right text-emerald-700 font-medium">{fmtNum(s.qty_arrived)}</td>
                    <td className="px-3 py-2 text-right font-bold text-rose-700">{fmtNum(s.qty_open ?? s.qty_short)}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground whitespace-nowrap">{s.receipt_code || '—'}</td>
                    <td className="px-3 py-2 text-right">
                      <button data-testid={`short-resolve-${s.short_number}`}
                        onClick={() => { setResolveShort(s); setResType('hilang_tanggungan_vendor'); setResNotes(''); }}
                        className="h-7 px-2.5 rounded-md bg-rose-600 text-white text-[11px] font-semibold hover:bg-rose-700 whitespace-nowrap">
                        Selesaikan
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-3 py-2 bg-rose-50/60 border-t border-rose-200 text-[11px] text-rose-800">
            Jalur normal: vendor menemukan barangnya lalu <strong>mengirim ulang</strong> — selisih
            tertutup OTOMATIS saat penerimaan kiriman ulang selesai QC. Tombol
            <strong> Selesaikan</strong> dipakai bila barang dinyatakan hilang atau ternyata salah input.
          </div>
        </div>
      )}

      {/* ── Tabs ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`receipt-tab-${t.id}`}
            className={`h-8 px-3 rounded-lg text-xs font-semibold border transition-colors whitespace-nowrap ${
              tab === t.id
                ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] border-transparent'
                : 'bg-[var(--card-surface,#fff)] text-foreground border-border hover:bg-foreground/5'}`}>
            {t.label}
          </button>
        ))}
        <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1 ml-1">
          <Info className="w-3 h-3 shrink-0" />
          Vendor deklarasi kirim → penerimaan otomatis muncul di sini
        </span>
      </div>

      {/* ── Tabel utama ───────────────────────────────────────────────── */}
      <div className="rounded-xl bg-[var(--card-surface,#fff)] border border-[var(--glass-border,rgba(0,0,0,0.08))] shadow-[var(--shadow-card,0_1px_2px_rgba(0,0,0,0.06))] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[1180px]" data-testid="receipt-table">
            <thead className="bg-foreground/[0.04]">
              <tr className="text-left text-muted-foreground">
                <th className="px-2 py-2 w-8" />
                <th className="px-3 py-2 font-semibold">Kode / Tanggal</th>
                <th className="px-3 py-2 font-semibold">Vendor CMT</th>
                <th className="px-3 py-2 font-semibold">PO</th>
                <th className="px-3 py-2 font-semibold text-right">Klaim vendor</th>
                <th className="px-3 py-2 font-semibold text-right">Sampai (dokumen)</th>
                <th className="px-3 py-2 font-semibold text-right">Lolos QC</th>
                <th className="px-3 py-2 font-semibold text-right">Reject</th>
                <th className="px-3 py-2 font-semibold text-right">Belum sampai</th>
                <th className="px-3 py-2 font-semibold text-right">Blm diputuskan</th>
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="px-3 py-2 font-semibold text-right">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={12} className="px-3 py-10 text-center text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Memuat…
                </td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={12} className="px-3 py-10 text-center text-muted-foreground">
                  Belum ada penerimaan pada tab ini.
                </td></tr>
              )}
              {!loading && filtered.map(r => {
                const open = !!expanded[r.id];
                const editable = r.status === 'on_qc';
                return (
                  <Fragment key={r.id}>
                    <tr className="border-t border-foreground/5 hover:bg-foreground/[0.02] align-top"
                      data-testid={`receipt-row-${r.receipt_code}`}>
                      <td className="px-2 py-2">
                        <button onClick={() => setExpanded(p => ({ ...p, [r.id]: !p[r.id] }))}
                          data-testid={`receipt-expand-${r.receipt_code}`}
                          className="w-6 h-6 rounded-md hover:bg-foreground/10 inline-flex items-center justify-center text-foreground">
                          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">{r.receipt_code}</div>
                        <div className="text-[11px] text-muted-foreground whitespace-nowrap">{fmtDate(r.receipt_date || r.created_at)}</div>
                      </td>
                      <td className="px-3 py-2 text-foreground max-w-[180px] break-words">
                        {r.cmt_name || '—'}
                        {/* keputusan 3a — deklarasi kirim CMT→DA bisa diketik STAF DA
                            (vendor tidak memakai sistem). Layar ini gerbang UANG, jadi
                            asal angkanya harus terlihat sebelum qty_actual diisi. */}
                        {r.declaration_entered_by_staff && (
                          <span className="mt-1 block">
                            <StaffEntryBadge source="staff" by={r.declaration_entered_by} compact
                              testId={`da-receive-entry-badge-${r.receipt_code}`} />
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-foreground max-w-[160px] break-words">{r.po_number || '—'}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{fmtNum(r.total_claimed_by_cmt ?? r.total_shipped_by_cmt)}</td>
                      <td className="px-3 py-2 text-right font-medium text-foreground">{fmtNum(r.total_shipped_by_cmt)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-emerald-700">{fmtNum(r.total_qty_actual)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-red-700">{fmtNum(r.total_qty_reject)}</td>
                      <td className={`px-3 py-2 text-right font-bold ${Number(r.total_qty_short_open || 0) > 0 ? 'text-rose-700 bg-rose-50' : 'text-muted-foreground'}`}
                        data-testid={`receipt-short-${r.receipt_code}`}>
                        {fmtNum(r.total_qty_short_open ?? r.total_qty_short)}
                      </td>
                      <td className="px-3 py-2 text-right font-bold text-orange-700">{fmtNum(r.total_reject_undecided)}</td>
                      <td className="px-3 py-2"><StatusPill status={r.status} label={r.status_label} /></td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {/* W5 — surat jalan CMT → DA (boleh dicetak kapan saja;
                              kolom hasil QC tinggal dicentang bila sudah diisi) */}
                          <button
                            onClick={() => setSjReceipt(r)}
                            title="Cetak Surat Jalan CMT → DA (pilih kolom)"
                            data-testid={`receipt-surat-jalan-${r.receipt_code}`}
                            className="h-7 px-2 rounded-md border border-border text-[11px] font-medium text-foreground hover:bg-foreground/5 inline-flex items-center gap-1 whitespace-nowrap">
                            <FileText className="w-3 h-3" /> Surat Jalan
                          </button>
                          {editable && (
                            <>
                              <button
                                onClick={() => completeQc(r)}
                                disabled={!r.can_complete_qc || finishing[r.id]}
                                title={r.can_complete_qc ? 'Selesaikan QC' : 'Isi qty lolos semua baris dulu'}
                                data-testid={`receipt-complete-${r.receipt_code}`}
                                className="h-7 px-2.5 rounded-md bg-emerald-600 text-white text-[11px] font-semibold hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1 whitespace-nowrap">
                                {finishing[r.id] ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                                Selesaikan QC
                              </button>
                              <button onClick={() => cancelReceipt(r)} data-testid={`receipt-cancel-${r.receipt_code}`}
                                className="h-7 px-2 rounded-md border border-border text-[11px] text-muted-foreground hover:bg-foreground/5 inline-flex items-center gap-1">
                                <Ban className="w-3 h-3" /> Batal
                              </button>
                            </>
                          )}
                          {!editable && r.pass_rate != null && (
                            <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                              Pass {r.pass_rate}% · Reject {r.reject_rate}%
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>

                    {open && (
                      <tr className="border-t border-foreground/5 bg-foreground/[0.015]">
                        <td colSpan={12} className="px-3 py-3">
                          <div className="rounded-lg bg-[var(--card-surface,#fff)] border border-[var(--glass-border,rgba(0,0,0,0.08))] overflow-hidden">
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs min-w-[1020px]">
                                <thead className="bg-foreground/[0.04]">
                                  <tr className="text-left text-muted-foreground">
                                    <th className="px-3 py-2 font-semibold">SKU / Produk</th>
                                    <th className="px-3 py-2 font-semibold">Warna · Size</th>
                                    <th className="px-3 py-2 font-semibold text-right">Klaim vendor</th>
                                    <th className="px-3 py-2 font-semibold text-right">Lolos QC</th>
                                    <th className="px-3 py-2 font-semibold text-right">Reject</th>
                                    <th className="px-3 py-2 font-semibold text-right">Belum sampai</th>
                                    <th className="px-3 py-2 font-semibold">Alasan reject</th>
                                    <th className="px-3 py-2 font-semibold text-right">Aksi</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(r.lines || []).length === 0 && (
                                    <tr><td colSpan={8} className="px-3 py-5 text-center text-muted-foreground">
                                      Belum ada baris — deklarasi vendor mungkin kosong.
                                    </td></tr>
                                  )}
                                  {(r.lines || []).map(line => {
                                    const dirty = !!draft[line.id];
                                    const claimed = Number(line.qty_claimed_by_cmt || line.qty_shipped_by_cmt || 0);
                                    const declared = Number(line.qty_shipped_by_cmt || 0);
                                    const shortQty = Math.max(0, Number(line.qty_short || 0) - Number(line.qty_short_resolved || 0));
                                    const shortOpen = (line.short_status === 'open') ? shortQty : 0;
                                    return (
                                      <tr key={line.id} className="border-t border-foreground/5 align-middle">
                                        <td className="px-3 py-2">
                                          <div className="font-mono text-[11px] font-semibold text-foreground">{line.sku_code || '—'}</div>
                                          <div className="text-[11px] text-muted-foreground break-words max-w-[220px]">{line.product_name || ''}</div>
                                        </td>
                                        <td className="px-3 py-2 text-foreground whitespace-nowrap">
                                          {[line.color, line.size].filter(Boolean).join(' · ') || '—'}
                                        </td>
                                        <td className="px-3 py-2 text-right font-medium text-foreground">
                                          {fmtNum(claimed)}
                                          {!editable && claimed !== declared && (
                                            <div className="text-[10px] text-rose-700 font-semibold whitespace-nowrap">
                                              dokumen: {fmtNum(declared)}
                                            </div>
                                          )}
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                          <NumBox value={lineValue(line, 'qty_actual')} max={claimed || undefined}
                                            disabled={!editable} testId={`line-qty-${line.id}`}
                                            onChange={v => setLineDraft(line, 'qty_actual', v)} />
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                          <NumBox value={lineValue(line, 'reject_qty')} max={claimed || undefined}
                                            disabled={!editable} tone="reject" testId={`line-reject-${line.id}`}
                                            onChange={v => setLineDraft(line, 'reject_qty', v)} />
                                        </td>
                                        <td className={`px-3 py-2 text-right font-bold ${shortOpen > 0 ? 'text-rose-700 bg-rose-50' : 'text-muted-foreground'}`}
                                          data-testid={`line-short-${line.id}`}
                                          title={shortOpen > 0 ? 'Barang belum sampai — kewajiban vendor, dokumen sudah dikoreksi' : ''}>
                                          {fmtNum(shortOpen)}
                                        </td>
                                        <td className="px-3 py-2">
                                          <input
                                            value={lineValue(line, 'reject_reason') || ''}
                                            onChange={e => setLineDraft(line, 'reject_reason', e.target.value)}
                                            disabled={!editable}
                                            placeholder="mis. jahitan lepas"
                                            data-testid={`line-reason-${line.id}`}
                                            className="w-44 h-8 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground outline-none focus:border-[hsl(var(--primary))] disabled:opacity-60"
                                          />
                                        </td>
                                        <td className="px-3 py-2">
                                          <div className="flex items-center justify-end gap-1.5 flex-wrap">
                                            {editable && (
                                              <button onClick={() => saveLine(r, line)} disabled={!dirty || savingLine[line.id]}
                                                data-testid={`line-save-${line.id}`}
                                                className="h-7 px-2.5 rounded-md bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-[11px] font-semibold hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-1 whitespace-nowrap">
                                                {savingLine[line.id] ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                                Simpan
                                              </button>
                                            )}
                                            {!editable && (
                                              <>
                                                <button onClick={() => openKoreksi('qc', line, r)}
                                                  data-testid={`line-koreksi-qc-${line.id}`}
                                                  title="Koreksi resmi qty lolos QC — stok FG & buku kuantitas ikut dikoreksi"
                                                  className="h-7 px-2 rounded-md border border-border text-[11px] font-medium text-foreground hover:bg-foreground/5 whitespace-nowrap inline-flex items-center gap-1">
                                                  <Pencil className="w-3 h-3" /> Koreksi hasil QC
                                                </button>
                                                <button onClick={() => openKoreksi('deklarasi', line, r)}
                                                  data-testid={`line-koreksi-deklarasi-${line.id}`}
                                                  title="Koreksi klaim vendor (dirambatkan ke dokumen deklarasi + notifikasi vendor)"
                                                  className="h-7 px-2 rounded-md border border-rose-300 text-[11px] font-medium text-rose-700 hover:bg-rose-50 whitespace-nowrap inline-flex items-center gap-1">
                                                  <FileWarning className="w-3 h-3" /> Koreksi deklarasi
                                                </button>
                                              </>
                                            )}
                                            {!editable && Number(line.reject_qty || 0) > 0 && (
                                              <>
                                                <button onClick={() => openRework(line, r, 'permak_sendiri')}
                                                  data-testid={`line-permak-${line.id}`}
                                                  className="h-7 px-2 rounded-md border border-border text-[11px] font-medium text-foreground hover:bg-foreground/5 whitespace-nowrap">
                                                  Permak sendiri
                                                </button>
                                                <button onClick={() => openRework(line, r, 'retur_ke_cmt')}
                                                  data-testid={`line-retur-${line.id}`}
                                                  className="h-7 px-2 rounded-md bg-orange-600 text-white text-[11px] font-semibold hover:bg-orange-700 whitespace-nowrap inline-flex items-center gap-1">
                                                  <Undo2 className="w-3 h-3" /> Retur CMT
                                                </button>
                                              </>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                          {editable && (
                            <p className="text-[11px] text-muted-foreground mt-2">
                              Isi <strong>Lolos QC</strong> dan <strong>Reject</strong> lalu Simpan per baris.
                              Setelah semua baris terisi, tombol <strong>Selesaikan QC</strong> aktif —
                              stok FG naik sebesar qty lolos, reject masuk karantina, tagihan CMT dibuat otomatis.
                              Bila <strong>lolos + reject &lt; klaim vendor</strong>, sisanya otomatis dicatat sebagai
                              <strong> selisih kirim (belum sampai)</strong>: dokumen deklarasi vendor dikoreksi ke qty
                              yang benar-benar sampai, vendor diberi notifikasi, dan sisa kirim vendor terbuka kembali.
                            </p>
                          )}
                          {!editable && (
                            <p className="text-[11px] text-muted-foreground mt-2">
                              QC sudah selesai — angka TIDAK bisa diubah langsung. Pakai
                              <strong> Koreksi hasil QC</strong> (stok FG & buku kuantitas ikut dikoreksi) atau
                              <strong> Koreksi deklarasi</strong> (klaim vendor salah tulis). Semua koreksi
                              wajib beralasan dan tercatat di jejak audit.
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Dialog rework ─────────────────────────────────────────────── */}
      {rework && (
        <Modal
          onClose={() => setRework(null)}
          title={rwType === 'retur_ke_cmt' ? 'Retur Reject ke Vendor CMT' : 'Permak Sendiri'}
          size="lg">
          <div className="space-y-3" data-testid="rework-dialog">
            <div className="rounded-lg bg-foreground/[0.04] border border-border p-3 text-xs text-foreground">
              <div><span className="text-muted-foreground">Penerimaan:</span> <strong>{rework.receipt.receipt_code}</strong></div>
              <div><span className="text-muted-foreground">Reject tercatat:</span> <strong>{fmtNum(rework.line.reject_qty)} pcs</strong></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[11px] font-semibold text-muted-foreground">Jenis penanganan</span>
                <select value={rwType} onChange={e => setRwType(e.target.value)} data-testid="rework-type"
                  className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground">
                  <option value="permak_sendiri">Permak sendiri (diperbaiki di DA)</option>
                  <option value="retur_ke_cmt">Retur ke CMT (vendor kerjakan ulang)</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold text-muted-foreground">Qty</span>
                <input type="number" min={1} value={rwQty} onChange={e => setRwQty(e.target.value)}
                  data-testid="rework-qty"
                  className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold text-muted-foreground">Ongkos / pcs (Rp)</span>
                <input type="number" min={0} value={rwCost} onChange={e => setRwCost(e.target.value)}
                  className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold text-muted-foreground">Target kembali</span>
                <input type="date" value={rwDeadline} onChange={e => setRwDeadline(e.target.value)}
                  className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
              </label>
            </div>
            <label className="block">
              <span className="text-[11px] font-semibold text-muted-foreground">Alasan / instruksi</span>
              <textarea value={rwReason} onChange={e => setRwReason(e.target.value)} rows={2}
                className="mt-1 w-full px-2 py-1.5 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
            </label>
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-[11px] text-blue-900">
              {rwType === 'retur_ke_cmt'
                ? 'Barang dikeluarkan dari karantina dan dikirim balik ke vendor lewat Surat Jalan REWORK. Vendor akan melihatnya di Portal Vendor → Penerimaan Material, mengerjakan ulang, lalu mengirim balik melalui deklarasi kirim. Qty diterima PO bertambah saat penerimaan rework selesai QC.'
                : 'Barang tetap di DA (karantina). Saat permak ditandai BERHASIL, stok FG naik sebesar qty yang diperbaiki dan qty diterima PO bertambah otomatis.'}
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setRework(null)}
                className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-foreground/5">
                Batal
              </button>
              <button onClick={submitRework} disabled={rwSaving} data-testid="rework-submit"
                className="h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-xs font-semibold hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1.5">
                {rwSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wrench className="w-3.5 h-3.5" />}
                Proses
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Dialog KOREKSI RESMI (hasil QC / deklarasi vendor) ─────────── */}
      {koreksi && (
        <Modal
          onClose={() => setKoreksi(null)}
          title={koreksi.mode === 'qc' ? 'Koreksi Resmi Hasil QC' : 'Koreksi Klaim Kirim Vendor'}
          size="lg">
          <div className="space-y-3" data-testid="koreksi-dialog">
            <div className="rounded-lg bg-foreground/[0.04] border border-border p-3 text-xs text-foreground space-y-0.5">
              <div><span className="text-muted-foreground">Penerimaan:</span> <strong>{koreksi.receipt.receipt_code}</strong></div>
              <div><span className="text-muted-foreground">SKU:</span> <strong>{koreksi.line.sku_code || '—'}</strong></div>
              <div>
                <span className="text-muted-foreground">Sekarang:</span>{' '}
                klaim <strong>{fmtNum(koreksi.line.qty_claimed_by_cmt || koreksi.line.qty_shipped_by_cmt)}</strong> ·
                lolos <strong>{fmtNum(koreksi.line.qty_actual)}</strong> ·
                reject <strong>{fmtNum(koreksi.line.reject_qty)}</strong> ·
                belum sampai <strong className="text-rose-700">{fmtNum(koreksi.line.qty_short)}</strong>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[11px] font-semibold text-muted-foreground">
                  {koreksi.mode === 'qc' ? 'Qty LOLOS QC yang benar' : 'Qty KLAIM vendor yang benar'}
                </span>
                <input type="number" min={0} value={korQty} onChange={e => setKorQty(e.target.value)}
                  data-testid="koreksi-qty"
                  className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
              </label>
              {koreksi.mode === 'qc' && (
                <label className="block">
                  <span className="text-[11px] font-semibold text-muted-foreground">Qty reject</span>
                  <input type="number" min={0} value={korReject} onChange={e => setKorReject(e.target.value)}
                    data-testid="koreksi-reject"
                    className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
                  <span className="text-[10px] text-muted-foreground">
                    Reject yang sudah masuk karantina/permak tidak bisa diubah.
                  </span>
                </label>
              )}
            </div>
            <label className="block">
              <span className="text-[11px] font-semibold text-muted-foreground">Alasan koreksi (wajib)</span>
              <textarea value={korReason} onChange={e => setKorReason(e.target.value)} rows={2}
                data-testid="koreksi-reason"
                placeholder={koreksi.mode === 'qc' ? 'mis. salah hitung, aktual 100 pcs' : 'mis. surat jalan vendor tertulis 100, seharusnya 90'}
                className="mt-1 w-full px-2 py-1.5 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
            </label>
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-[11px] text-blue-900">
              {koreksi.mode === 'qc'
                ? 'Stok FG dikoreksi sebesar selisihnya lewat SSOT stok, buku kuantitas dihitung ulang dari dokumen, dan dokumen selisih kirim disegarkan. Semua tercatat di jejak audit.'
                : 'Klaim vendor diperbarui dan dirambatkan ke dokumen deklarasi kirim vendor (dengan jejak audit). Vendor mendapat NOTIFIKASI berisi angka baru; tidak ada proses sanggahan.'}
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setKoreksi(null)}
                className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-foreground/5">
                Batal
              </button>
              <button onClick={submitKoreksi} disabled={korSaving} data-testid="koreksi-submit"
                className="h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-xs font-semibold hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1.5">
                {korSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Pencil className="w-3.5 h-3.5" />}
                Simpan koreksi
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Dialog PENYELESAIAN SELISIH KIRIM ─────────────────────────── */}
      {resolveShort && (
        <Modal onClose={() => setResolveShort(null)}
          title={`Selesaikan Selisih Kirim ${resolveShort.short_number}`} size="lg">
          <div className="space-y-3" data-testid="short-resolve-dialog">
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-900 space-y-0.5">
              <div><span className="opacity-70">PO / Vendor:</span> <strong>{resolveShort.po_number || '—'}</strong> · {resolveShort.vendor_name || '—'}</div>
              <div><span className="opacity-70">SKU:</span> <strong>{resolveShort.sku || '—'}</strong></div>
              <div>
                <span className="opacity-70">Klaim</span> <strong>{fmtNum(resolveShort.qty_claimed)}</strong> ·
                <span className="opacity-70"> sampai</span> <strong>{fmtNum(resolveShort.qty_arrived)}</strong> ·
                <span className="opacity-70"> belum sampai</span> <strong>{fmtNum(resolveShort.qty_open ?? resolveShort.qty_short)} pcs</strong>
              </div>
            </div>
            <label className="block">
              <span className="text-[11px] font-semibold text-muted-foreground">Keputusan</span>
              <select value={resType} onChange={e => setResType(e.target.value)} data-testid="short-resolve-type"
                className="mt-1 w-full h-9 px-2 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground">
                {SHORT_RESOLUTIONS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold text-muted-foreground">Catatan</span>
              <textarea value={resNotes} onChange={e => setResNotes(e.target.value)} rows={2}
                data-testid="short-resolve-notes"
                placeholder="mis. barang tidak ditemukan setelah dicari 3 hari — dibebankan ke vendor"
                className="mt-1 w-full px-2 py-1.5 rounded-md bg-[var(--card-surface,#fff)] border border-border text-xs text-foreground" />
            </label>
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-[11px] text-blue-900">
              Tidak ada pemotongan tagihan otomatis: keputusan tanggungan hanya DICATAT + vendor
              diberi notifikasi, lalu Finance memprosesnya di modul Tagihan CMT. Tanpa batas waktu —
              selisih boleh tetap terbuka sampai barang ditemukan.
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setResolveShort(null)}
                className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-foreground/5">
                Batal
              </button>
              <button onClick={submitResolveShort} disabled={resSaving} data-testid="short-resolve-submit"
                className="h-9 px-4 rounded-lg bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 disabled:opacity-50 inline-flex items-center gap-1.5">
                {resSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                Simpan keputusan
              </button>
            </div>
          </div>
        </Modal>
      )}
      {/* ── Dialog PILIH KOLOM SURAT JALAN CMT → DA (W5) ───────────────── */}
      {sjReceipt && (
        <PdfColumnPicker
          docType="cmt-delivery-note"
          open={!!sjReceipt}
          onOpenChange={(v) => { if (!v) setSjReceipt(null); }}
          defaultKeys={SJ_DEFAULT_COLS}
          title={`Surat Jalan CMT → DA — ${sjReceipt.receipt_code}`}
          confirmLabel="Cetak Surat Jalan"
          hint="Centang kolom yang ingin tercetak. Kolom hasil QC (Qty Terima / Qty Reject) hanya perlu dicentang bila surat jalan dicetak SETELAH pemeriksaan."
          onConfirm={async (cols) => {
            const receipt = sjReceipt;
            setSjReceipt(null);
            await downloadSuratJalan(receipt, cols);
          }}
        />
      )}
    </div>
  );
}
