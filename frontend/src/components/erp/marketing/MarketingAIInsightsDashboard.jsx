import React, { useState, useEffect, useCallback } from 'react';
import {
  Brain, TrendingUp, TrendingDown, Minus, BarChart3, MessageSquare,
  Zap, AlertTriangle, CheckCircle2, RefreshCw, Loader2,
  ChevronRight, Target, ArrowUp, ArrowDown, Sparkles, Clock
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) { return new Intl.NumberFormat('id-ID').format(n || 0); }
function fmtRp(n) { return `Rp ${fmt(n)}`; }

const MODULE_ICONS = {
  complaints: '📋', orders: '📦', content: '📅', discounts: '🏷️',
  health: '❤️', ads: '📢', launches: '🚀', general: '⚡'
};

const URGENCY_CONFIG = {
  urgent: { label: 'Segera', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', dot: 'bg-red-500' },
  high:   { label: 'Tinggi', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300', dot: 'bg-orange-500' },
  medium: { label: 'Sedang', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', dot: 'bg-amber-400' },
  low:    { label: 'Rendah', color: 'bg-muted text-muted-foreground dark:bg-slate-800 dark:text-foreground/70', dot: 'bg-muted' }
};

const SENTIMENT_CONFIG = {
  positive: { label: 'Positif', color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: CheckCircle2 },
  neutral:  { label: 'Netral',  color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20',   icon: Minus },
  negative: { label: 'Negatif', color: 'text-red-600',     bg: 'bg-red-50 dark:bg-red-900/20',       icon: AlertTriangle }
};

function UrgencyBadge({ urgency }) {
  const cfg = URGENCY_CONFIG[urgency] || URGENCY_CONFIG.medium;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function ForecastBar({ predicted, max }) {
  const pct = max > 0 ? Math.min(100, (predicted / max) * 100) : 0;
  return (
    <div className="w-full bg-muted rounded-full h-1.5 mt-1">
      <div className="bg-primary h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function MarketingAIInsightsDashboard({ token }) {
  const { toast } = useToast();
  const [overview, setOverview] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [sentiment, setSentiment] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const [loading, setLoading] = useState({ overview: true, forecast: false, sentiment: false, recommendations: false });
  const [activeTab, setActiveTab] = useState('overview');

  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };

  const fetchOverview = useCallback(async () => {
    setLoading(l => ({ ...l, overview: true }));
    try {
      const res = await axios.get(`${API}/api/marketing/ai-insights/overview`, { headers: authH });
      if (res.data.success) setOverview(res.data.data);
    } catch (e) {
      toast({ title: 'Gagal load overview', variant: 'destructive' });
    } finally {
      setLoading(l => ({ ...l, overview: false }));
    }
  }, [token]); // eslint-disable-line

  const runForecast = async () => {
    setLoading(l => ({ ...l, forecast: true }));
    try {
      const res = await axios.post(`${API}/api/marketing/ai-insights/forecast`, {}, { headers: authH });
      if (res.data.success) setForecast(res.data.data);
    } catch (e) {
      toast({ title: 'Forecast gagal', description: e.response?.data?.detail, variant: 'destructive' });
    } finally {
      setLoading(l => ({ ...l, forecast: false }));
    }
  };

  const runSentiment = async () => {
    setLoading(l => ({ ...l, sentiment: true }));
    try {
      const res = await axios.post(`${API}/api/marketing/ai-insights/sentiment`, {}, { headers: authH });
      if (res.data.success) setSentiment(res.data.data);
    } catch (e) {
      toast({ title: 'Analisis sentimen gagal', description: e.response?.data?.detail, variant: 'destructive' });
    } finally {
      setLoading(l => ({ ...l, sentiment: false }));
    }
  };

  const runRecommendations = async () => {
    setLoading(l => ({ ...l, recommendations: true }));
    try {
      const res = await axios.post(`${API}/api/marketing/ai-insights/recommendations`, {}, { headers: authH });
      if (res.data.success) setRecommendations(res.data.data);
    } catch (e) {
      toast({ title: 'Rekomendasi gagal', description: e.response?.data?.detail, variant: 'destructive' });
    } finally {
      setLoading(l => ({ ...l, recommendations: false }));
    }
  };

  useEffect(() => { fetchOverview(); }, [fetchOverview]);

  const tabs = [
    { id: 'overview',        label: 'Data Overview',    icon: BarChart3 },
    { id: 'forecast',        label: 'Sales Forecast',   icon: TrendingUp },
    { id: 'sentiment',       label: 'Analisis Sentimen', icon: MessageSquare },
    { id: 'recommendations', label: 'Action Items',     icon: Zap }
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="ai-insights-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Brain size={24} className="text-primary" />
            AI Marketing Insights
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Sales forecast, analisis sentimen, dan rekomendasi AI</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchOverview} disabled={loading.overview}>
          {loading.overview ? <Loader2 size={13} className="mr-1 animate-spin" /> : <RefreshCw size={13} className="mr-1" />}
          Refresh Data
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-lg mb-6 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap flex-1 justify-center ${
              activeTab === t.id
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <t.icon size={14} />{t.label}
          </button>
        ))}
      </div>

      {/* Tab: Overview */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          {loading.overview ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="animate-spin text-muted-foreground" size={28} />
            </div>
          ) : overview ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Orders Card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">📦 Orders (30 Hari)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-3xl font-bold tabular-nums">{fmt(overview.orders?.recent_30d)}</p>
                  <p className="text-xs text-muted-foreground">Total: {fmt(overview.orders?.total)} orders</p>
                  <div className="space-y-1">
                    {Object.entries(overview.orders?.status_counts || {}).map(([s, n]) => (
                      <div key={s} className="flex justify-between text-xs">
                        <span className="text-muted-foreground capitalize">{s}</span>
                        <span className="font-medium tabular-nums">{fmt(n)}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Complaints Card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">📋 Komplain (30 Hari)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-3xl font-bold tabular-nums">{fmt(overview.complaints?.recent_30d)}</p>
                  {overview.complaints?.overdue > 0 && (
                    <div className="flex items-center gap-1.5 px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-md">
                      <AlertTriangle size={12} />
                      <span className="text-xs font-medium">{overview.complaints?.overdue} overdue SLA</span>
                    </div>
                  )}
                  <div className="space-y-1">
                    {Object.entries(overview.complaints?.categories || {}).slice(0, 3).map(([c, n]) => (
                      <div key={c} className="flex justify-between text-xs">
                        <span className="text-muted-foreground">{c.replace(/_/g, ' ')}</span>
                        <span className="font-medium tabular-nums">{n}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Reviews Card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">⭐ Rating & Review</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-3xl font-bold tabular-nums">{overview.reviews?.avg_rating?.toFixed(1)} / 5.0</p>
                  <p className="text-xs text-muted-foreground">{fmt(overview.reviews?.total)} total reviews</p>
                  <div className="space-y-1">
                    {Object.entries(overview.reviews?.rating_distribution || {}).sort((a, b) => b[0] - a[0]).map(([r, n]) => (
                      <div key={r} className="flex items-center gap-2 text-xs">
                        <span className="text-muted-foreground w-10">{'⭐'.repeat(Number(r))}</span>
                        <div className="flex-1 bg-muted rounded-full h-1.5">
                          <div className="bg-amber-400 h-1.5 rounded-full" style={{ width: `${overview.reviews?.total > 0 ? (n / overview.reviews.total * 100) : 0}%` }} />
                        </div>
                        <span className="font-medium w-8 text-right tabular-nums">{n}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Discounts Card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">🏷️ Discount Campaign</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-3xl font-bold tabular-nums">{fmt(overview.discounts?.active)}</p>
                  <p className="text-xs text-muted-foreground">Campaign aktif</p>
                  {overview.discounts?.expiring_soon > 0 && (
                    <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 rounded-md">
                      <Clock size={12} />
                      <span className="text-xs font-medium">{overview.discounts?.expiring_soon} berakhir dalam 3 hari</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Health Card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">❤️ Kesehatan Akun</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-3xl font-bold tabular-nums">{(overview.health?.accounts || []).length}</p>
                  <p className="text-xs text-muted-foreground">Total akun terpantau</p>
                  {overview.health?.critical_count > 0 && (
                    <div className="flex items-center gap-1.5 px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-md">
                      <AlertTriangle size={12} />
                      <span className="text-xs font-medium">{overview.health?.critical_count} akun kritis</span>
                    </div>
                  )}
                  {overview.health?.warning_count > 0 && (
                    <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 rounded-md">
                      <AlertTriangle size={12} />
                      <span className="text-xs font-medium">{overview.health?.warning_count} akun perlu perhatian</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Quick AI Actions */}
              <Card className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2"><Sparkles size={14} className="text-primary" /> AI Actions</CardTitle>
                  <CardDescription className="text-xs">Jalankan analisis AI</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button size="sm" className="w-full justify-start" variant="outline" onClick={() => { setActiveTab('forecast'); runForecast(); }}>
                    <TrendingUp size={13} className="mr-2" /> Sales Forecast 7 Hari
                  </Button>
                  <Button size="sm" className="w-full justify-start" variant="outline" onClick={() => { setActiveTab('sentiment'); runSentiment(); }}>
                    <MessageSquare size={13} className="mr-2" /> Analisis Sentimen Customer
                  </Button>
                  <Button size="sm" className="w-full justify-start" variant="outline" onClick={() => { setActiveTab('recommendations'); runRecommendations(); }}>
                    <Zap size={13} className="mr-2" /> Generate Action Items
                  </Button>
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <Brain size={32} className="opacity-30 mb-2" />
              <p className="text-sm">Gagal load data</p>
              <Button size="sm" variant="outline" className="mt-2" onClick={fetchOverview}>Coba Lagi</Button>
            </div>
          )}
        </div>
      )}

      {/* Tab: Forecast */}
      {activeTab === 'forecast' && (
        <div className="space-y-4">
          {!forecast && !loading.forecast && (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
                <TrendingUp size={40} className="text-muted-foreground opacity-40" />
                <div className="text-center">
                  <p className="font-medium">Sales Forecast 7 Hari</p>
                  <p className="text-sm text-muted-foreground mt-1">AI akan menganalisis tren historis dan memprediksikan penjualan 7 hari ke depan</p>
                </div>
                <Button onClick={runForecast}>
                  <Sparkles size={14} className="mr-2" /> Jalankan Forecast
                </Button>
              </CardContent>
            </Card>
          )}
          {loading.forecast && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <p className="text-sm text-muted-foreground">AI sedang menganalisis data...</p>
            </div>
          )}
          {forecast && !loading.forecast && (
            <div className="space-y-4">
              {/* Summary */}
              <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 border-blue-200 dark:border-blue-800">
                <CardContent className="pt-4">
                  <div className="flex items-start gap-3">
                    <Brain size={20} className="text-blue-600 mt-0.5 shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-blue-900 dark:text-blue-100">{forecast.summary}</p>
                      <div className="flex items-center gap-3 mt-2">
                        <span className={`inline-flex items-center gap-1 text-xs font-medium ${
                          forecast.trend === 'upward' ? 'text-emerald-600' :
                          forecast.trend === 'downward' ? 'text-red-600' : 'text-amber-600'
                        }`}>
                          {forecast.trend === 'upward' ? <ArrowUp size={12} /> : forecast.trend === 'downward' ? <ArrowDown size={12} /> : <Minus size={12} />}
                          Tren: {forecast.trend === 'upward' ? 'Naik' : forecast.trend === 'downward' ? 'Turun' : 'Stabil'}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          Confidence: {forecast.confidence}
                        </Badge>
                      </div>
                      {forecast.key_factors?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {forecast.key_factors.map((f, i) => (
                            <span key={i} className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full">{f}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Forecast Grid */}
              {forecast.forecast?.length > 0 && (() => {
                const maxOrders = Math.max(...forecast.forecast.map(d => d.predicted_orders || 0));
                return (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
                    {forecast.forecast.map((day, i) => (
                      <Card key={i} className="overflow-hidden">
                        <CardHeader className="pb-1 pt-3 px-3">
                          <div className="text-xs text-muted-foreground">{new Date(day.date).toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: 'short' })}</div>
                        </CardHeader>
                        <CardContent className="px-3 pb-3">
                          <p className="text-2xl font-bold tabular-nums text-primary">{fmt(day.predicted_orders)}</p>
                          <p className="text-xs text-muted-foreground">orders</p>
                          <ForecastBar predicted={day.predicted_orders} max={maxOrders} />
                          <p className="text-xs font-medium mt-1.5">{fmtRp(day.predicted_revenue)}</p>
                          <Badge variant="outline" className="text-xs mt-1">{day.confidence}</Badge>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                );
              })()}

              <Button variant="outline" size="sm" onClick={runForecast}>
                <RefreshCw size={13} className="mr-1" /> Refresh Forecast
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Tab: Sentiment */}
      {activeTab === 'sentiment' && (
        <div className="space-y-4">
          {!sentiment && !loading.sentiment && (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
                <MessageSquare size={40} className="text-muted-foreground opacity-40" />
                <div className="text-center">
                  <p className="font-medium">Analisis Sentimen Customer</p>
                  <p className="text-sm text-muted-foreground mt-1">AI akan menganalisis teks komplain dan review untuk mendeteksi tren sentimen</p>
                </div>
                <Button onClick={runSentiment}>
                  <Sparkles size={14} className="mr-2" /> Analisis Sekarang
                </Button>
              </CardContent>
            </Card>
          )}
          {loading.sentiment && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <p className="text-sm text-muted-foreground">AI sedang menganalisis sentimen...</p>
            </div>
          )}
          {sentiment && !loading.sentiment && (() => {
            const sConfig = SENTIMENT_CONFIG[sentiment.overall_sentiment] || SENTIMENT_CONFIG.neutral;
            const SIcon = sConfig.icon;
            return (
              <div className="space-y-4">
                {/* Overall */}
                <Card className={`${sConfig.bg} border-0`}>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-3">
                      <SIcon size={32} className={sConfig.color} />
                      <div>
                        <div className="flex items-center gap-2">
                          <p className={`text-xl font-bold ${sConfig.color}`}>{sConfig.label}</p>
                          <Badge variant="outline" className="text-xs">Score: {(sentiment.sentiment_score * 100).toFixed(0)}%</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-0.5">{sentiment.summary}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Themes */}
                  {sentiment.themes?.length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Tema Utama yang Terdeteksi</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {sentiment.themes.map((t, i) => (
                          <div key={i} className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full ${
                                t.sentiment === 'positive' ? 'bg-emerald-500' :
                                t.sentiment === 'negative' ? 'bg-red-500' : 'bg-amber-400'
                              }`} />
                              <span className="text-sm">{t.theme}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">{t.frequency}x</Badge>
                              <Badge className={`text-xs ${
                                t.impact === 'high' ? 'bg-red-100 text-red-700' :
                                t.impact === 'medium' ? 'bg-amber-100 text-amber-700' : 'bg-muted text-muted-foreground'
                              }`}>{t.impact}</Badge>
                            </div>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}

                  {/* Top Issues */}
                  {sentiment.top_issues?.length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Isu Paling Sering</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {sentiment.top_issues.map((iss, i) => (
                          <div key={i} className="flex items-center justify-between">
                            <span className="text-sm">{iss.issue}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold tabular-nums">{iss.count}x</span>
                              <UrgencyBadge urgency={iss.urgency} />
                            </div>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}
                </div>

                {/* Recommendations */}
                {sentiment.recommendations?.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2"><Zap size={14} className="text-primary" /> Rekomendasi AI</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-1.5">
                        {sentiment.recommendations.map((r, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm">
                            <ChevronRight size={14} className="text-primary mt-0.5 shrink-0" />
                            {r}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}

                <Button variant="outline" size="sm" onClick={runSentiment}>
                  <RefreshCw size={13} className="mr-1" /> Analisis Ulang
                </Button>
              </div>
            );
          })()}
        </div>
      )}

      {/* Tab: Recommendations */}
      {activeTab === 'recommendations' && (
        <div className="space-y-4">
          {!recommendations && !loading.recommendations && (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
                <Zap size={40} className="text-muted-foreground opacity-40" />
                <div className="text-center">
                  <p className="font-medium">AI Action Items</p>
                  <p className="text-sm text-muted-foreground mt-1">AI akan menganalisis seluruh data marketing dan memberikan prioritas aksi hari ini</p>
                </div>
                <Button onClick={runRecommendations}>
                  <Sparkles size={14} className="mr-2" /> Generate Action Items
                </Button>
              </CardContent>
            </Card>
          )}
          {loading.recommendations && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <p className="text-sm text-muted-foreground">AI sedang menyusun rekomendasi...</p>
            </div>
          )}
          {recommendations && !loading.recommendations && (
            <div className="space-y-4">
              {/* Summary */}
              <Card className="bg-gradient-to-r from-violet-50 to-purple-50 dark:from-violet-950/30 dark:to-purple-950/30 border-violet-200 dark:border-violet-800">
                <CardContent className="pt-4">
                  <div className="flex items-start gap-3">
                    <Brain size={20} className="text-violet-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-violet-900 dark:text-violet-100">{recommendations.summary}</p>
                      <Badge className={`mt-2 text-xs ${
                        recommendations.overall_health === 'healthy' ? 'bg-emerald-100 text-emerald-700' :
                        recommendations.overall_health === 'critical' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                      }`}>
                        Health: {recommendations.overall_health}
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Action Items */}
              <div className="space-y-3">
                {(recommendations.action_items || []).map((item, i) => (
                  <Card key={i} className="transition-all hover:shadow-md">
                    <CardContent className="pt-4">
                      <div className="flex items-start gap-3">
                        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                          <span className="text-xs font-bold text-primary">{item.priority}</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="font-semibold text-sm">{item.title}</span>
                            <UrgencyBadge urgency={item.urgency} />
                            <span className="text-lg">{MODULE_ICONS[item.module] || '⚡'}</span>
                          </div>
                          <p className="text-sm text-muted-foreground">{item.description}</p>
                          {item.estimated_impact && (
                            <p className="text-xs text-primary mt-1.5 flex items-center gap-1">
                              <Target size={11} /> {item.estimated_impact}
                            </p>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Button variant="outline" size="sm" onClick={runRecommendations}>
                <RefreshCw size={13} className="mr-1" /> Refresh Action Items
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
