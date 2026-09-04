/**
 * ThreeWayMatchModule — PO ↔ GR ↔ AP Invoice Reconciliation Dashboard
 * Phase 27 — P2P Flow Completion
 *
 * Two views:
 *  A) Dashboard — list of POs with match status (matched/pending/over/under)
 *  B) Detail — per-line breakdown for ONE PO showing qty/value across PO, GR, Invoice
 *
 * Also includes a side panel for "Available GRs" → "Buat AP Invoice dari GR".
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Scale, RefreshCw, FileText, Truck, Package, AlertTriangle, CheckCircle2,
  Filter, ChevronRight, Plus, Search, DollarSign, Layers, TrendingUp,
  TrendingDown, X, ArrowLeft, Building2, Calendar,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ───────────────────────────────────────────────────────────────
function fmtRp(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return formatRupiah(n);
}
function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return v; }
}

const STATUS_META = {
  matched:  { label: 'Match',     icon: CheckCircle2,  color: 'text-green-700 bg-green-100 border-green-400 dark:text-green-300 dark:bg-green-500/15 dark:border-green-400/30' },
  pending:  { label: 'Pending',   icon: FileText,      color: 'text-foreground bg-muted border-border dark:text-foreground/70 dark:bg-slate-500/15 dark:border-slate-400/30' },
  over:     { label: 'Over-bill', icon: TrendingUp,    color: 'text-red-700 bg-red-100 border-red-400 dark:text-red-300 dark:bg-red-500/15 dark:border-red-400/30' },
  under:    { label: 'Under-bill',icon: TrendingDown,  color: 'text-amber-700 bg-amber-100 border-amber-400 dark:text-amber-300 dark:bg-amber-500/15 dark:border-amber-400/30' },
  variance: { label: 'Variance',  icon: AlertTriangle, color: 'text-amber-700 bg-amber-100 border-amber-400 dark:text-amber-300 dark:bg-amber-500/15 dark:border-amber-400/30' },
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.pending;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.color}`}>
      <Icon className="w-3 h-3" /> {m.label}
    </span>
  );
}

// ─── Available GRs Panel — Create AP Invoice From GR ──────────────────────
function CreateAPFromGRDialog({ open, onClose, headers, onSuccess }) {
  const [grs, setGrs] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [taxPct, setTaxPct] = useState('11');
  const [notes, setNotes] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/rahaza/grs/available-for-invoice`, { headers });
      if (r.ok) {
        const data = await r.json();
        setGrs(data.items || []);
      }
    } catch (e) {
      toast.error('Gagal memuat GR');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => {
    if (open) {
      load();
      setSelectedIds(new Set());
    }
  }, [open, load]);

  const toggle = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // Group by supplier (must be same supplier per invoice)
  const groupedBySupplier = useMemo(() => {
    const map = {};
    grs.forEach(g => {
      const k = g.supplier_name || '(Tanpa Supplier)';
      if (!map[k]) map[k] = [];
      map[k].push(g);
    });
    return map;
  }, [grs]);

  const selectedSupplier = useMemo(() => {
    const sel = grs.filter(g => selectedIds.has(g.id));
    if (sel.length === 0) return null;
    return sel[0].supplier_name;
  }, [grs, selectedIds]);

  const totalSelected = useMemo(() => {
    return grs.filter(g => selectedIds.has(g.id)).reduce((s, g) => s + (g.receivable_amount || 0), 0);
  }, [grs, selectedIds]);

  const handleCreate = async () => {
    if (selectedIds.size === 0) {
      toast.error('Pilih minimal 1 GR');
      return;
    }
    setCreating(true);
    try {
      const r = await fetch(`${API}/api/rahaza/ap-invoices/from-gr`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          gr_ids: Array.from(selectedIds),
          tax_pct: parseFloat(taxPct) || 0,
          due_date: dueDate || undefined,
          notes: notes || undefined,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Gagal membuat invoice');
      toast.success(`✓ AP Invoice ${data.invoice_number} dibuat`);
      onSuccess?.(data);
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !creating) onClose(); }}>
      <DialogContent className="max-w-4xl bg-card border-foreground/10 max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-foreground">
            <Plus className="w-5 h-5 text-violet-600 dark:text-violet-300" /> Buat AP Invoice dari GR
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Pilih GR yang sudah diterima untuk dijadikan AP Invoice. Hanya GR dari 1 supplier yang sama dapat digabung.
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {loading ? (
            <div className="h-40 flex items-center justify-center text-muted-foreground">Memuat GRs...</div>
          ) : Object.keys(groupedBySupplier).length === 0 ? (
            <div className="h-40 flex flex-col items-center justify-center text-muted-foreground/60 gap-2">
              <Truck className="w-10 h-10 opacity-30" />
              <p className="text-sm">Tidak ada GR yang siap di-invoice.</p>
              <p className="text-xs">GR harus berstatus "received"/"completed" dan belum di-invoice.</p>
            </div>
          ) : (
            Object.entries(groupedBySupplier).map(([supplier, items]) => {
              const disabled = !!selectedSupplier && selectedSupplier !== supplier;
              return (
                <div key={supplier} className="space-y-1.5">
                  <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                    <Building2 className="w-3 h-3" /> {supplier} {disabled && <span className="text-amber-700 dark:text-amber-400 text-[10px]">(Tidak dapat dipilih — supplier berbeda)</span>}
                  </div>
                  {items.map(g => {
                    const checked = selectedIds.has(g.id);
                    return (
                      <button
                        key={g.id}
                        disabled={disabled && !checked}
                        data-testid={`gr-pick-${g.id}`}
                        onClick={() => toggle(g.id)}
                        className={`w-full text-left p-2.5 rounded-lg border flex items-center justify-between gap-2 transition ${
                          checked ? 'bg-violet-100 dark:bg-violet-500/15 border-violet-500 dark:border-violet-400/40' :
                          disabled ? 'bg-foreground/[0.03] border-foreground/5 opacity-40 cursor-not-allowed' :
                          'bg-foreground/[0.03] border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 rounded border flex items-center justify-center ${checked ? 'bg-violet-500 border-violet-400' : 'border-foreground/20'}`}>
                            {checked && <CheckCircle2 className="w-4 h-4 text-foreground" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-mono text-violet-600 dark:text-violet-300">{g.receipt_number}</span>
                              {g.po_number && <span className="text-[10px] text-muted-foreground/60">← {g.po_number}</span>}
                            </div>
                            <div className="text-[10px] text-muted-foreground mt-0.5">
                              {fmtDate(g.received_at)} · {g.items_count} item · {fmtNum(g.total_net)} pcs net
                            </div>
                          </div>
                        </div>
                        <div className="text-sm font-bold text-green-600 dark:text-green-300">{fmtRp(g.receivable_amount)}</div>
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        {/* Form footer */}
        <div className="border-t border-foreground/10 pt-3 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Tax %</label>
              <Input
                type="number"
                value={taxPct}
                onChange={e => setTaxPct(e.target.value)}
                className="bg-foreground/5 border-foreground/10 text-sm mt-1"
                data-testid="ap-tax-pct"
              />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Jatuh Tempo</label>
              <Input
                type="date"
                value={dueDate}
                onChange={e => setDueDate(e.target.value)}
                className="bg-foreground/5 border-foreground/10 text-sm mt-1"
                data-testid="ap-due-date"
              />
            </div>
            <div className="flex items-end justify-end">
              <div className="text-right">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Total Pre-tax</div>
                <div className="text-lg font-bold text-green-600 dark:text-green-300">{fmtRp(totalSelected)}</div>
              </div>
            </div>
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Catatan</label>
            <Textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={2}
              placeholder="Catatan opsional..."
              className="bg-foreground/5 border-foreground/10 text-sm mt-1 resize-none"
              data-testid="ap-notes"
            />
          </div>
        </div>

        <DialogFooter className="flex flex-row gap-2 sm:justify-end">
          <Button variant="ghost" onClick={onClose} disabled={creating} className="text-muted-foreground">Batal</Button>
          <Button
            onClick={handleCreate}
            disabled={creating || selectedIds.size === 0}
            className="bg-violet-600 hover:bg-violet-500"
            data-testid="ap-create-submit"
          >
            {creating ? 'Membuat...' : `Buat Invoice (${selectedIds.size} GR)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── PO Detail View (drill-down) ──────────────────────────────────────────
function PODetailView({ poId, headers, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/api/rahaza/3way-match/${poId}`, { headers });
        if (r.ok && active) setData(await r.json());
        else if (active) toast.error('Gagal memuat detail');
      } catch (e) {
        if (active) toast.error('Network error');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [poId, headers]);

  if (loading || !data) {
    return (
      <GlassCard className="p-8 text-center text-muted-foreground">
        <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin text-violet-600 dark:text-violet-400" />
        Memuat detail 3-way match...
      </GlassCard>
    );
  }

  const po = data.po || {};
  const grs = data.grs || [];
  const invoices = data.invoices || [];
  const lines = data.lines || [];

  return (
    <div className="space-y-5">
      <GlassCard className="p-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack} className="text-foreground/70 hover:text-foreground" data-testid="threeway-back">
              <ArrowLeft className="w-4 h-4 mr-1" /> Kembali
            </Button>
            <div>
              <h3 className="text-lg font-bold text-foreground font-mono">{po.po_number}</h3>
              <p className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                <Building2 className="w-3 h-3" /> {po.vendor_name}
                <span className="text-muted-foreground/50">·</span>
                <Calendar className="w-3 h-3" /> {fmtDate(po.po_date)}
              </p>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Linked Documents */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <SourceCard icon={Package} label="Purchase Order" count={1} color="violet" detail={po.po_number} />
        <SourceCard icon={Truck} label="Goods Receipts" count={grs.length} color="amber"
                    detail={grs.map(g => g.receipt_number).join(', ') || '—'} />
        <SourceCard icon={FileText} label="AP Invoices" count={invoices.length} color="emerald"
                    detail={invoices.map(i => i.invoice_number).join(', ') || '—'} />
      </div>

      {/* Per-Line Breakdown */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Rekonsiliasi Per Item ({lines.length})
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b border-foreground/10">
                <th className="text-left py-2 px-2">Material</th>
                <th className="text-right py-2 px-2">PO Qty</th>
                <th className="text-right py-2 px-2">PO Value</th>
                <th className="text-right py-2 px-2">GR Net Qty</th>
                <th className="text-right py-2 px-2">GR Value</th>
                <th className="text-right py-2 px-2">Inv Qty</th>
                <th className="text-right py-2 px-2">Inv Amount</th>
                <th className="text-right py-2 px-2">Variance %</th>
                <th className="text-left py-2 px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {lines.length === 0 ? (
                <tr><td colSpan="9" className="py-6 text-center text-muted-foreground/60 italic">Belum ada item.</td></tr>
              ) : lines.map((l, idx) => (
                <tr key={idx} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                  <td className="py-2 px-2 text-foreground">
                    <div>{l.material_name}</div>
                    <div className="text-[10px] text-muted-foreground/60 font-mono">{l.material_code}</div>
                  </td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(l.po_qty)} {l.unit}</td>
                  <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtRp(l.po_subtotal)}</td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(l.net_qty)} {l.unit}</td>
                  <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtRp(l.received_value)}</td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(l.invoiced_qty)} {l.unit}</td>
                  <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300">{fmtRp(l.invoiced_amount)}</td>
                  <td className="py-2 px-2 text-right">
                    <span className={l.variance_pct > 0 ? 'text-red-600 dark:text-red-300' : l.variance_pct < 0 ? 'text-amber-600 dark:text-amber-300' : 'text-green-600 dark:text-green-300'}>
                      {l.variance_pct > 0 ? '+' : ''}{l.variance_pct}%
                    </span>
                  </td>
                  <td className="py-2 px-2"><StatusBadge status={l.match_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Linked GRs */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Truck className="w-4 h-4 text-amber-600 dark:text-amber-300" /> Goods Receipts ({grs.length})
        </h4>
        {grs.length === 0 ? <p className="text-xs text-muted-foreground/60 italic">Belum ada GR.</p> : (
          <div className="space-y-1.5">
            {grs.map(gr => (
              <div key={gr.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08] flex items-center justify-between">
                <div>
                  <span className="text-xs font-mono text-amber-600 dark:text-amber-300">{gr.receipt_number}</span>
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{gr.status}</span>
                </div>
                <div className="text-[10px] text-muted-foreground">{fmtDate(gr.created_at)} · {(gr.items || []).length} item</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Linked Invoices */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-300" /> AP Invoices ({invoices.length})
        </h4>
        {invoices.length === 0 ? <p className="text-xs text-muted-foreground/60 italic">Belum ada invoice.</p> : (
          <div className="space-y-1.5">
            {invoices.map(inv => (
              <div key={inv.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08] flex items-center justify-between">
                <div>
                  <span className="text-xs font-mono text-emerald-600 dark:text-emerald-300">{inv.invoice_number}</span>
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70 capitalize">{inv.status}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-muted-foreground">{fmtDate(inv.issue_date)}</span>
                  <span className="text-emerald-600 dark:text-emerald-300 font-bold">{fmtRp(inv.total)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function SourceCard({ icon: Icon, label, count, detail, color }) {
  const toneMap = {
    violet: 'text-violet-600 dark:text-violet-300 bg-violet-50 dark:bg-violet-500/10',
    amber: 'text-amber-600 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10',
    emerald: 'text-emerald-600 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/10',
  };
  return (
    <GlassCard className="p-3">
      <div className={`flex items-center gap-2 text-xs ${toneMap[color]?.split(' ')[0]}`}>
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div className="text-2xl font-bold text-foreground mt-1">{count}</div>
      <div className="text-[10px] text-muted-foreground truncate mt-0.5" title={detail}>{detail}</div>
    </GlassCard>
  );
}

// ─── Main Module ──────────────────────────────────────────────────────────
export default function ThreeWayMatchModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedPoId, setSelectedPoId] = useState(null);
  const [showCreateAP, setShowCreateAP] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const q = statusFilter === 'all' ? '' : `?status=${statusFilter}`;
      const r = await fetch(`${API}/api/rahaza/3way-match${q}`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat dashboard');
        return;
      }
      setData(await r.json());
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [headers, statusFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let list = data.rows || [];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(r =>
        (r.po_number || '').toLowerCase().includes(q) ||
        (r.vendor_name || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [data, search]);

  if (selectedPoId) {
    return <PODetailView poId={selectedPoId} headers={headers} onBack={() => setSelectedPoId(null)} />;
  }

  const kpis = data?.kpis || {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rekonsiliasi PO (3 Arah)"
        subtitle="Cocokkan Purchase Order ↔ Penerimaan Barang ↔ Faktur Supplier dalam satuan dasar sebelum pembayaran disetujui."
        icon={Scale}
        actions={
          <div className="flex items-center gap-2">
            <Button
              onClick={() => setShowCreateAP(true)}
              className="bg-violet-600 hover:bg-violet-500 text-foreground text-xs h-8"
              data-testid="create-ap-from-gr-btn"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Buat AP dari GR
            </Button>
            <Button variant="ghost" size="sm" onClick={fetchData} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="threeway-refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        }
      />

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KPI label="Total PO" value={kpis.total_pos || 0} icon={Package} tone="slate" />
        <KPI label="Matched" value={kpis.matched || 0} icon={CheckCircle2} tone="green" />
        <KPI label="Pending Inv" value={kpis.pending || 0} icon={FileText} tone="slate" />
        <KPI label="Over-billed" value={kpis.over || 0} icon={TrendingUp} tone="red" />
        <KPI label="Under-billed" value={kpis.under || 0} icon={TrendingDown} tone="amber" />
        <KPI label="Variance Total" value={kpis.variance || 0} icon={AlertTriangle} tone="amber" />
      </div>

      {/* Value KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <KPIBig label="Ordered" value={fmtRp(kpis.total_ordered_value)} icon={Package} tone="violet" />
        <KPIBig label="Received" value={fmtRp(kpis.total_received_value)} icon={Truck} tone="amber" />
        <KPIBig label="Invoiced" value={fmtRp(kpis.total_invoiced_value)} icon={FileText} tone="emerald" />
        <KPIBig label="Paid" value={fmtRp(kpis.total_paid)} icon={DollarSign} tone="green" />
      </div>

      {/* Filter + Table */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <Tabs value={statusFilter} onValueChange={setStatusFilter}>
            <TabsList className="bg-foreground/5 h-auto p-1 flex-wrap">
              <TabsTrigger value="all" data-testid="3way-tab-all">Semua</TabsTrigger>
              <TabsTrigger value="matched" data-testid="3way-tab-matched">Matched</TabsTrigger>
              <TabsTrigger value="pending" data-testid="3way-tab-pending">Pending</TabsTrigger>
              <TabsTrigger value="over" data-testid="3way-tab-over">Over-bill</TabsTrigger>
              <TabsTrigger value="under" data-testid="3way-tab-under">Under-bill</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center bg-foreground/5 border border-foreground/10 rounded-md px-3 min-w-[220px]">
            <Search className="w-4 h-4 text-muted-foreground/60" />
            <Input
              placeholder="Cari nomor PO / vendor..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-0 focus-visible:ring-0 text-sm"
              data-testid="3way-search"
            />
          </div>
        </div>

        {loading ? (
          <div className="h-40 flex items-center justify-center text-muted-foreground">Memuat...</div>
        ) : filtered.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-muted-foreground/60 gap-2">
            <Scale className="w-10 h-10 opacity-30" />
            <p className="text-sm">Tidak ada PO untuk filter saat ini.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-foreground/10">
                  <th className="text-left py-2 px-2">PO #</th>
                  <th className="text-left py-2 px-2">Vendor</th>
                  <th className="text-left py-2 px-2">Tanggal</th>
                  <th className="text-right py-2 px-2">Ordered</th>
                  <th className="text-right py-2 px-2">Received</th>
                  <th className="text-right py-2 px-2">Invoiced</th>
                  <th className="text-right py-2 px-2">Variance</th>
                  <th className="text-right py-2 px-2">%</th>
                  <th className="text-left py-2 px-2">Status</th>
                  <th className="text-center py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <motion.tr
                    key={r.po_id}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="border-b border-foreground/5 hover:bg-foreground/[0.03] cursor-pointer"
                    data-testid={`3way-row-${r.po_id}`}
                    onClick={() => setSelectedPoId(r.po_id)}
                  >
                    <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{r.po_number}</td>
                    <td className="py-2 px-2 text-foreground truncate max-w-[200px]" title={r.vendor_name}>{r.vendor_name}</td>
                    <td className="py-2 px-2 text-muted-foreground">{fmtDate(r.po_date)}</td>
                    <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtRp(r.total_ordered_value)}</td>
                    <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtRp(r.total_received_value)}</td>
                    <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300">{fmtRp(r.total_invoiced_value)}</td>
                    <td className="py-2 px-2 text-right">
                      <span className={r.value_variance > 0 ? 'text-red-600 dark:text-red-300' : r.value_variance < 0 ? 'text-amber-600 dark:text-amber-300' : 'text-muted-foreground'}>
                        {fmtRp(r.value_variance)}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right">
                      <span className={Math.abs(r.variance_pct) > 0.5 ? (r.variance_pct > 0 ? 'text-red-600 dark:text-red-300' : 'text-amber-600 dark:text-amber-300') : 'text-green-600 dark:text-green-300'}>
                        {r.variance_pct > 0 ? '+' : ''}{r.variance_pct}%
                      </span>
                    </td>
                    <td className="py-2 px-2"><StatusBadge status={r.match_status} /></td>
                    <td className="py-2 px-2 text-center"><ChevronRight className="w-4 h-4 text-muted-foreground/50 inline" /></td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <CreateAPFromGRDialog
        open={showCreateAP}
        onClose={() => setShowCreateAP(false)}
        headers={headers}
        onSuccess={() => fetchData()}
      />
    </div>
  );
}

function KPI({ label, value, icon: Icon, tone }) {
  const t = {
    slate:  'text-foreground/70',
    green:  'text-green-600 dark:text-green-300',
    amber:  'text-amber-600 dark:text-amber-300',
    red:    'text-red-600 dark:text-red-300',
    violet: 'text-violet-600 dark:text-violet-300',
  }[tone] || 'text-foreground/70';
  return (
    <div className="p-2.5 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08]">
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`text-xl font-bold ${t}`}>{fmtNum(value)}</div>
    </div>
  );
}

function KPIBig({ label, value, icon: Icon, tone }) {
  const t = {
    violet:  'text-violet-600 dark:text-violet-300 bg-violet-50 dark:bg-violet-500/10',
    amber:   'text-amber-600 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10',
    emerald: 'text-emerald-600 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/10',
    green:   'text-green-600 dark:text-green-300 bg-green-50 dark:bg-green-500/10',
  }[tone] || 'text-foreground/70 bg-foreground/5';
  return (
    <GlassCard className="p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        {Icon && <Icon className="w-3.5 h-3.5" />} {label}
      </div>
      <div className={`text-xl font-bold ${t.split(' ')[0]}`}>{value}</div>
    </GlassCard>
  );
}

