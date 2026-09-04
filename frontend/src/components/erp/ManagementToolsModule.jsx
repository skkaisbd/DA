import { useState, useEffect, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  FileText, Users, Shield, RefreshCw, Calendar, AlertCircle, Factory,
  TrendingUp, DollarSign, BarChart3, CheckCircle2, Clock, Activity
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const fmtRp = formatRupiah;

function WeeklyDigestTab() {
  const { toast } = useToast();
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const loadDigest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/management/weekly-digest?days=${days}`);
      setDigest(res.data);
    } catch (err) {
      toast({ title: 'Gagal memuat digest', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [days, toast]);

  useEffect(() => { loadDigest(); }, [loadDigest]);

  if (loading) return <div className="text-center py-8 text-muted-foreground"><RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" /></div>;
  if (!digest) return null;

  const healthColor = digest.health === 'good' ? 'text-green-600' : digest.health === 'warning' ? 'text-yellow-600' : 'text-red-600';
  const healthLabel = digest.health === 'good' ? '✅ Kondisi Baik' : digest.health === 'warning' ? '⚠️ Ada Perhatian' : '🚨 Perlu Tindakan';

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
          <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 hari</SelectItem>
            <SelectItem value="14">14 hari</SelectItem>
            <SelectItem value="30">30 hari</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={loadDigest} data-testid="mgmt-tools-digest-refresh"><RefreshCw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      </div>

      {/* Health Badge */}
      <div className="flex items-center gap-2">
        <Activity className="h-5 w-5" />
        <span className={`text-lg font-bold ${healthColor}`}>{healthLabel}</span>
        {digest.alert_count > 0 && (
          <Badge variant="destructive" className="ml-1">{digest.alert_count} alert</Badge>
        )}
      </div>

      {/* Sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Production */}
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Factory className="h-4 w-4 text-orange-500" />Produksi
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Work Order Baru</span>
              <span className="font-medium">{digest.production?.new_work_orders}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">WO Selesai</span>
              <span className="font-medium">{digest.production?.completed_work_orders}</span>
            </div>
          </CardContent>
        </Card>

        {/* Finance */}
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-green-500" />Keuangan
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Invoice Baru</span>
              <span className="font-medium">{digest.finance?.new_invoices}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total Invoice</span>
              <span className="font-medium">{fmtRp(digest.finance?.total_invoiced)}</span>
            </div>
          </CardContent>
        </Card>

        {/* Maklon */}
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-blue-500" />Maklon
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Order Baru</span>
              <span className="font-medium">{digest.maklon?.new_orders}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Order Selesai</span>
              <span className="font-medium">{digest.maklon?.completed_orders}</span>
            </div>
          </CardContent>
        </Card>

        {/* HR */}
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Users className="h-4 w-4 text-purple-500" />SDM
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Pengajuan Cuti</span>
              <span className="font-medium">{digest.hr?.leave_requests}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Isu Kehadiran</span>
              <span className="font-medium">{digest.hr?.attendance_issues}</span>
            </div>
          </CardContent>
        </Card>

        {/* Marketing */}
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-pink-500" />Marketing
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Sesi Live</span>
              <span className="font-medium">{digest.marketing?.live_sessions}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Revenue Live</span>
              <span className="font-medium">{fmtRp(digest.marketing?.live_revenue)}</span>
            </div>
          </CardContent>
        </Card>

        {/* Alerts */}
        <Card className={`border ${ digest.alert_count > 0 ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertCircle className={`h-4 w-4 ${digest.alert_count > 0 ? 'text-red-700 dark:text-red-500' : 'text-green-500'}`} />Alert Sistem
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Stok Rendah</span>
              <span className="font-medium">{digest.alerts?.low_stock_materials}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Rak &gt;90% Penuh</span>
              <span className="font-medium">{digest.alerts?.high_occupancy_racks}</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function PermissionAuditTab() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/management/audit/permissions?days=${days}`);
      setData(res.data);
    } catch (err) {
      toast({ title: 'Gagal memuat audit log', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [days, toast]);

  useEffect(() => { loadAudit(); }, [loadAudit]);

  const ROLE_COLORS = {
    superadmin: 'bg-red-100 text-red-700 border-red-200',
    admin: 'bg-orange-100 text-orange-700 border-orange-200',
    manager: 'bg-blue-100 text-blue-700 border-blue-200',
    supervisor: 'bg-purple-100 text-purple-700 border-purple-200',
    staff: 'bg-muted text-foreground border-border',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
          <SelectTrigger className="w-32 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 hari</SelectItem>
            <SelectItem value="30">30 hari</SelectItem>
            <SelectItem value="90">90 hari</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={loadAudit} data-testid="mgmt-tools-audit-refresh"><RefreshCw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      </div>

      {loading && <div className="text-center py-8"><RefreshCw className="h-6 w-6 animate-spin mx-auto" /></div>}
      {!loading && data && (
        <div className="space-y-5">
          {/* Permission Change Log */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Log Perubahan Role/Permission ({data.permission_changes?.length || 0})
            </p>
            {data.permission_changes?.length > 0 ? (
              <div className="space-y-2">
                {data.permission_changes.map((log, i) => (
                  <div key={i} className="p-3 rounded-lg border border-border text-sm">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{log.action} — {log.entity_type}</p>
                        <p className="text-xs text-muted-foreground">{log.user_name || log.user_id}</p>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {log.timestamp ? new Date(log.timestamp).toLocaleDateString('id-ID') : '-'}
                      </span>
                    </div>
                    {log.diff && Object.keys(log.diff).length > 0 && (
                      <div className="mt-2 text-xs bg-muted/50 p-2 rounded">
                        {Object.entries(log.diff).slice(0, 3).map(([k, v]) => (
                          <div key={k}><strong>{k}:</strong> {JSON.stringify(v.before)} → {JSON.stringify(v.after)}</div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-sm text-muted-foreground border-2 border-dashed border-border rounded-lg">
                Tidak ada perubahan permission dalam periode ini
              </div>
            )}
          </div>

          {/* Current User Roles */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Role Pengguna Aktif ({data.current_roles?.length || 0})
            </p>
            <div className="space-y-2">
              {(data.current_roles || []).slice(0, 20).map((u, i) => (
                <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg border border-border text-sm">
                  <div className="flex-1">
                    <p className="font-medium">{u.name || u.email}</p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </div>
                  <Badge className={`text-[10px] border ${ROLE_COLORS[u.role] || 'bg-muted text-muted-foreground'}`}>
                    {u.role}
                  </Badge>
                  {!u.is_active && <Badge variant="destructive" className="text-[10px]">Nonaktif</Badge>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ManagementToolsModule() {
  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-xl font-bold flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-slate-600 to-muted flex items-center justify-center">
            <BarChart3 className="h-4 w-4 text-foreground" />
          </div>
          Management Tools
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">Weekly Digest & Audit Log Permission</p>
      </div>
      <Tabs defaultValue="digest">
        <TabsList className="h-9">
          <TabsTrigger value="digest" className="text-xs" data-testid="mgmt-tools-tab-digest"><Calendar className="h-3.5 w-3.5 mr-1.5" />Weekly Digest</TabsTrigger>
          <TabsTrigger value="audit" className="text-xs" data-testid="mgmt-tools-tab-audit"><Shield className="h-3.5 w-3.5 mr-1.5" />Audit Permission</TabsTrigger>
        </TabsList>
        <TabsContent value="digest" className="mt-4"><WeeklyDigestTab /></TabsContent>
        <TabsContent value="audit" className="mt-4"><PermissionAuditTab /></TabsContent>
      </Tabs>
    </div>
  );
}
