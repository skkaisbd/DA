/**
 * Employee Travel Settlement Module
 * CV. Dewi Aditya — Employee Expense Management (EEM) Phase B
 *
 * Features:
 *  - Karyawan: buat settlement aktual setelah pulang dinas
 *  - Manager/HR: approve settlement
 *  - Finance: post GL + lihat outstanding advance monitoring
 *  - GL Reconciliation: Dr Beban Dinas / Cr Uang Muka / Dr-Cr Bank (selisih)
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Plus, RefreshCw, FileText, CheckCircle, XCircle,
  Clock, Send, Banknote, Eye, AlertCircle, Filter,
  TrendingUp, TrendingDown, Minus, Upload, Trash2,
  AlertTriangle, ChevronRight, BarChart3, Download
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { PageHeader, StatTile } from './moduleAtoms';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = formatRupiah;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('id-ID', { day:'2-digit', month:'short', year:'numeric' }) : '—';

const EXPENSE_CATEGORIES = [
  'Transportasi', 'Akomodasi', 'Konsumsi / Makan',
  'Representasi / Entertainment', 'Komunikasi', 'ATK / Perlengkapan',
  'Parkir / Tol', 'Lain-lain'
];

const STATUS_CONFIG = {
  draft:     { label: 'Draft',              color: 'bg-muted text-foreground' },
  submitted: { label: 'Menunggu Approval',  color: 'bg-yellow-100 text-yellow-800' },
  approved:  { label: 'Disetujui — Siap Post', color: 'bg-blue-100 text-blue-800' },
  rejected:  { label: 'Ditolak',            color: 'bg-red-100 text-red-800' },
  posted:    { label: 'Sudah Di-Post GL',   color: 'bg-purple-100 text-purple-800' },
};

const STL_TYPE_CONFIG = {
  return:     { label: 'Kembalian', color: 'text-green-600',  icon: TrendingDown, note: 'Karyawan kembalikan sisa' },
  additional: { label: 'Kurang Bayar', color: 'text-red-600', icon: TrendingUp,   note: 'Perusahaan bayar tambahan' },
  exact:      { label: 'Tepat',     color: 'text-muted-foreground/60', icon: Minus,        note: 'Advance dan aktual sama' },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || { label: status, color: 'bg-muted text-foreground' };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>{c.label}</span>;
}

function ReconciliationCard({ settlement }) {
  const advance = settlement.advance_received || 0;
  const actual  = settlement.total_actual || 0;
  const diff    = settlement.difference || 0;  // advance - actual
  const stlType = settlement.settlement_type || 'exact';
  const stlConf = STL_TYPE_CONFIG[stlType];

  return (
    <div className="rounded-xl border p-4 space-y-3">
      <p className="text-sm font-semibold">Rekonsiliasi Uang Muka</p>
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center rounded-lg bg-blue-50 dark:bg-blue-950/30 p-3">
          <div className="text-xs text-muted-foreground">Uang Muka Diterima</div>
          <div className="text-lg font-bold text-blue-700 dark:text-blue-300">{fmt(advance)}</div>
          <div className="text-xs text-muted-foreground">Debet 1-1610</div>
        </div>
        <div className="text-center rounded-lg bg-orange-50 dark:bg-orange-950/30 p-3">
          <div className="text-xs text-muted-foreground">Biaya Aktual</div>
          <div className="text-lg font-bold text-orange-700 dark:text-orange-300">{fmt(actual)}</div>
          <div className="text-xs text-muted-foreground">Kredit 6-3400</div>
        </div>
        <div className={`text-center rounded-lg p-3 ${
          stlType === 'return' ? 'bg-green-50 dark:bg-green-950/30' :
          stlType === 'additional' ? 'bg-red-50 dark:bg-red-950/30' :
          'bg-muted dark:bg-gray-900/30'
        }`}>
          <div className="text-xs text-muted-foreground">Selisih</div>
          <div className={`text-lg font-bold ${stlConf.color}`}>{fmt(Math.abs(diff))}</div>
          <div className={`text-xs font-medium ${stlConf.color}`}>{stlConf.label}</div>
        </div>
      </div>
      <div className={`text-xs px-3 py-2 rounded-lg ${
        stlType === 'return' ? 'bg-green-50 text-green-800 dark:bg-green-950/30 dark:text-green-300' :
        stlType === 'additional' ? 'bg-red-50 text-red-800 dark:bg-red-950/30 dark:text-red-300' :
        'bg-muted text-foreground'
      }`}>
        {stlType === 'return' && <>✔ Karyawan mengembalikan <b>{fmt(Math.abs(diff))}</b> ke perusahaan (Dr Bank / Cr 1-1610)</>}
        {stlType === 'additional' && <>⚠️ Perusahaan perlu membayar tambahan <b>{fmt(Math.abs(diff))}</b> ke karyawan (Dr 6-3400 / Cr Bank)</>}
        {stlType === 'exact' && <>✔ Uang muka tepat sama dengan biaya aktual — tidak ada selisih</>}
      </div>
    </div>
  );
}

function GLPreview({ settlement }) {
  const advance = settlement.advance_received || 0;
  const actual  = settlement.total_actual || 0;
  const diff    = Math.abs(settlement.difference || 0);
  const stlType = settlement.settlement_type || 'exact';

  return (
    <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
      <p className="text-xs font-semibold text-muted-foreground">PREVIEW JURNAL ENTRY</p>
      <div className="font-mono text-xs space-y-1">
        {actual > 0 && (
          <div className="flex items-center gap-2">
            <span className="w-6 text-blue-600 font-bold">Dr</span>
            <span className="w-20 text-muted-foreground">6-3400</span>
            <span className="flex-1">Biaya Perjalanan Dinas</span>
            <span className="font-bold">{fmt(actual)}</span>
          </div>
        )}
        {advance > 0 && (
          <div className="flex items-center gap-2">
            <span className="w-6 text-purple-600 font-bold">Cr</span>
            <span className="w-20 text-muted-foreground">1-1610</span>
            <span className="flex-1">Uang Muka Karyawan</span>
            <span className="font-bold">{fmt(advance)}</span>
          </div>
        )}
        {stlType === 'return' && diff > 0 && (
          <div className="flex items-center gap-2">
            <span className="w-6 text-blue-600 font-bold">Dr</span>
            <span className="w-20 text-muted-foreground">1-1201</span>
            <span className="flex-1">Bank (terima kembalian)</span>
            <span className="font-bold">{fmt(diff)}</span>
          </div>
        )}
        {stlType === 'additional' && diff > 0 && (
          <div className="flex items-center gap-2">
            <span className="w-6 text-purple-600 font-bold">Cr</span>
            <span className="w-20 text-muted-foreground">1-1201</span>
            <span className="flex-1">Bank (bayar tambahan)</span>
            <span className="font-bold">{fmt(diff)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─ Settlement Form (untuk karyawan buat settlement baru)
function SettlementForm({ token, travel, onClose, onSaved }) {
  const [items, setItems] = useState([{ date: '', category: '', amount: '', notes: '', receipt_url: '' }]);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // SESI #27 — kolom nomor mengikuti kebijakan Otomatis/Manual milik owner.
  const numPolicy = useDocNumberPolicy('employee_travel_settlements.settlement_number', token);
  const [stlNumber, setStlNumber] = useState('');

  const addItem = () => setItems(p => [...p, { date: '', category: '', amount: '', notes: '', receipt_url: '' }]);
  const removeItem = (i) => setItems(p => p.filter((_, idx) => idx !== i));
  const setItem = (i, k, v) => setItems(p => p.map((it, idx) => idx === i ? { ...it, [k]: v } : it));

  const handleReceipt = (i, file) => {
    if (!file || file.size > 5 * 1024 * 1024) { setError('Max 5MB'); return; }
    const r = new FileReader();
    r.onload = (e) => setItem(i, 'receipt_url', e.target.result);
    r.readAsDataURL(file);
  };

  const totalActual = items.reduce((s, it) => s + (parseFloat(it.amount) || 0), 0);
  const advance = travel?.cash_advance_paid || travel?.cash_advance_approved || 0;
  const diff = advance - totalActual;
  const stlType = diff > 0.01 ? 'return' : diff < -0.01 ? 'additional' : 'exact';

  const handleSave = async () => {
    const validItems = items.filter(it => it.date && it.category && parseFloat(it.amount) > 0);
    if (!validItems.length) { setError('Minimal 1 item dengan tanggal, kategori, dan nominal'); return; }
    setSaving(true); setError('');
    try {
      const r = await fetch(`${API}/api/hr/expenses/travel/${travel.id}/settlements`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actual_items: validItems.map(it => ({ ...it, amount: parseFloat(it.amount) })),
          ...docNumberPayload(numPolicy, 'settlement_number', stlNumber),
          notes,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      onSaved(d);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      {/* Trip info */}
      <div className="rounded-lg bg-muted/50 p-3 grid grid-cols-2 gap-2 text-sm">
        <div><span className="text-xs text-muted-foreground">Trip</span><p className="font-mono font-bold">{travel.trip_number}</p></div>
        <div><span className="text-xs text-muted-foreground">Destinasi</span><p className="font-medium">{travel.destination}</p></div>
        <div><span className="text-xs text-muted-foreground">Tanggal</span><p>{fmtDate(travel.start_date)} – {fmtDate(travel.end_date)}</p></div>
        <div><span className="text-xs text-muted-foreground">Uang Muka Diterima</span><p className="font-bold text-blue-700">{fmt(advance)}</p></div>
      </div>

      <DocNumberField
        policy={numPolicy} value={stlNumber} onChange={setStlNumber}
        testId="settlement-docnum" label="Nomor Penyelesaian Dinas" />

      {/* Actual items */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium">Biaya Aktual *</label>
          <Button size="sm" variant="outline" onClick={addItem}><Plus className="w-3.5 h-3.5 mr-1" />Tambah</Button>
        </div>
        <div className="space-y-3">
          {items.map((it, i) => (
            <div key={i} className="border rounded-lg p-3 space-y-2 bg-muted/20">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Tanggal</label>
                  <Input type="date" value={it.date} onChange={e => setItem(i,'date',e.target.value)} className="h-8 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Kategori</label>
                  <Select value={it.category} onValueChange={v => setItem(i,'category',v)}>
                    <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Pilih" /></SelectTrigger>
                    <SelectContent>{EXPENSE_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Nominal (Rp)</label>
                  <Input type="number" placeholder="0" value={it.amount} onChange={e => setItem(i,'amount',e.target.value)} className="h-8 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Keterangan</label>
                  <Input placeholder="opsional" value={it.notes} onChange={e => setItem(i,'notes',e.target.value)} className="h-8 text-sm" />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <label className="text-xs text-muted-foreground flex items-center gap-1 cursor-pointer">
                  <Upload className="w-3 h-3" />Foto Struk
                  <input type="file" accept="image/*" className="hidden" onChange={e => handleReceipt(i, e.target.files[0])} />
                </label>
                {it.receipt_url && <span className="text-xs text-green-600">✓ Uploaded</span>}
                {items.length > 1 && (
                  <Button size="sm" variant="ghost" className="ml-auto h-6 w-6 p-0 text-red-700 dark:text-red-500" onClick={() => removeItem(i)}>
                    <Trash2 className="w-3 h-3" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Reconciliation Preview */}
      <div className="rounded-xl border p-4 space-y-3">
        <p className="text-sm font-semibold">Preview Rekonsiliasi</p>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <div className="text-center p-2 rounded bg-blue-50 dark:bg-blue-950/30">
            <div className="text-xs text-muted-foreground">Uang Muka</div>
            <div className="font-bold text-blue-700 dark:text-blue-300">{fmt(advance)}</div>
          </div>
          <div className="text-center p-2 rounded bg-orange-50 dark:bg-orange-950/30">
            <div className="text-xs text-muted-foreground">Biaya Aktual</div>
            <div className="font-bold text-orange-700 dark:text-orange-300">{fmt(totalActual)}</div>
          </div>
          <div className={`text-center p-2 rounded ${
            stlType==='return' ? 'bg-green-50 dark:bg-green-950/30' :
            stlType==='additional' ? 'bg-red-50 dark:bg-red-950/30' : 'bg-muted'
          }`}>
            <div className="text-xs text-muted-foreground">Selisih</div>
            <div className={`font-bold ${
              stlType==='return' ? 'text-green-700 dark:text-green-300' :
              stlType==='additional' ? 'text-red-700 dark:text-red-300' : 'text-foreground'
            }`}>{fmt(Math.abs(diff))}</div>
            <div className={`text-xs ${
              stlType==='return' ? 'text-green-600' :
              stlType==='additional' ? 'text-red-600' : 'text-muted-foreground/80'
            }`}>
              {stlType === 'return' ? '← Kembalikan' : stlType === 'additional' ? '→ Klaim' : 'Tepat'}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Catatan</label>
        <Textarea placeholder="Keterangan tambahan (opsional)" value={notes} onChange={e => setNotes(e.target.value)} rows={2} />
      </div>

      {error && <div className="text-sm text-red-600 flex items-center gap-1"><AlertCircle className="w-4 h-4" />{error}</div>}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={handleSave} disabled={saving}>{saving ? 'Menyimpan...' : 'Simpan Draft'}</Button>
      </DialogFooter>
    </div>
  );
}

// ─ Settlement Detail + Actions
function SettlementDetail({ stl, token, onClose, onRefresh, role }) {
  const [loading, setLoading] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [note, setNote] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const isApprover = ['superadmin','admin','owner','hr','manager','finance'].includes(role?.toLowerCase());
  const isFinance  = ['superadmin','admin','owner','finance'].includes(role?.toLowerCase());

  const doAction = async (endpoint, body = {}) => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/expenses/settlements/${stl.id}/${endpoint}`, {
        method: 'POST', headers, body: JSON.stringify(body),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Gagal'); }
      onRefresh(); onClose();
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      {/* Header info */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><p className="text-xs text-muted-foreground">Nomor Settlement</p><p className="font-mono font-bold">{stl.settlement_number}</p></div>
        <div><p className="text-xs text-muted-foreground">Status</p><StatusBadge status={stl.status} /></div>
        <div><p className="text-xs text-muted-foreground">Karyawan</p><p className="font-medium">{stl.employee_name}</p></div>
        <div><p className="text-xs text-muted-foreground">Trip</p><p className="font-mono text-xs">{stl.trip_number}</p></div>
        <div className="col-span-2"><p className="text-xs text-muted-foreground">Destinasi</p><p className="font-semibold">{stl.destination}</p></div>
      </div>

      {/* Reconciliation */}
      <ReconciliationCard settlement={stl} />

      {/* GL Preview (hanya untuk finance) */}
      {isFinance && <GLPreview settlement={stl} />}

      {/* Actual items */}
      {(stl.actual_items || []).length > 0 && (
        <div>
          <p className="text-sm font-medium mb-2">Detail Biaya Aktual</p>
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50"><tr>
                <th className="text-left p-2 text-xs">Tgl</th>
                <th className="text-left p-2 text-xs">Kategori</th>
                <th className="text-right p-2 text-xs">Nominal</th>
                <th className="text-left p-2 text-xs">Struk</th>
              </tr></thead>
              <tbody>{(stl.actual_items || []).map((it, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 text-xs">{it.date}</td>
                  <td className="p-2 text-xs">{it.category}</td>
                  <td className="p-2 text-xs text-right font-medium">{fmt(it.amount)}</td>
                  <td className="p-2">
                    {it.receipt_url ? <a href={it.receipt_url} target="_blank" rel="noreferrer" className="text-blue-600 text-xs hover:underline">Lihat</a> : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}

      {/* GL JE info jika sudah posted */}
      {stl.gl_je_number && (
        <div className="rounded-lg bg-purple-50 border border-purple-200 p-3">
          <p className="text-sm font-medium text-purple-800">Journal Entry</p>
          <p className="font-mono text-sm text-purple-700">{stl.gl_je_number}</p>
          <p className="text-xs text-muted-foreground">Dipost oleh {stl.posted_by_name} • {fmtDate(stl.posted_at)}</p>
        </div>
      )}

      {/* Reject reason */}
      {stl.reject_reason && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-3">
          <p className="text-sm font-medium text-red-700">Alasan Ditolak</p>
          <p className="text-sm text-red-600">{stl.reject_reason}</p>
        </div>
      )}

      {/* Reject form */}
      {showReject && (
        <div className="space-y-2">
          <Textarea placeholder="Alasan penolakan" value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} />
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowReject(false)}>Batal</Button>
            <Button variant="destructive" size="sm"
              disabled={!rejectReason.trim() || loading}
              onClick={() => doAction('reject', { reason: rejectReason })}>
              Konfirmasi Tolak
            </Button>
          </div>
        </div>
      )}

      <DialogFooter className="flex-wrap gap-2">
        <Button variant="outline" onClick={onClose}>Tutup</Button>
        {stl.status === 'draft' && (
          <Button size="sm" onClick={() => doAction('submit')} disabled={loading}>
            <Send className="w-3.5 h-3.5 mr-1" />Submit
          </Button>
        )}
        {isApprover && stl.status === 'submitted' && !showReject && (
          <>
            <Button variant="destructive" size="sm" onClick={() => setShowReject(true)} disabled={loading}>Tolak</Button>
            <div className="flex items-center gap-2">
              <Input placeholder="Catatan" className="h-8 text-sm w-36" value={note} onChange={e => setNote(e.target.value)} />
              <Button size="sm" onClick={() => doAction('approve', { note })} disabled={loading}>
                <CheckCircle className="w-3.5 h-3.5 mr-1" />Setujui
              </Button>
            </div>
          </>
        )}
        {isFinance && stl.status === 'approved' && (
          <Button size="sm" className="bg-purple-600 hover:bg-purple-700 text-foreground"
            onClick={() => doAction('post', {})} disabled={loading}>
            <Banknote className="w-3.5 h-3.5 mr-1" />Post GL
          </Button>
        )}
      </DialogFooter>
    </div>
  );
}

// ─ Outstanding Cash Advance Panel
function OutstandingAdvancePanel({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/expenses/outstanding-advances`, { headers });
      setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="p-8 text-center text-muted-foreground">Memuat data outstanding...</div>;
  if (!data || data.total === 0) return (
    <div className="rounded-xl border p-8 text-center text-muted-foreground">
      <CheckCircle className="w-10 h-10 mx-auto mb-3 opacity-30 text-green-500" />
      <p className="font-medium">Tidak ada uang muka outstanding</p>
      <p className="text-sm">Semua advance sudah di-settle.</p>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-orange-50 dark:bg-orange-950/20 p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-medium text-orange-800 dark:text-orange-300">
            {data.total} uang muka belum di-settle — Total Outstanding: {fmt(data.total_outstanding)}
          </p>
          <p className="text-sm text-orange-700 dark:text-orange-400">
            Akun GL: <span className="font-mono">1-1610 Uang Muka Karyawan</span>
          </p>
        </div>
      </div>
      <div className="rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 border-b">
            <tr>
              <th className="text-left p-3 font-medium">Trip / Karyawan</th>
              <th className="text-left p-3 font-medium">Destinasi</th>
              <th className="text-center p-3 font-medium">Tgl Kembali</th>
              <th className="text-right p-3 font-medium">Advance</th>
              <th className="text-center p-3 font-medium">Hari Belum Settle</th>
              <th className="text-center p-3 font-medium">Status Settlement</th>
            </tr>
          </thead>
          <tbody>
            {(data.items || []).map(item => {
              const daysOverdue = item.days_since_return;
              const isOverdue = daysOverdue !== null && daysOverdue > 7;
              return (
                <tr key={item.id} className={`border-t ${ isOverdue ? 'bg-red-50/50 dark:bg-red-950/10' : '' }`}>
                  <td className="p-3">
                    <div className="font-mono text-xs text-muted-foreground">{item.trip_number}</div>
                    <div className="font-medium">{item.employee_name}</div>
                    <div className="text-xs text-muted-foreground">{item.employee_dept}</div>
                  </td>
                  <td className="p-3">{item.destination}</td>
                  <td className="p-3 text-center text-xs">{fmtDate(item.end_date)}</td>
                  <td className="p-3 text-right font-bold">{fmt(item.cash_advance_paid)}</td>
                  <td className="p-3 text-center">
                    {daysOverdue !== null ? (
                      <span className={`font-bold ${ isOverdue ? 'text-red-600' : 'text-orange-500' }`}>
                        {daysOverdue} hari
                      </span>
                    ) : '—'}
                  </td>
                  <td className="p-3 text-center">
                    {item.pending_settlement ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800">
                        {item.pending_settlement.settlement_number}: {item.pending_settlement.status}
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800">
                        Belum ada settlement
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="border-t bg-muted/50">
            <tr>
              <td colSpan={3} className="p-3 text-sm font-bold">Total Outstanding (1-1610)</td>
              <td className="p-3 text-right font-bold text-orange-700">{fmt(data.total_outstanding)}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

// ── Main Module ────────────────────────────────────────────────────────────────

export default function EmployeeTravelSettlementModule({ token, user }) {
  const [settlements, setSettlements] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState('my');   // my | queue | outstanding
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTravel, setSelectedTravel] = useState(null); // travel request for new settlement
  const [selected, setSelected] = useState(null);              // settlement detail
  const [myTrips, setMyTrips] = useState([]);  // eligible trips to settle
  
  // Phase 4: Bulk selection & Export
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [exportFromDate, setExportFromDate] = useState('');
  const [exportToDate, setExportToDate] = useState('');
  
  const role = user?.role || '';
  const isFinance = ['superadmin','admin','owner','finance'].includes(role.toLowerCase());
  const isApprover = ['superadmin','admin','owner','hr','manager','finance'].includes(role.toLowerCase());
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter !== 'all') params.set('status', filter);
      if (search) params.set('search', search);
      if (activeTab === 'my') params.set('employee_id', user?.id || '');

      const [stlR, sumR] = await Promise.all([
        fetch(`${API}/api/hr/expenses/settlements?${params}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/hr/expenses/settlement-summary`, { headers }).then(r => r.json()),
      ]);
      setSettlements(Array.isArray(stlR.items) ? stlR.items : []);
      setSummary(sumR);

      // Fetch eligible trips (advance_paid / on_trip) for creating new settlement
      const trR = await fetch(
        `${API}/api/hr/expenses/travel?status=advance_paid,on_trip,approved&employee_id=${user?.id || ''}`,
        { headers }
      ).then(r => r.json());
      setMyTrips(Array.isArray(trR.items) ? trR.items : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token, filter, search, activeTab, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(); }, [fetchData]);

  // Phase 4: Export function — RC-23: toast sukses hanya bila backend OK (dulu fire-and-forget)
  const handleExport = async () => {
    const params = new URLSearchParams();
    if (filter !== 'all') params.set('status', filter);
    if (exportFromDate) params.set('from_date', exportFromDate);
    if (exportToDate) params.set('to_date', exportToDate);
    try {
      const res = await fetch(`${API}/api/hr/expenses/settlements/export?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        toast.error(`Export gagal (HTTP ${res.status}). Coba lagi atau hubungi admin.`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'settlements-export.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Export berhasil. File terdownload.');
    } catch (e) {
      toast.error('Export gagal: ' + (e?.message || 'network error'));
    }
  };

  // Phase 4: Bulk approve
  const handleBulkApprove = async () => {
    if (!selectedIds.length) {
      toast.error('Pilih minimal 1 settlement untuk di-approve');
      return;
    }
    
    if (!window.confirm(`Approve ${selectedIds.length} settlement?`)) return;
    
    setBulkLoading(true);
    try {
      const res = await fetch(`${API}/api/hr/expenses/settlements/bulk-approve`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          settlement_ids: selectedIds,
          approval_note: 'Bulk approved from UI'
        })
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(`${data.success_count} settlement berhasil di-approve`);
        if (data.failed_count > 0) {
          toast.warning(`${data.failed_count} settlement gagal. Cek console untuk detail.`);
          console.warn('Failed items:', data.results.failed);
        }
        setSelectedIds([]);
        fetchData();
      } else {
        toast.error(data.detail || 'Gagal bulk approve');
      }
    } catch (err) {
      console.error('Bulk approve error:', err);
      toast.error('Terjadi kesalahan saat bulk approve');
    } finally {
      setBulkLoading(false);
    }
  };

  // Phase 4: Bulk post GL (Finance only)
  const handleBulkPost = async () => {
    if (!selectedIds.length) {
      toast.error('Pilih minimal 1 settlement untuk di-post GL');
      return;
    }
    
    if (!window.confirm(`Post GL untuk ${selectedIds.length} settlement? Ini akan membuat Journal Entry.`)) return;
    
    setBulkLoading(true);
    try {
      const res = await fetch(`${API}/api/hr/expenses/settlements/bulk-post`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ settlement_ids: selectedIds })
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(`${data.success_count} settlement berhasil di-post GL`);
        if (data.failed_count > 0) {
          toast.warning(`${data.failed_count} settlement gagal. Cek console untuk detail.`);
          console.warn('Failed items:', data.results.failed);
        }
        setSelectedIds([]);
        fetchData();
      } else {
        toast.error(data.detail || 'Gagal bulk post GL');
      }
    } catch (err) {
      console.error('Bulk post error:', err);
      toast.error('Terjadi kesalahan saat bulk post');
    } finally {
      setBulkLoading(false);
    }
  };

  // Toggle selection
  const toggleSelect = (id) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    const eligibleIds = filteredItems.map(s => s.id);
    setSelectedIds(prev => 
      prev.length === eligibleIds.length ? [] : eligibleIds
    );
  };

  const tabs = [
    { id: 'my',          label: 'Settlement Saya' },
    ...(isApprover ? [{ id: 'queue', label: `Queue (${summary?.pending_post || 0})` }] : []),
    ...(isFinance  ? [{ id: 'outstanding', label: `Outstanding Advance (${
      summary?.outstanding_advances_count || 0
    })` }] : []),
  ];

  const filteredItems = settlements.filter(s => {
    if (filter !== 'all' && s.status !== filter) return false;
    if (search && !s.settlement_number?.toLowerCase().includes(search.toLowerCase()) && 
        !s.trip_number?.toLowerCase().includes(search.toLowerCase()) &&
        !s.destination?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const { page, setPage, totalPages, total, paged } = useClientPagination(settlements, 10);
  return (
    <div className="space-y-5" data-testid="travel-settlement-page">
      <PageHeader
        icon={FileText}
        eyebrow="SDM / Finance · Employee Expense Management"
        title="Settlement Perjalanan Dinas"
        subtitle="Laporan biaya aktual, rekonsiliasi uang muka, dan posting GL jurnal perjalanan dinas."
        actions={
          <div className="flex gap-2 items-center">
            {/* Phase 4: Export with date range */}
            <div className="flex gap-1 items-center border rounded-lg px-2 py-1">
              <Input
                type="date"
                placeholder="Dari"
                value={exportFromDate}
                onChange={(e) => setExportFromDate(e.target.value)}
                className="h-7 w-32 text-xs"
              />
              <span className="text-xs text-muted-foreground">-</span>
              <Input
                type="date"
                placeholder="Sampai"
                value={exportToDate}
                onChange={(e) => setExportToDate(e.target.value)}
                className="h-7 w-32 text-xs"
              />
              <Button variant="ghost" size="sm" onClick={handleExport} className="h-7">
                <Download className="w-3.5 h-3.5 mr-1" />
                Export CSV
              </Button>
            </div>
            
            <Button variant="ghost" onClick={fetchData} className="h-9 border">
              <RefreshCw className="w-3.5 h-3.5" />
            </Button>
            {myTrips.length > 0 && (
              <Button onClick={() => setShowCreate(true)} className="h-9" data-testid="btn-new-settlement">
                <Plus className="w-3.5 h-3.5 mr-1.5" />Settlement Baru
              </Button>
            )}
          </div>
        }
      />

      {/* RC-IA-2a — klarifikasi pintu bersama HR/Keuangan */}
      <div className="px-3 py-2 rounded-lg bg-primary/5 border border-primary/15 text-xs text-muted-foreground">
        <strong className="text-foreground">Inbox bersama SDM &amp; Keuangan</strong> — layar yang sama dibuka dari dua portal. SDM menyetujui perjalanan dinas, Keuangan memproses settlement &amp; posting GL.
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="Menunggu Approval" value={summary.settlement_counts?.submitted || 0} accent="warning" />
          <StatTile label="Siap Di-Post" value={summary.settlement_counts?.approved || 0} accent="info" />
          <StatTile label="Sudah Di-Post" value={summary.settlement_counts?.posted || 0} accent="success" />
          <StatTile label="Outstanding Advance" value={summary.outstanding_advances_count || 0}
            accent={(summary.outstanding_advances_count || 0) > 0 ? 'danger' : 'default'} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex rounded-lg border overflow-hidden w-fit">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === t.id ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'outstanding' ? (
        <OutstandingAdvancePanel token={token} />
      ) : (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className="h-8 w-44 text-sm">
                <Filter className="w-3.5 h-3.5 mr-1" /><SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="submitted">Menunggu Approval</SelectItem>
                <SelectItem value="approved">Disetujui</SelectItem>
                <SelectItem value="posted">Sudah Post</SelectItem>
                <SelectItem value="rejected">Ditolak</SelectItem>
              </SelectContent>
            </Select>
            <Input placeholder="Cari nomor / destinasi..." value={search} onChange={e => setSearch(e.target.value)} className="h-8 text-sm w-52" />
          </div>

          {/* Phase 4: Bulk Action Bar */}
          {selectedIds.length > 0 && (
            <div className="rounded-lg border bg-primary/5 p-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">
                  {selectedIds.length} settlement dipilih
                </span>
                <Button variant="outline" size="sm" onClick={() => setSelectedIds([])}>
                  Clear Selection
                </Button>
              </div>
              <div className="flex items-center gap-2">
                {isApprover && (
                  <Button 
                    size="sm" 
                    onClick={handleBulkApprove} 
                    disabled={bulkLoading}
                    data-testid="bulk-approve-btn"
                  >
                    <CheckCircle className="w-3.5 h-3.5 mr-1" />
                    Approve Selected
                  </Button>
                )}
                {isFinance && (
                  <Button 
                    size="sm" 
                    onClick={handleBulkPost} 
                    disabled={bulkLoading}
                    className="bg-purple-600 hover:bg-purple-700"
                    data-testid="bulk-post-btn"
                  >
                    <Banknote className="w-3.5 h-3.5 mr-1" />
                    Post GL Selected
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* List */}
          <div className="rounded-xl border overflow-hidden">
            {loading ? (
              <div className="p-12 text-center text-muted-foreground">
                <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
                Memuat settlement...
              </div>
            ) : settlements.length === 0 ? (
              <div className="p-12 text-center text-muted-foreground">
                <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">Belum ada settlement</p>
                {myTrips.length > 0 && (
                  <p className="text-sm mt-1">Klik "Settlement Baru" untuk memulai rekonsiliasi perjalanan dinas.</p>
                )}
              </div>
            ) : (
              <>
              <table className="w-full text-sm">
                <thead className="bg-muted/50 border-b">
                  <tr>
                    {(isApprover || isFinance) && (
                      <th className="text-left p-3 w-12">
                        <Checkbox
                          checked={selectedIds.length === filteredItems.length && filteredItems.length > 0}
                          onCheckedChange={toggleSelectAll}
                          data-testid="select-all-checkbox"
                        />
                      </th>
                    )}
                    <th className="text-left p-3 font-medium">Nomor / Trip</th>
                    <th className="text-left p-3 font-medium">Karyawan</th>
                    <th className="text-left p-3 font-medium">Destinasi</th>
                    <th className="text-right p-3 font-medium">Aktual</th>
                    <th className="text-right p-3 font-medium">Advance</th>
                    <th className="text-center p-3 font-medium">Selisih</th>
                    <th className="text-center p-3 font-medium">Status</th>
                    <th className="text-center p-3 font-medium">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map(s => {
                    const diff = s.difference || 0;
                    const stlType = s.settlement_type || 'exact';
                    return (
                      <tr key={s.id} className="border-t hover:bg-muted/30 transition-colors">
                        {(isApprover || isFinance) && (
                          <td className="p-3">
                            <Checkbox
                              checked={selectedIds.includes(s.id)}
                              onCheckedChange={() => toggleSelect(s.id)}
                              data-testid={`select-checkbox-${s.id}`}
                            />
                          </td>
                        )}
                        <td className="p-3">
                          <div className="font-mono text-xs text-muted-foreground">{s.settlement_number}</div>
                          <div className="text-xs text-muted-foreground">{s.trip_number}</div>
                        </td>
                        <td className="p-3">
                          <div className="font-medium">{s.employee_name}</div>
                          <div className="text-xs text-muted-foreground">{s.employee_dept}</div>
                        </td>
                        <td className="p-3">
                          <div>{s.destination}</div>
                          <div className="text-xs text-muted-foreground">{fmtDate(s.start_date)} – {fmtDate(s.end_date)}</div>
                        </td>
                        <td className="p-3 text-right font-bold">{fmt(s.total_actual)}</td>
                        <td className="p-3 text-right">{fmt(s.advance_received)}</td>
                        <td className="p-3 text-center">
                          <span className={`text-xs font-bold ${
                            stlType==='return' ? 'text-green-600' :
                            stlType==='additional' ? 'text-red-600' : 'text-muted-foreground/80'
                          }`}>
                            {stlType === 'return' ? '↓' : stlType === 'additional' ? '↑' : '='} {fmt(Math.abs(diff))}
                          </span>
                        </td>
                        <td className="p-3 text-center"><StatusBadge status={s.status} /></td>
                        <td className="p-3 text-center">
                          <Button size="sm" variant="ghost" onClick={() => setSelected(s)} className="h-7">
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </>
            )}
          </div>
        </>
      )}

      {/* Create: pilih trip dulu */}
      <Dialog open={showCreate && !selectedTravel} onOpenChange={v => { if (!v) setShowCreate(false); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Pilih Perjalanan Dinas untuk Di-Settle</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {myTrips.length === 0 ? (
              <p className="text-sm text-muted-foreground">Tidak ada perjalanan dinas yang eligible untuk settlement.</p>
            ) : myTrips.map(tr => (
              <div key={tr.id}
                className="rounded-lg border p-3 hover:bg-muted/50 cursor-pointer transition-colors"
                onClick={() => setSelectedTravel(tr)}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-mono text-xs text-muted-foreground">{tr.trip_number}</div>
                    <div className="font-medium">{tr.destination}</div>
                    <div className="text-xs text-muted-foreground">{fmtDate(tr.start_date)} – {fmtDate(tr.end_date)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-muted-foreground">Uang Muka</div>
                    <div className="font-bold text-blue-700">{fmt(tr.cash_advance_paid || tr.cash_advance_approved || 0)}</div>
                    <ChevronRight className="w-4 h-4 ml-auto text-muted-foreground" />
                  </div>
                </div>
              </div>
            ))}
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setShowCreate(false)}>Batal</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Settlement Form */}
      <Dialog open={!!selectedTravel} onOpenChange={v => { if (!v) { setSelectedTravel(null); setShowCreate(false); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-purple-600" />Settlement Perjalanan Dinas
          </DialogTitle></DialogHeader>
          {selectedTravel && (
            <SettlementForm
              token={token}
              travel={selectedTravel}
              onClose={() => { setSelectedTravel(null); setShowCreate(false); }}
              onSaved={(d) => { setSelectedTravel(null); setShowCreate(false); fetchData(); setSelected(d); }}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Detail / Action Dialog */}
      <Dialog open={!!selected} onOpenChange={v => !v && setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-purple-600" />
            {selected?.settlement_number} — {selected?.destination}
          </DialogTitle></DialogHeader>
          {selected && (
            <SettlementDetail
              stl={selected}
              token={token}
              role={role}
              onClose={() => setSelected(null)}
              onRefresh={fetchData}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
