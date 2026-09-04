import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, Calendar, CheckCircle2, XCircle, Eye, Settings,
  RefreshCw, CheckCheck, AlertTriangle, FileText, Upload,
  Paperclip, Clock, X, Info, Wallet,
} from 'lucide-react';
import OnwardCTA from './OnwardCTA';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ─────────────────────────────────────────────────────────────────
const fmt = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
const fmtDuration = (d, wd) => {
  if (!d) return '—';
  const wdStr = wd && wd !== d ? ` (${wd} hari kerja)` : '';
  return `${d} hari${wdStr}`;
};

// ─── Status Badge ─────────────────────────────────────────────────────────────
const STATUS_CFG = {
  pending_approval: { label: 'Menunggu Supervisor', cls: 'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-400/30' },
  pending_hr_approval: { label: 'Menunggu HR',      cls: 'bg-blue-50 dark:bg-blue-400/15 text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-400/30' },
  approved:         { label: 'Disetujui',            cls: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-400/30' },
  rejected:         { label: 'Ditolak',              cls: 'bg-red-50 dark:bg-red-400/15 text-red-700 dark:text-red-400 border-red-400 dark:border-red-400/30' },
  cancelled:        { label: 'Dibatalkan',           cls: 'bg-muted dark:bg-slate-400/15 text-muted-foreground border-border dark:border-slate-400/30' },
  draft:            { label: 'Draft',                cls: 'bg-muted dark:bg-slate-400/15 text-foreground/70 border-border dark:border-slate-300/20' },
};
function LeaveBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft;
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${cfg.cls}`}>{cfg.label}</span>;
}

// ─── Request Type Badge ───────────────────────────────────────────────────────
const REQ_TYPE_CFG = {
  cuti:  { label: 'Cuti',  icon: '🏖️', cls: 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-400/30' },
  sakit: { label: 'Sakit', icon: '🏥', cls: 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-400 dark:border-red-400/30' },
  izin:  { label: 'Izin',  icon: '📋', cls: 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-400/30' },
};
function RequestTypeBadge({ type }) {
  const cfg = REQ_TYPE_CFG[type] || REQ_TYPE_CFG.izin;
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${cfg.cls}`}>{cfg.icon} {cfg.label}</span>;
}

// ─── Document Upload Component ────────────────────────────────────────────────
function DocumentUpload({ value, onChange, required, docNote, token }) {
  const fileRef = useRef();
  const [uploading, setUploading] = useState(false);

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API}/api/rahaza/leaves/upload-document`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload gagal');
      onChange({ url: data.url, filename: file.name });
      toast.success('Dokumen berhasil diupload');
    } catch (e) { toast.error(e.message); }
    finally { setUploading(false); }
  };

  return (
    <div className="space-y-2">
      <Label className={`text-xs flex items-center gap-1 ${required ? 'text-amber-700 dark:text-amber-400' : ''}`}>
        <Paperclip size={12} />
        Bukti / Dokumen Pendukung
        {required && <span className="text-red-700 dark:text-red-400 ml-0.5">*</span>}
      </Label>
      {docNote && (
        <div className="flex items-start gap-1.5 p-2 rounded bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 text-[11px] text-amber-600 dark:text-amber-300">
          <Info size={12} className="mt-0.5 shrink-0" />
          {docNote}
        </div>
      )}
      {value?.url ? (
        <div className="flex items-center gap-2 p-2 rounded bg-foreground/5 border border-foreground/10">
          <FileText size={14} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
          <span className="text-xs text-emerald-600 dark:text-emerald-400 truncate flex-1">{value.filename}</span>
          <a href={`${API}${value.url}`} target="_blank" rel="noreferrer" className="text-xs text-blue-600 dark:text-blue-400 hover:underline shrink-0">Lihat</a>
          <button onClick={() => onChange(null)} className="text-red-700 dark:text-red-400 hover:text-red-600 dark:text-red-300 shrink-0"><X size={12} /></button>
        </div>
      ) : (
        <div
          onClick={() => fileRef.current?.click()}
          className="flex items-center justify-center gap-2 p-3 rounded border-2 border-dashed border-foreground/20 hover:border-primary/50 cursor-pointer transition-colors text-sm text-muted-foreground"
          data-testid="doc-upload-area"
        >
          {uploading ? <RefreshCw size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? 'Mengupload...' : 'Klik untuk upload foto/PDF (maks 8MB)'}
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept="image/*,application/pdf"
        onChange={e => handleFile(e.target.files?.[0])}
      />
    </div>
  );
}

// ─── MAIN MODULE ──────────────────────────────────────────────────────────────
export default function RahazaLeaveModule({ token, onNavigate }) {
  const [leaves, setLeaves] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterReqType, setFilterReqType] = useState('');
  const [activeTab, setActiveTab] = useState('requests');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bulkApproving, setBulkApproving] = useState(false);

  // Modals
  const [requestModal, setRequestModal] = useState(false);
  const [typeModal, setTypeModal] = useState(false);
  const [detailModal, setDetailModal] = useState(false);
  const [selectedLeave, setSelectedLeave] = useState(null);
  const [rejectModal, setRejectModal] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [cancelModal, setCancelModal] = useState(null);
  const [cancelReason, setCancelReason] = useState('');

  // Request form + working days preview
  const EMPTY_FORM = { employee_id: '', leave_type_id: '', from_date: '', to_date: '',
                       reason: '', is_half_day: false, half_day_period: 'AM', attachment: null };
  const [requestForm, setRequestForm] = useState(EMPTY_FORM);
  const [wdPreview, setWdPreview] = useState(null);
  const [wdLoading, setWdLoading] = useState(false);
  const [typeForm, setTypeForm] = useState({ code: '', name: '', paid: true, quota_default: 12, description: '',
    request_type: 'cuti', requires_document: false, max_days_without_doc: 0, doc_note: '' });
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Selected leave type info (for validation hints)
  const selectedLT = leaveTypes.find(lt => lt.id === requestForm.leave_type_id);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);
      const [lr, lts, emps] = await Promise.all([
        fetch(`${API}/api/rahaza/leaves?${params}&limit=100`, { headers }).then(r => r.json()),
        fetch(`${API}/api/rahaza/leave-types`, { headers }).then(r => r.json()),
        fetch(`${API}/api/rahaza/employees?limit=200`, { headers }).then(r => r.json()),
      ]);
      let allLeaves = lr?.items || (Array.isArray(lr) ? lr : []);
      if (filterReqType) allLeaves = allLeaves.filter(l => l.request_type === filterReqType);
      setLeaves(allLeaves);
      setLeaveTypes(Array.isArray(lts) ? lts : []);
      setEmployees((emps?.items || emps?.employees || emps?.data || (Array.isArray(emps) ? emps : [])));
    } catch (e) { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  }, [filterStatus, filterReqType, token]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const pendingCount = leaves.filter(l => l.status === 'pending_approval' || l.status === 'pending_hr_approval').length;

  // ── Live working days preview ────────────────────────────────────────────────
  useEffect(() => {
    const { from_date, to_date, is_half_day } = requestForm;
    if (!from_date || !to_date || is_half_day) { setWdPreview(null); return; }
    if (new Date(to_date) < new Date(from_date)) { setWdPreview(null); return; }
    setWdLoading(true);
    fetch(`${API}/api/rahaza/leaves/working-days?from_date=${from_date}&to_date=${to_date}`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(d => setWdPreview(d))
      .catch(() => setWdPreview(null))
      .finally(() => setWdLoading(false));
  }, [requestForm.from_date, requestForm.to_date, requestForm.is_half_day]); // eslint-disable-line

  // ── Submit request ──────────────────────────────────────────────────────────
  const submitRequest = async () => {
    const { employee_id, leave_type_id, from_date, to_date, reason,
            is_half_day, half_day_period, attachment } = requestForm;

    if (!employee_id || !leave_type_id || !from_date || !to_date)
      return toast.error('Lengkapi semua field wajib');

    // Validate document if required
    if (selectedLT?.requires_document) {
      const maxNoDoc = parseInt(selectedLT.max_days_without_doc || 0);
      const dur = is_half_day ? 0.5 : (new Date(to_date) - new Date(from_date)) / 86400000 + 1;
      if ((!attachment?.url) && (maxNoDoc === 0 || dur > maxNoDoc))
        return toast.error(`Dokumen wajib dilampirkan. ${selectedLT.doc_note || ''}`);
    }

    setSaving(true);
    try {
      const payload = {
        employee_id, leave_type_id, from_date, to_date, reason,
        is_half_day, half_day_period,
        attachment_url: attachment?.url || '',
        attachment_filename: attachment?.filename || '',
        request_type: selectedLT?.request_type || 'cuti',
      };
      const r = await fetch(`${API}/api/rahaza/leaves/request`, {
        method: 'POST', headers, body: JSON.stringify(payload) });
      if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`); }
      toast.success('Request berhasil dikirim');
      setRequestModal(false);
      setRequestForm(EMPTY_FORM);
      load();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  // ── Approve ─────────────────────────────────────────────────────────────────
  const approveLeave = async (id) => {
    const r = await fetch(`${API}/api/rahaza/leaves/${id}/approve`, { method: 'POST', headers, body: '{}' });
    if (r.ok) { toast.success('Request disetujui'); load(); }
    else toast.error('Gagal approve');
  };

  // ── Reject ──────────────────────────────────────────────────────────────────
  const rejectLeave = async () => {
    if (!rejectModal) return;
    const r = await fetch(`${API}/api/rahaza/leaves/${rejectModal.id}/reject`, {
      method: 'POST', headers, body: JSON.stringify({ reason: rejectReason || 'Tidak disetujui' }) });
    if (r.ok) { toast.success('Request ditolak'); setRejectModal(null); setRejectReason(''); load(); }
    else toast.error('Gagal tolak');
  };

  // ── Cancel ──────────────────────────────────────────────────────────────────
  const cancelLeave = async () => {
    if (!cancelModal) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/rahaza/leaves/${cancelModal.id}/cancel`, {
        method: 'POST', headers, body: JSON.stringify({ reason: cancelReason }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal membatalkan');
      toast.success('Cuti berhasil dibatalkan, saldo dikembalikan');
      setCancelModal(null); setCancelReason(''); load();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  // ── Bulk approve ────────────────────────────────────────────────────────────
  const bulkApprove = async () => {
    setBulkApproving(true);
    try {
      const r = await fetch(`${API}/api/rahaza/leaves/bulk-approve`, {
        method: 'POST', headers, body: JSON.stringify({}) });
      const d = await r.json();
      toast.success(d.message || `${d.approved} request disetujui`);
      load();
    } catch { toast.error('Gagal bulk approve'); }
    finally { setBulkApproving(false); }
  };

  // ── Save Leave Type ─────────────────────────────────────────────────────────
  const saveLeaveType = async () => {
    if (!typeForm.code || !typeForm.name) return toast.error('Kode & nama wajib diisi');
    setSaving(true);
    try {
      // BUG-4: backend dulu MEMBUANG request_type/requires_document/... yang
      // dikirim form ini. Sekarang seluruh field tersimpan; edit juga tersedia.
      const editing = Boolean(typeForm.id);
      const r = await fetch(`${API}/api/rahaza/leave-types${editing ? `/${typeForm.id}` : ''}`, {
        method: editing ? 'PUT' : 'POST', headers,
        body: JSON.stringify({
          ...typeForm,
          quota_default: parseInt(typeForm.quota_default, 10) || 0,
          max_days_without_doc: parseInt(typeForm.max_days_without_doc, 10) || 0,
        }) });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal menyimpan'); }
      toast.success(editing ? 'Jenis cuti diperbarui' : 'Jenis cuti disimpan');
      setTypeModal(false);
      load();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  const deactivateLeaveType = async (lt) => {
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/rahaza/leave-types/${lt.id}`, { method: 'DELETE', headers });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Gagal menonaktifkan'); }
      toast.success(`Jenis cuti "${lt.name}" dinonaktifkan`);
      setDeactivateTarget(null);
      load();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5 p-4 lg:p-6" data-testid="leave-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Izin & Cuti</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Kelola request cuti, izin, dan sakit karyawan</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}><RefreshCw size={13} className="mr-1" /> Refresh</Button>
          {pendingCount > 0 && (
            <Button variant="outline" size="sm" onClick={bulkApprove} disabled={bulkApproving}
              className="text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-400/30" data-testid="bulk-approve-btn">
              <CheckCheck size={13} className="mr-1" />
              Approve Semua ({pendingCount})
            </Button>
          )}
          <Button size="sm" onClick={() => setRequestModal(true)} data-testid="new-request-btn">
            <Plus size={13} className="mr-1" /> Buat Request
          </Button>
        </div>
      </div>

      <OnwardCTA
        onNavigate={onNavigate}
        title="Setelah Approve Cuti"
        actions={[
          { module: 'hr-leave-balances', label: 'Lihat Saldo Cuti', icon: Wallet, primary: true, hint: 'Cek saldo cuti karyawan setelah pengajuan disetujui' },
        ]}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="requests" data-testid="tab-requests">
            Daftar Request
            {pendingCount > 0 && <span className="ml-1.5 text-[10px] bg-amber-500 text-foreground px-1.5 py-0.5 rounded-full">{pendingCount}</span>}
          </TabsTrigger>
          <TabsTrigger value="types" data-testid="tab-types">Master Tipe</TabsTrigger>
        </TabsList>

        {/* ── TAB: REQUESTS ── */}
        <TabsContent value="requests" className="mt-4 space-y-4">
          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <Select value={filterStatus || 'all'} onValueChange={v => setFilterStatus(v === 'all' ? '' : v)}>
              <SelectTrigger className="h-9 w-40 text-xs" data-testid="filter-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                <SelectItem value="pending_approval">Menunggu Supervisor</SelectItem>
                <SelectItem value="pending_hr_approval">Menunggu HR</SelectItem>
                <SelectItem value="approved">Disetujui</SelectItem>
                <SelectItem value="rejected">Ditolak</SelectItem>
                <SelectItem value="cancelled">Dibatalkan</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterReqType || 'all'} onValueChange={v => setFilterReqType(v === 'all' ? '' : v)}>
              <SelectTrigger className="h-9 w-40 text-xs" data-testid="filter-reqtype"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Tipe</SelectItem>
                <SelectItem value="cuti">🏖️ Cuti</SelectItem>
                <SelectItem value="sakit">🏥 Sakit</SelectItem>
                <SelectItem value="izin">📋 Izin</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Request list */}
          {loading ? (
            <div className="py-10 text-center text-muted-foreground text-sm">Memuat...</div>
          ) : leaves.length === 0 ? (
            <GlassCard className="p-10 text-center text-muted-foreground text-sm">
              Tidak ada request ditemukan
            </GlassCard>
          ) : (
            <div className="space-y-2">
              {leaves.map(lv => (
                <GlassCard key={lv.id} className="p-4" data-testid={`leave-row-${lv.id}`}>
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-semibold text-sm">{lv.employee_name || lv.employee_id}</span>
                        <LeaveBadge status={lv.status} />
                        <RequestTypeBadge type={lv.request_type || 'cuti'} />
                        {lv.is_half_day && <Badge variant="outline" className="text-[10px]">½ Hari ({lv.half_day_period})</Badge>}
                        {lv.attachment_url && (
                          <Badge variant="outline" className="text-[10px] bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-400/30">
                            <Paperclip size={9} className="mr-0.5" /> Dok
                          </Badge>
                        )}
                        {/* Multi-level indicator */}
                        {lv.approval_level_required === 2 && (
                          <Badge variant="outline" className="text-[10px] bg-violet-100 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-400 dark:border-violet-400/30">
                            2-Level
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{lv.leave_type_name}</span>
                        {' · '}{fmt(lv.from_date)} – {fmt(lv.to_date)}
                        {' · '}{fmtDuration(lv.duration_days, lv.duration_working_days)}
                        {lv.reason && <span className="ml-2 italic">"{lv.reason}"</span>}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0"
                        onClick={() => { setSelectedLeave(lv); setDetailModal(true); }}>
                        <Eye size={13} />
                      </Button>
                      {lv.status === 'pending_approval' && (
                        <>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-emerald-600 dark:text-emerald-400"
                            onClick={() => approveLeave(lv.id)} data-testid={`approve-${lv.id}`}>
                            <CheckCircle2 size={13} className="mr-1" /> Approve (Supervisor)
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-700 dark:text-red-400"
                            onClick={() => setRejectModal(lv)} data-testid={`reject-${lv.id}`}>
                            <XCircle size={13} className="mr-1" /> Tolak
                          </Button>
                        </>
                      )}
                      {lv.status === 'pending_hr_approval' && (
                        <>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-blue-600 dark:text-blue-400"
                            onClick={() => approveLeave(lv.id)} data-testid={`approve-hr-${lv.id}`}>
                            <CheckCircle2 size={13} className="mr-1" /> Approve (HR)
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-700 dark:text-red-400"
                            onClick={() => setRejectModal(lv)} data-testid={`reject-hr-${lv.id}`}>
                            <XCircle size={13} className="mr-1" /> Tolak
                          </Button>
                        </>
                      )}
                      {lv.status === 'approved' && new Date(lv.from_date) > new Date() && (
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-muted-foreground"
                          onClick={() => { setCancelModal(lv); setCancelReason(''); }}
                          data-testid={`cancel-${lv.id}`}>
                          <X size={13} className="mr-1" /> Batalkan
                        </Button>
                      )}
                    </div>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── TAB: LEAVE TYPES (master jenis/alasan cuti) ── */}
        <TabsContent value="types" className="mt-4 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-muted-foreground">
              Jenis cuti menentukan <b>kuota</b>, apakah <b>dibayar</b>, dan apakah
              <b> wajib melampirkan dokumen</b>. Perubahan langsung dipakai form pengajuan &amp; payroll.
            </p>
            <Button size="sm" data-testid="leave-type-add"
              onClick={() => { setTypeForm({ code:'',name:'',paid:true,quota_default:12,description:'',
                request_type:'cuti',requires_document:false,max_days_without_doc:0,doc_note:'' }); setTypeModal(true); }}>
              <Plus size={13} className="mr-1" /> Tambah Tipe
            </Button>
          </div>
          <div className="space-y-2" data-testid="leave-type-list">
            {leaveTypes.map(lt => (
              <GlassCard key={lt.id} className={`p-3 ${lt.active === false ? 'opacity-55' : ''}`}>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ background: lt.color || '#888' }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{lt.name}</span>
                      <span className="text-xs font-mono text-muted-foreground">{lt.code}</span>
                      <RequestTypeBadge type={lt.request_type || 'cuti'} />
                      {lt.requires_document && (
                        <Badge variant="outline" className="text-[10px] bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-400/30">
                          <Paperclip size={9} className="mr-0.5" /> Dok Wajib
                        </Badge>
                      )}
                      {/* BUG-4: dulu hanya membaca `unpaid`; jenis buatan HR (yang
                          menulis `paid`) tidak pernah menampilkan status apa pun. */}
                      {lt.unpaid
                        ? <Badge variant="outline" className="text-[10px] text-muted-foreground" data-testid={`lt-unpaid-${lt.code}`}>Tanpa Gaji</Badge>
                        : <Badge variant="outline" className="text-[10px] bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-400/40" data-testid={`lt-paid-${lt.code}`}>Berbayar</Badge>}
                      {lt.active === false && (
                        <Badge variant="outline" className="text-[10px] text-muted-foreground">Nonaktif</Badge>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      Kuota: {lt.quota_default} hari/tahun
                      {lt.legal_basis && <span className="ml-2 italic text-[10px]">{lt.legal_basis}</span>}
                      {lt.doc_note && <span className="ml-2 text-amber-700 dark:text-amber-400 text-[10px]">{lt.doc_note}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button size="sm" variant="ghost" data-testid={`leave-type-edit-${lt.code}`}
                      onClick={() => { setTypeForm({ ...lt, paid: !lt.unpaid }); setTypeModal(true); }}>
                      <Settings size={13} className="mr-1" /> Ubah
                    </Button>
                    {lt.active !== false && (
                      <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-700"
                        data-testid={`leave-type-off-${lt.code}`}
                        onClick={() => setDeactivateTarget(lt)}>
                        <XCircle size={13} className="mr-1" /> Nonaktifkan
                      </Button>
                    )}
                  </div>
                </div>
              </GlassCard>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* ── DIALOG: NEW REQUEST ── */}
      <Dialog open={requestModal} onOpenChange={setRequestModal}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="new-request-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Calendar size={16} /> Buat Request Izin/Cuti</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div>
              <Label className="text-xs">Karyawan <span className="text-red-700 dark:text-red-400">*</span></Label>
              <Select value={requestForm.employee_id || 'none'}
                onValueChange={v => setRequestForm(f => ({ ...f, employee_id: v === 'none' ? '' : v }))}>
                <SelectTrigger className="mt-1 h-9" data-testid="req-employee"><SelectValue placeholder="Pilih karyawan..." /></SelectTrigger>
                <SelectContent>
                  {employees.map(e => <SelectItem key={e.id} value={e.id}>{e.name} ({e.employee_code})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs">Tipe Izin/Cuti <span className="text-red-700 dark:text-red-400">*</span></Label>
              <Select value={requestForm.leave_type_id || 'none'}
                onValueChange={v => setRequestForm(f => ({ ...f, leave_type_id: v === 'none' ? '' : v }))}>
                <SelectTrigger className="mt-1 h-9" data-testid="req-type"><SelectValue placeholder="Pilih tipe..." /></SelectTrigger>
                <SelectContent>
                  {['cuti', 'sakit', 'izin'].map(rt => (
                    <div key={rt}>
                      <div className="px-2 py-1 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                        {REQ_TYPE_CFG[rt].icon} {REQ_TYPE_CFG[rt].label}
                      </div>
                      {leaveTypes.filter(lt => lt.request_type === rt).map(lt => (
                        <SelectItem key={lt.id} value={lt.id}>
                          {lt.name} ({lt.quota_default} hari)
                        </SelectItem>
                      ))}
                    </div>
                  ))}
                </SelectContent>
              </Select>
              {selectedLT?.legal_basis && (
                <p className="text-[10px] text-muted-foreground mt-1">{selectedLT.legal_basis}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Dari Tanggal <span className="text-red-700 dark:text-red-400">*</span></Label>
                <GlassInput type="date" className="mt-1 h-9 text-sm"
                  value={requestForm.from_date}
                  onChange={e => setRequestForm(f => ({ ...f, from_date: e.target.value }))}
                  data-testid="req-from" />
              </div>
              <div>
                <Label className="text-xs">Sampai Tanggal <span className="text-red-700 dark:text-red-400">*</span></Label>
                <GlassInput type="date" className="mt-1 h-9 text-sm"
                  value={requestForm.to_date}
                  onChange={e => setRequestForm(f => ({ ...f, to_date: e.target.value }))}
                  data-testid="req-to" />
              </div>
            </div>

            {/* Working days preview */}
            {(wdPreview || wdLoading) && !requestForm.is_half_day && (
              <div className={`rounded-lg px-3 py-2 text-xs border ${
                wdLoading ? 'bg-muted/30 border-border text-muted-foreground' :
                wdPreview?.holiday_days > 0 ? 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30 text-amber-600 dark:text-amber-300' :
                'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-300'
              }`} data-testid="wd-preview">
                {wdLoading ? (
                  <span className="flex items-center gap-1"><RefreshCw size={11} className="animate-spin" /> Menghitung...</span>
                ) : wdPreview ? (
                  <div className="space-y-1">
                    <div className="font-semibold">
                      {wdPreview.working_days === wdPreview.calendar_days
                        ? `${wdPreview.working_days} hari kerja`
                        : `${wdPreview.working_days} hari kerja dari ${wdPreview.calendar_days} hari kalender`
                      }
                    </div>
                    {(wdPreview.weekend_days > 0 || wdPreview.holiday_days > 0) && (
                      <div className="text-[10px] space-y-0.5">
                        {wdPreview.weekend_days > 0 && (
                          <div>📅 {wdPreview.weekend_days} hari akhir pekan (tidak dihitung)</div>
                        )}
                        {wdPreview.holiday_days > 0 && (
                          <div>
                            🎌 {wdPreview.holiday_days} libur nasional dalam periode ini:
                            <span className="ml-1">{wdPreview.holidays.map(h => h.name).join(', ')}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}

            {/* Half day option */}
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer text-sm">
                <input type="checkbox" checked={requestForm.is_half_day}
                  onChange={e => setRequestForm(f => ({ ...f, is_half_day: e.target.checked }))}
                  className="rounded" />
                Setengah Hari
              </label>
              {requestForm.is_half_day && (
                <Select value={requestForm.half_day_period}
                  onValueChange={v => setRequestForm(f => ({ ...f, half_day_period: v }))}>
                  <SelectTrigger className="h-8 w-24 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="AM">Pagi (AM)</SelectItem>
                    <SelectItem value="PM">Siang (PM)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>

            <div>
              <Label className="text-xs">Alasan</Label>
              <Textarea className="mt-1 text-sm" rows={2} placeholder="Tulis alasan..."
                value={requestForm.reason}
                onChange={e => setRequestForm(f => ({ ...f, reason: e.target.value }))}
                data-testid="req-reason" />
            </div>

            {/* Document upload */}
            <DocumentUpload
              value={requestForm.attachment}
              onChange={att => setRequestForm(f => ({ ...f, attachment: att }))}
              required={selectedLT?.requires_document}
              docNote={selectedLT?.doc_note}
              token={token}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRequestModal(false)}>Batal</Button>
            <Button onClick={submitRequest} disabled={saving} data-testid="req-submit">
              Kirim Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── DIALOG: DETAIL ── */}
      {selectedLeave && (
        <Dialog open={detailModal} onOpenChange={setDetailModal}>
          <DialogContent className="max-w-md" data-testid="detail-dialog">
            <DialogHeader><DialogTitle>Detail Request Cuti</DialogTitle></DialogHeader>
            <div className="space-y-2 text-sm mt-2">
              <div className="flex justify-between"><span className="text-muted-foreground">Karyawan</span><span className="font-medium">{selectedLeave.employee_name}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Tipe</span><span>{selectedLeave.leave_type_name}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Request Type</span><RequestTypeBadge type={selectedLeave.request_type} /></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Periode</span><span>{fmt(selectedLeave.from_date)} – {fmt(selectedLeave.to_date)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Durasi</span><span>{fmtDuration(selectedLeave.duration_days, selectedLeave.duration_working_days)}</span></div>
              {selectedLeave.is_half_day && <div className="flex justify-between"><span className="text-muted-foreground">Half Day</span><span>{selectedLeave.half_day_period}</span></div>}
              <div className="flex justify-between"><span className="text-muted-foreground">Status</span><LeaveBadge status={selectedLeave.status} /></div>
              {selectedLeave.reason && <div className="flex justify-between"><span className="text-muted-foreground">Alasan</span><span className="text-right max-w-[200px]">{selectedLeave.reason}</span></div>}
              {selectedLeave.rejected_reason && <div className="flex justify-between"><span className="text-muted-foreground">Alasan Tolak</span><span className="text-red-700 dark:text-red-400">{selectedLeave.rejected_reason}</span></div>}
              {selectedLeave.cancel_reason && <div className="flex justify-between"><span className="text-muted-foreground">Alasan Batal</span><span className="text-muted-foreground">{selectedLeave.cancel_reason}</span></div>}
              {selectedLeave.attachment_url && (
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Dokumen</span>
                  <a href={`${API}${selectedLeave.attachment_url}`} target="_blank" rel="noreferrer"
                    className="text-blue-600 dark:text-blue-400 hover:underline text-xs flex items-center gap-1">
                    <Paperclip size={12} /> {selectedLeave.attachment_filename || 'Lihat Dokumen'}
                  </a>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* ── DIALOG: REJECT ── */}
      <Dialog open={!!rejectModal} onOpenChange={v => !v && setRejectModal(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Tolak Request Cuti</DialogTitle></DialogHeader>
          <div className="space-y-2 mt-2">
            <p className="text-sm text-muted-foreground">Tolak request <b>{rejectModal?.employee_name}</b> ({rejectModal?.leave_type_name})?</p>
            <Textarea placeholder="Alasan penolakan..." value={rejectReason}
              onChange={e => setRejectReason(e.target.value)} rows={2} data-testid="reject-reason" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectModal(null)}>Batal</Button>
            <Button onClick={rejectLeave} className="bg-red-600 hover:bg-red-700" data-testid="confirm-reject">Tolak</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── DIALOG: CANCEL ── */}
      <Dialog open={!!cancelModal} onOpenChange={v => !v && setCancelModal(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Batalkan Cuti</DialogTitle></DialogHeader>
          <div className="space-y-2 mt-2">
            <p className="text-sm text-muted-foreground">Batalkan cuti <b>{cancelModal?.employee_name}</b> ({fmt(cancelModal?.from_date)} – {fmt(cancelModal?.to_date)})?
              Saldo cuti akan dikembalikan.</p>
            <Textarea placeholder="Alasan pembatalan..." value={cancelReason}
              onChange={e => setCancelReason(e.target.value)} rows={2} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelModal(null)}>Batal</Button>
            <Button onClick={cancelLeave} disabled={saving} className="bg-muted hover:bg-muted-foreground/30">Batalkan Cuti</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── DIALOG: NEW LEAVE TYPE ── */}
      <Dialog open={typeModal} onOpenChange={setTypeModal}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="new-type-dialog">
          <DialogHeader><DialogTitle>
            {typeForm.id ? `Ubah Jenis Cuti — ${typeForm.name || typeForm.code}` : 'Tambah Tipe Izin/Cuti'}
          </DialogTitle></DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Kode <span className="text-red-700 dark:text-red-400">*</span></Label>
                <GlassInput className="mt-1 h-9 text-sm" placeholder="SICK" value={typeForm.code}
                  onChange={e => setTypeForm(f => ({ ...f, code: e.target.value.toUpperCase() }))} />
              </div>
              <div>
                <Label className="text-xs">Nama <span className="text-red-700 dark:text-red-400">*</span></Label>
                <GlassInput className="mt-1 h-9 text-sm" placeholder="Izin Sakit" value={typeForm.name}
                  onChange={e => setTypeForm(f => ({ ...f, name: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Request Type</Label>
                <Select value={typeForm.request_type} onValueChange={v => setTypeForm(f => ({ ...f, request_type: v }))}>
                  <SelectTrigger className="mt-1 h-9 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cuti">🏖️ Cuti</SelectItem>
                    <SelectItem value="sakit">🏥 Sakit</SelectItem>
                    <SelectItem value="izin">📋 Izin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Kuota Default (hari)</Label>
                <GlassInput type="number" min={0} className="mt-1 h-9 text-sm" value={typeForm.quota_default}
                  onChange={e => setTypeForm(f => ({ ...f, quota_default: e.target.value }))} />
              </div>
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={typeForm.paid}
                  onChange={e => setTypeForm(f => ({ ...f, paid: e.target.checked }))} /> Berbayar
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={typeForm.requires_document}
                  onChange={e => setTypeForm(f => ({ ...f, requires_document: e.target.checked }))} />
                Wajib Dokumen
              </label>
            </div>
            {typeForm.requires_document && (
              <div>
                <Label className="text-xs">Maks. Hari Tanpa Dokumen</Label>
                <GlassInput type="number" min={0} className="mt-1 h-9 text-sm"
                  placeholder="0 = selalu wajib" value={typeForm.max_days_without_doc}
                  onChange={e => setTypeForm(f => ({ ...f, max_days_without_doc: e.target.value }))} />
                <Label className="text-xs mt-2">Catatan Dokumen</Label>
                <GlassInput className="mt-1 h-9 text-sm" placeholder="Contoh: Lampirkan surat dokter"
                  value={typeForm.doc_note}
                  onChange={e => setTypeForm(f => ({ ...f, doc_note: e.target.value }))} />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTypeModal(false)} data-testid="leave-type-cancel">Batal</Button>
            <Button onClick={saveLeaveType} disabled={saving} data-testid="leave-type-save">
              {typeForm.id ? 'Simpan Perubahan' : 'Simpan'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── DIALOG: KONFIRMASI NONAKTIF JENIS CUTI ── */}
      <Dialog open={Boolean(deactivateTarget)} onOpenChange={(v) => { if (!v) setDeactivateTarget(null); }}>
        <DialogContent data-testid="leave-type-off-dialog">
          <DialogHeader>
            <DialogTitle>Nonaktifkan jenis cuti?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            &quot;{deactivateTarget?.name}&quot; tidak akan muncul lagi di form pengajuan.
            Riwayat pengajuan yang sudah ada TETAP tersimpan. Pengajuan yang masih
            menunggu keputusan harus diproses dulu.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeactivateTarget(null)}>Batal</Button>
            <Button variant="destructive" disabled={saving}
              onClick={() => deactivateLeaveType(deactivateTarget)}
              data-testid="leave-type-off-confirm">Nonaktifkan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
