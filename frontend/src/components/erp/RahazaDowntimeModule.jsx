import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Wrench, Plus, Clock, AlertOctagon, CheckCircle, RefreshCw } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;

export default function RahazaDowntimeModule({ headers }) {
  const { toast } = useToast();
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [showClose, setShowClose] = useState(null); // event to close
  const [machines, setMachines] = useState([]);
  const [reasonCodes, setReasonCodes] = useState([]);
  const [period, setPeriod] = useState('7');
  const [form, setForm] = useState({ machine_id: '', reason_code: 'OTH-001', reason_name: 'Lainnya', notes: '' });
  const [closeEndAt, setCloseEndAt] = useState('');

  const loadMeta = useCallback(async () => {
    try {
      const [m, rc] = await Promise.all([
        axios.get(`${API}/api/rahaza/machines`, { headers }),
        axios.get(`${API}/api/rahaza/downtime/reason-codes`, { headers }),
      ]);
      setMachines(m.data || []);
      setReasonCodes(rc.data || []);
    } catch (e) {}
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = new Date(Date.now() - parseInt(period) * 86400000).toISOString().slice(0, 10);
      const to   = new Date().toISOString().slice(0, 10);
      const [ev, sum] = await Promise.all([
        axios.get(`${API}/api/rahaza/downtime`, { headers, params: { from, to } }),
        axios.get(`${API}/api/rahaza/downtime/summary`, { headers, params: { from, to } }),
      ]);
      setEvents(ev.data || []);
      setSummary(sum.data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [headers, period]);

  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    if (!form.machine_id) { toast({ title: 'Pilih mesin terlebih dahulu', variant: 'destructive' }); return; }
    try {
      const rc = reasonCodes.find(r => r.code === form.reason_code);
      await axios.post(`${API}/api/rahaza/downtime`, { ...form, reason_name: rc?.name || form.reason_name }, { headers });
      toast({ title: 'Downtime dicatat' });
      setShowForm(false);
      load();
    } catch (e) { toast({ title: 'Gagal menyimpan', variant: 'destructive' }); }
  };

  const handleClose = async () => {
    if (!showClose) return;
    try {
      await axios.put(`${API}/api/rahaza/downtime/${showClose.id}`, { end_at: closeEndAt || new Date().toISOString() }, { headers });
      toast({ title: 'Downtime ditutup' });
      setShowClose(null);
      load();
    } catch (e) { toast({ title: 'Gagal menutup', variant: 'destructive' }); }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(events, 10);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><AlertOctagon className="w-5 h-5 text-red-500" /> Log Downtime Mesin</h2>
          <p className="text-sm text-muted-foreground">Catat henti mesin untuk akurasi OEE Availability</p>
        </div>
        <div className="flex gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 hari</SelectItem>
              <SelectItem value="30">30 hari</SelectItem>
              <SelectItem value="90">90 hari</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" onClick={() => setShowForm(true)}><Plus className="w-4 h-4 mr-1" /> Log Downtime</Button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Total Event', value: summary.total_events, color: 'text-foreground' },
            { label: 'Total Downtime', value: `${summary.total_downtime_min} menit`, color: 'text-red-500' },
            { label: 'Total Jam', value: `${summary.total_downtime_hours} jam`, color: 'text-red-500' },
            { label: 'Top Reason', value: summary.by_reason?.[0]?.reason_name || '-', color: 'text-orange-500' },
          ].map(s => (
            <Card key={s.label}><CardContent className="pt-4">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className={`text-lg font-bold ${s.color}`}>{s.value}</p>
            </CardContent></Card>
          ))}
        </div>
      )}

      {loading ? <div className="text-center py-8 text-muted-foreground">Memuat...</div> : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Mesin</th>
                <th className="text-left px-4 py-2 font-medium">Alasan</th>
                <th className="text-left px-4 py-2 font-medium">Mulai</th>
                <th className="text-left px-4 py-2 font-medium">Durasi</th>
                <th className="text-left px-4 py-2 font-medium">Status</th>
                <th className="text-right px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map(e => (
                <tr key={e.id} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-2">
                    <p className="font-medium">{e.machine_name || e.machine_code || e.machine_id}</p>
                    <p className="text-xs text-muted-foreground">{e.machine_code}</p>
                  </td>
                  <td className="px-4 py-2">
                    <p>{e.reason_name}</p>
                    <p className="text-xs text-muted-foreground">{e.reason_code}</p>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{e.start_at?.slice(0, 16).replace('T', ' ')}</td>
                  <td className="px-4 py-2">
                    {e.duration_min ? <span className="font-medium">{e.duration_min} menit</span> : <span className="text-muted-foreground text-xs">ongoing</span>}
                  </td>
                  <td className="px-4 py-2">
                    <Badge variant={e.status === 'open' ? 'destructive' : 'secondary'}>
                      {e.status === 'open' ? 'Berjalan' : 'Selesai'}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    {e.status === 'open' && (
                      <Button variant="outline" size="sm" onClick={() => { setShowClose(e); setCloseEndAt(new Date().toISOString().slice(0, 16)); }}>
                        <CheckCircle className="w-3.5 h-3.5 mr-1" /> Tutup
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr><td colSpan={6} className="text-center py-10 text-muted-foreground">
                  <Wrench className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  Belum ada downtime tercatat
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} />

      {/* Log Downtime Form */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log Downtime Baru</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium">Mesin *</label>
              <Select value={form.machine_id} onValueChange={v => setForm(f => ({ ...f, machine_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Pilih mesin" /></SelectTrigger>
                <SelectContent>{machines.map(m => <SelectItem key={m.id} value={m.id}>{m.code} — {m.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium">Kode Alasan *</label>
              <Select value={form.reason_code} onValueChange={v => setForm(f => ({ ...f, reason_code: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{reasonCodes.map(rc => <SelectItem key={rc.code} value={rc.code}>{rc.code} — {rc.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium">Catatan</label>
              <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Detail tambahan..." />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
              <Button onClick={handleSave}>Simpan</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Close Downtime */}
      <Dialog open={!!showClose} onOpenChange={() => setShowClose(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Tutup Downtime</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Mesin: <strong>{showClose?.machine_name}</strong></p>
          <div>
            <label className="text-sm font-medium">Waktu Selesai</label>
            <Input type="datetime-local" value={closeEndAt} onChange={e => setCloseEndAt(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowClose(null)}>Batal</Button>
            <Button onClick={handleClose}>Konfirmasi Selesai</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
