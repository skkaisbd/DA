/**
 * FinanceKasbonModule — Finance Portal: Pencairan & Monitoring Kasbon/Pinjaman
 * Finance proses pencairan setelah HR approve, catat pembayaran, monitoring outstanding.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import {
  CheckCircle2, DollarSign, TrendingDown, Users,
  RefreshCw, Search, X, Wallet, Calendar,
  CreditCard, BarChart3, FileText, AlertCircle, Plus,
  Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

/* F13 (sesi #11) — layar UANG yang tidak bisa dibawa ke rapat.
   Kasbon & pinjaman karyawan dulu hanya bisa dibaca sebagai KARTU: tidak ada
   tabel, tidak ada urutan, tidak ada unduhan. Akibatnya pertanyaan paling wajar
   dari Keuangan — "siapa saja yang masih punya sisa, urut dari yang terbesar?" —
   dijawab dengan menggulir 200 kartu lalu MENGETIK ULANG angkanya ke Excel
   (sumber salah-ketik paling umum). Angka yang benar di layar tetapi tidak bisa
   dibawa keluar sama saja dengan tidak punya angka. */
const KASBON_VIEW_KEY = 'finance_kasbon_view';
const CSV_HEAD = ['No. Pengajuan', 'Karyawan', 'Departemen', 'Jenis', 'Keperluan',
  'Status', 'Jumlah', 'Terbayar', 'Sisa', 'Cicilan/bulan', 'Jml cicilan',
  'Mulai potong'];

const API = process.env.REACT_APP_BACKEND_URL;
const authH = () => ({ Authorization: `Bearer ${localStorage.getItem('erp_token')}`, 'Content-Type': 'application/json' });
const fmt = formatRupiah;
const fmtDate = (d) => { if (!d) return '-'; try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return d; } };

const STATUS_CFG = {
  submitted:   { label: 'Menunggu HR',     bg: 'bg-amber-100 dark:bg-amber-400/20',   text: 'text-amber-700 dark:text-amber-400' },
  hr_approved: { label: 'Siap Dicairkan',  bg: 'bg-blue-100 dark:bg-blue-400/20',     text: 'text-blue-700 dark:text-blue-400' },
  disbursed:   { label: 'Aktif',           bg: 'bg-emerald-100 dark:bg-emerald-400/20', text: 'text-emerald-700 dark:text-emerald-400' },
  paid_off:    { label: 'Lunas',           bg: 'bg-violet-100 dark:bg-violet-400/20', text: 'text-violet-700 dark:text-violet-400' },
  hr_rejected: { label: 'Ditolak HR',      bg: 'bg-red-100 dark:bg-red-400/20',       text: 'text-red-700 dark:text-red-400' },
  cancelled:   { label: 'Dibatalkan',      bg: 'bg-muted dark:bg-slate-400/20',   text: 'text-muted-foreground dark:text-slate-400' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.submitted;
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>{cfg.label}</span>;
}

// ─── Disburse Modal ───────────────────────────────────────────────────────────
function DisburseModal({ req, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const nowYM = new Date().toISOString().slice(0, 7);
  const [form, setForm] = useState({ disbursement_date: today, deduction_start_period: nowYM, finance_notes: '' });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/dewi/kasbon/requests/${req.id}/disburse`, {
        method: 'PATCH', headers: authH(), body: JSON.stringify(form),
      });
      const d = await r.json();
      if (d.ok) { toast.success('Kasbon berhasil dicairkan'); onDone(); }
      else toast.error(d.detail || 'Gagal');
    } catch (_e) { toast.error('Terjadi kesalahan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-[var(--glass-border)] flex items-center justify-between">
          <h3 className="font-semibold">Proses Pencairan</h3>
          <button onClick={onClose}><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          {/* Info */}
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-1 text-xs">
            <div className="flex justify-between"><span className="text-muted-foreground">Karyawan</span><strong>{req.employee_name}</strong></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Jenis</span><span>{req.type_label}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Jumlah</span><strong className="text-foreground text-sm">{fmt(req.amount)}</strong></div>
            {req.installment_count > 1 && <div className="flex justify-between"><span className="text-muted-foreground">Cicilan</span><span>{req.installment_count}x × {fmt(req.installment_amount)}/bulan</span></div>}
            <div className="flex justify-between"><span className="text-muted-foreground">Keperluan</span><span>{req.purpose}</span></div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Tanggal Pencairan</label>
            <input type="date" value={form.disbursement_date} onChange={e => setForm(p => ({...p, disbursement_date: e.target.value}))}
              className="w-full h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Mulai Potongan Gaji (Periode YYYY-MM)</label>
            <input type="month" value={form.deduction_start_period} onChange={e => setForm(p => ({...p, deduction_start_period: e.target.value}))}
              className="w-full h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            <p className="text-xs text-muted-foreground mt-1">Potongan gaji mulai periode ini</p>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan Finance</label>
            <textarea value={form.finance_notes} onChange={e => setForm(p => ({...p, finance_notes: e.target.value}))}
              placeholder="Nomor transfer, metode pencairan, dll..."
              className="w-full h-16 px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm resize-none" />
          </div>
        </div>
        <div className="p-5 border-t border-[var(--glass-border)] flex gap-3">
          <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
          <button onClick={handleSubmit} disabled={saving}
            className="flex-1 h-10 rounded-xl bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50">
            {saving ? 'Memproses...' : 'Cairkan Sekarang'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Repay Modal ──────────────────────────────────────────────────────────────
function RepayModal({ req, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const nowYM = new Date().toISOString().slice(0, 7);
  const suggested = req.type === 'kasbon' ? req.outstanding_balance : req.installment_amount;
  const [form, setForm] = useState({ amount: String(suggested || ''), method: 'payroll_deduction', date: today, period: nowYM, notes: '' });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!form.amount || Number(form.amount) <= 0) { toast.error('Jumlah harus > 0'); return; }
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/dewi/kasbon/requests/${req.id}/repay`, {
        method: 'POST', headers: authH(),
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      const d = await r.json();
      if (d.ok) { toast.success('Pembayaran berhasil dicatat'); onDone(); }
      else toast.error(d.detail || 'Gagal');
    } catch (_e) { toast.error('Terjadi kesalahan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-[var(--glass-border)] flex items-center justify-between">
          <h3 className="font-semibold">Catat Pembayaran</h3>
          <button onClick={onClose}><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-xs space-y-1">
            <div className="flex justify-between"><span className="text-muted-foreground">Karyawan</span><strong>{req.employee_name}</strong></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Saldo Outstanding</span><strong className="text-amber-600 dark:text-amber-400">{fmt(req.outstanding_balance)}</strong></div>
            {req.installment_amount > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Cicilan Bulanan</span><span>{fmt(req.installment_amount)}</span></div>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[['payroll_deduction','Potong Gaji'],['manual','Bayar Manual']].map(([v,l]) => (
              <button key={v} onClick={() => setForm(p => ({...p, method: v}))}
                className={`p-2.5 rounded-xl border-2 text-xs font-medium transition-all ${form.method===v ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.05)] text-foreground' : 'border-[var(--glass-border)] text-muted-foreground'}`}>
                {l}
              </button>
            ))}
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Jumlah Pembayaran</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">Rp</span>
              <input type="number" value={form.amount} onChange={e => setForm(p => ({...p, amount: e.target.value}))}
                className="w-full h-9 pl-10 pr-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Tanggal</label>
              <input type="date" value={form.date} onChange={e => setForm(p => ({...p, date: e.target.value}))}
                className="w-full h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Periode Gaji</label>
              <input type="month" value={form.period} onChange={e => setForm(p => ({...p, period: e.target.value}))}
                className="w-full h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan</label>
            <input value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
              placeholder="Referensi pembayaran, dll..."
              className="w-full h-9 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
          </div>
        </div>
        <div className="p-5 border-t border-[var(--glass-border)] flex gap-3">
          <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
          <button onClick={handleSubmit} disabled={saving || !form.amount}
            className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-semibold disabled:opacity-50">
            {saving ? 'Menyimpan...' : 'Catat Pembayaran'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Active Kasbon Row ─────────────────────────────────────────────────────────
function ActiveRow({ req, onRepay, onDisburse }) {
  const pct = req.amount > 0 ? Math.min(100, Math.round((req.paid_amount / req.amount) * 100)) : 0;

  return (
    <div className="p-4 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] hover:bg-[var(--card-surface)] transition-colors">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span className="text-xs font-mono text-muted-foreground">{req.request_number}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${req.type==='kasbon' ? 'bg-orange-100 dark:bg-orange-400/20 text-orange-700 dark:text-orange-400' : 'bg-blue-100 dark:bg-blue-400/20 text-blue-700 dark:text-blue-400'}`}>{req.type_label}</span>
            <StatusBadge status={req.status} />
          </div>
          <p className="text-sm font-semibold text-foreground">{req.employee_name}</p>
          <p className="text-xs text-muted-foreground">{req.department} · {req.purpose}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-sm font-bold text-foreground">{fmt(req.amount)}</p>
          <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">Sisa: {fmt(req.outstanding_balance)}</p>
        </div>
      </div>

      {req.status === 'disbursed' && (
        <>
          <div className="space-y-1 mb-3">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Terbayar: {fmt(req.paid_amount)}</span><span>{pct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-[var(--card-surface)] overflow-hidden">
              <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mb-3">
            <span>Mulai potong: {req.deduction_start_period}</span>
            {req.installment_count > 1 && <span>Cicilan: {fmt(req.installment_amount)}/bulan</span>}
          </div>
          <button onClick={() => onRepay(req)} data-testid={`repay-btn-${req.id}`}
            className="w-full h-8 rounded-lg border border-[hsl(var(--primary))] text-[hsl(var(--primary))] text-xs font-medium hover:bg-[hsl(var(--primary)/0.05)]">
            + Catat Pembayaran
          </button>
        </>
      )}

      {req.status === 'hr_approved' && (
        <button onClick={() => onDisburse(req)} data-testid={`disburse-btn-${req.id}`}
          className="w-full h-8 rounded-lg bg-emerald-500 text-white text-xs font-semibold mt-1">
          Proses Pencairan
        </button>
      )}
    </div>
  );
}

// ─── Main Module ──────────────────────────────────────────────────────────────
export default function FinanceKasbonModule() {
  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('pending');
  const [search, setSearch] = useState('');
  const [disburseReq, setDisburseReq] = useState(null);
  const [repayReq, setRepayReq] = useState(null);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(KASBON_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  // Urutan default: SISA terbesar di atas. Itu pertanyaan pertama Keuangan
  // ("siapa yang paling besar utangnya"), jadi tidak boleh perlu diklik dulu.
  const [sort, setSort] = useState({ key: 'outstanding_balance', dir: 'desc' });
  useEffect(() => {
    try { localStorage.setItem(KASBON_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rAll, rStats] = await Promise.all([
        fetch(`${API}/api/dewi/kasbon/requests?limit=200`, { headers: authH() }),
        fetch(`${API}/api/dewi/kasbon/stats`, { headers: authH() }),
      ]);
      const [dAll, dStats] = await Promise.all([rAll.json(), rStats.json()]);
      if (dAll.ok) setRequests(dAll.requests || []);
      if (dStats.ok) setStats(dStats.stats || {});
    } catch (_e) { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = requests.filter(r => {
    const matchTab = tab === 'pending' ? r.status === 'hr_approved'
      : tab === 'active' ? r.status === 'disbursed'
      : tab === 'done' ? ['paid_off', 'hr_rejected', 'cancelled'].includes(r.status)
      : true;
    const q = search.toLowerCase();
    const matchQ = !q || r.employee_name?.toLowerCase().includes(q) || r.request_number?.toLowerCase().includes(q);
    return matchTab && matchQ;
  });

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
    r.request_number, r.employee_name, r.department, r.type_label, r.purpose,
    STATUS_CFG[r.status]?.label || r.status, r.amount ?? 0, r.paid_amount ?? 0,
    r.outstanding_balance ?? 0, r.installment_amount ?? 0, r.installment_count ?? 0,
    r.deduction_start_period || '',
  ]);

  const statCards = [
    { label: 'Siap Dicairkan', value: stats.pending_finance || 0, unit: 'pengajuan', icon: DollarSign, color: 'text-blue-500', urgent: (stats.pending_finance||0) > 0 },
    { label: 'Kasbon Aktif', value: stats.active_count || 0, unit: 'karyawan', icon: Users, color: 'text-emerald-500' },
    { label: 'Total Outstanding', value: fmt(stats.total_outstanding || 0), unit: '', icon: Wallet, color: 'text-amber-500' },
    { label: 'Total Dicairkan', value: fmt(stats.total_disbursed_all || 0), unit: '', icon: BarChart3, color: 'text-violet-500' },
  ];

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Finance — Kasbon & Pinjaman</h2>
          <p className="text-xs text-muted-foreground">Proses pencairan dan monitoring pembayaran</p>
        </div>
        <button onClick={load} className="w-9 h-9 rounded-xl border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {statCards.map((s, i) => (
          <div key={i} className={`p-4 rounded-2xl border ${s.urgent ? 'border-blue-500/40 bg-blue-50 dark:bg-blue-500/10' : 'border-[var(--glass-border)] bg-[var(--card-surface)]'}`}>
            <s.icon className={`w-5 h-5 mb-2 ${s.color}`} />
            <p className="text-lg font-bold text-foreground">{s.value} <span className="text-xs font-normal text-muted-foreground">{s.unit}</span></p>
            <p className="text-xs text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Tabs + Search */}
      <div className="flex gap-2 flex-wrap">
        <div className="flex gap-1 p-1 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          {[['pending','Siap Cairkan'],['active','Aktif'],['done','Selesai'],['all','Semua']].map(([k,l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${tab===k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              {l}
              {k==='pending' && (stats.pending_finance||0) > 0 && (
                <span className="ml-1 px-1.5 rounded-full bg-blue-500 text-white text-[10px]">{stats.pending_finance}</span>
              )}
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari karyawan / no. pengajuan..."
            data-testid="kasbon-search"
            className="w-full h-9 pl-9 pr-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-[var(--glass-border)] overflow-hidden">
            <button type="button" onClick={() => setView('table')} data-testid="kasbon-view-table"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <Table2 size={12} /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')} data-testid="kasbon-view-grid"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <LayoutGrid size={12} /> Kartu
            </button>
          </div>
          <ExportCsvButton filename="kasbon-pinjaman-karyawan" testId="kasbon-export-csv"
            head={CSV_HEAD} rows={csvRows}
            note={`Rp ${(rows.reduce((s, r) => s + Number(r.outstanding_balance || 0), 0)).toLocaleString('id-ID')} sisa`} />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-28 rounded-xl bg-[var(--glass-bg)] animate-pulse" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-muted-foreground text-sm">{tab==='pending' ? 'Tidak ada pengajuan yang perlu dicairkan' : 'Tidak ada data'}</p>
        </div>
      ) : view === 'table' ? (
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--card-surface)]">
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="kasbon-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left">
                  {[['request_number', 'No. Pengajuan'], ['employee_name', 'Karyawan'],
                    ['department', 'Departemen'], ['type_label', 'Jenis'],
                    ['purpose', 'Keperluan'], ['status', 'Status'],
                    ['amount', 'Jumlah'], ['paid_amount', 'Terbayar'],
                    ['outstanding_balance', 'Sisa'],
                    ['installment_amount', 'Cicilan/bulan'],
                    ['deduction_start_period', 'Mulai potong']].map(([k, label]) => (
                    <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                      <button type="button" onClick={() => toggleSort(k)}
                        data-testid={`kasbon-sort-${k}`}
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
              <tbody className="divide-y divide-[var(--glass-border)]">
                {paged.map((r) => (
                  <tr key={r.id} className="hover:bg-[var(--glass-bg)]"
                    data-testid={`kasbon-row-${r.request_number}`}>
                    <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.request_number}</td>
                    <td className="px-2.5 py-2 font-medium">{r.employee_name}</td>
                    <td className="px-2.5 py-2 text-muted-foreground">{r.department || '—'}</td>
                    <td className="px-2.5 py-2">{r.type_label}</td>
                    <td className="px-2.5 py-2 text-muted-foreground max-w-[16rem] truncate"
                      title={r.purpose}>{r.purpose || '—'}</td>
                    <td className="px-2.5 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{fmt(r.amount)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{fmt(r.paid_amount)}</td>
                    <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap text-amber-600 dark:text-amber-400">
                      {fmt(r.outstanding_balance)}
                    </td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">
                      {r.installment_count > 1
                        ? `${fmt(r.installment_amount)} × ${r.installment_count}`
                        : '—'}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{r.deduction_start_period || '—'}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">
                      {r.status === 'hr_approved' && (
                        <button onClick={() => setDisburseReq(r)} data-testid={`disburse-btn-${r.id}`}
                          className="h-7 px-2 rounded-lg bg-emerald-500 text-white text-xs font-semibold">
                          Cairkan
                        </button>
                      )}
                      {r.status === 'disbursed' && (
                        <button onClick={() => setRepayReq(r)} data-testid={`repay-btn-${r.id}`}
                          className="h-7 px-2 rounded-lg border border-[hsl(var(--primary))] text-[hsl(var(--primary))] text-xs font-medium">
                          Catat bayar
                        </button>
                      )}
                      {!['hr_approved', 'disbursed'].includes(r.status) && (
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
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {paged.map(req => (
            <ActiveRow key={req.id} req={req} onDisburse={setDisburseReq} onRepay={setRepayReq} />
          ))}
        </div>
      )}
      {view === 'grid' && (
        <PaginationLite page={page} totalPages={totalPages} total={total}
          pageSize={pageSize} onPageChange={setPage} />
      )}

      {disburseReq && <DisburseModal req={disburseReq} onClose={() => setDisburseReq(null)} onDone={() => { setDisburseReq(null); load(); }} />}
      {repayReq && <RepayModal req={repayReq} onClose={() => setRepayReq(null)} onDone={() => { setRepayReq(null); load(); }} />}
    </div>
  );
}
