import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Edit2, Trash2, Eye, ArrowRight, X, Factory, CheckCircle2, XCircle, Clock, ClipboardList, History, Package, BarChart3 } from 'lucide-react';
import OnwardCTA from './OnwardCTA';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { AuditHistoryDrawer } from './AuditHistoryDrawer';
import { DataTable } from './DataTableV2';
import { PageHeader } from './moduleAtoms';
import POStageTrackingPanel from './POStageTrackingPanel';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_COLORS = {
  draft:         { bg: 'bg-muted dark:bg-slate-400/15',  border: 'border-border/25',  text: 'text-foreground/70',   label: 'Draft' },
  confirmed:     { bg: 'bg-blue-50 dark:bg-blue-400/15',   border: 'border-blue-300/25',   text: 'text-blue-600 dark:text-blue-300',    label: 'Confirmed' },
  in_production: { bg: 'bg-primary/15',    border: 'border-primary/25',    text: 'text-primary',     label: 'In Production' },
  completed:     { bg: 'bg-emerald-50 dark:bg-emerald-400/15',border: 'border-emerald-300/25',text: 'text-emerald-600 dark:text-emerald-300', label: 'Completed' },
  closed:        { bg: 'bg-foreground/10', border: 'border-foreground/20', text: 'text-foreground/70', label: 'Closed' },
  cancelled:     { bg: 'bg-red-50 dark:bg-red-400/15',    border: 'border-red-300/25',    text: 'text-red-600 dark:text-red-300',     label: 'Cancelled' },
};

function StatusBadge({ status }) {
  const s = STATUS_COLORS[status] || STATUS_COLORS.draft;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${s.bg} ${s.border} border ${s.text}`}>
      {s.label}
    </span>
  );
}

export default function RahazaOrdersModule({ token, onNavigate }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailOrder, setDetailOrder] = useState(null);
  const [auditOrder, setAuditOrder] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [models, setModels] = useState([]);
  const [sizes, setSizes] = useState([]);
  const [statuses, setStatuses] = useState([]);

  const [form, setForm] = useState({
    order_date: new Date().toISOString().slice(0,10),
    due_date: '',
    customer_id: '',
    is_internal: false,
    notes: '',
    items: [],
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  // SESI #27 — nomor order mengikuti kebijakan Otomatis/Manual milik owner.
  const numPolicy = useDocNumberPolicy('rahaza_orders.order_number', token);
  const [orderNumber, setOrderNumber] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/rahaza/orders`, { headers });
      if (res.ok) setOrders(await res.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);
  useEffect(() => {
    const h = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch('/api/rahaza/customers', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/models', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/sizes', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/orders-statuses', { headers: h }).then(r => r.ok ? r.json() : []),
    ]).then(([c, m, s, st]) => { setCustomers(c); setModels(m); setSizes(s); setStatuses(st); });
  }, [token]);

  const openCreate = () => {
    setEditing(null);
    setForm({
      order_date: new Date().toISOString().slice(0,10),
      due_date: '', customer_id: '', is_internal: false, notes: '',
      items: [{ model_id: '', size_id: '', qty: 1 }],
    });
    setOrderNumber('');
    setFormError('');
    setModalOpen(true);
  };
  const openEdit = async (order) => {
    const res = await fetch(`/api/rahaza/orders/${order.id}`, { headers });
    if (!res.ok) return;
    const full = await res.json();
    setEditing(full);
    setForm({
      order_date: full.order_date || '',
      due_date: full.due_date || '',
      customer_id: full.customer_id || '',
      is_internal: !!full.is_internal,
      notes: full.notes || '',
      items: (full.items || []).map(i => ({ id: i.id, model_id: i.model_id, size_id: i.size_id, qty: i.qty, notes: i.notes || '' })),
    });
    setFormError('');
    setModalOpen(true);
  };
  const openDetail = async (order) => {
    const res = await fetch(`/api/rahaza/orders/${order.id}`, { headers });
    if (res.ok) setDetailOrder(await res.json());
  };

  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { model_id: '', size_id: '', qty: 1 }] }));
  const updateItem = (idx, key, val) => setForm(f => ({
    ...f, items: f.items.map((it, i) => i === idx ? { ...it, [key]: val } : it),
  }));
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));

  const handleSave = async () => {
    setSaving(true); setFormError('');
    try {
      const payload = { ...form };
      // Nomor dokumen hanya dikirim bila kebijakan = MANUAL (dan hanya saat BUAT baru;
      // mengubah nomor order yang sudah terbit = memutus jejak arsip).
      if (!editing) Object.assign(payload, docNumberPayload(numPolicy, 'order_number', orderNumber));
      payload.items = payload.items.filter(i => i.model_id && i.size_id && Number(i.qty) > 0).map(i => ({ ...i, qty: Number(i.qty) }));
      if (payload.items.length === 0) {
        throw new Error('Tambahkan minimal 1 item pesanan.');
      }
      if (!payload.is_internal && !payload.customer_id) {
        throw new Error('Pilih pelanggan atau centang "Produksi Internal".');
      }
      const url = editing ? `/api/rahaza/orders/${editing.id}` : '/api/rahaza/orders';
      const method = editing ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers, body: JSON.stringify(payload) });
      if (!res.ok) {
        const STATUS_MSG = { 400:'Data tidak valid.', 403:'Tidak ada akses.', 404:'Tidak ditemukan.', 409:'Konflik data.' };
        throw new Error(STATUS_MSG[res.status] || `Gagal menyimpan (HTTP ${res.status})`);
      }
      setModalOpen(false);
      fetchOrders();
    } catch (err) { setFormError(err.message); }
    finally { setSaving(false); }
  };

  const transition = async (order, newStatus) => {
    if (!window.confirm(`Ubah status ke ${newStatus}?`)) return;
    const res = await fetch(`/api/rahaza/orders/${order.id}/status`, {
      method: 'POST', headers, body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) { fetchOrders(); if (detailOrder?.id === order.id) openDetail(order); }
    else { alert('Gagal transisi status'); }
  };

  const handleDelete = async (order) => {
    if (!window.confirm(`Hapus order ${order.order_number}?`)) return;
    await fetch(`/api/rahaza/orders/${order.id}`, { method: 'DELETE', headers });
    fetchOrders();
  };

  // FASE 20 — `generateWO()` DIHAPUS, bukan diberi endpoint baru.
  // Buktinya engine-nya memang sudah dipensiunkan, bukan cuma "endpoint lupa dibuat":
  //   · `db.rahaza_work_orders`: SEMUA penulisnya ada di `routes/_archive/`,
  //     index-nya dihapus di server.py ("FASE 4 (E10): koleksi DELETE"), 0 dokumen;
  //   · `dewi_maklon_pos.py` menegaskan: "FASE 4 (E10 DELETE): engine
  //     rahaza_work_orders diarsip — TIDAK insert WO lagi";
  //   · penggantinya sudah hidup: modul `prod-work-orders` (EngineJobsModule).
  // Menambah `POST /orders/{id}/generate-work-orders` justru akan MENGHIDUPKAN
  // ULANG engine yang sengaja dimatikan dan membuat jejak produksi fiktif.
  // Jalur pengguna tetap ada lewat OnwardCTA "Buat / Lihat Work Order" di bawah.

  if (loading && orders.length === 0) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
    </div>
  );

  return (
    <div className="space-y-5" data-testid="rahaza-orders-page">
      <PageHeader
        icon={Package}
        eyebrow="Portal Produksi"
        title="Order Produksi"
        subtitle="Order dari pelanggan atau produksi untuk stok. Setiap order berisi satu atau lebih item (Model + Size + Qty)."
        actions={<Button onClick={openCreate} data-testid="orders-add-btn"><Plus className="w-4 h-4 mr-1.5" /> Order Baru</Button>}
      />

      {/* RC-FLOW-UX Alur 3 — Order → Work Order */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'prod-work-orders', label: 'Buat / Lihat Work Order', icon: ClipboardList, primary: true, hint: 'Ubah order jadi perintah produksi (WO)' },
        ]}
      />

      <DataTable
        tableId="orders"
        loading={loading}
        rows={orders}
        searchFields={['order_number', 'customer_name', 'status', 'notes']}
        filters={[
          { key: 'status', label: 'Status', type: 'select',
            options: statuses.map(s => ({ value: s.value, label: s.label })) },
          { key: 'order_date', label: 'Tanggal', type: 'date-range' },
        ]}
        columns={[
          { key: 'order_number', label: 'No. Order', sortable: true,
            render: (r, v) => <span className="font-mono text-xs">{v}</span> },
          { key: 'order_date', label: 'Tanggal', sortable: true,
            render: (r, v) => <span className="text-foreground/70">{v || '—'}</span> },
          { key: 'customer_name', label: 'Pelanggan', sortable: true,
            accessor: (r) => r.customer_name || (r.is_internal ? 'Produksi Internal' : '-') },
          { key: 'item_count', label: 'Items', align: 'right', sortable: true,
            accessor: (r) => r.item_count || 0 },
          { key: 'total_qty', label: 'Total Qty', align: 'right', sortable: true,
            render: (r) => <span className="font-semibold">{r.total_qty || 0} pcs</span> },
          { key: 'due_date', label: 'Due', sortable: true,
            render: (r, v) => <span className="text-foreground/70">{v || '—'}</span> },
          { key: 'status', label: 'Status',
            render: (r) => <StatusBadge status={r.status} /> },
        ]}
        emptyTitle="Belum ada Order Produksi"
        emptyDescription="Buat order pertama untuk memulai alur produksi."
        emptyIcon={Package}
        emptyAction={
          <Button
            onClick={openCreate}
            className="h-9"
            data-testid="orders-empty-cta-create"
          >
            <Plus className="w-4 h-4 mr-1.5" /> Buat Order Pertama
          </Button>
        }
        emptyHelp="Alur lengkap: Order → generate Work Order → Material Issue → produksi. Tanpa Order, tidak ada WO, dan produksi tidak tercatat."
        exportFilename={`orders-${new Date().toISOString().slice(0,10)}.csv`}
        rowActions={(o) => (
          <div className="inline-flex items-center gap-1">
            <button onClick={() => openDetail(o)} className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" title="Detail" data-testid={`order-detail-${o.order_number}`}><Eye className="w-3.5 h-3.5" /></button>
            {o.status === 'draft' && (
              <>
                <button onClick={() => openEdit(o)} className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" title="Edit" data-testid={`order-edit-${o.order_number}`}><Edit2 className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(o)} className="p-1.5 rounded hover:bg-red-50 dark:bg-red-400/10 text-muted-foreground hover:text-red-700 dark:text-red-400" title="Hapus"><Trash2 className="w-3.5 h-3.5" /></button>
              </>
            )}
          </div>
        )}
      />

      {/* Create/Edit Modal */}
      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? `Edit Order ${editing.order_number}` : 'Order Baru'} size="lg">
          <div className="space-y-4" data-testid="orders-form">
            {formError && <div className="bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-300/20 rounded-lg p-3 text-sm text-red-600 dark:text-red-300">{formError}</div>}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Tanggal Order</label>
                <GlassInput type="date" value={form.order_date} onChange={e => setForm({...form, order_date: e.target.value})} data-testid="order-field-order_date" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Due Date (target selesai)</label>
                <GlassInput type="date" value={form.due_date} onChange={e => setForm({...form, due_date: e.target.value})} data-testid="order-field-due_date" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="is_internal" checked={form.is_internal}
                onChange={e => setForm({...form, is_internal: e.target.checked, customer_id: e.target.checked ? '' : form.customer_id})}
                className="h-4 w-4" data-testid="order-field-is_internal" />
              <label htmlFor="is_internal" className="text-sm text-foreground cursor-pointer">Produksi Internal (tanpa pelanggan, untuk stok sendiri)</label>
            </div>
            {!form.is_internal && (
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Pelanggan <span className="text-red-700 dark:text-red-400">*</span></label>
                <SmartNativeSelect value={form.customer_id} onChange={e => setForm({...form, customer_id: e.target.value})}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="order-field-customer_id">
                  <option value="">— Pilih Pelanggan —</option>
                  {customers.filter(c => c.active).map(c => <option key={c.id} value={c.id}>{`${c.code} · ${c.name}`}</option>)}
                </SmartNativeSelect>
              </div>
            )}

            {/* Items */}
            <div className="border-t border-[var(--glass-border)] pt-3">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-semibold text-foreground">Item Pesanan</label>
                <button onClick={addItem} className="text-xs text-primary hover:text-primary/80 flex items-center gap-1" data-testid="order-add-item-btn"><Plus className="w-3 h-3" /> Tambah Item</button>
              </div>
              <div className="space-y-2">
                {form.items.map((it, idx) => (
                  <div key={idx} className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 items-center">
                    <SmartNativeSelect value={it.model_id} onChange={e => updateItem(idx, 'model_id', e.target.value)}
                      className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                      data-testid={`order-item-${idx}-model`}>
                      <option value="">— Model —</option>
                      {models.filter(m => m.active).map(m => <option key={m.id} value={m.id}>{`${m.code} · ${m.name}`}</option>)}
                    </SmartNativeSelect>
                    <SmartNativeSelect value={it.size_id} onChange={e => updateItem(idx, 'size_id', e.target.value)}
                      className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                      data-testid={`order-item-${idx}-size`}>
                      <option value="">— Size —</option>
                      {sizes.filter(s => s.active).map(s => <option key={s.id} value={s.id}>{s.code}</option>)}
                    </SmartNativeSelect>
                    <GlassInput type="number" value={it.qty} onChange={e => updateItem(idx, 'qty', e.target.value)}
                      placeholder="Qty" data-testid={`order-item-${idx}-qty`} />
                    <button onClick={() => removeItem(idx)} className="p-1.5 rounded hover:bg-red-50 dark:bg-red-400/10 text-muted-foreground hover:text-red-700 dark:text-red-400">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Catatan</label>
              <GlassInput value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} placeholder="Opsional" />
            </div>

            {!editing && (
              <DocNumberField
                policy={numPolicy} value={orderNumber} onChange={setOrderNumber}
                testId="order-docnum" label="Nomor Order" />
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="order-save-btn">
                {saving ? 'Menyimpan...' : (editing ? 'Simpan Perubahan' : 'Buat Order')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Detail modal */}
      {detailOrder && (
        <Modal onClose={() => setDetailOrder(null)} title={`Detail Order ${detailOrder.order_number}`} size="lg">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div><span className="text-muted-foreground">Status:</span> <StatusBadge status={detailOrder.status} /></div>
              <div><span className="text-muted-foreground">Tanggal:</span> <b>{detailOrder.order_date}</b></div>
              <div><span className="text-muted-foreground">Pelanggan:</span> <b>{detailOrder.customer_name || (detailOrder.is_internal ? 'Produksi Internal' : '-')}</b></div>
              <div><span className="text-muted-foreground">Due:</span> <b>{detailOrder.due_date || '-'}</b></div>
            </div>
            <GlassPanel className="p-0 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-[var(--glass-bg)]"><tr className="text-left text-xs text-muted-foreground">
                  <th className="px-3 py-2">Model</th><th className="px-3 py-2">Size</th><th className="px-3 py-2 text-right">Qty</th>
                </tr></thead>
                <tbody>
                  {(detailOrder.items || []).map(it => (
                    <tr key={it.id} className="border-t border-[var(--glass-border)]">
                      <td className="px-3 py-2">{it.model_code} · {it.model_name}</td>
                      <td className="px-3 py-2">{it.size_code}</td>
                      <td className="px-3 py-2 text-right font-semibold">{it.qty} pcs</td>
                    </tr>
                  ))}
                  <tr className="border-t border-[var(--glass-border)] bg-[var(--glass-bg)]">
                    <td colSpan={2} className="px-3 py-2 font-semibold">Total</td>
                    <td className="px-3 py-2 text-right font-bold text-primary">{detailOrder.total_qty} pcs</td>
                  </tr>
                </tbody>
              </table>
            </GlassPanel>

            {/* Status actions */}
            <div className="border-t border-[var(--glass-border)] pt-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs text-muted-foreground">Aksi:</div>
                <Button
                  variant="ghost"
                  onClick={() => setAuditOrder(detailOrder)}
                  className="gap-1.5 text-xs text-muted-foreground hover:text-foreground h-7 px-2"
                  data-testid="order-audit-btn"
                  title="Lihat riwayat perubahan"
                >
                  <History className="w-3.5 h-3.5" />
                  Riwayat
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {(statuses.find(s => s.value === detailOrder.status)?.allowed_next || []).map(ns => (
                  <Button key={ns} variant="ghost" onClick={() => transition(detailOrder, ns)} className="gap-1.5 border border-[var(--glass-border)]" data-testid={`order-transition-${ns}`}>
                    <ArrowRight className="w-3.5 h-3.5" /> {STATUS_COLORS[ns]?.label || ns}
                  </Button>
                ))}
                {(statuses.find(s => s.value === detailOrder.status)?.allowed_next || []).length === 0 && !['draft','confirmed','in_production'].includes(detailOrder.status) && (
                  <div className="text-xs text-muted-foreground">Tidak ada transisi lanjutan.</div>
                )}
              </div>
            </div>

            {/* Stage Tracking Panel (GAP #3) */}
            {detailOrder && ['in_production','completed'].includes(detailOrder.status) && (
              <GlassPanel className="p-4 border-t border-[var(--glass-border)] mt-4">
                <POStageTrackingPanel
                  po={detailOrder}
                  headers={{ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }}
                />
              </GlassPanel>
            )}
          </div>
        </Modal>
      )}

      {/* Phase 12.3 — Audit history drawer */}
      <AuditHistoryDrawer
        open={!!auditOrder}
        onClose={() => setAuditOrder(null)}
        token={token}
        entityType="rahaza_order"
        entityId={auditOrder?.id}
        entityLabel={auditOrder ? `Order ${auditOrder.order_number}` : ''}
      />
    </div>
  );
}
