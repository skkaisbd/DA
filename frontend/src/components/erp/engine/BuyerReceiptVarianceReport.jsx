import { useState, useEffect, Fragment } from 'react';
import { ChevronDown, ChevronRight, FileDown, FileSpreadsheet, RefreshCw, PackageCheck, AlertTriangle, Search } from 'lucide-react';
import { toast } from 'sonner';
import { apiGet } from '../../../lib/api';

const fmtNum = (v) => Number(v || 0).toLocaleString('id-ID');

export default function BuyerReceiptVarianceReport() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [search, setSearch] = useState('');

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await apiGet('/buyer-receipt-variance');
      setRows(Array.isArray(data) ? data : []);
    } catch (e) { toast.error(e.message || 'Gagal memuat laporan'); setRows([]); }
    setLoading(false);
  };

  const toggle = (poId) => setExpanded(prev => ({ ...prev, [poId]: !prev[poId] }));

  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter(r => (r.po_number || '').toLowerCase().includes(q) || (r.customer_name || '').toLowerCase().includes(q) || (r.vendor_name || '').toLowerCase().includes(q))
    : rows;

  const grandShipped = filtered.reduce((s, r) => s + (r.total_shipped || 0), 0);
  const grandReceived = filtered.reduce((s, r) => s + (r.total_received || 0), 0);
  const grandVariance = grandShipped - grandReceived;
  // GAP G: dokumen surat jalan DIKOREKSI ke qty yang benar-benar diterima, jadi
  // `total_variance` bisa 0 sementara barangnya memang belum sampai. Angka yang
  // harus dilihat pengguna adalah SELISIH TERBUKA (`SEL-BYR-…` status open).
  const grandShortOpen = filtered.reduce((s, r) => s + (r.qty_short_open || 0), 0);
  const poWithVariance = filtered.filter(r => (r.total_variance || 0) !== 0 || (r.qty_short_open || 0) > 0).length;

  const varianceClass = (v) => v > 0 ? 'text-red-600' : v < 0 ? 'text-orange-600' : 'text-muted-foreground/70';
  const varianceText = (v) => v > 0 ? fmtNum(v) : v < 0 ? `+${fmtNum(-v)}` : '0';

  const exportExcel = async () => {
    try {
      const XLSX = await import('xlsx');
      const aoa = [['No. PO', 'Customer', 'Vendor', 'SKU', 'Serial', 'Produk', 'Size/Warna', 'Dikirim', 'Diterima', 'Selisih', 'Belum sampai']];
      filtered.forEach(r => {
        (r.items || []).forEach(it => {
          aoa.push([r.po_number, r.customer_name, r.vendor_name, it.sku, it.serial_number,
            it.product_name, `${it.size || '-'}/${it.color || '-'}`, it.shipped, it.received,
            it.variance, it.qty_short_open || 0]);
        });
        aoa.push([`TOTAL ${r.po_number}`, '', '', '', '', '', '', r.total_shipped, r.total_received,
          r.total_variance, r.qty_short_open || 0]);
      });
      const ws = XLSX.utils.aoa_to_sheet(aoa);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Selisih Terima');
      XLSX.writeFile(wb, `Laporan-Selisih-Terima-${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (e) { toast.error('Gagal export Excel: ' + e.message); }
  };

  const exportPDF = async () => {
    try {
      const { default: jsPDF } = await import('jspdf');
      const autoTable = (await import('jspdf-autotable')).default;
      const doc = new jsPDF();
      doc.setFontSize(16); doc.setFont('helvetica', 'bold');
      doc.text('LAPORAN SELISIH KIRIM vs DITERIMA', 105, 16, { align: 'center' });
      doc.setFontSize(9); doc.setFont('helvetica', 'normal');
      doc.text(`Dicetak: ${new Date().toLocaleString('id-ID')}`, 14, 24);
      doc.text(`Total Dikirim: ${fmtNum(grandShipped)} | Total Diterima: ${fmtNum(grandReceived)} | Total Selisih: ${fmtNum(grandVariance)} pcs | Belum sampai (open): ${fmtNum(grandShortOpen)} pcs`, 14, 30);
      const body = [];
      filtered.forEach(r => {
        (r.items || []).forEach(it => {
          body.push([r.po_number, it.sku || '-', it.serial_number || '-', it.product_name || '-',
            fmtNum(it.shipped), fmtNum(it.received), varianceText(it.variance),
            fmtNum(it.qty_short_open)]);
        });
      });
      autoTable(doc, {
        startY: 36,
        head: [['No. PO', 'SKU', 'Serial', 'Produk', 'Dikirim', 'Diterima', 'Selisih', 'Belum sampai']],
        body,
        styles: { fontSize: 8 }, headStyles: { fillColor: [37, 99, 235] },
      });
      doc.save(`Laporan-Selisih-Terima-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (e) { toast.error('Gagal export PDF: ' + e.message); }
  };

  return (
    <div className="space-y-4" data-testid="receipt-variance-report">
      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: 'Total Dikirim', value: `${fmtNum(grandShipped)} pcs`, color: 'text-emerald-700', bg: 'bg-emerald-50' },
          { label: 'Total Diterima', value: `${fmtNum(grandReceived)} pcs`, color: 'text-blue-700', bg: 'bg-blue-50' },
          { label: 'Total Selisih Dokumen', value: `${fmtNum(grandVariance)} pcs`, color: grandVariance > 0 ? 'text-red-700' : 'text-foreground/90', bg: 'bg-red-50' },
          { label: 'Belum Sampai (open)', value: `${fmtNum(grandShortOpen)} pcs`, color: grandShortOpen > 0 ? 'text-rose-700' : 'text-foreground/90', bg: 'bg-rose-50' },
          { label: 'PO Ada Selisih', value: poWithVariance, color: 'text-amber-700', bg: 'bg-amber-50' },
        ].map(s => (
          <div key={s.label} className={`${s.bg} rounded-xl p-4`} data-testid={`variance-kpi-${s.label}`}>
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground -mt-2">
        Catatan: saat buyer menerima lebih sedikit, dokumen surat jalan otomatis dikoreksi ke qty
        yang benar-benar diterima (klaim awal tersimpan di jejak audit) dan kekurangannya menjadi
        dokumen selisih <strong>SEL-BYR-…</strong> berstatus <strong>open</strong> — itulah kolom
        <strong> Belum sampai</strong> di bawah.
      </p>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="w-4 h-4 text-muted-foreground/70 absolute left-3 top-1/2 -translate-y-1/2" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari PO / customer / vendor..."
            data-testid="variance-search"
            className="pl-9 pr-3 py-2 border border-border rounded-lg text-sm w-72 focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <button onClick={fetchData} className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-sm hover:bg-muted/60">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={exportPDF} data-testid="variance-export-pdf"
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
            <FileDown className="w-4 h-4" /> Export PDF
          </button>
          <button onClick={exportExcel} data-testid="variance-export-excel"
            className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700">
            <FileSpreadsheet className="w-4 h-4" /> Export Excel
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-16 text-muted-foreground/70"><RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3" />Memuat laporan...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground/70">
          <PackageCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">Belum ada data pengiriman ke buyer</p>
        </div>
      ) : (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                <th className="w-8"></th>
                <th className="text-left px-3 py-2.5 text-xs font-semibold text-muted-foreground uppercase">No. PO</th>
                <th className="text-left px-3 py-2.5 text-xs font-semibold text-muted-foreground uppercase">Customer</th>
                <th className="text-left px-3 py-2.5 text-xs font-semibold text-muted-foreground uppercase">Vendor</th>
                <th className="text-right px-3 py-2.5 text-xs font-semibold text-emerald-600 uppercase">Dikirim</th>
                <th className="text-right px-3 py-2.5 text-xs font-semibold text-blue-600 uppercase">Diterima</th>
                <th className="text-right px-3 py-2.5 text-xs font-semibold text-red-600 uppercase">Selisih</th>
                <th className="text-right px-3 py-2.5 text-xs font-semibold text-rose-600 uppercase">Belum sampai</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filtered.map(r => {
                const key = r.po_id || r.po_number;
                const isOpen = expanded[key];
                return (
                  <Fragment key={key}>
                    <tr className="hover:bg-muted/60 cursor-pointer" onClick={() => toggle(key)} data-testid={`variance-po-row-${r.po_number}`}>
                      <td className="px-2 text-muted-foreground/70">{isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</td>
                      <td className="px-3 py-2.5 font-bold text-blue-700">{r.po_number || '-'}</td>
                      <td className="px-3 py-2.5 text-foreground/90">{r.customer_name || '-'}</td>
                      <td className="px-3 py-2.5 text-muted-foreground">{r.vendor_name || '-'}</td>
                      <td className="px-3 py-2.5 text-right font-semibold text-emerald-700">{fmtNum(r.total_shipped)}</td>
                      <td className="px-3 py-2.5 text-right font-semibold text-blue-700">{fmtNum(r.total_received)}</td>
                      <td className={`px-3 py-2.5 text-right font-bold ${varianceClass(r.total_variance)}`}>
                        {(r.total_variance || 0) !== 0 && <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />}
                        {varianceText(r.total_variance)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-bold ${(r.qty_short_open || 0) > 0 ? 'text-rose-700 bg-rose-50' : 'text-muted-foreground/70'}`}
                        data-testid={`variance-short-${r.po_number}`}>
                        {fmtNum(r.qty_short_open)}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={`${key}-detail`}>
                        <td colSpan={8} className="bg-muted/40/60 px-6 py-3">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-muted-foreground border-b border-border">
                                <th className="text-left py-1.5 px-2">Serial</th>
                                <th className="text-left py-1.5 px-2">SKU</th>
                                <th className="text-left py-1.5 px-2">Produk</th>
                                <th className="text-right py-1.5 px-2">Dikirim</th>
                                <th className="text-right py-1.5 px-2">Diterima</th>
                                <th className="text-right py-1.5 px-2">Selisih</th>
                                <th className="text-right py-1.5 px-2">Belum sampai</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/60">
                              {(r.items || []).map((it, i) => (
                                <tr key={i}>
                                  <td className="py-1.5 px-2 font-mono text-amber-700">{it.serial_number || '—'}</td>
                                  <td className="py-1.5 px-2 font-mono text-blue-700">{it.sku || '-'}</td>
                                  <td className="py-1.5 px-2 text-foreground/90">{it.product_name} <span className="text-muted-foreground/70">{it.size}/{it.color}</span></td>
                                  <td className="py-1.5 px-2 text-right text-emerald-700">{fmtNum(it.shipped)}</td>
                                  <td className="py-1.5 px-2 text-right text-blue-700">{fmtNum(it.received)}</td>
                                  <td className={`py-1.5 px-2 text-right font-semibold ${varianceClass(it.variance)}`}>{varianceText(it.variance)}</td>
                                  <td className={`py-1.5 px-2 text-right font-semibold ${(it.qty_short_open || 0) > 0 ? 'text-rose-700' : 'text-muted-foreground/70'}`}>{fmtNum(it.qty_short_open)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {(r.short_docs || []).filter(d => d.status === 'open').length > 0 && (
                            <div className="mt-2 text-[11px] text-rose-800">
                              Dokumen selisih terbuka:{' '}
                              {(r.short_docs || []).filter(d => d.status === 'open')
                                .map(d => `${d.short_number} (${d.sku} · ${fmtNum(d.qty_open)} pcs)`).join(' · ')}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
