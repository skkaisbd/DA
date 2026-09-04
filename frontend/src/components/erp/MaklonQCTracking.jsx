import { useState, useEffect, useCallback, useMemo } from 'react';
import { ClipboardCheck, Plus, RefreshCw, TrendingDown, AlertTriangle, BarChart3, Trash2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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

const STAGES = [
  { value: 'raw_material', label: 'Raw Material' },
  { value: 'cutting',      label: 'Cutting' },
  { value: 'sewing',       label: 'Sewing' },
  { value: 'final',        label: 'Final' },
  { value: 'pre_packing',  label: 'Pre-Packing' },
];

const RESULT_CONFIG = {
  pending:         { label: 'Pending',       color: 'bg-muted dark:bg-slate-500/15 text-foreground/70 border-border dark:border-slate-400/30' },
  pass:            { label: 'Pass',          color: 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border-green-400 dark:border-green-400/30' },
  pass_with_notes: { label: 'Pass w/ Notes', color: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-400/30' },
  fail:            { label: 'Fail',          color: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300 border-red-400 dark:border-red-400/30' },
  rework:          { label: 'Rework',        color: 'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300 border-orange-400 dark:border-orange-400/30' },
};

function ResultBadge({ result }) {
  const c = RESULT_CONFIG[result] || RESULT_CONFIG.pending;
  return <span className={`inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>{c.label}</span>;
}

export default function MaklonQCTracking({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [checks, setChecks] = useState([]);
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState({});
  const [pareto, setPareto] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('checks');
  const [stageFilter, setStageFilter] = useState('all');
  const [createDialog, setCreateDialog] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [c, o, s, p] = await Promise.all([
        fetch('/api/dewi/maklon/qc', { headers }),
        fetch('/api/dewi/maklon/pos', { headers }),
        fetch('/api/dewi/maklon/qc/summary/overview', { headers }),
        fetch('/api/dewi/maklon/qc/defect-pareto', { headers }),
      ]);
      if (c.ok) setChecks(await c.json());
      if (o.ok) setOrders(posToLegacyOrders(await o.json()));
      if (s.ok) setSummary(await s.json());
      if (p.ok) { const d = await p.json(); setPareto(d.items || []); }
    } catch (e) { toast.error('Gagal memuat QC'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const deleteCheck = async (c) => {
    if (!window.confirm('Hapus QC check ini?')) return;
    const r = await fetch(`/api/dewi/maklon/qc/${c.id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('QC dihapus'); fetchAll(); }
    else toast.error('Gagal menghapus');
  };

  const filtered = stageFilter === 'all' ? checks : checks.filter(c => c.stage === stageFilter);

  const stats = [
    { label: 'Total QC Checks', value: summary.total_checks || 0,                icon: ClipboardCheck, color: 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-500/10 border-blue-300 dark:border-blue-400/20' },
    { label: 'Total Diperiksa',  value: (summary.total_inspected || 0).toLocaleString('id-ID'), icon: BarChart3, color: 'text-cyan-600 dark:text-cyan-400 bg-cyan-100 dark:bg-cyan-500/10 border-cyan-300 dark:border-cyan-400/20' },
    { label: 'Reject Rate',     value: `${summary.overall_reject_rate_pct || 0}%`, icon: TrendingDown,   color: 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 border-red-300 dark:border-red-400/20' },
    { label: 'Alerts',          value: summary.alerts_count || 0,                 icon: AlertTriangle,  color: 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-400/20' },
  ];

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="p-6 space-y-6" data-testid="maklon-qc">
      <PageHeader
        title="QC Tracking Maklon"
        subtitle={`QC per tahap produksi dengan analisis reject rate (threshold: ${summary.reject_threshold_pct || 5}%)`}
        icon={ClipboardCheck}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={fetchAll} className="gap-2" data-testid="qc-refresh-btn">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button size="sm" onClick={() => setCreateDialog(true)} className="gap-1.5" data-testid="qc-create-btn">
              <Plus className="w-3.5 h-3.5" /> Input QC
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
            <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
              <div className={`w-8 h-8 rounded-lg border ${s.color} flex items-center justify-center mb-2`}>
                <s.icon className={`w-4 h-4 ${s.color.split(' ')[0]}`} />
              </div>
              <div className="text-2xl font-bold text-foreground">{s.value}</div>
              <div className="text-xs text-foreground/50">{s.label}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="checks">QC Records</TabsTrigger>
          <TabsTrigger value="pareto">Defect Pareto</TabsTrigger>
          <TabsTrigger value="by-stage">Per Stage</TabsTrigger>
        </TabsList>

        <TabsContent value="checks">
          <GlassCard className="p-5 space-y-3">
            <div className="flex gap-2 items-center">
              <Label className="text-xs">Filter Stage:</Label>
              <Select value={stageFilter} onValueChange={setStageFilter}>
                <SelectTrigger className="w-48 h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Stage</SelectItem>
                  {STAGES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {loading ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Memuat...</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada QC check</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="qc-table">
                  <thead><tr className="border-b border-foreground/5 text-xs text-foreground/50">
                    <th className="pb-2 text-left">Tanggal</th>
                    <th className="pb-2 text-left">Order</th>
                    <th className="pb-2 text-left">Stage</th>
                    <th className="pb-2 text-left">Inspector</th>
                    <th className="pb-2 text-right">Diperiksa</th>
                    <th className="pb-2 text-right">Pass</th>
                    <th className="pb-2 text-right">Reject</th>
                    <th className="pb-2 text-right">Reject %</th>
                    <th className="pb-2 text-left">Result</th>
                    <th className="pb-2 text-center">Aksi</th>
                  </tr></thead>
                  <tbody className="divide-y divide-white/5">
                    {paged.map(c => (
                      <tr key={c.id} className={`hover:bg-foreground/[0.03] ${c.alert_triggered ? 'bg-red-100 dark:bg-red-500/5' : ''}`}>
                        <td className="py-2.5 pr-3 text-xs text-foreground/60">{(c.inspected_at || '').slice(0, 10)}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/70">{c.order_code}</td>
                        <td className="py-2.5 pr-3"><Badge variant="outline" className="text-[10px]">{c.stage}</Badge></td>
                        <td className="py-2.5 pr-3 text-foreground/70">{c.inspector_name}</td>
                        <td className="py-2.5 pr-3 text-right font-semibold">{c.qty_inspected}</td>
                        <td className="py-2.5 pr-3 text-right text-green-700 dark:text-green-400">{c.qty_passed}</td>
                        <td className="py-2.5 pr-3 text-right text-red-700 dark:text-red-400">{c.qty_rejected}</td>
                        <td className="py-2.5 pr-3 text-right">
                          <span className={`font-semibold ${c.alert_triggered ? 'text-red-700 dark:text-red-400' : 'text-foreground/70'}`}>
                            {c.reject_rate_pct}%{c.alert_triggered && ' ⚠'}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3"><ResultBadge result={c.result} /></td>
                        <td className="py-2.5 text-center">
                          <Button size="icon" variant="ghost" className="w-7 h-7 text-red-400/70" onClick={() => deleteCheck(c)}><Trash2 className="w-3.5 h-3.5" /></Button>
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

        <TabsContent value="pareto">
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-4">Top Defects (Pareto Analysis)</h3>
            {pareto.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada data defect</div>
            ) : (
              <div className="space-y-2">
                {pareto.map((d, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="w-32 text-xs font-mono text-foreground/60 truncate">{d.defect_code}</div>
                    <div className="flex-1 text-sm truncate">{d.description}</div>
                    <div className="w-16 text-right text-xs text-foreground/60">{d.qty_total}</div>
                    <div className="w-48 bg-foreground/5 rounded-full h-2 overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-red-500 to-amber-400" style={{ width: `${d.pct_of_total}%` }} />
                    </div>
                    <div className="w-16 text-right text-xs font-semibold text-amber-600 dark:text-amber-300">{d.pct_of_total}%</div>
                    <div className="w-16 text-right text-xs text-foreground/40">Σ{d.cumulative_pct}%</div>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        </TabsContent>

        <TabsContent value="by-stage">
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-4">QC Distribution per Stage</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {STAGES.map(s => {
                const count = summary.by_stage?.[s.value] || 0;
                return (
                  <div key={s.value} className="bg-foreground/5 rounded p-4 border border-foreground/10">
                    <div className="text-xs text-foreground/50">{s.label}</div>
                    <div className="text-2xl font-bold text-foreground mt-1">{count}</div>
                    <div className="text-[10px] text-foreground/40">checks recorded</div>
                  </div>
                );
              })}
            </div>
          </GlassCard>
        </TabsContent>
      </Tabs>

      {createDialog && (
        <QCDialog orders={orders} headers={headers}
          onClose={() => setCreateDialog(false)}
          onSuccess={() => { setCreateDialog(false); fetchAll(); }}
        />
      )}
    </div>
  );
}

function QCDialog({ orders, headers, onClose, onSuccess }) {
  const [form, setForm] = useState({
    order_id: '', stage: 'cutting', qty_inspected: '', qty_passed: '', qty_rejected: '', qty_rework: 0,
    result: 'pending', notes: '', defects: [],
  });
  const [saving, setSaving] = useState(false);
  const [defectForm, setDefectForm] = useState({ defect_code: '', description: '', qty_affected: 1 });
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const addDefect = () => {
    if (!defectForm.description) { toast.error('Deskripsi defect wajib'); return; }
    setForm(p => ({ ...p, defects: [...p.defects, { ...defectForm, qty_affected: Number(defectForm.qty_affected) || 1 }] }));
    setDefectForm({ defect_code: '', description: '', qty_affected: 1 });
  };
  const removeDefect = (idx) => setForm(p => ({ ...p, defects: p.defects.filter((_, i) => i !== idx) }));

  const save = async () => {
    if (!form.order_id || !form.qty_inspected) { toast.error('Order & qty wajib'); return; }
    setSaving(true);
    const payload = {
      ...form,
      qty_inspected: Number(form.qty_inspected) || 0,
      qty_passed: Number(form.qty_passed) || 0,
      qty_rejected: Number(form.qty_rejected) || 0,
      qty_rework: Number(form.qty_rework) || 0,
    };
    const r = await fetch('/api/dewi/maklon/qc', { method: 'POST', headers, body: JSON.stringify(payload) });
    setSaving(false);
    if (r.ok) {
      const data = await r.json();
      toast.success(`QC tercatat. Reject rate: ${data.reject_rate_pct}%${data.alert_triggered ? ' ⚠ ALERT' : ''}`);
      onSuccess();
    } else {
      toast.error((await r.json()).detail || 'Gagal menyimpan');
    }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="qc-dialog">
        <DialogHeader><DialogTitle>Input QC Check</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1 col-span-2">
              <Label>Order *</Label>
              <Select value={form.order_id} onValueChange={v => set('order_id', v)}>
                <SelectTrigger data-testid="qc-order-select"><SelectValue placeholder="Pilih order..." /></SelectTrigger>
                <SelectContent>
                  {orders.filter(o => !['draft','cancelled'].includes(o.status)).map(o => (
                    <SelectItem key={o.id} value={o.id}>{o.order_code} — {o.product_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Stage *</Label>
              <Select value={form.stage} onValueChange={v => set('stage', v)}>
                <SelectTrigger data-testid="qc-stage-select"><SelectValue /></SelectTrigger>
                <SelectContent>{STAGES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Result</Label>
              <Select value={form.result} onValueChange={v => set('result', v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(RESULT_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>Qty Diperiksa *</Label><Input type="number" min="0" value={form.qty_inspected} onChange={e => set('qty_inspected', e.target.value)} data-testid="qc-qty-inspected" /></div>
            <div className="space-y-1"><Label>Qty Pass</Label><Input type="number" min="0" value={form.qty_passed} onChange={e => set('qty_passed', e.target.value)} /></div>
            <div className="space-y-1"><Label>Qty Reject</Label><Input type="number" min="0" value={form.qty_rejected} onChange={e => set('qty_rejected', e.target.value)} /></div>
            <div className="space-y-1"><Label>Qty Rework</Label><Input type="number" min="0" value={form.qty_rework} onChange={e => set('qty_rework', e.target.value)} /></div>
            <div className="space-y-1 col-span-2"><Label>Catatan</Label><Textarea value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} /></div>
          </div>

          <div className="border-t border-foreground/10 pt-3">
            <div className="text-xs font-semibold text-foreground/60 mb-2">Daftar Defect</div>
            <div className="grid grid-cols-[1fr_2fr_80px_auto] gap-2 mb-2">
              <Input placeholder="Kode (opsional)" value={defectForm.defect_code} onChange={e => setDefectForm({...defectForm, defect_code: e.target.value})} />
              <Input placeholder="Deskripsi defect" value={defectForm.description} onChange={e => setDefectForm({...defectForm, description: e.target.value})} />
              <Input type="number" min="1" placeholder="Qty" value={defectForm.qty_affected} onChange={e => setDefectForm({...defectForm, qty_affected: e.target.value})} />
              <Button size="sm" onClick={addDefect} data-testid="qc-add-defect-btn">Tambah</Button>
            </div>
            {form.defects.length > 0 && (
              <div className="space-y-1">
                {form.defects.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs bg-foreground/5 rounded px-2 py-1">
                    {d.defect_code && <span className="font-mono text-foreground/60">{d.defect_code}</span>}
                    <span className="flex-1">{d.description}</span>
                    <span className="font-semibold">qty: {d.qty_affected}</span>
                    <Button size="icon" variant="ghost" className="w-5 h-5 text-red-700 dark:text-red-400" onClick={() => removeDefect(i)}><Trash2 className="w-3 h-3" /></Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="qc-save-btn">{saving ? 'Menyimpan...' : 'Simpan QC'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
