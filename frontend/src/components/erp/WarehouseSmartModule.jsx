import { useState, useEffect, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { AlertTriangle, RefreshCw, Package, Warehouse, RotateCcw, CheckCircle2, XCircle, Undo2, RotateCw, Brain, ShoppingCart } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const SEVERITY_STYLE = {
  critical: 'border-red-200 bg-red-50 text-red-700',
  warning:  'border-yellow-200 bg-yellow-50 text-yellow-700',
};

function AlertsTab() {
  const { toast } = useToast();
  const [alerts, setAlerts] = useState([]);
  const [meta, setMeta] = useState({});
  const [loading, setLoading] = useState(true);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/warehouse/alerts?threshold=90');
      setAlerts(res.data || []);
      setMeta(res.metadata || {});
    } catch (err) {
      toast({ title: 'Gagal memuat alert', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2">
          {meta.critical > 0 && <Badge variant="destructive">{meta.critical} Kritis</Badge>}
          {meta.warning > 0 && <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200">{meta.warning} Peringatan</Badge>}
          {meta.total_alerts === 0 && !loading && <Badge variant="outline" className="text-green-600">✅ Tidak ada alert</Badge>}
        </div>
        <div className="flex items-center gap-2">
          {/* SESI #33 — alert stok tidak lagi jalan buntu: dari sini langsung ke
              Daftar Belanja Mingguan yang mengubah kekurangan jadi usul beli + PR. */}
          <Button size="sm" variant="outline"
            onClick={() => {
              if (window.location.hash === '#wh-shopping-list') window.location.hash = '';
              window.location.hash = '#wh-shopping-list';
            }}
            data-testid="wh-smart-goto-shopping">
            <ShoppingCart className="h-3.5 w-3.5 mr-1.5" />Belanja Mingguan
          </Button>
          <Button size="sm" variant="outline" onClick={loadAlerts} disabled={loading} data-testid="wh-smart-alerts-refresh">
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
          </Button>
        </div>
      </div>

      {/* W3 — kejujuran layar: "tidak ada alert" TIDAK sama dengan "stok aman"
          kalau ambangnya belum pernah diisi. Ini akar keluhan pemilik: menu ini
          selalu sunyi karena 333 dari 333 material tidak punya ambang. */}
      {!loading && meta.materials_missing_threshold > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-300/40 bg-amber-50 dark:bg-amber-400/10 px-4 py-3"
          data-testid="wh-smart-threshold-notice">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-700 dark:text-amber-300">
            <strong>{meta.materials_missing_threshold} dari {meta.materials_total} material belum punya ambang stok</strong>
            {meta.materials_with_threshold === 0
              ? ' — selama ambangnya kosong, alert stok TIDAK akan pernah berbunyi walau stok habis.'
              : ' — material tersebut tidak akan pernah memicu alert.'}
            <button
              onClick={() => {
                // Kontrak tab hub yang sudah ada (`hub_tab_<moduleId>`) supaya
                // mendarat LANGSUNG di tab Ambang Stok. Hash dikosongkan dulu
                // bila sudah sama, karena tanpa perubahan hash tidak ada
                // `hashchange` ⇒ tombolnya akan terasa "mati".
                try { sessionStorage.setItem('hub_tab_wh-master', 'thresholds'); } catch (e) { /* noop */ }
                if (window.location.hash === '#wh-master=thresholds') window.location.hash = '';
                window.location.hash = '#wh-master=thresholds';
              }}
              className="ml-1 underline font-medium"
              data-testid="wh-smart-goto-thresholds">
              Isi di Master Item → Ambang Stok
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8"><RefreshCw className="h-6 w-6 animate-spin mx-auto" /></div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <CheckCircle2 className="h-10 w-10 text-green-500 mx-auto mb-2" />
          <p className="text-sm font-medium">
            {meta.materials_with_threshold === 0 ? 'Belum ada yang bisa dipantau' : 'Semua sistem normal'}
          </p>
          <p className="text-xs mt-1">
            {meta.materials_with_threshold === 0
              ? 'Isi ambang stok dulu di Master Item → Ambang Stok, baru alert bisa berbunyi.'
              : `Tidak ada rak melebihi 90%; ${meta.materials_with_threshold} material dipantau dan semuanya di atas ambang`}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <div key={i} className={`p-3 rounded-lg border ${SEVERITY_STYLE[alert.severity]} flex items-start gap-3`}>
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium">{alert.message}</p>
                {alert.type === 'rack_occupancy' && (
                  <div className="mt-1">
                    <div className="h-1.5 bg-foreground/50 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-current rounded-full transition-all"
                        style={{ width: `${alert.occupancy_pct}%` }}
                      />
                    </div>
                    <p className="text-xs mt-0.5">{alert.occupied} / {alert.total} slot • {alert.occupancy_pct}%</p>
                  </div>
                )}
                {alert.type === 'low_stock' && (
                  <p className="text-xs mt-0.5">
                    Stok: {alert.current_qty} {alert.unit} | Ambang: {alert.alert_at ?? alert.reorder_point} {alert.unit}
                    {alert.min_stock_qty > 0 && <> (min {alert.min_stock_qty})</>}
                    {alert.reorder_point > 0 && <> · pesan ulang {alert.reorder_point}</>}
                    {alert.shortage > 0 && <> — kurang <strong>{alert.shortage} {alert.unit}</strong></>}
                  </p>
                )}
              </div>
              <Badge variant="outline" className="text-[10px] flex-shrink-0">
                {alert.type === 'rack_occupancy' ? 'Rak' : 'Stok'}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SmartReorderTab() {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState({});
  const [saving, setSaving] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/warehouse/smart-reorder?limit=100');
      setItems(res.data || []);
      setMeta(res.metadata || {});
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const applySmartRP = async (item) => {
    setSaving(item.material_id);
    try {
      await apiFetch(`/warehouse/smart-reorder/${item.material_id}`, {
        method: 'PUT',
        body: { reorder_point: item.smart_reorder_point },
      });
      toast({ title: `Reorder point ${item.name} diperbarui ke ${item.smart_reorder_point}` });
      loadData();
    } catch (err) {
      toast({ title: 'Gagal update', description: err.message, variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">{meta.needs_update || 0} material perlu update reorder point</p>
        <Button size="sm" variant="outline" onClick={loadData} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
        </Button>
      </div>
      {loading ? (
        <div className="text-center py-8"><RefreshCw className="h-6 w-6 animate-spin mx-auto" /></div>
      ) : items.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground text-sm">Belum ada material terdaftar</div>
      ) : (
        <div className="space-y-2">
          {items.map((item, i) => (
            <div key={i} className="p-3 rounded-lg border border-border">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-sm">{item.name}</p>
                    <Badge variant="outline" className="text-[10px]">{item.sku}</Badge>
                    {item.status === 'low' && <Badge variant="destructive" className="text-[10px]">Stok Rendah</Badge>}
                    {item.needs_update && <Badge className="text-[10px] bg-blue-100 text-blue-700 border-blue-200">Update RP</Badge>}
                  </div>
                  <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
                    <span>Stok: {item.current_qty} {item.unit}</span>
                    <span>RP Saat Ini: {item.current_reorder_point}</span>
                    {item.smart_reorder_point > 0 && (
                      <span className="text-blue-600 font-medium">Smart RP: {item.smart_reorder_point}</span>
                    )}
                    <span>Avg Harian: {item.avg_daily_consumption}</span>
                  </div>
                </div>
                {item.needs_update && item.smart_reorder_point > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => applySmartRP(item)}
                    disabled={saving === item.material_id}
                  >
                    {saving === item.material_id
                      ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      : <><Brain className="h-3.5 w-3.5 mr-1" />Apply</>
                    }
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UndoStockTab() {
  const { toast } = useToast();
  const [data, setData] = useState({ undoable: [], soft_deleted: [] });
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/warehouse/stock-adjustments/undo-history?days=7');
      setData(res.data || { undoable: [], soft_deleted: [] });
    } catch {
      setData({ undoable: [], soft_deleted: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const doUndo = async (id) => {
    setProcessing(id);
    try {
      await apiFetch(`/warehouse/stock-adjustments/${id}/undo`, { method: 'POST' });
      toast({ title: 'Adjustment berhasil di-undo' });
      loadData();
    } catch (err) {
      toast({ title: 'Gagal undo', description: err.message, variant: 'destructive' });
    } finally {
      setProcessing(null);
    }
  };

  const doRestore = async (id) => {
    setProcessing(id);
    try {
      await apiFetch(`/warehouse/stock-adjustments/${id}/restore`, { method: 'POST' });
      toast({ title: 'Adjustment berhasil di-restore' });
      loadData();
    } catch (err) {
      toast({ title: 'Gagal restore', description: err.message, variant: 'destructive' });
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">Adjustment dalam 7 hari terakhir yang bisa di-undo</p>
        <Button size="sm" variant="outline" onClick={loadData}><RefreshCw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </div>
      {loading ? (
        <div className="text-center py-8"><RefreshCw className="h-6 w-6 animate-spin mx-auto" /></div>
      ) : (
        <>
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Dapat Di-Undo ({data.undoable?.length})</p>
            {data.undoable?.length === 0 ? (
              <div className="text-center py-6 text-sm text-muted-foreground border-2 border-dashed border-border rounded-lg">
                Tidak ada adjustment yang bisa di-undo
              </div>
            ) : (
              <div className="space-y-2">
                {data.undoable.map((m, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-border text-sm">
                    <Package className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1">
                      <p className="font-medium">{m.sku} — {m.movement_type}</p>
                      <p className="text-xs text-muted-foreground">
                        Qty: {m.qty} {m.unit} · {m.created_at ? new Date(m.created_at).toLocaleString('id-ID') : '-'}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => doUndo(m.id)} disabled={processing === m.id}>
                      {processing === m.id ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <><Undo2 className="h-3.5 w-3.5 mr-1" />Undo</>}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Soft-Deleted (bisa Restore) ({data.soft_deleted?.length})</p>
            {data.soft_deleted?.length === 0 ? (
              <div className="text-center py-4 text-sm text-muted-foreground">Tidak ada item soft-deleted</div>
            ) : (
              <div className="space-y-2">
                {data.soft_deleted.map((m, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-border text-sm opacity-60">
                    <XCircle className="h-4 w-4 text-red-700 dark:text-red-400 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="font-medium line-through">{m.sku} — {m.movement_type}</p>
                      <p className="text-xs text-muted-foreground">Di-undo oleh {m.deleted_by || '-'}</p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => doRestore(m.id)} disabled={processing === m.id}>
                      {processing === m.id ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <><RotateCw className="h-3.5 w-3.5 mr-1" />Restore</>}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function WarehouseSmartModule() {
  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-xl font-bold flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-teal-500 to-green-600 flex items-center justify-center">
            <Warehouse className="h-4 w-4 text-foreground" />
          </div>
          Smart Warehouse
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">Alert gudang, smart reorder point & undo stock adjustment</p>
      </div>
      <Tabs defaultValue="alerts">
        <TabsList className="h-9">
          <TabsTrigger value="alerts" className="text-xs" data-testid="wh-smart-tab-alerts"><AlertTriangle className="h-3.5 w-3.5 mr-1.5" />Alert Gudang</TabsTrigger>
          <TabsTrigger value="reorder" className="text-xs" data-testid="wh-smart-tab-reorder"><Package className="h-3.5 w-3.5 mr-1.5" />Smart Reorder</TabsTrigger>
          <TabsTrigger value="undo" className="text-xs" data-testid="wh-smart-tab-undo"><Undo2 className="h-3.5 w-3.5 mr-1.5" />Undo Stock</TabsTrigger>
        </TabsList>
        <TabsContent value="alerts" className="mt-4"><AlertsTab /></TabsContent>
        <TabsContent value="reorder" className="mt-4"><SmartReorderTab /></TabsContent>
        <TabsContent value="undo" className="mt-4"><UndoStockTab /></TabsContent>
      </Tabs>
    </div>
  );
}
