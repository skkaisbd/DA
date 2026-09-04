import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import { MiniBar } from './VendorShared';
import { apiGet, apiPost } from '../../../lib/api';

/**
 * ProductionProgressModule — "Input Progress" (produksi INTERNAL).
 *
 * FIX P0 (WS-H C2): versi lama membaca koleksi legacy `work_orders` (via GET /work-orders)
 * yang TIDAK PERNAH diisi flow produksi hidup → tabel selalu kosong. Progress produksi
 * hidup memakai model job-item (`production_jobs` → `production_job_items` → POST
 * /production-progress {job_item_id}). Modul ini kini mengikuti model yang sama dengan
 * VendorProgress.jsx, di-scope ke job internal (business_type=internal).
 *
 * Catatan backend: /production-progress hanya POST+GET(by work_order_id); TIDAK ada
 * PUT/DELETE, dan GET tidak bisa filter job_item_id → riwayat/edit/hapus lama (yang
 * memanggil endpoint tak-ada) dibuang. Progres per item dibaca dari produced_qty.
 */
export default function ProductionProgressModule() {
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobItems, setJobItems] = useState([]);
  const [childJobs, setChildJobs] = useState([]);
  const [selectedChildJobId, setSelectedChildJobId] = useState('');
  const [childJobItems, setChildJobItems] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);
  const [form, setForm] = useState({ progress_date: new Date().toISOString().split('T')[0], completed_quantity: '', notes: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchJobs(); }, []);

  const fetchJobs = async () => {
    setLoadingJobs(true);
    try {
      const data = await apiGet('/production-jobs?business_type=internal');
      const list = Array.isArray(data) ? data : (data?.items || []);
      // Tampilkan job yang masih bisa di-input (belum Completed)
      setJobs(list.filter(j => j.status !== 'Completed'));
    } catch (e) {
      setJobs([]);
    } finally {
      setLoadingJobs(false);
    }
  };

  const loadJobItems = async (jobId) => {
    const job = jobs.find(j => j.id === jobId);
    setSelectedJob(job || null);
    setSelectedChildJobId('');
    setChildJobItems([]);
    if (!jobId) { setJobItems([]); setChildJobs([]); return; }
    try {
      const data = await apiGet(`/production-job-items?job_id=${jobId}`);
      setJobItems(Array.isArray(data) ? data : []);
      setChildJobs(job?.child_jobs || []);
    } catch (e) { setJobItems([]); }
  };

  const loadChildJobItems = async (childJobId) => {
    setSelectedChildJobId(childJobId);
    if (!childJobId) { setChildJobItems([]); return; }
    try {
      const data = await apiGet(`/production-job-items?job_id=${childJobId}`);
      setChildJobItems(Array.isArray(data) ? data : []);
    } catch (e) { setChildJobItems([]); }
  };

  const openProgress = (item) => {
    setSelectedItem(item);
    setForm({ progress_date: new Date().toISOString().split('T')[0], completed_quantity: '', notes: '' });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedItem) return;
    setSaving(true);
    try {
      await apiPost('/production-progress', {
        job_item_id: selectedItem.id,
        progress_date: form.progress_date,
        completed_quantity: Number(form.completed_quantity),
        notes: form.notes,
      });
      toast.success('Progress produksi tersimpan');
      setShowModal(false);
      await loadJobItems(selectedJob?.id);
      if (selectedChildJobId) await loadChildJobItems(selectedChildJobId);
      fetchJobs();
    } catch (err) {
      toast.error(err.message || 'Gagal menyimpan progress');
    } finally {
      setSaving(false);
    }
  };

  const maxInput = (item) => Math.max(0, (item.available_qty ?? item.shipment_qty ?? 0) - (item.produced_qty || 0));

  const renderItemsTable = (items, isChild = false) => {
    if (!items.length) return <p className="text-sm text-muted-foreground/70 px-4 py-3">Tidak ada item pada job ini.</p>;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-muted/40">
              <th className="text-left px-4 py-2.5 text-xs text-amber-600 font-semibold">Serial</th>
              <th className="text-left px-4 py-2.5 text-xs text-muted-foreground">Produk</th>
              <th className="text-left px-4 py-2.5 text-xs text-muted-foreground">SKU</th>
              <th className="text-left px-4 py-2.5 text-xs text-muted-foreground">Artikel Buyer</th>
              <th className="text-left px-4 py-2.5 text-xs text-muted-foreground">Size</th>
              <th className="text-left px-4 py-2.5 text-xs text-muted-foreground">Warna</th>
              <th className="text-right px-4 py-2.5 text-xs text-muted-foreground">Tersedia</th>
              <th className="text-right px-4 py-2.5 text-xs text-muted-foreground">Diproduksi</th>
              <th className="text-right px-4 py-2.5 text-xs text-muted-foreground">Sisa</th>
              <th className="px-4 py-2.5 text-xs text-muted-foreground">Progress</th>
              <th className="px-4 py-2.5 text-xs text-muted-foreground">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {items.map(item => {
              const avail = item.available_qty ?? item.shipment_qty ?? 0;
              const produced = item.produced_qty || 0;
              const pct = avail > 0 ? Math.round((produced / avail) * 100) : 0;
              const sisa = Math.max(0, avail - produced);
              const isDone = produced >= avail && avail > 0;
              return (
                <tr key={item.id} className={`hover:bg-muted/60 ${isDone ? 'bg-emerald-50/30' : ''} ${isChild ? 'bg-purple-50/20' : ''}`}>
                  <td className="px-4 py-3 font-mono text-xs text-amber-700 font-semibold">{item.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                  <td className="px-4 py-3 font-medium text-foreground">{item.product_name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{item.buyer_ref_code || '—'}</td>
                  <td className="px-4 py-3 text-xs text-center">{item.size || '-'}</td>
                  <td className="px-4 py-3 text-xs text-center">{item.color || '-'}</td>
                  <td className="px-4 py-3 text-right font-medium text-blue-700">{avail.toLocaleString('id-ID')}</td>
                  <td className="px-4 py-3 text-right font-bold text-emerald-700">{produced.toLocaleString('id-ID')}</td>
                  <td className={`px-4 py-3 text-right font-medium ${sisa === 0 ? 'text-emerald-600' : 'text-orange-600'}`}>{sisa.toLocaleString('id-ID')}</td>
                  <td className="px-4 py-3 min-w-32"><MiniBar pct={pct} /></td>
                  <td className="px-4 py-3">
                    {isDone ? (
                      <span className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded text-xs font-medium">✅ Selesai</span>
                    ) : (
                      <button onClick={() => openProgress(item)}
                        data-testid="open-progress-btn"
                        className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700">
                        <Plus className="w-3 h-3" /> Input Progress
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Progres Produksi</h1>
        <p className="text-muted-foreground text-sm mt-1">Catat progress produksi harian per SKU. Pilih Job Produksi internal, lalu update qty per item.</p>
      </div>

      {/* Job selector */}
      <div className="bg-card border border-border rounded-xl p-4 shadow-sm">
        <label className="block text-sm font-semibold text-foreground/90 mb-2">Pilih Job Produksi (Internal)</label>
        {loadingJobs ? (
          <p className="text-sm text-muted-foreground/70">Memuat job produksi…</p>
        ) : jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground/70">Tidak ada Job Produksi internal aktif. Buat PO Internal lalu distribusikan ke Job Produksi (menu Pekerjaan Produksi) terlebih dahulu.</p>
        ) : (
          <SmartNativeSelect
            data-testid="prod-progress-job-select"
            className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedJob?.id || ''}
            onChange={e => loadJobItems(e.target.value)}
          >
            <option value="">— Pilih Job Produksi —</option>
            {jobs.map(j => (
              <option key={j.id} value={j.id}>
                {j.job_number} — PO: {j.po_number || '-'} ({j.progress_pct || 0}% selesai){j.child_job_count > 0 ? ` • +${j.child_job_count} child` : ''}
              </option>
            ))}
          </SmartNativeSelect>
        )}
      </div>

      {selectedJob && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm">
          <div className="flex justify-between items-center">
            <span className="font-semibold text-blue-700">{selectedJob.job_number} — PO: {selectedJob.po_number || '-'}</span>
            <span className="text-xs text-blue-600">Status: {selectedJob.status}</span>
          </div>
          <div className="mt-2"><MiniBar pct={selectedJob.progress_pct || 0} /></div>
          <p className="text-xs text-blue-600 mt-1">
            Total tersedia: {(selectedJob.total_available || 0).toLocaleString('id-ID')} pcs • Diproduksi: {(selectedJob.total_produced || 0).toLocaleString('id-ID')} pcs
          </p>
        </div>
      )}

      {/* PARENT JOB ITEMS */}
      {selectedJob && (
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-border/60 bg-muted/40">
            <h3 className="font-semibold text-foreground/90 text-sm">Item Produksi — Job Utama ({selectedJob?.job_number})</h3>
          </div>
          {renderItemsTable(jobItems, false)}
        </div>
      )}

      {/* CHILD JOBS */}
      {childJobs.length > 0 && (
        <div className="space-y-3">
          <div className="bg-purple-50 border border-purple-200 rounded-xl p-3">
            <p className="text-sm font-semibold text-purple-700 mb-2">Child Jobs — Shipment Tambahan/Pengganti</p>
            <div className="flex gap-2 flex-wrap">
              {childJobs.map(child => (
                <button key={child.id}
                  onClick={() => loadChildJobItems(selectedChildJobId === child.id ? '' : child.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${selectedChildJobId === child.id ? 'bg-purple-600 text-white border-purple-600' : 'border-purple-300 text-purple-700 hover:bg-purple-100'}`}>
                  {child.job_number} ({child.shipment_type})
                </button>
              ))}
            </div>
          </div>
          {childJobItems.length > 0 && (
            <div className="bg-card rounded-xl border border-purple-200 shadow-sm overflow-hidden ml-6">
              <div className="px-4 py-3 border-b border-purple-100 bg-purple-50">
                <h3 className="font-semibold text-purple-700 text-sm">
                  Child Job: {childJobs.find(c => c.id === selectedChildJobId)?.job_number}
                </h3>
              </div>
              {renderItemsTable(childJobItems, true)}
            </div>
          )}
        </div>
      )}

      {/* Progress Input Modal */}
      {showModal && selectedItem && (
        <Modal title={`Input Progress: ${selectedItem.sku || selectedItem.product_name}`} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-muted/40 rounded-xl p-3 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Info Item</p>
              {[
                ['Serial / Batch', selectedItem.serial_number || '-'],
                ['Produk', selectedItem.product_name],
                ['SKU', selectedItem.sku || '-'],
                ['Artikel Buyer', selectedItem.buyer_ref_code || '—'],
                ['Size', selectedItem.size || '-'],
                ['Warna', selectedItem.color || '-'],
                ['Material Tersedia', `${selectedItem.available_qty ?? selectedItem.shipment_qty ?? 0} pcs`],
                ['Sudah Diproduksi', `${selectedItem.produced_qty || 0} pcs`],
                ['Sisa (Maks Input)', `${maxInput(selectedItem)} pcs`],
              ].map(([l, v]) => (
                <div key={l} className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{l}</span>
                  <span className={`font-semibold ${l === 'Sisa (Maks Input)' ? 'text-orange-600' : 'text-foreground'}`}>{v}</span>
                </div>
              ))}
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal Progress *</label>
              <input required type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.progress_date} onChange={e => setForm(f => ({ ...f, progress_date: e.target.value }))} />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">
                Jumlah Selesai Hari Ini (pcs) * <span className="text-xs text-muted-foreground/70">maks: {maxInput(selectedItem)} pcs</span>
              </label>
              <input required type="number" min="1" max={maxInput(selectedItem)}
                data-testid="progress-qty-input"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-right"
                value={form.completed_quantity}
                onChange={e => setForm(f => ({ ...f, completed_quantity: e.target.value }))}
                placeholder={`0 – ${maxInput(selectedItem)}`} />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan</label>
              <textarea rows="2" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Catatan produksi..." />
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={saving} data-testid="save-progress-btn"
                className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                {saving ? 'Menyimpan...' : 'Simpan Progress'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
