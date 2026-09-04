import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  MessageSquare, Plus, RefreshCw, CheckCircle2, Clock,
  Loader2, Users as UsersIcon, X, Save, Star, BarChart3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from './moduleAtoms';

const API = process.env.REACT_APP_BACKEND_URL;

export default function HR360FeedbackModule({ token, user }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [cycles, setCycles] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [users, setUsers] = useState([]);
  const [tab, setTab] = useState('open');
  const [loading, setLoading] = useState(false);
  const [newDialog, setNewDialog] = useState(false);
  const [reviewDialog, setReviewDialog] = useState(null);
  const [detailDialog, setDetailDialog] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3] = await Promise.all([
        axios.get(`${API}/api/rahaza/360-feedback/cycles?status=${tab === 'all' ? '' : tab}`, { headers }),
        axios.get(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers }),
        axios.get(`${API}/api/users`, { headers }).catch(() => ({ data: [] })),
      ]);
      setCycles(r1.data.cycles || []);
      setEmployees(Array.isArray(r2.data) ? r2.data : (r2.data.items || r2.data.rows || []));
      setUsers(Array.isArray(r3.data) ? r3.data : []);
    } finally { setLoading(false); }
  }, [headers, tab]);

  useEffect(() => { load(); }, [load]);

  const close = async (id) => {
    if (!window.confirm('Tutup cycle & compute aggregate?')) return;
    try {
      await axios.post(`${API}/api/rahaza/360-feedback/cycles/${id}/close`, {}, { headers });
      toast.success('Cycle ditutup');
      load();
    } catch { toast.error('Gagal tutup'); }
  };

  return (
    <div className="space-y-6 p-6" data-testid="360-feedback-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-blue-600 dark:text-blue-400" /> 360° Feedback
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Penilaian multi-source: self + manager + peer + subordinate · {cycles.length} cycle</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}><RefreshCw className="w-4 h-4 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setNewDialog(true)} data-testid="360-new-cycle"><Plus className="w-4 h-4 mr-1" />Buat Cycle</Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="open">Terbuka</TabsTrigger>
          <TabsTrigger value="closed">Tertutup</TabsTrigger>
          <TabsTrigger value="all">Semua</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4 space-y-2">
          {loading ? (
            <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
          ) : cycles.length === 0 ? (
            <EmptyState icon={MessageSquare} title="Belum ada feedback cycle" description="Klik 'Buat Cycle' untuk memulai proses 360° feedback." />
          ) : null}
          {cycles.map(c => {
            const myReviewer = c.reviewers?.find(r => r.reviewer_id === user?.id);
            const submitted = c.reviewers?.filter(r => r.status === 'submitted').length || 0;
            const total = c.reviewers?.length || 0;
            return (
              <div key={c.cycle_id} className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold">{c.target_employee_name}</h3>
                      <span className="text-xs font-mono text-muted-foreground">{c.target_employee_code}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${c.status === 'open' ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300' : 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300'}`}>{c.status}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{c.period_name}</p>
                    <p className="text-xs text-muted-foreground mt-1">Progress: <strong>{submitted}/{total}</strong> reviewer submitted</p>
                  </div>
                  <div className="flex gap-1">
                    {myReviewer && myReviewer.status === 'pending' && c.status === 'open' && (
                      <Button size="sm" onClick={() => setReviewDialog(c)} data-testid={`360-review-${c.cycle_id}`}>
                        <Star className="w-3 h-3 mr-1" />Isi Review
                      </Button>
                    )}
                    {c.status === 'closed' && (
                      <Button size="sm" variant="outline" onClick={() => setDetailDialog(c)}>
                        <BarChart3 className="w-3 h-3 mr-1" />Lihat Hasil
                      </Button>
                    )}
                    {c.status === 'open' && submitted === total && total > 0 && (
                      <Button size="sm" variant="outline" onClick={() => close(c.cycle_id)}>
                        <CheckCircle2 className="w-3 h-3 mr-1" />Tutup
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          {cycles.length === 0 && !loading && (
            <div className="text-center py-16 text-muted-foreground">
              <MessageSquare className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>Belum ada cycle 360 feedback</p>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {newDialog && (
        <NewCycleDialog employees={employees} users={users} headers={headers}
          onClose={() => setNewDialog(false)}
          onCreated={() => { setNewDialog(false); load(); }} />
      )}
      {reviewDialog && (
        <ReviewDialog cycle={reviewDialog} headers={headers}
          onSubmit={() => { setReviewDialog(null); load(); }}
          onClose={() => setReviewDialog(null)} />
      )}
      {detailDialog && (
        <DetailDialog cycle={detailDialog} onClose={() => setDetailDialog(null)} />
      )}
    </div>
  );
}

function NewCycleDialog({ employees, users, headers, onClose, onCreated }) {
  const [targetId, setTargetId] = useState('');
  const [periodName, setPeriodName] = useState('');
  const [reviewers, setReviewers] = useState([]);
  const [saving, setSaving] = useState(false);

  const addReviewer = (userId, relationship) => {
    const u = users.find(x => x.id === userId);
    if (!u || reviewers.some(r => r.reviewer_id === userId)) return;
    setReviewers([...reviewers, { reviewer_id: userId, reviewer_name: u.name, relationship }]);
  };

  const submit = async () => {
    if (!targetId) { toast.error('Pilih target karyawan'); return; }
    if (reviewers.length === 0) { toast.error('Tambahkan minimal 1 reviewer'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/api/rahaza/360-feedback/cycles`,
        { target_employee_id: targetId, period_name: periodName, reviewers }, { headers });
      toast.success('Cycle dibuat');
      onCreated();
    } catch { toast.error('Gagal'); }
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Buat 360 Feedback Cycle</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label>Target Karyawan *</Label>
            <Select value={targetId} onValueChange={setTargetId}>
              <SelectTrigger><SelectValue placeholder="Pilih target..." /></SelectTrigger>
              <SelectContent>
                {employees.slice(0, 50).map(e => <SelectItem key={e.id} value={e.id}>{`${e.employee_code} — ${e.name}`}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1"><Label>Nama Periode</Label>
            <Input value={periodName} onChange={e => setPeriodName(e.target.value)} placeholder="Q1 2026 Review" />
          </div>
          <div className="space-y-1">
            <Label>Tambah Reviewer (pilih user & hubungan)</Label>
            <div className="flex gap-1">
              <Select onValueChange={(v) => { const [uid, rel] = v.split('|'); addReviewer(uid, rel); }}>
                <SelectTrigger><SelectValue placeholder="Pilih user + relationship..." /></SelectTrigger>
                <SelectContent>
                  {users.slice(0, 20).map(u => (
                    <div key={u.id} className="border-b border-foreground/5 last:border-0">
                      <div className="px-2 py-1 text-[10px] text-muted-foreground">{u.name}</div>
                      {['self', 'manager', 'peer', 'subordinate'].map(rel => (
                        <SelectItem key={`${u.id}|${rel}`} value={`${u.id}|${rel}`} className="pl-5">
                          sebagai {rel}
                        </SelectItem>
                      ))}
                    </div>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {reviewers.length > 0 && (
              <div className="space-y-1 mt-2">
                {reviewers.map((r, i) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-foreground/5 rounded px-2 py-1">
                    <span>{r.reviewer_name} <span className="text-muted-foreground">({r.relationship})</span></span>
                    <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setReviewers(reviewers.filter((_, idx) => idx !== i))}><X className="w-3 h-3" /></Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}Buat Cycle
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReviewDialog({ cycle, headers, onSubmit, onClose }) {
  const [responses, setResponses] = useState({});
  const [saving, setSaving] = useState(false);

  const set = (qid, val) => setResponses(r => ({ ...r, [qid]: val }));

  const submit = async () => {
    const arr = (cycle.questions || []).map(q => ({
      question_id: q.id,
      score: q.type === 'text' ? null : (responses[q.id + '_score'] ?? 0),
      comment: responses[q.id + '_comment'] || responses[q.id] || '',
    }));
    setSaving(true);
    try {
      await axios.post(`${API}/api/rahaza/360-feedback/cycles/${cycle.cycle_id}/submit`,
        { responses: arr }, { headers });
      toast.success('Feedback tersimpan'); onSubmit();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal'); }
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Review: {cycle.target_employee_name}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {(cycle.questions || []).map(q => (
            <div key={q.id} className="space-y-1 border-b border-foreground/5 pb-3">
              <Label className="text-xs">{q.text}</Label>
              {q.type === 'text' ? (
                <Textarea rows={2} onChange={e => set(q.id, e.target.value)} placeholder="Jawaban Anda..." />
              ) : (
                <div className="flex items-center gap-2">
                  {[1, 2, 3, 4, 5].map(n => (
                    <button key={n} type="button"
                      className={`w-8 h-8 rounded-full border text-xs ${
                        responses[q.id + '_score'] === n ? 'bg-blue-500 border-blue-400 text-foreground' : 'border-foreground/10 hover:bg-foreground/5'
                      }`}
                      onClick={() => set(q.id + '_score', n)}>{n}</button>
                  ))}
                  <span className="text-[10px] text-muted-foreground ml-2">(1=kurang, 5=sangat baik)</span>
                </div>
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}Kirim Review
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailDialog({ cycle, onClose }) {
  const agg = cycle.aggregate || {};
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>Hasil 360: {cycle.target_employee_name}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {Object.entries(agg).map(([qid, data]) => (
            <div key={qid} className="border-b border-foreground/5 pb-2">
              <div className="text-xs font-medium">{data.question}</div>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 h-2 bg-foreground/10 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-400" style={{ width: `${(data.avg_score / 5) * 100}%` }} />
                </div>
                <span className="text-xs font-bold font-mono">{data.avg_score}/5</span>
                <span className="text-[10px] text-muted-foreground">({data.total_responses} resp)</span>
              </div>
              {Object.keys(data.by_relation || {}).length > 0 && (
                <div className="text-[10px] text-muted-foreground mt-1">
                  Per relationship: {Object.entries(data.by_relation).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                </div>
              )}
            </div>
          ))}
          {Object.keys(agg).length === 0 && <p className="text-center text-xs text-muted-foreground py-8">Belum ada data aggregate</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
