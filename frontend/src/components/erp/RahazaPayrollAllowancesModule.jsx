import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  HandCoins, Plus, Edit2, Trash2, RefreshCw, Save, X, Loader2,
  Users as UsersIcon, Building2, User as UserIcon, Info,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;

const SCOPE_CFG = {
  all:        { label: 'Semua Karyawan', icon: UsersIcon,   color: 'text-emerald-600 dark:text-emerald-400' },
  department: { label: 'Per Departemen', icon: Building2,   color: 'text-blue-600 dark:text-blue-400' },
  employee:   { label: 'Karyawan Tertentu', icon: UserIcon, color: 'text-purple-600 dark:text-purple-400' },
};

export default function RahazaPayrollAllowancesModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [items, setItems] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editDialog, setEditDialog] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${API}/api/rahaza/payroll-allowances`, { headers }),
        fetch(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers }),
      ]);
      const d1 = await r1.json();
      const d2 = await r2.json();
      setItems(d1.allowances || []);
      setEmployees(Array.isArray(d2) ? d2 : d2.items || d2.rows || d2.employees || []);
    } catch (e) {
      toast.error('Gagal memuat data: ' + (e.message || e));
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form) => {
    const isEdit = !!form.allowance_id;
    const url = isEdit
      ? `${API}/api/rahaza/payroll-allowances/${form.allowance_id}`
      : `${API}/api/rahaza/payroll-allowances`;
    const r = await fetch(url, { method: isEdit ? 'PUT' : 'POST', headers, body: JSON.stringify(form) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast.error(d.detail || 'Gagal simpan'); return; }
    toast.success(isEdit ? 'Tunjangan diupdate' : 'Tunjangan ditambahkan');
    setEditDialog(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus tunjangan ini? Tidak akan mempengaruhi payroll yang sudah final.')) return;
    const r = await fetch(`${API}/api/rahaza/payroll-allowances/${id}`, { method: 'DELETE', headers });
    if (!r.ok) { toast.error('Gagal hapus'); return; }
    toast.success('Tunjangan dihapus');
    load();
  };

  const handleToggleActive = async (item) => {
    const r = await fetch(`${API}/api/rahaza/payroll-allowances/${item.allowance_id}`, {
      method: 'PUT', headers,
      body: JSON.stringify({ ...item, is_active: !item.is_active }),
    });
    if (!r.ok) { toast.error('Gagal update status'); return; }
    load();
  };

  const departments = useMemo(() => {
    const set = new Set();
    employees.forEach(e => { if (e.department) set.add(e.department); });
    return Array.from(set).sort();
  }, [employees]);

  const { page, setPage, totalPages, total, paged } = useClientPagination(items, 10);
  return (
    <div className="space-y-6 p-6" data-testid="payroll-allowances-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <HandCoins className="w-6 h-6 text-emerald-600 dark:text-emerald-400" /> Tunjangan Tetap (Fixed Allowances)
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Konfigurasi tunjangan yang otomatis ditambahkan ke slip gaji · {items.length} template
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="allowances-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setEditDialog({})} data-testid="allowances-add">
            <Plus className="w-4 h-4 mr-1" /> Tambah Tunjangan
          </Button>
        </div>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-2 rounded-xl border border-blue-300 dark:border-blue-500/20 bg-blue-100 dark:bg-blue-500/5 px-4 py-3">
        <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <div className="text-xs text-muted-foreground">
          Tunjangan tetap akan otomatis dihitung & ditambahkan ke slip gaji saat payroll run dibuat.
          Gunakan cakupan <strong>Semua</strong> untuk tunjangan seluruh karyawan, atau pilih <strong>Per Departemen</strong>/<strong>Karyawan Tertentu</strong>
          untuk tunjangan spesifik (contoh: tunjangan jabatan, insentif supervisor).
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
              <th className="text-left px-4 py-3">Nama Tunjangan</th>
              <th className="text-left px-4 py-3">Jumlah</th>
              <th className="text-left px-4 py-3">Tipe</th>
              <th className="text-left px-4 py-3">Cakupan</th>
              <th className="text-left px-4 py-3">Aktif</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {paged.map(it => {
              const s = SCOPE_CFG[it.applicable_to] || SCOPE_CFG.all;
              const Icon = s.icon;
              return (
                <tr key={it.allowance_id} className="hover:bg-foreground/5 group">
                  <td className="px-4 py-3">
                    <div className="font-medium">{it.name}</div>
                    {it.description && <div className="text-xs text-muted-foreground">{it.description}</div>}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm">
                    {it.calc_type === 'percentage_gross'
                      ? <span className="text-amber-700 dark:text-amber-400">{it.amount}% dari Gross</span>
                      : <span className="text-emerald-600 dark:text-emerald-400">{fmtRp(it.amount)}</span>}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <span className="px-2 py-0.5 rounded-full bg-muted dark:bg-slate-500/20 text-foreground/70">
                      {it.calc_type === 'percentage_gross' ? '% Gross' : 'Tetap'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-xs">
                      <Icon className={`w-3.5 h-3.5 ${s.color}`} />
                      <span>{s.label}</span>
                      {it.applicable_to === 'department' && it.department && (
                        <span className="text-muted-foreground">· {it.department}</span>
                      )}
                      {it.applicable_to === 'employee' && (
                        <span className="text-muted-foreground">· {(it.employee_ids || []).length} karyawan</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Switch
                      checked={!!it.is_active}
                      onCheckedChange={() => handleToggleActive(it)}
                      data-testid={`allowance-toggle-${it.allowance_id}`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button size="icon" variant="ghost" className="h-7 w-7"
                        onClick={() => setEditDialog(it)}
                        data-testid={`allowance-edit-${it.allowance_id}`}>
                        <Edit2 className="w-3.5 h-3.5" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400"
                        onClick={() => handleDelete(it.allowance_id)}
                        data-testid={`allowance-delete-${it.allowance_id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="text-center py-12 text-muted-foreground">
                  <HandCoins className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>Belum ada template tunjangan</p>
                  <Button size="sm" className="mt-3" onClick={() => setEditDialog({})}>
                    Tambah Tunjangan Pertama
                  </Button>
                </td>
              </tr>
            )}
            {loading && (
              <tr><td colSpan={6} className="text-center py-8"><Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" /></td></tr>
            )}
          </tbody>
        </table>
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
      </div>

      {editDialog !== null && (
        <AllowanceDialog
          initial={editDialog}
          departments={departments}
          employees={employees}
          onSave={handleSave}
          onClose={() => setEditDialog(null)}
        />
      )}
    </div>
  );
}

function AllowanceDialog({ initial, departments, employees, onSave, onClose }) {
  const [form, setForm] = useState({
    name: '',
    amount: 0,
    calc_type: 'fixed',
    applicable_to: 'all',
    department: '',
    employee_ids: [],
    description: '',
    is_active: true,
    ...initial,
  });
  const [saving, setSaving] = useState(false);
  const [empSearch, setEmpSearch] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error('Nama tunjangan wajib diisi'); return; }
    if (form.applicable_to === 'department' && !form.department) {
      toast.error('Pilih departemen'); return;
    }
    if (form.applicable_to === 'employee' && (form.employee_ids || []).length === 0) {
      toast.error('Pilih minimal 1 karyawan'); return;
    }
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  const toggleEmp = (id) => {
    setForm(f => ({
      ...f,
      employee_ids: f.employee_ids.includes(id)
        ? f.employee_ids.filter(x => x !== id)
        : [...f.employee_ids, id],
    }));
  };

  const filteredEmps = employees.filter(e =>
    empSearch
      ? e.name.toLowerCase().includes(empSearch.toLowerCase()) ||
        e.employee_code.toLowerCase().includes(empSearch.toLowerCase())
      : true
  );

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{form.allowance_id ? 'Edit Tunjangan' : 'Tambah Tunjangan'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label>Nama Tunjangan <span className="text-red-700 dark:text-red-400">*</span></Label>
            <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Tunjangan Makan, Transport, Jabatan..." required data-testid="allowance-name" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Tipe Perhitungan</Label>
              <Select value={form.calc_type} onValueChange={v => setForm(f => ({ ...f, calc_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="fixed">Jumlah Tetap (Rp)</SelectItem>
                  <SelectItem value="percentage_gross">% dari Gross</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>{form.calc_type === 'percentage_gross' ? 'Persentase (%)' : 'Jumlah (Rp)'}</Label>
              <Input type="number" min={0} step={form.calc_type === 'percentage_gross' ? 0.1 : 1000}
                value={form.amount}
                onChange={e => setForm(f => ({ ...f, amount: parseFloat(e.target.value) || 0 }))}
                data-testid="allowance-amount" />
            </div>
          </div>

          <div className="space-y-1">
            <Label>Cakupan</Label>
            <Select value={form.applicable_to} onValueChange={v => setForm(f => ({ ...f, applicable_to: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Karyawan</SelectItem>
                <SelectItem value="department">Per Departemen</SelectItem>
                <SelectItem value="employee">Karyawan Tertentu</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {form.applicable_to === 'department' && (
            <div className="space-y-1">
              <Label>Departemen</Label>
              <Select value={form.department} onValueChange={v => setForm(f => ({ ...f, department: v }))}>
                <SelectTrigger><SelectValue placeholder="Pilih departemen..." /></SelectTrigger>
                <SelectContent>
                  {departments.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}

          {form.applicable_to === 'employee' && (
            <div className="space-y-2">
              <Label>Pilih Karyawan ({form.employee_ids.length} dipilih)</Label>
              <Input placeholder="Cari karyawan..." value={empSearch}
                onChange={e => setEmpSearch(e.target.value)} className="h-8" />
              <div className="max-h-52 overflow-y-auto rounded-xl border border-foreground/10 bg-foreground/5 divide-y divide-white/5">
                {filteredEmps.slice(0, 50).map(e => (
                  <label key={e.id} className="flex items-center gap-2 px-3 py-2 hover:bg-foreground/10 cursor-pointer text-sm">
                    <input type="checkbox" checked={form.employee_ids.includes(e.id)}
                      onChange={() => toggleEmp(e.id)} className="accent-emerald-500" />
                    <div className="flex-1">
                      <div className="font-medium text-xs">{e.name}</div>
                      <div className="text-[10px] text-muted-foreground">{e.employee_code} · {e.department || '—'}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1">
            <Label>Deskripsi (opsional)</Label>
            <Textarea value={form.description} rows={2}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Keterangan tambahan..." />
          </div>

          <div className="flex items-center gap-2">
            <Switch checked={!!form.is_active}
              onCheckedChange={v => setForm(f => ({ ...f, is_active: v }))} />
            <Label className="cursor-pointer">Aktif (ikut dihitung di payroll)</Label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              <X className="w-4 h-4 mr-1" /> Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="allowance-save">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
