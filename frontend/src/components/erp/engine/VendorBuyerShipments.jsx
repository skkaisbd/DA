import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Send, Download, Filter, Search, ChevronDown, ChevronRight, X, CheckCircle, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import { apiGet, apiPost } from '../../../lib/api';

export default function VendorBuyerShipments({ user }) {
  const [shipments, setShipments] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [shorts, setShorts] = useState({ items: [], total_qty_open: 0 });
  const [jobItems, setJobItems] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [expandedShipment, setExpandedShipment] = useState(null);
  const [dispatches, setDispatches] = useState({});
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ job_id: '', shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [] });
  const [searchJob, setSearchJob] = useState('');
  const [showAllJobs, setShowAllJobs] = useState(false);

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    try {
      const [sData, jData] = await Promise.all([
        apiGet('/buyer-shipments'),
        apiGet('/production-jobs'),
      ]);
      setShipments(Array.isArray(sData) ? sData : []);
      setJobs(Array.isArray(jData) ? jData : []);
      try {
        const sh = await apiGet('/prod/short-shipments?status=open');
        setShorts(sh && typeof sh === 'object' ? sh : { items: [], total_qty_open: 0 });
      } catch { setShorts({ items: [], total_qty_open: 0 }); }
    } catch (e) {
      setShipments([]); setJobs([]);
    }
  };

  const loadJobItems = async (jobId) => {
    const job = jobs.find(j => j.id === jobId);
    setSelectedJob(job || null);
    setForm(f => ({ ...f, job_id: jobId, items: [] }));
    if (!jobId) { setJobItems([]); return; }
    const data = await apiGet(`/production-job-items?job_id=${jobId}`);
    const items = Array.isArray(data) ? data : [];
    setJobItems(items);
    setForm(f => ({
      ...f,
      po_id: job?.po_id || '',
      items: items.map(i => ({
        job_item_id: i.id,
        po_item_id: i.po_item_id || null,
        product_name: i.product_name,
        sku: i.sku,
        size: i.size,
        color: i.color,
        serial_number: i.serial_number || '',
        ordered_qty: i.ordered_qty,
        produced_qty: i.total_produced_qty ?? i.produced_qty,  // parent + child
        // Angka yang relevan untuk vendor = deklarasi ke DA & yang DITERIMA DA
        // (bukan dispatch DA→buyer). Selisih kirim membuka kembali sisa kirim.
        shipped_to_da: i.declared_to_da ?? i.shipped_to_buyer ?? 0,
        received_by_da: i.received_by_da ?? i.received_to_buyer ?? 0,
        qty_short_open: i.qty_short_open || 0,
        shipped_to_buyer: i.shipped_to_buyer || 0,
        received_to_buyer: i.received_to_buyer || 0,
        remaining_to_ship: i.remaining_to_ship || 0,  // produced − diterima DA; selisih membuka lagi
        qty_shipped: 0,
      }))
    }));
  };

  const updateQty = (idx, val) => {
    const items = [...form.items];
    items[idx] = { ...items[idx], qty_shipped: val };
    setForm(f => ({ ...f, items }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.job_id) { toast.error('Pilih Production Job terlebih dahulu'); return; }
    const validItems = form.items.filter(i => Number(i.qty_shipped) > 0);
    if (validItems.length === 0) { toast.error('Isi minimal 1 item dengan qty > 0'); return; }

    // Check: qty to ship now <= remaining_to_ship
    for (const item of validItems) {
      if (Number(item.qty_shipped) > Number(item.remaining_to_ship)) {
        toast.warning(`Qty kirim ${item.sku} (${item.qty_shipped}) melebihi sisa pengiriman (${item.remaining_to_ship} pcs). Server akan memvalidasi terhadap qty produksi aktual.`);
        return;
      }
    }

    // Check if master shipment already exists for this job
    const existingShipment = shipments.find(s => s.job_id === form.job_id);
    const shipmentNumber = existingShipment ? existingShipment.shipment_number : `SJ-${form.job_id.slice(-6).toUpperCase()}-${Date.now().toString().slice(-4)}`;

    setLoading(true);
    try {
      await apiPost('/buyer-shipments', {
        shipment_number: shipmentNumber,
        job_id: form.job_id,
        po_id: form.po_id || selectedJob?.po_id,
        shipment_date: form.shipment_date,
        notes: form.notes,
        vendor_id: user.vendor_id,
        items: validItems.map(i => ({ ...i, qty_shipped: Number(i.qty_shipped) }))
      });
      setShowModal(false);
      fetchAll();
    } catch (err) {
      toast.error(err.message || 'Gagal membuat pengiriman');
    } finally {
      setLoading(false);
    }
  };

  const loadDispatches = async (shipmentId) => {
    if (expandedShipment === shipmentId) { setExpandedShipment(null); return; }
    setExpandedShipment(shipmentId);
    if (!dispatches[shipmentId]) {
      try {
        const data = await apiGet(`/buyer-shipment-dispatches?shipment_id=${shipmentId}`);
        setDispatches(prev => ({ ...prev, [shipmentId]: Array.isArray(data) ? data : [] }));
      } catch (e) {
        setDispatches(prev => ({ ...prev, [shipmentId]: [] }));
      }
    }
  };

  const openDispatch = (shipment) => {
    // Open modal pre-selected with this job
    const job = jobs.find(j => j.id === shipment.job_id);
    setSelectedJob(job || null);
    setForm({ job_id: shipment.job_id || '', shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [], po_id: shipment.po_id || '' });
    setJobItems([]);
    if (shipment.job_id) loadJobItems(shipment.job_id);
    setShowModal(true);
  };

  const downloadPDF = async (shipment, dispatchData) => {
    try {
      const { default: jsPDF } = await import('jspdf');
      const autoTable = (await import('jspdf-autotable')).default;
      const doc = new jsPDF();
      doc.setFontSize(18); doc.setFont('helvetica', 'bold');
      doc.text('SURAT JALAN / DELIVERY NOTE', 105, 20, { align: 'center' });
      doc.setFontSize(10); doc.setFont('helvetica', 'normal');
      doc.text(`No. SJ: ${shipment.shipment_number}`, 14, 36);
      doc.text(`Status: ${shipment.ship_status || 'Pending'}`, 14, 43);
      doc.text(`Vendor: ${shipment.vendor_name}`, 14, 50);
      doc.text(`PO: ${shipment.po_number || '-'} | Customer: ${shipment.customer_name || '-'}`, 14, 57);

      const allItems = (dispatches[shipment.id] || []).flatMap(d => d.items || []);
      autoTable(doc, {
        startY: 65,
        head: [['No', 'Produk', 'SKU', 'Size', 'Warna', 'Dispatch', 'Dikirim']],
        body: allItems.map((it, i) => [i + 1, it.product_name, it.sku || '-', it.size || '-', it.color || '-', `#${it.dispatch_seq || 1}`, it.qty_shipped]),
        foot: [['', '', '', '', '', 'Total', allItems.reduce((s, i) => s + (i.qty_shipped || 0), 0)]],
        styles: { fontSize: 9 }, headStyles: { fillColor: [16, 185, 129] }, footStyles: { fontStyle: 'bold' }
      });
      doc.save(`SJ-${shipment.shipment_number}.pdf`);
    } catch (err) { toast.error('Gagal generate PDF: ' + err.message); }
  };

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const getStatusColor = (s) => {
    if (s === 'Fully Shipped') return 'bg-emerald-100 text-emerald-700 border border-emerald-200';
    if (s === 'Partially Shipped') return 'bg-amber-100 text-amber-700 border border-amber-200';
    return 'bg-muted text-muted-foreground';
  };

  // Compute remaining_to_ship for modal items
  const canAddDispatch = (job) => {
    if (!job) return false;
    return job.status === 'In Progress' || job.total_produced > 0;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Deklarasi Pengiriman ke DA</h1>
          <p className="text-muted-foreground text-sm mt-1">Kirim produk jadi (FG) dari CMT ke Gudang DA. DA akan verifikasi qty aktual + reject, lalu baru dispatch ke buyer.</p>
        </div>
        <button onClick={() => { setForm({ job_id: '', shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [] }); setSelectedJob(null); setJobItems([]); setShowModal(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700"
          data-testid="btn-create-cmt-shipment">
          <Plus className="w-4 h-4" /> Deklarasi Kirim ke DA
        </button>
      </div>

      {/* Phase B info banner */}
      <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900 flex items-start gap-2"
           data-testid="phase-b-banner">
        <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-700" />
        <span>
          <strong>Perubahan alur (Phase B — CMT → DA → Buyer):</strong> vendor CMT tidak lagi kirim langsung
          ke buyer. Setiap deklarasi pengiriman disini akan otomatis dibuatkan <em>CMT Receipt</em> draft di
          sisi DA. Setelah DA verifikasi &amp; approve (bisa reject sebagian bila cacat), stok FG DA naik dan
          AP CMT muncul di Finance = Σ qty_actual × cmt_rate. Baru DA yang dispatch ke buyer.
        </span>
      </div>

      {/* ── KEWAJIBAN: barang yang BELUM SAMPAI di DA ────────────────────────
          Aturan owner: qty pada dokumen deklarasi disesuaikan dengan yang
          benar-benar diterima DA; kekurangannya tetap kewajiban vendor. */}
      {shorts.items?.length > 0 && (
        <div className="rounded-xl border border-rose-300 bg-card overflow-hidden" data-testid="vendor-short-panel">
          <div className="px-3 py-2 bg-rose-50 border-b border-rose-200">
            <p className="text-sm font-bold text-rose-900">
              ⚠ {Number(shorts.total_qty_open || 0).toLocaleString('id-ID')} pcs BELUM SAMPAI di DA — harus dicari &amp; dikirim ulang
            </p>
            <p className="text-[11px] text-rose-700 mt-0.5">
              DA hanya menerima lebih sedikit dari klaim kirim Anda. Dokumen deklarasi sudah
              dikoreksi mengikuti qty yang diterima, dan <strong>sisa kirim Anda bertambah</strong> —
              silakan buat <em>Dispatch</em> baru untuk mengirim ulang kekurangannya.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[720px]">
              <thead className="bg-muted/40">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2 font-semibold">No. Selisih</th>
                  <th className="px-3 py-2 font-semibold">PO</th>
                  <th className="px-3 py-2 font-semibold">SKU</th>
                  <th className="px-3 py-2 font-semibold text-right">Klaim kirim</th>
                  <th className="px-3 py-2 font-semibold text-right">Diterima DA</th>
                  <th className="px-3 py-2 font-semibold text-right">Belum sampai</th>
                  <th className="px-3 py-2 font-semibold">Tanggal</th>
                </tr>
              </thead>
              <tbody>
                {shorts.items.map(s => (
                  <tr key={s.id} className="border-t border-border/60">
                    <td className="px-3 py-2 font-mono text-[11px] font-semibold">{s.short_number}</td>
                    <td className="px-3 py-2">{s.po_number || '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px]">{s.sku || '—'}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{Number(s.qty_claimed || 0).toLocaleString('id-ID')}</td>
                    <td className="px-3 py-2 text-right text-emerald-700 font-medium">{Number(s.qty_arrived || 0).toLocaleString('id-ID')}</td>
                    <td className="px-3 py-2 text-right font-bold text-rose-700">{Number(s.qty_open ?? s.qty_short ?? 0).toLocaleString('id-ID')}</td>
                    <td className="px-3 py-2 text-muted-foreground">{s.short_date || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {shipments.length === 0 ? (
          <div className="bg-card rounded-xl border border-border p-12 text-center">
            <Send className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
            <p className="text-muted-foreground/70">Belum ada data pengiriman</p>
          </div>
        ) : shipments.map(s => {
          // Use backend-calculated fixed totals
          const totalOrdered = s.total_ordered || 0;
          const totalShipped = s.total_shipped || 0;
          const remaining = s.remaining || Math.max(0, totalOrdered - totalShipped);
          const progressPct = s.progress_pct || (totalOrdered > 0 ? Math.round((totalShipped / totalOrdered) * 100) : 0);
          const isExpanded = expandedShipment === s.id;
          const jobForShipment = jobs.find(j => j.id === s.job_id);
          const dispatchCount = s.dispatch_count || s.last_dispatch_seq || 0;

          return (
            <div key={s.id} className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-bold text-foreground">{s.shipment_number}</p>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(progressPct >= 100 ? 'Fully Shipped' : progressPct > 0 ? 'Partially Shipped' : 'Pending')}`}>
                        {progressPct >= 100 ? 'Fully Shipped' : progressPct > 0 ? 'Partially Shipped' : 'Pending'}
                      </span>
                      {dispatchCount > 0 && <span className="text-xs text-muted-foreground/70">{dispatchCount} dispatch</span>}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">PO: {s.po_number || '-'} • {s.customer_name || '-'}</p>
                    <p className="text-xs text-muted-foreground/70 mt-0.5">Job: {jobForShipment?.job_number || s.job_id || '-'}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    {/* Add dispatch button — only if not fully shipped */}
                    {progressPct < 100 && (
                      <button onClick={() => openDispatch(s)}
                        className="flex items-center gap-1 px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-sm hover:bg-emerald-100 border border-emerald-200">
                        <Plus className="w-3.5 h-3.5" /> Dispatch
                      </button>
                    )}
                    <button onClick={() => { loadDispatches(s.id); downloadPDF(s, dispatches[s.id]); }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-muted/40 text-foreground/90 rounded-lg text-sm hover:bg-muted">
                      <Download className="w-3.5 h-3.5" /> PDF
                    </button>
                    <button onClick={() => loadDispatches(s.id)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-sm hover:bg-blue-100">
                      {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />} Riwayat
                    </button>
                  </div>
                </div>

                {/* Progress bar with FIXED ordered qty */}
                <div className="mt-3 bg-muted/40 rounded-lg p-3">
                  <div className="flex items-center justify-between text-sm mb-1.5">
                    <span className="font-bold text-foreground/90">{totalShipped.toLocaleString('id-ID')} / {totalOrdered.toLocaleString('id-ID')} pcs</span>
                    <span className={`font-bold ${progressPct >= 100 ? 'text-emerald-700' : 'text-blue-700'}`}>{progressPct}%</span>
                  </div>
                  <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${progressPct >= 100 ? 'bg-emerald-500' : progressPct > 50 ? 'bg-blue-500' : 'bg-amber-500'}`}
                      style={{ width: `${Math.min(progressPct, 100)}%` }} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground/70 mt-1">
                    <span>Sisa: {remaining.toLocaleString('id-ID')} pcs</span>
                    <span>Ordered (PO): {totalOrdered.toLocaleString('id-ID')} pcs</span>
                  </div>
                </div>
              </div>

              {/* Dispatch history */}
              {isExpanded && (
                <div className="border-t border-border/60 bg-muted/40">
                  <p className="px-5 pt-3 text-xs font-semibold text-muted-foreground uppercase">Riwayat Dispatch</p>
                  {(dispatches[s.id] || []).length === 0 ? (
                    <p className="px-5 py-3 text-sm text-muted-foreground/70">Memuat riwayat...</p>
                  ) : (() => {
                    let cumulative = 0;
                    return (dispatches[s.id] || []).map(d => {
                      cumulative += d.total_qty || 0;
                      const dispatchRemaining = Math.max(0, totalOrdered - cumulative);
                      return (
                        <div key={d.dispatch_seq} className="px-5 py-3 border-b border-border/60 last:border-0">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">{d.dispatch_seq}</span>
                              <span className="text-xs font-bold text-foreground/90">Dispatch #{d.dispatch_seq}</span>
                              <span className="text-xs text-muted-foreground/70">{fmtDate(d.dispatch_date)}</span>
                            </div>
                            <div className="flex items-center gap-3 text-xs">
                              <span className="text-emerald-700 font-bold">+{(d.total_qty || 0).toLocaleString('id-ID')} pcs</span>
                              <span className="text-blue-700">Kumulatif: {cumulative.toLocaleString('id-ID')}/{totalOrdered.toLocaleString('id-ID')}</span>
                              <span className="text-muted-foreground/70">Sisa: {dispatchRemaining.toLocaleString('id-ID')}</span>
                            </div>
                          </div>
                          <div className="mt-2 grid grid-cols-4 gap-1.5">
                            {(d.items || []).map(it => (
                              <div key={it.id} className="bg-card rounded px-2 py-1.5 text-xs border border-border/60">
                                <p className="font-mono text-amber-700 font-semibold">{it.serial_number || '—'}</p>
                                <p className="font-mono text-blue-600">{it.sku || '-'}</p>
                                <p className="font-bold">{(it.qty_shipped || 0).toLocaleString('id-ID')} pcs</p>
                                {it.edit_history?.length > 0 && (
                                  <span data-testid={`vendor-edited-badge-${it.id}`}
                                    title={(it.edit_history || []).map(h => `${fmtDate(h.edited_at)} • ${h.old_qty}→${h.new_qty} pcs • ${h.edited_by}: ${h.reason}`).join('\n')}
                                    className="mt-1 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 text-[9px] font-semibold cursor-help">
                                    <Pencil className="w-2.5 h-2.5" /> diedit admin
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create/Add Dispatch Modal */}
      {showModal && (
        <Modal title={form.job_id && shipments.find(s => s.job_id === form.job_id) ? "Tambah Dispatch Pengiriman" : "Buat Pengiriman ke Buyer"} onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Show info if this is a continuation */}
            {form.job_id && shipments.find(s => s.job_id === form.job_id) && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
                📦 <strong>Pengiriman Lanjutan</strong>: Dispatch baru akan ditambahkan ke record pengiriman yang sudah ada untuk job ini.
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Pilih Job Produksi *</label>
                {/* Search */}
                <input
                  type="text"
                  placeholder="🔍 Cari nomor job atau PO..."
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-2"
                  value={searchJob}
                  onChange={e => setSearchJob(e.target.value)}
                />
                <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={form.job_id} onChange={e => { setSearchJob(''); loadJobItems(e.target.value); }}>
                  <option value="">— Pilih Job Produksi —</option>
                  {/* Jobs with available qty to ship — shown by default */}
                  {(() => {
                    const q = searchJob.toLowerCase();
                    // Filter jobs yang masih punya remaining to ship
                    const available = jobs.filter(j => {
                      const hasRemaining = (j.remaining_to_ship || 0) > 0;
                      const matchSearch = !q || j.job_number?.toLowerCase().includes(q) || j.po_number?.toLowerCase().includes(q);
                      return hasRemaining && matchSearch;
                    });
                    const notStarted = jobs.filter(j => {
                      const noProduced = (j.total_produced || 0) === 0;
                      const matchSearch = !q || j.job_number?.toLowerCase().includes(q) || j.po_number?.toLowerCase().includes(q);
                      return noProduced && matchSearch && (showAllJobs || q);
                    });
                    const completed = jobs.filter(j => {
                      const fullyShipped = (j.remaining_to_ship || 0) <= 0 && (j.total_produced || 0) > 0;
                      const matchSearch = !q || j.job_number?.toLowerCase().includes(q) || j.po_number?.toLowerCase().includes(q);
                      return fullyShipped && matchSearch && (showAllJobs || q);
                    });
                    return (
                      <>
                        {available.length > 0 && (
                          <optgroup label={`✅ Ada Sisa Kirim (${available.length})`}>
                            {available.map(j => {
                              const existShipment = shipments.find(s => s.job_id === j.id);
                              const label = existShipment ? `${j.job_number} | PO: ${j.po_number || '-'} | ${j.progress_pct || 0}% prod. | Lanjut kirim` : `${j.job_number} | PO: ${j.po_number || '-'} | ${j.progress_pct || 0}% prod. | Belum dikirim`;
                              return <option key={j.id} value={j.id}>{label}</option>;
                            })}
                          </optgroup>
                        )}
                        {notStarted.length > 0 && (
                          <optgroup label={`⏳ Belum Ada Produksi (${notStarted.length})`}>
                            {notStarted.map(j => <option key={j.id} value={j.id}>{j.job_number} | PO: {j.po_number || '-'} | 0% prod.</option>)}
                          </optgroup>
                        )}
                        {completed.length > 0 && (
                          <optgroup label={`🏁 Sudah Fully Shipped (${completed.length})`}>
                            {completed.map(j => <option key={j.id} value={j.id}>{j.job_number} | PO: {j.po_number || '-'} | Selesai</option>)}
                          </optgroup>
                        )}
                        {available.length === 0 && notStarted.length === 0 && completed.length === 0 && q && (
                          <option disabled>Tidak ditemukan: "{searchJob}"</option>
                        )}
                      </>
                    );
                  })()}
                </SmartNativeSelect>
                {/* Toggle show all */}
                <button type="button" className="text-xs text-blue-600 hover:underline mt-1" onClick={() => setShowAllJobs(v => !v)}>
                  {showAllJobs ? '▲ Sembunyikan job selesai/belum mulai' : '▼ Tampilkan semua job'}
                </button>
                {jobs.length === 0 && <p className="text-xs text-amber-600 mt-1">Belum ada Production Job.</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal Dispatch</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={form.shipment_date} onChange={e => setForm(f => ({ ...f, shipment_date: e.target.value }))} />
              </div>
            </div>

            {selectedJob && (
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-sm">
                <p className="font-semibold text-blue-700">{selectedJob.job_number} — {selectedJob.po_number}</p>
                <p className="text-xs text-blue-500 mt-0.5">Qty kirim tidak boleh melebihi sisa yang belum dikirim</p>
              </div>
            )}

            {form.items.length > 0 && (
              <div>
                <label className="block text-sm font-semibold text-foreground/90 mb-2">Item Pengiriman</label>
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/40">
                      <tr>
                        <th className="text-left px-3 py-2 text-xs text-amber-600">Serial</th>
                        <th className="text-left px-3 py-2 text-xs text-muted-foreground">Produk / SKU</th>
                        <th className="text-right px-3 py-2 text-xs text-muted-foreground">Dipesan</th>
                        <th className="text-right px-3 py-2 text-xs text-emerald-600">Diproduksi</th>
                        <th className="text-right px-3 py-2 text-xs text-muted-foreground bg-amber-50">Diklaim ke DA</th>
                        <th className="text-right px-3 py-2 text-xs text-muted-foreground bg-blue-50">Diterima DA</th>
                        <th className="text-right px-3 py-2 text-xs text-rose-600 bg-rose-50">Belum sampai</th>
                        <th className="text-right px-3 py-2 text-xs text-muted-foreground bg-emerald-50">Sisa Kirim</th>
                        <th className="text-right px-3 py-2 text-xs text-foreground/90 font-bold">Kirim Sekarang *</th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.items.map((item, idx) => (
                        <tr key={idx} className="border-t border-border/60">
                          <td className="px-3 py-2 font-mono text-xs text-amber-700 font-semibold">{item.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                          <td className="px-3 py-2">
                            <p className="font-medium">{item.product_name}</p>
                            <p className="text-xs font-mono text-blue-600">{item.sku || '-'} · {item.size}/{item.color}</p>
                          </td>
                          <td className="px-3 py-2 text-right text-muted-foreground">{(item.ordered_qty || 0).toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-emerald-700 font-medium">
                            {(item.produced_qty || 0).toLocaleString('id-ID')}
                            {item.child_produced_qty > 0 && (
                              <span className="block text-xs text-purple-600">+{item.child_produced_qty} child</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-amber-700 bg-amber-50">{(item.shipped_to_da || 0).toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-blue-700 bg-blue-50">{(item.received_by_da || 0).toLocaleString('id-ID')}</td>
                          <td className={`px-3 py-2 text-right font-bold bg-rose-50 ${(item.qty_short_open || 0) > 0 ? 'text-rose-700' : 'text-muted-foreground/60'}`}>{(item.qty_short_open || 0).toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-emerald-700 font-bold bg-emerald-50">{(item.remaining_to_ship || 0).toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2">
                            <input type="number" min="0" max={item.remaining_to_ship}
                              className={`w-24 border rounded px-2 py-1 text-sm text-right ml-auto block focus:outline-none focus:ring-1 ${Number(item.qty_shipped) > Number(item.remaining_to_ship) ? 'border-red-400 text-red-600' : 'border-border focus:ring-emerald-500'}`}
                              value={item.qty_shipped}
                              onChange={e => updateQty(idx, e.target.value)} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-muted/40 font-bold border-t border-border">
                      <tr>
                        <td colSpan={2} className="px-3 py-2">Total</td>
                        <td className="px-3 py-2 text-right">{form.items.reduce((s, i) => s + (Number(i.ordered_qty) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-emerald-700">{form.items.reduce((s, i) => s + (Number(i.produced_qty) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-amber-700 bg-amber-50">{form.items.reduce((s, i) => s + (Number(i.shipped_to_da) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-blue-700 bg-blue-50">{form.items.reduce((s, i) => s + (Number(i.received_by_da) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-rose-700 bg-rose-50">{form.items.reduce((s, i) => s + (Number(i.qty_short_open) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-emerald-700 bg-emerald-50">{form.items.reduce((s, i) => s + (Number(i.remaining_to_ship) || 0), 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-blue-700">{form.items.reduce((s, i) => s + (Number(i.qty_shipped) || 0), 0).toLocaleString('id-ID')} pcs</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan</label>
              <textarea rows="2" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={loading}
                className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
                {loading ? 'Menyimpan...' : 'Kirim'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
// ─── VENDOR MATERIAL INSPECTION ───────────────────────────────────────────────


