import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart3, RefreshCw, Scissors, Shirt, ClipboardCheck, PackageCheck,
  ChevronRight, CheckCircle2, AlertTriangle, Info, Edit3, BarChart2
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { motion } from 'framer-motion';

const STAGE_ROWS = [
  { key: 'cutting',  label: 'Cutting',  icon: Scissors,       color: 'text-violet-600 dark:text-violet-400',
    inputs: [{field:'qty_in', label:'Input ke Cutting'}, {field:'qty_out', label:'Output Cutting'}] },
  { key: 'sewing',   label: 'Sewing',   icon: Shirt,          color: 'text-purple-600 dark:text-purple-400',
    inputs: [{field:'qty_out', label:'Output Jahit'}] },
  { key: 'qc',       label: 'QC',       icon: ClipboardCheck, color: 'text-amber-700 dark:text-amber-400',
    inputs: [{field:'qty_pass', label:'QC Pass', color:'text-green-700 dark:text-green-400'}, {field:'qty_fail', label:'QC Fail', color:'text-red-700 dark:text-red-400'}] },
  { key: 'packing',  label: 'Packing',  icon: PackageCheck,   color: 'text-orange-600 dark:text-orange-400',
    inputs: [{field:'qty_out', label:'Output Packing'}] },
];

const STAGE_QTY_DISPLAY = [
  { key:'cutting_input',  label:'Cut Input',   stage:'cutting' },
  { key:'cutting_output', label:'Cut Output',  stage:'cutting' },
  { key:'sewing_output',  label:'Sew Output',  stage:'sewing'  },
  { key:'qc_pass',        label:'QC Pass',     stage:'qc',     color:'text-green-700 dark:text-green-400' },
  { key:'qc_fail',        label:'QC Fail',     stage:'qc',     color:'text-red-700 dark:text-red-400'  },
  { key:'packing_output', label:'Pack Output', stage:'packing' },
];

function StageInputDialog({ po, stage, summary, headers, onClose, onSuccess }) {
  const stageRow = STAGE_ROWS.find(s => s.key === stage);
  const sq = summary?.stage_qty || {};
  const [vals, setVals] = useState({
    qty_in:   sq.cutting_input  || '',
    qty_out:  stage === 'cutting' ? (sq.cutting_output || '') :
              stage === 'sewing'  ? (sq.sewing_output  || '') :
              stage === 'packing' ? (sq.packing_output || '') : '',
    qty_pass: sq.qc_pass || '',
    qty_fail: sq.qc_fail || '',
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { stage };
      if (stage === 'cutting') {
        if (vals.qty_in  !== '') payload.qty_in  = Number(vals.qty_in);
        if (vals.qty_out !== '') payload.qty_out = Number(vals.qty_out);
      } else if (stage === 'sewing') {
        if (vals.qty_out !== '') payload.qty_out = Number(vals.qty_out);
      } else if (stage === 'qc') {
        if (vals.qty_pass !== '') payload.qty_pass = Number(vals.qty_pass);
        if (vals.qty_fail !== '') payload.qty_fail = Number(vals.qty_fail);
      } else if (stage === 'packing') {
        if (vals.qty_out !== '') payload.qty_out = Number(vals.qty_out);
      }
      const r = await fetch(`/api/production-pos/${po.id}/stage-qty`, {
        method: 'PUT', headers, body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error((await r.json()).detail || 'Gagal');
      toast.success(`Stage qty ${stageRow?.label} diperbarui`);
      onSuccess();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {stageRow?.icon && <stageRow.icon className="w-4 h-4" />}
            Input Qty — {stageRow?.label}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="text-xs text-foreground/50 flex items-center gap-2 bg-foreground/5 p-2 rounded">
            <Info className="w-3.5 h-3.5 shrink-0" />
            Target: <strong>{po.qty_ordered || summary?.qty_ordered || 0} pcs</strong>
            {summary?.wip_data_available && (
              <span className="ml-2 text-blue-600 dark:text-blue-400">• Data real dari WIP tersedia</span>
            )}
          </div>
          {stageRow?.inputs.map(inp => (
            <div key={inp.field} className="space-y-1.5">
              <Label className={`text-xs ${inp.color || ''}`}>{inp.label} (pcs)</Label>
              <Input
                type="number" min="0"
                value={vals[inp.field]}
                onChange={e => setVals(p => ({...p, [inp.field]: e.target.value}))}
                placeholder="0"
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Batal</Button>
          <Button onClick={save} disabled={saving}>{saving ? 'Menyimpan...' : 'Simpan'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function POStageTrackingPanel({ po, headers }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editStage, setEditStage] = useState(null);

  const load = useCallback(async () => {
    if (!po?.id) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/production-pos/${po.id}/stage-summary`, { headers });
      if (r.ok) setSummary(await r.json());
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [po?.id, headers]);

  useEffect(() => { load(); }, [load]);

  const sq = summary?.stage_qty || {};
  const qtyOrdered = summary?.qty_ordered || po?.qty_ordered || 0;
  const progress = summary?.progress_pct || 0;

  if (!po) return null;

  return (
    <div className="space-y-4" data-testid="po-stage-tracking">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-violet-600 dark:text-violet-400" />
          <span className="text-sm font-semibold text-foreground/80">Stage Tracking Produksi</span>
          {summary?.wip_data_available && (
            <span className="text-[10px] bg-blue-100 dark:bg-blue-500/15 border border-blue-400/25 text-blue-600 dark:text-blue-300 px-2 py-0.5 rounded-full">
              Data Real-Time WIP
            </span>
          )}
        </div>
        <Button size="sm" variant="ghost" onClick={load} className="h-7 w-7 p-0">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {loading && !summary ? (
        <div className="text-center py-6 text-foreground/40 text-xs">Memuat stage data...</div>
      ) : (
        <>
          {/* Progress bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-foreground/50">
              <span>Progress Produksi</span>
              <span className="font-bold text-foreground/80">{progress}%</span>
            </div>
            <div className="h-2 bg-foreground/10 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.6 }}
                className="h-full bg-gradient-to-r from-violet-500 to-purple-400 rounded-full"
              />
            </div>
          </div>

          {/* Stage cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {STAGE_ROWS.map(({ key, label, icon: Icon, color, inputs }) => {
              const hasData = STAGE_QTY_DISPLAY
                .filter(d => d.stage === key)
                .some(d => sq[d.key] > 0);
              return (
                <motion.div
                  key={key}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`rounded-xl border p-3 space-y-2 ${
                    hasData ? 'bg-primary/5 border-primary/25' : 'bg-foreground/[0.03] border-foreground/[0.08]'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-1.5">
                      <Icon className={`w-3.5 h-3.5 ${color}`} />
                      <span className="text-xs font-semibold text-foreground/70">{label}</span>
                    </div>
                    {hasData && <CheckCircle2 className="w-3 h-3 text-green-700 dark:text-green-400" />}
                  </div>
                  {STAGE_QTY_DISPLAY.filter(d => d.stage === key).map(d => (
                    <div key={d.key} className="flex justify-between text-xs">
                      <span className="text-foreground/40">{d.label}</span>
                      <span className={`font-bold ${d.color || 'text-foreground/80'}`}>
                        {sq[d.key] ?? '—'}
                      </span>
                    </div>
                  ))}
                  <Button
                    size="sm" variant="outline"
                    className="w-full h-6 text-[10px] mt-1 gap-1"
                    onClick={() => setEditStage(key)}
                  >
                    <Edit3 className="w-2.5 h-2.5" /> Input
                  </Button>
                </motion.div>
              );
            })}
          </div>

          {/* Summary row */}
          {summary && (
            <div className="flex flex-wrap items-center gap-3 text-xs bg-foreground/5 rounded-lg p-2.5">
              <span className="text-foreground/40">Target: {qtyOrdered} pcs</span>
              <span className="text-foreground/40">·</span>
              <span className="text-foreground/60">{summary.wo_count} WO terhubung</span>
              {(sq.qc_pass > 0 || sq.qc_fail > 0) && (
                <>
                  <span className="text-foreground/40">·</span>
                  <span className="text-green-700 dark:text-green-400">✓ {sq.qc_pass || 0} pass</span>
                  <span className="text-red-700 dark:text-red-400">✗ {sq.qc_fail || 0} fail</span>
                  <span className="text-foreground/40">
                    ({(((sq.qc_fail||0)/((sq.qc_pass||0)+(sq.qc_fail||0)||1))*100).toFixed(1)}% reject)
                  </span>
                </>
              )}
            </div>
          )}
        </>
      )}

      {editStage && (
        <StageInputDialog
          po={po} stage={editStage} summary={summary}
          headers={headers}
          onClose={() => setEditStage(null)}
          onSuccess={() => { setEditStage(null); load(); }}
        />
      )}
    </div>
  );
}
