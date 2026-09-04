import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Calendar, Clock, Plus, Trash2, CheckCircle2, XCircle, HelpCircle,
  Loader2, Paperclip, Upload, FileText, Info, X, RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { GlassInput } from '@/components/ui/glass';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
const fmt = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

const STATUS_CFG = {
  pending_approval: { label: 'Menunggu Supervisor', icon: HelpCircle, cls: 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-700' },
  pending_hr_approval: { label: 'Menunggu HR',       icon: Clock,       cls: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-700' },
  approved:         { label: 'Disetujui',  icon: CheckCircle2, cls: 'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-700' },
  rejected:         { label: 'Ditolak',   icon: XCircle,      cls: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-700' },
  cancelled:        { label: 'Dibatalkan', icon: X,           cls: 'bg-muted text-muted-foreground border-border dark:bg-slate-800/30 dark:text-muted-foreground dark:border-slate-600' },
};
function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.pending_approval;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${cfg.cls}`}>
      <Icon className="w-3 h-3" /> {cfg.label}
    </span>
  );
}

const REQ_TYPE_CFG = {
  cuti:  { label: 'Cuti',  icon: '🏖️' },
  sakit: { label: 'Sakit', icon: '🏥' },
  izin:  { label: 'Izin',  icon: '📋' },
};

// ─── Document Upload ──────────────────────────────────────────────────────────
function DocUpload({ value, onChange, required, docNote, headers }) {
  const fileRef = useRef();
  const [uploading, setUploading] = useState(false);
  const { toast } = useToast();

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API}/api/rahaza/leaves/upload-document`, {
        method: 'POST', headers: { Authorization: headers.Authorization }, body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload gagal');
      onChange({ url: data.url, filename: file.name });
      toast({ title: 'Dokumen berhasil diupload' });
    } catch (e) { toast({ title: e.message, variant: 'destructive' }); }
    finally { setUploading(false); }
  };

  return (
    <div className="space-y-2">
      <Label className={`text-xs flex items-center gap-1 ${required ? 'text-amber-600 dark:text-amber-400' : ''}`}>
        <Paperclip size={12} />
        Bukti / Dokumen Pendukung {required && <span className="text-red-700 dark:text-red-500">*</span>}
      </Label>
      {docNote && (
        <div className="flex items-start gap-1.5 p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 text-[11px] text-amber-700 dark:text-amber-300">
          <Info size={12} className="mt-0.5 shrink-0" /> {docNote}
        </div>
      )}
      {value?.url ? (
        <div className="flex items-center gap-2 p-2 rounded border bg-muted/30">
          <FileText size={14} className="text-emerald-600 shrink-0" />
          <span className="text-xs text-emerald-600 truncate flex-1">{value.filename}</span>
          <a href={`${API}${value.url}`} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:underline">Lihat</a>
          <button onClick={() => onChange(null)} className="text-red-700 dark:text-red-400 hover:text-red-700 dark:text-red-500"><X size={12} /></button>
        </div>
      ) : (
        <div onClick={() => fileRef.current?.click()}
          className="flex items-center justify-center gap-2 p-3 rounded border-2 border-dashed border-muted-foreground/30 hover:border-primary/50 cursor-pointer transition-colors text-sm text-muted-foreground"
          data-testid="portal-doc-upload">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? 'Mengupload...' : 'Upload foto/PDF (maks 8MB)'}
        </div>
      )}
      <input ref={fileRef} type="file" className="hidden" accept="image/*,application/pdf"
        onChange={e => handleFile(e.target.files?.[0])} />
    </div>
  );
}

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
export default function PortalSayaCuti({ user, headers }) {
  const { toast } = useToast();
  const [tab, setTab] = useState('leaves');

  const [employee, setEmployee] = useState(null);
  const [leaves, setLeaves] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [balances, setBalances] = useState([]);
  const [overtimes, setOvertimes] = useState([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const EMPTY = { leave_type_id: '', from_date: '', to_date: '', reason: '',
                  is_half_day: false, half_day_period: 'AM', attachment: null };
  const [form, setForm] = useState(EMPTY);
  const [wdPreview, setWdPreview] = useState(null);
  const [wdLoading, setWdLoading] = useState(false);

  const [otForm, setOtForm] = useState({ date: '', start_time: '08:00', end_time: '17:00', reason: '' });
  const [showOtForm, setShowOtForm] = useState(false);

  // Resolve employee from current user — pakai endpoint /portal-saya/me/employee
  const loadEmployee = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/portal-saya/me/employee`, { headers });
      if (res.data && res.data.id) setEmployee(res.data);
    } catch (e) {
      // 404 = employee not linked, tampilkan pesan ke user
      if (e.response?.status !== 404) console.error('loadEmployee error', e);
    }
  }, [headers]); // eslint-disable-line

  const loadData = useCallback(async () => {
    if (!employee?.id) return;
    setLoading(true);
    try {
      const [lv, lt, bal, ot] = await Promise.all([
        axios.get(`${API}/api/portal-saya/me/leaves?limit=50`, { headers }),
        axios.get(`${API}/api/rahaza/leave-types`, { headers }),
        axios.get(`${API}/api/portal-saya/me/leave-balance`, { headers }),
        // FASE 20 — dulu '/api/rahaza/overtime-requests' (tidak pernah ada di
        // backend). Karena pemanggilnya memakai `.catch(...)`, 404-nya tertelan
        // total: kartu "Lembur Saya" selalu kosong tanpa satu pun pesan error.
        // Endpoint benar '/api/rahaza/overtime' membalas {ok, overtime:[...]}.
        axios.get(`${API}/api/rahaza/overtime?employee_id=${employee.id}&limit=30`, { headers })
          .catch(() => ({ data: { overtime: [] } })),
      ]);
      setLeaves(lv.data?.items || []);
      setLeaveTypes(Array.isArray(lt.data) ? lt.data : []);
      setBalances(bal.data?.balances || []);
      setOvertimes(ot.data?.overtime || ot.data?.items || []);
    } catch (e) { toast({ title: 'Gagal memuat data', variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [employee?.id, headers]); // eslint-disable-line

  useEffect(() => { loadEmployee(); }, [loadEmployee]);
  useEffect(() => { loadData(); }, [loadData]);

  // Live working days preview
  useEffect(() => {
    if (!form.from_date || !form.to_date || form.is_half_day) { setWdPreview(null); return; }
    if (new Date(form.to_date) < new Date(form.from_date)) { setWdPreview(null); return; }
    setWdLoading(true);
    axios.get(`${API}/api/rahaza/leaves/working-days?from_date=${form.from_date}&to_date=${form.to_date}`, { headers })
      .then(r => setWdPreview(r.data))
      .catch(() => setWdPreview(null))
      .finally(() => setWdLoading(false));
  }, [form.from_date, form.to_date, form.is_half_day]); // eslint-disable-line

  const selectedLT = leaveTypes.find(lt => lt.id === form.leave_type_id);

  const submitLeave = async () => {
    if (!form.leave_type_id || !form.from_date || !form.to_date)
      return toast({ title: 'Lengkapi field wajib', variant: 'destructive' });
    if (!employee?.id)
      return toast({ title: 'Data karyawan Anda tidak ditemukan. Hubungi HR.', variant: 'destructive' });

    // Validate document
    if (selectedLT?.requires_document) {
      const maxNoDoc = parseInt(selectedLT.max_days_without_doc || 0);
      const dur = form.is_half_day ? 0.5 : (new Date(form.to_date) - new Date(form.from_date)) / 86400000 + 1;
      if (!form.attachment?.url && (maxNoDoc === 0 || dur > maxNoDoc))
        return toast({ title: `Dokumen wajib: ${selectedLT.doc_note || 'Upload bukti pendukung.'}`, variant: 'destructive' });
    }

    setSubmitting(true);
    try {
      await axios.post(`${API}/api/rahaza/leaves/request`, {
        employee_id:       employee.id,
        leave_type_id:     form.leave_type_id,
        from_date:         form.from_date,
        to_date:           form.to_date,
        reason:            form.reason,
        is_half_day:       form.is_half_day,
        half_day_period:   form.half_day_period,
        attachment_url:    form.attachment?.url || '',
        attachment_filename: form.attachment?.filename || '',
        request_type:      selectedLT?.request_type || 'cuti',
      }, { headers });
      toast({ title: 'Request berhasil dikirim! Menunggu persetujuan.' });
      setShowForm(false);
      setForm(EMPTY);
      loadData();
    } catch (e) {
      toast({ title: e.response?.data?.detail || 'Gagal kirim request', variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const cancelLeave = async (id) => {
    if (!window.confirm('Batalkan pengajuan ini?')) return;
    try {
      await axios.post(`${API}/api/rahaza/leaves/${id}/cancel`, { reason: 'Dibatalkan oleh karyawan' }, { headers });
      toast({ title: 'Request dibatalkan' });
      loadData();
    } catch (e) {
      toast({ title: e.response?.data?.detail || 'Gagal membatalkan', variant: 'destructive' });
    }
  };

  const submitOT = async () => {
    if (!otForm.date || !otForm.start_time || !otForm.end_time || !otForm.reason)
      return toast({ title: 'Lengkapi semua field', variant: 'destructive' });
    if (!employee?.id)
      return toast({ title: 'Data karyawan tidak ditemukan', variant: 'destructive' });
    setSubmitting(true);
    try {
      // FASE 20 — POST-nya juga salah alamat: endpoint benar '/api/rahaza/overtime'
      // (body {employee_id, date, start_time, end_time, reason} sudah sesuai).
      // Sebelum ini setiap pengajuan lembur karyawan GAGAL dengan pesan generik.
      await axios.post(`${API}/api/rahaza/overtime`, {
        employee_id: employee.id, ...otForm }, { headers });
      toast({ title: 'Request lembur dikirim' });
      setShowOtForm(false);
      setOtForm({ date: '', start_time: '08:00', end_time: '17:00', reason: '' });
      loadData();
    } catch (e) {
      toast({ title: e.response?.data?.detail || 'Gagal kirim request lembur', variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  if (!employee) {
    return (
      <div className="p-6 text-center space-y-2">
        <p className="text-muted-foreground text-sm">
          {loading ? 'Mencari data karyawan...' : 'Data karyawan Anda belum terdaftar. Hubungi HR untuk mendaftarkan akun Anda.'}
        </p>
        {loading && <Loader2 className="mx-auto animate-spin" size={20} />}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="portal-cuti">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Cuti & Izin</h2>
          <p className="text-xs text-muted-foreground">{employee.name} · {employee.employee_code}</p>
        </div>
        <Button size="sm" onClick={() => loadData()} variant="outline">
          <RefreshCw size={13} className="mr-1" /> Refresh
        </Button>
      </div>

      {/* Balance Cards */}
      {balances.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {balances.filter(b => b.remaining > 0 || b.used > 0).map(b => (
            <Card key={b.leave_type_id} className="p-3">
              <p className="text-[10px] text-muted-foreground truncate">{b.leave_type_name}</p>
              <p className="text-lg font-bold tabular-nums">{b.remaining}</p>
              <p className="text-[10px] text-muted-foreground">sisa dari {b.quota} hari</p>
            </Card>
          ))}
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="leaves" data-testid="tab-cuti">Cuti & Izin</TabsTrigger>
          <TabsTrigger value="overtime" data-testid="tab-lembur">Lembur</TabsTrigger>
        </TabsList>

        {/* ── CUTI/IZIN TAB ── */}
        <TabsContent value="leaves" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowForm(v => !v)} data-testid="btn-ajukan-cuti">
              <Plus size={13} className="mr-1" /> Ajukan {showForm ? '↑' : 'Baru'}
            </Button>
          </div>

          {showForm && (
            <Card className="p-4 space-y-3" data-testid="leave-form">
              {/* Leave type grouped by request_type */}
              <div>
                <Label className="text-xs">Tipe Izin/Cuti <span className="text-red-700 dark:text-red-500">*</span></Label>
                <Select value={form.leave_type_id || 'none'}
                  onValueChange={v => setForm(f => ({ ...f, leave_type_id: v === 'none' ? '' : v }))}>
                  <SelectTrigger className="mt-1 h-9 text-sm" data-testid="select-leave-type"><SelectValue placeholder="Pilih tipe..." /></SelectTrigger>
                  <SelectContent>
                    {['cuti', 'sakit', 'izin'].map(rt => {
                      const typeGroup = leaveTypes.filter(lt => lt.request_type === rt);
                      if (!typeGroup.length) return null;
                      return (
                        <div key={rt}>
                          <div className="px-2 py-1 text-[10px] font-bold text-muted-foreground uppercase">
                            {REQ_TYPE_CFG[rt].icon} {REQ_TYPE_CFG[rt].label}
                          </div>
                          {typeGroup.map(lt => (
                            <SelectItem key={lt.id} value={lt.id}>
                              {lt.name} {lt.quota_default ? `(${lt.quota_default} hari)` : ''}
                            </SelectItem>
                          ))}
                        </div>
                      );
                    })}
                  </SelectContent>
                </Select>
                {selectedLT?.legal_basis && (
                  <p className="text-[10px] text-muted-foreground mt-1">{selectedLT.legal_basis}</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Dari Tanggal <span className="text-red-700 dark:text-red-500">*</span></Label>
                  <GlassInput type="date" className="mt-1 h-9 text-sm"
                    value={form.from_date} onChange={e => setForm(f => ({ ...f, from_date: e.target.value }))}
                    data-testid="leave-from-date" />
                </div>
                <div>
                  <Label className="text-xs">Sampai Tanggal <span className="text-red-700 dark:text-red-500">*</span></Label>
                  <GlassInput type="date" className="mt-1 h-9 text-sm"
                    value={form.to_date} onChange={e => setForm(f => ({ ...f, to_date: e.target.value }))}
                    data-testid="leave-to-date" />
                </div>
              </div>

              {/* Working days preview */}
              {(wdPreview || wdLoading) && !form.is_half_day && (
                <div className={`rounded-lg px-3 py-2 text-xs border ${
                  wdLoading ? 'bg-muted/30 border-border text-muted-foreground' :
                  wdPreview?.holiday_days > 0 ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-300' :
                  'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300'
                }`} data-testid="portal-wd-preview">
                  {wdLoading ? 'Menghitung hari kerja...' : wdPreview ? (
                    <div>
                      <span className="font-semibold">
                        {wdPreview.working_days === wdPreview.calendar_days
                          ? `${wdPreview.working_days} hari kerja`
                          : `${wdPreview.working_days} hari kerja (dari ${wdPreview.calendar_days} hari)`}
                      </span>
                      {wdPreview.holiday_days > 0 && (
                        <div className="mt-0.5">
                          🎌 Libur dalam periode: {wdPreview.holidays.map(h => h.name).join(', ')}
                        </div>
                      )}
                      {wdPreview.weekend_days > 0 && (
                        <div>📅 {wdPreview.weekend_days} hari akhir pekan tidak dihitung</div>
                      )}
                    </div>
                  ) : null}
                </div>
              )}

              {/* Half day */}
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={form.is_half_day}
                    onChange={e => setForm(f => ({ ...f, is_half_day: e.target.checked }))} className="rounded" />
                  Setengah Hari
                </label>
                {form.is_half_day && (
                  <Select value={form.half_day_period} onValueChange={v => setForm(f => ({ ...f, half_day_period: v }))}>
                    <SelectTrigger className="h-8 w-28 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="AM">Pagi (AM)</SelectItem>
                      <SelectItem value="PM">Siang (PM)</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </div>

              <div>
                <Label className="text-xs">Alasan</Label>
                <Textarea className="mt-1 text-sm" rows={2}
                  placeholder="Tulis alasan..."
                  value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
                  data-testid="leave-reason" />
              </div>

              {/* Document upload */}
              <DocUpload
                value={form.attachment}
                onChange={att => setForm(f => ({ ...f, attachment: att }))}
                required={selectedLT?.requires_document}
                docNote={selectedLT?.doc_note}
                headers={headers}
              />

              <div className="flex gap-2 pt-1">
                <Button onClick={submitLeave} disabled={submitting} size="sm" data-testid="btn-submit-cuti">
                  {submitting ? <Loader2 size={13} className="mr-1 animate-spin" /> : null}
                  Kirim Pengajuan
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>Batal</Button>
              </div>
            </Card>
          )}

          {/* List */}
          {loading ? (
            <div className="py-8 flex justify-center"><Loader2 className="animate-spin" size={20} /></div>
          ) : leaves.length === 0 ? (
            <Card className="p-8 text-center text-muted-foreground text-sm">Belum ada pengajuan</Card>
          ) : (
            <div className="space-y-2">
              {leaves.map(lv => (
                <Card key={lv.id} className="p-3" data-testid={`portal-leave-${lv.id}`}>
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-medium text-sm">{lv.leave_type_name}</span>
                        <StatusBadge status={lv.status} />
                        {lv.is_half_day && <Badge variant="outline" className="text-[10px]">½ {lv.half_day_period}</Badge>}
                        {lv.attachment_url && (
                          <a href={`${API}${lv.attachment_url}`} target="_blank" rel="noreferrer"
                            className="inline-flex items-center gap-1 text-[10px] text-blue-500 hover:underline">
                            <Paperclip size={9} /> Dok
                          </a>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {fmt(lv.from_date)} – {fmt(lv.to_date)} · {lv.duration_days} hari
                        {lv.duration_working_days && lv.duration_working_days !== lv.duration_days && (
                          <span className="text-emerald-600 dark:text-emerald-400 ml-1">
                            ({lv.duration_working_days} hari kerja)
                          </span>
                        )}
                        {lv.reason && <span className="italic ml-1">"{lv.reason}"</span>}
                      </p>
                      {lv.holidays_in_period?.length > 0 && (
                        <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                          🎌 Libur: {lv.holidays_in_period.map(h => h.name).join(', ')}
                        </p>
                      )}
                      {lv.rejected_reason && (
                        <p className="text-xs text-red-700 dark:text-red-500 mt-0.5">Alasan: {lv.rejected_reason}</p>
                      )}
                    </div>
                    {(lv.status === 'pending_approval') && (
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-700 dark:text-red-400"
                        onClick={() => cancelLeave(lv.id)}>
                        <Trash2 size={12} />
                      </Button>
                    )}
                    {lv.status === 'approved' && new Date(lv.from_date) > new Date() && (
                      <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
                        onClick={() => cancelLeave(lv.id)}>
                        Batalkan
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── LEMBUR TAB ── */}
        <TabsContent value="overtime" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setShowOtForm(v => !v)} data-testid="btn-ajukan-lembur">
              <Plus size={13} className="mr-1" /> Ajukan Lembur
            </Button>
          </div>
          {showOtForm && (
            <Card className="p-4 space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label className="text-xs">Tanggal</Label>
                  <GlassInput type="date" className="mt-1 h-9 text-sm"
                    value={otForm.date} onChange={e => setOtForm(f => ({ ...f, date: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Mulai</Label>
                  <GlassInput type="time" className="mt-1 h-9 text-sm"
                    value={otForm.start_time} onChange={e => setOtForm(f => ({ ...f, start_time: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Selesai</Label>
                  <GlassInput type="time" className="mt-1 h-9 text-sm"
                    value={otForm.end_time} onChange={e => setOtForm(f => ({ ...f, end_time: e.target.value }))} />
                </div>
              </div>
              <div>
                <Label className="text-xs">Alasan / Pekerjaan</Label>
                <Textarea className="mt-1 text-sm" rows={2}
                  value={otForm.reason} onChange={e => setOtForm(f => ({ ...f, reason: e.target.value }))} />
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={submitOT} disabled={submitting}>Kirim</Button>
                <Button size="sm" variant="outline" onClick={() => setShowOtForm(false)}>Batal</Button>
              </div>
            </Card>
          )}
          {overtimes.length === 0 ? (
            <Card className="p-8 text-center text-muted-foreground text-sm">Belum ada request lembur</Card>
          ) : (
            <div className="space-y-2">
              {overtimes.map(ot => (
                <Card key={ot.id} className="p-3">
                  <div className="flex items-center gap-2">
                    <Clock size={14} className="text-muted-foreground shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium">{ot.date} · {ot.start_time} – {ot.end_time}</p>
                      <p className="text-xs text-muted-foreground">{ot.reason}</p>
                    </div>
                    <StatusBadge status={ot.status || 'pending_approval'} />
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
