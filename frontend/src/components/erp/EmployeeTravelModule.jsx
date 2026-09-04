/**
 * Employee Travel Module — Perjalanan Dinas
 * CV. Dewi Aditya — Employee Expense Management (EEM)
 *
 * Features:
 *  - Submit travel request dengan auto per diem calculation
 *  - Cash advance tracking
 *  - Status flow: draft → submitted → approved → advance_paid → on_trip → completed
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Plus, RefreshCw, MapPin, CheckCircle, XCircle,
  Clock, Send, Banknote, Eye, AlertCircle, Filter,
  CalendarDays, DollarSign, Plane, Download
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { PageHeader, StatTile } from './moduleAtoms';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = formatRupiah;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('id-ID', { day:'2-digit', month:'short', year:'numeric' }) : '—';

const DEST_TYPES = [
  { value: 'dalam_kota', label: 'Dalam Kota', icon: '🏙️' },
  { value: 'luar_kota',  label: 'Luar Kota',  icon: '🚗' },
  { value: 'luar_negeri', label: 'Luar Negeri', icon: '✈️' },
];

const STATUS_CONFIG = {
  draft:        { label: 'Draft',                color: 'bg-muted text-foreground' },
  submitted:    { label: 'Menunggu Persetujuan', color: 'bg-yellow-100 text-yellow-800' },
  approved:     { label: 'Disetujui',            color: 'bg-blue-100 text-blue-800' },
  rejected:     { label: 'Ditolak',              color: 'bg-red-100 text-red-800' },
  advance_paid: { label: 'Uang Muka Dibayar',   color: 'bg-teal-100 text-teal-800' },
  on_trip:      { label: 'Sedang Perjalanan',    color: 'bg-orange-100 text-orange-800' },
  completed:    { label: 'Selesai',              color: 'bg-green-100 text-green-800' },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || { label: status, color: 'bg-muted text-foreground' };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>{c.label}</span>;
}

function TravelForm({ token, onClose, onSaved }) {
  const [form, setForm] = useState({
    destination: '', destination_type: 'luar_kota', purpose: '',
    start_date: '', end_date: '', transport_estimate: '', accommodation_estimate: '',
    other_estimate: '', cash_advance_requested: '', notes: '', use_per_diem: true,
  });
  const [perDiemPreview, setPerDiemPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // SESI #27 — kolom nomor SPPD mengikuti kebijakan Otomatis/Manual milik owner.
  const numPolicy = useDocNumberPolicy('employee_travel_requests.trip_number', token);
  const [tripNumber, setTripNumber] = useState('');

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  // Preview per diem
  const fetchPerDiemPreview = useCallback(async () => {
    if (!form.destination_type || !form.start_date || !form.end_date) return;
    try {
      const days = Math.max(1, Math.ceil((new Date(form.end_date) - new Date(form.start_date)) / 86400000) + 1);
      // Use rate from API (will use defaults if not configured)
      const rates = { dalam_kota: 100000, luar_kota: 300000, luar_negeri: 600000 };
      const daily = rates[form.destination_type] || 150000;
      setPerDiemPreview({ per_diem_daily: daily, days_count: days, per_diem_total: daily * days });
    } catch (e) { /* ignore */ }
  }, [form.destination_type, form.start_date, form.end_date]);

  useEffect(() => { fetchPerDiemPreview(); }, [fetchPerDiemPreview]);

  const calcTotal = () => {
    const pd = form.use_per_diem ? (perDiemPreview?.per_diem_total || 0) : 0;
    return pd + (parseFloat(form.transport_estimate) || 0) +
      (parseFloat(form.accommodation_estimate) || 0) +
      (parseFloat(form.other_estimate) || 0);
  };

  const handleSubmit = async () => {
    if (!form.destination.trim() || !form.purpose.trim()) { setError('Destinasi dan tujuan wajib diisi'); return; }
    if (!form.start_date || !form.end_date) { setError('Tanggal berangkat dan pulang wajib diisi'); return; }
    if (new Date(form.end_date) < new Date(form.start_date)) { setError('Tanggal pulang tidak boleh sebelum tanggal berangkat'); return; }
    setSaving(true); setError('');
    try {
      const body = {
        ...form,
        ...docNumberPayload(numPolicy, 'trip_number', tripNumber),
        transport_estimate: parseFloat(form.transport_estimate) || 0,
        accommodation_estimate: parseFloat(form.accommodation_estimate) || 0,
        other_estimate: parseFloat(form.other_estimate) || 0,
        cash_advance_requested: parseFloat(form.cash_advance_requested) || 0,
      };
      const r = await fetch(`${API}/api/hr/expenses/travel`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      onSaved(d);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <DocNumberField
        policy={numPolicy} value={tripNumber} onChange={setTripNumber}
        testId="travel-docnum" label="Nomor Perjalanan Dinas" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-sm font-medium">Destinasi *</label>
          <Input placeholder="mis: Surabaya, Jawa Timur" value={form.destination} onChange={e => set('destination', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Tipe Perjalanan</label>
          <Select value={form.destination_type} onValueChange={v => set('destination_type', v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{DEST_TYPES.map(d => <SelectItem key={d.value} value={d.value}>{d.icon} {d.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Tanggal Berangkat *</label>
          <Input type="date" value={form.start_date} onChange={e => set('start_date', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Tanggal Kembali *</label>
          <Input type="date" value={form.end_date} onChange={e => set('end_date', e.target.value)} />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Tujuan / Agenda *</label>
        <Textarea placeholder="Jelaskan tujuan dan agenda perjalanan dinas" value={form.purpose} onChange={e => set('purpose', e.target.value)} rows={2} />
      </div>

      {/* Per Diem Preview */}
      {perDiemPreview && (
        <div className="rounded-lg border bg-blue-50 dark:bg-blue-950/30 p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-blue-800 dark:text-blue-300">Uang Harian (Per Diem)</span>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={form.use_per_diem} onChange={e => set('use_per_diem', e.target.checked)} />
              Gunakan per diem
            </label>
          </div>
          {form.use_per_diem && (
            <div className="text-sm text-blue-700 dark:text-blue-400">
              {fmt(perDiemPreview.per_diem_daily)} × {perDiemPreview.days_count} hari =
              <span className="font-bold ml-1">{fmt(perDiemPreview.per_diem_total)}</span>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-sm font-medium">Estimasi Transport (Rp)</label>
          <Input type="number" placeholder="0" value={form.transport_estimate} onChange={e => set('transport_estimate', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Estimasi Akomodasi (Rp)</label>
          <Input type="number" placeholder="0" value={form.accommodation_estimate} onChange={e => set('accommodation_estimate', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Biaya Lain (Rp)</label>
          <Input type="number" placeholder="0" value={form.other_estimate} onChange={e => set('other_estimate', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Uang Muka Diminta (Rp)</label>
          <Input type="number" placeholder="0" value={form.cash_advance_requested} onChange={e => set('cash_advance_requested', e.target.value)} />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Catatan</label>
        <Textarea placeholder="Informasi tambahan (opsional)" value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} />
      </div>

      {/* Total Budget */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-green-50 dark:bg-green-950/30">
        <span className="text-sm font-medium">Estimasi Total Budget</span>
        <span className="text-lg font-bold text-green-700 dark:text-green-300">{fmt(calcTotal())}</span>
      </div>

      {error && <div className="text-sm text-red-600 flex items-center gap-1"><AlertCircle className="w-4 h-4" />{error}</div>}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={handleSubmit} disabled={saving}>{saving ? 'Menyimpan...' : 'Simpan Draft'}</Button>
      </DialogFooter>
    </div>
  );
}

function TravelDetail({ req, token, onClose, onRefresh, role }) {
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);
  const [note, setNote] = useState('');
  const [advanceAmount, setAdvanceAmount] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const doAction = async (endpoint, body = {}) => {
    setActionLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/expenses/travel/${req.id}/${endpoint}`, {
        method: 'POST', headers, body: JSON.stringify(body),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Gagal'); }
      onRefresh(); onClose();
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const isApprover = ['superadmin','admin','owner','hr','manager','finance'].includes(role?.toLowerCase());
  const isFinance = ['superadmin','admin','owner','finance'].includes(role?.toLowerCase());

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><p className="text-xs text-muted-foreground">Nomor</p><p className="font-mono font-bold">{req.trip_number}</p></div>
        <div><p className="text-xs text-muted-foreground">Status</p><StatusBadge status={req.status} /></div>
        <div><p className="text-xs text-muted-foreground">Karyawan</p><p className="font-medium">{req.employee_name}</p><p className="text-xs text-muted-foreground">{req.employee_dept}</p></div>
        <div><p className="text-xs text-muted-foreground">Tipe</p><p>{req.destination_label || req.destination_type}</p></div>
        <div className="col-span-2"><p className="text-xs text-muted-foreground">Destinasi</p><p className="font-medium text-lg">{req.destination}</p></div>
        <div><p className="text-xs text-muted-foreground">Tanggal Pergi</p><p>{fmtDate(req.start_date)}</p></div>
        <div><p className="text-xs text-muted-foreground">Tanggal Kembali</p><p>{fmtDate(req.end_date)}</p></div>
        <div className="col-span-2"><p className="text-xs text-muted-foreground">Tujuan</p><p>{req.purpose}</p></div>
      </div>

      <div className="rounded-lg border p-3 space-y-2">
        <p className="text-sm font-medium">Rincian Budget</p>
        <div className="grid grid-cols-2 gap-2 text-sm">
          {req.use_per_diem && <><div className="text-muted-foreground">Per Diem ({req.days_count} hari)</div><div className="text-right font-medium">{fmt(req.per_diem_total)}</div></>}
          {req.transport_estimate > 0 && <><div className="text-muted-foreground">Transport</div><div className="text-right font-medium">{fmt(req.transport_estimate)}</div></>}
          {req.accommodation_estimate > 0 && <><div className="text-muted-foreground">Akomodasi</div><div className="text-right font-medium">{fmt(req.accommodation_estimate)}</div></>}
          {req.other_estimate > 0 && <><div className="text-muted-foreground">Lain-lain</div><div className="text-right font-medium">{fmt(req.other_estimate)}</div></>}
          <div className="font-bold border-t pt-1">Total Budget</div><div className="text-right font-bold border-t pt-1">{fmt(req.total_budget)}</div>
          {req.cash_advance_requested > 0 && <><div className="text-muted-foreground">Uang Muka Diminta</div><div className="text-right">{fmt(req.cash_advance_requested)}</div></>}
          {req.cash_advance_approved > 0 && <><div className="text-blue-700 dark:text-blue-300">Uang Muka Disetujui</div><div className="text-right text-blue-700 dark:text-blue-300 font-bold">{fmt(req.cash_advance_approved)}</div></>}
          {req.cash_advance_paid > 0 && <><div className="text-green-700 dark:text-green-300">Uang Muka Dibayar</div><div className="text-right text-green-700 dark:text-green-300 font-bold">{fmt(req.cash_advance_paid)}</div></>}
        </div>
      </div>

      {req.reject_reason && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-3">
          <p className="text-sm font-medium text-red-700">Alasan Ditolak</p>
          <p className="text-sm text-red-600">{req.reject_reason}</p>
        </div>
      )}

      {showReject && (
        <div className="space-y-2">
          <Textarea placeholder="Alasan penolakan (wajib)" value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} />
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowReject(false)}>Batal</Button>
            <Button variant="destructive" size="sm"
              disabled={!rejectReason.trim() || actionLoading}
              onClick={() => doAction('reject', { reason: rejectReason })}>
              Konfirmasi Tolak
            </Button>
          </div>
        </div>
      )}

      {isFinance && req.status === 'approved' && (
        <div className="rounded-lg bg-teal-50 border border-teal-200 p-3 space-y-2">
          <p className="text-sm font-medium text-teal-800">Bayar Uang Muka</p>
          <div className="flex gap-2">
            <Input
              type="number"
              placeholder={`Jumlah (disetujui: ${fmt(req.cash_advance_approved)})`}
              value={advanceAmount}
              onChange={e => setAdvanceAmount(e.target.value)}
              className="text-sm h-8"
            />
            <Button size="sm" className="bg-teal-600 hover:bg-teal-700 text-foreground whitespace-nowrap"
              onClick={() => doAction('advance-paid', { amount_paid: parseFloat(advanceAmount) || req.cash_advance_approved })}
              disabled={actionLoading}>
              <Banknote className="w-3.5 h-3.5 mr-1" />Bayar
            </Button>
          </div>
        </div>
      )}

      <DialogFooter className="flex-wrap gap-2">
        <Button variant="outline" onClick={onClose}>Tutup</Button>
        {req.status === 'draft' && (
          <Button size="sm" onClick={() => doAction('submit')} disabled={actionLoading}>
            <Send className="w-3.5 h-3.5 mr-1" />Submit
          </Button>
        )}
        {isApprover && req.status === 'submitted' && !showReject && (
          <>
            <Button variant="destructive" size="sm" onClick={() => setShowReject(true)} disabled={actionLoading}>Tolak</Button>
            <div className="flex gap-2 items-center">
              <Input placeholder="Catatan" className="h-8 text-sm w-36" value={note} onChange={e => setNote(e.target.value)} />
              <Button size="sm" onClick={() => doAction('approve', { note, cash_advance_approved: req.cash_advance_requested })} disabled={actionLoading}>
                <CheckCircle className="w-3.5 h-3.5 mr-1" />Setujui
              </Button>
            </div>
          </>
        )}
        {['approved', 'advance_paid', 'on_trip'].includes(req.status) && (
          <Button size="sm" variant="outline"
            onClick={() => doAction('complete')} disabled={actionLoading}>
            <CheckCircle className="w-3.5 h-3.5 mr-1" />Tandai Selesai
          </Button>
        )}
      </DialogFooter>
    </div>
  );
}

export default function EmployeeTravelModule({ token, user }) {
  const [reqs, setReqs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState('my');
  
  // Phase 4: Bulk & Export
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [exportFromDate, setExportFromDate] = useState('');
  const [exportToDate, setExportToDate] = useState('');
  
  const role = user?.role || '';
  const isApprover = ['superadmin','admin','owner','hr','manager','finance'].includes(role.toLowerCase());
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter !== 'all') params.set('status', filter);
      if (search) params.set('search', search);
      if (viewMode === 'my') params.set('employee_id', user?.id || '');
      const [tr, sr] = await Promise.all([
        fetch(`${API}/api/hr/expenses/travel?${params}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/hr/expenses/my-summary`, { headers }).then(r => r.json()),
      ]);
      setReqs(Array.isArray(tr.items) ? tr.items : []);
      setSummary(sr);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token, filter, search, viewMode, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(); }, [fetchData]);

  // Phase 4: Export — RC-23: toast sukses hanya bila backend OK (dulu fire-and-forget)
  const handleExport = async () => {
    const params = new URLSearchParams();
    if (filter !== 'all') params.set('status', filter);
    if (exportFromDate) params.set('from_date', exportFromDate);
    if (exportToDate) params.set('to_date', exportToDate);
    try {
      const res = await fetch(`${API}/api/hr/expenses/travel/export?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        toast.error(`Export gagal (HTTP ${res.status}). Coba lagi atau hubungi admin.`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'travel-export.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Export berhasil. File terdownload.');
    } catch (e) {
      toast.error('Export gagal: ' + (e?.message || 'network error'));
    }
  };

  // Phase 4: Bulk approve
  const handleBulkApprove = async () => {
    if (!selectedIds.length) {
      toast.error('Pilih minimal 1 travel request untuk di-approve');
      return;
    }
    if (!window.confirm(`Approve ${selectedIds.length} travel request?`)) return;
    
    setBulkLoading(true);
    try {
      const res = await fetch(`${API}/api/hr/expenses/travel/bulk-approve`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ travel_ids: selectedIds, approval_note: 'Bulk approved from UI' })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`${data.success_count} travel request berhasil di-approve`);
        if (data.failed_count > 0) {
          toast.warning(`${data.failed_count} travel request gagal. Cek console.`);
          console.warn('Failed:', data.results.failed);
        }
        setSelectedIds([]);
        fetchData();
      } else {
        toast.error(data.detail || 'Gagal bulk approve');
      }
    } catch (err) {
      console.error(err);
      toast.error('Terjadi kesalahan');
    } finally {
      setBulkLoading(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const toggleSelectAll = () => {
    const eligibleIds = filteredReqs.map(r => r.id);
    setSelectedIds(prev => prev.length === eligibleIds.length ? [] : eligibleIds);
  };

  const filteredReqs = reqs.filter(r => {
    if (filter !== 'all' && r.status !== filter) return false;
    if (search && !r.trip_number?.toLowerCase().includes(search.toLowerCase()) && 
        !r.destination?.toLowerCase().includes(search.toLowerCase()) &&
        !r.employee_name?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const { page, setPage, totalPages, total, paged } = useClientPagination(reqs, 10);
  return (
    <div className="space-y-5" data-testid="employee-travel-page">
      <PageHeader
        icon={MapPin}
        eyebrow="SDM · Employee Expense Management"
        title="Perjalanan Dinas"
        subtitle="Request, tracking, dan kelola perjalanan dinas karyawan."
        actions={
          <div className="flex gap-2 items-center">
            {/* Phase 4: Export with date range */}
            <div className="flex gap-1 items-center border rounded-lg px-2 py-1">
              <Input type="date" value={exportFromDate} onChange={(e) => setExportFromDate(e.target.value)} className="h-7 w-32 text-xs" />
              <span className="text-xs text-muted-foreground">-</span>
              <Input type="date" value={exportToDate} onChange={(e) => setExportToDate(e.target.value)} className="h-7 w-32 text-xs" />
              <Button variant="ghost" size="sm" onClick={handleExport} className="h-7">
                <Download className="w-3.5 h-3.5 mr-1" />Export CSV
              </Button>
            </div>
            <Button variant="ghost" onClick={fetchData} className="h-9 border"><RefreshCw className="w-3.5 h-3.5" /></Button>
            <Button onClick={() => setShowCreate(true)} className="h-9" data-testid="btn-new-travel">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Request Baru
            </Button>
          </div>
        }
      />

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="Total Request Saya" value={summary.travel_requests?.total || 0} />
          <StatTile label="Menunggu Persetujuan" value={summary.travel_requests?.pending || 0} accent="warning" />
          <StatTile label="Dalam Proses" value={summary.travel_requests?.active || 0} accent="info" />
          <StatTile label="Total Request" value={reqs.length} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {isApprover && (
          <div className="flex rounded-lg border overflow-hidden">
            {['my','all'].map(m => (
              <button key={m} onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  viewMode === m ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                }`}>
                {m === 'my' ? 'Request Saya' : 'Semua Request'}
              </button>
            ))}
          </div>
        )}
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="h-8 w-48 text-sm">
            <Filter className="w-3.5 h-3.5 mr-1" /><SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Status</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="submitted">Menunggu Persetujuan</SelectItem>
            <SelectItem value="approved">Disetujui</SelectItem>
            <SelectItem value="advance_paid">Uang Muka Dibayar</SelectItem>
            <SelectItem value="completed">Selesai</SelectItem>
            <SelectItem value="rejected">Ditolak</SelectItem>
          </SelectContent>
        </Select>
        <Input placeholder="Cari destinasi / tujuan..." value={search} onChange={e => setSearch(e.target.value)} className="h-8 text-sm w-52" />
      </div>

      {/* Phase 4: Bulk Action Bar */}
      {selectedIds.length > 0 && (
        <div className="rounded-lg border bg-primary/5 p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">{selectedIds.length} travel request dipilih</span>
            <Button variant="outline" size="sm" onClick={() => setSelectedIds([])}>Clear Selection</Button>
          </div>
          {isApprover && (
            <Button size="sm" onClick={handleBulkApprove} disabled={bulkLoading} data-testid="bulk-approve-travel-btn">
              <CheckCircle className="w-3.5 h-3.5 mr-1" />Approve Selected
            </Button>
          )}
        </div>
      )}

      {/* List */}
      <div className="rounded-xl border overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-muted-foreground">
            <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
            Memuat data perjalanan dinas...
          </div>
        ) : reqs.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground">
            <MapPin className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="font-medium">Belum ada request perjalanan dinas</p>
            <p className="text-sm mt-1">Klik "Request Baru" untuk mengajukan perjalanan dinas.</p>
          </div>
        ) : (
          <>
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b">
              <tr>
                {isApprover && (
                  <th className="text-left p-3 w-12">
                    <Checkbox
                      checked={selectedIds.length === filteredReqs.length && filteredReqs.length > 0}
                      onCheckedChange={toggleSelectAll}
                      data-testid="select-all-travel-checkbox"
                    />
                  </th>
                )}
                <th className="text-left p-3 font-medium">Nomor / Destinasi</th>
                <th className="text-left p-3 font-medium">Karyawan</th>
                <th className="text-center p-3 font-medium">Tanggal</th>
                <th className="text-right p-3 font-medium">Budget</th>
                <th className="text-center p-3 font-medium">Status</th>
                <th className="text-center p-3 font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {paged.map(r => (
                <tr key={r.id} className="border-t hover:bg-muted/30 transition-colors">
                  {isApprover && (
                    <td className="p-3">
                      <Checkbox
                        checked={selectedIds.includes(r.id)}
                        onCheckedChange={() => toggleSelect(r.id)}
                        data-testid={`select-travel-${r.id}`}
                      />
                    </td>
                  )}
                  <td className="p-3">
                    <div className="font-mono text-xs text-muted-foreground">{r.trip_number}</div>
                    <div className="font-medium flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-muted-foreground" />{r.destination}
                    </div>
                    <div className="text-xs text-muted-foreground">{r.destination_label || r.destination_type}</div>
                  </td>
                  <td className="p-3">
                    <div className="font-medium">{r.employee_name}</div>
                    <div className="text-xs text-muted-foreground">{r.employee_dept}</div>
                  </td>
                  <td className="p-3 text-center">
                    <div className="text-xs">{fmtDate(r.start_date)}</div>
                    <div className="text-xs text-muted-foreground">s/d {fmtDate(r.end_date)}</div>
                    <div className="text-xs font-medium">{r.days_count} hari</div>
                  </td>
                  <td className="p-3 text-right">
                    <div className="font-bold">{fmt(r.total_budget)}</div>
                    {r.cash_advance_requested > 0 && (
                      <div className="text-xs text-muted-foreground">Muka: {fmt(r.cash_advance_requested)}</div>
                    )}
                  </td>
                  <td className="p-3 text-center"><StatusBadge status={r.status} /></td>
                  <td className="p-3 text-center">
                    <Button size="sm" variant="ghost" onClick={() => setSelected(r)} className="h-7">
                      <Eye className="w-3.5 h-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </>
        )}
      </div>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MapPin className="w-5 h-5 text-green-600" />Request Perjalanan Dinas Baru
            </DialogTitle>
          </DialogHeader>
          <TravelForm token={token} onClose={() => setShowCreate(false)} onSaved={(d) => { setShowCreate(false); fetchData(); setSelected(d); }} />
        </DialogContent>
      </Dialog>

      <Dialog open={!!selected} onOpenChange={v => !v && setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MapPin className="w-5 h-5 text-green-600" />
              {selected?.trip_number} — {selected?.destination}
            </DialogTitle>
          </DialogHeader>
          {selected && <TravelDetail req={selected} token={token} role={role} onClose={() => setSelected(null)} onRefresh={fetchData} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
