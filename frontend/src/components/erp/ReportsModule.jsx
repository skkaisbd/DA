
import { useState, useEffect, useCallback } from 'react';
import { Download, FileText, BarChart2, TrendingUp, CreditCard, Factory, Truck, RotateCcw, AlertTriangle, RefreshCw, Search, Filter, Calendar, ChevronDown, ChevronRight, Package, Building2, Boxes } from 'lucide-react';
import PaginationBar from './PaginationBar';
import { PdfColumnPicker } from './pdf/PdfColumnPicker';
import { formatRupiah } from '@/lib/format';

const REPORT_TYPES = [
  { id: 'production', label: 'Laporan Produksi', icon: Factory, description: 'PO + item + buku kuantitas (produksi/diterima/reject)', color: 'blue' },
  { id: 'per-po', label: 'Rekap per PO', icon: Boxes, description: 'Satu baris per PO: pesan, produksi, terima, kirim, nilai order', color: 'indigo' },
  { id: 'progress', label: 'Laporan Progres', icon: TrendingUp, description: 'Catatan progres produksi harian per job', color: 'emerald' },
  { id: 'financial', label: 'Laporan Keuangan', icon: CreditCard, description: 'Invoice AR: tagihan, terbayar, sisa piutang', color: 'purple' },
  { id: 'shipment', label: 'Laporan Pengiriman', icon: Truck, description: 'Surat jalan ke buyer + qty barang jadi keluar', color: 'amber' },
  { id: 'rework', label: 'Laporan Reject & Rework', icon: RotateCcw, description: 'Baris penerimaan CMT yang direject + tindak lanjut permak', color: 'red' },
  { id: 'material-issue', label: 'Permintaan Material', icon: AlertTriangle, description: 'Pengeluaran material dari gudang ke job', color: 'orange' },
  { id: 'per-client', label: 'Laporan per Klien Maklon', icon: Building2, description: 'KPI & HPP per klien maklon', color: 'cyan' },
];

/* Domain wajib dipisah (keputusan owner): produksi internal DA vs maklon. */
const DOMAIN_TABS = [
  { id: 'all', label: 'Gabungan' },
  { id: 'internal', label: 'Internal DA' },
  { id: 'maklon', label: 'Maklon' },
];

const fmt = formatRupiah;
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
const fmtNum = (v) => (v || 0).toLocaleString('id-ID');

export default function ReportsModule({ token }) {
  const [activeReport, setActiveReport] = useState('production');
  const [domain, setDomain] = useState('all');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  // Pagination state
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [pagination, setPagination] = useState(null); // {page, limit, total, total_pages, has_next, has_prev}

  // Filters
  const [filters, setFilters] = useState({
    date_from: '', date_to: '', status: ''
  });
  const [showFilters, setShowFilters] = useState(false);
  // W2 — dialog pemilih kolom PDF (per jenis laporan)
  const [pickerOpen, setPickerOpen] = useState(false);

  // Reset page when report type changes
  useEffect(() => {
    setPage(1);
    setPagination(null);
    fetchReport(1);
  }, [activeReport, domain]); // eslint-disable-line

  // When page changes, re-fetch
  useEffect(() => {
    fetchReport(page);
  }, [page]); // eslint-disable-line

  // 2026-08-06: 'per-po' dulu di-hardcode kosong di FE (setData([])) sehingga laporan
  // ini SELALU kosong. Sekarang dilayani backend SSOT seperti tipe lainnya.
  const PAGINATED_TYPES = ['production', 'per-po', 'progress', 'financial', 'shipment', 'rework', 'material-issue'];

  const fetchReport = useCallback(async (targetPage = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      params.set('domain', domain);

      let res;
      if (activeReport === 'per-client') {
        // Per Client report - fetch all clients with analysis
        res = await fetch(`/api/dewi/maklon/clients`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        const clients = await res.json();
        // Fetch analysis for each client (simplified - in production would batch this)
        const clientData = [];
        for (const client of clients.slice(0, 10)) { // limit to 10 for performance
          try {
            const analysisRes = await fetch(`/api/rahaza/hpp/maklon-client/${client.id}`, {
              headers: { Authorization: `Bearer ${token}` }
            });
            if (analysisRes.ok) {
              const analysis = await analysisRes.json();
              clientData.push({
                client_code: client.code,
                client_name: client.name,
                total_orders: analysis.total_orders,
                total_qty: analysis.total_qty,
                total_revenue: analysis.total_revenue,
                total_hpp: analysis.total_hpp_actual,
                margin: analysis.margin_amount,
                margin_pct: analysis.margin_pct,
                on_time_rate: analysis.on_time_rate,
              });
            }
          } catch (e) {
            // Skip failed client
          }
        }
        setData(clientData);
        setPagination(null);
      } else if (PAGINATED_TYPES.includes(activeReport)) {
        // Paginated reports
        params.set('page', targetPage);
        params.set('limit', limit);
        res = await fetch(`/api/rahaza/reports/${activeReport}?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        const result = await res.json();
        if (result && result.items && result.pagination) {
          setData(result.items);
          setPagination(result.pagination);
        } else {
          // Fallback: legacy response
          setData(Array.isArray(result) ? result : []);
          setPagination(null);
        }
      } else {
        res = await fetch(`/api/rahaza/reports/${activeReport}?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        const result = await res.json();
        setData(Array.isArray(result) ? result : []);
        setPagination(null);
      }
    } catch (e) {
      setData([]);
      setPagination(null);
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeReport, filters, token, limit, domain]);

  const handleFilter = () => {
    setPage(1);
    fetchReport(1);
  };

  const resetFilters = () => {
    setFilters({ date_from: '', date_to: '', status: '' });
  };

  // Excel export using server-side endpoint
  const exportToExcel = async () => {
    if (!data.length) return;
    try {
      const params = new URLSearchParams({ type: `report-${activeReport}` });
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      const res = await fetch(`/api/export-excel?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `laporan_${activeReport}_${new Date().toISOString().split('T')[0]}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        // Fallback to client-side export
        const XLSX = (await import('xlsx')).default || (await import('xlsx'));
        const colDefs = getColumns();
        const headers = colDefs.map(c => c.label);
        const rows = data.map(row => colDefs.map(c => {
          const val = row[c.key];
          if (c.format === 'date') return fmtDate(val);
          if (c.format === 'currency') return Number(val || 0);
          if (c.format === 'number') return Number(val || 0);
          return val ?? '';
        }));
        const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
        const colWidths = headers.map((h, i) => ({
          wch: Math.min(Math.max(h.length, ...rows.map(r => String(r[i] || '').length)) + 2, 30)
        }));
        ws['!cols'] = colWidths;
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, activeReport);
        XLSX.writeFile(wb, `laporan_${activeReport}_${new Date().toISOString().split('T')[0]}.xlsx`);
      }
    } catch (e) {
      console.error('Excel export error:', e);
      alert('Gagal export Excel: ' + e.message);
    }
  };

  // PDF export
  // W2 (sesi #29) — kolom DIPILIH PEMAKAI tepat sebelum mencetak. Sebelum ini
  // daftar kolom hanya bisa diubah di layar setelan, sehingga kolom Serial No
  // (yang sudah ada di katalog PDF) tidak pernah bisa dipilih dari sini.
  const exportToPDF = async (cols) => {
    if (!data.length) return;
    try {
      const params = new URLSearchParams({ type: `report-${activeReport}` });
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      if (Array.isArray(cols) && cols.length) params.append('cols', cols.join(','));
      const res = await fetch(`/api/export-pdf?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `laporan_${activeReport}_${new Date().toISOString().split('T')[0]}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        // Fallback: CSV download
        alert('PDF export gagal, coba export Excel/CSV sebagai alternatif');
      }
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  const exportToCSV = () => {
    if (!data.length) return;
    const colDefs = getColumns();
    const headers = colDefs.map(c => c.label);
    const rows = data.map(row => colDefs.map(c => {
      const val = row[c.key];
      if (c.format === 'date') return fmtDate(val);
      if (c.format === 'currency') return Number(val || 0);
      return String(val ?? '').replace(/,/g, ';');
    }));
    const csv = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `laporan_${activeReport}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  const getColumns = () => {
    switch (activeReport) {
      case 'production':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'domain', label: 'DOMAIN' },
          { key: 'pelanggan', label: 'PELANGGAN' },
          { key: 'vendor', label: 'PELAKSANA' },
          { key: 'sku', label: 'SKU' },
          { key: 'produk', label: 'PRODUK' },
          { key: 'ukuran', label: 'UKURAN' },
          { key: 'warna', label: 'WARNA' },
          { key: 'qty_pesan', label: 'QTY PESAN', format: 'number' },
          { key: 'qty_produksi', label: 'QTY PRODUKSI', format: 'number' },
          { key: 'qty_diterima', label: 'QTY DITERIMA', format: 'number' },
          { key: 'qty_reject', label: 'QTY REJECT', format: 'number' },
          { key: 'pct_selesai', label: '% SELESAI', format: 'number' },
          { key: 'status_po', label: 'STATUS PO' },
          { key: 'deadline', label: 'DEADLINE', format: 'date' },
        ];
      case 'per-po':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'domain', label: 'DOMAIN' },
          { key: 'pelanggan', label: 'PELANGGAN' },
          { key: 'status_po', label: 'STATUS' },
          { key: 'baris_item', label: 'ITEM', format: 'number' },
          { key: 'qty_pesan', label: 'QTY PESAN', format: 'number' },
          { key: 'qty_produksi', label: 'PRODUKSI', format: 'number' },
          { key: 'qty_diterima', label: 'DITERIMA', format: 'number' },
          { key: 'qty_reject', label: 'REJECT', format: 'number' },
          { key: 'qty_rework_terbuka', label: 'REWORK', format: 'number' },
          { key: 'qty_selisih_kirim', label: 'SELISIH KIRIM', format: 'number' },
          { key: 'qty_kirim_buyer', label: 'KIRIM BUYER', format: 'number' },
          { key: 'jumlah_job', label: 'JOB', format: 'number' },
          { key: 'jumlah_penerimaan', label: 'PENERIMAAN', format: 'number' },
          { key: 'pct_selesai', label: '% SELESAI', format: 'number' },
          { key: 'nilai_order', label: 'NILAI ORDER', format: 'currency' },
          { key: 'status_bayar', label: 'BAYAR' },
          { key: 'deadline', label: 'DEADLINE', format: 'date' },
        ];
      case 'progress':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_job', label: 'NO JOB' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'pelanggan', label: 'PELANGGAN' },
          { key: 'pelaksana', label: 'PELAKSANA' },
          { key: 'sku', label: 'SKU' },
          { key: 'produk', label: 'PRODUK' },
          { key: 'ukuran', label: 'UKURAN' },
          { key: 'warna', label: 'WARNA' },
          { key: 'qty', label: 'QTY', format: 'number' },
          { key: 'dicatat_oleh', label: 'DICATAT OLEH' },
          { key: 'catatan', label: 'CATATAN' },
        ];
      case 'financial':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_invoice', label: 'NO INVOICE' },
          { key: 'pelanggan', label: 'PELANGGAN' },
          { key: 'no_po_maklon', label: 'NO PO MAKLON' },
          { key: 'subtotal', label: 'SUBTOTAL', format: 'currency' },
          { key: 'pajak', label: 'PAJAK', format: 'currency' },
          { key: 'total', label: 'TOTAL', format: 'currency' },
          { key: 'terbayar', label: 'TERBAYAR', format: 'currency' },
          { key: 'sisa', label: 'SISA', format: 'currency' },
          { key: 'status', label: 'STATUS' },
          { key: 'jatuh_tempo', label: 'JATUH TEMPO', format: 'date' },
          { key: 'sumber', label: 'SUMBER' },
        ];
      case 'shipment':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_pengiriman', label: 'NO SURAT JALAN' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'pelanggan', label: 'PELANGGAN' },
          { key: 'vendor', label: 'PELAKSANA' },
          { key: 'baris', label: 'BARIS', format: 'number' },
          { key: 'qty', label: 'QTY KIRIM', format: 'number' },
          { key: 'qty_fg_keluar', label: 'FG KELUAR', format: 'number' },
          { key: 'status', label: 'STATUS' },
          { key: 'catatan', label: 'CATATAN' },
        ];
      case 'rework':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_penerimaan', label: 'NO PENERIMAAN' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'vendor_cmt', label: 'VENDOR CMT' },
          { key: 'sku', label: 'SKU' },
          { key: 'produk', label: 'PRODUK' },
          { key: 'ukuran', label: 'UKURAN' },
          { key: 'warna', label: 'WARNA' },
          { key: 'qty_diterima', label: 'QTY DITERIMA', format: 'number' },
          { key: 'qty_reject', label: 'QTY REJECT', format: 'number' },
          { key: 'alasan_reject', label: 'ALASAN' },
          { key: 'tindak_lanjut', label: 'TINDAK LANJUT' },
          { key: 'status_permak', label: 'STATUS PERMAK' },
        ];
      case 'material-issue':
        return [
          { key: 'tanggal', label: 'TANGGAL', format: 'date' },
          { key: 'no_mi', label: 'NO MI' },
          { key: 'no_po', label: 'NO PO' },
          { key: 'no_job', label: 'NO JOB' },
          { key: 'material', label: 'MATERIAL' },
          { key: 'qty_diminta', label: 'QTY DIMINTA', format: 'number' },
          { key: 'qty_dikeluarkan', label: 'QTY KELUAR', format: 'number' },
          { key: 'satuan', label: 'SATUAN' },
          { key: 'status', label: 'STATUS' },
          { key: 'dibuat_oleh', label: 'DIBUAT OLEH' },
          { key: 'catatan', label: 'CATATAN' },
        ];
      case 'per-client':
        return [
          { key: 'client_code', label: 'KODE KLIEN' },
          { key: 'client_name', label: 'NAMA KLIEN' },
          { key: 'total_orders', label: 'TOTAL ORDER', format: 'number' },
          { key: 'total_qty', label: 'TOTAL QTY', format: 'number' },
          { key: 'total_revenue', label: 'PENDAPATAN', format: 'currency' },
          { key: 'total_hpp', label: 'HPP', format: 'currency' },
          { key: 'margin', label: 'MARGIN', format: 'currency' },
          { key: 'margin_pct', label: 'MARGIN %', format: 'number' },
          { key: 'on_time_rate', label: 'ON TIME %', format: 'number' },
        ];
      default: return [];
    }
  };

  const renderValue = (val, format) => {
    if (format === 'date') return fmtDate(val);
    if (format === 'currency') return fmt(val);
    if (format === 'number') return fmtNum(val);
    return val ?? '-';
  };

  const STATUS_COLORS = {
    'Paid': 'bg-emerald-100 text-emerald-700',
    'Unpaid': 'bg-red-100 text-red-700',
    'Partial': 'bg-amber-100 text-amber-700',
    'Completed': 'bg-emerald-100 text-emerald-700',
    'In Progress': 'bg-primary/15 text-primary',
    'In Production': 'bg-primary/15 text-primary',
    'Pending': 'bg-amber-100 text-amber-700',
    'Approved': 'bg-emerald-100 text-emerald-700',
    'Rejected': 'bg-red-100 text-red-700',
    'Sent': 'bg-primary/15 text-primary',
    'Received': 'bg-emerald-100 text-emerald-700',
    'Draft': 'bg-secondary text-muted-foreground',
    'Closed': 'bg-secondary text-muted-foreground',
  };

  // Summary stats
  const getSummary = () => {
    if (!data.length) return null;
    switch (activeReport) {
      case 'production':
      case 'per-po': {
        const totalQty = data.reduce((s, r) => s + (r.qty_pesan || 0), 0);
        const totalProd = data.reduce((s, r) => s + (r.qty_produksi || 0), 0);
        const totalTerima = data.reduce((s, r) => s + (r.qty_diterima || 0), 0);
        const totalReject = data.reduce((s, r) => s + (r.qty_reject || 0), 0);
        const poSet = new Set(data.map(r => r.no_po));
        return [
          { label: activeReport === 'per-po' ? 'Jumlah PO' : 'Baris Item', value: activeReport === 'per-po' ? poSet.size : data.length },
          { label: 'Qty Dipesan', value: fmtNum(totalQty) + ' pcs' },
          { label: 'Qty Diproduksi', value: fmtNum(totalProd) + ' pcs' },
          { label: 'Qty Diterima', value: fmtNum(totalTerima) + ' pcs' },
          { label: 'Qty Reject', value: fmtNum(totalReject) + ' pcs' },
          { label: 'Terima / Produksi', value: totalProd ? (totalTerima / totalProd * 100).toFixed(1) + '%' : '-' },
        ];
      }
      case 'financial': {
        const totalInv = data.reduce((s, r) => s + (r.total || 0), 0);
        const totalPaid = data.reduce((s, r) => s + (r.terbayar || 0), 0);
        const totalSisa = data.reduce((s, r) => s + (r.sisa || 0), 0);
        return [
          { label: 'Total Invoice', value: data.length },
          { label: 'Total Tagihan', value: fmt(totalInv) },
          { label: 'Total Terbayar', value: fmt(totalPaid) },
          { label: 'Sisa Piutang', value: fmt(totalSisa) },
        ];
      }
      case 'shipment': {
        const totalQty = data.reduce((s, r) => s + (r.qty || 0), 0);
        return [
          { label: 'Total Pengiriman', value: data.length },
          { label: 'Total Qty Dikirim', value: fmtNum(totalQty) + ' pcs' },
        ];
      }
      case 'rework': {
        const totalTerima = data.reduce((s, r) => s + (r.qty_diterima || 0), 0);
        const totalReject = data.reduce((s, r) => s + (r.qty_reject || 0), 0);
        const belum = data.filter(r => r.tindak_lanjut === 'belum diputuskan').length;
        return [
          { label: 'Baris Reject', value: data.length },
          { label: 'Qty Diterima', value: fmtNum(totalTerima) + ' pcs' },
          { label: 'Qty Reject', value: fmtNum(totalReject) + ' pcs' },
          { label: 'Rasio Reject', value: totalTerima ? (totalReject / totalTerima * 100).toFixed(1) + '%' : '-' },
          { label: 'Belum Ditindak', value: belum },
        ];
      }
      default: return [{ label: 'Total Data', value: data.length }];
    }
  };

  const summary = getSummary();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Laporan Umum</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Sumber data SSOT: PO produksi, job, buku kuantitas, penerimaan CMT, pengiriman, dan invoice AR
          </p>
        </div>
        <div className="inline-flex overflow-hidden rounded-lg border border-border" role="group"
             aria-label="Pilih domain bisnis" data-testid="reports-domain-switch">
          {DOMAIN_TABS.map(d => (
            <button
              key={d.id} type="button" onClick={() => setDomain(d.id)}
              data-testid={`reports-domain-${d.id}`}
              aria-pressed={domain === d.id}
              className={`px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                domain === d.id ? 'bg-primary text-primary-foreground' : 'bg-transparent text-muted-foreground hover:bg-[var(--glass-bg-hover)]'
              }`}
            >{d.label}</button>
          ))}
        </div>
      </div>

      {/* Report Type Selector */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        {REPORT_TYPES.map(r => {
          const Icon = r.icon;
          const isActive = activeReport === r.id;
          return (
            <button key={r.id} onClick={() => setActiveReport(r.id)}
              className={`p-3 rounded-xl border text-left transition-all ${
                isActive ? 'bg-primary border-blue-600 text-foreground shadow-md' : 'bg-[var(--card-surface)] border-border text-foreground hover:border-primary/25 hover:shadow-sm'
              }`}>
              <Icon className={`w-4 h-4 mb-1 ${isActive ? 'text-foreground' : 'text-primary'}`} />
              <p className={`text-xs font-semibold leading-tight ${isActive ? 'text-foreground' : 'text-foreground'}`}>{r.label}</p>
              <p className="mt-0.5 text-[10px] leading-tight text-muted-foreground line-clamp-2">{r.description}</p>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
        <button onClick={() => setShowFilters(!showFilters)}
          className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-foreground hover:bg-[var(--glass-bg)]">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-primary" />
            <span>Filter & Pencarian</span>
            {Object.values(filters).filter(Boolean).length > 0 && (
              <span className="bg-primary/15 text-primary px-2 py-0.5 rounded-full text-xs font-bold">
                {Object.values(filters).filter(Boolean).length} aktif
              </span>
            )}
          </div>
          {showFilters ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        {showFilters && (
          <div className="px-5 pb-4 border-t border-border pt-4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Dari Tanggal</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--input-surface)] text-foreground"
                  value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Sampai Tanggal</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--input-surface)] text-foreground"
                  value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Status</label>
                <input type="text" placeholder="Filter status..." className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--input-surface)] text-foreground"
                  value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))} />
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              <button onClick={handleFilter} className="flex items-center gap-1 px-4 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110">
                <Search className="w-3.5 h-3.5" /> Terapkan Filter
              </button>
              <button onClick={resetFilters} className="px-4 py-2 border border-border rounded-lg text-sm text-muted-foreground hover:bg-[var(--glass-bg)]">
                Reset
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Summary Cards */}
      {summary && data.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {summary.map((s, i) => (
            <div key={i} className="bg-[var(--card-surface)] rounded-xl border border-border p-3 shadow-sm">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className="text-lg font-bold text-foreground mt-0.5">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Report Table */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <h3 className="font-semibold text-foreground">
              {REPORT_TYPES.find(r => r.id === activeReport)?.label}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {pagination ? `${pagination.total.toLocaleString('id-ID')} record total · halaman ${pagination.page}/${pagination.total_pages}` : `${data.length} record`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => fetchReport(page)} className="flex items-center gap-1 px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-[var(--glass-bg)]">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
            <button onClick={exportToExcel} disabled={!data.length}
              className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-foreground rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed">
              <Download className="w-3.5 h-3.5" /> Excel
            </button>
            <button onClick={() => setPickerOpen(true)} disabled={!data.length}
              className="flex items-center gap-1 px-3 py-1.5 bg-red-600 text-foreground rounded-lg text-sm hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="report-export-pdf-btn">
              <FileText className="w-3.5 h-3.5" /> PDF (pilih kolom)
            </button>
            <button onClick={exportToCSV} disabled={!data.length}
              className="flex items-center gap-1 px-3 py-1.5 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed">
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : !data.length ? (
          <div className="text-center py-16 text-muted-foreground">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="font-medium">Tidak ada data untuk laporan ini</p>
            <p className="text-sm mt-1">Coba ubah filter atau pilih periode yang berbeda</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-[var(--glass-bg)]">
                <tr>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase w-10 sticky left-0 bg-[var(--glass-bg)]">#</th>
                  {getColumns().filter(c => c.key !== '_no').map(c => (
                    <th key={c.key} className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase whitespace-nowrap">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((row, i) => (
                  <tr key={i} className="hover:bg-[var(--glass-bg)]">
                    <td className="px-3 py-2.5 text-sm text-muted-foreground sticky left-0 bg-[var(--card-surface)]">{((page - 1) * limit) + i + 1}</td>
                    {getColumns().filter(c => c.key !== '_no').map(c => (
                      <td key={c.key} className="px-3 py-2.5 text-sm text-foreground whitespace-nowrap">
                        {c.key === 'status' || c.key === 'inspection_status' ? (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[row[c.key]] || 'bg-secondary text-muted-foreground'}`}>
                            {row[c.key] || '-'}
                          </span>
                        ) : (
                          renderValue(row[c.key], c.format)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {pagination && pagination.total_pages > 1 && (
          <div className="px-5 py-3 border-t border-border">
            <PaginationBar pagination={pagination} onPageChange={setPage} />
          </div>
        )}
      </div>

      {/* W2 — pemilih kolom PDF: kolom yang tercetak DIPILIH pemakai, termasuk Serial */}
      <PdfColumnPicker
        docType={`report-${activeReport}`}
        token={token}
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onConfirm={(cols) => exportToPDF(cols)}
        title={`Kolom PDF — ${REPORT_TYPES.find(r => r.id === activeReport)?.label || activeReport}`}
        hint="Centang kolom yang ingin tercetak (mis. Serial produksi). Pilihan diingat untuk cetakan berikutnya."
      />
    </div>
  );
}
