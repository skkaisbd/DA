import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Calendar, Plus, Trash2, ChevronLeft, ChevronRight, Calculator, RefreshCw } from 'lucide-react';

const MONTHS = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
const DAYS_SHORT = ['Min','Sen','Sel','Rab','Kam','Jum','Sab'];

const TYPE_COLOR = {
  holiday: 'bg-red-500 text-foreground',
  exception: 'bg-amber-500 text-foreground',
  special: 'bg-blue-500 text-foreground',
};
const TYPE_LABEL = { holiday: 'Hari Libur', exception: 'Pengecualian', special: 'Catatan Khusus' };
const TYPE_BADGE = {
  holiday: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 border-red-400 dark:border-red-500/30',
  exception: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-500/30',
  special: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-500/30',
};

const BLANK = { date: '', name: '', type: 'holiday', notes: '' };

export default function RahazaProductionCalendarModule({ token }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(BLANK);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [workdayResult, setWorkdayResult] = useState(null);
  const [wdFrom, setWdFrom] = useState('');
  const [wdTo, setWdTo] = useState('');
  const [seeding, setSeeding] = useState(false);

  const hdrs = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/rahaza/production-calendar?year=${year}&month=${month}`, { headers: hdrs });
      if (res.ok) setEntries(await res.json());
    } finally {
      setLoading(false);
    }
  }, [year, month, hdrs]);

  useEffect(() => { load(); }, [load]);

  const entryMap = {};
  entries.forEach(e => { entryMap[e.date] = e; });

  // Build calendar days for current month
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month, 0).getDate();
  const calendarCells = [];
  for (let i = 0; i < firstDay; i++) calendarCells.push(null);
  for (let d = 1; d <= daysInMonth; d++) calendarCells.push(d);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  const handleCreate = async () => {
    if (!form.date || !form.name) return setMsg({ type: 'error', text: 'Tanggal dan nama wajib diisi' });
    setSaving(true);
    try {
      const res = await fetch('/api/rahaza/production-calendar', {
        method: 'POST', headers: { ...hdrs, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setMsg({ type: 'success', text: 'Entri berhasil ditambahkan' });
        setShowForm(false);
        setForm(BLANK);
        await load();
      } else {
        const e = await res.json();
        setMsg({ type: 'error', text: e.detail || 'Gagal menyimpan' });
      }
    } finally {
      setSaving(false);
      setTimeout(() => setMsg(null), 4000);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus entri ini?')) return;
    const res = await fetch(`/api/rahaza/production-calendar/${id}`, { method: 'DELETE', headers: hdrs });
    if (res.ok) { await load(); setMsg({ type: 'success', text: 'Entri dihapus' }); }
    setTimeout(() => setMsg(null), 3000);
  };

  const calcWorkdays = async () => {
    if (!wdFrom || !wdTo) return;
    const res = await fetch(`/api/rahaza/production-calendar/working-days?from_date=${wdFrom}&to_date=${wdTo}`, { headers: hdrs });
    if (res.ok) setWorkdayResult(await res.json());
  };

  const seedNational = async () => {
    setSeeding(true);
    try {
      const res = await fetch('/api/rahaza/production-calendar/seed-national', { method: 'POST', headers: hdrs });
      if (res.ok) {
        const d = await res.json();
        setMsg({ type: 'success', text: `${d.seeded} hari libur nasional 2026 ditambahkan` });
        await load();
      }
    } finally {
      setSeeding(false);
      setTimeout(() => setMsg(null), 4000);
    }
  };

  return (
    <div className="space-y-5" data-testid="production-calendar-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Kalender Produksi</h2>
          <p className="text-sm text-foreground/50 mt-0.5">Hari libur nasional & pengecualian produksi</p>
        </div>
        <div className="flex gap-2">
          <button onClick={seedNational} disabled={seeding}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[var(--glass-border)] text-sm text-foreground/70 hover:bg-[var(--glass-bg-hover)] disabled:opacity-50"
            data-testid="seed-national-btn">
            <RefreshCw className={`w-3.5 h-3.5 ${seeding ? 'animate-spin' : ''}`} />
            {seeding ? 'Memuat...' : 'Seed Libur Nasional 2026'}
          </button>
          <button onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.25)] text-[hsl(var(--primary))] text-sm hover:bg-[hsl(var(--primary)/0.25)] transition-colors"
            data-testid="new-entry-btn">
            <Plus className="w-4 h-4" /> Tambah Entri
          </button>
        </div>
      </div>

      {/* Alert */}
      {msg && (
        <div className={`px-4 py-3 rounded-xl border text-sm ${msg.type === 'success' ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30 text-red-600 dark:text-red-300'}`}>
          {msg.text}
        </div>
      )}

      {/* Legend */}
      <div className="flex gap-3 flex-wrap">
        {Object.entries(TYPE_LABEL).map(([k, v]) => (
          <div key={k} className="flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-sm ${k === 'holiday' ? 'bg-red-500' : k === 'exception' ? 'bg-amber-500' : 'bg-blue-500'}`} />
            <span className="text-xs text-foreground/60">{v}</span>
          </div>
        ))}
      </div>

      {/* Add Form */}
      {showForm && (
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-5 space-y-4" data-testid="calendar-form">
          <h3 className="font-semibold text-foreground">Tambah Entri Kalender</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-foreground/60 mb-1">Tanggal</label>
              <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="cal-date" />
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/60 mb-1">Tipe</label>
              <SmartNativeSelect value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="cal-type">
                {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </SmartNativeSelect>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-foreground/60 mb-1">Nama/Keterangan</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Contoh: Hari Raya Idul Fitri"
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="cal-name" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground/60 mb-1">Catatan (opsional)</label>
            <input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Keterangan tambahan..."
              className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="cal-notes" />
          </div>
          <div className="flex gap-3 pt-1">
            <button onClick={handleCreate} disabled={saving}
              className="px-5 py-2 rounded-xl bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-sm font-medium hover:opacity-90 disabled:opacity-50"
              data-testid="cal-submit-btn">
              {saving ? 'Menyimpan...' : 'Simpan'}
            </button>
            <button onClick={() => { setShowForm(false); setForm(BLANK); }}
              className="px-5 py-2 rounded-xl border border-[var(--glass-border)] text-sm text-foreground/70 hover:bg-[var(--glass-bg-hover)]">
              Batal
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Calendar */}
        <div className="xl:col-span-2 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl overflow-hidden">
          {/* Nav */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--glass-border)]">
            <button onClick={prevMonth} className="p-1.5 rounded-lg hover:bg-[var(--glass-bg-hover)] text-foreground/60 hover:text-foreground transition-colors" data-testid="cal-prev">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <h3 className="font-semibold text-foreground">{MONTHS[month - 1]} {year}</h3>
            <button onClick={nextMonth} className="p-1.5 rounded-lg hover:bg-[var(--glass-bg-hover)] text-foreground/60 hover:text-foreground transition-colors" data-testid="cal-next">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Day headers */}
          <div className="grid grid-cols-7 border-b border-[var(--glass-border)]">
            {DAYS_SHORT.map(d => (
              <div key={d} className={`py-2 text-center text-xs font-semibold ${d === 'Min' ? 'text-red-700 dark:text-red-400' : 'text-foreground/50'}`}>{d}</div>
            ))}
          </div>

          {/* Days */}
          <div className="grid grid-cols-7">
            {calendarCells.map((day, idx) => {
              if (!day) return <div key={`empty-${idx}`} className="h-14 border-b border-r border-[var(--glass-border)]" />;
              const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const entry = entryMap[dateStr];
              const isSunday = new Date(year, month - 1, day).getDay() === 0;
              const isToday = dateStr === new Date().toISOString().slice(0, 10);
              return (
                <div key={day}
                  className={`h-14 p-1 border-b border-r border-[var(--glass-border)] transition-colors relative
                    ${isToday ? 'bg-[hsl(var(--primary)/0.05)]' : ''}
                    ${isSunday ? 'bg-red-100 dark:bg-red-500/5' : ''}`}>
                  <div className={`text-xs font-medium w-6 h-6 rounded-full flex items-center justify-center mx-auto
                    ${isToday ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]' : isSunday ? 'text-red-700 dark:text-red-400' : 'text-foreground/70'}`}>
                    {day}
                  </div>
                  {entry && (
                    <div className={`mt-0.5 px-1 py-0.5 rounded text-[9px] leading-tight truncate ${TYPE_COLOR[entry.type] || 'bg-foreground/20 text-foreground'}`}
                      title={entry.name}>
                      {entry.name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {loading && (
            <div className="text-center py-4 text-foreground/40 text-sm">Memuat...</div>
          )}
        </div>

        {/* Right Panel */}
        <div className="space-y-4">
          {/* Working Days Calculator */}
          <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Calculator className="w-4 h-4 text-[hsl(var(--primary))]" />
              <h3 className="font-semibold text-foreground text-sm">Kalkulator Hari Kerja</h3>
            </div>
            <div className="space-y-2">
              <div>
                <label className="block text-xs text-foreground/50 mb-1">Dari</label>
                <input type="date" value={wdFrom} onChange={e => setWdFrom(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="wd-from" />
              </div>
              <div>
                <label className="block text-xs text-foreground/50 mb-1">Sampai</label>
                <input type="date" value={wdTo} onChange={e => setWdTo(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="wd-to" />
              </div>
              <button onClick={calcWorkdays}
                className="w-full py-2 rounded-lg bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.25)] text-[hsl(var(--primary))] text-sm hover:bg-[hsl(var(--primary)/0.25)] transition-colors"
                data-testid="calc-workdays-btn">
                Hitung
              </button>
            </div>
            {workdayResult && (
              <div className="p-3 rounded-lg bg-[var(--card-surface)] space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-foreground/50">Total hari kalender</span>
                  <span className="font-mono text-foreground">{workdayResult.total_calendar_days}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-foreground/50">Hari libur</span>
                  <span className="font-mono text-red-700 dark:text-red-400">{workdayResult.holidays}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-foreground/50">Weekend</span>
                  <span className="font-mono text-amber-700 dark:text-amber-400">{workdayResult.weekends_excluded}</span>
                </div>
                <div className="flex justify-between border-t border-[var(--glass-border)] pt-1.5 mt-1.5">
                  <span className="font-semibold text-foreground">Hari kerja efektif</span>
                  <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">{workdayResult.working_days}</span>
                </div>
              </div>
            )}
          </div>

          {/* Month Entries List */}
          <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-5">
            <h3 className="font-semibold text-foreground text-sm mb-3">
              {MONTHS[month - 1]} {year} · {entries.length} entri
            </h3>
            {entries.length === 0 ? (
              <p className="text-xs text-foreground/40 text-center py-4">Tidak ada entri bulan ini</p>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {entries.map(e => (
                  <div key={e.id} className="flex items-start gap-2" data-testid={`cal-entry-${e.id}`}>
                    <div className="text-right shrink-0 w-6">
                      <p className="text-xs font-bold text-foreground">{e.day}</p>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-foreground truncate">{e.name}</p>
                      <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] border ${TYPE_BADGE[e.type]}`}>{TYPE_LABEL[e.type]}</span>
                    </div>
                    {e.created_by !== 'system' && (
                      <button onClick={() => handleDelete(e.id)}
                        className="p-1 rounded text-foreground/30 hover:text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10 transition-colors shrink-0"
                        data-testid={`del-entry-${e.id}`} title="Hapus">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
