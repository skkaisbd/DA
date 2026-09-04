import { useState, useEffect, useCallback, useReducer, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, RefreshCw, FileText, DollarSign, Calendar, Users, Zap, CheckCircle2, Store } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, StatusBadge, EmptyState } from './moduleAtoms';
import { DataTable } from './DataTableV2';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRupiah } from '@/lib/format';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const fmt = formatRupiah;

const _INIT = { invoices: [], customers: [], accounts: [], channels: [], loading: true };
function _reducer(s, a) {
  if (a.type === 'loaded') return { ...s, ...a.data, loading: false };
  if (a.type === 'loading') return { ...s, loading: true };
  return s;
}

// Color per platform
const PLATFORM_COLORS = {
  shopee:    'bg-orange-500/15 text-orange-400 border-orange-500/30',
  tiktok:    'bg-pink-500/15 text-pink-400 border-pink-500/30',
  tokopedia: 'bg-green-500/15 text-green-400 border-green-500/30',
  maklon:    'bg-blue-500/15 text-blue-400 border-blue-500/30',
  other:     'bg-muted/15 text-muted-foreground border-border/30',
};

function ChannelBadge({ channel, channels }) {
  if (!channel) return null;
  const ch = channels.find(c => c.channel_key === channel);
  if (!ch) return <span className="text-xs text-muted-foreground">{channel}</span>;
  const cls = PLATFORM_COLORS[ch.platform] || PLATFORM_COLORS.other;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${cls}`}>
      <Store size={9} />
      {ch.channel_label}
    </span>
  );
}

export default function RahazaARInvoicesModule({ token }) {
  const [{ invoices, customers, accounts, channels, loading }, dispatch] = useReducer(_reducer, _INIT);
  const [creating, setCreating] = useState(false);
  const [paying, setPaying] = useState(null);
  const [quickPayId, setQuickPayId] = useState(null);
  const [showStatement, setShowStatement] = useState(false);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);

  const hdrs = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const refresh = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let x = false;
    dispatch({ type: 'loading' });
    const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
    Promise.all([
      fetch('/api/rahaza/ar-invoices', { headers: h }).then(r => r.json()),
      fetch('/api/rahaza/customers', { headers: h }).then(r => r.json()),
      fetch('/api/rahaza/cash-accounts', { headers: h }).then(r => r.json()),
      fetch('/api/rahaza/channel-gl-mapping', { headers: h }).then(r => r.json()),
    ]).then(([inv, cs, acc, chs]) => {
      if (x) return;
      dispatch({ type: 'loaded', data: {
        invoices: Array.isArray(inv) ? inv : [],
        customers: Array.isArray(cs) ? cs : [],
        accounts: Array.isArray(acc) ? acc : [],
        channels: Array.isArray(chs) ? chs : [],
      }});
    }).catch(() => { if (!x) dispatch({ type: 'loaded', data: {} }); });
    return () => { x = true; };
  }, [token, tick]);

  const changeStatus = useCallback(async (id, status) => {
    await fetch(`/api/rahaza/ar-invoices/${id}/status`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    setTick(t => t + 1);
  }, [token]);

  const sendInvoice = useCallback(async (id) => {
    setError('');
    const r = await fetch(`/api/rahaza/ar-invoices/${id}/send`, { method: 'POST', headers: hdrs });
    if (!r.ok) { setError(`Gagal mengirim invoice (HTTP ${r.status})`); return; }
    const data = await r.json();
    if (data._posting_result && !data._posting_result.ok) {
      setError(`Invoice terkirim tapi posting JE gagal: ${data._posting_result.error}`);
    }
    setTick(t => t + 1);
  }, [hdrs]);

  const recordPayment = useCallback(async (id, payload) => {
    const r = await fetch(`/api/rahaza/ar-invoices/${id}/payment`, {
      method: 'POST', headers: hdrs, body: JSON.stringify(payload),
    });
    if (r.ok) { setPaying(null); setTick(t => t + 1); toast.success('Pembayaran berhasil dicatat.'); }
    else { setError(`Gagal catat pembayaran (HTTP ${r.status})`); }
  }, [hdrs]);

  const quickPay = useCallback(async (inv) => {
    setQuickPayId(inv.id);
    const payload = {
      amount: inv.balance,
      account_id: accounts[0]?.id || '',
      date: new Date().toISOString().split('T')[0],
      notes: 'Lunas - Bayar Sekarang',
    };
    const r = await fetch(`/api/rahaza/ar-invoices/${inv.id}/payment`, {
      method: 'POST', headers: hdrs, body: JSON.stringify(payload),
    });
    if (r.ok) {
      setTick(t => t + 1);
      toast.success(`${inv.invoice_number} berhasil dilunasi ${fmt(inv.balance)}.`);
    } else {
      const d = await r.json().catch(() => ({}));
      toast.error(d.detail || `Gagal (HTTP ${r.status})`);
    }
    setQuickPayId(null);
  }, [hdrs, accounts]);

  const unpaidInvoices = invoices.filter(i => i.status !== 'paid' && i.balance > 0);
  const totalOutstanding = unpaidInvoices.reduce((s, i) => s + (i.balance || 0), 0);
  const totalPaid = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + (i.total || 0), 0);

  return (
    <div className="space-y-5" data-testid="rahaza-ar-invoices-page">
      <PageHeader
        icon={FileText}
        eyebrow="Portal Keuangan · AR"
        title="Invoice Penjualan (AR)"
        subtitle="Kelola piutang pelanggan. Gunakan ⚡ Bayar Sekarang untuk lunas instan, atau buka form untuk pembayaran parsial."
        actions={
          <>
            <Button variant="ghost" onClick={() => setShowStatement(true)} className="h-9 border border-[var(--glass-border)] gap-1.5"><Users className="w-3.5 h-3.5" />Statement</Button>
            <Button variant="ghost" onClick={refresh} className="h-9 border border-[var(--glass-border)]"><RefreshCw className="w-3.5 h-3.5" /></Button>
            <Button onClick={() => setCreating(true)} className="h-9 gap-1.5" data-testid="ar-create-btn"><Plus className="w-3.5 h-3.5" />Invoice Baru</Button>
          </>
        }
      />

      {error && <div className="bg-[hsl(var(--destructive)/0.12)] border border-[hsl(var(--destructive)/0.22)] rounded-lg p-3 text-sm text-[hsl(var(--destructive))]">{error}<button onClick={() => setError('')} className="ml-2 text-xs underline">Tutup</button></div>}

      {/* Outstanding alert banner */}
      {unpaidInvoices.length > 0 && (
        <div className="bg-amber-400/8 border border-amber-400/20 rounded-lg px-4 py-3 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-amber-400">{unpaidInvoices.length} invoice belum lunas · Total: {fmt(totalOutstanding)}</p>
            <p className="text-xs text-foreground/50 mt-0.5">Klik ⚡ di baris invoice untuk lunas instan dengan jumlah penuh.</p>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <ARStatTile label="Total Invoice" value={invoices.length} accent="primary" />
        <ARStatTile label="Belum Lunas" value={unpaidInvoices.length} accent="warning" />
        <ARStatTile label="Outstanding" value={fmt(totalOutstanding)} accent="danger" />
        <ARStatTile label="Total Dibayar" value={fmt(totalPaid)} accent="success" />
      </div>

      {/* Invoice table */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-[10px] uppercase tracking-wider text-foreground/50">
                <th className="px-4 py-3">Invoice</th>
                <th className="px-3 py-3">Channel</th>
                <th className="px-3 py-3">Pelanggan</th>
                <th className="px-3 py-3">Terbit</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3 text-right">Total</th>
                <th className="px-3 py-3 text-right">Balance</th>
                <th className="px-3 py-3 text-center">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="py-8"><div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-lg mx-4" />)}</div></td></tr>
              ) : invoices.length === 0 ? (
                <tr><td colSpan={8} className="py-8"><EmptyState icon={FileText} title="Belum ada invoice" description="Klik 'Invoice Baru' untuk membuat invoice penjualan pertama." /></td></tr>
              ) : invoices.map((inv, idx) => (
                <tr key={inv.id} className={`border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors ${idx % 2 === 0 ? '' : 'bg-[var(--glass-bg)]/20'}`}
                  data-testid={`ar-row-${inv.invoice_number}`}>
                  <td className="px-4 py-2">
                    <div className="font-mono text-xs font-semibold text-foreground">{inv.invoice_number}</div>
                    <div className="text-[10px] text-muted-foreground">{inv.shipment_number || '—'}</div>
                  </td>
                  <td className="px-3 py-2"><ChannelBadge channel={inv.sales_channel} channels={channels} /></td>
                  <td className="px-3 py-2 text-xs text-foreground">{inv.customer_name}</td>
                  <td className="px-3 py-2 text-xs text-foreground/70">{inv.issue_date}</td>
                  <td className="px-3 py-2"><StatusBadge status={inv.status} /></td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{fmt(inv.total)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {inv.balance > 0
                      ? <span className="text-amber-400 font-semibold">{fmt(inv.balance)}</span>
                      : <span className="text-emerald-400">Lunas</span>}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-center gap-1">
                      {/* Status controls */}
                      {inv.status === 'draft' && (
                        <button onClick={() => sendInvoice(inv.id)} className="text-[10px] px-2 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors whitespace-nowrap" data-testid={`ar-send-${inv.id}`}>Kirim</button>
                      )}
                      {inv.status === 'sent' && (
                        <button onClick={() => changeStatus(inv.id, 'overdue')} className="text-[10px] px-2 py-0.5 rounded border border-amber-400/30 bg-amber-400/10 text-amber-400 hover:bg-amber-400/20 transition-colors whitespace-nowrap">Jatuh Tempo</button>
                      )}
                      {/* Bayar form (partial) */}
                      {inv.status !== 'paid' && inv.balance > 0 && (
                        <button
                          onClick={() => setPaying(inv)}
                          className="text-[10px] px-2 py-0.5 rounded border border-[var(--glass-border)] bg-[var(--glass-bg)] text-foreground/70 hover:bg-[var(--glass-bg-hover)] transition-colors whitespace-nowrap"
                          data-testid={`ar-pay-form-${inv.id}`}
                          title="Buka form pembayaran"
                        >
                          Bayar
                        </button>
                      )}
                      {/* ⚡ Bayar Sekarang — 1-click full payment */}
                      {inv.status !== 'paid' && inv.balance > 0 && (
                        <button
                          onClick={() => quickPay(inv)}
                          disabled={quickPayId === inv.id}
                          className="h-7 px-2 rounded border border-emerald-400/30 bg-emerald-400/10 text-emerald-400 hover:bg-emerald-400/20 transition-colors flex items-center gap-1 text-[10px] font-semibold disabled:opacity-50"
                          data-testid={`ar-quick-pay-${inv.id}`}
                          title={`Lunas sekarang: ${fmt(inv.balance)}`}
                        >
                          {quickPayId === inv.id
                            ? <RefreshCw className="w-3 h-3 animate-spin" />
                            : <Zap className="w-3 h-3" />}
                          Lunas
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Create Invoice Modal */}
      {creating && <CreateInvoiceModal token={token} customers={customers} channels={channels} onClose={() => setCreating(false)} onCreated={refresh} />}

      {/* Payment Modal */}
      {paying && (
        <PaymentModal
          invoice={paying}
          accounts={accounts}
          onClose={() => setPaying(null)}
          onPay={(payload) => recordPayment(paying.id, payload)}
        />
      )}

      {/* Statement Modal */}
      {showStatement && <CustomerStatementModal token={token} customers={customers} onClose={() => setShowStatement(false)} />}
    </div>
  );
}

function ARStatTile({ label, value, accent }) {
  const accents = {
    primary: 'border-[hsl(var(--primary)/0.25)] bg-[hsl(var(--primary)/0.08)] text-[hsl(var(--primary))]',
    warning: 'border-[hsl(var(--warning)/0.25)] bg-[hsl(var(--warning)/0.08)] text-[hsl(var(--warning))]',
    danger:  'border-[hsl(var(--destructive)/0.25)] bg-[hsl(var(--destructive)/0.08)] text-[hsl(var(--destructive))]',
    success: 'border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success)/0.08)] text-[hsl(var(--success))]',
  };
  return (
    <div className={`rounded-[var(--radius-lg)] border p-3 ${accents[accent] || 'border-[var(--glass-border)] bg-[var(--glass-bg)]'}`}>
      <p className="text-[10px] uppercase tracking-wider text-foreground/50">{label}</p>
      <p className="text-lg font-bold mt-0.5 font-mono">{value}</p>
    </div>
  );
}

function CreateInvoiceModal({ token, customers, channels, onClose, onCreated }) {
  const today = new Date().toISOString().split('T')[0];
  const [form, setForm] = useState({ customer_id: '', issue_date: today, due_date: '', notes: '', sales_channel: '' });
  const [items, setItems] = useState([{ description: '', qty: 1, unit_price: 0 }]);
  const [saving, setSaving] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  // SESI #27 — nomor invoice AR mengikuti kebijakan Otomatis/Manual milik owner
  // (ditegakkan sejak sesi #18, tetapi kolomnya belum pernah ada di layar ini).
  const numPolicy = useDocNumberPolicy('rahaza_ar_invoices.invoice_number', token);
  const [invNumber, setInvNumber] = useState('');

  const total = items.reduce((s, i) => s + (Number(i.qty) * Number(i.unit_price)), 0);

  const submit = async () => {
    setSaving(true);
    try {
      const r = await fetch('/api/rahaza/ar-invoices', {
        method: 'POST', headers,
        body: JSON.stringify({ ...form, items,
                               ...docNumberPayload(numPolicy, 'invoice_number', invNumber) }),
      });
      if (r.ok) { onCreated(); onClose(); }
    } finally { setSaving(false); }
  };

  // Group channels by platform
  const platforms = [...new Set(channels.map(c => c.platform))].sort();
  const selectedChannel = channels.find(c => c.channel_key === form.sales_channel);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-foreground mb-4">Invoice Baru</h2>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground uppercase block mb-1">Pelanggan *</label>
            <SmartNativeSelect value={form.customer_id} onChange={e => setForm({ ...form, customer_id: e.target.value })} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="ar-create-customer">
              <option value="">— Pilih —</option>
              {customers.map(c => <option key={c.id} value={c.id}>{`${c.code} · ${c.name}`}</option>)}
            </SmartNativeSelect>
          </div>
          {/* Sales Channel — routing GL otomatis */}
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground uppercase block mb-1">
              Channel Penjualan
              <span className="normal-case ml-1 text-[10px] text-primary/70">(menentukan akun pendapatan otomatis)</span>
            </label>
            <SmartNativeSelect
              value={form.sales_channel}
              onChange={e => setForm({ ...form, sales_channel: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="ar-create-channel"
            >
              <option value="">— Default (Maklon/Umum) —</option>
              {platforms.map(platform => (
                <optgroup key={platform} label={platform.toUpperCase()}>
                  {channels.filter(c => c.platform === platform).map(c => (
                    <option key={c.channel_key} value={c.channel_key}>{c.channel_label}</option>
                  ))}
                </optgroup>
              ))}
            </SmartNativeSelect>
            {selectedChannel && (
              <p className="text-[10px] text-muted-foreground mt-1">
                Auto-post: Dr <span className="font-mono text-primary">{selectedChannel.debit_ar}</span> / Cr <span className="font-mono text-primary">{selectedChannel.credit_revenue}</span>
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-muted-foreground uppercase block mb-1">Tgl Terbit</label>
            <GlassInput type="date" value={form.issue_date} onChange={e => setForm({ ...form, issue_date: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground uppercase block mb-1">Jatuh Tempo</label>
            <GlassInput type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
          </div>
        </div>
        {/* Items */}
        <div className="space-y-2 mb-4">
          <div className="flex items-center justify-between">
            <label className="text-xs text-muted-foreground uppercase">Item Invoice</label>
            <button onClick={() => setItems(p => [...p, { description: '', qty: 1, unit_price: 0 }])} className="text-xs text-primary hover:underline" data-testid="ar-add-item-btn">+ Tambah Baris</button>
          </div>
          {items.map((item, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <input value={item.description} onChange={e => setItems(p => p.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} placeholder="Deskripsi" className="col-span-6 h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground" data-testid={`ar-item-desc-${i}`} />
              <input type="number" value={item.qty} onChange={e => setItems(p => p.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))} className="col-span-2 h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground text-right font-mono" data-testid={`ar-item-qty-${i}`} />
              <input type="number" value={item.unit_price} onChange={e => setItems(p => p.map((x, j) => j === i ? { ...x, unit_price: e.target.value } : x))} className="col-span-3 h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground text-right font-mono" placeholder="Harga" data-testid={`ar-item-price-${i}`} />
              <button onClick={() => setItems(p => p.filter((_, j) => j !== i))} className="col-span-1 h-9 grid place-items-center text-red-400 hover:text-red-300 text-lg">×</button>
            </div>
          ))}
          <div className="text-right text-sm font-semibold text-foreground">Total: {fmt(total)}</div>
        </div>
        <div>
          <label className="text-xs text-muted-foreground uppercase block mb-1">Catatan</label>
          <GlassInput value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Opsional" />
        </div>
        <DocNumberField
          policy={numPolicy} value={invNumber} onChange={setInvNumber}
          testId="ar-inv-docnum" label="Nomor Invoice" />
        <div className="flex gap-2 mt-6 justify-end">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button>
          <Button onClick={submit} disabled={saving || !form.customer_id} data-testid="ar-create-submit">{saving ? 'Menyimpan...' : 'Buat Invoice'}</Button>
        </div>
      </GlassCard>
    </div>
  );
}

function PaymentModal({ invoice, accounts, onClose, onPay }) {
  const [amount, setAmount] = useState(invoice.balance);
  const [account_id, setAccount] = useState(accounts[0]?.id || '');
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [notes, setNotes] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-md w-full" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-foreground mb-2">Record Pembayaran</h2>
        <p className="text-xs text-muted-foreground mb-4">{invoice.invoice_number} · Balance: {fmt(invoice.balance)}</p>
        <div className="space-y-3">
          <div><label className="text-xs uppercase text-muted-foreground">Jumlah</label><GlassInput type="number" min={0} step="1000" value={amount} onChange={e => setAmount(Number(e.target.value))} data-testid="ar-pay-amount" /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Rekening</label><SmartNativeSelect value={account_id} onChange={e => setAccount(e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="ar-pay-account"><option value="">— Tidak link ke rekening —</option>{accounts.map(a => <option key={a.id} value={a.id}>{`${a.code} · ${a.name} (${fmt(a.balance)})`}</option>)}</SmartNativeSelect></div>
          <div><label className="text-xs uppercase text-muted-foreground">Tanggal</label><GlassInput type="date" value={date} onChange={e => setDate(e.target.value)} /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Catatan</label><GlassInput value={notes} onChange={e => setNotes(e.target.value)} /></div>
        </div>
        <div className="flex gap-2 mt-6 justify-end"><Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button><Button onClick={() => onPay({ amount, account_id, date, notes })} data-testid="ar-pay-submit"><DollarSign className="w-4 h-4 mr-1.5" />Simpan</Button></div>
      </GlassCard>
    </div>
  );
}

function CustomerStatementModal({ token, customers, onClose }) {
  const today = new Date().toISOString().split('T')[0];
  const firstOfMonth = today.slice(0, 7) + '-01';
  const [customer_id, setCustomerId] = useState(customers[0]?.id || '');
  const [date_from, setFrom] = useState(firstOfMonth);
  const [date_to, setTo] = useState(today);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const fmt2 = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

  const load = async () => {
    if (!customer_id) { setErr('Pilih pelanggan dulu'); return; }
    setErr(''); setLoading(true); setData(null);
    try {
      const url = `/api/rahaza/customer-statement/${customer_id}?date_from=${date_from}&date_to=${date_to}`;
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) { setErr(`Gagal memuat (HTTP ${r.status})`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-3xl w-full max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-xl font-bold text-foreground flex items-center gap-2"><Users className="w-5 h-5 text-primary" /> Statement Pelanggan</h2>
          <button onClick={onClose} className="text-foreground/60 hover:text-foreground">✕</button>
        </div>
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="col-span-2">
            <label className="text-xs uppercase text-muted-foreground mb-1 block">Pelanggan</label>
            <SmartNativeSelect value={customer_id} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="stmt-customer">
              <option value="">— Pilih —</option>
              {customers.map(c => <option key={c.id} value={c.id}>{`${c.code} · ${c.name}`}</option>)}
            </SmartNativeSelect>
          </div>
          <div><label className="text-xs uppercase text-muted-foreground mb-1 block">Dari</label><GlassInput type="date" value={date_from} onChange={e => setFrom(e.target.value)} /></div>
          <div><label className="text-xs uppercase text-muted-foreground mb-1 block">Sampai</label><GlassInput type="date" value={date_to} onChange={e => setTo(e.target.value)} /></div>
        </div>
        <div className="flex justify-end mb-3">
          <Button onClick={load} disabled={loading} data-testid="stmt-load"><Calendar className="w-4 h-4 mr-1.5" /> {loading ? 'Memuat...' : 'Tampilkan'}</Button>
        </div>
        {err && <div className="bg-[hsl(var(--destructive)/0.12)] border border-[hsl(var(--destructive)/0.22)] rounded-lg p-3 text-sm text-[hsl(var(--destructive))] mb-3">{err}</div>}
        {data && (
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-2">
              <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3"><p className="text-[10px] uppercase text-muted-foreground">Invoice</p><p className="text-lg font-bold font-mono">{data.summary.count}</p></div>
              <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3"><p className="text-[10px] uppercase text-muted-foreground">Total Tagihan</p><p className="text-sm font-bold font-mono">{fmt2(data.summary.total_billed)}</p></div>
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/8 p-3"><p className="text-[10px] uppercase text-muted-foreground">Dibayar</p><p className="text-sm font-bold font-mono text-emerald-400">{fmt2(data.summary.total_paid)}</p></div>
              <div className="rounded-lg border border-amber-400/20 bg-amber-400/8 p-3"><p className="text-[10px] uppercase text-muted-foreground">Outstanding</p><p className="text-sm font-bold font-mono text-amber-400">{fmt2(data.summary.outstanding)}</p></div>
            </div>
          </div>
        )}
        <div className="flex justify-end mt-6">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Tutup</Button>
        </div>
      </GlassCard>
    </div>
  );
}
