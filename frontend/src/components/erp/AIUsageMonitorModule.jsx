import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  DollarSign, Activity, AlertTriangle, CheckCircle2, RefreshCw, Loader2,
  TrendingUp, Zap, Clock, Brain, BarChart3, List, Sparkles, Settings, Save, Power
} from 'lucide-react';

const HEALTH_COLOR = {
  healthy: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  monitor: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30',
};

const HEALTH_LABEL = {
  healthy: 'Sehat',
  monitor: 'Pantau',
  warning: 'Peringatan',
  critical: 'Kritis',
};

function fmtUSD(v) {
  if (v == null) return '$0.0000';
  return `$${Number(v).toFixed(4)}`;
}

function fmtNum(v) {
  if (v == null) return '0';
  return Number(v).toLocaleString('id-ID');
}

export default function AIUsageMonitorModule({ token }) {
  const [activeTab, setActiveTab] = useState('today');
  const [today, setToday] = useState(null);
  const [summary, setSummary] = useState(null);
  const [logs, setLogs] = useState([]);
  const [budgets, setBudgets] = useState(null);
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [period, setPeriod] = useState(7);
  const [loading, setLoading] = useState(false);
  const [logFilter, setLogFilter] = useState('');

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const BASE = process.env.REACT_APP_BACKEND_URL;

  const fetchToday = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/ai/usage/today`, { headers });
      const data = await r.json();
      setToday(data?.data || null);
    } catch (e) { console.error(e); }
  }, [BASE, headers]);

  const fetchSummary = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/ai/usage/summary?days=${period}`, { headers });
      const data = await r.json();
      setSummary(data?.data || null);
    } catch (e) { console.error(e); }
  }, [BASE, headers, period]);

  const fetchLogs = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ limit: '100' });
      if (logFilter) qs.append('feature', logFilter);
      const r = await fetch(`${BASE}/api/ai/usage/logs?${qs}`, { headers });
      const data = await r.json();
      setLogs(data?.data || []);
    } catch (e) { console.error(e); }
  }, [BASE, headers, logFilter]);

  const fetchBudgets = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/ai/usage/budgets`, { headers });
      const data = await r.json();
      setBudgets(data?.data || null);
    } catch (e) { console.error(e); }
  }, [BASE, headers]);

  const fetchSettings = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/ai/usage/settings`, { headers });
      const data = await r.json();
      const d = data?.data;
      if (d) {
        setSettings(d);
        setForm({
          ai_enabled: !!d.ai_enabled,
          daily_budget_usd: d.daily_budget_usd,
          monthly_budget_usd: d.monthly_budget_usd,
          per_feature_daily_usd: d.per_feature_daily_usd,
          default_tier: d.default_tier,
          disabled_features: Array.isArray(d.disabled_features) ? [...d.disabled_features] : [],
        });
      }
    } catch (e) { console.error(e); }
  }, [BASE, headers]);

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const toggleFeature = (key, enabled) => setForm(f => ({
    ...f,
    disabled_features: enabled
      ? f.disabled_features.filter(x => x !== key)
      : Array.from(new Set([...f.disabled_features, key])),
  }));

  const saveSettings = useCallback(async () => {
    if (!form) return;
    setSavingSettings(true);
    try {
      const r = await fetch(`${BASE}/api/ai/usage/settings`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ai_enabled: form.ai_enabled,
          daily_budget_usd: Number(form.daily_budget_usd),
          monthly_budget_usd: Number(form.monthly_budget_usd),
          per_feature_daily_usd: Number(form.per_feature_daily_usd),
          default_tier: form.default_tier,
          disabled_features: form.disabled_features,
        }),
      });
      const data = await r.json();
      if (r.ok && data?.success) {
        toast.success('Setting AI berhasil disimpan');
        await Promise.all([fetchSettings(), fetchToday()]);
      } else {
        toast.error(data?.detail || 'Gagal menyimpan setting AI');
      }
    } catch (e) {
      toast.error('Gagal menyimpan setting AI');
    } finally {
      setSavingSettings(false);
    }
  }, [BASE, headers, form, fetchSettings, fetchToday]);

  const refreshAll = useCallback(() => {
    setLoading(true);
    Promise.all([fetchToday(), fetchSummary(), fetchLogs(), fetchBudgets(), fetchSettings()])
      .finally(() => setLoading(false));
  }, [fetchToday, fetchSummary, fetchLogs, fetchBudgets, fetchSettings]);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Brain className="w-6 h-6 text-violet-500" /> AI Usage Monitor
          </h1>
          <p className="text-sm text-muted-foreground">
            Monitor cost & usage Emergent LLM per fitur. Real-time budget alert & cost analytics.
          </p>
        </div>
        <Button onClick={refreshAll} disabled={loading} size="sm" data-testid="ai-usage-refresh">
          {loading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />} Refresh
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-4 w-full md:w-[640px]">
          <TabsTrigger value="today" data-testid="ai-usage-tab-today"><Zap className="w-4 h-4 mr-1.5" /> Hari Ini</TabsTrigger>
          <TabsTrigger value="summary" data-testid="ai-usage-tab-summary"><BarChart3 className="w-4 h-4 mr-1.5" /> Summary</TabsTrigger>
          <TabsTrigger value="logs" data-testid="ai-usage-tab-logs"><List className="w-4 h-4 mr-1.5" /> Logs</TabsTrigger>
          <TabsTrigger value="settings" data-testid="ai-usage-tab-settings"><Settings className="w-4 h-4 mr-1.5" /> Pengaturan</TabsTrigger>
        </TabsList>

        <TabsContent value="today" className="mt-4 space-y-4">
          {!today ? (
            <GlassCard className="p-6 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 inline animate-spin mr-2" /> Memuat...</GlassCard>
          ) : (
            <>
              <GlassCard className={`p-6 border ${HEALTH_COLOR[today.health]}`}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold flex items-center gap-2">
                      <Activity className="w-4 h-4" /> Status Hari Ini ({today.date})
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {today.total_calls} calls · {fmtNum(today.total_tokens)} tokens · {fmtUSD(today.total_cost_usd)}
                    </p>
                  </div>
                  <Badge className={HEALTH_COLOR[today.health]} variant="outline">
                    {HEALTH_LABEL[today.health] || today.health}
                  </Badge>
                </div>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span>Budget Harian: {fmtUSD(today.daily_budget_usd)}</span>
                  <span className="font-semibold">{today.budget_used_pct}% terpakai</span>
                </div>
                <Progress value={Math.min(today.budget_used_pct, 100)} className="h-2" />
                {today.health === 'critical' && (
                  <div className="mt-3 p-2 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-600 dark:text-red-400 flex items-start gap-1.5">
                    <AlertTriangle className="w-4 h-4 mt-0.5" />
                    <span>Budget harian terlampaui. Fitur AI akan fallback ke heuristic mode. Set env var <code>LLM_DAILY_BUDGET_USD</code> untuk naikkan limit.</span>
                  </div>
                )}
              </GlassCard>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard label="Total Calls" value={fmtNum(today.total_calls)} icon={Activity} color="blue" />
                <StatCard label="Success" value={fmtNum(today.successful_calls)} icon={CheckCircle2} color="emerald" />
                <StatCard label="Failed" value={fmtNum(today.failed_calls)} icon={AlertTriangle} color="amber" />
                <StatCard label="Tokens" value={fmtNum(today.total_tokens)} icon={Zap} color="indigo" />
              </div>

              {today.top_features?.length > 0 ? (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-violet-500" /> Top Features (Hari Ini)</h3>
                  <div className="space-y-2">
                    {today.top_features.map((f, i) => {
                      const pct = today.total_cost_usd > 0 ? (f.cost_usd / today.total_cost_usd * 100) : 0;
                      return (
                        <div key={i} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                          <div className="flex items-center justify-between mb-1">
                            <div>
                              <span className="font-medium text-sm">{f.feature}</span>
                              <span className="text-xs text-muted-foreground ml-2">{f.calls} call{f.calls > 1 ? 's' : ''}</span>
                            </div>
                            <span className="text-sm font-semibold text-violet-600 dark:text-violet-400">{fmtUSD(f.cost_usd)}</span>
                          </div>
                          <Progress value={pct} className="h-1" />
                        </div>
                      );
                    })}
                  </div>
                </GlassCard>
              ) : (
                <GlassCard className="p-8 text-center text-sm text-muted-foreground">
                  <Sparkles className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  Belum ada AI call hari ini. Gunakan fitur AI (Daily Summary, AI Quote, dll) untuk melihat statistik.
                </GlassCard>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="summary" className="mt-4 space-y-4">
          <GlassCard className="p-4 flex items-center gap-3">
            <span className="text-sm font-medium">Periode:</span>
            <Select value={String(period)} onValueChange={(v) => setPeriod(Number(v))}>
              <SelectTrigger className="w-32" data-testid="ai-usage-period"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 hari</SelectItem>
                <SelectItem value="7">7 hari</SelectItem>
                <SelectItem value="14">14 hari</SelectItem>
                <SelectItem value="30">30 hari</SelectItem>
                <SelectItem value="90">90 hari</SelectItem>
              </SelectContent>
            </Select>
            {budgets && (
              <div className="ml-auto flex gap-2 text-xs text-muted-foreground">
                <span>Daily: {fmtUSD(budgets.daily_usd)}</span>
                <span>·</span>
                <span>Monthly: {fmtUSD(budgets.monthly_usd)}</span>
              </div>
            )}
          </GlassCard>

          {!summary ? (
            <GlassCard className="p-6 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 inline animate-spin mr-2" /> Memuat...</GlassCard>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <StatCard label="Total Cost" value={fmtUSD(summary.overall.total_cost_usd)} icon={DollarSign} color="emerald" />
                <StatCard label="Total Calls" value={fmtNum(summary.overall.total_calls)} icon={Activity} color="blue" />
                <StatCard label="Success" value={fmtNum(summary.overall.successful_calls)} icon={CheckCircle2} color="emerald" small />
                <StatCard label="Failed" value={fmtNum(summary.overall.failed_calls)} icon={AlertTriangle} color="amber" small />
                <StatCard label="Avg Latency" value={`${fmtNum(summary.overall.avg_latency_ms)}ms`} icon={Clock} color="indigo" small />
              </div>

              {summary.by_feature?.length > 0 && (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-violet-500" /> Cost per Feature</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                        <tr>
                          <th className="text-left py-2 px-2">Feature</th>
                          <th className="text-right py-2 px-2">Calls</th>
                          <th className="text-right py-2 px-2">Success</th>
                          <th className="text-right py-2 px-2">Failed</th>
                          <th className="text-right py-2 px-2">Tokens</th>
                          <th className="text-right py-2 px-2">Avg Latency</th>
                          <th className="text-right py-2 px-2">Cost</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.by_feature.map((f, i) => (
                          <tr key={i} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass)]">
                            <td className="py-2 px-2 font-medium">{f.feature}</td>
                            <td className="py-2 px-2 text-right">{fmtNum(f.calls)}</td>
                            <td className="py-2 px-2 text-right text-emerald-500">{fmtNum(f.successful)}</td>
                            <td className="py-2 px-2 text-right text-red-500">{fmtNum(f.failed)}</td>
                            <td className="py-2 px-2 text-right text-muted-foreground">{fmtNum(f.tokens)}</td>
                            <td className="py-2 px-2 text-right text-muted-foreground">{fmtNum(f.avg_latency_ms)}ms</td>
                            <td className="py-2 px-2 text-right font-semibold text-violet-600 dark:text-violet-400">{fmtUSD(f.cost_usd)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </GlassCard>
              )}

              {summary.by_day?.length > 0 && (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-indigo-500" /> Daily Cost Trend</h3>
                  <div className="space-y-1.5">
                    {summary.by_day.map((d, i) => {
                      const maxCost = Math.max(...summary.by_day.map((x) => x.cost_usd), 0.0001);
                      const pct = (d.cost_usd / maxCost) * 100;
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs text-muted-foreground w-24 shrink-0">{d.date}</span>
                          <div className="flex-1 h-5 bg-[var(--glass)] rounded relative">
                            <div className="h-full rounded bg-gradient-to-r from-violet-500 to-indigo-500" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs font-medium w-20 text-right">{fmtUSD(d.cost_usd)}</span>
                          <span className="text-xs text-muted-foreground w-12 text-right">{d.calls}c</span>
                        </div>
                      );
                    })}
                  </div>
                </GlassCard>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          <GlassCard className="p-4 mb-3 flex items-center gap-3">
            <span className="text-sm font-medium">Filter Feature:</span>
            <Select value={logFilter || '__all__'} onValueChange={(v) => setLogFilter(v === '__all__' ? '' : v)}>
              <SelectTrigger className="w-64" data-testid="ai-usage-log-filter"><SelectValue placeholder="Semua feature" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua feature</SelectItem>
                {Array.from(new Set(logs.map((l) => l.feature).concat(summary?.by_feature?.map((f) => f.feature) || []))).filter(Boolean).map((f) => (
                  <SelectItem key={f} value={f}>{f}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={fetchLogs}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh</Button>
            <span className="ml-auto text-xs text-muted-foreground">{logs.length} log entries</span>
          </GlassCard>

          {logs.length === 0 ? (
            <GlassCard className="p-10 text-center text-sm text-muted-foreground">Belum ada log</GlassCard>
          ) : (
            <GlassCard className="p-3">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-muted-foreground border-b border-[var(--glass-border)]">
                    <tr>
                      <th className="text-left py-2 px-2">Waktu</th>
                      <th className="text-left py-2 px-2">Feature</th>
                      <th className="text-left py-2 px-2">Model</th>
                      <th className="text-right py-2 px-2">Tokens</th>
                      <th className="text-right py-2 px-2">Latency</th>
                      <th className="text-right py-2 px-2">Cost</th>
                      <th className="text-center py-2 px-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((l) => (
                      <tr key={l.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass)]">
                        <td className="py-1.5 px-2 text-muted-foreground">{l.created_at ? new Date(l.created_at).toLocaleString('id-ID') : '—'}</td>
                        <td className="py-1.5 px-2 font-medium">{l.feature}</td>
                        <td className="py-1.5 px-2 text-muted-foreground">{l.model_provider}/{l.model_name}</td>
                        <td className="py-1.5 px-2 text-right">{fmtNum(l.tokens_total)}</td>
                        <td className="py-1.5 px-2 text-right">{fmtNum(l.latency_ms)}ms</td>
                        <td className="py-1.5 px-2 text-right font-medium">{fmtUSD(l.cost_usd)}</td>
                        <td className="py-1.5 px-2 text-center">
                          {l.success ? (
                            <Badge className="bg-emerald-500/15 text-emerald-600 border-emerald-500/30" variant="outline">OK</Badge>
                          ) : (
                            <Badge className="bg-red-500/15 text-red-600 border-red-500/30" variant="outline" title={l.error || ''}>FAIL</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}
        </TabsContent>

        <TabsContent value="settings" className="mt-4 space-y-4">
          {!form ? (
            <GlassCard className="p-6 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 inline animate-spin mr-2" /> Memuat...</GlassCard>
          ) : (
            <>
              {/* Master switch */}
              <GlassCard className="p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Power className={`w-5 h-5 ${form.ai_enabled ? 'text-emerald-500' : 'text-muted-foreground'}`} />
                    <div>
                      <p className="font-semibold text-sm text-foreground">AI Master Switch</p>
                      <p className="text-xs text-muted-foreground">Nonaktifkan untuk mematikan SEMUA fitur AI sekaligus.</p>
                    </div>
                  </div>
                  <Switch checked={form.ai_enabled} onCheckedChange={(v) => setField('ai_enabled', v)} data-testid="ai-set-master" />
                </div>
              </GlassCard>

              {/* Budgets */}
              <GlassCard className="p-5 space-y-4">
                <h3 className="font-semibold text-sm flex items-center gap-2 text-foreground"><DollarSign className="w-4 h-4 text-emerald-500" /> Budget (USD)</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Harian</label>
                    <Input type="number" min="0" step="0.5" value={form.daily_budget_usd}
                      onChange={(e) => setField('daily_budget_usd', e.target.value)} data-testid="ai-set-daily" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Bulanan</label>
                    <Input type="number" min="0" step="5" value={form.monthly_budget_usd}
                      onChange={(e) => setField('monthly_budget_usd', e.target.value)} data-testid="ai-set-monthly" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Per Fitur / Hari</label>
                    <Input type="number" min="0" step="0.5" value={form.per_feature_daily_usd}
                      onChange={(e) => setField('per_feature_daily_usd', e.target.value)} data-testid="ai-set-perfeature" />
                  </div>
                </div>
                {settings?.env_defaults && (
                  <p className="text-xs text-muted-foreground">
                    Default env: harian ${settings.env_defaults.daily_budget_usd} · bulanan ${settings.env_defaults.monthly_budget_usd}.
                    Bila budget terlampaui, panggilan AI ditolak otomatis.
                  </p>
                )}
              </GlassCard>

              {/* Default tier */}
              <GlassCard className="p-5">
                <h3 className="font-semibold text-sm mb-2 flex items-center gap-2 text-foreground"><Brain className="w-4 h-4 text-violet-500" /> Tier Model Default</h3>
                <Select value={form.default_tier} onValueChange={(v) => setField('default_tier', v)}>
                  <SelectTrigger className="w-full md:w-80" data-testid="ai-set-tier"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(settings?.tiers || []).map(t => (
                      <SelectItem key={t} value={t}>{t} — {settings?.tier_models?.[t]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-2">executive = analisis berat (Opus), standard = umum (Sonnet), light = ringan/murah (Haiku).</p>
              </GlassCard>

              {/* Feature toggles */}
              <GlassCard className="p-5">
                <h3 className="font-semibold text-sm mb-3 flex items-center gap-2 text-foreground"><Zap className="w-4 h-4 text-amber-500" /> Aktif / Nonaktif per Fitur AI</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {(settings?.feature_groups || []).map(g => {
                    const enabled = !form.disabled_features.includes(g.key);
                    return (
                      <div key={g.key} className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                        <div>
                          <span className="text-sm text-foreground">{g.label}</span>
                          <span className="block text-[11px] text-muted-foreground font-mono">{g.key}</span>
                        </div>
                        <Switch checked={enabled} onCheckedChange={(v) => toggleFeature(g.key, v)} data-testid={`ai-set-feat-${g.key}`} />
                      </div>
                    );
                  })}
                </div>
              </GlassCard>

              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={fetchSettings} disabled={savingSettings} data-testid="ai-set-reset">Reset</Button>
                <Button onClick={saveSettings} disabled={savingSettings} data-testid="ai-set-save" className="bg-violet-600 hover:bg-violet-700 text-white">
                  {savingSettings ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />} Simpan Pengaturan
                </Button>
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color, small = false }) {
  const map = {
    blue: 'from-blue-500/10 to-cyan-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400',
    emerald: 'from-emerald-500/10 to-teal-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    amber: 'from-amber-500/10 to-orange-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400',
    red: 'from-red-500/10 to-rose-500/10 border-red-500/20 text-red-600 dark:text-red-400',
    indigo: 'from-indigo-500/10 to-violet-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
  };
  return (
    <div className={`p-3 rounded-xl bg-gradient-to-br border ${map[color] || map.blue}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-70" />}
      </div>
      <div className={`font-bold text-foreground ${small ? 'text-base' : 'text-2xl'}`}>{value}</div>
    </div>
  );
}
