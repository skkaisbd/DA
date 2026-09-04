import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Users, Plus, Edit2, Search, Save, X, Loader2, RefreshCw, User,
  Briefcase, FileText, CreditCard, Phone, UploadCloud, Trash2,
  Camera, Calendar, MapPin, GraduationCap, Heart, Landmark, Shield,
  AlertCircle, CheckCircle2, Power, Filter, Mail, UserCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;

const DEPARTMENTS = ['Produksi', 'QC', 'Gudang/WMS', 'HRD', 'Finance/Accounting', 'Marketing', 'IT', 'Administrasi', 'Manajemen', 'Lainnya'];
const JOB_TITLES = ['Operator Cutting', 'Operator CMT-Sewing', 'Operator QC', 'Operator Finishing', 'Operator Packing', 'Operator Washer', 'Operator Sontek', 'Supervisor', 'Staff Gudang', 'Staff Admin', 'Manager', 'Lainnya'];
const WAGE_SCHEMES = [
  { value: 'borongan_pcs', label: 'Borongan (per pcs)' },
  { value: 'borongan_jam', label: 'Borongan (per jam)' },
  { value: 'mingguan',     label: 'Gaji Mingguan' },
  { value: 'bulanan',      label: 'Gaji Bulanan' },
];
const CONTRACT_TYPES = [
  { value: 'PKWT',   label: 'PKWT (Kontrak Terbatas)' },
  { value: 'PKWTT',  label: 'PKWTT (Kontrak Tidak Terbatas)' },
  { value: 'Magang', label: 'Magang / Percobaan' },
  { value: 'Tetap',  label: 'Karyawan Tetap' },
];
const EDUCATION_LEVELS = ['Tidak Sekolah', 'SD', 'SMP', 'SMA/SMK', 'D1-D3', 'S1', 'S2', 'S3'];
const MARITAL_STATUS = [
  { value: 'single',   label: 'Belum Menikah' },
  { value: 'married',  label: 'Menikah' },
  { value: 'divorced', label: 'Cerai Hidup' },
  { value: 'widowed',  label: 'Cerai Mati' },
];
const RELIGIONS = ['Islam', 'Kristen Protestan', 'Katolik', 'Hindu', 'Buddha', 'Konghucu', 'Kepercayaan'];
const TAX_PTKP = [
  { value: 'TK/0', label: 'TK/0 — Tidak Kawin, tanpa tanggungan' },
  { value: 'TK/1', label: 'TK/1 — Tidak Kawin, 1 tanggungan' },
  { value: 'TK/2', label: 'TK/2 — Tidak Kawin, 2 tanggungan' },
  { value: 'TK/3', label: 'TK/3 — Tidak Kawin, 3 tanggungan' },
  { value: 'K/0',  label: 'K/0 — Kawin, tanpa tanggungan' },
  { value: 'K/1',  label: 'K/1 — Kawin, 1 tanggungan' },
  { value: 'K/2',  label: 'K/2 — Kawin, 2 tanggungan' },
  { value: 'K/3',  label: 'K/3 — Kawin, 3 tanggungan' },
];
const BANKS = ['BCA', 'BRI', 'Mandiri', 'BNI', 'BSI', 'CIMB Niaga', 'Permata', 'Danamon', 'BTN', 'Mega', 'Panin', 'Jago', 'Lainnya'];
const RELATIONS = ['Orang Tua', 'Pasangan', 'Saudara Kandung', 'Anak', 'Teman', 'Lainnya'];
const DOC_CATEGORIES = ['Kontrak Kerja', 'KTP', 'NPWP', 'Ijazah', 'SKCK', 'Sertifikat', 'Surat Pengalaman', 'BPJS', 'KK (Kartu Keluarga)', 'Pas Foto', 'Lainnya'];

const defaultEmployee = {
  employee_code: '', name: '', department: 'Produksi', job_title: 'Operator CMT-Sewing',
  location_id: '', phone: '', email: '', contract_type: 'PKWT', contract_start_date: '',
  contract_end_date: '', wage_scheme: 'borongan_pcs', base_rate: 0,
  manager_id: '',
  gender: 'L', birth_date: '', birth_place: '', marital_status: 'single', religion: 'Islam',
  nationality: 'Indonesia', ktp_address: '', current_address: '',
  education_level: 'SMA/SMK', education_institution: '', education_major: '', photo_url: '',
  ktp_number: '', npwp_number: '', tax_ptkp: 'TK/0',
  bpjs_kesehatan_number: '', bpjs_ketenagakerjaan_number: '',
  bank_name: 'BCA', bank_account_number: '', bank_account_holder: '',
  emergency_contact_name: '', emergency_phone: '', emergency_relation: 'Orang Tua',
};

export default function HREmployeeModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [employees, setEmployees] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [deptFilter, setDeptFilter] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);
  const [editing, setEditing] = useState(null);
  // Link user modal
  const [linkTarget, setLinkTarget] = useState(null); // employee object
  const [users, setUsers] = useState([]);
  const [linking, setLinking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        axios.get(`${API}/api/rahaza/employees?active_only=${activeOnly}&limit=500`, { headers }),
        axios.get(`${API}/api/rahaza/locations`, { headers }).catch(() => ({ data: [] })),
      ]);
      setEmployees(Array.isArray(r1.data) ? r1.data : (r1.data.items || r1.data.rows || []));
      setLocations(r2.data || []);
    } catch (e) {
      toast.error('Gagal memuat data karyawan');
    } finally { setLoading(false); }
  }, [headers, activeOnly]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [r1, r2] = await Promise.all([
          axios.get(`${API}/api/rahaza/employees?active_only=${activeOnly}&limit=500`, { headers }),
          axios.get(`${API}/api/rahaza/locations`, { headers }).catch(() => ({ data: [] })),
        ]);
        if (!active) return;
        setEmployees(Array.isArray(r1.data) ? r1.data : (r1.data.items || r1.data.rows || []));
        setLocations(r2.data || []);
      } catch {
        if (active) toast.error('Gagal memuat data karyawan');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, activeOnly]);

  const filtered = employees.filter(e => {
    if (deptFilter && e.department !== deptFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      e.name?.toLowerCase().includes(q) ||
      e.employee_code?.toLowerCase().includes(q) ||
      e.phone?.includes(q) ||
      e.ktp_number?.includes(q) ||
      e.email?.toLowerCase().includes(q)
    );
  });

  const handleDelete = async (emp) => {
    if (!window.confirm(`Non-aktifkan karyawan ${emp.name} (${emp.employee_code})?`)) return;
    try {
      await axios.delete(`${API}/api/rahaza/employees/${emp.id}`, { headers });
      toast.success('Karyawan dinon-aktifkan');
      load();
    } catch { toast.error('Gagal non-aktifkan'); }
  };

  const handleSave = async (form) => {
    try {
      const isEdit = !!form.id;
      const url = isEdit
        ? `${API}/api/rahaza/employees/${form.id}`
        : `${API}/api/rahaza/employees`;
      await axios[isEdit ? 'put' : 'post'](url, form, { headers });
      toast.success(isEdit ? 'Karyawan diupdate' : 'Karyawan ditambahkan');
      setEditing(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal simpan');
    }
  };

  const openLinkUser = async (emp) => {
    setLinkTarget(emp);
    if (users.length === 0) {
      try {
        const r = await axios.get(`${API}/api/auth/users?limit=200`, { headers });
        setUsers(Array.isArray(r.data) ? r.data : []);
      } catch { /* noop */ }
    }
  };

  const handleLinkUser = async (userId) => {
    if (!linkTarget) return;
    setLinking(true);
    try {
      await axios.post(`${API}/api/rahaza/employees/${linkTarget.id}/link-user`,
        { user_id: userId }, { headers });
      toast.success(userId ? `Akun ditautkan ke ${linkTarget.name}` : 'Tautan akun dihapus');
      setLinkTarget(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal tautkan');
    } finally { setLinking(false); }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="space-y-6 p-6" data-testid="hr-employees-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="w-6 h-6 text-blue-600 dark:text-blue-400" /> Data Karyawan & Kontrak
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Master karyawan lengkap: kontrak, personal, pajak & BPJS, bank, dokumen · {filtered.length} {activeOnly ? 'aktif' : 'total'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="employees-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setEditing({ ...defaultEmployee })} data-testid="employees-add">
            <Plus className="w-4 h-4 mr-1" /> Tambah Karyawan
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari nama / kode / NIK / email / HP..." className="pl-9 h-9" data-testid="employees-search" />
        </div>
        <Select value={deptFilter || 'all'} onValueChange={v => setDeptFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-44 h-9"><SelectValue placeholder="Semua Divisi" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Divisi</SelectItem>
            {DEPARTMENTS.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 text-xs">
          <Switch checked={activeOnly} onCheckedChange={setActiveOnly} id="active-only" />
          <Label htmlFor="active-only" className="cursor-pointer">Aktif saja</Label>
        </div>
      </div>

      <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
              <th className="text-left px-4 py-3 w-10"></th>
              <th className="text-left px-4 py-3">Kode / Nama</th>
              <th className="text-left px-4 py-3">Divisi & Jabatan</th>
              <th className="text-left px-4 py-3">Kontrak</th>
              <th className="text-left px-4 py-3">Kontak</th>
              <th className="text-left px-4 py-3">Kelengkapan</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {paged.map(e => <EmployeeRow key={e.id} emp={e}
              onEdit={() => setEditing(e)} onDelete={() => handleDelete(e)}
              onLinkUser={() => openLinkUser(e)} token={token} />)}
            {filtered.length === 0 && !loading && (
              <tr><td colSpan={7}>
                <EmptyState icon={Users} title="Belum ada karyawan" description="Tambahkan karyawan pertama menggunakan tombol '+' di atas." />
              </td></tr>
            )}
            {loading && Array.from({ length: 5 }).map((_, i) => (
              <tr key={i}>{[...Array(7)].map((__, j) => <td key={j} className="px-3 py-2.5"><Skeleton className="h-4" /></td>)}</tr>
            ))}
          </tbody>
        </table>
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
      </div>

      {editing && (
        <EmployeeDialog
          initial={editing}
          locations={locations}
          employees={employees}
          headers={headers}
          token={token}
          onSave={handleSave}
          onClose={() => setEditing(null)}
        />
      )}

      {/* ── Link User Dialog ── */}
      {linkTarget && (
        <Dialog open onOpenChange={() => setLinkTarget(null)}>
          <DialogContent className="max-w-md" data-testid="link-user-dialog">
            <DialogHeader>
              <DialogTitle>Tautkan Akun Login — {linkTarget.name}</DialogTitle>
              <p className="text-xs text-muted-foreground mt-1">
                Pilih akun pengguna yang akan ditautkan ke karyawan ini.
                Setelah ditautkan, karyawan dapat mengakses Portal Saya (slip gaji, cuti, dll).
              </p>
            </DialogHeader>
            {linkTarget.user_id && (
              <div className="flex items-center justify-between p-2 rounded bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-400 dark:border-emerald-500/30 text-xs text-emerald-600 dark:text-emerald-400">
                <span>Saat ini: {linkTarget.user_email || linkTarget.user_id}</span>
                <Button variant="ghost" size="sm" className="h-6 text-xs text-red-700 dark:text-red-400"
                  onClick={() => handleLinkUser('')} disabled={linking}>
                  Hapus Tautan
                </Button>
              </div>
            )}
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {users.filter(u => u.role !== 'superadmin').map(u => (
                <button key={u.id}
                  onClick={() => handleLinkUser(u.id)}
                  disabled={linking}
                  className={`w-full text-left p-2.5 rounded-lg border text-sm transition-colors ${
                    linkTarget.user_id === u.id
                      ? 'bg-primary/10 border-primary/40 text-primary'
                      : 'border-border hover:bg-muted/30'
                  }`}
                  data-testid={`link-user-${u.id}`}
                >
                  <div className="font-medium">{u.name || u.email}</div>
                  <div className="text-xs text-muted-foreground">{u.email} · {u.role}</div>
                </button>
              ))}
              {users.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Memuat daftar user...</p>}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setLinkTarget(null)}>Tutup</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function EmployeeRow({ emp, onEdit, onDelete, onLinkUser, token }) {
  // Kelengkapan score: essential fields present
  const fields = [
    emp.ktp_number && emp.ktp_number.length === 16,
    !!emp.bank_account_number,
    !!emp.phone,
    !!emp.contract_type,
    !!emp.birth_date,
    !!emp.emergency_contact_name,
    !!emp.bpjs_kesehatan_number,
    !!emp.tax_ptkp && emp.tax_ptkp !== 'TK/0',
  ];
  const complete = fields.filter(Boolean).length;
  const pct = Math.round(complete / fields.length * 100);
  const contractEnd = emp.contract_end_date ? new Date(emp.contract_end_date) : null;
  const daysUntilEnd = contractEnd ? Math.ceil((contractEnd - new Date()) / 86400000) : null;
  const isExpiring = daysUntilEnd !== null && daysUntilEnd >= 0 && daysUntilEnd <= 30;

  return (
    <tr className="hover:bg-foreground/5" data-testid={`employee-row-${emp.id}`}>
      <td className="px-4 py-3">
        {emp.photo_url ? (
          <img src={`${API}${emp.photo_url}${emp.photo_url.includes('?') ? '&' : '?'}auth=${token}`}
            alt={emp.name}
            className="w-9 h-9 rounded-full object-cover border border-foreground/10" />
        ) : (
          <div className="w-9 h-9 rounded-full bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 flex items-center justify-center text-xs font-semibold">
            {(emp.name || '?').slice(0, 2).toUpperCase()}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="font-medium text-sm">{emp.name}</div>
        <div className="text-xs text-muted-foreground font-mono">{emp.employee_code}</div>
      </td>
      <td className="px-4 py-3">
        <div className="text-sm">{emp.job_title || '—'}</div>
        <div className="text-xs text-muted-foreground">{emp.department || '—'}</div>
        {emp.manager_name && (
          <div className="text-[10px] text-indigo-600 dark:text-indigo-400 mt-0.5 flex items-center gap-1">
            <span className="opacity-70">↳</span> {emp.manager_name}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
            emp.contract_type === 'PKWTT' || emp.contract_type === 'Tetap' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300' :
            emp.contract_type === 'PKWT' ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300' :
            emp.contract_type === 'Magang' ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300' :
            'bg-muted dark:bg-slate-500/20 text-foreground/70'
          }`}>{emp.contract_type || '—'}</span>
        </div>
        {emp.contract_end_date && (
          <div className={`text-xs mt-1 ${isExpiring ? 'text-red-700 dark:text-red-400 font-semibold' : 'text-muted-foreground'}`}>
            s/d {new Date(emp.contract_end_date).toLocaleDateString('id-ID')}
            {isExpiring && ` (${daysUntilEnd}hr)`}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-xs">
        {emp.phone && <div className="flex items-center gap-1"><Phone className="w-3 h-3 text-muted-foreground" />{emp.phone}</div>}
        {emp.email && <div className="flex items-center gap-1 text-muted-foreground"><Mail className="w-3 h-3" />{emp.email}</div>}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 w-20 bg-foreground/10 rounded-full overflow-hidden">
            <div className={`h-full ${pct >= 80 ? 'bg-emerald-400' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'}`}
              style={{ width: `${pct}%` }} />
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">{pct}%</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onEdit}
            data-testid={`employee-edit-${emp.id}`}>
            <Edit2 className="w-3.5 h-3.5" />
          </Button>
          <Button
            size="icon" variant="ghost"
            className={`h-7 w-7 ${emp.user_id ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}
            onClick={onLinkUser}
            title={emp.user_id ? `Terhubung: ${emp.user_email || emp.user_id}` : 'Tautkan akun login'}
            data-testid={`employee-link-${emp.id}`}
          >
            <User className="w-3.5 h-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400" onClick={onDelete}>
            <Power className="w-3.5 h-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function EmployeeDialog({ initial, locations, employees = [], headers, token, onSave, onClose }) {
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [tab, setTab] = useState('dasar');
  const isEdit = !!form.id;

  const loadDocs = useCallback(async () => {
    if (!form.id) return;
    try {
      const { data } = await axios.get(`${API}/api/rahaza/employees/${form.id}/documents`, { headers });
      setDocuments(data.documents || []);
    } catch { /* ignore: docs are optional */ }
  }, [form.id, headers]);

  useEffect(() => {
    if (!form.id) return undefined;
    let active = true;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/api/rahaza/employees/${form.id}/documents`, { headers });
        if (active) setDocuments(data.documents || []);
      } catch { /* ignore: docs are optional */ }
    })();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.id, headers]);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e?.target ? e.target.value : e }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.employee_code || !form.name) { toast.error('Kode dan nama wajib diisi'); return; }
    if (form.ktp_number && form.ktp_number.length !== 16) { toast.error('NIK KTP harus 16 digit'); return; }
    if (form.npwp_number && form.npwp_number.replace(/[^0-9]/g, '').length !== 15) { toast.error('NPWP harus 15 digit'); return; }
    setSaving(true); await onSave(form); setSaving(false);
  };

  const uploadFile = async (file, onUrl, category = '') => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const { data } = await axios.post(
        `${API}/api/upload?entity_type=employee&entity_id=${form.id || 'new'}`,
        fd, { headers: { ...headers, 'Content-Type': 'multipart/form-data' } }
      );
      // storage_path → build public URL
      const url = data.storage_path ? `/api/files/${data.storage_path}` : '';
      onUrl(url, data);
      if (form.id && category) {
        // Save category
        try {
          await axios.put(`${API}/api/attachments/${data.id}/meta`, { category }, { headers });
        } catch { /* ignore: category metadata is best-effort */ }
      }
      return data;
    } catch (e) {
      toast.error('Upload gagal: ' + (e.response?.data?.detail || e.message));
      return null;
    }
  };

  const onPhotoChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 3 * 1024 * 1024) { toast.error('Foto max 3MB'); return; }
    const data = await uploadFile(file, (url) => setForm(f => ({ ...f, photo_url: url })));
    if (data && form.id) {
      // Update photo_url on employee record
      await axios.post(`${API}/api/rahaza/employees/${form.id}/photo`,
        { photo_url: `/api/files/${data.storage_path}` }, { headers });
    }
  };

  const onDocUpload = async (e, category) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadFile(file, () => {}, category);
    toast.success(`Dokumen ${category} diunggah`);
    loadDocs();
    e.target.value = '';
  };

  const deleteDoc = async (attId) => {
    if (!window.confirm('Hapus dokumen ini?')) return;
    try {
      await axios.delete(`${API}/api/attachments/${attId}`, { headers });
      toast.success('Dokumen dihapus');
      loadDocs();
    } catch { toast.error('Gagal hapus'); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[95vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserCheck className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            {isEdit ? `Edit ${form.name}` : 'Tambah Karyawan Baru'}
          </DialogTitle>
          <DialogDescription>
            Kelola data karyawan: info dasar, personal, pajak &amp; BPJS, bank, dan dokumen.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit}>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="grid grid-cols-5 w-full">
              <TabsTrigger value="dasar" className="text-xs"><Briefcase className="w-3 h-3 mr-1" />Info Dasar</TabsTrigger>
              <TabsTrigger value="personal" className="text-xs"><User className="w-3 h-3 mr-1" />Personal</TabsTrigger>
              <TabsTrigger value="pajak" className="text-xs"><Shield className="w-3 h-3 mr-1" />Pajak & BPJS</TabsTrigger>
              <TabsTrigger value="bank" className="text-xs"><Landmark className="w-3 h-3 mr-1" />Bank & Emergency</TabsTrigger>
              <TabsTrigger value="dokumen" disabled={!isEdit} className="text-xs"><FileText className="w-3 h-3 mr-1" />Dokumen{!isEdit && ' (simpan dulu)'}</TabsTrigger>
            </TabsList>

            {/* Tab 1: Info Dasar */}
            <TabsContent value="dasar" className="space-y-3 mt-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Kode Karyawan *" data-testid="emp-code">
                  <Input value={form.employee_code} onChange={set('employee_code')} required placeholder="EMP-001" />
                </Field>
                <Field label="Nama Lengkap *" data-testid="emp-name">
                  <Input value={form.name} onChange={set('name')} required />
                </Field>
                <Field label="Divisi / Departemen">
                  <Sel value={form.department} onChange={set('department')} options={DEPARTMENTS.map(d => ({ value: d, label: d }))} />
                </Field>
                <Field label="Jabatan">
                  <Sel value={form.job_title} onChange={set('job_title')} options={JOB_TITLES.map(j => ({ value: j, label: j }))} />
                </Field>
                <Field label="Atasan (Manager)" help="Atasan yang akan approve usulan kenaikan gaji">
                  <Sel
                    value={form.manager_id || ''}
                    onChange={set('manager_id')}
                    options={[
                      { value: '', label: '— Tidak ada atasan —' },
                      ...employees
                        .filter(e => e.id !== form.id && e.active !== false)
                        .map(e => ({ value: e.id, label: `${e.employee_code} — ${e.name}${e.job_title ? ` (${e.job_title})` : ''}` })),
                    ]}
                  />
                </Field>
                <Field label="Lokasi Utama">
                  <Sel value={form.location_id || ''} onChange={set('location_id')} options={[{ value: '', label: '— Pilih —' }, ...locations.filter(l => l.active).map(l => ({ value: l.id, label: `${l.code} · ${l.name}` }))]} />
                </Field>
                <Field label="No. Telepon">
                  <Input value={form.phone} onChange={set('phone')} placeholder="08xxxxxxxxxx" />
                </Field>
                <Field label="Email">
                  <Input type="email" value={form.email} onChange={set('email')} placeholder="user@example.com" />
                </Field>
                <Field label="Tipe Kontrak">
                  <Sel value={form.contract_type || ''} onChange={set('contract_type')} options={CONTRACT_TYPES} />
                </Field>
                <Field label="Tgl Mulai Kontrak">
                  <Input type="date" value={form.contract_start_date || ''} onChange={set('contract_start_date')} />
                </Field>
                <Field label="Tgl Berakhir Kontrak" help="Wajib untuk PKWT/Magang">
                  <Input type="date" value={form.contract_end_date || ''} onChange={set('contract_end_date')} />
                </Field>
                <Field label="Skema Gaji *">
                  <Sel value={form.wage_scheme} onChange={set('wage_scheme')} options={WAGE_SCHEMES} />
                </Field>
                <Field label="Rate / Base (Rp)" help="Borongan pcs=Rp/pcs, jam=Rp/jam, mingguan/bulanan=total">
                  <Input type="number" min={0} value={form.base_rate} onChange={e => setForm(f => ({ ...f, base_rate: Number(e.target.value) }))} />
                </Field>
              </div>
            </TabsContent>

            {/* Tab 2: Personal */}
            <TabsContent value="personal" className="space-y-3 mt-4">
              <div className="grid grid-cols-[120px_1fr] gap-4 items-start">
                <div className="space-y-2">
                  {form.photo_url ? (
                    <img src={`${API}${form.photo_url}${form.photo_url.includes('?') ? '&' : '?'}auth=${token}`} alt={form.name}
                      className="w-28 h-28 rounded-xl object-cover border border-foreground/10" />
                  ) : (
                    <div className="w-28 h-28 rounded-xl bg-foreground/5 border border-dashed border-foreground/20 flex flex-col items-center justify-center text-muted-foreground">
                      <Camera className="w-6 h-6 mb-1 opacity-50" />
                      <span className="text-[10px]">Foto</span>
                    </div>
                  )}
                  <label className="block">
                    <input type="file" accept="image/*" className="hidden" onChange={onPhotoChange} disabled={!isEdit} />
                    <Button size="sm" variant="outline" type="button" className="w-full text-xs h-8"
                      disabled={!isEdit}
                      onClick={(ev) => ev.currentTarget.parentElement.querySelector('input').click()}>
                      <UploadCloud className="w-3 h-3 mr-1" /> {form.photo_url ? 'Ganti' : 'Upload'}
                    </Button>
                    {!isEdit && <div className="text-[10px] text-muted-foreground mt-1 text-center">Simpan dulu</div>}
                  </label>
                </div>

                <div className="grid grid-cols-2 gap-3 flex-1">
                  <Field label="Jenis Kelamin">
                    <Sel value={form.gender} onChange={set('gender')} options={[{ value: 'L', label: 'Laki-laki' }, { value: 'P', label: 'Perempuan' }]} />
                  </Field>
                  <Field label="Status Pernikahan">
                    <Sel value={form.marital_status} onChange={set('marital_status')} options={MARITAL_STATUS} />
                  </Field>
                  <Field label="Tempat Lahir">
                    <Input value={form.birth_place} onChange={set('birth_place')} placeholder="Kota kelahiran" />
                  </Field>
                  <Field label="Tanggal Lahir">
                    <Input type="date" value={form.birth_date || ''} onChange={set('birth_date')} />
                  </Field>
                  <Field label="Agama">
                    <Sel value={form.religion} onChange={set('religion')} options={RELIGIONS.map(r => ({ value: r, label: r }))} />
                  </Field>
                  <Field label="Kewarganegaraan">
                    <Input value={form.nationality} onChange={set('nationality')} />
                  </Field>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="Alamat KTP">
                  <Textarea value={form.ktp_address} onChange={set('ktp_address')} rows={2}
                    placeholder="Sesuai KTP (RT/RW, Kel, Kec, Kota)" />
                </Field>
                <Field label="Alamat Tinggal Saat Ini">
                  <Textarea value={form.current_address} onChange={set('current_address')} rows={2}
                    placeholder="Alamat domisili sekarang" />
                </Field>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <Field label="Pendidikan Terakhir">
                  <Sel value={form.education_level} onChange={set('education_level')} options={EDUCATION_LEVELS.map(e => ({ value: e, label: e }))} />
                </Field>
                <Field label="Sekolah / Universitas">
                  <Input value={form.education_institution} onChange={set('education_institution')} placeholder="Nama institusi" />
                </Field>
                <Field label="Jurusan">
                  <Input value={form.education_major} onChange={set('education_major')} placeholder="Jurusan / program" />
                </Field>
              </div>
            </TabsContent>

            {/* Tab 3: Pajak & BPJS */}
            <TabsContent value="pajak" className="space-y-3 mt-4">
              <div className="rounded-lg border border-amber-300 dark:border-amber-500/20 bg-amber-100 dark:bg-amber-500/5 p-3 text-xs text-muted-foreground">
                <AlertCircle className="inline w-3.5 h-3.5 mr-1 text-amber-700 dark:text-amber-400" />
                Data ini digunakan untuk <strong>perhitungan PPh21 & BPJS otomatis</strong> di payroll. Pastikan akurat.
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="NIK KTP (16 digit) *" help="Nomor Induk Kependudukan — wajib untuk BPJS & pajak">
                  <Input value={form.ktp_number} onChange={set('ktp_number')}
                    maxLength={16} placeholder="3310xxxxxxxxxxxx" />
                  {form.ktp_number && form.ktp_number.length !== 16 && (
                    <div className="text-[10px] text-red-700 dark:text-red-400 mt-1">NIK harus tepat 16 digit ({form.ktp_number.length}/16)</div>
                  )}
                </Field>
                <Field label="NPWP (15 digit)" help="Opsional jika karyawan sudah terdaftar">
                  <Input value={form.npwp_number} onChange={set('npwp_number')} placeholder="xx.xxx.xxx.x-xxx.xxx" />
                </Field>
                <Field label="PTKP (Status Pajak)" help="Menentukan Penghasilan Tidak Kena Pajak untuk PPh21">
                  <Sel value={form.tax_ptkp} onChange={set('tax_ptkp')} options={TAX_PTKP} />
                </Field>
                <div></div>
                <Field label="No. BPJS Kesehatan">
                  <Input value={form.bpjs_kesehatan_number} onChange={set('bpjs_kesehatan_number')}
                    placeholder="13 digit" />
                </Field>
                <Field label="No. BPJS Ketenagakerjaan">
                  <Input value={form.bpjs_ketenagakerjaan_number} onChange={set('bpjs_ketenagakerjaan_number')}
                    placeholder="11 digit" />
                </Field>
              </div>
            </TabsContent>

            {/* Tab 4: Bank & Emergency */}
            <TabsContent value="bank" className="space-y-4 mt-4">
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
                  <Landmark className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> Rekening Bank (untuk transfer payroll)
                </h3>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Nama Bank">
                    <Sel value={form.bank_name} onChange={set('bank_name')} options={BANKS.map(b => ({ value: b, label: b }))} />
                  </Field>
                  <Field label="No. Rekening">
                    <Input value={form.bank_account_number} onChange={set('bank_account_number')} placeholder="xxxxxxxxxx" />
                  </Field>
                  <Field label="Atas Nama" help="Biasanya = nama karyawan">
                    <Input value={form.bank_account_holder || form.name} onChange={set('bank_account_holder')} />
                  </Field>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
                  <Heart className="w-4 h-4 text-red-700 dark:text-red-400" /> Emergency Contact
                </h3>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Nama Kontak Darurat">
                    <Input value={form.emergency_contact_name} onChange={set('emergency_contact_name')} placeholder="Nama keluarga" />
                  </Field>
                  <Field label="No. HP Kontak Darurat">
                    <Input value={form.emergency_phone} onChange={set('emergency_phone')} placeholder="08xxxxxxxxxx" />
                  </Field>
                  <Field label="Hubungan">
                    <Sel value={form.emergency_relation} onChange={set('emergency_relation')} options={RELATIONS.map(r => ({ value: r, label: r }))} />
                  </Field>
                </div>
              </div>
            </TabsContent>

            {/* Tab 5: Dokumen */}
            <TabsContent value="dokumen" className="space-y-3 mt-4">
              <div className="rounded-lg border border-blue-300 dark:border-blue-500/20 bg-blue-100 dark:bg-blue-500/5 p-3 text-xs">
                <FileText className="inline w-3.5 h-3.5 mr-1 text-blue-600 dark:text-blue-400" />
                Upload dokumen karyawan seperti: scan KTP, NPWP, ijazah, kontrak kerja, sertifikat, dll. <strong>Max 10MB per file</strong>.
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {DOC_CATEGORIES.map(cat => (
                  <label key={cat} className="rounded-lg border border-dashed border-foreground/20 bg-foreground/5 px-3 py-2 hover:bg-foreground/10 cursor-pointer text-xs flex items-center gap-2">
                    <UploadCloud className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="flex-1">{cat}</span>
                    <input type="file" className="hidden" onChange={(e) => onDocUpload(e, cat)} />
                  </label>
                ))}
              </div>

              <div className="rounded-xl border border-foreground/10 bg-foreground/5 overflow-hidden">
                {documents.length === 0 ? (
                  <div className="text-center py-10 text-muted-foreground text-sm">
                    <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    Belum ada dokumen
                  </div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="bg-foreground/5 text-muted-foreground">
                      <tr>
                        <th className="text-left px-3 py-2">Nama File</th>
                        <th className="text-left px-3 py-2">Kategori</th>
                        <th className="text-left px-3 py-2">Ukuran</th>
                        <th className="text-left px-3 py-2">Diupload</th>
                        <th className="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {documents.map(d => (
                        <tr key={d.id} className="hover:bg-foreground/5">
                          <td className="px-3 py-2">
                            <a href={`${API}/api/files/${d.storage_path}?auth=${token}`}
                              target="_blank" rel="noreferrer"
                              className="text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                              <FileText className="w-3 h-3" /> {d.original_filename}
                            </a>
                          </td>
                          <td className="px-3 py-2">
                            <span className="px-1.5 py-0.5 rounded-full bg-foreground/10 text-[10px]">{d.category || '—'}</span>
                          </td>
                          <td className="px-3 py-2 text-muted-foreground font-mono">
                            {d.size ? `${(d.size / 1024).toFixed(1)} KB` : '—'}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {d.created_at ? new Date(d.created_at).toLocaleDateString('id-ID') : '—'}
                          </td>
                          <td className="px-3 py-2">
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400"
                              onClick={() => deleteDoc(d.id)}>
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={onClose}>
              <X className="w-4 h-4 mr-1" /> Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="emp-save">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, help, children, ...props }) {
  return (
    <div className="space-y-1" {...props}>
      <Label className="text-xs">{label}</Label>
      {children}
      {help && <p className="text-[10px] text-muted-foreground">{help}</p>}
    </div>
  );
}

function Sel({ value, onChange, options }) {
  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger className="h-9"><SelectValue placeholder="— Pilih —" /></SelectTrigger>
      <SelectContent>
        {options.map(o => <SelectItem key={o.value} value={o.value || '_'}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
