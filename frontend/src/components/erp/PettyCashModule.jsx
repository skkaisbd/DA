/**
 * PettyCashModule — Kas Kecil / Petty Cash
 * CV. Dewi Aditya — Phase 6B
 *
 * Fitur:
 *  - Daftar dana (fund) + saldo real-time
 *  - Buat dana baru + replenish + close
 *  - Input transaksi: expense / advance / return
 *  - History transaksi per fund + GL posting status
 *  - Retry posting jika gagal
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Wallet, Plus, RefreshCw, ChevronRight, AlertCircle,
  CheckCircle2, XCircle, Loader2, ArrowUpCircle, ArrowDownCircle,
  RotateCcw, Receipt, Banknote, Eye
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const BASE = `${API}/api/finance/petty-cash`;
const FINANCE_ROLES = ['superadmin', 'admin', 'owner', 'finance'];

const fmt = formatRupiah;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';

function token() { return localStorage.getItem('erp_token'); }
function userRole() {
  try { return JSON.parse(localStorage.getItem('erp_user') || '{}').role; } catch { return null; }
}

// ── Warna berdasarkan tipe transaksi ──────────────────────────────────────────
const TXN_CONFIG = {
  expense:   { label: 'Pengeluaran',     color: 'text-rose-500',    icon: ArrowUpCircle,   sign: '-' },
  advance:   { label: 'Uang Muka',       color: 'text-orange-500',  icon: ArrowUpCircle,   sign: '-' },
  return:    { label: 'Pengembalian',    color: 'text-emerald-500', icon: ArrowDownCircle, sign: '+' },
  replenish: { label: 'Replenishment',   color: 'text-blue-500',    icon: ArrowDownCircle, sign: '+' },
  opening:   { label: 'Saldo Awal',      color: 'text-blue-400',    icon: ArrowDownCircle, sign: '+' },
};

// ── Create Fund Dialog ─────────────────────────────────────────────────────────
function CreateFundDialog({ open, onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', custodian_name: '', opening_balance: '', bank_account_code: '1-1201' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open) { setForm({ name: '', custodian_name: '', opening_balance: '', bank_account_code: '1-1201' }); setErr(''); }
  }, [open]);

  const save = async () => {
    if (!form.name.trim()) return setErr('Nama dana wajib diisi.');
    setSaving(true); setErr('');
    try {
      const res = await fetch(`${BASE}/funds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ ...form, opening_balance: parseFloat(form.opening_balance || 0) }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Gagal membuat dana');
      toast.success(`Dana "${d.name}" berhasil dibuat.`);
      onCreated();
      onClose();
    } catch (e) { setErr(e.message); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Buat Dana Kas Kecil</DialogTitle>
          <DialogDescription>Dana baru untuk pengeluaran operasional kecil.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {err && <div className="text-destructive text-sm bg-destructive/10 rounded px-3 py-2">{err}</div>}
          <div className="space-y-1">
            <Label>Nama Dana *</Label>
            <Input data-testid="fund-name" placeholder="mis. Kas Kecil Operasional" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label>Nama Kasir / Pengelola</Label>
            <Input data-testid="fund-custodian" placeholder="mis. Budi Santoso" value={form.custodian_name} onChange={e => setForm(p => ({ ...p, custodian_name: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label>Saldo Awal (IDR)</Label>
            <Input data-testid="fund-opening" type="number" min="0" placeholder="0" value={form.opening_balance} onChange={e => setForm(p => ({ ...p, opening_balance: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label>Bank Sumber</Label>
            <Select value={form.bank_account_code} onValueChange={v => setForm(p => ({ ...p, bank_account_code: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1-1201">Bank BCA (1-1201)</SelectItem>
                <SelectItem value="1-1202">Bank Mandiri (1-1202)</SelectItem>
                <SelectItem value="1-1203">Bank BRI (1-1203)</SelectItem>
                <SelectItem value="1-1101">Kas (1-1101)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Batal</Button>
          <Button data-testid="fund-save" onClick={save} disabled={saving}>
            {saving && <Loader2 size={13} className="mr-1 animate-spin" />}
            Buat Dana
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Replenish Dialog ───────────────────────────────────────────────────────────
function ReplenishDialog({ open, fund, onClose, onDone }) {
  const [amount, setAmount] = useState('');
  const [memo, setMemo]   = useState('');
  const [bankCode, setBankCode] = useState('1-1201');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => { if (open) { setAmount(''); setMemo(''); setErr(''); } }, [open]);

  const save = async () => {
    if (!amount || parseFloat(amount) <= 0) return setErr('Jumlah harus > 0.');
    setSaving(true); setErr('');
    try {
      const res = await fetch(`${BASE}/funds/${fund.id}/replenish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ amount: parseFloat(amount), bank_account_code: bankCode, memo }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Gagal replenish');
      toast.success(`Replenishment ${fmt(d.new_balance)} dicatat + GL dipost.`);
      onDone();
      onClose();
    } catch (e) { setErr(e.message); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Replenishment Kas Kecil</DialogTitle>
          <DialogDescription>Isi ulang dana <strong>{fund?.name}</strong>.<br/>Saldo saat ini: <strong>{fmt(fund?.current_balance)}</strong></DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {err && <div className="text-destructive text-sm bg-destructive/10 rounded px-3 py-2">{err}</div>}
          <div className="space-y-1">
            <Label>Jumlah Replenishment (IDR) *</Label>
            <Input data-testid="replenish-amount" type="number" min="1" placeholder="500000" value={amount} onChange={e => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Bank Sumber</Label>
            <Select value={bankCode} onValueChange={setBankCode}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1-1201">Bank BCA (1-1201)</SelectItem>
                <SelectItem value="1-1202">Bank Mandiri (1-1202)</SelectItem>
                <SelectItem value="1-1203">Bank BRI (1-1203)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Keterangan</Label>
            <Input placeholder="opsional" value={memo} onChange={e => setMemo(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Batal</Button>
          <Button data-testid="replenish-confirm" onClick={save} disabled={saving}>
            {saving && <Loader2 size={13} className="mr-1 animate-spin" />}
            Replenish
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Add Expense Dialog ────────────────────────────────────────────────────────
function AddTxnDialog({ open, fund, onClose, onDone }) {
  const [form, setForm] = useState({ txn_type: 'expense', amount: '', category: '', payee: '', memo: '', txn_date: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    if (open) {
      setForm({ txn_type: 'expense', amount: '', category: '', payee: '', memo: '', txn_date: new Date().toISOString().slice(0, 10) });
      setErr('');
      // Fetch categories
      fetch(`${API}/api/hr/expenses/master-categories`, {
        headers: { Authorization: `Bearer ${token()}` }
      }).then(r => r.json()).then(d => setCategories(d.items || [])).catch(() => {});
    }
  }, [open]);

  const save = async () => {
    if (!form.amount || parseFloat(form.amount) <= 0) return setErr('Jumlah harus > 0.');
    setSaving(true); setErr('');
    try {
      const res = await fetch(`${BASE}/transactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ ...form, fund_id: fund.id, amount: parseFloat(form.amount) }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Gagal simpan');
      const glOk = d.gl_posting?.ok;
      toast.success(`Transaksi dicatat. GL: ${glOk ? 'Terposting ✅' : 'Gagal post ⚠️'}`);
      if (!glOk) toast.error(`GL Error: ${d.gl_posting?.error || 'Unknown'}`);
      onDone();
      onClose();
    } catch (e) { setErr(e.message); } finally { setSaving(false); }
  };

  const TXN_TYPES = [
    { value: 'expense', label: 'Pengeluaran (Expense)' },
    { value: 'advance', label: 'Uang Muka (Advance)' },
    { value: 'return',  label: 'Pengembalian (Return)' },
  ];

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Catat Transaksi Kas Kecil</DialogTitle>
          <DialogDescription>Dana: <strong>{fund?.name}</strong> | Saldo: <strong>{fmt(fund?.current_balance)}</strong></DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {err && <div className="text-destructive text-sm bg-destructive/10 rounded px-3 py-2">{err}</div>}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Tipe Transaksi *</Label>
              <Select value={form.txn_type} onValueChange={v => setForm(p => ({ ...p, txn_type: v }))}>
                <SelectTrigger data-testid="txn-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TXN_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Tanggal *</Label>
              <Input type="date" value={form.txn_date} onChange={e => setForm(p => ({ ...p, txn_date: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Jumlah (IDR) *</Label>
            <Input data-testid="txn-amount" type="number" min="1" placeholder="150000" value={form.amount} onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label>Kategori Biaya</Label>
            <Select value={form.category} onValueChange={v => setForm(p => ({ ...p, category: v }))}>
              <SelectTrigger data-testid="txn-category"><SelectValue placeholder="Pilih kategori..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">-- Tanpa Kategori --</SelectItem>
                {categories.map(c => <SelectItem key={c.name} value={c.name}>{c.code ? `${c.code} - ${c.name}` : c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Dibayarkan Ke (Payee)</Label>
            <Input data-testid="txn-payee" placeholder="Nama toko / vendor" value={form.payee} onChange={e => setForm(p => ({ ...p, payee: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label>Keterangan</Label>
            <Input data-testid="txn-memo" placeholder="Deskripsi singkat transaksi" value={form.memo} onChange={e => setForm(p => ({ ...p, memo: e.target.value }))} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Batal</Button>
          <Button data-testid="txn-save" onClick={save} disabled={saving}>
            {saving && <Loader2 size={13} className="mr-1 animate-spin" />}
            Simpan & Post GL
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Fund Card ─────────────────────────────────────────────────────────────────
function FundCard({ fund, onSelect, isActive }) {
  const pct = fund.opening_balance > 0
    ? Math.min(100, (fund.current_balance / fund.opening_balance) * 100)
    : 100;
  const isLow = pct < 25;
  return (
    <Card
      data-testid={`fund-card-${fund.id}`}
      className={`cursor-pointer transition-all shadow-[var(--shadow-card)] ${
        isActive ? 'ring-2 ring-[hsl(var(--primary))]' : 'hover:shadow-md'
      }`}
      onClick={() => onSelect(fund)}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div>
            <p className="font-semibold text-sm text-foreground">{fund.name}</p>
            {fund.custodian_name && (
              <p className="text-xs text-muted-foreground">{fund.custodian_name}</p>
            )}
          </div>
          <Badge variant="outline" className={fund.status === 'active' ? 'border-emerald-500/30 text-emerald-600' : 'text-muted-foreground'}>
            {fund.status === 'active' ? 'Aktif' : 'Tutup'}
          </Badge>
        </div>
        <p className={`text-xl font-bold ${isLow ? 'text-rose-500' : 'text-foreground'}`}>
          {fmt(fund.current_balance)}
        </p>
        {isLow && (
          <p className="text-xs text-rose-500 mt-1 flex items-center gap-1">
            <AlertCircle size={11} /> Saldo rendah — perlu replenishment
          </p>
        )}
        <div className="mt-2 h-1.5 bg-muted rounded-full">
          <div
            className={`h-full rounded-full transition-all ${
              isLow ? 'bg-rose-500' : pct < 50 ? 'bg-amber-500' : 'bg-emerald-500'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </CardContent>
    </Card>
  );
}

// ── Transaction Row ────────────────────────────────────────────────────────────
function TxnRow({ txn, canRetry, onRetry }) {
  const cfg = TXN_CONFIG[txn.txn_type] || TXN_CONFIG.expense;
  const Icon = cfg.icon;
  return (
    <TableRow data-testid={`txn-row-${txn.id}`}>
      <TableCell className="w-8">
        <Icon size={14} className={cfg.color} />
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{fmtDate(txn.txn_date)}</TableCell>
      <TableCell>
        <Badge variant="outline" className="text-xs">{cfg.label}</Badge>
      </TableCell>
      <TableCell className="text-sm max-w-[160px] truncate">
        {txn.payee || txn.memo || txn.category || '—'}
      </TableCell>
      <TableCell className="text-right">
        <span className={`font-semibold text-sm ${cfg.color}`}>
          {cfg.sign}{fmt(txn.amount)}
        </span>
      </TableCell>
      <TableCell>
        {txn.gl_posted ? (
          <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 text-xs gap-1">
            <CheckCircle2 size={10} /> Posted
          </Badge>
        ) : (
          <Badge variant="outline" className="border-rose-500/30 bg-rose-500/10 text-rose-600 text-xs gap-1">
            <XCircle size={10} /> Unposted
          </Badge>
        )}
      </TableCell>
      {canRetry && (
        <TableCell>
          {!txn.gl_posted && (
            <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={() => onRetry(txn)}>
              <RotateCcw size={11} /> Retry
            </Button>
          )}
        </TableCell>
      )}
    </TableRow>
  );
}

// ── Main Module ────────────────────────────────────────────────────────────────
export default function PettyCashModule() {
  const [funds, setFunds] = useState([]);
  const [txns, setTxns]   = useState([]);
  const [activeFund, setActiveFund] = useState(null);
  const [loading, setLoading] = useState(true);
  const [txnLoading, setTxnLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [replenishOpen, setReplenishOpen] = useState(false);
  const [addTxnOpen, setAddTxnOpen] = useState(false);

  const role = userRole();
  const canManage = FINANCE_ROLES.includes(role);

  const fetchFunds = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/funds`, { headers: { Authorization: `Bearer ${token()}` } });
      const d = await r.json();
      const list = d.items || [];
      setFunds(list);
      setActiveFund(prev => {
        if (!prev) return list.length > 0 ? list[0] : null;
        const refreshed = list.find(f => f.id === prev.id);
        return refreshed || prev;
      });
    } catch { toast.error('Gagal memuat dana kas kecil'); }
    finally { setLoading(false); }
  }, []);

  const fetchTxns = useCallback(async (fundId) => {
    if (!fundId) return;
    setTxnLoading(true);
    try {
      const r = await fetch(`${BASE}/transactions?fund_id=${fundId}&limit=50`, {
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      setTxns(d.items || []);
    } catch { toast.error('Gagal memuat transaksi'); }
    finally { setTxnLoading(false); }
  }, []);

  useEffect(() => { fetchFunds(); }, [fetchFunds]);
  useEffect(() => { if (activeFund?.id) fetchTxns(activeFund.id); }, [activeFund?.id, fetchTxns]);

  const handleRetryPosting = async (txn) => {
    try {
      const r = await fetch(`${BASE}/transactions/${txn.id}/retry-posting`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      if (d.ok) { toast.success('Retry berhasil — JE terposting.'); fetchTxns(activeFund.id); }
      else toast.error(`Retry gagal: ${d.error}`);
    } catch { toast.error('Koneksi bermasalah'); }
  };

  const handleCloseFund = async () => {
    if (!activeFund || !window.confirm(`Tutup dana "${activeFund.name}"? Sisa saldo akan dikembalikan ke bank.`)) return;
    try {
      const r = await fetch(`${BASE}/funds/${activeFund.id}/close`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      if (d.ok) { toast.success('Dana ditutup.'); setActiveFund(null); fetchFunds(); }
      else toast.error(d.detail || 'Gagal menutup dana');
    } catch { toast.error('Koneksi bermasalah'); }
  };

  const afterAction = () => { fetchFunds(); if (activeFund) fetchTxns(activeFund.id); };

  const totalBalance = funds.filter(f => f.status === 'active').reduce((s, f) => s + (f.current_balance || 0), 0);
  const unpostedCount = txns.filter(t => !t.gl_posted).length;

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Kas Kecil</h1>
          <p className="text-sm text-muted-foreground">Imprest fund management dengan auto-posting GL.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchFunds} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
          {canManage && (
            <Button size="sm" data-testid="create-fund-btn" onClick={() => setCreateOpen(true)} className="gap-2">
              <Plus size={14} /> Buat Dana Baru
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Total Saldo Aktif</p>
            <p className="text-lg font-bold text-foreground">{fmt(totalBalance)}</p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Jumlah Dana</p>
            <p className="text-lg font-bold">{funds.filter(f => f.status === 'active').length}</p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Transaksi Unposted</p>
            <p className={`text-lg font-bold ${unpostedCount > 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
              {unpostedCount}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* Fund List */}
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Dana Tersedia</p>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-muted-foreground" /></div>
          ) : funds.length === 0 ? (
            <Card className="shadow-[var(--shadow-card)]">
              <CardContent className="pt-6 text-center">
                <Wallet size={32} className="mx-auto opacity-20 mb-2" />
                <p className="text-sm text-muted-foreground">Belum ada dana kas kecil.</p>
                {canManage && (
                  <Button size="sm" className="mt-3" onClick={() => setCreateOpen(true)}>Buat Dana</Button>
                )}
              </CardContent>
            </Card>
          ) : (
            funds.map(f => (
              <FundCard key={f.id} fund={f} isActive={activeFund?.id === f.id} onSelect={setActiveFund} />
            ))
          )}
        </div>

        {/* Fund Detail + Txns */}
        <div className="space-y-4">
          {activeFund ? (
            <>
              {/* Fund Actions */}
              <Card className="shadow-[var(--shadow-card)]">
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="font-semibold text-foreground">{activeFund.name}</h2>
                      <p className="text-sm text-muted-foreground">Saldo: <strong>{fmt(activeFund.current_balance)}</strong></p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        data-testid="add-txn-btn"
                        onClick={() => setAddTxnOpen(true)}
                        disabled={activeFund.status !== 'active'}
                        className="gap-2"
                      >
                        <Receipt size={13} /> Catat Transaksi
                      </Button>
                      {canManage && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid="replenish-btn"
                            onClick={() => setReplenishOpen(true)}
                            disabled={activeFund.status !== 'active'}
                          >
                            <Banknote size={13} className="mr-1" /> Replenish
                          </Button>
                          {activeFund.status === 'active' && (
                            <Button variant="ghost" size="sm" className="text-destructive" onClick={handleCloseFund}>
                              Tutup Dana
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Transaction History */}
              <Card className="shadow-[var(--shadow-card)]">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Receipt size={15} /> Riwayat Transaksi
                  </CardTitle>
                  {unpostedCount > 0 && (
                    <CardDescription className="flex items-center gap-1 text-rose-500">
                      <AlertCircle size={12} /> {unpostedCount} transaksi belum terposting ke GL
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent>
                  {txnLoading ? (
                    <div className="flex justify-center py-8"><Loader2 className="animate-spin text-muted-foreground" /></div>
                  ) : txns.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground text-sm">
                      <Receipt size={32} className="mx-auto opacity-20 mb-2" />
                      Belum ada transaksi pada dana ini.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-muted/30">
                          <TableHead className="w-8" />
                          <TableHead className="text-xs">Tanggal</TableHead>
                          <TableHead className="text-xs">Tipe</TableHead>
                          <TableHead className="text-xs">Keterangan</TableHead>
                          <TableHead className="text-xs text-right">Jumlah</TableHead>
                          <TableHead className="text-xs">GL Status</TableHead>
                          <TableHead className="w-16" />
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {txns.map(t => (
                          <TxnRow key={t.id} txn={t} canRetry={canManage} onRetry={handleRetryPosting} />
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </>
          ) : (
            <Card className="shadow-[var(--shadow-card)]">
              <CardContent className="flex flex-col items-center justify-center py-16 gap-3">
                <Eye size={40} className="opacity-20" />
                <p className="text-sm text-muted-foreground">Pilih dana untuk melihat detail & transaksi.</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Dialogs */}
      <CreateFundDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={afterAction} />
      {activeFund && (
        <>
          <ReplenishDialog open={replenishOpen} fund={activeFund} onClose={() => setReplenishOpen(false)} onDone={afterAction} />
          <AddTxnDialog open={addTxnOpen} fund={activeFund} onClose={() => setAddTxnOpen(false)} onDone={afterAction} />
        </>
      )}
    </div>
  );
}
