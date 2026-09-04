import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, X, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import { apiGet, apiPost } from '../../../lib/api';

export default function VendorVarianceReport({ token, user }) {
  const [variances, setVariances] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    job_id: '',
    variance_type: 'OVERPRODUCTION',
    reason: '',
    notes: '',
    items: []
  });

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [vData, jData] = await Promise.all([
        apiGet('/production-variances'),
        apiGet('/production-jobs'),
      ]);
      setVariances(Array.isArray(vData) ? vData : []);
      setJobs(Array.isArray(jData) ? jData : []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const openCreate = () => {
    setForm({ job_id: '', variance_type: 'OVERPRODUCTION', reason: '', notes: '', items: [] });
    setShowModal(true);
  };

  const handleJobChange = async (jobId) => {
    setForm(prev => ({ ...prev, job_id: jobId, items: [] }));
    if (!jobId) return;
    try {
      const data = await apiGet(`/production-jobs/${jobId}`);
      const items = (data.items || []).map(ji => ({
        job_item_id: ji.id,
        product_name: ji.product_name,
        sku: ji.sku,
        size: ji.size,
        color: ji.color,
        ordered_qty: ji.ordered_qty || 0,
        produced_qty: ji.produced_qty || 0,
        variance_qty: 0
      }));
      setForm(prev => ({ ...prev, items }));
    } catch (e) { console.error(e); }
  };

  const updateItemVariance = (index, value) => {
    setForm(prev => {
      const items = [...prev.items];
      items[index].variance_qty = parseInt(value) || 0;
      return { ...prev, items };
    });
  };

  const submit = async () => {
    if (!form.job_id || !form.variance_type || !form.reason) {
      toast.error('Job, Tipe Variance, dan Alasan wajib diisi');
      return;
    }
    const itemsWithVariance = form.items.filter(i => i.variance_qty > 0);
    if (itemsWithVariance.length === 0) {
      toast.error('Harap input variance qty untuk minimal 1 item');
      return;
    }
    try {
      await apiPost('/production-variances', { ...form, items: itemsWithVariance });
      toast.success('Laporan variance berhasil disimpan');
      setShowModal(false);
      fetchAll();
    } catch (err) {
      toast.error(`Gagal: ${err.message || 'Unknown error'}`);
    }
  };

  const getTypeBadge = (type) => {
    return type === 'OVERPRODUCTION' 
      ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700">Over</span>
      : <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Under</span>;
  };

  const getStatusBadge = (status) => {
    const cfg = {
      'Reported': 'bg-yellow-100 text-yellow-700',
      'Acknowledged': 'bg-blue-100 text-blue-700',
      'Resolved': 'bg-green-100 text-green-700'
    };
    return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cfg[status] || 'bg-gray-100 text-gray-700'}`}>{status}</span>;
  };

  if (loading) return <div className="p-8">Loading...</div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Laporan Variance Produksi</h2>
          <p className="text-sm text-muted-foreground">Laporkan overproduction atau underproduction</p>
        </div>
        <button onClick={openCreate} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2">
          <Plus className="w-4 h-4" /> Buat Laporan
        </button>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-card p-4 rounded-lg border border-border">
          <p className="text-xs text-muted-foreground mb-1">Total Laporan</p>
          <p className="text-2xl font-bold text-foreground">{variances.length}</p>
        </div>
        <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
          <p className="text-xs text-orange-600 mb-1">Overproduction</p>
          <p className="text-2xl font-bold text-orange-700">{variances.filter(v => v.variance_type === 'OVERPRODUCTION').length}</p>
        </div>
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <p className="text-xs text-blue-600 mb-1">Underproduction</p>
          <p className="text-2xl font-bold text-blue-700">{variances.filter(v => v.variance_type === 'UNDERPRODUCTION').length}</p>
        </div>
      </div>

      {/* Variance List */}
      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <table className="w-full">
          <thead className="bg-muted/40 border-b border-border">
            <tr>
              {['No. Job', 'No. PO', 'Type', 'Total Variance (pcs)', 'Alasan', 'Status', 'Tanggal'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-foreground/90">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variances.map(v => (
              <tr key={v.id} className="border-b border-border/60 hover:bg-muted/60">
                <td className="px-4 py-3 text-sm">{v.job_number}</td>
                <td className="px-4 py-3 text-sm">{v.po_number}</td>
                <td className="px-4 py-3">{getTypeBadge(v.variance_type)}</td>
                <td className="px-4 py-3 text-sm font-medium text-foreground">{v.total_variance_qty}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">{v.reason}</td>
                <td className="px-4 py-3">{getStatusBadge(v.status)}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground">{new Date(v.created_at).toLocaleDateString('id-ID')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {variances.length === 0 && (
          <div className="p-8 text-center text-muted-foreground">
            <AlertTriangle className="w-12 h-12 mx-auto mb-2 text-muted-foreground/50" />
            <p>Belum ada laporan variance</p>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-card border-b border-border px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-bold text-foreground">Buat Laporan Variance</h3>
              <button onClick={() => setShowModal(false)} className="text-muted-foreground/70 hover:text-muted-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              {/* Job Selection */}
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Pilih Job Produksi</label>
                <SmartNativeSelect value={form.job_id} onChange={(e) => handleJobChange(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg">
                  <option value="">-- Pilih Job --</option>
                  {jobs.map(j => (
                    <option key={j.id} value={j.id}>{j.job_number} | PO: {j.po_number}</option>
                  ))}
                </SmartNativeSelect>
              </div>

              {/* Variance Type */}
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tipe Variance</label>
                <select value={form.variance_type} onChange={(e) => setForm({ ...form, variance_type: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg">
                  <option value="OVERPRODUCTION">Overproduction (Produksi Lebih)</option>
                  <option value="UNDERPRODUCTION">Underproduction (Produksi Kurang)</option>
                </select>
              </div>

              {/* Reason */}
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Alasan *</label>
                <textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg" rows={2}
                  placeholder="Jelaskan alasan variance (contoh: Material surplus/defisit, permintaan mendadak)"></textarea>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan Tambahan</label>
                <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg" rows={2}
                  placeholder="Catatan internal (opsional)"></textarea>
              </div>

              {/* Items Table */}
              {form.items.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-foreground/90 mb-2">Item Produksi - Input Variance Qty</label>
                  <div className="border border-border rounded-lg overflow-hidden">
                    <table className="w-full">
                      <thead className="bg-muted/40">
                        <tr>
                          {['Produk', 'SKU', 'Size', 'Color', 'Dipesan', 'Diproduksi', 'Variance Qty'].map(h => (
                            <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-foreground/90">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {form.items.map((item, idx) => (
                          <tr key={idx} className="border-t border-border/60">
                            <td className="px-3 py-2 text-sm">{item.product_name}</td>
                            <td className="px-3 py-2 text-sm">{item.sku}</td>
                            <td className="px-3 py-2 text-sm">{item.size}</td>
                            <td className="px-3 py-2 text-sm">{item.color}</td>
                            <td className="px-3 py-2 text-sm">{item.ordered_qty}</td>
                            <td className="px-3 py-2 text-sm">{item.produced_qty}</td>
                            <td className="px-3 py-2">
                              <input type="number" min="0" value={item.variance_qty}
                                onChange={(e) => updateItemVariance(idx, e.target.value)}
                                className="w-24 px-2 py-1 border border-border rounded text-sm" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <div className="sticky bottom-0 bg-muted/40 border-t border-border px-6 py-4 flex justify-end gap-2">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 bg-card border border-border text-foreground/90 rounded-lg hover:bg-muted/60">
                Batal
              </button>
              <button onClick={submit} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                Simpan Laporan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


