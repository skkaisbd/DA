import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { AlertTriangle, Sparkles, TrendingDown, Users, Loader2, Brain, Target, UserX, Shield } from 'lucide-react';
import { IconButton } from '../IconButton';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts';

const RISK_COLOR = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' };
const RISK_LABEL = { high: 'Tinggi', medium: 'Sedang', low: 'Rendah' };

export default function HRAttritionModule({ token }) {
  const [loading, setLoading] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [department, setDepartment] = useState('');
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/attrition/dashboard`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setHistory(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat dashboard: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handlePredict = async () => {
    setPredicting(true);
    setResult(null);
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/attrition/predict${department ? `?department=${department}` : ''}`;
      const r = await fetch(url, { method: 'POST', headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data?.data);
      toast.success('Prediksi selesai!', { icon: <Sparkles className="w-4 h-4" /> });
      fetchHistory();
    } catch (e) {
      toast.error(`Prediksi gagal: ${e.message}`);
    } finally {
      setPredicting(false);
    }
  };

  const highRiskCount = result?.analysis?.employees?.filter(e => e.risk_level === 'high').length || 0;
  const mediumRiskCount = result?.analysis?.employees?.filter(e => e.risk_level === 'medium').length || 0;
  const lowRiskCount = result?.analysis?.employees?.filter(e => e.risk_level === 'low').length || 0;

  const riskDistribution = [
    { name: 'High Risk', value: highRiskCount, color: RISK_COLOR.high },
    { name: 'Medium Risk', value: mediumRiskCount, color: RISK_COLOR.medium },
    { name: 'Low Risk', value: lowRiskCount, color: RISK_COLOR.low },
  ];

  return (
    <div className="space-y-6 p-6" data-testid="hr-attrition-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-amber-500 to-red-600 flex items-center justify-center">
            <TrendingDown className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Predictive Attrition</h1>
            <p className="text-sm text-muted-foreground">Prediksi risiko resign karyawan dengan AI</p>
          </div>
        </div>
        <IconButton icon={Sparkles} onClick={fetchHistory} disabled={loading} tooltip="Refresh" />
      </div>

      {/* Control Panel */}
      <GlassCard className="p-6">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <Select value={department || '__all__'} onValueChange={(v) => setDepartment(v === '__all__' ? '' : v)}>
              <SelectTrigger>
                <SelectValue placeholder="Semua departemen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua Departemen</SelectItem>
                <SelectItem value="Production">Production</SelectItem>
                <SelectItem value="Warehouse">Warehouse</SelectItem>
                <SelectItem value="Finance">Finance</SelectItem>
                <SelectItem value="HR">HR</SelectItem>
                <SelectItem value="Marketing">Marketing</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handlePredict} disabled={predicting} className="shrink-0">
            {predicting ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Memprediksi...</> : <><Brain className="w-4 h-4 mr-2" /> Prediksi Attrition</>}
          </Button>
        </div>
      </GlassCard>

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Risk Summary Cards */}
          <GlassCard className="p-5 flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: `${RISK_COLOR.high}20`, border: `1px solid ${RISK_COLOR.high}35` }}>
              <AlertTriangle className="w-6 h-6" style={{ color: RISK_COLOR.high }} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground mb-0.5">High Risk</p>
              <p className="text-2xl font-bold text-foreground leading-none">{highRiskCount}</p>
              <p className="text-xs text-muted-foreground mt-1">Perlu perhatian segera</p>
            </div>
          </GlassCard>

          <GlassCard className="p-5 flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: `${RISK_COLOR.medium}20`, border: `1px solid ${RISK_COLOR.medium}35` }}>
              <Shield className="w-6 h-6" style={{ color: RISK_COLOR.medium }} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground mb-0.5">Medium Risk</p>
              <p className="text-2xl font-bold text-foreground leading-none">{mediumRiskCount}</p>
              <p className="text-xs text-muted-foreground mt-1">Pantau secara berkala</p>
            </div>
          </GlassCard>

          <GlassCard className="p-5 flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: `${RISK_COLOR.low}20`, border: `1px solid ${RISK_COLOR.low}35` }}>
              <Users className="w-6 h-6" style={{ color: RISK_COLOR.low }} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground mb-0.5">Low Risk</p>
              <p className="text-2xl font-bold text-foreground leading-none">{lowRiskCount}</p>
              <p className="text-xs text-muted-foreground mt-1">Stabil & engaged</p>
            </div>
          </GlassCard>
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Employee List */}
          <GlassCard className="p-6">
            <div className="flex items-center gap-2 mb-4">
              <Users className="w-5 h-5 text-indigo-500" />
              <h2 className="text-lg font-semibold text-foreground">Daftar Karyawan</h2>
            </div>
            <div className="space-y-2 max-h-[500px] overflow-y-auto">
              {result.analysis?.employees?.slice(0, 20).map((emp, i) => {
                const rColor = RISK_COLOR[emp.risk_level] || '#64748b';
                return (
                  <Dialog key={i}>
                    <DialogTrigger asChild>
                      <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)] transition-colors cursor-pointer">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{emp.name}</p>
                          <p className="text-xs text-muted-foreground">{emp.employee_id} • {emp.department}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-lg font-bold" style={{ color: rColor }}>{emp.risk_score}</span>
                          <Badge variant="outline" style={{ borderColor: rColor, color: rColor }}>{RISK_LABEL[emp.risk_level]}</Badge>
                        </div>
                      </div>
                    </DialogTrigger>
                    <DialogContent className="max-w-2xl">
                      <DialogHeader>
                        <DialogTitle>{emp.name} - Detail Risiko Attrition</DialogTitle>
                      </DialogHeader>
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-xs text-muted-foreground">ID Karyawan</p>
                            <p className="text-sm font-medium">{emp.employee_id}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Departemen</p>
                            <p className="text-sm font-medium">{emp.department}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Risk Score</p>
                            <p className="text-2xl font-bold" style={{ color: rColor }}>{emp.risk_score}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">Risk Level</p>
                            <Badge style={{ background: rColor }}>{RISK_LABEL[emp.risk_level]}</Badge>
                          </div>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-2">Faktor Risiko</p>
                          <ul className="space-y-1">
                            {emp.risk_factors?.map((rf, j) => (
                              <li key={j} className="text-xs text-muted-foreground flex items-start gap-2">
                                <span className="text-amber-500 mt-0.5">•</span>{rf}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-2">Saran Retensi</p>
                          <ul className="space-y-1">
                            {emp.retention_suggestions?.map((rs, j) => (
                              <li key={j} className="text-xs text-muted-foreground flex items-start gap-2">
                                <span className="text-green-500 mt-0.5">•</span>{rs}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </DialogContent>
                  </Dialog>
                );
              })}
            </div>
          </GlassCard>

          {/* Insights Panel */}
          <GlassCard className="p-6 space-y-6">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-emerald-500" />
                <h2 className="text-lg font-semibold text-foreground">Insights & Action Items</h2>
              </div>
              {result.analysis?.overall_insights && (
                <div className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] mb-4">
                  <p className="text-xs text-muted-foreground leading-relaxed">{result.analysis.overall_insights}</p>
                </div>
              )}
              {result.analysis?.priority_actions && result.analysis.priority_actions.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2">Aksi Prioritas</h3>
                  <ul className="space-y-2">
                    {result.analysis.priority_actions.map((pa, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <span className="text-blue-500 font-bold mt-0.5">{i + 1}.</span>{pa}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Department Summary */}
            {result.analysis?.department_summary && result.analysis.department_summary.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-3">Ringkasan per Departemen</h3>
                <div className="space-y-2">
                  {result.analysis.department_summary.map((ds, i) => (
                    <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                      <span className="text-xs font-medium text-foreground">{ds.department}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground">Avg Risk: <span className="font-bold">{ds.avg_risk?.toFixed(1) || 0}</span></span>
                        <Badge variant="outline" style={{ borderColor: RISK_COLOR.high, color: RISK_COLOR.high }}>{ds.high_risk_count} High</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </GlassCard>
        </div>
      )}

      {!result && (
        <GlassCard className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <TrendingDown className="w-16 h-16 text-muted-foreground/40 mb-4" />
            <p className="text-sm text-muted-foreground">Klik "Prediksi Attrition" untuk memulai analisis risiko resign karyawan</p>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
