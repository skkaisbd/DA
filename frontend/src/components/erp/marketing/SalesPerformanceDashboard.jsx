import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp, DollarSign, ShoppingBag, Package, RefreshCw, Loader2, Calendar, Store
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { AccountBadge, getPlatformConfig } from './AccountBadge';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) { return new Intl.NumberFormat('id-ID').format(n || 0); }
function fmtRp(n) { return `Rp ${fmt(n)}`; }

export default function SalesPerformanceDashboard({ token }) {
  const { toast } = useToast();
  const [overview, setOverview] = useState(null);
  const [topProducts, setTopProducts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [daysFilter, setDaysFilter] = useState(30);

  // Sync dengan active account context
  const { activeAccount } = useActiveMarketingAccount();
  
  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };

  // Fetch daftar akun untuk dropdown
  useEffect(() => {
    axios.get(`${API}/api/marketing/accounts?status=active`, { headers: authH })
      .then(r => setAccounts(Array.isArray(r.data) ? r.data : []))
      .catch(() => {});
  }, [token]); // eslint-disable-line

  // Jika ada active account dari context, pre-fill filter
  useEffect(() => {
    if (activeAccount && !accountFilter) {
      setAccountFilter(activeAccount.id);
    }
  }, [activeAccount]); // eslint-disable-line
  
  const fetchOverview = useCallback(async () => {
    setOverviewLoading(true);
    try {
      const params = {};
      if (startDate) params.start_date = new Date(startDate).toISOString();
      if (endDate) params.end_date = new Date(endDate).toISOString();
      if (platformFilter) params.platform = platformFilter;
      if (accountFilter) params.account_id = accountFilter;
      const res = await axios.get(`${API}/api/marketing/performance/overview`, { params, headers: authH });
      if (res.data.success) {
        setOverview(res.data.data);
      }
    } catch (e) {
      toast({ title: 'Gagal load performance', variant: 'destructive' });
    } finally {
      setOverviewLoading(false);
    }
  }, [startDate, endDate, platformFilter, accountFilter, token]); // eslint-disable-line
  
  const fetchTopProducts = useCallback(async () => {
    setLoading(true);
    try {
      const params = { days: daysFilter, limit: 10 };
      if (accountFilter) params.account_id = accountFilter;
      if (platformFilter) params.platform = platformFilter;
      const res = await axios.get(`${API}/api/marketing/performance/top-products`, {
        params,
        headers: authH
      });
      if (res.data.success) {
        setTopProducts(res.data.data.products || []);
      }
    } catch (e) {
      toast({ title: 'Gagal load top products', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [daysFilter, accountFilter, platformFilter, token]); // eslint-disable-line
  
  useEffect(() => { fetchOverview(); }, [fetchOverview]);
  useEffect(() => { fetchTopProducts(); }, [fetchTopProducts]);
  
  const kpis = [
    { label: 'Total Revenue', value: fmtRp(overview?.total_revenue), sub: `${fmt(overview?.total_orders || 0)} orders`, color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: DollarSign },
    { label: 'Total Orders', value: fmt(overview?.total_orders), sub: `${fmt(overview?.total_items || 0)} items`, color: 'text-indigo-600', bg: 'bg-indigo-50 dark:bg-indigo-900/20', icon: ShoppingBag },
    { label: 'AOV (Rata2 Order)', value: fmtRp(overview?.aov), sub: 'Average Order Value', color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-900/20', icon: TrendingUp },
    { label: 'Total Items', value: fmt(overview?.total_items), sub: 'Produk terjual', color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-900/20', icon: Package },
  ];
  
  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="sales-dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sales Performance</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Analisa performa penjualan dari semua platform
            {accountFilter && accounts.find(a => a.id === accountFilter) && (
              <span className="ml-2">
                — <AccountBadge account={accounts.find(a => a.id === accountFilter)} size="xs" />
              </span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { fetchOverview(); fetchTopProducts(); }}>
          <RefreshCw size={13} className="mr-1" /> Refresh
        </Button>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => (
          <div key={k.label} className={`rounded-xl border p-4 ${k.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              <k.icon size={15} className={k.color} />
            </div>
            <p className={`text-2xl font-bold tabular-nums ${k.color}`}>{overviewLoading ? '...' : (k.value || '0')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{overviewLoading ? '' : k.sub}</p>
          </div>
        ))}
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <CardTitle className="flex-1">Top 10 Produk Terlaris</CardTitle>
              <Select value={String(daysFilter)} onValueChange={v => setDaysFilter(Number(v))}>
                <SelectTrigger className="w-[120px] h-9 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 hari</SelectItem>
                  <SelectItem value="30">30 hari</SelectItem>
                  <SelectItem value="60">60 hari</SelectItem>
                  <SelectItem value="90">90 hari</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <Loader2 className="animate-spin text-muted-foreground" size={24} />
              </div>
            ) : topProducts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                <Package size={32} className="opacity-30 mb-2" />
                <p className="text-sm">Tidak ada data produk</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      {['#', 'Produk', 'Qty Terjual', 'Revenue', 'Orders'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {topProducts.map((p, i) => (
                      <tr key={i} className="hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                        <td className="px-3 py-2 font-medium max-w-[250px] truncate" title={p.product_name}>{p.product_name}</td>
                        <td className="px-3 py-2 tabular-nums font-bold text-primary">{fmt(p.total_qty)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtRp(p.total_revenue)}</td>
                        <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmt(p.order_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Filter</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Akun</label>
              <Select
                value={accountFilter || 'all'}
                onValueChange={v => setAccountFilter(v === 'all' ? '' : v)}
                data-testid="account-filter-select"
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Semua Akun" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">
                    <span className="flex items-center gap-1.5">
                      <Store size={12} className="text-muted-foreground" /> Semua Akun
                    </span>
                  </SelectItem>
                  {accounts.map(a => {
                    const cfg = getPlatformConfig(a.platform);
                    return (
                      <SelectItem key={a.id} value={a.id}>
                        <span className="flex items-center gap-1.5">
                          <span>{cfg.icon}</span>
                          <span className="truncate max-w-[160px]">{a.account_name}</span>
                        </span>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tanggal Mulai</label>
              <Input type="date" className="h-9 text-sm" value={startDate} onChange={e => setStartDate(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tanggal Akhir</label>
              <Input type="date" className="h-9 text-sm" value={endDate} onChange={e => setEndDate(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Platform</label>
              <Select value={platformFilter || 'all'} onValueChange={v => setPlatformFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Semua Platform" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Platform</SelectItem>
                  <SelectItem value="shopee">🛍️ Shopee</SelectItem>
                  <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                  <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button className="w-full" size="sm" onClick={() => { fetchOverview(); fetchTopProducts(); }}>
              <Calendar size={13} className="mr-1" /> Terapkan Filter
            </Button>
          </CardContent>
        </Card>
      </div>
      
      {overview?.by_platform && Object.keys(overview.by_platform).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Performa per Platform</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.entries(overview.by_platform).map(([platform, data]) => (
                <div key={platform} className="border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-2xl">{platform === 'shopee' ? '🛒' : platform === 'tiktok' ? '🎵' : '🟢'}</span>
                    <span className="font-semibold capitalize">{platform}</span>
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Revenue:</span>
                      <span className="font-bold">{fmtRp(data.revenue)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Orders:</span>
                      <span className="font-bold">{fmt(data.orders)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
