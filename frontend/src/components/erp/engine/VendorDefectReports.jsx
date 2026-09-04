import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, AlertOctagon, X } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import { apiGet, apiPost } from '../../../lib/api';

export default function VendorDefectReports({ token, user }) {
  const [reports, setReports] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [jobItems, setJobItems] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    job_id: '', job_item_id: '', sku: '', product_name: '', size: '', color: '',
    defect_qty: '', defect_type: 'Material Cacat',
    description: '', report_date: new Date().toISOString().split('T')[0],
    shipment_id: ''
  });

  const DEFECT_TYPES = ['Material Cacat', 'Jahitan Longgar', 'Warna Pudar', 'Ukuran Tidak Sesuai', 'Material Robek', 'Noda/Kotor', 'Lainnya'];

  useEffect(() => { fetchReports(); fetchJobs(); fetchShipments(); }, []);

  const fetchReports = async () => {
    try {
      const data = await apiGet('/material-defect-reports');
      setReports(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const fetchJobs = async () => {
    try {
      const data = await apiGet('/production-jobs');
      setJobs(Array.isArray(data) ? data.filter(j => j.status === 'In Progress') : []);
    } catch (e) { console.error(e); }
  };

  const fetchShipments = async () => {
    try {
      const data = await apiGet('/vendor-shipments');
      setShipments(Array.isArray(data) ? data.filter(s => s.status === 'Received') : []);
    } catch (e) { console.error(e); }
  };

  const handleJobSelect = async (jobId) => {
    setForm(f => ({ ...f, job_id: jobId, job_item_id: '', sku: '', product_name: '', size: '', color: '' }));
    if (!jobId) { setJobItems([]); return; }
    try {
      const data = await apiGet(`/production-job-items?job_id=${jobId}`);
      setJobItems(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const handleItemSelect = (itemId) => {
    const item = jobItems.find(i => i.id === itemId);
    setForm(f => ({
      ...f, job_item_id: itemId,
      sku: item?.sku || '', product_name: item?.product_name || '',
      size: item?.size || '', color: item?.color || ''
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await apiPost('/material-defect-reports', { ...form, defect_qty: Number(form.defect_qty) });
      setShowModal(false);
      fetchReports();

      // Auto-prompt to create Replacement Request
      const confirmReplace = window.confirm(
        `✅ Laporan cacat berhasil disimpan!\n\nDitemukan ${form.defect_qty} pcs material CACAT.\nApakah Anda ingin mengajukan Permintaan Material Pengganti kepada ERP?`
      );
      if (confirmReplace && form.shipment_id) {
        try {
          const reqData = await apiPost('/material-requests', {
            request_type: 'REPLACEMENT',
            original_shipment_id: form.shipment_id,
            defect_report_id: data.id,
            reason: `Material cacat: ${form.defect_type} — ${form.description}`,
            items: [{
              sku: form.sku, product_name: form.product_name, size: form.size, color: form.color,
              serial_number: '', requested_qty: Number(form.defect_qty),
              reason: `${form.defect_type}: ${form.description}`
            }]
          });
          toast.success(`Permintaan Pengganti ${reqData.request_number} berhasil diajukan ke ERP`);
        } catch (reqErr) {
          toast.error(`Gagal mengajukan permintaan: ${reqErr.message}`);
        }
      } else if (confirmReplace && !form.shipment_id) {
        toast.error('Pilih Shipment Asal terlebih dahulu untuk mengajukan permintaan pengganti.');
      }
    } catch (err) {
      toast.error(err.message || 'Gagal menyimpan laporan');
    } finally {
      setLoading(false);
    }
  };

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <AlertOctagon className="w-6 h-6 text-red-600" />
            Laporan Cacat Material
          </h1>
          <p className="text-muted-foreground text-sm mt-1">Laporkan material atau produk yang cacat/rusak selama produksi</p>
        </div>
        <button onClick={() => setShowModal(true)} className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700">
          <Plus className="w-4 h-4" /> Buat Laporan Cacat
        </button>
      </div>

      {/* Reports List */}
      {reports.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/70 text-sm">Belum ada laporan cacat</div>
      ) : (
        <div className="space-y-2">
          {reports.map(r => (
            <div key={r.id} className="bg-card border border-border rounded-xl p-4 flex items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-foreground">{r.product_name}</span>
                  {r.sku && <span className="text-xs font-mono text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">{r.sku}</span>}
                  <span className="text-xs text-muted-foreground/70">{r.size}/{r.color}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Cacat: <span className="text-red-600 font-medium">{r.defect_qty} pcs</span> •
                  Tipe: {r.defect_type} •
                  Tanggal: {fmtDate(r.report_date)} •
                  Oleh: {r.reported_by}
                </p>
                {r.description && <p className="text-xs text-muted-foreground/70 mt-0.5">{r.description}</p>}
              </div>
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${r.status === 'Reported' ? 'bg-red-100 text-red-700' : 'bg-muted text-muted-foreground'}`}>
                {r.status}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Create Defect Report Modal */}
      {showModal && (
        <Modal title="Buat Laporan Cacat Material" onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              Laporan cacat akan diteruskan ke tim ERP. Jika material perlu diganti, sistem akan membantu Anda mengajukan permintaan pengganti.
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Shipment Asal <span className="text-xs text-muted-foreground/70">(diperlukan untuk permintaan pengganti)</span></label>
              <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-card"
                value={form.shipment_id} onChange={e => setForm(f => ({ ...f, shipment_id: e.target.value }))}>
                <option value="">— Pilih Shipment Asal (opsional) —</option>
                {shipments.map(s => <option key={s.id} value={s.id}>{s.shipment_number} — {fmtDate(s.shipment_date)}</option>)}
              </SmartNativeSelect>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Pekerjaan Produksi</label>
                <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 bg-card"
                  value={form.job_id} onChange={e => handleJobSelect(e.target.value)}>
                  <option value="">— Pilih Job (opsional) —</option>
                  {jobs.map(j => <option key={j.id} value={j.id}>{j.job_number} — {j.po_number}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Item Spesifik</label>
                <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 bg-card"
                  value={form.job_item_id} onChange={e => handleItemSelect(e.target.value)} disabled={!form.job_id}>
                  <option value="">— Pilih Item (opsional) —</option>
                  {jobItems.map(i => <option key={i.id} value={i.id}>{i.sku || i.product_name} ({i.size}/{i.color})</option>)}
                </SmartNativeSelect>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Nama Produk *</label>
                <input required className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.product_name} onChange={e => setForm(f => ({ ...f, product_name: e.target.value }))} placeholder="Nama Produk" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">SKU</label>
                <input className="w-full border border-border rounded-lg px-3 py-2 text-sm font-mono" value={form.sku} onChange={e => setForm(f => ({ ...f, sku: e.target.value }))} placeholder="PRD-BLK-M" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Size</label>
                <input className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.size} onChange={e => setForm(f => ({ ...f, size: e.target.value }))} placeholder="M" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Warna</label>
                <input className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} placeholder="Hitam" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Qty Cacat *</label>
                <input required type="number" min="1" className="w-full border border-red-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-red-400" value={form.defect_qty} onChange={e => setForm(f => ({ ...f, defect_qty: e.target.value }))} placeholder="5" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Jenis Cacat *</label>
                <select required className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-card" value={form.defect_type} onChange={e => setForm(f => ({ ...f, defect_type: e.target.value }))}>
                  {DEFECT_TYPES.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal Laporan</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.report_date} onChange={e => setForm(f => ({ ...f, report_date: e.target.value }))} />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Deskripsi / Detail Cacat</label>
              <textarea rows="3" className="w-full border border-border rounded-lg px-3 py-2 text-sm" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Jelaskan detail kerusakan atau cacat yang ditemukan..." />
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={loading} className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50">
                {loading ? 'Menyimpan...' : 'Kirim Laporan Cacat'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}


// ─── VENDOR SERIAL TRACKING ──────────────────────────────────────────────────


