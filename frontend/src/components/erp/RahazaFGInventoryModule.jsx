import { useState, useEffect, useCallback } from 'react';
import {
  Archive, Search, TrendingUp, TrendingDown, RefreshCw,
  ArrowDownCircle, ArrowUpCircle, Activity, Info,
  MinusCircle, CheckCircle2, AlertCircle, ChevronDown, X,
  Grid3X3, Table as TableIcon,
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import FGStockMatrixView from './FGStockMatrixView';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const REASON_OPTIONS = [
  { value: 'surat_jalan_internal', label: 'Surat Jalan Internal',  color: 'text-blue-300 border-blue-300/30 bg-blue-400/10' },
  { value: 'sample',               label: 'Sample / Contoh',       color: 'text-purple-300 border-purple-300/30 bg-purple-400/10' },
  { value: 'koreksi_stok',         label: 'Koreksi Stok (Adjustment)', color: 'text-amber-300 border-amber-300/30 bg-amber-400/10' },
  { value: 'retur',                label: 'Retur / Rusak',          color: 'text-red-300 border-red-300/30 bg-red-400/10' },
  { value: 'lainnya',              label: 'Lainnya',                color: 'text-muted-foreground border-[var(--glass-border)] bg-[var(--glass-bg)]' },
];

const SOURCE_LABEL = {
  production_internal:    { label: 'Produksi Internal',  cls: 'text-blue-300 border-blue-300/30 bg-blue-400/10' },
  production_customer_po: { label: 'Customer PO',        cls: 'text-amber-300 border-amber-300/30 bg-amber-400/10' },
  production_packing_event: { label: 'Output Packing',  cls: 'text-emerald-300 border-emerald-300/30 bg-emerald-400/10' },
  shipment_dispatch:      { label: 'Surat Jalan',        cls: 'text-rose-300 border-rose-300/30 bg-rose-400/10' },
  manual_issue:           { label: 'Issue Manual',       cls: 'text-orange-300 border-orange-300/30 bg-orange-400/10' },
};

const EMPTY_FORM = { material_id: '', qty: '', reason: 'surat_jalan_internal', customer_id: undefined, reference_number: '', notes: '' };

export default function RahazaFGInventoryModule({ token }) {
  const { toast } = useToast();
  const [items,     setItems]     = useState([]);
  const [stocks,    setStocks]    = useState({});
  const [movements, setMovements] = useState([]);
  const [issues,    setIssues]    = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [search,    setSearch]    = useState('');
  const [activeTab, setActiveTab] = useState('stock');
  const [showIssueForm, setShowIssueForm] = useState(false);
  const [form,      setForm]      = useState(EMPTY_FORM);
  // SESI #27 — nomor dokumen pengeluaran FG mengikuti kebijakan owner.
  const numPolicy = useDocNumberPolicy('rahaza_fg_issues.issue_number',
                                       localStorage.getItem('erp_token'));
  const [issueNo, setIssueNo] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [updatedAt, setUpdatedAt] = useState('');

  const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: 'fg' });
      if (search) params.set('search', search);
      const [matR, stockR, movR, issR, custR] = await Promise.all([
        fetch(`/api/rahaza/materials?${params}`, { headers: h }),
        fetch('/api/rahaza/material-stock', { headers: h }),
        fetch('/api/rahaza/fg-movements?limit=100', { headers: h }),
        fetch('/api/rahaza/fg-issues?limit=50', { headers: h }),
        fetch('/api/rahaza/customers?limit=200', { headers: h }),
      ]);
      if (matR.ok)  setItems(await matR.json());
      if (movR.ok)  setMovements(await movR.json());
      if (issR.ok)  setIssues(await issR.json());
      if (custR.ok) setCustomers(await custR.json());
      if (stockR.ok) {
        const sd = await stockR.json();
        const map = {};
        (Array.isArray(sd) ? sd : (sd.rows || [])).forEach(s => {
          map[s.material_id] = (map[s.material_id] || 0) + (s.qty || 0);
        });
        setStocks(map);
      }
      setUpdatedAt(new Date().toLocaleTimeString('id-ID'));
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // KPIs
  const totalQty     = items.reduce((a, m) => a + (stocks[m.id] || 0), 0);
  const totalStocked = items.filter(m => (stocks[m.id] || 0) > 0).length;
  const today        = new Date().toDateString();
  const inToday  = movements.filter(m => m.direction === 'in'  && new Date(m.timestamp).toDateString() === today).reduce((a,m)=>a+m.qty,0);
  const outToday = movements.filter(m => m.direction === 'out' && new Date(m.timestamp).toDateString() === today).reduce((a,m)=>a+m.qty,0);

  // Get current stock for selected FG in form
  const selectedMat   = items.find(m => m.id === form.material_id);
  const availableStock = selectedMat ? (stocks[selectedMat.id] || 0) : 0;

  const handleSubmitIssue = async () => {
    if (!form.material_id)  return toast({ title: 'Pilih produk jadi terlebih dahulu', variant: 'destructive' });
    if (!form.qty || parseFloat(form.qty) <= 0) return toast({ title: 'Qty harus lebih dari 0', variant: 'destructive' });
    if (parseFloat(form.qty) > availableStock)  return toast({ title: `Stok tidak cukup. Tersedia: ${availableStock} pcs`, variant: 'destructive' });
    setSubmitting(true);
    try {
      const res = await fetch('/api/rahaza/fg-issue', {
        method: 'POST',
        headers: h,
        body: JSON.stringify({ ...form, qty: parseInt(form.qty),
                               ...docNumberPayload(numPolicy, 'issue_number', issueNo) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal membuat issue');
      toast({ title: `✅ FG Issue ${data.issue_number} berhasil — ${form.qty} pcs dikurangi dari stok` });
      setForm(EMPTY_FORM);
      setShowIssueForm(false);
      fetchData();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  // RC-UI-03: client-side pagination (10/page) for the 3 tables (top-level hooks)
  const itemsPg     = useClientPagination(items, 10);
  const issuesPg    = useClientPagination(issues, 10);
  const movementsPg = useClientPagination(movements, 10);

  return (
    <div className="space-y-5" data-testid="fg-inventory-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Archive className="w-6 h-6 text-emerald-400" />
            Inventory Produk Jadi
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Stok barang jadi (FG) dari produksi Internal &amp; Customer PO.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => { setShowIssueForm(v => !v); setActiveTab('stock'); }}
            className="gap-1.5 text-xs bg-rose-500/80 hover:bg-rose-500"
            data-testid="fg-issue-btn"
          >
            <MinusCircle className="w-3.5 h-3.5" />
            Keluarkan Stok FG
          </Button>
          <Button variant="ghost" onClick={fetchData} className="gap-1.5 text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <GlassPanel className="p-4 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total SKU</div>
          <div className="text-2xl font-bold text-foreground">{items.length}</div>
        </GlassPanel>
        <GlassPanel className="p-4 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total On Hand</div>
          <div className="text-2xl font-bold text-primary">{totalQty.toLocaleString('id-ID')}</div>
          <div className="text-[10px] text-muted-foreground">pcs</div>
        </GlassPanel>
        <GlassPanel className="p-4 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1 flex items-center justify-center gap-1">
            <ArrowDownCircle className="w-3 h-3 text-emerald-400" /> Masuk Hari Ini
          </div>
          <div className="text-2xl font-bold text-emerald-400">+{inToday.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">pcs dari produksi</div>
        </GlassPanel>
        <GlassPanel className="p-4 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1 flex items-center justify-center gap-1">
            <ArrowUpCircle className="w-3 h-3 text-rose-400" /> Keluar Hari Ini
          </div>
          <div className="text-2xl font-bold text-rose-400">-{outToday.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">pcs dikirim/dikeluarkan</div>
        </GlassPanel>
      </div>

      {/* ── ISSUE FORM (slide-in panel) ─────────────────────────────────── */}
      {showIssueForm && (
        <GlassCard className="p-5 border border-rose-400/30 bg-rose-400/5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              <MinusCircle className="w-4 h-4 text-rose-400" />
              Pengeluaran Stok Produk Jadi
            </h3>
            <button onClick={() => setShowIssueForm(false)} className="text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Pilih FG */}
            <div className="md:col-span-2">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Produk Jadi *</label>
              <Select value={form.material_id} onValueChange={v => setForm(f=>({...f, material_id: v, qty: ''}))}>
                <SelectTrigger data-testid="fg-issue-material">
                  <SelectValue placeholder="— Pilih Produk Jadi —" />
                </SelectTrigger>
                <SelectContent>
                  {items.map(m => (
                    <SelectItem key={m.id} value={m.id} disabled={(stocks[m.id]||0) <= 0}>
                      {m.code} — {m.name}
                      <span className={`ml-2 text-xs ${(stocks[m.id]||0) > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                        ({(stocks[m.id]||0)} pcs tersedia)
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {form.material_id && (
                <div className="mt-1 text-xs text-muted-foreground">
                  Stok tersedia: <span className="font-semibold text-foreground">{availableStock} pcs</span>
                </div>
              )}
            </div>

            {/* Qty */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Qty Dikeluarkan (pcs) *</label>
              <GlassInput
                type="number" min="1" max={availableStock}
                value={form.qty}
                onChange={e => setForm(f=>({...f, qty: e.target.value}))}
                placeholder={`max ${availableStock}`}
                data-testid="fg-issue-qty"
              />
              {form.qty && parseFloat(form.qty) > availableStock && (
                <div className="mt-1 text-xs text-rose-400 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> Melebihi stok tersedia
                </div>
              )}
            </div>

            {/* Alasan */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Alasan Pengeluaran *</label>
              <Select value={form.reason} onValueChange={v => setForm(f=>({...f, reason: v}))}>
                <SelectTrigger data-testid="fg-issue-reason">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REASON_OPTIONS.map(r => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Customer (opsional) */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Tujuan / Customer
                <span className="ml-1 text-[10px] opacity-60">(opsional)</span>
              </label>
              <Select value={form.customer_id || undefined} onValueChange={v => setForm(f=>({...f, customer_id: v}))}>
                <SelectTrigger data-testid="fg-issue-customer">
                  <SelectValue placeholder="— Tidak ada —" />
                </SelectTrigger>
                <SelectContent>
                  {customers.map(c => (
                    <SelectItem key={c.id} value={c.id}>{c.code} — {c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Nomor Referensi */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                No. Referensi / SJ Manual
                <span className="ml-1 text-[10px] opacity-60">(opsional)</span>
              </label>
              <GlassInput
                value={form.reference_number}
                onChange={e => setForm(f=>({...f, reference_number: e.target.value}))}
                placeholder="Contoh: SJ-2026-001"
                data-testid="fg-issue-reference"
              />
            </div>

            {/* Catatan */}
            <div className="md:col-span-2">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Catatan</label>
              <GlassInput
                value={form.notes}
                onChange={e => setForm(f=>({...f, notes: e.target.value}))}
                placeholder="Catatan tambahan…"
                data-testid="fg-issue-notes"
              />
            </div>

            {/* SESI #27 — nomor dokumen (otomatis/manual sesuai setelan owner) */}
            <div className="md:col-span-2">
              <DocNumberField
                policy={numPolicy} value={issueNo} onChange={setIssueNo}
                testId="fg-issue-docnum" label="Nomor Pengeluaran Barang Jadi" />
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-5 pt-4 border-t border-[var(--glass-border)]">
            <Button variant="ghost" onClick={() => { setShowIssueForm(false); setForm(EMPTY_FORM); }}>
              Batal
            </Button>
            <Button
              onClick={handleSubmitIssue}
              disabled={submitting || !form.material_id || !form.qty || parseFloat(form.qty) > availableStock}
              className="bg-rose-500 hover:bg-rose-600 gap-2"
              data-testid="fg-issue-submit"
            >
              {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              Konfirmasi Pengeluaran
            </Button>
          </div>
        </GlassCard>
      )}

      {/* Flow Info Banner */}
      <GlassPanel className="p-3 flex items-start gap-3 border border-blue-400/20 bg-blue-400/5">
        <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-muted-foreground leading-relaxed">
          <span className="font-semibold text-foreground mr-1">Alur Stok FG:</span>
          <span className="text-blue-300">Produksi Internal</span> → WO selesai → FG +qty → <b>Keluarkan Stok</b> manual
          <span className="mx-2">|</span>
          <span className="text-amber-300">Customer PO</span> → WO selesai → FG +qty → Surat Jalan dispatch → FG −qty otomatis
        </div>
      </GlassPanel>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="stock" data-testid="fg-tab-stock">
            <Archive className="w-3.5 h-3.5 mr-1.5" /> Stok ({totalStocked}/{items.length} SKU)
          </TabsTrigger>
          <TabsTrigger value="matrix" data-testid="fg-tab-matrix">
            <Grid3X3 className="w-3.5 h-3.5 mr-1.5" /> Matrix Size × Color
          </TabsTrigger>
          <TabsTrigger value="issues" data-testid="fg-tab-issues">
            <MinusCircle className="w-3.5 h-3.5 mr-1.5" /> Pengeluaran ({issues.length})
          </TabsTrigger>
          <TabsTrigger value="movements" data-testid="fg-tab-movements">
            <Activity className="w-3.5 h-3.5 mr-1.5" /> Riwayat ({movements.length})
          </TabsTrigger>
        </TabsList>

        {/* ── STOCK TAB ── */}
        <TabsContent value="stock">
          <GlassCard className="p-0 overflow-hidden">
            <div className="flex items-center gap-3 p-4 border-b border-[var(--glass-border)]">
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <GlassInput placeholder="Cari produk jadi…" className="pl-8 h-8 text-sm"
                  value={search} onChange={e => setSearch(e.target.value)} />
              </div>
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : items.length === 0 ? (
              <div className="text-center py-16 space-y-2">
                <Archive className="w-10 h-10 mx-auto text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Belum ada produk jadi.</p>
                <p className="text-xs text-muted-foreground/70">
                  Otomatis muncul saat WO selesai atau output Packing dicatat.
                </p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
                    <th className="px-4 py-2.5 text-left font-medium">Kode FG</th>
                    <th className="px-4 py-2.5 text-left font-medium">Nama Produk</th>
                    <th className="px-4 py-2.5 text-center font-medium">Stok (pcs)</th>
                    <th className="px-4 py-2.5 text-center font-medium">Status</th>
                    <th className="px-4 py-2.5 text-center font-medium">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {itemsPg.paged.map(m => {
                    const qty = stocks[m.id] || 0;
                    return (
                      <tr key={m.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]">
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-xs bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded">
                            {m.code}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="font-medium text-foreground">{m.name}</div>
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`text-lg font-bold ${qty > 0 ? 'text-emerald-400' : 'text-muted-foreground/50'}`}>
                            {qty.toLocaleString('id-ID')}
                          </span>
                          <span className="text-xs text-muted-foreground ml-1">pcs</span>
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {qty > 0 ? (
                            <Badge variant="outline" className="text-emerald-300 border-emerald-300/30 text-[10px]">
                              <TrendingUp className="w-3 h-3 mr-1" /> Ada Stok
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-muted-foreground text-[10px]">
                              <TrendingDown className="w-3 h-3 mr-1" /> Kosong
                            </Badge>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {qty > 0 && (
                            <button
                              onClick={() => {
                                setForm(f => ({...f, material_id: m.id}));
                                setShowIssueForm(true);
                                window.scrollTo({ top: 0, behavior: 'smooth' });
                              }}
                              className="text-xs text-rose-300 hover:text-rose-200 underline"
                              data-testid={`fg-issue-quick-${m.code}`}
                            >
                              Keluarkan
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {itemsPg.total > 0 && <PaginationLite page={itemsPg.page} totalPages={itemsPg.totalPages} total={itemsPg.total} pageSize={itemsPg.pageSize} onPageChange={itemsPg.setPage} />}
          </GlassCard>
        </TabsContent>

        {/* ── MATRIX TAB (P1-WH-3) ── */}
        <TabsContent value="matrix">
          <FGStockMatrixView
            token={token}
            onCellAction={(action, cell) => {
              if (action === 'issue') {
                setForm(f => ({ ...f, material_id: cell.material_id, qty: '' }));
                setShowIssueForm(true);
                setActiveTab('stock');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }
            }}
          />
        </TabsContent>

        {/* ── ISSUES TAB ── */}
        <TabsContent value="issues">
          <GlassCard className="p-0 overflow-hidden">
            {issues.length === 0 ? (
              <div className="text-center py-16 space-y-2">
                <MinusCircle className="w-10 h-10 mx-auto text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Belum ada pengeluaran stok FG.</p>
                <Button size="sm" variant="outline" onClick={() => setShowIssueForm(true)} className="mt-2">
                  + Buat Pengeluaran
                </Button>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[11px] text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
                    <th className="px-4 py-2 text-left">No. Issue</th>
                    <th className="px-4 py-2 text-left">Produk</th>
                    <th className="px-4 py-2 text-right">Qty</th>
                    <th className="px-4 py-2 text-left">Alasan</th>
                    <th className="px-4 py-2 text-left">Tujuan</th>
                    <th className="px-4 py-2 text-left">Ref</th>
                    <th className="px-4 py-2 text-left">Diproses</th>
                    <th className="px-4 py-2 text-left">Tgl</th>
                  </tr>
                </thead>
                <tbody>
                  {issuesPg.paged.map(iss => {
                    const reason = REASON_OPTIONS.find(r => r.value === iss.reason);
                    return (
                      <tr key={iss.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]">
                        <td className="px-4 py-2 font-mono text-primary">{iss.issue_number}</td>
                        <td className="px-4 py-2">
                          <div className="font-mono text-xs text-emerald-300">{iss.fg_code}</div>
                          <div className="text-muted-foreground truncate max-w-[120px]">{iss.fg_name}</div>
                        </td>
                        <td className="px-4 py-2 text-right font-bold text-rose-400">
                          -{iss.qty} pcs
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${reason?.color || ''}`}>
                            {reason?.label || iss.reason}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">{iss.customer_name || '—'}</td>
                        <td className="px-4 py-2 text-muted-foreground">{iss.reference_number || '—'}</td>
                        <td className="px-4 py-2 text-muted-foreground">{iss.issued_by || '—'}</td>
                        <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                          {new Date(iss.issued_at).toLocaleDateString('id-ID', { day:'2-digit', month:'short' })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {issuesPg.total > 0 && <PaginationLite page={issuesPg.page} totalPages={issuesPg.totalPages} total={issuesPg.total} pageSize={issuesPg.pageSize} onPageChange={issuesPg.setPage} />}
          </GlassCard>
        </TabsContent>

        {/* ── MOVEMENTS TAB ── */}
        <TabsContent value="movements">
          <GlassCard className="p-0 overflow-hidden">
            {movements.length === 0 ? (
              <div className="text-center py-16">
                <Activity className="w-10 h-10 mx-auto text-muted-foreground/30 mb-2" />
                <p className="text-sm text-muted-foreground">Belum ada pergerakan stok FG.</p>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[11px] text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
                    <th className="px-4 py-2 text-left">Waktu</th>
                    <th className="px-4 py-2 text-left">Kode FG</th>
                    <th className="px-4 py-2 text-left">Arah</th>
                    <th className="px-4 py-2 text-right">Qty</th>
                    <th className="px-4 py-2 text-left">Sumber</th>
                    <th className="px-4 py-2 text-left">WO / SJ / Ref</th>
                    <th className="px-4 py-2 text-left">Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {movementsPg.paged.map(mv => {
                    const src = SOURCE_LABEL[mv.source] || { label: mv.source, cls: 'text-muted-foreground border-[var(--glass-border)]' };
                    return (
                      <tr key={mv.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)]">
                        <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                          {new Date(mv.timestamp).toLocaleString('id-ID', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}
                        </td>
                        <td className="px-4 py-2 font-mono text-emerald-300">{mv.fg_code}</td>
                        <td className="px-4 py-2">
                          {mv.direction === 'in' ? (
                            <span className="inline-flex items-center gap-1 text-emerald-300">
                              <ArrowDownCircle className="w-3 h-3" /> Masuk
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-300">
                              <ArrowUpCircle className="w-3 h-3" /> Keluar
                            </span>
                          )}
                        </td>
                        <td className={`px-4 py-2 text-right font-bold ${mv.direction==='in' ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {mv.direction==='in' ? '+' : '-'}{mv.qty}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${src.cls}`}>
                            {src.label}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">
                          {mv.wo_number || mv.shipment_number || mv.reference_number || '—'}
                        </td>
                        <td className="px-4 py-2 text-muted-foreground truncate max-w-[160px]">
                          {mv.notes || '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {movementsPg.total > 0 && <PaginationLite page={movementsPg.page} totalPages={movementsPg.totalPages} total={movementsPg.total} pageSize={movementsPg.pageSize} onPageChange={movementsPg.setPage} />}
          </GlassCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
