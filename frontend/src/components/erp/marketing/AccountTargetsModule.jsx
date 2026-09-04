/**
 * AccountTargetsModule — LAYAR SIKLUS + Target Bulanan per Akun & KOL/Creator.
 *
 * F5 (2026-08-13): tab pertama **Siklus** menyatukan target → anggaran → omzet →
 * marjin → ROI dalam satu layar (satu permintaan ke `/api/marketing/cycle/overview`).
 * Tab lama (Platform Akun / KOL / Budget) DIPERTAHANKAN karena keduanya menjawab
 * pertanyaan berbeda: Siklus untuk "bagaimana bulan ini berjalan", tab lama untuk
 * menyetel angka per baris.
 *
 * Modul yang SAMA dipakai dua portal (`marketing-targets` & `mgmt-marketing-cycle`)
 * lewat prop `scope` — bukan dua salinan komponen, supaya Marketing dan Manajemen
 * tidak bisa melihat angka yang berbeda.
 */
import { useState, useEffect, useCallback } from 'react';
import { Target, RefreshCw, ChevronLeft, ChevronRight, Save, Loader2, Users, FileDown, Wallet, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AccountBadge } from './AccountBadge';
import BudgetAllocationTab from './BudgetAllocationTab';
import CycleView from './CycleView';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const MONTH_NAMES = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des'];

// ─── Shared helper components ─────────────────────────────────────────────────
function ProgressBar({ pct, status }) {
  const colors = { on_track:'bg-emerald-500', warning:'bg-amber-500', behind:'bg-red-500', no_target:'bg-muted' };
  return (
    <div className="h-1.5 bg-muted rounded-full overflow-hidden mt-1">
      <div className={`h-full transition-all ${colors[status] || 'bg-primary'}`}
        style={{ width: `${Math.min(pct || 0, 100)}%` }} />
    </div>
  );
}

function StatusBadge({ status, pct }) {
  if (status === 'no_target') return <Badge variant="outline" className="text-[10px] text-muted-foreground">Belum set</Badge>;
  const cfg = { on_track:'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 border-emerald-400 dark:border-emerald-500/30', warning:'bg-amber-100 dark:bg-amber-500/10 text-amber-600 border-amber-400 dark:border-amber-500/30', behind:'bg-red-100 dark:bg-red-500/10 text-red-600 border-red-400 dark:border-red-500/30' };
  return <Badge variant="outline" className={`text-[10px] ${cfg[status] || ''}`}>{pct}%</Badge>;
}

// ─── Account Target Form Dialog ───────────────────────────────────────────────
function TargetFormDialog({ open, onOpenChange, account, year, month, existingTarget, onSaved, token }) {
  const [form, setForm] = useState({ revenue_target:'', orders_target:'', health_score_target:80, notes:'', reason:'' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setForm({
      revenue_target:      existingTarget?.revenue_target      || '',
      orders_target:       existingTarget?.orders_target       || '',
      health_score_target: existingTarget?.health_score_target ?? 80,
      notes:               existingTarget?.notes               || '',
      reason:              '',
    });
  }, [open, existingTarget]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/targets`, {
        method: 'POST',
        headers: { Authorization:`Bearer ${token}`, 'Content-Type':'application/json' },
        body: JSON.stringify({
          account_id: account.id, year, month,
          revenue_target: parseFloat(form.revenue_target) || 0,
          orders_target:  parseInt(form.orders_target)    || 0,
          health_score_target: parseInt(form.health_score_target) || 80,
          notes: form.notes || null,
          reason: form.reason || null,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Gagal simpan');
      toast.success(`Target ${account.account_name} ${MONTH_NAMES[month-1]} disimpan`);
      onSaved(); onOpenChange(false);
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Target size={16} className="text-primary" /> Set Target — {account?.account_name}</DialogTitle>
          <p className="text-xs text-muted-foreground">{MONTH_NAMES[month-1]} {year}</p>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          {account && <AccountBadge account={account} size="sm" />}
          <div><Label className="text-xs">Target Revenue (Rp)</Label>
            <Input type="number" min={0} value={form.revenue_target} onChange={e=>setForm(f=>({...f,revenue_target:e.target.value}))} placeholder="50000000" className="mt-1 h-9" data-testid="target-revenue-input" /></div>
          <div><Label className="text-xs">Target Orders</Label>
            <Input type="number" min={0} value={form.orders_target} onChange={e=>setForm(f=>({...f,orders_target:e.target.value}))} placeholder="500" className="mt-1 h-9" data-testid="target-orders-input" /></div>
          <div><Label className="text-xs">Target Health Score (0–100)</Label>
            <Input type="number" min={0} max={100} value={form.health_score_target} onChange={e=>setForm(f=>({...f,health_score_target:e.target.value}))} className="mt-1 h-9" data-testid="target-health-input" /></div>
          <div><Label className="text-xs">Catatan (opsional)</Label>
            <Input value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} placeholder="Strategi bulan ini..." className="mt-1 h-9" /></div>
          <div><Label className="text-xs">Alasan perubahan (opsional, masuk jejak)</Label>
            <Input value={form.reason} onChange={e=>setForm(f=>({...f,reason:e.target.value}))}
              placeholder="mis. target dinaikkan setelah kampanye 8.8 disetujui"
              className="mt-1 h-9" data-testid="target-reason-input" />
            <p className="text-[10px] text-muted-foreground mt-1">
              Tampil di layar <b>Jejak Perubahan</b> bersama nilai lama → baru.
            </p></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={()=>onOpenChange(false)}>Batal</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="target-save-btn">
            {saving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />} Simpan Target
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Creator Target Form Dialog ───────────────────────────────────────────────
function CreatorTargetFormDialog({ open, onOpenChange, creator, year, month, existingTarget, onSaved, token }) {
  const [form, setForm] = useState({ revenue_target:'', sessions_target:'', viewers_target:'', notes:'' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setForm({
      revenue_target:  existingTarget?.revenue  || '',
      sessions_target: existingTarget?.sessions || '',
      viewers_target:  existingTarget?.viewers  || '',
      notes:           existingTarget?.notes    || '',
    });
  }, [open, existingTarget]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/targets/creator`, {
        method: 'POST',
        headers: { Authorization:`Bearer ${token}`, 'Content-Type':'application/json' },
        body: JSON.stringify({
          creator_id: creator.id, year, month,
          revenue_target:  parseFloat(form.revenue_target)  || 0,
          sessions_target: parseInt(form.sessions_target)   || 0,
          viewers_target:  parseInt(form.viewers_target)    || 0,
          notes: form.notes || null,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Gagal simpan');
      toast.success(`Target ${creator.name} ${MONTH_NAMES[month-1]} disimpan`);
      onSaved(); onOpenChange(false);
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="creator-target-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Target size={16} className="text-primary" /> Target KOL — {creator?.name}</DialogTitle>
          <p className="text-xs text-muted-foreground">{MONTH_NAMES[month-1]} {year}</p>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div><Label className="text-xs">Target Revenue (Rp)</Label>
            <Input type="number" min={0} value={form.revenue_target} onChange={e=>setForm(f=>({...f,revenue_target:e.target.value}))} placeholder="50000000" className="mt-1 h-9" data-testid="creator-target-revenue" /></div>
          <div><Label className="text-xs">Target Sessions (jumlah live)</Label>
            <Input type="number" min={0} value={form.sessions_target} onChange={e=>setForm(f=>({...f,sessions_target:e.target.value}))} placeholder="12" className="mt-1 h-9" data-testid="creator-target-sessions" /></div>
          <div><Label className="text-xs">Target Viewers (total)</Label>
            <Input type="number" min={0} value={form.viewers_target} onChange={e=>setForm(f=>({...f,viewers_target:e.target.value}))} placeholder="80000" className="mt-1 h-9" data-testid="creator-target-viewers" /></div>
          <div><Label className="text-xs">Catatan (opsional)</Label>
            <Input value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} placeholder="Strategi bulan ini..." className="mt-1 h-9" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={()=>onOpenChange(false)}>Batal</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="creator-target-save-btn">
            {saving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />} Simpan Target
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN MODULE
// ══════════════════════════════════════════════════════════════════════════════
export default function AccountTargetsModule({ token, scope = 'marketing', moduleId }) {
  const now = new Date();
  const [year, setYear]   = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  // Tab awal ditentukan dari PROP (bukan sessionStorage): pelajaran sesi #5 —
  // petunjuk tab lewat sessionStorage bergantung urutan mount, sehingga deep-link
  // mendarat di tab pertama dan layar yang diminta seolah tidak ada.
  const [activeTab, setActiveTab] = useState('cycle');

  // Account targets
  const [summary, setSummary]     = useState(null);
  const [accounts, setAccounts]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [editAccount, setEditAccount]   = useState(null);
  const [editTarget, setEditTarget]     = useState(null);
  const [dialogOpen, setDialogOpen]     = useState(false);

  // Creator targets
  const [creatorSummary, setCreatorSummary]   = useState(null);
  const [creators, setCreators]               = useState([]);
  const [loadingCreator, setLoadingCreator]   = useState(true);
  const [editCreator, setEditCreator]         = useState(null);
  const [editCreatorTarget, setEditCreatorTarget] = useState(null);
  const [creatorDialogOpen, setCreatorDialogOpen] = useState(false);
  const [exportingCreator, setExportingCreator]   = useState(false);

  const authH = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sumRes, accRes] = await Promise.all([
        fetch(`${API}/api/marketing/targets/monthly-summary?year=${year}&month=${month}`, { headers: authH }),
        fetch(`${API}/api/marketing/accounts?status=active`, { headers: authH }),
      ]);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (accRes.ok) setAccounts(await accRes.json());
    } catch { toast.error('Gagal memuat data akun'); }
    finally { setLoading(false); }
  }, [year, month, token]); // eslint-disable-line

  const loadCreators = useCallback(async () => {
    setLoadingCreator(true);
    try {
      const [sumRes, crRes] = await Promise.all([
        fetch(`${API}/api/marketing/targets/creator/monthly-summary?year=${year}&month=${month}`, { headers: authH }),
        fetch(`${API}/api/marketing/kol/creators?limit=100`, { headers: authH }),
      ]);
      if (sumRes.ok) setCreatorSummary(await sumRes.json());
      if (crRes.ok) {
        const data = await crRes.json();
        setCreators(Array.isArray(data) ? data : (data.creators || []));
      }
    } catch { toast.error('Gagal memuat data creator'); }
    finally { setLoadingCreator(false); }
  }, [year, month, token]); // eslint-disable-line

  useEffect(() => { load(); loadCreators(); }, [load, loadCreators]);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y-1); } else setMonth(m => m-1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y+1); } else setMonth(m => m+1); };

  const openEdit = (row) => {
    setEditAccount(accounts.find(a => a.id === row.account_id) || row);
    setEditTarget(row.target.revenue != null ? row : null);
    setDialogOpen(true);
  };

  const openEditCreator = (row) => {
    setEditCreator(creators.find(c => c.id === row.creator_id) || { id: row.creator_id, name: row.creator_name });
    setEditCreatorTarget(row.target.revenue != null ? row.target : null);
    setCreatorDialogOpen(true);
  };

  const handleExportCreatorPDF = async () => {
    setExportingCreator(true);
    try {
      const res = await fetch(
        `${API}/api/marketing/targets/creator/export-pdf?year=${year}&month=${month}`,
        { headers: authH }
      );
      if (!res.ok) throw new Error('Gagal generate PDF');
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `target-creator-${MONTH_NAMES[month-1].toLowerCase()}-${year}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF target creator berhasil didownload');
    } catch (e) { toast.error(e.message); }
    finally { setExportingCreator(false); }
  };

  const s  = summary?.summary || {};
  const cs = creatorSummary?.summary || {};

  return (
    <div className="space-y-5 p-4 lg:p-6" data-testid="account-targets-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Target size={22} className="text-primary" />
            {scope === 'management' ? 'Siklus Marketing — Semua Toko' : 'Siklus Target, Anggaran & Omzet'}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Satu layar: target → rencana anggaran → omzet nyata → realisasi → marjin → ROI,
            per toko &amp; gabungan{scope === 'management' ? ' (tampilan Manajemen)' : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prevMonth} data-testid="cycle-prev-month"
            aria-label="Bulan sebelumnya"><ChevronLeft size={14} /></Button>
          <span className="font-semibold text-sm min-w-[120px] text-center" data-testid="cycle-period-label">{MONTH_NAMES[month-1]} {year}</span>
          <Button variant="outline" size="sm" onClick={nextMonth} data-testid="cycle-next-month"
            aria-label="Bulan berikutnya"><ChevronRight size={14} /></Button>
          <Button variant="outline" size="sm" onClick={() => { load(); loadCreators(); }}
            data-testid="cycle-reload-all" aria-label="Muat ulang">
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="cycle" data-testid="tab-cycle">
            <Activity size={13} className="mr-1.5" /> Siklus Bulan Ini
          </TabsTrigger>
          <TabsTrigger value="accounts" data-testid="tab-accounts">
            <Target size={13} className="mr-1.5" /> Platform Akun
          </TabsTrigger>
          <TabsTrigger value="creators" data-testid="tab-creators">
            <Users size={13} className="mr-1.5" /> KOL / Creator
          </TabsTrigger>
          <TabsTrigger value="budget" data-testid="tab-budget">
            <Wallet size={13} className="mr-1.5" /> Budget &amp; Alokasi
          </TabsTrigger>
        </TabsList>

        {/* ── TAB SIKLUS (F5) ── */}
        <TabsContent value="cycle" className="mt-4">
          <CycleView
            token={token}
            scope={scope}
            moduleId={moduleId}
            period={`${year}-${String(month).padStart(2, '0')}`}
            monthLabel={`${MONTH_NAMES[month - 1]} ${year}`}
          />
        </TabsContent>

        {/* ── TAB AKUN ── */}
        <TabsContent value="accounts" className="mt-4 space-y-4">
          {s.total_accounts > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <GlassCard className="p-4"><p className="text-xs text-muted-foreground">Total Akun</p><p className="text-2xl font-bold">{s.total_accounts}</p></GlassCard>
              <GlassCard className="p-4">
                <p className="text-xs text-muted-foreground">Revenue Actual</p>
                <p className="text-base font-bold">{fmtRp(s.rev_actual)}</p>
                {s.rev_target > 0 && <p className="text-xs text-muted-foreground">/ {fmtRp(s.rev_target)}</p>}
              </GlassCard>
              <GlassCard className="p-4">
                <p className="text-xs text-muted-foreground">Orders Actual</p>
                <p className="text-2xl font-bold">{fmtNum(s.ord_actual)}</p>
                {s.ord_target > 0 && <p className="text-xs text-muted-foreground">/ {fmtNum(s.ord_target)}</p>}
              </GlassCard>
              <GlassCard className={`p-4 ${s.rev_pct >= 90 ? 'border-emerald-400 dark:border-emerald-500/30 bg-emerald-100 dark:bg-emerald-500/5' : s.rev_pct >= 70 ? 'border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5' : 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5'}`}>
                <p className="text-xs text-muted-foreground">Pencapaian Revenue</p>
                <p className={`text-2xl font-bold ${s.rev_pct >= 90 ? 'text-emerald-600' : s.rev_pct >= 70 ? 'text-amber-600' : 'text-red-600'}`}>{s.rev_pct != null ? `${s.rev_pct}%` : '—'}</p>
              </GlassCard>
            </div>
          )}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Target vs Aktual per Akun</CardTitle></CardHeader>
            <CardContent className="p-0">
              {loading ? <div className="py-10 text-center text-muted-foreground text-sm"><Loader2 className="mx-auto animate-spin" size={20} /></div>
              : !summary?.accounts?.length ? <div className="py-10 text-center text-muted-foreground text-sm">Belum ada akun aktif</div>
              : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="targets-table">
                    <thead><tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 text-left">Akun</th>
                      <th className="px-4 py-2.5 text-right">Revenue</th>
                      <th className="px-4 py-2.5 text-right">Orders</th>
                      <th className="px-4 py-2.5 text-right">Health</th>
                      <th className="px-4 py-2.5 text-right">Task</th>
                      <th className="px-4 py-2.5 text-center">Aksi</th>
                    </tr></thead>
                    <tbody className="divide-y">
                      {summary.accounts.map(row => (
                        <tr key={row.account_id} className="hover:bg-muted/20" data-testid={`target-row-${row.account_code}`}>
                          <td className="px-4 py-3"><AccountBadge account={row} size="xs" /></td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-semibold text-xs">{fmtRp(row.actual.revenue)}</div>
                            {row.target.revenue != null && <><div className="text-[10px] text-muted-foreground">/ {fmtRp(row.target.revenue)}</div><ProgressBar pct={row.achievement.revenue_pct} status={row.achievement.revenue_status} /></>}
                            <StatusBadge status={row.achievement.revenue_status} pct={row.achievement.revenue_pct} />
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-semibold text-xs">{fmtNum(row.actual.orders)}</div>
                            {row.target.orders != null && <><div className="text-[10px] text-muted-foreground">/ {fmtNum(row.target.orders)}</div><ProgressBar pct={row.achievement.orders_pct} status={row.achievement.orders_status} /></>}
                            <StatusBadge status={row.achievement.orders_status} pct={row.achievement.orders_pct} />
                          </td>
                          <td className="px-4 py-3 text-right text-xs">
                            <span className={`font-bold ${row.health_score >= 80 ? 'text-emerald-600' : row.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>{row.health_score ?? 'N/A'}</span>
                          </td>
                          <td className="px-4 py-3 text-right text-xs">
                            <span className="font-semibold">{row.task_stats.done}</span>
                            <span className="text-muted-foreground"> / {row.task_stats.total}</span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openEdit(row)} data-testid={`set-target-${row.account_code}`}>
                              <Target size={11} className="mr-1" />{row.target.revenue != null ? 'Edit' : 'Set'}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB KOL / CREATOR ── */}
        <TabsContent value="creators" className="mt-4 space-y-4">
          {cs.total_creators > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <GlassCard className="p-4"><p className="text-xs text-muted-foreground">Total Creator</p><p className="text-2xl font-bold">{cs.total_creators}</p></GlassCard>
              <GlassCard className="p-4">
                <p className="text-xs text-muted-foreground">Revenue Actual</p>
                <p className="text-base font-bold">{fmtRp(cs.rev_actual)}</p>
                {cs.rev_target > 0 && <p className="text-xs text-muted-foreground">/ {fmtRp(cs.rev_target)}</p>}
              </GlassCard>
              <GlassCard className={`p-4 ${cs.rev_pct >= 90 ? 'border-emerald-400 dark:border-emerald-500/30 bg-emerald-100 dark:bg-emerald-500/5' : cs.rev_pct >= 70 ? 'border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5' : 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5'}`}>
                <p className="text-xs text-muted-foreground">Pencapaian Revenue</p>
                <p className={`text-2xl font-bold ${cs.rev_pct >= 90 ? 'text-emerald-600' : cs.rev_pct >= 70 ? 'text-amber-600' : 'text-red-600'}`}>{cs.rev_pct != null ? `${cs.rev_pct}%` : '—'}</p>
              </GlassCard>
              <GlassCard className="p-4">
                <p className="text-xs text-muted-foreground">Total Sessions</p>
                <p className="text-2xl font-bold">{creatorSummary?.creators?.reduce((s,c) => s+(c.actual?.sessions||0), 0) || 0}</p>
              </GlassCard>
            </div>
          )}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-1.5">
                  <Users size={13} className="text-violet-500" /> Target vs Aktual per KOL/Creator
                </CardTitle>
                <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5"
                  onClick={handleExportCreatorPDF}
                  disabled={exportingCreator || loadingCreator}
                  data-testid="export-creator-pdf-btn">
                  {exportingCreator ? <Loader2 size={12} className="animate-spin" /> : <FileDown size={12} />}
                  Export PDF
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loadingCreator ? <div className="py-10 text-center text-muted-foreground text-sm"><Loader2 className="mx-auto animate-spin" size={20} /></div>
              : !creatorSummary?.creators?.length ? <div className="py-10 text-center text-muted-foreground text-sm">Belum ada creator aktif</div>
              : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="creator-targets-table">
                    <thead><tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 text-left">Creator</th>
                      <th className="px-4 py-2.5 text-right">Revenue</th>
                      <th className="px-4 py-2.5 text-right">Sessions</th>
                      <th className="px-4 py-2.5 text-right">Viewers</th>
                      <th className="px-4 py-2.5 text-center">Aksi</th>
                    </tr></thead>
                    <tbody className="divide-y">
                      {creatorSummary.creators.map(row => (
                        <tr key={row.creator_id} className="hover:bg-muted/20" data-testid={`creator-target-row-${row.creator_code}`}>
                          <td className="px-4 py-3">
                            <div className="text-sm font-medium">{row.creator_name}</div>
                            <div className="text-xs text-muted-foreground font-mono">{row.creator_code}</div>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-semibold text-xs">{fmtRp(row.actual.revenue)}</div>
                            {row.target.revenue != null && <><div className="text-[10px] text-muted-foreground">/ {fmtRp(row.target.revenue)}</div><ProgressBar pct={row.achievement.revenue_pct} status={row.achievement.revenue_status} /></>}
                            <StatusBadge status={row.achievement.revenue_status} pct={row.achievement.revenue_pct} />
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-semibold text-xs">{row.actual.sessions}</div>
                            {row.target.sessions != null && <div className="text-[10px] text-muted-foreground">/ {row.target.sessions}</div>}
                            {row.achievement.sessions_pct != null && <span className="text-[10px] text-muted-foreground">{row.achievement.sessions_pct}%</span>}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-semibold text-xs">{fmtNum(row.actual.viewers)}</div>
                            {row.target.viewers != null && <div className="text-[10px] text-muted-foreground">/ {fmtNum(row.target.viewers)}</div>}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openEditCreator(row)} data-testid={`set-creator-target-${row.creator_code}`}>
                              <Target size={11} className="mr-1" />{row.target.revenue != null ? 'Edit' : 'Set'}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB BUDGET & ALOKASI ── */}
        <TabsContent value="budget" className="mt-4">
          <BudgetAllocationTab
            token={token}
            accounts={accounts}
            period={`${year}-${String(month).padStart(2, '0')}`}
            monthLabel={`${MONTH_NAMES[month - 1]} ${year}`}
          />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      {editAccount && (
        <TargetFormDialog open={dialogOpen} onOpenChange={setDialogOpen}
          account={editAccount} year={year} month={month}
          existingTarget={editTarget?.target} onSaved={load} token={token} />
      )}
      {editCreator && (
        <CreatorTargetFormDialog open={creatorDialogOpen} onOpenChange={setCreatorDialogOpen}
          creator={editCreator} year={year} month={month}
          existingTarget={editCreatorTarget} onSaved={loadCreators} token={token} />
      )}
    </div>
  );
}
