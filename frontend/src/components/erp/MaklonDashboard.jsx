import { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Factory, Users, Package, TrendingUp, Clock, CheckCircle2, DollarSign, AlertTriangle, RefreshCw, Target, Calculator, XCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { useToast } from '@/hooks/use-toast';
import { PageHeader } from './moduleAtoms';
import { fetchMaklonOrders, posToLegacyOrders } from '@/lib/maklonOrderAdapter';
import apiFetch from '@/lib/apiFetch';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

// Panel alur produksi maklon (Rencana PO → Cutting → Vendor CMT → QC → Permak →
// Dispatch ke Buyer). Komponennya SAMA dengan Portal Produksi — hanya
// `businessType` yang berbeda, jadi tidak ada duplikasi logika/angka.
const ProductionDashboardOverview = lazy(() => import('./ProductionDashboardOverview'));

const STATUS_CONFIG = {
  draft:          { label: 'Draft',           color: 'bg-muted text-foreground border-border dark:bg-slate-500/15 dark:text-foreground/70 dark:border-slate-400/30' },
  confirmed:      { label: 'Dikonfirmasi',    color: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400/30' },
  material_ready: { label: 'Material Siap',   color: 'bg-cyan-100 text-cyan-700 border-cyan-300 dark:bg-cyan-500/15 dark:text-cyan-300 dark:border-cyan-400/30' },
  cutting:        { label: 'Cutting',         color: 'bg-violet-100 text-violet-700 border-violet-300 dark:bg-violet-500/15 dark:text-violet-300 dark:border-violet-400/30' },
  sewing:         { label: 'Sewing',          color: 'bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-400/30' },
  qc:             { label: 'QC',              color: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/30' },
  packing:        { label: 'Packing',         color: 'bg-orange-100 text-orange-700 border-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-400/30' },
  completed:      { label: 'Selesai',         color: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-500/15 dark:text-green-300 dark:border-green-400/30' },
  invoiced:       { label: 'Ditagih',         color: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-400/30' },
  cancelled:      { label: 'Dibatalkan',      color: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-400/30' },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return <span className={`inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>{c.label}</span>;
}

export default function MaklonDashboard({ token, onNavigate, defaultTab }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const { toast: showToast } = useToast();

  const [summary, setSummary] = useState({});
  const [recentOrders, setRecentOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState(defaultTab || 'overview');

  // SLA tab states
  const [slaData, setSlaData] = useState(null);
  const [slaLoading, setSlaLoading] = useState(false);
  const [slaDays, setSlaDays] = useState(90);
  const [selectedClient, setSelectedClient] = useState(null);
  const [clientDetail, setClientDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Lead Time tab states
  const [leadTimeForm, setLeadTimeForm] = useState({
    garment_type: 'blouse',
    quantity: 100,
    complexity: 'medium',
    has_embroidery: false,
    has_special_material: false,
    rush_order: false,
  });
  const [leadTimeResult, setLeadTimeResult] = useState(null);
  const [leadTimeLoading, setLeadTimeLoading] = useState(false);

  useEffect(() => {
    if (defaultTab) {
      setActiveTab(defaultTab);
    }
    // Check for tab hint from redirect (Phase 3.3A)
    const tabHint = sessionStorage.getItem('maklon_dashboard_tab');
    if (tabHint) {
      setActiveTab(tabHint);
      sessionStorage.removeItem('maklon_dashboard_tab');
    }
  }, [defaultTab]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [sumR, ordersR] = await Promise.all([
        fetch('/api/dewi/maklon/summary', { headers }),
        fetch('/api/dewi/maklon/pos', { headers }),
      ]);
      if (sumR.ok) setSummary(await sumR.json());
      if (ordersR.ok) {
        const orderList = posToLegacyOrders(await ordersR.json());
        setRecentOrders(orderList.slice(0, 10));
      }
    } catch (e) {
      toast.error('Gagal memuat data dashboard');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // SLA Dashboard functions
  const loadSLADashboard = useCallback(async () => {
    setSlaLoading(true);
    try {
      const result = await apiFetch(`/maklon/sla/dashboard?days=${slaDays}`);
      setSlaData(result);
    } catch (err) {
      showToast({ title: 'Gagal memuat SLA Dashboard', variant: 'destructive' });
    } finally {
      setSlaLoading(false);
    }
  }, [slaDays, showToast]);

  const loadClientDetail = async (client) => {
    setSelectedClient(client);
    setLoadingDetail(true);
    try {
      const res = await apiFetch(`/maklon/sla/client/${client.client_id}?days=${slaDays}`);
      setClientDetail(res.data);
    } catch {
      setClientDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'sla') {
      loadSLADashboard();
    }
  }, [activeTab, loadSLADashboard]);

  // Lead Time Estimator function
  const handleLeadTimeEstimate = async () => {
    if (!leadTimeForm.garment_type || !leadTimeForm.quantity) {
      showToast({ title: 'Isi jenis garmen dan jumlah terlebih dahulu', variant: 'destructive' });
      return;
    }
    setLeadTimeLoading(true);
    try {
      const res = await apiFetch('/maklon/sla/lead-time/estimate', {
        method: 'POST',
        body: { ...leadTimeForm, quantity: parseInt(leadTimeForm.quantity) },
      });
      setLeadTimeResult(res.data);
    } catch (err) {
      showToast({ title: 'Gagal estimasi', description: err.message, variant: 'destructive' });
    } finally {
      setLeadTimeLoading(false);
    }
  };

  const stats = [
    { label: 'Total Klien',        value: summary.total_clients || 0,     icon: Users,         color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-400/20' },
    { label: 'Klien Aktif',        value: summary.active_clients || 0,    icon: CheckCircle2,  color: 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border-green-300 dark:border-green-400/20' },
    { label: 'Order Aktif',        value: summary.active_orders || 0,     icon: Clock,         color: 'text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border-amber-400/20' },
    { label: 'Order Selesai',      value: summary.completed_orders || 0,  icon: Package,       color: 'text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10 border-violet-400/20' },
    { label: 'Draft',              value: summary.draft_orders || 0,      icon: AlertTriangle, color: 'text-orange-400 bg-orange-500/10 border-orange-400/20' },
    { label: 'Dikonfirmasi',       value: summary.confirmed_orders || 0,  icon: CheckCircle2,  color: 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-500/10 border-cyan-400/20' },
    { label: 'Sedang Produksi',    value: summary.in_production || 0,     icon: Factory,       color: 'text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-500/10 border-pink-400/20' },
    { label: 'Total Revenue',      value: `Rp ${(summary.total_revenue || 0).toLocaleString('id-ID')}`, icon: DollarSign, color: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-300 dark:border-emerald-400/20' },
  ];


  const SLA_COLORS = {
    good: 'text-green-700 dark:text-green-600 bg-green-50 border-green-200 dark:text-green-400 dark:bg-green-500/10 dark:border-green-400/20',
    warning: 'text-yellow-600 bg-yellow-50 border-yellow-200 dark:text-yellow-400 dark:bg-yellow-500/10 dark:border-yellow-400/20',
    poor: 'text-red-700 dark:text-red-600 bg-red-50 border-red-200 dark:text-red-400 dark:bg-red-500/10 dark:border-red-400/20',
  };

  const PERIOD_OPTIONS = [
    { value: 30,  label: '30 hari' },
    { value: 60,  label: '60 hari' },
    { value: 90,  label: '90 hari' },
    { value: 180, label: '6 bulan' },
  ];

  const GARMENT_TYPES = ['shirt', 'blouse', 'dress', 'pants', 'skirt', 'jacket', 'coat', 'uniform', 'casual', 'formal', 'other'];

  const fmtPct = (n) => n != null ? `${n.toFixed(1)}%` : '-';
  const fmtRp = formatRupiah;


  // SLA dashboard data
  const slaItems = slaData?.data || [];
  const slaMeta = slaData?.metadata || {};

  const { page, setPage, totalPages, total, paged } = useClientPagination(recentOrders, 10);
  return (
    <div className="p-6 space-y-6" data-testid="maklon-dashboard">
      <PageHeader
        title="Dashboard Maklon"
        description="Ringkasan order maklon, klien aktif, performa produksi & monitoring SLA"
        icon={Factory}
        actions={
          <Button size="sm" onClick={fetchData} variant="outline" className="gap-2" data-testid="refresh-dashboard">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </Button>
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-4" data-testid="dashboard-tabs">
          <TabsTrigger value="overview" data-testid="tab-overview">
            <Package className="w-4 h-4 mr-2" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="alur" data-testid="tab-alur-produksi">
            <Factory className="w-4 h-4 mr-2" />
            Alur Produksi
          </TabsTrigger>
          <TabsTrigger value="sla" data-testid="tab-sla">
            <CheckCircle2 className="w-4 h-4 mr-2" />
            SLA per Klien
          </TabsTrigger>
          <TabsTrigger value="leadtime" data-testid="tab-leadtime">
            <Calculator className="w-4 h-4 mr-2" />
            Smart Lead Time
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: Overview Dashboard */}
        <TabsContent value="overview" className="space-y-6" data-testid="overview-content">
          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {stats.map((s, i) => (
              <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
                <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
                  <div className={`w-8 h-8 rounded-lg border ${s.color} flex items-center justify-center mb-2`}>
                    <s.icon className={`w-4 h-4 ${s.color.split(' ')[0]}`} />
                  </div>
                  <div className="text-2xl font-bold text-foreground">{s.value}</div>
                  <div className="text-xs text-foreground/50">{s.label}</div>
                </GlassCard>
              </motion.div>
            ))}
          </div>

          {/* Quick Actions */}
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-3">Quick Actions</h3>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onNavigate && onNavigate('maklon-clients')} className="gap-1.5" data-testid="btn-kelola-klien">
                <Users className="w-3.5 h-3.5" /> Kelola Klien
              </Button>
              <Button size="sm" onClick={() => onNavigate && onNavigate('maklon-po')} variant="outline" className="gap-1.5" data-testid="btn-kelola-order">
                <Package className="w-3.5 h-3.5" /> Kelola Order
              </Button>
            </div>
          </GlassCard>

          {/* Recent Orders */}
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-4">Order Terbaru</h3>
            {loading ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Memuat...</div>
            ) : recentOrders.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada order maklon</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-foreground/5 text-xs text-foreground/50">
                      <th className="pb-2 text-left">Order Code</th>
                      <th className="pb-2 text-left">Klien</th>
                      <th className="pb-2 text-left">Produk</th>
                      <th className="pb-2 text-center">Qty</th>
                      <th className="pb-2 text-right">Nilai Order</th>
                      <th className="pb-2 text-left">Deadline</th>
                      <th className="pb-2 text-center">Progress</th>
                      <th className="pb-2 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {paged.map((order) => (
                      <tr key={order.id} className="hover:bg-foreground/[0.03] transition-colors">
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/70">{order.order_code}</td>
                        <td className="py-2.5 pr-3 text-foreground">{order.client_name}</td>
                        <td className="py-2.5 pr-3">
                          <div className="font-medium text-foreground">{order.product_name}</div>
                          <div className="text-xs text-foreground/40">{order.product_category}</div>
                        </td>
                        <td className="py-2.5 pr-3 text-center font-bold">{order.qty_ordered}</td>
                        <td className="py-2.5 pr-3 text-right text-foreground/80">Rp {(order.total_value || 0).toLocaleString('id-ID')}</td>
                        <td className="py-2.5 pr-3 text-xs text-foreground/60">{order.deadline_date}</td>
                        <td className="py-2.5 pr-3 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <div className="w-16 h-1.5 bg-foreground/10 rounded-full overflow-hidden">
                              <div className="h-full bg-primary" style={{ width: `${order.progress_percentage || 0}%` }} />
                            </div>
                            <span className="text-xs text-foreground/50">{order.progress_percentage || 0}%</span>
                          </div>
                        </td>
                        <td className="py-2.5 pr-3"><StatusBadge status={order.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </div>
            )}
          </GlassCard>
        </TabsContent>

        {/* TAB 2: Alur Produksi (maklon) — sumber: GET /api/prod/dashboard?business_type=maklon.
            Label tahap terakhir otomatis menjadi "Dispatch ke Buyer" (bukan "Serah Terima FG"). */}
        <TabsContent value="alur" className="space-y-4" data-testid="alur-produksi-content">
          <Suspense fallback={
            <div className="flex items-center justify-center h-48">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
            </div>
          }>
            <ProductionDashboardOverview token={token} onNavigate={onNavigate} businessType="maklon" />
          </Suspense>
        </TabsContent>

        {/* TAB 3: SLA per Klien */}
        <TabsContent value="sla" className="space-y-4" data-testid="sla-content">
          {selectedClient && clientDetail ? (
            <div>
              <Button size="sm" variant="outline" onClick={() => { setSelectedClient(null); setClientDetail(null); }} className="mb-4" data-testid="btn-back-to-sla">
                ← Kembali ke Dashboard
              </Button>
              <div className="mb-4">
                <h3 className="text-lg font-bold">{clientDetail.client?.name}</h3>
                <p className="text-sm text-muted-foreground">{clientDetail.client?.code} · {clientDetail.client?.company}</p>
              </div>
              <div className="grid grid-cols-3 gap-3 mb-4">
                {[
                  { label: 'Total Order', value: clientDetail.summary?.total },
                  { label: 'Selesai', value: clientDetail.summary?.completed },
                  { label: 'On-Time Rate', value: fmtPct(clientDetail.summary?.on_time_rate) },
                ].map((m, i) => (
                  <Card key={i}><CardContent className="p-3 text-center"><p className="text-xs text-muted-foreground">{m.label}</p><p className="text-xl font-bold">{m.value ?? '-'}</p></CardContent></Card>
                ))}
              </div>
              <div className="space-y-2">
                {(clientDetail.orders || []).map((o, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-border text-sm">
                    <div className="flex-shrink-0">
                      {o.status === 'on_time' ? <CheckCircle2 className="h-4 w-4 text-green-700 dark:text-green-500" /> :
                       o.status === 'late' ? <XCircle className="h-4 w-4 text-red-700 dark:text-red-500" /> :
                       <Clock className="h-4 w-4 text-yellow-500" />}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium">{o.order_code} — {o.garment_type}</p>
                      <p className="text-xs text-muted-foreground">Deadline: {o.deadline_date ? new Date(o.deadline_date).toLocaleDateString('id-ID') : '-'}</p>
                    </div>
                    <Badge variant="outline" className="text-[10px]">{o.stage}</Badge>
                    {o.lead_days && <span className="text-xs text-muted-foreground">{o.lead_days}h</span>}
                  </div>
                ))}
                {!clientDetail.orders?.length && <div className="text-center py-6 text-sm text-muted-foreground">Belum ada order dalam periode ini</div>}
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <Select value={String(slaDays)} onValueChange={v => setSlaDays(Number(v))}>
                  <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PERIOD_OPTIONS.map(o => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Button size="sm" variant="outline" onClick={loadSLADashboard} disabled={slaLoading} data-testid="btn-refresh-sla">
                  <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${slaLoading ? 'animate-spin' : ''}`} />Refresh
                </Button>
              </div>

              {/* Overall Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                {[
                  { icon: Users,      label: 'Total Client',   value: slaMeta.total_clients || 0 },
                  { icon: TrendingUp, label: 'Total Order',     value: slaMeta.total_orders || 0 },
                  { icon: CheckCircle2,label: 'On-Time Rate',  value: fmtPct(slaMeta.overall_on_time_rate) },
                  { icon: Clock,      label: 'Avg Lead Days',  value: slaMeta.overall_avg_lead_days ? `${slaMeta.overall_avg_lead_days}h` : '-' },
                ].map((m, i) => (
                  <Card key={i} className="border border-border">
                    <CardContent className="p-3 flex items-center gap-2">
                      <m.icon className="h-5 w-5 text-primary" />
                      <div><p className="text-[11px] text-muted-foreground">{m.label}</p><p className="text-sm font-bold">{m.value}</p></div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Clients List */}
              {slaLoading ? (
                <div className="text-center py-8 text-muted-foreground"><RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" /></div>
              ) : slaItems.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Users className="h-10 w-10 mx-auto mb-2 opacity-20" />
                  <p className="text-sm">Belum ada data order dalam periode ini</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {slaItems.map((client, i) => (
                    <button
                      key={i}
                      onClick={() => loadClientDetail(client)}
                      className="w-full text-left p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                      data-testid={`sla-client-${i}`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="font-medium text-sm">{client.client_name}</p>
                            <Badge className={`text-[10px] border ${SLA_COLORS[client.sla_status]}`}>
                              {client.sla_status === 'good' ? '✅ Good' : client.sla_status === 'warning' ? '⚠️ Warning' : '🚨 Poor'}
                            </Badge>
                          </div>
                          <div className="flex gap-4 text-xs text-muted-foreground">
                            <span>Orders: {client.total_orders}</span>
                            <span>Selesai: {client.completed_orders}</span>
                            <span>Tepat waktu: {client.on_time}</span>
                            <span>Terlambat: {client.late}</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-bold">{fmtPct(client.on_time_rate)}</p>
                          <p className="text-xs text-muted-foreground">Avg {client.avg_lead_days || '-'}h</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </TabsContent>

        {/* TAB 3: Smart Lead Time Estimator */}
        <TabsContent value="leadtime" className="space-y-4" data-testid="leadtime-content">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Calculator className="h-4 w-4 text-blue-500" />Input Parameter
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Jenis Garmen</Label>
                    <Select value={leadTimeForm.garment_type} onValueChange={v => setLeadTimeForm(p => ({...p, garment_type: v}))}>
                      <SelectTrigger className="mt-1 h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {GARMENT_TYPES.map(g => <SelectItem key={g} value={g} className="capitalize">{g}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-xs">Jumlah (pcs)</Label>
                    <Input className="mt-1 h-9" type="number" min="1" value={leadTimeForm.quantity} onChange={e => setLeadTimeForm(p => ({...p, quantity: e.target.value}))} />
                  </div>
                </div>

                <div>
                  <Label className="text-xs">Kompleksitas</Label>
                  <Select value={leadTimeForm.complexity} onValueChange={v => setLeadTimeForm(p => ({...p, complexity: v}))}>
                    <SelectTrigger className="mt-1 h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="simple">Simple (jahitan dasar)</SelectItem>
                      <SelectItem value="medium">Medium (standar)</SelectItem>
                      <SelectItem value="complex">Complex (detil tinggi)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  {[
                    { key: 'has_embroidery', label: 'Ada bordir/sulam' },
                    { key: 'has_special_material', label: 'Bahan khusus/impor' },
                    { key: 'rush_order', label: 'Rush order (percepatan)' },
                  ].map(opt => (
                    <div key={opt.key} className="flex items-center gap-2">
                      <Checkbox
                        id={opt.key}
                        checked={leadTimeForm[opt.key]}
                        onCheckedChange={v => setLeadTimeForm(p => ({...p, [opt.key]: v}))}
                      />
                      <Label htmlFor={opt.key} className="text-sm cursor-pointer">{opt.label}</Label>
                    </div>
                  ))}
                </div>

                <Button className="w-full" onClick={handleLeadTimeEstimate} disabled={leadTimeLoading} data-testid="btn-estimate-leadtime">
                  {leadTimeLoading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Menghitung...</> : <><Calculator className="h-4 w-4 mr-2" />Hitung Estimasi</>}
                </Button>
              </CardContent>
            </Card>

            <Card className="border border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="h-4 w-4 text-green-700 dark:text-green-500" />Hasil Estimasi
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!leadTimeResult && !leadTimeLoading && (
                  <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                    <Calculator className="h-10 w-10 mb-3 opacity-20" />
                    <p className="text-sm">Isi form dan klik Hitung Estimasi</p>
                  </div>
                )}
                {leadTimeResult && (
                  <div className="space-y-4">
                    <div className="text-center p-4 bg-primary/10 rounded-lg">
                      <p className="text-4xl font-bold text-primary">{leadTimeResult.estimated_days} hari</p>
                      <p className="text-sm text-muted-foreground mt-1">Target selesai: {leadTimeResult.target_delivery_date}</p>
                    </div>
                    {leadTimeResult.recommendation && (
                      <div className="p-3 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-400/20 rounded-lg text-sm text-yellow-800 dark:text-yellow-400">
                        {leadTimeResult.recommendation}
                      </div>
                    )}
                    <div className="space-y-1.5">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Breakdown</p>
                      {[
                        { label: 'Base hari', value: leadTimeResult.breakdown?.base_days },
                        { label: 'Multiplier kompleksitas', value: `×${leadTimeResult.breakdown?.complexity_mult}` },
                        { label: 'Faktor qty', value: `+${leadTimeResult.breakdown?.qty_factor_pct}%` },
                        { label: 'Faktor workload', value: `+${leadTimeResult.breakdown?.workload_factor_pct}%` },
                        { label: 'Order aktif saat ini', value: leadTimeResult.breakdown?.active_orders_now },
                        leadTimeResult.breakdown?.embroidery_days > 0 && { label: 'Bordir', value: `+${leadTimeResult.breakdown.embroidery_days}h` },
                        leadTimeResult.breakdown?.special_material_days > 0 && { label: 'Bahan khusus', value: `+${leadTimeResult.breakdown.special_material_days}h` },
                        leadTimeResult.breakdown?.rush_discount_days > 0 && { label: 'Rush discount', value: `-${leadTimeResult.breakdown.rush_discount_days}h` },
                      ].filter(Boolean).map((row, i) => (
                        <div key={i} className="flex justify-between text-sm py-1 border-b border-border last:border-0">
                          <span className="text-muted-foreground">{row.label}</span>
                          <span className="font-medium">{row.value}</span>
                        </div>
                      ))}
                    </div>
                    {leadTimeResult.historical_avg_days && (
                      <div className="text-xs text-muted-foreground text-center">
                        Rata-rata historis: <strong>{leadTimeResult.historical_avg_days} hari</strong> dari {leadTimeResult.historical_sample_size} order
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
