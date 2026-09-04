import { useState, useEffect, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { CheckCircle2, XCircle, Clock, TrendingUp, Users, RefreshCw, Calculator, AlertTriangle, Target } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const SLA_COLORS = {
  good: 'text-green-600 bg-green-50 border-green-200',
  warning: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  poor: 'text-red-600 bg-red-50 border-red-200',
};

const fmtPct = (n) => n != null ? `${n.toFixed(1)}%` : '-';
const fmtRp = formatRupiah;

const PERIOD_OPTIONS = [
  { value: 30,  label: '30 hari' },
  { value: 60,  label: '60 hari' },
  { value: 90,  label: '90 hari' },
  { value: 180, label: '6 bulan' },
];

function SLADashboardTab() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(90);
  const [selectedClient, setSelectedClient] = useState(null);
  const [clientDetail, setClientDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiFetch(`/maklon/sla/dashboard?days=${days}`);
      setData(result);
    } catch (err) {
      toast({ title: 'Gagal memuat SLA Dashboard', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [days, toast]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  const loadClientDetail = async (client) => {
    setSelectedClient(client);
    setLoadingDetail(true);
    try {
      const res = await apiFetch(`/maklon/sla/client/${client.client_id}?days=${days}`);
      setClientDetail(res.data);
    } catch {
      setClientDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const items = data?.data || [];
  const meta = data?.metadata || {};

  if (selectedClient && clientDetail) {
    return (
      <div>
        <Button size="sm" variant="outline" onClick={() => { setSelectedClient(null); setClientDetail(null); }} className="mb-4">
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
                {o.status === 'on_time' ? <CheckCircle2 className="h-4 w-4 text-green-500" /> :
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
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
          <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PERIOD_OPTIONS.map(o => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={loadDashboard} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
        </Button>
      </div>

      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {[
          { icon: Users,      label: 'Total Client',   value: meta.total_clients || 0 },
          { icon: TrendingUp, label: 'Total Order',     value: meta.total_orders || 0 },
          { icon: CheckCircle2,label: 'On-Time Rate',  value: fmtPct(meta.overall_on_time_rate) },
          { icon: Clock,      label: 'Avg Lead Days',  value: meta.overall_avg_lead_days ? `${meta.overall_avg_lead_days}h` : '-' },
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
      {loading ? (
        <div className="text-center py-8 text-muted-foreground"><RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" /></div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Users className="h-10 w-10 mx-auto mb-2 opacity-20" />
          <p className="text-sm">Belum ada data order dalam periode ini</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((client, i) => (
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
  );
}

function LeadTimeTab() {
  const { toast } = useToast();
  const [form, setForm] = useState({
    garment_type: 'blouse',
    quantity: 100,
    complexity: 'medium',
    has_embroidery: false,
    has_special_material: false,
    rush_order: false,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const GARMENT_TYPES = ['shirt', 'blouse', 'dress', 'pants', 'skirt', 'jacket', 'coat', 'uniform', 'casual', 'formal', 'other'];

  const handleEstimate = async () => {
    if (!form.garment_type || !form.quantity) {
      toast({ title: 'Isi jenis garmen dan jumlah terlebih dahulu', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch('/maklon/sla/lead-time/estimate', {
        method: 'POST',
        body: { ...form, quantity: parseInt(form.quantity) },
      });
      setResult(res.data);
    } catch (err) {
      toast({ title: 'Gagal estimasi', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
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
              <Select value={form.garment_type} onValueChange={v => setForm(p => ({...p, garment_type: v}))}>
                <SelectTrigger className="mt-1 h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {GARMENT_TYPES.map(g => <SelectItem key={g} value={g} className="capitalize">{g}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Jumlah (pcs)</Label>
              <Input className="mt-1 h-9" type="number" min="1" value={form.quantity} onChange={e => setForm(p => ({...p, quantity: e.target.value}))} />
            </div>
          </div>

          <div>
            <Label className="text-xs">Kompleksitas</Label>
            <Select value={form.complexity} onValueChange={v => setForm(p => ({...p, complexity: v}))}>
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
                  checked={form[opt.key]}
                  onCheckedChange={v => setForm(p => ({...p, [opt.key]: v}))}
                />
                <Label htmlFor={opt.key} className="text-sm cursor-pointer">{opt.label}</Label>
              </div>
            ))}
          </div>

          <Button className="w-full" onClick={handleEstimate} disabled={loading}>
            {loading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Menghitung...</> : <><Calculator className="h-4 w-4 mr-2" />Hitung Estimasi</>}
          </Button>
        </CardContent>
      </Card>

      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Target className="h-4 w-4 text-green-500" />Hasil Estimasi
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!result && !loading && (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Calculator className="h-10 w-10 mb-3 opacity-20" />
              <p className="text-sm">Isi form dan klik Hitung Estimasi</p>
            </div>
          )}
          {result && (
            <div className="space-y-4">
              <div className="text-center p-4 bg-primary/10 rounded-lg">
                <p className="text-4xl font-bold text-primary">{result.estimated_days} hari</p>
                <p className="text-sm text-muted-foreground mt-1">Target selesai: {result.target_delivery_date}</p>
              </div>
              {result.recommendation && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                  {result.recommendation}
                </div>
              )}
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Breakdown</p>
                {[
                  { label: 'Base hari', value: result.breakdown?.base_days },
                  { label: 'Multiplier kompleksitas', value: `×${result.breakdown?.complexity_mult}` },
                  { label: 'Faktor qty', value: `+${result.breakdown?.qty_factor_pct}%` },
                  { label: 'Faktor workload', value: `+${result.breakdown?.workload_factor_pct}%` },
                  { label: 'Order aktif saat ini', value: result.breakdown?.active_orders_now },
                  result.breakdown?.embroidery_days > 0 && { label: 'Bordir', value: `+${result.breakdown.embroidery_days}h` },
                  result.breakdown?.special_material_days > 0 && { label: 'Bahan khusus', value: `+${result.breakdown.special_material_days}h` },
                  result.breakdown?.rush_discount_days > 0 && { label: 'Rush discount', value: `-${result.breakdown.rush_discount_days}h` },
                ].filter(Boolean).map((row, i) => (
                  <div key={i} className="flex justify-between text-sm py-1 border-b border-border last:border-0">
                    <span className="text-muted-foreground">{row.label}</span>
                    <span className="font-medium">{row.value}</span>
                  </div>
                ))}
              </div>
              {result.historical_avg_days && (
                <div className="text-xs text-muted-foreground text-center">
                  Rata-rata historis: <strong>{result.historical_avg_days} hari</strong> dari {result.historical_sample_size} order
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function MaklonSLADashboard() {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-teal-600 flex items-center justify-center">
              <Target className="h-4 w-4 text-foreground" />
            </div>
            SLA Dashboard & Lead Time
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">Monitoring on-time delivery per klien & kalkulator lead time</p>
        </div>
      </div>
      <Tabs defaultValue="sla">
        <TabsList className="h-9">
          <TabsTrigger value="sla" className="text-xs"><CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />SLA per Klien</TabsTrigger>
          <TabsTrigger value="leadtime" className="text-xs"><Calculator className="h-3.5 w-3.5 mr-1.5" />Smart Lead Time</TabsTrigger>
        </TabsList>
        <TabsContent value="sla" className="mt-4"><SLADashboardTab /></TabsContent>
        <TabsContent value="leadtime" className="mt-4"><LeadTimeTab /></TabsContent>
      </Tabs>
    </div>
  );
}
