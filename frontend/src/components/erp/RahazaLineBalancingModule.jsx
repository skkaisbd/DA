import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Activity, AlertTriangle, CheckCircle2, Users, Target, BarChart3, RefreshCw, Calendar, ChevronDown, ChevronUp } from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';

const BALANCE_COLOR = (ratio) => {
  if (!ratio) return 'text-muted-foreground';
  if (ratio > 110) return 'text-red-300';
  if (ratio < 70) return 'text-amber-300';
  return 'text-emerald-300';
};

const BALANCE_BG = (type) => {
  if (type === 'overloaded') return 'border-red-300/20 bg-red-400/5';
  if (type === 'underutilized') return 'border-amber-300/20 bg-amber-400/5';
  return 'border-emerald-300/20 bg-emerald-400/5';
};

const BALANCE_LABEL = { overloaded: 'Overloaded', underutilized: 'Kurang Optimal', null: 'Seimbang' };

function BalanceMeter({ ratio }) {
  if (!ratio) return <span className="text-xs text-muted-foreground">N/A</span>;
  const pct = Math.min(ratio, 150);
  const color = ratio > 110 ? '#f87171' : ratio < 70 ? '#fbbf24' : '#34d399';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-[var(--glass-bg)] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color, maxWidth: '100%' }} />
      </div>
      <span className={`text-xs font-mono font-bold w-12 ${BALANCE_COLOR(ratio)}`}>{ratio}%</span>
    </div>
  );
}

export default function RahazaLineBalancingModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [shifts, setShifts] = useState([]);
  const [shiftId, setShiftId] = useState('');
  const [expandedLine, setExpandedLine] = useState(null);
  const headers = { Authorization: `Bearer ${token}` };

  const loadShifts = useCallback(async () => {
    const r = await fetch('/api/rahaza/shifts', { headers });
    if (r.ok) setShifts(await r.json());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadBalance = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ assign_date: date });
      if (shiftId) params.set('shift_id', shiftId);
      const r = await fetch(`/api/rahaza/supervisor/line-balance?${params}`, { headers });
      if (r.ok) setData(await r.json());
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, date, shiftId]);

  useEffect(() => { loadShifts(); }, [loadShifts]);
  useEffect(() => { loadBalance(); }, [loadBalance]);

  const s = data?.summary || {};

  return (
    <div className="space-y-5" data-testid="line-balance-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Line Balancing</h1>
          <p className="text-muted-foreground text-sm mt-1">Analisis keseimbangan beban kerja antar lini produksi berdasarkan operator, target, dan kapasitas SAM.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 border border-[var(--glass-border)] rounded-lg px-2.5 h-9">
            <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="bg-transparent text-sm text-foreground outline-none" data-testid="lb-date" />
          </div>
          <SmartNativeSelect value={shiftId} onChange={e => setShiftId(e.target.value)}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="lb-shift">
            <option value="">Semua Shift</option>
            {shifts.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </SmartNativeSelect>
          <Button variant="ghost" onClick={loadBalance} className="border border-[var(--glass-border)] h-9 px-3">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Factory Summary */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3" data-testid="lb-summary">
          <GlassPanel className="p-3 col-span-1">
            <p className="text-xs text-muted-foreground">Total Lini</p>
            <p className="text-2xl font-bold text-foreground">{s.total_lines || 0}</p>
          </GlassPanel>
          <GlassPanel className="p-3 col-span-1">
            <p className="text-xs text-muted-foreground">Total Operator</p>
            <p className="text-2xl font-bold text-foreground">{s.total_operators || 0}</p>
          </GlassPanel>
          <GlassPanel className="p-3 col-span-1">
            <p className="text-xs text-muted-foreground">Target (pcs)</p>
            <p className="text-2xl font-bold text-primary">{(s.total_target_pcs || 0).toLocaleString()}</p>
          </GlassPanel>
          <GlassPanel className="p-3 col-span-1">
            <p className="text-xs text-muted-foreground">Kapasitas Est.</p>
            <p className="text-2xl font-bold text-foreground">{(s.total_estimated_capacity || 0).toLocaleString()}</p>
          </GlassPanel>
          <GlassPanel className={`p-3 col-span-1 ${s.factory_balance_pct > 110 ? 'bg-red-400/10 border-red-300/20' : s.factory_balance_pct < 70 ? 'bg-amber-400/10 border-amber-300/20' : 'bg-emerald-400/10 border-emerald-300/20'}`}>
            <p className="text-xs text-muted-foreground">Balance Pabrik</p>
            <p className={`text-2xl font-bold ${BALANCE_COLOR(s.factory_balance_pct)}`}>{s.factory_balance_pct ?? '—'}%</p>
          </GlassPanel>
          <GlassPanel className="p-3 col-span-1 bg-red-400/8 border-red-300/20">
            <p className="text-xs text-muted-foreground">Overloaded</p>
            <p className="text-2xl font-bold text-red-300">{s.overloaded_lines || 0}</p>
          </GlassPanel>
          <GlassPanel className="p-3 col-span-1 bg-amber-400/8 border-amber-300/20">
            <p className="text-xs text-muted-foreground">Under-utilized</p>
            <p className="text-2xl font-bold text-amber-300">{s.underutilized_lines || 0}</p>
          </GlassPanel>
        </div>
      )}

      {/* Line Cards */}
      {loading ? (
        <div className="flex items-center justify-center h-48"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>
      ) : !data || data.lines.length === 0 ? (
        <GlassCard className="p-8 text-center text-muted-foreground">
          <BarChart3 className="w-12 h-12 opacity-20 mx-auto mb-3" />
          <p>Belum ada assignment untuk tanggal {date}. <br />Tambahkan assignment di menu "Assign Lini Hari Ini" terlebih dahulu.</p>
        </GlassCard>
      ) : (
        <div className="space-y-3" data-testid="lb-lines">
          {data.lines.map(line => (
            <GlassCard key={line.line_id} className={`p-4 border ${BALANCE_BG(line.imbalance_type)}`} data-testid={`lb-line-${line.line_code}`}>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-[var(--glass-bg)] flex items-center justify-center">
                    <Activity className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <p className="font-semibold text-foreground">{line.line_name}</p>
                    <p className="text-xs text-muted-foreground">{line.line_code} · {line.operator_count} operator</p>
                  </div>
                  {line.imbalance_type && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                      line.imbalance_type === 'overloaded' ? 'text-red-300 border-red-300/20 bg-red-400/10' : 'text-amber-300 border-amber-300/20 bg-amber-400/10'
                    }`}>
                      {BALANCE_LABEL[line.imbalance_type]}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-6 flex-wrap">
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">Target</p>
                    <p className="text-sm font-bold text-primary">{line.total_target_pcs.toLocaleString()} pcs</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">Kapasitas Est.</p>
                    <p className="text-sm font-bold text-foreground">{line.estimated_capacity.toLocaleString()} pcs</p>
                  </div>
                  {line.avg_sam_minutes && (
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Avg SAM</p>
                      <p className="text-sm font-bold text-foreground">{line.avg_sam_minutes} min</p>
                    </div>
                  )}
                  <div className="w-32">
                    <p className="text-xs text-muted-foreground mb-1">Balance</p>
                    <BalanceMeter ratio={line.balance_ratio_pct} />
                  </div>
                  <button onClick={() => setExpandedLine(expandedLine === line.line_id ? null : line.line_id)}
                    className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground" data-testid={`lb-expand-${line.line_code}`}>
                    {expandedLine === line.line_id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Operator list (expandable) */}
              {expandedLine === line.line_id && line.operators.length > 0 && (
                <div className="mt-3 pt-3 border-t border-[var(--glass-border)]">
                  <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">Operator di Lini Ini</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                    {line.operators.map(op => (
                      <div key={op.employee_id} className="flex items-center gap-2 p-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                        <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center text-[10px] font-bold text-primary shrink-0">
                          {(op.name || '?')[0]}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-foreground truncate">{op.name}</p>
                          <p className="text-[10px] text-muted-foreground">{op.shift_name} · {op.target_pcs} pcs target</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
