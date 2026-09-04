import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  LayoutDashboard, ShoppingBag, MessageCircle, Tag, Rocket, Calendar,
  HeartPulse, BarChart3, Zap, RefreshCw, Loader2, AlertTriangle,
  CheckCircle2, Clock, XCircle, Plus, ArrowRight, Bell, TrendingUp
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import NoStoreScopeNotice from './NoStoreScopeNotice';

const API = process.env.REACT_APP_BACKEND_URL;

function fmtRp(n) {
  if (!n || n === 0) return 'Rp 0';
  if (n >= 1e9)  return `Rp ${(n/1e9).toFixed(1)}M`;
  if (n >= 1e6)  return `Rp ${(n/1e6).toFixed(1)}jt`;
  if (n >= 1e3)  return `Rp ${(n/1e3).toFixed(0)}rb`;
  return `Rp ${n}`;
}
function fmt(n) {
  // Nilai yang BELUM diketahui harus tampil sebagai '—'. `format('—')` memberi
  // "NaN" di kartu KPI — pembacanya menyimpulkan aplikasinya rusak.
  const v = Number(n);
  return Number.isFinite(v) ? new Intl.NumberFormat('id-ID').format(v) : '—';
}

// ── Mini stat cards ───────────────────────────────────────────────────────────────────
function ModuleCard({ icon: Icon, iconColor, bg, title, stats, onClick, quickActions }) {
  return (
    <Card className="hover:shadow-md transition-all duration-200 cursor-pointer group" onClick={onClick}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className={`p-2.5 rounded-xl ${bg}`}>
            <Icon size={20} className={iconColor} />
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity">
            <ArrowRight size={14} />
          </Button>
        </div>
        <h3 className="font-semibold text-sm mb-2">{title}</h3>
        <div className="grid grid-cols-2 gap-1">
          {stats.map(s => (
            <div key={s.label} className={`rounded-lg p-2 ${s.highlight ? 'bg-primary/5' : 'bg-muted/40'}`}>
              <p className={`text-base font-bold leading-tight ${s.valueColor || ''}`}>{s.value}</p>
              <p className="text-[11px] text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
        {quickActions && quickActions.length > 0 && (
          <div className="mt-3 pt-3 border-t flex flex-wrap gap-1">
            {quickActions.map(qa => (
              <button key={qa.label}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                onClick={e => { e.stopPropagation(); qa.onClick(); }}
              >
                <Plus size={10} />{qa.label}
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Alert item ───────────────────────────────────────────────────────────────────────
const SEVERITY_CONFIG = {
  error:   { bg: 'bg-red-50 dark:bg-red-900/20',    border: 'border-red-200 dark:border-red-800',   icon: AlertTriangle, iconColor: 'text-red-500' },
  warning: { bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', icon: Clock,          iconColor: 'text-amber-500' },
  info:    { bg: 'bg-blue-50 dark:bg-blue-900/20',   border: 'border-blue-200 dark:border-blue-800',  icon: Bell,           iconColor: 'text-blue-500' },
  success: { bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-800', icon: CheckCircle2, iconColor: 'text-emerald-500' },
};

function AlertItem({ alert, onNavigate }) {
  const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
  const Icon = cfg.icon;
  return (
    <div className={`flex gap-3 p-3 rounded-lg border ${cfg.bg} ${cfg.border}`}>
      <Icon size={16} className={`${cfg.iconColor} flex-shrink-0 mt-0.5`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold leading-tight">{alert.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{alert.message}</p>
      </div>
      {alert.link_module && (
        <button
          onClick={() => onNavigate(alert.link_module)}
          className="text-xs text-primary hover:underline flex-shrink-0 mt-0.5"
        >
          Lihat ›
        </button>
      )}
    </div>
  );
}


export default function MarketingOverviewDashboard({ token, onNavigate }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);

  const [loading,    setLoading]    = useState(true);
  const [alertsData, setAlertsData] = useState([]);
  const [alertsLoading, setAlertsLoading] = useState(false);

  // Module summaries
  const [orders,    setOrders]    = useState(null);
  const [complaints,setComplaints]= useState(null);
  const [health,    setHealth]    = useState(null);
  const [discounts, setDiscounts] = useState(null);
  const [launches,  setLaunches]  = useState(null);
  const [content,   setContent]   = useState(null);

  const nav = (moduleId) => { if (onNavigate) onNavigate(moduleId); };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4, r5, r6] = await Promise.allSettled([
        axios.get(`${API}/api/marketing/orders/summary`,      { headers: authH }),
        axios.get(`${API}/api/marketing/complaints/summary`,  { headers: authH }),
        axios.get(`${API}/api/marketing/health/summary`,      { headers: authH }),  // correct route
        axios.get(`${API}/api/marketing/discounts/summary`,   { headers: authH }),
        axios.get(`${API}/api/marketing/product-launches/summary`, { headers: authH }),
        axios.get(`${API}/api/marketing/content-calendar/summary`, { headers: authH }),
      ]);
      // Orders: flat response
      if (r1.status==='fulfilled') setOrders(r1.value.data);
      // Complaints: flat response
      if (r2.status==='fulfilled') setComplaints(r2.value.data);
      // Health: has data key
      if (r3.status==='fulfilled' && r3.value.data.success) setHealth(r3.value.data.data);
      // Discounts: has data key
      if (r4.status==='fulfilled' && r4.value.data.success) setDiscounts(r4.value.data.data);
      // Launches: has data key
      if (r5.status==='fulfilled' && r5.value.data.success) setLaunches(r5.value.data.data);
      // Content: has data key
      if (r6.status==='fulfilled' && r6.value.data.success) setContent(r6.value.data.data);
    } catch {}
    finally { setLoading(false); }
  }, [authH]);

  const fetchAlerts = useCallback(async () => {
    setAlertsLoading(true);
    try {
      const res = await axios.post(`${API}/api/marketing/alerts/preview`, {}, { headers: authH });
      if (res.data.success) setAlertsData(res.data.fired || []);
    } catch {}
    finally { setAlertsLoading(false); }
  }, [authH]);

  const triggerAlerts = async () => {
    try {
      const res = await axios.post(`${API}/api/marketing/alerts/evaluate`, {}, { headers: authH });
      toast({ title: `🔔 ${res.data.total_fired} alert dikirim` });
      fetchAlerts();
    } catch { toast({ title: 'Gagal trigger alerts', variant: 'destructive' }); }
  };

  useEffect(() => { fetchAll(); fetchAlerts(); }, [fetchAll, fetchAlerts]);

  const modules = [
    {
      icon: ShoppingBag, iconColor: 'text-indigo-600', bg: 'bg-indigo-50 dark:bg-indigo-900/20',
      title: 'Unified Orders',
      onClick: () => nav('marketing-orders'),
      stats: [
        { label: 'Total',       value: fmt(orders?.total_orders ?? '—') },
        { label: 'Perlu Aksi',  value: fmt(orders?.need_action  ?? '—'), valueColor: 'text-amber-600', highlight: (orders?.need_action||0) > 0 },
        { label: 'Delivered',   value: fmt(orders?.by_status?.delivered ?? '—'), valueColor: 'text-emerald-600' },
        { label: 'Revenue',     value: orders?.total_revenue ? fmtRp(orders.total_revenue) : '—', valueColor: 'text-indigo-600' },
      ],
      quickActions: [{ label: 'Lihat Picking List', onClick: () => nav('marketing-orders') }],
    },
    {
      icon: MessageCircle, iconColor: 'text-red-600', bg: 'bg-red-50 dark:bg-red-900/20',
      title: 'Kelola Komplain',
      onClick: () => nav('marketing-complaints'),
      stats: [
        { label: 'Total',     value: fmt(complaints?.total    ?? '—') },
        { label: 'Open',      value: fmt(complaints?.by_status?.open ?? '—'), valueColor: 'text-amber-600', highlight: true },
        { label: 'Overdue',   value: fmt(complaints?.overdue  ?? '—'), valueColor: 'text-red-600', highlight: (complaints?.overdue || 0) > 0 },
        { label: 'Resolved',  value: fmt(complaints?.resolved ?? '—'), valueColor: 'text-emerald-600' },
      ],
      quickActions: [
        { label: 'Tambah Komplain', onClick: () => nav('marketing-complaints') },
      ],
    },
    {
      icon: HeartPulse, iconColor: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20',
      title: 'Account Health',
      onClick: () => nav('marketing-health'),
      stats: [
        { label: 'Total Akun', value: fmt(health?.total_accounts ?? '—') },
        { label: 'Sehat',      value: fmt(health?.healthy        ?? '—'), valueColor: 'text-emerald-600', highlight: true },
        { label: 'Warning',    value: fmt(health?.warning        ?? '—'), valueColor: 'text-amber-600' },
        { label: 'Critical',   value: fmt(health?.critical       ?? '—'), valueColor: 'text-red-600', highlight: (health?.critical||0) > 0 },
      ],
      quickActions: [],
    },
    {
      icon: Tag, iconColor: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-900/20',
      title: 'Discount Campaigns',
      onClick: () => nav('marketing-discounts'),
      stats: [
        { label: 'Total',         value: fmt(discounts?.total        ?? '—') },
        { label: 'Aktif',         value: fmt(discounts?.active       ?? '—'), valueColor: 'text-emerald-600', highlight: true },
        { label: 'Akan Datang',   value: fmt(discounts?.upcoming     ?? '—'), valueColor: 'text-blue-600' },
        { label: 'Habis 3 Hari',  value: fmt(discounts?.expiring_soon ?? '—'), valueColor: (discounts?.expiring_soon || 0) > 0 ? 'text-amber-600' : '', highlight: (discounts?.expiring_soon || 0) > 0 },
      ],
      quickActions: [{ label: 'Buat Kampanye', onClick: () => nav('marketing-discounts') }],
    },
    {
      icon: Rocket, iconColor: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-900/20',
      title: 'Product Launch',
      onClick: () => nav('marketing-product-launches'),
      stats: [
        { label: 'Total',       value: fmt(launches?.total       ?? '—') },
        { label: 'Planning',    value: fmt(launches?.planning    ?? '—'), valueColor: 'text-muted-foreground/80' },
        { label: 'Siap Launch', value: fmt(launches?.ready       ?? '—'), valueColor: 'text-blue-600', highlight: true },
        { label: 'Launched',    value: fmt(launches?.launched    ?? '—'), valueColor: 'text-emerald-600' },
      ],
      quickActions: [
        { label: 'Tambah Produk', onClick: () => nav('marketing-product-launches') },
      ],
    },
    {
      icon: Calendar, iconColor: 'text-teal-600', bg: 'bg-teal-50 dark:bg-teal-900/20',
      title: 'Content Calendar',
      onClick: () => nav('marketing-content-calendar'),
      stats: [
        { label: 'Total',       value: fmt(content?.total     ?? '—') },
        { label: 'Draft',       value: fmt(content?.draft     ?? '—'), valueColor: 'text-muted-foreground/80' },
        { label: 'Terjadwal',   value: fmt(content?.scheduled ?? '—'), valueColor: 'text-blue-600', highlight: true },
        { label: 'Tayang',      value: fmt(content?.posted    ?? '—'), valueColor: 'text-emerald-600' },
      ],
      quickActions: [
        { label: 'Tambah Konten Hari Ini', onClick: () => nav('marketing-content-calendar') },
      ],
    },
  ];

  // Highlight counts for top banner
  const urgentCount = (
    (complaints?.overdue || 0) +
    (discounts?.expiring_soon || 0) +
    (launches?.ready || 0)
  );

  const urgentBannerParts = [
    complaints?.overdue > 0 && `${complaints.overdue} komplain overdue`,
    discounts?.expiring_soon > 0 && `${discounts.expiring_soon} kampanye akan habis`,
    launches?.ready > 0 && `${launches.ready} produk siap launch`,
  ].filter(Boolean);

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="marketing-overview-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <LayoutDashboard size={24} className="text-primary" />
            Marketing Overview
          </h1>
          <p className="text-sm text-muted-foreground">Ringkasan semua modul Portal Marketing</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchAll(); fetchAlerts(); }}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button size="sm" variant="outline" onClick={triggerAlerts}>
            <Bell size={14} className="mr-1" />Cek Alert
          </Button>
        </div>
      </div>

      {/* Staf berlingkup toko yang belum di-assign: nol yang MENJELASKAN dirinya */}
      <div className="mb-5">
        <NoStoreScopeNotice token={token} what="Semua angka di ringkasan ini" />
      </div>

      {/* Urgent Banner */}
      {urgentCount > 0 && (
        <div className="mb-5 p-3.5 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 flex items-center gap-3">
          <div className="p-2 rounded-full bg-amber-100 dark:bg-amber-900/40">
            <AlertTriangle size={16} className="text-amber-600" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
              {urgentCount} hal memerlukan perhatian segera
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {urgentBannerParts.join(' · ')}
            </p>
          </div>
        </div>
      )}

      {/* Module Cards Grid */}
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 size={32} className="animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {modules.map(m => <ModuleCard key={m.title} {...m} />)}
        </div>
      )}

      {/* Quick Actions Row */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Zap size={14} className="text-amber-500" />Quick Actions
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          <div className="flex flex-wrap gap-2">
            {[
              { label: '➕ Tambah Konten Hari Ini', onClick: () => nav('marketing-content-calendar'), color: 'bg-teal-50 text-teal-700 hover:bg-teal-100 dark:bg-teal-900/20 dark:text-teal-300' },
              { label: '🏷️ Buat Kampanye Diskon', onClick: () => nav('marketing-discounts'), color: 'bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-300' },
              { label: '🚀 Tambah Produk Launch', onClick: () => nav('marketing-product-launches'), color: 'bg-purple-50 text-purple-700 hover:bg-purple-100 dark:bg-purple-900/20 dark:text-purple-300' },
              { label: '⚠️ Cek Komplain Overdue', onClick: () => nav('marketing-complaints'), color: 'bg-red-50 text-red-700 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-300' },
              { label: '📊 Sales Performance', onClick: () => nav('marketing-performance'), color: 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-300' },
              { label: '📥 Import Data Baru', onClick: () => nav('marketing-import'), color: 'bg-muted text-foreground hover:bg-muted dark:bg-gray-900/20 dark:text-gray-300' },
            ].map(qa => (
              <button key={qa.label}
                className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium border border-transparent transition-colors ${qa.color}`}
                onClick={qa.onClick}
              >{qa.label}</button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Active Alerts Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bell size={14} className="text-primary" />Alert Aktif
                {alertsData.length > 0 && (
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-foreground text-xs font-bold">{alertsData.length}</span>
                )}
              </div>
              <button onClick={fetchAlerts} className="text-xs text-muted-foreground hover:text-primary">
                {alertsLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              </button>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2">
            {alertsLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={20} className="animate-spin text-muted-foreground" /></div>
            ) : alertsData.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-muted-foreground">
                <CheckCircle2 size={24} className="text-emerald-600 dark:text-emerald-400" />
                <p className="text-sm">Semua kondisi normal 🎉</p>
              </div>
            ) : (
              <div className="space-y-2">
                {alertsData.slice(0, 5).map((a, i) => (
                  <AlertItem key={i} alert={a} onNavigate={nav} />
                ))}
                {alertsData.length > 5 && (
                  <p className="text-xs text-center text-muted-foreground">+{alertsData.length - 5} alert lainnya</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp size={14} className="text-primary" />Status Module Sekilas
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2">
            <div className="space-y-2">
              {[
                { label: 'Orders aktif (new+packed+shipped)', value: fmt((orders?.by_status?.new||0) + (orders?.by_status?.packed||0) + (orders?.by_status?.shipped||0)), color: (orders?.need_action||0) > 0 ? 'text-amber-600' : 'text-emerald-600', onClick: () => nav('marketing-orders') },
                { label: 'Komplain belum selesai',            value: fmt(complaints?.by_status?.open || 0), color: (complaints?.by_status?.open || 0) > 0 ? 'text-red-600' : 'text-emerald-600', onClick: () => nav('marketing-complaints') },
                { label: 'Campaign diskon aktif',             value: fmt(discounts?.active || 0), color: 'text-emerald-600', onClick: () => nav('marketing-discounts') },
                { label: 'Produk siap launch',                value: fmt(launches?.ready || 0), color: (launches?.ready || 0) > 0 ? 'text-blue-600' : 'text-muted-foreground', onClick: () => nav('marketing-product-launches') },
                { label: 'Konten terjadwal',                  value: fmt(content?.scheduled || 0), color: (content?.scheduled || 0) > 0 ? 'text-teal-600' : 'text-muted-foreground', onClick: () => nav('marketing-content-calendar') },
                { label: 'Upcoming launches (30 hari)',       value: fmt(launches?.upcoming_30 || 0), color: 'text-purple-600', onClick: () => nav('marketing-product-launches') },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between py-1.5 border-b last:border-0 hover:bg-muted/30 px-1 rounded cursor-pointer transition-colors" onClick={row.onClick}>
                  <span className="text-xs text-muted-foreground">{row.label}</span>
                  <span className={`text-sm font-bold ${row.color}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
