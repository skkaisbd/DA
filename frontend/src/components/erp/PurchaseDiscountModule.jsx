import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, HandCoins, CheckCircle, Clock } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function PurchaseDiscountModule({ token }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [paymentForm, setPaymentForm] = useState(null);
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/ap-invoices?status=sent', { headers });
      if (r.ok) {
        const data = await r.json();
        // Enrich with early payment discount eligibility
        const enriched = data.map(inv => {
          const issueDate = new Date(inv.issue_date);
          const discountDeadline = new Date(issueDate);
          discountDeadline.setDate(issueDate.getDate() + 10); // Assume 10 days discount period
          const daysLeft = Math.ceil((discountDeadline - new Date()) / (1000 * 60 * 60 * 24));
          const isEligible = daysLeft > 0;
          const discountPercent = 2; // 2% early payment discount
          const discountAmount = isEligible ? Math.round(inv.balance * discountPercent / 100) : 0;
          return {
            ...inv,
            discount_eligible: isEligible,
            discount_deadline: discountDeadline.toISOString().split('T')[0],
            discount_days_left: daysLeft,
            discount_percent: discountPercent,
            discount_amount: discountAmount
          };
        });
        setInvoices(enriched);
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat AP invoices', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchInvoices(); }, [fetchInvoices]);

  const pay = async () => {
    if (!paymentForm) return;
    if (!paymentForm.account_id || !paymentForm.amount) {
      toast({ title: 'Error', description: 'Account dan amount wajib diisi', variant: 'destructive' });
      return;
    }
    try {
      const r = await fetch(`/api/rahaza/ap-invoices/${paymentForm.invoice_id}/payment`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          amount: Number(paymentForm.amount),
          discount_amount: Number(paymentForm.discount_amount) || 0,
          account_id: paymentForm.account_id,
          date: paymentForm.date || new Date().toISOString().split('T')[0],
          notes: paymentForm.notes
        })
      });
      if (r.ok) {
        const savedAmount = paymentForm.discount_amount || 0;
        toast({
          title: 'Sukses',
          description: `Pembayaran berhasil. ${savedAmount > 0 ? `Hemat: ${fmt(savedAmount)}` : ''}`
        });
        setPaymentForm(null);
        fetchInvoices();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal bayar', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal pembayaran', variant: 'destructive' });
    }
  };

  const applyDiscount = (invoice) => {
    if (!invoice.discount_eligible) return;
    const netAmount = invoice.balance - invoice.discount_amount;
    setPaymentForm(f => ({
      ...f,
      discount_applied: true,
      discount_amount: invoice.discount_amount,
      amount: netAmount
    }));
  };

  const eligibleInvoices = invoices.filter(i => i.discount_eligible);
  const totalDiscountAvailable = eligibleInvoices.reduce((s, i) => s + i.discount_amount, 0);

  const { page, setPage, totalPages, total, paged } = useClientPagination(invoices, 10);
  return (
    <div className="space-y-5" data-testid="purchase-discount-page">
      <PageHeader
        icon={HandCoins}
        eyebrow="Portal Finance · AP Management"
        title="Diskon Pembelian (AP Payment)"
        subtitle="Kelola pembayaran AP dengan early payment discount. Hemat biaya dengan bayar lebih awal."
        actions={
          <Button variant="ghost" onClick={fetchInvoices} className="h-9 border border-[var(--glass-border)]" data-testid="pd-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
          </Button>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatTile label="Total Unpaid AP" value={invoices.length} />
        <StatTile label="Eligible untuk Diskon" value={eligibleInvoices.length} accent="success" />
        <StatTile label="Potensi Hemat" value={fmt(totalDiscountAvailable)} accent="success" />
      </div>
      <GlassCard className="p-4">
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : invoices.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Tidak ada AP invoice yang belum dibayar</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="pd-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Invoice No</th>
                  <th className="pb-2">Vendor</th>
                  <th className="pb-2">Jatuh Tempo</th>
                  <th className="pb-2 text-right">Saldo</th>
                  <th className="pb-2">Diskon</th>
                  <th className="pb-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(inv => (
                  <tr
                    key={inv.id}
                    className={`border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30 ${inv.discount_eligible ? 'bg-emerald-500/5' : ''}`}
                    data-testid={`pd-row-${inv.id}`}
                  >
                    <td className="py-3 font-mono text-xs">{inv.invoice_number}</td>
                    <td className="py-3">{inv.vendor_name}</td>
                    <td className="py-3 text-xs">{inv.due_date}</td>
                    <td className="py-3 text-right font-mono">{fmt(inv.balance)}</td>
                    <td className="py-3">
                      {inv.discount_eligible ? (
                        <div className="flex items-center gap-1">
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-300" />
                          <span className="text-xs text-emerald-300 font-semibold">
                            {inv.discount_percent}% ({fmt(inv.discount_amount)})
                          </span>
                          <Clock className="w-3 h-3 text-yellow-300 ml-1" />
                          <span className="text-xs text-yellow-300">{inv.discount_days_left}d left</span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">Expired</span>
                      )}
                    </td>
                    <td className="py-3 text-right">
                      <Button
                        size="sm"
                        onClick={() => setPaymentForm({
                          invoice_id: inv.id,
                          invoice_number: inv.invoice_number,
                          vendor_name: inv.vendor_name,
                          balance: inv.balance,
                          discount_eligible: inv.discount_eligible,
                          discount_amount: inv.discount_amount,
                          discount_percent: inv.discount_percent,
                          amount: inv.balance,
                          discount_applied: false,
                          account_id: '',
                          date: '',
                          notes: ''
                        })}
                        data-testid={`pd-pay-${inv.id}`}
                      >
                        Bayar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        )}
      </GlassCard>
      {paymentForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setPaymentForm(null)}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="pd-payment-form">
            <h2 className="text-xl font-bold text-foreground mb-4">Pembayaran AP Invoice</h2>
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-4">
              <div className="text-sm space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Invoice:</span>
                  <span className="font-mono">{paymentForm.invoice_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Vendor:</span>
                  <span>{paymentForm.vendor_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Saldo:</span>
                  <span className="font-mono">{fmt(paymentForm.balance)}</span>
                </div>
              </div>
            </div>
            {paymentForm.discount_eligible && (
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-300" />
                    <span className="text-sm font-semibold text-emerald-300">Early Payment Discount Available</span>
                  </div>
                  {!paymentForm.discount_applied && (
                    <Button size="sm" onClick={() => applyDiscount(paymentForm)} data-testid="pd-apply-discount">
                      Apply Diskon
                    </Button>
                  )}
                </div>
                <div className="text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Diskon {paymentForm.discount_percent}%:</span>
                    <span className="font-mono text-emerald-300">-{fmt(paymentForm.discount_amount)}</span>
                  </div>
                  {paymentForm.discount_applied && (
                    <div className="flex justify-between font-semibold">
                      <span className="text-foreground">Net Amount:</span>
                      <span className="font-mono text-emerald-300">{fmt(paymentForm.amount)}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground">Jumlah Bayar (Rp)</label>
                <GlassInput
                  type="number"
                  value={paymentForm.amount}
                  onChange={e => setPaymentForm(f => ({ ...f, amount: e.target.value, discount_applied: false }))}
                  data-testid="pd-amount"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Account ID (Kas/Bank)</label>
                <GlassInput
                  value={paymentForm.account_id}
                  onChange={e => setPaymentForm(f => ({ ...f, account_id: e.target.value }))}
                  placeholder="UUID cash account"
                  data-testid="pd-account-id"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Tanggal Pembayaran</label>
                <input
                  type="date"
                  value={paymentForm.date}
                  onChange={e => setPaymentForm(f => ({ ...f, date: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="pd-date"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Catatan</label>
                <textarea
                  value={paymentForm.notes}
                  onChange={e => setPaymentForm(f => ({ ...f, notes: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  rows={2}
                  data-testid="pd-notes"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => setPaymentForm(null)} className="border border-[var(--glass-border)]" data-testid="pd-cancel">
                Batal
              </Button>
              <Button onClick={pay} data-testid="pd-confirm">
                <HandCoins className="w-4 h-4 mr-2" />
                Konfirmasi Pembayaran
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
