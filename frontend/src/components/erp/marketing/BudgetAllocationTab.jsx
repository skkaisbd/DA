/**
 * BudgetAllocationTab — KEPUTUSAN #5 + F5.2
 * Budget marketing per TOKO × BULAN × KATEGORI + realisasi (spend) + compare + ROI.
 *
 * F5.2 (2026-08-13): realisasi kategori `diskon`, `ads`, `komisi`, `kol`, `livehost`
 * kini DIHITUNG SISTEM dari data sumbernya, bukan diketik. Setiap angka otomatis
 * membawa **bukti** (jumlah dokumen sumber) yang ditampilkan di kolom terakhir.
 * Kategori BARU `komisi` (komisi kreator) ditambahkan: sebelumnya biaya penjualan
 * ini tidak punya tempat di rencana anggaran sama sekali.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Wallet, Save, Loader2, Plus, Trash2, TrendingUp, PieChart, Users, RefreshCw, Lock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;

const CATS = [
  { key: 'ads',      label: 'Ads / Iklan',   hint: 'otomatis: data iklan',   color: 'bg-blue-500' },
  { key: 'kol',      label: 'KOL / Kreator',  hint: 'otomatis: fee tetap',    color: 'bg-violet-500' },
  { key: 'komisi',   label: 'Komisi kreator', hint: 'otomatis: % dari omzet', color: 'bg-fuchsia-500' },
  // sesi #34 — host live digaji BULANAN lewat payroll HR (upah per-sesi dihapus)
  { key: 'livehost', label: 'Live Host',      hint: 'otomatis: gaji bulanan HR', color: 'bg-pink-500' },
  { key: 'sample',   label: 'Sample',         hint: 'input manual',           color: 'bg-amber-500' },
  { key: 'diskon',   label: 'Diskon / Promo', hint: 'otomatis: dari pesanan', color: 'bg-emerald-500' },
];
const FEE_TYPES = [
  { v: 'none', l: 'Tidak ada' },
  { v: 'fixed', l: 'Fee tetap (fixed rate)' },
  { v: 'commission', l: 'Komisi (% sales)' },
  { v: 'both', l: 'Fee + Komisi' },
];

function Bar({ pct, over }) {
  return (
    <div className="h-2 bg-muted rounded-full overflow-hidden mt-1">
      <div className={`h-full transition-all ${over ? 'bg-red-500' : 'bg-primary'}`}
        style={{ width: `${Math.min(pct || 0, 100)}%` }} />
    </div>
  );
}

export default function BudgetAllocationTab({ token, accounts, period: periodProp, monthLabel }) {
  const authH = { Authorization: `Bearer ${token}` };
  /* SESI #34 — PERIODE ANGGARAN 7 HARI (default) tanpa membuang mode bulanan.
     Keputusan pemilik: "periode budget menjadi 7 hari yang sebelumnya satu bulan…
     yang saat ini satu bulan jangan dihapus namun bisa dikonfigurasi balik".
     Setelan dibaca dari `/api/marketing/budget/period-settings`; kalau mode
     `weekly`, layar memakai periode 7-hari (kunci = tanggal MULAI) alih-alih
     periode bulanan yang dikirim halaman induk. */
  const [pSettings, setPSettings] = useState(null);
  const [weekStart, setWeekStart] = useState('');
  const weekly = (pSettings?.period_mode || 'weekly') === 'weekly';
  const period = weekly ? (weekStart || pSettings?.current_period || '') : periodProp;

  useEffect(() => {
    fetch(`${API}/api/marketing/budget/period-settings`, { headers: authH })
      .then((r) => r.json())
      .then((d) => {
        if (!d?.settings) return;
        setPSettings(d.settings);
        setWeekStart((w) => w || d.settings.current_period);
      })
      .catch(() => {});
  }, [token]); // eslint-disable-line

  // Pilihan 8 periode 7-hari terakhir, dihitung dari tanggal mulai periode kini.
  const weekOptions = (() => {
    const days = pSettings?.period_days || 7;
    const base = pSettings?.current_period || new Date().toISOString().slice(0, 10);
    const out = [];
    for (let i = 0; i < 8; i += 1) {
      const d = new Date(`${base}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() - i * days);
      const start = d.toISOString().slice(0, 10);
      const e = new Date(d); e.setUTCDate(e.getUTCDate() + days - 1);
      out.push({ start, label: `${start} → ${e.toISOString().slice(0, 10)}` });
    }
    return out;
  })();

  const jsonH = { ...authH, 'Content-Type': 'application/json' };

  const [accountId, setAccountId] = useState('');
  const [budgetForm, setBudgetForm] = useState({ ads: '', kol: '', komisi: '', livehost: '', sample: '', diskon: '' });
  // F6.5 — alasan perubahan angka ikut tercatat di jejak (opsional).
  const [budgetReason, setBudgetReason] = useState('');
  const [summary, setSummary] = useState(null);
  const [spendEntries, setSpendEntries] = useState([]);
  const [kolList, setKolList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savingBudget, setSavingBudget] = useState(false);
  const [newSpend, setNewSpend] = useState({ category: 'ads', amount: '', description: '' });
  const [addingSpend, setAddingSpend] = useState(false);

  // default account
  useEffect(() => {
    if (!accountId && accounts?.length) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  const load = useCallback(async () => {
    if (!accountId || !period) return;
    setLoading(true);
    try {
      const [bRes, sRes, spRes, kRes] = await Promise.all([
        fetch(`${API}/api/marketing/budget?account_id=${accountId}&period=${period}`, { headers: authH }),
        fetch(`${API}/api/marketing/budget/summary?account_id=${accountId}&period=${period}`, { headers: authH }),
        fetch(`${API}/api/marketing/budget/spend?account_id=${accountId}&period=${period}`, { headers: authH }),
        fetch(`${API}/api/marketing/budget/kol-cost?account_id=${accountId}`, { headers: authH }),
      ]);
      if (bRes.ok) {
        const b = await bRes.json();
        const bbc = b.budget_by_category || {};
        const next = {};
        CATS.forEach(c => { next[c.key] = bbc[c.key] || ''; });
        setBudgetForm(next);
      }
      if (sRes.ok) setSummary(await sRes.json());
      if (spRes.ok) setSpendEntries((await spRes.json()).entries || []);
      if (kRes.ok) setKolList((await kRes.json()).creators || []);
    } catch { toast.error('Gagal memuat data budget'); }
    finally { setLoading(false); }
  }, [accountId, period, token]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const saveBudget = async () => {
    setSavingBudget(true);
    try {
      const budget_by_category = {};
      CATS.forEach(c => { budget_by_category[c.key] = parseFloat(budgetForm[c.key]) || 0; });
      const res = await fetch(`${API}/api/marketing/budget`, {
        method: 'PUT', headers: jsonH,
        body: JSON.stringify({ account_id: accountId, period, budget_by_category,
          reason: budgetReason || '' }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Gagal simpan budget');
      toast.success('Budget disimpan');
      setBudgetReason('');
      load();
    } catch (e) { toast.error(e.message); }
    finally { setSavingBudget(false); }
  };

  const addSpend = async () => {
    if (!(parseFloat(newSpend.amount) > 0)) { toast.error('Jumlah spend harus > 0'); return; }
    setAddingSpend(true);
    try {
      const res = await fetch(`${API}/api/marketing/budget/spend`, {
        method: 'POST', headers: jsonH,
        body: JSON.stringify({
          account_id: accountId, period, category: newSpend.category,
          amount: parseFloat(newSpend.amount) || 0, description: newSpend.description || '',
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Gagal catat spend');
      toast.success('Spend dicatat');
      setNewSpend({ category: 'ads', amount: '', description: '' });
      load();
    } catch (e) { toast.error(e.message); }
    finally { setAddingSpend(false); }
  };

  const delSpend = async (id) => {
    try {
      const res = await fetch(`${API}/api/marketing/budget/spend/${id}`, { method: 'DELETE', headers: authH });
      if (!res.ok) throw new Error('Gagal hapus');
      toast.success('Spend dihapus');
      load();
    } catch (e) { toast.error(e.message); }
  };

  const saveKolCost = async (creator) => {
    try {
      const cfg = creator.cost_config || {};
      const res = await fetch(`${API}/api/marketing/budget/kol-cost/${creator.creator_id}`, {
        method: 'PUT', headers: jsonH,
        body: JSON.stringify({
          fee_type: cfg.fee_type || 'none',
          fixed_fee: parseFloat(cfg.fixed_fee) || 0,
          commission_pct: parseFloat(cfg.commission_pct) || 0,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Gagal simpan');
      toast.success(`Konfigurasi biaya "${creator.name}" disimpan`);
      load();
    } catch (e) { toast.error(e.message); }
  };

  const updKol = (idx, patch) => setKolList(list => list.map((k, i) =>
    i === idx ? { ...k, cost_config: { ...(k.cost_config || {}), ...patch } } : k));

  const catMap = {};
  (summary?.categories || []).forEach(c => { catMap[c.category] = c; });
  const srcMap = {};
  (summary?.spend_sources || []).forEach(s => { srcMap[s.category] = s; });

  return (
    <div className="space-y-4" data-testid="budget-allocation-tab">
      {/* Periode terkunci: tombol Simpan akan ditolak 423 — katakan SEBELUM diklik */}
      {summary?.locked && (
        <div className="rounded-md border border-amber-400 dark:border-amber-500/40 bg-amber-100 dark:bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2"
          data-testid="budget-locked-banner">
          <Lock size={14} className="mt-0.5 shrink-0" />
          <span>
            Periode <b>{period}</b> untuk toko ini sudah <b>DITUTUP</b>
            {summary.lock?.closed_by_name ? ` oleh ${summary.lock.closed_by_name}` : ''}
            {summary.lock?.reason ? ` — alasan: ${summary.lock.reason}` : ''}.
            Rencana anggaran & catatan belanja bulan ini tidak bisa diubah sampai periode
            dibuka kembali (Siklus Bulan Ini → tombol kunci).
          </span>
        </div>
      )}
      {/* Account selector */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* SESI #34 — pemilih PERIODE 7 HARI (default). Mode bulanan tetap ada,
            dipilih di Setelan; kalau mode bulanan, pemilih ini tidak muncul dan
            periode diambil dari halaman induk seperti sebelumnya. */}
        {weekly && (
          <div className="min-w-[240px]" data-testid="budget-week-picker-wrap">
            <Label className="text-xs text-muted-foreground">
              Periode {pSettings?.period_days || 7} hari
            </Label>
            <Select value={weekStart} onValueChange={setWeekStart}>
              <SelectTrigger className="h-9 mt-1" data-testid="budget-week-select">
                <SelectValue placeholder="Pilih periode" />
              </SelectTrigger>
              <SelectContent>
                {weekOptions.map((w) => (
                  <SelectItem key={w.start} value={w.start}>{w.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="min-w-[240px]">
          <Label className="text-xs text-muted-foreground">Akun Toko</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="h-9 mt-1" data-testid="budget-account-select">
              <SelectValue placeholder="Pilih akun" />
            </SelectTrigger>
            <SelectContent>
              {(accounts || []).map(a => (
                <SelectItem key={a.id} value={a.id}>{a.account_name} · {a.platform}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Badge variant="outline" className="mt-5">{monthLabel}</Badge>
        <Button variant="outline" size="sm" className="mt-5" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="budget-summary-cards">
          <GlassCard className="p-4"><p className="text-xs text-muted-foreground">Total Budget</p><p className="text-lg font-bold">{fmtRp(summary.total_budget)}</p></GlassCard>
          <GlassCard className="p-4"><p className="text-xs text-muted-foreground">Total Spend</p><p className="text-lg font-bold">{fmtRp(summary.total_spend)}</p></GlassCard>
          <GlassCard className={`p-4 ${summary.total_remaining < 0 ? 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5' : ''}`}>
            <p className="text-xs text-muted-foreground">Sisa Budget</p>
            <p className={`text-lg font-bold ${summary.total_remaining < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtRp(summary.total_remaining)}</p>
          </GlassCard>
          <GlassCard className="p-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1"><TrendingUp size={11} /> ROI</p>
            <p className="text-lg font-bold">{summary.roi_pct}%</p>
            <p className="text-[10px] text-muted-foreground">Sales {fmtRp(summary.sales)}</p>
          </GlassCard>
        </div>
      )}

      {/* Budget plan + compare per category */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5"><PieChart size={14} className="text-primary" /> Rencana Budget vs Realisasi per Kategori</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="budget-category-table">
              <thead><tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                <th className="px-3 py-2 text-left">Kategori</th>
                <th className="px-3 py-2 text-right">Budget (Rp)</th>
                <th className="px-3 py-2 text-right">Realisasi</th>
                <th className="px-3 py-2 text-right">Manual</th>
                <th className="px-3 py-2 text-right">Otomatis</th>
                <th className="px-3 py-2 text-right">Sisa</th>
                <th className="px-3 py-2 text-left w-[160px]">Pemakaian</th>
                <th className="px-3 py-2 text-left">Bukti angka otomatis</th>
              </tr></thead>
              <tbody className="divide-y">
                {CATS.map(c => {
                  const row = catMap[c.key] || {};
                  const src = srcMap[c.key] || {};
                  const over = row.status === 'over';
                  return (
                    <tr key={c.key} data-testid={`budget-cat-${c.key}`}>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${c.color}`} />
                          <span className="font-medium">{c.label}</span>
                          {row.mode && (
                            <Badge variant="outline" className="text-[9px]"
                              data-testid={`budget-mode-${c.key}`}>{row.mode}</Badge>
                          )}
                        </div>
                        <span className="text-[10px] text-muted-foreground ml-4">{c.hint}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <Input type="number" min={0} value={budgetForm[c.key]}
                          data-testid={`budget-input-${c.key}`}
                          onChange={e => setBudgetForm(f => ({ ...f, [c.key]: e.target.value }))}
                          className="h-8 text-right w-32 ml-auto" placeholder="0" />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold" data-testid={`spend-${c.key}`}>{fmtRp(row.spend)}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground">{fmtRp(row.manual)}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground" data-testid={`spend-auto-${c.key}`}>{fmtRp(row.auto)}</td>
                      <td className={`px-3 py-2.5 text-right font-medium ${row.remaining < 0 ? 'text-red-600' : ''}`}>{fmtRp(row.remaining)}</td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center justify-between text-[10px]">
                          <span className={over ? 'text-red-600 font-semibold' : 'text-muted-foreground'}>{row.used_pct || 0}%</span>
                          {over && <Badge variant="outline" className="text-[9px] text-red-600 border-red-400">Over</Badge>}
                        </div>
                        <Bar pct={row.used_pct} over={over} />
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-muted-foreground max-w-[240px]"
                        data-testid={`budget-evidence-${c.key}`}>
                        {src.evidence || (row.mode === 'manual' ? 'hanya dari entri manual' : '—')}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-end justify-end gap-2 mt-3">
            <div className="flex-1 min-w-[220px]">
              <Label className="text-[11px]">Alasan perubahan (opsional, masuk jejak)</Label>
              <Input value={budgetReason} onChange={(e) => setBudgetReason(e.target.value)}
                placeholder="mis. anggaran iklan ditambah untuk kejar target"
                className="mt-1 h-9" data-testid="budget-reason-input" />
            </div>
            <Button size="sm" onClick={saveBudget} disabled={savingBudget || !accountId} data-testid="budget-save-btn">
              {savingBudget ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Save size={13} className="mr-1" />} Simpan Budget
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Manual spend entries */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-1.5"><Wallet size={14} className="text-blue-500" /> Catat Realisasi Manual (biaya yang TIDAK terbaca sistem)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-[11px] text-muted-foreground" data-testid="spend-manual-note">
            Kategori bertanda <b>auto</b> (diskon, ads, komisi, KOL, live host) realisasinya
            sudah dihitung sistem dari data sumbernya. Mencatatnya lagi di sini membuat
            biaya yang sama <b>dihitung dua kali</b> — pakai jalur manual hanya untuk biaya
            yang memang tidak punya sumber data (mis. Sample, atau biaya di luar kebiasaan).
          </p>
          <div className="flex items-end gap-2 flex-wrap">
            <div className="min-w-[150px]">
              <Label className="text-xs">Kategori</Label>
              <Select value={newSpend.category} onValueChange={v => setNewSpend(s => ({ ...s, category: v }))}>
                <SelectTrigger className="h-9 mt-1" data-testid="spend-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATS.map(c => <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="w-40">
              <Label className="text-xs">Jumlah (Rp)</Label>
              <Input type="number" min={0} value={newSpend.amount} data-testid="spend-amount-input"
                onChange={e => setNewSpend(s => ({ ...s, amount: e.target.value }))} className="h-9 mt-1" placeholder="0" />
            </div>
            <div className="flex-1 min-w-[180px]">
              <Label className="text-xs">Keterangan</Label>
              <Input value={newSpend.description} data-testid="spend-desc-input"
                onChange={e => setNewSpend(s => ({ ...s, description: e.target.value }))} className="h-9 mt-1" placeholder="mis. Iklan Shopee CPAS" />
            </div>
            <Button size="sm" className="h-9" onClick={addSpend} disabled={addingSpend || !accountId} data-testid="spend-add-btn">
              {addingSpend ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Tambah
            </Button>
          </div>
          {spendEntries.length > 0 ? (
            <div className="rounded-lg border divide-y max-h-64 overflow-y-auto" data-testid="spend-list">
              {spendEntries.map(e => (
                <div key={e.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">{CATS.find(c => c.key === e.category)?.label || e.category}</Badge>
                    <span className="font-semibold">{fmtRp(e.amount)}</span>
                    <span className="text-xs text-muted-foreground">{e.description}</span>
                  </div>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-red-500" onClick={() => delSpend(e.id)} data-testid={`spend-del-${e.id}`}>
                    <Trash2 size={13} />
                  </Button>
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-muted-foreground text-center py-3">Belum ada entri realisasi manual</p>}
        </CardContent>
      </Card>

      {/* KOL cost config */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-1.5"><Users size={14} className="text-violet-500" /> Konfigurasi Biaya KOL / Kreator (fee tetap &amp; / atau komisi)</CardTitle></CardHeader>
        <CardContent className="p-0">
          {kolList.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">Belum ada kreator yang ditugaskan ke akun ini</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="kol-cost-table">
                <thead><tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                  <th className="px-3 py-2 text-left">Kreator</th>
                  <th className="px-3 py-2 text-left">Skema Bayar</th>
                  <th className="px-3 py-2 text-right">Fee Tetap (Rp)</th>
                  <th className="px-3 py-2 text-right">Komisi (%)</th>
                  <th className="px-3 py-2 text-center">Aksi</th>
                </tr></thead>
                <tbody className="divide-y">
                  {kolList.map((k, idx) => {
                    const cfg = k.cost_config || {};
                    const ft = cfg.fee_type || 'none';
                    return (
                      <tr key={k.creator_id} data-testid={`kol-cost-row-${idx}`}>
                        <td className="px-3 py-2.5"><div className="font-medium">{k.name}</div><div className="text-[10px] text-muted-foreground font-mono">{k.creator_code}</div></td>
                        <td className="px-3 py-2.5">
                          <Select value={ft} onValueChange={v => updKol(idx, { fee_type: v })}>
                            <SelectTrigger className="h-8 w-[170px]" data-testid={`kol-feetype-${idx}`}><SelectValue /></SelectTrigger>
                            <SelectContent>{FEE_TYPES.map(f => <SelectItem key={f.v} value={f.v}>{f.l}</SelectItem>)}</SelectContent>
                          </Select>
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <Input type="number" min={0} value={cfg.fixed_fee ?? ''} disabled={ft === 'none' || ft === 'commission'}
                            data-testid={`kol-fixedfee-${idx}`}
                            onChange={e => updKol(idx, { fixed_fee: e.target.value })} className="h-8 w-28 text-right ml-auto" placeholder="0" />
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <Input type="number" min={0} max={100} value={cfg.commission_pct ?? ''} disabled={ft === 'none' || ft === 'fixed'}
                            data-testid={`kol-commission-${idx}`}
                            onChange={e => updKol(idx, { commission_pct: e.target.value })} className="h-8 w-20 text-right ml-auto" placeholder="0" />
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => saveKolCost(k)} data-testid={`kol-save-${idx}`}>
                            <Save size={11} className="mr-1" /> Simpan
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {summary?.kol_detail?.length > 0 && (
            <div className="px-3 py-2 border-t bg-muted/20 text-xs text-muted-foreground">
              Biaya KOL terhitung bulan ini: {summary.kol_detail.map(d => `${d.creator_name} ${fmtRp(d.cost)}`).join(' · ')}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
