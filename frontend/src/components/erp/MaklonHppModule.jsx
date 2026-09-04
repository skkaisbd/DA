import { useState, useEffect, useCallback, useMemo } from 'react';
import { Target, Plus, Trash2, RefreshCw, Calculator } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { fetchMaklonOrders } from '@/lib/maklonOrderAdapter';
import { formatRupiah } from '@/lib/format';

const CATEGORIES = [
  { value: 'material',  label: 'Material/Kain' },
  { value: 'labor',     label: 'Upah (Sewing)' },
  { value: 'overhead',  label: 'Overhead' },
  { value: 'packaging', label: 'Packaging/Aksesoris' },
  { value: 'other',     label: 'Lainnya' },
];

const fmt = formatRupiah;

export default function MaklonHppModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [orders, setOrders] = useState([]);
  const [selectedOrderId, setSelectedOrderId] = useState('');
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [components, setComponents] = useState([]);
  const [overheadPct, setOverheadPct] = useState('15');
  const [marginPct, setMarginPct] = useState('20');
  const [notes, setNotes] = useState('');
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      // P1.B cutover: read from /api/dewi/maklon/pos via adapter
      const allOrders = await fetchMaklonOrders(headers);
      setOrders(allOrders.filter(o => !['draft','cancelled'].includes(o.status)));
    } catch (e) { toast.error('Gagal memuat order'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  const loadOrder = async (oid) => {
    setSelectedOrderId(oid);
    const o = orders.find(x => x.id === oid);
    setSelectedOrder(o);
    setResult(null);
    try {
      const r = await fetch(`/api/dewi/maklon/hpp/${oid}`, { headers });
      if (r.ok) {
        const d = await r.json();
        setComponents(d.components || []);
        setOverheadPct(String(d.overhead_pct || 15));
        setMarginPct(String(d.profit_margin_pct || 20));
        setNotes(d.notes || '');
        setResult(d);
      } else {
        setComponents([]);
        setNotes('');
      }
    } catch (e) { /* no-op */ }
  };

  const addComponent = () => setComponents([...components, { name: '', category: 'material', qty: 1, unit: 'pcs', unit_cost: 0 }]);
  const updateComp = (i, k, v) => {
    const next = [...components];
    next[i] = { ...next[i], [k]: v };
    setComponents(next);
  };
  const removeComp = (i) => setComponents(components.filter((_, idx) => idx !== i));

  const save = async () => {
    if (!selectedOrderId) { toast.error('Pilih order dulu'); return; }
    if (components.length === 0) { toast.error('Tambahkan minimal 1 komponen biaya'); return; }
    setSaving(true);
    const payload = {
      order_id: selectedOrderId,
      components: components.map(c => ({
        ...c,
        qty: Number(c.qty) || 0,
        unit_cost: Number(c.unit_cost) || 0,
      })),
      overhead_pct: Number(overheadPct) || 0,
      profit_margin_pct: Number(marginPct) || 0,
      notes,
    };
    const r = await fetch('/api/dewi/maklon/hpp', { method: 'POST', headers, body: JSON.stringify(payload) });
    setSaving(false);
    if (r.ok) {
      toast.success('HPP tersimpan');
      loadOrder(selectedOrderId);
    } else {
      toast.error((await r.json()).detail || 'Gagal');
    }
  };

  // Live preview
  const directCost = components.reduce((sum, c) => sum + (Number(c.qty) || 0) * (Number(c.unit_cost) || 0), 0);
  const overheadAmt = directCost * (Number(overheadPct) || 0) / 100;
  const totalHpp = directCost + overheadAmt;
  const qty = Number(selectedOrder?.qty_ordered) || 1;
  const hppPerPcs = qty > 0 ? totalHpp / qty : 0;
  const suggestedPrice = hppPerPcs * (1 + (Number(marginPct) || 0) / 100);
  const actualPrice = Number(selectedOrder?.price_per_pcs) || 0;
  const actualMarginPct = hppPerPcs > 0 ? ((actualPrice - hppPerPcs) / hppPerPcs) * 100 : 0;

  return (
    <div className="p-6 space-y-6" data-testid="maklon-hpp">
      <PageHeader
        title="HPP Jasa Jahit Maklon"
        subtitle="Hitung harga pokok produksi + margin untuk setiap order maklon"
        icon={Target}
        actions={
          <Button size="sm" variant="outline" onClick={fetchOrders} className="gap-2" data-testid="hpp-refresh-btn">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </Button>
        }
      />

      <GlassCard className="p-5">
        <Label className="mb-2 block">Pilih Order</Label>
        <Select value={selectedOrderId} onValueChange={loadOrder}>
          <SelectTrigger className="w-full md:w-96" data-testid="hpp-order-select"><SelectValue placeholder="Pilih order..." /></SelectTrigger>
          <SelectContent>
            {orders.map(o => (
              <SelectItem key={o.id} value={o.id}>{o.order_code} — {o.product_name} ({o.qty_ordered}pcs)</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </GlassCard>

      {selectedOrder && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4">
          {/* Components editor */}
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-foreground/80">Komponen Biaya</h3>
              <Button size="sm" variant="outline" onClick={addComponent} className="gap-1" data-testid="hpp-add-component-btn">
                <Plus className="w-3.5 h-3.5" /> Tambah
              </Button>
            </div>
            {components.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada komponen</div>
            ) : (
              <div className="space-y-2">
                {components.map((c, i) => (
                  <div key={i} className="grid grid-cols-[2fr_1fr_80px_80px_1fr_120px_auto] gap-2 items-end text-xs">
                    <div>
                      {i === 0 && <Label className="text-[10px]">Nama</Label>}
                      <Input value={c.name} onChange={e => updateComp(i, 'name', e.target.value)} placeholder="Komponen" data-testid={`hpp-comp-name-${i}`} />
                    </div>
                    <div>
                      {i === 0 && <Label className="text-[10px]">Kategori</Label>}
                      <Select value={c.category} onValueChange={v => updateComp(i, 'category', v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{CATEGORIES.map(cat => <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div>
                      {i === 0 && <Label className="text-[10px]">Qty</Label>}
                      <Input type="number" value={c.qty} onChange={e => updateComp(i, 'qty', e.target.value)} />
                    </div>
                    <div>
                      {i === 0 && <Label className="text-[10px]">Unit</Label>}
                      <Input value={c.unit} onChange={e => updateComp(i, 'unit', e.target.value)} />
                    </div>
                    <div>
                      {i === 0 && <Label className="text-[10px]">Harga Satuan</Label>}
                      <Input type="number" value={c.unit_cost} onChange={e => updateComp(i, 'unit_cost', e.target.value)} />
                    </div>
                    <div className="text-right font-semibold">
                      {i === 0 && <Label className="text-[10px]">Subtotal</Label>}
                      <div>{fmt((Number(c.qty) || 0) * (Number(c.unit_cost) || 0))}</div>
                    </div>
                    <Button size="icon" variant="ghost" className="w-7 h-7 text-red-700 dark:text-red-400" onClick={() => removeComp(i)}><Trash2 className="w-3 h-3" /></Button>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-foreground/10">
              <div className="space-y-1"><Label>Overhead (%)</Label><Input type="number" value={overheadPct} onChange={e => setOverheadPct(e.target.value)} data-testid="hpp-overhead-input" /></div>
              <div className="space-y-1"><Label>Target Margin (%)</Label><Input type="number" value={marginPct} onChange={e => setMarginPct(e.target.value)} data-testid="hpp-margin-input" /></div>
              <div className="space-y-1 col-span-2"><Label>Catatan</Label><Textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} /></div>
            </div>
            <div className="mt-4 flex justify-end">
              <Button onClick={save} disabled={saving} className="gap-1.5" data-testid="hpp-save-btn">
                <Calculator className="w-3.5 h-3.5" /> {saving ? 'Menyimpan...' : 'Simpan HPP'}
              </Button>
            </div>
          </GlassCard>

          {/* Live preview */}
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground/80 mb-3">Live Calculation</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-foreground/60">Qty Order:</span><span className="font-semibold">{qty} pcs</span></div>
              <div className="flex justify-between"><span className="text-foreground/60">Biaya Langsung:</span><span>{fmt(directCost)}</span></div>
              <div className="flex justify-between"><span className="text-foreground/60">Overhead ({overheadPct}%):</span><span>{fmt(overheadAmt)}</span></div>
              <div className="flex justify-between font-semibold border-t border-foreground/10 pt-2"><span>Total HPP:</span><span>{fmt(totalHpp)}</span></div>
              <div className="flex justify-between"><span className="text-foreground/60">HPP per pcs:</span><span className="font-semibold text-primary">{fmt(hppPerPcs)}</span></div>
              <div className="border-t border-foreground/10 pt-2 mt-2" />
              <div className="flex justify-between"><span className="text-foreground/60">Harga Jual Aktual:</span><span>{fmt(actualPrice)}</span></div>
              <div className="flex justify-between"><span className="text-foreground/60">Harga Saran ({marginPct}%):</span><span className="font-semibold text-green-700 dark:text-green-400">{fmt(suggestedPrice)}</span></div>
              <div className={`flex justify-between pt-2 border-t border-foreground/10 ${actualMarginPct < 0 ? 'text-red-700 dark:text-red-400' : actualMarginPct < 10 ? 'text-amber-700 dark:text-amber-400' : 'text-green-700 dark:text-green-400'}`}>
                <span>Margin Aktual:</span><span className="font-bold">{actualMarginPct.toFixed(2)}%</span>
              </div>
            </div>
            {actualMarginPct < 5 && selectedOrder && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-3 bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-400/30 rounded p-2 text-xs text-red-600 dark:text-red-300">
                ⚠ Margin di bawah 5%. Pertimbangkan renegosiasi harga atau efisiensi biaya.
              </motion.div>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  );
}
