import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import {
  Building2, Users, Plus, X, RefreshCw, ChevronRight, Pencil, Trash2,
  TrendingUp, AlertCircle, BarChart3, TreePine, Target, AlertTriangle,
  CheckCircle2, ChevronDown, ChevronUp, Layers
} from 'lucide-react';
import { OrgNode } from './OrgNode';
import { Skeleton } from '@/components/ui/skeleton';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = (path, opts = {}) => fetch(`${BACKEND_URL}/api/dewi/org${path}`, opts);

const TYPE_CONFIG = {
  company:    { label: 'Perusahaan', color: '#6366f1', bg: '#6366f115' },
  division:   { label: 'Divisi',     color: '#10b981', bg: '#10b98115' },
  department: { label: 'Departemen', color: '#f59e0b', bg: '#f59e0b15' },
  team:       { label: 'Tim',        color: '#8b5cf6', bg: '#8b5cf615' },
  section:    { label: 'Seksi',      color: '#14b8a6', bg: '#14b8a615' },
};

const TYPE_LEVELS = ['company','division','department','team','section'];

function TypeBadge({ type }) {
  const c = TYPE_CONFIG[type] || { label: type, color: '#64748b', bg: '#64748b15' };
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: c.bg, color: c.color }}>{c.label}</span>
  );
}

export default function HROrgChartModule({ token }) {
  const [tab, setTab] = useState('chart'); // chart | units | positions | headcount
  const [chart, setChart] = useState(null);
  const [units, setUnits] = useState([]);
  const [positions, setPositions] = useState([]);
  const [headcount, setHeadcount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [showUnitForm, setShowUnitForm] = useState(false);
  const [showPosForm, setShowPosForm] = useState(false);
  const [editUnit, setEditUnit] = useState(null);
  const [unitForm, setUnitForm] = useState({ name: '', code: '', type: 'department', parent_id: '', head_employee_name: '', headcount_target: 0, color: '', description: '' });
  const [posForm, setPosForm] = useState({ title: '', unit_id: '', grade: 1, headcount_target: 1, salary_grade: '' });
  const [saving, setSaving] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [cRes, uRes, pRes, hRes] = await Promise.all([
        API(`/chart`, { headers }),
        API(`/units`, { headers }),
        API(`/positions`, { headers }),
        API(`/headcount`, { headers }),
      ]);
      const [cd, ud, pd, hd] = await Promise.all([cRes.json(), uRes.json(), pRes.json(), hRes.json()]);
      setChart(cd);
      setUnits(ud.units || []);
      setPositions(pd.positions || []);
      setHeadcount(hd);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSeed = async () => {
    setSeeding(true);
    await API(`/seed`, { method: 'POST', headers });
    setSeeding(false);
    fetchAll();
  };

  const openUnitForm = (u = null) => {
    setEditUnit(u);
    setUnitForm(u ? {
      name: u.name, code: u.code, type: u.type, parent_id: u.parent_id || '',
      head_employee_name: u.head_employee_name, headcount_target: u.headcount_target, color: u.color, description: u.description
    } : { name: '', code: '', type: 'department', parent_id: '', head_employee_name: '', headcount_target: 0, color: '', description: '' });
    setShowUnitForm(true);
  };

  const handleSaveUnit = async () => {
    setSaving(true);
    try {
      const body = { ...unitForm, parent_id: unitForm.parent_id || null };
      if (editUnit) {
        await API(`/units/${editUnit.unit_id}`, { method: 'PUT', headers, body: JSON.stringify(body) });
      } else {
        await API(`/units`, { method: 'POST', headers, body: JSON.stringify(body) });
      }
      setShowUnitForm(false);
      fetchAll();
    } catch {} finally { setSaving(false); }
  };

  const handleDeleteUnit = async (uid) => {
    if (!window.confirm('Hapus unit ini?')) return;
    try {
      const r = await API(`/units/${uid}`, { method: 'DELETE', headers });
      const d = await r.json();
      if (!d.ok) { alert(d.detail || 'Tidak bisa dihapus'); return; }
      fetchAll();
    } catch {}
  };

  const handleSavePos = async () => {
    setSaving(true);
    try {
      const unit = units.find(u => u.unit_id === posForm.unit_id);
      const body = { ...posForm, unit_name: unit?.name || '' };
      await API(`/positions`, { method: 'POST', headers, body: JSON.stringify(body) });
      setShowPosForm(false);
      fetchAll();
    } catch {} finally { setSaving(false); }
  };

  // RC-UI-03: client-side pagination (10/page) for units & positions tables (top-level, before early return)
  const unitsPg     = useClientPagination(units, 10);
  const positionsPg = useClientPagination(positions, 10);

  if (loading) return (
    <div className="space-y-4 p-4" data-testid="hr-org-skeleton">
      <Skeleton className="h-16 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );

  const chartTree = chart?.tree ? (Array.isArray(chart.tree) ? chart.tree : [chart.tree]) : [];

  return (
    <div className="space-y-5" data-testid="hr-org-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><TreePine className="w-6 h-6 text-primary" />Struktur Organisasi</h1>
          <p className="text-muted-foreground text-sm">Bagan organisasi, unit, posisi, dan headcount planning</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleSeed} disabled={seeding}
            className="h-9 px-3 rounded-lg border border-dashed border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground">
            {seeding ? 'Memuat...' : 'Muat Demo'}
          </button>
          <button onClick={fetchAll} className="h-9 w-9 rounded-lg border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => openUnitForm()}
            className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Tambah Unit
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <GlassCard hover={false} className="p-4 text-center">
          <p className="text-2xl font-bold text-primary">{units.length}</p>
          <p className="text-xs text-muted-foreground">Total Unit</p>
        </GlassCard>
        <GlassCard hover={false} className="p-4 text-center">
          <p className="text-2xl font-bold">{positions.length}</p>
          <p className="text-xs text-muted-foreground">Total Posisi</p>
        </GlassCard>
        <GlassCard hover={false} className="p-4 text-center">
          <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{headcount?.summary?.total_actual || 0}</p>
          <p className="text-xs text-muted-foreground">Karyawan Aktual</p>
        </GlassCard>
        <GlassCard hover={false} className="p-4 text-center">
          <p className="text-2xl font-bold" style={{ color: headcount?.summary?.gap > 0 ? '#f59e0b' : '#10b981' }}>
            {headcount?.summary?.gap ?? 0}
          </p>
          <p className="text-xs text-muted-foreground">Gap Headcount</p>
        </GlassCard>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[var(--nav-pill-bg)] border border-[var(--glass-border)] w-fit">
        {[['chart','Bagan Org'],['units','Unit'],['positions','Posisi'],['headcount','Headcount']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              tab === k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}>{l}</button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 text-sm text-red-700 dark:text-red-400">
          <AlertCircle className="w-4 h-4" />{error}
        </div>
      )}

      {/* ─── ORG CHART ───────────────────────────────────── */}
      {tab === 'chart' && (
        <GlassCard hover={false} className="p-5">
          {chartTree.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <TreePine className="w-10 h-10 text-muted-foreground/30" />
              <p className="text-muted-foreground text-sm">Belum ada struktur organisasi. Klik "Muat Demo" untuk mulai.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {chartTree.map(node => (
                <OrgNode key={node.unit_id} node={node} depth={0} />
              ))}
            </div>
          )}
        </GlassCard>
      )}

      {/* ─── UNITS ───────────────────────────────────────── */}
      {tab === 'units' && (
        <div className="space-y-3">
          {units.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">Belum ada unit</div>
          ) : (
            <GlassCard hover={false} className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr>
                      {['Nama Unit','Tipe','Induk','Kepala','Aktual','Target','Gap',''].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--glass-border)]">
                    {unitsPg.paged.map(u => {
                      const parent = units.find(p => p.unit_id === u.parent_id);
                      const gap = (u.headcount_target || 0) - (u.headcount_actual || 0);
                      return (
                        <tr key={u.unit_id} className="hover:bg-[var(--glass-bg-hover)]">
                          <td className="px-4 py-3 font-medium" style={{ paddingLeft: `${(u.level || 0) * 16 + 16}px` }}>{u.name}</td>
                          <td className="px-4 py-3"><TypeBadge type={u.type} /></td>
                          <td className="px-4 py-3 text-muted-foreground">{parent?.name || '—'}</td>
                          <td className="px-4 py-3 text-muted-foreground">{u.head_employee_name || '—'}</td>
                          <td className="px-4 py-3 font-semibold text-foreground">{u.headcount_actual || 0}</td>
                          <td className="px-4 py-3 text-muted-foreground">{u.headcount_target || 0}</td>
                          <td className="px-4 py-3">
                            <span className={`text-xs font-medium ${gap > 0 ? 'text-amber-700 dark:text-amber-400' : gap < 0 ? 'text-red-700 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                              {gap > 0 ? `-${gap}` : gap < 0 ? `+${Math.abs(gap)}` : 'OK'}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex gap-1">
                              <button onClick={() => openUnitForm(u)}
                                className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)] text-muted-foreground hover:text-foreground">
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => handleDeleteUnit(u.unit_id)}
                                className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-red-50 dark:bg-red-400/10 text-muted-foreground hover:text-red-700 dark:text-red-400">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {unitsPg.total > 0 && <PaginationLite page={unitsPg.page} totalPages={unitsPg.totalPages} total={unitsPg.total} pageSize={unitsPg.pageSize} onPageChange={unitsPg.setPage} />}
            </GlassCard>
          )}
        </div>
      )}

      {/* ─── POSITIONS ─────────────────────────────────────── */}
      {tab === 'positions' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setShowPosForm(true)}
              className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 flex items-center gap-1.5">
              <Plus className="w-4 h-4" /> Tambah Posisi
            </button>
          </div>
          {positions.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">Belum ada posisi</div>
          ) : (
            <GlassCard hover={false} className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr>
                      {['Jabatan','Unit','Grade','Aktual','Target','Salary Grade'].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--glass-border)]">
                    {positionsPg.paged.map(p => (
                      <tr key={p.position_id} className="hover:bg-[var(--glass-bg-hover)]">
                        <td className="px-4 py-3 font-medium">{p.title}</td>
                        <td className="px-4 py-3 text-muted-foreground">{p.unit_name}</td>
                        <td className="px-4 py-3">
                          <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--nav-pill-active)] font-mono">G{p.grade}</span>
                        </td>
                        <td className="px-4 py-3 font-semibold">{p.headcount_actual}</td>
                        <td className="px-4 py-3 text-muted-foreground">{p.headcount_target}</td>
                        <td className="px-4 py-3 text-muted-foreground">{p.salary_grade || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {positionsPg.total > 0 && <PaginationLite page={positionsPg.page} totalPages={positionsPg.totalPages} total={positionsPg.total} pageSize={positionsPg.pageSize} onPageChange={positionsPg.setPage} />}
            </GlassCard>
          )}
        </div>
      )}

      {/* ─── HEADCOUNT ─────────────────────────────────────── */}
      {tab === 'headcount' && headcount && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Total Aktual', value: headcount.summary.total_actual, color: '#10b981' },
              { label: 'Total Target', value: headcount.summary.total_target, color: '#6366f1' },
              { label: 'Gap', value: headcount.summary.gap, color: headcount.summary.gap > 0 ? '#f59e0b' : '#10b981' },
            ].map((k, i) => (
              <GlassCard key={i} hover={false} className="p-4 text-center">
                <p className="text-2xl font-bold" style={{ color: k.color }}>{k.value}</p>
                <p className="text-xs text-muted-foreground">{k.label}</p>
              </GlassCard>
            ))}
          </div>

          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold mb-4">Headcount per Unit</h3>
            <div className="space-y-3">
              {(headcount.units || []).filter(u => u.target > 0).map((u, i) => {
                const pct = u.target > 0 ? Math.min((u.actual / u.target) * 100, 120) : 0;
                const statusColor = u.status === 'ok' ? '#10b981' : u.status === 'under' ? '#f59e0b' : '#ef4444';
                return (
                  <div key={u.unit_id} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <TypeBadge type={u.type} />
                        <span className="font-medium text-foreground">{u.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">{u.actual}/{u.target}</span>
                        <span className="font-semibold" style={{ color: statusColor }}>
                          {u.status === 'ok' ? 'Terpenuhi' : u.status === 'under' ? `Kurang ${u.gap}` : `Lebih ${Math.abs(u.gap)}`}
                        </span>
                      </div>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--glass-border)] overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(pct, 100)}%`, background: statusColor }} />
                    </div>
                  </div>
                );
              })}
              {(headcount.units || []).filter(u => u.target > 0).length === 0 && (
                <p className="text-center text-muted-foreground text-sm py-4">Belum ada data</p>
              )}
            </div>
          </GlassCard>
        </div>
      )}

      {/* ─── UNIT FORM ─────────────────────────────────────── */}
      {showUnitForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg">
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">{editUnit ? 'Edit Unit' : 'Tambah Unit'}</h2>
                <button onClick={() => setShowUnitForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Nama Unit *</label>
                    <input value={unitForm.name} onChange={e => setUnitForm(p => ({...p, name: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Kode</label>
                    <input value={unitForm.code} onChange={e => setUnitForm(p => ({...p, code: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Tipe</label>
                    <select value={unitForm.type} onChange={e => setUnitForm(p => ({...p, type: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      {TYPE_LEVELS.map(t => <option key={t} value={t}>{TYPE_CONFIG[t].label}</option>)}
                    </select></div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Unit Induk</label>
                    <SmartNativeSelect value={unitForm.parent_id} onChange={e => setUnitForm(p => ({...p, parent_id: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="">Tidak ada (root)</option>
                      {units.filter(u => !editUnit || u.unit_id !== editUnit.unit_id).map(u => <option key={u.unit_id} value={u.unit_id}>{u.name}</option>)}
                    </SmartNativeSelect></div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Nama Kepala</label>
                    <input value={unitForm.head_employee_name} onChange={e => setUnitForm(p => ({...p, head_employee_name: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Target Headcount</label>
                    <input type="number" value={unitForm.headcount_target} onChange={e => setUnitForm(p => ({...p, headcount_target: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" min={0} /></div>
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => setShowUnitForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm">Batal</button>
                <button onClick={handleSaveUnit} disabled={saving || !unitForm.name}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
                  {saving ? 'Menyimpan...' : (editUnit ? 'Simpan' : 'Tambah')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── POSITION FORM ────────────────────────────────── */}
      {showPosForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md">
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">Tambah Posisi</h2>
                <button onClick={() => setShowPosForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div><label className="text-xs font-medium text-muted-foreground block mb-1">Judul Jabatan *</label>
                  <input value={posForm.title} onChange={e => setPosForm(p => ({...p, title: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Unit</label>
                    <SmartNativeSelect value={posForm.unit_id} onChange={e => setPosForm(p => ({...p, unit_id: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="">Pilih unit</option>
                      {units.map(u => <option key={u.unit_id} value={u.unit_id}>{u.name}</option>)}
                    </SmartNativeSelect></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Grade (1-10)</label>
                    <input type="number" value={posForm.grade} onChange={e => setPosForm(p => ({...p, grade: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" min={1} max={10} /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Target Headcount</label>
                    <input type="number" value={posForm.headcount_target} onChange={e => setPosForm(p => ({...p, headcount_target: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" min={1} /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Salary Grade</label>
                    <input value={posForm.salary_grade} onChange={e => setPosForm(p => ({...p, salary_grade: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" placeholder="A, B, C..." /></div>
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => setShowPosForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm">Batal</button>
                <button onClick={handleSavePos} disabled={saving || !posForm.title}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
                  {saving ? 'Menyimpan...' : 'Tambah'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
