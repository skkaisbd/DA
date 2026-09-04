import React, { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import axios from 'axios';
import { Clock, Plus, RefreshCw, Users, Calendar, Edit2, Trash2, ChevronRight, Moon, Sun, Sunset, AlertCircle } from 'lucide-react';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { StatCard } from '@/components/ui/data-card';

const API = process.env.REACT_APP_BACKEND_URL;
const DAYS_ID = { Mon: 'Sen', Tue: 'Sel', Wed: 'Rab', Thu: 'Kam', Fri: 'Jum', Sat: 'Sab', Sun: 'Min' };
const ALL_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function ShiftBadge({ shift }) {
  const isNight = (shift.start_time || '').startsWith('2') || (shift.start_time || '').startsWith('22') || (shift.start_time || '').startsWith('23');
  const isEvening = parseInt((shift.start_time || '0').split(':')[0]) >= 14;
  const Icon = isNight ? Moon : isEvening ? Sunset : Sun;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-foreground"
      style={{ backgroundColor: shift.color || '#64748b' }}
    >
      <Icon size={10} />
      {shift.shift_code}
    </span>
  );
}

function ShiftCard({ shift, onEdit, onDelete, assignCount }) {
  return (
    <div className="bg-card rounded-xl border border-border p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <ShiftBadge shift={shift} />
            {shift.is_overnight && <span className="text-[10px] text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">overnight</span>}
            {shift.is_default && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">default</span>}
          </div>
          <h3 className="font-semibold text-foreground text-sm mt-1">{shift.shift_name}</h3>
          <div className="flex items-center gap-1 mt-1 text-muted-foreground/60 text-xs">
            <Clock size={12} />
            <span>{shift.start_time} — {shift.end_time}</span>
            <span className="text-foreground/70 mx-1">•</span>
            <span>{shift.effective_hours} jam efektif</span>
          </div>
          <div className="flex gap-1 mt-2 flex-wrap">
            {ALL_DAYS.map(d => (
              <span key={d} className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                shift.days_active?.includes(d)
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-muted text-muted-foreground'
              }`}>{DAYS_ID[d]}</span>
            ))}
          </div>
          {assignCount > 0 && (
            <p className="text-xs text-muted-foreground mt-1.5 flex items-center gap-1">
              <Users size={11} /> {assignCount} karyawan aktif
            </p>
          )}
        </div>
        {!shift.is_default && (
          <div className="flex gap-1 ml-2">
            <button onClick={() => onEdit(shift)} className="p-1.5 text-muted-foreground hover:text-blue-500 rounded hover:bg-blue-50">
              <Edit2 size={14} />
            </button>
            <button onClick={() => onDelete(shift.id)} className="p-1.5 text-muted-foreground hover:text-red-700 dark:text-red-500 rounded hover:bg-red-50">
              <Trash2 size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ShiftForm({ initial, shifts, onSave, onCancel }) {
  const [form, setForm] = useState(initial || {
    shift_code: '', shift_name: '', start_time: '08:00', end_time: '17:00',
    break_duration_minutes: 60, days_active: ['Mon','Tue','Wed','Thu','Fri'],
    is_overnight: false, color: '#3b82f6', description: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleDay = (d) => setForm(p => ({
    ...p,
    days_active: p.days_active.includes(d) ? p.days_active.filter(x => x !== d) : [...p.days_active, d],
  }));

  const calcHours = () => {
    const [sh, sm] = (form.start_time || '08:00').split(':').map(Number);
    const [eh, em] = (form.end_time || '17:00').split(':').map(Number);
    let totalMin = (eh * 60 + em) - (sh * 60 + sm);
    if (form.is_overnight || totalMin <= 0) totalMin += 24 * 60;
    return Math.max(0, ((totalMin - (form.break_duration_minutes || 60)) / 60).toFixed(1));
  };

  const handleSubmit = async () => {
    if (!form.shift_code || !form.shift_name || !form.start_time || !form.end_time) {
      setError('Kode shift, nama, jam mulai, dan jam selesai wajib diisi.'); return;
    }
    setSaving(true); setError('');
    try {
      await onSave({ ...form, break_duration_minutes: parseInt(form.break_duration_minutes) });
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal menyimpan');
    } finally { setSaving(false); }
  };

  return (
    <div className="bg-card rounded-2xl border border-border p-5 space-y-4">
      <h2 className="font-semibold text-foreground">{initial ? 'Edit Shift' : 'Buat Shift Baru'}</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Kode Shift *</label>
          <input value={form.shift_code} onChange={e => setForm(p => ({ ...p, shift_code: e.target.value.toUpperCase() }))}
            placeholder="PAGI" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Nama Shift *</label>
          <input value={form.shift_name} onChange={e => setForm(p => ({ ...p, shift_name: e.target.value }))}
            placeholder="Shift Pagi" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Jam Mulai *</label>
          <input type="time" value={form.start_time} onChange={e => setForm(p => ({ ...p, start_time: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Jam Selesai *</label>
          <input type="time" value={form.end_time} onChange={e => setForm(p => ({ ...p, end_time: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Istirahat (menit)</label>
          <input type="number" value={form.break_duration_minutes} onChange={e => setForm(p => ({ ...p, break_duration_minutes: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Warna</label>
          <div className="flex items-center gap-2">
            <input type="color" value={form.color} onChange={e => setForm(p => ({ ...p, color: e.target.value }))}
              className="w-10 h-10 border border-border rounded-lg cursor-pointer" />
            <input value={form.color} onChange={e => setForm(p => ({ ...p, color: e.target.value }))}
              className="flex-1 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-muted-foreground/50 mb-2">Hari Aktif</label>
        <div className="flex gap-1 flex-wrap">
          {ALL_DAYS.map(d => (
            <button key={d} type="button" onClick={() => toggleDay(d)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                form.days_active.includes(d)
                  ? 'bg-blue-500 text-foreground border-blue-500'
                  : 'bg-card text-muted-foreground/60 border-border hover:border-blue-300'
              }`}>{DAYS_ID[d]}</button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.is_overnight} onChange={e => setForm(p => ({ ...p, is_overnight: e.target.checked }))}
            className="w-4 h-4 accent-purple-500" />
          <span className="text-sm text-muted-foreground/50">Shift Overnight (melewati tengah malam)</span>
        </label>
      </div>

      <p className="text-sm text-muted-foreground/60">
        Jam kerja efektif: <strong className="text-blue-600">{calcHours()} jam</strong>
      </p>

      <div>
        <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Deskripsi</label>
        <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
          rows={2} placeholder="Keterangan shift..."
          className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400" />
      </div>

      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg p-2 border border-red-200">{error}</div>}
      <div className="flex gap-3">
        <button onClick={onCancel} className="px-4 py-2 text-sm border border-border rounded-xl hover:bg-muted">Batal</button>
        <button onClick={handleSubmit} disabled={saving}
          className="flex-1 flex items-center justify-center gap-2 py-2 bg-blue-500 hover:bg-blue-600 text-foreground text-sm font-medium rounded-xl">
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
          {initial ? 'Simpan Perubahan' : 'Buat Shift'}
        </button>
      </div>
    </div>
  );
}

function AssignmentForm({ shifts, onSave, onCancel }) {
  const [form, setForm] = useState({ employee_id: '', shift_id: '', effective_from: new Date().toISOString().slice(0, 10), effective_until: '', department: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!form.employee_id || !form.shift_id || !form.effective_from) {
      setError('ID Karyawan, shift, dan tanggal mulai wajib diisi.'); return;
    }
    setSaving(true); setError('');
    try {
      await onSave({ ...form, effective_until: form.effective_until || null });
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal assign shift');
    } finally { setSaving(false); }
  };

  return (
    <div className="bg-card rounded-2xl border border-border p-5 space-y-4">
      <h2 className="font-semibold text-foreground">Assign Shift ke Karyawan</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">ID Karyawan *</label>
          <input value={form.employee_id} onChange={e => setForm(p => ({ ...p, employee_id: e.target.value }))}
            placeholder="emp-001" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Shift *</label>
          <SmartNativeSelect value={form.shift_id} onChange={e => setForm(p => ({ ...p, shift_id: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">-- Pilih Shift --</option>
            {shifts.filter(s => !s.is_default).map(s => (
              <option key={s.id} value={s.id}>{s.shift_code} — {s.shift_name} ({s.start_time}–{s.end_time})</option>
            ))}
          </SmartNativeSelect>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Berlaku Mulai *</label>
          <input type="date" value={form.effective_from} onChange={e => setForm(p => ({ ...p, effective_from: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Berlaku Hingga (opsional)</label>
          <input type="date" value={form.effective_until} onChange={e => setForm(p => ({ ...p, effective_until: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Departemen</label>
          <input value={form.department} onChange={e => setForm(p => ({ ...p, department: e.target.value }))}
            placeholder="Produksi / HR / Keuangan..." className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground/50 mb-1">Catatan</label>
          <input value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
      </div>
      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg p-2 border border-red-200">{error}</div>}
      <div className="flex gap-3">
        <button onClick={onCancel} className="px-4 py-2 text-sm border border-border rounded-xl hover:bg-muted">Batal</button>
        <button onClick={handleSubmit} disabled={saving}
          className="flex-1 flex items-center justify-center gap-2 py-2 bg-emerald-500 hover:bg-emerald-600 text-foreground text-sm font-medium rounded-xl">
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Users size={14} />} Assign Shift
        </button>
      </div>
    </div>
  );
}

export default function HRShiftManagementModule({ user }) {
  const [shifts, setShifts] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('shifts');
  const [view, setView] = useState('list');
  const [editShift, setEditShift] = useState(null);
  const [assignCounts, setAssignCounts] = useState({});
  const token = localStorage.getItem('erp_token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const isAdmin = ['superadmin', 'admin', 'owner', 'hr'].includes((user?.role || '').toLowerCase());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [shiftRes, assignRes, sumRes] = await Promise.all([
        axios.get(`${API}/api/hr/shifts`, { headers }),
        axios.get(`${API}/api/hr/shifts/assignments`, { headers }),
        axios.get(`${API}/api/hr/shifts/summary`, { headers }),
      ]);
      setShifts(shiftRes.data?.data || []);
      setAssignments(assignRes.data?.data || []);
      setSummary(sumRes.data?.data || null);
      // Build assign count map
      const counts = {};
      for (const a of assignRes.data?.data || []) {
        counts[a.shift_id] = (counts[a.shift_id] || 0) + 1;
      }
      setAssignCounts(counts);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const handleCreateShift = async (data) => {
    await axios.post(`${API}/api/hr/shifts`, data, { headers });
    setView('list');
    load();
  };

  const handleUpdateShift = async (data) => {
    await axios.put(`${API}/api/hr/shifts/${editShift.id}`, data, { headers });
    setEditShift(null);
    setView('list');
    load();
  };

  const handleDeleteShift = async (id) => {
    if (!window.confirm('Nonaktifkan shift ini?')) return;
    await axios.delete(`${API}/api/hr/shifts/${id}`, { headers });
    load();
  };

  const handleAssign = async (data) => {
    await axios.post(`${API}/api/hr/shifts/assignments`, data, { headers });
    setView('list');
    load();
  };

  const handleSeedDefaults = async () => {
    await axios.post(`${API}/api/hr/shifts/seed-defaults`, {}, { headers });
    load();
  };

  const nonDefaultShifts = shifts.filter(s => !s.is_default);

  const { page, setPage, totalPages, total, paged } = useClientPagination(assignments, 10);
  return (
    <div className="min-h-screen bg-muted p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Clock className="text-blue-500" size={22} /> Manajemen Shift Karyawan
          </h1>
          <p className="text-sm text-muted-foreground/60 mt-0.5">Kelola template shift dan assignment karyawan</p>
        </div>
        <button onClick={load} className="p-2 text-muted-foreground hover:text-muted-foreground/50 rounded-lg hover:bg-card border border-border">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Summary cards */}
      {!loading && summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Shift Aktif',    value: summary.total_shifts,            tone: 'primary' },
            { label: 'Karyawan Ter-assign',  value: summary.total_assigned_employees, tone: 'success' },
            { label: 'Shift Terbanyak',      value: summary.by_shift?.[0]?.shift_name || '-', tone: 'warning', compact: true },
            { label: 'Fallback Default',     value: 'Aktif',                          tone: 'neutral', compact: true },
          ].map(s => (
            <StatCard
              key={s.label}
              label={s.label}
              value={s.value}
              tone={s.tone}
              compact={s.compact}
              data-testid={`shift-stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`}
            />
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-card border border-border rounded-xl p-1 w-fit">
        {[{key:'shifts',label:'Template Shift'},{key:'assignments',label:'Assignment'}].map(t => (
          <button key={t.key} onClick={() => { setTab(t.key); setView('list'); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-blue-500 text-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <RefreshCw size={24} className="animate-spin text-blue-600 dark:text-blue-400" />
          <span className="ml-3 text-muted-foreground/60">Memuat...</span>
        </div>
      ) : tab === 'shifts' ? (
        <>
          {view === 'form' ? (
            <ShiftForm
              initial={editShift}
              shifts={nonDefaultShifts}
              onSave={editShift ? handleUpdateShift : handleCreateShift}
              onCancel={() => { setView('list'); setEditShift(null); }}
            />
          ) : (
            <>
              <div className="flex gap-2 mb-4">
                {isAdmin && (
                  <>
                    <button onClick={() => { setEditShift(null); setView('form'); }}
                      className="flex items-center gap-1.5 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-foreground text-sm font-medium rounded-xl">
                      <Plus size={15} /> Shift Baru
                    </button>
                    {nonDefaultShifts.length === 0 && (
                      <button onClick={handleSeedDefaults}
                        className="flex items-center gap-1.5 px-4 py-2 bg-muted hover:bg-muted text-foreground text-sm font-medium rounded-xl border border-border">
                        Seed Default Shifts
                      </button>
                    )}
                  </>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {shifts.map(shift => (
                  <ShiftCard
                    key={shift.id}
                    shift={shift}
                    assignCount={assignCounts[shift.id] || 0}
                    onEdit={(s) => { setEditShift(s); setView('form'); }}
                    onDelete={handleDeleteShift}
                  />
                ))}
              </div>
              {shifts.length === 0 && (
                <div className="text-center py-20 text-muted-foreground">
                  <Clock size={40} className="mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Belum ada shift template</p>
                  <button onClick={handleSeedDefaults} className="mt-2 text-blue-500 underline text-sm">
                    Seed 5 default shifts (Pagi, Siang, Malam, Normal, Fleksibel)
                  </button>
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <>
          {view === 'assign' ? (
            <AssignmentForm shifts={shifts} onSave={handleAssign} onCancel={() => setView('list')} />
          ) : (
            <>
              <div className="flex gap-2 mb-4">
                {isAdmin && (
                  <button onClick={() => setView('assign')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-foreground text-sm font-medium rounded-xl">
                    <Users size={15} /> Assign Shift
                  </button>
                )}
              </div>
              {assignments.length === 0 ? (
                <div className="text-center py-20 text-muted-foreground">
                  <Users size={40} className="mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Belum ada assignment shift</p>
                  <p className="text-sm mt-1">Semua karyawan menggunakan shift default (08:00–17:00)</p>
                </div>
              ) : (
                <div className="bg-card rounded-xl border border-border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted border-b border-border">
                      <tr>
                        {['ID Karyawan','Shift','Dept','Berlaku Mulai','Berlaku Hingga','Status'].map(h => (
                          <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground/60">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {paged.map(a => (
                        <tr key={a.id} className="hover:bg-muted">
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground/50">{a.employee_id}</td>
                          <td className="px-4 py-3">
                            <ShiftBadge shift={{ shift_code: a.shift_code, color: a.shift_color }} />
                          </td>
                          <td className="px-4 py-3 text-muted-foreground/50">{a.department || '—'}</td>
                          <td className="px-4 py-3 text-muted-foreground/50">{a.effective_from}</td>
                          <td className="px-4 py-3 text-muted-foreground">{a.effective_until || 'Sampai dicabut'}</td>
                          <td className="px-4 py-3">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              a.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground'
                            }`}>{a.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
