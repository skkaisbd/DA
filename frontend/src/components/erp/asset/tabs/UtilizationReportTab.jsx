/**
 * UtilizationReportTab — Asset Utilization Report (Session 28)
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 *
 * Self-contained: only depends on props (token, categories) + helper modules.
 */
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import {
  Package, RefreshCw, AlertTriangle, User, Download,
  Gauge, TrendingUp, Zap,
} from 'lucide-react';
import { apicall, fmtCurrency, fmtDate, API } from '../utils';
import { KPICard } from '../components/KPICard';

export function UtilizationReportTab({ token, categories }) {
  // Default: last 90 days
  const today = new Date().toISOString().slice(0, 10);
  const ninetyDaysAgo = new Date(Date.now() - 90 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(ninetyDaysAgo);
  const [dateTo, setDateTo] = useState(today);
  const [categoryId, setCategoryId] = useState('all');
  const [threshold, setThreshold] = useState(30);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('top'); // top | underutilized | idle

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
        underutilized_threshold: String(threshold),
        limit: '100',
      });
      if (categoryId && categoryId !== 'all') params.append('category_id', categoryId);
      const data = await apicall('GET', `/api/assets/reports/utilization?${params}`, token);
      setReport(data);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat utilization report');
    } finally {
      setLoading(false);
    }
  }, [token, dateFrom, dateTo, categoryId, threshold]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const exportCsv = async () => {
    try {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
        underutilized_threshold: String(threshold),
      });
      if (categoryId && categoryId !== 'all') params.append('category_id', categoryId);
      const res = await fetch(`${API}/api/assets/reports/utilization/export.csv?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Export gagal (${res.status})`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `asset_utilization_${dateFrom}_to_${dateTo}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('CSV berhasil diunduh');
    } catch (e) {
      toast.error(e.message || 'Export gagal');
    }
  };

  const summary = report?.summary || {};
  const detailRows = (
    view === 'top' ? report?.top_utilized :
    view === 'underutilized' ? report?.underutilized :
    report?.idle_assets
  ) || [];

  return (
    <div className="space-y-4" data-testid="utilization-report-tab">
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tanggal Mulai</label>
              <Input
                type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                data-testid="util-filter-date-from" className="h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Tanggal Akhir</label>
              <Input
                type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                data-testid="util-filter-date-to" className="h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Kategori</label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger className="h-9" data-testid="util-filter-category">
                  <SelectValue placeholder="Semua kategori" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua kategori</SelectItem>
                  {(categories || []).map(c => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">
                Underutil &lt; (%)
              </label>
              <Input
                type="number" min="0" max="100"
                value={threshold} onChange={e => setThreshold(parseInt(e.target.value || '0', 10))}
                data-testid="util-filter-threshold" className="h-9"
              />
            </div>
            <div className="flex items-end gap-2">
              <Button
                onClick={load} disabled={loading}
                data-testid="util-apply-button"
                className="h-9 flex-1"
              >
                <RefreshCw size={14} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Memuat...' : 'Terapkan'}
              </Button>
              <Button
                variant="outline" onClick={exportCsv}
                data-testid="util-export-csv-button" className="h-9"
              >
                <Download size={14} className="mr-1" /> CSV
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPICard
          label="Total Aset Dievaluasi" value={summary.total_assets || 0}
          icon={Package} accent="blue"
          sub={`${summary.assets_in_use_today || 0} sedang dipakai hari ini`}
        />
        <KPICard
          label="Rata-Rata Utilization" value={`${summary.avg_utilization_pct || 0}%`}
          icon={Gauge} accent="emerald"
          sub={`${summary.fully_utilized_count || 0} aset ≥95% (full)`}
        />
        <KPICard
          label="Underutilized" value={summary.underutilized_count || 0}
          icon={AlertTriangle} accent="amber"
          sub={`< ${threshold}% utilization`}
        />
        <KPICard
          label="Idle Total" value={summary.idle_in_window_count || 0}
          icon={Zap} accent="violet"
          sub={`${fmtCurrency(summary.underutilized_value_at_risk || 0)} nilai berisiko`}
        />
      </div>

      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-1.5">
                <TrendingUp size={14} className="text-emerald-500" />
                Per Kategori
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.by_category.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">Tidak ada data</p>
              ) : (
                <div className="space-y-2.5">
                  {report.by_category.map(c => (
                    <div key={c.category_id} data-testid={`util-cat-${c.category_id}`}>
                      <div className="flex items-center justify-between mb-1 text-xs">
                        <span className="font-medium">{c.category_name}</span>
                        <span className="text-muted-foreground">
                          {c.asset_count} aset · {c.avg_utilization_pct}%
                        </span>
                      </div>
                      <Progress value={c.avg_utilization_pct} className="h-1.5" />
                      <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
                        <span>Underutil: <b>{c.underutilized_count}</b></span>
                        <span>Idle: <b>{c.idle_count}</b></span>
                        <span>Cost: <b>{fmtCurrency(c.total_purchase_cost)}</b></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-1.5">
                <User size={14} className="text-blue-500" />
                Top Pemegang Aset
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.by_assignee.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">
                  Belum ada penugasan dalam periode ini
                </p>
              ) : (
                <div className="space-y-2">
                  {report.by_assignee.slice(0, 8).map(a => (
                    <div
                      key={a.assignee_id}
                      data-testid={`util-assignee-${a.assignee_id}`}
                      className="flex items-center justify-between text-xs py-1.5 px-2 rounded hover:bg-muted/50"
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-600 flex items-center justify-center font-semibold text-[10px]">
                          {(a.assignee_name || '?').slice(0, 2).toUpperCase()}
                        </div>
                        <span className="font-medium">{a.assignee_name}</span>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{a.unique_assets} aset</p>
                        <p className="text-[10px] text-muted-foreground">{a.total_assigned_days} hari</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Daftar Aset</CardTitle>
            <div className="flex items-center gap-1">
              <Button
                size="sm" variant={view === 'top' ? 'default' : 'outline'}
                onClick={() => setView('top')} className="h-7 text-xs"
                data-testid="util-view-top"
              >
                Top Utilized
              </Button>
              <Button
                size="sm" variant={view === 'underutilized' ? 'default' : 'outline'}
                onClick={() => setView('underutilized')} className="h-7 text-xs"
                data-testid="util-view-underutilized"
              >
                Underutilized
                {summary.underutilized_count > 0 && (
                  <Badge className="ml-1.5 text-[10px] h-4 px-1 bg-amber-500">
                    {summary.underutilized_count}
                  </Badge>
                )}
              </Button>
              <Button
                size="sm" variant={view === 'idle' ? 'default' : 'outline'}
                onClick={() => setView('idle')} className="h-7 text-xs"
                data-testid="util-view-idle"
              >
                Idle
                {summary.idle_in_window_count > 0 && (
                  <Badge className="ml-1.5 text-[10px] h-4 px-1 bg-violet-500">
                    {summary.idle_in_window_count}
                  </Badge>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {detailRows.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm" data-testid="util-empty-detail">
              Tidak ada aset dalam kategori ini
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground border-b">
                    <th className="py-2 px-2">Aset</th>
                    <th className="py-2 px-2">Kategori</th>
                    <th className="py-2 px-2 text-right">Utilization</th>
                    <th className="py-2 px-2 text-right">Hari Aktif</th>
                    <th className="py-2 px-2">Assignee</th>
                    <th className="py-2 px-2">Last Activity</th>
                    <th className="py-2 px-2 text-right">Nilai</th>
                  </tr>
                </thead>
                <tbody>
                  {detailRows.map(r => (
                    <tr
                      key={r.asset_id}
                      data-testid={`util-row-${r.asset_id}`}
                      className="border-b last:border-b-0 hover:bg-muted/30"
                    >
                      <td className="py-2 px-2">
                        <p className="font-medium">{r.asset_name}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{r.asset_number}</p>
                      </td>
                      <td className="py-2 px-2">{r.category_name || '—'}</td>
                      <td className="py-2 px-2 text-right">
                        <span
                          className={`font-semibold ${
                            r.utilization_pct >= 80 ? 'text-emerald-600' :
                            r.utilization_pct >= 40 ? 'text-blue-600' :
                            r.utilization_pct > 0 ? 'text-amber-600' : 'text-red-600'
                          }`}
                        >
                          {r.utilization_pct}%
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right">
                        {r.assigned_days} / {r.effective_window_days}
                      </td>
                      <td className="py-2 px-2">{r.current_assignee || <span className="text-muted-foreground">—</span>}</td>
                      <td className="py-2 px-2 text-muted-foreground text-[11px]">
                        {r.last_assigned_date ? fmtDate(r.last_assigned_date) : '—'}
                      </td>
                      <td className="py-2 px-2 text-right">{fmtCurrency(r.purchase_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
