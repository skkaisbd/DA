import { useState, useEffect, useCallback, useMemo } from 'react';
import { Banknote, RefreshCw, FileText, Eye, CreditCard, X, AlertCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { fetchMaklonOrders, posToLegacyOrders } from '@/lib/maklonOrderAdapter';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import OnwardCTA from './OnwardCTA';
import { formatRupiah } from '@/lib/format';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_CONFIG = {
  draft:        { label: 'Draft',        color: 'bg-muted text-foreground border-border dark:bg-slate-500/15 dark:text-foreground/70 dark:border-slate-400/30' },
  issued:       { label: 'Diterbitkan',  color: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400/30' },
  partial_paid: { label: 'Partial',      color: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/30' },
  paid:         { label: 'Lunas',        color: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-500/15 dark:text-green-300 dark:border-green-400/30' },
  overdue:      { label: 'Overdue',      color: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-400/30' },
  cancelled:    { label: 'Dibatalkan',   color: 'bg-muted text-muted-foreground border-border dark:bg-slate-500/15 dark:text-muted-foreground dark:border-slate-400/30' },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return <span className={`inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>{c.label}</span>;
}

const fmt = formatRupiah;

export default function MaklonBillingModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [invoices, setInvoices] = useState([]);
  const [eligibleOrders, setEligibleOrders] = useState([]);
  const [summary, setSummary] = useState({});
  const [aging, setAging] = useState({ buckets: {}, rows: [] });
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('invoices');
  const [generateDialog, setGenerateDialog] = useState(false);
  const [viewDialog, setViewDialog] = useState(null);
  const [payDialog, setPayDialog] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [inv, elig, sum, ag] = await Promise.all([
        fetch('/api/dewi/maklon/invoices', { headers }),
        fetch('/api/dewi/maklon/invoices/eligible', { headers }),
        fetch('/api/dewi/maklon/reports/billing-summary', { headers }),
        fetch('/api/dewi/maklon/reports/aging', { headers }),
      ]);
      if (inv.ok) setInvoices(await inv.json());
      // SATU SUMBER: daftar PO yang bisa ditagih + pratinjau qty/nilai dihitung server
      // (rumus yang sama dengan dokumen yang terbit) — bukan ditebak di browser.
      if (elig.ok) setEligibleOrders(await elig.json());
      if (sum.ok) setSummary(await sum.json());
      if (ag.ok) setAging(await ag.json());
    } catch (e) { toast.error('Gagal memuat data billing'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const cancelInvoice = async (inv) => {
    if (!window.confirm(`Batalkan invoice ${inv.invoice_number}?`)) return;
    const r = await fetch(`/api/dewi/maklon/invoices/${inv.id}/cancel`, { method: 'POST', headers });
    if (r.ok) { toast.success('Invoice dibatalkan'); fetchAll(); }
    else toast.error((await r.json()).detail || 'Gagal');
  };

  const printInvoicePdf = async (inv) => {
    try {
      const res = await fetch(`/api/dewi/maklon/invoices/${inv.id}/pdf`, { headers: { Authorization: headers.Authorization } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `Invoice_${inv.invoice_number || inv.id}.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('PDF invoice berhasil diunduh');
    } catch (e) { toast.error('Gagal mengunduh PDF invoice'); }
  };

  const stats = [
    { label: 'Total Invoice',   value: summary.total_invoices || 0,          color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-400/20' },
    { label: 'Total Tagihan',   value: fmt(summary.total_billed),             color: 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-500/10 border-cyan-400/20' },
    { label: 'Sudah Dibayar',   value: fmt(summary.total_paid),               color: 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border-green-300 dark:border-green-400/20' },
    { label: 'Outstanding',     value: fmt(summary.total_outstanding),        color: 'text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border-amber-400/20' },
    { label: 'Overdue',         value: `${summary.overdue_count || 0} (${fmt(summary.overdue_amount)})`, color: 'text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border-red-300 dark:border-red-400/20' },
  ];

  const { page, setPage, totalPages, total, paged } = useClientPagination(invoices, 10);
  return (
    <div className="p-6 space-y-6" data-testid="maklon-billing">
      <PageHeader
        title="Invoice & Billing Maklon"
        subtitle="Generate invoice dari order, kelola payment, laporan aging"
        icon={Banknote}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={fetchAll} className="gap-2" data-testid="billing-refresh-btn">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button size="sm" onClick={() => setGenerateDialog(true)} className="gap-1.5" data-testid="billing-generate-btn">
              <FileText className="w-3.5 h-3.5" /> Generate Invoice
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
            <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
              <div className="text-xs text-foreground/50">{s.label}</div>
              <div className={`text-lg font-bold mt-1 ${s.color.split(' ')[0]}`}>{s.value}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      {/* RC-FLOW-UX: onward — Maklon Invoice → Piutang (AR) / PO 360 (Alur 10) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'fin-ar-invoices', label: 'Piutang / AR Invoice', icon: Banknote, primary: true, hint: 'Kelola tagihan & pembayaran di Keuangan' },
          { module: 'maklon-po-360', label: 'Lihat PO 360°', icon: FileText, hint: 'Status menyeluruh PO maklon' },
        ]}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="aging">Aging Report</TabsTrigger>
        </TabsList>

        <TabsContent value="invoices">
          <GlassCard className="p-5">
            {loading ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Memuat...</div>
            ) : invoices.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada invoice</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="invoices-table">
                  <thead><tr className="border-b border-foreground/5 text-xs text-foreground/50">
                    <th className="pb-2 text-left">Invoice #</th>
                    <th className="pb-2 text-left">Klien</th>
                    <th className="pb-2 text-left">Order</th>
                    <th className="pb-2 text-left">Issue</th>
                    <th className="pb-2 text-left">Due</th>
                    <th className="pb-2 text-right">Total</th>
                    <th className="pb-2 text-right">Paid</th>
                    <th className="pb-2 text-right">Balance</th>
                    <th className="pb-2 text-left">Status</th>
                    <th className="pb-2 text-center">Aksi</th>
                  </tr></thead>
                  <tbody className="divide-y divide-white/5">
                    {paged.map(i => (
                      <tr key={i.id} className="hover:bg-foreground/[0.03]">
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/80">{i.invoice_number}</td>
                        <td className="py-2.5 pr-3 text-foreground">{i.client_name}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/60">{i.order_code}</td>
                        <td className="py-2.5 pr-3 text-xs text-foreground/60">{i.issue_date}</td>
                        <td className="py-2.5 pr-3 text-xs text-foreground/60">{i.due_date}</td>
                        <td className="py-2.5 pr-3 text-right">{fmt(i.total_amount)}</td>
                        <td className="py-2.5 pr-3 text-right text-green-700 dark:text-green-400">{fmt(i.paid_amount)}</td>
                        <td className="py-2.5 pr-3 text-right text-amber-600 dark:text-amber-300 font-semibold">{fmt(i.balance_amount)}</td>
                        <td className="py-2.5 pr-3"><StatusBadge status={i.status} /></td>
                        <td className="py-2.5">
                          <div className="flex gap-1 justify-center">
                            <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setViewDialog(i)} title="Detail"><Eye className="w-3.5 h-3.5" /></Button>
                            <Button size="icon" variant="ghost" className="w-7 h-7 text-blue-700 dark:text-blue-400" onClick={() => printInvoicePdf(i)} title="Cetak PDF (Invoice)" data-testid={`maklon-invoice-print-${i.id}`}><FileText className="w-3.5 h-3.5" /></Button>
                            {['issued','partial_paid','overdue'].includes(i.status) && (
                              <Button size="icon" variant="ghost" className="w-7 h-7 text-green-700 dark:text-green-400" onClick={() => setPayDialog(i)} title="Bayar"><CreditCard className="w-3.5 h-3.5" /></Button>
                            )}
                            {i.status !== 'cancelled' && i.paid_amount === 0 && (
                              <Button size="icon" variant="ghost" className="w-7 h-7 text-red-700 dark:text-red-400" onClick={() => cancelInvoice(i)} title="Batal"><X className="w-3.5 h-3.5" /></Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </div>
            )}
          </GlassCard>
        </TabsContent>

        <TabsContent value="aging">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
            {['current','1_30','31_60','61_90','over_90'].map(k => {
              const labels = {current:'Current',1_30:'1-30 hari',31_60:'31-60',61_90:'61-90',over_90:'> 90'};
              const colors = {current:'text-green-700 dark:text-green-400',1_30:'text-amber-700 dark:text-amber-400',31_60:'text-orange-400',61_90:'text-red-700 dark:text-red-400',over_90:'text-red-700 dark:text-red-500'};
              return (
                <GlassCard key={k} className="p-4">
                  <div className="text-xs text-foreground/50">{labels[k]}</div>
                  <div className={`text-lg font-bold mt-1 ${colors[k]}`}>{fmt(aging.buckets?.[k])}</div>
                </GlassCard>
              );
            })}
          </div>
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-3">Outstanding Invoices</h3>
            {(aging.rows || []).length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Tidak ada invoice outstanding</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-foreground/5 text-xs text-foreground/50">
                    <th className="pb-2 text-left">Invoice</th><th className="pb-2 text-left">Klien</th>
                    <th className="pb-2 text-left">Due</th><th className="pb-2 text-right">Outstanding</th>
                    <th className="pb-2 text-center">Overdue</th><th className="pb-2 text-left">Bucket</th>
                  </tr></thead>
                  <tbody className="divide-y divide-white/5">
                    {(aging.rows || []).map((r, i) => (
                      <tr key={i}>
                        <td className="py-2 font-mono text-xs text-foreground/80">{r.invoice_number}</td>
                        <td className="py-2">{r.client_name}</td>
                        <td className="py-2 text-xs text-foreground/60">{r.due_date}</td>
                        <td className="py-2 text-right font-semibold">{fmt(r.balance_amount)}</td>
                        <td className="py-2 text-center text-xs">{r.days_overdue > 0 ? `${r.days_overdue}d` : '-'}</td>
                        <td className="py-2 text-xs"><span className={`font-semibold ${r.bucket === 'current' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>{r.bucket}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>
        </TabsContent>
      </Tabs>

      {generateDialog && (
        <GenerateDialog orders={eligibleOrders} headers={headers}
          onClose={() => setGenerateDialog(false)}
          onSuccess={() => { setGenerateDialog(false); fetchAll(); }}
        />
      )}
      {viewDialog && <ViewInvoiceDialog invoice={viewDialog} headers={headers} onClose={() => setViewDialog(null)} />}
      {payDialog && (
        <PaymentDialog invoice={payDialog} headers={headers}
          onClose={() => setPayDialog(null)}
          onSuccess={() => { setPayDialog(null); fetchAll(); }}
        />
      )}
    </div>
  );
}

function GenerateDialog({ orders, headers, onClose, onSuccess }) {
  const [orderId, setOrderId] = useState('');
  const [taxPct, setTaxPct] = useState('');
  const [terms, setTerms] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  // SESI #27 — nomor invoice maklon mengikuti kebijakan Otomatis/Manual milik owner
  // (ditegakkan sejak sesi #18, tetapi kolomnya belum pernah ada di layar ini).
  const numPolicy = useDocNumberPolicy('dewi_maklon_invoices.invoice_number',
                                       localStorage.getItem('erp_token'));
  const [invNumber, setInvNumber] = useState('');
  const selected = orders.find(o => o.id === orderId);

  const gen = async () => {
    if (!orderId) { toast.error('Pilih PO'); return; }
    setSaving(true);
    const payload = { order_id: orderId };
    if (taxPct) payload.tax_pct = Number(taxPct);
    if (terms) payload.payment_terms = terms;
    if (notes) payload.notes = notes;
    if (selected?.source !== 'engine_ar') Object.assign(payload, docNumberPayload(numPolicy, 'invoice_number', invNumber));
    const r = await fetch('/api/dewi/maklon/invoices/generate', { method: 'POST', headers, body: JSON.stringify(payload) });
    setSaving(false);
    if (r.ok) {
      const inv = await r.json();
      toast.success(`Invoice ${inv.invoice_number} dibuat`);
      onSuccess();
    } else {
      toast.error((await r.json()).detail || 'Gagal');
    }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="generate-invoice-dialog">
        <DialogHeader><DialogTitle>Generate Invoice</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          {orders.length === 0 ? (
            <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-400/30 rounded p-3 text-sm text-amber-600 dark:text-amber-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              Tidak ada order yang bisa diinvoice. Order harus sudah dikonfirmasi dan belum punya invoice.
            </div>
          ) : (
            <>
              <div className="space-y-1">
                <Label>Order *</Label>
                <Select value={orderId} onValueChange={setOrderId}>
                  <SelectTrigger data-testid="gen-order-select"><SelectValue placeholder="Pilih PO..." /></SelectTrigger>
                  <SelectContent>
                    {orders.map(o => (
                      <SelectItem key={o.id} value={o.id} disabled={!o.billable}>
                        {o.po_number} — {o.client_name} · terkirim {o.total_received}/{o.total_ordered} pcs · Rp {Number(o.subtotal || 0).toLocaleString('id-ID')}
                        {!o.billable ? ' (belum ada kiriman)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selected?.source === 'engine_ar' && (
                  <p className="text-xs text-muted-foreground" data-testid="gen-engine-ar-note">
                    Menerbitkan AR otomatis <b>{selected.ar_invoice_number}</b>: {selected.line_count} baris,
                    qty = yang diterima klien × harga jasa (selling price). Nomor mengikuti AR — tidak dibuat nomor baru.
                  </p>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1"><Label>PPN % (opsional)</Label><Input type="number" placeholder="default config" value={taxPct} onChange={e => setTaxPct(e.target.value)} /></div>
                <div className="space-y-1">
                  <Label>Payment Terms</Label>
                  <Select value={terms} onValueChange={setTerms}>
                    <SelectTrigger><SelectValue placeholder="default config" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="net_7">Net 7</SelectItem>
                      <SelectItem value="net_14">Net 14</SelectItem>
                      <SelectItem value="net_30">Net 30</SelectItem>
                      <SelectItem value="net_60">Net 60</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1"><Label>Catatan</Label><Textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} /></div>
              {selected?.source !== 'engine_ar' && (
                <DocNumberField
                  policy={numPolicy} value={invNumber} onChange={setInvNumber}
                  testId="maklon-inv-docnum" label="Nomor Invoice" />
              )}
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={gen} disabled={saving || orders.length === 0} data-testid="gen-save-btn">{saving ? 'Generating...' : 'Generate'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaymentDialog({ invoice, headers, onClose, onSuccess }) {
  const [amount, setAmount] = useState(invoice.balance_amount || 0);
  const [method, setMethod] = useState('transfer');
  const [ref, setRef] = useState('');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [cashAccounts, setCashAccounts] = useState([]);
  const [cashAccountId, setCashAccountId] = useState('');
  useEffect(() => {
    fetch('/api/rahaza/cash-accounts', { headers })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setCashAccounts(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [headers]);

  const save = async () => {
    if (!amount || Number(amount) <= 0) { toast.error('Jumlah pembayaran wajib'); return; }
    setSaving(true);
    const r = await fetch('/api/dewi/maklon/payments', { method: 'POST', headers, body: JSON.stringify({
      invoice_id: invoice.id, amount: Number(amount), method, reference_no: ref, payment_date: date, notes,
      cash_account_id: cashAccountId || null,
    })});
    setSaving(false);
    if (r.ok) {
      const d = await r.json();
      if (d.gl_error) toast.warning(`Pembayaran dicatat, jurnal GL gagal: ${d.gl_error}`);
      else toast.success(`Pembayaran dicatat${d.gl_je_number ? ` · Jurnal ${d.gl_je_number}` : ''}`);
      onSuccess();
    }
    else toast.error((await r.json()).detail || 'Gagal');
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="payment-dialog">
        <DialogHeader><DialogTitle>Catat Pembayaran — {invoice.invoice_number}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="bg-foreground/5 rounded p-3 text-sm grid grid-cols-2 gap-2">
            <div>Total: <span className="font-semibold">{fmt(invoice.total_amount)}</span></div>
            <div>Paid: <span className="font-semibold text-green-700 dark:text-green-400">{fmt(invoice.paid_amount)}</span></div>
            <div className="col-span-2 text-amber-600 dark:text-amber-300">Outstanding: <span className="font-semibold">{fmt(invoice.balance_amount)}</span></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>Jumlah *</Label><Input type="number" min="0" value={amount} onChange={e => setAmount(e.target.value)} data-testid="pay-amount-input" /></div>
            <div className="space-y-1">
              <Label>Metode</Label>
              <Select value={method} onValueChange={setMethod}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="transfer">Transfer</SelectItem>
                  <SelectItem value="cash">Cash</SelectItem>
                  <SelectItem value="check">Cek</SelectItem>
                  <SelectItem value="giro">Giro</SelectItem>
                  <SelectItem value="other">Lainnya</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>Tgl Bayar</Label><Input type="date" value={date} onChange={e => setDate(e.target.value)} /></div>
            <div className="space-y-1"><Label>No. Referensi</Label><Input value={ref} onChange={e => setRef(e.target.value)} placeholder="TF-001" /></div>
            <div className="space-y-1 col-span-2">
              <Label>Rekening Kas/Bank Penerima</Label>
              <Select value={cashAccountId} onValueChange={setCashAccountId}>
                <SelectTrigger data-testid="pay-cash-account-select"><SelectValue placeholder="Default profil (Bank BCA) — pilih untuk mutasi kas" /></SelectTrigger>
                <SelectContent>
                  {cashAccounts.map(a => (
                    <SelectItem key={a.id} value={a.id}>{a.name}{a.gl_account_code ? ` · ${a.gl_account_code}` : ''}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 col-span-2"><Label>Catatan</Label><Textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="pay-save-btn">{saving ? 'Menyimpan...' : 'Catat'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ViewInvoiceDialog({ invoice, headers, onClose }) {
  const [detail, setDetail] = useState(invoice);
  const [downloading, setDownloading] = useState(false);
  useEffect(() => {
    fetch(`/api/dewi/maklon/invoices/${invoice.id}`, { headers })
      .then(r => r.ok && r.json())
      .then(d => d && setDetail(d))
      .catch(() => {});
  }, [invoice.id, headers]);

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`/api/dewi/maklon/invoices/${invoice.id}/pdf`, {
        headers: { Authorization: headers.Authorization },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Invoice_${detail.invoice_number || invoice.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('PDF invoice berhasil diunduh');
    } catch (e) {
      toast.error('Gagal mengunduh PDF invoice');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Invoice Detail — {detail.invoice_number}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div><span className="text-foreground/50">Klien:</span> <span className="font-semibold">{detail.client_name}</span></div>
            <div><span className="text-foreground/50">Order:</span> <span className="font-mono text-xs">{detail.order_code}</span></div>
            <div><span className="text-foreground/50">Tgl Terbit:</span> {detail.issue_date}</div>
            <div><span className="text-foreground/50">Jatuh Tempo:</span> {detail.due_date}</div>
            <div><span className="text-foreground/50">Terms:</span> {detail.payment_terms}</div>
            <div><span className="text-foreground/50">PPN:</span> {detail.tax_pct}%</div>
          </div>

          <div className="rounded-xl border pt-3 border-t border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <div className="text-xs font-semibold text-foreground/60 mb-2">Line Items</div>
            <table className="w-full text-xs">
              <thead><tr className="text-foreground/50"><th className="text-left pb-1">Deskripsi</th><th className="text-right pb-1">Qty</th><th className="text-right pb-1">Harga</th><th className="text-right pb-1">Subtotal</th></tr></thead>
              <tbody>{(detail.lines || []).map((l, i) => (
                <tr key={i}><td className="py-1">{l.description}</td><td className="text-right">{l.qty} {l.unit}</td><td className="text-right">{fmt(l.unit_price)}</td><td className="text-right font-semibold">{fmt(l.line_total)}</td></tr>
              ))}</tbody>
            </table>
          </div>

          <div className="border-t border-foreground/10 pt-3 space-y-1 text-right">
            <div>Subtotal: <span className="font-semibold">{fmt(detail.subtotal)}</span></div>
            {detail.discount_amount > 0 && <div>Diskon: <span className="text-red-700 dark:text-red-400">- {fmt(detail.discount_amount)}</span></div>}
            <div>PPN ({detail.tax_pct}%): <span>{fmt(detail.tax_amount)}</span></div>
            <div className="text-base font-bold">Total: {fmt(detail.total_amount)}</div>
            <div className="text-green-700 dark:text-green-400">Dibayar: {fmt(detail.paid_amount)}</div>
            <div className="text-amber-600 dark:text-amber-300 font-semibold">Saldo: {fmt(detail.balance_amount)}</div>
            <div>Status: <StatusBadge status={detail.status} /></div>
          </div>

          {detail.payments && detail.payments.length > 0 && (
            <div className="pt-3 border-t border-foreground/10">
              <div className="text-xs font-semibold text-foreground/60 mb-2">Riwayat Pembayaran</div>
              <div className="space-y-1 text-xs">
                {detail.payments.map(p => (
                  <div key={p.id} className="flex justify-between bg-foreground/5 rounded px-2 py-1">
                    <span>{p.payment_date} · {p.method}{p.reference_no ? ` · ${p.reference_no}` : ''}</span>
                    <span className="font-semibold text-green-700 dark:text-green-400">{fmt(p.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Tutup</Button>
          <Button onClick={downloadPdf} disabled={downloading} data-testid="maklon-invoice-print-pdf" className="gap-2">
            <FileText className="w-4 h-4" />
            {downloading ? 'Menyiapkan…' : 'Cetak PDF (Invoice)'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
