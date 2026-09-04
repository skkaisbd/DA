import { useEffect, useState, useCallback } from 'react';
import { Receipt, X, AlertCircle, CheckCircle2, Wallet, Download } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { clientApi, fmtCurrency, fmtDate, INVOICE_STATUS_LABEL } from './clientApi';

const FILTERS = [
  { id: 'all', label: 'Semua' },
  { id: 'issued', label: 'Belum Lunas' },
  { id: 'partial_paid', label: 'Bayar Sebagian' },
  { id: 'overdue', label: 'Lewat Tempo' },
  { id: 'paid', label: 'Lunas' },
];

function StatusBadge({ status }) {
  const tone =
    status === 'paid'
      ? 'bg-emerald-100 text-emerald-700'
      : status === 'overdue'
      ? 'bg-red-100 text-red-700'
      : status === 'partial_paid'
      ? 'bg-amber-100 text-amber-700'
      : status === 'cancelled'
      ? 'bg-foreground/10 text-foreground/60'
      : 'bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))]';
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium ${tone}`}>
      {INVOICE_STATUS_LABEL[status] || status}
    </span>
  );
}

function InvoiceDrawer({ open, onClose, invoice, token }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!open || !invoice) return;
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const d = await clientApi.request(`/invoices/${invoice.id}`, { token });
        if (!cancel) setDetail(d);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [open, invoice, token]);

  const downloadPdf = async () => {
    if (!detail) return;
    setDownloading(true);
    try {
      const res = await fetch(`/api/dewi/client-portal/invoices/${detail.id}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Invoice_${detail.invoice_number}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('PDF berhasil diunduh');
    } catch (e) {
      toast.error('Gagal mengunduh PDF');
    } finally {
      setDownloading(false);
    }
  };

  if (!open || !invoice) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" data-testid="client-invoice-drawer">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full md:max-w-2xl bg-[hsl(var(--background))] border-l border-foreground/10 overflow-y-auto">
        <div className="sticky top-0 z-10 bg-[hsl(var(--background))]/95 backdrop-blur border-b border-foreground/10 px-6 py-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Invoice
            </div>
            <div className="text-base font-semibold text-foreground font-mono">
              {invoice.invoice_number}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={downloadPdf}
              disabled={!detail || downloading}
              data-testid="client-invoice-download-pdf"
            >
              <Download size={14} />
              {downloading ? 'Memproses...' : 'PDF'}
            </Button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-foreground/5"
              data-testid="client-invoice-drawer-close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {loading || !detail ? (
          <div className="p-10 text-center text-foreground/50">Memuat detail...</div>
        ) : (
          <div className="p-6 space-y-5">
            <div className="flex items-center gap-2 mb-1">
              <StatusBadge status={detail.status} />
              <span className="text-xs text-foreground/55">
                · Order {detail.order_code}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Tanggal Terbit
                </div>
                <div className="font-medium text-foreground">{fmtDate(detail.issue_date)}</div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Jatuh Tempo
                </div>
                <div className="font-medium text-foreground">{fmtDate(detail.due_date)}</div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Term Pembayaran
                </div>
                <div className="font-medium text-foreground uppercase">
                  {(detail.payment_terms || 'net_30').replace('_', ' ')}
                </div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  PPN
                </div>
                <div className="font-medium text-foreground">{detail.tax_pct || 0}%</div>
              </div>
            </div>

            {/* Lines */}
            <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
              <table className="w-full text-sm">
                <thead className="bg-foreground/[0.04] text-foreground/55">
                  <tr>
                    <th className="text-left font-medium px-3 py-2">Deskripsi</th>
                    <th className="text-right font-medium px-3 py-2">Qty</th>
                    <th className="text-right font-medium px-3 py-2">Harga</th>
                    <th className="text-right font-medium px-3 py-2">Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.lines || []).map((l, i) => (
                    <tr key={i} className="border-t border-foreground/5">
                      <td className="px-3 py-2 text-foreground">{l.description}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {l.qty} {l.unit}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-foreground/75">
                        {fmtCurrency(l.unit_price)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {fmtCurrency(l.line_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Totals */}
            <div className="rounded-xl border border-foreground/10 p-4 space-y-1.5 text-sm">
              <div className="flex justify-between text-foreground/65">
                <span>Subtotal</span>
                <span className="tabular-nums">{fmtCurrency(detail.subtotal)}</span>
              </div>
              {(detail.discount_amount || 0) > 0 && (
                <div className="flex justify-between text-foreground/65">
                  <span>Diskon</span>
                  <span className="tabular-nums">-{fmtCurrency(detail.discount_amount)}</span>
                </div>
              )}
              <div className="flex justify-between text-foreground/65">
                <span>PPN ({detail.tax_pct || 0}%)</span>
                <span className="tabular-nums">{fmtCurrency(detail.tax_amount)}</span>
              </div>
              <div className="flex justify-between text-base font-bold text-foreground pt-2 border-t border-foreground/10">
                <span>Total</span>
                <span className="tabular-nums">{fmtCurrency(detail.total_amount)}</span>
              </div>
              <div className="flex justify-between text-foreground/65">
                <span>Sudah Dibayar</span>
                <span className="tabular-nums text-emerald-700">
                  {fmtCurrency(detail.paid_amount)}
                </span>
              </div>
              <div
                className={`flex justify-between font-semibold pt-2 border-t border-foreground/10 ${
                  detail.balance_amount > 0 ? 'text-amber-700' : 'text-emerald-700'
                }`}
              >
                <span>Saldo Tagihan</span>
                <span className="tabular-nums">{fmtCurrency(detail.balance_amount)}</span>
              </div>
            </div>

            {/* Payment history */}
            <div>
              <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-2 flex items-center gap-1.5">
                <Wallet size={13} />
                Riwayat Pembayaran ({(detail.payments || []).length})
              </div>
              {(detail.payments || []).length === 0 ? (
                <div className="text-sm text-foreground/45 rounded-xl border border-dashed border-foreground/10 p-4 text-center">
                  Belum ada pembayaran tercatat.
                </div>
              ) : (
                <div className="space-y-2">
                  {detail.payments.map((p) => (
                    <div
                      key={p.id}
                      className="rounded-xl border border-foreground/10 p-3 flex items-center justify-between text-sm"
                    >
                      <div>
                        <div className="font-medium text-foreground">
                          {fmtCurrency(p.amount)}
                        </div>
                        <div className="text-xs text-foreground/55">
                          {fmtDate(p.payment_date)} · {p.method}
                          {p.reference_no && ` · #${p.reference_no}`}
                        </div>
                      </div>
                      <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400" />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {detail.notes && (
              <div className="rounded-xl border border-foreground/10 p-3 text-sm">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45 mb-1">
                  Catatan
                </div>
                <div className="text-foreground/85">{detail.notes}</div>
              </div>
            )}

            {detail.balance_amount > 0 && detail.status !== 'cancelled' && (
              <div className="rounded-xl border border-amber-400 dark:border-amber-400/30 bg-amber-400/5 p-3 text-sm flex gap-2">
                <AlertCircle size={16} className="text-amber-700 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-medium text-amber-200">
                    Saldo terutang {fmtCurrency(detail.balance_amount)}
                  </div>
                  <div className="text-xs text-foreground/65 mt-0.5">
                    Konfirmasi pembayaran ke tim Finance CV. Dewi Aditya melalui WhatsApp
                    atau email setelah transfer.
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ClientInvoices({ token }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = filter === 'all' ? '/invoices' : `/invoices?status=${filter}`;
      const data = await clientApi.request(path, { token });
      setInvoices(data);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filter, token]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6" data-testid="client-invoices">
      <div>
        <div className="text-xs uppercase tracking-[0.18em] text-foreground/45 mb-1">
          Invoice & Bayar
        </div>
        <h1 className="text-3xl font-bold text-foreground">Tagihan Saya</h1>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            data-testid={`client-invoices-filter-${f.id}`}
            className={`px-3 py-1.5 text-xs rounded-full whitespace-nowrap transition ${
              filter === f.id
                ? 'bg-[hsl(var(--primary))] text-foreground font-medium'
                : 'bg-foreground/5 text-foreground/65 hover:bg-foreground/10'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-xl bg-foreground/[0.05]" />
          ))}
        </div>
      ) : invoices.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-foreground/10 p-12 text-center">
          <Receipt size={32} className="mx-auto text-foreground/30 mb-2" />
          <p className="text-sm text-foreground/50">Tidak ada invoice untuk filter ini.</p>
        </div>
      ) : (
        <div className="rounded-2xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/[0.04] text-foreground/55">
              <tr>
                <th className="text-left font-medium px-4 py-3">No. Invoice</th>
                <th className="text-left font-medium px-4 py-3">Order</th>
                <th className="text-left font-medium px-4 py-3">Terbit</th>
                <th className="text-left font-medium px-4 py-3">Jatuh Tempo</th>
                <th className="text-right font-medium px-4 py-3">Total</th>
                <th className="text-right font-medium px-4 py-3">Saldo</th>
                <th className="text-left font-medium px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((i) => (
                <tr
                  key={i.id}
                  onClick={() => setActive(i)}
                  data-testid={`client-invoice-row-${i.id}`}
                  className="border-t border-foreground/5 hover:bg-foreground/[0.05] cursor-pointer transition"
                >
                  <td className="px-4 py-3 font-mono text-xs text-foreground/85">
                    {i.invoice_number}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-foreground/65">
                    {i.order_code}
                  </td>
                  <td className="px-4 py-3 text-foreground/65 whitespace-nowrap">
                    {fmtDate(i.issue_date)}
                  </td>
                  <td className="px-4 py-3 text-foreground/65 whitespace-nowrap">
                    {fmtDate(i.due_date)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">
                    {fmtCurrency(i.total_amount)}
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums font-medium ${
                      i.balance_amount > 0 ? 'text-amber-700' : 'text-emerald-700'
                    }`}
                  >
                    {fmtCurrency(i.balance_amount)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={i.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <InvoiceDrawer
        open={Boolean(active)}
        invoice={active}
        token={token}
        onClose={() => setActive(null)}
      />
    </div>
  );
}
