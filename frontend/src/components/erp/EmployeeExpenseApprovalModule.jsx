/**
 * Employee Expense Approval Module
 * CV. Dewi Aditya — Employee Expense Management (EEM)
 *
 * Unified approval inbox untuk:
 *  - Klaim Biaya (Reimbursement) — Manager/HR approve/reject → Finance disburse
 *  - Perjalanan Dinas — Manager/HR approve → Finance bayar uang muka
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  CheckCircle, XCircle, Clock, RefreshCw,
  Wallet, MapPin, Banknote, AlertCircle, Filter,
  Search, Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { PageHeader, StatTile } from './moduleAtoms';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

/* F13 (sesi #11) — inbox UANG yang tidak bisa disempitkan maupun dibawa keluar.
   Layar ini dulu hanya punya 3 tab jenis: TIDAK ADA kotak pencarian sama sekali,
   tidak ada tabel, tidak ada unduhan. Untuk inbox yang isinya bisa puluhan klaim,
   "cari klaim Pak Budi" berarti menggulir dengan mata; dan pertanyaan Keuangan
   "total yang menunggu dibayar bulan ini berapa?" tidak bisa dijawab tanpa
   menjumlah kartu satu per satu. */
const EXPENSE_VIEW_KEY = 'hr_expense_approval_view';
const CSV_HEAD = ['No. Referensi', 'Jenis', 'Judul', 'Karyawan', 'Departemen',
  'Diajukan', 'Status', 'Jumlah'];

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = formatRupiah;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('id-ID', { day:'2-digit', month:'short', year:'numeric' }) : '—';

function TypeBadge({ type }) {
  if (type === 'expense_claim') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"><Wallet className="w-3 h-3" />Klaim Biaya</span>;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800"><MapPin className="w-3 h-3" />Perjalanan Dinas</span>;
}

function StatusBadge({ status }) {
  const configs = {
    submitted: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-blue-100 text-blue-800',
    advance_paid: 'bg-teal-100 text-teal-800',
  };
  const labels = {
    submitted: 'Menunggu Persetujuan',
    approved: 'Disetujui — Menunggu Disbursement',
    advance_paid: 'Uang Muka Dibayar',
  };
  const c = configs[status] || 'bg-muted text-foreground';
  const l = labels[status] || status;
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c}`}>{l}</span>;
}

function ActionModal({ item, token, onClose, onRefresh }) {
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);
  const [note, setNote] = useState('');
  const [advanceAmount, setAdvanceAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const isClaim = item.type === 'expense_claim';
  const baseUrl = isClaim ? `${API}/api/hr/expenses/claims/${item.id}` : `${API}/api/hr/expenses/travel/${item.id}`;

  const doAction = async (endpoint, body = {}) => {
    setLoading(true);
    try {
      const r = await fetch(`${baseUrl}/${endpoint}`, {
        method: 'POST', headers, body: JSON.stringify(body),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Gagal'); }
      onRefresh(); onClose();
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      {/* Item Header */}
      <div className="rounded-lg bg-muted/50 p-4 space-y-3">
        <div className="flex items-start justify-between">
          <TypeBadge type={item.type} />
          <StatusBadge status={item.status} />
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Karyawan</p>
            <p className="font-medium">{item.employee_name}</p>
            <p className="text-xs text-muted-foreground">{item.employee_dept}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Nomor Referensi</p>
            <p className="font-mono font-bold text-xs">{item.ref_number}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs text-muted-foreground">{isClaim ? 'Judul Klaim' : 'Destinasi'}</p>
            <p className="font-medium">{item.title}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="text-lg font-bold">{fmt(item.amount)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Diajukan</p>
            <p>{fmtDate(item.submitted_at)}</p>
          </div>
        </div>
      </div>

      {/* Approve Section */}
      {item.status === 'submitted' && (
        <div className="space-y-3">
          {showReject ? (
            <div className="space-y-2">
              <label className="text-sm font-medium">Alasan Penolakan *</label>
              <Textarea
                placeholder="Jelaskan alasan penolakan..."
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                rows={3}
              />
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowReject(false)}>Batal</Button>
                <Button variant="destructive" size="sm"
                  disabled={!rejectReason.trim() || loading}
                  onClick={() => doAction('reject', { reason: rejectReason })}>
                  <XCircle className="w-3.5 h-3.5 mr-1" />Konfirmasi Tolak
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex gap-2">
                <Input
                  placeholder="Catatan persetujuan (opsional)"
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  className="text-sm"
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setShowReject(true)} disabled={loading}>
                  <XCircle className="w-3.5 h-3.5 mr-1" />Tolak
                </Button>
                <Button onClick={() => doAction('approve', { note, cash_advance_approved: item.amount })} disabled={loading}
                  className="bg-green-600 hover:bg-green-700 text-foreground">
                  <CheckCircle className="w-3.5 h-3.5 mr-1" />Setujui
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Finance Actions */}
      {!isClaim && item.status === 'approved' && (
        <div className="rounded-lg bg-teal-50 border border-teal-200 p-3 space-y-2">
          <p className="text-sm font-medium text-teal-800">Bayar Uang Muka Perjalanan Dinas</p>
          <div className="flex gap-2">
            <Input
              type="number"
              placeholder={`Jumlah (estimasi: ${fmt(item.amount)})`}
              value={advanceAmount}
              onChange={e => setAdvanceAmount(e.target.value)}
              className="text-sm h-8"
            />
            <Button size="sm" className="bg-teal-600 hover:bg-teal-700 text-foreground whitespace-nowrap"
              onClick={() => doAction('advance-paid', { amount_paid: parseFloat(advanceAmount) || item.amount })}
              disabled={loading}>
              <Banknote className="w-3.5 h-3.5 mr-1" />Bayar
            </Button>
          </div>
        </div>
      )}

      {isClaim && item.status === 'approved' && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3">
          <p className="text-sm font-medium text-green-800 mb-2">Disbursement Klaim Biaya</p>
          <Button className="bg-green-600 hover:bg-green-700 text-foreground" size="sm"
            onClick={() => doAction('disburse', { payment_method: 'transfer' })}
            disabled={loading}>
            <Banknote className="w-3.5 h-3.5 mr-1" />Bayar & Post GL
          </Button>
        </div>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Tutup</Button>
      </DialogFooter>
    </div>
  );
}

export default function EmployeeExpenseApprovalModule({ token, user }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all | expense_claim | travel_request
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(EXPENSE_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  // Default: yang PALING BESAR di atas. Inbox persetujuan uang dibaca dari
  // risiko terbesar, bukan dari urutan masuk.
  const [sort, setSort] = useState({ key: 'amount', dir: 'desc' });
  useEffect(() => {
    try { localStorage.setItem(EXPENSE_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const headers = { Authorization: `Bearer ${token}` };
  const role = user?.role || '';
  const isFinance = ['superadmin','admin','owner','finance'].includes(role.toLowerCase());

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [pr, sr] = await Promise.all([
        fetch(`${API}/api/hr/expenses/pending-approval`, { headers }).then(r => r.json()),
        fetch(`${API}/api/hr/expenses/summary`, { headers }).then(r => r.json()),
      ]);
      let allItems = Array.isArray(pr.items) ? pr.items : [];
      if (filter !== 'all') allItems = allItems.filter(i => i.type === filter);

      // Also include approved expense claims for finance disburse
      if (isFinance) {
        const approvedClaims = await fetch(`${API}/api/hr/expenses/claims?status=approved`, { headers }).then(r => r.json());
        const existing = new Set(allItems.map(i => i.id));
        (approvedClaims.items || []).forEach(c => {
          if (!existing.has(c.id)) {
            allItems.push({
              id: c.id, type: 'expense_claim', type_label: 'Klaim Biaya',
              ref_number: c.claim_number, employee_name: c.employee_name,
              employee_dept: c.employee_dept, title: c.title,
              amount: c.total_amount, status: 'approved',
              submitted_at: c.submitted_at,
            });
          }
        });
      }

      setItems(allItems);
      setSummary(sr);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token, filter, isFinance]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPending = (summary?.expense_claims?.total_pending_approval || 0) + (summary?.travel_requests?.total_pending_approval || 0);
  const pendingAdvance = summary?.travel_requests?.pending_advance || 0;

  // Menyempitkan + mengurutkan di layar, lalu MENGUNDUH YANG TERLIHAT
  // (aturan `lib/csv.js` — jangan kueri ulang saat unduh).
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = (items || []).filter((it) => !q || [
      it.ref_number, it.employee_name, it.employee_dept, it.title,
    ].some((v) => String(v || '').toLowerCase().includes(q)));
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = a?.[key], bv = b?.[key];
      const num = key === 'amount';
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [items, search, sort]);
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 12);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const sumVisible = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
  const csvRows = rows.map((r) => [
    r.ref_number, r.type_label || (r.type === 'expense_claim' ? 'Klaim Biaya' : 'Perjalanan Dinas'),
    r.title, r.employee_name, r.employee_dept, fmtDate(r.submitted_at), r.status,
    r.amount ?? 0,
  ]);

  return (
    <div className="space-y-5" data-testid="expense-approval-page">
      <PageHeader
        icon={CheckCircle}
        eyebrow="SDM / Finance · Employee Expense Management"
        title="Inbox Approval Klaim & Perjalanan"
        subtitle="Review dan proses persetujuan klaim biaya serta perjalanan dinas karyawan."
        actions={
          <Button variant="ghost" onClick={fetchData} className="h-9 border">
            <RefreshCw className="w-3.5 h-3.5 mr-1" />Muat Ulang
          </Button>
        }
      />

      {/* RC-IA-2a — klarifikasi pintu bersama HR/Keuangan */}
      <div className="px-3 py-2 rounded-lg bg-primary/5 border border-primary/15 text-xs text-muted-foreground">
        <strong className="text-foreground">Inbox bersama SDM &amp; Keuangan</strong> — layar yang sama dibuka dari dua portal. SDM menyetujui klaim, Keuangan melakukan pencairan (disbursement).
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Total Pending" value={totalPending} accent={totalPending > 0 ? 'warning' : 'default'} />
        <StatTile label="Klaim Menunggu" value={summary?.expense_claims?.total_pending_approval || 0} />
        <StatTile label="Dinas Menunggu" value={summary?.travel_requests?.total_pending_approval || 0} />
        <StatTile label="Menunggu Disbursement" value={pendingAdvance + (summary?.expense_claims?.counts?.approved || 0)} accent={pendingAdvance > 0 ? 'info' : 'default'} />
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex rounded-lg border overflow-hidden">
          {[['all','Semua'], ['expense_claim','Klaim Biaya'], ['travel_request','Perjalanan Dinas']].map(([v, l]) => (
            <button key={v} onClick={() => setFilter(v)}
              data-testid={`expense-filter-${v}`}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                filter === v ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
              }`}>
              {l}
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari no. referensi / karyawan / judul…"
            data-testid="expense-search"
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-border bg-card text-sm" />
        </div>
        <div className="inline-flex rounded-lg border overflow-hidden">
          <button type="button" onClick={() => setView('table')} data-testid="expense-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-card text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="expense-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-card text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
        <ExportCsvButton filename="inbox-approval-klaim-dinas" testId="expense-export-csv"
          head={CSV_HEAD} rows={csvRows}
          note={`total ${fmt(sumVisible)}`} />
        <span className="text-xs text-muted-foreground" data-testid="expense-visible-sum">
          {rows.length} item terlihat · total <strong className="text-foreground">{fmt(sumVisible)}</strong>
        </span>
      </div>

      {/* Items List */}
      <div className="space-y-3">
        {loading ? (
          <div className="p-12 text-center text-muted-foreground">
            <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
            Memuat data...
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border p-12 text-center text-muted-foreground">
            <CheckCircle className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="font-medium">Tidak ada item yang perlu diproses</p>
            <p className="text-sm mt-1">Semua klaim dan perjalanan dinas sudah diproses.</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border p-10 text-center text-muted-foreground"
            data-testid="expense-search-empty">
            <p className="font-medium">Tidak ada item yang cocok dengan pencarian «{search}»</p>
            <p className="text-sm mt-1">Kosongkan pencarian untuk melihat {items.length} item lagi.</p>
          </div>
        ) : view === 'table' ? (
          <div className="rounded-xl border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="expense-table">
                <thead className="bg-muted/60">
                  <tr className="text-left">
                    {[['ref_number', 'No. Referensi'], ['type_label', 'Jenis'],
                      ['title', 'Judul'], ['employee_name', 'Karyawan'],
                      ['employee_dept', 'Departemen'], ['submitted_at', 'Diajukan'],
                      ['status', 'Status'], ['amount', 'Jumlah']].map(([k, label]) => (
                      <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                        <button type="button" onClick={() => toggleSort(k)}
                          data-testid={`expense-sort-${k}`}
                          className="inline-flex items-center gap-1 hover:text-primary">
                          {label}
                          <ArrowUpDown size={10}
                            className={sort.key === k ? 'text-primary' : 'opacity-40'} />
                        </button>
                      </th>
                    ))}
                    <th className="px-2.5 py-2 font-semibold text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {paged.map((item) => (
                    <tr key={item.id} className="hover:bg-muted/40 cursor-pointer"
                      onClick={() => setSelected(item)}
                      data-testid={`expense-row-${item.ref_number}`}>
                      <td className="px-2.5 py-2 font-mono whitespace-nowrap">{item.ref_number}</td>
                      <td className="px-2.5 py-2"><TypeBadge type={item.type} /></td>
                      <td className="px-2.5 py-2 max-w-[18rem] truncate" title={item.title}>{item.title}</td>
                      <td className="px-2.5 py-2 font-medium whitespace-nowrap">{item.employee_name}</td>
                      <td className="px-2.5 py-2 text-muted-foreground whitespace-nowrap">{item.employee_dept || '—'}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(item.submitted_at)}</td>
                      <td className="px-2.5 py-2"><StatusBadge status={item.status} /></td>
                      <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{fmt(item.amount)}</td>
                      <td className="px-2.5 py-2 text-right whitespace-nowrap">
                        {item.status === 'submitted' && (
                          <Button size="sm" variant="outline" className="h-7 text-xs"
                            onClick={(e) => { e.stopPropagation(); setSelected(item); }}>
                            Proses
                          </Button>
                        )}
                        {(item.status === 'approved' && isFinance) && (
                          <Button size="sm" className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"
                            onClick={(e) => { e.stopPropagation(); setSelected(item); }}>
                            <Banknote className="w-3 h-3 mr-1" />Bayar
                          </Button>
                        )}
                        {!(item.status === 'submitted' || (item.status === 'approved' && isFinance)) && (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationLite page={page} totalPages={totalPages} total={total}
              pageSize={pageSize} onPageChange={setPage} className="px-3" />
          </div>
        ) : paged.map(item => (
          <div key={item.id}
            className="rounded-xl border bg-card p-4 hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => setSelected(item)}>
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                  item.type === 'expense_claim' ? 'bg-blue-100 dark:bg-blue-900' : 'bg-green-100 dark:bg-green-900'
                }`}>
                  {item.type === 'expense_claim'
                    ? <Wallet className="w-5 h-5 text-blue-600" />
                    : <MapPin className="w-5 h-5 text-green-600" />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <TypeBadge type={item.type} />
                    <StatusBadge status={item.status} />
                  </div>
                  <p className="font-medium mt-1">{item.title}</p>
                  <p className="text-sm text-muted-foreground">
                    {item.employee_name} · {item.employee_dept} · {fmtDate(item.submitted_at)}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold">{fmt(item.amount)}</p>
                <p className="text-xs font-mono text-muted-foreground">{item.ref_number}</p>
              </div>
            </div>
            <div className="mt-3 flex gap-2 justify-end">
              {item.status === 'submitted' && (
                <>
                  <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50"
                    onClick={e => { e.stopPropagation(); setSelected(item); }}>
                    <XCircle className="w-3.5 h-3.5 mr-1" />Tolak
                  </Button>
                  <Button size="sm" className="bg-green-600 hover:bg-green-700 text-foreground"
                    onClick={e => { e.stopPropagation(); setSelected(item); }}>
                    <CheckCircle className="w-3.5 h-3.5 mr-1" />Setujui
                  </Button>
                </>
              )}
              {(item.status === 'approved' && isFinance) && (
                <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-foreground"
                  onClick={e => { e.stopPropagation(); setSelected(item); }}>
                  <Banknote className="w-3.5 h-3.5 mr-1" />Proses Pembayaran
                </Button>
              )}
            </div>
          </div>
        ))}
        {view === 'grid' && rows.length > 0 && (
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} />
        )}
      </div>

      {/* Action Modal */}
      <Dialog open={!!selected} onOpenChange={v => !v && setSelected(null)}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              Proses {selected?.type === 'expense_claim' ? 'Klaim Biaya' : 'Perjalanan Dinas'}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <ActionModal
              item={selected}
              token={token}
              onClose={() => setSelected(null)}
              onRefresh={fetchData}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
