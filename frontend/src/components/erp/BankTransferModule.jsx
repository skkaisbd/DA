/**
 * BankTransferModule — Transfer Bank Antar Rekening
 * CV. Dewi Aditya — Phase 6C
 *
 * Fitur:
 *  - Form transfer dari akun A ke akun B
 *  - Auto-posting GL (Dr Bank Tujuan / Cr Bank Sumber)
 *  - History transfer dengan status GL
 *  - Void transfer + retry posting
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ArrowRightLeft, Plus, RefreshCw, CheckCircle2, XCircle,
  Loader2, RotateCcw, AlertCircle, ArrowRight, Banknote
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
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL;
const BASE = `${API}/api/finance/bank-transfers`;

const fmt = formatRupiah;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';

function token() { return localStorage.getItem('erp_token'); }
function userRole() {
  try { return JSON.parse(localStorage.getItem('erp_user') || '{}').role; } catch { return null; }
}

const FINANCE_ROLES = ['superadmin', 'admin', 'owner', 'finance'];

// Bank account list (COA)
const BANK_ACCOUNTS = [
  { code: '1-1101', name: 'Kas Kecil' },
  { code: '1-1201', name: 'Bank BCA' },
  { code: '1-1202', name: 'Bank Mandiri' },
  { code: '1-1203', name: 'Bank BRI' },
  { code: '1-1204', name: 'Bank BNI' },
  { code: '1-1205', name: 'Bank BSI' },
];

// ── Transfer Form Dialog ─────────────────────────────────────────────────────
function TransferDialog({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    from_account_code: '1-1201',
    to_account_code: '1-1202',
    amount: '',
    transfer_date: new Date().toISOString().slice(0, 10),
    memo: '',
    ref_external: '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr]   = useState('');
  const [result, setResult] = useState(null);
  // SESI #27 — kolom nomor dokumen mengikuti kebijakan Otomatis/Manual milik owner.
  // Tanpa ini, mode MANUAL berarti transfer TIDAK BISA dibuat (backend minta nomor
  // yang layarnya tak pernah tampilkan).
  const numPolicy = useDocNumberPolicy('rahaza_bank_transfers.ref_number', token());
  const [refNumber, setRefNumber] = useState('');

  useEffect(() => {
    if (open) {
      setForm({
        from_account_code: '1-1201',
        to_account_code: '1-1202',
        amount: '',
        transfer_date: new Date().toISOString().slice(0, 10),
        memo: '',
        ref_external: '',
      });
      setRefNumber('');
      setErr('');
      setResult(null);
    }
  }, [open]);

  const fromName = BANK_ACCOUNTS.find(a => a.code === form.from_account_code)?.name || form.from_account_code;
  const toName   = BANK_ACCOUNTS.find(a => a.code === form.to_account_code)?.name || form.to_account_code;

  const save = async () => {
    if (!form.amount || parseFloat(form.amount) <= 0) return setErr('Jumlah transfer harus > 0.');
    if (form.from_account_code === form.to_account_code) return setErr('Rekening sumber dan tujuan tidak boleh sama.');
    setSaving(true); setErr('');
    try {
      const res = await fetch(BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
        body: JSON.stringify({
          ...form,
          ...docNumberPayload(numPolicy, 'ref_number', refNumber),
          amount: parseFloat(form.amount),
          from_account_name: fromName,
          to_account_name: toName,
        }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Gagal membuat transfer');
      setResult(d);
      if (d.gl_posting?.ok) {
        toast.success(`Transfer ${d.transfer?.ref_number} berhasil + GL terposting ✅`);
      } else {
        toast.warning(`Transfer dicatat, tapi GL posting gagal: ${d.gl_posting?.error || '?'}`);
      }
      onCreated();
    } catch (e) { setErr(e.message); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Transfer Bank Antar Rekening</DialogTitle>
          <DialogDescription>
            Jurnal otomatis: Dr {toName || '?'} / Cr {fromName || '?'}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="py-4 space-y-3">
            <div className={`flex items-center gap-3 p-3 rounded-lg border ${
              result.gl_posting?.ok
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-700'
            }`}>
              {result.gl_posting?.ok ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
              <div>
                <p className="font-medium text-sm">{result.transfer?.ref_number}</p>
                <p className="text-xs">
                  {result.gl_posting?.ok
                    ? `GL: ${result.gl_posting.je_number} ✅`
                    : `GL Gagal: ${result.gl_posting?.error}`}
                </p>
              </div>
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <div className="flex justify-between">
                <span>Dari:</span><span className="font-medium">{result.transfer?.from_account_name}</span>
              </div>
              <div className="flex justify-between">
                <span>Ke:</span><span className="font-medium">{result.transfer?.to_account_name}</span>
              </div>
              <div className="flex justify-between">
                <span>Jumlah:</span><span className="font-bold text-foreground">{fmt(result.transfer?.amount)}</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3 py-2">
            {err && <div className="text-destructive text-sm bg-destructive/10 rounded px-3 py-2">{err}</div>}

            {/* Preview JE */}
            {form.amount > 0 && (
              <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/40 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{fromName}</span>
                <ArrowRight size={12} />
                <span className="font-medium text-foreground">{toName}</span>
                <span className="ml-auto font-bold text-foreground">{fmt(parseFloat(form.amount || 0))}</span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Rekening Sumber *</Label>
                <Select value={form.from_account_code} onValueChange={v => setForm(p => ({ ...p, from_account_code: v }))}>
                  <SelectTrigger data-testid="from-account"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {BANK_ACCOUNTS.map(a => (
                      <SelectItem key={a.code} value={a.code} disabled={a.code === form.to_account_code}>
                        {a.name} ({a.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Rekening Tujuan *</Label>
                <Select value={form.to_account_code} onValueChange={v => setForm(p => ({ ...p, to_account_code: v }))}>
                  <SelectTrigger data-testid="to-account"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {BANK_ACCOUNTS.map(a => (
                      <SelectItem key={a.code} value={a.code} disabled={a.code === form.from_account_code}>
                        {a.name} ({a.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1">
              <Label>Jumlah (IDR) *</Label>
              <Input
                data-testid="transfer-amount"
                type="number" min="1"
                placeholder="5000000"
                value={form.amount}
                onChange={e => setForm(p => ({ ...p, amount: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Tanggal Transfer</Label>
                <Input type="date" value={form.transfer_date} onChange={e => setForm(p => ({ ...p, transfer_date: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <Label>No. Referensi Bank</Label>
                <Input data-testid="transfer-ref" placeholder="opsional" value={form.ref_external} onChange={e => setForm(p => ({ ...p, ref_external: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Keterangan</Label>
              <Input data-testid="transfer-memo" placeholder="Tujuan transfer" value={form.memo} onChange={e => setForm(p => ({ ...p, memo: e.target.value }))} />
            </div>

            <DocNumberField
              policy={numPolicy} value={refNumber} onChange={setRefNumber}
              testId="transfer-docnum" label="Nomor Dokumen Transfer" />
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={onClose}>Tutup</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={saving}>Batal</Button>
              <Button data-testid="transfer-submit" onClick={save} disabled={saving}>
                {saving && <Loader2 size={13} className="mr-1 animate-spin" />}
                Transfer & Post GL
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Module ────────────────────────────────────────────────────────────────
export default function BankTransferModule() {
  const [transfers, setTransfers] = useState([]);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);

  const role = userRole();
  const canManage = FINANCE_ROLES.includes(role);

  const fetchTransfers = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}?limit=50`, {
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      setTransfers(d.items || []);
      setTotal(d.total || 0);
    } catch { toast.error('Gagal memuat data transfer'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchTransfers(); }, [fetchTransfers]);

  const handleRetry = async (id) => {
    try {
      const r = await fetch(`${BASE}/${id}/retry-posting`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      if (d.ok || d.already_posted) { toast.success('Retry GL berhasil.'); fetchTransfers(); }
      else toast.error(`Retry gagal: ${d.error}`);
    } catch { toast.error('Koneksi bermasalah'); }
  };

  const handleVoid = async (tf) => {
    if (!window.confirm(`Void transfer ${tf.ref_number}? Akan dibuat JE reversal.`)) return;
    try {
      const r = await fetch(`${BASE}/${tf.id}/void`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json();
      if (d.ok) { toast.success(`Transfer ${tf.ref_number} divoid. JE reversal: ${d.je_number}`); fetchTransfers(); }
      else toast.error(d.error || 'Gagal void');
    } catch { toast.error('Koneksi bermasalah'); }
  };

  const unpostedCount = transfers.filter(t => !t.gl_posted && t.status !== 'voided').length;

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Transfer Bank Antar Rekening</h1>
          <p className="text-sm text-muted-foreground">
            Auto-posting GL: Dr Bank Tujuan / Cr Bank Sumber. Tidak perlu input jurnal manual.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchTransfers} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
          {canManage && (
            <Button
              size="sm"
              data-testid="create-transfer-btn"
              onClick={() => setDialogOpen(true)}
              className="gap-2"
            >
              <Plus size={14} /> Transfer Baru
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Total Transfer</p>
            <p className="text-lg font-bold">{total}</p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">GL Terposting</p>
            <p className="text-lg font-bold text-emerald-500">
              {transfers.filter(t => t.gl_posted).length}
            </p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Unposted</p>
            <p className={`text-lg font-bold ${unpostedCount > 0 ? 'text-rose-500' : 'text-muted-foreground'}`}>
              {unpostedCount}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Unposted Alert */}
      {unpostedCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-600">
          <AlertCircle size={14} />
          <span>{unpostedCount} transfer belum terposting ke GL. Klik tombol Retry di baris yang bermasalah.</span>
        </div>
      )}

      {/* Table */}
      <Card className="shadow-[var(--shadow-card)]">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <ArrowRightLeft size={15} className="text-primary" />
            Riwayat Transfer
          </CardTitle>
          {total > 50 && (
            <CardDescription>Menampilkan 50 transfer terbaru dari {total} total.</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="animate-spin text-muted-foreground" />
            </div>
          ) : transfers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
              <ArrowRightLeft size={40} className="opacity-20" />
              <p className="text-sm">Belum ada transfer bank.</p>
              {canManage && (
                <Button size="sm" onClick={() => setDialogOpen(true)}>
                  <Plus size={13} className="mr-1" /> Transfer Pertama
                </Button>
              )}
            </div>
          ) : (
            <div className="rounded-[var(--radius-md)] border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/30">
                    <TableHead className="text-xs uppercase">No. Ref</TableHead>
                    <TableHead className="text-xs uppercase">Tanggal</TableHead>
                    <TableHead className="text-xs uppercase">Dari</TableHead>
                    <TableHead className="text-xs uppercase"></TableHead>
                    <TableHead className="text-xs uppercase">Ke</TableHead>
                    <TableHead className="text-xs uppercase text-right">Jumlah</TableHead>
                    <TableHead className="text-xs uppercase">GL Status</TableHead>
                    <TableHead className="text-xs uppercase">Status</TableHead>
                    {canManage && <TableHead className="w-24 text-xs uppercase">Aksi</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transfers.map(tf => (
                    <TableRow key={tf.id} data-testid={`transfer-row-${tf.id}`}>
                      <TableCell className="font-mono text-xs">{tf.ref_number}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtDate(tf.transfer_date)}</TableCell>
                      <TableCell className="text-sm">{tf.from_account_name || tf.from_account_code}</TableCell>
                      <TableCell><ArrowRight size={12} className="text-muted-foreground" /></TableCell>
                      <TableCell className="text-sm">{tf.to_account_name || tf.to_account_code}</TableCell>
                      <TableCell className="text-right font-semibold text-sm">{fmt(tf.amount)}</TableCell>
                      <TableCell>
                        {tf.gl_posted ? (
                          <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 text-xs gap-1">
                            <CheckCircle2 size={10} /> {tf.gl_je_number || 'Posted'}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="border-rose-500/30 bg-rose-500/10 text-rose-600 text-xs gap-1">
                            <XCircle size={10} /> Unposted
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-xs ${
                          tf.status === 'voided' ? 'text-muted-foreground' : 'text-foreground'
                        }`}>
                          {tf.status === 'voided' ? 'Voided' : 'Selesai'}
                        </Badge>
                      </TableCell>
                      {canManage && (
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {!tf.gl_posted && tf.status !== 'voided' && (
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 gap-1 text-xs"
                                data-testid={`retry-posting-${tf.id}`}
                                onClick={() => handleRetry(tf.id)}
                              >
                                <RotateCcw size={11} /> Retry
                              </Button>
                            )}
                            {tf.status !== 'voided' && (
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 text-xs text-destructive hover:text-destructive"
                                data-testid={`void-transfer-${tf.id}`}
                                onClick={() => handleVoid(tf)}
                              >
                                Void
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <TransferDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreated={fetchTransfers} />
    </div>
  );
}
