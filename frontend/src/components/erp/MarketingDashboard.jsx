import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Store, TrendingUp, Package, RefreshCw, Plus, BarChart3, Activity, Tv2,
} from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader } from './moduleAtoms';
import { PeriodSelector } from './PeriodSelector';
import { AccountCard } from './AccountCard';
import { RevenueChart } from './RevenueChart';
import { HealthScoreGauge } from './HealthScoreGauge';
import { AccountDetailPage } from './marketing/AccountDetailPage';
import { MarketingCycleStrip } from './marketing/MarketingCycleStrip';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const fmt = formatRupiah;
const fmtCompact = (n) => {
  if (!n) return 'Rp 0';
  if (n >= 1_000_000_000) return `Rp ${(n / 1_000_000_000).toFixed(1)}M`;
  if (n >= 1_000_000) return `Rp ${(n / 1_000_000).toFixed(1)}jt`;
  if (n >= 1_000) return `Rp ${(n / 1_000).toFixed(0)}rb`;
  return `Rp ${n.toLocaleString('id-ID')}`;
};

export default function MarketingDashboard({ token, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [perAccountTrend, setPerAccountTrend] = useState({}); // { accountId: [{date,total,live}] }
  // FASE D (2026-08-16) — bawaan periode = BULAN BERJALAN, bukan kosong/30 hari.
  // Target, anggaran, dan ROI marketing semuanya BULANAN. Dengan bawaan lama
  // (30 hari terakhir dari backend) rentangnya selalu menyerempet dua bulan,
  // sehingga omzet di layar tidak pernah bisa disandingkan dengan targetnya —
  // dan itulah yang terbaca sebagai "angka dashboard tidak nyambung".
  const [period, setPeriod] = useState(() => {
    const d = new Date();
    return {
      date_from: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`,
      date_to: d.toISOString().split('T')[0],
    };
  });
  const [chartAccountFilter, setChartAccountFilter] = useState('all');
  const [detailAccount, setDetailAccount] = useState(null); // null = dashboard, object = detail view
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );
  // Bulan yang dipakai untuk angka RESMI (target/anggaran/ROI) — diambil dari
  // tanggal akhir rentang supaya layar dan SSOT siklus bicara tentang bulan sama.
  const cyclePeriod = useMemo(
    () => (period.date_to || new Date().toISOString().split('T')[0]).slice(0, 7),
    [period.date_to]
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (period.date_from) params.append('date_from', period.date_from);
      if (period.date_to) params.append('date_to', period.date_to);

      const [overviewRes, accountsRes] = await Promise.all([
        fetch(`${API_BASE}/api/marketing/dashboard/overview?${params.toString()}`, { headers }),
        fetch(`${API_BASE}/api/marketing/accounts?status=active`, { headers }),
      ]);

      let overviewData = null;
      if (overviewRes.ok) {
        overviewData = await overviewRes.json();
        setOverview(overviewData);
      }
      const accs = accountsRes.ok ? await accountsRes.json() : [];
      setAccounts(accs);

      // Fetch sales trend per account (top 10)
      const accTrendMap = {};
      for (const acc of accs.slice(0, 10)) {
        const r = await fetch(
          `${API_BASE}/api/marketing/accounts/${acc.id}/sales?${params.toString()}`,
          { headers }
        );
        if (r.ok) {
          const list = await r.json();
          const map = {};
          list.forEach(item => {
            if (!map[item.date]) map[item.date] = { date: item.date, total: 0, live: 0 };
            const rev = item.metrics?.revenue || 0;
            if (item.revenue_type === 'live') map[item.date].live += rev;
            else map[item.date].total += rev;
          });
          accTrendMap[acc.id] = Object.values(map).sort((a, b) => a.date.localeCompare(b.date));
        }
      }
      setPerAccountTrend(accTrendMap);
    } catch (e) {
      toast.error('Gagal memuat dashboard');
    } finally {
      setLoading(false);
    }
  }, [period, headers]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Computed trend data berdasarkan filter akun
  const trendData = useMemo(() => {
    if (chartAccountFilter === 'all') {
      // Agregat semua akun
      const merged = {};
      Object.values(perAccountTrend).forEach(rows => {
        rows.forEach(row => {
          if (!merged[row.date]) merged[row.date] = { date: row.date, total: 0, live: 0 };
          merged[row.date].total += row.total;
          merged[row.date].live += row.live;
        });
      });
      return Object.values(merged).sort((a, b) => a.date.localeCompare(b.date));
    }
    return perAccountTrend[chartAccountFilter] || [];
  }, [perAccountTrend, chartAccountFilter]);

  // Average health score across active accounts — exclude null (N/A)
  const avgHealthScore = useMemo(() => {
    if (!accounts || accounts.length === 0) return null;
    const scored = accounts.filter(a => a.health_score !== null && a.health_score !== undefined);
    if (scored.length === 0) return null;
    const total = scored.reduce((sum, a) => sum + a.health_score, 0);
    return Math.round(total / scored.length);
  }, [accounts]);

  return (
    <div className="space-y-5" data-testid="marketing-dashboard">

      {/* ── Account Detail View ── */}
      {detailAccount && (
        <AccountDetailPage
          account={detailAccount}
          token={token}
          onBack={() => setDetailAccount(null)}
          onNavigate={onNavigate}
        />
      )}

      {/* ── Dashboard View ── */}
      {!detailAccount && (<>
      <PageHeader
        icon={Store}
        eyebrow="Portal Marketing · Ringkasan"
        title="Dashboard Marketing"
        subtitle="Satu layar untuk target, omzet, anggaran, dan kesehatan tiap toko (Shopee, TikTokShop, Tokopedia) — angka resmi bulanan diambil dari SSOT siklus marketing."
        actions={
          <Button onClick={fetchData} variant="outline" size="sm" data-testid="refresh-dashboard-btn">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
          </Button>
        }
      />

      {/* Angka RESMI satu bulan — dijumlah backend (SSOT siklus marketing) */}
      <MarketingCycleStrip token={token} period={cyclePeriod} />

      {/* Period Selector */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <PeriodSelector value={period} onChange={setPeriod} />
        <div className="flex items-center gap-2">
          <Button onClick={() => onNavigate?.('marketing-sales')} size="sm" data-testid="quick-input-sales">
            <Plus className="w-3.5 h-3.5 mr-1.5" /> Input Sales
          </Button>
          <Button onClick={() => onNavigate?.('marketing-task-hub')} size="sm" variant="outline" data-testid="quick-tasks">
            Buka Tugas
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : (
        <>
          {/* Summary KPIs */}
          {overview && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <GlassPanel className="p-5" data-testid="kpi-total-revenue">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs uppercase text-muted-foreground tracking-wider">Omzet Rentang Terpilih</div>
                  <TrendingUp className="w-4 h-4 text-primary" />
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground">
                  {fmtCompact(overview.summary?.total_revenue)}
                </div>
                <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                  <Tv2 className="w-3 h-3 text-pink-400" />
                  Live: {fmtCompact(overview.summary?.total_revenue_live)}
                </div>
              </GlassPanel>

              <GlassPanel className="p-5" data-testid="kpi-total-orders">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs uppercase text-muted-foreground tracking-wider">Jumlah Order</div>
                  <Package className="w-4 h-4 text-primary" />
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground">
                  {Number(overview.summary?.total_orders || 0).toLocaleString('id-ID')}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  AOV: {fmt(overview.summary?.avg_order_value)}
                </div>
              </GlassPanel>

              <GlassPanel className="p-5" data-testid="kpi-active-accounts">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs uppercase text-muted-foreground tracking-wider">Toko Aktif</div>
                  <Store className="w-4 h-4 text-primary" />
                </div>
                <div className="text-2xl font-bold tabular-nums text-foreground">
                  {overview.summary?.active_accounts || 0}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  dari {overview.summary?.total_accounts || 0} total akun
                </div>
              </GlassPanel>

              <GlassPanel className="p-5 bg-primary/5 border-primary/30" data-testid="kpi-top-account">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs uppercase text-primary tracking-wider">Toko Terbaik</div>
                  <BarChart3 className="w-4 h-4 text-primary" />
                </div>
                {overview.top_account ? (
                  <>
                    <div className="text-sm font-semibold text-foreground truncate">
                      {overview.top_account.account_name}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {fmtCompact(overview.top_account.revenue)}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">Belum ada data</div>
                )}
              </GlassPanel>
            </div>
          )}

          {/* Revenue Chart + Health Gauge */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <GlassCard className="p-5 lg:col-span-2" data-testid="revenue-trend-card">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h3 className="text-base font-semibold flex items-center gap-2">
                    <Activity className="w-4 h-4 text-primary" /> Tren Omzet
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Omzet total vs live per hari (rentang terpilih)</p>
                </div>
                <div className="flex items-center gap-2">
                  {/* Filter chart per akun */}
                  <Select value={chartAccountFilter} onValueChange={setChartAccountFilter}>
                    <SelectTrigger className="h-7 text-xs w-44" data-testid="chart-account-filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Semua Akun</SelectItem>
                      {accounts.map(a => (
                        <SelectItem key={a.id} value={a.id}>{a.account_name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400" /> Total</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-pink-400" /> Live</span>
                  </div>
                </div>
              </div>
              <RevenueChart data={trendData} height={280} />
            </GlassCard>

            <GlassCard className="p-5 flex flex-col items-center justify-center" data-testid="health-score-card">
              <h3 className="text-base font-semibold mb-1">Rata-rata Skor Kesehatan</h3>
              <p className="text-xs text-muted-foreground mb-4">Rata-rata semua toko aktif</p>
              <HealthScoreGauge score={avgHealthScore ?? 0} size={140} label="" />
              <div className="mt-4 w-full text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Sangat baik (≥80)</span>
                  <span className="text-emerald-400">{accounts.filter(a => a.health_score !== null && a.health_score !== undefined && a.health_score >= 80).length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Cukup (60-79)</span>
                  <span className="text-yellow-400">{accounts.filter(a => a.health_score !== null && a.health_score !== undefined && a.health_score >= 60 && a.health_score < 80).length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Perlu perbaikan</span>
                  <span className="text-red-400">{accounts.filter(a => a.health_score !== null && a.health_score !== undefined && a.health_score < 60).length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Belum ada data</span>
                  <span className="text-muted-foreground">{accounts.filter(a => a.health_score === null || a.health_score === undefined).length}</span>
                </div>
              </div>
            </GlassCard>
          </div>

          {/* Accounts Grid */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Akun Platform</h3>
                <p className="text-xs text-muted-foreground">Klik akun untuk dashboard detail</p>
              </div>
              <Button
                size="sm"
                onClick={() => onNavigate?.('marketing-accounts')}
                data-testid="manage-accounts-btn"
              >
                <Plus className="w-4 h-4 mr-2" /> Kelola Akun
              </Button>
            </div>

            {accounts.length === 0 ? (
              <GlassCard className="p-12 text-center">
                <Store className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground mb-4">Belum ada akun platform</p>
                <Button
                  size="sm"
                  onClick={() => onNavigate?.('marketing-accounts')}
                  data-testid="add-first-account"
                >
                  <Plus className="w-4 h-4 mr-2" /> Tambah Akun Pertama
                </Button>
              </GlassCard>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {accounts.map(account => (
                  <AccountCard
                    key={account.id}
                    account={account}
                    token={token}
                    onViewDetail={setDetailAccount}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
      </>)}
    </div>
  );
}
