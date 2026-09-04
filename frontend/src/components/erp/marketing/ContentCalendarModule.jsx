import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ContentPerformanceView from './ContentPerformanceView';
import CreatorScorecardView from './CreatorScorecardView';
import PlatformKpiView from './PlatformKpiView';
import {
  Calendar, Plus, Pencil, Trash2, Sparkles, ChevronLeft, ChevronRight,
  Loader2, RefreshCw, CheckCircle2, Clock, XCircle, AlertCircle, Filter, X, Search
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { useMarketingAccounts, getPlatformIcon } from '@/hooks/useMarketingAccounts';
import axios from 'axios';
import { MarketingAccountSelect } from './pickers/MarketingPickers';
// F10 (sesi #10) — kalender konten dipakai rapat konten; wajib bisa diunduh.
import ExportCsvButton from '@/components/ui/export-csv-button';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { shopee: '🛒', tiktok: '🎵', tokopedia: '🟢', instagram: '📷', facebook: '🔵' };
const STATUS_CONFIG = {
  draft:     { label: 'Draft',     color: 'bg-muted text-muted-foreground dark:bg-gray-800 dark:text-gray-300', icon: AlertCircle },
  scheduled: { label: 'Terjadwal', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', icon: Clock },
  posted:    { label: 'Tayang',    color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
  cancelled: { label: 'Batal',     color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', icon: XCircle },
};

const MONTHS_ID = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
const DAYS_ID   = ['Min','Sen','Sel','Rab','Kam','Jum','Sab'];

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>
      <Icon size={10} />{c.label}
    </span>
  );
}

function KPICard({ label, value, sub, color, bg, icon: Icon }) {
  return (
    <Card className={`${bg} border-0`}>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-background/60 dark:bg-black/20`}>
          <Icon size={20} className={color} />
        </div>
        <div>
          <p className="text-xl font-bold leading-tight">{value}</p>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

const EMPTY_FORM = {
  account_id: '', account_name: '', platform: 'shopee', date: '', content_type: 'foto_produk',
  title: '', description: '', cta: '', post_time: '', reference_link: '', status: 'draft'
};

function ContentCalendarBase({ token }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const { accounts: masterAccounts, byId: accountById } = useMarketingAccounts(token);

  const now = new Date();
  const [year,  setYear]  = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [view,  setView]  = useState('calendar'); // 'calendar' | 'list'

  const [summary,      setSummary]      = useState(null);
  const [calendarData, setCalendarData] = useState([]);
  const [listData,     setListData]     = useState([]);
  const [pagination,   setPagination]   = useState(null);
  const [contentTypes, setContentTypes] = useState([]);
  const [accounts,     setAccounts]     = useState([]);

  const [loading,    setLoading]    = useState(true);
  const [aiLoading,  setAiLoading]  = useState('');

  const [filterStatus,  setFilterStatus]  = useState('');
  const [filterPlatform,setFilterPlatform]= useState('');
  // F14 — filter per TOKO memakai account_id (SSOT), bukan mencocokkan nama toko.
  const [filterAccountId, setFilterAccountId] = useState('');
  const [filterType,    setFilterType]    = useState('');
  const [listPage,      setListPage]      = useState(1);
  // F10 (sesi #10) — daftar konten bisa panjang; "cari judul" adalah cara paling
  // cepat menemukan satu konten (dulu hanya ada penyaring status/jenis/platform).
  const [listSearch,    setListSearch]    = useState('');

  const [showForm,   setShowForm]   = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form,       setForm]       = useState(EMPTY_FORM);
  const [formLoading,setFormLoading]= useState(false);

  const [showDetail, setShowDetail] = useState(null);

  const fetchTypes = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/content-calendar/types`, { headers: authH });
      setContentTypes(res.data.types || []);
    } catch {}
  }, [authH]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/content-calendar/summary`, { headers: authH });
      if (res.data.success) setSummary(res.data.data);
    } catch {}
  }, [authH]);

  const fetchMonthly = useCallback(async () => {
    setLoading(true);
    try {
      const params = { year, month };
      if (filterPlatform) params.platform = filterPlatform;
      if (filterAccountId) params.account_id = filterAccountId;
      const res = await axios.get(`${API}/api/marketing/content-calendar/monthly`, { params, headers: authH });
      if (res.data.success) setCalendarData(res.data.data || []);
    } catch { toast({ title: 'Gagal load kalender', variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [year, month, filterPlatform, filterAccountId, authH, toast]);

  const needle = listSearch.trim().toLowerCase();
  const visibleList = needle
    ? (listData || []).filter((e) => [e.title, e.cta, e.account_name, e.platform,
      e.content_type_label, e.published_url]
      .some((v) => String(v || '').toLowerCase().includes(needle)))
    : (listData || []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page: listPage, page_size: 20 };
      if (filterStatus)   params.status = filterStatus;
      if (filterPlatform) params.platform = filterPlatform;
      if (filterAccountId) params.account_id = filterAccountId;
      if (filterType)     params.content_type = filterType;
      const res = await axios.get(`${API}/api/marketing/content-calendar`, { params, headers: authH });
      if (res.data.success) {
        setListData(res.data.data || []);
        setPagination(res.data.pagination);
        // Build unique account list
        const accs = [...new Set((res.data.data || []).map(e => e.account_name))].filter(Boolean);
        if (accs.length) setAccounts(accs);
      }
    } catch { toast({ title: 'Gagal load konten', variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [listPage, filterStatus, filterPlatform, filterType, filterAccountId, authH, toast]);

  useEffect(() => { fetchTypes(); fetchSummary(); }, [fetchTypes, fetchSummary]);
  useEffect(() => { if (view === 'calendar') fetchMonthly(); else fetchList(); }, [view, fetchMonthly, fetchList]);

  // Build calendar grid
  const buildGrid = () => {
    const firstDay = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const cells = [];
    for (let i = 0; i < firstDay; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    return cells;
  };

  const getEntriesForDay = (day) => {
    if (!day) return [];
    const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    return calendarData.filter(e => e.date === dateStr);
  };

  const prevMonth = () => { if (month === 1) { setYear(y => y - 1); setMonth(12); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setYear(y => y + 1); setMonth(1); } else setMonth(m => m + 1); };

  const openCreate = (dateStr) => {
    setEditTarget(null);
    setForm({ ...EMPTY_FORM, date: dateStr || '' });
    setShowForm(true);
  };

  const openEdit = (entry) => {
    setEditTarget(entry);
    setForm({
      account_id: entry.account_id || '',
      account_name: entry.account_name || '', platform: entry.platform || 'shopee',
      date: entry.date || '', content_type: entry.content_type || 'foto_produk',
      title: entry.title || '', description: entry.description || '',
      cta: entry.cta || '', post_time: entry.post_time || '',
      reference_link: entry.reference_link || '', status: entry.status || 'draft',
    });
    setShowForm(true);
  };

  // When account_id changes, auto-fill account_name & platform from master
  const handleAccountChange = (accountId) => {
    const acc = accountById[accountId];
    setForm(f => ({
      ...f,
      account_id: accountId,
      account_name: acc?.account_name || acc?.name || '',
      platform: acc?.platform || f.platform,
    }));
  };

  const handleSave = async () => {
    if (!form.account_id || !form.date || !form.title) {
      toast({ title: 'Wajib pilih Akun, isi Tanggal, dan Judul/Hook', variant: 'destructive' }); return;
    }
    setFormLoading(true);
    try {
      if (editTarget) {
        await axios.put(`${API}/api/marketing/content-calendar/${editTarget.id}`, form, { headers: authH });
        toast({ title: 'Konten diperbarui' });
      } else {
        await axios.post(`${API}/api/marketing/content-calendar`, form, { headers: authH });
        toast({ title: 'Konten berhasil ditambahkan' });
      }
      setShowForm(false);
      fetchSummary();
      if (view === 'calendar') fetchMonthly(); else fetchList();
    } catch { toast({ title: 'Gagal menyimpan', variant: 'destructive' }); }
    finally { setFormLoading(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus entri ini?')) return;
    try {
      await axios.delete(`${API}/api/marketing/content-calendar/${id}`, { headers: authH });
      toast({ title: 'Dihapus' });
      if (showDetail?.id === id) setShowDetail(null);
      fetchSummary();
      if (view === 'calendar') fetchMonthly(); else fetchList();
    } catch { toast({ title: 'Gagal hapus', variant: 'destructive' }); }
  };

  const handleAIHook = async (entryId) => {
    setAiLoading(entryId);
    try {
      const res = await axios.post(`${API}/api/marketing/content-calendar/${entryId}/ai-hook`, {}, { headers: authH });
      if (res.data.success) {
        toast({ title: '✨ AI Hook Generated', description: res.data.applied_hook });
        if (view === 'calendar') fetchMonthly(); else fetchList();
      }
    } catch { toast({ title: 'AI Hook gagal', variant: 'destructive' }); }
    finally { setAiLoading(''); }
  };

  const handleStatusChange = async (entryId, newStatus) => {
    try {
      await axios.post(`${API}/api/marketing/content-calendar/${entryId}/status`, { status: newStatus }, { headers: authH });
      toast({ title: `Status → ${STATUS_CONFIG[newStatus]?.label}` });
      fetchSummary();
      if (view === 'calendar') fetchMonthly(); else fetchList();
    } catch { toast({ title: 'Gagal update status', variant: 'destructive' }); }
  };

  const kpis = [
    { label: 'Total Konten',  value: summary?.total     ?? '—', sub: `${summary?.this_month ?? 0} bulan ini`,  color: 'text-indigo-600',  bg: 'bg-indigo-50 dark:bg-indigo-900/20', icon: Calendar },
    { label: 'Terjadwal',     value: summary?.scheduled ?? '—', sub: 'Menunggu posting',                       color: 'text-blue-600',    bg: 'bg-blue-50 dark:bg-blue-900/20',   icon: Clock },
    { label: 'Sudah Tayang',  value: summary?.posted    ?? '—', sub: 'Total posted',                           color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: CheckCircle2 },
    { label: 'Draft',         value: summary?.draft     ?? '—', sub: 'Perlu finalisasi',                       color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20', icon: AlertCircle },
  ];

  const grid = buildGrid();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="content-calendar-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Content Calendar</h1>
          <p className="text-sm text-muted-foreground">Jadwal konten multi-platform dengan AI hook generation</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchSummary(); if (view==='calendar') fetchMonthly(); else fetchList(); }}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button size="sm" onClick={() => openCreate('')} data-testid="btn-add-content">
            <Plus size={14} className="mr-1" />Tambah Konten
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => <KPICard key={k.label} {...k} />)}
      </div>

      {/* View toggle + filters */}
      <Card className="mb-4">
        <CardContent className="p-3 flex flex-wrap gap-3 items-center">
          <div className="flex rounded-md border overflow-hidden">
            <button onClick={() => setView('calendar')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${view==='calendar' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}>
              📅 Kalender
            </button>
            <button onClick={() => setView('list')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${view==='list' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}>
              📋 Daftar
            </button>
          </div>

          <div className="w-52">
            <MarketingAccountSelect token={token} value={filterAccountId}
              onChange={setFilterAccountId} label="" includeAll allLabel="Semua Toko"
              required={false} testId="content-filter-account" />
          </div>
          <Select value={filterPlatform || 'all'} onValueChange={v => setFilterPlatform(v === 'all' ? '' : v)}>
            <SelectTrigger className="w-40 h-8 text-xs">
              <SelectValue placeholder="Platform" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Platform</SelectItem>
              {['shopee','tiktok','tokopedia','instagram','facebook'].map(p => (
                <SelectItem key={p} value={p}>{PLATFORM_ICONS[p]} {p.charAt(0).toUpperCase()+p.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {view === 'list' && (
            <>
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input className="h-8 pl-8 w-52 text-xs" placeholder="cari judul / hook / toko"
                  value={listSearch} onChange={(e) => setListSearch(e.target.value)}
                  data-testid="content-search" />
              </div>
              <Select value={filterStatus || 'all'} onValueChange={v => { setFilterStatus(v === 'all' ? '' : v); setListPage(1); }}>
                <SelectTrigger className="w-36 h-8 text-xs"><SelectValue placeholder="Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Status</SelectItem>
                  {Object.entries(STATUS_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={filterType || 'all'} onValueChange={v => { setFilterType(v === 'all' ? '' : v); setListPage(1); }}>
                <SelectTrigger className="w-40 h-8 text-xs"><SelectValue placeholder="Jenis Konten" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Jenis</SelectItem>
                  {contentTypes.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </>
          )}

          {(filterStatus || filterPlatform || filterType) && (
            <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => { setFilterStatus(''); setFilterPlatform(''); setFilterType(''); }}>
              <X size={12} className="mr-1" />Reset
            </Button>
          )}

          {view === 'list' && (
            <ExportCsvButton
              filename="kalender-konten"
              testId="content-export-csv"
              head={['Tanggal', 'Platform', 'Toko', 'Jenis', 'Judul', 'CTA/Hook', 'Jam',
                'Status', 'Link terbit', 'Views', 'Likes', 'Komentar', 'Orders', 'GMV']}
              rows={visibleList.map((e) => [e.date, e.platform, e.account_name,
                e.content_type_label || e.content_type, e.title, e.cta, e.post_time,
                e.status, e.published_url || '',
                e.kpi?.views ?? '', e.kpi?.likes ?? '', e.kpi?.comments ?? '',
                e.kpi?.orders ?? '', e.kpi?.gmv ?? ''])}
            />
          )}
        </CardContent>
      </Card>

      {/* CALENDAR VIEW */}
      {view === 'calendar' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <Button variant="ghost" size="icon" onClick={prevMonth}><ChevronLeft size={16} /></Button>
              <CardTitle className="text-base">{MONTHS_ID[month - 1]} {year}</CardTitle>
              <Button variant="ghost" size="icon" onClick={nextMonth}><ChevronRight size={16} /></Button>
            </div>
          </CardHeader>
          <CardContent className="p-3">
            {loading ? (
              <div className="flex justify-center py-16"><Loader2 size={28} className="animate-spin text-muted-foreground" /></div>
            ) : (
              <>
                <div className="grid grid-cols-7 mb-1">
                  {DAYS_ID.map(d => (
                    <div key={d} className="text-center text-xs font-semibold text-muted-foreground py-1">{d}</div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-1">
                  {grid.map((day, idx) => {
                    const entries = day ? getEntriesForDay(day) : [];
                    const dateStr = day ? `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}` : '';
                    const isToday = dateStr === todayStr;
                    return (
                      <div key={idx}
                        className={`min-h-[80px] rounded-lg border p-1 transition-colors ${
                          !day ? 'bg-muted/20 border-transparent' :
                          isToday ? 'border-primary bg-primary/5' :
                          'border-border hover:border-primary/40 cursor-pointer'
                        }`}
                        onClick={() => day && openCreate(dateStr)}
                      >
                        {day && (
                          <>
                            <div className={`text-xs font-semibold mb-1 text-right ${isToday ? 'text-primary' : 'text-muted-foreground'}`}>
                              {isToday ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs">{day}</span> : day}
                            </div>
                            <div className="space-y-0.5">
                              {entries.slice(0, 3).map(e => (
                                <div key={e.id}
                                  className={`text-xs px-1 py-0.5 rounded truncate cursor-pointer hover:opacity-80 ${
                                    e.status === 'posted'    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30' :
                                    e.status === 'scheduled' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30' :
                                    e.status === 'cancelled' ? 'bg-red-100 text-red-700 dark:bg-red-900/30' :
                                    'bg-muted text-muted-foreground dark:bg-gray-800'
                                  }`}
                                  onClick={(ev) => { ev.stopPropagation(); setShowDetail(e); }}
                                  title={e.title}
                                >
                                  {PLATFORM_ICONS[e.platform] || '📌'} {e.title}
                                </div>
                              ))}
                              {entries.length > 3 && (
                                <div className="text-xs text-muted-foreground text-center">+{entries.length - 3} lagi</div>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* LIST VIEW */}
      {view === 'list' && (
        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex justify-center py-16"><Loader2 size={28} className="animate-spin text-muted-foreground" /></div>
            ) : visibleList.length === 0 ? (
              <div className="text-center py-16 text-muted-foreground">
                <Calendar size={40} className="mx-auto mb-3 opacity-30" />
                <p className="font-medium">Belum ada konten</p>
                <Button size="sm" className="mt-3" onClick={() => openCreate('')}><Plus size={12} className="mr-1" />Tambah</Button>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/40">
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Tanggal</th>
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Platform / Akun</th>
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Jenis</th>
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Judul / Hook</th>
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Jam</th>
                        <th className="px-4 py-3 text-left font-semibold text-xs text-muted-foreground uppercase">Status</th>
                        <th className="px-4 py-3 text-right font-semibold text-xs text-muted-foreground uppercase">Aksi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleList.map((e, i) => (
                        <tr key={e.id} className={`border-b last:border-0 hover:bg-muted/30 transition-colors ${i % 2 === 0 ? '' : 'bg-muted/10'}`}>
                          <td className="px-4 py-3 font-mono text-xs">{e.date}</td>
                          <td className="px-4 py-3">
                            <div className="font-medium">{PLATFORM_ICONS[e.platform] || '📌'} {e.platform}</div>
                            <div className="text-xs text-muted-foreground">{e.account_name}</div>
                          </td>
                          <td className="px-4 py-3 text-xs">{e.content_type_label || e.content_type}</td>
                          <td className="px-4 py-3 max-w-[220px]">
                            <div className="font-medium truncate" title={e.title}>{e.title}</div>
                            {e.cta && <div className="text-xs text-muted-foreground">{e.cta}</div>}
                          </td>
                          <td className="px-4 py-3 text-xs">{e.post_time || '—'}</td>
                          <td className="px-4 py-3"><StatusBadge status={e.status} /></td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1">
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleAIHook(e.id)}
                                disabled={aiLoading === e.id} title="Generate AI Hook">
                                {aiLoading === e.id ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                              </Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEdit(e)}>
                                <Pencil size={12} />
                              </Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-red-500 hover:text-red-600" onClick={() => handleDelete(e.id)}>
                                <Trash2 size={12} />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {pagination && pagination.total_pages > 1 && (
                  <div className="flex items-center justify-between px-4 py-3 border-t">
                    <p className="text-xs text-muted-foreground">{pagination.total} konten ditemukan</p>
                    <div className="flex gap-1">
                      <Button size="sm" variant="outline" disabled={listPage <= 1} onClick={() => setListPage(p => p - 1)}>‹ Prev</Button>
                      <span className="px-3 py-1.5 text-xs">{listPage} / {pagination.total_pages}</span>
                      <Button size="sm" variant="outline" disabled={listPage >= pagination.total_pages} onClick={() => setListPage(p => p + 1)}>Next ›</Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* DETAIL DIALOG */}
      <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
        <DialogContent className="max-w-lg">
          {showDetail && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {PLATFORM_ICONS[showDetail.platform]} {showDetail.title}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-muted-foreground">Akun:</span> <strong>{showDetail.account_name}</strong></div>
                  <div><span className="text-muted-foreground">Tanggal:</span> <strong>{showDetail.date}</strong></div>
                  <div><span className="text-muted-foreground">Jenis:</span> {showDetail.content_type_label}</div>
                  <div><span className="text-muted-foreground">Jam:</span> {showDetail.post_time || '—'}</div>
                </div>
                {showDetail.description && <p className="text-muted-foreground">{showDetail.description}</p>}
                {showDetail.cta && <div><span className="text-muted-foreground">CTA:</span> {showDetail.cta}</div>}
                {showDetail.reference_link && (
                  <div data-testid="content-reference-link-view">
                    <span className="text-muted-foreground">Link Referensi:</span>{' '}
                    <a href={showDetail.reference_link} target="_blank" rel="noopener noreferrer"
                      className="text-primary underline break-all hover:opacity-80">
                      {showDetail.reference_link}
                    </a>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <StatusBadge status={showDetail.status} />
                  <div className="flex gap-1">
                    {Object.keys(STATUS_CONFIG).map(s => s !== showDetail.status && (
                      <Button key={s} size="sm" variant="outline" className="h-6 text-xs px-2"
                        onClick={() => { handleStatusChange(showDetail.id, s); setShowDetail(null); }}>
                        → {STATUS_CONFIG[s].label}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button variant="outline" size="sm" onClick={() => { setShowDetail(null); openEdit(showDetail); }}>
                  <Pencil size={12} className="mr-1" />Edit
                </Button>
                <Button variant="outline" size="sm" onClick={() => { handleAIHook(showDetail.id); setShowDetail(null); }}
                  disabled={aiLoading === showDetail.id}>
                  <Sparkles size={12} className="mr-1" />AI Hook
                </Button>
                <Button variant="destructive" size="sm" onClick={() => handleDelete(showDetail.id)}>
                  <Trash2 size={12} className="mr-1" />Hapus
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* CREATE/EDIT DIALOG */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editTarget ? 'Edit Konten' : 'Tambah Konten'}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Akun / Toko Marketplace *</Label>
              <Select value={form.account_id || ''} onValueChange={handleAccountChange}>
                <SelectTrigger className="mt-1" data-testid="content-account-select">
                  <SelectValue placeholder={masterAccounts.length === 0 ? 'Belum ada akun — buat di Manage Accounts' : 'Pilih akun...'} />
                </SelectTrigger>
                <SelectContent>
                  {masterAccounts.length === 0 && (
                    <SelectItem value="empty" disabled>Belum ada akun aktif</SelectItem>
                  )}
                  {masterAccounts.map(acc => (
                    <SelectItem key={acc.id} value={acc.id}>
                      {getPlatformIcon(acc.platform)} {acc.account_name} <span className="text-xs text-muted-foreground ml-1">({acc.platform})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {form.account_id && (
                <p className="text-xs text-muted-foreground mt-1">
                  Platform: <strong>{form.platform}</strong> (otomatis dari akun terpilih)
                </p>
              )}
            </div>
            <div>
              <Label>Tanggal *</Label>
              <Input type="date" value={form.date} onChange={e => setForm(f => ({...f, date: e.target.value}))} className="mt-1" />
            </div>
            <div>
              <Label>Status</Label>
              <Select value={form.status} onValueChange={v => setForm(f => ({...f, status: v}))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(STATUS_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Jenis Konten *</Label>
              <Select value={form.content_type} onValueChange={v => setForm(f => ({...f, content_type: v}))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {contentTypes.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Judul / Hook *</Label>
              <Input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
                placeholder="Hook atau judul konten yang menarik" className="mt-1" />
            </div>
            <div className="col-span-2">
              <Label>Deskripsi</Label>
              <Textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
                placeholder="Deskripsi detail konten..." className="mt-1" rows={2} />
            </div>
            <div>
              <Label>CTA</Label>
              <Input value={form.cta} onChange={e => setForm(f => ({...f, cta: e.target.value}))}
                placeholder="Klik di bio!" className="mt-1" />
            </div>
            <div>
              <Label>Jam Posting</Label>
              <Input type="time" value={form.post_time} onChange={e => setForm(f => ({...f, post_time: e.target.value}))} className="mt-1" />
            </div>
            <div className="col-span-2">
              <Label>Link Referensi / Google Drive</Label>
              <Input type="url" value={form.reference_link}
                data-testid="content-reference-link-input"
                onChange={e => setForm(f => ({...f, reference_link: e.target.value}))}
                placeholder="https://drive.google.com/... (materi foto/video/brief)" className="mt-1" />
              <p className="text-[10px] text-muted-foreground mt-1">Tautan aset konten (Drive/Canva/Figma) — bisa dibuka langsung dari detail konten.</p>
            </div>
            <div className="col-span-2">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={v => setForm(f => ({...f, status: v}))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(STATUS_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
            <Button onClick={handleSave} disabled={formLoading}>
              {formLoading && <Loader2 size={14} className="mr-2 animate-spin" />}
              {editTarget ? 'Simpan Perubahan' : 'Tambah Konten'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


/**
 * F7.4 — kalender konten kini punya EMPAT sisi dalam satu pintu:
 * "Kalender & Rencana", **"Performa Konten"** (KPI per kreator), **"Scorecard
 * Kreator"** (target vs pencapaian), dan **"KPI Platform"** (hasil impor ekspor
 * Seller Center). Dibungkus di sini (bukan menyalin modul) supaya tidak lahir
 * pintu kembar: satu pintu, beberapa tampilan, satu sumber angka.
 */
export default function ContentCalendarModule(props) {
  const [tab, setTab] = useState('kalender');
  return (
    <div className="space-y-3 p-4 lg:p-6">
      <div className="flex flex-wrap gap-1.5" data-testid="content-tabs">
        {[['kalender', 'Kalender & Rencana'], ['performa', 'Performa Konten'],
          ['scorecard', 'Scorecard Kreator'], ['kpi', 'KPI Platform']].map(([v, l]) => (
          <button key={v} type="button" onClick={() => setTab(v)}
            data-testid={`content-tab-${v}`}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold border ${tab === v
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background text-foreground border-border hover:bg-muted/50'}`}>
            {l}
          </button>
        ))}
      </div>
      {tab === 'kalender' && <ContentCalendarBase {...props} />}
      {tab === 'performa' && <ContentPerformanceView token={props.token} />}
      {tab === 'scorecard' && (
        <CreatorScorecardView token={props.token} onNavigate={props.onNavigate} />
      )}
      {tab === 'kpi' && <PlatformKpiView token={props.token} onNavigate={props.onNavigate} />}
    </div>
  );
}
