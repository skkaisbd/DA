/**
 * PredictiveMaintenanceTab — Predictive Maintenance Alerts (Session 28)
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 *
 * Self-contained: only depends on props (token, categories) + helper modules.
 */
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import {
  CheckCircle2, Clock, AlertTriangle, AlertCircle, Activity, Gauge, TrendingUp,
} from 'lucide-react';
import { apicall } from '../utils';
import { KPICard } from '../components/KPICard';
import { PMAlertCard } from '../components/PMAlertCard';

export function PredictiveMaintenanceTab({ token, categories }) {
  const [config, setConfig] = useState({
    upcoming_window_days: 30,
    stale_months: 6,
    high_frequency_window_days: 90,
    high_frequency_threshold: 3,
    category_id: 'all',
  });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all'); // all | overdue | upcoming | stale | high_frequency | predicted
  const [ackBusy, setAckBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        upcoming_window_days: String(config.upcoming_window_days),
        stale_months: String(config.stale_months),
        high_frequency_window_days: String(config.high_frequency_window_days),
        high_frequency_threshold: String(config.high_frequency_threshold),
      });
      if (config.category_id && config.category_id !== 'all') params.append('category_id', config.category_id);
      const data = await apicall('GET', `/api/assets/predictive-maintenance/alerts?${params}`, token);
      setReport(data);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat alerts');
    } finally {
      setLoading(false);
    }
  }, [token, config]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const acknowledge = async (alert) => {
    setAckBusy(true);
    try {
      await apicall('POST', '/api/assets/predictive-maintenance/acknowledge', token, {
        asset_id: alert.asset_id,
        alert_kind: alert.kind,
        note: '',
      });
      toast.success(`Alert "${alert.asset_name}" di-snooze 30 hari`);
      await load();
    } catch (e) {
      toast.error(e.message || 'Gagal snooze');
    } finally {
      setAckBusy(false);
    }
  };

  const summary = report?.summary || {};

  const sections = [
    { kind: 'overdue', title: 'Overdue', list: report?.overdue || [], icon: AlertTriangle, color: 'text-red-500' },
    { kind: 'high_frequency', title: 'High Frequency', list: report?.high_frequency || [], icon: TrendingUp, color: 'text-rose-500' },
    { kind: 'upcoming', title: 'Upcoming', list: report?.upcoming || [], icon: Clock, color: 'text-amber-500' },
    { kind: 'predicted', title: 'Predicted', list: report?.predicted || [], icon: Gauge, color: 'text-blue-500' },
    { kind: 'stale', title: 'Stale (No Recent Maintenance)', list: report?.stale || [], icon: Activity, color: 'text-violet-500' },
  ];

  const visible = filter === 'all' ? sections : sections.filter(s => s.kind === filter);

  return (
    <div className="space-y-4" data-testid="pm-alerts-tab">
      {/* Config Bar */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Upcoming Window</label>
              <Input
                type="number" min="1" max="365"
                value={config.upcoming_window_days}
                onChange={e => setConfig(p => ({ ...p, upcoming_window_days: parseInt(e.target.value || '30', 10) }))}
                data-testid="pm-config-upcoming-days"
                className="h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Stale (bulan)</label>
              <Input
                type="number" min="1" max="36"
                value={config.stale_months}
                onChange={e => setConfig(p => ({ ...p, stale_months: parseInt(e.target.value || '6', 10) }))}
                data-testid="pm-config-stale-months"
                className="h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">High Freq Window</label>
              <Input
                type="number" min="7" max="365"
                value={config.high_frequency_window_days}
                onChange={e => setConfig(p => ({ ...p, high_frequency_window_days: parseInt(e.target.value || '90', 10) }))}
                data-testid="pm-config-hf-days"
                className="h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">High Freq Threshold</label>
              <Input
                type="number" min="2" max="20"
                value={config.high_frequency_threshold}
                onChange={e => setConfig(p => ({ ...p, high_frequency_threshold: parseInt(e.target.value || '3', 10) }))}
                data-testid="pm-config-hf-threshold"
                className="h-9"
              />
            </div>
            <div className="flex items-end">
              <Button
                onClick={load} disabled={loading}
                data-testid="pm-apply-button"
                className="h-9 w-full"
              >
                <AlertCircle size={14} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Memuat...' : 'Terapkan'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary KPI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KPICard
          label="Critical" value={summary.critical_count || 0}
          icon={AlertTriangle} accent="violet"
          sub="Memerlukan tindakan segera"
        />
        <KPICard
          label="Overdue" value={summary.overdue_count || 0}
          icon={AlertCircle} accent="amber"
        />
        <KPICard
          label="Upcoming" value={summary.upcoming_count || 0}
          icon={Clock} accent="blue"
        />
        <KPICard
          label="Stale + Predicted" value={(summary.stale_count || 0) + (summary.predicted_count || 0)}
          icon={Activity} accent="emerald"
        />
        <KPICard
          label="High Frequency" value={summary.high_frequency_count || 0}
          icon={TrendingUp} accent="violet"
          sub="Pola maintenance abnormal"
        />
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-1.5 flex-wrap" data-testid="pm-filter-pills">
        <Button
          size="sm" variant={filter === 'all' ? 'default' : 'outline'}
          onClick={() => setFilter('all')} className="h-7 text-xs"
          data-testid="pm-filter-all"
        >
          Semua ({summary.total_alerts || 0})
        </Button>
        {sections.map(s => (
          <Button
            key={s.kind}
            size="sm" variant={filter === s.kind ? 'default' : 'outline'}
            onClick={() => setFilter(s.kind)}
            disabled={s.list.length === 0}
            className="h-7 text-xs"
            data-testid={`pm-filter-${s.kind}`}
          >
            {s.title} ({s.list.length})
          </Button>
        ))}
      </div>

      {/* Sections */}
      {summary.total_alerts === 0 && !loading && (
        <Card data-testid="pm-empty-state">
          <CardContent className="py-12 text-center">
            <CheckCircle2 size={48} className="mx-auto text-emerald-500 mb-3" />
            <p className="text-base font-semibold">Tidak ada alert maintenance</p>
            <p className="text-xs text-muted-foreground mt-1">
              Semua aset dalam kondisi terkontrol berdasarkan parameter yang diatur.
            </p>
          </CardContent>
        </Card>
      )}

      {visible.map(s => {
        if (s.list.length === 0) return null;
        const Icon = s.icon;
        return (
          <Card key={s.kind} data-testid={`pm-section-${s.kind}`}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Icon size={15} className={s.color} />
                {s.title}
                <Badge className="text-[10px] h-4 px-1.5">{s.list.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {s.list.slice(0, 20).map(a => (
                <PMAlertCard
                  key={`${a.kind}-${a.asset_id}`}
                  alert={a}
                  ackBusy={ackBusy}
                  onAcknowledge={acknowledge}
                />
              ))}
              {s.list.length > 20 && (
                <p className="text-xs text-center text-muted-foreground mt-1">
                  ... dan {s.list.length - 20} alert lainnya
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
