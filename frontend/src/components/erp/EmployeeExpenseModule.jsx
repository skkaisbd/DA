/**
 * Employee Expense Module — Klaim Biaya Karyawan (Reimbursement)
 * CV. Dewi Aditya — Employee Expense Management (EEM)
 *
 * Features:
 *  - Karyawan: submit klaim, upload receipt (base64), track status
 *  - Manager/HR: list semua klaim pending, approve/reject
 *  - Finance: disburse (bayar) + GL posting otomatis
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Plus, RefreshCw, Wallet, CheckCircle, XCircle,
  Clock, Send, Banknote, ChevronDown, ChevronUp,
  Trash2, FileText, Eye, Upload, AlertCircle, Filter, Download
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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

// Phase 4.5: kategori expense dimuat dinamis dari backend
// (`GET /api/hr/expenses/categories` → master `employee_expense_categories`,
//  fallback COA 6-3xxx, fallback konstanta backend).
// CATATAN BUG-FIX 2026-07-25: konstanta `CATEGORIES` lama dihapus saat refactor
// Phase 4.5 TAPI pemakaiannya di form klaim tidak pernah diganti ⇒ `ClaimForm`
// crash ReferenceError begitu dibuka (klaim biaya tidak bisa dibuat dari UI).
// Sekarang ClaimForm memuat sendiri kategorinya + fallback aman bila API kosong.
const CATEGORY_FALLBACK = [
  'Transportasi', 'Akomodasi', 'Konsumsi', 'Komunikasi',
  'Alat Tulis Kantor', 'Perjalanan Dinas', 'Lain-lain',
];

const STATUS_CONFIG = {
  draft:     { label: 'Draft',              color: 'bg-muted text-foreground',     icon: FileText },
  submitted: { label: 'Menunggu Persetujuan', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  approved:  { label: 'Disetujui',          color: 'bg-blue-100 text-blue-800',     icon: CheckCircle },
  rejected:  { label: 'Ditolak',            color: 'bg-red-100 text-red-800',       icon: XCircle },
  paid:      { label: 'Sudah Dibayar',      color: 'bg-green-100 text-green-800',   icon: Banknote },
  posted:    { label: 'Sudah Post GL',      color: 'bg-purple-100 text-purple-800', icon: CheckCircle },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || { label: status, color: 'bg-muted text-foreground' };
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>{c.label}</span>;
}

function ClaimForm({ token, onClose, onSaved }) {
  const [title, setTitle] = useState('');
  const [items, setItems] = useState([{ date: '', category: '', amount: '', notes: '', receipt_url: '' }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // SESI #27 — kolom nomor mengikuti kebijakan Otomatis/Manual milik owner.
  const numPolicy = useDocNumberPolicy('rahaza_expense_claims.claim_number', token);
  const [claimNumber, setClaimNumber] = useState('');
  // Kategori dinamis (master → COA → fallback). Dimuat sekali saat form dibuka.
  const [categories, setCategories] = useState(CATEGORY_FALLBACK.map(n => ({ code: n, name: n, label: n })));

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetch(`${API}/api/hr/expenses/categories`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!r.ok) return;
        const d = await r.json();
        const rows = Array.isArray(d?.categories) ? d.categories : [];
        if (alive && rows.length) setCategories(rows);
      } catch {
        /* biarkan fallback dipakai — form tetap bisa diisi */
      }
    })();
    return () => { alive = false; };
  }, [token]);

  const addItem = () => setItems(prev => [...prev, { date: '', category: '', amount: '', notes: '', receipt_url: '' }]);
  const removeItem = (i) => setItems(prev => prev.filter((_, idx) => idx !== i));
  const updateItem = (i, field, val) => setItems(prev => prev.map((it, idx) => idx === i ? { ...it, [field]: val } : it));

  const handleReceiptUpload = (i, file) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setError('Ukuran file maksimal 5MB'); return; }
    const reader = new FileReader();
    reader.onload = (e) => updateItem(i, 'receipt_url', e.target.result);
    reader.readAsDataURL(file);
  };

  const total = items.reduce((s, it) => s + (parseFloat(it.amount) || 0), 0);

  const handleSubmit = async () => {
    if (!title.trim()) { setError('Judul klaim wajib diisi'); return; }
    const validItems = items.filter(it => it.date && it.category && parseFloat(it.amount) > 0);
    if (!validItems.length) { setError('Minimal 1 item dengan tanggal, kategori, dan nominal'); return; }
    setSaving(true); setError('');
    try {
      const r = await fetch(`${API}/api/hr/expenses/claims`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          ...docNumberPayload(numPolicy, 'claim_number', claimNumber),
          items: validItems.map(it => ({ ...it, amount: parseFloat(it.amount) })),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal simpan');
      onSaved(d);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium mb-1 block">Judul Klaim *</label>
        <Input placeholder="mis: Biaya Perjalanan ke Surabaya" value={title} onChange={e => setTitle(e.target.value)}
          data-testid="claim-title" />
      </div>

      <DocNumberField
        policy={numPolicy} value={claimNumber} onChange={setClaimNumber}
        testId="claim-docnum" label="Nomor Klaim" />

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium">Item Klaim *</label>
          <Button size="sm" variant="outline" onClick={addItem}><Plus className="w-3.5 h-3.5 mr-1" />Tambah Item</Button>
        </div>
        <div className="space-y-3">
          {items.map((it, i) => (
            <div key={i} className="border rounded-lg p-3 space-y-2 bg-muted/30">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Tanggal</label>
                  <Input type="date" value={it.date} onChange={e => updateItem(i, 'date', e.target.value)}
                    data-testid={`claim-item-${i}-date`} className="h-8 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Kategori</label>
                  <Select value={it.category} onValueChange={v => updateItem(i, 'category', v)}>
                    <SelectTrigger className="h-8 text-sm" data-testid={`claim-item-${i}-category`}>
                      <SelectValue placeholder="Pilih" />
                    </SelectTrigger>
                    <SelectContent>{categories.map(c => (
                      <SelectItem key={c.code || c.name} value={c.name || c.code}
                        data-testid={`claim-item-${i}-category-option-${c.code || c.name}`}>
                        {c.label || c.name || c.code}
                      </SelectItem>
                    ))}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Nominal (Rp)</label>
                  <Input type="number" placeholder="0" value={it.amount} onChange={e => updateItem(i, 'amount', e.target.value)}
                    data-testid={`claim-item-${i}-amount`} className="h-8 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Keterangan</label>
                  <Input placeholder="Opsional" value={it.notes} onChange={e => updateItem(i, 'notes', e.target.value)}
                    data-testid={`claim-item-${i}-notes`} className="h-8 text-sm" />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground flex items-center gap-1 cursor-pointer">
                  <Upload className="w-3 h-3" />
                  <span>Foto Struk</span>
                  <input type="file" accept="image/*" className="hidden" onChange={e => handleReceiptUpload(i, e.target.files[0])} />
                </label>
                {it.receipt_url && <span className="text-xs text-green-600 font-medium">✓ Terupload</span>}
                {items.length > 1 && (
                  <Button size="sm" variant="ghost" className="ml-auto h-6 w-6 p-0 text-red-700 dark:text-red-500" onClick={() => removeItem(i)}><Trash2 className="w-3 h-3" /></Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50 dark:bg-blue-950">
        <span className="text-sm font-medium">Total Klaim</span>
        <span className="text-lg font-bold text-blue-700 dark:text-blue-300">{fmt(total)}</span>
      </div>

      {error && <div className="text-sm text-red-600 flex items-center gap-1"><AlertCircle className="w-4 h-4" />{error}</div>}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={handleSubmit} disabled={saving}>{saving ? 'Menyimpan...' : 'Simpan Draft'}</Button>
      </DialogFooter>
    </div>
  );
}

function ClaimDetail({ claim, token, onClose, onRefresh, role }) {
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);
  const [note, setNote] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const doAction = async (endpoint, body = {}) => {
    setActionLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/expenses/claims/${claim.id}/${endpoint}`, {
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
      <div className="grid grid-cols-2 gap-3">
        <div className="text-sm">
          <p className="text-muted-foreground text-xs">Nomor Klaim</p>
          <p className="font-mono font-bold">{claim.claim_number}</p>
        </div>
        <div className="text-sm">
          <p className="text-muted-foreground text-xs">Status</p>
          <StatusBadge status={claim.status} />
        </div>
        <div className="text-sm">
          <p className="text-muted-foreground text-xs">Karyawan</p>
          <p className="font-medium">{claim.employee_name}</p>
          <p className="text-xs text-muted-foreground">{claim.employee_dept}</p>
        </div>
        <div className="text-sm">
          <p className="text-muted-foreground text-xs">Total</p>
          <p className="font-bold text-lg text-blue-700 dark:text-blue-300">{fmt(claim.total_amount)}</p>
        </div>
      </div>

      <div>
        <p className="text-sm font-medium mb-2">Item Klaim ({(claim.items || []).length})</p>
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-2 text-xs font-medium">Tgl</th>
                <th className="text-left p-2 text-xs font-medium">Kategori</th>
                <th className="text-right p-2 text-xs font-medium">Nominal</th>
                <th className="text-left p-2 text-xs font-medium">Struk</th>
              </tr>
            </thead>
            <tbody>
              {(claim.items || []).map((it, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 text-xs">{it.date}</td>
                  <td className="p-2 text-xs">{it.category}</td>
                  <td className="p-2 text-xs text-right font-medium">{fmt(it.amount)}</td>
                  <td className="p-2">
                    {it.receipt_url ? (
                      <a href={it.receipt_url} target="_blank" rel="noreferrer" className="text-blue-600 text-xs hover:underline">Lihat</a>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {claim.reject_reason && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-3">
          <p className="text-sm font-medium text-red-700">Alasan Ditolak</p>
          <p className="text-sm text-red-600">{claim.reject_reason}</p>
        </div>
      )}
      {claim.gl_je_number && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3">
          <p className="text-sm font-medium text-green-700">GL Journal Entry</p>
          <p className="text-sm font-mono text-green-600">{claim.gl_je_number}</p>
          <p className="text-xs text-muted-foreground">Dibayar oleh {claim.paid_by_name} pada {fmtDate(claim.paid_at)}</p>
        </div>
      )}

      {showReject && (
        <div className="space-y-2">
          <Textarea
            placeholder="Alasan penolakan (wajib diisi)"
            value={rejectReason}
            onChange={e => setRejectReason(e.target.value)}
            rows={3}
          />
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

      <DialogFooter className="flex-wrap gap-2">
        <Button variant="outline" onClick={onClose}>Tutup</Button>
        {isApprover && claim.status === 'submitted' && !showReject && (
          <>
            <Button variant="destructive" size="sm" onClick={() => setShowReject(true)} disabled={actionLoading}>Tolak</Button>
            <div className="flex gap-2 items-center">
              <Input placeholder="Catatan (opsional)" className="h-8 text-sm w-40" value={note} onChange={e => setNote(e.target.value)} />
              <Button size="sm" onClick={() => doAction('approve', { note })} disabled={actionLoading}>
                <CheckCircle className="w-3.5 h-3.5 mr-1" />Setujui
              </Button>
            </div>
          </>
        )}
        {isFinance && claim.status === 'approved' && (
          <Button size="sm" className="bg-green-600 hover:bg-green-700 text-foreground"
            onClick={() => doAction('disburse', { payment_method: 'transfer' })} disabled={actionLoading}>
            <Banknote className="w-3.5 h-3.5 mr-1" />Bayar & Post GL
          </Button>
        )}
        {claim.status === 'draft' && (
          <Button size="sm" onClick={() => doAction('submit')} disabled={actionLoading}>
            <Send className="w-3.5 h-3.5 mr-1" />Submit
          </Button>
        )}
      </DialogFooter>
    </div>
  );
}

export default function EmployeeExpenseModule({ token, user }) {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState('my'); // 'my' | 'all'
  
  // Phase 4: Bulk & Export
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [exportFromDate, setExportFromDate] = useState('');
  const [exportToDate, setExportToDate] = useState('');
  
  // Phase 4.5: kategori COA-driven dimuat DI DALAM ClaimForm (lihat komentar
  // BUG-FIX di atas). State di level ini dulu dideklarasikan tapi tidak pernah
  // diisi maupun dipakai ⇒ dihapus supaya tidak menyesatkan.
  
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
      const [cr, sr] = await Promise.all([
        fetch(`${API}/api/hr/expenses/claims?${params}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/hr/expenses/my-summary`, { headers }).then(r => r.json()),
      ]);
      setClaims(Array.isArray(cr.items) ? cr.items : []);
      setSummary(sr);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token, filter, search, viewMode, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(); }, [fetchData]);

  // Phase 4: Export function — RC-23: toast sukses hanya bila backend OK (dulu fire-and-forget)
  const handleExport = async () => {
    const params = new URLSearchParams();
    if (filter !== 'all') params.set('status', filter);
    if (exportFromDate) params.set('from_date', exportFromDate);
    if (exportToDate) params.set('to_date', exportToDate);
    try {
      const res = await fetch(`${API}/api/hr/expenses/claims/export?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        toast.error(`Export gagal (HTTP ${res.status}). Coba lagi atau hubungi admin.`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'claims-export.csv';
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
      toast.error('Pilih minimal 1 klaim untuk di-approve');
      return;
    }
    if (!window.confirm(`Approve ${selectedIds.length} klaim?`)) return;
    
    setBulkLoading(true);
    try {
      const res = await fetch(`${API}/api/hr/expenses/claims/bulk-approve`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim_ids: selectedIds, approval_note: 'Bulk approved from UI' })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`${data.success_count} klaim berhasil di-approve`);
        if (data.failed_count > 0) {
          toast.warning(`${data.failed_count} klaim gagal. Cek console.`);
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
    const eligibleIds = filteredClaims.map(c => c.id);
    setSelectedIds(prev => prev.length === eligibleIds.length ? [] : eligibleIds);
  };

  const filteredClaims = claims.filter(c => {
    if (filter !== 'all' && c.status !== filter) return false;
    if (search && !c.claim_number?.toLowerCase().includes(search.toLowerCase()) && 
        !c.title?.toLowerCase().includes(search.toLowerCase()) &&
        !c.employee_name?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleClaimSaved = async (claim) => {
    setShowCreate(false);
    await fetchData();
    // Auto-select untuk detail view
    setSelected(claim);
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(claims, 10);
  return (
    <div className="space-y-5" data-testid="employee-expense-page">
      <PageHeader
        icon={Wallet}
        eyebrow="SDM · Employee Expense Management"
        title="Klaim Biaya Karyawan"
        subtitle="Submit, track, dan kelola klaim biaya & reimbursement."
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
            <Button onClick={() => setShowCreate(true)} className="h-9" data-testid="btn-new-claim">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Klaim Baru
            </Button>
          </div>
        }
      />

      {/* Summary Stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="Total Klaim Saya" value={summary.expense_claims?.total || 0} />
          <StatTile label="Menunggu Persetujuan" value={summary.expense_claims?.pending || 0} accent="warning" />
          <StatTile label="Sudah Disetujui" value={summary.expense_claims?.approved || 0} accent="success" />
          <StatTile label="Total Diklaim" value={fmt(summary.expense_claims?.total_claimed)} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {isApprover && (
          <div className="flex rounded-lg border overflow-hidden">
            {['my','all'].map(m => (
              <button key={m}
                onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  viewMode === m ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                }`}>
                {m === 'my' ? 'Klaim Saya' : 'Semua Klaim'}
              </button>
            ))}
          </div>
        )}
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="h-8 w-44 text-sm">
            <Filter className="w-3.5 h-3.5 mr-1" /><SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Status</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="submitted">Menunggu Persetujuan</SelectItem>
            <SelectItem value="approved">Disetujui</SelectItem>
            <SelectItem value="rejected">Ditolak</SelectItem>
            <SelectItem value="posted">Sudah Dibayar</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="Cari nomor / judul..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="h-8 text-sm w-52"
        />
      </div>

      {/* Phase 4: Bulk Action Bar */}
      {selectedIds.length > 0 && (
        <div className="rounded-lg border bg-primary/5 p-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">{selectedIds.length} klaim dipilih</span>
            <Button variant="outline" size="sm" onClick={() => setSelectedIds([])}>Clear Selection</Button>
          </div>
          {isApprover && (
            <Button size="sm" onClick={handleBulkApprove} disabled={bulkLoading} data-testid="bulk-approve-claims-btn">
              <CheckCircle className="w-3.5 h-3.5 mr-1" />Approve Selected
            </Button>
          )}
        </div>
      )}

      {/* Claims List */}
      <div className="rounded-xl border overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-muted-foreground">
            <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
            Memuat klaim...
          </div>
        ) : claims.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground">
            <Wallet className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="font-medium">Belum ada klaim biaya</p>
            <p className="text-sm mt-1">Klik "Klaim Baru" untuk submit reimbursement pertama Anda.</p>
          </div>
        ) : (
          <>
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b">
              <tr>
                {isApprover && (
                  <th className="text-left p-3 w-12">
                    <Checkbox
                      checked={selectedIds.length === filteredClaims.length && filteredClaims.length > 0}
                      onCheckedChange={toggleSelectAll}
                      data-testid="select-all-claims-checkbox"
                    />
                  </th>
                )}
                <th className="text-left p-3 font-medium">Nomor / Judul</th>
                <th className="text-left p-3 font-medium">Karyawan</th>
                <th className="text-right p-3 font-medium">Total</th>
                <th className="text-center p-3 font-medium">Item</th>
                <th className="text-center p-3 font-medium">Status</th>
                <th className="text-center p-3 font-medium">Tanggal</th>
                <th className="text-center p-3 font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {paged.map(c => (
                <tr key={c.id} className="border-t hover:bg-muted/30 transition-colors">
                  {isApprover && (
                    <td className="p-3">
                      <Checkbox
                        checked={selectedIds.includes(c.id)}
                        onCheckedChange={() => toggleSelect(c.id)}
                        data-testid={`select-claim-${c.id}`}
                      />
                    </td>
                  )}
                  <td className="p-3">
                    <div className="font-mono text-xs text-muted-foreground">{c.claim_number}</div>
                    <div className="font-medium">{c.title}</div>
                  </td>
                  <td className="p-3">
                    <div className="font-medium">{c.employee_name}</div>
                    <div className="text-xs text-muted-foreground">{c.employee_dept}</div>
                  </td>
                  <td className="p-3 text-right font-bold">{fmt(c.total_amount)}</td>
                  <td className="p-3 text-center">
                    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-muted text-xs font-bold">
                      {(c.items || []).length}
                    </span>
                  </td>
                  <td className="p-3 text-center"><StatusBadge status={c.status} /></td>
                  <td className="p-3 text-center text-xs text-muted-foreground">{fmtDate(c.created_at)}</td>
                  <td className="p-3 text-center">
                    <Button size="sm" variant="ghost" onClick={() => setSelected(c)} className="h-7">
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

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wallet className="w-5 h-5 text-blue-600" />Buat Klaim Biaya Baru
            </DialogTitle>
          </DialogHeader>
          <ClaimForm token={token} onClose={() => setShowCreate(false)} onSaved={handleClaimSaved} />
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={v => !v && setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wallet className="w-5 h-5 text-blue-600" />
              {selected?.claim_number} — {selected?.title}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <ClaimDetail
              claim={selected}
              token={token}
              role={role}
              onClose={() => setSelected(null)}
              onRefresh={fetchData}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
