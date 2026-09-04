/**
 * AccountDetailPage
 * Halaman detail per platform account di Portal Marketing.
 * Menampilkan: KPI, Revenue Trend, Sales History, KOL Creator, LiveHost yang di-assign.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowLeft, TrendingUp, ShoppingBag, Users, Radio, RefreshCw,
  Star, Activity, Calendar, BarChart3, Loader2, Target,
  MessageCircle, RotateCcw, AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { RevenueChart } from '../RevenueChart';
import { AccountBadge, getPlatformConfig } from './AccountBadge';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

const fmt = formatRupiah;
const fmtCompact = (n) => {
  if (!n) return 'Rp 0';
  if (n >= 1_000_000_000) return `Rp ${(n / 1_000_000_000).toFixed(1)}M`;
  if (n >= 1_000_000) return `Rp ${(n / 1_000_000).toFixed(1)}jt`;
  if (n >= 1_000) return `Rp ${(n / 1_000).toFixed(0)}rb`;
  return `Rp ${n.toLocaleString('id-ID')}`;
};
const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID');
const pct = (n) => n != null ? `${(n * 100).toFixed(1)}%` : '-';

// ─── Target Progress Bar ──────────────────────────────────────────────────────
function TargetBar({ label, actual, target, fmtFn = fmtCompact }) {
  if (target == null || target === 0) return null;
  const p = Math.min(Math.round((actual / target) * 100), 100);
  const over = actual > target;
  const color = p >= 90 ? 'bg-emerald-500' : p >= 70 ? 'bg-amber-500' : 'bg-red-500';
  const textColor = p >= 90 ? 'text-emerald-600' : p >= 70 ? 'text-amber-600' : 'text-red-600';
  return (
    <div className="space-y-1" data-testid={`target-bar-${label.toLowerCase()}`}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={`font-semibold tabular-nums ${textColor}`}>
          {fmtFn(actual)} / {fmtFn(target)}
          <span className="ml-1.5 font-bold">{p}%</span>
          {over && <span className="ml-1 text-emerald-500">✓</span>}
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${p}%` }} />
      </div>
    </div>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, color = 'text-primary' }) {
  return (
    <GlassPanel className="p-4" data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">{label}</span>
        {Icon && <Icon size={14} className={color} />}
      </div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-0.5">{sub}</div>}
    </GlassPanel>
  );
}

// ─── Sales History Table ──────────────────────────────────────────────────────
function SalesTable({ data }) {
  if (!data.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <Calendar size={32} className="mx-auto mb-2 opacity-30" />
      Belum ada data sales untuk akun ini
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" data-testid="sales-history-table">
        <thead>
          <tr className="text-left text-muted-foreground border-b">
            <th className="py-2 px-3">Tanggal</th>
            <th className="py-2 px-3">Type</th>
            <th className="py-2 px-3 text-right">Revenue</th>
            <th className="py-2 px-3 text-right">Orders</th>
            <th className="py-2 px-3 text-right">AOV</th>
            <th className="py-2 px-3 text-right">CR</th>
            <th className="py-2 px-3 text-right">Rating</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={row.id || i} className="border-b last:border-0 hover:bg-muted/20" data-testid={`sales-row-${i}`}>
              <td className="py-2 px-3 font-mono">{row.date}</td>
              <td className="py-2 px-3">
                <Badge variant="outline" className={
                  row.revenue_type === 'live'
                    ? 'bg-pink-100 dark:bg-pink-500/10 text-pink-500 border-pink-400 dark:border-pink-500/30 text-[10px]'
                    : 'bg-blue-100 dark:bg-blue-500/10 text-blue-500 border-blue-400 dark:border-blue-500/30 text-[10px]'
                }>
                  {row.revenue_type === 'live' ? '🎥 Live' : '📊 Total'}
                </Badge>
              </td>
              <td className="py-2 px-3 text-right tabular-nums font-medium">{fmt(row.metrics?.revenue)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmtNum(row.metrics?.orders)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmt(row.metrics?.aov)}</td>
              <td className="py-2 px-3 text-right tabular-nums">{pct(row.metrics?.conversion_rate)}</td>
              <td className="py-2 px-3 text-right tabular-nums">
                {row.metrics?.rating ? (
                  <span className="flex items-center justify-end gap-0.5">
                    <Star size={10} className="text-amber-700 dark:text-amber-400 fill-amber-400" />
                    {Number(row.metrics.rating).toFixed(1)}
                  </span>
                ) : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Creators Tab ─────────────────────────────────────────────────────────────
function CreatorsTab({ creators, loading, creatorTargets = {} }) {
  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>;
  if (!creators.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <Users size={32} className="mx-auto mb-2 opacity-30" />
      Tidak ada KOL/Creator yang di-assign ke akun ini
    </div>
  );

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {creators.map(c => {
        const mt = creatorTargets[c.id];
        const revTgt  = mt?.revenue_target  || 0;
        const sessTgt = mt?.sessions_target || 0;
        const hasTarget = revTgt > 0 || sessTgt > 0;

        const revPct  = revTgt  > 0 ? Math.min(100, Math.round(((c.this_month?.revenue  || 0) / revTgt)  * 100)) : null;
        const sessPct = sessTgt > 0 ? Math.min(100, Math.round(((c.this_month?.sessions || 0) / sessTgt) * 100)) : null;
        const pctColor = (p) => p >= 90 ? 'bg-emerald-500' : p >= 60 ? 'bg-amber-500' : 'bg-red-500';

        return (
          <div key={c.id} className="rounded-lg border bg-card p-3" data-testid={`creator-card-${c.id}`}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center text-foreground text-xs font-bold shrink-0">
                {c.name?.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{c.name}</div>
                <div className="text-xs text-muted-foreground">{c.creator_code}</div>
              </div>
              <div className={`text-[10px] ml-auto shrink-0 px-1.5 py-0.5 rounded-full border font-medium ${
                c.status === 'active' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 border-emerald-400 dark:border-emerald-500/30' : 'bg-muted dark:bg-gray-500/10 text-muted-foreground border-border dark:border-gray-500/30'
              }`}>{c.status}</div>
            </div>

            {/* Actual stats */}
            <div className="grid grid-cols-3 gap-1 text-center text-[10px] mb-2">
              <div className="rounded bg-muted/30 p-1.5">
                <div className="text-muted-foreground">Sesi</div>
                <div className="font-bold">{c.this_month?.sessions || 0}</div>
              </div>
              <div className="rounded bg-muted/30 p-1.5">
                <div className="text-muted-foreground">Revenue</div>
                <div className="font-bold text-emerald-600">{fmtCompact(c.this_month?.revenue || 0)}</div>
              </div>
              <div className="rounded bg-muted/30 p-1.5">
                <div className="text-muted-foreground">Viewers</div>
                <div className="font-bold">{fmtNum(c.this_month?.viewers || 0)}</div>
              </div>
            </div>

            {/* Per-month target progress */}
            {hasTarget && (
              <div className="space-y-1.5 pt-2 border-t border-border">
                {revTgt > 0 && (
                  <div>
                    <div className="flex justify-between text-[10px] mb-0.5">
                      <span className="text-muted-foreground">Revenue</span>
                      <span className={revPct >= 90 ? 'text-emerald-600' : revPct >= 60 ? 'text-amber-600' : 'text-red-500'}>
                        {fmtCompact(c.this_month?.revenue || 0)} / {fmtCompact(revTgt)} ({revPct}%)
                      </span>
                    </div>
                    <div className="h-1 bg-muted rounded-full overflow-hidden">
                      <div className={`h-full ${pctColor(revPct)}`} style={{ width: `${revPct}%` }} />
                    </div>
                  </div>
                )}
                {sessTgt > 0 && (
                  <div>
                    <div className="flex justify-between text-[10px] mb-0.5">
                      <span className="text-muted-foreground">Sesi</span>
                      <span className={sessPct >= 90 ? 'text-emerald-600' : sessPct >= 60 ? 'text-amber-600' : 'text-red-500'}>
                        {c.this_month?.sessions || 0} / {sessTgt} ({sessPct}%)
                      </span>
                    </div>
                    <div className="h-1 bg-muted rounded-full overflow-hidden">
                      <div className={`h-full ${pctColor(sessPct)}`} style={{ width: `${sessPct}%` }} />
                    </div>
                  </div>
                )}
                <p className="text-[9px] text-violet-500 text-right">target {new Date().toLocaleString('id-ID',{month:'short',year:'numeric'})}</p>
              </div>
            )}
            {!hasTarget && (
              <p className="text-[9px] text-muted-foreground text-center pt-1 italic">Belum ada target bulan ini</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── LiveHosts Tab ────────────────────────────────────────────────────────────
function LiveHostsTab({ hosts, loading }) {
  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>;
  if (!hosts.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <Radio size={32} className="mx-auto mb-2 opacity-30" />
      Tidak ada LiveHost yang di-assign ke akun ini
    </div>
  );

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {hosts.map(h => (
        <div key={h.id} className="rounded-lg border bg-card p-3" data-testid={`host-card-${h.id}`}>
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-sm font-semibold">{h.name}</div>
              <div className="text-xs text-muted-foreground">{h.email}</div>
            </div>
            <Badge variant="outline" className={`text-[10px] ${
              h.status === 'active' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 border-emerald-400 dark:border-emerald-500/30' : 'bg-muted dark:bg-gray-500/10 text-muted-foreground border-border dark:border-gray-500/30'
            }`}>{h.status}</Badge>
          </div>
          <div className="text-[10px] text-muted-foreground">
            {h.employment_type} · Rp {fmtNum(h.hourly_rate)}/jam
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Orders Tab ───────────────────────────────────────────────────────────────
function OrdersTab({ orders, loading }) {
  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>;
  if (!orders.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <ShoppingBag size={32} className="mx-auto mb-2 opacity-30" />
      Belum ada data order untuk akun ini
    </div>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" data-testid="account-orders-table">
        <thead><tr className="border-b text-muted-foreground">
          <th className="py-2 px-3 text-left">Order ID</th>
          <th className="py-2 px-3 text-left">Produk</th>
          <th className="py-2 px-3 text-right">Total</th>
          <th className="py-2 px-3 text-center">Status</th>
          <th className="py-2 px-3">Tanggal</th>
        </tr></thead>
        <tbody>
          {orders.slice(0, 50).map((o, i) => (
            <tr key={o.id || i} className="border-b last:border-0 hover:bg-muted/20">
              <td className="py-2 px-3 font-mono">{o.order_id || o.id}</td>
              <td className="py-2 px-3 max-w-[160px] truncate">{o.product_name || o.items?.[0]?.name || '—'}</td>
              <td className="py-2 px-3 text-right tabular-nums">{fmtCompact(o.total_payment || o.revenue || 0)}</td>
              <td className="py-2 px-3 text-center">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                  o.status === 'delivered' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600' :
                  o.status === 'cancelled' ? 'bg-red-100 dark:bg-red-500/10 text-red-600' : 'bg-blue-100 dark:bg-blue-500/10 text-blue-600'
                }`}>{o.status}</span>
              </td>
              <td className="py-2 px-3 text-muted-foreground">{o.order_date?.slice(0, 10) || o.date || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Complaints Tab ───────────────────────────────────────────────────────────
function ComplaintsTab({ complaints, loading }) {
  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>;
  if (!complaints.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <MessageCircle size={32} className="mx-auto mb-2 opacity-30" />
      Belum ada komplain untuk akun ini
    </div>
  );
  return (
    <div className="space-y-2" data-testid="account-complaints-list">
      {complaints.map((c, i) => (
        <div key={c.id || i} className="rounded-lg border bg-card p-3">
          <div className="flex items-start justify-between gap-2 mb-1">
            <div className="font-mono text-xs text-muted-foreground">{c.complaint_number || c.id?.slice(0,8)}</div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              c.status === 'resolved' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600' :
              c.status === 'open' ? 'bg-red-100 dark:bg-red-500/10 text-red-600' : 'bg-amber-100 dark:bg-amber-500/10 text-amber-600'
            }`}>{c.status}</span>
          </div>
          <p className="text-sm font-medium truncate">{c.complaint_text || c.title || '—'}</p>
          <p className="text-xs text-muted-foreground mt-1">{c.product_name && `${c.product_name} · `}{c.complaint_date?.slice(0,10) || c.date || ''}</p>
        </div>
      ))}
    </div>
  );
}

// ─── Reviews Tab ─────────────────────────────────────────────────────────────
function ReviewsTab({ reviews, loading }) {
  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>;
  if (!reviews.length) return (
    <div className="py-10 text-center text-muted-foreground text-sm">
      <Star size={32} className="mx-auto mb-2 opacity-30" />
      Belum ada review untuk akun ini
    </div>
  );
  return (
    <div className="space-y-2" data-testid="account-reviews-list">
      {reviews.map((r, i) => (
        <div key={r.id || i} className="rounded-lg border bg-card p-3">
          <div className="flex items-center gap-2 mb-1">
            <div className="flex">
              {[1,2,3,4,5].map(s => (
                <Star key={s} size={11} className={s <= (r.rating || 0) ? 'text-amber-700 dark:text-amber-400 fill-amber-400' : 'text-muted-foreground'} />
              ))}
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ml-auto ${
              r.status === 'responded' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600' : 'bg-amber-100 dark:bg-amber-500/10 text-amber-600'
            }`}>{r.status || 'pending'}</span>
          </div>
          <p className="text-sm truncate">{r.review_text || '—'}</p>
          <p className="text-xs text-muted-foreground mt-1">{r.product && `${r.product} · `}{r.date || ''}</p>
        </div>
      ))}
    </div>
  );
}

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
export function AccountDetailPage({ account, token, onBack, onNavigate }) {
  const { setActiveAccount } = useActiveMarketingAccount();
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const cfg = getPlatformConfig(account.platform);

  const now = new Date();
  const [salesData, setSalesData] = useState([]);
  const [creators, setCreators] = useState([]);
  const [hosts, setHosts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [target, setTarget] = useState(null);
  const [creatorTargets, setCreatorTargets] = useState({});
  const [loading, setLoading] = useState(true);
  const [creatorsLoading, setCreatorsLoading] = useState(true);
  const [hostsLoading, setHostsLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [complaintsLoading, setComplaintsLoading] = useState(true);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [tab, setTab] = useState('sales');

  // Fetch sales data
  const fetchSales = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/accounts/${account.id}/sales?limit=60`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSalesData(Array.isArray(data) ? data.sort((a, b) => b.date.localeCompare(a.date)) : []);
      }
    } catch { toast.error('Gagal memuat data sales'); }
    finally { setLoading(false); }
  }, [account.id, headers]);

  // Fetch assigned KOL creators + their per-month targets
  const fetchCreators = useCallback(async () => {
    setCreatorsLoading(true);
    try {
      const [crRes, tgRes] = await Promise.all([
        fetch(`${API}/api/marketing/kol/creators?account_id=${account.id}&limit=50`, { headers }),
        fetch(`${API}/api/marketing/targets/creator?year=${now.getFullYear()}&month=${now.getMonth()+1}`, { headers }),
      ]);
      if (crRes.ok) {
        const data = await crRes.json();
        setCreators(data?.creators || (Array.isArray(data) ? data : []));
      }
      if (tgRes.ok) {
        const tgts = await tgRes.json();
        const map = {};
        if (Array.isArray(tgts)) tgts.forEach(t => { map[t.creator_id] = t; });
        setCreatorTargets(map);
      }
    } catch { /* noop */ }
    finally { setCreatorsLoading(false); }
  }, [account.id, headers]); // eslint-disable-line

  // Fetch assigned LiveHosts (client-side filter)
  const fetchHosts = useCallback(async () => {
    setHostsLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost`, { headers });
      if (res.ok) {
        const data = await res.json();
        const filtered = (Array.isArray(data) ? data : []).filter(h =>
          (h.assigned_accounts || []).some(a => a.id === account.id)
        );
        setHosts(filtered);
      }
    } catch { /* noop */ }
    finally { setHostsLoading(false); }
  }, [account.id, headers]);

  useEffect(() => {
    fetchSales();
    fetchCreators();
    fetchHosts();
    // Fetch target bulan ini
    fetch(`${API}/api/marketing/targets?account_id=${account.id}&year=${now.getFullYear()}&month=${now.getMonth() + 1}`, { headers })
      .then(r => r.ok ? r.json() : [])
      .then(data => setTarget(Array.isArray(data) && data.length > 0 ? data[0] : null))
      .catch(() => {});
    // Fetch orders (by account_name since orders use string-based matching)
    setOrdersLoading(true);
    fetch(`${API}/api/marketing/orders?account_name=${encodeURIComponent(account.account_name)}&limit=50`, { headers })
      .then(r => r.ok ? r.json() : { orders: [] })
      .then(d => setOrders(Array.isArray(d) ? d : (d.orders || [])))
      .catch(() => {})
      .finally(() => setOrdersLoading(false));
    // Fetch complaints by account_id
    setComplaintsLoading(true);
    fetch(`${API}/api/marketing/complaints?account_id=${account.id}&page_size=50`, { headers })
      .then(r => r.ok ? r.json() : { complaints: [] })
      .then(d => setComplaints(d.complaints || []))
      .catch(() => {})
      .finally(() => setComplaintsLoading(false));
    // Fetch reviews by account_id
    setReviewsLoading(true);
    fetch(`${API}/api/marketing/reviews?account_id=${account.id}&page_size=50`, { headers })
      .then(r => r.ok ? r.json() : { data: [] })
      .then(d => setReviews(d.data || []))
      .catch(() => {})
      .finally(() => setReviewsLoading(false));
  }, [fetchSales, fetchCreators, fetchHosts]); // eslint-disable-line

  // Compute revenue trend from sales data
  const trendData = useMemo(() => {
    const map = {};
    salesData.forEach(row => {
      if (!map[row.date]) map[row.date] = { date: row.date, total: 0, live: 0 };
      const rev = row.metrics?.revenue || 0;
      if (row.revenue_type === 'live') map[row.date].live += rev;
      else map[row.date].total += rev;
    });
    return Object.values(map).sort((a, b) => a.date.localeCompare(b.date));
  }, [salesData]);

  // Compute KPI summary (last 30 days total-type only)
  const kpi = useMemo(() => {
    const totalRows = salesData.filter(r => r.revenue_type === 'total');
    const liveRows = salesData.filter(r => r.revenue_type === 'live');
    const rev = totalRows.reduce((s, r) => s + (r.metrics?.revenue || 0), 0);
    const revLive = liveRows.reduce((s, r) => s + (r.metrics?.revenue || 0), 0);
    const orders = totalRows.reduce((s, r) => s + (r.metrics?.orders || 0), 0);
    const aov = orders > 0 ? rev / orders : 0;
    const ratings = totalRows.map(r => r.metrics?.rating).filter(Boolean);
    const avgRating = ratings.length ? (ratings.reduce((s, r) => s + r, 0) / ratings.length) : null;
    return { rev, revLive, orders, aov, avgRating, days: totalRows.length };
  }, [salesData]);

  const healthColor = account.health_score >= 80 ? 'text-emerald-500'
    : account.health_score >= 60 ? 'text-amber-500'
    : account.health_score != null ? 'text-red-500' : 'text-muted-foreground';

  return (
    <div className="space-y-5" data-testid="account-detail-page">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="mt-0.5 h-8 px-2"
          data-testid="back-to-dashboard"
        >
          <ArrowLeft size={16} className="mr-1" /> Kembali
        </Button>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h1 className="text-xl font-bold truncate">{account.account_name}</h1>
            <AccountBadge account={account} size="sm" />
            <Badge variant="outline" className={`text-xs ${
              account.status === 'active' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 border-emerald-400 dark:border-emerald-500/30' : ''
            }`}>{account.status}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {account.account_code} · {account.username && `@${account.username} · `}
            {account.group?.replace('_', ' ')}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setActiveAccount(account);
              onNavigate?.('marketing-sales');
            }}
            data-testid="goto-input-sales"
          >
            <TrendingUp size={13} className="mr-1.5" /> Input Sales
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setActiveAccount(account);
              toast.success(`Akun aktif: ${account.account_name}`);
            }}
            data-testid="set-active-account"
          >
            Set Akun Aktif
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard label="Total Revenue" value={fmtCompact(kpi.rev)} sub={`+Live: ${fmtCompact(kpi.revLive)}`} icon={TrendingUp} color="text-primary" />
        <KpiCard label="Total Orders" value={fmtNum(kpi.orders)} sub={`${kpi.days} hari data`} icon={ShoppingBag} color="text-blue-500" />
        <KpiCard label="Avg Order Value" value={fmtCompact(kpi.aov)} icon={BarChart3} color="text-amber-500" />
        <KpiCard
          label="Health Score"
          value={account.health_score != null ? account.health_score : 'N/A'}
          sub={account.health_score >= 80 ? 'Excellent' : account.health_score >= 60 ? 'Good' : account.health_score != null ? 'Perlu perhatian' : 'Belum ada data'}
          icon={Activity}
          color={healthColor}
        />
        <KpiCard label="KOL / Creator" value={creators.length} sub="yang di-assign" icon={Users} color="text-violet-500" />
        <KpiCard label="Live Host" value={hosts.length} sub="yang di-assign" icon={Radio} color="text-pink-500" />
      </div>

      {/* Target Bulan Ini */}
      <GlassCard className="p-4" data-testid="account-target-section">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            <Target size={14} className="text-primary" />
            Target Bulan Ini — {now.toLocaleString('id-ID', { month: 'long', year: 'numeric' })}
          </h3>
          <Button
            size="sm" variant="outline" className="h-7 text-xs"
            onClick={() => onNavigate?.('marketing-targets')}
            data-testid="goto-set-target"
          >
            <Target size={11} className="mr-1" />
            {target ? 'Edit Target' : 'Set Target'}
          </Button>
        </div>
        {target ? (
          <div className="space-y-3">
            <TargetBar label="Revenue" actual={kpi.rev} target={target.revenue_target} fmtFn={fmtCompact} />
            <TargetBar label="Orders" actual={kpi.orders} target={target.orders_target} fmtFn={(n) => fmtNum(n)} />
            {target.notes && (
              <p className="text-xs text-muted-foreground italic border-t pt-2 mt-2">📝 {target.notes}</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            Belum ada target untuk bulan ini.
            <button onClick={() => onNavigate?.('marketing-targets')} className="ml-1 text-primary hover:underline">
              Set target sekarang →
            </button>
          </p>
        )}
      </GlassCard>

      {/* Revenue Trend Chart */}
      <GlassCard className="p-5" data-testid="account-revenue-chart">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Activity size={14} className="text-primary" /> Revenue Trend — {account.account_name}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">Total vs Live revenue harian</p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400" /> Total</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-pink-400" /> Live</span>
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={fetchSales}>
              <RefreshCw size={11} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>
        </div>
        {loading ? (
          <div className="h-52 flex items-center justify-center text-muted-foreground text-sm">
            <Loader2 className="animate-spin mr-2" size={18} /> Memuat data...
          </div>
        ) : trendData.length === 0 ? (
          <div className="h-52 flex items-center justify-center text-muted-foreground text-sm">
            Belum ada data sales untuk akun ini
          </div>
        ) : (
          <RevenueChart data={trendData} height={220} />
        )}
      </GlassCard>

      {/* Tabs: Sales | Creator | LiveHost | Orders | Komplain | Reviews */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList data-testid="account-detail-tabs" className="flex-wrap h-auto">
          <TabsTrigger value="sales" data-testid="tab-sales">
            <TrendingUp size={13} className="mr-1.5" />Sales History
          </TabsTrigger>
          <TabsTrigger value="creators" data-testid="tab-creators">
            <Users size={13} className="mr-1.5" />KOL Creator ({creators.length})
          </TabsTrigger>
          <TabsTrigger value="hosts" data-testid="tab-hosts">
            <Radio size={13} className="mr-1.5" />LiveHost ({hosts.length})
          </TabsTrigger>
          <TabsTrigger value="orders" data-testid="tab-orders">
            <ShoppingBag size={13} className="mr-1.5" />Orders ({orders.length})
          </TabsTrigger>
          <TabsTrigger value="complaints" data-testid="tab-complaints">
            <MessageCircle size={13} className="mr-1.5" />Komplain ({complaints.length})
          </TabsTrigger>
          <TabsTrigger value="reviews" data-testid="tab-reviews">
            <Star size={13} className="mr-1.5" />Reviews ({reviews.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sales" className="mt-4">
          <GlassCard className="p-0 overflow-hidden">
            {loading ? (
              <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>
            ) : (
              <SalesTable data={salesData} />
            )}
          </GlassCard>
        </TabsContent>

        <TabsContent value="creators" className="mt-4">
          <CreatorsTab creators={creators} loading={creatorsLoading} creatorTargets={creatorTargets} />
        </TabsContent>

        <TabsContent value="hosts" className="mt-4">
          <LiveHostsTab hosts={hosts} loading={hostsLoading} />
        </TabsContent>

        <TabsContent value="orders" className="mt-4">
          <GlassCard className="p-0 overflow-hidden">
            <OrdersTab orders={orders} loading={ordersLoading} />
          </GlassCard>
        </TabsContent>

        <TabsContent value="complaints" className="mt-4">
          <ComplaintsTab complaints={complaints} loading={complaintsLoading} />
        </TabsContent>

        <TabsContent value="reviews" className="mt-4">
          <ReviewsTab reviews={reviews} loading={reviewsLoading} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
