/**
 * Payment Tab - LiveHost Payment Management & Sync to Finance
 */

import { useState, useEffect, useCallback } from 'react';
import { DollarSign, RefreshCw, ChevronLeft, ChevronRight, Loader2, CheckCircle, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;
const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const fmtRp = (n) => `Rp ${fmt(n)}`;

export default function PaymentTab({ authH }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [paymentStatus, setPaymentStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const fetchPaymentStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/payment/status?month=${month}`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setPaymentStatus(data);
      }
    } catch (e) {
      toast.error('Gagal memuat payment status');
    } finally {
      setLoading(false);
    }
  }, [authH, month]);

  useEffect(() => {
    fetchPaymentStatus();
  }, [fetchPaymentStatus]);

  const handleCalculate = async () => {
    if (!window.confirm(`Calculate payment untuk semua shift bulan ${month}?`)) return;
    setCalculating(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/payment/calculate?month=${month}`, {
        method: 'POST',
        headers: authH,
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(data.message);
        fetchPaymentStatus();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal calculate payment');
      }
    } catch (e) {
      toast.error('Gagal calculate payment');
    } finally {
      setCalculating(false);
    }
  };

  const handleSync = async () => {
    if (!window.confirm(`Sync payment ke Finance untuk bulan ${month}? Ini akan membuat payroll entries di Finance module.`)) return;
    setSyncing(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/payment/sync-to-finance?month=${month}`, {
        method: 'POST',
        headers: authH,
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(data.message);
        fetchPaymentStatus();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal sync payment');
      }
    } catch (e) {
      toast.error('Gagal sync payment');
    } finally {
      setSyncing(false);
    }
  };

  const changeMonth = (offset) => {
    const [year, mon] = month.split('-').map(Number);
    const date = new Date(year, mon - 1 + offset, 1);
    setMonth(date.toISOString().slice(0, 7));
  };

  return (
    <div className="space-y-6">
      {/* Month Selector & Actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => changeMonth(-1)} className="h-9">
            <ChevronLeft size={14} />
          </Button>
          <Input
            type="month"
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="w-40 h-9"
            data-testid="payment-month-selector"
          />
          <Button variant="outline" size="sm" onClick={() => changeMonth(1)} className="h-9">
            <ChevronRight size={14} />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchPaymentStatus} className="h-9">
            <RefreshCw size={14} className="mr-1.5" />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={handleCalculate}
            disabled={calculating}
            className="h-9"
            data-testid="calculate-payment-btn"
          >
            {calculating ? (
              <>
                <Loader2 size={14} className="mr-1.5 animate-spin" />
                Calculating...
              </>
            ) : (
              <>
                <DollarSign size={14} className="mr-1.5" />
                Calculate Payment
              </>
            )}
          </Button>
          <Button
            size="sm"
            onClick={handleSync}
            disabled={syncing}
            className="h-9 bg-emerald-600 hover:bg-emerald-700"
            data-testid="sync-to-finance-btn"
          >
            {syncing ? (
              <>
                <Loader2 size={14} className="mr-1.5 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <CheckCircle size={14} className="mr-1.5" />
                Sync to Finance
              </>
            )}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : !paymentStatus ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <DollarSign size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">No payment data</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-1">Total Shifts</p>
                  <p className="text-2xl font-bold">{paymentStatus.total_completed_shifts}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-1">Total Amount</p>
                  <p className="text-2xl font-bold text-emerald-600">{fmtRp(paymentStatus.total_amount)}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-1">Pending</p>
                  <p className="text-2xl font-bold text-amber-600">{paymentStatus.status_summary.pending.count}</p>
                  <p className="text-xs text-muted-foreground mt-1">{fmtRp(paymentStatus.status_summary.pending.total_pay)}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-1">Synced</p>
                  <p className="text-2xl font-bold text-emerald-600">{paymentStatus.status_summary.synced_to_finance.count}</p>
                  <p className="text-xs text-muted-foreground mt-1">{fmtRp(paymentStatus.status_summary.synced_to_finance.total_pay)}</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Payment Pipeline Status */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Payment Pipeline - {month}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Pending */}
                <div className="flex items-center justify-between p-4 bg-amber-50 dark:bg-amber-900/10 rounded-lg border border-amber-200 dark:border-amber-900/30">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                      <Clock size={20} className="text-amber-600" />
                    </div>
                    <div>
                      <p className="font-medium">Pending Calculation</p>
                      <p className="text-sm text-muted-foreground">Shift yang belum dihitung paymentnya</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold">{paymentStatus.status_summary.pending.count} shifts</p>
                    <p className="text-sm text-muted-foreground">{fmtRp(paymentStatus.status_summary.pending.total_pay)}</p>
                  </div>
                </div>

                {/* Calculated */}
                <div className="flex items-center justify-between p-4 bg-blue-50 dark:bg-blue-900/10 rounded-lg border border-blue-200 dark:border-blue-900/30">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                      <DollarSign size={20} className="text-blue-600" />
                    </div>
                    <div>
                      <p className="font-medium">Calculated</p>
                      <p className="text-sm text-muted-foreground">Sudah dihitung, siap di-sync ke Finance</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold">{paymentStatus.status_summary.calculated.count} shifts</p>
                    <p className="text-sm text-muted-foreground">{fmtRp(paymentStatus.status_summary.calculated.total_pay)}</p>
                  </div>
                </div>

                {/* Synced */}
                <div className="flex items-center justify-between p-4 bg-emerald-50 dark:bg-emerald-900/10 rounded-lg border border-emerald-200 dark:border-emerald-900/30">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                      <CheckCircle size={20} className="text-emerald-600" />
                    </div>
                    <div>
                      <p className="font-medium">Synced to Finance</p>
                      <p className="text-sm text-muted-foreground">Sudah masuk payroll Finance module</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold">{paymentStatus.status_summary.synced_to_finance.count} shifts</p>
                    <p className="text-sm text-muted-foreground">{fmtRp(paymentStatus.status_summary.synced_to_finance.total_pay)}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Payment Calculation Formula */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Payment Calculation Formula</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm">
                <div className="flex items-start gap-2">
                  <Badge variant="outline" className="mt-0.5">Base Pay</Badge>
                  <p className="flex-1">= (Actual Hours Worked) × (Hourly Rate)</p>
                </div>
                <div className="flex items-start gap-2">
                  <Badge variant="outline" className="mt-0.5 bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30">Bonus</Badge>
                  <p className="flex-1">= 10% of Revenue (if revenue &gt; Rp 5,000,000)</p>
                </div>
                <div className="flex items-start gap-2">
                  <Badge variant="outline" className="mt-0.5 bg-red-50 text-red-700 dark:bg-red-900/30">Penalty</Badge>
                  <p className="flex-1">= Rp 50,000 (if attendance = late)</p>
                </div>
                <div className="flex items-start gap-2 pt-2 border-t">
                  <Badge className="mt-0.5">Total Pay</Badge>
                  <p className="flex-1 font-medium">= Base Pay + Bonus - Penalty</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
