import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Plus, Trash2, AlertTriangle, CheckCircle2, RefreshCw,
  Warehouse, Info, Loader2
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';

export default function MaklonMaterialIssuePanel({ order, headers }) {
  const [issues, setIssues] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ material_id: '', location_id: '', qty: '', unit: 'meter', notes: '' });
  const [saving, setSaving] = useState(false);
  const [stockInfo, setStockInfo] = useState(null);

  const orderId = order?.id;

  const load = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    try {
      const [issR, matR, locR] = await Promise.all([
        fetch(`/api/dewi/maklon/orders/${orderId}/material-issues`, { headers }),
        fetch('/api/rahaza/materials?limit=200', { headers }),
        // FASE D: sumber lokasi = SSOT storage terpadu (zona kanonik wh_* + legacy storage).
        // Sebelumnya /api/wms/legacy/locations (bin/wh_positions) → id TIDAK cocok dgn
        // rahaza_material_stock → cek stok selalu 0 (mismatch Maklon). Sekarang konsisten.
        fetch('/api/rahaza/storage-locations', { headers }),
      ]);
      if (issR.ok) setIssues(await issR.json());
      if (matR.ok) {
        const m = await matR.json();
        setMaterials(Array.isArray(m) ? m : (m.items || []));
      }
      if (locR.ok) {
        const l = await locR.json();
        setLocations(Array.isArray(l) ? l : (l.items || []));
      }
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [orderId, headers]);

  useEffect(() => {
    if (!orderId) return undefined;
    let active = true;
    (async () => {
      try {
        const [issR, matR, locR] = await Promise.all([
          fetch(`/api/dewi/maklon/orders/${orderId}/material-issues`, { headers }),
          fetch('/api/rahaza/materials?limit=200', { headers }),
          fetch('/api/rahaza/storage-locations', { headers }),
        ]);
        if (!active) return;
        if (issR.ok) setIssues(await issR.json());
        if (matR.ok) {
          const m = await matR.json();
          setMaterials(Array.isArray(m) ? m : (m.items || []));
        }
        if (locR.ok) {
          const l = await locR.json();
          setLocations(Array.isArray(l) ? l : (l.items || []));
        }
      } catch (e) { console.warn(e); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [orderId, headers]);

  const checkStock = useCallback(async (material_id, location_id) => {
    if (!material_id) { setStockInfo(null); return; }
    try {
      // FASE D: /material-stock balikin ARRAY baris per-lokasi. Backend Maklon validasi
      // stok KANONIK lintas-lokasi (stock_service.get_onhand), jadi tampilkan total
      // tersedia (semua lokasi) + rincian di lokasi terpilih.
      const r = await fetch(`/api/rahaza/material-stock?material_id=${material_id}`, { headers });
      if (!r.ok) { setStockInfo(null); return; }
      const d = await r.json();
      const rows = Array.isArray(d) ? d : (d.items || []);
      const total = rows.reduce((s, x) => s + (Number(x.qty) || 0), 0);
      const unit = rows[0]?.unit || '';
      const locRow = location_id ? rows.find(x => x.location_id === location_id) : null;
      setStockInfo({ qty: total, unit, loc_qty: locRow ? (Number(locRow.qty) || 0) : null, has_location: !!location_id });
    } catch (e) { setStockInfo(null); }
  }, [headers]);

  const handleFieldChange = (field, value) => {
    setForm(p => { const n = {...p, [field]: value}; return n; });
    if (field === 'material_id' || field === 'location_id') {
      const newForm = {...form, [field]: value};
      checkStock(newForm.material_id, newForm.location_id);
    }
  };

  const submit = async () => {
    if (!form.material_id || !form.location_id || !form.qty) {
      toast.error('Material, lokasi, dan qty wajib diisi'); return;
    }
    setSaving(true);
    try {
      const r = await fetch(`/api/dewi/maklon/orders/${order.id}/material-issues`, {
        method: 'POST', headers,
        body: JSON.stringify({ ...form, qty: Number(form.qty) }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Gagal');
      toast.success(data.message || 'Material berhasil dikeluarkan');
      setShowForm(false);
      setForm({ material_id: '', location_id: '', qty: '', unit: 'meter', notes: '' });
      setStockInfo(null);
      load();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const cancelIssue = async (issueId) => {
    if (!window.confirm('Batalkan issue ini? Stok akan dikembalikan ke warehouse.')) return;
    try {
      const r = await fetch(`/api/dewi/maklon/orders/${order.id}/material-issues/${issueId}`, {
        method: 'DELETE', headers,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success(d.message);
      load();
    } catch (err) { toast.error(err.message); }
  };

  const totalQty = useMemo(() => issues.reduce((s, i) => s + (i.qty || 0), 0), [issues]);
  const isInternal = order?.fabric_provided_by !== 'client';

  return (
    <div className="space-y-4" data-testid="maklon-material-issues">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Warehouse className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
          <span className="text-sm font-semibold text-foreground/80">Material Issue</span>
          <span className="text-xs text-foreground/40">({issues.length} item, total {totalQty.toFixed(2)} unit)</span>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={load} className="h-7 w-7 p-0">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          {isInternal && !['completed','invoiced','cancelled'].includes(order?.status) && (
            <Button size="sm" className="gap-1.5 h-7 text-xs" onClick={() => setShowForm(true)} data-testid="material-issue-add-btn">
              <Plus className="w-3 h-3" /> Issue Material
            </Button>
          )}
        </div>
      </div>

      {!isInternal && (
        <div className="flex items-start gap-2 bg-blue-100 dark:bg-blue-500/10 border border-blue-400/25 rounded-lg p-3 text-xs text-blue-600 dark:text-blue-300">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          Order ini menggunakan material dari klien. Material Issue hanya untuk order dengan fabric dari internal.
        </div>
      )}

      {/* Issues list */}
      {loading ? (
        <div className="text-center py-6 text-foreground/40 text-xs flex items-center justify-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Memuat...
        </div>
      ) : issues.length === 0 ? (
        <div className="text-center py-8 text-foreground/35 text-xs">
          <Warehouse className="w-6 h-6 mx-auto mb-2 opacity-30" />
          Belum ada material yang dikeluarkan
        </div>
      ) : (
        <AnimatePresence>
          {issues.map((issue, idx) => (
            <motion.div
              key={issue.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ delay: idx * 0.04 }}
              className="flex items-center justify-between rounded-lg border border-foreground/[0.08] bg-foreground/[0.03] px-3 py-2.5"
            >
              <div className="space-y-0.5 flex-1 min-w-0">
                <div className="text-sm font-semibold text-foreground/90">{issue.material_name}</div>
                <div className="text-[10px] text-foreground/40">
                  <span className="font-mono">{issue.material_code}</span>
                  {' · '}{issue.location_name}
                  {' · '}{new Date(issue.issued_at).toLocaleDateString('id-ID', {day:'2-digit',month:'short',year:'numeric'})}
                  {' · '}{issue.issued_by}
                </div>
                {issue.notes && <div className="text-[10px] text-foreground/40 italic">{issue.notes}</div>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <div className="text-right">
                  <div className="text-sm font-bold text-cyan-600 dark:text-cyan-400">{issue.qty} {issue.unit}</div>
                  <div className="text-[10px] text-foreground/35">Sisa: {issue.stock_after?.toFixed(2)}</div>
                </div>
                <Button
                  size="icon" variant="ghost"
                  className="w-7 h-7 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/15"
                  onClick={() => cancelIssue(issue.id)}
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      )}

      {/* Issue Form Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Package className="w-4 h-4" /> Issue Material ke Order
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="text-xs text-foreground/50 bg-foreground/5 p-2 rounded">
              Order: <strong>{order?.order_code}</strong> · {order?.product_name} · {order?.qty_ordered} pcs
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Material</Label>
              <Select value={form.material_id} onValueChange={v => handleFieldChange('material_id', v)}>
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Pilih material..." />
                </SelectTrigger>
                <SelectContent>
                  {materials.map(m => (
                    <SelectItem key={m.id} value={m.id} className="text-xs">
                      [{m.code}] {m.name} ({m.unit})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Lokasi Warehouse</Label>
              <Select value={form.location_id} onValueChange={v => handleFieldChange('location_id', v)}>
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Pilih lokasi..." />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(l => (
                    <SelectItem key={l.id} value={l.id} className="text-xs">
                      {l.code ? `${l.code} · ${l.name}` : l.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Stock info — total kanonik (lintas lokasi) + rincian di lokasi terpilih */}
            {stockInfo && (
              <div className={`flex flex-col gap-1 text-xs p-2 rounded border ${
                (stockInfo.qty || 0) > 0
                  ? 'bg-green-100 dark:bg-green-500/10 border-green-500/25 text-green-600 dark:text-green-300'
                  : 'bg-red-100 dark:bg-red-500/10 border-red-500/25 text-red-600 dark:text-red-300'
              }`}>
                <div className="flex items-center gap-2">
                  {(stockInfo.qty || 0) > 0
                    ? <CheckCircle2 className="w-3 h-3" />
                    : <AlertTriangle className="w-3 h-3" />}
                  Stok tersedia (total): <strong>{(stockInfo.qty || 0).toLocaleString('id-ID')} {stockInfo.unit || ''}</strong>
                </div>
                {stockInfo.has_location && (
                  <div className="text-[10px] opacity-80 pl-5">
                    Di lokasi terpilih: <strong>{(stockInfo.loc_qty ?? 0).toLocaleString('id-ID')} {stockInfo.unit || ''}</strong>
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Qty</Label>
                <Input
                  type="number" min="0.01" step="0.01" placeholder="0"
                  value={form.qty}
                  onChange={e => handleFieldChange('qty', e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Satuan</Label>
                <Select value={form.unit} onValueChange={v => handleFieldChange('unit', v)}>
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {['meter','yard','kg','lembar','roll','pcs'].map(u => (
                      <SelectItem key={u} value={u} className="text-xs">{u}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Catatan (opsional)</Label>
              <Input
                placeholder="Keterangan tambahan"
                value={form.notes}
                onChange={e => handleFieldChange('notes', e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)} disabled={saving}>Batal</Button>
            <Button onClick={submit} disabled={saving}>
              {saving ? <><Loader2 className="w-3.5 h-3.5 animate-spin mr-2" />Memproses...</> : 'Issue Material'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
