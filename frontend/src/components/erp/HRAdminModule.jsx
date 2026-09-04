import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Settings, Sparkles, Landmark, UserX, MapPin, Database, RefreshCw, LayoutGrid,
  Plus, Edit2, Trash2, Save, X, Loader2, TrendingUp, TrendingDown,
  CheckCircle2, AlertCircle, FileText, MessageSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { EmptyState } from './EmptyState';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtIDR = formatRupiah;

export default function HRAdminModule({ token }) {
  return (
    <div className="space-y-6 p-6" data-testid="hr-admin-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="w-6 h-6 text-indigo-600 dark:text-indigo-400" /> HR Admin & Konfigurasi
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Struktur gaji, resignasi, geolocation attendance, dan demo seed
        </p>
      </div>

      <Tabs defaultValue="grades">
        <TabsList className="grid grid-cols-4 w-full max-w-xl">
          <TabsTrigger value="grades"       className="text-xs"><Landmark className="w-3 h-3 mr-1" />Struktur Gaji</TabsTrigger>
          <TabsTrigger value="resignations" className="text-xs"><UserX className="w-3 h-3 mr-1" />Resignasi</TabsTrigger>
          <TabsTrigger value="office"       className="text-xs"><MapPin className="w-3 h-3 mr-1" />Lokasi Kantor</TabsTrigger>
          <TabsTrigger value="seed"         className="text-xs"><Database className="w-3 h-3 mr-1" />Demo Seed</TabsTrigger>
        </TabsList>

        <TabsContent value="grades"       className="mt-4"><SalaryGradesTab token={token} /></TabsContent>
        <TabsContent value="resignations" className="mt-4"><ResignationsTab token={token} /></TabsContent>
        <TabsContent value="office"       className="mt-4"><OfficeLocationTab token={token} /></TabsContent>
        <TabsContent value="seed"         className="mt-4"><SeedTab token={token} /></TabsContent>
      </Tabs>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
function SalaryGradesTab({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [grades, setGrades] = useState([]);
  const [audit, setAudit] = useState({ violations: [], total_graded: 0 });
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        axios.get(`${API}/api/rahaza/salary-grades`, { headers }),
        axios.get(`${API}/api/rahaza/salary-grades/audit`, { headers }).catch(() => ({ data: {} })),
      ]);
      setGrades(r1.data.grades || []);
      setAudit(r2.data || {});
    } finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const save = async (form) => {
    try {
      if (form.id) {
        await axios.put(`${API}/api/rahaza/salary-grades/${form.id}`, form, { headers });
      } else {
        await axios.post(`${API}/api/rahaza/salary-grades`, form, { headers });
      }
      toast.success('Grade tersimpan');
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal'); }
  };

  const del = async (id) => {
    if (!window.confirm('Non-aktifkan grade ini?')) return;
    await axios.delete(`${API}/api/rahaza/salary-grades/${id}`, { headers });
    toast.success('Grade dinon-aktifkan'); load();
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(grades, 10);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Struktur Gaji per Grade (Salary Bands)</h3>
          <p className="text-xs text-muted-foreground">
            {audit.total_graded || 0} karyawan dengan grade · {audit.violations?.length || 0} di luar band
            {audit.violations?.length > 0 && ' (perlu adjustment)'}
          </p>
        </div>
        <Button size="sm" onClick={() => setEditing({})} data-testid="grade-add">
          <Plus className="w-4 h-4 mr-1" />Tambah Grade
        </Button>
      </div>

      <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
        <table className="w-full text-sm">
          <thead className="bg-foreground/5 text-xs text-muted-foreground">
            <tr><th className="text-left px-3 py-2">Code</th><th className="text-left px-3 py-2">Nama</th>
              <th className="text-right px-3 py-2">Min</th><th className="text-right px-3 py-2">Mid</th>
              <th className="text-right px-3 py-2">Max</th><th className="px-3 py-2"></th></tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {paged.map(g => (
              <tr key={g.id}>
                <td className="px-3 py-2 font-mono font-bold">{g.grade_code}</td>
                <td className="px-3 py-2">{g.grade_name}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(g.min_salary)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs text-blue-600 dark:text-blue-400">{fmtIDR(g.mid_salary)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(g.max_salary)}</td>
                <td className="px-3 py-2">
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(g)}><Edit2 className="w-3 h-3" /></Button>
                  <Button size="icon" variant="ghost" className="h-6 w-6 text-red-700 dark:text-red-400" onClick={() => del(g.id)}><Trash2 className="w-3 h-3" /></Button>
                </td>
              </tr>
            ))}
            {grades.length === 0 && <tr><td colSpan={6}>
              <EmptyState icon={LayoutGrid} title="Belum ada grade karyawan" description="Tambahkan grade pertama untuk memulai klasifikasi jabatan." />
            </td></tr>}
          </tbody>
        </table>
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
      </div>

      {audit.violations?.length > 0 && (
        <div className="rounded-xl border border-red-300 dark:border-red-500/20 bg-red-100 dark:bg-red-500/5 p-4">
          <div className="text-sm font-semibold text-red-600 dark:text-red-300 mb-2">⚠️ Violasi Band Gaji ({audit.violations.length})</div>
          <div className="space-y-1 text-xs">
            {audit.violations.map((v, i) => (
              <div key={i} className="flex items-center gap-2">
                {v.status === 'below' ? <TrendingDown className="w-3 h-3 text-amber-700 dark:text-amber-400" /> : <TrendingUp className="w-3 h-3 text-red-700 dark:text-red-400" />}
                <span>{v.name} ({v.employee_code}) · {v.grade}: Rp {v.base_rate.toLocaleString('id-ID')}
                  (<span className={v.status === 'below' ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400'}>{v.status}</span> range
                  Rp {v.grade_min.toLocaleString('id-ID')}–{v.grade_max.toLocaleString('id-ID')})</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {editing && <GradeDialog initial={editing} onSave={save} onClose={() => setEditing(null)} />}
    </div>
  );
}

function GradeDialog({ initial, onSave, onClose }) {
  const [form, setForm] = useState({
    grade_code: '', grade_name: '', level: 1,
    min_salary: 0, mid_salary: 0, max_salary: 0, department: '',
    description: '', is_active: true, ...initial,
  });
  const [saving, setSaving] = useState(false);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{form.id ? 'Edit Grade' : 'Tambah Grade'}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>Code *</Label><Input value={form.grade_code} onChange={e => setForm(f => ({ ...f, grade_code: e.target.value.toUpperCase() }))} placeholder="G1" /></div>
            <div className="space-y-1"><Label>Level *</Label><Input type="number" min={1} value={form.level} onChange={e => setForm(f => ({ ...f, level: +e.target.value }))} /></div>
          </div>
          <div className="space-y-1"><Label>Nama Grade *</Label><Input value={form.grade_name} onChange={e => setForm(f => ({ ...f, grade_name: e.target.value }))} placeholder="Level 1 — Staff" /></div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1"><Label>Min (Rp)</Label><Input type="number" value={form.min_salary} onChange={e => setForm(f => ({ ...f, min_salary: +e.target.value }))} /></div>
            <div className="space-y-1"><Label>Mid (Rp)</Label><Input type="number" value={form.mid_salary} onChange={e => setForm(f => ({ ...f, mid_salary: +e.target.value }))} /></div>
            <div className="space-y-1"><Label>Max (Rp)</Label><Input type="number" value={form.max_salary} onChange={e => setForm(f => ({ ...f, max_salary: +e.target.value }))} /></div>
          </div>
          <div className="space-y-1"><Label>Deskripsi</Label><Textarea rows={2} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={async () => { setSaving(true); await onSave(form); setSaving(false); }} disabled={saving || !form.grade_code || !form.grade_name}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════════
function ResignationsTab({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    const r = await axios.get(`${API}/api/rahaza/resignation/list`, { headers });
    setItems(r.data.items || []);
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Proses Resignasi & Offboarding</h3>
          <p className="text-xs text-muted-foreground">{items.length} karyawan dalam proses/sudah resign</p>
        </div>
      </div>
      <div className="rounded-xl border border-foreground/10 bg-foreground/5">
        {items.length === 0 ? (
          <EmptyState icon={UserX} title="Tidak ada resignasi aktif" description="Semua karyawan masih aktif. Proses resignasi akan muncul di sini." />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 text-xs text-muted-foreground">
              <tr><th className="text-left px-3 py-2">Karyawan</th><th className="text-left px-3 py-2">Divisi</th>
                <th className="text-left px-3 py-2">Status</th><th className="text-left px-3 py-2">Tgl Resign</th>
                <th className="text-left px-3 py-2">Alasan</th><th className="px-3 py-2"></th></tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map(i => (
                <tr key={i.id}>
                  <td className="px-3 py-2"><div className="font-medium">{i.name}</div><div className="text-[10px] text-muted-foreground">{i.employee_code}</div></td>
                  <td className="px-3 py-2 text-xs">{i.department}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      i.employee_status === 'resigned' ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300' :
                      'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300'}`}>{i.employee_status}</span>
                  </td>
                  <td className="px-3 py-2 text-xs font-mono">{i.resignation_date || '—'}</td>
                  <td className="px-3 py-2 text-xs max-w-xs truncate">{i.reason_for_leaving || '—'}</td>
                  <td className="px-3 py-2"><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(i)}><FileText className="w-3 h-3 mr-1" />Proses</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing && <ResignationProcessDialog emp={editing} headers={headers} onReload={load} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ResignationProcessDialog({ emp, headers, onReload, onClose }) {
  const [tab, setTab] = useState('clearance');
  const [clearance, setClearance] = useState(emp.clearance || {});
  const [interview, setInterview] = useState({ nps_score: 0, notes: '', positive_feedback: '', improvement_areas: '', would_recommend: false });

  const saveClearance = async () => {
    try {
      await axios.put(`${API}/api/rahaza/resignation/clearance/${emp.id}`, clearance, { headers });
      toast.success('Clearance diupdate'); onReload();
    } catch { toast.error('Gagal'); }
  };
  const saveInterview = async () => {
    try {
      await axios.post(`${API}/api/rahaza/resignation/exit-interview/${emp.id}`, interview, { headers });
      toast.success('Exit interview tersimpan'); onReload();
    } catch { toast.error('Gagal'); }
  };
  const accept = async () => {
    if (!window.confirm('Accept resignation? Karyawan akan di-deactivate.')) return;
    try {
      await axios.post(`${API}/api/rahaza/resignation/accept/${emp.id}`, { rehire_eligible: true }, { headers });
      toast.success('Resignation accepted'); onReload(); onClose();
    } catch { toast.error('Gagal'); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Offboarding: {emp.name}</DialogTitle></DialogHeader>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="clearance" className="text-xs">Clearance Checklist</TabsTrigger>
            <TabsTrigger value="interview" className="text-xs">Exit Interview</TabsTrigger>
          </TabsList>
          <TabsContent value="clearance" className="space-y-2 mt-3">
            {['asset_returned', 'final_payslip_issued', 'bpjs_transferred', 'handover_done', 'account_disabled', 'id_card_returned'].map(k => (
              <label key={k} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-foreground/5 p-2 rounded">
                <input type="checkbox" checked={!!clearance[k]} onChange={e => setClearance(c => ({ ...c, [k]: e.target.checked }))} className="accent-emerald-500" />
                <span className="flex-1">{k.replace(/_/g, ' ')}</span>
                {clearance[k] && <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />}
              </label>
            ))}
            <Textarea placeholder="Catatan tambahan..." value={clearance.notes || ''} onChange={e => setClearance(c => ({ ...c, notes: e.target.value }))} rows={2} />
            <Button size="sm" onClick={saveClearance}><Save className="w-3 h-3 mr-1" />Simpan Clearance</Button>
          </TabsContent>
          <TabsContent value="interview" className="space-y-3 mt-3">
            <div className="space-y-1"><Label>NPS Score (0-10): seberapa Anda akan rekomendasikan bekerja di sini?</Label>
              <Input type="number" min={0} max={10} value={interview.nps_score} onChange={e => setInterview(i => ({ ...i, nps_score: +e.target.value }))} />
            </div>
            <div className="space-y-1"><Label>Pengalaman positif</Label><Textarea rows={2} value={interview.positive_feedback} onChange={e => setInterview(i => ({ ...i, positive_feedback: e.target.value }))} /></div>
            <div className="space-y-1"><Label>Area yang bisa ditingkatkan</Label><Textarea rows={2} value={interview.improvement_areas} onChange={e => setInterview(i => ({ ...i, improvement_areas: e.target.value }))} /></div>
            <div className="space-y-1"><Label>Catatan HR</Label><Textarea rows={2} value={interview.notes} onChange={e => setInterview(i => ({ ...i, notes: e.target.value }))} /></div>
            <label className="flex items-center gap-2 text-xs cursor-pointer"><input type="checkbox" checked={interview.would_recommend} onChange={e => setInterview(i => ({ ...i, would_recommend: e.target.checked }))} className="accent-emerald-500" />Bersedia merekomendasikan perusahaan ke kerabat</label>
            <Button size="sm" onClick={saveInterview}><Save className="w-3 h-3 mr-1" />Simpan Exit Interview</Button>
          </TabsContent>
        </Tabs>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose}>Tutup</Button>
          {emp.employee_status !== 'resigned' && (
            <Button variant="destructive" onClick={accept}><CheckCircle2 className="w-4 h-4 mr-1" />Accept Resignation</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════════
function OfficeLocationTab({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [office, setOffice] = useState({ name: 'Kantor Utama', lat: '', lng: '', address: '', geofence_radius_m: 300 });

  useEffect(() => {
    axios.get(`${API}/api/rahaza/attendance/office-location`, { headers }).then(r => setOffice(o => ({ ...o, ...r.data })));
  }, [headers]);

  const save = async () => {
    try {
      await axios.put(`${API}/api/rahaza/attendance/office-location`, office, { headers });
      toast.success('Lokasi kantor disimpan');
    } catch { toast.error('Gagal simpan'); }
  };

  const useCurrent = () => {
    if (!navigator.geolocation) { toast.error('Browser tidak support geolocation'); return; }
    navigator.geolocation.getCurrentPosition(
      p => { setOffice(o => ({ ...o, lat: p.coords.latitude, lng: p.coords.longitude })); toast.success('Koordinat saat ini di-set'); },
      () => toast.error('Gagal dapat lokasi')
    );
  };

  return (
    <div className="space-y-3 max-w-lg">
      <div>
        <h3 className="text-sm font-semibold">Geofence Absensi Kantor</h3>
        <p className="text-xs text-muted-foreground">Karyawan yang clock-in di luar radius akan ditandai <code>out_of_range</code>.</p>
      </div>
      <div className="space-y-2">
        <div className="space-y-1"><Label>Nama Kantor</Label><Input value={office.name} onChange={e => setOffice(o => ({ ...o, name: e.target.value }))} /></div>
        <div className="space-y-1"><Label>Alamat</Label><Input value={office.address || ''} onChange={e => setOffice(o => ({ ...o, address: e.target.value }))} placeholder="Bandung, West Java" /></div>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1"><Label>Latitude</Label><Input type="number" step="0.0001" value={office.lat || ''} onChange={e => setOffice(o => ({ ...o, lat: e.target.value }))} placeholder="-6.9147" /></div>
          <div className="space-y-1"><Label>Longitude</Label><Input type="number" step="0.0001" value={office.lng || ''} onChange={e => setOffice(o => ({ ...o, lng: e.target.value }))} placeholder="107.6098" /></div>
          <div className="space-y-1"><Label>Radius (m)</Label><Input type="number" value={office.geofence_radius_m || 300} onChange={e => setOffice(o => ({ ...o, geofence_radius_m: +e.target.value }))} /></div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={useCurrent}><MapPin className="w-4 h-4 mr-1" />Pakai Lokasi Saat Ini</Button>
          <Button size="sm" onClick={save}><Save className="w-4 h-4 mr-1" />Simpan</Button>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
function SeedTab({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const run = async (force) => {
    if (force && !window.confirm('⚠️ Force reset akan OVERWRITE data existing (grade, leave types, template, courses). Yakin?')) return;
    setRunning(true);
    try {
      const { data } = await axios.post(`${API}/api/rahaza/hr-seed/run`, { force }, { headers });
      setResult(data.summary);
      toast.success('Seed berhasil dijalankan');
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal seed'); }
    setRunning(false);
  };

  return (
    <div className="space-y-3 max-w-lg">
      <div>
        <h3 className="text-sm font-semibold">Demo Data Seed</h3>
        <p className="text-xs text-muted-foreground">Generate 12 karyawan aktif, 7 salary grades, 5 leave types, 3 LMS courses, 1 onboarding template.</p>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => run(false)} disabled={running} data-testid="seed-run">
          {running ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Sparkles className="w-4 h-4 mr-1" />}Jalankan Seed
        </Button>
        <Button size="sm" variant="destructive" onClick={() => run(true)} disabled={running}>
          <RefreshCw className="w-4 h-4 mr-1" />Force Reset
        </Button>
      </div>
      {result && (
        <div className="rounded-xl border border-emerald-300 dark:border-emerald-500/20 bg-emerald-100 dark:bg-emerald-500/5 p-3 text-xs space-y-1">
          <div>🧑‍💼 Karyawan: {result.employees?.created} baru, {result.employees?.skipped} existing</div>
          <div>🏷️ Grades: {result.grades?.created} baru, {result.grades?.skipped} existing</div>
          <div>🏖️ Leave Types: {result.leave_types?.created} baru</div>
          <div>📋 Onboarding Template: {result.onboarding_template}</div>
          <div>📚 LMS Courses: {result.courses?.created} baru</div>
        </div>
      )}
    </div>
  );
}
