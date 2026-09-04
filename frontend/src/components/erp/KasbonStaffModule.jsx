/**
 * KasbonStaffModule — Portal Saya: Pengajuan Kasbon & Pinjaman
 * Staff bisa ajukan kasbon/pinjaman, lihat status, dan riwayat cicilan.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import {
  Plus, FileText, Clock, CheckCircle2, XCircle, Wallet,
  Upload, X, ChevronDown, ChevronUp, RefreshCw, AlertCircle,
  Calendar, DollarSign, Paperclip, Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
// FASE G (sesi #18) — kolom nomor dokumen yang MENGIKUTI kebijakan Otomatis/Manual
// yang disetel System Admin. Tanpa ini layar & backend bisa berbeda pendapat.
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const KASBONSTAFF_VIEW_KEY = 'kasbon_staff_view';
const CSV_HEAD = ['No. Pengajuan', 'Jenis', 'Keperluan', 'Status', 'Jumlah',
  'Terbayar', 'Sisa', 'Cicilan/bulan', 'Jml cicilan', 'Mulai potong', 'Diajukan'];

const API = process.env.REACT_APP_BACKEND_URL;
const authH = () => ({ Authorization: `Bearer ${localStorage.getItem('erp_token')}`, 'Content-Type': 'application/json' });

const fmt = formatRupiah;
const fmtDate = (d) => { if (!d) return '-'; try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return d; } };

const STATUS_CFG = {
  submitted:   { label: 'Menunggu HR',     color: '#f59e0b', bg: 'bg-amber-100 dark:bg-amber-400/20',   text: 'text-amber-700 dark:text-amber-400' },
  hr_approved: { label: 'Disetujui HR',    color: '#3b82f6', bg: 'bg-blue-100 dark:bg-blue-400/20',     text: 'text-blue-700 dark:text-blue-400' },
  hr_rejected: { label: 'Ditolak HR',      color: '#ef4444', bg: 'bg-red-100 dark:bg-red-400/20',       text: 'text-red-700 dark:text-red-400' },
  disbursed:   { label: 'Aktif',           color: '#10b981', bg: 'bg-emerald-100 dark:bg-emerald-400/20', text: 'text-emerald-700 dark:text-emerald-400' },
  paid_off:    { label: 'Lunas',           color: '#6366f1', bg: 'bg-violet-100 dark:bg-violet-400/20', text: 'text-violet-700 dark:text-violet-400' },
  cancelled:   { label: 'Dibatalkan',      color: '#94a3b8', bg: 'bg-muted dark:bg-slate-400/20',   text: 'text-muted-foreground dark:text-slate-400' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.submitted;
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>{cfg.label}</span>;
}

function ProgressBar({ paid, total }) {
  const pct = total > 0 ? Math.min(100, Math.round((paid / total) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Terbayar: {fmt(paid)}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--glass-bg)] overflow-hidden">
        <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Request Card ─────────────────────────────────────────────────────────────
function RequestCard({ req, onRefresh }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--card-surface)] overflow-hidden">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-xs font-mono text-muted-foreground">{req.request_number}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${req.type === 'kasbon' ? 'bg-orange-100 dark:bg-orange-400/20 text-orange-700 dark:text-orange-400' : 'bg-blue-100 dark:bg-blue-400/20 text-blue-700 dark:text-blue-400'}`}>
                {req.type_label}
              </span>
              <StatusBadge status={req.status} />
            </div>
            <p className="text-sm font-semibold text-foreground">{fmt(req.amount)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{req.purpose}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-xs text-muted-foreground">{fmtDate(req.created_at)}</p>
            {req.status === 'disbursed' && (
              <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400 mt-0.5">Sisa: {fmt(req.outstanding_balance)}</p>
            )}
          </div>
        </div>

        {req.status === 'disbursed' && (
          <div className="mt-3">
            <ProgressBar paid={req.paid_amount} total={req.amount} />
          </div>
        )}

        {req.status === 'hr_rejected' && req.hr_notes && (
          <div className="mt-2 flex items-start gap-2 p-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
            <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-600 dark:text-red-400">Alasan penolakan: {req.hr_notes}</p>
          </div>
        )}

        <button onClick={() => setExpanded(p => !p)}
          className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {expanded ? 'Sembunyikan' : 'Detail & Riwayat'}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-[var(--glass-border)] p-4 space-y-3 bg-[var(--glass-bg)]">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div><span className="text-muted-foreground">Jenis</span><p className="font-medium">{req.type_label}</p></div>
            <div><span className="text-muted-foreground">Jumlah</span><p className="font-medium">{fmt(req.amount)}</p></div>
            <div><span className="text-muted-foreground">Cicilan</span><p className="font-medium">{req.installment_count}x × {fmt(req.installment_amount)}</p></div>
            {req.disbursement_date && <div><span className="text-muted-foreground">Tanggal Cair</span><p className="font-medium">{fmtDate(req.disbursement_date)}</p></div>}
            {req.deduction_start_period && <div><span className="text-muted-foreground">Mulai Potong</span><p className="font-medium">{req.deduction_start_period}</p></div>}
          </div>
          {req.repayments?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Riwayat Pembayaran</p>
              <div className="space-y-1.5">
                {req.repayments.map(r => (
                  <div key={r.id} className="flex items-center justify-between text-xs p-2 rounded-lg bg-[var(--card-surface)]">
                    <div>
                      <span className="font-medium text-foreground">{fmt(r.amount)}</span>
                      <span className="text-muted-foreground ml-2">· {r.method === 'payroll_deduction' ? 'Potong Gaji' : 'Manual'}</span>
                      {r.period && <span className="text-muted-foreground ml-1">· {r.period}</span>}
                    </div>
                    <span className="text-muted-foreground">{fmtDate(r.date)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Request Form ─────────────────────────────────────────────────────────────
function RequestForm({ onSuccess, onClose }) {
  const [form, setForm] = useState({
    type: 'kasbon', amount: '', purpose: '', notes: '', installment_count: 1,
    request_number: '',
  });
  // FASE G — kasbon & pinjaman adalah DUA jenis dokumen dengan kebijakan sendiri.
  const numPolicy = useDocNumberPolicy(
    form.type === 'kasbon'
      ? 'dewi_kasbon_requests.request_number'
      : 'dewi_kasbon_requests.request_number_pinjaman',
    localStorage.getItem('erp_token'),
  );
  const [docs, setDocs] = useState([]);
  const [saving, setSaving] = useState(false);

  const installmentAmt = form.amount && form.installment_count
    ? Math.ceil(Number(form.amount) / Number(form.installment_count))
    : 0;

  const handleFileAdd = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('Ukuran file maks 5MB'); return; }
    const reader = new FileReader();
    reader.onload = (ev) => {
      setDocs(p => [...p, { name: file.name, data: ev.target.result, mime_type: file.type }]);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleSubmit = async () => {
    if (!form.purpose.trim()) { toast.error('Keperluan harus diisi'); return; }
    if (!form.amount || Number(form.amount) <= 0) { toast.error('Jumlah harus lebih dari 0'); return; }
    // FASE G — mode MANUAL: nomor wajib diisi di layar, jangan biarkan backend
    // yang menolak setelah semua kolom lain diisi.
    if (numPolicy?.mode === 'manual' && !(form.request_number || '').trim()) {
      toast.error(`Nomor ${numPolicy.label} wajib diisi (pola ${numPolicy.format})`);
      return;
    }
    setSaving(true);
    try {
      const { request_number: _rn, ...rest } = form;
      const r = await fetch(`${API}/api/dewi/kasbon/requests`, {
        method: 'POST',
        headers: authH(),
        body: JSON.stringify({
          ...rest,
          amount: Number(form.amount),
          installment_count: Number(form.installment_count),
          documents: docs,
          // nomor HANYA dikirim bila kebijakannya manual (mode otomatis MENOLAK ketikan)
          ...docNumberPayload(numPolicy, 'request_number', form.request_number),
        }),
      });
      const d = await r.json();
      if (d.ok) { toast.success('Pengajuan berhasil dikirim'); onSuccess(); }
      else toast.error(d.detail || 'Gagal mengajukan');
    } catch (_e) { toast.error('Terjadi kesalahan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-[var(--glass-border)] flex items-center justify-between">
          <h3 className="font-semibold text-foreground">Ajukan Kasbon / Pinjaman</h3>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          {/* Type */}
          <div className="grid grid-cols-2 gap-3">
            {[['kasbon','Kasbon','Gaji dimuka, lunas 1x potong gaji'],['pinjaman','Pinjaman','Cicilan bulanan, auto-potong gaji']].map(([k,l,d]) => (
              <button key={k} onClick={() => setForm(p => ({...p, type: k, installment_count: k==='kasbon'?1:p.installment_count}))}
                className={`p-3 rounded-xl border-2 text-left transition-all ${form.type===k ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.05)]' : 'border-[var(--glass-border)] hover:border-[var(--glass-border)]'}`}>
                <p className="text-sm font-semibold text-foreground">{l}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{d}</p>
              </button>
            ))}
          </div>

          {/* FASE G (sesi #18) — nomor pengajuan mengikuti kebijakan Otomatis/Manual
              yang disetel System Admin. Kasbon & Pinjaman punya kebijakan sendiri. */}
          <DocNumberField
            policy={numPolicy}
            value={form.request_number}
            onChange={(v) => setForm(p => ({ ...p, request_number: v }))}
            testId="kasbon-docnum"
          />

          {/* Amount */}
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Jumlah yang Diminta *</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">Rp</span>
              <input type="number" min={0} value={form.amount} onChange={e => setForm(p => ({...p, amount: e.target.value}))}
                placeholder="1.000.000"
                className="w-full h-10 pl-10 pr-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
          </div>

          {/* Installment (pinjaman only) */}
          {form.type === 'pinjaman' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Jumlah Cicilan (Bulan) *</label>
              <div className="flex gap-2 flex-wrap">
                {[1,2,3,4,5,6,8,10,12].map(n => (
                  <button key={n} onClick={() => setForm(p => ({...p, installment_count: n}))}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${form.installment_count===n ? 'bg-[hsl(var(--primary))] text-foreground border-transparent' : 'border-[var(--glass-border)] text-muted-foreground hover:text-foreground'}`}>
                    {n}x
                  </button>
                ))}
              </div>
              {installmentAmt > 0 && (
                <p className="text-xs text-muted-foreground mt-1.5">Cicilan per bulan: <strong>{fmt(installmentAmt)}</strong> (dipotong dari gaji)</p>
              )}
            </div>
          )}

          {/* Purpose */}
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Keperluan / Tujuan *</label>
            <input value={form.purpose} onChange={e => setForm(p => ({...p, purpose: e.target.value}))}
              placeholder="Contoh: Biaya pengobatan, renovasi rumah, pendidikan..."
              className="w-full h-10 px-3 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
          </div>

          {/* Notes */}
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Keterangan Tambahan</label>
            <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
              placeholder="Tambahkan informasi lainnya jika diperlukan..."
              className="w-full h-16 px-3 py-2 rounded-xl border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm resize-none" />
          </div>

          {/* Document Upload */}
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Dokumen Pendukung</label>
            <label className="flex items-center gap-2 px-3 py-2 rounded-xl border border-dashed border-[var(--glass-border)] hover:border-[hsl(var(--primary))] cursor-pointer transition-colors">
              <Upload className="w-4 h-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Upload dokumen (PDF/JPG, maks 5MB)</span>
              <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={handleFileAdd} className="hidden" />
            </label>
            {docs.length > 0 && (
              <div className="mt-2 space-y-1">
                {docs.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs p-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                    <Paperclip className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate">{d.name}</span>
                    <button onClick={() => setDocs(p => p.filter((_,j) => j!==i))} className="text-muted-foreground hover:text-red-500"><X className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="p-5 border-t border-[var(--glass-border)] flex gap-3">
          <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
          <button onClick={handleSubmit} disabled={saving || !form.purpose.trim() || !form.amount}
            className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-semibold disabled:opacity-50">
            {saving ? 'Mengirim...' : 'Kirim Pengajuan'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Module ──────────────────────────────────────────────────────────────
export default function KasbonStaffModule() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [tab, setTab] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/kasbon/my-requests`, { headers: authH() });
      const d = await r.json();
      if (d.ok) setRequests(d.requests || []);
    } catch (_e) { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = tab === 'all' ? requests
    : tab === 'active' ? requests.filter(r => r.status === 'disbursed')
    : tab === 'pending' ? requests.filter(r => ['submitted','hr_approved'].includes(r.status))
    : requests.filter(r => ['paid_off','hr_rejected','cancelled'].includes(r.status));

  const activeAmt = requests.filter(r => r.status==='disbursed').reduce((s,r) => s + (r.outstanding_balance||0), 0);

  // ── F13-B (sesi #12) — riwayat kasbon SAYA harus bisa dibawa ──────────────
  // Kartu bagus untuk melihat satu pengajuan, tetapi karyawan juga perlu
  // menjawab "total yang sudah saya bayar berapa" dan sering diminta HR/Finance
  // mengirimkan riwayatnya. Tanpa tabel & unduhan, jawabannya adalah tangkapan
  // layar berkali-kali — bukti yang tidak bisa dijumlahkan.
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(KASBONSTAFF_VIEW_KEY) || 'grid'; } catch { return 'grid'; }
  });
  useEffect(() => {
    try { localStorage.setItem(KASBONSTAFF_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [sort, setSort] = useState({ key: 'created_at', dir: 'desc' });
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
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 10);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const csvRows = rows.map((r) => [
    r.request_number, r.type_label || r.type, r.purpose || '',
    STATUS_CFG[r.status]?.label || r.status,
    r.amount ?? 0, r.paid_amount ?? 0, r.outstanding_balance ?? 0,
    r.installment_amount ?? 0, r.installment_count ?? 0,
    r.deduction_start_period || '', String(r.created_at || '').slice(0, 10),
  ]);

  return (
    // Lebar wadah mengikuti tampilan: kartu tetap nyaman dibaca di kolom sempit,
    // tetapi tabel 11 kolom akan terpotong kalau dipaksa `max-w-2xl`.
    <div className={`p-4 space-y-4 mx-auto ${view === 'table' ? 'max-w-6xl' : 'max-w-2xl'}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Kasbon & Pinjaman Saya</h2>
          <p className="text-xs text-muted-foreground">Ajukan dan pantau status kasbon/pinjaman Anda</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="w-9 h-9 rounded-xl border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => setShowForm(true)}
            data-testid="kasbon-new-btn"
            className="flex items-center gap-2 h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium">
            <Plus className="w-4 h-4" /> Ajukan
          </button>
        </div>
      </div>

      {/* Summary Card */}
      {activeAmt > 0 && (
        <div className="p-4 rounded-2xl bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20">
          <div className="flex items-center gap-3">
            <Wallet className="w-8 h-8 text-amber-600 dark:text-amber-400 shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Total Saldo Kasbon/Pinjaman Aktif</p>
              <p className="text-xl font-bold text-foreground">{fmt(activeAmt)}</p>
              <p className="text-xs text-muted-foreground">akan dipotong dari gaji berikutnya</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
        {[['all','Semua'],['pending','Menunggu'],['active','Aktif'],['done','Selesai']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${tab===k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* Pengalih tampilan + unduh */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex rounded-lg border border-[var(--glass-border)] overflow-hidden">
          <button type="button" onClick={() => setView('table')} data-testid="kasbonstaff-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="kasbonstaff-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
        <ExportCsvButton filename="kasbon-saya" testId="kasbonstaff-export-csv"
          head={CSV_HEAD} rows={csvRows}
          note={`Rp ${(rows.reduce((s, r) => s + Number(r.outstanding_balance || 0), 0)).toLocaleString('id-ID')} sisa`} />
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-24 rounded-2xl bg-[var(--glass-bg)] animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-muted-foreground text-sm">Belum ada pengajuan</p>
          <button onClick={() => setShowForm(true)} className="mt-3 text-xs text-[hsl(var(--primary))] hover:underline">Buat pengajuan baru</button>
        </div>
      ) : view === 'table' ? (
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--card-surface)]">
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="kasbonstaff-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left">
                  {[['request_number', 'No. Pengajuan'], ['type_label', 'Jenis'],
                    ['purpose', 'Keperluan'], ['status', 'Status'],
                    ['amount', 'Jumlah'], ['paid_amount', 'Terbayar'],
                    ['outstanding_balance', 'Sisa'],
                    ['installment_amount', 'Cicilan/bulan'],
                    ['installment_count', 'Jml cicilan'],
                    ['deduction_start_period', 'Mulai potong'],
                    ['created_at', 'Diajukan']].map(([k, label]) => (
                    <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                      <button type="button" onClick={() => toggleSort(k)}
                        data-testid={`kasbonstaff-sort-${k}`}
                        className="inline-flex items-center gap-1 hover:text-primary">
                        {label}
                        <ArrowUpDown size={10}
                          className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]">
                    <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.request_number}</td>
                    <td className="px-2.5 py-2">{r.type_label || r.type}</td>
                    <td className="px-2.5 py-2 max-w-[220px] truncate" title={r.purpose}>{r.purpose}</td>
                    <td className="px-2.5 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{fmt(r.amount)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{fmt(r.paid_amount || 0)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap font-semibold">{fmt(r.outstanding_balance || 0)}</td>
                    <td className="px-2.5 py-2 text-right whitespace-nowrap">{r.installment_amount ? fmt(r.installment_amount) : '—'}</td>
                    <td className="px-2.5 py-2 text-right">{r.installment_count || '—'}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{r.deduction_start_period || '—'}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(r.created_at)}</td>
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
            {paged.map(req => <RequestCard key={req.id} req={req} onRefresh={load} />)}
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} />
        </>
      )}

      {showForm && <RequestForm onSuccess={() => { setShowForm(false); load(); }} onClose={() => setShowForm(false)} />}
    </div>
  );
}
