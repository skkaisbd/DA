/**
 * WMS CMT Vendor Hub — Alur CMT Vendor / Sub-contract (Maklon)
 * ============================================================
 * Hub tunggal (SSOT) untuk seluruh siklus kerja CMT vendor / sub-contract:
 *
 *   A. KIRIM KE VENDOR (Dispatch)  — backend routes/wms_cmt_dispatches.py
 *      draft -> dispatched (auto Surat Jalan SJ-CMT) -> partially_returned / fully_returned
 *      + cancel. Collection: wh_cmt_dispatches, wh_delivery_notes.
 *
 *   B. TERIMA HASIL JADI (Receipt + QC + posting FG) — backend routes/dewi_cmt_packing.py
 *      Draft -> Submitted -> Approved (posting FG ke rahaza_material_stock) / Rejected.
 *      Collections: cmt_receipts, cmt_receipt_lines, rahaza_material_stock, rahaza_fg_movements.
 *
 * Catatan arsitektur: prod-cmt-packing di-redirect ke modul ini (O1.2 single-SSOT),
 * jadi kedua sisi alur disajikan di sini sebagai dua seksi.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Truck, Plus, RefreshCw, Eye, RotateCcw, Loader2, Search, PackageCheck,
  Package, X, Save, ArrowRight, Send, CheckCircle2, XCircle, Trash2, FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { EmptyState } from './EmptyState';
import OnwardCTA from './OnwardCTA';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL;

// ── status → warna badge ──────────────────────────────────────────────────
const DISPATCH_STATUS = {
  draft:             { label: 'Draft',            cls: 'bg-muted text-muted-foreground border-border' },
  dispatched:        { label: 'Terkirim',         cls: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30' },
  partially_returned:{ label: 'Retur Sebagian',   cls: 'bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30' },
  fully_returned:    { label: 'Retur Penuh',      cls: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30' },
  cancelled:         { label: 'Dibatalkan',       cls: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30' },
};
const RECEIPT_STATUS = {
  Draft:     { label: 'Draft',     cls: 'bg-muted text-muted-foreground border-border' },
  Submitted: { label: 'Diajukan',  cls: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30' },
  Approved:  { label: 'Disetujui', cls: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30' },
  Rejected:  { label: 'Ditolak',   cls: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30' },
};

const fmt = (n) => new Intl.NumberFormat('id-ID').format(Number(n ?? 0));
const fmtDate = (iso) => {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return String(iso).slice(0, 10) || '-'; }
};

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

function StatusBadge({ map, status, testId }) {
  const s = map[status] || { label: status || '-', cls: 'bg-secondary text-muted-foreground border-border' };
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-medium border ${s.cls}`}
      data-testid={testId}
    >
      {s.label}
    </span>
  );
}

// ════════════════════════════════════════════════════════════════════════
// SECTION A — DISPATCH (Kirim ke Vendor)
// ════════════════════════════════════════════════════════════════════════
function DispatchSection({ token, onNavigate }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [header, setHeader] = useState({ cmt_name: '', cmt_address: '', wo_number: '', notes: '' });
  const [lines, setLines] = useState([{ material_code: '', material_name: '', qty: '', unit: 'meter', unit_cost: '', roll_nos: '', remarks: '' }]);

  const [executeFor, setExecuteFor] = useState(null); // dispatch obj
  const [shipInfo, setShipInfo] = useState({ shipper_name: '', vehicle_no: '' });
  const [returnFor, setReturnFor] = useState(null);    // dispatch obj
  const [returnForm, setReturnForm] = useState({ material_code: '', qty_returned: '', unit: 'meter' });
  const [viewFor, setViewFor] = useState(null);        // dispatch obj (detail)

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const d = await api('GET', `/api/wms/cmt-dispatches?${params.toString()}`, token);
      setItems(d.items || []);
    } catch (e) {
      toast.error(`Gagal memuat dispatch: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const resetCreate = () => {
    setHeader({ cmt_name: '', cmt_address: '', wo_number: '', notes: '' });
    setLines([{ material_code: '', material_name: '', qty: '', unit: 'meter', unit_cost: '', roll_nos: '', remarks: '' }]);
  };

  const addLine = () => setLines((p) => [...p, { material_code: '', material_name: '', qty: '', unit: 'meter', unit_cost: '', roll_nos: '', remarks: '' }]);
  const removeLine = (i) => setLines((p) => p.filter((_, idx) => idx !== i));
  const patchLine = (i, key, val) => setLines((p) => p.map((ln, idx) => (idx === i ? { ...ln, [key]: val } : ln)));

  const submitCreate = async () => {
    if (!header.cmt_name.trim()) { toast.error('Nama vendor CMT wajib diisi'); return; }
    const validLines = lines.filter((l) => (l.material_name.trim() || l.material_code.trim()) && Number(l.qty) > 0);
    if (validLines.length === 0) { toast.error('Minimal 1 komponen dengan qty > 0'); return; }
    setSaving(true);
    try {
      const payload = {
        cmt_name: header.cmt_name.trim(),
        cmt_address: header.cmt_address.trim(),
        wo_number: header.wo_number.trim(),
        notes: header.notes.trim(),
        lines: validLines.map((l) => ({
          material_code: l.material_code.trim(),
          material_name: l.material_name.trim() || l.material_code.trim(),
          roll_nos: l.roll_nos ? l.roll_nos.split(',').map((s) => s.trim()).filter(Boolean) : [],
          qty: Number(l.qty),
          unit: l.unit || 'meter',
          unit_cost: Number(l.unit_cost) || 0,
          remarks: l.remarks.trim(),
        })),
      };
      const res = await api('POST', '/api/wms/cmt-dispatches', token, payload);
      toast.success(`Dispatch ${res.dispatch?.dispatch_no || ''} dibuat (draft)`);
      setCreateOpen(false);
      resetCreate();
      load();
    } catch (e) {
      toast.error(`Gagal membuat dispatch: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const doExecute = async () => {
    if (!executeFor) return;
    setSaving(true);
    try {
      const res = await api('POST', `/api/wms/cmt-dispatches/${executeFor.id}/dispatch`, token, {
        shipper_name: shipInfo.shipper_name.trim(),
        vehicle_no: shipInfo.vehicle_no.trim(),
      });
      toast.success(`Terkirim ke vendor — Surat Jalan ${res.sj_number} terbit`);
      setExecuteFor(null);
      setShipInfo({ shipper_name: '', vehicle_no: '' });
      load();
    } catch (e) {
      toast.error(`Gagal kirim: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const doReturn = async () => {
    if (!returnFor) return;
    if (!returnForm.material_code) { toast.error('Pilih komponen yang diretur'); return; }
    if (!(Number(returnForm.qty_returned) > 0)) { toast.error('Qty retur harus > 0'); return; }
    setSaving(true);
    try {
      const res = await api('POST', `/api/wms/cmt-dispatches/${returnFor.id}/return-line`, token, {
        material_code: returnForm.material_code,
        qty_returned: Number(returnForm.qty_returned),
        unit: returnForm.unit || 'meter',
      });
      toast.success(`Retur dicatat — status: ${DISPATCH_STATUS[res.dispatch?.status]?.label || res.dispatch?.status}`);
      setReturnFor(null);
      setReturnForm({ material_code: '', qty_returned: '', unit: 'meter' });
      load();
    } catch (e) {
      toast.error(`Gagal catat retur: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const doCancel = async (d) => {
    if (!window.confirm(`Batalkan dispatch ${d.dispatch_no}?`)) return;
    try {
      await api('POST', `/api/wms/cmt-dispatches/${d.id}/cancel`, token, { reason: 'Dibatalkan dari UI' });
      toast.success('Dispatch dibatalkan');
      load();
    } catch (e) {
      toast.error(`Gagal batalkan: ${e.message}`);
    }
  };

  const openView = async (d) => {
    try {
      const full = await api('GET', `/api/wms/cmt-dispatches/${d.id}`, token);
      setViewFor(full);
    } catch (e) {
      toast.error(`Gagal muat detail: ${e.message}`);
    }
  };

  const openReturn = (d) => {
    const first = (d.lines || []).find((l) => (l.qty_outstanding ?? l.qty) > 0) || (d.lines || [])[0];
    setReturnForm({ material_code: first?.material_code || '', qty_returned: '', unit: first?.unit || 'meter' });
    setReturnFor(d);
  };

  return (
    <div className="flex flex-col gap-4" data-testid="dispatch-section">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[220px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Cari no. dispatch / vendor / WO…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            data-testid="search-dispatch-input"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[190px]" data-testid="dispatch-status-filter">
            <SelectValue placeholder="Semua status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" data-testid="dispatch-filter-all">Semua status</SelectItem>
            <SelectItem value="draft" data-testid="dispatch-filter-draft">Draft</SelectItem>
            <SelectItem value="dispatched" data-testid="dispatch-filter-dispatched">Terkirim</SelectItem>
            <SelectItem value="partially_returned" data-testid="dispatch-filter-partial">Retur Sebagian</SelectItem>
            <SelectItem value="fully_returned" data-testid="dispatch-filter-returned">Retur Penuh</SelectItem>
            <SelectItem value="cancelled" data-testid="dispatch-filter-cancelled">Dibatalkan</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={load} disabled={loading} data-testid="refresh-dispatch-btn">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
        <Button onClick={() => { resetCreate(); setCreateOpen(true); }} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="create-dispatch-btn">
          <Plus className="w-4 h-4 mr-2" /> Dispatch Baru
        </Button>
      </div>

      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'wms-delivery-notes', label: 'Surat Jalan (SJ-CMT)', icon: Truck, primary: true, hint: 'Dispatch otomatis menerbitkan Surat Jalan' },
          { module: 'wms-stock-hub', label: 'Lihat Stok Terkini', hint: 'Material keluar ke vendor → cek posisi stok' },
        ]}
      />

      {/* list */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="loading-dispatches">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border border-border rounded-xl p-4 space-y-3">
              <div className="flex justify-between"><Skeleton className="h-5 w-32" /><Skeleton className="h-5 w-16" /></div>
              <Skeleton className="h-4 w-48" /><Skeleton className="h-4 w-36" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="Belum ada dispatch CMT"
          description="Kirim komponen ke vendor CMT. Klik 'Dispatch Baru' untuk memulai."
          action={{ label: 'Dispatch Baru', onClick: () => { resetCreate(); setCreateOpen(true); } }}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="dispatch-list">
          {items.map((d) => (
            <div
              key={d.id}
              className="bg-foreground/5 border border-border rounded-xl p-4 hover:bg-foreground/10 transition-colors"
              data-testid={`dispatch-card-${d.dispatch_no}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Truck className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                    <h3 className="font-semibold text-foreground truncate">{d.dispatch_no}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{d.cmt_name}</p>
                  {d.wo_number && <p className="text-xs text-muted-foreground/70">WO: {d.wo_number}</p>}
                </div>
                <StatusBadge map={DISPATCH_STATUS} status={d.status} testId={`dispatch-status-${d.dispatch_no}`} />
              </div>

              <div className="space-y-1.5 text-sm mb-3">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Komponen:</span>
                  <span className="text-foreground font-mono">{(d.lines || []).length} item</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total Qty:</span>
                  <span className="text-foreground font-mono">{fmt((d.lines || []).reduce((s, l) => s + (l.qty || 0), 0))}</span>
                </div>
                {d.sj_number && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Surat Jalan:</span>
                    <span className="text-blue-600 dark:text-blue-300 font-mono">{d.sj_number}</span>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-2 pt-3 border-t border-border">
                <Button size="sm" variant="outline" onClick={() => openView(d)} data-testid={`dispatch-view-btn-${d.dispatch_no}`}>
                  <Eye className="w-3.5 h-3.5 mr-1" /> Detail
                </Button>
                {d.status === 'draft' && (
                  <>
                    <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white" onClick={() => { setShipInfo({ shipper_name: '', vehicle_no: '' }); setExecuteFor(d); }} data-testid={`dispatch-execute-btn-${d.dispatch_no}`}>
                      <ArrowRight className="w-3.5 h-3.5 mr-1" /> Kirim
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => doCancel(d)} data-testid={`dispatch-cancel-btn-${d.dispatch_no}`}>
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Batal
                    </Button>
                  </>
                )}
                {(d.status === 'dispatched' || d.status === 'partially_returned') && (
                  <Button size="sm" variant="outline" onClick={() => openReturn(d)} data-testid={`dispatch-return-btn-${d.dispatch_no}`}>
                    <RotateCcw className="w-3.5 h-3.5 mr-1" /> Catat Retur
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* CREATE DIALOG */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-auto" data-testid="create-dispatch-dialog">
          <DialogHeader>
            <DialogTitle>Buat Dispatch CMT Baru</DialogTitle>
            <DialogDescription>Kirim komponen (kain/aksesoris) ke vendor CMT. Status awal: draft.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 sm:col-span-1">
              <Label>Nama Vendor CMT *</Label>
              <Input value={header.cmt_name} onChange={(e) => setHeader({ ...header, cmt_name: e.target.value })} placeholder="mis. CV Jahit Makmur" data-testid="input-cmt-name" />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <Label>No. Work Order</Label>
              <Input value={header.wo_number} onChange={(e) => setHeader({ ...header, wo_number: e.target.value })} placeholder="WO-2026-001" data-testid="input-wo-number" />
            </div>
            <div className="col-span-2">
              <Label>Alamat Vendor</Label>
              <Input value={header.cmt_address} onChange={(e) => setHeader({ ...header, cmt_address: e.target.value })} placeholder="Alamat pengiriman" data-testid="input-cmt-address" />
            </div>
            <div className="col-span-2">
              <Label>Catatan</Label>
              <Textarea value={header.notes} onChange={(e) => setHeader({ ...header, notes: e.target.value })} placeholder="Instruksi khusus…" data-testid="input-dispatch-notes" />
            </div>
          </div>

          <div className="border border-border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-foreground/5 border-b border-border">
              <span className="text-sm font-semibold flex items-center gap-2"><Package className="w-4 h-4" /> Komponen Dikirim</span>
              <Button size="sm" variant="outline" onClick={addLine} data-testid="add-line-btn"><Plus className="w-3.5 h-3.5 mr-1" /> Tambah Baris</Button>
            </div>
            <div className="p-3 space-y-3">
              {lines.map((ln, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`line-row-${i}`}>
                  <div className="col-span-3">
                    <Label className="text-xs">Kode</Label>
                    <Input value={ln.material_code} onChange={(e) => patchLine(i, 'material_code', e.target.value)} placeholder="KAIN-01" data-testid={`line-material-code-${i}`} />
                  </div>
                  <div className="col-span-4">
                    <Label className="text-xs">Nama Material</Label>
                    <Input value={ln.material_name} onChange={(e) => patchLine(i, 'material_name', e.target.value)} placeholder="Kain Katun" data-testid={`line-material-name-${i}`} />
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs">Qty</Label>
                    <Input type="number" min="0" step="0.01" value={ln.qty} onChange={(e) => patchLine(i, 'qty', e.target.value)} placeholder="0" data-testid={`line-qty-${i}`} />
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs">Unit</Label>
                    <Input value={ln.unit} onChange={(e) => patchLine(i, 'unit', e.target.value)} placeholder="meter" data-testid={`line-unit-${i}`} />
                  </div>
                  <div className="col-span-1 flex justify-center pb-1">
                    <Button size="icon" variant="ghost" className="text-red-600 hover:text-red-700 h-8 w-8" onClick={() => removeLine(i)} disabled={lines.length === 1} data-testid={`line-remove-${i}`}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} data-testid="cancel-create-dispatch">Batal</Button>
            <Button onClick={submitCreate} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="submit-create-dispatch">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} Simpan Draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* EXECUTE (dispatch) DIALOG */}
      <Dialog open={!!executeFor} onOpenChange={(o) => !o && setExecuteFor(null)}>
        <DialogContent className="max-w-md" data-testid="execute-dispatch-dialog">
          <DialogHeader>
            <DialogTitle>Kirim ke Vendor</DialogTitle>
            <DialogDescription>Surat Jalan (SJ-CMT) akan otomatis diterbitkan.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>Nama Pengirim / Kurir</Label>
              <Input value={shipInfo.shipper_name} onChange={(e) => setShipInfo({ ...shipInfo, shipper_name: e.target.value })} placeholder="mis. Budi" data-testid="input-shipper-name" />
            </div>
            <div>
              <Label>No. Kendaraan</Label>
              <Input value={shipInfo.vehicle_no} onChange={(e) => setShipInfo({ ...shipInfo, vehicle_no: e.target.value })} placeholder="B 1234 XY" data-testid="input-vehicle-no" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExecuteFor(null)} data-testid="cancel-execute-dispatch">Batal</Button>
            <Button onClick={doExecute} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="confirm-execute-dispatch">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />} Kirim & Terbitkan SJ
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* RETURN DIALOG */}
      <Dialog open={!!returnFor} onOpenChange={(o) => !o && setReturnFor(null)}>
        <DialogContent className="max-w-md" data-testid="return-dispatch-dialog">
          <DialogHeader>
            <DialogTitle>Catat Retur Material</DialogTitle>
            <DialogDescription>Rekam material yang dikembalikan vendor.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>Komponen</Label>
              <Select value={returnForm.material_code} onValueChange={(v) => setReturnForm({ ...returnForm, material_code: v })}>
                <SelectTrigger data-testid="select-return-material">
                  <SelectValue placeholder="Pilih komponen" />
                </SelectTrigger>
                <SelectContent>
                  {(returnFor?.lines || []).map((l, i) => (
                    <SelectItem key={i} value={l.material_code} data-testid={`return-material-opt-${i}`}>
                      {l.material_name || l.material_code} (sisa {fmt(l.qty_outstanding ?? l.qty)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Qty Diretur</Label>
              <Input type="number" min="0" step="0.01" value={returnForm.qty_returned} onChange={(e) => setReturnForm({ ...returnForm, qty_returned: e.target.value })} placeholder="0" data-testid="input-return-qty" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReturnFor(null)} data-testid="cancel-return">Batal</Button>
            <Button onClick={doReturn} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="confirm-return">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RotateCcw className="w-4 h-4 mr-2" />} Catat Retur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* VIEW DETAIL DIALOG */}
      <Dialog open={!!viewFor} onOpenChange={(o) => !o && setViewFor(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-auto" data-testid="view-dispatch-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Truck className="w-5 h-5 text-blue-600 dark:text-blue-400" /> {viewFor?.dispatch_no}</DialogTitle>
            <DialogDescription>Detail dispatch & status retur per komponen.</DialogDescription>
          </DialogHeader>
          {viewFor && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div><span className="text-muted-foreground">Vendor CMT:</span><p className="font-medium">{viewFor.cmt_name}</p></div>
                <div><span className="text-muted-foreground">Status:</span><p className="font-medium">{DISPATCH_STATUS[viewFor.status]?.label || viewFor.status}</p></div>
                <div><span className="text-muted-foreground">No. WO:</span><p className="font-medium">{viewFor.wo_number || '-'}</p></div>
                <div><span className="text-muted-foreground">Surat Jalan:</span><p className="font-medium">{viewFor.sj_number || '-'}</p></div>
                <div><span className="text-muted-foreground">Dikirim:</span><p className="font-medium">{fmtDate(viewFor.dispatched_at)}</p></div>
                <div><span className="text-muted-foreground">Alamat:</span><p className="font-medium">{viewFor.cmt_address || '-'}</p></div>
              </div>
              <div className="border border-border rounded-lg overflow-hidden">
                <table className="w-full text-xs" data-testid="view-dispatch-lines">
                  <thead className="bg-foreground/5 text-muted-foreground">
                    <tr>
                      <th className="text-left px-3 py-2">Material</th>
                      <th className="text-right px-3 py-2">Qty</th>
                      <th className="text-right px-3 py-2">Retur</th>
                      <th className="text-right px-3 py-2">Sisa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(viewFor.lines || []).map((l, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-3 py-2">{l.material_name || l.material_code}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(l.qty)} {l.unit}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(l.qty_returned)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(l.qty_outstanding ?? l.qty)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {viewFor.notes && <div><span className="text-muted-foreground">Catatan:</span><p className="mt-1">{viewFor.notes}</p></div>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// SECTION B — RECEIPT + QC (Terima Hasil Jadi)
// ════════════════════════════════════════════════════════════════════════
function ReceiptSection({ token, onNavigate }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ cmt_name: '', wo_number: '', delivery_note: '', notes: '' });
  // SESI #27 — nomor penerimaan CMT mengikuti kebijakan Otomatis/Manual milik owner
  // (jenis dokumen ini ditegakkan sejak sesi #18 tetapi formnya belum punya kolomnya,
  // sehingga mode MANUAL berarti penerimaan TIDAK BISA dibuat).
  const numPolicy = useDocNumberPolicy('cmt_receipts.receipt_code', token);
  const [receiptCode, setReceiptCode] = useState('');

  const [detail, setDetail] = useState(null); // full receipt {..., lines}
  const [lineForm, setLineForm] = useState({ sku_code: '', product_name: '', color: '', size: '', qty_expected: '' });
  const [showAddLine, setShowAddLine] = useState(false);

  const [rejectFor, setRejectFor] = useState(null);
  const [rejectReason, setRejectReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (search) params.set('cmt_name', search);
      const [list, sum] = await Promise.all([
        api('GET', `/api/prod/cmt-receipts?${params.toString()}`, token),
        api('GET', '/api/prod/cmt-receipts/summary', token).catch(() => null),
      ]);
      setItems(Array.isArray(list) ? list : []);
      setSummary(sum);
    } catch (e) {
      toast.error(`Gagal memuat penerimaan: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter, search]);

  useEffect(() => { load(); }, [load]);

  const submitCreate = async () => {
    if (!form.cmt_name.trim()) { toast.error('Nama vendor CMT wajib diisi'); return; }
    setSaving(true);
    try {
      const res = await api('POST', '/api/prod/cmt-receipts', token, {
        cmt_name: form.cmt_name.trim(),
        wo_number: form.wo_number.trim(),
        delivery_note: form.delivery_note.trim(),
        notes: form.notes.trim(),
        ...docNumberPayload(numPolicy, 'receipt_code', receiptCode),
      });
      toast.success(`Penerimaan ${res.receipt_code} dibuat (Draft)`);
      setCreateOpen(false);
      setForm({ cmt_name: '', wo_number: '', delivery_note: '', notes: '' });
      load();
      openDetail(res);
    } catch (e) {
      toast.error(`Gagal membuat penerimaan: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (r) => {
    try {
      const full = await api('GET', `/api/prod/cmt-receipts/${r.id}`, token);
      setDetail(full);
    } catch (e) {
      toast.error(`Gagal muat detail: ${e.message}`);
    }
  };
  const reloadDetail = async () => {
    if (!detail) return;
    const full = await api('GET', `/api/prod/cmt-receipts/${detail.id}`, token);
    setDetail(full);
  };

  const addLine = async () => {
    if (!lineForm.product_name.trim() && !lineForm.sku_code.trim()) { toast.error('Nama produk atau kode SKU wajib'); return; }
    setSaving(true);
    try {
      await api('POST', `/api/prod/cmt-receipts/${detail.id}/lines`, token, {
        sku_code: lineForm.sku_code.trim(),
        product_name: lineForm.product_name.trim(),
        color: lineForm.color.trim(),
        size: lineForm.size.trim(),
        qty_expected: Number(lineForm.qty_expected) || 0,
      });
      setShowAddLine(false);
      setLineForm({ sku_code: '', product_name: '', color: '', size: '', qty_expected: '' });
      await reloadDetail();
      load();
    } catch (e) {
      toast.error(`Gagal tambah baris: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const setCount = async (line, val) => {
    try {
      await api('PUT', `/api/prod/cmt-receipts/${detail.id}/lines/${line.id}`, token, { qty_actual: val === '' ? null : Number(val) });
      setDetail((prev) => ({ ...prev, lines: (prev.lines || []).map((l) => (l.id === line.id ? { ...l, qty_actual: val === '' ? null : Number(val) } : l)) }));
    } catch (e) {
      toast.error(`Gagal simpan hitung: ${e.message}`);
    }
  };

  const deleteLine = async (line) => {
    if (!window.confirm('Hapus baris ini?')) return;
    try {
      await api('DELETE', `/api/prod/cmt-receipts/${detail.id}/lines/${line.id}`, token);
      await reloadDetail();
      load();
    } catch (e) {
      toast.error(`Gagal hapus: ${e.message}`);
    }
  };

  const submitReceipt = async () => {
    setSaving(true);
    try {
      await api('POST', `/api/prod/cmt-receipts/${detail.id}/submit`, token, {});
      toast.success('Penerimaan diajukan ke Admin Produksi');
      await reloadDetail();
      load();
    } catch (e) {
      toast.error(`Gagal submit: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const approveReceipt = async () => {
    setSaving(true);
    try {
      await api('POST', `/api/prod/cmt-receipts/${detail.id}/approve`, token, {});
      toast.success('Disetujui — stok FG diposting');
      await reloadDetail();
      load();
    } catch (e) {
      toast.error(`Gagal approve: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const doReject = async () => {
    setSaving(true);
    try {
      await api('POST', `/api/prod/cmt-receipts/${rejectFor.id}/reject`, token, { reason: rejectReason.trim() });
      toast.success('Penerimaan ditolak');
      setRejectFor(null);
      setRejectReason('');
      if (detail && detail.id === rejectFor.id) await reloadDetail();
      load();
    } catch (e) {
      toast.error(`Gagal reject: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const stat = (label, val, testId, cls) => (
    <div className="bg-foreground/5 border border-border rounded-lg px-3 py-2" data-testid={testId}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-lg font-bold ${cls || 'text-foreground'}`}>{fmt(val)}</div>
    </div>
  );

  const dLines = detail?.lines || [];
  const dCounted = dLines.filter((l) => l.qty_actual !== null && l.qty_actual !== undefined);
  const dTotalExp = dLines.reduce((s, l) => s + (l.qty_expected || 0), 0);
  const dTotalAct = dCounted.reduce((s, l) => s + (l.qty_actual || 0), 0);
  const isDraft = detail?.status === 'Draft';
  const isSubmitted = detail?.status === 'Submitted';

  return (
    <div className="flex flex-col gap-4" data-testid="receipt-section">
      {/* summary */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="receipt-summary">
          {stat('Total', summary.total, 'stat-total')}
          {stat('Draft', summary.pending, 'stat-draft', 'text-muted-foreground')}
          {stat('Diajukan', summary.submitted, 'stat-submitted', 'text-amber-600 dark:text-amber-400')}
          {stat('Disetujui', summary.approved, 'stat-approved', 'text-emerald-600 dark:text-emerald-400')}
          {stat('Ditolak', summary.rejected, 'stat-rejected', 'text-red-600 dark:text-red-400')}
          {stat('Pcs Hari Ini', summary.pcs_approved_today, 'stat-pcs-today', 'text-blue-600 dark:text-blue-400')}
        </div>
      )}

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[220px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input placeholder="Cari vendor CMT…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" data-testid="search-receipt-input" />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]" data-testid="receipt-status-filter">
            <SelectValue placeholder="Semua status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" data-testid="receipt-filter-all">Semua status</SelectItem>
            <SelectItem value="Draft" data-testid="receipt-filter-draft">Draft</SelectItem>
            <SelectItem value="Submitted" data-testid="receipt-filter-submitted">Diajukan</SelectItem>
            <SelectItem value="Approved" data-testid="receipt-filter-approved">Disetujui</SelectItem>
            <SelectItem value="Rejected" data-testid="receipt-filter-rejected">Ditolak</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={load} disabled={loading} data-testid="refresh-receipt-btn">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
        <Button onClick={() => setCreateOpen(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="create-receipt-btn">
          <Plus className="w-4 h-4 mr-2" /> Penerimaan Baru
        </Button>
      </div>

      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'wms-stock-hub', label: 'Stok Produk Jadi (FG)', icon: Package, primary: true, hint: 'Approve penerimaan → stok FG bertambah' },
        ]}
      />

      {/* list */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="loading-receipts">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border border-border rounded-xl p-4 space-y-3">
              <div className="flex justify-between"><Skeleton className="h-5 w-32" /><Skeleton className="h-5 w-16" /></div>
              <Skeleton className="h-4 w-48" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={PackageCheck}
          title="Belum ada penerimaan CMT"
          description="Catat hasil jadi dari vendor CMT. Klik 'Penerimaan Baru' untuk memulai."
          action={{ label: 'Penerimaan Baru', onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="receipt-list">
          {items.map((r) => (
            <div
              key={r.id}
              className="bg-foreground/5 border border-border rounded-xl p-4 hover:bg-foreground/10 transition-colors cursor-pointer"
              onClick={() => openDetail(r)}
              data-testid={`receipt-card-${r.receipt_code}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <PackageCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                    <h3 className="font-semibold text-foreground truncate">{r.receipt_code}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{r.cmt_name}</p>
                  {r.wo_number && <p className="text-xs text-muted-foreground/70">WO: {r.wo_number}</p>}
                </div>
                <StatusBadge map={RECEIPT_STATUS} status={r.status} testId={`receipt-status-${r.receipt_code}`} />
              </div>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Baris:</span><span className="font-mono">{fmt(r.line_count)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Qty Kirim:</span><span className="font-mono">{fmt(r.total_qty_expected)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Qty Hitung:</span><span className="font-mono">{fmt(r.total_qty_actual)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Tgl:</span><span>{fmtDate(r.receipt_date || r.created_at)}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* CREATE RECEIPT DIALOG */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg" data-testid="create-receipt-dialog">
          <DialogHeader>
            <DialogTitle>Buat Penerimaan CMT</DialogTitle>
            <DialogDescription>Catat hasil jadi yang diterima dari vendor. Status awal: Draft.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2">
              <Label>Nama Vendor CMT *</Label>
              <Input value={form.cmt_name} onChange={(e) => setForm({ ...form, cmt_name: e.target.value })} placeholder="mis. CV Jahit Makmur" data-testid="input-receipt-cmt-name" />
            </div>
            <div>
              <Label>No. Work Order</Label>
              <Input value={form.wo_number} onChange={(e) => setForm({ ...form, wo_number: e.target.value })} placeholder="WO-2026-001" data-testid="input-receipt-wo" />
            </div>
            <div>
              <Label>No. Surat Jalan Vendor</Label>
              <Input value={form.delivery_note} onChange={(e) => setForm({ ...form, delivery_note: e.target.value })} placeholder="SJ vendor" data-testid="input-delivery-note" />
            </div>
            <div className="col-span-2">
              <Label>Catatan</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="input-receipt-notes" />
            </div>
            <div className="col-span-2">
              <DocNumberField
                policy={numPolicy} value={receiptCode} onChange={setReceiptCode}
                testId="receipt-docnum" label="Nomor Penerimaan" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} data-testid="cancel-create-receipt">Batal</Button>
            <Button onClick={submitCreate} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="submit-create-receipt">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} Buat & Isi Detail
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* RECEIPT DETAIL DIALOG */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-auto" data-testid="receipt-detail-dialog">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <PackageCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400" /> {detail.receipt_code}
                  <StatusBadge map={RECEIPT_STATUS} status={detail.status} testId="detail-receipt-status" />
                </DialogTitle>
                <DialogDescription>{detail.cmt_name}{detail.wo_number ? ` · WO: ${detail.wo_number}` : ''}</DialogDescription>
              </DialogHeader>

              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-muted-foreground">
                  Total kirim: <span className="font-mono text-foreground">{fmt(dTotalExp)}</span> · Total hitung: <span className="font-mono text-foreground">{fmt(dTotalAct)}</span>
                </div>
                {isDraft && (
                  <Button size="sm" variant="outline" onClick={() => setShowAddLine((s) => !s)} data-testid="toggle-add-receiptline">
                    <Plus className="w-3.5 h-3.5 mr-1" /> Tambah Baris
                  </Button>
                )}
              </div>

              {showAddLine && isDraft && (
                <div className="grid grid-cols-12 gap-2 items-end border border-border rounded-lg p-3 mb-2" data-testid="add-receiptline-form">
                  <div className="col-span-3"><Label className="text-xs">SKU</Label><Input value={lineForm.sku_code} onChange={(e) => setLineForm({ ...lineForm, sku_code: e.target.value })} data-testid="input-line-sku" /></div>
                  <div className="col-span-4"><Label className="text-xs">Nama Produk</Label><Input value={lineForm.product_name} onChange={(e) => setLineForm({ ...lineForm, product_name: e.target.value })} data-testid="input-line-product" /></div>
                  <div className="col-span-2"><Label className="text-xs">Warna</Label><Input value={lineForm.color} onChange={(e) => setLineForm({ ...lineForm, color: e.target.value })} data-testid="input-line-color" /></div>
                  <div className="col-span-1"><Label className="text-xs">Size</Label><Input value={lineForm.size} onChange={(e) => setLineForm({ ...lineForm, size: e.target.value })} data-testid="input-line-size" /></div>
                  <div className="col-span-2"><Label className="text-xs">Qty Kirim</Label><Input type="number" min="0" value={lineForm.qty_expected} onChange={(e) => setLineForm({ ...lineForm, qty_expected: e.target.value })} data-testid="input-line-qty-expected" /></div>
                  <div className="col-span-12 flex justify-end">
                    <Button size="sm" onClick={addLine} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="add-receiptline-btn">
                      {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Plus className="w-3.5 h-3.5 mr-1" />} Tambah
                    </Button>
                  </div>
                </div>
              )}

              <div className="border border-border rounded-lg overflow-hidden">
                <table className="w-full text-xs" data-testid="receipt-lines-table">
                  <thead className="bg-foreground/5 text-muted-foreground">
                    <tr>
                      <th className="text-left px-3 py-2">Produk</th>
                      <th className="text-left px-3 py-2">Varian</th>
                      <th className="text-right px-3 py-2">Kirim</th>
                      <th className="text-right px-3 py-2">Hitung Fisik (QC)</th>
                      {isDraft && <th className="px-3 py-2"></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {dLines.length === 0 ? (
                      <tr><td colSpan={isDraft ? 5 : 4} className="px-3 py-6 text-center text-muted-foreground">Belum ada baris. Tambahkan item.</td></tr>
                    ) : dLines.map((l) => (
                      <tr key={l.id} className="border-t border-border" data-testid={`receipt-line-${l.id}`}>
                        <td className="px-3 py-2">{l.product_name || l.sku_code || '-'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{[l.color, l.size].filter(Boolean).join(' / ') || '-'}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(l.qty_expected)}</td>
                        <td className="px-3 py-2 text-right">
                          {isDraft ? (
                            <Input
                              type="number" min="0"
                              defaultValue={l.qty_actual ?? ''}
                              onBlur={(e) => setCount(l, e.target.value)}
                              className="h-8 w-24 ml-auto text-right"
                              data-testid={`line-count-input-${l.id}`}
                            />
                          ) : (
                            <span className="font-mono">{l.qty_actual ?? '-'}</span>
                          )}
                        </td>
                        {isDraft && (
                          <td className="px-3 py-2 text-right">
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-red-600 hover:text-red-700" onClick={() => deleteLine(l)} data-testid={`delete-line-${l.id}`}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {detail.status === 'Rejected' && detail.reject_reason && (
                <div className="mt-2 text-sm text-red-600 dark:text-red-400" data-testid="detail-reject-reason">
                  Alasan ditolak: {detail.reject_reason}
                </div>
              )}

              <DialogFooter className="mt-3">
                {isDraft && (
                  <>
                    <Button variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => setRejectFor(detail)} data-testid="detail-reject-btn">
                      <XCircle className="w-4 h-4 mr-2" /> Tolak
                    </Button>
                    <Button onClick={submitReceipt} disabled={saving || dCounted.length === 0} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="receipt-submit-btn">
                      {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />} Ajukan ke Admin
                    </Button>
                  </>
                )}
                {isSubmitted && (
                  <>
                    <Button variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => setRejectFor(detail)} data-testid="detail-reject-btn-2">
                      <XCircle className="w-4 h-4 mr-2" /> Tolak
                    </Button>
                    <Button onClick={approveReceipt} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="receipt-approve-btn">
                      {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />} Setujui & Posting FG
                    </Button>
                  </>
                )}
                {(detail.status === 'Approved' || detail.status === 'Rejected') && (
                  <Button variant="outline" onClick={() => setDetail(null)} data-testid="detail-close-btn">
                    <FileText className="w-4 h-4 mr-2" /> Tutup
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* REJECT DIALOG */}
      <Dialog open={!!rejectFor} onOpenChange={(o) => !o && setRejectFor(null)}>
        <DialogContent className="max-w-md" data-testid="reject-receipt-dialog">
          <DialogHeader>
            <DialogTitle>Tolak Penerimaan</DialogTitle>
            <DialogDescription>Berikan alasan penolakan {rejectFor?.receipt_code}.</DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Label>Alasan</Label>
            <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="mis. kualitas jahitan buruk" data-testid="input-reject-reason" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectFor(null)} data-testid="cancel-reject">Batal</Button>
            <Button onClick={doReject} disabled={saving} className="bg-red-600 hover:bg-red-700 text-white" data-testid="confirm-reject">
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <XCircle className="w-4 h-4 mr-2" />} Tolak
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
// MAIN HUB
// ════════════════════════════════════════════════════════════════════════
export default function WMSCMTDispatchesModule({ token, onNavigate }) {
  const [section, setSection] = useState('dispatch');

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-card via-card to-muted text-foreground" data-testid="wms-cmt-dispatches-module">
      {/* header */}
      <div className="border-b border-border bg-black/5 dark:bg-black/20 backdrop-blur-sm">
        <div className="p-6 pb-0">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 rounded-xl bg-blue-100 dark:bg-blue-500/20 border border-blue-300 dark:border-blue-500/30">
              <Truck className="w-5 h-5 text-blue-600 dark:text-blue-300" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-foreground">CMT Vendor / Sub-contract</h1>
              <p className="text-sm text-muted-foreground mt-0.5">Kirim komponen ke vendor & terima hasil jadi (QC + posting FG)</p>
            </div>
          </div>

          <Tabs value={section} onValueChange={setSection}>
            <TabsList className="bg-foreground/5">
              <TabsTrigger value="dispatch" data-testid="section-dispatch">
                <Truck className="w-4 h-4 mr-2" /> Kirim ke Vendor
              </TabsTrigger>
              <TabsTrigger value="receipt" data-testid="section-receipt">
                <PackageCheck className="w-4 h-4 mr-2" /> Terima Hasil Jadi
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* body */}
      <div className="flex-1 overflow-auto p-6">
        {section === 'dispatch'
          ? <DispatchSection token={token} onNavigate={onNavigate} />
          : <ReceiptSection token={token} onNavigate={onNavigate} />}
      </div>
    </div>
  );
}
