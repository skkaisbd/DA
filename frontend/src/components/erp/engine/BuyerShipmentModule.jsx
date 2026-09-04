
import { useState, useEffect, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Eye, Trash2, Package, CheckCircle, Clock, TruckIcon, Download, ChevronDown, ChevronRight, History, ClipboardCheck, ClipboardList, BarChart3, ListChecks } from 'lucide-react';
import { toast } from 'sonner';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import FileAttachmentPanel from './FileAttachmentPanel';
import ImportExportPanel from './ImportExportPanel';
import BuyerReceiptVarianceReport from './BuyerReceiptVarianceReport';
import { BizBadge, BizFilter, matchBiz } from './BusinessTypeBadge';
import { apiGet, apiPost, apiPut, apiDelete, apiFetch } from '../../../lib/api';

export default function BuyerShipmentModule({ userRole, hasPerm = () => false, portalId }) {
  // Pemisahan data per proses bisnis: Portal Produksi = internal, Portal Maklon = maklon.
  const businessType = portalId === 'maklon' ? 'maklon' : portalId === 'production' ? 'internal' : null;
  const [shipments, setShipments] = useState([]);
  const [pos, setPOs] = useState([]);
  const [poItems, setPoItems] = useState([]);
  const [selectedPO, setSelectedPO] = useState(null);
  const [showModal, setShowModal] = useState(false);
  // ── LANJUTAN DISPATCH pada surat jalan yang SAMA (keluhan pemilik 2026-06) ──
  // Berisi surat jalan yang sedang DILANJUTKAN (bukan dibuat baru). Kalau terisi,
  // form mengirim `shipment_id` sehingga backend menambah `dispatch_seq`
  // berikutnya pada surat jalan itu — nomornya tidak berubah.
  const [continueShip, setContinueShip] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    shipment_number: '',
    po_id: '',
    shipment_date: new Date().toISOString().split('T')[0],
    notes: '',
    items: [],
    // Phase B: DA dispatch wajib pilih source_receipt_ids (approved cmt_receipts)
    source_receipt_ids: [],
  });
  const [availableReceipts, setAvailableReceipts] = useState([]);   // Phase B: cmt_receipts yg bisa jadi source
  // ─── FASE E (2026-08-15) — SATU SSOT KAPASITAS KIRIM ──────────────────────
  // Dulu layar menghitung sendiri: cap = Σ(qty_actual − reject_qty) dan TIDAK
  // mengurangi yang sudah dikirim. Dua kesalahan sekaligus:
  //   · `qty_actual` pada baris penerimaan SUDAH berarti qty LOLOS QC, jadi
  //     mengurangi reject lagi = memotong reject DUA KALI ("chip 90 jadi 80").
  //   · tanpa mengurangi yang sudah dikirim, form mem-prefill angka yang PASTI
  //     ditolak backend, dan pemakai baru tahu setelah klik Simpan.
  // Sekarang angkanya DIBACA dari backend (`/api/buyer-dispatch-capacity`) —
  // rumus yang sama persis dengan pagar yang menolak saat Simpan.
  const [capRows, setCapRows] = useState({});       // key ("poi:<id>") -> baris kapasitas
  const [capTotals, setCapTotals] = useState(null);
  const [capLoading, setCapLoading] = useState(false);
  // ─── FASE E — tab KEKURANGAN KIRIM (dispatch list) ────────────────────────
  const [outstanding, setOutstanding] = useState({ items: [], buyers: [], totals: null });
  const [outLoading, setOutLoading] = useState(false);
  const [outBuyer, setOutBuyer] = useState('');
  const [outShowSettled, setOutShowSettled] = useState(false);
  const [recvItem, setRecvItem] = useState(null);
  const [recvForm, setRecvForm] = useState({ qty_received: '', reason: '' });
  const [recvLoading, setRecvLoading] = useState(false);
  // ── SELISIH TERIMA BUYER (barang belum sampai) — GAP G ───────────────────
  const [buyerShorts, setBuyerShorts] = useState({ items: [], total_qty_open: 0 });
  const [resolveBShort, setResolveBShort] = useState(null);
  const [bResType, setBResType] = useState('dikirim_ulang');
  const [bResNotes, setBResNotes] = useState('');
  const [bResSaving, setBResSaving] = useState(false);
  const [viewMode, setViewMode] = useState('list');
  // Identifier + filter Internal/Maklon — relevan saat list menggabungkan kedua tipe
  const [bizFilter, setBizFilter] = useState('all');
  // 'buyer' = surat jalan DA → buyer (default), 'da' = deklarasi vendor → DA, 'all' = semua
  const [recvFilter, setRecvFilter] = useState('buyer');
  // ─── Phase D: consolidated multi-PO surat jalan ─────────────────────────
  const [consolidate, setConsolidate] = useState(false);
  const [consBuyer, setConsBuyer] = useState('');
  const [consReceipts, setConsReceipts] = useState([]);       // approved receipts annotated w/ _buyer + _po_number
  const [consLoading, setConsLoading] = useState(false);
  const [receiptLinesCache, setReceiptLinesCache] = useState({}); // rid -> lines[]

  const isSuperAdmin = userRole === 'superadmin';
  const canCreate = ['superadmin', 'admin'].includes(userRole) || hasPerm('shipment.create');
  const canEdit = ['superadmin', 'admin'].includes(userRole) || hasPerm('shipment.create');
  const canForceEdit = ['superadmin', 'admin'].includes(userRole);

  useEffect(() => { fetchAll(); }, [businessType]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const btq = businessType ? `?business_type=${businessType}` : '';
      const [sData, pData] = await Promise.all([
        apiGet(`/buyer-shipments${btq}`),
        apiGet('/production-pos?status=In Production'),
      ]);
      setShipments(Array.isArray(sData) ? sData : []);
      try {
        const sh = await apiGet('/buyer-shorts?status=open');
        setBuyerShorts(sh && typeof sh === 'object' ? sh : { items: [], total_qty_open: 0 });
      } catch { setBuyerShorts({ items: [], total_qty_open: 0 }); }
      const allPOs = await apiGet('/production-pos');
      // Filter PO yang masih punya sisa untuk dikirim (remaining_qty_to_ship > 0)
      // + sesuaikan proses bisnis portal (internal vs maklon)
      setPOs(Array.isArray(allPOs) ? allPOs.filter(p =>
        ['In Production', 'Completed', 'Distributed'].includes(p.status) &&
        (p.remaining_qty_to_ship || p.total_qty) > 0 &&
        (!businessType || (businessType === 'maklon' ? p.business_type === 'maklon' : p.business_type !== 'maklon'))
      ) : []);
    } catch (e) {
      setShipments([]); setPOs([]);
    }
    setLoading(false);
  };

  const loadPOItems = async (poId, poOverride = null) => {
    if (!poId) { setPoItems([]); setSelectedPO(null); setForm(f => ({...f, po_id: '', items: [], source_receipt_ids: []})); setAvailableReceipts([]); resetCapacity(); return; }
    try {
      const data = await apiGet(`/po-items?po_id=${poId}`);
      const po = poOverride || pos.find(p => p.id === poId);
      setSelectedPO(po);
      setPoItems(Array.isArray(data) ? data : []);
      const items = (Array.isArray(data) ? data : []).map(pi => ({
        po_item_id: pi.id,
        product_name: pi.product_name,
        sku: pi.sku || '',
        size: pi.size || '',
        color: pi.color || '',
        serial_number: pi.serial_number || '',
        ordered_qty: pi.qty,
        qty_shipped: '',
      }));
      setForm(f => ({...f, po_id: poId, items, source_receipt_ids: []}));
      resetCapacity();
      // PO INTERNAL: tidak lewat CMT — kapasitas kirim = hasil produksi job internal
      // (dibaca dari backend per po_item), tanpa pemilih CMT Receipt.
      if (po && po.business_type === 'internal') {
        setAvailableReceipts([]);
        const map = await fetchCapacityByPoItems(items.map(i => i.po_item_id));
        setForm(f => ({ ...f, items: annotateItemsWithCapacity(items, map) }));
        return;
      }
      // Phase B: fetch Approved cmt_receipts for this PO to enforce source_receipt_ids picker
      try {
        const rcpAll = await apiGet(`/prod/cmt-receipts?status=Approved`);
        const forPo = (Array.isArray(rcpAll) ? rcpAll : []).filter(r =>
          r.po_id === poId || (po && (r.po_number === po.po_number || r.wo_number === po.po_number))
        );
        setAvailableReceipts(forPo);
      } catch { setAvailableReceipts([]); }
    } catch (e) { setPoItems([]); }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // FASE E — KAPASITAS KIRIM: SATU ANGKA, DIBACA DARI BACKEND
  // ═══════════════════════════════════════════════════════════════════════════
  const resetCapacity = () => { setCapRows({}); setCapTotals(null); };

  const fetchCapacity = async (receiptIds) => {
    const ids = (receiptIds || []).filter(Boolean);
    if (ids.length === 0) { resetCapacity(); return {}; }
    setCapLoading(true);
    try {
      const res = await apiGet(
        `/buyer-dispatch-capacity?with_fg_stock=1&receipt_ids=${encodeURIComponent(ids.join(','))}`);
      const map = {};
      for (const r of (res?.items || [])) map[r.key] = r;
      setCapRows(map);
      setCapTotals(res?.totals || null);
      return map;
    } catch (e) {
      toast.error(`Gagal memuat sisa bisa kirim: ${e.message || 'kesalahan jaringan'}`);
      resetCapacity();
      return {};
    } finally { setCapLoading(false); }
  };

  const fetchCapacityByPoItems = async (poItemIds) => {
    const ids = (poItemIds || []).filter(Boolean);
    if (ids.length === 0) { resetCapacity(); return {}; }
    setCapLoading(true);
    try {
      const res = await apiGet(
        `/buyer-dispatch-capacity?with_fg_stock=1&po_item_ids=${encodeURIComponent(ids.join(','))}`);
      const map = {};
      for (const r of (res?.items || [])) map[r.key] = r;
      setCapRows(map);
      setCapTotals(res?.totals || null);
      return map;
    } catch (e) {
      toast.error(`Gagal memuat sisa bisa kirim: ${e.message || 'kesalahan jaringan'}`);
      resetCapacity();
      return {};
    } finally { setCapLoading(false); }
  };

  // Baris item DIBANGUN dari kapasitas (mode gabungan): hanya item yang benar-benar
  // punya penerimaan dari CMT yang muncul, dan qty di-prefill = SISA (bukan cap penuh).
  const rowsFromCapacity = (map) => Object.values(map)
    .filter(r => r.po_item_id)
    .map(r => ({
      po_item_id: r.po_item_id,
      sku: r.sku || '',
      product_name: r.product_name || '',
      size: r.size || '',
      color: r.color || '',
      serial_number: r.serial_number || '',
      po_number: r.po_number || '',
      po_id: r.po_id || '',
      ordered_qty: r.ordered || 0,
      good_from_cmt: r.good_from_cmt || 0,
      reworked_ok: r.reworked_ok || 0,
      internal_produced: r.internal_produced || 0,
      dispatched: r.dispatched || 0,
      shippable: r.shippable || 0,
      fg_stock: r.fg_stock,
      qty_shipped: r.shippable > 0 ? String(r.shippable) : '',
    }));

  // Mode satu-PO: baris tetap dari PO items, tapi angkanya DILENGKAPI kapasitas.
  const annotateItemsWithCapacity = (items, map) => items.map(it => {
    const r = map[`poi:${it.po_item_id}`];
    if (!r) return { ...it, good_from_cmt: 0, reworked_ok: 0, internal_produced: 0, dispatched: 0, shippable: 0, qty_shipped: '' };
    return {
      ...it,
      good_from_cmt: r.good_from_cmt || 0,
      reworked_ok: r.reworked_ok || 0,
      internal_produced: r.internal_produced || 0,
      dispatched: r.dispatched || 0,
      shippable: r.shippable || 0,
      fg_stock: r.fg_stock,
      qty_shipped: r.shippable > 0 ? String(r.shippable) : '',
    };
  });

  const toggleSourceReceipt = async (rid) => {
    const has = form.source_receipt_ids.includes(rid);
    const src = has ? form.source_receipt_ids.filter(x => x !== rid) : [...form.source_receipt_ids, rid];
    setForm(f => ({ ...f, source_receipt_ids: src }));
    const map = await fetchCapacity(src);
    setForm(f => ({ ...f, items: annotateItemsWithCapacity(f.items, map) }));
  };

  const updateItemQty = (idx, val) => {
    const items = [...form.items];
    const row = items[idx];
    // Batas KERAS = sisa bisa kirim (angka yang sama dengan pagar backend). Kalau
    // kapasitas belum dimuat (belum pilih receipt) batasnya qty order supaya form
    // tidak diam-diam mengunci input ke 0.
    const cap = row.shippable != null ? Number(row.shippable) : Number(row.ordered_qty || 0);
    let next = val;
    if (val !== '') {
      const n = Number(val);
      next = String(Number.isFinite(n) ? Math.max(0, Math.min(n, cap)) : 0);
      if (Number.isFinite(n) && n > cap) {
        toast.warning(`${row.sku || 'Item'}: maksimal ${cap.toLocaleString('id-ID')} pcs (sisa bisa kirim).`);
      }
    }
    items[idx] = { ...row, qty_shipped: next };
    setForm(f => ({ ...f, items }));
  };

  // ─── Phase D: consolidation helpers ─────────────────────────────────────
  const enterConsolidation = async () => {
    setConsLoading(true);
    try {
      const btq = businessType ? `?business_type=${businessType}` : '';
      const [rcpAll, allPOs] = await Promise.all([
        apiGet('/prod/cmt-receipts?status=Approved'),
        apiGet(`/production-pos${btq}`),
      ]);
      const poList = Array.isArray(allPOs) ? allPOs : [];
      const poById = {}; poList.forEach(p => { poById[p.id] = p; });
      const annotated = (Array.isArray(rcpAll) ? rcpAll : []).map(r => {
        const po = poById[r.po_id] || poList.find(p => p.po_number === (r.po_number || r.wo_number));
        return { ...r, _buyer: (po?.customer_name || '').trim(), _po_number: po?.po_number || r.po_number || r.wo_number || '' };
      }).filter(r => r._buyer);
      setConsReceipts(annotated);
    } catch { setConsReceipts([]); }
    setConsLoading(false);
  };

  const consBuyers = [...new Set(consReceipts.map(r => r._buyer))].sort();
  const consReceiptsForBuyer = consReceipts.filter(r => r._buyer === consBuyer);

  const toggleConsReceipt = async (r) => {
    const rid = r.id;
    // OPTIMISTIC: centang berpindah SEKARANG supaya klik tidak terasa "tidak jadi".
    const has = form.source_receipt_ids.includes(rid);
    const src = has ? form.source_receipt_ids.filter(x => x !== rid) : [...form.source_receipt_ids, rid];
    setForm(f => ({ ...f, source_receipt_ids: src }));
    const map = await fetchCapacity(src);
    setForm(f => ({ ...f, items: rowsFromCapacity(map) }));
  };

  const selectConsBuyer = (name) => {
    setConsBuyer(name);
    setForm(f => ({ ...f, source_receipt_ids: [], items: [] }));
    resetCapacity();
  };

  const openCreateModal = () => {
    setShowModal(true);
    setContinueShip(null);
    setConsolidate(false); setConsBuyer(''); setConsReceipts([]); setReceiptLinesCache({});
    setForm({ shipment_number: '', po_id: '', shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [], source_receipt_ids: [] });
    setAvailableReceipts([]); resetCapacity();
  };

  // Dulu satu-satunya cara mengirim sisa adalah membuat surat jalan BARU, jadi
  // satu PO berakhir punya beberapa nomor surat jalan dan tidak satu pun mencapai
  // 100%. Tombol "+ Dispatch" membuka form yang SAMA dengan surat jalan induknya
  // terpasang: PO, sumber penerimaan, dan sisa bisa kirim dimuat ulang dari
  // backend supaya angkanya tidak pernah ditebak layar.
  const openContinueModal = async (row) => {
    setShowModal(true);
    setContinueShip(row);
    setConsolidate(false); setConsBuyer(''); setConsReceipts([]); setReceiptLinesCache({});
    setForm({ shipment_number: row.shipment_number || '', po_id: '',
      shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [], source_receipt_ids: [] });
    setAvailableReceipts([]); resetCapacity();
    try {
      const det = await apiGet(`/buyer-shipments/${row.id}`);
      const srcIds = (det?.source_receipt_ids || []).filter(Boolean);
      const poIds = (det?.po_ids || []).filter(Boolean).length
        ? det.po_ids.filter(Boolean) : (det?.po_id ? [det.po_id] : []);
      if (poIds.length > 1) {
        setConsolidate(true);
        setConsBuyer(det.customer_name || '');
        await enterConsolidation();
        setForm(f => ({ ...f, source_receipt_ids: srcIds }));
        const map = await fetchCapacity(srcIds);
        setForm(f => ({ ...f, items: rowsFromCapacity(map) }));
      } else {
        const po = await ensurePOInList(poIds[0] || '');
        await loadPOItems(poIds[0] || '', po);
        setForm(f => ({ ...f, shipment_number: row.shipment_number || '', source_receipt_ids: srcIds }));
        const map = await fetchCapacity(srcIds);
        setForm(f => ({ ...f, items: annotateItemsWithCapacity(f.items, map) }));
      }
      if (srcIds.length === 0) {
        toast.warning('Surat jalan ini belum punya sumber penerimaan CMT — pilih dulu penerimaan (Approved) sebelum menambah dispatch.');
      }
    } catch (e) {
      toast.error(e.message || 'Gagal memuat surat jalan yang akan dilanjutkan');
    }
  };

  const toggleConsolidateMode = (on) => {
    setConsolidate(on);
    setConsBuyer('');
    setForm(f => ({ ...f, po_id: '', items: [], source_receipt_ids: [] }));
    setAvailableReceipts([]); resetCapacity(); setSelectedPO(null);
    if (on) enterConsolidation();
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // FASE E — DAFTAR KEKURANGAN KIRIM (dispatch list)
  // ═══════════════════════════════════════════════════════════════════════════
  const loadOutstanding = async (buyer = outBuyer, showSettled = outShowSettled) => {
    setOutLoading(true);
    try {
      const qs = new URLSearchParams();
      if (buyer) qs.set('buyer', buyer);
      if (showSettled) qs.set('include_settled', '1');
      const res = await apiGet(`/buyer-dispatch-outstanding${qs.toString() ? `?${qs}` : ''}`);
      setOutstanding({
        items: Array.isArray(res?.items) ? res.items : [],
        // daftar buyer diambil dari muatan TANPA filter supaya pilihan tidak
        // menyusut sendiri setiap kali difilter (jebakan klasik dropdown filter)
        buyers: (res?.buyers?.length ? res.buyers : outstanding.buyers) || [],
        totals: res?.totals || null,
      });
    } catch (e) {
      toast.error(`Gagal memuat kekurangan kirim: ${e.message || 'kesalahan jaringan'}`);
      setOutstanding({ items: [], buyers: [], totals: null });
    } finally { setOutLoading(false); }
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // PAPAN SISA KIRIM PER PO (keluhan pemilik 2026-06)
  // ═══════════════════════════════════════════════════════════════════════════
  // Daftar kekurangan kirim tampil PER ITEM, jadi untuk tahu "PO ini masih berapa"
  // pemakai harus menjumlahkan sendiri lalu mencari surat jalannya di tab lain.
  // Papan ini menggabungkan baris yang SAMA SUMBERNYA (tidak ada rumus baru:
  // angkanya tetap dari `/api/buyer-dispatch-outstanding`) dan menempelkan jalan
  // keluarnya: lanjutkan surat jalan yang belum 100%, atau buat yang pertama.
  const poBoard = useMemo(() => {
    const map = new Map();
    for (const r of (outstanding.items || [])) {
      const key = r.po_id || r.po_number || '-';
      const g = map.get(key) || {
        key, po_id: r.po_id, po_number: r.po_number || '-', buyer: r.buyer || '',
        ordered: 0, dispatched: 0, shippable: 0, remaining: 0, lines: 0,
      };
      g.ordered += Number(r.ordered || 0);
      g.dispatched += Number(r.dispatched || 0);
      g.shippable += Number(r.shippable || 0);
      g.remaining += Number(r.remaining_vs_order || 0);
      g.lines += 1;
      if (!g.buyer && r.buyer) g.buyer = r.buyer;
      map.set(key, g);
    }
    return Array.from(map.values()).map(g => ({
      ...g,
      pct: g.ordered > 0 ? Math.min(100, Math.round((g.dispatched / g.ordered) * 100)) : 0,
      openShip: shipments.find(s => {
        const ids = (s.po_ids?.length ? s.po_ids : [s.po_id]).filter(Boolean);
        return ids.includes(g.po_id) && (s.progress_pct || 0) < 100;
      }) || null,
    })).sort((a, b) => b.shippable - a.shippable || b.remaining - a.remaining);
  }, [outstanding.items, shipments]);

  // Papan sisa kirim memakai kapasitas kirim (tidak peduli status PO), sedangkan
  // pilihan PO di form hanya memuat status tertentu (In Production/Completed/
  // Distributed). Kalau PO dari papan tidak ada di daftar itu, labelnya kosong dan
  // pemakai tidak tahu PO mana yang sedang diisi — jadi PO-nya disisipkan.
  const ensurePOInList = async (poId) => {
    if (!poId) return null;
    const found = pos.find(p => p.id === poId);
    if (found) return found;
    try {
      const po = await apiGet(`/production-pos/${poId}`);
      if (po?.id) { setPOs(prev => [po, ...prev]); return po; }
    } catch { /* item tetap dimuat; hanya label PO yang kosong */ }
    return null;
  };

  const openCreateForPO = async (poId) => {
    openCreateModal();
    if (!poId) return;
    const po = await ensurePOInList(poId);
    await loadPOItems(poId, po);
  };

  const exportOutstandingCSV = () => {    const rows = outstanding.items || [];
    if (rows.length === 0) { toast.error('Tidak ada data untuk diunduh'); return; }
    const head = ['No. PO', 'Buyer', 'SKU', 'Produk', 'Size', 'Warna', 'Qty Order',
      'Sumber', 'Siap Kirim', 'Hasil Permak', 'Sudah Dikirim', 'Sisa Order', 'Sisa Bisa Kirim', 'Stok FG'];
    const esc = (v) => {
      const s = v == null ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const body = rows.map(r => [r.po_number, r.buyer, r.sku, r.product_name, r.size, r.color,
      r.ordered, r.source === 'internal' ? 'produksi internal' : 'CMT', r.source === 'internal' ? r.internal_produced : r.good_from_cmt, r.reworked_ok, r.dispatched, r.remaining_vs_order,
      r.shippable, r.fg_stock == null ? '' : Math.round(r.fg_stock)].map(esc).join(','));
    const csv = [head.join(','), ...body].join('\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `kekurangan-kirim-buyer-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`${rows.length} baris diunduh`);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    // ─── Phase D: consolidated multi-PO surat jalan ───────────────────────
    if (consolidate) {
      if (!consBuyer) { toast.error('Pilih buyer terlebih dahulu'); return; }
      if (form.source_receipt_ids.length === 0) { toast.error('Pilih minimal 1 CMT Receipt (Approved)'); return; }
      const validItems = form.items.filter(i => Number(i.qty_shipped) > 0);
      if (validItems.length === 0) { toast.error('Isi minimal 1 item dengan qty > 0'); return; }
      // FASE E — tolak DI LAYAR sebelum kirim ke server, dengan angka yang SAMA.
      const over = validItems.filter(i => Number(i.qty_shipped) > Number(i.shippable ?? 0));
      if (over.length > 0) {
        const o = over[0];
        toast.error(`${o.sku || 'Item'}: qty kirim ${o.qty_shipped} melebihi sisa bisa kirim ${Number(o.shippable || 0).toLocaleString('id-ID')} pcs.`);
        return;
      }
      const payload = {
        shipment_date: form.shipment_date,
        notes: form.notes,
        items: validItems.map(i => ({ po_item_id: i.po_item_id, sku: i.sku, qty_shipped: Number(i.qty_shipped) })),
        source_receipt_ids: form.source_receipt_ids,
        receiver_type: 'buyer',
      };
      if (continueShip) payload.shipment_id = continueShip.id;
      else if (form.shipment_number.trim()) payload.shipment_number = form.shipment_number.trim();
      try {
        const data = await apiPost('/buyer-shipments', payload);
        toast.success(continueShip
          ? `Dispatch #${data.dispatch_seq || ''} ditambahkan ke surat jalan ${data.shipment_number || ''}`
          : `Surat jalan konsolidasi ${data.shipment_number || ''} dibuat (${(data.po_ids || []).length} PO)`);
        setShowModal(false); setContinueShip(null); fetchAll();
      } catch (err) { toast.error(err.message || 'Gagal membuat surat jalan konsolidasi'); }
      return;
    }
    // ─── Single-PO mode ────────────────────────────────────────────────────
    if (!form.po_id) { toast.error('Pilih PO terlebih dahulu'); return; }
    const validItems = form.items.filter(i => Number(i.qty_shipped) > 0);
    if (validItems.length === 0) { toast.error('Isi minimal 1 item dengan qty > 0'); return; }
    // Phase B: DA dispatch wajib pilih source_receipt_ids (approved cmt_receipts)
    // — kecuali PO INTERNAL (sumber = hasil produksi job internal).
    const isInternalPO = selectedPO?.business_type === 'internal';
    if (!isInternalPO && form.source_receipt_ids.length === 0) {
      toast.error(
        'Phase B: wajib pilih minimal 1 CMT Receipt (Approved) sebagai sumber. ' +
        'Belum ada CMT Receipt yg approved? Minta DA admin proses "Terima FG dari CMT" dulu.'
      );
      return;
    }
    // FASE E — batas nyata adalah SISA BISA KIRIM (lolos QC + hasil permak −
    // sudah dikirim), bukan qty PO. Ditolak di layar dengan angka yang sama
    // supaya pemakai tidak perlu klik Simpan untuk tahu.
    const overSingle = validItems.filter(i => i.shippable != null && Number(i.qty_shipped) > Number(i.shippable));
    if (overSingle.length > 0) {
      const o = overSingle[0];
      toast.error(`${o.sku || 'Item'}: qty kirim ${o.qty_shipped} melebihi sisa bisa kirim ${Number(o.shippable || 0).toLocaleString('id-ID')} pcs.`);
      return;
    }
    for (const item of validItems) {
      if (Number(item.qty_shipped) > Number(item.ordered_qty)) {
        toast.warning(
          `${item.sku}: qty kirim (${item.qty_shipped}) melebihi qty PO (${item.ordered_qty}). ` +
          `Pastikan ada laporan OVERPRODUCTION variance yang mendukung.`
        );
      }
    }
    const payload = {
      ...form,
      items: validItems.map(i => ({...i, qty_shipped: Number(i.qty_shipped), ordered_qty: Number(i.ordered_qty)})),
      source_receipt_ids: form.source_receipt_ids,
      receiver_type: 'buyer',
    };
    if (continueShip) {
      payload.shipment_id = continueShip.id;
      delete payload.shipment_number;   // nomor surat jalan induk tidak boleh berubah
    }
    try {
      const data = await apiPost('/buyer-shipments', payload);
      toast.success(continueShip
        ? `Dispatch #${data.dispatch_seq || ''} ditambahkan ke surat jalan ${data.shipment_number || ''}`
        : `Shipment ${data.shipment_number || ''} berhasil dibuat`);
      setShowModal(false);
      setContinueShip(null);
      fetchAll();
    } catch (err) { toast.error(err.message || 'Gagal membuat buyer shipment'); }
  };

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/buyer-shipments/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
    } catch (e) { toast.error(e.message || 'Gagal memuat detail'); }
  };

  const recvTooltip = (item) => (item.received_history || []).map(h =>
    `${fmtDate(h.edited_at)} • ${h.old_qty}→${h.new_qty} pcs • ${h.edited_by}${h.reason ? ': ' + h.reason : ''}`
  ).join('\n');

  const openRecv = (item, dispatchSeq) => {
    const current = item.qty_received != null ? item.qty_received : item.qty_shipped;
    setRecvItem({ ...item, dispatch_seq: item.dispatch_seq || dispatchSeq });
    setRecvForm({ qty_received: String(current ?? 0), reason: '' });
  };

  const handleSaveRecv = async (e) => {
    e.preventDefault();
    if (recvForm.qty_received === '' || Number(recvForm.qty_received) < 0) { toast.error('Qty diterima tidak valid'); return; }
    setRecvLoading(true);
    try {
      const res = await apiPut(`/buyer-shipment-items/${recvItem.id}/received`, {
        qty_received: Number(recvForm.qty_received),
        reason: recvForm.reason.trim(),
      });
      const v = res?.variance ?? 0;
      const bs = res?.buyer_short;
      toast.success(
        `Qty diterima disimpan: ${res?.qty_received} pcs`
        + (bs
          ? ` · ${bs.qty_short} pcs BELUM SAMPAI → catatan selisih ${bs.short_number} dibuka, `
            + 'dokumen surat jalan dikoreksi ke qty diterima & stok FG dikembalikan '
            + '(siap dikirim ulang)'
          : ` (selisih ${v} pcs)`),
        { duration: bs ? 10000 : 5000 });
      setRecvItem(null);
      if (detailData?.id) await openDetail({ id: detailData.id });
      fetchAll();
    } catch (err) { toast.error(err.message || 'Gagal menyimpan qty diterima'); }
    finally { setRecvLoading(false); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/buyer-shipments/${confirmDelete.id}`);
      setConfirmDelete(null);
      fetchAll();
    } catch (e) { toast.error(e.message || 'Gagal menghapus'); }
  };

  // ── Keputusan atas selisih terima buyer (GAP G) ─────────────────────────
  const submitResolveBuyerShort = async () => {
    if (!resolveBShort) return;
    setBResSaving(true);
    try {
      const res = await apiPost(`/buyer-shorts/${resolveBShort.id}/resolve`, {
        resolution: bResType, notes: bResNotes.trim(),
      });
      const wo = res?.short?.stock_writeoff_qty;
      toast.success(`Selisih ${resolveBShort.short_number} diselesaikan`
        + (wo ? ` · ${wo} pcs stok FG dihapusbukukan (barang dinyatakan hilang)` : ''),
        { duration: 8000 });
      setResolveBShort(null); setBResNotes('');
      fetchAll();
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan keputusan selisih');
    } finally { setBResSaving(false); }
  };

  const downloadPDF = async (row) => {
    try {
      const res = await apiFetch(`/export-pdf?type=buyer-shipment&id=${row.id}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Buyer-Shipment-${row.shipment_number || row.id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error('Gagal mengunduh PDF: ' + (err.detail || `HTTP ${res.status}`));
      }
    } catch (e) { toast.error('Error: ' + e.message); }
  };

  const [expandedRows, setExpandedRows] = useState({});
  // FASE 22 (keluhan #6) — detail konsolidasi (rincian per PO, sumber penerimaan,
  // child shipment) dimuat saat baris dibuka. Dulu data ini HANYA ada di respons
  // backend dan tidak pernah dirender, sehingga owner menyimpulkan "child
  // shipment tidak bisa diambil datanya".
  const [shipDetail, setShipDetail] = useState({});   // {id: 'loading' | detail}
  const toggleExpand = async (id) => {
    const willOpen = !expandedRows[id];
    setExpandedRows(prev => ({ ...prev, [id]: willOpen }));
    if (willOpen && !shipDetail[id]) {
      setShipDetail(prev => ({ ...prev, [id]: 'loading' }));
      try {
        const d = await apiGet(`/buyer-shipments/${id}`);
        setShipDetail(prev => ({ ...prev, [id]: d || {} }));
      } catch (e) {
        setShipDetail(prev => ({ ...prev, [id]: {} }));
      }
    }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const fmtNum = (v) => (v || 0).toLocaleString('id-ID');

  const columns = [
    { key: '__expand', label: '', render: (_, row) => (
      <button type="button" onClick={(e) => { e.stopPropagation(); toggleExpand(row.id); }}
        data-testid={`shipment-expand-${row.shipment_number}`}
        title={expandedRows[row.id] ? 'Tutup rincian' : 'Buka rincian (dispatch, per PO, child shipment)'}
        className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors">
        <span className="text-xs">{expandedRows[row.id] ? '▼' : '▶'}</span>
      </button>
    ) },
    { key: 'shipment_number', label: 'No. Shipment', render: (v, row) => (
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-bold text-blue-700 whitespace-nowrap">{v}</span>
        <BizBadge type={row.business_type} size="xs" />
        {/* FASE 22 (keluhan #6): bedakan surat jalan GABUNGAN dan deklarasi
            vendor→DA. Dulu semuanya tampak sama dan kolom No. PO kosong pada
            surat jalan gabungan sehingga isinya tak bisa ditebak. */}
        {row.is_consolidated && (
          <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 text-[10px] font-bold whitespace-nowrap"
            title={`Gabungan ${(row.po_numbers || []).length} PO`}>GABUNGAN</span>
        )}
        {row.receiver_type === 'da' && (
          <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-bold whitespace-nowrap"
            title="Deklarasi kirim dari vendor CMT ke DA (bukan pengiriman ke buyer)">VENDOR → DA</span>
        )}
      </div>
    ) },
    { key: 'po_number', label: 'No. PO', render: (v, row) => {
      const nums = row.po_numbers && row.po_numbers.length ? row.po_numbers : (v ? [v] : []);
      if (nums.length === 0) return <span className="font-mono text-xs text-muted-foreground">-</span>;
      if (nums.length === 1) return <span className="font-mono text-xs text-foreground/90">{nums[0]}</span>;
      return (
        <div className="text-xs">
          <div className="font-semibold text-purple-700 whitespace-nowrap">{nums.length} PO (gabungan)</div>
          <div className="font-mono text-[11px] text-muted-foreground break-words">{nums.join(', ')}</div>
        </div>
      );
    } },
    { key: 'customer_name', label: 'Customer' },
    { key: 'progress', label: 'Progres Pengiriman', render: (_, row) => {
      // Use backend-calculated totals (fixed ordered_qty denominator)
      const totalOrdered = row.total_ordered || 0;
      const totalShipped = row.total_shipped || 0;
      const remaining = row.remaining || 0;
      const progressPct = row.progress_pct || 0;
      const dispatchCount = row.dispatch_count || 0;
      
      return (
        <div className="min-w-[180px]">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-bold text-foreground/90">{fmtNum(totalShipped)} / {fmtNum(totalOrdered)} pcs</span>
            <span className="font-bold text-blue-600">{progressPct}%</span>
          </div>
          <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all ${progressPct >= 100 ? 'bg-emerald-500' : progressPct > 0 ? 'bg-blue-500' : 'bg-muted'}`}
              style={{ width: `${Math.min(progressPct, 100)}%` }} />
          </div>
          <div className="flex items-center justify-between text-[10px] text-muted-foreground/70 mt-0.5">
            <span>Sisa: {fmtNum(remaining)} pcs</span>
            {dispatchCount > 0 && <span>{dispatchCount} dispatch</span>}
          </div>
        </div>
      );
    }},
    { key: 'status', label: 'Status', render: (_, row) => {
      const pct = row.progress_pct || 0;
      const s = pct >= 100 ? 'Fully Shipped' : pct > 0 ? 'Partially Shipped' : 'Pending';
      const color = s === 'Fully Shipped' ? 'bg-emerald-100 text-emerald-700' : 
                    s === 'Partially Shipped' ? 'bg-amber-100 text-amber-700' : 'bg-muted text-muted-foreground';
      return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{s}</span>;
    }},
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      <div className="flex items-center gap-1">
        {canEdit && (row.progress_pct || 0) < 100 && (
          <button onClick={(e) => { e.stopPropagation(); openContinueModal(row); }}
            className="px-2 py-1 rounded bg-blue-600 text-white text-[11px] font-semibold hover:bg-blue-700 whitespace-nowrap flex items-center gap-1"
            data-testid={`continue-dispatch-${row.shipment_number}`}
            title="Kirim sisa pada surat jalan INI (dispatch lanjutan, nomor tidak berubah)">
            <Plus className="w-3 h-3" /> Dispatch
          </button>
        )}
        <button onClick={() => openDetail(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail">
          <Eye className="w-4 h-4" />
        </button>
        <button onClick={() => downloadPDF(row)} className="p-1.5 rounded hover:bg-emerald-50 text-emerald-600" title="Cetak Surat Jalan (PDF)" data-testid="buyer-shipment-print-sj">
          <Download className="w-4 h-4" />
        </button>
        {canCreate && (
          <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus">
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    )}
  ];

  const expandedRow = (row) => {
    if (!expandedRows[row.id]) return null;
    const detail = shipDetail[row.id];
    const det = (detail && detail !== 'loading') ? detail : null;
    const poBreak = (det?.po_breakdown) || [];
    const childShips = (det?.child_shipments) || [];
    const srcReceipts = (det?.source_receipts) || [];
    const parentShip = det?.parent_shipment;

    const consolidationPanel = (
      <div className="mb-3 space-y-3" data-testid={`shipment-consolidation-${row.id}`}>
        {detail === 'loading' && (
          <p className="text-xs text-muted-foreground">Memuat rincian konsolidasi…</p>
        )}
        {poBreak.length > 0 && (
          <div className="bg-card rounded-lg border border-purple-200 overflow-hidden">
            <div className="px-4 py-2 bg-purple-50 border-b border-purple-100 text-xs font-semibold text-purple-800">
              Rincian per PO {poBreak.length > 1 ? `(surat jalan GABUNGAN — ${poBreak.length} PO)` : ''}
            </div>
            <div className="max-w-full overflow-x-auto">
              <table className="w-full text-xs min-w-[520px]">
                <thead className="bg-muted/40">
                  <tr>
                    <th className="text-left px-3 py-1.5 text-muted-foreground">No. PO</th>
                    <th className="text-left px-3 py-1.5 text-muted-foreground">Buyer</th>
                    <th className="text-right px-3 py-1.5 text-muted-foreground">Item</th>
                    <th className="text-right px-3 py-1.5 text-muted-foreground">Qty Kirim</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {poBreak.map((p, i) => (
                    <tr key={p.po_id || i}>
                      <td className="px-3 py-1.5 font-mono text-blue-700 whitespace-nowrap">{p.po_number || '-'}</td>
                      <td className="px-3 py-1.5 text-foreground/90">{p.customer_name || p.buyer_name || '-'}</td>
                      <td className="px-3 py-1.5 text-right text-muted-foreground">{fmtNum(p.line_count ?? p.item_count ?? (p.items || []).length)}</td>
                      <td className="px-3 py-1.5 text-right font-bold text-emerald-700">{fmtNum(p.qty_shipped)} pcs</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {srcReceipts.length > 0 && (
          <div className="bg-card rounded-lg border border-emerald-200 p-3">
            <p className="text-xs font-semibold text-emerald-800 mb-1.5">Sumber Penerimaan CMT ({srcReceipts.length})</p>
            <div className="flex flex-wrap gap-1.5">
              {srcReceipts.map((r, i) => (
                <span key={r.id || i} className="px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200 text-[11px] font-mono text-emerald-800 whitespace-nowrap">
                  {r.receipt_code || r.id} {r.po_number ? `· ${r.po_number}` : ''}
                </span>
              ))}
            </div>
          </div>
        )}
        {(childShips.length > 0 || parentShip) && (
          <div className="bg-card rounded-lg border border-blue-200 p-3">
            {parentShip && (
              <p className="text-xs text-blue-800 mb-1.5">
                Bagian dari surat jalan induk:{' '}
                <span className="font-mono font-semibold">{parentShip.shipment_number}</span>
              </p>
            )}
            {childShips.length > 0 && (
              <>
                <p className="text-xs font-semibold text-blue-800 mb-1.5">Child Shipment ({childShips.length})</p>
                <div className="space-y-1">
                  {childShips.map((c, i) => (
                    <div key={c.id || i} className="flex items-center justify-between gap-2 text-[11px] bg-blue-50/60 rounded px-2 py-1">
                      <span className="font-mono font-semibold text-blue-800 whitespace-nowrap">{c.shipment_number}</span>
                      <span className="text-muted-foreground">{c.po_number || '-'}</span>
                      <span className="font-semibold text-emerald-700 whitespace-nowrap">
                        {fmtNum((c.items || []).reduce((s, x) => s + (x.qty_shipped || 0), 0))} pcs
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
        {det && childShips.length === 0 && !parentShip && (
          <p className="text-[11px] text-muted-foreground">
            Child shipment: tidak ada (surat jalan ini bukan bagian dari rantai tambahan/pengganti).
          </p>
        )}
      </div>
    );

    if (!row.items || row.items.length === 0) {
      return (
        <div className="bg-blue-50/30 border-t border-blue-100 px-6 py-3">
          {consolidationPanel}
          <p className="text-xs text-muted-foreground">Belum ada item pada surat jalan ini.</p>
        </div>
      );
    }

    // Group items by dispatch_seq
    const dispatchGroups = {};
    const poItemCumulative = {};
    
    for (const item of row.items) {
      const seq = item.dispatch_seq || 1;
      if (!dispatchGroups[seq]) {
        dispatchGroups[seq] = { dispatch_seq: seq, dispatch_date: item.dispatch_date || item.created_at, items: [], total_qty: 0 };
      }
      dispatchGroups[seq].items.push(item);
      dispatchGroups[seq].total_qty += item.qty_shipped || 0;
    }
    
    const dispatches = Object.values(dispatchGroups).sort((a, b) => a.dispatch_seq - b.dispatch_seq);
    let cumulativeTotal = 0;
    // SESI #38 — biaya batch (FIFO) yang IKUT keluar bersama barangnya. Angka ini
    // yang dipakai jurnal COGS, jadi ia harus bisa dibaca di layar yang sama —
    // kalau tidak, staf tidak punya cara memeriksa kenapa laba terlihat aneh.
    const fmtRp = (v) => 'Rp ' + Math.round(v || 0).toLocaleString('id-ID');
    
    return (
      <div className="bg-blue-50/30 border-t border-blue-100 px-6 py-3">
        {consolidationPanel}
        <p className="text-xs font-semibold text-blue-700 mb-3 uppercase tracking-wide flex items-center gap-1.5">
          <History className="w-3.5 h-3.5" /> Riwayat Dispatch ({dispatches.length} round)
        </p>
        <div className="space-y-3">
          {dispatches.map((d, di) => {
            cumulativeTotal += d.total_qty;
            const dCogs = d.items.reduce((s, i) => s + Number(i.fg_cogs || 0), 0);
            const dUncosted = d.items.reduce((s, i) => s + Number(i.fg_cogs_uncosted_qty || 0), 0);
            return (
              <div key={d.dispatch_seq} className="bg-card rounded-lg border border-border overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-muted/40 border-b border-border/60">
                  <div className="flex items-center gap-3">
                    <span className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center">#{d.dispatch_seq}</span>
                    <div>
                      <p className="text-sm font-semibold text-foreground/90">Dispatch #{d.dispatch_seq}</p>
                      <p className="text-[10px] text-muted-foreground/70">{fmtDate(d.dispatch_date)}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-emerald-700">+{fmtNum(d.total_qty)} pcs</p>
                    <p className="text-[10px] text-muted-foreground/70">Kumulatif: {fmtNum(cumulativeTotal)} / {fmtNum(row.total_ordered || 0)} pcs</p>
                    {dCogs > 0 && (
                      <p className="text-[10px] text-indigo-700 font-semibold" data-testid={`dispatch-cogs-${d.dispatch_seq}`}>
                        HPP batch keluar: {fmtRp(dCogs)}
                        {dUncosted > 0 && (
                          <span className="ml-1 text-amber-700">· {fmtNum(dUncosted)} pcs belum berbiaya</span>
                        )}
                      </p>
                    )}
                  </div>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border/60">
                      <th className="text-left py-1.5 px-3 text-amber-700 font-semibold">Serial</th>
                      <th className="text-left py-1.5 px-3 text-muted-foreground">SKU</th>
                      <th className="text-left py-1.5 px-3 text-muted-foreground">Produk</th>
                      <th className="text-left py-1.5 px-3 text-muted-foreground">Size/Warna</th>
                      <th className="text-right py-1.5 px-3 text-muted-foreground">Qty Kirim</th>
                      <th className="text-right py-1.5 px-3 text-muted-foreground">HPP Batch (FIFO)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {d.items.map((item, idx) => (
                      <tr key={item.id || idx} className="hover:bg-blue-50/30">
                        <td className="py-1.5 px-3 font-mono text-amber-700 font-semibold">{item.serial_number || '—'}</td>
                        <td className="py-1.5 px-3 font-mono text-blue-700">{item.sku || '-'}</td>
                        <td className="py-1.5 px-3 text-foreground/90">{item.product_name}</td>
                        <td className="py-1.5 px-3 text-muted-foreground">{item.size || '-'}/{item.color || '-'}</td>
                        <td className="py-1.5 px-3 text-right font-bold text-emerald-700">{fmtNum(item.qty_shipped)} pcs</td>
                        <td className="py-1.5 px-3 text-right" data-testid={`item-cogs-${item.id || idx}`}>
                          {Number(item.fg_cogs || 0) <= 0 ? (
                            <span className="text-muted-foreground/60" title={item.fg_cogs == null
                              ? 'Barang ini keluar sebelum lapisan biaya batch dipasang'
                              : 'Batch masuknya belum punya biaya (BOM/upah jahit belum lengkap) — bukan Rp 0'}>
                              {item.fg_cogs == null ? '—' : 'belum berbiaya'}
                            </span>
                          ) : (
                            <span className="font-semibold text-indigo-700">{fmtRp(item.fg_cogs)}</span>
                          )}
                          {Number(item.fg_cogs_uncosted_qty || 0) > 0 && (
                            <span className="block text-[10px] text-amber-700">
                              {fmtNum(item.fg_cogs_uncosted_qty)} pcs tanpa lapisan biaya
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
        {/* Summary bar */}
        <div className="mt-3 bg-blue-100 rounded-lg p-3 flex items-center justify-between">
          <span className="text-xs font-semibold text-blue-800">Total Kumulatif</span>
          <span className="text-sm font-bold text-blue-800">{fmtNum(cumulativeTotal)} / {fmtNum(row.total_ordered || 0)} pcs ({row.progress_pct || 0}%)</span>
        </div>
      </div>
    );
  };

  // Summary stats using backend-calculated totals
  const showBizFilter = !businessType;
  const bizCounts = {
    all: shipments.length,
    internal: shipments.filter(s => s.business_type !== 'maklon').length,
    maklon: shipments.filter(s => s.business_type === 'maklon').length,
  };
  // FASE 22 (keluhan #6) — daftar ini dulu MENCAMPUR dua hal berbeda:
  // (a) surat jalan DA → buyer, dan (b) deklarasi kirim vendor CMT → DA
  // (`receiver_type='da'`, nomor SJ-CMT-DA-…). Akibatnya "Total Shipment" dan
  // progres pengiriman ke buyer ikut terhitung dari dokumen yang bukan
  // pengiriman ke buyer. Sekarang dipisah dengan saringan yang jelas.
  const isToBuyer = (s) => (s.receiver_type || 'buyer') !== 'da';
  const recvCounts = {
    buyer: shipments.filter(isToBuyer).length,
    da: shipments.filter(s => !isToBuyer(s)).length,
    all: shipments.length,
  };
  const filteredShipments = shipments
    .filter(s => !showBizFilter || matchBiz(s.business_type, bizFilter))
    .filter(s => recvFilter === 'all' ? true : recvFilter === 'da' ? !isToBuyer(s) : isToBuyer(s));
  const totalShipmentCount = filteredShipments.length;
  const fullyShipped = filteredShipments.filter(s => (s.progress_pct || 0) >= 100).length;
  const partialShipped = filteredShipments.filter(s => (s.progress_pct || 0) > 0 && (s.progress_pct || 0) < 100).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            Buyer Shipment
            {businessType && <BizBadge type={businessType} />}
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Pengiriman produk jadi ke buyer — support partial shipment multi-dispatch
            {businessType && (
              <span className="ml-1 font-medium text-foreground/80">
                · Menampilkan data <strong>{businessType === 'maklon' ? 'Produksi Maklon (CMT)' : 'Produksi Internal'}</strong>.
              </span>
            )}
          </p>
        </div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      {/* Tab toggle */}
      <div className="flex items-center gap-1 border-b border-border">
        <button onClick={() => setViewMode('list')} data-testid="tab-shipment-list"
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${viewMode === 'list' ? 'border-blue-600 text-blue-700' : 'border-transparent text-muted-foreground hover:text-foreground/90'}`}>
          <ListChecks className="w-4 h-4" /> Daftar Pengiriman
        </button>
        <button onClick={() => setViewMode('variance')} data-testid="tab-receipt-variance"
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${viewMode === 'variance' ? 'border-blue-600 text-blue-700' : 'border-transparent text-muted-foreground hover:text-foreground/90'}`}>
          <BarChart3 className="w-4 h-4" /> Laporan Selisih Terima
        </button>
        {/* FASE E — DAFTAR KEKURANGAN KIRIM. Sengaja TAB di layar ini, bukan menu
            baru: pekerjaannya sama (mengirim ke buyer), hanya sudut pandangnya
            "apa yang belum" bukan "apa yang sudah". */}
        <button onClick={() => { setViewMode('outstanding'); loadOutstanding(); }} data-testid="tab-dispatch-outstanding"
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${viewMode === 'outstanding' ? 'border-blue-600 text-blue-700' : 'border-transparent text-muted-foreground hover:text-foreground/90'}`}>
          <ClipboardList className="w-4 h-4" /> Kekurangan Kirim
          {outstanding.totals?.items > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">{outstanding.totals.items}</span>
          )}
        </button>
      </div>

      {viewMode === 'outstanding' ? (
        <div className="space-y-4" data-testid="dispatch-outstanding-panel">
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Kekurangan Kirim ke Buyer</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Item yang belum habis dikirim. <strong>Sisa Bisa Kirim</strong> = siap kirim (maklon: lolos QC + hasil permak · internal: hasil produksi) − sudah dikirim.
                  Kalau sisa 0 tetapi Sisa Order masih ada, barangnya belum diterima dari CMT.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <SmartNativeSelect value={outBuyer} data-testid="outstanding-buyer-filter"
                  onChange={e => { setOutBuyer(e.target.value); loadOutstanding(e.target.value, outShowSettled); }}
                  className="border border-border rounded-lg px-3 py-1.5 text-sm bg-background text-foreground">
                  <option value="">Semua Buyer</option>
                  {(outstanding.buyers || []).map(b => <option key={b} value={b}>{b}</option>)}
                </SmartNativeSelect>
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                  <input type="checkbox" checked={outShowSettled} data-testid="outstanding-show-settled"
                    onChange={e => { setOutShowSettled(e.target.checked); loadOutstanding(outBuyer, e.target.checked); }} />
                  Tampilkan yang sudah lunas
                </label>
                <button type="button" onClick={() => loadOutstanding()} data-testid="outstanding-refresh"
                  className="px-3 py-1.5 text-sm rounded-lg border border-border text-foreground/80 hover:bg-muted transition-colors">
                  Muat ulang
                </button>
                <button type="button" onClick={exportOutstandingCSV} data-testid="outstanding-export-csv"
                  disabled={!outstanding.items?.length}
                  className="px-3 py-1.5 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5">
                  <Download className="w-3.5 h-3.5" /> Unduh CSV
                </button>
              </div>
            </div>

            {outstanding.totals && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'Item Belum Lunas', value: outstanding.totals.items, testid: 'outstanding-kpi-items' },
                  { label: 'Total Qty Order', value: outstanding.totals.ordered, testid: 'outstanding-kpi-ordered' },
                  { label: 'Sudah Dikirim', value: outstanding.totals.dispatched, testid: 'outstanding-kpi-dispatched' },
                  { label: 'Siap Dikirim Sekarang', value: outstanding.totals.shippable, testid: 'outstanding-kpi-shippable' },
                ].map(k => (
                  <div key={k.label} className="rounded-lg border border-border bg-muted/30 px-3 py-2">
                    <div className="text-[11px] text-muted-foreground">{k.label}</div>
                    <div className="text-lg font-bold text-foreground" data-testid={k.testid}>{fmtNum(k.value)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── PAPAN SISA KIRIM PER PO ─────────────────────────────────────── */}
          {!outLoading && poBoard.length > 0 && (
            <div className="rounded-xl border border-blue-200 bg-blue-50/40 overflow-hidden"
              data-testid="outstanding-po-board">
              <div className="px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap border-b border-blue-200 bg-blue-50">
                <h3 className="text-sm font-semibold text-blue-900 flex items-center gap-1.5">
                  <ListChecks className="w-4 h-4" /> Papan Sisa Kirim per PO
                  <span className="px-1.5 py-0.5 rounded-full bg-blue-600 text-white text-[10px] font-bold">{poBoard.length}</span>
                </h3>
                <p className="text-[11px] text-blue-800/80">
                  Satu baris = satu PO. Tombol dispatch <strong>melanjutkan surat jalan yang belum 100%</strong>
                  {' '}(nomor tidak berubah); kalau PO belum punya surat jalan, form terbuka dengan PO itu terpilih.
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="po-board-table">
                  <thead className="bg-card/60">
                    <tr>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">No. PO</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Buyer</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Order</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sudah Dikirim</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground w-40">Progres</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sisa Order</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sisa Bisa Kirim</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Surat Jalan Berjalan</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {poBoard.map(g => (
                      <tr key={g.key} className="border-t border-blue-100 bg-card/40 hover:bg-card/80 transition-colors"
                        data-testid={`po-board-row-${g.po_number}`}>
                        <td className="px-3 py-2 font-mono text-xs text-blue-700 font-semibold">{g.po_number}</td>
                        <td className="px-3 py-2 text-foreground/90">{g.buyer || '-'}</td>
                        <td className="px-3 py-2 text-right text-muted-foreground">{fmtNum(g.ordered)}</td>
                        <td className="px-3 py-2 text-right text-amber-700">{fmtNum(g.dispatched)}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                              <div className="h-full bg-blue-600 rounded-full" style={{ width: `${g.pct}%` }} />
                            </div>
                            <span className="text-[11px] text-muted-foreground w-9 text-right">{g.pct}%</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right font-semibold text-foreground">{fmtNum(g.remaining)}</td>
                        <td className="px-3 py-2 text-right">
                          {g.shippable > 0
                            ? <span className="font-bold text-emerald-700" data-testid={`po-board-shippable-${g.po_number}`}>{fmtNum(g.shippable)}</span>
                            : <span className="text-xs text-muted-foreground">belum ada barang</span>}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs">
                          {g.openShip
                            ? <span className="text-blue-700">{g.openShip.shipment_number} <span className="text-muted-foreground">({g.openShip.progress_pct || 0}%)</span></span>
                            : <span className="text-muted-foreground/70">belum ada</span>}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {canEdit && (
                            <button type="button" disabled={g.shippable <= 0}
                              onClick={() => (g.openShip ? openContinueModal(g.openShip) : openCreateForPO(g.po_id))}
                              data-testid={`board-dispatch-${g.po_number}`}
                              title={g.shippable > 0
                                ? (g.openShip ? `Tambah dispatch ke ${g.openShip.shipment_number}` : 'Buat surat jalan pertama untuk PO ini')
                                : 'Barang belum diterima dari CMT'}
                              className="px-2.5 py-1 rounded-lg bg-blue-600 text-white text-[11px] font-semibold hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1 whitespace-nowrap">
                              <Plus className="w-3 h-3" /> {g.openShip ? 'Lanjut Dispatch' : 'Dispatch Baru'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {outLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-11 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : (outstanding.items || []).length === 0 ? (            <div className="rounded-xl border border-border bg-card py-12 text-center" data-testid="outstanding-empty">
              <CheckCircle className="w-10 h-10 mx-auto mb-3 text-emerald-600 opacity-60" />
              <p className="text-sm text-foreground/80 font-medium">Tidak ada kekurangan kirim.</p>
              <p className="text-xs text-muted-foreground mt-1">Semua item sudah terkirim penuh ke buyer.</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border bg-card">
              <table className="w-full text-sm" data-testid="outstanding-table">
                <thead className="bg-muted/40">
                  <tr>
                    <th className="text-left px-3 py-2 text-xs text-muted-foreground">No. PO</th>
                    <th className="text-left px-3 py-2 text-xs text-muted-foreground">Buyer</th>
                    <th className="text-left px-3 py-2 text-xs text-muted-foreground">SKU</th>
                    <th className="text-left px-3 py-2 text-xs text-muted-foreground">Produk</th>
                    <th className="text-left px-3 py-2 text-xs text-muted-foreground">Size/Warna</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Order</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground" title="Maklon: lolos QC penerimaan CMT · Internal: hasil produksi job">Siap Kirim</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Permak</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Dikirim</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sisa Order</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sisa Bisa Kirim</th>
                    <th className="text-right px-3 py-2 text-xs text-muted-foreground">Stok FG</th>
                  </tr>
                </thead>
                <tbody>
                  {outstanding.items.map(r => (
                    <tr key={r.key} className="border-t border-border/60 hover:bg-muted/20 transition-colors"
                      data-testid={`outstanding-row-${r.sku || r.key}`}>
                      <td className="px-3 py-2 font-mono text-xs text-blue-700">{r.po_number || '-'}</td>
                      <td className="px-3 py-2 text-foreground/90">{r.buyer || '-'}</td>
                      <td className="px-3 py-2 font-mono text-xs text-blue-600">{r.sku || '-'}</td>
                      <td className="px-3 py-2 text-foreground/90">{r.product_name || '-'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.size || '-'}/{r.color || '-'}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{fmtNum(r.ordered)}</td>
                      <td className="px-3 py-2 text-right text-foreground/80">
                        {r.source === 'internal'
                          ? <span title="Hasil produksi internal">{fmtNum(r.internal_produced)} <span className="text-[10px] text-blue-700 font-semibold">produksi</span></span>
                          : <span title="Lolos QC penerimaan dari CMT">{fmtNum(r.good_from_cmt)} <span className="text-[10px] text-muted-foreground">QC</span></span>}
                      </td>
                      <td className="px-3 py-2 text-right text-emerald-700">{r.source === 'internal' ? '—' : (r.reworked_ok ? `+${fmtNum(r.reworked_ok)}` : '0')}</td>
                      <td className="px-3 py-2 text-right text-amber-700">{fmtNum(r.dispatched)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-foreground">{fmtNum(r.remaining_vs_order)}</td>
                      <td className="px-3 py-2 text-right">
                        {r.shippable > 0
                          ? <span className="font-bold text-emerald-700" data-testid={`outstanding-shippable-${r.sku || r.key}`}>{fmtNum(r.shippable)}</span>
                          : <span className="text-xs text-muted-foreground" title={r.source === 'internal' ? 'Belum ada hasil produksi' : 'Barang belum diterima dari CMT'}>belum ada barang</span>}
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {r.fg_stock == null
                          ? <span title="Master FG untuk SKU ini belum ada di gudang (bukan stok 0)">—</span>
                          : fmtNum(Math.round(r.fg_stock))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : viewMode === 'variance' ? (
        <BuyerReceiptVarianceReport />
      ) : (
      <>
      {/* ── SELISIH TERIMA BUYER (barang belum sampai) ─────────────────────
          Aturan owner: dokumen surat jalan dikoreksi ke qty yang benar-benar
          diterima buyer; selisihnya jadi dokumen sendiri, barangnya kembali ke
          stok FG (siap dikirim ulang). Keputusan tanggungan (CMT/DA) diambil
          saat PO ditutup. */}
      {buyerShorts.items?.length > 0 && (
        <div className="rounded-xl bg-card border border-rose-300 overflow-hidden" data-testid="buyer-short-panel">
          <div className="px-3 py-2 bg-rose-50 border-b border-rose-200 flex items-center gap-2 flex-wrap">
            <Package className="w-4 h-4 text-rose-700 shrink-0" />
            <span className="text-xs font-bold text-rose-900">
              Selisih Terima Buyer — {fmtNum(buyerShorts.total_qty_open)} pcs BELUM SAMPAI
            </span>
            <span className="text-[11px] text-rose-700">
              Barang sudah dikembalikan ke stok FG · kirim ulang, atau tentukan tanggungan (CMT / DA).
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[900px]">
              <thead className="bg-muted/40">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2 font-semibold">No. Selisih</th>
                  <th className="px-3 py-2 font-semibold">Surat Jalan / PO</th>
                  <th className="px-3 py-2 font-semibold">Buyer</th>
                  <th className="px-3 py-2 font-semibold">SKU</th>
                  <th className="px-3 py-2 font-semibold text-right">Dikirim</th>
                  <th className="px-3 py-2 font-semibold text-right">Diterima</th>
                  <th className="px-3 py-2 font-semibold text-right">Belum sampai</th>
                  <th className="px-3 py-2 font-semibold text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {buyerShorts.items.map(s => (
                  <tr key={s.id} className="border-t border-border/60">
                    <td className="px-3 py-2 font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">{s.short_number}</td>
                    <td className="px-3 py-2 text-foreground">
                      <div className="font-medium truncate max-w-[170px]">{s.shipment_number || '—'}</div>
                      <div className="text-[11px] text-muted-foreground truncate max-w-[170px]">{s.po_number || '—'}</div>
                    </td>
                    <td className="px-3 py-2 text-foreground truncate max-w-[150px]">{s.customer_name || '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-foreground whitespace-nowrap">{s.sku || '—'}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{fmtNum(s.qty_shipped_claimed)}</td>
                    <td className="px-3 py-2 text-right text-emerald-700 font-medium">{fmtNum(s.qty_received)}</td>
                    <td className="px-3 py-2 text-right font-bold text-rose-700">{fmtNum(s.qty_open ?? s.qty_short)}</td>
                    <td className="px-3 py-2 text-right">
                      <button data-testid={`buyer-short-resolve-${s.short_number}`}
                        onClick={() => { setResolveBShort(s); setBResType('dikirim_ulang'); setBResNotes(''); }}
                        className="h-7 px-2.5 rounded-md bg-rose-600 text-white text-[11px] font-semibold hover:bg-rose-700 whitespace-nowrap">
                        Putuskan
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Shipment', value: totalShipmentCount, icon: TruckIcon, color: 'text-blue-700', bg: 'bg-blue-50' },
          { label: 'Fully Shipped', value: fullyShipped, icon: CheckCircle, color: 'text-emerald-700', bg: 'bg-emerald-50' },
          { label: 'Partially Shipped', value: partialShipped, icon: Clock, color: 'text-amber-700', bg: 'bg-amber-50' },
        ].map(s => {
          const Icon = s.icon;
          return (
            <div key={s.label} className={`${s.bg} rounded-xl p-4 border border-transparent`}>
              <div className="flex items-center gap-3">
                <Icon className={`w-6 h-6 ${s.color}`} />
                <div>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                  <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        {canEdit && (
          <button onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 shadow-sm">
            <Plus className="w-4 h-4" /> Buat Buyer Shipment
          </button>
        )}
        <ImportExportPanel importType={null} exportType="buyer-shipments" />
        <div className="inline-flex rounded-lg border border-border overflow-hidden ml-2" data-testid="shipment-receiver-filter">
          {[
            { k: 'buyer', label: `Ke Buyer (${recvCounts.buyer})` },
            { k: 'da', label: `Deklarasi Vendor → DA (${recvCounts.da})` },
            { k: 'all', label: `Semua (${recvCounts.all})` },
          ].map(t => (
            <button key={t.k} onClick={() => setRecvFilter(t.k)}
              data-testid={`shipment-recv-${t.k}`}
              className={`px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${recvFilter === t.k ? 'bg-blue-600 text-white' : 'bg-card text-muted-foreground hover:bg-muted/60'}`}>
              {t.label}
            </button>
          ))}
        </div>
        {showBizFilter && <div className="ml-auto"><BizFilter value={bizFilter} onChange={setBizFilter} counts={bizCounts} /></div>}
      </div>

      <DataTable columns={columns} data={filteredShipments} loading={loading}
        expandedRow={expandedRow}
        storageKey="buyerShipments"
        onRowClick={(row) => toggleExpand(row.id)} />
      </>
      )}

      {/* Create Modal */}
      {showModal && (
        <Modal title={continueShip ? `Lanjutkan Dispatch — ${continueShip.shipment_number}` : 'Buat Buyer Shipment'}
          onClose={() => { setShowModal(false); setContinueShip(null); }} size="2xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            {continueShip && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900" data-testid="continue-dispatch-banner">
                Kiriman ini ditambahkan sebagai <strong>dispatch berikutnya</strong> pada surat jalan{' '}
                <span className="font-mono font-semibold">{continueShip.shipment_number}</span> — nomornya TIDAK berubah,
                dan progres pengiriman PO naik pada surat jalan yang sama. Qty maksimal tetap
                &quot;sisa bisa kirim&quot; (lolos QC + hasil permak − yang sudah dikirim).
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">No. Surat Jalan <span className="text-muted-foreground font-normal">{continueShip ? '(tetap, tidak berubah)' : '(kosongkan = auto)'}</span></label>
                <input type="text" placeholder="otomatis sesuai format" disabled={!!continueShip}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
                  value={form.shipment_number} onChange={e => setForm(f => ({...f, shipment_number: e.target.value}))} data-testid="sj-number-input" />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm"
                  value={form.shipment_date} onChange={e => setForm(f => ({...f, shipment_date: e.target.value}))} />
              </div>
            </div>

            {/* Phase D: consolidation toggle */}
            <label className={`flex items-center gap-3 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 ${continueShip ? 'opacity-60' : 'cursor-pointer'}`} data-testid="consolidate-toggle">
              <input type="checkbox" checked={consolidate} disabled={!!continueShip}
                onChange={e => toggleConsolidateMode(e.target.checked)} className="w-4 h-4" />
              <span className="text-sm">
                <span className="font-semibold text-violet-900">Gabungkan beberapa PO (konsolidasi)</span>
                <span className="block text-xs text-violet-700">1 surat jalan untuk banyak PO milik buyer yang sama — progress tetap dihitung per PO.</span>
              </span>
            </label>

            {/* Single-PO picker */}
            {!consolidate && (
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Pilih PO *</label>
              <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:opacity-60"
                data-testid="buyer-shipment-po-select"
                disabled={!!continueShip}
                value={form.po_id} onChange={e => loadPOItems(e.target.value)}>
                <option value="">-- Pilih PO --</option>
                {pos.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.po_number} | {p.vendor_name || ''} | {p.created_at ? new Date(p.created_at).toLocaleDateString('id-ID') : ''}
                  </option>
                ))}
              </SmartNativeSelect>
            </div>
            )}

            {/* Phase D: consolidation — buyer + multi-PO receipt picker */}
            {consolidate && (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-foreground/90 mb-1">Pilih Buyer *</label>
                  <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm"
                    value={consBuyer} onChange={e => selectConsBuyer(e.target.value)} data-testid="cons-buyer-select">
                    <option value="">{consLoading ? 'Memuat…' : '-- Pilih Buyer --'}</option>
                    {consBuyers.map(b => <option key={b} value={b}>{b}</option>)}
                  </SmartNativeSelect>
                  {!consLoading && consBuyers.length === 0 && (
                    <p className="text-xs text-amber-700 mt-1">Belum ada CMT Receipt (Approved) yang bisa dikirim. Proses &quot;Terima FG dari CMT&quot; dulu.</p>
                  )}
                </div>
                {consBuyer && (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 space-y-2">
                    <div className="text-sm font-semibold text-emerald-900 flex items-center gap-2">
                      <ClipboardCheck className="w-4 h-4" /> Pilih CMT Receipt (Approved) lintas-PO
                    </div>
                    <div className="max-h-56 overflow-y-auto space-y-1">
                      {consReceiptsForBuyer.map(r => {
                        const actual = r.total_actual ?? r.total_qty_actual ?? 0;
                        const rejected = r.total_rejected ?? 0;
                        return (
                          <label key={r.id} className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-white/60 cursor-pointer text-sm"
                            data-testid={`cons-receipt-${r.receipt_code}`}>
                            <input type="checkbox" checked={form.source_receipt_ids.includes(r.id)} onChange={() => toggleConsReceipt(r)} className="mt-0.5" />
                            <span className="flex-1">
                              <span className="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-semibold mr-1">{r._po_number}</span>
                              <span className="font-mono text-xs">{r.receipt_code}</span>
                              {/* FASE E — label diperjelas: angka ini qty LOLOS QC, bukan
                                  "sisa bisa kirim". Dulu tertulis "actual 90 pcs" lalu
                                  tabel menampilkan 80, dan tidak ada yang menjelaskan
                                  bedanya. Sisa bisa kirim ada di kolom tabel. */}
                              <span className="text-muted-foreground text-xs ml-2">· {r.cmt_name || '—'} · lolos QC {Number(actual).toLocaleString('id-ID')} pcs
                                {rejected > 0 && <span className="text-red-600"> (reject {Number(rejected).toLocaleString('id-ID')})</span>}
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                    {form.source_receipt_ids.length > 0 && (
                      <div className="text-xs text-emerald-800">Dipilih: <strong>{form.source_receipt_ids.length}</strong> receipt dari <strong>{new Set(form.items.map(i => i.po_number)).size}</strong> PO.
                        {capTotals && <> Sisa bisa kirim <strong>{Number(capTotals.shippable || 0).toLocaleString('id-ID')} pcs</strong> (lolos QC {Number(capTotals.good_from_cmt || 0).toLocaleString('id-ID')}{capTotals.reworked_ok ? ` + permak ${Number(capTotals.reworked_ok).toLocaleString('id-ID')}` : ''} − sudah dikirim {Number(capTotals.dispatched || 0).toLocaleString('id-ID')}).</>}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {!consolidate && form.po_id && selectedPO?.business_type === 'internal' && (
              <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900" data-testid="internal-dispatch-info">
                <div className="text-sm font-semibold">PO Produksi Internal — sumber kirim = hasil produksi</div>
                Tidak perlu CMT Receipt. Batas qty kirim = <strong>hasil produksi job internal − sudah dikirim</strong>;
                stok FG gudang (hasil scan-in) tetap menjadi pagar terakhir saat Simpan.
                {capLoading ? ' Menghitung sisa bisa kirim…'
                  : capTotals ? <> Sisa bisa kirim <strong>{Number(capTotals.shippable || 0).toLocaleString('id-ID')} pcs</strong> (diproduksi {Number(capTotals.internal_produced || 0).toLocaleString('id-ID')} − sudah dikirim {Number(capTotals.dispatched || 0).toLocaleString('id-ID')}).</>
                  : null}
              </div>
            )}
            {/* Phase B: source_receipt_ids picker (DA dispatch wajib punya CMT Receipt Approved) */}
            {!consolidate && form.po_id && selectedPO?.business_type !== 'internal' && (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 space-y-2">
                <div className="flex items-start gap-2">
                  <ClipboardCheck className="w-4 h-4 mt-0.5 text-emerald-700" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-emerald-900">
                      Sumber FG (Phase B): pilih CMT Receipt yang sudah di-approve
                    </div>
                    <div className="text-xs text-emerald-800 mt-0.5">
                      Dispatch DA→Buyer wajib mengacu ke penerimaan FG dari CMT
                      (<code>cmt_receipts</code> status <em>Approved</em>). Batas qty kirim
                      = <strong>lolos QC + hasil permak − sudah dikirim</strong> (lihat kolom
                      tabel di bawah).
                    </div>
                  </div>
                </div>
                {availableReceipts.length === 0 ? (
                  <div className="text-xs px-2 py-1 bg-amber-50 border border-amber-200 rounded text-amber-800">
                    Belum ada CMT Receipt status <strong>Approved</strong> untuk PO ini. Minta DA admin
                    proses &quot;Terima FG dari CMT&quot; dulu.
                  </div>
                ) : (
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {availableReceipts.map(r => {
                      const actual = r.total_actual ?? r.total_qty_actual ?? 0;
                      const rejected = r.total_rejected ?? 0;
                      return (
                      <label key={r.id}
                        className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-white/60 cursor-pointer text-sm"
                        data-testid={`source-receipt-${r.receipt_code}`}>
                        <input
                          type="checkbox"
                          checked={form.source_receipt_ids.includes(r.id)}
                          onChange={() => toggleSourceReceipt(r.id)}
                          className="mt-0.5"
                        />
                        <span className="flex-1">
                          <span className="font-mono text-xs">{r.receipt_code}</span>
                          <span className="text-muted-foreground text-xs ml-2">
                            · {r.cmt_name || '—'} · lolos QC {Number(actual).toLocaleString('id-ID')} pcs
                            {rejected > 0 && (
                              <span className="text-red-600"> (reject {Number(rejected).toLocaleString('id-ID')})</span>
                            )}
                          </span>
                        </span>
                      </label>
                    );})}
                  </div>
                )}
                {form.source_receipt_ids.length > 0 && (
                  <div className="text-xs text-emerald-800" data-testid="single-po-capacity-summary">
                    Dipilih: <strong>{form.source_receipt_ids.length}</strong> receipt.
                    {capLoading ? ' Menghitung sisa bisa kirim…'
                      : capTotals ? <> Sisa bisa kirim <strong>{Number(capTotals.shippable || 0).toLocaleString('id-ID')} pcs</strong> (lolos QC {Number(capTotals.good_from_cmt || 0).toLocaleString('id-ID')}{capTotals.reworked_ok ? ` + permak ${Number(capTotals.reworked_ok).toLocaleString('id-ID')}` : ''} − sudah dikirim {Number(capTotals.dispatched || 0).toLocaleString('id-ID')}).</>
                      : null}
                  </div>
                )}
              </div>
            )}
            {form.items.length > 0 && (
              <div className="space-y-2">
                {/* FASE E — RUMUS DITULIS DI LAYAR. Dulu hanya ada satu kolom
                    "Maks (dari CMT)" yang isinya salah hitung, jadi pemakai tidak
                    punya cara memeriksa kenapa angkanya begitu. */}
                <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
                  <span className="text-muted-foreground" data-testid="dispatch-capacity-formula">
                    {selectedPO?.business_type === 'internal'
                      ? <>Sisa bisa kirim = <strong>hasil produksi</strong> − <strong>sudah dikirim</strong></>
                      : <>Sisa bisa kirim = <strong>lolos QC</strong> + <strong>hasil permak</strong> − <strong>sudah dikirim</strong></>}
                  </span>
                  {capLoading ? (
                    <span className="text-blue-700 font-medium" data-testid="dispatch-capacity-loading">Menghitung sisa…</span>
                  ) : capTotals && (
                    <span className="text-emerald-800 font-semibold" data-testid="dispatch-capacity-total">
                      Total sisa bisa kirim: {Number(capTotals.shippable || 0).toLocaleString('id-ID')} pcs
                    </span>
                  )}
                </div>
                <div className="overflow-x-auto">
                <table className="w-full text-sm border border-border rounded-xl overflow-hidden" data-testid="dispatch-items-table">
                  <thead className="bg-muted/40">
                    <tr>
                      {consolidate && <th className="text-left px-3 py-2 text-xs text-muted-foreground">PO</th>}
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Serial</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Produk</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Size/Warna</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Qty Order</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground" title={selectedPO?.business_type === 'internal' ? 'Qty hasil produksi job internal' : 'Qty yang LOLOS QC saat barang diterima dari CMT (reject tidak termasuk)'}>{selectedPO?.business_type === 'internal' ? 'Diproduksi' : 'Lolos QC'}</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground" title="Qty reject yang sudah diperbaiki (permak berhasil) sehingga boleh dikirim">Hasil Permak</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground" title="Total yang sudah dikirim ke buyer pada semua surat jalan">Sudah Dikirim</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground" title="Batas maksimal qty kirim untuk item ini">Sisa Bisa Kirim</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Qty Kirim *</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.items.map((item, idx) => {
                      const hasCap = item.shippable != null;
                      const sisa = Number(item.shippable || 0);
                      const notProduced = hasCap && sisa <= 0 && selectedPO?.business_type === 'internal' && Number(item.internal_produced || 0) === 0;
                      const lunas = hasCap && sisa <= 0;
                      const lowStock = hasCap && item.fg_stock != null && Number(item.fg_stock) < sisa;
                      return (
                      <tr key={idx} className={`border-t border-border/60 ${lunas ? 'bg-muted/30' : ''}`}
                        data-testid={`dispatch-item-row-${item.sku || idx}`}>
                        {consolidate && <td className="px-3 py-2"><span className="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-semibold">{item.po_number || '-'}</span></td>}
                        <td className="px-3 py-2 font-mono text-xs text-amber-700">{item.serial_number || '-'}</td>
                        <td className="px-3 py-2 font-mono text-xs text-blue-600">{item.sku || '-'}</td>
                        <td className="px-3 py-2 text-foreground/90">{item.product_name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{item.size || '-'}/{item.color || '-'}</td>
                        <td className="px-3 py-2 text-right text-muted-foreground">{Number(item.ordered_qty || 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right text-foreground/80">{hasCap ? Number((selectedPO?.business_type === 'internal' ? item.internal_produced : item.good_from_cmt) || 0).toLocaleString('id-ID') : '—'}</td>
                        <td className="px-3 py-2 text-right text-foreground/80">
                          {hasCap && Number(item.reworked_ok || 0) > 0
                            ? <span className="text-emerald-700 font-semibold" title="Reject yang sudah diperbaiki dan sekarang boleh dikirim">+{Number(item.reworked_ok).toLocaleString('id-ID')}</span>
                            : (hasCap ? '0' : '—')}
                        </td>
                        <td className="px-3 py-2 text-right text-amber-700">{hasCap ? Number(item.dispatched || 0).toLocaleString('id-ID') : '—'}</td>
                        <td className="px-3 py-2 text-right">
                          {!hasCap ? <span className="text-muted-foreground">—</span> : lunas ? (
                            <span className="inline-block px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-[10px] font-bold" data-testid={`dispatch-item-lunas-${item.sku || idx}`}>{notProduced ? 'BELUM PRODUKSI' : 'LUNAS'}</span>
                          ) : (
                            <span className="font-bold text-emerald-700" data-testid={`dispatch-item-shippable-${item.sku || idx}`}>{sisa.toLocaleString('id-ID')}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <input type="number" min="0" max={hasCap ? sisa : item.ordered_qty}
                            disabled={lunas}
                            data-testid={`dispatch-item-qty-${item.sku || idx}`}
                            className="w-24 border border-border rounded px-2 py-1 text-right text-sm bg-background text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={item.qty_shipped} onChange={e => updateItemQty(idx, e.target.value)} />
                          {lowStock && (
                            <div className="text-[10px] text-amber-700 mt-0.5" title="Stok fisik gudang lebih kecil dari sisa dokumen">
                              stok FG {Number(item.fg_stock).toLocaleString('id-ID')}
                            </div>
                          )}
                        </td>
                      </tr>
                    );})}
                  </tbody>
                </table>
                </div>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan</label>
              <textarea className="w-full border border-border rounded-lg px-3 py-2 text-sm" rows="2"
                value={form.notes} onChange={e => setForm(f => ({...f, notes: e.target.value}))} />
            </div>
            <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
              data-testid="sj-submit-btn">
              {continueShip ? 'Tambah Dispatch' : 'Simpan'}
            </button>
          </form>
        </Modal>
      )}

      {/* Detail Modal with Dispatch History */}
      {showDetail && detailData && (
        <Modal title={`Detail: ${detailData.shipment_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            {/* Summary Card */}
            <div className="bg-gradient-to-r from-blue-50 to-emerald-50 rounded-xl p-4 border border-blue-100">
              <div className="grid grid-cols-4 gap-4 text-center">
                <div>
                  <p className="text-xs text-muted-foreground">Total Order</p>
                  <p className="text-xl font-bold text-foreground">{fmtNum(detailData.total_ordered)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Sudah Kirim</p>
                  <p className="text-xl font-bold text-emerald-700">{fmtNum(detailData.total_shipped)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Sisa</p>
                  <p className="text-xl font-bold text-amber-700">{fmtNum(detailData.remaining)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Progress</p>
                  <p className="text-xl font-bold text-blue-700">{detailData.progress_pct}%</p>
                </div>
              </div>
              <div className="w-full h-3 bg-card/70 rounded-full overflow-hidden mt-3">
                <div className={`h-full rounded-full transition-all ${detailData.progress_pct >= 100 ? 'bg-emerald-500' : 'bg-blue-500'}`}
                  style={{ width: `${Math.min(detailData.progress_pct || 0, 100)}%` }} />
              </div>
            </div>

            {/* Diterima vs Selisih strip */}
            {(() => {
              const items = detailData.items || [];
              const totalShipped = items.reduce((s, i) => s + (i.qty_shipped || 0), 0);
              const totalReceived = items.reduce((s, i) => s + (i.qty_received != null ? i.qty_received : (i.qty_shipped || 0)), 0);
              const totalVar = totalShipped - totalReceived;
              return (
                <div className="grid grid-cols-3 gap-3" data-testid="received-summary-strip">
                  <div className="bg-emerald-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-muted-foreground">Total Dikirim</p>
                    <p className="text-lg font-bold text-emerald-700">{fmtNum(totalShipped)} pcs</p>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-muted-foreground">Total Diterima (aktual)</p>
                    <p className="text-lg font-bold text-blue-700">{fmtNum(totalReceived)} pcs</p>
                  </div>
                  <div className={`rounded-lg p-3 text-center ${totalVar !== 0 ? 'bg-red-50' : 'bg-muted/40'}`}>
                    <p className="text-xs text-muted-foreground">Selisih</p>
                    <p className={`text-lg font-bold ${totalVar > 0 ? 'text-red-600' : totalVar < 0 ? 'text-orange-600' : 'text-muted-foreground'}`}>{fmtNum(totalVar)} pcs</p>
                  </div>
                </div>
              );
            })()}

            {/* Phase D: per-PO breakdown (consolidated surat jalan) */}
            {(() => {
              const items = detailData.items || [];
              const poNumbers = [...new Set(items.map(i => i.po_number).filter(Boolean))];
              if (poNumbers.length <= 1) return null;
              const groups = poNumbers.map(pn => {
                const rows = items.filter(i => i.po_number === pn);
                return {
                  pn,
                  shipped: rows.reduce((s, i) => s + (i.qty_shipped || 0), 0),
                  received: rows.reduce((s, i) => s + (i.qty_received != null ? i.qty_received : (i.qty_shipped || 0)), 0),
                };
              });
              return (
                <div className="rounded-xl border border-violet-200 bg-violet-50/50 p-3" data-testid="detail-per-po">
                  <div className="text-sm font-semibold text-violet-900 mb-2">Rincian per PO (surat jalan konsolidasi — {poNumbers.length} PO)</div>
                  <table className="w-full text-sm">
                    <thead><tr className="text-xs text-muted-foreground">
                      <th className="text-left py-1">No. PO</th>
                      <th className="text-right py-1">Dikirim</th>
                      <th className="text-right py-1">Diterima</th>
                      <th className="text-right py-1">Selisih</th>
                    </tr></thead>
                    <tbody>
                      {groups.map(g => (
                        <tr key={g.pn} className="border-t border-violet-100">
                          <td className="py-1"><span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-semibold">{g.pn}</span></td>
                          <td className="py-1 text-right text-emerald-700">{fmtNum(g.shipped)}</td>
                          <td className="py-1 text-right text-blue-700">{fmtNum(g.received)}</td>
                          <td className={`py-1 text-right ${(g.shipped - g.received) !== 0 ? 'text-red-600' : 'text-muted-foreground'}`}>{fmtNum(g.shipped - g.received)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: 'No. Shipment', v: <span className="font-bold text-blue-700">{detailData.shipment_number}</span> },
                { l: (detailData.po_ids && detailData.po_ids.length > 1) ? 'PO Terkait' : 'No. PO',
                  v: (detailData.po_ids && detailData.po_ids.length > 1)
                    ? <span className="flex flex-wrap gap-1">{[...new Set((detailData.items || []).map(i => i.po_number).filter(Boolean))].map(pn => <span key={pn} className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-semibold">{pn}</span>)}</span>
                    : (detailData.po_number || '-') },
                { l: 'Customer', v: detailData.customer_name || '-' },
                { l: 'Vendor', v: detailData.vendor_name || '-' },
                { l: 'Dibuat', v: fmtDate(detailData.created_at) },
                { l: 'Status', v: <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  (detailData.progress_pct || 0) >= 100 ? 'bg-emerald-100 text-emerald-700' :
                  (detailData.progress_pct || 0) > 0 ? 'bg-amber-100 text-amber-700' : 'bg-muted text-muted-foreground'
                }`}>{(detailData.progress_pct || 0) >= 100 ? 'Fully Shipped' : (detailData.progress_pct || 0) > 0 ? 'Partially Shipped' : 'Pending'}</span> },
              ].map(it => (
                <div key={it.l} className="bg-muted/40 rounded-lg p-3">
                  <p className="text-xs text-muted-foreground">{it.l}</p>
                  <div className="font-medium text-sm mt-0.5">{it.v}</div>
                </div>
              ))}
            </div>

            {/* Dispatch History */}
            {(detailData.dispatches || []).length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-foreground/90 flex items-center gap-2">
                    <History className="w-4 h-4 text-blue-500" />
                    Riwayat Dispatch ({detailData.dispatches.length} round)
                  </h4>
                  {/* Cumulative PDF Export (total, not per dispatch) */}
                  <button onClick={async () => {
                    try {
                      const res = await apiFetch(`/export-pdf?type=buyer-shipment&id=${detailData.id}`);
                      if (!res.ok) throw new Error('Export gagal');
                      const blob = await res.blob();
                      const url = window.URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${detailData.shipment_number || 'Buyer-Shipment'}-Total.pdf`;
                      a.click();
                      window.URL.revokeObjectURL(url);
                    } catch (err) { toast.error('Error: ' + err.message); }
                  }} className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg font-medium hover:bg-blue-700 flex items-center gap-1" data-testid="export-cumulative-pdf">
                    PDF Total Kumulatif
                  </button>
                </div>
                <div className="space-y-2">
                  {(() => {
                    let cumulative = 0;
                    return detailData.dispatches.map((d, i) => {
                      cumulative += d.total_qty;
                      const remaining = Math.max(0, (detailData.total_ordered || 0) - cumulative);
                      return (
                        <div key={d.dispatch_seq} className="border border-border rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-4 py-2.5 bg-muted/40">
                            <div className="flex items-center gap-2">
                              <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                                {d.dispatch_seq}
                              </span>
                              <span className="text-sm font-semibold text-foreground/90">Dispatch #{d.dispatch_seq}</span>
                              <span className="text-xs text-muted-foreground/70">· {fmtDate(d.dispatch_date)}</span>
                            </div>
                            <div className="flex items-center gap-3 text-xs">
                              <span className="text-emerald-700 font-bold">+{fmtNum(d.total_qty)} pcs</span>
                              <span className="text-blue-700">Kumulatif: {fmtNum(cumulative)}</span>
                              <span className="text-muted-foreground">Sisa: {fmtNum(remaining)}</span>
                              {/* Per-dispatch PDF button */}
                              <button onClick={async (e) => {
                                e.stopPropagation();
                                try {
                                  const res = await apiFetch(`/export-pdf?type=buyer-shipment-dispatch&shipment_id=${detailData.id}&dispatch_seq=${d.dispatch_seq}`);
                                  if (!res.ok) throw new Error('Export gagal');
                                  const blob = await res.blob();
                                  const url = window.URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = `${detailData.shipment_number || 'Dispatch'}-D${d.dispatch_seq}.pdf`;
                                  a.click();
                                  window.URL.revokeObjectURL(url);
                                } catch (err) { toast.error('Error: ' + err.message); }
                              }} className="px-2 py-1 bg-card border border-blue-300 text-blue-600 rounded text-[10px] font-medium hover:bg-blue-50 flex items-center gap-1" data-testid={`export-dispatch-${d.dispatch_seq}-pdf`}>
                                PDF D{d.dispatch_seq}
                              </button>
                            </div>
                          </div>
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="bg-muted/40 text-muted-foreground border-b border-border/60">
                                <th className="text-left py-1.5 px-3">Serial</th>
                                <th className="text-left py-1.5 px-3">SKU</th>
                                <th className="text-left py-1.5 px-3">Produk</th>
                                <th className="text-right py-1.5 px-3">Dikirim</th>
                                <th className="text-right py-1.5 px-3">Diterima</th>
                                <th className="text-right py-1.5 px-3">Selisih</th>
                                <th className="text-right py-1.5 px-3">HPP Batch (FIFO)</th>
                                {canForceEdit && <th className="py-1.5 px-2"></th>}
                              </tr>
                            </thead>
                            <tbody>
                              {d.items.map((item, idx) => {
                                const received = item.qty_received != null ? item.qty_received : item.qty_shipped;
                                const variance = (item.qty_shipped || 0) - received;
                                return (
                                <tr key={item.id || idx} className="border-t border-border/60 hover:bg-muted/60">
                                  <td className="py-1.5 px-3 font-mono text-amber-700">{item.serial_number || '—'}</td>
                                  <td className="py-1.5 px-3 font-mono text-blue-700">{item.sku || '-'}</td>
                                  <td className="py-1.5 px-3 text-foreground/90">{item.product_name} <span className="text-muted-foreground/70">{item.size}/{item.color}</span></td>
                                  <td className="py-1.5 px-3 text-right font-bold text-emerald-700">
                                    {fmtNum(item.qty_shipped)}
                                  </td>
                                  <td className="py-1.5 px-3 text-right font-bold text-blue-700">
                                    {fmtNum(received)}
                                    {item.qty_received != null && (
                                      <span title={recvTooltip(item)} data-testid={`received-badge-${item.id}`}
                                        className="ml-1 inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-blue-100 text-blue-700 text-[9px] font-semibold align-middle cursor-help">
                                        <ClipboardCheck className="w-2.5 h-2.5" />
                                      </span>
                                    )}
                                  </td>
                                  <td className={`py-1.5 px-3 text-right font-semibold ${variance > 0 ? 'text-red-600' : variance < 0 ? 'text-orange-600' : 'text-muted-foreground/70'}`}>
                                    {variance > 0 ? fmtNum(variance) : variance < 0 ? `+${fmtNum(-variance)}` : '0'}
                                  </td>
                                  {/* SESI #38 — biaya batch (FIFO) yang dipakai jurnal COGS.
                                      Dialog detail adalah jalan yang lebih sering dipakai staf,
                                      jadi angkanya harus ada di sini juga. */}
                                  <td className="py-1.5 px-3 text-right" data-testid={`detail-item-cogs-${item.id || idx}`}>
                                    {Number(item.fg_cogs || 0) <= 0 ? (
                                      <span className="text-muted-foreground/60"
                                        title={item.fg_cogs == null
                                          ? 'Barang ini keluar sebelum lapisan biaya batch dipasang'
                                          : 'Batch masuknya belum punya biaya (BOM/upah jahit belum lengkap) — bukan Rp 0'}>
                                        {item.fg_cogs == null ? '—' : 'belum berbiaya'}
                                      </span>
                                    ) : (
                                      <span className="font-semibold text-indigo-700">
                                        Rp {Math.round(item.fg_cogs).toLocaleString('id-ID')}
                                      </span>
                                    )}
                                    {Number(item.fg_cogs_uncosted_qty || 0) > 0 && (
                                      <span className="block text-[10px] text-amber-700">
                                        {fmtNum(item.fg_cogs_uncosted_qty)} pcs tanpa lapisan biaya
                                      </span>
                                    )}
                                  </td>
                                  {canForceEdit && (
                                    <td className="py-1.5 px-2 text-right whitespace-nowrap">
                                      <button onClick={(e) => { e.stopPropagation(); openRecv(item, d.dispatch_seq); }}
                                        className="p-1 rounded hover:bg-blue-50 text-blue-600" title="Set qty diterima (aktual)"
                                        data-testid={`set-received-item-${item.id}`}>
                                        <ClipboardCheck className="w-3.5 h-3.5" />
                                      </button>
                                    </td>
                                  )}
                                </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    });
                  })()}
                </div>
              </div>
            )}

            {/* Summary Items (per SKU cumulative) */}
            {(detailData.summary_items || []).length > 0 && (
              <div>
                <h4 className="font-semibold text-foreground/90 mb-2">Ringkasan per Item</h4>
                <table className="w-full text-sm border border-border rounded-xl overflow-hidden">
                  <thead className="bg-muted/40">
                    <tr>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Serial</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Produk</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Qty Order</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Total Kirim</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Sisa</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {detailData.summary_items.map((item, idx) => (
                      <tr key={idx}>
                        <td className="px-3 py-2 font-mono text-xs text-amber-700">{item.serial_number || '—'}</td>
                        <td className="px-3 py-2 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                        <td className="px-3 py-2">{item.product_name} <span className="text-xs text-muted-foreground/70">{item.size}/{item.color}</span></td>
                        <td className="px-3 py-2 text-right">{fmtNum(item.ordered_qty)}</td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700">{fmtNum(item.cumulative_shipped)}</td>
                        <td className="px-3 py-2 text-right font-bold text-amber-700">{fmtNum(Math.max(0, (item.ordered_qty || 0) - (item.cumulative_shipped || 0)))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <FileAttachmentPanel entityType="buyer_shipment" entityId={detailData.id} />
          </div>
        </Modal>
      )}

      {/* Set Qty Diterima (Actual Received) Modal */}
      {recvItem && (
        <Modal title="Set Qty Diterima (Aktual)" onClose={() => setRecvItem(null)} size="md">
          <form onSubmit={handleSaveRecv} className="space-y-4" data-testid="set-received-form">
            <div className="bg-muted/40 rounded-lg p-3 text-sm space-y-1">
              <div className="flex justify-between"><span className="text-muted-foreground">Produk</span><span className="font-medium text-foreground">{recvItem.product_name || '-'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">SKU</span><span className="font-mono text-blue-700">{recvItem.sku || '-'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Serial</span><span className="font-mono text-amber-700">{recvItem.serial_number || '—'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Dispatch</span><span className="font-medium">#{recvItem.dispatch_seq || 1}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Qty Dikirim</span><span className="font-bold text-emerald-700">{fmtNum(recvItem.qty_shipped)} pcs</span></div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Qty Diterima aktual (pcs) *</label>
              <input type="number" min="0" autoFocus data-testid="set-received-qty-input"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={recvForm.qty_received}
                onChange={e => setRecvForm(f => ({ ...f, qty_received: e.target.value }))} />
              {recvForm.qty_received !== '' && (
                <p className="text-xs mt-1 text-muted-foreground">
                  Selisih: <span className={`font-semibold ${(recvItem.qty_shipped - Number(recvForm.qty_received)) !== 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                    {fmtNum(recvItem.qty_shipped - Number(recvForm.qty_received))} pcs
                  </span>
                </p>
              )}
              {recvForm.qty_received !== '' && (recvItem.qty_shipped - Number(recvForm.qty_received)) > 0 && (
                <div className="mt-2 rounded-lg bg-rose-50 border border-rose-200 p-2.5 text-[11px] text-rose-900"
                  data-testid="recv-short-notice">
                  <strong>{fmtNum(recvItem.qty_shipped - Number(recvForm.qty_received))} pcs dianggap BELUM SAMPAI.</strong>{' '}
                  Sistem akan: (1) mengoreksi qty pada surat jalan menjadi {fmtNum(Number(recvForm.qty_received))} pcs
                  (klaim awal tetap tersimpan di jejak audit), (2) membuka catatan selisih
                  <em> SEL-BYR-…</em>, (3) mengembalikan barangnya ke stok FG supaya bisa
                  <strong> dikirim ulang</strong>, dan (4) memberi tahu Admin &amp; Finance.
                  Keputusan tanggungan (CMT / DA) diambil saat PO ditutup.
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan (opsional)</label>
              <textarea rows="2" data-testid="set-received-reason-input"
                placeholder="Contoh: 3 pcs cacat saat diterima buyer"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={recvForm.reason}
                onChange={e => setRecvForm(f => ({ ...f, reason: e.target.value }))} />
            </div>

            {recvItem.received_history?.length > 0 && (
              <div className="border border-border rounded-lg p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-1.5 flex items-center gap-1"><History className="w-3.5 h-3.5" /> Riwayat qty diterima</p>
                <div className="space-y-1 max-h-28 overflow-y-auto">
                  {recvItem.received_history.map((h, i) => (
                    <div key={i} className="text-[11px] text-muted-foreground">
                      <span className="font-mono text-foreground/90">{h.old_qty}→{h.new_qty}</span> • {fmtDate(h.edited_at)} • {h.edited_by}{h.reason ? <span className="italic">: {h.reason}</span> : ''}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button type="submit" disabled={recvLoading} data-testid="set-received-save-btn"
                className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                {recvLoading ? 'Menyimpan...' : 'Simpan Qty Diterima'}
              </button>
              <button type="button" onClick={() => setRecvItem(null)}
                className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Buyer Shipment"
          message={`Yakin ingin menghapus shipment ${confirmDelete.shipment_number}?`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {/* ── Keputusan atas selisih terima buyer ─────────────────────────── */}
      {resolveBShort && (
        <Modal title={`Putuskan Selisih ${resolveBShort.short_number}`}
          onClose={() => setResolveBShort(null)} size="md">
          <div className="space-y-4" data-testid="buyer-short-dialog">
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm space-y-1 text-rose-900">
              <div className="flex justify-between"><span className="opacity-70">Surat Jalan</span><span className="font-medium">{resolveBShort.shipment_number || '—'}</span></div>
              <div className="flex justify-between"><span className="opacity-70">PO / Buyer</span><span className="font-medium">{resolveBShort.po_number || '—'} · {resolveBShort.customer_name || '—'}</span></div>
              <div className="flex justify-between"><span className="opacity-70">SKU</span><span className="font-mono">{resolveBShort.sku || '—'}</span></div>
              <div className="flex justify-between"><span className="opacity-70">Dikirim → Diterima</span><span className="font-medium">{fmtNum(resolveBShort.qty_shipped_claimed)} → {fmtNum(resolveBShort.qty_received)} pcs</span></div>
              <div className="flex justify-between"><span className="opacity-70">Belum sampai</span><span className="font-bold">{fmtNum(resolveBShort.qty_open ?? resolveBShort.qty_short)} pcs</span></div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Keputusan *</label>
              <SmartNativeSelect value={bResType} onChange={e => setBResType(e.target.value)}
                data-testid="buyer-short-resolution"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm">
                <option value="dikirim_ulang">Akan dikirim ulang (barang ketinggalan / salah hitung)</option>
                <option value="tanggungan_cmt">Hilang — ditanggung vendor CMT (keputusan finance)</option>
                <option value="tanggungan_da">Hilang — ditanggung DA (keputusan finance)</option>
                <option value="dibatalkan">Batalkan (qty diterima salah dicatat)</option>
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan</label>
              <textarea rows="2" value={bResNotes} onChange={e => setBResNotes(e.target.value)}
                data-testid="buyer-short-notes"
                placeholder="mis. hasil investigasi ekspedisi: barang hilang di jalan"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm" />
            </div>
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-[11px] text-blue-900">
              Pilihan <strong>hilang</strong> akan MENGHAPUSBUKUKAN stok FG {fmtNum(resolveBShort.qty_open ?? resolveBShort.qty_short)} pcs
              yang tadi dikembalikan (karena barangnya memang tidak ada), lalu mencatat pihak yang
              menanggung untuk diproses Finance. Pilihan <strong>dikirim ulang</strong> membiarkan
              barang tetap di stok FG — catatan selisih tertutup otomatis saat pengiriman ulang dibuat.
            </div>
            <div className="flex gap-3">
              <button type="button" onClick={submitResolveBuyerShort} disabled={bResSaving}
                data-testid="buyer-short-save"
                className="flex-1 bg-rose-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-rose-700 disabled:opacity-50">
                {bResSaving ? 'Menyimpan...' : 'Simpan Keputusan'}
              </button>
              <button type="button" onClick={() => setResolveBShort(null)}
                className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
