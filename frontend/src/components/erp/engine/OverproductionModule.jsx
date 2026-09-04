import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, Filter, TrendingUp, TrendingDown, AlertTriangle, X, Eye, CheckCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch, apiGet, apiPut } from '../../../lib/api';

export default function OverproductionModule({ token, portalId }) {
  // FASE IA-1 — pemisahan data per proses bisnis (Portal Produksi = internal, Maklon = maklon).
  const businessType = portalId === 'maklon' ? 'maklon' : portalId === 'production' ? 'internal' : null;
  const [variances, setVariances] = useState([]);
  const [stats, setStats] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Filters
  const [filterType, setFilterType] = useState('');
  const [filterVendor, setFilterVendor] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterFrom, setFilterFrom] = useState('');
  const [filterTo, setFilterTo] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Detail modal
  const [selectedVariance, setSelectedVariance] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [statusForm, setStatusForm] = useState({ status: '', admin_notes: '' });

  useEffect(() => { fetchAll(); }, [businessType]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchAll = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (businessType) params.append('business_type', businessType);
      if (filterType) params.append('variance_type', filterType);
      if (filterVendor) params.append('vendor_id', filterVendor);
      if (filterStatus) params.append('status', filterStatus);
      if (filterFrom) params.append('from', filterFrom);
      if (filterTo) params.append('to', filterTo);
      if (searchQuery) params.append('search', searchQuery);
      
      const [vData, sData, vendorData] = await Promise.all([
        apiGet(`/production-variances?${params}`),
        apiGet(`/production-variances/stats?${params}`),
        apiGet('/garments'),
      ]);
      
      setVariances(Array.isArray(vData) ? vData : []);
      setStats(sData);
      setVendors(Array.isArray(vendorData) ? vendorData : []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const openDetail = (variance) => {
    setSelectedVariance(variance);
    setStatusForm({ status: variance.status, admin_notes: variance.admin_notes || '' });
    setShowDetail(true);
  };

  const updateStatus = async () => {
    if (!statusForm.status) {
      toast.error('Status wajib diisi');
      return;
    }
    try {
      await apiPut(`/production-variances/${selectedVariance.id}`, statusForm);
      toast.success('Status variance berhasil diupdate');
      setShowDetail(false);
      fetchAll();
    } catch (err) {
      toast.error(err.message || 'Gagal update status');
    }
  };

  const getTypeBadge = (type) => {
    return type === 'OVERPRODUCTION' 
      ? <span className="px-2 py-1 rounded-lg text-sm font-medium bg-orange-100 text-orange-700 flex items-center gap-1">
          <TrendingUp className="w-4 h-4" /> Overproduction
        </span>
      : <span className="px-2 py-1 rounded-lg text-sm font-medium bg-blue-100 text-blue-700 flex items-center gap-1">
          <TrendingDown className="w-4 h-4" /> Underproduction
        </span>;
  };

  const getStatusBadge = (status) => {
    const cfg = {
      'Reported': { bg: 'bg-yellow-100', text: 'text-yellow-700', icon: <AlertTriangle className="w-3.5 h-3.5" /> },
      'Acknowledged': { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Clock className="w-3.5 h-3.5" /> },
      'Resolved': { bg: 'bg-green-100', text: 'text-green-700', icon: <CheckCircle className="w-3.5 h-3.5" /> }
    };
    const c = cfg[status] || cfg['Reported'];
    return <span className={`px-2 py-1 rounded-lg text-sm font-medium ${c.bg} ${c.text} flex items-center gap-1`}>
      {c.icon} {status}
    </span>;
  };

  const fmtNum = (n) => (n || 0).toLocaleString('id-ID');
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';

  if (loading) return <div className="p-8">Loading...</div>;

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Laporan Variance</h2>
          <p className="text-sm text-muted-foreground">
            Selisih produksi (over/under) terhadap target
            {businessType && (
              <span className="ml-1 font-medium text-foreground/80">
                — data <strong>{businessType === 'maklon' ? 'Produksi Maklon (CMT)' : 'Produksi Internal'}</strong> saja.
              </span>
            )}
          </p>
        </div>
        <button onClick={fetchAll} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Statistics Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-card p-5 rounded-xl border border-border shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-muted-foreground font-medium">Total Laporan</p>
              <AlertTriangle className="w-5 h-5 text-muted-foreground/70" />
            </div>
            <p className="text-3xl font-bold text-foreground">{fmtNum(stats.total_records)}</p>
          </div>
          
          <div className="bg-gradient-to-br from-orange-50 to-orange-100 p-5 rounded-xl border border-orange-200 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-orange-600 font-medium">Overproduction</p>
              <TrendingUp className="w-5 h-5 text-orange-500" />
            </div>
            <p className="text-3xl font-bold text-orange-700">{fmtNum(stats.overproduction.count)}</p>
            <p className="text-xs text-orange-600 mt-1">{fmtNum(stats.overproduction.total_qty)} pcs total</p>
          </div>
          
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-5 rounded-xl border border-blue-200 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-blue-600 font-medium">Underproduction</p>
              <TrendingDown className="w-5 h-5 text-blue-500" />
            </div>
            <p className="text-3xl font-bold text-blue-700">{fmtNum(stats.underproduction.count)}</p>
            <p className="text-xs text-blue-600 mt-1">{fmtNum(stats.underproduction.total_qty)} pcs total</p>
          </div>
          
          <div className="bg-gradient-to-br from-muted/40 to-muted p-5 rounded-xl border border-border shadow-sm">
            <p className="text-xs text-muted-foreground font-medium mb-2">Status Breakdown</p>
            <div className="space-y-1">
              {Object.entries(stats.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{status}:</span>
                  <span className="font-semibold text-foreground">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-card p-4 rounded-xl border border-border mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground/90">Filter</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm">
            <option value="">Semua Tipe</option>
            <option value="OVERPRODUCTION">Overproduction</option>
            <option value="UNDERPRODUCTION">Underproduction</option>
          </select>
          
          <SmartNativeSelect value={filterVendor} onChange={(e) => setFilterVendor(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm">
            <option value="">Semua Vendor</option>
            {vendors.map(v => (
              <option key={v.id} value={v.id}>{v.garment_name}</option>
            ))}
          </SmartNativeSelect>
          
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm">
            <option value="">Semua Status</option>
            <option value="Reported">Reported</option>
            <option value="Acknowledged">Acknowledged</option>
            <option value="Resolved">Resolved</option>
          </select>
          
          <input type="date" value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm" placeholder="Dari Tanggal" />
          
          <input type="date" value={filterTo} onChange={(e) => setFilterTo(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm" placeholder="Sampai Tanggal" />
          
          <button onClick={fetchAll} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
            Terapkan
          </button>
        </div>
      </div>

      {/* Variance List */}
      <div className="bg-card rounded-xl border border-border overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                {['Vendor', 'No. Job', 'No. PO', 'Tipe', 'Total Variance', 'Alasan', 'Status', 'Tanggal', 'Aksi'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-foreground/90 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {variances.map(v => (
                <tr key={v.id} className="hover:bg-muted/60 transition-colors">
                  <td className="px-4 py-3 text-sm font-medium text-foreground">{v.vendor_name}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{v.job_number}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{v.po_number}</td>
                  <td className="px-4 py-3">{getTypeBadge(v.variance_type)}</td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-bold text-foreground">{fmtNum(v.total_variance_qty)}</span>
                    <span className="text-xs text-muted-foreground ml-1">pcs</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs">
                    <div className="truncate" title={v.reason}>{v.reason}</div>
                  </td>
                  <td className="px-4 py-3">{getStatusBadge(v.status)}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{fmtDate(v.created_at)}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => openDetail(v)} className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Lihat Detail">
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {variances.length === 0 && (
          <div className="p-12 text-center">
            <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-muted-foreground/50" />
            <p className="text-muted-foreground font-medium">Tidak ada data variance</p>
            <p className="text-sm text-muted-foreground/70 mt-1">Variance akan muncul ketika vendor melaporkan overproduction atau underproduction</p>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {showDetail && selectedVariance && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-card border-b border-border px-6 py-4 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-bold text-foreground">Detail Variance Report</h3>
                <p className="text-sm text-muted-foreground">Job: {selectedVariance.job_number} | PO: {selectedVariance.po_number}</p>
              </div>
              <button onClick={() => setShowDetail(false)} className="text-muted-foreground/70 hover:text-muted-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-6">
              {/* Variance Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Vendor</p>
                  <p className="font-medium text-foreground">{selectedVariance.vendor_name}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Tipe Variance</p>
                  {getTypeBadge(selectedVariance.variance_type)}
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Total Variance</p>
                  <p className="text-2xl font-bold text-foreground">{fmtNum(selectedVariance.total_variance_qty)} pcs</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Status Saat Ini</p>
                  {getStatusBadge(selectedVariance.status)}
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-muted-foreground mb-1">Alasan</p>
                  <p className="text-sm text-foreground/90 bg-muted/40 p-3 rounded-lg border border-border">{selectedVariance.reason}</p>
                </div>
                {selectedVariance.notes && (
                  <div className="col-span-2">
                    <p className="text-xs text-muted-foreground mb-1">Catatan Vendor</p>
                    <p className="text-sm text-foreground/90 bg-muted/40 p-3 rounded-lg border border-border">{selectedVariance.notes}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Dilaporkan Oleh</p>
                  <p className="text-sm text-foreground/90">{selectedVariance.reported_by}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Tanggal Laporan</p>
                  <p className="text-sm text-foreground/90">{fmtDate(selectedVariance.created_at)}</p>
                </div>
              </div>

              {/* Items Table */}
              {selectedVariance.items && selectedVariance.items.length > 0 && (
                <div>
                  <p className="text-sm font-semibold text-foreground/90 mb-2">Detail Item Variance</p>
                  <div className="border border-border rounded-lg overflow-hidden">
                    <table className="w-full">
                      <thead className="bg-muted/40">
                        <tr>
                          {['Produk', 'SKU', 'Size', 'Color', 'Dipesan', 'Diproduksi', 'Variance'].map(h => (
                            <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-foreground/90">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {selectedVariance.items.map((item, idx) => (
                          <tr key={idx}>
                            <td className="px-3 py-2 text-sm text-foreground/90">{item.product_name}</td>
                            <td className="px-3 py-2 text-sm text-muted-foreground">{item.sku}</td>
                            <td className="px-3 py-2 text-sm text-muted-foreground">{item.size}</td>
                            <td className="px-3 py-2 text-sm text-muted-foreground">{item.color}</td>
                            <td className="px-3 py-2 text-sm text-foreground/90">{fmtNum(item.ordered_qty)}</td>
                            <td className="px-3 py-2 text-sm text-foreground/90">{fmtNum(item.produced_qty)}</td>
                            <td className="px-3 py-2 text-sm font-bold text-foreground">{fmtNum(item.variance_qty)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Update Status Section */}
              <div className="border-t border-border pt-6">
                <p className="text-sm font-semibold text-foreground/90 mb-3">Update Status Variance</p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-foreground/90 mb-1">Status Baru *</label>
                    <select value={statusForm.status} onChange={(e) => setStatusForm({ ...statusForm, status: e.target.value })}
                      className="w-full px-3 py-2 border border-border rounded-lg">
                      <option value="Reported">Reported</option>
                      <option value="Acknowledged">Acknowledged (Diketahui)</option>
                      <option value="Resolved">Resolved (Diselesaikan)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan Admin</label>
                    <textarea value={statusForm.admin_notes} onChange={(e) => setStatusForm({ ...statusForm, admin_notes: e.target.value })}
                      className="w-full px-3 py-2 border border-border rounded-lg" rows={3}
                      placeholder="Catatan atau instruksi untuk vendor (opsional)"></textarea>
                  </div>
                </div>
              </div>
            </div>

            <div className="sticky bottom-0 bg-muted/40 border-t border-border px-6 py-4 flex justify-end gap-2">
              <button onClick={() => setShowDetail(false)} className="px-4 py-2 bg-card border border-border text-foreground/90 rounded-lg hover:bg-muted/60">
                Tutup
              </button>
              <button onClick={updateStatus} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                Update Status
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
