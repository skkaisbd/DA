import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Plus, RefreshCw, Truck, FileText, Send, PackageCheck, XCircle, Trash2,
  ExternalLink, ClipboardList, Calendar,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { PageHeader, StatTile, StatusBadge } from './moduleAtoms';
import { DataTable } from './DataTableV2';
import { formatRupiah } from '@/lib/format';

// ─────────────────────────────────────────────────────────────────────────────
// PT Rahaza ERP — Shipments / Surat Jalan (Phase 14.3)
// Modul untuk mengelola pengiriman barang jadi dari Order + WO ke pelanggan.
// Fitur: CRUD, status transition (draft → dispatched → delivered/cancelled),
//        PDF Surat Jalan, tautan ke AR Invoice otomatis.
// ─────────────────────────────────────────────────────────────────────────────

const toneForStatus = (s) => ({
  draft: 'muted',
  dispatched: 'info',
  delivered: 'success',
  cancelled: 'danger',
}[s] || 'default');

const API = '/api/rahaza';

export default function RahazaShipmentsModule({ token, onNavigate }) {
  const [shipments, setShipments] = useState([]);
  const [orders, setOrders] = useState([]);
  const [workOrders, setWorkOrders] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [shp, ord, wos, cs] = await Promise.all([
        fetch(`${API}/shipments`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${API}/orders`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${API}/work-orders`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${API}/customers`, { headers }).then((r) => r.json()).catch(() => []),
      ]);
      setShipments(Array.isArray(shp) ? shp : []);
      setOrders(Array.isArray(ord) ? ord : []);
      setWorkOrders(Array.isArray(wos) ? wos : []);
      setCustomers(Array.isArray(cs) ? cs : []);
    } catch (e) {
      toast.error('Gagal memuat data shipment');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const createShipment = async (body) => {
    const r = await fetch(`${API}/shipments`, {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      toast.error(e.detail || `Gagal membuat shipment (HTTP ${r.status})`);
      return false;
    }
    toast.success('Shipment draft berhasil dibuat');
    setCreating(false);
    fetchAll();
    return true;
  };

  const changeStatus = async (id, status, label) => {
    const r = await fetch(`${API}/shipments/${id}/status`, {
      method: 'POST', headers, body: JSON.stringify({ status }),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      toast.error(e.detail || `Gagal ${label}`);
      return;
    }
    const data = await r.json();
    if (data.auto_invoice_number) {
      toast.success(`${label} · AR draft ${data.auto_invoice_number} dibuat otomatis`);
    } else {
      toast.success(label);
    }
    fetchAll();
  };

  const deleteShipment = async (id) => {
    if (!window.confirm('Hapus shipment draft ini?')) return;
    const r = await fetch(`${API}/shipments/${id}`, { method: 'DELETE', headers });
    if (!r.ok) { toast.error('Gagal menghapus'); return; }
    toast.success('Shipment dihapus');
    fetchAll();
  };

  const openPDF = async (sid, shipmentNumber) => {
    try {
      const r = await fetch(`${API}/shipments/${sid}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) { toast.error('Gagal memuat PDF'); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const w = window.open(url, '_blank');
      if (!w) toast.info('Pop-up diblokir. Klik kanan link untuk buka manual.');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast.error('Gagal membuka PDF Surat Jalan');
    }
  };

  const openAR = () => {
    if (onNavigate) onNavigate('fin-ar-invoices');
  };

  // ── Stats ─────────────────────────────────────────────────────────────────
  const stats = useMemo(() => {
    const total = shipments.length;
    const draft = shipments.filter((s) => s.status === 'draft').length;
    const dispatched = shipments.filter((s) => s.status === 'dispatched').length;
    const delivered = shipments.filter((s) => s.status === 'delivered').length;
    return { total, draft, dispatched, delivered };
  }, [shipments]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5" data-testid="rahaza-shipments-page">
      {/* DEPRECATION BANNER (Session #11.14 — P2 Consolidation #12) */}
      <div
        className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300"
        data-testid="ship-deprecation-banner"
        role="alert"
      >
        <strong>⚠️ Modul Ini Sudah Tidak Aktif (DEPRECATED)</strong> — Pengiriman ke Customer
        kini dikelola di <em>Warehouse → Surat Jalan Customer (SSOT)</em>
        (<code>wms-delivery-notes</code>). Modul ini dipertahankan sementara untuk
        kompatibilitas data lama. Lihat <strong>FORENSIC_09 — P2 Consolidation #12</strong>.
      </div>
      <PageHeader
        icon={Truck}
        eyebrow="Portal Produksi · Sales Closure"
        title="Pengiriman (Surat Jalan)"
        subtitle="Kelola pengiriman barang jadi — draft, dispatch (auto-invoice AR), delivered, atau cancel. Cetak Surat Jalan A5 langsung dari sistem."
        actions={
          <>
            <Button
              variant="ghost"
              onClick={fetchAll}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="ship-refresh"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button
              onClick={() => setCreating(true)}
              className="h-9"
              data-testid="ship-create"
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Shipment Baru
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatTile label="Total" value={stats.total} accent="primary" />
        <StatTile label="Draft" value={stats.draft} accent="default" />
        <StatTile label="Dispatched" value={stats.dispatched} accent="info" />
        <StatTile label="Delivered" value={stats.delivered} accent="success" />
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
        </div>
      ) : (
        <DataTable
          tableId="shipments"
          rows={shipments}
          searchFields={[
            'shipment_number', 'order_number_snapshot',
            'customer_name_snapshot', 'driver_name', 'vehicle_number', 'status',
          ]}
          filters={[
            { key: 'status', label: 'Status', type: 'select', options: [
              { value: 'draft', label: 'Draft' },
              { value: 'dispatched', label: 'Dispatched' },
              { value: 'delivered', label: 'Delivered' },
              { value: 'cancelled', label: 'Cancelled' },
            ] },
            { key: 'shipment_date', label: 'Tgl Kirim', type: 'date-range' },
          ]}
          columns={[
            { key: 'shipment_number', label: 'Surat Jalan #', sortable: true,
              render: (_, v) => <span className="font-mono text-xs">{v}</span> },
            { key: 'shipment_date', label: 'Tanggal', sortable: true,
              render: (_, v) => <span className="text-xs text-foreground/70">{v || '-'}</span> },
            { key: 'order_number_snapshot', label: 'Order', sortable: true,
              render: (_, v) => <span className="font-mono text-xs">{v || '-'}</span> },
            { key: 'customer_name_snapshot', label: 'Pelanggan', sortable: true,
              render: (_, v) => <span>{v || '-'}</span> },
            { key: 'total_qty', label: 'Qty', align: 'right', sortable: true,
              render: (_, v) => <span className="font-mono text-xs">{Number(v || 0).toFixed(0)} pcs</span> },
            { key: 'driver_name', label: 'Driver / Kendaraan',
              render: (r) => (
                <div className="text-[11px] text-foreground/60 leading-tight">
                  <div>{r.driver_name || '-'}</div>
                  <div className="font-mono">{r.vehicle_number || '-'}</div>
                </div>
              ) },
            { key: 'status', label: 'Status',
              render: (r) => <StatusBadge status={r.status} tone={toneForStatus(r.status)} /> },
            { key: 'auto_invoice_number', label: 'AR Invoice',
              render: (r) => r.auto_invoice_number ? (
                <button
                  onClick={openAR}
                  className="inline-flex items-center gap-1 text-[11px] font-mono text-[hsl(var(--primary))] hover:underline"
                  data-testid={`ship-open-ar-${r.shipment_number}`}
                >
                  {r.auto_invoice_number}
                  <ExternalLink className="w-3 h-3" />
                </button>
              ) : <span className="text-[11px] text-foreground/40">-</span> },
          ]}
          emptyTitle="Belum ada shipment"
          emptyDescription='Klik "Shipment Baru" untuk membuat Surat Jalan dari order yang sudah confirmed.'
          emptyIcon={Truck}
          exportFilename={`shipments-${new Date().toISOString().slice(0, 10)}.csv`}
          rowActions={(r) => (
            <div className="inline-flex items-center gap-2 flex-wrap">
              <button
                onClick={() => openPDF(r.id, r.shipment_number)}
                className="text-xs text-[hsl(var(--primary))] hover:underline inline-flex items-center gap-1"
                data-testid={`ship-pdf-${r.shipment_number}`}
                title="Surat Jalan PDF"
              >
                <FileText className="w-3 h-3" /> PDF
              </button>
              {r.status === 'draft' && (
                <>
                  <button
                    onClick={() => changeStatus(r.id, 'dispatched', 'Dispatch shipment')}
                    className="text-xs text-[hsl(var(--info))] hover:underline inline-flex items-center gap-1"
                    data-testid={`ship-dispatch-${r.shipment_number}`}
                  >
                    <Send className="w-3 h-3" /> Dispatch
                  </button>
                  <button
                    onClick={() => changeStatus(r.id, 'cancelled', 'Cancel shipment')}
                    className="text-xs text-[hsl(var(--destructive))] hover:underline inline-flex items-center gap-1"
                  >
                    <XCircle className="w-3 h-3" /> Batal
                  </button>
                  <button
                    onClick={() => deleteShipment(r.id)}
                    className="text-xs text-foreground/60 hover:text-[hsl(var(--destructive))] hover:underline inline-flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" /> Hapus
                  </button>
                </>
              )}
              {r.status === 'dispatched' && (
                <>
                  <button
                    onClick={() => changeStatus(r.id, 'delivered', 'Konfirmasi delivered')}
                    className="text-xs text-[hsl(var(--success))] hover:underline inline-flex items-center gap-1"
                    data-testid={`ship-deliver-${r.shipment_number}`}
                  >
                    <PackageCheck className="w-3 h-3" /> Delivered
                  </button>
                  <button
                    onClick={() => changeStatus(r.id, 'cancelled', 'Cancel shipment')}
                    className="text-xs text-[hsl(var(--destructive))] hover:underline inline-flex items-center gap-1"
                  >
                    <XCircle className="w-3 h-3" /> Batal
                  </button>
                </>
              )}
            </div>
          )}
        />
      )}

      {creating && (
        <CreateShipmentModal
          orders={orders}
          workOrders={workOrders}
          customers={customers}
          onClose={() => setCreating(false)}
          onCreate={createShipment}
        />
      )}
    </div>
  );
}

// ─── Create Modal ────────────────────────────────────────────────────────────
function CreateShipmentModal({ orders, workOrders, customers, onClose, onCreate }) {
  const today = new Date().toISOString().split('T')[0];
  const [order_id, setOrderId] = useState('');
  const [shipment_date, setShipDate] = useState(today);
  const [driver_name, setDriver] = useState('');
  const [vehicle_number, setVehicle] = useState('');
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState([]); // {wo_id, qty, unit_price}
  const [submitting, setSubmitting] = useState(false);

  // WOs difilter berdasarkan order terpilih
  const orderWOs = useMemo(
    () => workOrders.filter((w) => w.order_id === order_id),
    [workOrders, order_id]
  );

  const selectedOrder = useMemo(
    () => orders.find((o) => o.id === order_id),
    [orders, order_id]
  );

  const customerName = useMemo(() => {
    if (!selectedOrder) return '-';
    const c = customers.find((x) => x.id === selectedOrder.customer_id);
    return c?.name || selectedOrder.customer_name_snapshot || '-';
  }, [selectedOrder, customers]);

  // Reset items saat ganti order
  useEffect(() => { setItems([]); }, [order_id]);

  const addAllWOs = () => {
    setItems(orderWOs.map((w) => ({
      wo_id: w.id,
      wo_number: w.wo_number,
      model_name: w.model_name_snapshot || w.model_code_snapshot || '-',
      size_code: w.size_code,
      max_qty: Number(w.qty) || 0,
      qty: Number(w.qty) || 0,
      unit_price: 0,
    })));
  };

  const toggleWO = (wo) => {
    const exists = items.find((i) => i.wo_id === wo.id);
    if (exists) {
      setItems(items.filter((i) => i.wo_id !== wo.id));
    } else {
      setItems([...items, {
        wo_id: wo.id,
        wo_number: wo.wo_number,
        model_name: wo.model_name_snapshot || wo.model_code_snapshot || '-',
        size_code: wo.size_code,
        max_qty: Number(wo.qty) || 0,
        qty: Number(wo.qty) || 0,
        unit_price: 0,
      }]);
    }
  };

  const updateItem = (wo_id, patch) => {
    setItems(items.map((i) => i.wo_id === wo_id ? { ...i, ...patch } : i));
  };

  const totalQty = items.reduce((s, i) => s + (Number(i.qty) || 0), 0);
  const totalValue = items.reduce(
    (s, i) => s + (Number(i.qty) || 0) * (Number(i.unit_price) || 0), 0
  );

  const canSubmit = order_id && items.length > 0 && items.every((i) => Number(i.qty) > 0);

  const submit = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    const ok = await onCreate({
      order_id,
      shipment_date,
      driver_name,
      vehicle_number,
      notes,
      items: items.map((i) => ({
        wo_id: i.wo_id, qty: Number(i.qty), unit_price: Number(i.unit_price) || 0,
      })),
    });
    setSubmitting(false);
    if (!ok) return;
  };

  const fmt = formatRupiah;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <GlassCard
        className="p-6 max-w-3xl w-full max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
              <Truck className="w-5 h-5 text-[hsl(var(--primary))]" /> Buat Shipment Baru
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              Pilih Order yang sudah <span className="font-semibold">confirmed</span>, lalu pilih WO yang dikirim & qty.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-foreground/60 hover:text-foreground text-sm"
            aria-label="Tutup"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          {/* ── Order ── */}
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
              Order Produksi
            </label>
            <SmartNativeSelect
              value={order_id}
              onChange={(e) => setOrderId(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="ship-create-order"
            >
              <option value="">— Pilih Order —</option>
              {orders.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.order_number} · {o.customer_name_snapshot || '-'} ({o.status})
                </option>
              ))}
            </SmartNativeSelect>
            {selectedOrder && (
              <p className="text-[11px] text-muted-foreground mt-1">
                Pelanggan: <span className="text-foreground">{customerName}</span>
              </p>
            )}
          </div>

          {/* ── Header form ── */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <div>
              <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
                Tanggal Kirim
              </label>
              <GlassInput
                type="date"
                value={shipment_date}
                onChange={(e) => setShipDate(e.target.value)}
                data-testid="ship-create-date"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
                Pengemudi
              </label>
              <GlassInput
                value={driver_name}
                onChange={(e) => setDriver(e.target.value)}
                placeholder="Nama driver"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
                No. Kendaraan
              </label>
              <GlassInput
                value={vehicle_number}
                onChange={(e) => setVehicle(e.target.value)}
                placeholder="B 1234 XX"
              />
            </div>
          </div>

          {/* ── WO Items ── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs uppercase tracking-wider text-muted-foreground">
                Work Orders Dikirim
              </label>
              {order_id && orderWOs.length > 0 && (
                <Button
                  variant="ghost"
                  onClick={addAllWOs}
                  className="h-7 px-2 text-xs border border-[var(--glass-border)]"
                >
                  <Plus className="w-3 h-3 mr-1" /> Pilih Semua WO
                </Button>
              )}
            </div>

            {!order_id ? (
              <div className="text-xs text-muted-foreground border border-dashed border-[var(--glass-border)] rounded-lg p-4 text-center">
                Pilih order untuk melihat daftar WO.
              </div>
            ) : orderWOs.length === 0 ? (
              <div className="text-xs text-muted-foreground border border-dashed border-[var(--glass-border)] rounded-lg p-4 text-center">
                <ClipboardList className="w-5 h-5 mx-auto mb-1 opacity-60" />
                Order ini belum punya WO. Buat WO dulu sebelum shipment.
              </div>
            ) : (
              <div className="border border-[var(--glass-border)] rounded-lg overflow-hidden">
                <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-[var(--glass-bg)] text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                  <div className="col-span-1">Pilih</div>
                  <div className="col-span-4">WO · Model · Size</div>
                  <div className="col-span-2 text-right">Max Qty</div>
                  <div className="col-span-2 text-right">Qty Kirim</div>
                  <div className="col-span-3 text-right">Harga Satuan</div>
                </div>
                <div className="divide-y divide-[var(--glass-border)]">
                  {orderWOs.map((wo) => {
                    const sel = items.find((i) => i.wo_id === wo.id);
                    return (
                      <div
                        key={wo.id}
                        className="grid grid-cols-12 gap-2 px-3 py-2 items-center text-xs"
                      >
                        <div className="col-span-1">
                          <input
                            type="checkbox"
                            checked={!!sel}
                            onChange={() => toggleWO(wo)}
                            className="accent-[hsl(var(--primary))]"
                            data-testid={`ship-wo-${wo.wo_number}`}
                          />
                        </div>
                        <div className="col-span-4">
                          <div className="font-mono text-[11px] text-foreground/90">{wo.wo_number}</div>
                          <div className="text-[10px] text-muted-foreground">
                            {(wo.model_name_snapshot || wo.model_code_snapshot || '-')} · {wo.size_code || '-'}
                          </div>
                        </div>
                        <div className="col-span-2 text-right text-foreground/70 font-mono">
                          {Number(wo.qty || 0).toFixed(0)}
                        </div>
                        <div className="col-span-2">
                          <GlassInput
                            type="number"
                            min={0}
                            disabled={!sel}
                            value={sel?.qty ?? 0}
                            onChange={(e) => updateItem(wo.id, { qty: Number(e.target.value) })}
                            className="h-8 text-xs text-right"
                          />
                        </div>
                        <div className="col-span-3">
                          <GlassInput
                            type="number"
                            min={0}
                            step="1000"
                            disabled={!sel}
                            value={sel?.unit_price ?? 0}
                            onChange={(e) => updateItem(wo.id, { unit_price: Number(e.target.value) })}
                            className="h-8 text-xs text-right"
                            placeholder="0"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {items.length > 0 && (
              <div className="grid grid-cols-2 gap-2 mt-3">
                <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-lg p-3">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Total Qty
                  </div>
                  <div className="text-lg font-bold text-foreground font-mono">
                    {totalQty.toFixed(0)} pcs
                  </div>
                </div>
                <div className="bg-[hsl(var(--primary)/0.08)] border border-[hsl(var(--primary)/0.22)] rounded-lg p-3">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Est. Nilai AR (saat dispatch)
                  </div>
                  <div className="text-lg font-bold text-[hsl(var(--primary))] font-mono">
                    {fmt(totalValue)}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Catatan ── */}
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
              Catatan (opsional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground resize-none"
              placeholder="Instruksi khusus driver, packing, dll"
            />
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="flex gap-2 mt-6 justify-end">
          <Button
            variant="ghost"
            onClick={onClose}
            className="border border-[var(--glass-border)]"
          >
            Batal
          </Button>
          <Button
            onClick={submit}
            disabled={!canSubmit || submitting}
            data-testid="ship-create-submit"
          >
            <Truck className="w-4 h-4 mr-1.5" />
            {submitting ? 'Menyimpan...' : 'Buat Shipment Draft'}
          </Button>
        </div>
      </GlassCard>
    </div>
  );
}
