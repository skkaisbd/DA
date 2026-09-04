import { useState, useEffect, useCallback, useMemo } from 'react';
import { FileCheck, Plus, RefreshCw, Eye, CheckCircle2, XCircle, RotateCcw, Send, Edit2, Trash2, Camera } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { fetchMaklonOrders, posToLegacyOrders } from '@/lib/maklonOrderAdapter';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_CONFIG = {
  draft:               { label: 'Draft',             color: 'bg-muted text-foreground border-border dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-400/30' },
  in_progress:         { label: 'Sedang Dibuat',     color: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-400/30' },
  submitted:           { label: 'Menunggu Approval', color: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-400/30' },
  approved:            { label: 'Disetujui',         color: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-500/15 dark:text-green-300 dark:border-green-400/30' },
  rejected:            { label: 'Ditolak',           color: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-400/30' },
  revision_requested:  { label: 'Revisi',            color: 'bg-orange-100 text-orange-700 border-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-400/30' },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return <span className={`inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.color}`}>{c.label}</span>;
}

export default function MaklonSampleManagement({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [samples, setSamples] = useState([]);
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('all');
  const [editDialog, setEditDialog] = useState(null);
  const [viewDialog, setViewDialog] = useState(null);
  const [reviseDialog, setReviseDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [s, o, sum] = await Promise.all([
        fetch('/api/dewi/maklon/samples', { headers }),
        fetch('/api/dewi/maklon/pos', { headers }),
        fetch('/api/dewi/maklon/samples/summary/overview', { headers }),
      ]);
      if (s.ok) setSamples(await s.json());
      if (o.ok) setOrders(posToLegacyOrders(await o.json()));
      if (sum.ok) setSummary(await sum.json());
    } catch (e) { toast.error('Gagal memuat data sample'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const submitSample = async (s) => {
    const r = await fetch(`/api/dewi/maklon/samples/${s.id}/submit`, { method: 'POST', headers });
    if (r.ok) { toast.success('Sample disubmit untuk approval'); fetchAll(); }
    else toast.error((await r.json()).detail || 'Gagal submit');
  };
  const approveSample = async (s) => {
    if (!window.confirm(`Setujui sample ${s.sample_code}?`)) return;
    const r = await fetch(`/api/dewi/maklon/samples/${s.id}/approve`, { method: 'POST', headers, body: JSON.stringify({}) });
    if (r.ok) { toast.success('Sample disetujui'); fetchAll(); }
    else toast.error((await r.json()).detail || 'Gagal menyetujui');
  };
  const deleteSample = async (s) => {
    if (!window.confirm(`Hapus sample ${s.sample_code}?`)) return;
    const r = await fetch(`/api/dewi/maklon/samples/${s.id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Sample dihapus'); fetchAll(); }
    else toast.error((await r.json()).detail || 'Gagal menghapus');
  };

  const filtered = tab === 'all' ? samples : samples.filter(s => {
    if (tab === 'pending') return ['submitted', 'revision_requested'].includes(s.status);
    if (tab === 'approved') return s.status === 'approved';
    if (tab === 'rejected') return s.status === 'rejected';
    if (tab === 'drafts') return ['draft', 'in_progress'].includes(s.status);
    return true;
  });

  const stats = [
    { label: 'Total Sample',   value: summary.total_samples || 0,   color: 'text-blue-400 bg-blue-500/10 border-blue-400/20' },
    { label: 'Menunggu',       value: summary.pending_approval || 0, color: 'text-amber-400 bg-amber-500/10 border-amber-400/20' },
    { label: 'Disetujui',      value: summary.approved || 0,        color: 'text-green-400 bg-green-500/10 border-green-400/20' },
    { label: 'Ditolak',        value: summary.rejected || 0,        color: 'text-red-400 bg-red-500/10 border-red-400/20' },
  ];

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="p-6 space-y-6" data-testid="maklon-samples">
      <PageHeader
        title="Sample Management"
        subtitle="Kelola sample produk untuk order maklon dengan workflow approval dari klien"
        icon={FileCheck}
        testId="maklon-samples-header"
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={fetchAll} className="gap-2" data-testid="samples-refresh-btn">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button size="sm" onClick={() => setEditDialog({})} className="gap-1.5" data-testid="samples-create-btn">
              <Plus className="w-3.5 h-3.5" /> Buat Sample
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
            <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
              <div className="text-xs text-foreground/50">{s.label}</div>
              <div className={`text-2xl font-bold mt-1 ${s.color.split(' ')[0]}`}>{s.value}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="all">Semua ({samples.length})</TabsTrigger>
          <TabsTrigger value="drafts">Draft</TabsTrigger>
          <TabsTrigger value="pending">Pending Approval</TabsTrigger>
          <TabsTrigger value="approved">Disetujui</TabsTrigger>
          <TabsTrigger value="rejected">Ditolak</TabsTrigger>
        </TabsList>

        <TabsContent value={tab}>
          <GlassCard className="p-5">
            {loading ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Memuat...</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-10 text-foreground/40 text-sm">Belum ada sample</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="samples-table">
                  <thead><tr className="border-b border-foreground/5 text-xs text-foreground/55">
                    <th className="pb-2 text-left">Sample Code</th>
                    <th className="pb-2 text-left">Order</th>
                    <th className="pb-2 text-left">Produk</th>
                    <th className="pb-2 text-left">Klien</th>
                    <th className="pb-2 text-center">Revisi</th>
                    <th className="pb-2 text-left">Status</th>
                    <th className="pb-2 text-center">Aksi</th>
                  </tr></thead>
                  <tbody className="divide-y divide-white/5">
                    {paged.map(s => (
                      <tr key={s.id} className="hover:bg-foreground/[0.03]">
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/70">{s.sample_code}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-foreground/60">{s.order_code}</td>
                        <td className="py-2.5 pr-3 text-foreground">{s.product_name}</td>
                        <td className="py-2.5 pr-3 text-foreground/70">{s.client_name}</td>
                        <td className="py-2.5 pr-3 text-center">
                          <Badge variant="outline" className="text-[10px]">#{s.revision_number || 0}</Badge>
                        </td>
                        <td className="py-2.5 pr-3"><StatusBadge status={s.status} /></td>
                        <td className="py-2.5">
                          <div className="flex gap-1 justify-center">
                            <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setViewDialog(s)} title="Detail"><Eye className="w-3.5 h-3.5" /></Button>
                            {['draft','in_progress','revision_requested'].includes(s.status) && (
                              <>
                                <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setEditDialog({ data: s })} title="Edit"><Edit2 className="w-3.5 h-3.5" /></Button>
                                <Button size="icon" variant="ghost" className="w-7 h-7 text-blue-400" onClick={() => submitSample(s)} title="Submit"><Send className="w-3.5 h-3.5" /></Button>
                              </>
                            )}
                            {s.status === 'submitted' && (
                              <>
                                <Button size="icon" variant="ghost" className="w-7 h-7 text-green-400" onClick={() => approveSample(s)} title="Setujui"><CheckCircle2 className="w-3.5 h-3.5" /></Button>
                                <Button size="icon" variant="ghost" className="w-7 h-7 text-orange-400" onClick={() => setReviseDialog(s)} title="Minta Revisi"><RotateCcw className="w-3.5 h-3.5" /></Button>
                                <Button size="icon" variant="ghost" className="w-7 h-7 text-red-400" onClick={() => setRejectDialog(s)} title="Tolak"><XCircle className="w-3.5 h-3.5" /></Button>
                              </>
                            )}
                            {['draft','in_progress','rejected'].includes(s.status) && (
                              <Button size="icon" variant="ghost" className="w-7 h-7 text-red-400/70" onClick={() => deleteSample(s)} title="Hapus"><Trash2 className="w-3.5 h-3.5" /></Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </div>
            )}
          </GlassCard>
        </TabsContent>
      </Tabs>

      {editDialog !== null && (
        <SampleDialog data={editDialog?.data || null} orders={orders} headers={headers}
          onClose={() => setEditDialog(null)}
          onSuccess={() => { setEditDialog(null); fetchAll(); }}
        />
      )}
      {viewDialog && <ViewSampleDialog sample={viewDialog} headers={headers} onClose={() => setViewDialog(null)} />}
      {reviseDialog && (
        <RevisionDialog sample={reviseDialog} headers={headers}
          onClose={() => setReviseDialog(null)}
          onSuccess={() => { setReviseDialog(null); fetchAll(); }}
        />
      )}
      {rejectDialog && (
        <RejectDialog sample={rejectDialog} headers={headers}
          onClose={() => setRejectDialog(null)}
          onSuccess={() => { setRejectDialog(null); fetchAll(); }}
        />
      )}
    </div>
  );
}

function SampleDialog({ data, orders, headers, onClose, onSuccess }) {
  const isEdit = !!data;
  const [form, setForm] = useState(data || {
    order_id: '', product_name: '', description: '', target_size: 'M',
    fabric_used: '', color_used: '', sample_qty: 1, notes: '', buyer_catalog_id: null
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  // SESI #27 — kebijakan penomoran kode sampel. `ORDER` = kode order terpilih supaya
  // pratinjaunya nomor yang benar-benar akan lahir (SMP-<ORDER>-01).
  const orderCode = (orders || []).find(o => o.id === form.order_id)?.order_code || '';
  const numPolicy = useDocNumberPolicy('dewi_maklon_samples.sample_code',
                                       localStorage.getItem('erp_token'),
                                       { ORDER: orderCode });
  const [sampleCode, setSampleCode] = useState('');

  // Phase M2.1: load buyer catalogs untuk klien dari order yg dipilih
  const [catalogs, setCatalogs] = useState([]);
  const [loadingCat, setLoadingCat] = useState(false);

  useEffect(() => {
    if (!form.order_id || isEdit) { setCatalogs([]); return; }
    const selectedOrder = orders.find(o => o.id === form.order_id);
    if (!selectedOrder?.client_id) { setCatalogs([]); return; }
    setLoadingCat(true);
    fetch(`/api/dewi/maklon/buyer-catalog?client_id=${selectedOrder.client_id}&status=active`, { headers })
      .then(r => r.ok ? r.json() : [])
      .then(list => setCatalogs(Array.isArray(list) ? list : []))
      .finally(() => setLoadingCat(false));
  }, [form.order_id, orders, headers, isEdit]);

  const handlePickCatalog = (catalogId) => {
    if (catalogId === 'NONE') {
      set('buyer_catalog_id', null);
      return;
    }
    const cat = catalogs.find(c => c.id === catalogId);
    if (!cat) return;
    setForm(prev => ({
      ...prev,
      buyer_catalog_id: cat.id,
      // Auto-fill kosong fields dari catalog
      product_name: prev.product_name?.trim() || cat.product_name || cat.artikel_code,
      description: prev.description?.trim() || cat.description || '',
      color_used: prev.color_used?.trim() || (cat.color_options?.[0] || ''),
    }));
    toast.success(`Auto-fill dari Buyer Catalog: ${cat.artikel_code}`);
  };

  const save = async () => {
    if (!form.order_id || !form.product_name) { toast.error('Order & nama produk wajib'); return; }
    setSaving(true);
    const url = isEdit ? `/api/dewi/maklon/samples/${data.id}` : '/api/dewi/maklon/samples';
    const method = isEdit ? 'PUT' : 'POST';
    const payload = { ...form, sample_qty: Number(form.sample_qty) || 1 };
    // SESI #27 — kode sampel hanya dikirim bila kebijakan = MANUAL (dan hanya saat BUAT).
    if (!isEdit) Object.assign(payload, docNumberPayload(numPolicy, 'sample_code', sampleCode));
    const r = await fetch(url, { method, headers, body: JSON.stringify(payload) });
    setSaving(false);
    if (r.ok) { toast.success(isEdit ? 'Sample diperbarui' : 'Sample dibuat'); onSuccess(); }
    else toast.error((await r.json()).detail || 'Gagal menyimpan');
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="sample-dialog">
        <DialogHeader><DialogTitle>{isEdit ? `Edit: ${data.sample_code}` : 'Buat Sample Baru'}</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1 col-span-2">
              <Label>Order Maklon *</Label>
              <Select value={form.order_id} onValueChange={v => set('order_id', v)} disabled={isEdit}>
                <SelectTrigger data-testid="sample-order-select"><SelectValue placeholder="Pilih order..." /></SelectTrigger>
                <SelectContent>
                  {orders.filter(o => !['cancelled','completed','invoiced'].includes(o.status)).map(o => (
                    <SelectItem key={o.id} value={o.id}>{o.order_code} — {o.product_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* Phase M2.1: Buyer Catalog picker (optional) */}
            {!isEdit && form.order_id && catalogs.length > 0 && (
              <div className="space-y-1 col-span-2 bg-violet-500/5 border border-violet-400/20 rounded-lg p-2">
                <Label className="text-xs text-violet-300">📖 Link ke Buyer Catalog (opsional)</Label>
                <Select value={form.buyer_catalog_id || 'NONE'} onValueChange={handlePickCatalog}>
                  <SelectTrigger className="h-9" data-testid="sample-buyer-catalog-select">
                    <SelectValue placeholder="Pilih artikel dari Buyer Catalog (auto-fill spec)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="NONE">— Tidak link ke catalog (freestyle) —</SelectItem>
                    {catalogs.map(c => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.artikel_code} — {c.product_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="text-[10px] text-foreground/45">
                  Sample yang ter-link akan jadi referensi approval untuk semua PO masa depan dengan artikel sama.
                </div>
              </div>
            )}
            {!isEdit && form.order_id && !loadingCat && catalogs.length === 0 && (
              <div className="col-span-2 text-[10px] text-foreground/45 italic">
                Belum ada Buyer Catalog active untuk klien ini.
              </div>
            )}
            <div className="space-y-1 col-span-2"><Label>Nama Produk Sample *</Label><Input value={form.product_name} onChange={e => set('product_name', e.target.value)} data-testid="sample-product-name-input" /></div>
            <div className="space-y-1"><Label>Target Size</Label><Input value={form.target_size} onChange={e => set('target_size', e.target.value)} /></div>
            <div className="space-y-1"><Label>Qty Sample</Label><Input type="number" min="1" value={form.sample_qty} onChange={e => set('sample_qty', e.target.value)} /></div>
            <div className="space-y-1"><Label>Kain Digunakan</Label><Input value={form.fabric_used || ''} onChange={e => set('fabric_used', e.target.value)} placeholder="Contoh: Rayon Premium" /></div>
            <div className="space-y-1"><Label>Warna</Label><Input value={form.color_used || ''} onChange={e => set('color_used', e.target.value)} placeholder="Contoh: Navy" /></div>
            <div className="space-y-1 col-span-2"><Label>Deskripsi</Label><Textarea value={form.description || ''} onChange={e => set('description', e.target.value)} rows={2} /></div>
            <div className="space-y-1 col-span-2"><Label>Catatan</Label><Textarea value={form.notes || ''} onChange={e => set('notes', e.target.value)} rows={2} /></div>
            {!isEdit && (
              <div className="col-span-2">
                <DocNumberField
                  policy={numPolicy} value={sampleCode} onChange={setSampleCode}
                  testId="sample-docnum" label="Kode Sampel" />
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="sample-save-btn">{saving ? 'Menyimpan...' : (isEdit ? 'Simpan' : 'Buat')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ViewSampleDialog({ sample, headers, onClose }) {
  const [detail, setDetail] = useState(sample);

  useEffect(() => {
    fetch(`/api/dewi/maklon/samples/${sample.id}`, { headers })
      .then(r => r.ok && r.json())
      .then(d => d && setDetail(d))
      .catch(() => {});
  }, [sample.id, headers]);

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Detail Sample: {detail.sample_code}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2 text-sm">
          <InfoRow label="Order" value={detail.order_code} />
          <InfoRow label="Klien" value={detail.client_name} />
          <InfoRow label="Produk" value={detail.product_name} />
          <InfoRow label="Size" value={detail.target_size} />
          <InfoRow label="Qty Sample" value={detail.sample_qty} />
          <InfoRow label="Kain" value={detail.fabric_used} />
          <InfoRow label="Warna" value={detail.color_used} />
          <InfoRow label="Status" value={<StatusBadge status={detail.status} />} />
          <InfoRow label="Revisi" value={`#${detail.revision_number || 0}`} />
          <InfoRow label="Deskripsi" value={detail.description} />
          <InfoRow label="Catatan" value={detail.notes} />
          {detail.approved_by_name && <InfoRow label="Disetujui oleh" value={`${detail.approved_by_name} (${detail.approval_feedback || '-'})`} />}
          {detail.rejected_by_name && <InfoRow label="Ditolak oleh" value={`${detail.rejected_by_name} — ${detail.rejection_reason || ''}`} />}

          {detail.revisions && detail.revisions.length > 0 && (
            <div className="pt-3 border-t border-border">
              <div className="text-xs font-semibold text-foreground/60 mb-2">Riwayat Revisi</div>
              <div className="space-y-2">
                {detail.revisions.map(r => (
                  <div key={r.id} className="bg-foreground/5 rounded p-2 text-xs">
                    <div className="flex justify-between">
                      <span className="font-semibold text-orange-300">Revisi #{r.revision_number}</span>
                      <span className="text-foreground/40">{r.requested_by}</span>
                    </div>
                    <div className="mt-1 text-foreground/70">Alasan: {r.reason}</div>
                    {r.changes_required && <div className="text-foreground/50">Perubahan: {r.changes_required}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Tutup</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RevisionDialog({ sample, headers, onClose, onSuccess }) {
  const [reason, setReason] = useState('');
  const [changes, setChanges] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!reason) { toast.error('Alasan revisi wajib'); return; }
    setSaving(true);
    const r = await fetch(`/api/dewi/maklon/samples/${sample.id}/revision`, {
      method: 'POST', headers, body: JSON.stringify({ reason, changes_required: changes })
    });
    setSaving(false);
    if (r.ok) { toast.success('Revisi dicatat'); onSuccess(); }
    else toast.error((await r.json()).detail || 'Gagal');
  };
  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Minta Revisi: {sample.sample_code}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1"><Label>Alasan Revisi *</Label><Textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} /></div>
          <div className="space-y-1"><Label>Perubahan yang Diperlukan</Label><Textarea value={changes} onChange={e => setChanges(e.target.value)} rows={3} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving}>{saving ? 'Menyimpan...' : 'Minta Revisi'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({ sample, headers, onClose, onSuccess }) {
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!reason) { toast.error('Alasan penolakan wajib'); return; }
    setSaving(true);
    const r = await fetch(`/api/dewi/maklon/samples/${sample.id}/reject`, {
      method: 'POST', headers, body: JSON.stringify({ reason })
    });
    setSaving(false);
    if (r.ok) { toast.success('Sample ditolak'); onSuccess(); }
    else toast.error((await r.json()).detail || 'Gagal');
  };
  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Tolak Sample: {sample.sample_code}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1"><Label>Alasan Penolakan *</Label><Textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button variant="destructive" onClick={submit} disabled={saving}>{saving ? 'Menyimpan...' : 'Tolak Sample'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InfoRow({ label, value }) {
  if (!value && value !== 0) return null;
  return <div className="flex gap-3"><span className="text-foreground/50 shrink-0 w-32">{label}:</span><span className="text-foreground/80">{value}</span></div>;
}
