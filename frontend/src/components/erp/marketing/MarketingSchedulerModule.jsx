import { useState, useEffect, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Play, RefreshCw, Clock, CheckCircle2, XCircle, Cpu, CalendarClock, Activity, Table2, LayoutGrid } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

// F10 (2026-08-13) — layar ini KARTU-SAJA. Untuk job terjadwal, yang dicari orang
// justru perbandingan baris: "job mana yang mati", "kapan jalan berikutnya",
// "run terakhir gagal atau tidak". Tabel dijadikan tampilan default; Kartu tetap ada.
const VIEW_KEY = 'marketing_scheduler_view';
const JOB_HEADS = ['Job', 'Jadwal (cron)', 'Status', 'Jalan berikutnya', 'Aksi'];
const RUN_HEADS = ['Waktu mulai', 'Job', 'Status', 'Galat'];
const fmtDT = (v) => (v ? new Date(v).toLocaleString('id-ID') : '—');

function StatusBadge({ enabled, running }) {
  if (running) return <Badge className="bg-green-100 text-green-700 border-green-200"><Activity className="h-3 w-3 mr-1" />Berjalan</Badge>;
  if (enabled) return <Badge className="bg-blue-100 text-blue-700 border-blue-200">Aktif</Badge>;
  return <Badge variant="secondary">Tidak Aktif</Badge>;
}

export default function MarketingSchedulerModule() {
  const { toast } = useToast();
  const [jobs, setJobs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [runningJob, setRunningJob] = useState(null);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'table'; } catch { return 'table'; }
  });

  useEffect(() => {
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, runsRes] = await Promise.all([
        apiFetch('/dewi/scheduler/jobs'),
        apiFetch('/dewi/scheduler/runs?limit=20'),
      ]);
      setJobs(jobsRes.jobs || []);
      setSchedulerRunning(jobsRes.scheduler_running || false);
      setRuns(Array.isArray(runsRes) ? runsRes : []);
    } catch (err) {
      toast({ title: 'Gagal memuat status scheduler', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadData(); }, [loadData]);

  const runNow = async (jobId, desc) => {
    setRunningJob(jobId);
    try {
      await apiFetch(`/dewi/scheduler/jobs/${jobId}/run-now`, { method: 'POST' });
      toast({ title: `Job "${desc}" berhasil dijalankan ✅` });
      await loadData();
    } catch (err) {
      toast({ title: 'Job gagal', description: err.message, variant: 'destructive' });
    } finally {
      setRunningJob(null);
    }
  };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center">
              <Cpu className="h-4 w-4 text-foreground" />
            </div>
            Scheduler & Otomasi
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">Status job terjadwal, task auto-creation, dan file cleanup</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge enabled running={schedulerRunning} />
          <div className="flex rounded-md border border-border overflow-hidden">
            <button type="button" onClick={() => setView('table')} data-testid="scheduler-view-table"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <Table2 size={12} /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')} data-testid="scheduler-view-grid"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <LayoutGrid size={12} /> Kartu
            </button>
          </div>
          <Button size="sm" variant="outline" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
          </Button>
        </div>
      </div>

      {/* Jobs List */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Registered Jobs ({jobs.length})</p>
        {loading ? (
          <div className="text-center py-8 text-sm text-muted-foreground"><RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" /></div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">Tidak ada job terdaftar</div>
        ) : view === 'table' ? (
          <div className="rounded-lg border border-border overflow-x-auto bg-background">
            <table className="w-full text-xs" data-testid="scheduler-jobs-table">
              <thead className="bg-muted/60"><tr>{JOB_HEADS.map((h) => (
                <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
              ))}</tr></thead>
              <tbody className="divide-y divide-border">
                {jobs.map(job => (
                  <tr key={job.id} className="hover:bg-muted/30" data-testid={`scheduler-row-${job.id}`}>
                    <td className="px-3 py-2">
                      <div className="font-medium text-foreground">{job.description}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">{job.id}</div>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{job.cron_label || '—'}</td>
                    <td className="px-3 py-2">
                      {job.enabled
                        ? <Badge className="text-[10px] bg-green-100 text-green-700 border-green-200">Aktif</Badge>
                        : <Badge variant="secondary" className="text-[10px]">Non-aktif</Badge>}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{fmtDT(job.next_run_at)}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="sm" variant="outline" onClick={() => runNow(job.id, job.description)}
                        disabled={runningJob === job.id} data-testid={`run-job-${job.id}`}>
                        {runningJob === job.id
                          ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                          : <><Play className="h-3.5 w-3.5 mr-1" />Run Now</>}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          jobs.map(job => (
            <Card key={job.id} className="border border-border">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <CalendarClock className="h-4 w-4 text-teal-500" />
                      <p className="font-medium text-sm">{job.description}</p>
                      <Badge variant="outline" className="text-[10px]">{job.cron_label}</Badge>
                      {job.enabled
                        ? <Badge className="text-[10px] bg-green-100 text-green-700 border-green-200">Aktif</Badge>
                        : <Badge variant="secondary" className="text-[10px]">Non-aktif</Badge>
                      }
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Next: {job.next_run_at ? new Date(job.next_run_at).toLocaleString('id-ID') : 'N/A'}
                      </span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => runNow(job.id, job.description)}
                    disabled={runningJob === job.id}
                    data-testid={`run-job-${job.id}`}
                  >
                    {runningJob === job.id
                      ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      : <><Play className="h-3.5 w-3.5 mr-1" />Run Now</>
                    }
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Recent Runs */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Run History Terakhir ({runs.length})</p>
        {runs.length === 0 && !loading && (
          <div className="text-center py-6 text-sm text-muted-foreground border-2 border-dashed border-border rounded-lg">
            Belum ada riwayat run
          </div>
        )}
        <div className="space-y-2">
          {view === 'table' && runs.length > 0 ? (
            <div className="rounded-lg border border-border overflow-x-auto bg-background">
              <table className="w-full text-xs" data-testid="scheduler-runs-table">
                <thead className="bg-muted/60"><tr>{RUN_HEADS.map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                ))}</tr></thead>
                <tbody className="divide-y divide-border">
                  {runs.map((run, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="px-3 py-2 whitespace-nowrap">{fmtDT(run.started_at)}</td>
                      <td className="px-3 py-2 font-mono text-[11px]">{run.job_id}</td>
                      <td className="px-3 py-2">
                        <Badge variant={run.status === 'success' ? 'outline' : 'destructive'}
                          className="text-[10px]">{run.status}</Badge>
                      </td>
                      <td className="px-3 py-2 text-red-600 max-w-[320px] truncate" title={run.error || ''}>
                        {run.error || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : runs.map((run, i) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-border last:border-0 text-sm">
              <div className="flex-shrink-0">
                {run.status === 'success'
                  ? <CheckCircle2 className="h-4 w-4 text-green-500" />
                  : <XCircle className="h-4 w-4 text-red-500" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-xs truncate">{run.job_id}</p>
                {run.error && <p className="text-[11px] text-red-500 truncate">{run.error}</p>}
              </div>
              <span className="text-xs text-muted-foreground flex-shrink-0">
                {run.started_at ? new Date(run.started_at).toLocaleString('id-ID') : '-'}
              </span>
              <Badge
                variant={run.status === 'success' ? 'outline' : 'destructive'}
                className="text-[10px] flex-shrink-0"
              >
                {run.status}
              </Badge>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
