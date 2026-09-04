import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  Wrench, Activity, AlertTriangle, CheckCircle2, Loader2, Plus, Sparkles,
  TrendingDown, Cog, ClipboardList, Clock, Trash2
} from 'lucide-react';

const STATUS_COLOR = {
  healthy: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  monitor: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
  at_risk: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30',
};

const STATUS_LABEL = {
  healthy: 'Sehat',
  monitor: 'Pantau',
  at_risk: 'Berisiko',
  critical: 'Kritis',
};

const MAINT_TYPE_OPTIONS = [
  { value: 'preventive', label: 'Preventive' },
  { value: 'corrective', label: 'Corrective' },
  { value: 'inspection', label: 'Inspection' },
];

export default function PredictiveMaintenanceModule({ token }) {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedMachine, setSelectedMachine] = useState(null);
  const [detailHealth, setDetailHealth] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [aiAdvice, setAiAdvice] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  const [logDialogOpen, setLogDialogOpen] = useState(false);
  const [logForm, setLogForm] = useState({
    machine_id: '',
    maintenance_type: 'preventive',
    description: '',
    technician: '',
    cost: 0,
  });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const BASE = process.env.REACT_APP_BACKEND_URL;

  const fetchDashboard = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/dashboard`, { headers });
      const data = await r.json();
      setDashboard(data?.data || null);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers]);

  const fetchMachines = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/machines`, { headers });
      const data = await r.json();
      setMachines(data?.data || []);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers]);

  const fetchLogs = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/maintenance-logs`, { headers });
      const data = await r.json();
      setLogs(data?.data || []);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers]);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchDashboard(), fetchMachines(), fetchLogs()]).finally(() => setLoading(false));
  }, [fetchDashboard, fetchMachines, fetchLogs]);

  const openMachine = async (m) => {
    setSelectedMachine(m);
    setDetailHealth(null);
    setAiAdvice(null);
    setDetailOpen(true);
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/machines/${m.id}/health`, { headers });
      const data = await r.json();
      setDetailHealth(data?.data || null);
    } catch (e) {
      console.error(e);
    }
  };

  const runAIPredict = async () => {
    if (!selectedMachine) return;
    setAiLoading(true);
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/machines/${selectedMachine.id}/predict`, {
        method: 'POST', headers,
      });
      const data = await r.json();
      setAiAdvice(data?.data || null);
      toast.success('AI prediction selesai', { icon: <Sparkles className="w-4 h-4" /> });
    } catch (e) {
      toast.error(`AI predict gagal: ${e.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const createLog = async () => {
    if (!logForm.machine_id) {
      toast.error('Pilih mesin');
      return;
    }
    if (!logForm.description?.trim()) {
      toast.error('Description wajib diisi');
      return;
    }
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/maintenance-logs`, {
        method: 'POST', headers,
        body: JSON.stringify({ ...logForm, cost: Number(logForm.cost) || 0 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Log maintenance dicatat');
      setLogDialogOpen(false);
      setLogForm({ machine_id: '', maintenance_type: 'preventive', description: '', technician: '', cost: 0 });
      fetchLogs();
      fetchMachines();
      fetchDashboard();
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  const deleteLog = async (id) => {
    if (!confirm('Hapus log maintenance?')) return;
    try {
      const r = await fetch(`${BASE}/api/production/predictive-maintenance/maintenance-logs/${id}`, {
        method: 'DELETE', headers,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Log dihapus');
      fetchLogs();
      fetchMachines();
      fetchDashboard();
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(logs, 10);
  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Wrench className="w-6 h-6 text-orange-500" /> Predictive Maintenance
          </h1>
          <p className="text-sm text-muted-foreground">
            Monitoring kesehatan mesin & prediksi maintenance berdasarkan log historis + AI advice (Emergent LLM).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={logDialogOpen} onOpenChange={setLogDialogOpen}>
            <DialogTrigger asChild>
              <Button data-testid="pm-add-log-btn"><Plus className="w-4 h-4 mr-1" /> Catat Maintenance</Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle>Catat Maintenance Log</DialogTitle></DialogHeader>
              <div className="space-y-3 py-2">
                <div>
                  <Label>Mesin *</Label>
                  <Select value={logForm.machine_id} onValueChange={(v) => setLogForm({ ...logForm, machine_id: v })}>
                    <SelectTrigger data-testid="pm-log-machine"><SelectValue placeholder="Pilih mesin..." /></SelectTrigger>
                    <SelectContent>
                      {machines.map((m) => <SelectItem key={m.id} value={m.id}>{m.name || m.code || m.id}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Tipe</Label>
                    <Select value={logForm.maintenance_type} onValueChange={(v) => setLogForm({ ...logForm, maintenance_type: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {MAINT_TYPE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Biaya (Rp)</Label>
                    <Input type="number" value={logForm.cost} onChange={(e) => setLogForm({ ...logForm, cost: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Teknisi</Label>
                  <Input value={logForm.technician} onChange={(e) => setLogForm({ ...logForm, technician: e.target.value })} placeholder="Nama teknisi" />
                </div>
                <div>
                  <Label>Description *</Label>
                  <Textarea data-testid="pm-log-desc" value={logForm.description} onChange={(e) => setLogForm({ ...logForm, description: e.target.value })} rows={3} placeholder="Detail pekerjaan, gejala, dll" />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setLogDialogOpen(false)}>Batal</Button>
                <Button data-testid="pm-log-save" onClick={createLog}>Simpan</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-3 w-full md:w-[480px]">
          <TabsTrigger value="dashboard" data-testid="pm-tab-dashboard"><Activity className="w-4 h-4 mr-1.5" /> Dashboard</TabsTrigger>
          <TabsTrigger value="machines" data-testid="pm-tab-machines"><Cog className="w-4 h-4 mr-1.5" /> Mesin</TabsTrigger>
          <TabsTrigger value="logs" data-testid="pm-tab-logs"><ClipboardList className="w-4 h-4 mr-1.5" /> Logs</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-4 space-y-4">
          {loading || !dashboard ? (
            <GlassCard className="p-6 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 inline animate-spin mr-2" /> Memuat...</GlassCard>
          ) : dashboard.total_machines === 0 ? (
            <GlassCard className="p-12 text-center">
              <Cog className="w-12 h-12 text-muted-foreground mx-auto mb-2 opacity-50" />
              <h3 className="font-semibold text-foreground">Belum ada data mesin</h3>
              <p className="text-sm text-muted-foreground">Tambahkan mesin di modul Produksi → Mesin, lalu mulai catat maintenance.</p>
            </GlassCard>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                <StatCard label="Total Mesin" value={dashboard.total_machines} icon={Cog} color="blue" />
                <StatCard label="Sehat" value={dashboard.healthy} icon={CheckCircle2} color="emerald" />
                <StatCard label="Pantau" value={dashboard.monitor} icon={Activity} color="blue" />
                <StatCard label="Berisiko" value={dashboard.at_risk} icon={AlertTriangle} color="amber" />
                <StatCard label="Kritis" value={dashboard.critical} icon={TrendingDown} color="red" />
                <StatCard label="Avg Score" value={`${dashboard.average_score}`} icon={Activity} color="indigo" />
              </div>

              {dashboard.overdue_pm > 0 && (
                <GlassCard className="p-4 border border-amber-500/30 bg-amber-500/5">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <p className="text-sm font-medium text-foreground">
                      {dashboard.overdue_pm} mesin overdue preventive maintenance (&gt;90 hari)
                    </p>
                  </div>
                </GlassCard>
              )}

              {dashboard.critical_machines?.length > 0 && (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-500" /> Mesin Kondisi Kritis</h3>
                  <div className="space-y-2">
                    {dashboard.critical_machines.map((m) => (
                      <div key={m.id} className="p-3 rounded-lg bg-red-500/5 border border-red-500/20">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-sm font-medium">{m.name || m.code}</div>
                            <div className="text-[11px] text-muted-foreground">{m.next_maintenance_recommendation}</div>
                          </div>
                          <Badge className={STATUS_COLOR.critical} variant="outline">Score {m.score}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="machines" className="mt-4">
          {machines.length === 0 ? (
            <GlassCard className="p-10 text-center text-sm text-muted-foreground">Belum ada data mesin</GlassCard>
          ) : (
            <div className="space-y-2">
              {machines.map((m) => (
                <div
                  key={m.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => openMachine(m)}
                  onKeyDown={(e) => e.key === 'Enter' && openMachine(m)}
                  data-testid={`pm-machine-${m.id}`}
                  className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:border-orange-500/40 cursor-pointer transition"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div>
                      <span className="font-medium text-sm">{m.name || m.code}</span>
                      <span className="text-xs text-muted-foreground ml-2">{m.code} · {m.type || 'mesin'}</span>
                    </div>
                    <Badge className={STATUS_COLOR[m.health?.status]} variant="outline">
                      {STATUS_LABEL[m.health?.status] || m.health?.status} · {m.health?.score}
                    </Badge>
                  </div>
                  <Progress value={m.health?.score || 0} className="h-1.5" />
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1">
                    <span>{m.maintenance_logs_count || 0} log</span>
                    <span>{m.health?.next_maintenance_recommendation}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          {logs.length === 0 ? (
            <GlassCard className="p-10 text-center text-sm text-muted-foreground">Belum ada maintenance log</GlassCard>
          ) : (
            <GlassCard className="p-3">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                    <tr>
                      <th className="text-left py-2 px-2">Tanggal</th>
                      <th className="text-left py-2 px-2">Mesin</th>
                      <th className="text-left py-2 px-2">Tipe</th>
                      <th className="text-left py-2 px-2">Deskripsi</th>
                      <th className="text-left py-2 px-2">Teknisi</th>
                      <th className="text-right py-2 px-2">Biaya</th>
                      <th className="text-right py-2 px-2">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paged.map((l) => (
                      <tr key={l.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass)]">
                        <td className="py-2 px-2 text-xs">{l.performed_at ? new Date(l.performed_at).toLocaleString('id-ID') : '—'}</td>
                        <td className="py-2 px-2">{l.machine_name || '—'}</td>
                        <td className="py-2 px-2"><Badge variant="outline" className="text-[11px]">{l.maintenance_type}</Badge></td>
                        <td className="py-2 px-2 text-muted-foreground">{l.description}</td>
                        <td className="py-2 px-2 text-muted-foreground">{l.technician || '—'}</td>
                        <td className="py-2 px-2 text-right text-xs">{l.cost ? `Rp ${Number(l.cost).toLocaleString('id-ID')}` : '—'}</td>
                        <td className="py-2 px-2 text-right">
                          <button onClick={() => deleteLog(l.id)} className="text-red-500 hover:underline" data-testid={`pm-log-del-${l.id}`}>
                            <Trash2 className="w-3.5 h-3.5 inline" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </div>
            </GlassCard>
          )}
        </TabsContent>
      </Tabs>

      {/* Machine Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {selectedMachine && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Cog className="w-5 h-5 text-orange-500" /> {selectedMachine.name || selectedMachine.code}
                </DialogTitle>
              </DialogHeader>
              {!detailHealth ? (
                <div className="py-8 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Memuat...</div>
              ) : (
                <div className="space-y-4">
                  <div className="p-3 rounded-xl bg-gradient-to-br from-orange-500/10 to-red-500/10 border border-orange-500/20">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold">Health Score</span>
                      <Badge className={STATUS_COLOR[detailHealth.health.status]} variant="outline">
                        {STATUS_LABEL[detailHealth.health.status]} · {detailHealth.health.score}
                      </Badge>
                    </div>
                    <Progress value={detailHealth.health.score} className="h-2" />
                    <p className="text-[11px] text-muted-foreground mt-1">{detailHealth.health.next_maintenance_recommendation}</p>
                  </div>

                  {detailHealth.health.factors?.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Faktor Health Score</h4>
                      <div className="space-y-1">
                        {detailHealth.health.factors.map((f, i) => (
                          <div key={i} className="flex items-center justify-between p-2 rounded bg-[var(--glass)] border border-[var(--glass-border)] text-xs">
                            <span>{f.factor}</span>
                            <span className="text-red-500 font-medium">{f.impact}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="p-3 rounded-lg bg-gradient-to-br from-indigo-500/10 to-violet-500/10 border border-indigo-500/20">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold flex items-center gap-1"><Sparkles className="w-4 h-4 text-indigo-500" /> AI Maintenance Advice</span>
                      <Button size="sm" onClick={runAIPredict} disabled={aiLoading} data-testid="pm-ai-predict">
                        {aiLoading ? <><Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> Generating...</> : <><Sparkles className="w-3.5 h-3.5 mr-1" /> Generate</>}
                      </Button>
                    </div>
                    {aiAdvice ? (
                      <div className="whitespace-pre-wrap text-xs text-muted-foreground">{aiAdvice.advice}</div>
                    ) : (
                      <p className="text-xs text-muted-foreground">Klik Generate untuk dapat rekomendasi AI.</p>
                    )}
                  </div>

                  {detailHealth.recent_logs?.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Riwayat Maintenance Terakhir</h4>
                      <div className="space-y-1">
                        {detailHealth.recent_logs.slice(0, 5).map((l, i) => (
                          <div key={i} className="p-2 rounded bg-[var(--glass)] border border-[var(--glass-border)] text-xs">
                            <div className="flex items-center justify-between">
                              <span><Clock className="w-3 h-3 inline mr-1" />{l.performed_at ? new Date(l.performed_at).toLocaleDateString('id-ID') : '—'}</span>
                              <Badge variant="outline" className="text-[10px]">{l.maintenance_type}</Badge>
                            </div>
                            <p className="text-muted-foreground mt-0.5">{l.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setDetailOpen(false)}>Tutup</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }) {
  const map = {
    blue: 'from-blue-500/10 to-cyan-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400',
    emerald: 'from-emerald-500/10 to-teal-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    amber: 'from-amber-500/10 to-orange-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400',
    red: 'from-red-500/10 to-rose-500/10 border-red-500/20 text-red-600 dark:text-red-400',
    indigo: 'from-indigo-500/10 to-violet-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
  };
  return (
    <div className={`p-3 rounded-xl bg-gradient-to-br border ${map[color] || map.blue}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-70" />}
      </div>
      <div className="font-bold text-foreground text-2xl">{value}</div>
    </div>
  );
}
