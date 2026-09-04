import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ClipboardList, Plus, RefreshCw, Eye, Trash2, FileText, CheckCircle2,
  Loader2, Search, Package, Truck, Hammer, AlertTriangle, MapPin,
  X, Save, User, ListChecks, PlayCircle, ScanLine,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
// Sprint A.1: UniversalScanner SSOT
import UniversalScanner from './scanner/UniversalScanner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CFG = {
  pending:     { label: 'Pending',    color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300' },
  in_progress: { label: 'Berjalan',   color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300' },
  completed:   { label: 'Selesai',    color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300' },
};

const SOURCE_ICON = {
  shipment: Truck,
  material_issue: Hammer,
  pending_movement: Package,
  manual: ListChecks,
};

export default function WMSPickListModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [picklists, setPicklists] = useState([]);
  const [tab, setTab] = useState('pending');
  const [loading, setLoading] = useState(false);
  const [createDialog, setCreateDialog] = useState(false);
  const [viewing, setViewing] = useState(null); // {picklist}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const statusParam = tab === 'all' ? '' : `?status=${tab}`;
      const r = await fetch(`${API}/api/wms/picklist${statusParam}`, { headers });
      const d = await r.json();
      setPicklists(d.picklists || []);
    } finally { setLoading(false); }
  }, [headers, tab]);

  useEffect(() => { load(); }, [load]);

  const handleOpenView = async (id) => {
    const r = await fetch(`${API}/api/wms/picklist/${id}`, { headers });
    const d = await r.json();
    if (r.ok) setViewing(d.picklist);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus pick list ini?')) return;
    const r = await fetch(`${API}/api/wms/picklist/${id}`, { method: 'DELETE', headers });
    if (!r.ok) { toast.error('Gagal hapus'); return; }
    toast.success('Pick list dihapus');
    load();
  };

  const handleComplete = async (id) => {
    if (!window.confirm('Tandai pick list sebagai selesai?')) return;
    const r = await fetch(`${API}/api/wms/picklist/${id}/complete`, { method: 'POST', headers });
    if (!r.ok) { toast.error('Gagal complete'); return; }
    toast.success('Pick list selesai');
    load();
    setViewing(null);
  };

  const downloadPdf = (pl) => {
    const url = `${API}/api/wms/picklist/${pl.picklist_id}/pdf`;
    fetch(url, { headers })
      .then(r => r.ok ? r.blob() : Promise.reject())
      .then(blob => {
        const href = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = href; a.download = `picklist_${pl.ref_number}.pdf`; a.click();
        URL.revokeObjectURL(href);
      })
      .catch(() => toast.error('Gagal download PDF'));
  };

  const markPicked = async (picklist_id, pick_item_id, picked_qty) => {
    const r = await fetch(`${API}/api/wms/picklist/${picklist_id}/item/${pick_item_id}/pick`, {
      method: 'PUT', headers, body: JSON.stringify({ picked_qty }),
    });
    if (!r.ok) { toast.error('Gagal update'); return; }
    // Refresh viewing
    handleOpenView(picklist_id);
    load();
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(picklists, 10);
  return (
    <div className="space-y-6 p-6" data-testid="wms-picklist-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-indigo-600 dark:text-indigo-400" /> Pick List Generator
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Daftar ambil barang dengan rute optimal berdasarkan lokasi rak · {picklists.length} pick list
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="picklist-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setCreateDialog(true)} data-testid="picklist-create">
            <Plus className="w-4 h-4 mr-1" /> Buat Pick List
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-4 w-full max-w-md">
          <TabsTrigger value="pending" className="text-xs">Pending</TabsTrigger>
          <TabsTrigger value="in_progress" className="text-xs">Berjalan</TabsTrigger>
          <TabsTrigger value="completed" className="text-xs">Selesai</TabsTrigger>
          <TabsTrigger value="all" className="text-xs">Semua</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4 space-y-3">
          {loading && <div className="text-center py-10"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" /></div>}

          <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-3">Ref / Sumber</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="text-left px-4 py-3">Items</th>
                  <th className="text-left px-4 py-3">Progress</th>
                  <th className="text-left px-4 py-3">Operator</th>
                  <th className="text-left px-4 py-3">Tanggal</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {paged.map(pl => {
                  const picked = (pl.items || []).filter(i => i.status === 'picked').length;
                  const total = (pl.items || []).length;
                  const pct = total ? Math.round(picked / total * 100) : 0;
                  const Icon = SOURCE_ICON[pl.source_type] || ListChecks;
                  const s = STATUS_CFG[pl.status] || STATUS_CFG.pending;
                  return (
                    <tr key={pl.picklist_id} className="hover:bg-foreground/5" data-testid={`picklist-row-${pl.picklist_id}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium font-mono text-xs">{pl.ref_number}</div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                          <Icon className="w-3 h-3" />
                          {pl.source_type} {pl.source_ref && `· ${pl.source_ref}`}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${s.color}`}>{s.label}</span>
                      </td>
                      <td className="px-4 py-3 text-xs">
                        <span className="font-medium">{total}</span> item · {pl.total_qty || 0} pcs
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 bg-foreground/10 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-400" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs font-mono">{picked}/{total}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs">{pl.assignee_name || '—'}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {(pl.created_at || '').slice(0, 16).replace('T', ' ')}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          <Button size="icon" variant="ghost" className="h-7 w-7" title="Lihat"
                            onClick={() => handleOpenView(pl.picklist_id)}
                            data-testid={`picklist-view-${pl.picklist_id}`}>
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7" title="Cetak PDF"
                            onClick={() => downloadPdf(pl)}
                            data-testid={`picklist-pdf-${pl.picklist_id}`}>
                            <FileText className="w-3.5 h-3.5" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400"
                            onClick={() => handleDelete(pl.picklist_id)}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {picklists.length === 0 && !loading && (
                  <tr>
                    <td colSpan={7} className="text-center py-12 text-muted-foreground">
                      <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-30" />
                      <p>Belum ada pick list</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        </TabsContent>
      </Tabs>

      {createDialog && (
        <CreatePickListDialog
          headers={headers}
          onCreated={(pl) => { setCreateDialog(false); load(); handleOpenView(pl.picklist_id); }}
          onClose={() => setCreateDialog(false)}
        />
      )}

      {viewing && (
        <PickListDetailDialog
          picklist={viewing}
          onMarkPicked={markPicked}
          onComplete={() => handleComplete(viewing.picklist_id)}
          onDownloadPdf={() => downloadPdf(viewing)}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}

function CreatePickListDialog({ headers, onCreated, onClose }) {
  const [sourceType, setSourceType] = useState('shipment');
  const [shipments, setShipments] = useState([]);
  const [mis, setMis] = useState([]);
  const [sourceId, setSourceId] = useState('');
  const [preview, setPreview] = useState(null);
  const [assignee, setAssignee] = useState('');
  const [employees, setEmployees] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Load data
    fetch(`${API}/api/rahaza/shipments?limit=50`, { headers }).then(r => r.json()).then(d => setShipments(Array.isArray(d) ? d : d.shipments || []));
    fetch(`${API}/api/rahaza/material-issues?limit=50`, { headers }).then(r => r.json()).then(d => setMis(Array.isArray(d) ? d : d.issues || d.rows || [])).catch(() => {});
    // FASE 20 — dulu '/api/rahaza/master/employees' (404 senyap) ⇒ daftar petugas
    // pick selalu kosong. Endpoint benar membalas {total, items:[...]}.
    fetch(`${API}/api/rahaza/employees?active_only=true&limit=200`, { headers }).then(r => r.json()).then(d => setEmployees(Array.isArray(d) ? d : d.items || d.rows || []));
  }, [headers]);

  const genPreview = async () => {
    if (!sourceId) { toast.error('Pilih sumber'); return; }
    const r = await fetch(`${API}/api/wms/picklist/source/${sourceType}/${sourceId}`, { headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal generate'); return; }
    setPreview(d);
  };

  const savePickList = async () => {
    if (!preview) return;
    setSaving(true);
    const emp = employees.find(e => e.id === assignee);
    const body = {
      source_type: preview.source_type,
      source_id: preview.source_id,
      source_ref: preview.source_ref,
      items: preview.items.map(i => ({ material_id: i.material_id, material_code: i.material_code, material_name: i.material_name, qty: i.qty_to_pick, unit: i.unit })),
      assignee_id: assignee || '',
      assignee_name: emp?.name || '',
    };
    const r = await fetch(`${API}/api/wms/picklist`, { method: 'POST', headers, body: JSON.stringify(body) });
    const d = await r.json();
    setSaving(false);
    if (!r.ok) { toast.error(d.detail || 'Gagal simpan'); return; }
    toast.success('Pick list dibuat');
    onCreated(d.picklist);
  };

  const options = sourceType === 'shipment' ? shipments : mis;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Buat Pick List</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Sumber</Label>
              <Select value={sourceType} onValueChange={v => { setSourceType(v); setSourceId(''); setPreview(null); }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="shipment">Shipment (FG Outbound)</SelectItem>
                  <SelectItem value="material_issue">Material Issue (RM Outbound)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>{sourceType === 'shipment' ? 'Pilih Shipment' : 'Pilih Material Issue'}</Label>
              <Select value={sourceId} onValueChange={setSourceId}>
                <SelectTrigger><SelectValue placeholder="— Pilih —" /></SelectTrigger>
                <SelectContent>
                  {options.slice(0, 50).map(o => (
                    <SelectItem key={o.id} value={o.id}>
                      {`${o.shipment_number || o.mi_number || o.issue_number || o.id.slice(0, 8)} · ${(o.customer_name || o.reference || 'manual').slice(0, 30)}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={genPreview} disabled={!sourceId} data-testid="picklist-preview">
              <Eye className="w-4 h-4 mr-1" /> Preview Pick List
            </Button>
          </div>

          {preview && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 overflow-hidden">
              <div className="px-4 py-2 bg-foreground/5 flex items-center justify-between">
                <div className="text-xs">
                  <span className="font-semibold">{preview.source_ref}</span> ·
                  <span className="text-muted-foreground"> {preview.total_items} item · {preview.total_qty} pcs</span>
                  {preview.short_items > 0 && (
                    <span className="text-red-700 dark:text-red-400 ml-2">⚠ {preview.short_items} item short</span>
                  )}
                </div>
              </div>
              <table className="w-full text-xs">
                <thead className="bg-foreground/5">
                  <tr className="text-left text-muted-foreground">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Barcode Posisi</th>
                    <th className="px-3 py-2">Lokasi</th>
                    <th className="px-3 py-2">Material</th>
                    <th className="px-3 py-2 text-right">Qty</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {preview.items.map((it, i) => (
                    <tr key={it.pick_item_id} className={it.status === 'short' ? 'bg-red-100 dark:bg-red-500/5' : ''}>
                      <td className="px-3 py-2">{i + 1}</td>
                      <td className="px-3 py-2 font-mono">{it.position_barcode || '—'}</td>
                      <td className="px-3 py-2">
                        {it.status === 'short' ? <span className="text-red-700 dark:text-red-400">—</span> :
                          `${it.building_code}/${it.zone_code}/${it.rack_code}`}
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{it.material_code}</div>
                        <div className="text-[10px] text-muted-foreground">{it.material_name}</div>
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{it.qty_to_pick} {it.unit}</td>
                      <td className="px-3 py-2">
                        {it.status === 'short'
                          ? <span className="text-red-700 dark:text-red-400 text-[10px] flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> SHORT</span>
                          : <span className="text-muted-foreground text-[10px]">pending</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {preview && (
            <div className="space-y-1">
              <Label>Tugaskan ke Operator (opsional)</Label>
              <Select value={assignee || 'none'} onValueChange={v => setAssignee(v === 'none' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Pilih operator..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">— Tidak ditugaskan —</SelectItem>
                  {employees.slice(0, 100).map(e => (
                    <SelectItem key={e.id} value={e.id}>{`${e.employee_code} — ${e.name}`}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={savePickList} disabled={!preview || saving} data-testid="picklist-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
            Simpan Pick List
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PickListDetailDialog({ picklist, onMarkPicked, onComplete, onDownloadPdf, onClose }) {
  const items = picklist.items || [];
  const picked = items.filter(i => i.status === 'picked').length;
  const total = items.length;
  const pct = total ? Math.round(picked / total * 100) : 0;
  const s = STATUS_CFG[picklist.status] || STATUS_CFG.pending;
  const [localItems, setLocalItems] = useState(items);

  // Sprint A.1: Scan-to-pick handler
  const handleScanToPick = useCallback((barcode) => {
    const item = localItems.find(
      it => it.position_barcode && it.position_barcode === barcode && it.status !== 'picked'
    );
    if (item) {
      toast.success(`Posisi ${barcode} — mengkonfirmasi pick ${item.material_code}`);
      onMarkPicked(picklist.picklist_id, item.pick_item_id, item.qty_to_pick);
      setLocalItems(prev => prev.map(i =>
        i.pick_item_id === item.pick_item_id
          ? { ...i, status: 'picked', picked_qty: i.qty_to_pick }
          : i
      ));
    } else {
      // Try matching material code/barcode too
      const byMat = localItems.find(
        it => (it.material_code === barcode || it.material_barcode === barcode) && it.status !== 'picked'
      );
      if (byMat) {
        toast.success(`Material ${barcode} — mengkonfirmasi pick`);
        onMarkPicked(picklist.picklist_id, byMat.pick_item_id, byMat.qty_to_pick);
        setLocalItems(prev => prev.map(i =>
          i.pick_item_id === byMat.pick_item_id
            ? { ...i, status: 'picked', picked_qty: i.qty_to_pick }
            : i
        ));
      } else {
        toast.warning(`Barcode "${barcode}" tidak cocok dengan item pending di pick list ini`);
      }
    }
  }, [localItems, onMarkPicked, picklist.picklist_id]);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            Pick List {picklist.ref_number}
            <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${s.color}`}>{s.label}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2">
            <div className="text-muted-foreground">Sumber</div>
            <div className="font-semibold">{picklist.source_type} · {picklist.source_ref}</div>
          </div>
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2">
            <div className="text-muted-foreground">Operator</div>
            <div className="font-semibold">{picklist.assignee_name || '—'}</div>
          </div>
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2">
            <div className="text-muted-foreground">Total Items</div>
            <div className="font-semibold">{total} item · {picklist.total_qty} pcs</div>
          </div>
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-2">
            <div className="text-muted-foreground">Progress</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-foreground/10 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-400" style={{ width: `${pct}%` }} />
              </div>
              <span className="font-mono">{picked}/{total}</span>
            </div>
          </div>
        </div>

        {/* Sprint A.1: Scan-to-Pick input */}
        {picklist.status !== 'completed' && (
          <div className="mb-3 p-3 rounded-xl bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-300 dark:border-indigo-400/20">
            <div className="flex items-center gap-2 mb-1.5">
              <ScanLine className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
              <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-300">Scan-to-Pick</span>
              <span className="text-[10px] text-muted-foreground">Scan barcode posisi atau material untuk konfirmasi otomatis</span>
            </div>
            <UniversalScanner
              variant="inline"
              onScan={handleScanToPick}
              placeholder="Scan posisi / material barcode..."
              autoFocus
              data-testid="picklist-scan-input"
            />
          </div>
        )}

        <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">#</th>
                <th className="px-3 py-2 text-left">Barcode Posisi</th>
                <th className="px-3 py-2 text-left">Lokasi</th>
                <th className="px-3 py-2 text-left">Material</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-center">Pick</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {localItems.map((it, i) => (
                <PickItemRow
                  key={it.pick_item_id}
                  item={it} idx={i + 1}
                  onMark={(qty) => onMarkPicked(picklist.picklist_id, it.pick_item_id, qty)}
                  disabled={picklist.status === 'completed'}
                />
              ))}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onDownloadPdf}><FileText className="w-4 h-4 mr-1" /> PDF</Button>
          {picklist.status !== 'completed' && (
            <Button onClick={onComplete} data-testid="picklist-complete">
              <CheckCircle2 className="w-4 h-4 mr-1" /> Tandai Selesai
            </Button>
          )}
          <Button variant="ghost" onClick={onClose}>Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PickItemRow({ item, idx, onMark, disabled }) {
  const [qty, setQty] = useState(item.picked_qty || item.qty_to_pick);
  const isShort = item.status === 'short';
  const isPicked = item.status === 'picked';
  const isPartial = item.status === 'partial';

  return (
    <tr className={isShort ? 'bg-red-100 dark:bg-red-500/5' : isPicked ? 'bg-emerald-100 dark:bg-emerald-500/5' : ''}>
      <td className="px-3 py-2 text-xs">{idx}</td>
      <td className="px-3 py-2 font-mono text-xs">{item.position_barcode || '—'}</td>
      <td className="px-3 py-2 text-xs">
        {isShort ? <span className="text-red-700 dark:text-red-400">—</span> :
          <span className="flex items-center gap-1"><MapPin className="w-3 h-3 text-muted-foreground" />{item.building_code}/{item.zone_code}/{item.rack_code}</span>}
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-xs">{item.material_code}</div>
        <div className="text-[10px] text-muted-foreground">{item.material_name}</div>
      </td>
      <td className="px-3 py-2 text-right font-mono text-xs">{item.qty_to_pick} {item.unit}</td>
      <td className="px-3 py-2 text-center">
        {isShort ? (
          <span className="text-red-700 dark:text-red-400 text-[10px] flex items-center justify-center gap-1">
            <AlertTriangle className="w-3 h-3" /> SHORT
          </span>
        ) : isPicked ? (
          <span className="text-emerald-600 dark:text-emerald-400 text-[10px] flex items-center justify-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> {item.picked_qty}
          </span>
        ) : (
          <div className="flex items-center gap-1 justify-center">
            <Input type="number" value={qty} onChange={e => setQty(Number(e.target.value))}
              className="h-7 w-16 text-xs" min={0} step={0.01} disabled={disabled} />
            <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-600 dark:text-emerald-400"
              onClick={() => onMark(qty)} disabled={disabled}
              data-testid={`pick-item-${item.pick_item_id}`}>
              <CheckCircle2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        )}
      </td>
    </tr>
  );
}
