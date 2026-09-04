/**
 * MaklonPO360Module — Maklon PO 360° View
 * Phase 25 — P2 Workflow Consolidation #1
 *
 * Unified view for ONE Maklon PO showing all aspects in tabs:
 *   1. Detail (header + items + dispatches)
 *   2. BOM Material (estimate + actual)
 *   3. Sample (sampling + revisions)
 *   4. Production (WO progress + stage qty)
 *   5. QC (defect tracking)
 *   6. Billing (invoices + payments)
 *   7. HPP Snapshot (cost roll-up)
 *   8. Timeline (chronological activity log)
 *
 * Backward compatible — existing per-module screens still accessible via sidebar.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, ArrowLeft, RefreshCw, ChevronRight, Search, Truck, FileText,
  Layers, Clipboard, ShieldCheck, DollarSign, Activity, BarChart3,
  Calendar, Clock, AlertCircle, CheckCircle2, TrendingUp, Users,
  Send, BoxesIcon, Banknote, X, Ban,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import OnwardCTA from './OnwardCTA';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';
import ProgressBreakdownBar from './engine/ProgressBreakdownBar';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ───────────────────────────────────────────────────────────────
const fmtRp = (v) => (v === null || v === undefined || v === '') ? '—' : formatRupiah(v);
function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return v; }
}
function fmtDateOnly(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return v; }
}

const STATUS_CONFIG = {
  draft:              { label: 'Draft',             color: 'bg-muted text-foreground border-border dark:bg-slate-100 dark:bg-slate-500/15 dark:text-foreground/70 dark:border-slate-300 dark:border-slate-400/30' },
  confirmed:          { label: 'Dikonfirmasi',      color: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-100 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400 dark:border-blue-400/30' },
  in_production:      { label: 'Produksi',          color: 'bg-violet-100 text-violet-700 border-violet-300 dark:bg-violet-100 dark:bg-violet-500/15 dark:text-violet-300 dark:border-violet-400 dark:border-violet-400/30' },
  partial_delivered:  { label: 'Sebagian Terkirim', color: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-100 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400 dark:border-amber-400/30' },
  completed:          { label: 'Selesai',           color: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-100 dark:bg-green-500/15 dark:text-green-300 dark:border-green-400 dark:border-green-400/30' },
  invoiced:           { label: 'Ditagih',           color: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-100 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400 dark:border-emerald-400/30' },
  cancelled:          { label: 'Dibatalkan',        color: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-100 dark:bg-red-500/15 dark:text-red-300 dark:border-red-400 dark:border-red-400/30' },
};

function StatusBadge({ status, dict = STATUS_CONFIG }) {
  const c = dict[status] || dict.draft;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>
      {c.label}
    </span>
  );
}

// ─── PO Picker (when no PO selected) ───────────────────────────────────────
function POPickerView({ headers, onPick, onBack, onNavigate }) {
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos?limit=200`, { headers });
      if (r.ok) setPos(await r.json());
    } catch (e) {
      toast.error('Gagal memuat daftar PO');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    let list = pos;
    if (statusFilter !== 'all') list = list.filter(p => p.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(p =>
        (p.po_number || '').toLowerCase().includes(q) ||
        (p.client_name || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [pos, statusFilter, search]);

  // RC-UI-03: client-side pagination (10/page) for PO picker list
  const filteredPg = useClientPagination(filtered, 10);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Maklon PO 360° View"
        subtitle="Pilih PO untuk membuka tampilan terintegrasi: Detail · BOM · Sample · Produksi · QC · Billing · HPP · Timeline"
        icon={Package}
        actions={
          <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="text-muted-foreground hover:text-foreground">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        }
      />

      {/* RC-FLOW-UX-CORE — onward CTA into the standalone billing module */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Alur Terkait"
        actions={[
          { module: 'maklon-billing', label: 'Invoice & Billing', icon: Banknote, hint: 'Daftar invoice & penagihan Maklon' },
        ]}
      />

      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center flex-1 min-w-[240px] bg-foreground/5 border border-foreground/10 rounded-md px-3">
            <Search className="w-4 h-4 text-muted-foreground/60" />
            <Input
              placeholder="Cari nomor PO atau nama klien..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-0 focus-visible:ring-0 text-sm"
              data-testid="po360-search"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-44 bg-foreground/5 border-foreground/10 text-sm">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="confirmed">Dikonfirmasi</SelectItem>
              <SelectItem value="in_production">Produksi</SelectItem>
              <SelectItem value="partial_delivered">Sebagian Terkirim</SelectItem>
              <SelectItem value="completed">Selesai</SelectItem>
              <SelectItem value="invoiced">Ditagih</SelectItem>
              <SelectItem value="cancelled">Dibatalkan</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground">Memuat...</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-muted-foreground/60 gap-2">
            <Package className="w-10 h-10 opacity-30" />
            <p className="text-sm">Tidak ada PO ditemukan</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
            {filteredPg.paged.map(po => {
              const progressPct = po.total_qty > 0
                ? Math.round(((po.qty_dispatched || 0) / po.total_qty) * 100)
                : 0;
              return (
                <motion.button
                  key={po.id}
                  data-testid={`po360-row-${po.id}`}
                  initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                  className="w-full text-left flex items-center justify-between p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30 transition-all group"
                  onClick={() => onPick(po)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-500/20 flex items-center justify-center">
                      <Package className="w-5 h-5 text-violet-600 dark:text-violet-300" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-bold text-foreground">{po.po_number}</span>
                        <StatusBadge status={po.status} />
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-muted-foreground">{po.client_name}</span>
                        <span className="text-xs text-muted-foreground/60">{po.po_date}</span>
                        {po.deadline && <span className="text-xs text-amber-700 dark:text-amber-400">📅 {po.deadline}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="hidden md:block w-32">
                      <div className="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>{fmtNum(po.qty_dispatched || 0)} / {fmtNum(po.total_qty)}</span>
                        <span>{progressPct}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-green-400"
                             style={{ width: `${progressPct}%` }} />
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-green-600 dark:text-green-300">{fmtRp(po.total_value)}</div>
                      <div className="text-xs text-muted-foreground">{fmtNum(po.total_qty)} pcs</div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground/50 group-hover:text-violet-400 transition-colors" />
                  </div>
                </motion.button>
              );
            })}
          </div>
        )}
        {filteredPg.total > 0 && <PaginationLite page={filteredPg.page} totalPages={filteredPg.totalPages} total={filteredPg.total} pageSize={filteredPg.pageSize} onPageChange={filteredPg.setPage} />}
      </GlassCard>
    </div>
  );
}

// ─── Header Strip with KPIs ────────────────────────────────────────────────
function HeaderStrip({ kpis, onBack, onRefresh, loading }) {
  return (
    <GlassCard className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="text-foreground/70 hover:text-foreground" data-testid="po360-back">
            <ArrowLeft className="w-4 h-4 mr-1" /> Pilih PO Lain
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-foreground font-mono">{kpis.po_number || 'PO'}</h2>
              <StatusBadge status={kpis.status} />
            </div>
            <p className="text-sm text-muted-foreground mt-0.5 flex items-center gap-2">
              <Users className="w-3 h-3" /> {kpis.client_name || '—'}
              {kpis.deadline && (
                <>
                  <span className="text-muted-foreground/50">·</span>
                  <Calendar className="w-3 h-3 text-amber-700 dark:text-amber-400" />
                  <span className="text-amber-600 dark:text-amber-300">Deadline: {fmtDateOnly(kpis.deadline)}</span>
                </>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="po360-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Progress bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-foreground/5 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Progress Produksi</span>
            <span className="text-foreground font-semibold">
              {fmtNum(kpis.total_produced)} / {fmtNum(kpis.total_qty)} pcs ({kpis.progress_pct || 0}%)
            </span>
          </div>
          <div className="h-2 rounded-full bg-foreground/10 overflow-hidden">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500"
                        initial={{ width: 0 }} animate={{ width: `${kpis.progress_pct || 0}%` }} transition={{ duration: 0.5 }} />
          </div>
        </div>
        <div className="bg-foreground/5 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Progress Pengiriman</span>
            <span className="text-foreground font-semibold">
              {fmtNum(kpis.total_dispatched)} / {fmtNum(kpis.total_qty)} pcs ({kpis.dispatch_pct || 0}%)
            </span>
          </div>
          <div className="h-2 rounded-full bg-foreground/10 overflow-hidden">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-green-500"
                        initial={{ width: 0 }} animate={{ width: `${kpis.dispatch_pct || 0}%` }} transition={{ duration: 0.5 }} />
          </div>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KPICell label="Total Pcs" value={fmtNum(kpis.total_qty)} icon={Package} tone="slate" />
        <KPICell label="Nilai PO" value={fmtRp(kpis.total_value)} icon={DollarSign} tone="green" small />
        <KPICell label="Sisa Kirim" value={fmtNum(kpis.total_remaining)} icon={Truck} tone="amber" />
        <KPICell label="Dispatches" value={kpis.dispatch_count || 0} icon={Truck} tone="violet" />
        <KPICell label="Invoiced" value={fmtRp(kpis.invoiced_amount)} icon={FileText} tone="blue" small />
        <KPICell label="Outstanding" value={fmtRp(kpis.outstanding_amount)} icon={AlertCircle} tone="red" small />
        <KPICell label="Sample Disetujui" value={kpis.sample_approved || 0} icon={CheckCircle2} tone="emerald" />
        <KPICell label="Sample Pending" value={kpis.sample_pending || 0} icon={Clock} tone="amber" />
        <KPICell label="QC Pass" value={kpis.qc_pass || 0} icon={ShieldCheck} tone="green" />
        <KPICell label="QC Fail" value={kpis.qc_fail || 0} icon={AlertCircle} tone="red" />
        <KPICell label="Paid" value={fmtRp(kpis.paid_amount)} icon={Banknote} tone="emerald" small />
        <KPICell label="Invoice Count" value={kpis.invoice_count || 0} icon={FileText} tone="cyan" />
      </div>
    </GlassCard>
  );
}

function KPICell({ label, value, icon: Icon, tone = 'slate', small = false }) {
  const toneMap = {
    slate:   'text-foreground/70',
    green:   'text-green-600 dark:text-green-300',
    amber:   'text-amber-600 dark:text-amber-300',
    violet:  'text-violet-600 dark:text-violet-300',
    blue:    'text-blue-600 dark:text-blue-300',
    red:     'text-red-600 dark:text-red-300',
    emerald: 'text-emerald-600 dark:text-emerald-300',
    cyan:    'text-cyan-600 dark:text-cyan-300',
  };
  return (
    <div className="p-2.5 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] transition-colors">
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`${small ? 'text-sm' : 'text-lg'} font-bold ${toneMap[tone]} leading-tight`}>{value}</div>
    </div>
  );
}

// ─── Tab Panels (Self-contained, query backend per-tab needs) ──────────────
function DetailTab({ data }) {
  if (!data) return null;
  const { po, dispatches, material_receives } = data;
  return (
    <div className="space-y-5">
      <GlassCard className="p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Package className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Items PO
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b border-foreground/10">
                <th className="text-left py-2 px-2">Seri</th>
                <th className="text-left py-2 px-2">Artikel</th>
                <th className="text-left py-2 px-2">Warna / Size</th>
                <th className="text-right py-2 px-2">Qty</th>
                <th className="text-right py-2 px-2">Produced</th>
                <th className="text-right py-2 px-2">Dispatched</th>
                <th className="text-right py-2 px-2">Sisa</th>
                <th className="text-right py-2 px-2">CMT/pcs</th>
                <th className="text-right py-2 px-2">Subtotal</th>
                <th className="text-left py-2 px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(po.items || []).map(it => (
                <tr key={it.item_id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                  <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{it.seri_no}</td>
                  <td className="py-2 px-2 text-foreground">{it.artikel}</td>
                  <td className="py-2 px-2 text-foreground/70">{it.color || '—'} / {it.size || '—'}</td>
                  <td className="py-2 px-2 text-right text-foreground">{fmtNum(it.qty)}</td>
                  <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtNum(it.qty_produced)}</td>
                  <td className="py-2 px-2 text-right text-green-600 dark:text-green-300">{fmtNum(it.qty_dispatched)}</td>
                  <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtNum(it.qty_remaining)}</td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtRp(it.cmt_rate_per_pcs)}</td>
                  <td className="py-2 px-2 text-right text-green-600 dark:text-green-300 font-semibold">{fmtRp(it.subtotal)}</td>
                  <td className="py-2 px-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{it.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <GlassCard className="p-4">
          <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Truck className="w-4 h-4 text-amber-600 dark:text-amber-300" /> Riwayat Dispatch ({dispatches.length})
          </h3>
          {dispatches.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 italic">Belum ada dispatch.</p>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {dispatches.map(d => (
                <div key={d.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-amber-600 dark:text-amber-300">{d.dispatch_number}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{d.status}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">{fmtDate(d.created_at)}</div>
                  <div className="text-xs text-foreground/70 mt-0.5">
                    Total {fmtNum((d.items || []).reduce((s, i) => s + (i.qty_dispatched || 0), 0))} pcs · {(d.items || []).length} item
                  </div>
                  {d.driver_name && <div className="text-[10px] text-muted-foreground/60 mt-0.5">Sopir: {d.driver_name} ({d.vehicle_no || '—'})</div>}
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className="p-4">
          <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <BoxesIcon className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> Material dari Klien ({material_receives.length})
          </h3>
          {material_receives.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 italic">Belum ada penerimaan material.</p>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {material_receives.map(r => (
                <div key={r.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-cyan-600 dark:text-cyan-300">{r.receive_number || r.id.slice(0, 8)}</span>
                    <span className="text-[10px] text-muted-foreground">{fmtDate(r.receive_date || r.created_at)}</span>
                  </div>
                  <div className="text-xs text-foreground/70 mt-1">{(r.items || []).length} jenis material</div>
                  {r.notes && <div className="text-[10px] text-muted-foreground/60 mt-0.5 italic">{r.notes}</div>}
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

// ─── BOM Tab ──────────────────────────────────────────────────────────────────
// 2026-08-01: disambungkan ke BOM Template maklon.
//  · Angka dulu selalu kosong karena tabel membaca `qty_estimated/estimated_cost`
//    sedangkan penulis lama mengisi `qty_total_est/cost_per_unit` → sekarang
//    dibaca dua-duanya (dan backend menulis kedua alias).
//  · Ditambah tombol Sinkronkan (template AKTIF) + pilih versi template,
//    daftar template sumber, peringatan, serta checklist material dari klien.
const CAT_LABEL = { fabric: 'Kain/Benang', accessories: 'Aksesoris', packaging: 'Kemasan', other: 'Lainnya' };

function BOMTab({ data, poId, headers, onRefresh }) {
  const bom = data?.bom;
  const [busy, setBusy] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [expect, setExpect] = useState(null);

  const loadExpectation = useCallback(async () => {
    if (!poId) return;
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos/${poId}/material-expectation`, { headers });
      if (r.ok) setExpect(await r.json());
    } catch (e) { console.error('expectation error', e); }
  }, [poId, headers]);

  useEffect(() => { loadExpectation(); }, [loadExpectation]);

  const syncBom = async (templateId = null) => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos/${poId}/bom-sync`, {
        method: 'POST', headers,
        body: JSON.stringify({ template_id: templateId, force: true }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        const d = body?.detail;
        toast.error(typeof d === 'string' ? d : (d?.message || 'Gagal sinkronkan BOM'));
        return;
      }
      toast.success(
        `BOM tersinkron: ${body.materials || 0} material `
        + `(${body.bulk_rows || 0} kain/benang, ${body.accessory_rows || 0} aksesoris ke kebutuhan PO)`,
      );
      setPickerOpen(false);
      await Promise.all([onRefresh?.(), loadExpectation()]);
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally { setBusy(false); }
  };

  const openPicker = async () => {
    setPickerOpen(true);
    try {
      const catIds = [...new Set(((data?.po?.items) || data?.items || [])
        .map(i => i.catalog_item_id || i.buyer_catalog_id).filter(Boolean))];
      const all = [];
      for (const cid of catIds) {
        const r = await fetch(`${API}/api/dewi/maklon/bom-templates?buyer_catalog_id=${cid}`, { headers });
        if (r.ok) {
          const d = await r.json();
          all.push(...(Array.isArray(d) ? d : (d.templates || d.items || [])));
        }
      }
      setTemplates(all);
    } catch (e) { console.error('template list error', e); }
  };

  const lines = bom?.lines || bom?.materials || [];
  const qtyEst = (l) => Number(l.qty_estimated ?? l.qty_total_est ?? 0);
  const costEst = (l) => Number(l.estimated_cost ?? (qtyEst(l) * Number(l.cost_per_unit || 0)));
  const costAct = (l) => Number(l.actual_cost ?? (Number(l.qty_actual || 0) * Number(l.cost_per_unit || 0)));
  const totalEst = lines.reduce((s, l) => s + costEst(l), 0);
  const totalAct = lines.reduce((s, l) => s + costAct(l), 0);
  const warnings = bom?.warnings || expect?.warnings || [];
  const srcTemplates = bom?.source_templates || expect?.source_templates || [];

  const actionBar = (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={() => syncBom(null)} disabled={busy || !poId}
        className="h-8 bg-cyan-600 hover:bg-cyan-700 text-white" data-testid="po360-bom-sync">
        <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${busy ? 'animate-spin' : ''}`} />
        {busy ? 'Menyinkronkan...' : 'Sinkronkan dari Template Aktif'}
      </Button>
      <Button size="sm" variant="outline" onClick={openPicker} disabled={busy || !poId}
        className="h-8 border-foreground/15" data-testid="po360-bom-pick-version">
        <Layers className="w-3.5 h-3.5 mr-1.5" /> Pilih Versi Template
      </Button>
    </div>
  );

  const picker = pickerOpen && (
    <GlassCard className="p-4 space-y-2 border-cyan-500/30" data-testid="po360-bom-template-picker">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">Terapkan versi template tertentu</h4>
        <Button size="sm" variant="ghost" onClick={() => setPickerOpen(false)}><X className="w-4 h-4" /></Button>
      </div>
      {templates.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">
          Tidak ada template untuk artikel pada PO ini. Buat dulu di Katalog Buyer → BOM Template.
        </p>
      ) : templates.map(t => (
        <div key={t.id} className="flex items-center justify-between border border-foreground/10 rounded-lg px-3 py-2">
          <div className="text-xs">
            <span className="font-semibold text-foreground">v{t.version}</span>
            {t.version_label ? <span className="text-muted-foreground"> · {t.version_label}</span> : null}
            {t.is_active ? <span className="ml-2 text-emerald-600 dark:text-emerald-300">(aktif)</span> : null}
            <div className="text-muted-foreground">{(t.materials || []).length} material · {t.buyer_catalog_code || t.buyer_catalog_id}</div>
          </div>
          <Button size="sm" variant="outline" className="h-7 border-foreground/15"
            disabled={busy} onClick={() => syncBom(t.id)}>Terapkan</Button>
        </div>
      ))}
      <p className="text-[11px] text-muted-foreground">
        Versi yang dipilih manual akan <b>dikunci</b> — tidak ditimpa saat item PO diubah.
      </p>
    </GlassCard>
  );

  const expectationCard = expect && expect.lines?.length > 0 && (
    <GlassCard className="p-4 space-y-3" data-testid="po360-material-expectation">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <BoxesIcon className="w-4 h-4 text-amber-600 dark:text-amber-300" />
          Ekspektasi Material dari Klien
        </h3>
        <div className="flex gap-3 text-xs">
          <span className="text-muted-foreground">Belum datang: <b className="text-amber-600 dark:text-amber-300">{expect.summary.pending}</b></span>
          <span className="text-muted-foreground">Sebagian: <b className="text-blue-600 dark:text-blue-300">{expect.summary.partial}</b></span>
          <span className="text-muted-foreground">Lengkap: <b className="text-emerald-600 dark:text-emerald-300">{expect.summary.complete}</b></span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b border-foreground/10">
              <th className="text-left py-2 px-2">Material</th>
              <th className="text-left py-2 px-2">Jenis</th>
              <th className="text-right py-2 px-2">Ditunggu</th>
              <th className="text-right py-2 px-2">Diterima</th>
              <th className="text-right py-2 px-2">Sisa</th>
              <th className="text-left py-2 px-2">Satuan</th>
              <th className="text-left py-2 px-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {expect.lines.map((l, i) => (
              <tr key={i} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                <td className="py-2 px-2 text-foreground">{l.material_name}</td>
                <td className="py-2 px-2 text-foreground/70">{CAT_LABEL[l.material_category] || l.material_category || '—'}</td>
                <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(l.qty_expected)}</td>
                <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300">{fmtNum(l.qty_received)}</td>
                <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtNum(l.qty_outstanding)}</td>
                <td className="py-2 px-2 text-muted-foreground">{l.unit || '—'}</td>
                <td className="py-2 px-2">
                  <StatusBadge status={l.status} dict={{
                    pending:  { label: 'Belum datang', color: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400 dark:border-amber-400/30' },
                    partial:  { label: 'Sebagian',     color: 'bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400 dark:border-blue-400/30' },
                    complete: { label: 'Lengkap',      color: 'bg-green-100 dark:bg-green-500/15 text-green-700 dark:text-green-300 border-green-400 dark:border-green-400/30' },
                  }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Dihitung dari BOM PO vs Penerimaan Material yang tercatat — tidak menyentuh stok.
      </p>
    </GlassCard>
  );

  if (!bom) {
    return (
      <div className="space-y-4">
        <GlassCard className="p-8 text-center text-muted-foreground/80 space-y-3">
          <FileText className="w-12 h-12 mx-auto opacity-30" />
          <p className="text-sm">Belum ada BOM untuk PO ini.</p>
          <p className="text-xs">
            Klik <b>Sinkronkan dari Template Aktif</b> untuk menurunkan kebutuhan material dari
            BOM Template artikel katalog. Aksesoris otomatis masuk ke kebutuhan PO dan ikut
            tercetak di Surat Jalan.
          </p>
          <div className="flex justify-center">{actionBar}</div>
        </GlassCard>
        {picker}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> Bill of Materials
              {bom.source === 'template_manual' && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300 border border-violet-400/40">
                  versi dipilih manual (terkunci)
                </span>
              )}
            </h3>
            <div className="text-xs text-muted-foreground mt-1">
              {srcTemplates.length > 0
                ? <>Sumber: {srcTemplates.map(t => `v${t.version}${t.label ? ` (${t.label})` : ''}`).join(', ')}</>
                : <>Sumber template belum tercatat</>}
              {bom.total_qty ? <> · Basis {fmtNum(bom.total_qty)} pcs</> : null}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-4 text-xs">
              <div><span className="text-muted-foreground">Total Est: </span><span className="text-blue-600 dark:text-blue-300 font-semibold">{fmtRp(totalEst)}</span></div>
              <div><span className="text-muted-foreground">Total Aktual: </span><span className="text-green-600 dark:text-green-300 font-semibold">{fmtRp(totalAct)}</span></div>
            </div>
            {actionBar}
          </div>
        </div>

        {warnings.length > 0 && (
          <div className="rounded-lg border border-amber-400/40 bg-amber-50 dark:bg-amber-500/10 p-3 space-y-1" data-testid="po360-bom-warnings">
            {warnings.map((w, i) => (
              <div key={i} className="text-xs text-amber-800 dark:text-amber-200 flex gap-2">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" /><span>{w}</span>
              </div>
            ))}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b border-foreground/10">
                <th className="text-left py-2 px-2">Material</th>
                <th className="text-left py-2 px-2">Kategori</th>
                <th className="text-right py-2 px-2">Qty/pcs</th>
                <th className="text-right py-2 px-2">Qty Est</th>
                <th className="text-right py-2 px-2">Qty Aktual</th>
                <th className="text-left py-2 px-2">Unit</th>
                <th className="text-left py-2 px-2">Dipasok</th>
                <th className="text-right py-2 px-2">Biaya Est</th>
                <th className="text-right py-2 px-2">Biaya Aktual</th>
              </tr>
            </thead>
            <tbody>
              {lines.length === 0 ? (
                <tr><td colSpan="9" className="py-4 text-center text-muted-foreground/60 italic">Belum ada material line.</td></tr>
              ) : lines.map((l, idx) => (
                <tr key={idx} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                  <td className="py-2 px-2 text-foreground">
                    {l.material_name || l.name}
                    {l.line_type === 'bulk' && <span className="ml-2 text-[10px] text-cyan-700 dark:text-cyan-300">bulk</span>}
                  </td>
                  <td className="py-2 px-2 text-foreground/70">{CAT_LABEL[l.material_category] || l.material_category || l.category || '—'}</td>
                  <td className="py-2 px-2 text-right text-foreground/60">{fmtNum(l.qty_per_pcs)}</td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(qtyEst(l))}</td>
                  <td className="py-2 px-2 text-right text-foreground/70">{fmtNum(l.qty_actual)}</td>
                  <td className="py-2 px-2 text-muted-foreground">{l.unit || '—'}</td>
                  <td className="py-2 px-2 text-foreground/70">{(l.ownership || 'client_provided') === 'client_provided' ? 'Klien' : 'CV. DA'}</td>
                  <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtRp(costEst(l))}</td>
                  <td className="py-2 px-2 text-right text-green-600 dark:text-green-300">{fmtRp(costAct(l))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
      {picker}
      {expectationCard}
    </div>
  );
}

function SamplesTab({ data }) {
  const samples = data?.samples || [];
  const revisions = data?.sample_revisions || [];
  if (samples.length === 0) {
    return (
      <GlassCard className="p-8 text-center text-muted-foreground/60">
        <Clipboard className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Belum ada sample untuk PO ini.</p>
      </GlassCard>
    );
  }
  return (
    <div className="space-y-4">
      {samples.map(s => {
        const revs = revisions.filter(r => r.sample_id === s.id);
        return (
          <GlassCard key={s.id} className="p-4 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-bold text-foreground">{s.sample_code}</span>
                  <StatusBadge status={s.status} dict={{
                    draft:               { label: 'Draft',             color: 'bg-muted dark:bg-slate-500/15 text-foreground/70 border-border dark:border-slate-400/30' },
                    in_progress:         { label: 'Sedang Dibuat',     color: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-400/30' },
                    submitted:           { label: 'Menunggu Approval', color: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-400/30' },
                    approved:            { label: 'Disetujui',         color: 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border-green-400 dark:border-green-400/30' },
                    rejected:            { label: 'Ditolak',           color: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300 border-red-400 dark:border-red-400/30' },
                    revision_requested:  { label: 'Revisi',            color: 'bg-orange-500/15 text-orange-300 border-orange-400/30' },
                  }} />
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">{s.artikel || '—'} {s.color ? `· ${s.color}` : ''} {s.size ? `· ${s.size}` : ''}</div>
              </div>
              <div className="text-xs text-muted-foreground/60">{fmtDate(s.created_at)}</div>
            </div>
            {s.notes && <p className="text-xs text-muted-foreground italic">{s.notes}</p>}
            {revs.length > 0 && (
              <div className="pl-3 border-l-2 border-orange-400/30 space-y-1">
                <div className="text-[10px] text-orange-300 uppercase tracking-wider">Riwayat Revisi ({revs.length})</div>
                {revs.map(r => (
                  <div key={r.id} className="text-xs text-muted-foreground">
                    <span className="text-muted-foreground/60">{fmtDate(r.created_at)}</span> — {r.reason || r.notes || 'Revisi'}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        );
      })}
    </div>
  );
}

function ProductionTab({ data }) {
  const { po } = data || {};
  const items = po?.items || [];
  if (items.length === 0) {
    return <GlassCard className="p-8 text-center text-muted-foreground/60 text-sm">Belum ada item produksi.</GlassCard>;
  }
  return (
    <GlassCard className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <Activity className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Status Produksi per Item / WO
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b border-foreground/10">
              <th className="text-left py-2 px-2">Seri</th>
              <th className="text-left py-2 px-2">Artikel</th>
              <th className="text-left py-2 px-2">Warna/Size</th>
              <th className="text-left py-2 px-2">WO Number</th>
              <th className="text-right py-2 px-2">Target</th>
              <th className="text-right py-2 px-2">Produced</th>
              <th className="text-right py-2 px-2">% Progress</th>
              <th className="text-left py-2 px-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map(it => {
              const pct = it.qty > 0 ? Math.round(((it.qty_produced || 0) / it.qty) * 100) : 0;
              return (
                <tr key={it.item_id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                  <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{it.seri_no}</td>
                  <td className="py-2 px-2 text-foreground">{it.artikel}</td>
                  <td className="py-2 px-2 text-foreground/70">{it.color || '—'}/{it.size || '—'}</td>
                  <td className="py-2 px-2 font-mono text-cyan-600 dark:text-cyan-300">{it.wo_number || <span className="text-muted-foreground/50">belum dibuat</span>}</td>
                  <td className="py-2 px-2 text-right text-foreground">{fmtNum(it.qty)}</td>
                  <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtNum(it.qty_produced)}</td>
                  <td className="py-2 px-2 text-right">
                    <div className="flex items-center gap-2 justify-end">
                      <div className="w-16 h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-violet-500 to-green-500" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-foreground/70 w-8 text-right">{pct}%</span>
                    </div>
                  </td>
                  <td className="py-2 px-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{it.status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}

function QCTab({ data }) {
  const qcs = data?.qc_checks || [];
  if (qcs.length === 0) {
    return (
      <GlassCard className="p-8 text-center text-muted-foreground/60">
        <ShieldCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Belum ada QC check untuk PO ini.</p>
      </GlassCard>
    );
  }
  return (
    <GlassCard className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <ShieldCheck className="w-4 h-4 text-green-600 dark:text-green-300" /> Quality Control Checks ({qcs.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b border-foreground/10">
              <th className="text-left py-2 px-2">Tanggal</th>
              <th className="text-left py-2 px-2">Stage</th>
              <th className="text-right py-2 px-2">Sample Size</th>
              <th className="text-right py-2 px-2">Defects</th>
              <th className="text-right py-2 px-2">% Defect</th>
              <th className="text-left py-2 px-2">Result</th>
              <th className="text-left py-2 px-2">Checked By</th>
              <th className="text-left py-2 px-2">Catatan</th>
            </tr>
          </thead>
          <tbody>
            {qcs.map(q => {
              const sampleSize = q.sample_size || q.qty_checked || 0;
              const defects = q.defect_count || q.qty_defect || 0;
              const pct = sampleSize > 0 ? ((defects / sampleSize) * 100).toFixed(1) : '—';
              const isPass = ['pass', 'passed'].includes(q.result);
              return (
                <tr key={q.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                  <td className="py-2 px-2 text-foreground/70">{fmtDate(q.created_at)}</td>
                  <td className="py-2 px-2 text-violet-600 dark:text-violet-300">{q.stage || '—'}</td>
                  <td className="py-2 px-2 text-right text-foreground">{fmtNum(sampleSize)}</td>
                  <td className="py-2 px-2 text-right text-red-600 dark:text-red-300">{fmtNum(defects)}</td>
                  <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{pct}%</td>
                  <td className="py-2 px-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${isPass ? 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border-green-400 dark:border-green-400/30' : 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300 border-red-400 dark:border-red-400/30'}`}>
                      {(q.result || 'pending').toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-muted-foreground">{q.checked_by_name || q.checked_by || '—'}</td>
                  <td className="py-2 px-2 text-muted-foreground italic truncate max-w-[180px]" title={q.notes}>{q.notes || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}

function BillingTab({ data }) {
  const invoices = data?.invoices || [];
  const payments = data?.payments || [];
  const arInvoice = data?.ar_invoice;
  return (
    <div className="space-y-4">
      {arInvoice && (
        <GlassCard className="p-4 border-emerald-300 dark:border-emerald-400/20">
          <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
            <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-300" /> AR Invoice (Finance)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div><span className="text-muted-foreground">Nomor: </span><span className="text-foreground font-mono">{arInvoice.invoice_number}</span></div>
            <div><span className="text-muted-foreground">Tanggal: </span><span className="text-foreground">{fmtDateOnly(arInvoice.invoice_date)}</span></div>
            <div><span className="text-muted-foreground">Total: </span><span className="text-green-600 dark:text-green-300 font-bold">{fmtRp(arInvoice.total_amount)}</span></div>
            <div><span className="text-muted-foreground">Status: </span><span className="text-emerald-600 dark:text-emerald-300 capitalize">{arInvoice.status}</span></div>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-blue-600 dark:text-blue-300" /> Maklon Invoices ({invoices.length})
        </h3>
        {invoices.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 italic">Belum ada invoice yang dibuat untuk PO ini.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-foreground/10">
                  <th className="text-left py-2 px-2">Invoice #</th>
                  <th className="text-left py-2 px-2">Tanggal</th>
                  <th className="text-left py-2 px-2">Due Date</th>
                  <th className="text-right py-2 px-2">Total</th>
                  <th className="text-right py-2 px-2">Dibayar</th>
                  <th className="text-right py-2 px-2">Outstanding</th>
                  <th className="text-left py-2 px-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map(inv => {
                  const paid = Number(inv.amount_paid || 0);
                  const total = Number(inv.total_amount || 0);
                  const outstanding = Math.max(0, total - paid);
                  return (
                    <tr key={inv.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                      <td className="py-2 px-2 font-mono text-blue-600 dark:text-blue-300">{inv.invoice_number}</td>
                      <td className="py-2 px-2 text-foreground/70">{fmtDateOnly(inv.issue_date || inv.invoice_date)}</td>
                      <td className="py-2 px-2 text-foreground/70">{fmtDateOnly(inv.due_date)}</td>
                      <td className="py-2 px-2 text-right text-foreground font-semibold">{fmtRp(total)}</td>
                      <td className="py-2 px-2 text-right text-green-600 dark:text-green-300">{fmtRp(paid)}</td>
                      <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtRp(outstanding)}</td>
                      <td className="py-2 px-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70 capitalize">{inv.status}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Banknote className="w-4 h-4 text-green-600 dark:text-green-300" /> Pembayaran ({payments.length})
        </h3>
        {payments.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 italic">Belum ada pembayaran tercatat.</p>
        ) : (
          <div className="space-y-1.5">
            {payments.map(p => (
              <div key={p.id} className="flex items-center justify-between p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
                <div>
                  <div className="text-xs font-mono text-green-600 dark:text-green-300">{p.payment_number || p.id.slice(0, 8)}</div>
                  <div className="text-[10px] text-muted-foreground">{fmtDateOnly(p.payment_date)} · {p.payment_method || 'transfer'}</div>
                </div>
                <div className="text-sm font-bold text-green-600 dark:text-green-300">{fmtRp(p.amount)}</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function HPPTab({ data }) {
  const hpp = data?.hpp || {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPIBigCard label="Nilai PO" value={fmtRp(hpp.po_total_value)} icon={DollarSign} tone="green" />
        <KPIBigCard label="Material Diterima (Klien)" value={fmtRp(hpp.material_received_value)} icon={BoxesIcon} tone="cyan" />
        <KPIBigCard label="Sudah Ditagih" value={fmtRp(hpp.invoiced_amount)} icon={FileText} tone="blue" />
      </div>
      <GlassCard className="p-4 space-y-2">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Snapshot HPP / Margin
        </h3>
        <table className="w-full text-xs mt-2">
          <tbody className="space-y-1">
            <HPPRow label="Nilai PO (Revenue)" value={hpp.po_total_value} tone="green" />
            <HPPRow label="BOM Estimasi (Biaya)" value={hpp.bom_estimated_cost} tone="blue" />
            <HPPRow label="BOM Aktual (Biaya)" value={hpp.bom_actual_cost} tone="cyan" />
            <HPPRow label="Material Diterima dari Klien" value={hpp.material_received_value} tone="amber" />
            <HPPRow label="Margin Estimasi" value={hpp.gross_margin_estimate} tone="emerald" emphasized />
            <HPPRow label="Margin Aktual" value={hpp.gross_margin_actual} tone="emerald" emphasized />
            <HPPRow label="Sudah Ditagih" value={hpp.invoiced_amount} tone="blue" />
            <HPPRow label="Sudah Dibayar" value={hpp.paid_amount} tone="green" />
            <HPPRow label="Outstanding" value={hpp.outstanding_amount} tone="red" emphasized />
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}

function KPIBigCard({ label, value, icon: Icon, tone }) {
  const t = { green: 'text-green-600 dark:text-green-300 bg-green-50 dark:bg-green-500/10', cyan: 'text-cyan-600 dark:text-cyan-300 bg-cyan-50 dark:bg-cyan-500/10', blue: 'text-blue-600 dark:text-blue-300 bg-blue-50 dark:bg-blue-500/10' }[tone] || 'text-foreground/70 bg-foreground/5';
  return (
    <GlassCard className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        {Icon && <Icon className="w-3.5 h-3.5" />} {label}
      </div>
      <div className={`text-2xl font-bold ${t.split(' ')[0]}`}>{value}</div>
    </GlassCard>
  );
}

function HPPRow({ label, value, tone = 'slate', emphasized = false }) {
  const t = { green: 'text-green-600 dark:text-green-300', blue: 'text-blue-600 dark:text-blue-300', cyan: 'text-cyan-600 dark:text-cyan-300', amber: 'text-amber-600 dark:text-amber-300', emerald: 'text-emerald-600 dark:text-emerald-300', red: 'text-red-600 dark:text-red-300', slate: 'text-foreground/70' }[tone];
  return (
    <tr className="border-b border-foreground/5">
      <td className={`py-1.5 px-2 ${emphasized ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>{label}</td>
      <td className={`py-1.5 px-2 text-right ${t} ${emphasized ? 'font-bold' : ''}`}>
        {value === null || value === undefined ? <span className="text-muted-foreground/50 italic">N/A</span> : fmtRp(value)}
      </td>
    </tr>
  );
}

function TimelineTab({ timeline, loading, onRefresh }) {
  if (loading) return <div className="flex items-center justify-center h-40 text-muted-foreground">Memuat timeline...</div>;
  const events = timeline?.events || [];
  if (events.length === 0) {
    return <GlassCard className="p-8 text-center text-muted-foreground/60 text-sm">Belum ada activity untuk PO ini.</GlassCard>;
  }
  return (
    <GlassCard className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Timeline Aktivitas ({events.length} event)
        </h3>
        <Button variant="ghost" size="sm" onClick={onRefresh} className="text-muted-foreground hover:text-foreground">
          <RefreshCw className="w-3 h-3 mr-1" /> Refresh
        </Button>
      </div>
      <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
        {events.map((e, idx) => (
          <motion.div
            key={`${e.type}-${e.when}-${idx}`}
            initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.02 }}
            className="flex items-start gap-3 p-3 rounded-lg bg-foreground/[0.03] border-l-2 border-violet-500 dark:border-violet-400/40 hover:bg-foreground/5"
          >
            <div className="w-8 h-8 rounded-full bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center flex-shrink-0">
              <TimelineIcon name={e.icon} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-foreground">{e.label}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-muted-foreground">{e.type}</span>
              </div>
              <div className="text-[10px] text-muted-foreground/60 mt-0.5 flex items-center gap-2 flex-wrap">
                <Clock className="w-3 h-3" /> {fmtDate(e.when)}
                {(e.actor_name || e.actor) && <span>· oleh {e.actor_name || e.actor}</span>}
                {e.reason && <span className="text-red-600 dark:text-red-300">· Reason: {e.reason}</span>}
                {e.amount && <span className="text-green-600 dark:text-green-300">· {fmtRp(e.amount)}</span>}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}

function TimelineIcon({ name }) {
  const map = {
    'package': Package, 'check-circle': CheckCircle2, 'ban': Ban, 'truck': Truck,
    'check': CheckCircle2, 'x-circle': X, 'inbox': BoxesIcon, 'clipboard': Clipboard,
    'send': Send, 'x': X, 'shield-check': ShieldCheck, 'shield-alert': AlertCircle,
    'file-text': FileText, 'banknote': Banknote, 'activity': Activity, 'trophy': TrendingUp,
  };
  const Icon = map[name] || Activity;
  return <Icon className="w-4 h-4 text-violet-600 dark:text-violet-300" />;
}

// ─── Main Component ────────────────────────────────────────────────────────
export default function MaklonPO360Module({ token, deepLinkParams, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [selectedPoId, setSelectedPoId] = useState(deepLinkParams?.po_id || null);
  const [data, setData] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [tab, setTab] = useState(deepLinkParams?.tab || 'detail');

  const fetchData = useCallback(async () => {
    if (!selectedPoId) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos/${selectedPoId}/360`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat data 360°');
        setSelectedPoId(null);
        return;
      }
      setData(await r.json());
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedPoId, headers]);

  const fetchTimeline = useCallback(async () => {
    if (!selectedPoId) return;
    setTimelineLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/maklon/pos/${selectedPoId}/timeline`, { headers });
      if (r.ok) setTimeline(await r.json());
    } catch (e) {
      console.error('timeline error', e);
    } finally {
      setTimelineLoading(false);
    }
  }, [selectedPoId, headers]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { if (tab === 'timeline') fetchTimeline(); }, [tab, fetchTimeline]);

  // Update deep link param when selection changes externally (for fresh load via PO list nav)
  useEffect(() => {
    if (deepLinkParams?.po_id && deepLinkParams.po_id !== selectedPoId) {
      setSelectedPoId(deepLinkParams.po_id);
    }
  }, [deepLinkParams?.po_id, selectedPoId]);

  const handlePick = (po) => {
    setSelectedPoId(po.id);
  };

  const handleBack = () => {
    setSelectedPoId(null);
    setData(null);
    setTimeline(null);
    setTab('detail');
  };

  const handleRefresh = () => {
    fetchData();
    if (tab === 'timeline') fetchTimeline();
  };

  if (!selectedPoId) {
    return <POPickerView headers={headers} onPick={handlePick} onBack={() => onNavigate?.('maklon-dashboard')} onNavigate={onNavigate} />;
  }

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <GlassCard className="p-8 flex flex-col items-center justify-center text-muted-foreground">
          <RefreshCw className="w-8 h-8 mb-2 animate-spin text-violet-700 dark:text-violet-400" />
          Memuat 360° View untuk PO {selectedPoId.slice(0, 8)}…
        </GlassCard>
      </div>
    );
  }

  if (!data) {
    return (
      <GlassCard className="p-8 text-center text-muted-foreground space-y-3">
        <AlertCircle className="w-10 h-10 mx-auto text-red-700 dark:text-red-400" />
        <p>Gagal memuat data PO.</p>
        <Button onClick={handleBack} variant="outline" className="border-foreground/10">Kembali ke daftar</Button>
      </GlassCard>
    );
  }

  const tabs = [
    { value: 'detail',     label: 'Detail',     icon: Package },
    { value: 'bom',        label: 'BOM',        icon: Layers },
    { value: 'samples',    label: 'Sample',     icon: Clipboard },
    { value: 'production', label: 'Produksi',   icon: Activity },
    { value: 'qc',         label: 'QC',         icon: ShieldCheck },
    { value: 'billing',    label: 'Billing',    icon: DollarSign },
    { value: 'hpp',        label: 'HPP',        icon: BarChart3 },
    { value: 'timeline',   label: 'Timeline',   icon: Clock },
  ];

  return (
    <div className="space-y-6">
      <HeaderStrip kpis={data.kpis || {}} onBack={handleBack} onRefresh={handleRefresh} loading={loading} />

      {data.progress_breakdown?.breakdown && (
        <GlassCard className="p-4" data-testid="po360-progress-breakdown">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-violet-600" /> Progress Multi-State (Barang Jadi vs Reject vs Permak)
            </h3>
            <div className="text-xs text-muted-foreground">
              Barang Jadi: <span className="font-semibold text-emerald-600">{fmtNum(data.progress_breakdown.breakdown.qty_good)}</span> ·
              {' '}Siap kirim: <span className="font-semibold text-foreground">{fmtNum(data.progress_breakdown.breakdown.qty_good_ready)}</span>
            </div>
          </div>
          <ProgressBreakdownBar breakdown={data.progress_breakdown.breakdown} />
        </GlassCard>
      )}

      <GlassCard className="p-4">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-foreground/5 grid grid-cols-4 md:grid-cols-8 gap-1 h-auto p-1">
            {tabs.map(t => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                data-testid={`po360-tab-${t.value}`}
                className="data-[state=active]:bg-violet-600 data-[state=active]:text-foreground text-xs flex items-center gap-1.5"
              >
                <t.icon className="w-3.5 h-3.5" /> {t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <div className="mt-5">
            <AnimatePresence mode="wait">
              <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                {tab === 'detail'     && <DetailTab data={data} />}
                {tab === 'bom'        && <BOMTab data={data} poId={selectedPoId} headers={headers} onRefresh={fetchData} />}
                {tab === 'samples'    && <SamplesTab data={data} />}
                {tab === 'production' && <ProductionTab data={data} />}
                {tab === 'qc'         && <QCTab data={data} />}
                {tab === 'billing'    && <BillingTab data={data} />}
                {tab === 'hpp'        && <HPPTab data={data} />}
                {tab === 'timeline'   && <TimelineTab timeline={timeline} loading={timelineLoading} onRefresh={fetchTimeline} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </Tabs>
      </GlassCard>
    </div>
  );
}

