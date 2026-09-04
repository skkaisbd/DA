/**
 * LoansTab — Peminjaman Alat / Aset (ACC-3).
 *
 * Menggantikan menu "Peminjaman" yang dulu salah domain di Portal Aksesoris
 * (lihat memory/PRODUKSI_E9_AKSESORIS.md §ACC-3 & PRODUKSI_E7_ASET.md §AST-3).
 * Di sini yang dipinjam = UNIT ASET ber-nomor, bukan qty barang habis pakai.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import {
  RotateCcw, Plus, RefreshCw, Search, AlertTriangle, CheckCircle2, PackageCheck, Clock,
} from 'lucide-react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { apicall, fmtDate } from '../utils';
import { KPICard } from '../components/KPICard';
import { StatusBadge } from '../components/StatusBadge';
import { LOAN_STATUS_CONFIG, RETURN_CONDITION_LABEL } from '../constants';
import { CreateLoanDialog } from '../dialogs/CreateLoanDialog';
import { ReturnLoanDialog } from '../dialogs/ReturnLoanDialog';

export function LoansTab({ token }) {
  const [loans, setLoans] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState('active');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [returnLoan, setReturnLoan] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [rows, sm] = await Promise.all([
        apicall('GET', `/api/assets/loans?status=${status}`, token),
        apicall('GET', '/api/assets/loans/summary', token),
      ]);
      setLoans(Array.isArray(rows) ? rows : []);
      setSummary(sm || null);
    } catch (e) {
      setErr(e.message || 'Gagal memuat data peminjaman');
    } finally { setLoading(false); }
  }, [token, status]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return loans;
    return loans.filter(l => `${l.loan_number} ${l.asset_number} ${l.asset_name} ${l.borrower_name} ${l.borrower_divisi} ${l.purpose}`
      .toLowerCase().includes(q));
  }, [loans, search]);

  const rowStatus = (l) => (l.is_overdue ? 'overdue' : l.status);

  return (
    <div className="space-y-4" data-testid="asset-loans-tab">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <RotateCcw size={18} className="text-primary" /> Peminjaman Alat &amp; Aset
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Alat/aset yang dibawa keluar dan harus dikembalikan. Satu pinjaman = satu unit aset ber-nomor —
            bukan stok habis pakai (aksesoris pakai jalur Request &amp; Issue).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setShowCreate(true)} data-testid="asset-loan-new-btn">
            <Plus size={14} className="mr-1" /> Pinjamkan Aset
          </Button>
          <Button size="sm" variant="outline" onClick={load} data-testid="asset-loan-refresh">
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard label="Sedang Dipinjam" value={summary?.active_loans ?? '—'} icon={RotateCcw} accent="violet"
          testId="asset-loan-kpi-active"
          sub={summary?.longest_out_days ? `terlama ${summary.longest_out_days} hari` : 'belum ada'} />
        <KPICard label="Terlambat" value={summary?.overdue_loans ?? '—'} icon={AlertTriangle} accent="amber"
          testId="asset-loan-kpi-overdue"
          sub="melewati target kembali" />
        <KPICard label="Kembali Bulan Ini" value={summary?.returned_this_month ?? '—'} icon={CheckCircle2} accent="emerald"
          testId="asset-loan-kpi-returned"
          sub="sudah dikembalikan" />
        <KPICard label="Aset Siap Dipinjam" value={summary?.available_assets ?? '—'} icon={PackageCheck} accent="blue"
          testId="asset-loan-kpi-available"
          sub="berstatus aktif" />
      </div>

      {summary?.by_divisi?.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">Dipinjam per divisi:</span>
          {summary.by_divisi.map(d => (
            <span key={d.divisi} className="px-2 py-0.5 rounded-full border border-border bg-muted/40">
              {d.divisi} · {d.count}
            </span>
          ))}
        </div>
      )}

      {/* Filter */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-8" placeholder="Cari no. pinjam / aset / peminjam..." value={search}
            onChange={e => setSearch(e.target.value)} data-testid="asset-loan-search" />
        </div>
        <SmartNativeSelect value={status} onChange={e => setStatus(e.target.value)}
          className="w-44" searchable={false} data-testid="asset-loan-status-filter">
          <option value="active">Sedang Dipinjam</option>
          <option value="returned">Sudah Kembali</option>
          <option value="all">Semua</option>
        </SmartNativeSelect>
      </div>

      {err && (
        <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-3 py-2">
          {err}
        </div>
      )}

      {/* Tabel */}
      <div className="rounded-xl border overflow-hidden">
        <table className="w-full" data-testid="asset-loans-table">
          <thead className="bg-muted/40">
            <tr>
              {['No. Pinjam', 'Aset', 'Peminjam', 'Tujuan', 'Tgl Pinjam', 'Target Kembali', 'Status', ''].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-3 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              <tr><td colSpan={8} className="text-center py-10 text-sm text-muted-foreground">Memuat...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="py-12">
                <div className="flex flex-col items-center gap-2 text-center">
                  <RotateCcw size={28} className="text-muted-foreground/50" />
                  <p className="font-semibold text-sm">Belum ada peminjaman</p>
                  <p className="text-xs text-muted-foreground max-w-sm">
                    Catat alat/aset yang dibawa keluar lewat tombol "Pinjamkan Aset" agar keberadaannya
                    terlacak dan bisa ditagih saat jatuh tempo.
                  </p>
                </div>
              </td></tr>
            ) : filtered.map(l => (
              <tr key={l.id} className="hover:bg-muted/30 transition-colors" data-testid={`asset-loan-row-${l.id}`}>
                <td className="px-3 py-2.5 text-sm font-mono">{l.loan_number}</td>
                <td className="px-3 py-2.5 text-sm">
                  <div className="font-medium">{l.asset_name}</div>
                  <div className="text-xs text-muted-foreground font-mono">{l.asset_number}</div>
                </td>
                <td className="px-3 py-2.5 text-sm">
                  <div>{l.borrower_name}</div>
                  {l.borrower_divisi && <div className="text-xs text-muted-foreground">{l.borrower_divisi}</div>}
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[220px]">{l.purpose || '-'}</td>
                <td className="px-3 py-2.5 text-xs">{fmtDate(l.loan_date)}</td>
                <td className="px-3 py-2.5 text-xs">
                  {l.expected_return_date ? fmtDate(l.expected_return_date) : <span className="text-muted-foreground">tidak ditentukan</span>}
                  {l.status === 'returned' && l.return_date && (
                    <div className="text-[11px] text-emerald-600 dark:text-emerald-400">
                      kembali {fmtDate(l.return_date)}
                      {l.condition_in ? ` · ${RETURN_CONDITION_LABEL[l.condition_in] || l.condition_in}` : ''}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={rowStatus(l)} configMap={LOAN_STATUS_CONFIG} />
                  {l.is_overdue && (
                    <div className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5 flex items-center gap-1">
                      <Clock size={10} /> {l.days_overdue} hari
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-right">
                  {l.status === 'active' ? (
                    <Button size="sm" variant="outline" onClick={() => setReturnLoan(l)}
                      data-testid={`asset-loan-return-${l.id}`}>
                      Kembalikan
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {l.returned_by_name ? `oleh ${l.returned_by_name}` : '—'}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loading && filtered.length > 0 && (
        <p className="text-xs text-muted-foreground">Menampilkan {filtered.length} peminjaman</p>
      )}

      <CreateLoanDialog open={showCreate} onClose={() => setShowCreate(false)} token={token}
        onCreated={() => { load(); }} />
      <ReturnLoanDialog open={!!returnLoan} onClose={() => setReturnLoan(null)} token={token}
        loan={returnLoan}
        onReturned={(d) => {
          load();
          if (d?.maintenance_created) {
            toast.info('Catatan pemeliharaan otomatis dibuat karena aset kembali dalam kondisi rusak.');
          }
        }} />
    </div>
  );
}
