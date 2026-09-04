import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Calendar, RefreshCw, Loader2, Users, TrendingUp, Edit2, Save, X,
  CalendarDays, Hourglass, CheckCircle2, AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

export default function HRLeaveBalancesModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [allocDialog, setAllocDialog] = useState(false);
  const [editDialog, setEditDialog] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const r = await axios.get(`${API}/api/rahaza/leave-balances?year=${year}`, { headers });
      setBalances(r.data.balances || []);
    } catch (e) {
      // RC-22: JANGAN telan error jadi empty-state menyesatkan — tampilkan error nyata
      const msg = e.response?.data?.detail || e.message || 'Gagal memuat saldo cuti';
      setLoadError(`Gagal memuat saldo cuti (${e.response?.status || 'network'}): ${msg}`);
      setBalances([]);
    } finally { setLoading(false); }
  }, [headers, year]);

  useEffect(() => { load(); }, [load]);

  const handleAllocate = async (forceReset) => {
    try {
      const { data } = await axios.post(
        `${API}/api/rahaza/leave-balances/allocate-year`,
        { year, force_reset: forceReset },
        { headers }
      );
      toast.success(`Alokasi: ${data.created} baru, ${data.updated} direset, ${data.total_employees} karyawan × ${data.total_leave_types} tipe cuti`);
      setAllocDialog(false);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Gagal alokasi'); }
  };

  const handleAdjust = async (form) => {
    try {
      await axios.put(`${API}/api/rahaza/leave-balances/${form.id}`,
        { adjust_delta: form.delta, reason: form.reason }, { headers });
      toast.success('Saldo diupdate');
      setEditDialog(null);
      load();
    } catch (e) { toast.error('Gagal update'); }
  };

  // Group by employee
  const byEmployee = useMemo(() => {
    const m = {};
    balances.forEach(b => {
      if (!b.employee) return;
      const eid = b.employee_id;
      m[eid] = m[eid] || { employee: b.employee, rows: [] };
      m[eid].rows.push(b);
    });
    return Object.values(m);
  }, [balances]);

  return (
    <div className="space-y-6 p-6" data-testid="leave-balances-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Calendar className="w-6 h-6 text-emerald-600 dark:text-emerald-400" /> Saldo Cuti Karyawan
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Tracking kuota cuti per karyawan per tahun · {byEmployee.length} karyawan tahun {year}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <Select value={String(year)} onValueChange={v => setYear(Number(v))}>
            <SelectTrigger className="w-28 h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[2024, 2025, 2026, 2027].map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setAllocDialog(true)} data-testid="allocate-year">
            <CalendarDays className="w-4 h-4 mr-1" /> Alokasi Tahunan
          </Button>
        </div>
      </div>

      {/* RC-22: banner error nyata — jangan tampilkan empty-state menyesatkan saat backend gagal */}
      {loadError && !loading && (
        <div className="rounded-lg border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-800 p-4 text-sm text-red-700 dark:text-red-300" data-testid="leave-balances-error">
          <p className="font-semibold">Terjadi kesalahan saat memuat data</p>
          <p className="mt-1">{loadError}</p>
        </div>
      )}

      {byEmployee.length === 0 && !loading && !loadError && (
        <div className="text-center py-20 text-muted-foreground">
          <Calendar className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>Belum ada saldo cuti untuk tahun {year}</p>
          <p className="text-xs mt-1">Klik "Alokasi Tahunan" untuk generate saldo semua karyawan.</p>
        </div>
      )}

      {loading && <div className="text-center py-10"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" /></div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {byEmployee.map(({ employee, rows }) => (
          <div key={employee.id} className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-semibold text-sm">{employee.name}</div>
                <div className="text-xs text-muted-foreground font-mono">{employee.employee_code}</div>
              </div>
            </div>
            <div className="space-y-2">
              {rows.map(r => {
                const pct = r.allocated > 0 ? Math.round((r.used / r.allocated) * 100) : 0;
                const remaining = r.remaining;
                return (
                  <div key={r.id} className="flex items-center gap-2 text-xs">
                    <div className="flex-shrink-0 w-24 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ background: r.leave_type?.color || '#6b7280' }} />
                      <span className="truncate">{r.leave_type?.name || '?'}</span>
                    </div>
                    <div className="flex-1 h-2 bg-foreground/10 rounded-full overflow-hidden">
                      <div className={`h-full ${pct > 80 ? 'bg-red-400' : pct > 50 ? 'bg-amber-400' : 'bg-emerald-400'}`}
                        style={{ width: `${Math.min(pct, 100)}%` }} />
                    </div>
                    <div className="w-20 text-right font-mono text-[10px]">
                      <span className={remaining < 0 ? 'text-red-700 dark:text-red-400' : 'text-foreground'}>{remaining}</span>
                      <span className="text-muted-foreground">/{r.allocated}</span>
                    </div>
                    <Button size="icon" variant="ghost" className="h-5 w-5"
                      onClick={() => setEditDialog({ ...r })}>
                      <Edit2 className="w-3 h-3" />
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {allocDialog && (
        <AllocateDialog year={year} onSave={handleAllocate} onClose={() => setAllocDialog(false)} />
      )}
      {editDialog && (
        <EditBalanceDialog balance={editDialog} onSave={handleAdjust} onClose={() => setEditDialog(null)} />
      )}
    </div>
  );
}

function AllocateDialog({ year, onSave, onClose }) {
  const [forceReset, setForceReset] = useState(false);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Alokasi Saldo Cuti Tahun {year}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="rounded-lg border border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5 p-3 text-xs">
            <AlertCircle className="inline w-3.5 h-3.5 mr-1 text-amber-700 dark:text-amber-400" />
            Aksi ini akan <strong>generate saldo cuti</strong> untuk semua karyawan aktif × semua tipe cuti untuk tahun {year}, berdasarkan <code>quota_default</code> setiap tipe cuti.
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={forceReset} onChange={e => setForceReset(e.target.checked)} className="accent-red-500" />
            <span className="text-xs text-red-700 dark:text-red-400">Force reset: hapus saldo yang sudah ada (used = 0)</span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={() => onSave(forceReset)} data-testid="allocate-confirm">
            <CalendarDays className="w-4 h-4 mr-1" /> Alokasikan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditBalanceDialog({ balance, onSave, onClose }) {
  const [delta, setDelta] = useState(0);
  const [reason, setReason] = useState('');
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust Saldo: {balance.leave_type?.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2 text-xs">
            <div>Karyawan: <strong>{balance.employee?.name}</strong></div>
            <div>Saldo saat ini: <strong>{balance.remaining}</strong> / {balance.allocated} hari ({balance.used} terpakai)</div>
          </div>
          <div className="space-y-1">
            <Label>Delta (+/-)</Label>
            <Input type="number" value={delta} onChange={e => setDelta(Number(e.target.value))}
              placeholder="Contoh: +3 menambah, -2 mengurangi" />
            <div className="text-[10px] text-muted-foreground">Saldo baru akan: <strong>{balance.allocated + delta}</strong> hari</div>
          </div>
          <div className="space-y-1">
            <Label>Alasan *</Label>
            <Input value={reason} onChange={e => setReason(e.target.value)}
              placeholder="Contoh: Bonus cuti kinerja, kompensasi hari libur" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={() => onSave({ id: balance.id, delta, reason })}
            disabled={!delta || !reason} data-testid="adjust-save">
            <Save className="w-4 h-4 mr-1" /> Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
