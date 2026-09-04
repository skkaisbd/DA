import { useState, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Brain, Sparkles, TrendingUp, Shield, Factory, RefreshCw,
  AlertTriangle, CheckCircle2, Clock, DollarSign, BarChart3
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const fmtRp = formatRupiah;

const RISK_COLOR = {
  low:    'text-green-600 bg-green-50 border-green-200',
  medium: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  high:   'text-red-600 bg-red-50 border-red-200',
};

const CAPACITY_COLOR = {
  under:  'text-blue-600 bg-blue-50',
  normal: 'text-green-600 bg-green-50',
  over:   'text-red-600 bg-red-50',
};

// ─────────────────────────────────────────────────────────────────────
// P2-1: AI Daily Summary
// ─────────────────────────────────────────────────────────────────────
function DailySummaryTab() {
  const { toast } = useToast();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(1);

  const generate = async () => {
    setLoading(true);
    setSummary(null);
    try {
      const res = await apiFetch(`/ai-business/daily-summary?days=${days}`, { method: 'POST' });
      setSummary(res.data);
      toast({ title: 'Ringkasan AI berhasil digenerate! ✨' });
    } catch (err) {
      toast({ title: 'Gagal generate', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
          <SelectTrigger className="w-36 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="1">Hari ini</SelectItem>
            <SelectItem value="7">7 hari</SelectItem>
            <SelectItem value="30">30 hari</SelectItem>
          </SelectContent>
        </Select>
        <Button
          className="bg-gradient-to-r from-purple-600 to-pink-600 text-foreground hover:opacity-90"
          onClick={generate}
          disabled={loading}
          data-testid="btn-generate-summary"
        >
          {loading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Generating...</> :
            <><Brain className="h-4 w-4 mr-2" />Generate Ringkasan AI</>}
        </Button>
      </div>

      {!summary && !loading && (
        <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
          <Brain className="h-12 w-12 mb-3 opacity-20" />
          <p className="text-sm">Klik "Generate Ringkasan AI" untuk mendapatkan<br />analisis bisnis berbasis AI</p>
          <p className="text-xs mt-1 opacity-60">Estimasi waktu: 15-30 detik</p>
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center justify-center py-16 border-2 border-dashed border-primary/30 rounded-lg">
          <div className="h-12 w-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin mb-4" />
          <p className="text-sm text-muted-foreground">AI sedang menganalisis data bisnis...</p>
        </div>
      )}

      {summary && (
        <div className="space-y-4">
          <Card className="border border-purple-200 bg-purple-50/50">
            <CardContent className="p-4">
              <p className="text-xs text-purple-600 font-semibold uppercase tracking-wide mb-2">Ringkasan AI — {summary.generated_at ? new Date(summary.generated_at).toLocaleString('id-ID') : ''}</p>
              <div className="text-sm leading-relaxed whitespace-pre-wrap">{summary.summary}</div>
            </CardContent>
          </Card>

          {/* Raw metrics */}
          {summary.metrics && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[
                { icon: Factory,   label: 'WO Selesai',    value: summary.metrics.produksi?.work_order_selesai },
                { icon: DollarSign,label: 'Total Invoice', value: fmtRp(summary.metrics.keuangan?.total_invoiced_rp) },
                { icon: CheckCircle2,label: 'Maklon Done',  value: summary.metrics.maklon?.order_selesai },
                { icon: TrendingUp,label: 'Live Revenue',  value: fmtRp(summary.metrics.marketing?.revenue_live_rp) },
                { icon: AlertTriangle,label: 'Stok Rendah', value: summary.metrics.alert?.stok_rendah },
                { icon: Clock,     label: 'Isu Hadir',     value: summary.metrics.sdm?.isu_kehadiran },
              ].map((m, i) => (
                <Card key={i} className="border border-border">
                  <CardContent className="p-3 flex items-center gap-2">
                    <m.icon className="h-4 w-4 text-muted-foreground" />
                    <div><p className="text-[11px] text-muted-foreground">{m.label}</p><p className="text-sm font-bold">{m.value ?? '-'}</p></div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// P2-2: AI Revenue Forecast
// ─────────────────────────────────────────────────────────────────────
function RevenueForecastTab() {
  const { toast } = useToast();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(3);

  const generate = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await apiFetch(`/ai-business/revenue-forecast?months=${months}`, { method: 'POST' });
      setResult(res.data);
      toast({ title: 'Forecast berhasil! 📈' });
    } catch (err) {
      toast({ title: 'Gagal forecast', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const TREND_COLOR = {
    growing: 'text-green-600',
    stable: 'text-blue-600',
    declining: 'text-red-600',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select value={String(months)} onValueChange={v => setMonths(Number(v))}>
          <SelectTrigger className="w-40 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="1">Prediksi 1 bulan</SelectItem>
            <SelectItem value="3">Prediksi 3 bulan</SelectItem>
            <SelectItem value="6">Prediksi 6 bulan</SelectItem>
          </SelectContent>
        </Select>
        <Button className="bg-gradient-to-r from-green-600 to-teal-600 text-foreground hover:opacity-90" onClick={generate} disabled={loading}>
          {loading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Forecasting...</> : <><TrendingUp className="h-4 w-4 mr-2" />Generate Forecast</>}
        </Button>
      </div>

      {!result && !loading && (
        <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
          <TrendingUp className="h-10 w-10 mb-3 opacity-20" />
          <p className="text-sm">Generate prediksi revenue AI untuk {months} bulan ke depan</p>
        </div>
      )}
      {loading && <div className="flex flex-col items-center justify-center py-12"><RefreshCw className="h-8 w-8 animate-spin text-teal-500 mb-3" /><p className="text-sm text-muted-foreground">AI menganalisis data historis...</p></div>}

      {result && (
        <div className="space-y-4">
          {/* Trend & Insights */}
          {result.forecast && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Trend:</span>
                <span className={`font-bold ${TREND_COLOR[result.forecast.growth_trend] || 'text-foreground'}`}>
                  {result.forecast.growth_trend?.toUpperCase()}
                </span>
              </div>

              {result.forecast.analysis && (
                <Card className="border border-teal-200 bg-teal-50/50">
                  <CardContent className="p-4 text-sm leading-relaxed">{result.forecast.analysis}</CardContent>
                </Card>
              )}

              {result.forecast.key_insights?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Key Insights</p>
                  <ul className="space-y-1">
                    {result.forecast.key_insights.map((insight, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="text-teal-500 mt-0.5">•</span>{insight}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.forecast.forecast_months?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Prediksi per Bulan</p>
                  <div className="space-y-2">
                    {result.forecast.forecast_months.map((m, i) => (
                      <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-border">
                        <div>
                          <p className="font-medium text-sm">{m.month}</p>
                          <p className="text-xs text-muted-foreground">{m.notes}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-bold text-sm">{fmtRp(m.predicted_rp)}</p>
                          <Badge variant="outline" className="text-[10px]">{m.confidence}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.forecast.recommendation && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
                  💡 {result.forecast.recommendation}
                </div>
              )}
            </div>
          )}

          {/* Historical */}
          {result.historical?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Data Historis</p>
              <div className="space-y-1">
                {result.historical.slice(-6).map((m, i) => (
                  <div key={i} className="flex justify-between text-sm py-1 border-b border-border last:border-0">
                    <span className="text-muted-foreground">{m.month}</span>
                    <span className="font-medium">{fmtRp(m.total_rp)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// P2-4: AI Fraud Detection
// ─────────────────────────────────────────────────────────────────────
function FraudDetectionTab() {
  const { toast } = useToast();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);

  const analyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await apiFetch(`/ai-business/fraud-detection?days=${days}`, { method: 'POST' });
      setResult(res.data);
      toast({ title: 'Analisis fraud selesai 🔍' });
    } catch (err) {
      toast({ title: 'Gagal analisis', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
          <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 hari</SelectItem>
            <SelectItem value="30">30 hari</SelectItem>
            <SelectItem value="90">90 hari</SelectItem>
          </SelectContent>
        </Select>
        <Button className="bg-gradient-to-r from-red-600 to-orange-600 text-foreground hover:opacity-90" onClick={analyze} disabled={loading}>
          {loading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Menganalisis...</> : <><Shield className="h-4 w-4 mr-2" />Analisis Fraud</>}
        </Button>
      </div>

      {!result && !loading && (
        <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
          <Shield className="h-10 w-10 mb-3 opacity-20" />
          <p className="text-sm">AI akan mendeteksi anomali transaksi dan potensi fraud</p>
        </div>
      )}
      {loading && <div className="flex flex-col items-center justify-center py-12"><RefreshCw className="h-8 w-8 animate-spin text-red-700 dark:text-red-500 mb-3" /><p className="text-sm text-muted-foreground">AI menganalisis pola transaksi...</p></div>}

      {result && result.ai_analysis && (
        <div className="space-y-4">
          {/* Risk Level */}
          <div className={`p-4 rounded-lg border ${RISK_COLOR[result.ai_analysis.risk_level] || 'border-border'}`}>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="h-5 w-5" />
              <p className="font-bold">Risk Level: {result.ai_analysis.risk_level?.toUpperCase()}</p>
            </div>
            {result.ai_analysis.overall_assessment && (
              <p className="text-sm leading-relaxed">{result.ai_analysis.overall_assessment}</p>
            )}
          </div>

          {/* Anomalies */}
          {result.ai_analysis.anomalies_found?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Anomali Ditemukan ({result.ai_analysis.anomalies_found.length})</p>
              <div className="space-y-2">
                {result.ai_analysis.anomalies_found.map((a, i) => (
                  <div key={i} className="p-3 rounded-lg border border-orange-200 bg-orange-50">
                    <p className="text-sm font-medium">{a.type || a.description}</p>
                    {a.recommendation && <p className="text-xs text-muted-foreground mt-1">{a.recommendation}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {result.ai_analysis.recommended_actions?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Rekomendasi Tindakan</p>
              <ul className="space-y-1">
                {result.ai_analysis.recommended_actions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-red-700 dark:text-red-500 mt-0.5">→</span>{a}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// P2-6: AI Production Optimizer
// ─────────────────────────────────────────────────────────────────────
function ProductionOptimizerTab() {
  const { toast } = useToast();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const analyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await apiFetch('/ai-business/production-optimize', { method: 'POST' });
      setResult(res.data);
      toast({ title: 'Analisis produksi selesai! 🏭' });
    } catch (err) {
      toast({ title: 'Gagal analisis', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Button
        className="bg-gradient-to-r from-orange-600 to-yellow-600 text-foreground hover:opacity-90"
        onClick={analyze}
        disabled={loading}
      >
        {loading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Mengoptimalkan...</> : <><Factory className="h-4 w-4 mr-2" />Optimize Jadwal Produksi</>}
      </Button>

      {!result && !loading && (
        <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
          <Factory className="h-10 w-10 mb-3 opacity-20" />
          <p className="text-sm">AI akan menganalisis backlog produksi dan memberikan<br />rekomendasi penjadwalan optimal</p>
        </div>
      )}
      {loading && <div className="flex flex-col items-center justify-center py-12"><RefreshCw className="h-8 w-8 animate-spin text-orange-500 mb-3" /><p className="text-sm text-muted-foreground">AI menganalisis jadwal produksi...</p></div>}

      {result && result.optimization && (
        <div className="space-y-4">
          {/* Capacity Status */}
          <div className={`p-3 rounded-lg ${CAPACITY_COLOR[result.optimization.capacity_status] || 'bg-muted'}`}>
            <p className="font-bold">Kapasitas: {result.optimization.capacity_status?.toUpperCase()}</p>
            {result.optimization.efficiency_score != null && (
              <p className="text-sm">Efficiency Score: {result.optimization.efficiency_score}%</p>
            )}
          </div>

          {result.optimization.overall_assessment && (
            <Card className="border border-orange-200 bg-orange-50/50">
              <CardContent className="p-4 text-sm leading-relaxed">{result.optimization.overall_assessment}</CardContent>
            </Card>
          )}

          {result.optimization.bottlenecks?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Bottleneck</p>
              <ul className="space-y-1">
                {result.optimization.bottlenecks.map((b, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm"><span className="text-orange-500">⚠</span>{b}</li>
                ))}
              </ul>
            </div>
          )}

          {result.optimization.scheduling_suggestions?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Saran Penjadwalan</p>
              <ul className="space-y-1">
                {result.optimization.scheduling_suggestions.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm"><span className="text-green-500">✓</span>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Current state summary */}
          {result.current_state && (
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'WO Aktif', value: result.current_state.work_orders_aktif },
                { label: 'Maklon Aktif', value: result.current_state.maklon_orders_aktif },
                { label: 'Material Kritis', value: result.current_state.material_kritis },
              ].map((m, i) => (
                <Card key={i}><CardContent className="p-3 text-center"><p className="text-xs text-muted-foreground">{m.label}</p><p className="text-xl font-bold">{m.value ?? '-'}</p></CardContent></Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Main Export
// ─────────────────────────────────────────────────────────────────────
export default function AIBusinessDashboard() {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-purple-600 to-pink-500 flex items-center justify-center">
              <Brain className="h-4 w-4 text-foreground" />
            </div>
            AI Business Intelligence
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Daily Summary · Revenue Forecast · Fraud Detection · Production Optimizer
          </p>
        </div>
        <Badge className="bg-purple-100 text-purple-700 border-purple-200">Claude AI</Badge>
      </div>

      <Tabs defaultValue="summary">
        <TabsList className="h-9 flex-wrap">
          <TabsTrigger value="summary" className="text-xs"><Sparkles className="h-3.5 w-3.5 mr-1.5" />Daily Summary</TabsTrigger>
          <TabsTrigger value="forecast" className="text-xs"><TrendingUp className="h-3.5 w-3.5 mr-1.5" />Forecast</TabsTrigger>
          <TabsTrigger value="fraud" className="text-xs"><Shield className="h-3.5 w-3.5 mr-1.5" />Fraud AI</TabsTrigger>
          <TabsTrigger value="production" className="text-xs"><Factory className="h-3.5 w-3.5 mr-1.5" />Prod. Optimizer</TabsTrigger>
        </TabsList>
        <TabsContent value="summary" className="mt-4"><DailySummaryTab /></TabsContent>
        <TabsContent value="forecast" className="mt-4"><RevenueForecastTab /></TabsContent>
        <TabsContent value="fraud" className="mt-4"><FraudDetectionTab /></TabsContent>
        <TabsContent value="production" className="mt-4"><ProductionOptimizerTab /></TabsContent>
      </Tabs>
    </div>
  );
}
