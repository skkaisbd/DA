/**
 * HRAttendanceSessionsModule — REKAP ISTIRAHAT & IZIN + ANTREAN PERSETUJUAN.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * KENAPA MODUL INI ADA
 * ════════════════════════════════════════════════════════════════════════════
 * Permintaan user 2026-07-26:
 *   · "Izin keluar butuh persetujuan atasan/HR dulu, bukan langsung tercatat."
 *   · "Buatkan menu Rekap Istirahat & Izin (filter tanggal/karyawan) + export Excel."
 *
 * Sebelum ini backend sudah menyimpan sesi keluar-masuk di
 * `rahaza_attendance_events.sessions[]`, tetapi TIDAK ADA satu pun layar yang
 * menampilkannya — jadi HR tidak punya cara melihat siapa istirahat berapa lama
 * atau menyetujui izin. Modul ini menutup celah FE↔BE tersebut.
 *
 * Endpoint yang dipakai (semuanya sudah ada di backend):
 *   GET  /api/rahaza/attendance/permits?status=pending
 *   POST /api/rahaza/attendance/permits/{id}/approve | /reject
 *   GET  /api/rahaza/attendance/sessions?from_date&to_date&employee_id&kind&status
 *   GET  /api/rahaza/attendance/sessions/export.xlsx
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Coffee, DoorOpen, Download, Loader2, RefreshCw, CheckCircle2, XCircle,
  Hourglass, Users, Timer, AlertCircle, Search,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);

const fmtTime = (v) => {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleTimeString('id-ID', {
      hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta',
    });
  } catch { return '—'; }
};

const fmtDur = (m) => {
  const x = Math.max(0, Math.round(Number(m) || 0));
  return x < 60 ? `${x} mnt` : `${Math.floor(x / 60)} j ${x % 60} mnt`;
};

const STATUS_BADGE = {
  pending: 'bg-amber-100 text-amber-800 border-amber-300',
  approved: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  rejected: 'bg-red-100 text-red-800 border-red-300',
  cancelled: 'bg-slate-100 text-slate-700 border-slate-300',
  not_required: 'bg-blue-100 text-blue-800 border-blue-300',
};
const STATUS_TEXT = {
  pending: 'Menunggu', approved: 'Disetujui', rejected: 'Ditolak',
  cancelled: 'Dibatalkan', not_required: 'Tercatat',
};

export default function HRAttendanceSessionsModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [tab, setTab] = useState('pending');

  const [pending, setPending] = useState([]);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [exporting, setExporting] = useState(false);

  const [filters, setFilters] = useState({
    from_date: daysAgoISO(7), to_date: todayISO(),
    employee_id: '', kind: '', status: '', q: '',
  });

  const [decide, setDecide] = useState(null);   // { item, mode: 'approve'|'reject' }
  const [notes, setNotes] = useState('');

  const loadPending = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/rahaza/attendance/permits?status=pending`, { headers });
      setPending(r.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal memuat antrean izin');
    }
  }, [headers]);

  const loadRows = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (filters.from_date) p.set('from_date', filters.from_date);
      if (filters.to_date) p.set('to_date', filters.to_date);
      if (filters.employee_id) p.set('employee_id', filters.employee_id);
      if (filters.kind) p.set('kind', filters.kind);
      if (filters.status) p.set('status', filters.status);
      const r = await axios.get(`${API}/api/rahaza/attendance/sessions?${p}`, { headers });
      setRows(r.data?.items || []);
      setSummary(r.data?.summary || {});
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal memuat rekap sesi');
    }
  }, [headers, filters]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadPending(), loadRows()]);
    setLoading(false);
  }, [loadPending, loadRows]);

  useEffect(() => {
    axios.get(`${API}/api/rahaza/employees`, { headers })
      .then((r) => {
        const d = r.data;
        setEmployees(Array.isArray(d) ? d : (d?.items || d?.rows || d?.data || []));
      })
      .catch(() => setEmployees([]));
  }, [headers]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const submitDecision = async () => {
    if (!decide) return;
    const { item, mode } = decide;
    if (mode === 'reject' && !notes.trim()) {
      toast.error('Alasan penolakan wajib diisi.');
      return;
    }
    setBusy(item.id);
    try {
      await axios.post(
        `${API}/api/rahaza/attendance/permits/${item.id}/${mode}`,
        { notes: notes.trim() }, { headers },
      );
      toast.success(mode === 'approve'
        ? `Izin ${item.employee_name} disetujui — durasi dihitung mulai sekarang.`
        : `Izin ${item.employee_name} ditolak.`);
      setDecide(null); setNotes('');
      await loadAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal memproses keputusan');
    } finally { setBusy(''); }
  };

  const exportExcel = async () => {
    setExporting(true);
    try {
      const p = new URLSearchParams();
      if (filters.from_date) p.set('from_date', filters.from_date);
      if (filters.to_date) p.set('to_date', filters.to_date);
      if (filters.employee_id) p.set('employee_id', filters.employee_id);
      if (filters.kind) p.set('kind', filters.kind);
      if (filters.status) p.set('status', filters.status);
      const r = await axios.get(`${API}/api/rahaza/attendance/sessions/export.xlsx?${p}`,
        { headers, responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `rekap_istirahat_izin_${filters.from_date}_${filters.to_date}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Rekap Excel diunduh.');
    } catch (e) {
      toast.error('Gagal mengunduh Excel');
    } finally { setExporting(false); }
  };

  const filtered = rows.filter((r) => {
    const q = filters.q.trim().toLowerCase();
    if (!q) return true;
    return [r.employee_name, r.employee_code, r.reason, r.decision_notes]
      .some((v) => String(v || '').toLowerCase().includes(q));
  });

  return (
    <div className="p-6 space-y-5" data-testid="hr-attendance-sessions">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <span>PORTAL SDM</span><span>›</span><span>KEHADIRAN</span>
          </div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Timer className="w-6 h-6 text-primary" /> Istirahat &amp; Izin
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Setujui izin keluar karyawan dan lihat rekap keluar-masuk jam kerja.
            Hanya izin yang <b>disetujui</b> yang memotong jam kerja.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadAll} data-testid="sessions-refresh">
          <RefreshCw className="w-4 h-4 mr-1.5" /> Muat ulang
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-muted/40 p-1 rounded-xl w-fit">
        <button onClick={() => setTab('pending')} data-testid="tab-pending"
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            tab === 'pending' ? 'bg-white shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
          ⏳ Menunggu Persetujuan
          {pending.length > 0 && (
            <span className="ml-2 rounded-full bg-amber-500 text-white text-[11px] px-1.5 py-0.5"
              data-testid="pending-badge">{pending.length}</span>
          )}
        </button>
        <button onClick={() => setTab('rekap')} data-testid="tab-rekap"
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            tab === 'rekap' ? 'bg-white shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
          📋 Rekap Istirahat &amp; Izin
        </button>
      </div>

      {loading && <Skeleton className="h-52 w-full" />}

      {/* ── ANTREAN PERSETUJUAN ─────────────────────────────────────────── */}
      {!loading && tab === 'pending' && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Hourglass className="w-4 h-4" /> Pengajuan izin menunggu keputusan
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pending.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground" data-testid="pending-empty">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500" />
                Tidak ada pengajuan izin yang menunggu.
              </div>
            ) : (
              <div className="divide-y" data-testid="pending-list">
                {pending.map((it) => (
                  <div key={it.id} className="py-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-[240px]">
                      <p className="font-semibold flex items-center gap-2">
                        <Users className="w-4 h-4 text-muted-foreground" />
                        {it.employee_name}
                        <span className="text-xs text-muted-foreground">({it.employee_code})</span>
                      </p>
                      <p className="text-sm text-muted-foreground mt-0.5">
                        {it.date} · diajukan {fmtTime(it.requested_at)} · &quot;{it.reason}&quot;
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" disabled={busy === it.id}
                        onClick={() => { setDecide({ item: it, mode: 'approve' }); setNotes(''); }}
                        data-testid={`permit-approve-${it.id}`}>
                        <CheckCircle2 className="w-4 h-4 mr-1.5" /> Setujui
                      </Button>
                      <Button size="sm" variant="destructive" disabled={busy === it.id}
                        onClick={() => { setDecide({ item: it, mode: 'reject' }); setNotes(''); }}
                        data-testid={`permit-reject-${it.id}`}>
                        <XCircle className="w-4 h-4 mr-1.5" /> Tolak
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── REKAP ───────────────────────────────────────────────────────── */}
      {!loading && tab === 'rekap' && (
        <>
          <Card>
            <CardContent className="pt-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 items-end">
                <div>
                  <Label htmlFor="f-from" className="text-xs">Dari tanggal</Label>
                  <Input id="f-from" type="date" value={filters.from_date} data-testid="filter-from"
                    onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="f-to" className="text-xs">Sampai tanggal</Label>
                  <Input id="f-to" type="date" value={filters.to_date} data-testid="filter-to"
                    onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} />
                </div>
                <div>
                  <Label htmlFor="f-emp" className="text-xs">Karyawan</Label>
                  <select id="f-emp" data-testid="filter-employee"
                    className="w-full h-9 border rounded-md px-2 text-sm bg-background"
                    value={filters.employee_id}
                    onChange={(e) => setFilters((f) => ({ ...f, employee_id: e.target.value }))}>
                    <option value="">Semua karyawan</option>
                    {employees.map((e) => (
                      <option key={e.id} value={e.id}>{e.employee_code} — {e.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="f-kind" className="text-xs">Jenis</Label>
                  <select id="f-kind" data-testid="filter-kind"
                    className="w-full h-9 border rounded-md px-2 text-sm bg-background"
                    value={filters.kind}
                    onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))}>
                    <option value="">Semua</option>
                    <option value="istirahat">Istirahat</option>
                    <option value="izin">Izin</option>
                  </select>
                </div>
                <div>
                  <Label htmlFor="f-status" className="text-xs">Status</Label>
                  <select id="f-status" data-testid="filter-status"
                    className="w-full h-9 border rounded-md px-2 text-sm bg-background"
                    value={filters.status}
                    onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
                    <option value="">Semua</option>
                    <option value="pending">Menunggu</option>
                    <option value="approved">Disetujui</option>
                    <option value="rejected">Ditolak</option>
                    <option value="cancelled">Dibatalkan</option>
                    <option value="not_required">Istirahat (tercatat)</option>
                  </select>
                </div>
                <Button onClick={exportExcel} disabled={exporting} data-testid="export-excel">
                  {exporting ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                    : <Download className="w-4 h-4 mr-1.5" />}
                  Export Excel
                </Button>
              </div>
              <div className="mt-3 relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input className="pl-9" placeholder="Cari nama / NIK / alasan…" data-testid="filter-q"
                  value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} />
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard icon={Coffee} label="Sesi istirahat" value={summary.istirahat_count || 0}
              sub={fmtDur(summary.istirahat_minutes)} testid="stat-istirahat" />
            <StatCard icon={DoorOpen} label="Sesi izin" value={summary.izin_count || 0}
              sub={`${fmtDur(summary.izin_minutes)} disetujui`} testid="stat-izin" />
            <StatCard icon={Hourglass} label="Menunggu" value={summary.pending || 0}
              sub="perlu keputusan" testid="stat-pending" />
            <StatCard icon={XCircle} label="Ditolak/Batal"
              value={(summary.rejected || 0) + (summary.cancelled || 0)}
              sub="tidak memotong jam" testid="stat-rejected" />
          </div>

          <Card>
            <CardContent className="pt-5 overflow-x-auto">
              {filtered.length === 0 ? (
                <div className="py-10 text-center text-muted-foreground" data-testid="rekap-empty">
                  <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                  Tidak ada sesi istirahat/izin pada rentang ini.
                </div>
              ) : (
                <table className="w-full text-sm" data-testid="rekap-table">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-3">Tanggal</th>
                      <th className="py-2 pr-3">Karyawan</th>
                      <th className="py-2 pr-3">Jenis</th>
                      <th className="py-2 pr-3">Keluar</th>
                      <th className="py-2 pr-3">Kembali</th>
                      <th className="py-2 pr-3">Durasi</th>
                      <th className="py-2 pr-3">Alasan</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2">Diputuskan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r) => (
                      <tr key={`${r.id}`} className="border-b last:border-0 hover:bg-muted/40">
                        <td className="py-2 pr-3 whitespace-nowrap">{r.date}</td>
                        <td className="py-2 pr-3">
                          <div className="font-medium">{r.employee_name}</div>
                          <div className="text-xs text-muted-foreground">{r.employee_code}</div>
                        </td>
                        <td className="py-2 pr-3">
                          <Badge variant="outline" className="gap-1">
                            {r.kind === 'izin' ? <DoorOpen className="w-3 h-3" /> : <Coffee className="w-3 h-3" />}
                            {r.kind}
                          </Badge>
                        </td>
                        <td className="py-2 pr-3">{fmtTime(r.out_at)}</td>
                        <td className="py-2 pr-3">{fmtTime(r.in_at)}</td>
                        <td className="py-2 pr-3">{r.minutes ? fmtDur(r.minutes) : '—'}</td>
                        <td className="py-2 pr-3 max-w-[220px] truncate" title={r.reason || ''}>
                          {r.reason || '—'}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`text-[11px] px-1.5 py-0.5 rounded border ${STATUS_BADGE[r.approval_status] || ''}`}>
                            {STATUS_TEXT[r.approval_status] || r.approval_status}
                          </span>
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {r.approved_by_name || '—'}
                          {r.decision_notes ? ` · ${r.decision_notes}` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Dialog keputusan */}
      <Dialog open={Boolean(decide)} onOpenChange={(v) => { if (!v) { setDecide(null); setNotes(''); } }}>
        <DialogContent data-testid="decide-dialog">
          <DialogHeader>
            <DialogTitle>
              {decide?.mode === 'approve' ? 'Setujui Izin Keluar' : 'Tolak Izin Keluar'}
            </DialogTitle>
            <DialogDescription>
              {decide?.item?.employee_name} ({decide?.item?.employee_code}) — &quot;{decide?.item?.reason}&quot;.
              {decide?.mode === 'approve'
                ? ' Durasi izin dihitung MULAI SAAT DISETUJUI dan tidak dibayar sebagai jam kerja.'
                : ' Alasan penolakan wajib diisi dan akan dikirim ke karyawan.'}
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor="decide-notes">
              {decide?.mode === 'approve' ? 'Catatan (opsional)' : 'Alasan penolakan'}
            </Label>
            <Textarea id="decide-notes" rows={3} className="mt-1" value={notes}
              onChange={(e) => setNotes(e.target.value)} data-testid="decide-notes"
              placeholder={decide?.mode === 'approve' ? 'mis. maksimal 1 jam' : 'mis. sedang deadline produksi'} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDecide(null); setNotes(''); }}
              data-testid="decide-cancel">Batal</Button>
            <Button onClick={submitDecision} disabled={Boolean(busy)}
              variant={decide?.mode === 'approve' ? 'default' : 'destructive'}
              data-testid="decide-confirm">
              {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
              {decide?.mode === 'approve' ? 'Setujui' : 'Tolak'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, testid }) {
  return (
    <Card data-testid={testid}>
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon className="w-4 h-4" /> {label}
        </div>
        <p className="text-2xl font-bold mt-1">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}
