/**
 * Fulfillment Module — Phase 6: Online Order Bridge
 * Marketing Orders → Inventory FG Management
 * 
 * Flow:
 * 1. Queue: List orders pending fulfillment
 * 2. Allocate: Pilih FG stock dari inventory (manual select)
 * 3. Pick: Mark order sedang diambil dari gudang
 * 4. Pack: Konfirmasi packing selesai
 * 5. Dispatch: Kirim + reduce stock + post COGS to GL
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  Package, Truck, CheckCircle2, AlertCircle, Search, Plus, X, 
  ArrowRight, PackageCheck, PackageOpen, Send, Loader2, RefreshCw,
  BarChart3, Clock, ShoppingBag, FileText
} from 'lucide-react';
import OnwardCTA from './OnwardCTA';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const FULFILLMENT_STATUS = {
  pending_fulfillment: { label: 'Pending', color: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-400/30', icon: Clock },
  allocated: { label: 'Allocated', color: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-400/30', icon: PackageCheck },
  picking: { label: 'Picking', color: 'bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-400 dark:border-violet-400/30', icon: PackageOpen },
  packed_ready: { label: 'Packed', color: 'bg-cyan-100 dark:bg-cyan-500/15 text-cyan-600 dark:text-cyan-300 border-cyan-400 dark:border-cyan-400/30', icon: Package },
  awaiting_scanout: { label: 'Menunggu Scan-Out', color: 'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-300 border-orange-400 dark:border-orange-400/30', icon: Truck },
  dispatched: { label: 'Dispatched', color: 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border-green-400 dark:border-green-400/30', icon: Send },
  delivered: { label: 'Delivered', color: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-400/30', icon: CheckCircle2 },
};

function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtCurrency(v) { return `Rp ${fmtNum(v)}`; }

// ─── ALLOCATE INVENTORY DIALOG ─────────────────────────────────────────────────
function AllocateInventoryDialog({ order, onClose, onSuccess, headers }) {
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [inventory, setInventory] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);

  const fetchInventory = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/fulfillment/inventory/available?search=${searchQuery}&limit=50`, { headers });
      if (r.ok) {
        const data = await r.json();
        setInventory(data.items || []);
      }
    } catch (e) {
      toast.error('Gagal memuat inventory');
    } finally {
      setLoading(false);
    }
  }, [searchQuery, headers]);

  useEffect(() => {
    const timer = setTimeout(fetchInventory, 300);
    return () => clearTimeout(timer);
  }, [fetchInventory]);

  const handleAddItem = (item) => {
    const exists = selectedItems.find(i => i.material_id === item.material_id);
    if (exists) {
      toast.error('Item sudah dipilih');
      return;
    }
    setSelectedItems([...selectedItems, {
      material_id: item.material_id,
      sku_code: item.material_code || '',
      material_name: item.material_name,
      qty_allocated: 1,
      location_id: item.location || '',
      available_qty: item.available_quantity
    }]);
  };

  const handleRemoveItem = (materialId) => {
    setSelectedItems(selectedItems.filter(i => i.material_id !== materialId));
  };

  const handleQtyChange = (materialId, qty) => {
    setSelectedItems(selectedItems.map(i => 
      i.material_id === materialId ? { ...i, qty_allocated: parseInt(qty) || 0 } : i
    ));
  };

  const handleSubmit = async () => {
    if (selectedItems.length === 0) {
      toast.error('Pilih minimal 1 item');
      return;
    }
    
    const invalid = selectedItems.find(i => i.qty_allocated <= 0 || i.qty_allocated > i.available_qty);
    if (invalid) {
      toast.error(`Qty tidak valid untuk ${invalid.material_name}`);
      return;
    }

    setLoading(true);
    try {
      const r = await fetch(`${API}/api/fulfillment/orders/${order.id}/allocate`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ items: selectedItems })
      });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(err.detail || 'Gagal allocate');
      }
      toast.success('Stock berhasil dialokasikan');
      onSuccess();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto bg-card border-foreground/10">
      <DialogHeader>
        <DialogTitle>Allocate Inventory — Order {order.order_id}</DialogTitle>
        <DialogDescription className="text-muted-foreground">
          Pilih FG stock yang akan digunakan untuk memenuhi order ini
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input 
            value={searchQuery} 
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Cari material..."
            className="pl-10 bg-foreground/5 border-foreground/10"
          />
        </div>

        {/* Available Inventory */}
        <div className="border border-foreground/10 rounded-lg p-4 space-y-2 max-h-64 overflow-y-auto bg-foreground/[0.03]">
          <div className="text-xs font-semibold text-foreground/70 mb-2">Stock Tersedia</div>
          {loading && <div className="text-center py-4 text-muted-foreground">Memuat...</div>}
          {!loading && inventory.length === 0 && (
            <div className="text-center py-4 text-muted-foreground/60">Tidak ada stock tersedia</div>
          )}
          {!loading && inventory.map(item => (
            <div key={item.material_id} className="flex items-center justify-between p-2 bg-foreground/5 rounded border border-foreground/5 hover:bg-foreground/[0.08] transition">
              <div className="flex-1">
                <div className="text-sm font-medium text-foreground">{item.material_name}</div>
                <div className="text-xs text-muted-foreground">
                  {item.material_code} • Stock: {fmtNum(item.available_quantity)} {item.unit}
                </div>
              </div>
              <Button 
                size="sm" 
                onClick={() => handleAddItem(item)}
                className="bg-blue-600 hover:bg-blue-500"
              >
                <Plus className="w-3 h-3 mr-1" /> Pilih
              </Button>
            </div>
          ))}
        </div>

        {/* Selected Items */}
        <div className="border border-blue-400 dark:border-blue-400/30 rounded-lg p-4 space-y-2 bg-blue-100 dark:bg-blue-500/5">
          <div className="text-xs font-semibold text-blue-600 dark:text-blue-300 mb-2">Item Dipilih ({selectedItems.length})</div>
          {selectedItems.length === 0 && (
            <div className="text-center py-4 text-muted-foreground/60 text-sm">Belum ada item dipilih</div>
          )}
          {selectedItems.map(item => (
            <div key={item.material_id} className="flex items-center gap-3 p-3 bg-foreground/[0.08] rounded border border-foreground/10">
              <div className="flex-1">
                <div className="text-sm font-medium text-foreground">{item.material_name}</div>
                <div className="text-xs text-muted-foreground">{item.sku_code}</div>
              </div>
              <div className="flex items-center gap-2">
                <Input 
                  type="number" 
                  value={item.qty_allocated}
                  onChange={e => handleQtyChange(item.material_id, e.target.value)}
                  className="w-20 text-center bg-foreground/10 border-foreground/20"
                  min={1}
                  max={item.available_qty}
                />
                <span className="text-xs text-muted-foreground">/ {item.available_qty}</span>
                <Button 
                  size="sm" 
                  variant="ghost" 
                  onClick={() => handleRemoveItem(item.material_id)}
                  className="text-red-700 dark:text-red-400 hover:text-red-600 dark:text-red-300"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button 
          onClick={handleSubmit} 
          disabled={loading || selectedItems.length === 0}
          className="bg-blue-600 hover:bg-blue-500"
        >
          {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          Allocate {selectedItems.length > 0 && `(${selectedItems.length} items)`}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

// ─── DISPATCH DIALOG ───────────────────────────────────────────────────────────
function DispatchDialog({ order, onClose, onSuccess, headers }) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    tracking_number: '',
    courier: order.courier || '',
    notes: ''
  });

  const handleSubmit = async () => {
    if (!form.tracking_number) {
      toast.error('Tracking number wajib diisi');
      return;
    }

    setLoading(true);
    try {
      const r = await fetch(`${API}/api/fulfillment/orders/${order.id}/dispatch`, {
        method: 'POST',
        headers,
        body: JSON.stringify(form)
      });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(err.detail || 'Gagal dispatch');
      }
      const data = await r.json();
      toast.success(data.message || 'Order masuk antrian Scan-Out gudang');
      onSuccess();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <DialogContent className="max-w-lg bg-card border-foreground/10">
      <DialogHeader>
        <DialogTitle>Dispatch Order — {order.order_id}</DialogTitle>
        <DialogDescription className="text-muted-foreground">
          Konfirmasi pengiriman dan input tracking number
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4">
        <div className="bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20 rounded-lg p-3 text-sm">
          <div className="text-blue-600 dark:text-blue-300 font-semibold mb-2">Order Summary</div>
          <div className="space-y-1 text-xs text-foreground/70">
            <div>Customer: {order.customer_name}</div>
            <div>City: {order.city}</div>
            <div>Items: {order.fulfillment_items?.length || 0} allocated</div>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Tracking Number *</Label>
          <Input 
            value={form.tracking_number}
            onChange={e => setForm(f => ({ ...f, tracking_number: e.target.value }))}
            placeholder="JNE123456789"
            className="bg-foreground/5 border-foreground/10"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Kurir</Label>
          <Input 
            value={form.courier}
            onChange={e => setForm(f => ({ ...f, courier: e.target.value }))}
            placeholder="J&T Express"
            className="bg-foreground/5 border-foreground/10"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Catatan</Label>
          <Textarea 
            value={form.notes}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            rows={2}
            className="bg-foreground/5 border-foreground/10 resize-none"
          />
        </div>

        <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-400/20 rounded p-3 text-xs text-amber-600 dark:text-amber-300">
          ⚠️ Setelah dispatch: order masuk antrian <b>Scan-Out</b> di Gudang (WMS). Stok FG berkurang &amp; COGS di-posting ke Finance GL <b>saat gudang melakukan Scan-Out</b>.
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onClose} className="text-muted-foreground">Batal</Button>
        <Button 
          onClick={handleSubmit} 
          disabled={loading}
          className="bg-green-600 hover:bg-green-500"
        >
          {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          <Send className="w-4 h-4 mr-2" />
          Dispatch Order
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

// ─── ORDER DETAIL CARD ─────────────────────────────────────────────────────────
function OrderCard({ order, onAction, onAllocate, onDispatch }) {
  const statusInfo = FULFILLMENT_STATUS[order.fulfillment_status] || FULFILLMENT_STATUS.pending_fulfillment;
  const StatusIcon = statusInfo.icon;

  return (
    <GlassCard className="p-4 hover:bg-foreground/[0.08] transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-mono font-bold text-foreground">{order.order_id}</span>
            <Badge className={`text-[10px] px-2 py-0.5 ${statusInfo.color}`}>
              <StatusIcon className="w-3 h-3 mr-1" />
              {statusInfo.label}
            </Badge>
            {order.cogs_posted && (
              <Badge className="text-[10px] px-2 py-0.5 bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300">
                ✓ COGS Posted
              </Badge>
            )}
          </div>
          <div className="text-sm text-foreground font-medium">{order.product_name}</div>
          <div className="text-xs text-muted-foreground mt-1">
            {order.customer_name} • {order.city} • Qty: {order.quantity}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col gap-2">
          {order.fulfillment_status === 'pending_fulfillment' && (
            <Button size="sm" onClick={() => onAllocate(order)} className="bg-blue-600 hover:bg-blue-500">
              <Plus className="w-3 h-3 mr-1" /> Allocate
            </Button>
          )}
          {order.fulfillment_status === 'allocated' && (
            <Button size="sm" onClick={() => onAction(order, 'pick')} className="bg-violet-600 hover:bg-violet-500">
              <ArrowRight className="w-3 h-3 mr-1" /> Pick
            </Button>
          )}
          {order.fulfillment_status === 'picking' && (
            <Button size="sm" onClick={() => onAction(order, 'pack')} className="bg-cyan-600 hover:bg-cyan-500">
              <PackageCheck className="w-3 h-3 mr-1" /> Pack
            </Button>
          )}
          {order.fulfillment_status === 'packed_ready' && (
            <Button size="sm" onClick={() => onDispatch(order)} className="bg-green-600 hover:bg-green-500">
              <Send className="w-3 h-3 mr-1" /> Dispatch
            </Button>
          )}
          {order.fulfillment_status === 'awaiting_scanout' && (
            <div data-testid="awaiting-scanout-hint" className="flex items-center gap-1 text-[11px] text-orange-600 dark:text-orange-300 max-w-[130px] text-right">
              <Truck className="w-3 h-3 shrink-0" /> Menunggu Scan-Out gudang (WMS)
            </div>
          )}
        </div>
      </div>

      {/* Fulfillment Items */}
      {order.fulfillment_items && order.fulfillment_items.length > 0 && (
        <div className="border-t border-foreground/10 pt-2 mt-2">
          <div className="text-xs text-muted-foreground mb-1">Allocated Items:</div>
          <div className="space-y-1">
            {order.fulfillment_items.map((item, idx) => (
              <div key={idx} className="text-xs bg-foreground/5 rounded px-2 py-1 flex justify-between">
                <span className="text-foreground/70">{item.material_name}</span>
                <span className="text-foreground font-mono">{item.qty_allocated} pcs</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {order.tracking_number && (
        <div className="border-t border-foreground/10 pt-2 mt-2 text-xs text-muted-foreground">
          📦 Tracking: <span className="text-foreground font-mono">{order.tracking_number}</span>
        </div>
      )}
    </GlassCard>
  );
}

// ─── MAIN MODULE ───────────────────────────────────────────────────────────────
export default function FulfillmentModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }), [token]);

  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({});
  const [orders, setOrders] = useState([]);
  const [tab, setTab] = useState('pending');
  const [allocateDialog, setAllocateDialog] = useState(null);
  const [dispatchDialog, setDispatchDialog] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/fulfillment/summary`, { headers });
      if (r.ok) setStats(await r.json());
    } catch (e) {
      console.error('Failed to fetch stats', e);
    }
  }, [headers]);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const statusMap = {
        pending: 'pending_fulfillment',
        allocated: 'allocated',
        picking: 'picking',
        packed: 'packed_ready',
        dispatched: 'dispatched'
      };
      const status = statusMap[tab] || '';
      const r = await fetch(`${API}/api/fulfillment/queue?status=${status}&limit=50`, { headers });
      if (r.ok) {
        const data = await r.json();
        setOrders(data.orders || []);
      }
    } catch (e) {
      toast.error('Gagal memuat orders');
    } finally {
      setLoading(false);
    }
  }, [tab, headers]);

  useEffect(() => {
    fetchStats();
    fetchOrders();
  }, [fetchStats, fetchOrders]);

  const handleAction = async (order, action) => {
    const actionMap = {
      pick: { endpoint: 'pick', message: 'Picking dimulai' },
      pack: { endpoint: 'pack', message: 'Packing selesai' }
    };
    const { endpoint, message } = actionMap[action];

    try {
      const r = await fetch(`${API}/api/fulfillment/orders/${order.id}/${endpoint}`, {
        method: 'POST',
        headers
      });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(err.detail || 'Gagal');
      }
      toast.success(message);
      fetchOrders();
      fetchStats();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const handleRefresh = () => {
    fetchStats();
    fetchOrders();
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center">
              <Package className="w-5 h-5 text-foreground" />
            </div>
            Fulfillment Management
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Bridge: Marketing Orders → Inventory FG</p>
        </div>
        <Button onClick={handleRefresh} variant="outline" size="sm" className="border-foreground/10">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* RC-FLOW-UX — onward CTA: fulfillment → surat jalan + after-sales retur */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Lanjutkan Alur Pengiriman"
        actions={[
          { module: 'wms-delivery-notes', label: 'Buat Surat Jalan', icon: FileText, primary: true, hint: 'Order dikirim → dokumen Surat Jalan' },
          { module: 'marketing-returns', label: 'Retur & Refund', icon: Truck, hint: 'Jika ada retur setelah kirim (Alur 8)' },
        ]}
      />

      {/* Stats */}
      <div className="grid grid-cols-5 gap-4">
        {[
          { label: 'Pending', value: stats.pending_fulfillment || 0, icon: Clock, color: 'text-amber-600 dark:text-amber-300' },
          { label: 'Allocated', value: stats.allocated || 0, icon: PackageCheck, color: 'text-blue-600 dark:text-blue-300' },
          { label: 'Picking', value: stats.picking || 0, icon: PackageOpen, color: 'text-violet-600 dark:text-violet-300' },
          { label: 'Packed', value: stats.packed_ready || 0, icon: Package, color: 'text-cyan-600 dark:text-cyan-300' },
          { label: 'Dispatched Today', value: stats.dispatched_today || 0, icon: Send, color: 'text-green-600 dark:text-green-300' },
        ].map(s => (
          <GlassCard key={s.label} className="p-4">
            <div className="flex items-center justify-between mb-2">
              <s.icon className={`w-5 h-5 ${s.color}`} />
            </div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Orders Queue */}
      <GlassCard className="p-6">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-foreground/5 mb-4">
            <TabsTrigger value="pending">Pending</TabsTrigger>
            <TabsTrigger value="allocated">Allocated</TabsTrigger>
            <TabsTrigger value="picking">Picking</TabsTrigger>
            <TabsTrigger value="packed">Packed</TabsTrigger>
            <TabsTrigger value="dispatched">Dispatched</TabsTrigger>
          </TabsList>
        </Tabs>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">
            <Loader2 className="w-8 h-8 animate-spin mx-auto mb-3" />
            Memuat orders...
          </div>
        ) : orders.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground/60">
            <ShoppingBag className="w-12 h-12 mx-auto opacity-20 mb-3" />
            <p>Tidak ada orders untuk status ini</p>
          </div>
        ) : (
          <div className="space-y-3">
            {orders.map(order => (
              <OrderCard 
                key={order.id} 
                order={order}
                onAction={handleAction}
                onAllocate={setAllocateDialog}
                onDispatch={setDispatchDialog}
              />
            ))}
          </div>
        )}
      </GlassCard>

      {/* Dialogs */}
      {allocateDialog && (
        <Dialog open={!!allocateDialog} onOpenChange={() => setAllocateDialog(null)}>
          <AllocateInventoryDialog 
            order={allocateDialog}
            headers={headers}
            onClose={() => setAllocateDialog(null)}
            onSuccess={() => {
              setAllocateDialog(null);
              fetchOrders();
              fetchStats();
            }}
          />
        </Dialog>
      )}

      {dispatchDialog && (
        <Dialog open={!!dispatchDialog} onOpenChange={() => setDispatchDialog(null)}>
          <DispatchDialog 
            order={dispatchDialog}
            headers={headers}
            onClose={() => setDispatchDialog(null)}
            onSuccess={() => {
              setDispatchDialog(null);
              fetchOrders();
              fetchStats();
            }}
          />
        </Dialog>
      )}
    </div>
  );
}
