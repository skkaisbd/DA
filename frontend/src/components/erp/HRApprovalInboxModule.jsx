/**
 * HRApprovalInboxModule — Unified HR Approval Inbox
 * Phase 26 — P2 Workflow Consolidation #2
 *
 * Single inbox where Managers / HR see all pending HR requests:
 *   - Cuti / Izin
 *   - Lembur
 *   - Penyesuaian Gaji
 *   - Resignasi
 *
 * Each card has Approve & Reject actions. Click card → drawer with full detail.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Inbox, Filter, RefreshCw, Calendar, Clock, DollarSign, UserMinus,
  CheckCircle2, XCircle, Search, AlertTriangle, User, Building2,
  Briefcase, FileText, ChevronRight, Sparkles, CalendarCheck,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { formatNumber } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ──────────────────────────────────────────────────────────────
function fmtRp(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  const sign = n < 0 ? '-' : (n > 0 ? '+' : '');
  return `${sign}Rp ${formatNumber(Math.abs(n))}`;
}
function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return v; }
}

const TYPE_META = {
  leave:             { label: 'Cuti / Izin',       icon: Calendar,      color: 'violet',  bgClass: 'bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-400 dark:border-violet-400/30' },
  overtime:          { label: 'Lembur',            icon: Clock,         color: 'amber',   bgClass: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-400/30' },
  salary_adjustment: { label: 'Penyesuaian Gaji',  icon: DollarSign,    color: 'emerald', bgClass: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-400/30' },
  resignation:       { label: 'Resignasi',         icon: UserMinus,     color: 'red',     bgClass: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300 border-red-400 dark:border-red-400/30' },
  attendance:        { label: 'Approval Absensi',  icon: CalendarCheck, color: 'blue',    bgClass: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-400/30' },
};

function TypeBadge({ type }) {
  const m = TYPE_META[type] || { label: type, bgClass: 'bg-foreground/10 text-foreground/70 border-foreground/20' };
  const Icon = m.icon || FileText;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.bgClass}`}>
      <Icon className="w-3 h-3" /> {m.label}
    </span>
  );
}

// ─── Detail Drawer ────────────────────────────────────────────────────────
function ItemDetailDrawer({ item, open, onClose, onApprove, onReject }) {
  if (!item) return null;
  const meta = item.meta || {};
  const raw = item.raw || {};
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl bg-card border-foreground/10">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TypeBadge type={item.type} />
            <span className="text-foreground">{item.title || '—'}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {/* Requester */}
          <GlassCard className="p-4">
            <h4 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <User className="w-3 h-3" /> Pemohon
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><span className="text-muted-foreground">Nama: </span><span className="text-foreground">{item.requester_name || '—'}</span></div>
              <div><span className="text-muted-foreground">Kode: </span><span className="text-foreground font-mono">{item.requester_code || '—'}</span></div>
              <div><span className="text-muted-foreground">Departemen: </span><span className="text-foreground">{item.requester_dept || '—'}</span></div>
              <div><span className="text-muted-foreground">Diajukan: </span><span className="text-foreground text-xs">{fmtDate(item.submitted_at)}</span></div>
            </div>
          </GlassCard>

          {/* Type-specific meta */}
          <GlassCard className="p-4">
            <h4 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
              <FileText className="w-3 h-3" /> Detail Permohonan
            </h4>
            <div className="space-y-2 text-sm">
              {item.type === 'leave' && (
                <>
                  <Row label="Jenis Cuti" value={meta.leave_type || '—'} />
                  <Row label="Periode" value={`${meta.from_date} → ${meta.to_date} (${meta.total_days} hari)`} />
                  <Row label="Paid?" value={meta.is_paid ? '✓ Ya' : '✗ Tidak'} />
                  {meta.half_day && <Row label="Setengah Hari" value={meta.half_day} />}
                  {meta.attachment_url && (
                    <Row label="Lampiran" value={<a className="text-blue-600 dark:text-blue-300 underline" href={`${API}${meta.attachment_url}`} target="_blank" rel="noreferrer">Lihat dokumen</a>} />
                  )}
                </>
              )}
              {item.type === 'overtime' && (
                <>
                  <Row label="Tanggal" value={meta.date} />
                  <Row label="Jam" value={`${meta.start_time} - ${meta.end_time}`} />
                  <Row label="Durasi" value={`${meta.hours} jam`} />
                  <Row label="Rate Multiplier" value={`${meta.rate_multiplier}x`} />
                </>
              )}
              {item.type === 'salary_adjustment' && (
                <>
                  <Row label="Jenis" value={meta.adjustment_type || '—'} />
                  <Row label="Nilai Lama" value={fmtRp(meta.old_value)} />
                  <Row label="Nilai Baru" value={fmtRp(meta.new_value)} />
                  <Row label="Selisih" value={<span className={meta.delta >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-600 dark:text-red-300'}>{fmtRp(meta.delta)}</span>} />
                  <Row label="Effective Date" value={meta.effective_date || '—'} />
                  <Row label="Sub-status" value={meta.sub_status || '—'} />
                </>
              )}
              {item.type === 'resignation' && (
                <>
                  <Row label="Posisi" value={meta.position || '—'} />
                  <Row label="Tanggal Efektif" value={meta.resignation_effective_date || '—'} />
                  <Row label="Last Working Date" value={meta.last_working_date || '—'} />
                </>
              )}
              {item.type === 'attendance' && (
                <>
                  <Row label="Tanggal Absen" value={meta.date || '—'} />
                  <Row label="Clock-In" value={meta.check_in_time || '—'} />
                  <Row label="Clock-Out" value={meta.check_out_time || '—'} />
                  {meta.work_hours != null && (
                    <Row label="Jam Kerja" value={`${meta.work_hours} jam`} />
                  )}
                  {meta.attendance_type && (
                    <Row label="Tipe" value={meta.attendance_type} />
                  )}
                  {meta.location && (
                    <Row label="Lokasi" value={typeof meta.location === 'string' ? meta.location : JSON.stringify(meta.location)} />
                  )}
                  {meta.face_match != null && (
                    <Row label="Face Match" value={`${Math.round((Number(meta.face_match) || 0) * 100)}%`} />
                  )}
                  {meta.geo_distance_m != null && (
                    <Row label="Jarak ke Kantor" value={`${meta.geo_distance_m} m`} />
                  )}
                  {meta.photo_url && (
                    <Row label="Foto" value={<a className="text-blue-600 dark:text-blue-300 underline" href={`${API}${meta.photo_url}`} target="_blank" rel="noreferrer">Lihat foto</a>} />
                  )}
                </>
              )}
              <Row label="Alasan" value={item.reason || raw.reason || '—'} multiline />
            </div>
          </GlassCard>
        </div>

        <DialogFooter className="flex flex-row gap-2 sm:justify-end">
          <Button
            data-testid="hr-inbox-reject-confirm"
            variant="outline"
            className="border-red-400 dark:border-red-400/30 text-red-600 dark:text-red-300 hover:bg-red-100 dark:bg-red-500/10"
            onClick={() => onReject(item)}
          >
            <XCircle className="w-4 h-4 mr-1.5" /> Tolak
          </Button>
          <Button
            data-testid="hr-inbox-approve-confirm"
            className="bg-green-600 hover:bg-green-500"
            onClick={() => onApprove(item)}
          >
            <CheckCircle2 className="w-4 h-4 mr-1.5" /> Setujui
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, value, multiline = false }) {
  return (
    <div className={`flex ${multiline ? 'flex-col' : 'flex-row justify-between'} gap-1`}>
      <span className="text-muted-foreground">{label}:</span>
      <span className={`text-foreground ${multiline ? 'mt-0.5 italic' : 'text-right'}`}>{value || '—'}</span>
    </div>
  );
}

// ─── Reject Reason Dialog ─────────────────────────────────────────────────
function RejectDialog({ open, item, onClose, onConfirm }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) setReason(''); }, [open]);
  if (!item) return null;
  const submit = async () => {
    if (!reason.trim()) {
      toast.error('Alasan wajib diisi');
      return;
    }
    setBusy(true);
    try {
      await onConfirm(item, reason.trim());
      onClose();
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !busy) onClose(); }}>
      <DialogContent className="max-w-md bg-card border-foreground/10">
        <DialogHeader>
          <DialogTitle className="text-red-600 dark:text-red-300 flex items-center gap-2">
            <XCircle className="w-5 h-5" /> Tolak Permohonan
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">
            <span className="text-foreground">{item.title}</span> dari{' '}
            <span className="text-foreground">{item.requester_name || '—'}</span>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-foreground/70">Alasan Penolakan <span className="text-red-700 dark:text-red-400">*</span></label>
            <Textarea
              data-testid="hr-inbox-reject-reason"
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={4}
              placeholder="Tulis alasan penolakan..."
              className="bg-foreground/5 border-foreground/10 text-sm resize-none"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy} className="text-muted-foreground">Batal</Button>
          <Button onClick={submit} disabled={busy || !reason.trim()} className="bg-red-600 hover:bg-red-500" data-testid="hr-inbox-reject-submit">
            {busy ? 'Memproses...' : 'Konfirmasi Tolak'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Approve Confirmation Dialog ──────────────────────────────────────────
function ApproveDialog({ open, item, onClose, onConfirm }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) setNote(''); }, [open]);
  if (!item) return null;
  const submit = async () => {
    setBusy(true);
    try {
      await onConfirm(item, note.trim() || null);
      onClose();
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !busy) onClose(); }}>
      <DialogContent className="max-w-md bg-card border-foreground/10">
        <DialogHeader>
          <DialogTitle className="text-green-600 dark:text-green-300 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5" /> Setujui Permohonan
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">
            <span className="text-foreground">{item.title}</span> dari{' '}
            <span className="text-foreground">{item.requester_name || '—'}</span>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-foreground/70">Catatan (opsional)</label>
            <Textarea
              data-testid="hr-inbox-approve-note"
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={3}
              placeholder="Tambahkan catatan untuk pemohon..."
              className="bg-foreground/5 border-foreground/10 text-sm resize-none"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy} className="text-muted-foreground">Batal</Button>
          <Button onClick={submit} disabled={busy} className="bg-green-600 hover:bg-green-500" data-testid="hr-inbox-approve-submit">
            {busy ? 'Memproses...' : 'Konfirmasi Setujui'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Inbox Item Card ──────────────────────────────────────────────────────
function InboxItemCard({ item, onView, onApprove, onReject }) {
  const meta = TYPE_META[item.type] || {};
  const Icon = meta.icon || FileText;
  return (
    <motion.div
      data-testid={`hr-inbox-item-${item.id}`}
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.005 }}
      className="p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30 cursor-pointer group"
      onClick={() => onView(item)}
    >
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${meta.bgClass}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <TypeBadge type={item.type} />
            <span className="text-sm font-semibold text-foreground truncate">{item.title}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1"><User className="w-3 h-3" />{item.requester_name || '—'}</span>
            {item.requester_dept && <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{item.requester_dept}</span>}
            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{fmtDate(item.submitted_at)}</span>
          </div>
          {item.period && (
            <div className="text-xs text-foreground/70 mt-1.5">
              <span className="text-muted-foreground">Periode:</span> {item.period}
            </div>
          )}
          {item.reason && (
            <div className="text-xs text-muted-foreground mt-1 italic truncate" title={item.reason}>
              "{item.reason}"
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            size="sm"
            variant="outline"
            className="border-red-400 dark:border-red-400/30 text-red-600 dark:text-red-300 hover:bg-red-100 dark:bg-red-500/10 h-7 text-xs px-2"
            data-testid={`hr-inbox-reject-btn-${item.id}`}
            onClick={(e) => { e.stopPropagation(); onReject(item); }}
          >
            <XCircle className="w-3 h-3 mr-1" /> Tolak
          </Button>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-500 h-7 text-xs px-2"
            data-testid={`hr-inbox-approve-btn-${item.id}`}
            onClick={(e) => { e.stopPropagation(); onApprove(item); }}
          >
            <CheckCircle2 className="w-3 h-3 mr-1" /> Setujui
          </Button>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 group-hover:text-violet-600 dark:text-violet-400" />
        </div>
      </div>
    </motion.div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────
export default function HRApprovalInboxModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [viewItem, setViewItem] = useState(null);
  const [approveItem, setApproveItem] = useState(null);
  const [rejectItem, setRejectItem] = useState(null);

  const fetchInbox = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/inbox`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat inbox');
        return;
      }
      const data = await r.json();
      setItems(data.items || []);
      setCounts(data.counts || {});
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchInbox(); }, [fetchInbox]);

  const filtered = useMemo(() => {
    let list = items;
    if (tab !== 'all') list = list.filter(i => i.type === tab);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(i =>
        (i.title || '').toLowerCase().includes(q) ||
        (i.requester_name || '').toLowerCase().includes(q) ||
        (i.requester_code || '').toLowerCase().includes(q) ||
        (i.requester_dept || '').toLowerCase().includes(q) ||
        (i.reason || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [items, tab, search]);

  const doApprove = async (item, note) => {
    try {
      const r = await fetch(`${API}/api/hr/inbox/${item.type}/${item.id}/approve`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ note: note || undefined }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || 'Gagal approve');
      toast.success(`${TYPE_META[item.type]?.label || item.type} disetujui`);
      setViewItem(null);
      fetchInbox();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const doReject = async (item, reason) => {
    try {
      const r = await fetch(`${API}/api/hr/inbox/${item.type}/${item.id}/reject`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reason }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || 'Gagal reject');
      toast.success(`${TYPE_META[item.type]?.label || item.type} ditolak`);
      setViewItem(null);
      fetchInbox();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const total = (counts.leave || 0) + (counts.overtime || 0) + (counts.salary_adjustment || 0) + (counts.resignation || 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inbox Approval SDM"
        subtitle="Pusat persetujuan terpadu — Cuti, Lembur, Penyesuaian Gaji, Resignasi, dan Approval Absensi dalam satu tempat."
        icon={Inbox}
        actions={
          <div className="flex items-center gap-2">
            {/* RC-IA T-4: optional cross-link — hr-inbox (approval absensi) → hr-attendance-hub (kelola lengkap).
                Kedua modul dipertahankan by-design; link ini hanya jalan pintas navigasi. */}
            {onNavigate && (
              <Button
                variant="outline" size="sm"
                onClick={() => onNavigate('hr-attendance-hub', { tab: 'approval' })}
                className="gap-1.5 text-xs border-blue-400/40 text-blue-600 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-500/10"
                data-testid="hr-inbox-attendance-hub-link"
                title="Buka Attendance Hub (absensi manual, otomatis & approval)"
              >
                <CalendarCheck className="w-3.5 h-3.5" /> Attendance Hub
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={fetchInbox} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="hr-inbox-refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        }
      />

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <StatCard label="Total Pending" value={total} icon={Inbox} tone="violet" />
        <StatCard label="Cuti / Izin" value={counts.leave || 0} icon={Calendar} tone="violet" testId="kpi-leave" />
        <StatCard label="Lembur" value={counts.overtime || 0} icon={Clock} tone="amber" testId="kpi-overtime" />
        <StatCard label="Penyesuaian Gaji" value={counts.salary_adjustment || 0} icon={DollarSign} tone="emerald" testId="kpi-salary" />
        <StatCard label="Resignasi" value={counts.resignation || 0} icon={UserMinus} tone="red" testId="kpi-resignation" />
        <StatCard label="Approval Absensi" value={counts.attendance || 0} icon={CalendarCheck} tone="blue" testId="kpi-attendance" />
      </div>

      {/* Filter + Search */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-foreground/5 flex-wrap h-auto p-1">
              <TabsTrigger value="all" data-testid="hr-inbox-tab-all">Semua ({total})</TabsTrigger>
              <TabsTrigger value="leave" data-testid="hr-inbox-tab-leave">Cuti ({counts.leave || 0})</TabsTrigger>
              <TabsTrigger value="overtime" data-testid="hr-inbox-tab-overtime">Lembur ({counts.overtime || 0})</TabsTrigger>
              <TabsTrigger value="salary_adjustment" data-testid="hr-inbox-tab-salary">Gaji ({counts.salary_adjustment || 0})</TabsTrigger>
              <TabsTrigger value="resignation" data-testid="hr-inbox-tab-resignation">Resignasi ({counts.resignation || 0})</TabsTrigger>
              <TabsTrigger value="attendance" data-testid="hr-inbox-tab-attendance">Absensi ({counts.attendance || 0})</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center bg-foreground/5 border border-foreground/10 rounded-md px-3 min-w-[220px]">
            <Search className="w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Cari nama / departemen / alasan..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-0 focus-visible:ring-0 text-sm"
              data-testid="hr-inbox-search"
            />
          </div>
        </div>

        {/* RC-IA T-4: contextual cross-link only when viewing the attendance approval tab */}
        {tab === 'attendance' && onNavigate && (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-blue-400/30 bg-blue-50 dark:bg-blue-500/10 px-3 py-2 text-xs text-blue-700 dark:text-blue-300" data-testid="hr-inbox-attendance-crosslink-note">
            <span className="flex items-center gap-1.5"><CalendarCheck className="w-3.5 h-3.5 flex-shrink-0" /> Approval absensi juga tersedia di <b>Attendance Hub</b> — lengkap dengan absensi manual & otomatis.</span>
            <Button variant="ghost" size="sm" onClick={() => onNavigate('hr-attendance-hub', { tab: 'approval' })} className="h-6 px-2 text-xs text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-500/20 flex-shrink-0" data-testid="hr-inbox-attendance-hub-link-inline">
              Buka Hub <ChevronRight className="w-3 h-3 ml-0.5" />
            </Button>
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="space-y-2 w-full">{Array.from({length:4}).map((_,i)=><Skeleton key={i} className="h-14 rounded-lg"/>)}</div>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Sparkles}
            title="Tidak ada approval pending"
            description={tab === 'all' ? 'Semua permohonan sudah diproses 🎉' : `Tidak ada permohonan ${TYPE_META[tab]?.label || tab} yang pending.`}
            data-testid="hr-inbox-empty"
          />
        ) : (
          <div className="space-y-2">
            <AnimatePresence>
              {filtered.map(item => (
                <InboxItemCard
                  key={`${item.type}-${item.id}`}
                  item={item}
                  onView={setViewItem}
                  onApprove={setApproveItem}
                  onReject={setRejectItem}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </GlassCard>

      {/* Detail Drawer */}
      <ItemDetailDrawer
        item={viewItem}
        open={!!viewItem}
        onClose={() => setViewItem(null)}
        onApprove={(it) => { setViewItem(null); setApproveItem(it); }}
        onReject={(it) => { setViewItem(null); setRejectItem(it); }}
      />

      {/* Approve Confirm Dialog */}
      <ApproveDialog
        item={approveItem}
        open={!!approveItem}
        onClose={() => setApproveItem(null)}
        onConfirm={doApprove}
      />

      {/* Reject Dialog */}
      <RejectDialog
        item={rejectItem}
        open={!!rejectItem}
        onClose={() => setRejectItem(null)}
        onConfirm={doReject}
      />
    </div>
  );
}

function StatCard({ label, value, icon: Icon, tone = 'slate', testId }) {
  const toneMap = {
    violet:  'text-violet-600 dark:text-violet-300 bg-violet-100 dark:bg-violet-500/10 border-violet-300 dark:border-violet-400/20',
    amber:   'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-400/20',
    emerald: 'text-emerald-600 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-500/10 border-emerald-300 dark:border-emerald-400/20',
    red:     'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/10 border-red-300 dark:border-red-400/20',
    slate:   'text-foreground/70 bg-foreground/5 border-foreground/10',
  };
  const klass = toneMap[tone] || toneMap.slate;
  return (
    <GlassCard className="p-3" data-testid={testId}>
      <div className={`flex items-center gap-2 text-xs text-muted-foreground mb-1`}>
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`text-2xl font-bold ${klass.split(' ')[0]}`}>{fmtNum(value)}</div>
    </GlassCard>
  );
}

