import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, HandCoins, Plus, CheckCircle } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function EmployeeLoansModule({ token }) {
  const [loans, setLoans] = useState([]);
  const [tab, setTab] = useState('active');
  const [loading, setLoading] = useState(true);
  const [disburseForm, setDisburseForm] = useState(null);
  const [repayForm, setRepayForm] = useState(null);
  const [loanDetail, setLoanDetail] = useState(null);
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchLoans = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/hr/employee-loans?status=${tab}`, { headers });
      if (r.ok) setLoans(await r.json());
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat data pinjaman', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, tab]);

  useEffect(() => { fetchLoans(); }, [fetchLoans]);

  const disburse = async () => {
    if (!disburseForm) return;
    if (!disburseForm.employee_id || !disburseForm.loan_amount || !disburseForm.installment_amount || !disburseForm.installment_count) {
      toast({ title: 'Error', description: 'Semua field wajib diisi', variant: 'destructive' });
      return;
    }
    try {
      const r = await fetch('/api/rahaza/hr/employee-loans/disburse', {
        method: 'POST',
        headers,
        body: JSON.stringify(disburseForm)
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Pinjaman berhasil dicairkan' });
        setDisburseForm(null);
        fetchLoans();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal mencairkan pinjaman', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal mencairkan pinjaman', variant: 'destructive' });
    }
  };

  const repay = async () => {
    if (!repayForm || !repayForm.loan_id) return;
    try {
      const r = await fetch(`/api/rahaza/hr/employee-loans/${repayForm.loan_id}/repay`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          repayment_amount: Number(repayForm.repayment_amount),
          repayment_date: repayForm.repayment_date || new Date().toISOString().split('T')[0],
          notes: repayForm.notes
        })
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Pembayaran berhasil dicatat' });
        setRepayForm(null);
        if (loanDetail) viewDetail(loanDetail.id);
        fetchLoans();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal catat pembayaran', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal catat pembayaran', variant: 'destructive' });
    }
  };

  const viewDetail = async (loanId) => {
    try {
      const r = await fetch(`/api/rahaza/hr/employee-loans/${loanId}`, { headers });
      if (r.ok) setLoanDetail(await r.json());
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat detail pinjaman', variant: 'destructive' });
    }
  };

  const activeLoans = loans.filter(l => l.status === 'active');
  const totalOutstanding = activeLoans.reduce((s, l) => s + (l.outstanding_balance || 0), 0);
  const totalPaidThisMonth = loans.filter(l => {
    const d = new Date(l.disbursed_at || '');
    const now = new Date();
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear() && l.status === 'paid_off';
  }).length;
  const { page, setPage, totalPages, total, paged } = useClientPagination(loans, 10);

  return (
    <div className="space-y-5" data-testid="employee-loans-page">
      <PageHeader
        icon={HandCoins}
        eyebrow="Portal HR · Payroll & Benefits"
        title="Pinjaman Karyawan"
        subtitle="Kelola pinjaman karyawan dengan integrasi otomatis ke payroll. Sistem auto-deduct dari gaji bulanan."
        actions={
          <>
            <Button variant="ghost" onClick={fetchLoans} className="h-9 border border-[var(--glass-border)]" data-testid="loan-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
            </Button>
            <Button onClick={() => setDisburseForm({
              employee_id: '',
              loan_amount: 0,
              installment_amount: 0,
              installment_count: 12,
              disbursement_date: new Date().toISOString().split('T')[0],
              first_deduction_period: new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().slice(0, 7),
              notes: ''
            })} className="h-9" data-testid="loan-disburse-btn">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Cairkan Pinjaman
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatTile label="Pinjaman Aktif" value={activeLoans.length} />
        <StatTile label="Total Outstanding" value={fmt(totalOutstanding)} accent="warning" />
        <StatTile label="Lunas Bulan Ini" value={totalPaidThisMonth} accent="success" />
      </div>
      <GlassCard className="p-4">
        <div className="flex gap-2 mb-4">
          <Button variant={tab === 'active' ? 'default' : 'ghost'} onClick={() => setTab('active')} data-testid="loan-tab-active">
            Aktif
          </Button>
          <Button variant={tab === 'paid_off' ? 'default' : 'ghost'} onClick={() => setTab('paid_off')} data-testid="loan-tab-paid">
            Lunas
          </Button>
        </div>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : loans.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Belum ada data pinjaman</div>
        ) : (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="loan-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Loan Number</th>
                  <th className="pb-2">Nama Karyawan</th>
                  <th className="pb-2 text-right">Jumlah Pinjaman</th>
                  <th className="pb-2 text-right">Cicilan/Bulan</th>
                  <th className="pb-2">Progress</th>
                  <th className="pb-2 text-right">Outstanding</th>
                  <th className="pb-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(l => (
                  <tr key={l.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30 cursor-pointer" onClick={() => viewDetail(l.id)} data-testid={`loan-row-${l.id}`}>
                    <td className="py-3 font-mono text-xs">{l.loan_number}</td>
                    <td className="py-3">{l.employee_name}</td>
                    <td className="py-3 text-right font-mono">{fmt(l.loan_amount)}</td>
                    <td className="py-3 text-right font-mono">{fmt(l.installment_amount)}</td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-[var(--glass-border)] rounded-full h-2 overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${(l.paid_installments / l.installment_count) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {l.paid_installments}/{l.installment_count}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 text-right font-mono">{fmt(l.outstanding_balance)}</td>
                    <td className="py-3 text-right" onClick={e => e.stopPropagation()}>
                      {l.status === 'active' && (
                        <Button size="sm" onClick={() => setRepayForm({ loan_id: l.id, repayment_amount: l.installment_amount, repayment_date: '', notes: '' })} data-testid={`loan-repay-${l.id}`}>
                          Bayar Manual
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </>
        )}
      </GlassCard>
      {disburseForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setDisburseForm(null)}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="loan-disburse-form">
            <h2 className="text-xl font-bold text-foreground mb-4">Cairkan Pinjaman Baru</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground">Employee ID</label>
                <GlassInput value={disburseForm.employee_id} onChange={e => setDisburseForm(f => ({ ...f, employee_id: e.target.value }))} placeholder="UUID karyawan" data-testid="loan-employee-id" />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Jumlah Pinjaman (Rp)</label>
                <GlassInput type="number" value={disburseForm.loan_amount} onChange={e => setDisburseForm(f => ({ ...f, loan_amount: Number(e.target.value) }))} data-testid="loan-amount" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs uppercase text-muted-foreground">Cicilan/Bulan (Rp)</label>
                  <GlassInput type="number" value={disburseForm.installment_amount} onChange={e => setDisburseForm(f => ({ ...f, installment_amount: Number(e.target.value) }))} data-testid="loan-installment" />
                </div>
                <div>
                  <label className="text-xs uppercase text-muted-foreground">Jumlah Cicilan</label>
                  <GlassInput type="number" value={disburseForm.installment_count} onChange={e => setDisburseForm(f => ({ ...f, installment_count: Number(e.target.value) }))} data-testid="loan-count" />
                </div>
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Tanggal Pencairan</label>
                <input type="date" value={disburseForm.disbursement_date} onChange={e => setDisburseForm(f => ({ ...f, disbursement_date: e.target.value }))} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="loan-disb-date" />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Potong Mulai Periode (YYYY-MM)</label>
                <input type="month" value={disburseForm.first_deduction_period} onChange={e => setDisburseForm(f => ({ ...f, first_deduction_period: e.target.value }))} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="loan-first-period" />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Catatan</label>
                <textarea value={disburseForm.notes} onChange={e => setDisburseForm(f => ({ ...f, notes: e.target.value }))} className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" rows={2} data-testid="loan-notes" />
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => setDisburseForm(null)} className="border border-[var(--glass-border)]">Batal</Button>
              <Button onClick={disburse} data-testid="loan-disburse-confirm">Cairkan Pinjaman</Button>
            </div>
          </GlassCard>
        </div>
      )}
      {repayForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setRepayForm(null)}>
          <GlassCard className="p-6 max-w-md w-full" onClick={e => e.stopPropagation()} data-testid="loan-repay-form">
            <h2 className="text-xl font-bold text-foreground mb-4">Pembayaran Manual</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground">Jumlah Bayar (Rp)</label>
                <GlassInput type="number" value={repayForm.repayment_amount} onChange={e => setRepayForm(f => ({ ...f, repayment_amount: e.target.value }))} data-testid="repay-amount" />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Tanggal Bayar</label>
                <input type="date" value={repayForm.repayment_date} onChange={e => setRepayForm(f => ({ ...f, repayment_date: e.target.value }))} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="repay-date" />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Catatan</label>
                <textarea value={repayForm.notes} onChange={e => setRepayForm(f => ({ ...f, notes: e.target.value }))} className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" rows={2} placeholder="Bayar tunai" data-testid="repay-notes" />
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => setRepayForm(null)} className="border border-[var(--glass-border)]">Batal</Button>
              <Button onClick={repay} data-testid="repay-confirm">Catat Pembayaran</Button>
            </div>
          </GlassCard>
        </div>
      )}
      {loanDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setLoanDetail(null)}>
          <GlassCard className="p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()} data-testid="loan-detail">
            <h2 className="text-xl font-bold text-foreground mb-4">Detail Pinjaman: {loanDetail.loan_number}</h2>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div><span className="text-sm text-muted-foreground">Karyawan:</span> <span className="font-semibold">{loanDetail.employee_name}</span></div>
              <div><span className="text-sm text-muted-foreground">Status:</span> <span className={`px-2 py-1 rounded text-xs ${loanDetail.status === 'active' ? 'bg-blue-500/20 text-blue-300' : 'bg-emerald-500/20 text-emerald-300'}`}>{loanDetail.status}</span></div>
              <div><span className="text-sm text-muted-foreground">Jumlah Pinjaman:</span> <span className="font-mono">{fmt(loanDetail.loan_amount)}</span></div>
              <div><span className="text-sm text-muted-foreground">Outstanding:</span> <span className="font-mono">{fmt(loanDetail.outstanding_balance)}</span></div>
            </div>
            <h3 className="text-lg font-semibold mb-3">Riwayat Pembayaran ({loanDetail.repayments?.length || 0})</h3>
            {loanDetail.repayments && loanDetail.repayments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                      <th className="pb-2">Tanggal</th>
                      <th className="pb-2">Metode</th>
                      <th className="pb-2 text-right">Jumlah</th>
                      <th className="pb-2">Catatan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loanDetail.repayments.map(r => (
                      <tr key={r.id} className="border-b border-[var(--glass-border)]">
                        <td className="py-2 text-xs">{r.repayment_date}</td>
                        <td className="py-2"><span className={`px-2 py-1 rounded text-xs ${r.repayment_method === 'payroll' ? 'bg-blue-500/20 text-blue-300' : 'bg-emerald-500/20 text-emerald-300'}`}>{r.repayment_method}</span></td>
                        <td className="py-2 text-right font-mono">{fmt(r.repayment_amount)}</td>
                        <td className="py-2 text-xs text-muted-foreground">{r.notes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground text-sm">Belum ada pembayaran</div>
            )}
            <div className="flex justify-end mt-4">
              <Button onClick={() => setLoanDetail(null)}>Tutup</Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
