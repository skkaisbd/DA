import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Clock, Plus, Check, X, RefreshCw, Calendar, User, AlertCircle,
  CheckCircle2, XCircle, Loader2, Search, Save,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CFG = {
  pending:   { label: 'Pending',   color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300',   icon: Clock },
  approved:  { label: 'Disetujui', color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300', icon: CheckCircle2 },
  rejected:  { label: 'Ditolak',   color: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300',       icon: XCircle },
  cancelled: { label: 'Dibatalkan',color: 'bg-muted dark:bg-slate-500/20 text-foreground/70',   icon: X },
};

export default function RahazaOvertimeModule({ token, user }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [items, setItems] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [tab, setTab] = useState('pending');
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);

  const isApprover = ['superadmin', 'admin', 'owner', 'hr', 'manager'].includes(user?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const statusParam = tab === 'all' ? '' : `?status=${tab}`;
      const [r1, r2] = await Promise.all([
        axios.get(`${API}/api/rahaza/overtime${statusParam}`, { headers }),
        isApprover
          ? axios.get(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers }).catch(() => ({ data: [] }))
          : Promise.resolve({ data: [] }),
      ]);
      setItems(r1.data.overtime || []);
      setEmployees(Array.isArray(r2.data) ? r2.data : (r2.data.items || r2.data.rows || []));
    } finally { setLoading(false); }
  }, [headers, tab, isApprover]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form) => {
    try {
      await axios.post(`${API}/api/rahaza/overtime`, form, { headers });
      toast.success('Request lembur dikirim, menunggu approval');
      setDialog(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal submit'); }
  };

  const handleApprove = async (id) => {
    try {
      await axios.put(`${API}/api/rahaza/overtime/${id}/approve`, {}, { headers });
      toast.success('Lembur disetujui');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal approve'); }
  };

  const handleReject = async (id, reason) => {
    try {
      await axios.put(`${API}/api/rahaza/overtime/${id}/reject`, { reason }, { headers });
      toast.success('Lembur ditolak');
      setRejectDialog(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal reject'); }
  };

  const handleCancel = async (id) => {
    if (!window.confirm('Batalkan request lembur ini?')) return;
    try {
      await axios.delete(`${API}/api/rahaza/overtime/${id}`, { headers });
      toast.success('Request dibatalkan');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal cancel'); }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(items, 10);

  return (
    <div className="space-y-6 p-6" data-testid="overtime-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Clock className="w-6 h-6 text-amber-700 dark:text-amber-400" /> Request Lembur (Overtime)
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isApprover
              ? 'Kelola request lembur karyawan · Hanya lembur yang disetujui akan masuk ke payroll'
              : 'Ajukan request lembur · Tunggu persetujuan supervisor'}
            {' · '}{items.length} record
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="overtime-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setDialog({})} data-testid="overtime-create">
            <Plus className="w-4 h-4 mr-1" /> Ajukan Lembur
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-5 w-full max-w-md">
          <TabsTrigger value="pending" className="text-xs">Pending</TabsTrigger>
          <TabsTrigger value="approved" className="text-xs">Disetujui</TabsTrigger>
          <TabsTrigger value="rejected" className="text-xs">Ditolak</TabsTrigger>
          <TabsTrigger value="cancelled" className="text-xs">Dibatal</TabsTrigger>
          <TabsTrigger value="all" className="text-xs">Semua</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4">
          <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-3">Karyawan</th>
                  <th className="text-left px-4 py-3">Tanggal</th>
                  <th className="text-left px-4 py-3">Jam</th>
                  <th className="text-left px-4 py-3">Durasi</th>
                  <th className="text-left px-4 py-3">Alasan</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {paged.map(it => {
                  const s = STATUS_CFG[it.status] || STATUS_CFG.pending;
                  const StatIcon = s.icon;
                  return (
                    <tr key={it.id} className="hover:bg-foreground/5" data-testid={`overtime-row-${it.id}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-sm">{it.employee?.name || '—'}</div>
                        <div className="text-[10px] text-muted-foreground font-mono">{it.employee?.employee_code}</div>
                      </td>
                      <td className="px-4 py-3 text-xs font-mono">{it.date}</td>
                      <td className="px-4 py-3 text-xs">{it.start_time} — {it.end_time}</td>
                      <td className="px-4 py-3 text-xs">
                        <span className="font-bold">{it.hours}</span> jam
                        {it.rate_multiplier !== 1 && <span className="text-muted-foreground"> ×{it.rate_multiplier}</span>}
                      </td>
                      <td className="px-4 py-3 text-xs max-w-xs truncate">{it.reason || '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1 w-fit ${s.color}`}>
                          <StatIcon className="w-3 h-3" />{s.label}
                        </span>
                        {it.status === 'rejected' && it.rejected_reason && (
                          <div className="text-[10px] text-red-700 dark:text-red-400 mt-0.5">{it.rejected_reason}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          {isApprover && it.status === 'pending' && (
                            <>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-600 dark:text-emerald-400"
                                title="Approve" onClick={() => handleApprove(it.id)}
                                data-testid={`overtime-approve-${it.id}`}>
                                <Check className="w-3.5 h-3.5" />
                              </Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400"
                                title="Reject" onClick={() => setRejectDialog(it)}>
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            </>
                          )}
                          {it.status === 'pending' && (
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground"
                              title="Cancel" onClick={() => handleCancel(it.id)}>
                              <XCircle className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && !loading && (
                  <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">
                    <Clock className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p>Tidak ada request lembur</p>
                  </td></tr>
                )}
                {loading && <tr><td colSpan={7} className="text-center py-8"><Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" /></td></tr>}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-4" />
        </TabsContent>
      </Tabs>

      {dialog && (
        <OvertimeDialog
          employees={employees}
          isApprover={isApprover}
          currentUser={user}
          onSave={handleSave}
          onClose={() => setDialog(null)}
        />
      )}

      {rejectDialog && (
        <RejectDialog
          request={rejectDialog}
          onReject={(reason) => handleReject(rejectDialog.id, reason)}
          onClose={() => setRejectDialog(null)}
        />
      )}
    </div>
  );
}

function OvertimeDialog({ employees, isApprover, currentUser, onSave, onClose }) {
  const [form, setForm] = useState({
    employee_id: currentUser?.employee_id || '',
    date: new Date().toISOString().slice(0, 10),
    start_time: '17:00',
    end_time: '19:00',
    rate_multiplier: 1.5,
    reason: '',
  });
  const [saving, setSaving] = useState(false);

  const hours = useMemo(() => {
    try {
      const [h1, m1] = form.start_time.split(':').map(Number);
      const [h2, m2] = form.end_time.split(':').map(Number);
      const s = h1 * 60 + m1;
      let e = h2 * 60 + m2;
      if (e < s) e += 24 * 60;
      return ((e - s) / 60).toFixed(2);
    } catch { return 0; }
  }, [form.start_time, form.end_time]);

  const submit = async (e) => {
    e.preventDefault();
    if (isApprover && !form.employee_id) { toast.error('Pilih karyawan'); return; }
    if (!form.reason?.trim()) { toast.error('Alasan wajib diisi'); return; }
    setSaving(true);
    await onSave({ ...form, hours: parseFloat(hours) });
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Request Lembur Baru</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          {isApprover && (
            <div className="space-y-1">
              <Label>Karyawan *</Label>
              <Select value={form.employee_id} onValueChange={v => setForm(f => ({ ...f, employee_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Pilih karyawan..." /></SelectTrigger>
                <SelectContent>
                  {employees.slice(0, 100).map(e => <SelectItem key={e.id} value={e.id}>{`${e.employee_code} — ${e.name}`}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <Label>Tanggal *</Label>
            <Input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} required />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label>Mulai</Label>
              <Input type="time" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Selesai</Label>
              <Input type="time" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Durasi</Label>
              <Input value={`${hours} jam`} readOnly className="bg-muted/50" />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Tarif Lembur</Label>
            <Select value={String(form.rate_multiplier)} onValueChange={v => setForm(f => ({ ...f, rate_multiplier: Number(v) }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1.5">1.5× (Lembur hari kerja)</SelectItem>
                <SelectItem value="2">2× (Hari libur)</SelectItem>
                <SelectItem value="3">3× (Hari libur nasional jam ke-8+)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Alasan *</Label>
            <Textarea value={form.reason} rows={3}
              onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="Contoh: Menyelesaikan batch produksi urgent untuk client A" required />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving} data-testid="overtime-save">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Ajukan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({ request, onReject, onClose }) {
  const [reason, setReason] = useState('');
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Tolak Request Lembur</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2 text-xs">
            <div className="font-medium">{request.employee?.name}</div>
            <div className="text-muted-foreground">{request.date} · {request.hours} jam · {request.reason}</div>
          </div>
          <div className="space-y-1">
            <Label>Alasan Penolakan *</Label>
            <Textarea value={reason} rows={3} onChange={e => setReason(e.target.value)}
              placeholder="Contoh: Produksi sudah selesai di jam reguler" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button variant="destructive" onClick={() => onReject(reason || 'Tidak disebutkan')}>
            <X className="w-4 h-4 mr-1" /> Tolak
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
