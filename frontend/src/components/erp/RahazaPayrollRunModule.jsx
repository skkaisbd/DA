import { useState, useEffect, useCallback, useReducer, useMemo } from 'react';
import { Plus, RefreshCw, Download, Eye, Lock, Calendar, DollarSign, AlertTriangle, CheckCircle, ShieldAlert, Copy, FileText, FilesIcon, BookOpen, ExternalLink, AlertCircle, X, CreditCard } from 'lucide-react';
import OnwardCTA from './OnwardCTA';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader, StatusBadge } from './moduleAtoms';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmtIDR = formatRupiah;

const _PR_INIT = { runs: [], loading: true };
function _prReducer(s, a) {
  if (a.type === 'loaded') return { ...s, runs: a.runs, loading: false };
  if (a.type === 'loading') return { ...s, loading: true };
  return s;
}

/** GL Posting Status Badge */
function GLStatusBadge({ run, onNavigate }) {
  if (!run.gl_je_number && !run.post_error) {
    if (run.status !== 'finalized') return null;
    return <span className="text-[10px] text-muted-foreground italic">Belum diposting</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      {/* Finalize JE */}
      {run.gl_je_number && (
        <span
          className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-400 dark:border-emerald-500/30 cursor-pointer hover:bg-emerald-100 dark:bg-emerald-500/20"
          title={`Journal Entry Finalisasi: ${run.gl_je_number}`}
          onClick={() => onNavigate && onNavigate('fin-journal-list')}
          data-testid={`gl-badge-${run.run_number}`}
        >
          <BookOpen size={9} /> {run.gl_je_number}
        </span>
      )}
      {/* Payment JE */}
      {run.payment_gl_je_number && (
        <span
          className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-400 dark:border-blue-500/30 cursor-pointer hover:bg-blue-100 dark:bg-blue-500/20"
          title={`Journal Entry Pembayaran: ${run.payment_gl_je_number}`}
          onClick={() => onNavigate && onNavigate('fin-journal-list')}
          data-testid={`pay-je-badge-${run.run_number}`}
        >
          💸 {run.payment_gl_je_number}
        </span>
      )}
      {run.post_error && !run.gl_je_number && (
        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-400 dark:border-red-500/30" title={run.post_error}>
          <AlertCircle size={9} /> Error GL
        </span>
      )}
    </div>
  );
}

/** Bank account options for payment dialog */
const BANK_OPTIONS = [
  { code: '1-1201', label: 'Bank BCA (1-1201)' },
  { code: '1-1202', label: 'Bank Mandiri (1-1202)' },
  { code: '1-1200', label: 'Bank Umum (1-1200)' },
  { code: '1-1102', label: 'Kas Besar (1-1102)' },
  { code: '1-1101', label: 'Kas Kecil (1-1101)' },
];

/* Return last month period as {from, to} strings */
function lastMonthPeriod() {
  const now = new Date();
  const firstOfThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastOfLastMonth = new Date(firstOfThisMonth - 1);
  const firstOfLastMonth = new Date(lastOfLastMonth.getFullYear(), lastOfLastMonth.getMonth(), 1);
  const fmt = (d) => d.toISOString().split('T')[0];
  return { from: fmt(firstOfLastMonth), to: fmt(lastOfLastMonth) };
}

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

/** Download a file from a URL with auth token (triggers native browser download).
 *  URL relatif otomatis diberi REACT_APP_BACKEND_URL (aturan environment repo). */
async function downloadWithAuth(url, token, filename) {
  const full = url.startsWith('http') ? url : `${API_BASE}${url}`;
  const r = await fetch(full, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href; a.download = filename; a.click();
  URL.revokeObjectURL(href);
}

export default function RahazaPayrollRunModule({ token, onNavigate }) {
  const [{ runs, loading }, dispatch] = useReducer(_prReducer, _PR_INIT);
  const [creating, setCreating] = useState(false);
  const [createInitial, setCreateInitial] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [error, setError] = useState('');
  const [payDialog, setPayDialog] = useState(null);
  const [payForm, setPayForm] = useState({
    payment_date: new Date().toISOString().slice(0, 10),
    bank_account_code: '1-1201',
    payment_method: 'bank_transfer',
    notes: '',
  });
  const [paying, setPaying] = useState(false);
  const [tick, setTick] = useState(0);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const refresh = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let x = false;
    dispatch({ type: 'loading' });
    const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
    fetch('/api/rahaza/payroll-runs', { headers: h })
      .then(r => r.json())
      .then(data => { if (!x) dispatch({ type: 'loaded', runs: Array.isArray(data) ? data : [] }); })
      .catch(() => { if (!x) dispatch({ type: 'loaded', runs: [] }); });
    return () => { x = true; };
  }, [token, tick]);

  const createRun = useCallback(async (payload) => {
    setError('');
    const r = await fetch('/api/rahaza/payroll-runs', { method: 'POST', headers, body: JSON.stringify(payload) });
    if (!r.ok) {
      const STATUS_MSG = { 400: 'Data tidak valid atau tidak ada profile aktif.', 403: 'Tidak ada akses.' };
      setError(STATUS_MSG[r.status] || `Gagal buat run (HTTP ${r.status})`);
      return;
    }
    setCreating(false);
    setCreateInitial(null);
    setTick(t => t + 1);
  }, [headers]);

  const finalizeRun = async (id) => {
    if (!window.confirm('Finalisasi penggajian? Setelah difinalisasi, potongan tidak bisa diubah lagi.')) return;
    const r = await fetch(`/api/rahaza/payroll-runs/${id}/finalize`, { method: 'POST', headers });
    if (r.ok) { toast.success('Run difinalisasi & jurnal GL dibuat'); refresh(); if (viewing?.run?.id === id) openRun(id); }
    else setError(`Gagal finalisasi penggajian (HTTP ${r.status})`);
  };

  const retryPost = async (id) => {
    try {
      const r = await fetch(`/api/rahaza/payroll-runs/${id}/retry-post`, { method: 'POST', headers });
      const d = await r.json();
      if (r.ok && d._posting_result?.ok) toast.success(`GL Posting berhasil: ${d._posting_result.je_number}`);
      else toast.error(d._posting_result?.error || 'Gagal posting ke GL');
      refresh();
    } catch { toast.error('Gagal retry posting'); }
  };

  const payGaji = async () => {
    if (!payDialog) return;
    setPaying(true);
    try {
      const r = await fetch(`/api/rahaza/payroll-runs/${payDialog.id}/pay`, {
        method: 'POST', headers, body: JSON.stringify(payForm),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      if (d._payment_result?.ok) {
        toast.success(`Gaji dibayar! Journal Entry: ${d.payment_gl_je_number}`);
      } else {
        toast.error(d._payment_result?.error || 'Pembayaran gagal');
      }
      setPayDialog(null);
      refresh();
    } catch (e) { toast.error(e.message); }
    finally { setPaying(false); }
  };

  const voidPayment = async (run) => {
    if (!window.confirm(`Batalkan pembayaran ${run.run_number}? Journal Entry pembayaran akan di-void.`)) return;
    try {
      const r = await fetch(`/api/rahaza/payroll-runs/${run.id}/void-payment`, {
        method: 'POST', headers, body: JSON.stringify({ reason: 'Void oleh admin' }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success('Pembayaran di-void');
      refresh();
    } catch (e) { toast.error(e.message); }
  };

  const payObligation = async (run, type) => {
    const label = type === 'bpjs' ? 'BPJS' : 'PPh21 ke DJP';
    const bankCode = prompt(`Kode akun bank untuk bayar ${label}:`, '1-1201');
    if (!bankCode) return;
    try {
      const r = await fetch(`/api/rahaza/payroll-runs/${run.id}/pay-${type}`, {
        method: 'POST', headers,
        body: JSON.stringify({
          payment_date: new Date().toISOString().slice(0, 10),
          bank_account_code: bankCode,
          notes: `Bayar ${label} ${run.run_number}`,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`${label} berhasil dibayar! JE: ${d._payment_result?.je_number || d[`${type}_payment_je`]}`);
      refresh();
    } catch (e) { toast.error(e.message); }
  };

  const delRun = async (id) => {
    if (!window.confirm('Hapus run ini? (hanya bisa jika masih draft)')) return;
    const r = await fetch(`/api/rahaza/payroll-runs/${id}`, { method: 'DELETE', headers });
    if (r.ok) refresh(); else setError(`Gagal hapus (HTTP ${r.status})`);
  };

  // FASE 20 — dulu `window.open('/api/rahaza/payroll-runs/{id}/export')`, dua bug
  // sekaligus: (1) endpoint-nya tidak terdaftar karena handler CSV-nya jadi kode
  // mati di dalam `export_run_excel()` (lihat backend), dan (2) `window.open`
  // TIDAK BISA mengirim header Authorization sehingga tetap 401 walau route ada.
  // Sekarang memakai pola `downloadWithAuth` yang sama dengan export Excel.
  const exportCsv = async (id, num) => {
    try {
      toast.info('Menyiapkan CSV...');
      await downloadWithAuth(
        `/api/rahaza/payroll-runs/${id}/export`,
        token,
        `payroll_${String(num || id).replace(/\//g, '-')}.csv`
      );
      toast.success('CSV berhasil diunduh.');
    } catch (e) { toast.error(`Gagal download CSV: ${e.message}`); }
  };

  const downloadRunExcel = async (id, num) => {
    try {
      toast.info('Menyiapkan Excel...');
      await downloadWithAuth(
        `/api/rahaza/payroll-runs/${id}/export-excel`,
        token,
        `payroll_${num}.xlsx`
      );
      toast.success('Excel berhasil diunduh.');
    } catch (e) { toast.error(`Gagal download Excel: ${e.message}`); }
  };

  const downloadRunPdf = async (id, num) => {
    try {
      toast.info('Menyiapkan PDF semua slip...');
      await downloadWithAuth(
        `/api/rahaza/payroll-runs/${id}/pdf`,
        token,
        `payroll_${num}_all_slips.pdf`
      );
      toast.success('PDF berhasil diunduh.');
    } catch (e) { toast.error(`Gagal download PDF: ${e.message}`); }
  };

  const openRun = async (id) => {
    const r = await fetch(`/api/rahaza/payroll-runs/${id}`, { headers });
    if (r.ok) setViewing(await r.json());
  };

  /* Salin Bulan Lalu — pre-fill modal dengan periode bulan lalu */
  const salinBulanLalu = () => {
    setCreateInitial(lastMonthPeriod());
    setCreating(true);
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(runs, 10);
  return (
    <div className="space-y-5" data-testid="rahaza-payroll-run-page">
      <PageHeader
        icon={DollarSign}
        eyebrow="Portal SDM · Penggajian"
        title="Proses Penggajian"
        subtitle="Jalankan penggajian per periode. Gunakan &quot;Salin Bulan Lalu&quot; untuk isi otomatis periode sebelumnya."
        actions={
          <>
            {/* Salin Bulan Lalu — 1-click period pre-fill */}
            <Button
              variant="ghost"
              onClick={salinBulanLalu}
              className="h-9 border border-[var(--glass-border)] gap-1.5"
              data-testid="pr-copy-last-month"
              title={`Buat run untuk periode bulan lalu (${lastMonthPeriod().from} → ${lastMonthPeriod().to})`}
            >
              <Copy className="w-3.5 h-3.5" />
              Salin Bulan Lalu
            </Button>
            <Button variant="ghost" onClick={refresh} className="h-9 border border-[var(--glass-border)]" data-testid="pr-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button onClick={() => { setCreateInitial(null); setCreating(true); }} className="h-9" data-testid="pr-create">
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Buat Penggajian Baru
            </Button>
          </>
        }
      />

      {/* RC-FLOW-UX Alur 6 — Payroll → Jurnal Gaji (GL) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'fin-journal-hub', label: 'Jurnal Gaji (GL)', icon: BookOpen, primary: true, hint: 'Lihat jurnal akuntansi hasil finalisasi penggajian' },
        ]}
      />

      {error && <div className="bg-[hsl(var(--destructive)/0.12)] border border-[hsl(var(--destructive)/0.22)] rounded-lg p-3 text-sm text-[hsl(var(--destructive))]">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center h-48"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>
      ) : (
        <GlassCard className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3">Run #</th>
                  <th className="px-3 py-3">Periode</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Karyawan</th>
                  <th className="px-3 py-3 text-right">Gross</th>
                  <th className="px-3 py-3 text-right">Potongan</th>
                  <th className="px-3 py-3 text-right">Net</th>
                  <th className="px-3 py-3">GL Jurnal</th>
                  <th className="px-3 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr><td colSpan={9} className="text-center py-12 text-muted-foreground">
                    Belum ada proses penggajian. Klik &quot;Buat Penggajian Baru&quot; atau &quot;Salin Bulan Lalu&quot; untuk memulai.
                  </td></tr>
                ) : paged.map(r => (
                  <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors" data-testid={`pr-row-${r.run_number}`}>
                    <td className="px-4 py-2 font-mono text-xs text-foreground">{r.run_number}</td>
                    <td className="px-3 py-2 text-xs text-foreground">{r.period_from} → {r.period_to}</td>
                    <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-3 py-2 text-right text-foreground">{r.total_employees}</td>
                    <td className="px-3 py-2 text-right font-mono text-foreground">{fmtIDR(r.total_gross)}</td>
                    <td className="px-3 py-2 text-right font-mono text-red-600 dark:text-red-300">{fmtIDR(r.total_deductions)}</td>
                    <td className="px-3 py-2 text-right font-mono text-emerald-600 dark:text-emerald-300 font-semibold">{fmtIDR(r.total_net)}</td>
                    {/* GL Posting Status */}
                    <td className="px-3 py-2">
                      <GLStatusBadge run={r} onNavigate={onNavigate} />
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <button onClick={() => openRun(r.id)} className="text-xs text-primary hover:underline mr-2" data-testid={`pr-view-${r.run_number}`} title="Lihat detail"><Eye className="w-3 h-3 inline" /></button>
                      <button onClick={() => exportCsv(r.id, r.run_number)} className="text-xs text-foreground/50 hover:text-foreground hover:underline mr-2" title="Download CSV"><Download className="w-3 h-3 inline" /></button>
                      <button
                        onClick={() => downloadRunExcel(r.id, r.run_number)}
                        className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline mr-2"
                        data-testid={`pr-excel-${r.run_number}`}
                        title="Download Excel (Rekapitulasi + Slip + Data Bank)"
                      >
                        <FileText className="w-3 h-3 inline" />
                      </button>
                      <button
                        onClick={() => downloadRunPdf(r.id, r.run_number)}
                        className="text-xs text-primary hover:underline mr-2"
                        data-testid={`pr-pdf-run-${r.run_number}`}
                        title="Download semua slip PDF"
                      >
                        <FilesIcon className="w-3 h-3 inline" />
                      </button>
                      {r.status === 'draft' && (
                        <>
                          <button onClick={() => finalizeRun(r.id)} className="text-xs text-emerald-600 dark:text-emerald-300 hover:underline mr-2" data-testid={`pr-finalize-${r.run_number}`} title="Finalisasi"><Lock className="w-3 h-3 inline" /></button>
                          <button onClick={() => delRun(r.id)} className="text-xs text-red-600 dark:text-red-300 hover:underline" title="Hapus"><RefreshCw className="w-3 h-3 inline" /></button>
                        </>
                      )}
                      {r.status === 'finalized' && r.post_error && (
                        <button onClick={() => retryPost(r.id)} className="text-xs text-amber-600 dark:text-amber-300 hover:underline" title="Retry GL Posting"><AlertTriangle className="w-3 h-3 inline" /></button>
                      )}
                      {/* Bayar Gaji — tampil jika sudah finalized + GL posted + belum dibayar */}
                      {r.status === 'finalized' && r.gl_je_number && r.payment_status !== 'paid' && (
                        <button
                          onClick={() => { setPayDialog(r); setPayForm(f => ({ ...f, payment_date: new Date().toISOString().slice(0,10) })); }}
                          className="text-xs text-blue-600 dark:text-blue-300 hover:underline ml-1"
                          title="Bayar Gaji (buat payment JE)"
                          data-testid={`pay-btn-${r.run_number}`}
                        >
                          💸
                        </button>
                      )}
                      {r.payment_status === 'paid' && (
                        <button
                          onClick={() => voidPayment(r)}
                          className="text-xs text-muted-foreground hover:underline ml-1"
                          title="Void pembayaran"
                          data-testid={`void-pay-btn-${r.run_number}`}
                        >
                          <X className="w-3 h-3 inline" />
                        </button>
                      )}
                      {/* BPJS + PPh21 payment buttons */}
                      {r.status === 'finalized' && r.gl_je_number && (
                        <>
                          {r.bpjs_payment_status !== 'paid' && (
                            <button
                              onClick={() => payObligation(r, 'bpjs')}
                              className="text-xs text-teal-600 dark:text-teal-300 hover:underline ml-1"
                              title="Bayar BPJS"
                              data-testid={`bpjs-btn-${r.run_number}`}
                            >B</button>
                          )}
                          {r.pph21_payment_status !== 'paid' && (
                            <button
                              onClick={() => payObligation(r, 'pph21')}
                              className="text-xs text-purple-600 dark:text-purple-300 hover:underline ml-1"
                              title="Bayar PPh21 ke DJP"
                              data-testid={`pph21-btn-${r.run_number}`}
                            >P</button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        </GlassCard>
      )}

      {creating && (
        <CreateRunModal
          onClose={() => { setCreating(false); setCreateInitial(null); }}
          onCreate={createRun}
          token={token}
          initial={createInitial}
        />
      )}
      {viewing && (
        <RunDetailModal
          data={viewing}
          token={token}
          onClose={() => setViewing(null)}
          onRefresh={() => openRun(viewing.run.id)}
          onDownloadExcel={downloadRunExcel}
        />
      )}

      {/* ── Payment Dialog ── */}
      <Dialog open={!!payDialog} onOpenChange={o => !o && setPayDialog(null)}>
        <DialogContent className="max-w-sm" data-testid="pay-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CreditCard size={16} className="text-blue-600 dark:text-blue-400" />
              Bayar Gaji — {payDialog?.run_number}
            </DialogTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Jurnal: Dr Hutang Gaji / Cr Bank
            </p>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            {payDialog && (
              <div className="rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-400 dark:border-blue-500/30 px-3 py-2 text-sm">
                <span className="text-muted-foreground">Total dibayar:</span>
                <span className="ml-2 font-bold text-blue-600 dark:text-blue-300">
                  Rp {Number(payDialog.total_net || 0).toLocaleString('id-ID')}
                </span>
              </div>
            )}
            <div>
              <Label className="text-xs">Tanggal Pembayaran</Label>
              <input type="date" className="mt-1 w-full h-9 rounded border border-border bg-background px-3 text-sm"
                value={payForm.payment_date}
                onChange={e => setPayForm(f => ({ ...f, payment_date: e.target.value }))}
                data-testid="pay-date" />
            </div>
            <div>
              <Label className="text-xs">Rekening / Kas</Label>
              <Select value={payForm.bank_account_code}
                onValueChange={v => setPayForm(f => ({ ...f, bank_account_code: v }))}>
                <SelectTrigger className="mt-1 h-9 text-sm" data-testid="pay-bank-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {BANK_OPTIONS.map(b => (
                    <SelectItem key={b.code} value={b.code}>{b.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Metode</Label>
              <Select value={payForm.payment_method}
                onValueChange={v => setPayForm(f => ({ ...f, payment_method: v }))}>
                <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="bank_transfer">Transfer Bank</SelectItem>
                  <SelectItem value="cash">Tunai</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Catatan (opsional)</Label>
              <GlassInput className="mt-1 h-9 text-sm" placeholder="Keterangan pembayaran..."
                value={payForm.notes}
                onChange={e => setPayForm(f => ({ ...f, notes: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPayDialog(null)}>Batal</Button>
            <Button
              onClick={payGaji}
              disabled={paying}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="pay-confirm-btn"
            >
              {paying ? '💸 Memproses...' : '💸 Bayar Gaji'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CreateRunModal({ onClose, onCreate, token, initial }) {
  const today = new Date().toISOString().split('T')[0];
  const defaultFrom = initial?.from || (today.slice(0, 7) + '-01');
  const defaultTo = initial?.to || today;
  const [from, setFrom] = useState(defaultFrom);
  const [to, setTo] = useState(defaultTo);
  const [notes, setNotes] = useState('');
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState(null);
  const [showValidation, setShowValidation] = useState(false);

  const headers = { Authorization: `Bearer ${token}` };

  const validateAttendance = async () => {
    setValidating(true);
    try {
      const r = await fetch(
        `/api/rahaza/hr/reports/attendance-validation?period_from=${from}&period_to=${to}`,
        { headers }
      );
      if (r.ok) { setValidation(await r.json()); setShowValidation(true); }
    } finally { setValidating(false); }
  };

  const sevColor = (sev) => sev === 'high'
    ? 'text-red-600 dark:text-red-300 border-red-300 dark:border-red-300/20 bg-red-400/8'
    : 'text-amber-600 dark:text-amber-300 border-amber-300 dark:border-amber-300/20 bg-amber-400/8';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/50 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-foreground">Buat Proses Penggajian Baru</h2>
          {initial && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">Periode bulan lalu</span>
          )}
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Periode Dari</label>
              <GlassInput type="date" value={from} onChange={e => { setFrom(e.target.value); setValidation(null); setShowValidation(false); }} data-testid="pr-create-from" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Periode Sampai</label>
              <GlassInput type="date" value={to} onChange={e => { setTo(e.target.value); setValidation(null); setShowValidation(false); }} data-testid="pr-create-to" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground uppercase block mb-1">Catatan</label>
            <GlassInput value={notes} onChange={e => setNotes(e.target.value)} placeholder="Opsional" />
          </div>

          {/* Attendance Validation */}
          <div className="border border-[var(--glass-border)] rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-foreground/70 uppercase flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5" /> Validasi Attendance (Opsional)
              </span>
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs border border-[var(--glass-border)]"
                onClick={validateAttendance} disabled={validating} data-testid="pr-validate-att">
                {validating ? 'Memeriksa...' : 'Periksa Sekarang'}
              </Button>
            </div>
            {!showValidation && (
              <p className="text-xs text-muted-foreground">Klik &quot;Periksa Sekarang&quot; untuk melihat potensi masalah attendance sebelum run payroll.</p>
            )}
            {showValidation && validation && (
              <div className="space-y-2" data-testid="pr-validation-result">
                {validation.summary.total_warnings === 0 ? (
                  <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-300 bg-emerald-400/8 border border-emerald-300 dark:border-emerald-300/20 rounded-lg p-2.5">
                    <CheckCircle className="w-4 h-4 shrink-0" />
                    <span>Attendance lengkap untuk semua {validation.summary.total_employees} karyawan. Siap run payroll.</span>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-300 bg-amber-400/8 border border-amber-300 dark:border-amber-300/20 rounded-lg p-2.5">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      <span><strong>{validation.summary.total_warnings}</strong> karyawan punya attendance tidak lengkap. Payroll tetap bisa dijalankan.</span>
                    </div>
                    <div className="max-h-40 overflow-y-auto space-y-1">
                      {validation.warnings.slice(0, 10).map(w => (
                        <div key={w.employee_id} className={`text-[11px] rounded p-2 border ${sevColor(w.severity)}`}>
                          <span className="font-semibold">{w.employee_name}</span>
                          <span className="ml-2 font-normal">{w.warning_message}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="bg-primary/10 border border-primary/20 rounded-lg p-3 text-xs text-foreground/80">
            <Calendar className="w-3.5 h-3.5 inline-block mr-1" />
            Run akan otomatis hitung slip untuk semua karyawan dengan profile payroll aktif.
          </div>
        </div>
        <div className="flex gap-2 mt-6 justify-end">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button>
          <Button onClick={() => onCreate({ period_from: from, period_to: to, notes })} data-testid="pr-create-submit">Buat Run</Button>
        </div>
      </GlassCard>
    </div>
  );
}

function RunDetailModal({ data, token, onClose, onRefresh, onDownloadExcel }) {
  const run = data.run;
  const payslips = data.payslips || [];
  const locked = run.status !== 'draft';
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const [dlSlipId, setDlSlipId] = useState(null);
  const [dlAllLoading, setDlAllLoading] = useState(false);

  const saveAdjustment = async (slipId, deduction, notes) => {
    // FASE 20 — dulu hasil `fetch` TIDAK diperiksa sama sekali, jadi ketika
    // endpoint-nya belum ada (404) UI tetap memanggil `onRefresh()` dan tampak
    // "berhasil" padahal tidak ada yang tersimpan. Sekarang error dimunculkan.
    try {
      const r = await fetch(`/api/rahaza/payroll-runs/${run.id}/payslips/${slipId}/adjust`, {
        method: 'POST', headers, body: JSON.stringify({ deduction, notes }),
      });
      if (!r.ok) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch { /* noop */ }
        throw new Error(detail || `HTTP ${r.status}`);
      }
      toast.success('Penyesuaian tersimpan.');
      onRefresh();
    } catch (e) {
      toast.error(`Gagal menyimpan penyesuaian: ${e.message}`);
    }
  };

  const downloadSlipPdf = async (slip) => {
    setDlSlipId(slip.id);
    try {
      await downloadWithAuth(
        `/api/rahaza/payslips/${slip.id}/pdf`,
        token,
        `slip_${slip.employee_code}_${slip.period_from}_${slip.period_to}.pdf`
      );
      toast.success(`Slip ${slip.employee_code} berhasil diunduh.`);
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    } finally { setDlSlipId(null); }
  };

  const downloadAllPdf = async () => {
    setDlAllLoading(true);
    try {
      toast.info('Menyiapkan PDF semua slip gaji...');
      await downloadWithAuth(
        `/api/rahaza/payroll-runs/${run.id}/pdf`,
        token,
        `payroll_${run.run_number}_all_slips.pdf`
      );
      toast.success('PDF semua slip berhasil diunduh.');
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    } finally { setDlAllLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/50 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-5xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-xl font-bold text-foreground">{run.run_number}</h2>
            <p className="text-xs text-muted-foreground">{run.period_from} → {run.period_to} · Status: <span className={run.status === 'finalized' ? 'text-emerald-600 dark:text-emerald-300' : 'text-amber-600 dark:text-amber-300'}>{run.status}</span></p>
          </div>
          {/* PDF & Excel download actions */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => onDownloadExcel(run.id, run.run_number)}
              className="h-8 px-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 transition-colors flex items-center gap-1.5 text-xs font-semibold"
              data-testid="pr-download-excel"
              title="Download Excel: Rekapitulasi + Slip Individual + Data Transfer Bank"
            >
              <FileText className="w-3.5 h-3.5" />
              Export Excel
            </button>
            <button
              onClick={downloadAllPdf}
              disabled={dlAllLoading}
              className="h-8 px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors flex items-center gap-1.5 text-xs font-semibold disabled:opacity-50"
              data-testid="pr-download-all-pdf"
              title="Download PDF semua slip gaji dalam satu file"
            >
              {dlAllLoading
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <FilesIcon className="w-3.5 h-3.5" />}
              {dlAllLoading ? 'Menyiapkan...' : 'Download Semua Slip PDF'}
            </button>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-2xl leading-none">×</button>
          </div>
        </div>

        {/* Summary tiles */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          <GlassPanel className="px-3 py-2"><div className="text-[10px] uppercase text-muted-foreground">Total Kotor</div><div className="text-lg font-bold text-foreground">{fmtIDR(run.total_gross)}</div></GlassPanel>
          <GlassPanel className="px-3 py-2"><div className="text-[10px] uppercase text-muted-foreground">Potongan</div><div className="text-lg font-bold text-red-600 dark:text-red-300">{fmtIDR(run.total_deductions)}</div></GlassPanel>
          <GlassPanel className="px-3 py-2"><div className="text-[10px] uppercase text-muted-foreground">Net</div><div className="text-lg font-bold text-emerald-600 dark:text-emerald-300">{fmtIDR(run.total_net)}</div></GlassPanel>
        </div>

        {/* Payslips table
            FASE 20 — kolom di sini DULU membaca skema payslip LAMA
            (`base_salary`, `transport_allowance`, `meal_allowance`,
            `production_bonus`, `overtime_pay`, `total_deductions`, `net_salary`).
            TIDAK SATU PUN field itu dihasilkan `_compute_payslip_for_employee()`,
            yang menulis `earnings_total`, `allowance_total`, `overtime_amount`,
            `gross_pay`, `deductions_total`, `net_pay`. Akibatnya SELURUH kolom
            uang menampilkan "Rp 0" padahal total run benar (kelas bug yang sama
            dengan 404 senyap: HTTP 200, tapi layar bohong).
            `Transport`/`Bonus Prod.` dihapus karena backend tidak memisahkannya —
            semuanya masuk `allowances[]`; menampilkan kolom yang mustahil terisi
            hanya membuat pengguna menduga datanya hilang.
            Fallback ke nama lama dipertahankan (backend sendiri melakukannya,
            mis. `slip.get("net_pay", slip.get("net_salary", 0))`) supaya payslip
            lama di DB produksi tetap tampil. */}
        <table className="w-full text-sm">
          <thead className="bg-[var(--glass-bg)]">
            <tr className="text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Karyawan</th>
              <th className="px-3 py-2 text-right">Upah</th>
              <th className="px-3 py-2 text-right">Tunjangan</th>
              <th className="px-3 py-2 text-right">Lembur</th>
              <th className="px-3 py-2 text-right">Bruto</th>
              <th className="px-3 py-2 text-right">Potongan</th>
              <th className="px-3 py-2 text-right font-semibold text-foreground">Net</th>
              <th className="px-3 py-2 text-center">Slip</th>
              {!locked && <th className="px-3 py-2">Adj.</th>}
            </tr>
          </thead>
          <tbody>
            {payslips.map(s => (
              <tr key={s.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors" data-testid={`slip-${s.employee_code}`}>
                <td className="px-3 py-2">
                  <div className="font-semibold text-xs">{s.employee_name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono">{s.employee_code}</div>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(s.earnings_total ?? s.base_salary)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(s.allowance_total ?? s.meal_allowance)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(s.overtime_amount ?? s.overtime_pay)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{fmtIDR(s.gross_pay)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs text-red-600 dark:text-red-300">{fmtIDR(s.deductions_total ?? s.total_deductions)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs font-bold text-emerald-600 dark:text-emerald-300">{fmtIDR(s.net_pay ?? s.net_salary)}</td>
                {/* Per-slip PDF download */}
                <td className="px-3 py-2 text-center">
                  <button
                    onClick={() => downloadSlipPdf(s)}
                    disabled={dlSlipId === s.id}
                    className="h-7 w-7 rounded border border-primary/20 bg-primary/8 text-primary hover:bg-primary/20 transition-colors grid place-items-center disabled:opacity-50"
                    data-testid={`pr-pdf-slip-${s.employee_code}`}
                    title={`Download slip PDF ${s.employee_name}`}
                  >
                    {dlSlipId === s.id
                      ? <RefreshCw className="w-3 h-3 animate-spin" />
                      : <FileText className="w-3 h-3" />}
                  </button>
                </td>
                {!locked && (
                  <td className="px-3 py-2">
                    <AdjustCell slipId={s.id} current={s.manual_deduction || 0} notes={s.adjustment_notes || ''} onSave={saveAdjustment} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex justify-between items-center gap-2 mt-4">
          <p className="text-xs text-muted-foreground">{payslips.length} slip gaji · Klik <FileText className="w-3 h-3 inline" /> untuk unduh per karyawan, atau <FilesIcon className="w-3 h-3 inline" /> untuk semua.</p>
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Tutup</Button>
        </div>
      </GlassCard>
    </div>
  );
}

function AdjustCell({ slipId, current, notes, onSave }) {
  const [open, setOpen] = useState(false);
  const [val, setVal] = useState(current);
  const [n, setN] = useState(notes);
  const [busy, setBusy] = useState(false);

  // FASE 20 — `setN` sebelumnya tak pernah dipakai: kolom catatan dikirim ke
  // backend tapi TIDAK BISA diisi user. Karena backend kini benar-benar menyimpan
  // `adjustment_notes` (dan ikut di export CSV), inputnya dimunculkan.
  if (!open) return (
    <button
      onClick={() => { setVal(current); setN(notes); setOpen(true); }}
      className="text-xs text-primary hover:underline"
      title={notes ? `Catatan: ${notes}` : 'Penyesuaian manual'}
      data-testid={`payslip-adjust-open-${slipId}`}
    >
      {Number(current) > 0 ? `Adj: ${Number(current).toLocaleString('id-ID')}` : 'Adj'}
    </button>
  );
  const submit = async () => {
    setBusy(true);
    try { await onSave(slipId, val, n); setOpen(false); } finally { setBusy(false); }
  };
  return (
    <div className="flex items-center gap-1">
      <input
        type="number" min="0" value={val}
        onChange={e => setVal(Number(e.target.value))}
        placeholder="Potongan"
        className="w-24 h-7 px-2 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs font-mono"
        data-testid={`payslip-adjust-amount-${slipId}`}
      />
      <input
        type="text" value={n}
        onChange={e => setN(e.target.value)}
        placeholder="Catatan"
        className="w-32 h-7 px-2 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs"
        data-testid={`payslip-adjust-notes-${slipId}`}
      />
      <button
        onClick={submit} disabled={busy}
        className="text-xs px-2 h-7 rounded border border-emerald-400 dark:border-emerald-400/30 bg-emerald-50 dark:bg-emerald-400/10 text-emerald-600 dark:text-emerald-400 disabled:opacity-50"
        data-testid={`payslip-adjust-save-${slipId}`}
      >{busy ? '…' : '✓'}</button>
      <button
        onClick={() => setOpen(false)} disabled={busy}
        className="text-xs px-2 h-7 rounded border border-[var(--glass-border)] text-muted-foreground disabled:opacity-50"
        data-testid={`payslip-adjust-cancel-${slipId}`}
      >✕</button>
    </div>
  );
}
