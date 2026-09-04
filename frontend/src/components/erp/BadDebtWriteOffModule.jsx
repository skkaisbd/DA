import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, ShieldAlert, AlertTriangle, FileText } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

const AGING_BUCKETS = {
  '0-30 days': { color: 'bg-yellow-500/20 text-yellow-300', priority: 1 },
  '31-60 days': { color: 'bg-orange-500/20 text-orange-300', priority: 2 },
  '61-90 days': { color: 'bg-red-500/20 text-red-300', priority: 3 },
  '91-180 days': { color: 'bg-red-600/20 text-red-400', priority: 4 },
  '>180 days (bad debt candidate)': { color: 'bg-red-900/30 text-red-200 font-bold', priority: 5 },
};

export default function BadDebtWriteOffModule({ token }) {
  const [overdueData, setOverdueData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [minDays, setMinDays] = useState(30);
  const [writeOffTarget, setWriteOffTarget] = useState(null);
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchOverdueReport = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/ar-invoices/overdue-report?days=${minDays}`, { headers });
      if (r.ok) {
        setOverdueData(await r.json());
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat laporan overdue', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, minDays]);

  useEffect(() => { fetchOverdueReport(); }, [fetchOverdueReport]);

  const writeOff = async (invoice) => {
    if (!writeOffTarget) return;
    if (!writeOffTarget.reason || writeOffTarget.reason.trim().length < 10) {
      toast({ title: 'Error', description: 'Alasan write-off harus minimal 10 karakter untuk audit trail', variant: 'destructive' });
      return;
    }
    try {
      const r = await fetch(`/api/rahaza/ar-invoices/${invoice.id}/write-off-bad-debt`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          reason: writeOffTarget.reason,
          write_off_date: writeOffTarget.write_off_date || new Date().toISOString().split('T')[0]
        })
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: `Invoice ${invoice.invoice_number} berhasil di-write off` });
        setWriteOffTarget(null);
        fetchOverdueReport();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal write-off', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal write-off invoice', variant: 'destructive' });
    }
  };

  const summary = overdueData?.summary || {};
  const invoices = overdueData?.invoices || [];

  return (
    <div className="space-y-5" data-testid="bad-debt-page">
      <PageHeader
        icon={ShieldAlert}
        eyebrow="Portal Finance · AR Management"
        title="Hapus Buku Piutang Macet"
        subtitle="Kelola piutang overdue dan write-off piutang yang tidak tertagih. Sistem otomatis posting jurnal bad debt expense."
        actions={
          <Button variant="ghost" onClick={fetchOverdueReport} className="h-9 border border-[var(--glass-border)]" data-testid="bd-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
          </Button>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <StatTile label="Total Overdue" value={summary.total_overdue_invoices || 0} />
        <StatTile label="Jumlah Overdue" value={fmt(summary.total_overdue_amount)} accent="warning" />
        <StatTile
          label="High Risk (>180 hari)"
          value={summary.high_risk_count || 0}
          accent="destructive"
        />
        <StatTile label="High Risk Amount" value={fmt(summary.high_risk_amount)} accent="destructive" />
      </div>
      <GlassCard className="p-4">
        <div className="flex gap-3 mb-4 items-center">
          <label className="text-sm text-muted-foreground">Min. Overdue:</label>
          <select
            value={minDays}
            onChange={e => setMinDays(Number(e.target.value))}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
            data-testid="bd-min-days"
          >
            <option value={0}>Semua</option>
            <option value={30}>30+ hari</option>
            <option value={60}>60+ hari</option>
            <option value={90}>90+ hari</option>
            <option value={180}>180+ hari</option>
          </select>
          <div className="ml-auto flex gap-2">
            <div className="text-xs">
              <span className="text-muted-foreground">Legend:</span>
              {Object.entries(AGING_BUCKETS).map(([bucket, { color }]) => (
                <span key={bucket} className={`ml-2 px-2 py-1 rounded ${color}`}>
                  {bucket.replace(' (bad debt candidate)', '')}
                </span>
              ))}
            </div>
          </div>
        </div>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : invoices.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Tidak ada invoice overdue</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="bd-invoice-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Invoice No</th>
                  <th className="pb-2">Tanggal Jatuh Tempo</th>
                  <th className="pb-2">Overdue</th>
                  <th className="pb-2">Aging Bucket</th>
                  <th className="pb-2 text-right">Saldo</th>
                  <th className="pb-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map(inv => (
                  <tr
                    key={inv.id}
                    className={`border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30 ${inv.overdue_days > 180 ? 'bg-red-900/10' : ''}`}
                    data-testid={`bd-row-${inv.id}`}
                  >
                    <td className="py-3 font-mono text-xs">{inv.invoice_number}</td>
                    <td className="py-3 text-xs">{inv.due_date}</td>
                    <td className="py-3">
                      <span className="text-red-300 font-semibold">{inv.overdue_days} hari</span>
                    </td>
                    <td className="py-3">
                      <span className={`px-2 py-1 rounded text-xs ${AGING_BUCKETS[inv.aging_bucket]?.color || 'bg-muted/20 text-foreground/80'}`}>
                        {inv.aging_bucket}
                      </span>
                    </td>
                    <td className="py-3 text-right font-mono">{fmt(inv.balance)}</td>
                    <td className="py-3 text-right">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setWriteOffTarget({ ...inv, reason: '', write_off_date: '' })}
                        data-testid={`bd-writeoff-${inv.id}`}
                      >
                        <ShieldAlert className="w-3.5 h-3.5 mr-1" />
                        Write-Off
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
      {writeOffTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setWriteOffTarget(null)}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="bd-writeoff-dialog">
            <div className="flex items-start gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0" />
              <div>
                <h2 className="text-xl font-bold text-foreground">Konfirmasi Write-Off Bad Debt</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Tindakan ini akan menghapus buku piutang dan otomatis posting jurnal bad debt expense.
                </p>
              </div>
            </div>
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4">
              <div className="text-sm">
                <div className="flex justify-between mb-1">
                  <span className="text-muted-foreground">Invoice:</span>
                  <span className="font-mono font-semibold">{writeOffTarget.invoice_number}</span>
                </div>
                <div className="flex justify-between mb-1">
                  <span className="text-muted-foreground">Overdue:</span>
                  <span className="text-red-300 font-semibold">{writeOffTarget.overdue_days} hari</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Jumlah:</span>
                  <span className="font-mono text-lg font-bold text-red-300">{fmt(writeOffTarget.balance)}</span>
                </div>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground block mb-1">Tanggal Write-Off</label>
                <input
                  type="date"
                  value={writeOffTarget.write_off_date}
                  onChange={e => setWriteOffTarget(w => ({ ...w, write_off_date: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="bd-writeoff-date"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground block mb-1">
                  Alasan Write-Off <span className="text-red-400">*</span>
                </label>
                <textarea
                  value={writeOffTarget.reason}
                  onChange={e => setWriteOffTarget(w => ({ ...w, reason: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  rows={4}
                  placeholder="Contoh: Customer bangkrut, tidak tertagih setelah 6 bulan follow-up intensif"
                  data-testid="bd-writeoff-reason"
                />
                <div className="text-xs text-muted-foreground mt-1">
                  Min. 10 karakter untuk audit trail. Saat ini: {writeOffTarget.reason.length} karakter
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => setWriteOffTarget(null)} className="border border-[var(--glass-border)]" data-testid="bd-cancel">
                Batal
              </Button>
              <Button
                variant="destructive"
                onClick={() => writeOff(writeOffTarget)}
                disabled={!writeOffTarget.reason || writeOffTarget.reason.length < 10}
                data-testid="bd-confirm-writeoff"
              >
                <ShieldAlert className="w-4 h-4 mr-2" />
                Konfirmasi Write-Off
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
