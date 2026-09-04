/**
 * SupplierInvoiceModule — Faktur Supplier (AP dari Penerimaan)
 *
 * Menutup langkah terakhir siklus pengadaan (P2P) di dalam satu portal:
 *   PO → Penerimaan (GR) → **Faktur Supplier** → Persetujuan → Bayar.
 *
 * Nilai faktur memakai qty NET (diterima − ditolak) × harga per satuan DASAR
 * (INV-UOM-1), tetapi ditampilkan juga dalam satuan beli PO supaya cocok dengan
 * dokumen fisik dari supplier.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, Banknote, CheckCircle2, ClipboardCheck, FileText, Filter,
  RefreshCw, Search, Send, Truck,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import Modal from '../Modal';
import { toast } from 'sonner';
import { EP, apiGet, apiPost, fmtDate, fmtNum, fmtRp } from './procApi';

const AP_STATUS_META = {
  draft: { label: 'Draft', cls: 'bg-muted text-muted-foreground border-border' },
  sent: { label: 'Terkirim', cls: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-400/15 dark:text-blue-300 dark:border-blue-400/30' },
  partially_paid: { label: 'Dibayar Sebagian', cls: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-400/15 dark:text-amber-300 dark:border-amber-400/30' },
  paid: { label: 'Lunas', cls: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-400/15 dark:text-emerald-300 dark:border-emerald-400/30' },
  cancelled: { label: 'Dibatalkan', cls: 'bg-muted text-muted-foreground border-border' },
};

function ApBadge({ status }) {
  const m = AP_STATUS_META[status] || AP_STATUS_META.draft;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.cls}`}>
      {m.label}
    </span>
  );
}

function CreateInvoiceModal({ token, gr, onClose, onCreated }) {
  const [taxPct, setTaxPct] = useState(0);
  const [invNo, setInvNo] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const subtotal = Number(gr?.receivable_amount || 0);
  const tax = Math.round(subtotal * Number(taxPct || 0)) / 100;
  const total = subtotal + tax;

  const submit = async () => {
    setErr('');
    setSaving(true);
    try {
      const out = await apiPost(token, EP.apFromGr, {
        gr_ids: [gr.id],
        tax_pct: Number(taxPct || 0),
        due_date: dueDate || undefined,
        notes: notes || undefined,
      });
      toast.success(`Faktur ${out?.invoice_number} dibuat dari ${gr.receipt_number}`);
      onCreated?.(out);
      onClose();
    } catch (e) {
      setErr(e.message);
      toast.error(e.message);
    } finally { setSaving(false); }
  };

  return (
    <Modal onClose={onClose} title={`Buat Faktur dari ${gr.receipt_number}`} size="lg">
      <div className="space-y-4" data-testid="ap-create-modal">
        {err && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm">
            {err}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-xs text-muted-foreground">Supplier</div>
            <div className="font-medium">{gr.supplier_name}</div>
            {gr.supplier_code && <div className="text-xs font-mono text-muted-foreground">{gr.supplier_code}</div>}
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Referensi PO</div>
            <div className="font-mono text-xs">{gr.po_number || '—'}</div>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-3 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Qty diterima</span>
            <span className="tabular-nums">{fmtNum(gr.total_received)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Qty ditolak (tidak difakturkan)</span>
            <span className="tabular-nums text-red-600 dark:text-red-400">−{fmtNum(gr.total_rejected)}</span>
          </div>
          <div className="flex justify-between font-medium border-t border-[var(--glass-border)] pt-1">
            <span>Qty bersih difakturkan</span>
            <span className="tabular-nums">{fmtNum(gr.total_net)}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">No. Faktur Supplier</label>
            <GlassInput value={invNo} onChange={(e) => setInvNo(e.target.value)}
                        placeholder="opsional" data-testid="ap-form-supplier-invno" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">PPN (%)</label>
            <GlassInput type="number" min="0" max="100" value={taxPct}
                        onChange={(e) => setTaxPct(e.target.value)} className="text-right"
                        data-testid="ap-form-tax" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Jatuh Tempo</label>
            <GlassInput type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                        data-testid="ap-form-duedate" />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Catatan</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows="2"
            className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
            data-testid="ap-form-notes" />
        </div>

        <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-3 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Subtotal</span>
            <span className="tabular-nums" data-testid="ap-form-subtotal">{fmtRp(subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">PPN {taxPct || 0}%</span>
            <span className="tabular-nums">{fmtRp(tax)}</span>
          </div>
          <div className="flex justify-between font-bold border-t border-[var(--glass-border)] pt-1">
            <span>Total</span>
            <span className="tabular-nums" data-testid="ap-form-total">{fmtRp(total)}</span>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
          <Button variant="secondary" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving} data-testid="ap-form-submit">
            {saving ? 'Menyimpan...' : 'Buat Faktur'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function InvoiceDetail({ inv, onClose, onSend, sending }) {
  return (
    <Modal onClose={onClose} title={`Faktur ${inv.invoice_number}`} size="2xl">
      <div className="space-y-4" data-testid="ap-detail">
        <div className="flex items-center gap-2 flex-wrap">
          <ApBadge status={inv.status} />
          {inv.supplier_code && (
            <span className="text-xs font-mono px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
              {inv.supplier_code}
            </span>
          )}
          {(inv.po_numbers || []).map((p) => (
            <span key={p} className="text-xs px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
              PO {p}
            </span>
          ))}
          {(inv.gr_numbers || []).map((g) => (
            <span key={g} className="text-xs px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
              GR {g}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div><div className="text-xs text-muted-foreground">Supplier</div><div className="font-medium">{inv.vendor_name}</div></div>
          <div><div className="text-xs text-muted-foreground">Tanggal</div><div>{fmtDate(inv.issue_date)}</div></div>
          <div><div className="text-xs text-muted-foreground">Jatuh Tempo</div><div>{fmtDate(inv.due_date)}</div></div>
          <div><div className="text-xs text-muted-foreground">Sisa</div><div className="font-semibold tabular-nums">{fmtRp(inv.balance)}</div></div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--glass-border)]">
              <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                <th className="pb-2">Item</th>
                <th className="pb-2 text-right">Qty (dasar)</th>
                <th className="pb-2 text-right">Qty (satuan beli)</th>
                <th className="pb-2 text-right">Harga / dasar</th>
                <th className="pb-2 text-right">Jumlah</th>
              </tr>
            </thead>
            <tbody data-testid="ap-detail-items">
              {(inv.items || []).map((it) => (
                <tr key={it.id} className="border-b border-[var(--glass-border)]">
                  <td className="py-2">
                    <div className="text-xs font-medium">{it.description || it.material_name}</div>
                    <div className="text-[11px] text-muted-foreground">GR {it.gr_number}</div>
                  </td>
                  <td className="py-2 text-right font-mono text-xs">{fmtNum(it.qty)} {it.unit}</td>
                  <td className="py-2 text-right font-mono text-xs">
                    {it.po_uom && it.po_uom !== it.unit
                      ? `${fmtNum(it.qty_input)} ${it.po_uom}`
                      : '—'}
                  </td>
                  <td className="py-2 text-right font-mono text-xs">{fmtRp(it.price)}</td>
                  <td className="py-2 text-right font-mono text-xs">{fmtRp(it.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="font-semibold">
              <tr><td colSpan="4" className="py-1 text-right text-xs text-muted-foreground">Subtotal</td>
                  <td className="py-1 text-right font-mono text-xs">{fmtRp(inv.subtotal)}</td></tr>
              <tr><td colSpan="4" className="py-1 text-right text-xs text-muted-foreground">PPN {inv.tax_pct || 0}%</td>
                  <td className="py-1 text-right font-mono text-xs">{fmtRp(inv.tax_amount)}</td></tr>
              <tr className="border-t-2 border-[var(--glass-border)]">
                <td colSpan="4" className="py-2 text-right text-xs">Total</td>
                <td className="py-2 text-right font-mono">{fmtRp(inv.total)}</td></tr>
            </tfoot>
          </table>
        </div>

        {inv.notes && (
          <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-xs">
            {inv.notes}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
          <Button variant="secondary" onClick={onClose}>Tutup</Button>
          {inv.status === 'draft' && (
            <Button onClick={() => onSend(inv)} disabled={sending} data-testid="ap-detail-approve">
              <Send className="w-4 h-4 mr-1.5" />
              {sending ? 'Memproses...' : 'Setujui & Catat ke Buku Besar'}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

export default function SupplierInvoiceModule({ token }) {
  const [tab, setTab] = useState('pending');
  const [grs, setGrs] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [createGr, setCreateGr] = useState(null);
  const [detail, setDetail] = useState(null);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const [g, inv] = await Promise.all([
        apiGet(token, EP.grsForInvoice).catch(() => ({ items: [] })),
        apiGet(token, '/api/rahaza/ap-invoices').catch(() => []),
      ]);
      setGrs(g?.items || []);
      setInvoices(Array.isArray(inv) ? inv : inv?.items || []);
    } catch (e) {
      setErr(e.message);
      toast.error(`Gagal memuat faktur supplier: ${e.message}`);
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const approve = async (inv) => {
    setSending(true);
    try {
      await apiPost(token, `/api/rahaza/ap-invoices/${inv.id}/send`, {});
      toast.success(`Faktur ${inv.invoice_number} disetujui & dicatat ke buku besar`);
      setDetail(null);
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally { setSending(false); }
  };

  const filteredInv = useMemo(() => {
    const s = search.trim().toLowerCase();
    return invoices.filter((i) => {
      if (statusFilter && i.status !== statusFilter) return false;
      if (!s) return true;
      return [i.invoice_number, i.vendor_name, i.supplier_code, ...(i.po_numbers || [])]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(s));
    });
  }, [invoices, search, statusFilter]);

  const outstanding = invoices
    .filter((i) => !['paid', 'cancelled'].includes(i.status))
    .reduce((s, i) => s + Number(i.balance ?? i.total ?? 0), 0);

  return (
    <div className="space-y-5" data-testid="supplier-invoice-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Faktur Supplier</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Buat faktur hutang dari penerimaan barang, setujui, lalu catat ke buku besar.
            Qty yang ditolak QC tidak ikut difakturkan.
          </p>
        </div>
        <Button variant="secondary" onClick={load} data-testid="ap-refresh">
          <RefreshCw className="w-4 h-4 mr-1.5" /> Muat Ulang
        </Button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { l: 'Penerimaan siap difakturkan', v: grs.length, i: Truck },
          { l: 'Faktur draft', v: invoices.filter((i) => i.status === 'draft').length, i: FileText },
          { l: 'Total faktur', v: invoices.length, i: ClipboardCheck },
          { l: 'Hutang belum lunas', v: fmtRp(outstanding), i: Banknote },
        ].map((x) => (
          <div key={x.l} className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4">
            <div className="flex items-center gap-2 mb-1">
              <x.i className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
              <span className="text-xs text-muted-foreground line-clamp-1">{x.l}</span>
            </div>
            <div className="text-xl font-bold tabular-nums">{x.v}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-1 border-b border-[var(--glass-border)]">
        {[
          { key: 'pending', label: `Siap Difakturkan (${grs.length})` },
          { key: 'invoices', label: `Faktur (${invoices.length})` },
        ].map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            data-testid={`ap-tab-${t.key}`}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${tab === t.key
              ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
              : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
        </div>
      ) : tab === 'pending' ? (
        <GlassCard>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--glass-border)]">
                <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                  <th className="pb-3 pl-4">No. GR</th>
                  <th className="pb-3">Supplier</th>
                  <th className="pb-3">PO</th>
                  <th className="pb-3 text-right">Qty Bersih</th>
                  <th className="pb-3 text-right">Nilai</th>
                  <th className="pb-3 pr-4 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody data-testid="ap-pending-body">
                {grs.length === 0 && (
                  <tr><td colSpan="6" className="py-12 text-center text-muted-foreground">
                    <CheckCircle2 className="w-10 h-10 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">Tidak ada penerimaan yang menunggu faktur.</p>
                  </td></tr>
                )}
                {grs.map((g, idx) => (
                  <tr key={g.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}
                      data-testid={`ap-pending-row-${g.id}`}>
                    <td className="py-3 pl-4 font-mono text-xs">{g.receipt_number}</td>
                    <td className="py-3">
                      <div className="font-medium text-xs">{g.supplier_name}</div>
                      {g.supplier_code && <div className="text-[11px] font-mono text-muted-foreground">{g.supplier_code}</div>}
                      {!g.supplier_id && (
                        <div className="text-[11px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> belum tertaut master
                        </div>
                      )}
                    </td>
                    <td className="py-3 font-mono text-xs">{g.po_number || '—'}</td>
                    <td className="py-3 text-right font-mono text-xs">{fmtNum(g.total_net)}</td>
                    <td className="py-3 text-right font-mono text-xs">{fmtRp(g.receivable_amount)}</td>
                    <td className="py-3 pr-4 text-right">
                      <Button size="sm" onClick={() => setCreateGr(g)} data-testid={`ap-create-${g.id}`}>
                        Buat Faktur
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      ) : (
        <>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <GlassInput className="pl-9" placeholder="Cari no faktur, supplier, PO..."
                          value={search} onChange={(e) => setSearch(e.target.value)}
                          data-testid="ap-search" />
            </div>
            <SmartNativeSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              className="h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="ap-filter-status">
              <option value="">Semua status</option>
              {Object.entries(AP_STATUS_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
            </SmartNativeSelect>
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Filter className="w-3 h-3" /> {filteredInv.length} faktur
            </span>
          </div>

          <GlassCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                    <th className="pb-3 pl-4">No. Faktur</th>
                    <th className="pb-3">Supplier</th>
                    <th className="pb-3">Referensi</th>
                    <th className="pb-3">Tanggal</th>
                    <th className="pb-3 text-right">Total</th>
                    <th className="pb-3 text-right">Sisa</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3 pr-4 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody data-testid="ap-invoice-body">
                  {filteredInv.length === 0 && (
                    <tr><td colSpan="8" className="py-12 text-center text-muted-foreground">
                      <FileText className="w-10 h-10 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">Belum ada faktur supplier.</p>
                    </td></tr>
                  )}
                  {filteredInv.map((i, idx) => (
                    <tr key={i.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}
                        data-testid={`ap-invoice-row-${i.id}`}>
                      <td className="py-3 pl-4 font-mono text-xs">{i.invoice_number}</td>
                      <td className="py-3 text-xs">{i.vendor_name}</td>
                      <td className="py-3 text-[11px] font-mono text-muted-foreground">
                        {(i.po_numbers || []).join(', ') || (i.gr_numbers || []).join(', ') || '—'}
                      </td>
                      <td className="py-3 text-xs">{fmtDate(i.issue_date)}</td>
                      <td className="py-3 text-right font-mono text-xs">{fmtRp(i.total)}</td>
                      <td className="py-3 text-right font-mono text-xs">{fmtRp(i.balance ?? i.total)}</td>
                      <td className="py-3"><ApBadge status={i.status} /></td>
                      <td className="py-3 pr-4 text-right">
                        <Button variant="ghost" size="sm" onClick={() => setDetail(i)}
                                data-testid={`ap-view-${i.id}`}>
                          Detail
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </>
      )}

      {createGr && (
        <CreateInvoiceModal token={token} gr={createGr}
                            onClose={() => setCreateGr(null)}
                            onCreated={() => { load(); setTab('invoices'); }} />
      )}
      {detail && (
        <InvoiceDetail inv={detail} onClose={() => setDetail(null)} onSend={approve} sending={sending} />
      )}
    </div>
  );
}
