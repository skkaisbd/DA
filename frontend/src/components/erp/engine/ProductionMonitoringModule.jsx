
import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, ChevronDown, ChevronRight, Filter, TrendingUp, AlertTriangle, CheckCircle, Clock, BarChart2, Package } from 'lucide-react';
import StatusBadge from './StatusBadge';
import StaffEntryBadge from './StaffEntryBadge';
import { BizBadge } from './BusinessTypeBadge';
import { apiGet } from '../../../lib/api';

function PerformanceBadge({ performance }) {
  const cfg = {
    'On Track': { cls: 'bg-emerald-100 text-emerald-700 border border-emerald-200', icon: <CheckCircle className="w-3.5 h-3.5" />, label: 'On Track' },
    'At Risk':  { cls: 'bg-amber-100 text-amber-700 border border-amber-200',   icon: <Clock className="w-3.5 h-3.5" />,          label: 'At Risk' },
    'Overdue':  { cls: 'bg-red-100 text-red-700 border border-red-200',         icon: <AlertTriangle className="w-3.5 h-3.5" />,   label: 'Overdue' },
  };
  const c = cfg[performance] || cfg['On Track'];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.cls}`}>
      {c.icon} {c.label}
    </span>
  );
}

function ProgressBar({ pct, performance }) {
  const color = performance === 'Overdue' ? 'bg-red-500' : performance === 'At Risk' ? 'bg-amber-500' : pct >= 100 ? 'bg-emerald-500' : 'bg-blue-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
        <div className={`h-2 rounded-full transition-all duration-500 ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="text-xs font-bold text-foreground/90 w-10 text-right">{pct}%</span>
    </div>
  );
}

export default function ProductionMonitoringModule({ token, portalId }) {
  // FASE IA-1 — pemisahan data per proses bisnis (Portal Produksi = internal, Maklon = maklon).
  const businessType = portalId === 'maklon' ? 'maklon' : portalId === 'production' ? 'internal' : null;
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState({});
  const [filterVendor, setFilterVendor] = useState('');
  const [filterPerformance, setFilterPerformance] = useState('');
  const [page, setPage] = useState({});

  const PAGE_SIZE = 5;

  useEffect(() => { fetchData(); }, [businessType]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      // FASE IA-1: path lama `/production-monitoring-v2` TIDAK PERNAH ADA di backend
      // (404 ⇒ layar selalu kosong tanpa pesan). SSOT baru: /api/production-tracking.
      const btq = businessType ? `?business_type=${businessType}` : '';
      const json = await apiGet(`/production-tracking${btq}`);
      setData(Array.isArray(json) ? json : []);
    } catch (e) {
      console.error(e);
      // Jangan menelan error jadi "tidak ada data" — itu penyakit versi sebelumnya.
      setError(e?.message || 'Gagal memuat data tracking produksi');
      setData([]);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (vendorId) => {
    setExpanded(prev => ({ ...prev, [vendorId]: !prev[vendorId] }));
  };

  const filtered = data.filter(v => {
    if (filterVendor && v.vendor_id !== filterVendor) return false;
    if (filterPerformance && v.performance !== filterPerformance) return false;
    return true;
  });

  const getPage = (vid) => page[vid] || 0;
  const setVendorPage = (vid, p) => setPage(prev => ({ ...prev, [vid]: p }));

  // Use correct field names from API: total_jobs, total_produced, jobs_by_status, jobs
  const totalStats = {
    vendors: filtered.length,
    totalJobs: filtered.reduce((s, v) => s + (v.total_jobs || 0), 0),
    totalQty: filtered.reduce((s, v) => s + (v.total_qty || 0), 0),
    totalProduced: filtered.reduce((s, v) => s + (v.total_produced || 0), 0),
    totalShipped: filtered.reduce((s, v) => s + (v.total_shipped_to_buyer || 0), 0),
    overdue: filtered.filter(v => v.performance === 'Overdue').length,
    atRisk: filtered.filter(v => v.performance === 'At Risk').length,
  };
  const overallPct = totalStats.totalQty > 0 ? Math.round((totalStats.totalProduced / totalStats.totalQty) * 100) : 0;

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const fmtNum = (n) => (n || 0).toLocaleString('id-ID');

  return (
    <div className="space-y-6" data-testid="prod-tracking-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            Tracking Produksi
            {businessType && <BizBadge type={businessType} />}
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Pantau progres Production Jobs per pelaksana secara real-time
            {businessType && (
              <span className="ml-1 font-medium text-foreground/80">
                — data <strong>{businessType === 'maklon' ? 'Produksi Maklon (CMT)' : 'Produksi Internal'}</strong> saja.
              </span>
            )}
          </p>
        </div>
        <button onClick={fetchData} data-testid="prod-tracking-refresh" className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-muted/60">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div
          className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
          data-testid="prod-tracking-error"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Gagal memuat data</p>
            <p className="text-xs mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Overall Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        {[
          { label: 'Vendor Aktif', value: totalStats.vendors, cls: 'text-blue-700', bg: 'bg-blue-50' },
          { label: 'Prod. Jobs', value: fmtNum(totalStats.totalJobs), cls: 'text-foreground/90', bg: 'bg-muted/40' },
          { label: 'Total Qty', value: fmtNum(totalStats.totalQty), cls: 'text-foreground/90', bg: 'bg-muted/40' },
          { label: 'Diproduksi', value: fmtNum(totalStats.totalProduced), cls: 'text-emerald-700', bg: 'bg-emerald-50' },
          { label: 'Overdue', value: totalStats.overdue, cls: 'text-red-700', bg: 'bg-red-50' },
          { label: 'At Risk', value: totalStats.atRisk, cls: 'text-amber-700', bg: 'bg-amber-50' },
        ].map(s => (
          <div key={s.label} className={`${s.bg} rounded-xl p-3 border border-transparent`}>
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className={`text-xl font-bold mt-0.5 ${s.cls}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Overall Progress */}
      <div className="bg-card rounded-xl border border-border p-4 shadow-sm">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-semibold text-foreground/90 text-sm">Progress Keseluruhan</h3>
          <span className="text-sm font-bold text-blue-700">
            {fmtNum(totalStats.totalProduced)} / {fmtNum(totalStats.totalQty)} pcs ({overallPct}%)
          </span>
        </div>
        <div className="w-full bg-muted rounded-full h-3">
          <div
            className={`h-3 rounded-full transition-all duration-500 ${overallPct >= 100 ? 'bg-emerald-500' : 'bg-gradient-to-r from-blue-500 to-emerald-500'}`}
            style={{ width: `${Math.min(100, overallPct)}%` }}
          />
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <SmartNativeSelect
          value={filterVendor}
          onChange={e => { setFilterVendor(e.target.value); setExpanded({}); }}
          className="border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Semua Vendor</option>
          {data.map(v => <option key={v.vendor_id} value={v.vendor_id}>{v.vendor_name}</option>)}
        </SmartNativeSelect>
        <select
          value={filterPerformance}
          onChange={e => setFilterPerformance(e.target.value)}
          className="border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Semua Performa</option>
          <option value="On Track">On Track</option>
          <option value="At Risk">At Risk</option>
          <option value="Overdue">Overdue</option>
        </select>
        {(filterVendor || filterPerformance) && (
          <button onClick={() => { setFilterVendor(''); setFilterPerformance(''); }} className="text-xs text-muted-foreground/70 hover:text-muted-foreground underline">
            Reset Filter
          </button>
        )}
        <span className="ml-auto text-xs text-muted-foreground/70">{filtered.length} vendor ditampilkan</span>
      </div>

      {/* Vendor Cards */}
      {loading ? (
        <div className="text-center py-16 text-muted-foreground/70">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3" />
          <p>Memuat data monitoring...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="mx-auto max-w-xl py-14 text-center" data-testid="prod-tracking-empty">
          <BarChart2 className="mx-auto mb-3 h-12 w-12 opacity-30" />
          <p className="font-medium text-foreground">Belum ada Production Job untuk dipantau</p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Layar ini membaca <span className="font-mono text-xs">production_jobs</span> —
            yaitu perintah kerja nyata ke pelaksana. Jadi <strong>PO yang baru dibuat memang belum
            muncul di sini</strong>: PO harus <strong>dikonfirmasi</strong> dulu, lalu
            <strong> didistribusi</strong> menjadi job
            {businessType === 'maklon' ? ' ke vendor CMT (Kirim Material CMT)' : ' ke produksi internal'}.
            Selama itu belum dilakukan, kosongnya layar ini benar — bukan data yang hilang.
          </p>
          <p className="mt-2 text-xs text-muted-foreground/70">
            Untuk melihat semua PO termasuk yang belum jalan, buka menu PO
            {businessType === 'maklon' ? ' Maklon' : ' Produksi'} atau Pusat Laporan → kategori{' '}
            {businessType === 'maklon' ? 'Maklon' : 'Produksi Internal DA'}.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(vendor => {
            const isExpanded = expanded[vendor.vendor_id];
            const jobs = vendor.jobs || [];
            const currentPage = getPage(vendor.vendor_id);
            const totalPages = Math.ceil(jobs.length / PAGE_SIZE);
            const pagedJobs = jobs.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

            return (
              <div key={vendor.vendor_id} className={`bg-card rounded-xl border shadow-sm overflow-hidden transition-all ${
                vendor.performance === 'Overdue' ? 'border-red-200' :
                vendor.performance === 'At Risk' ? 'border-amber-200' : 'border-border'
              }`}>
                {/* Card Header */}
                <button
                  onClick={() => toggleExpand(vendor.vendor_id)}
                  className="w-full flex items-center gap-4 p-4 hover:bg-muted/60 transition-colors text-left"
                >
                  <div className="flex-shrink-0">
                    {isExpanded ? <ChevronDown className="w-5 h-5 text-muted-foreground" /> : <ChevronRight className="w-5 h-5 text-muted-foreground" />}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-bold text-foreground">{vendor.vendor_name}</span>
                      <span className="text-xs text-muted-foreground/70 font-mono">{vendor.vendor_code}</span>
                      <PerformanceBadge performance={vendor.performance} />
                      {/* keputusan owner 3a — angka progress vendor ini sebagian/seluruhnya
                          diketik STAF DA (vendor tidak memakai sistem). Wajib kelihatan di
                          layar monitoring karena tagihan CMT dihitung dari angka ini. */}
                      <StaffEntryBadge
                        source={vendor.progress_entry_source}
                        by={vendor.staff_entered_by}
                        qty={vendor.staff_entered_progress_qty}
                        testId={`monitoring-entry-badge-${vendor.vendor_id}`}
                      />
                      {vendor.location && <span className="text-xs text-muted-foreground/70">📍 {vendor.location}</span>}
                    </div>
                    <div className="mt-2 max-w-xs">
                      <ProgressBar pct={vendor.progress_pct || 0} performance={vendor.performance} />
                    </div>
                  </div>

                  {/* Summary Stats */}
                  <div className="flex-shrink-0 flex items-center gap-6 mr-4">
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Jobs</p>
                      <p className="font-bold text-foreground">{vendor.total_jobs || 0}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Target</p>
                      <p className="font-bold text-foreground">{fmtNum(vendor.total_qty)}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Diproduksi</p>
                      <p className="font-bold text-emerald-700">{fmtNum(vendor.total_produced)}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Lolos QC</p>
                      <p className="font-bold text-emerald-700">{fmtNum(vendor.total_accepted)}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Reject</p>
                      <p className={`font-bold ${Number(vendor.total_reject || 0) > 0 ? 'text-red-700' : 'text-muted-foreground'}`}>
                        {fmtNum(vendor.total_reject)}
                        {Number(vendor.total_reject || 0) > 0 && (
                          <span className="block text-[10px] font-medium text-red-600">{vendor.reject_rate_pct || 0}%</span>
                        )}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Rework</p>
                      <p className={`font-bold ${Number(vendor.total_rework_open || 0) > 0 ? 'text-orange-700' : 'text-muted-foreground'}`}>{fmtNum(vendor.total_rework_open)}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Dikirim</p>
                      <p className="font-bold text-blue-700">{fmtNum(vendor.total_shipped_to_buyer)}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground/70">Progress</p>
                      <p className={`font-bold text-lg ${
                        vendor.performance === 'Overdue' ? 'text-red-600' :
                        vendor.performance === 'At Risk' ? 'text-amber-600' : 'text-blue-700'
                      }`}>{vendor.progress_pct || 0}%</p>
                    </div>
                  </div>
                </button>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t border-border/60">
                    {/* Job Status Sub-stats */}
                    <div className="grid grid-cols-3 gap-3 p-4 bg-muted/40 border-b border-border/60">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-amber-500"></div>
                        <span className="text-xs text-muted-foreground">Berjalan: <strong>{vendor.jobs_by_status?.in_progress || 0}</strong></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                        <span className="text-xs text-muted-foreground">Selesai: <strong>{vendor.jobs_by_status?.completed || 0}</strong></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                        <span className="text-xs text-muted-foreground">Total Dikirim: <strong>{fmtNum(vendor.total_shipped_to_buyer)} pcs</strong></span>
                      </div>
                    </div>

                    {/* Production Jobs Table */}
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="bg-muted/40 border-b border-border/60">
                          <tr>
                            {['', 'No. Job', 'No. PO', 'No. Seri', 'Deadline', 'Tersedia', 'Diproduksi', 'Lolos QC', 'Reject', 'Rework', 'Dikirim', 'Sisa', 'Progress', 'Status'].map(h => (
                              <th key={h} className={`whitespace-nowrap text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider ${h === 'No. Seri' ? 'text-amber-600' : h === 'Reject' ? 'text-red-600' : h === 'Rework' ? 'text-orange-600' : 'text-muted-foreground'}`}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40">
                          {pagedJobs.length === 0 ? (
                            <tr><td colSpan={14} className="text-center py-6 text-muted-foreground/70 text-sm">Tidak ada production job</td></tr>
                          ) : pagedJobs.map(job => {
                            const totalAvail = job.total_available || job.ordered_qty || 0;
                            const totalProduced = job.produced_qty || 0;
                            const totalShipped = job.shipped_qty || 0;
                            const remaining = Math.max(0, totalAvail - totalProduced);
                            const pct = totalAvail > 0 ? Math.round((totalProduced / totalAvail) * 100) : 0;
                            const isOverdue = job.deadline && new Date(job.deadline) < new Date() && job.status !== 'Completed';
                            const serialNums = job.serial_numbers || [];
                            const hasChildren = (job.child_jobs || []).length > 0;
                            const jobExpandKey = `job-${job.id}`;
                            const isJobExpanded = expanded[jobExpandKey];

                            return [
                              <tr key={job.id} className="hover:bg-muted/60">
                                <td className="px-4 py-3 w-8">
                                  {hasChildren && (
                                    <button onClick={() => setExpanded(prev => ({ ...prev, [jobExpandKey]: !prev[jobExpandKey] }))}
                                      className="w-5 h-5 rounded flex items-center justify-center hover:bg-muted text-muted-foreground text-xs">
                                      {isJobExpanded ? '▼' : '▶'}
                                    </button>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-sm font-bold text-blue-700">
                                  {job.job_number}
                                  {hasChildren && (
                                    <span className="ml-1.5 px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">+{job.child_jobs.length}</span>
                                  )}
                                  {(job.progress_entry_source === 'staff' || job.progress_entry_source === 'mixed'
                                    || job.job_entered_by_staff) && (
                                    <span className="mt-1 block">
                                      <StaffEntryBadge
                                        source={job.progress_entry_source === 'none' ? 'staff' : job.progress_entry_source}
                                        by={job.staff_entered_by}
                                        compact
                                        testId={`monitoring-job-entry-badge-${job.job_number}`}
                                      />
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{job.po_number || '-'}</td>
                                <td className="px-4 py-3">
                                  {serialNums.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {serialNums.map(sn => (
                                        <span key={sn} className="px-1.5 py-0.5 bg-amber-50 border border-amber-200 rounded text-xs font-mono text-amber-700 font-semibold">{sn}</span>
                                      ))}
                                    </div>
                                  ) : <span className="text-muted-foreground/50 text-xs">—</span>}
                                </td>
                                <td className="px-4 py-3 text-xs">
                                  <span className={isOverdue ? 'text-red-600 font-medium' : 'text-muted-foreground'}>{fmtDate(job.deadline || job.delivery_deadline)}</span>
                                </td>
                                <td className="px-4 py-3 text-sm font-medium text-blue-700">{fmtNum(totalAvail)}</td>
                                <td className="px-4 py-3 text-sm font-medium text-emerald-700">{fmtNum(totalProduced)}</td>
                                <td className="px-4 py-3 text-sm font-semibold text-emerald-700">{fmtNum(job.accepted_qty)}</td>
                                <td className={`px-4 py-3 text-sm font-semibold ${Number(job.reject_qty || 0) > 0 ? 'text-red-700' : 'text-muted-foreground'}`}>
                                  {fmtNum(job.reject_qty)}
                                  {Number(job.reject_qty || 0) > 0 && <span className="ml-1 text-[10px]">({job.reject_rate_pct || 0}%)</span>}
                                </td>
                                <td className={`px-4 py-3 text-sm font-semibold ${Number(job.rework_open_qty || 0) > 0 ? 'text-orange-700' : 'text-muted-foreground'}`}>{fmtNum(job.rework_open_qty)}</td>
                                <td className="px-4 py-3 text-sm font-medium text-blue-700">{fmtNum(totalShipped)}</td>
                                <td className="px-4 py-3 text-sm font-medium text-orange-600">{fmtNum(remaining)}</td>
                                <td className="px-4 py-3 w-36">
                                  <div className="flex items-center gap-1.5">
                                    <div className="flex-1 bg-muted rounded-full h-1.5">
                                      <div className={`h-1.5 rounded-full ${pct >= 100 ? 'bg-emerald-500' : pct >= 50 ? 'bg-blue-500' : pct >= 25 ? 'bg-amber-500' : 'bg-red-400'}`}
                                        style={{ width: `${Math.min(100, pct)}%` }} />
                                    </div>
                                    <span className="text-xs font-medium text-muted-foreground w-8 text-right">{pct}%</span>
                                  </div>
                                </td>
                                <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                              </tr>,
                              /* Child job rows */
                              ...(isJobExpanded && hasChildren ? job.child_jobs.map(child => (
                                <tr key={`child-${child.id}`} className="bg-purple-50/30 hover:bg-purple-50/50">
                                  <td className="px-4 py-2.5"></td>
                                  <td className="px-4 py-2.5 pl-8">
                                    <div className="flex items-center gap-2">
                                      <div className="w-3 h-px bg-purple-300 mr-1" />
                                      <span className="font-bold text-purple-700 text-sm">{child.job_number}</span>
                                      <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${child.shipment_type === 'ADDITIONAL' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                                        {child.shipment_type}
                                      </span>
                                    </div>
                                  </td>
                                  <td colSpan={11} className="px-4 py-2.5 text-xs text-muted-foreground">
                                    <span className={`px-2 py-0.5 rounded-full text-xs ${child.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground'}`}>{child.status}</span>
                                  </td>
                                  <td className="px-4 py-2.5"></td>
                                </tr>
                              )) : [])
                            ];
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 border-t border-border/60">
                        <span className="text-xs text-muted-foreground">
                          Menampilkan {currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, jobs.length)} dari {jobs.length} job
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setVendorPage(vendor.vendor_id, currentPage - 1)}
                            disabled={currentPage === 0}
                            className="px-2 py-1 text-xs border border-border rounded hover:bg-card disabled:opacity-40"
                          >←</button>
                          {Array.from({ length: totalPages }, (_, i) => (
                            <button
                              key={i}
                              onClick={() => setVendorPage(vendor.vendor_id, i)}
                              className={`px-2 py-1 text-xs border rounded ${i === currentPage ? 'bg-blue-600 text-white border-blue-600' : 'border-border hover:bg-card'}`}
                            >{i + 1}</button>
                          ))}
                          <button
                            onClick={() => setVendorPage(vendor.vendor_id, currentPage + 1)}
                            disabled={currentPage >= totalPages - 1}
                            className="px-2 py-1 text-xs border border-border rounded hover:bg-card disabled:opacity-40"
                          >→</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
