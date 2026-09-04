import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Edit2, Trash2, RefreshCw, Wallet, Users, UserCog } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import ImportExportToolbar from './ImportExportToolbar';

const SCHEMES = [
  { code: 'pcs', label: 'Borongan Pcs', color: 'text-emerald-300' },
  { code: 'hourly', label: 'Borongan Jam', color: 'text-blue-300' },
  { code: 'weekly', label: 'Mingguan', color: 'text-amber-300' },
  { code: 'monthly', label: 'Bulanan', color: 'text-primary' },
];
const SCHEME_META = Object.fromEntries(SCHEMES.map(s => [s.code, s]));

const PERIOD_TYPES = [
  { code: 'weekly', label: 'Mingguan' },
  { code: 'monthly', label: 'Bulanan' },
];

const WEEK_DAYS = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'];

export default function RahazaPayrollProfilesModule({ token }) {
  const [profiles, setProfiles] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [p, e, pr] = await Promise.all([
        fetch('/api/rahaza/payroll-profiles', { headers }).then(r => r.json()),
        fetch('/api/rahaza/employees', { headers }).then(r => r.json()),
        fetch('/api/rahaza/processes', { headers }).then(r => r.json()),
      ]);
      setProfiles(Array.isArray(p) ? p : []);
      setEmployees(Array.isArray(e) ? e : (e.items || e.rows || []));
      setProcesses(Array.isArray(pr) ? pr : []);
    } catch { setError('Gagal memuat data'); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const save = async (body) => {
    setError('');
    const r = await fetch('/api/rahaza/payroll-profiles', { method: 'POST', headers, body: JSON.stringify(body) });
    if (!r.ok) { setError(`Gagal simpan (HTTP ${r.status})`); return; }
    setEditing(null); fetchAll();
  };

  const del = async (id) => {
    if (!window.confirm('Hapus profile payroll ini?')) return;
    const r = await fetch(`/api/rahaza/payroll-profiles/${id}`, { method: 'DELETE', headers });
    if (r.ok) fetchAll(); else setError(`Gagal hapus (HTTP ${r.status})`);
  };

  const empsWithoutProfile = employees.filter(e => e.active && !profiles.some(p => p.employee_id === e.id));

  const { page, setPage, totalPages, total, paged } = useClientPagination(profiles, 10);
  return (
    <div className="space-y-5" data-testid="rahaza-payroll-profiles-page">
      <PageHeader
        icon={UserCog}
        eyebrow="Portal SDM · Penggajian"
        title="Profil Gaji Karyawan"
        subtitle="Konfigurasi skema payroll, periode, dan rate per pegawai. Setiap pegawai dapat punya skema berbeda."
        actions={
          <>
            <ImportExportToolbar collectionKey="payroll_profiles" label="Profil Gaji Karyawan" onImported={fetchAll} />
            <Button variant="ghost" onClick={fetchAll} className="h-9 border border-[var(--glass-border)]" data-testid="pp-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh</Button>
            <Button onClick={() => setEditing({ employee_id: '', pay_scheme: 'monthly', period_type: 'monthly', base_rate: 0, overtime_rate: 0, cutoff_config: {}, pcs_process_rates: [] })} className="h-9" data-testid="pp-add"><Plus className="w-3.5 h-3.5 mr-1.5" /> Tambah Profil</Button>
          </>
        }
      />

      {error && <div className="bg-[hsl(var(--destructive)/0.12)] border border-[hsl(var(--destructive)/0.22)] rounded-lg p-3 text-sm text-[hsl(var(--destructive))]">{error}</div>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <StatTile label="Total Profile" value={profiles.length} accent="primary" testId="pp-count-total" />
        {SCHEMES.map(s => {
          const n = profiles.filter(p => p.pay_scheme === s.code).length;
          return <StatTile key={s.code} label={s.label} value={n} accent={s.code === 'pcs' ? 'success' : s.code === 'monthly' ? 'primary' : 'default'} />;
        })}
      </div>

      {empsWithoutProfile.length > 0 && (
        <div className="bg-[hsl(var(--warning)/0.10)] border border-[hsl(var(--warning)/0.22)] rounded-lg p-3 text-sm text-[hsl(var(--warning))] flex items-center gap-2">
          <Users className="w-3.5 h-3.5" />
          {empsWithoutProfile.length} pegawai aktif belum punya profile payroll.
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>
      ) : (
        <GlassCard className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3">Karyawan</th>
                  <th className="px-3 py-3">Skema</th>
                  <th className="px-3 py-3">Periode</th>
                  <th className="px-3 py-3 text-right">Tarif Dasar</th>
                  <th className="px-3 py-3 text-right">Tarif Lembur</th>
                  <th className="px-3 py-3">Tarif per Proses</th>
                  <th className="px-3 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {profiles.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">Belum ada profile. Tekan “Tambah Profile”.</td></tr>
                ) : paged.map(p => {
                  const sm = SCHEME_META[p.pay_scheme] || SCHEMES[3];
                  return (
                    <tr key={p.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]" data-testid={`pp-row-${p.employee_code}`}>
                      <td className="px-4 py-2">
                        <div className="font-mono text-xs text-foreground">{p.employee_code}</div>
                        <div className="text-xs text-muted-foreground">{p.employee_name}</div>
                      </td>
                      <td className="px-3 py-2"><span className={`text-xs font-semibold ${sm.color}`}>{sm.label}</span></td>
                      <td className="px-3 py-2 text-xs text-foreground">{p.period_type === 'weekly' ? `Mingguan (${WEEK_DAYS[p.cutoff_config?.week_start_day ?? 1]} start)` : `Bulanan (start day ${p.cutoff_config?.start_day ?? 1})`}</td>
                      <td className="px-3 py-2 text-right font-mono text-foreground">Rp {Number(p.base_rate || 0).toLocaleString('id-ID')}</td>
                      <td className="px-3 py-2 text-right font-mono text-foreground">Rp {Number(p.overtime_rate || 0).toLocaleString('id-ID')}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">{(p.pcs_process_rates || []).length > 0 ? `${p.pcs_process_rates.length} override` : '—'}</td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => setEditing({ ...p })} className="inline-flex items-center text-xs text-primary hover:underline mr-3" data-testid={`pp-edit-${p.employee_code}`}><Edit2 className="w-3 h-3 mr-1" />Ubah</button>
                        <button onClick={() => del(p.id)} className="inline-flex items-center text-xs text-red-300 hover:underline" data-testid={`pp-del-${p.employee_code}`}><Trash2 className="w-3 h-3 mr-1" />Hapus</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        </GlassCard>
      )}

      {editing && (
        <ProfileEditor
          profile={editing}
          employees={employees}
          processes={processes}
          isNew={!editing.id}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </div>
  );
}

function ProfileEditor({ profile, employees, processes, isNew, onClose, onSave }) {
  const [state, setState] = useState(profile);
  useEffect(() => setState(profile), [profile]);
  const update = (k, v) => setState(s => ({ ...s, [k]: v }));
  const updateCutoff = (k, v) => setState(s => ({ ...s, cutoff_config: { ...(s.cutoff_config || {}), [k]: v } }));

  const addProcRate = () => {
    setState(s => ({ ...s, pcs_process_rates: [...(s.pcs_process_rates || []), { process_id: '', process_code: '', rate: 0 }] }));
  };
  const removeProcRate = (i) => setState(s => ({ ...s, pcs_process_rates: s.pcs_process_rates.filter((_, idx) => idx !== i) }));
  const updateProcRate = (i, k, v) => setState(s => ({ ...s, pcs_process_rates: s.pcs_process_rates.map((r, idx) => idx === i ? { ...r, [k]: v } : r) }));

  const submit = () => {
    if (!state.employee_id) { alert('Pilih karyawan dulu'); return; }
    onSave({
      employee_id: state.employee_id,
      pay_scheme: state.pay_scheme,
      period_type: state.period_type,
      cutoff_config: state.cutoff_config || {},
      base_rate: Number(state.base_rate) || 0,
      overtime_rate: Number(state.overtime_rate) || 0,
      pcs_process_rates: (state.pcs_process_rates || []).filter(r => r.process_id),
      notes: state.notes || '',
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-foreground mb-4">{isNew ? 'Tambah' : 'Edit'} Profil Gaji</h2>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Karyawan</label>
              <SmartNativeSelect value={state.employee_id || ''} onChange={e => update('employee_id', e.target.value)} disabled={!isNew} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground disabled:opacity-60" data-testid="pp-edit-employee">
                <option value="">— Pilih karyawan —</option>
                {employees.filter(e => e.active).map(e => <option key={e.id} value={e.id}>{`${e.employee_code} · ${e.name}`}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Skema Gaji</label>
              <select value={state.pay_scheme} onChange={e => update('pay_scheme', e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="pp-edit-scheme">
                {SCHEMES.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Tipe Periode</label>
              <select value={state.period_type} onChange={e => update('period_type', e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground">
                {PERIOD_TYPES.map(p => <option key={p.code} value={p.code}>{p.label}</option>)}
              </select>
            </div>
            <div>
              {state.period_type === 'weekly' ? (
                <>
                  <label className="text-xs text-muted-foreground uppercase block mb-1">Hari Mulai Minggu</label>
                  <select value={state.cutoff_config?.week_start_day ?? 1} onChange={e => updateCutoff('week_start_day', Number(e.target.value))} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground">
                    {WEEK_DAYS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                  </select>
                </>
              ) : (
                <>
                  <label className="text-xs text-muted-foreground uppercase block mb-1">Tanggal Mulai Bulan</label>
                  <GlassInput type="number" min={1} max={28} value={state.cutoff_config?.start_day ?? 1} onChange={e => updateCutoff('start_day', Number(e.target.value))} />
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Tarif Dasar (Rp) — per {state.pay_scheme === 'pcs' ? 'pcs' : state.pay_scheme === 'hourly' ? 'jam' : state.pay_scheme === 'weekly' ? 'minggu' : 'bulan'}</label>
              <GlassInput type="number" min={0} step="100" value={state.base_rate || 0} onChange={e => update('base_rate', e.target.value)} data-testid="pp-edit-base-rate" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase block mb-1">Tarif Lembur (Rp/jam)</label>
              <GlassInput type="number" min={0} step="100" value={state.overtime_rate || 0} onChange={e => update('overtime_rate', e.target.value)} data-testid="pp-edit-ot-rate" />
            </div>
          </div>

          {state.pay_scheme === 'pcs' && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs text-muted-foreground uppercase">Rate Override per Proses (opsional)</label>
                <Button variant="ghost" className="h-7 px-2 text-xs border border-[var(--glass-border)]" onClick={addProcRate}><Plus className="w-3 h-3 mr-1" />Tambah</Button>
              </div>
              <div className="space-y-2">
                {(state.pcs_process_rates || []).map((r, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <SmartNativeSelect value={r.process_id} onChange={e => {
                      const p = processes.find(x => x.id === e.target.value);
                      updateProcRate(i, 'process_id', e.target.value);
                      if (p) updateProcRate(i, 'process_code', p.code);
                    }} className="flex-1 h-9 px-2 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground">
                      <option value="">— Pilih proses —</option>
                      {processes.map(p => <option key={p.id} value={p.id}>{`${p.code} · ${p.name}`}</option>)}
                    </SmartNativeSelect>
                    <GlassInput type="number" min={0} step="50" placeholder="Rate/pcs" value={r.rate} onChange={e => updateProcRate(i, 'rate', Number(e.target.value))} className="w-28 h-9 text-xs" />
                    <button onClick={() => removeProcRate(i)} className="h-9 w-9 text-red-300 hover:bg-red-400/10 rounded border border-[var(--glass-border)]"><Trash2 className="w-3.5 h-3.5 mx-auto" /></button>
                  </div>
                ))}
                {(state.pcs_process_rates || []).length === 0 && <div className="text-xs text-muted-foreground">Tidak ada override. Base rate berlaku untuk semua proses.</div>}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2 mt-6 justify-end">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button>
          <Button onClick={submit} data-testid="pp-edit-save">Simpan</Button>
        </div>
      </GlassCard>
    </div>
  );
}
