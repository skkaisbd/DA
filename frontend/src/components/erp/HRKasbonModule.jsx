/**
 * HRKasbonModule — HR Portal: Review Pengajuan Kasbon & Pinjaman
 * HR bisa lihat semua pengajuan, approve/reject, dan monitor overview.
 *
 * F13-B (sesi #12) — LAYAR UANG YANG TIDAK BISA DIBAWA KE RAPAT.
 * Antrian persetujuan kasbon dulu hanya bisa dibaca sebagai KARTU: tidak ada
 * tabel, tidak ada urutan, tidak ada halaman, tidak ada unduhan. Akibatnya
 * pertanyaan paling wajar HR — *"pengajuan mana yang paling besar dan paling
 * lama menunggu?"* — dijawab dengan menggulir kartu satu per satu. Angka ini
 * adalah UTANG KARYAWAN yang akan dipotong dari gaji; menyalinnya ulang dengan
 * tangan ke Excel adalah sumber salah-ketik yang paling mahal di modul ini.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import {
  CheckCircle2, XCircle, Clock, Users, DollarSign,
  RefreshCw, Search, Filter, X, Eye, FileText, AlertCircle,
  Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const HRKASBON_VIEW_KEY = 'hr_kasbon_view';
const CSV_HEAD = ['No. Pengajuan', 'Karyawan', 'Kode', 'Departemen', 'Jenis',
  'Keperluan', 'Status', 'Jumlah', 'Terbayar', 'Sisa', 'Cicilan/bulan',
  'Jml cicilan', 'Diajukan'];

const API = process.env.REACT_APP_BACKEND_URL;
const authH = () => ({ Authorization: `Bearer ${localStorage.getItem('erp_token')}`, 'Content-Type': 'application/json' });
const fmt = formatRupiah;
const fmtDate = (d) => { if (!d) return '-'; try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return d; } };

const STATUS_CFG = {
  submitted:   { label: 'Menunggu HR',     bg: 'bg-amber-100 dark:bg-amber-400/20',   text: 'text-amber-700 dark:text-amber-400' },
  hr_approved: { label: 'Disetujui HR',    bg: 'bg-blue-100 dark:bg-blue-400/20',     text: 'text-blue-700 dark:text-blue-400' },
  hr_rejected: { label: 'Ditolak HR',      bg: 'bg-red-100 dark:bg-red-400/20',       text: 'text-red-700 dark:text-red-400' },
  disbursed:   { label: 'Aktif/Dicairkan', bg: 'bg-emerald-100 dark:bg-emerald-400/20', text: 'text-emerald-700 dark:text-emerald-400' },
  paid_off:    { label: 'Lunas',           bg: 'bg-violet-100 dark:bg-violet-400/20', text: 'text-violet-700 dark:text-violet-400' },
  cancelled:   { label: 'Dibatalkan',      bg: 'bg-muted dark:bg-slate-400/20',   text: 'text-muted-foreground dark:text-slate-400' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.submitted;
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>{cfg.label}</span>;
}

// ─── Review Modal ─────────────────────────────────────────────────────────────
function ReviewModal({ req, onClose, onDone }) {
  const [action, setAction] = useState('approve');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/dewi/kasbon/requests/${req.id}/hr-review`, {
        method: 'PATCH', headers: authH(),
        body: JSON.stringify({ action, notes }),
      });
      const d = await r.json();
      if (d.ok) {
        toast.success(action === 'approve' ? 'Pengajuan disetujui' : 'Pengajuan ditolak');
        onDone();
      } else toast.error(d.detail || 'Gagal');
    } catch (_e) { toast.error('Terjadi kesalahan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-[var(--glass-border)] flex items-center justify-between">
          <h3 className="font-semibold">Review Pengajuan</h3>
          <button onClick={onClose}><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          {/* Applicant Info */}
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-1 text-xs">
            <div className="flex justify-between"><span className="text-muted-foreground">Karyawan</span><strong>{req.employee_name}</strong></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Departemen</span><span>{req.department || '-'}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Jenis</span><span>{req.type_label}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Jumlah</span><strong className="text-foreground">{fmt(req.amount)}</strong></div>
            {req.installment_count > 1 && <div className="flex justify-between"><span className="text-muted-foreground">Cicilan</span><span>{req.installment_count}x × {fmt(req.installment_amount)}</span></div>}
            <div className="flex justify-between"><span className="text-muted-foreground">Keperluan</span><span className="text-right max-w-[60%]">{req.purpose}</span></div>
            {req.documents?.length > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Dokumen</span><span>{req.documents.length} file</span></div>}
          </div>

          {/* Action */}
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => setAction('approve')}
              className={`p-3 rounded-xl border-2 flex items-center gap-2 transition-all ${action==='approve' ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10' : 'border-[var(--glass-border)]'}`}>
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              <span className="text-sm font-medium text-foreground">Setujui</span>
            </button>
            <button onClick={() => setAction('reject')}
              className={`p-3 rounded-xl border-2 flex items-center gap-2 transition-all ${action==='reject' ? 'border-red-500 bg-red-50 dark:bg-red-500/10' : 'border-[var(--glass-border)]'}`}>
              <XCircle className="w-4 h-4 text-red-500" />
              <span className="text-sm font-medium text-foreground">Tolak</span>
            </button>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">
              {action === 'reject' ? 'Alasan Penolakan *' : 'Catatan (opsional)'}
            </label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)}
              placeholder={action === 'reject' ? 'Jelaskan alasan penolakan...' : 'Tambahkan catatan...'}
              className="w-full h-16 px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm resize-none" />
          </div>
        </div>
        <div className="p-5 border-t border-[var(--glass-border)] flex gap-3">
          <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
          <button onClick={handleSubmit} disabled={saving || (action === 'reject' && !notes.trim())}
            className={`flex-1 h-10 rounded-xl text-sm font-semibold disabled:opacity-50 ${action==='approve' ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
            {saving ? 'Menyimpan...' : action === 'approve' ? 'Setujui' : 'Tolak'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Request Row ──────────────────────────────────────────────────────────────
function RequestRow({ req, onReview, onView }) {
  return (
    <div className="p-4 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] hover:bg-[var(--card-surface)] transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-mono text-muted-foreground">{req.request_number}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${req.type==='kasbon' ? 'bg-orange-100 dark:bg-orange-400/20 text-orange-700 dark:text-orange-400' : 'bg-blue-100 dark:bg-blue-400/20 text-blue-700 dark:text-blue-400'}`}>
              {req.type_label}
            </span>
            <StatusBadge status={req.status} />
          </div>
          <p className="text-sm font-semibold text-foreground">{req.employee_name}</p>
          <p className="text-xs text-muted-foreground">{req.department} · {req.purpose}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-sm font-bold text-foreground">{fmt(req.amount)}</p>
          <p className="text-xs text-muted-foreground">{fmtDate(req.created_at)}</p>
          {req.documents?.length > 0 && (
            <p className="text-xs text-blue-500 mt-0.5">{req.documents.length} dok.</p>
          )}
        </div>
      </div>
      {req.status === 'submitted' && (
        <div className="flex gap-2 mt-3">
          <button onClick={() => onReview(req)} data-testid={`hr-review-btn-${req.id}`}
            className="flex-1 h-8 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium">
            Review Pengajuan
          </button>
        </div>
      )}
      {req.hr_notes && (
        <p className="text-xs text-muted-foreground mt-2 italic">Catatan HR: {req.hr_notes}</p>
      )}
    </div>
  );
}

// ─── Main Module ──────────────────────────────────────────────────────────────
export default function HRKasbonModule() {
  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('submitted');
  const [search, setSearch] = useState('');
  const [reviewReq, setReviewReq] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rReqs, rStats] = await Promise.all([
        fetch(`${API}/api/dewi/kasbon/requests?limit=100`, { headers: authH() }),
        fetch(`${API}/api/dewi/kasbon/stats`, { headers: authH() }),
      ]);
      const [dReqs, dStats] = await Promise.all([rReqs.json(), rStats.json()]);
      if (dReqs.ok) setRequests(dReqs.requests || []);
      if (dStats.ok) setStats(dStats.stats || {});
    } catch (_e) { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSeed = async () => {
    const r = await fetch(`${API}/api/dewi/kasbon/seed`, { method: 'POST', headers: authH() });
    const d = await r.json();
    if (d.ok) { toast.success('Demo data berhasil dimuat'); load(); }
  };

  const filtered = requests.filter(r => {
    const matchStatus = !filterStatus || filterStatus === 'all' || r.status === filterStatus;
    const q = search.toLowerCase();
    const matchSearch = !q || r.employee_name?.toLowerCase().includes(q) || r.request_number?.toLowerCase().includes(q) || r.purpose?.toLowerCase().includes(q);
    return matchStatus && matchSearch;
  });

  // ── F13-B — tabel, urutan, halaman, unduhan ────────────────────────────────
  // Pilihan tampilan DIINGAT antar kunjungan: staf yang bekerja dengan tabel
  // tidak boleh disuruh mengklik ulang tiap membuka layar.
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(HRKASBON_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem(HRKASBON_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [sort, setSort] = useState({ key: 'amount', dir: 'desc' });

  // Yang diurutkan = yang TERLIHAT, dan yang diunduh = yang terlihat juga
  // (aturan `lib/csv.js`). Kueri ulang saat unduh melahirkan berkas yang tidak
  // sama dengan layar — dan yang dipercaya biasanya justru yang salah.
  const rows = useMemo(() => {
    const list = [...filtered];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = a?.[key], bv = b?.[key];
      const num = typeof av === 'number' || typeof bv === 'number';
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [filtered, sort]);
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 12);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const csvRows = rows.map((r) => [
    r.request_number, r.employee_name, r.employee_code || '', r.department || '',
    r.type_label || r.type || '', r.purpose || '',
    STATUS_CFG[r.status]?.label || r.status,
    r.amount ?? 0, r.paid_amount ?? 0, r.outstanding_balance ?? 0,
    r.installment_amount ?? 0, r.installment_count ?? 0,
    String(r.created_at || '').slice(0, 10),
  ]);

  const statCards = [
    { label: 'Menunggu Review HR', value: stats.pending_hr || 0, unit: 'pengajuan', icon: Clock, color: 'text-amber-500', urgent: (stats.pending_hr || 0) > 0 },
    { label: 'Menunggu Pencairan', value: stats.pending_finance || 0, unit: 'pengajuan', icon: DollarSign, color: 'text-blue-500' },
    { label: 'Aktif (Outstanding)', value: fmt(stats.total_outstanding || 0), unit: '', icon: Users, color: 'text-emerald-500' },
    { label: 'Bulan Ini', value: stats.this_month_requests || 0, unit: 'pengajuan', icon: FileText, color: 'text-violet-500' },
  ];

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Manajemen Kasbon & Pinjaman</h2>
          <p className="text-xs text-muted-foreground">Review pengajuan karyawan dan monitoring</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="w-9 h-9 rounded-xl border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={handleSeed} className="h-9 px-3 rounded-xl border border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground">
            Muat Demo
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {statCards.map((s, i) => (
          <div key={i} className={`p-4 rounded-2xl border ${s.urgent ? 'border-amber-500/40 bg-amber-50 dark:bg-amber-500/10' : 'border-[var(--glass-border)] bg-[var(--card-surface)]'}`}>
            <s.icon className={`w-5 h-5 mb-2 ${s.color}`} />
            <p className="text-lg font-bold text-foreground">{s.value} <span className="text-xs font-normal text-muted-foreground">{s.unit}</span></p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari karyawan, nomor, keperluan..."
            data-testid="hrkasbon-search"
            className="w-full h-9 pl-9 pr-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
        </div>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          data-testid="hrkasbon-filter-status"
          className="h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
          <option value="all">Semua Status</option>
          <option value="submitted">Menunggu HR</option>
          <option value="hr_approved">Disetujui HR</option>
          <option value="hr_rejected">Ditolak</option>
          <option value="disbursed">Aktif</option>
          <option value="paid_off">Lunas</option>
        </select>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-[var(--glass-border)] overflow-hidden">
            <button type="button" onClick={() => setView('table')} data-testid="hrkasbon-view-table"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <Table2 size={12} /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')} data-testid="hrkasbon-view-grid"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <LayoutGrid size={12} /> Kartu
            </button>
          </div>
          <ExportCsvButton filename="pengajuan-kasbon-hr" testId="hrkasbon-export-csv"
            head={CSV_HEAD} rows={csvRows}
            note={`Rp ${(rows.reduce((s, r) => s + Number(r.amount || 0), 0)).toLocaleString('id-ID')} diajukan`} />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 rounded-xl bg-[var(--glass-bg)] animate-pulse" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-muted-foreground text-sm">Tidak ada data</p>
        </div>
      ) : view === 'table' ? (
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--card-surface)]">
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="hrkasbon-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left">
                  {[['request_number', 'No. Pengajuan'], ['employee_name', 'Karyawan'],
                    ['employee_code', 'Kode'], ['department', 'Departemen'],
                    ['type_label', 'Jenis'], ['purpose', 'Keperluan'],
                    ['status', 'Status'], ['amount', 'Jumlah'],
                    ['outstanding_balance', 'Sisa'],
                    ['installment_amount', 'Cicilan/bulan'],
                    ['created_at', 'Diajukan']].map(([k, label]) => (
                    <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                      <button type="button" onClick={() => toggleSort(k)}
                        data-testid={`hrkasbon-sort-${k}`}
                        className="inline-flex items-center gap-1 hover:text-primary">
                        {label}
                        <ArrowUpDown size={10}
                          className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                      </button>
                    </th>
                  ))}
                  <th className="px-2.5 py-2 font-semibold text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]">
                    <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.request_number}</td>
                    <td className="px-2.5 py-2 font-medium">{r.employee_name}</td>
                    <td className="px-2.5 py-2 font-mono text-muted-foreground">{r.employee_code || '—'}</td>
                    <td className="px-2.5 py-2">{r.department || '—'}</td>
                    <td className="px-2.5 py-2">{r.type_label || r.type}</td>
                    <td className="px-2.5 py-2 max-w-[220px] truncate" title={r.purpose}>{r.purpose}</td>
                    <td className="px-2.5 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{fmt(r.amount)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{fmt(r.outstanding_balance || 0)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{r.installment_amount ? fmt(r.installment_amount) : '—'}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                    <td className="px-2.5 py-2 text-right">
                      {r.status === 'submitted' ? (
                        <button onClick={() => setReviewReq(r)} data-testid={`hr-review-btn-${r.id}`}
                          className="h-7 px-2.5 rounded-lg bg-[hsl(var(--primary))] text-primary-foreground text-[11px] font-medium">
                          Review
                        </button>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} className="px-3" />
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {paged.map(req => (
              <RequestRow key={req.id} req={req}
                onReview={setReviewReq}
                onView={() => {}}
              />
            ))}
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} />
        </>
      )}

      {reviewReq && (
        <ReviewModal req={reviewReq} onClose={() => setReviewReq(null)}
          onDone={() => { setReviewReq(null); load(); }} />
      )}
    </div>
  );
}
