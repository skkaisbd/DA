/**
 * LiveSessionAnalyticsDashboard — Phase 3 P1
 *
 * Advanced analytics untuk Live Session (Shopee/TikTok/Instagram).
 * Fitur: KPI overview, platform share, session comparison, host leaderboard,
 *        revenue trend chart, account health.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  TrendingUp, Users, ShoppingCart, DollarSign,
  RefreshCw, Star, BarChart3, Award, Activity,
  ChevronUp, ChevronDown, Eye, Zap, Package,
} from 'lucide-react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Badge } from '../../ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../ui/select';
import { useToast } from '../../../hooks/use-toast';
import { MarketingAccountSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL || '';

const FMT_IDR = v => `Rp ${(+v || 0).toLocaleString('id-ID')}`;
const FMT_NUM = v => (+v || 0).toLocaleString('id-ID');
const FMT_PCT = v => `${(+v || 0).toFixed(1)}%`;

const PLATFORM_COLORS = {
  shopee:    { bg: 'bg-orange-100 dark:bg-orange-500/15', text: 'text-orange-600 dark:text-orange-400', border: 'border-orange-400 dark:border-orange-500/30', bar: 'bg-orange-500' },
  tiktok:    { bg: 'bg-muted dark:bg-muted-foreground/15',   text: 'text-foreground/80',   border: 'border-border dark:border-border/60',   bar: 'bg-muted-foreground/40' },
  instagram: { bg: 'bg-pink-100 dark:bg-pink-500/15',   text: 'text-pink-600 dark:text-pink-400',   border: 'border-pink-400 dark:border-pink-500/30',   bar: 'bg-pink-500' },
  tokopedia: { bg: 'bg-green-100 dark:bg-green-500/15',  text: 'text-green-700 dark:text-green-400',  border: 'border-green-400 dark:border-green-500/30',  bar: 'bg-green-500' },
};

const PLATFORMS_LIST = ['shopee', 'tiktok', 'instagram', 'tokopedia'];

function DeltaBadge({ pct }) {
  if (pct == null) return null;
  const pos = pct >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${
      pos ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'
    }`}>
      {pos ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      {Math.abs(pct)}%
    </span>
  );
}

function MiniBarChart({ data, valueKey = 'revenue', labelKey = 'date' }) {
  if (!data || data.length === 0) return (
    <div className="flex items-center justify-center h-24 text-muted-foreground/80 text-xs">Belum ada data</div>
  );
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1);
  return (
    <div className="flex items-end gap-1 h-24 px-1">
      {data.slice(-14).map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center group relative">
          <div
            className="w-full bg-blue-500 rounded-sm opacity-70 hover:opacity-100 transition-all"
            style={{ height: `${((d[valueKey] || 0) / max) * 100}%` }}
          />
          <div className="absolute bottom-full mb-1 bg-muted border border-border rounded px-2 py-1 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 z-10">
            {d[labelKey]}: {FMT_IDR(d[valueKey])}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function LiveSessionAnalyticsDashboard({ user, headers }) {
  const [overview, setOverview] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [trend, setTrend] = useState([]);
  const [accountHealth, setAccountHealth] = useState([]);
  // F18#3 — panel "Produk Terlaris saat Live": endpoint sudah lama ada tetapi
  // TIDAK PUNYA LAYAR, dan sumber datanya pun belum bisa diisi. Keduanya beres.
  const [products, setProducts] = useState({ data: [], totals: {}, note: '' });
  const [accountId, setAccountId] = useState('');
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState('30');
  const [platform, setPlatform] = useState('all');
  const [activeTab, setActiveTab] = useState('overview');
  const { toast } = useToast();
  const authH = useMemo(() => headers || {}, [headers]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = { days: parseInt(days) };
      if (platform && platform !== 'all') params.platform = platform;
      // F14 — filter toko dikirim ke SEMUA endpoint analitik yang menerimanya.
      if (accountId) params.account_id = accountId;

      const [ovRes, sessRes, lbRes, trendRes, healthRes, prodRes] = await Promise.all([
        axios.get(`${API}/api/marketing/live/analytics/overview`, { headers: authH, params }),
        axios.get(`${API}/api/marketing/live/analytics/sessions-comparison`, { headers: authH, params: { ...params, limit: 10 } }),
        axios.get(`${API}/api/marketing/live/analytics/host-leaderboard`, { headers: authH, params }),
        axios.get(`${API}/api/marketing/live/analytics/revenue-trend`, { headers: authH, params: { ...params, granularity: 'weekly' } }),
        axios.get(`${API}/api/marketing/live/analytics/account-health`, { headers: authH, params: { days: parseInt(days), ...(accountId ? { account_id: accountId } : {}) } }),
        axios.get(`${API}/api/marketing/live/analytics/product-performance`, { headers: authH, params: { ...params, limit: 20 } }),
      ]);

      setOverview(ovRes.data);
      setSessions(sessRes.data?.data || []);
      setLeaderboard(lbRes.data?.data || []);
      setTrend(trendRes.data?.data || []);
      setAccountHealth(healthRes.data?.data || []);
      setProducts({
        data: prodRes.data?.data || [],
        totals: prodRes.data?.totals || {},
        note: prodRes.data?.note || '',
        source: prodRes.data?.source,
      });
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal load analytics', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [days, platform, accountId, authH, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const kpi = overview?.kpi || {};
  const platformShare = overview?.platform_share || [];
  const dailyTrend = overview?.daily_trend || [];

  const TABS = [
    { id: 'overview',  label: 'Overview' },
    { id: 'sessions',  label: 'Top Sessions' },
    { id: 'products',  label: 'Produk Terlaris' },
    { id: 'leaderboard', label: 'Host Ranking' },
    { id: 'trend',     label: 'Revenue Trend' },
    { id: 'health',    label: 'Account Health' },
  ];

  return (
    <div className="p-4 md:p-6 space-y-5 text-foreground">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Zap className="text-amber-700 dark:text-amber-400" /> Live Session Analytics
          </h2>
          <p className="text-sm text-muted-foreground mt-1">Analisis performa live session multi-platform</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <div className="w-52">
            <MarketingAccountSelect
              value={accountId} onChange={setAccountId} label=""
              includeAll allLabel="Semua Toko" required={false}
              testId="sel-analytics-account"
            />
          </div>
          <Select value={platform} onValueChange={setPlatform}>
            <SelectTrigger className="w-36 bg-card border-border text-sm" data-testid="sel-platform">
              <SelectValue placeholder="Semua Platform" />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {/* RC-20: Radix Select melarang value="" (crash ErrorBoundary) → pakai 'all' */}
              <SelectItem value="all">Semua Platform</SelectItem>
              {PLATFORMS_LIST.map(p => (
                <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-28 bg-card border-border text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              <SelectItem value="7">7 Hari</SelectItem>
              <SelectItem value="30">30 Hari</SelectItem>
              <SelectItem value="90">90 Hari</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}
            className="border-border text-foreground/80 hover:bg-muted" data-testid="btn-refresh-analytics">
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { icon: Zap,          label: 'Total Sesi',       value: FMT_NUM(kpi.total_sessions),       sub: `${days} hari` },
          { icon: DollarSign,   label: 'Total Revenue',    value: FMT_IDR(kpi.total_revenue_rp),     sub: <DeltaBadge pct={kpi.revenue_delta_vs_prev_period_pct} /> },
          { icon: ShoppingCart, label: 'Total Order',      value: FMT_NUM(kpi.total_orders),          sub: `${FMT_IDR(kpi.avg_revenue_per_session)}/sesi` },
          { icon: Eye,          label: 'Avg Peak Viewers', value: FMT_NUM(kpi.avg_viewers),           sub: `Conv ${FMT_PCT(kpi.avg_conversion_rate)}` },
        ].map(({ icon: Icon, label, value, sub }) => (
          <Card key={label} className="bg-card border-border">
            <CardContent className="pt-4 pb-3">
              <div className="flex justify-between items-start mb-1">
                <span className="text-xs text-muted-foreground">{label}</span>
                <Icon className="w-4 h-4 text-muted-foreground/60" />
              </div>
              <div className="text-xl font-bold text-foreground">{loading ? '…' : value}</div>
              <div className="text-xs text-muted-foreground/80 mt-0.5">{sub}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === t.id
                ? 'text-foreground border-b-2 border-blue-500'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`tab-${t.id}`}
          >{t.label}</button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Platform Share */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-foreground/80">Share per Platform</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {platformShare.length === 0 ? (
                <p className="text-muted-foreground/80 text-sm">Belum ada data</p>
              ) : platformShare.map(p => {
                const pc = PLATFORM_COLORS[p.platform] || { bg: 'bg-muted-foreground/30', text: 'text-foreground/80', bar: 'bg-muted-foreground/60' };
                return (
                  <div key={p.platform}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className={`font-medium ${pc.text}`}>{p.platform}</span>
                      <span className="text-muted-foreground">{FMT_IDR(p.revenue)} ({p.revenue_share_pct}%)</span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div className={`h-full ${pc.bar} rounded-full`} style={{ width: `${p.revenue_share_pct}%` }} />
                    </div>
                    <div className="text-xs text-muted-foreground/60 mt-0.5">{p.sessions} sesi &bull; {p.orders} order</div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Daily Trend Mini */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-foreground/80">Revenue Harian</CardTitle>
            </CardHeader>
            <CardContent>
              <MiniBarChart data={dailyTrend} valueKey="revenue" labelKey="date" />
              <div className="text-xs text-muted-foreground/80 mt-2 text-center">
                Top platform: <span className="text-foreground">{kpi.top_platform || '—'}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'sessions' && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80">Top {sessions.length} Sesi ({days} hari)</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sessions.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground/80">Belum ada data sesi</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="text-left px-4 py-2">#</th>
                      <th className="text-left px-4 py-2">Tanggal</th>
                      <th className="text-left px-4 py-2">Platform</th>
                      <th className="text-left px-4 py-2">Host</th>
                      <th className="text-right px-4 py-2">Revenue</th>
                      <th className="text-right px-4 py-2">Orders</th>
                      <th className="text-right px-4 py-2">Viewers</th>
                      <th className="text-right px-4 py-2">Conv%</th>
                      <th className="text-right px-4 py-2">vs Rata</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map(s => (
                      <tr key={s.id} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="px-4 py-2 text-muted-foreground/80">{s.rank}</td>
                        <td className="px-4 py-2 text-foreground/80">{s.session_date}</td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded border ${
                            PLATFORM_COLORS[s.platform]?.bg || 'bg-muted-foreground/30'
                          } ${PLATFORM_COLORS[s.platform]?.text || 'text-foreground/80'} ${
                            PLATFORM_COLORS[s.platform]?.border || 'border-border'
                          }`}>{s.platform}</span>
                        </td>
                        <td className="px-4 py-2 text-foreground/80">{s.host_name || '—'}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400 font-medium">{FMT_IDR(s.total_revenue)}</td>
                        <td className="px-4 py-2 text-right text-foreground/80">{s.orders_count}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{FMT_NUM(s.peak_viewers)}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{s.conversion_rate}%</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaBadge pct={s.vs_avg_pct} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'products' && (
        <Card className="bg-card border-border" data-testid="panel-live-products">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm text-foreground/80 flex items-center gap-1.5">
                <Package className="w-4 h-4" /> Produk Terlaris saat Live ({days} hari)
              </CardTitle>
              {products.data.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {FMT_NUM(products.totals.products)} produk ·{' '}
                  {FMT_NUM(products.totals.units_sold)} unit ·{' '}
                  {FMT_IDR(products.totals.revenue)}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Menjawab “barang mana yang paling laku saat live” — sumber angkanya
              rincian produk per sesi, bukan taksiran.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            {products.data.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                {products.note || 'Belum ada rincian produk pada sesi live.'}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="text-left px-4 py-2">#</th>
                      <th className="text-left px-4 py-2">SKU</th>
                      <th className="text-left px-4 py-2">Produk</th>
                      {!accountId && <th className="text-left px-4 py-2">Toko</th>}
                      <th className="text-right px-4 py-2">Unit</th>
                      <th className="text-right px-4 py-2">Omzet</th>
                      <th className="text-right px-4 py-2">Pangsa</th>
                      <th className="text-right px-4 py-2">Sesi</th>
                      <th className="text-right px-4 py-2">Unit/sesi</th>
                      <th className="text-right px-4 py-2">Harga rata²</th>
                      <th className="text-right px-4 py-2">Margin kotor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.data.map((p) => (
                      <tr key={`${p.catalog_item_id || p.sku}`} className="border-b border-border/60 hover:bg-muted/30">
                        <td className="px-4 py-2 text-muted-foreground">{p.rank}</td>
                        <td className="px-4 py-2 font-mono text-xs">{p.sku || '—'}</td>
                        <td className="px-4 py-2">
                          {p.name || '—'}
                          {p.category ? <span className="text-xs text-muted-foreground ml-1">({p.category})</span> : null}
                        </td>
                        {!accountId && (
                          <td className="px-4 py-2 text-xs text-muted-foreground max-w-[160px] truncate"
                            title={p.account_name}>{p.account_name || '—'}</td>
                        )}
                        <td className="px-4 py-2 text-right tabular-nums font-semibold">{FMT_NUM(p.total_units_sold)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-emerald-600 font-semibold">{FMT_IDR(p.total_revenue)}</td>
                        <td className="px-4 py-2 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <div className="h-1.5 w-14 bg-muted rounded-full overflow-hidden">
                              <div className="h-full bg-blue-500" style={{ width: `${Math.min(p.revenue_share_pct, 100)}%` }} />
                            </div>
                            <span className="text-xs tabular-nums w-10 text-right">{p.revenue_share_pct}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">{FMT_NUM(p.sessions_featured)}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{p.units_per_session}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{FMT_IDR(p.avg_price)}</td>
                        <td className={`px-4 py-2 text-right tabular-nums ${(p.gross_margin || 0) >= 0 ? '' : 'text-red-600'}`}>
                          {FMT_IDR(p.gross_margin)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'leaderboard' && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
              <Award className="w-4 h-4 text-amber-700 dark:text-amber-400" /> Host Leaderboard ({days} hari)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {leaderboard.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground/80">Belum ada data host</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="text-left px-4 py-2">Rank</th>
                      <th className="text-left px-4 py-2">Host</th>
                      <th className="text-right px-4 py-2">Sesi</th>
                      <th className="text-right px-4 py-2">Total Revenue</th>
                      <th className="text-right px-4 py-2">Avg/Sesi</th>
                      <th className="text-right px-4 py-2">Avg Viewers</th>
                      <th className="text-right px-4 py-2">Conv%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.map((h, i) => (
                      <tr key={h.host_name} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="px-4 py-2">
                          <span className={`font-bold ${
                            i === 0 ? 'text-amber-700 dark:text-amber-400' : i === 1 ? 'text-foreground/80' : i === 2 ? 'text-orange-600 dark:text-orange-400' : 'text-muted-foreground/80'
                          }`}>#{h.rank}</span>
                        </td>
                        <td className="px-4 py-2 font-medium text-foreground">{h.host_name}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{h.total_sessions}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400 font-medium">{FMT_IDR(h.total_revenue)}</td>
                        <td className="px-4 py-2 text-right text-foreground/80">{FMT_IDR(h.avg_revenue_per_session)}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{FMT_NUM(h.avg_viewers)}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{h.avg_conversion_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'trend' && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Revenue Trend (Weekly)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trend.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground/80">Belum ada data trend</div>
            ) : (
              <>
                <MiniBarChart data={trend} valueKey="revenue" labelKey="period" />
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground/80">
                        <th className="text-left py-1 px-2">Periode</th>
                        <th className="text-right py-1 px-2">Revenue</th>
                        <th className="text-right py-1 px-2">Sesi</th>
                        <th className="text-right py-1 px-2">Orders</th>
                        <th className="text-right py-1 px-2">Avg/Sesi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trend.map(t => (
                        <tr key={t.period} className="border-b border-border/30">
                          <td className="py-1 px-2 text-foreground/80">{t.period}</td>
                          <td className="py-1 px-2 text-right text-emerald-600 dark:text-emerald-400">{FMT_IDR(t.revenue)}</td>
                          <td className="py-1 px-2 text-right text-muted-foreground">{t.sessions}</td>
                          <td className="py-1 px-2 text-right text-muted-foreground">{t.orders}</td>
                          <td className="py-1 px-2 text-right text-muted-foreground">{FMT_IDR(t.avg_revenue_per_session)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'health' && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80">Account Health Score</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {accountHealth.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground/80">Belum ada data akun</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="text-left px-4 py-2">Akun</th>
                      <th className="text-left px-4 py-2">Platform</th>
                      <th className="text-right px-4 py-2">Sesi</th>
                      <th className="text-right px-4 py-2">Revenue</th>
                      <th className="text-right px-4 py-2">Conv%</th>
                      <th className="text-right px-4 py-2">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accountHealth.map(a => (
                      <tr key={`${a.account_name}-${a.platform}`} className="border-b border-border/50">
                        <td className="px-4 py-2 font-medium text-foreground">{a.account_name}</td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            PLATFORM_COLORS[a.platform]?.bg || 'bg-muted-foreground/30'
                          } ${PLATFORM_COLORS[a.platform]?.text || 'text-foreground/80'}`}>{a.platform}</span>
                        </td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{a.sessions}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">{FMT_IDR(a.total_revenue)}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{a.avg_conversion_rate}%</td>
                        <td className="px-4 py-2 text-right">
                          <span className={`font-bold ${
                            a.health_score >= 80 ? 'text-emerald-600 dark:text-emerald-400' :
                            a.health_score >= 60 ? 'text-blue-600 dark:text-blue-400' :
                            a.health_score >= 40 ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400'
                          }`}>{a.health_score}</span>
                          <span className="text-muted-foreground/60 text-xs ml-1">({a.health_status})</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
