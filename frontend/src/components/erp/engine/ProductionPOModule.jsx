
import { useState, useEffect, useRef } from 'react';
import { Plus, Eye, Pencil, Trash2, X, XCircle, Zap, AlertTriangle, Loader2, Layers } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import POWorkflowIndicator from './POWorkflowIndicator';
import FileAttachmentPanel from './FileAttachmentPanel';
import { PdfColumnPicker } from '../pdf/PdfColumnPicker';
import SearchableSelect from './SearchableSelect';
import ImportExportPanel from './ImportExportPanel';
import QuickCompleteModal from './QuickCompleteModal';
import { BizBadge } from './BusinessTypeBadge';
import { apiGet, apiPost, apiPut, apiDelete, apiFetch } from '../../../lib/api';
import { formatRupiah } from '@/lib/format';

const STATUS_OPTIONS = ['Draft', 'Confirmed', 'Distributed', 'In Production', 'Completed', 'Closed'];
const CLOSE_REASONS = ['Under Production', 'Over Production', 'Price Adjustment', 'Customer Agreement', 'Other'];

export default function ProductionPOModule({ userRole, hasPerm = () => false, businessType, onNavigate }) {
  // FASE 5 DA: businessType 'internal' | 'maklon' | undefined (semua)
  const isInternal = businessType === 'internal';
  const [pos, setPOs] = useState([]);
  // [FASE 4 CLEANUP] Legacy `products`/`product_variants` state removed — dead code.
  // Maklon now uses buyer-catalog (`catalog_item_id`); Internal uses `rahaza_models` + `rahaza_variant_id`.
  const [catalogItems, setCatalogItems] = useState([]);  // maklon: dewi_maklon_buyer_catalog (master produk maklon, per buyer)
  const [models, setModels] = useState([]);   // internal: rahaza_models (D3 FK)
  const [sizes, setSizes] = useState([]);     // internal: rahaza_sizes
  const [vendors, setVendors] = useState([]);
  const [buyers, setBuyers] = useState([]);
  const [accessories, setAccessories] = useState([]);
  // ── AKSESORIS BOM MUAT OTOMATIS DI FORM (keluhan pemilik 2026-06) ─────────
  // Katalog maklon sudah punya BOM aksesoris dan angkanya sudah benar di Surat
  // Jalan/SPP, TAPI form buat PO tidak menampilkannya sama sekali — pemakai
  // menyangka BOM belum kena lalu mengetik ulang barisnya (kerja dobel & baris
  // kembar). Panel di bawah membaca `POST /api/dewi/maklon/bom-templates/
  // preview-accessories`, yaitu MESIN YANG SAMA dengan yang menulis
  // `po_accessories` saat PO disimpan — jadi angka di layar tidak mungkin
  // berbeda dari yang tersimpan. Baris ini TIDAK dikirim di payload (backend
  // yang menuliskannya) supaya tidak ada baris kembar.
  const [bomAcc, setBomAcc] = useState({ rows: [], warnings: [], total_pcs: 0, loading: false });
  const [rahazaVariants, setRahazaVariants] = useState({}); // Fase 2: cache varian internal per model_id
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  // W2 (sesi #29) — dialog pemilih kolom untuk cetak SPP (termasuk Serial No).
  const [sppPickerOpen, setSppPickerOpen] = useState(false);
  const [showCloseModal, setShowCloseModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [detailData, setDetailData] = useState(null);
  // ACC-1 — kebutuhan aksesoris PO (dari BOM) + posisi stok
  const [accReq, setAccReq] = useState(null);
  const [accReqLoading, setAccReqLoading] = useState(false);
  const [accReqCreating, setAccReqCreating] = useState(false);
  // ACC-1 — hasil aksi "Buat Permintaan" ditampilkan INLINE (bukan `alert()` native)
  // supaya pesan anti-dobel tetap terbaca di konteks tabelnya & tidak memblokir UI.
  const [accReqMsg, setAccReqMsg] = useState(null); // { type:'success'|'error', text }
  const [closeTargetPO, setCloseTargetPO] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [closeForm, setCloseForm] = useState({ close_reason: CLOSE_REASONS[0], close_notes: '' });
  const [refetchKey, setRefetchKey] = useState(0);
  const [form, setForm] = useState({ po_number: '', customer_name: '', buyer_id: '', vendor_id: '', po_date: '', deadline: '', delivery_deadline: '', notes: '', items: [], po_accessories: [] });
  // KELUHAN #1 (2026-07-31) — validasi form TIDAK boleh pakai `alert()` native:
  // pesannya hilang begitu diklik, tidak bisa dibaca ulang, dan menutupi konteks
  // baris item yang salah. Sekarang: banner inline di dalam modal (data-testid
  // `po-form-error`) + fokus otomatis ke baris item bermasalah.
  const [formError, setFormError] = useState(null);   // { text, itemIdx }
  // FASE G (2026-08-16) — kebijakan nomor dokumen (otomatis/manual) dibaca dari
  // SSOT penomoran. Tanpa ini layar tetap menyuruh mengetik nomor walau owner
  // sudah menyetelnya OTOMATIS, dan pemakai menanggung penolakan backend atas
  // setelan yang tidak pernah ia lihat.
  const [numPolicy, setNumPolicy] = useState(null);

  useEffect(() => {
    const key = businessType === 'maklon'
      ? 'production_pos.po_number_maklon' : 'production_pos.po_number';
    apiGet(`/doc-number-policy?key=${key}`)
      .then(setNumPolicy)
      .catch(() => setNumPolicy(null));   // gagal baca kebijakan ⇒ perlakukan manual
  }, [businessType]);
  // Fase 3 — Cek seri dobel (live, non-blocking) saat BUAT ORDER. { [idx]: {loading, usages} }
  const [serialChecks, setSerialChecks] = useState({});
  const serialDebounce = useRef({});

  // Cek 1 seri ke SSOT (po_items.serial_number) untuk peringatan (tidak block simpan).
  const handleSerialChange = (idx, value) => {
    updateItem(idx, 'serial_number', value);
    if (serialDebounce.current[idx]) clearTimeout(serialDebounce.current[idx]);
    const v = (value || '').trim();
    if (!v) { setSerialChecks(s => ({ ...s, [idx]: null })); return; }
    serialDebounce.current[idx] = setTimeout(async () => {
      setSerialChecks(s => ({ ...s, [idx]: { loading: true, usages: [] } }));
      try {
        const params = new URLSearchParams({ serial: v, scope: 'all' });
        if (editData?.id) params.set('exclude_po_id', editData.id);
        const res = await apiGet(`/dewi/cmt-intake/serial-lookup?${params.toString()}`);
        setSerialChecks(s => ({ ...s, [idx]: { loading: false, usages: res.usages || [] } }));
      } catch { setSerialChecks(s => ({ ...s, [idx]: null })); }
    }, 450);
  };

  const isSuperAdmin = userRole === 'superadmin';
  const canEdit = ['superadmin', 'admin'].includes(userRole) || hasPerm('po.edit');
  const canCreate = userRole === 'superadmin' || hasPerm('production_po.create') || hasPerm('po.create');
  const canDelete = ['superadmin', 'admin'].includes(userRole) || hasPerm('po.delete');

  useEffect(() => {
    fetchAccessories();
    fetchVendors();  // vendor/CMT dibutuhkan di Internal & Maklon (kirim material ke vendor)
    if (isInternal) { fetchModels(); fetchSizes(); }
    else { fetchBuyers(); }
  }, [isInternal]);

  // Pratinjau aksesoris BOM ikut berubah setiap artikel/qty item berubah.
  // Kuncinya diringkas jadi string supaya efek tidak jalan saat field lain
  // (mis. nomor seri) disunting; debounce 400ms supaya ketikan qty tidak
  // memanggil server per angka.
  const bomAccKey = isInternal ? '' : (form.items || [])
    .map(it => `${it.catalog_item_id || ''}:${Number(it.qty) || 0}`).join('|');
  useEffect(() => {
    if (isInternal || !showModal) {
      setBomAcc({ rows: [], warnings: [], total_pcs: 0, loading: false });
      return;
    }
    const payloadItems = (form.items || [])
      .filter(it => it.catalog_item_id && Number(it.qty) > 0)
      .map(it => ({ catalog_item_id: it.catalog_item_id, qty: Number(it.qty),
        label: it.product_name || it.sku || '' }));
    if (payloadItems.length === 0) {
      setBomAcc({ rows: [], warnings: [], total_pcs: 0, loading: false });
      return;
    }
    setBomAcc(s => ({ ...s, loading: true }));
    const t = setTimeout(async () => {
      try {
        const res = await apiPost('/dewi/maklon/bom-templates/preview-accessories',
          { items: payloadItems });
        setBomAcc({ rows: res?.accessories || [], warnings: res?.warnings || [],
          total_pcs: res?.total_pcs || 0, loading: false });
      } catch (e) {
        setBomAcc({ rows: [], total_pcs: 0, loading: false,
          warnings: [`Gagal memuat aksesoris BOM: ${e.message || 'kesalahan jaringan'}`] });
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bomAccKey, isInternal, showModal]);

  const refetchPOs = () => setRefetchKey((k) => k + 1);

  // Server-paginated fetcher (Phase 10C)
  const posFetcher = async ({ page, per_page, sort_by, sort_dir, search }) => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(per_page));
    if (sort_by) params.set('sort_by', sort_by);
    if (sort_dir) params.set('sort_dir', sort_dir);
    if (search) params.set('search', search);
    if (filterStatus) params.set('status', filterStatus);
    if (businessType) params.set('business_type', businessType);
    const env = await apiGet(`/production-pos?${params.toString()}`);
    // Keep `pos` array around so `expandedRowRender` can show item details
    const items = Array.isArray(env?.items) ? env.items : (Array.isArray(env) ? env : []);
    setPOs(items);
    return env;
  };

  const fetchBuyers = async () => {
    try {
      // DA: klien maklon = dewi_maklon_clients
      const data = await apiGet('/dewi/maklon/clients');
      const rows = Array.isArray(data) ? data : (data?.items || []);
      setBuyers(rows.filter(b => b.active !== false).map(b => ({
        ...b, buyer_name: b.buyer_name || b.name || '', buyer_code: b.buyer_code || b.code || '',
      })));
    } catch (e) { console.error(e); }
  };

  const fetchAccessories = async () => {
    try {
      // SSOT aksesoris = rahaza_materials (type=accessory) via /acc/items.
      // Endpoint lama /accessories sudah DEPRECATED & mengembalikan kosong.
      const data = await apiGet('/acc/items?type=accessory');
      const rows = Array.isArray(data) ? data : (data?.items || []);
      setAccessories(rows.filter(a => a.active !== false && a.status !== 'inactive'));
    } catch (e) { setAccessories([]); }
  };

  const fetchVendors = async () => {
    try {
      // SSOT vendor/CMT = vendor_partners. Diekspos via /garments (require_auth saja,
      // BUKAN admin-only) supaya staff Produksi yang membuat PO tetap bisa memuat daftar.
      const data = await apiGet('/garments');
      const rows = Array.isArray(data) ? data : (data?.items || []);
      setVendors(rows
        .filter(v => v.status !== 'inactive' && v.active !== false && v.is_active !== false)
        .map(v => ({
          ...v, garment_name: v.garment_name || v.name || '', garment_code: v.garment_code || v.code || '',
        })));
    } catch (e) { setVendors([]); }
  };

  const fetchModels = async () => {
    try {
      const data = await apiGet('/rahaza/models?active=true&limit=500');
      const rows = Array.isArray(data) ? data : (data?.items || []);
      setModels(rows);
    } catch (e) { setModels([]); }
  };

  const fetchSizes = async () => {
    try {
      const data = await apiGet('/rahaza/sizes?active=true&limit=100');
      const rows = Array.isArray(data) ? data : (data?.items || []);
      setSizes(rows);
    } catch (e) { setSizes([]); }
  };

  // Fase 2: ambil daftar varian ber-SKU untuk sebuah model (di-cache per model_id)
  const fetchRahazaVariants = async (modelId) => {
    if (!modelId) return [];
    try {
      const data = await apiGet(`/rahaza/models/${modelId}/variants`);
      const list = (data && data.variants) ? data.variants : [];
      setRahazaVariants(prev => ({ ...prev, [modelId]: list }));
      return list;
    } catch (e) {
      setRahazaVariants(prev => ({ ...prev, [modelId]: [] }));
      return [];
    }
  };

  // [FASE 4 CLEANUP] Removed dead helpers `fetchProducts()` and `fetchVariantsForProduct()`.
  // They read the legacy `products`/`product_variants` collections which are no longer
  // rendered by any picker (Maklon → buyer-catalog, Internal → rahaza_models/variants).

  // MAKLON: master produk = Buyer Catalog (dewi_maklon_buyer_catalog), di-scope per buyer/klien.
  const fetchCatalog = async (clientId) => {
    if (!clientId) { setCatalogItems([]); return; }
    try {
      const data = await apiGet(`/dewi/maklon/buyer-catalog?client_id=${clientId}&status=active`);
      setCatalogItems(Array.isArray(data) ? data : (data?.items || []));
    } catch (e) { setCatalogItems([]); }
  };

  const openCreate = () => {
    setEditData(null);
    setFormError(null);
    setForm({ po_number: '', customer_name: isInternal ? 'Gudang FG Sendiri' : '', buyer_id: '', vendor_id: '', po_date: new Date().toISOString().split('T')[0], deadline: '', delivery_deadline: '', notes: '', items: [], po_accessories: [] });
    setShowModal(true);
  };

  const addItem = () => {
    setFormError(null);
    setForm(f => ({ ...f, items: [...f.items, isInternal
      ? { model_id: '', rahaza_variant_id: '', size_id: '', product_name: '', size: '', color: '', sku: '', qty: '', serial_number: '' }
      : { catalog_item_id: '', product_id: '', product_name: '', variant_id: '', size: '', color: '', sku: '', qty: '', serial_number: '', selling_price_snapshot: '', cmt_price_snapshot: '' }] }));
  };

  const addAccessoryItem = () => {
    setForm(f => ({ ...f, po_accessories: [...(f.po_accessories || []), { accessory_id: '', accessory_name: '', accessory_code: '', qty_needed: '', unit: 'pcs', notes: '' }] }));
  };

  const removeAccessoryItem = (idx) => {
    setForm(f => ({ ...f, po_accessories: (f.po_accessories || []).filter((_, i) => i !== idx) }));
  };

  const updateAccessoryItem = (idx, field, value) => {
    const items = [...(form.po_accessories || [])];
    items[idx] = { ...items[idx], [field]: value };
    if (field === 'accessory_id') {
      const acc = accessories.find(a => a.id === value);
      if (acc) {
        // Support both canonical (accessory_name/accessory_code) and legacy (name/code) shapes.
        items[idx].accessory_name = acc.accessory_name || acc.name || '';
        items[idx].accessory_code = acc.accessory_code || acc.code || '';
        items[idx].unit = acc.unit || 'pcs';
      }
    }
    setForm(f => ({ ...f, po_accessories: items }));
  };

  const removeItem = (idx) => {
    setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  };

  const updateItem = async (idx, field, value) => {
    // pesan error validasi dibersihkan begitu baris yang ditandai disentuh lagi
    setFormError(prev => (prev && (prev.itemIdx === idx || prev.itemIdx === null) ? null : prev));
    const newItems = [...form.items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'model_id') {
      const model = models.find(m => m.id === value);
      newItems[idx].product_name = model?.name || '';
      // Fase 2: model berubah → reset varian & derived fields; muat daftar varian
      newItems[idx].rahaza_variant_id = '';
      newItems[idx].size_id = '';
      newItems[idx].size = '';
      newItems[idx].color = '';
      newItems[idx].sku = '';
      if (value) fetchRahazaVariants(value);
    }
    if (field === 'rahaza_variant_id') {
      const list = rahazaVariants[newItems[idx].model_id] || [];
      const v = list.find(x => x.id === value);
      if (v) {
        newItems[idx].size_id = v.size_id || '';
        newItems[idx].size = v.size_code || '';
        newItems[idx].color = v.color_name || '';
        newItems[idx].sku = v.sku || '';
      } else {
        newItems[idx].size_id = ''; newItems[idx].size = ''; newItems[idx].color = ''; newItems[idx].sku = '';
      }
    }
    if (field === 'size_id') {
      const sz = sizes.find(s => s.id === value);
      newItems[idx].size = sz?.code || sz?.name || '';
      const model = models.find(m => m.id === newItems[idx].model_id);
      if (model?.code) newItems[idx].sku = `${model.code}-${newItems[idx].size}`;
    }
    if (field === 'catalog_item_id') {
      const cat = catalogItems.find(c => c.id === value);
      newItems[idx].product_name = cat?.product_name || '';
      newItems[idx].cmt_price_snapshot = cat?.default_cmt_price ?? '';
      newItems[idx].selling_price_snapshot = cat?.default_selling_price ?? '';
      newItems[idx].buyer_ref_code = cat?.buyer_ref_code || '';
      // reset variant-derived fields
      newItems[idx].maklon_variant_id = '';
      newItems[idx].color = ''; newItems[idx].color_code = ''; newItems[idx].size = '';
      const vars = (cat?.variants || []).filter(v => v.active !== false);
      // Bila artikel punya varian master data → SKU HARUS dipilih dari varian (kosongkan dulu).
      // Bila tidak ada varian → fallback custom, sku default = artikel_code.
      newItems[idx].sku = vars.length > 0 ? '' : (cat?.artikel_code || '');
    }
    if (field === 'maklon_variant_sku') {
      const cat = catalogItems.find(c => c.id === newItems[idx].catalog_item_id);
      const v = (cat?.variants || []).find(x => x.sku === value);
      if (v) {
        newItems[idx].maklon_variant_id = v.id || v.sku;
        newItems[idx].sku = v.sku || '';
        newItems[idx].color = v.color || '';
        newItems[idx].color_code = v.color_code || '';
        newItems[idx].size = v.size || '';
        if (v.buyer_ref_code) newItems[idx].buyer_ref_code = v.buyer_ref_code;
      } else {
        newItems[idx].maklon_variant_id = '';
        newItems[idx].sku = ''; newItems[idx].color = ''; newItems[idx].color_code = ''; newItems[idx].size = '';
      }
    }
    // [FASE 4 CLEANUP] Removed dead `product_id`/`variant_id` handlers (legacy products/
    // product_variants). No picker renders them; Maklon uses `catalog_item_id`.
    setForm(f => ({ ...f, items: newItems }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const fail = (text, itemIdx = null) => { setFormError({ text, itemIdx }); return false; };
    setFormError(null);
    if (form.items.length === 0) { fail('Tambahkan minimal 1 item produk.'); return; }
    // Validasi Maklon: artikel yg punya varian master data WAJIB pilih varian (SKU), bukan custom.
    if (!isInternal) {
      for (let i = 0; i < form.items.length; i++) {
        const it = form.items[i];
        if (!it.catalog_item_id) { fail(`Item #${i + 1}: pilih Produk (Katalog Buyer) terlebih dahulu.`, i); return; }
        const cat = catalogItems.find(c => c.id === it.catalog_item_id);
        const vars = (cat?.variants || []).filter(v => v.active !== false);
        if (vars.length > 0 && !vars.some(v => v.sku === it.sku)) {
          fail(`Item #${i + 1}: pilih Varian (Warna · Size · SKU) dari master data terlebih dahulu.`, i);
          return;
        }
        if (!it.qty || Number(it.qty) <= 0) { fail(`Item #${i + 1}: qty harus lebih dari 0.`, i); return; }
      }
    }
    // Validasi Internal (SSOT): tiap item WAJIB pilih Model + Varian (Warna · Size). Varian
    // membawa rahaza_variant_id → rantai FG per-warna (Produksi→Gudang→Toko) aktif & stok terlacak.
    if (isInternal) {
      for (let i = 0; i < form.items.length; i++) {
        const it = form.items[i];
        if (!it.model_id) { fail(`Item #${i + 1}: pilih Model produk.`, i); return; }
        if (!it.rahaza_variant_id) {
          fail(`Item #${i + 1}: pilih Varian (Warna · Size · SKU) dari master data terlebih dahulu. Warna wajib agar stok Finished Goods terlacak per varian.`, i);
          return;
        }
        if (!it.qty || Number(it.qty) <= 0) { fail(`Item #${i + 1}: qty harus lebih dari 0.`, i); return; }
      }
    }
    // Phase 8.6 — Send items + po_accessories together in the body (PUT supports delta update)
    const itemsPayload = form.items.map(it => (isInternal
      ? { ...it, qty: Number(it.qty) }
      : {
          ...it,
          qty: Number(it.qty),
          selling_price_snapshot: Number(it.selling_price_snapshot) || 0,
          cmt_price_snapshot: Number(it.cmt_price_snapshot) || 0,
        }));
    const accPayload = (form.po_accessories || [])
      .filter(a => a.accessory_name || a.accessory_id)
      .map(a => ({ ...a, qty_needed: Number(a.qty_needed) || 0 }));
    const payload = { ...form, items: itemsPayload, po_accessories: accPayload };
    if (businessType) payload.business_type = businessType;
    // FASE G (2026-08-16) — mode OTOMATIS: nomor JANGAN dikirim. Backend menolak
    // nomor ketikan saat mode otomatis (dan menyebut nomor yang akan dipakai),
    // supaya tidak ada nomor yang "lolos" tanpa mengikuti pola.
    if (!editData && numPolicy?.mode === 'auto') delete payload.po_number;
    try {
      const data = editData
        ? await apiPut(`/production-pos/${editData.id}`, payload)
        : await apiPost('/production-pos', payload);
      // For create path, backend doesn't accept po_accessories in POST; keep legacy secondary call
      if (!editData && accPayload.length > 0) {
        try {
          await apiPost('/po-accessories', { po_id: data.id, items: accPayload });
        } catch (e) { /* non-critical */ }
      }
      setShowModal(false);
      refetchPOs();
    } catch (err) { setFormError({ text: err.message || 'Gagal menyimpan PO', itemIdx: null }); }
  };

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/production-pos/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
      loadAccReq(row.id);
    } catch (e) { alert(e.message || 'Gagal memuat detail'); }
  };

  // ── ACC-1 — kebutuhan aksesoris PO (BOM explode + posisi stok + kekurangan) ──
  const loadAccReq = async (poId, { keepMessage = false } = {}) => {
    setAccReqLoading(true);
    setAccReq(null);
    // Pesan hasil aksi TIDAK dihapus saat refresh yang dipicu oleh aksi itu
    // sendiri — kalau tidak, notifikasi sukses langsung hilang sebelum terbaca.
    if (!keepMessage) setAccReqMsg(null);
    try {
      const d = await apiGet(`/production-pos/${poId}/accessory-requirements`);
      setAccReq(d);
    } catch (e) {
      setAccReq({ error: e.message || 'Gagal memuat kebutuhan aksesoris' });
    } finally { setAccReqLoading(false); }
  };

  const createAccRequest = async (poId, onlyShortage = true) => {
    setAccReqCreating(true);
    setAccReqMsg(null);
    try {
      const res = await apiFetch(`/production-pos/${poId}/accessory-requirements/create-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ only_shortage: onlyShortage }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || 'Gagal membuat permintaan aksesoris');
      setAccReqMsg({ type: 'success', text: d.message || 'Permintaan aksesoris dibuat & dikirim ke Inbox Approval Aksesoris.' });
      loadAccReq(poId, { keepMessage: true });
    } catch (e) {
      setAccReqMsg({ type: 'error', text: e.message || 'Gagal membuat permintaan aksesoris' });
    } finally { setAccReqCreating(false); }
  };

  const openEdit = async (row) => {
    // Phase 8.6 — Load full PO detail (items + po_accessories) so user can edit everything.
    try {
      const [poData, statsData] = await Promise.all([
        apiGet(`/production-pos/${row.id}`),
        apiGet(`/po-items-produced?po_id=${row.id}`),
      ]);
      const statsById = {};
      (Array.isArray(statsData) ? statsData : []).forEach(s => { statsById[s.id] = s; });
      // [FASE 4 CLEANUP] Removed dead per-item `/product-variants` fetch loop (legacy).
      // Historical PO items keep their stored size/color/sku fields; no variant dropdown
      // is rendered anymore (Internal uses rahaza variants, Maklon uses buyer-catalog).

      const mappedItems = (poData.items || []).map(it => {
        const st = statsById[it.id] || {};
        const sent_to_vendor = st.total_shipped || 0; // actually this is buyer; we also need vendor sent
        return {
          id: it.id,
          catalog_item_id: it.catalog_item_id || '',
          product_id: it.product_id || '',
          product_name: it.product_name || '',
          variant_id: it.variant_id || '',
          model_id: it.model_id || '',
          rahaza_variant_id: it.rahaza_variant_id || '',
          maklon_variant_id: it.maklon_variant_id || '',
          buyer_ref_code: it.buyer_ref_code || '',
          color_code: it.color_code || '',
          size_id: it.size_id || '',
          size: it.size || '',
          color: it.color || '',
          sku: it.sku || '',
          qty: it.qty || '',
          serial_number: it.serial_number || '',
          selling_price_snapshot: it.selling_price_snapshot || '',
          cmt_price_snapshot: it.cmt_price_snapshot || '',
          // guardrail hints
          __has_shipments: (st.total_shipped || 0) > 0 || (st.total_produced || 0) > 0,
          __min_qty: Math.max(st.total_shipped || 0, st.total_produced || 0),
        };
      });
      // Additionally fetch po-items to discover vendor-ship amount per item
      const piData = await apiGet(`/po-items?po_id=${row.id}`);
      const vendorSentById = {};
      (Array.isArray(piData) ? piData : []).forEach(pi => { vendorSentById[pi.id] = pi.total_sent_to_vendor || 0; });
      mappedItems.forEach(m => {
        const vendorSent = vendorSentById[m.id] || 0;
        if (vendorSent > 0) m.__has_shipments = true;
        m.__min_qty = Math.max(m.__min_qty || 0, vendorSent);
      });

      setEditData(poData);
      if (!isInternal) fetchCatalog(poData.buyer_id);
      else {
        // Fase 2: prefetch daftar varian untuk tiap model item internal (agar dropdown terisi)
        const modelIds = [...new Set(mappedItems.map(m => m.model_id).filter(Boolean))];
        modelIds.forEach(mid => fetchRahazaVariants(mid));
      }
      setForm({
        po_number: poData.po_number || '',
        customer_name: poData.customer_name || '',
        buyer_id: poData.buyer_id || '',
        vendor_id: poData.vendor_id || '',
        po_date: poData.po_date ? new Date(poData.po_date).toISOString().split('T')[0] : '',
        deadline: poData.deadline ? new Date(poData.deadline).toISOString().split('T')[0] : '',
        delivery_deadline: poData.delivery_deadline ? new Date(poData.delivery_deadline).toISOString().split('T')[0] : '',
        status: poData.status || 'Draft',
        notes: poData.notes || '',
        items: mappedItems,
        po_accessories: (poData.po_accessories || []).map(a => ({
          id: a.id,
          accessory_id: a.accessory_id || '',
          accessory_name: a.accessory_name || '',
          accessory_code: a.accessory_code || '',
          qty_needed: a.qty_needed || '',
          unit: a.unit || 'pcs',
          notes: a.notes || '',
        })),
      });
      setShowModal(true);
    } catch (err) {
      alert('Gagal memuat detail PO: ' + (err.message || err));
    }
  };

  const transitionStatus = async (poId, nextStatus) => {
    // FASE 5 DA: transisi status HANYA dari allowed_next backend (state machine)
    try {
      await apiPost(`/production-pos/${poId}/status`, { status: nextStatus });
      const data = await apiGet(`/production-pos/${poId}`);
      setDetailData(data);
      refetchPOs();
    } catch (err) { alert(err.message || 'Transisi status ditolak backend'); }
  };

  const handleClosePO = async (e) => {
    e.preventDefault();
    try {
      await apiPost(`/production-pos/${closeTargetPO.id}/close`, closeForm);
      setShowCloseModal(false);
      refetchPOs();
    } catch (e) { alert(e.message || 'Gagal menutup PO'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/production-pos/${confirmDelete.id}`);
      setConfirmDelete(null);
      refetchPOs();
    } catch (e) { alert(e.message || 'Gagal menghapus PO'); }
  };

  const [expandedPOs, setExpandedPOs] = useState({});
  const [quickCompletePO, setQuickCompletePO] = useState(null);
  const togglePO = (id) => setExpandedPOs(prev => ({ ...prev, [id]: !prev[id] }));

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const fmt = (v) => v ? formatRupiah(v) : 'Rp 0';

  const columns = [
    { key: 'po_number', label: 'No. PO / Identifikasi', render: (v, row) => (
      <div>
        <div className="flex items-center gap-2">
          <span className="font-bold text-blue-700">{v}</span>
          <BizBadge type={row.business_type} size="xs" />
        </div>
        <div className="text-xs text-muted-foreground/70 mt-0.5">
          {row.vendor_name ? <span className="text-purple-600">{row.vendor_name}</span> : <span>-</span>}
          {' · '}{fmtDate(row.po_date || row.created_at)}
        </div>
        {(row.serial_numbers || []).length > 0 && (
          <div className="text-xs text-emerald-600 mt-0.5 flex flex-wrap gap-1">
            {row.serial_numbers.slice(0, 3).map((sn, i) => (
              <span key={i} className="bg-emerald-50 px-1.5 py-0.5 rounded font-mono">{sn}</span>
            ))}
            {row.serial_numbers.length > 3 && <span className="text-muted-foreground/70">+{row.serial_numbers.length - 3} lagi</span>}
          </div>
        )}
      </div>
    )},
    { key: 'customer_name', label: 'Customer' },
    // FASE 9 (keluhan #4 owner: "bentuk cards yang memotong content dalamnya"):
    // `whitespace-nowrap` + `shrink-0` mencegah teks "2 item" terbelah dua baris
    // di dalam kotak rounded ketika kolom menyempit.
    { key: 'item_count', label: 'Items', render: (v, row) => (
      <button onClick={(e) => { e.stopPropagation(); togglePO(row.id); }}
        data-testid={`po-toggle-items-${row.id}`}
        className="inline-flex shrink-0 items-center gap-1 px-2 py-0.5 bg-muted text-foreground/90 text-xs rounded-full font-medium whitespace-nowrap leading-none hover:bg-blue-100 hover:text-blue-700 transition-colors">
        <span className="text-[10px]">{expandedPOs[row.id] ? '▼' : '▶'}</span>
        <span>{v || 0} item</span>
      </button>
    )},
    { key: 'total_qty', label: 'Total Qty', render: (v) => v?.toLocaleString('id-ID') },
    { key: 'deadline', label: 'Deadline Prod.', render: (v) => {
      if (!v) return '-';
      const isOverdue = new Date(v) < new Date();
      return <span className={isOverdue ? 'text-red-600 font-medium' : ''}>{fmtDate(v)}</span>;
    }},
    { key: 'delivery_deadline', label: 'Deadline Kirim', render: (v) => {
      if (!v) return '-';
      const isOverdue = new Date(v) < new Date();
      return <span className={isOverdue ? 'text-orange-600 font-medium' : 'text-muted-foreground'}>{fmtDate(v)}</span>;
    }},
    { key: 'status', label: 'Status / Workflow', render: (v, row) => (
      <div className="space-y-1.5">
        <StatusBadge status={v} />
        <POWorkflowIndicator status={v} compact={true} />
      </div>
    )},
    { key: 'created_by', label: 'Dibuat' },
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openDetail(row)} data-testid={`po-detail-btn-${row.id}`} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail"><Eye className="w-4 h-4" /></button>
        {/* 2026-08-01: pintu masuk ke BOM PO Maklon (Detail 360° → tab BOM).
            Sebelumnya BOM Template maklon tidak punya jalur dari daftar PO. */}
        {!isInternal && onNavigate && (
          <button
            onClick={() => onNavigate('maklon-po-360', { po_id: row.id, tab: 'bom' })}
            data-testid={`po-bom-btn-${row.id}`}
            className="p-1.5 rounded hover:bg-cyan-50 text-cyan-600"
            title="BOM & kebutuhan material (Detail 360°)"><Layers className="w-4 h-4" /></button>
        )}
        {canEdit && (
          <>
            <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-amber-50 text-amber-600" title="Edit"><Pencil className="w-4 h-4" /></button>
            {!['Closed', 'Completed'].includes(row.status) && (
              <>
                <button
                  onClick={() => setQuickCompletePO(row)}
                  data-testid={`quick-complete-btn-${row.id}`}
                  className="p-1.5 rounded hover:bg-violet-50 text-violet-600"
                  title="Quick Complete — selesaikan semua flow produksi sekaligus"
                >
                  <Zap className="w-4 h-4" />
                </button>
                <button onClick={() => { setCloseTargetPO(row); setCloseForm({ close_reason: CLOSE_REASONS[0], close_notes: '' }); setShowCloseModal(true); }}
                  className="p-1.5 rounded hover:bg-orange-50 text-orange-500 text-xs" title="Tutup PO">Close</button>
              </>
            )}
            <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus"><Trash2 className="w-4 h-4" /></button>
          </>
        )}
      </div>
    )}
  ];

  // Custom expandable row render for DataTable
  const expandedRowRender = (row) => {
    if (!expandedPOs[row.id] || !row.items || row.items.length === 0) return null;
    // FASE 9: konten expand DIBUNGKUS kartu dengan scroll horizontal SENDIRI
    // (`max-w-full overflow-x-auto`) supaya kolom paling kanan (Qty) tidak
    // terpotong oleh lebar tabel induk.
    return (
      <div className="bg-amber-50/30 border-t border-amber-100 px-4 py-3 max-w-full">
        <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Detail Item PO</p>
        <div className="max-w-full overflow-x-auto rounded-lg bg-[var(--card-surface,#fff)] border border-[var(--glass-border,rgba(0,0,0,0.08))]">
          <table className="w-full text-xs min-w-[760px]">
            <thead>
              <tr className="border-b border-amber-200">
                <th className="text-left py-1.5 pl-3 pr-3 text-amber-700 font-semibold whitespace-nowrap">Serial/Batch</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">SKU</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">Produk</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">Size</th>
                <th className="text-left py-1.5 pr-3 text-muted-foreground font-semibold">Warna</th>
                <th className="text-right py-1.5 pr-3 text-muted-foreground font-semibold whitespace-nowrap">Qty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-amber-100">
              {row.items.map(item => (
                <tr key={item.id} className="hover:bg-amber-50">
                  <td className="py-1.5 pl-3 pr-3 font-mono text-amber-700 font-semibold whitespace-nowrap">{item.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                  <td className="py-1.5 pr-3 font-mono text-blue-700">{item.sku || '-'}</td>
                  <td className="py-1.5 pr-3 text-foreground/90">{item.product_name}</td>
                  <td className="py-1.5 pr-3 text-muted-foreground">{item.size || '-'}</td>
                  <td className="py-1.5 pr-3 text-muted-foreground">{item.color || '-'}</td>
                  <td className="py-1.5 pr-3 text-right font-bold text-foreground/90 whitespace-nowrap">{(item.qty || 0).toLocaleString('id-ID')} pcs</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div><h1 className="text-2xl font-bold text-foreground">{isInternal ? 'PO Produksi Internal' : businessType === 'maklon' ? 'PO Maklon' : 'Production PO'}</h1><p className="text-muted-foreground text-sm mt-1">{isInternal ? 'Pesanan produksi untuk gudang sendiri — Model & Varian (Warna · Size · SKU) wajib dipilih' : businessType === 'maklon' ? 'Pesanan jasa maklon per klien — Artikel dari Katalog Buyer + Varian (Warna · Size · SKU)' : 'Kelola pesanan produksi multi-item dengan varian produk'}</p></div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      <div className="flex gap-2 flex-wrap">
        {['', ...STATUS_OPTIONS].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${filterStatus === s ? 'bg-blue-600 text-white border-blue-600' : 'border-border text-muted-foreground hover:bg-muted/60'}`}
            data-testid={`po-filter-${s || 'all'}`}>{s || 'Semua'}</button>
        ))}
      </div>

      <DataTable
        columns={columns}
        searchKeys={['po_number', 'customer_name']}
        expandedRow={expandedRowRender}
        storageKey="productionPOs"
        serverPagination={{
          fetcher: posFetcher,
          deps: [filterStatus, refetchKey],
          itemLabel: 'PO',
          initialSort: { key: 'created_at', dir: 'desc' },
          virtualize: true,
          virtualizeHeight: 650,
          estimatedRowHeight: 80,
        }}
        actions={
          <div className="flex items-center gap-2">
            <ImportExportPanel 
              importType="production-pos" 
              exportType="production-pos" 
              exportFilters={{ status: filterStatus }}
              onImportSuccess={() => refetchPOs()} 
            />
            {canCreate && (
              <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700" data-testid="create-po-btn"><Plus className="w-4 h-4" /> Buat PO</button>
            )}
          </div>
        }
      />

      {/* Create PO Modal */}
      {showModal && (
        <Modal title={editData ? `Edit PO: ${editData.po_number}` : (isInternal ? 'Buat PO Produksi Internal' : businessType === 'maklon' ? 'Buat PO Maklon' : 'Buat Production PO')} onClose={() => { setShowModal(false); setFormError(null); }} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            {formError && (
              <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2.5 text-sm text-red-700" data-testid="po-form-error">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span className="flex-1">{formError.text}</span>
                <button type="button" onClick={() => setFormError(null)} className="text-red-400 hover:text-red-600" aria-label="Tutup pesan"><X className="w-3.5 h-3.5" /></button>
              </div>
            )}
            {editData && editData.status === 'Closed' && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700">
                ⚠️ PO ini berstatus <strong>Closed</strong>. Anda mengedit sebagai Superadmin.
              </div>
            )}
            {editData && (
              <div className="bg-muted/40 rounded-xl p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Status Workflow</p>
                <POWorkflowIndicator status={editData.status} />
                <p className="text-[11px] text-muted-foreground mt-2">
                  🛡️ Guardrails aktif: item yang sudah memiliki shipment tidak dapat diubah SKU/Size/Color-nya, dan qty-nya tidak dapat lebih rendah dari total yang sudah dikirim/shipped.
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">
                  Nomor PO {numPolicy?.mode === 'auto' && !editData ? '' : '*'}
                  <span className="text-xs text-muted-foreground/70">
                    {numPolicy?.mode === 'auto' && !editData ? ' (otomatis)' : ' (manual)'}
                  </span>
                </label>
                {numPolicy?.mode === 'auto' && !editData ? (
                  <>
                    <input readOnly disabled data-testid="po-number-auto"
                      className="w-full border border-border rounded-lg px-3 py-2 text-sm font-mono bg-muted/50 text-muted-foreground"
                      value={numPolicy.nomor_berikutnya || numPolicy.contoh || 'dibuat otomatis'} />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Dibuat sistem saat disimpan (pola {numPolicy.format}). Ubah ke manual di
                      Administrasi Sistem → Penomoran Dokumen.
                    </p>
                  </>
                ) : (
                  <>
                    <input required data-testid="po-number-input"
                      className="w-full border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={form.po_number} onChange={e => setForm({...form, po_number: e.target.value})}
                      placeholder={numPolicy?.contoh || 'PO-2025-001'} />
                    {numPolicy?.format && !editData && (
                      <p className="text-[11px] text-muted-foreground mt-1">
                        Wajib mengikuti pola <b className="font-mono">{numPolicy.format}</b> —
                        contoh {numPolicy.contoh}.
                      </p>
                    )}
                  </>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">{isInternal ? 'Customer / Tujuan FG' : 'Buyer / Customer *'}</label>
                {isInternal ? (
                  <input data-testid="po-customer-input" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.customer_name} onChange={e => setForm({...form, customer_name: e.target.value})}
                    placeholder="Gudang FG Sendiri" />
                ) : (<>
                <SearchableSelect
                  options={buyers.map(b => ({ value: b.id, label: b.buyer_name, sub: b.buyer_code }))}
                  value={form.buyer_id}
                  onChange={val => {
                    const buyer = buyers.find(b => b.id === val);
                    setForm(f => ({...f, buyer_id: val, customer_name: buyer?.buyer_name || '',
                      items: f.items.map(it => ({ ...it, catalog_item_id: '', product_name: '', sku: '', size: '', color: '', cmt_price_snapshot: '', selling_price_snapshot: '' })) }));
                    fetchCatalog(val);
                  }}
                  placeholder="— Pilih Buyer —"
                />
                {!form.buyer_id && (
                  <input className="w-full border border-border rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    value={form.customer_name} onChange={e => setForm({...form, customer_name: e.target.value})} 
                    placeholder="Atau ketik nama customer manual" />
                )}
                </>)}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">
                Vendor / CMT{' '}
                <span className="text-xs text-muted-foreground/70">
                  {isInternal ? '(tujuan kirim material — opsional)' : 'opsional'}
                </span>
              </label>
              <SearchableSelect
                options={vendors.map(v => ({ value: v.id, label: v.garment_name, sub: v.garment_code }))}
                value={form.vendor_id}
                onChange={val => setForm({...form, vendor_id: val})}
                placeholder="— Pilih Vendor/CMT —"
                data-testid="po-vendor-select"
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Tanggal PO</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.po_date} onChange={e => setForm({...form, po_date: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Deadline Produksi</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.deadline} onChange={e => setForm({...form, deadline: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Deadline Pengiriman</label>
                <input type="date" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.delivery_deadline} onChange={e => setForm({...form, delivery_deadline: e.target.value})} />
              </div>
            </div>

            {/* PO Items */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-foreground/90">Item Produk *</label>
                <button type="button" onClick={addItem} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium">
                  <Plus className="w-3.5 h-3.5" /> Tambah Item
                </button>
              </div>
              {form.items.length === 0 && <p className="text-sm text-muted-foreground/70 italic text-center py-4 border border-dashed border-border rounded-lg">Klik "Tambah Item" untuk menambahkan produk ke PO</p>}
              <div className="space-y-3">
                {form.items.map((item, idx) => {
                  const hasShipments = !!item.__has_shipments;
                  const minQty = item.__min_qty || 0;
                  const maklonCat = !isInternal ? catalogItems.find(c => c.id === item.catalog_item_id) : null;
                  const maklonVariants = (maklonCat?.variants || []).filter(v => v.active !== false);
                  const maklonHasVariants = maklonVariants.length > 0;
                  const variantLocked = !isInternal && maklonHasVariants; // Size/Warna/SKU auto dari varian master data
                  const autoLocked = isInternal || variantLocked;
                  return (
                  <div key={idx} className={`border rounded-xl p-3 ${formError?.itemIdx === idx ? 'border-red-400 bg-red-50/50 ring-1 ring-red-200' : hasShipments ? 'border-amber-300 bg-amber-50/40' : 'border-border bg-muted/40'}`} data-testid={`po-item-row-${idx}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-muted-foreground">
                        Item #{idx + 1}
                        {hasShipments && (
                          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 uppercase tracking-wide">
                            🔒 sudah shipped (qty min: {minQty})
                          </span>
                        )}
                      </span>
                      {hasShipments ? (
                        <span className="text-xs text-muted-foreground/70" title="Tidak dapat dihapus karena sudah ada shipment/return">Tidak dapat dihapus</span>
                      ) : (
                        <button type="button" onClick={() => removeItem(idx)} className="text-red-400 hover:text-red-600"><X className="w-4 h-4" /></button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {isInternal ? (<>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Model (RnD) *</label>
                        <SearchableSelect
                          options={models.map(m => ({ value: m.id, label: m.name, sub: m.code }))}
                          value={item.model_id}
                          onChange={val => updateItem(idx, 'model_id', val)}
                          placeholder="Pilih Model"
                          required
                          disabled={hasShipments}
                          data-testid={`po-item-${idx}-model`}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Varian (Warna · Size · SKU) *</label>
                        <SearchableSelect
                          options={(rahazaVariants[item.model_id] || []).map(v => ({
                            value: v.id,
                            label: `${v.color_name || '-'} · ${v.size_code || '-'} — ${v.sku}`,
                            sub: v.sku,
                          }))}
                          value={item.rahaza_variant_id}
                          onChange={val => updateItem(idx, 'rahaza_variant_id', val)}
                          placeholder={item.model_id ? 'Pilih Varian ber-SKU' : 'Pilih Model dulu'}
                          required
                          disabled={!item.model_id || hasShipments}
                          data-testid={`po-item-${idx}-variant`}
                        />
                        {item.rahaza_variant_id && item.sku && (
                          <p className="text-[11px] text-emerald-700 font-medium mt-1" data-testid={`po-item-${idx}-sku-ok`}>
                            SKU terpilih: <span className="font-mono">{item.sku}</span>
                          </p>
                        )}
                        {item.model_id && (rahazaVariants[item.model_id] || []).length === 0 && (
                          <p className="text-[10px] text-amber-600 mt-1">Belum ada varian. Buat di Master Produk → tab Varian.</p>
                        )}
                      </div>
                      </>) : (<>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Produk (Buyer Catalog) *</label>
                        <SearchableSelect
                          options={catalogItems.map(c => ({ value: c.id, label: c.product_name, sub: c.artikel_code }))}
                          value={item.catalog_item_id}
                          onChange={val => updateItem(idx, 'catalog_item_id', val)}
                          placeholder={form.buyer_id ? 'Pilih dari Katalog Buyer' : 'Pilih Buyer dulu'}
                          required
                          disabled={!form.buyer_id || hasShipments}
                          data-testid={`po-item-${idx}-catalog`}
                        />
                        {(() => { const c = catalogItems.find(c => c.id === item.catalog_item_id); return c && ((c.color_options||[]).length || (c.size_options||[]).length) ? (
                          <p className="text-[10px] text-muted-foreground/70 mt-1">Warna: {(c.color_options||[]).join(', ') || '-'} • Size: {(c.size_options||[]).join(', ') || '-'}</p>
                        ) : null; })()}
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Artikel Buyer <span className="text-[10px] text-muted-foreground/60">(bisa custom)</span></label>
                        <input className="w-full border border-border rounded px-2 py-1.5 text-xs font-mono disabled:bg-muted disabled:text-muted-foreground" value={item.buyer_ref_code || ''} onChange={e => updateItem(idx, 'buyer_ref_code', e.target.value)} placeholder="kode artikel buyer" disabled={hasShipments} />
                      </div>
                      </>)}
                    </div>
                    {/* Selektor Varian dari master data (Maklon) — relasi ke Katalog Buyer */}
                    {!isInternal && item.catalog_item_id && (
                      <div className="mt-2">
                        <label className="block text-xs text-muted-foreground mb-1">
                          Varian (Warna · Size · SKU){maklonHasVariants && <span className="text-red-500"> *</span>}
                        </label>
                        {maklonHasVariants ? (
                          <SearchableSelect
                            options={maklonVariants.map(v => ({
                              value: v.sku,
                              label: `${v.color || '-'} · ${v.size || '-'} — ${v.sku}`,
                              sub: v.sku,
                            }))}
                            value={item.sku}
                            onChange={val => updateItem(idx, 'maklon_variant_sku', val)}
                            placeholder="Pilih varian dari master data"
                            required
                            disabled={hasShipments}
                            data-testid={`po-item-${idx}-variant`}
                          />
                        ) : (
                          <p className="text-[10px] text-amber-600 mt-1">Artikel ini belum punya varian ber-SKU. Isi Size/Warna/SKU manual, atau generate varian di Katalog Buyer → tab Varian.</p>
                        )}
                        {maklonHasVariants && item.sku && maklonVariants.some(v => v.sku === item.sku) && (
                          <p className="text-[11px] text-emerald-700 font-medium mt-1" data-testid={`po-item-${idx}-sku-ok`}>
                            SKU terpilih: <span className="font-mono">{item.sku}</span>
                          </p>
                        )}
                      </div>
                    )}
                    <div className="grid grid-cols-4 gap-2 mt-2">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Size{autoLocked && <span className="text-[10px] ml-1 text-muted-foreground/60">(auto)</span>}</label>
                        <input className="w-full border border-border rounded px-2 py-1.5 text-xs disabled:bg-muted disabled:text-muted-foreground" value={item.size} onChange={e => updateItem(idx, 'size', e.target.value)} placeholder="M" disabled={hasShipments || autoLocked} />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Warna{autoLocked && <span className="text-[10px] ml-1 text-muted-foreground/60">(auto)</span>}</label>
                        <input className="w-full border border-border rounded px-2 py-1.5 text-xs disabled:bg-muted disabled:text-muted-foreground" value={item.color} onChange={e => updateItem(idx, 'color', e.target.value)} placeholder="Hitam" disabled={hasShipments || autoLocked} />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">SKU{autoLocked && <span className="text-[10px] ml-1 text-muted-foreground/60">(auto)</span>}</label>
                        <input className="w-full border border-border rounded px-2 py-1.5 text-xs font-mono disabled:bg-muted disabled:text-muted-foreground" value={item.sku} onChange={e => updateItem(idx, 'sku', e.target.value)} placeholder="PRD-BLK-M" disabled={hasShipments || autoLocked} />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Qty *{hasShipments && <span className="text-amber-700 ml-1">(min {minQty})</span>}</label>
                        <input required type="number" min={hasShipments ? minQty : 1} className="w-full border border-border rounded px-2 py-1.5 text-xs" value={item.qty} onChange={e => updateItem(idx, 'qty', e.target.value)} placeholder="100" data-testid={`po-item-${idx}-qty`} />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-2">
                      <div className="col-span-1">
                        <label className="block text-xs text-muted-foreground mb-1">No. Seri / Batch <span className="text-amber-500 font-semibold">*</span></label>
                        <input required className="w-full border border-amber-200 rounded px-2 py-1.5 text-xs font-mono bg-amber-50 focus:outline-none focus:ring-1 focus:ring-amber-400" value={item.serial_number || ''} onChange={e => handleSerialChange(idx, e.target.value)} placeholder="SN-2025-001" data-testid={`po-item-serial-${idx}`} />
                        {(() => {
                          const cur = (item.serial_number || '').trim().toUpperCase().replace(/\s+/g, ' ');
                          if (!cur) return null;
                          const inFormDup = form.items.some((o, j) => j !== idx && (o.serial_number || '').trim().toUpperCase().replace(/\s+/g, ' ') === cur);
                          const chk = serialChecks[idx];
                          if (chk?.loading) {
                            return <p className="text-[10px] text-muted-foreground mt-1 inline-flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Mengecek seri…</p>;
                          }
                          const dbUsages = (chk && chk.usages) || [];
                          const dbDup = dbUsages.length > 0;
                          if (inFormDup || dbDup) {
                            return (
                              <p className="text-[10px] text-red-600 mt-1 flex items-start gap-1 font-medium" data-testid={`po-item-serial-warn-${idx}`}>
                                <AlertTriangle size={11} className="mt-px flex-shrink-0" />
                                <span>
                                  Seri dobel!{inFormDup ? ' Sama dgn item lain di PO ini.' : ''}
                                  {dbDup ? ` Sudah dipakai di ${dbUsages[0].po_number}${dbUsages.length > 1 ? ` +${dbUsages.length - 1} lagi` : ''}.` : ''}
                                  <span className="text-muted-foreground font-normal"> (boleh lanjut — hanya peringatan)</span>
                                </span>
                              </p>
                            );
                          }
                          if (chk && !chk.loading && dbUsages.length === 0) {
                            return <p className="text-[10px] text-emerald-600 mt-1">Seri unik ✓</p>;
                          }
                          return null;
                        })()}
                      </div>
                      {!isInternal && (<>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Selling Price (Rp)</label>
                        <input type="number" min="0" className="w-full border border-border rounded px-2 py-1.5 text-xs" value={item.selling_price_snapshot} onChange={e => updateItem(idx, 'selling_price_snapshot', e.target.value)} placeholder="85000" data-testid={`po-item-${idx}-selling`} />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">CMT Price (Rp)</label>
                        <input type="number" min="0" className="w-full border border-border rounded px-2 py-1.5 text-xs" value={item.cmt_price_snapshot} onChange={e => updateItem(idx, 'cmt_price_snapshot', e.target.value)} placeholder="35000" data-testid={`po-item-${idx}-rate`} />
                      </div>
                      </>)}
                    </div>
                  </div>
                  );
                })}
              </div>
            </div>

            {form.items.length > 0 && (
              <div className="bg-blue-50 rounded-lg p-3 text-sm">
                <div className="flex justify-between text-blue-700">
                  <span>Total Item: <strong>{form.items.length}</strong></span>
                  <span>Total Qty: <strong>{form.items.reduce((s, i) => s + (Number(i.qty) || 0), 0).toLocaleString('id-ID')} pcs</strong></span>
                </div>
              </div>
            )}

            {/* ── Aksesoris dari BOM Katalog (otomatis, read-only) ─────────── */}
            {!isInternal && (
              <div data-testid="po-bom-accessories-panel">
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-semibold text-foreground/90">
                    Aksesoris dari BOM Katalog{' '}
                    <span className="text-xs font-normal text-muted-foreground">(otomatis · tidak perlu diketik)</span>
                  </label>
                  {bomAcc.loading && (
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> menghitung…
                    </span>
                  )}
                </div>
                {bomAcc.rows.length === 0 ? (
                  <p className="text-xs text-muted-foreground/70 italic text-center py-2 border border-dashed border-border rounded-lg"
                    data-testid="po-bom-acc-empty">
                    {bomAcc.loading
                      ? 'Menghitung kebutuhan aksesoris dari BOM…'
                      : 'Pilih artikel Katalog Buyer + isi qty — aksesoris muncul otomatis bila artikel itu punya BOM Template aktif.'}
                  </p>
                ) : (
                  <div className="rounded-lg border border-emerald-200 overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-emerald-50">
                        <tr>
                          <th className="text-left px-3 py-1.5 text-emerald-800">Aksesoris</th>
                          <th className="text-left px-3 py-1.5 text-emerald-800">Kode</th>
                          <th className="text-right px-3 py-1.5 text-emerald-800">Kebutuhan</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-emerald-100 bg-card">
                        {bomAcc.rows.map((r, i) => (
                          <tr key={`${r.accessory_name}-${i}`} data-testid={`po-bom-acc-row-${i}`}>
                            <td className="px-3 py-1.5 text-foreground/90">
                              {r.accessory_name}
                              {r.unlinked && (
                                <span className="ml-1.5 px-1.5 py-0.5 rounded bg-red-100 text-red-700 text-[10px] font-bold">
                                  belum tertaut master
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-muted-foreground">{r.accessory_code || '-'}</td>
                            <td className="px-3 py-1.5 text-right font-bold text-emerald-700">
                              {Number(r.qty_needed || 0).toLocaleString('id-ID')} {r.unit || 'pcs'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="px-3 py-1.5 bg-emerald-50/60 text-[11px] text-emerald-800">
                      Untuk {Number(bomAcc.total_pcs || 0).toLocaleString('id-ID')} pcs. Baris ini ditulis
                      sistem saat PO disimpan — jangan ditambahkan lagi di bawah (nanti dobel).
                    </p>
                  </div>
                )}
                {(bomAcc.warnings || []).length > 0 && (
                  <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 space-y-0.5"
                    data-testid="po-bom-acc-warning">
                    {bomAcc.warnings.map((w, i) => (
                      <p key={i} className="text-[11px] text-amber-800 flex gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />{w}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* PO Accessories Add-on */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-foreground/90">
                  Aksesoris (Add-on){!isInternal && (
                    <span className="text-xs font-normal text-muted-foreground"> — hanya yang DI LUAR BOM</span>
                  )}
                </label>
                <button type="button" onClick={addAccessoryItem} className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium">
                  <Plus className="w-3.5 h-3.5" /> Tambah Aksesoris
                </button>
              </div>
              {(form.po_accessories || []).length === 0 && <p className="text-xs text-muted-foreground/70 italic text-center py-2 border border-dashed border-border rounded-lg">Opsional — Klik "Tambah Aksesoris" untuk menambahkan</p>}
              <div className="space-y-2">
                {(form.po_accessories || []).map((acc, idx) => (
                  <div key={idx} className="flex items-center gap-2 border border-emerald-200 rounded-lg p-2 bg-emerald-50/50">
                    <div className="flex-1">
                      <SearchableSelect
                        options={accessories.map(a => ({ value: a.id, label: a.accessory_name || a.name, sub: a.accessory_code || a.code || a.category || '' }))}
                        value={acc.accessory_id}
                        onChange={val => updateAccessoryItem(idx, 'accessory_id', val)}
                        placeholder="Pilih Aksesoris"
                      />
                    </div>
                    <input type="number" min="1" className="w-24 border border-border rounded px-2 py-1.5 text-xs" 
                      value={acc.qty_needed} onChange={e => updateAccessoryItem(idx, 'qty_needed', e.target.value)} placeholder="Qty" />
                    <span className="text-xs text-muted-foreground w-10">{acc.unit || 'pcs'}</span>
                    <input className="w-32 border border-border rounded px-2 py-1.5 text-xs" 
                      value={acc.notes || ''} onChange={e => updateAccessoryItem(idx, 'notes', e.target.value)} placeholder="Notes" />
                    <button type="button" onClick={() => removeAccessoryItem(idx)} className="text-red-400 hover:text-red-600"><X className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Catatan</label>
              <textarea rows="2" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
            </div>
            {editData && (
              <div>
                <label className="block text-sm font-medium text-foreground/90 mb-1">Status</label>
                {/* FASE 5 DA: status TIDAK bisa diubah manual — transisi hanya via tombol aksi
                    allowed_next di Detail PO (state machine backend). */}
                <div className="flex items-center gap-2">
                  <StatusBadge status={editData.status} />
                  <span className="text-xs text-muted-foreground">ubah status via tombol aksi di Detail PO</span>
                </div>
              </div>
            )}
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">{editData ? 'Simpan Perubahan' : 'Buat PO'}</button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Manual Close PO Modal */}
      {showCloseModal && closeTargetPO && (
        <Modal title={`Tutup PO Manual: ${closeTargetPO.po_number}`} onClose={() => setShowCloseModal(false)}>
          <form onSubmit={handleClosePO} className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
              Tindakan ini akan mengubah status PO menjadi <strong>Closed</strong>. Pastikan alasan dituliskan dengan benar.
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Alasan Penutupan *</label>
              <select required className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={closeForm.close_reason} onChange={e => setCloseForm({...closeForm, close_reason: e.target.value})}>
                {CLOSE_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Keterangan Tambahan</label>
              <textarea rows="3" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={closeForm.close_notes} onChange={e => setCloseForm({...closeForm, close_notes: e.target.value})} placeholder="Jelaskan detail alasan penutupan PO..." />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-orange-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-orange-700">Tutup PO</button>
              <button type="button" onClick={() => setShowCloseModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-muted/60">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailData && (
        <Modal title={`Detail PO: ${detailData.po_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            {/* PDF Export + Quick Complete */}
            <div className="flex justify-between items-center flex-wrap gap-2">
              {/* Quick Complete button (only for non-completed/closed POs) */}
              {canEdit && !['Completed', 'Closed'].includes(detailData.status) && (
                <button
                  onClick={() => { setShowDetail(false); setQuickCompletePO(detailData); }}
                  data-testid="detail-quick-complete-btn"
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-blue-600 text-white rounded-lg text-sm font-bold hover:from-violet-700 hover:to-blue-700 shadow-md hover:shadow-lg transition-all"
                >
                  <Zap className="w-4 h-4" />
                  Quick Complete
                </button>
              )}
              <button
                onClick={() => setSppPickerOpen(true)}
                data-testid="spp-export-pdf-btn"
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 font-medium">
                📄 Export PDF (SPP) — pilih kolom
              </button>
            </div>
            {/* FASE 5 DA: Aksi status dinamis dari allowed_next backend */}
            {canEdit && (Array.isArray(detailData.allowed_next) && detailData.allowed_next.length > 0 || detailData.can_close) && (
              <div data-testid="po-detail-actions" className="flex items-center flex-wrap gap-2 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 rounded-xl p-3">
                <span className="text-xs font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wide mr-1">Aksi:</span>
                {(detailData.allowed_next || []).map(ns => (
                  <button key={ns} data-testid={`po-action-${ns.toLowerCase().replace(/\s+/g, '-')}`}
                    onClick={() => transitionStatus(detailData.id, ns)}
                    className="px-3 py-1.5 rounded-lg text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors">
                    → {ns}
                  </button>
                ))}
                {detailData.can_close && (
                  <button data-testid="po-action-close"
                    onClick={() => { setShowDetail(false); setCloseTargetPO(detailData); setCloseForm({ close_reason: CLOSE_REASONS[0], close_notes: '' }); setShowCloseModal(true); }}
                    className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-orange-300 text-orange-600 hover:bg-orange-50 transition-colors">
                    Tutup PO
                  </button>
                )}
              </div>
            )}
            {/* Workflow Indicator */}
            <div className="bg-muted/40 rounded-xl p-4">
              <p className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide">Status Workflow</p>
              <POWorkflowIndicator status={detailData.status} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[{l:'No. PO',v:<span className="font-bold text-blue-700">{detailData.po_number}</span>},
                {l:'Customer',v:detailData.customer_name},
                {l:'Vendor',v:detailData.vendor_name||'-'},
                {l:'Status',v:<StatusBadge status={detailData.status} />},
                {l:'Tgl. PO',v:fmtDate(detailData.po_date)},
                {l:'Deadline Produksi',v:fmtDate(detailData.deadline)},
                {l:'Deadline Kirim',v:fmtDate(detailData.delivery_deadline)},
                {l:'Dibuat',v:detailData.created_by}
              ].map(it => <div key={it.l} className="bg-muted/40 rounded-lg p-3"><p className="text-xs text-muted-foreground">{it.l}</p><div className="font-medium text-sm mt-0.5">{it.v}</div></div>)}
            </div>
            {detailData.close_reason && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                <p className="text-sm font-semibold text-orange-700">Alasan Penutupan: {detailData.close_reason}</p>
                {detailData.close_notes && <p className="text-xs text-orange-600 mt-1">{detailData.close_notes}</p>}
                <p className="text-xs text-orange-500 mt-1">Ditutup oleh: {detailData.closed_by} pada {fmtDate(detailData.closed_at)}</p>
              </div>
            )}
            {detailData.items?.length > 0 && (
              <div className="space-y-3">
                <h4 className="font-semibold text-foreground/90">Item PO ({detailData.items.length})</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="bg-muted">
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Produk</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">No. Seri/Batch</th>
                      <th className="text-left px-3 py-2 text-xs text-muted-foreground">Size/Warna</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Qty</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Selling Price</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">CMT Price</th>
                      <th className="text-right px-3 py-2 text-xs text-muted-foreground">Margin/pcs</th>
                    </tr></thead>
                    <tbody>{detailData.items.map(it => {
                      const marginPcs = (it.selling_price_snapshot || 0) - (it.cmt_price_snapshot || 0);
                      return (
                        <tr key={it.id} className="border-t border-border/60">
                          <td className="px-3 py-2">{it.product_name}</td>
                          <td className="px-3 py-2 font-mono text-xs">{it.sku || '-'}</td>
                          <td className="px-3 py-2 font-mono text-xs text-amber-700 font-medium">{it.serial_number || <span className="text-muted-foreground/50">—</span>}</td>
                          <td className="px-3 py-2 text-xs">{it.size} / {it.color}</td>
                          <td className="px-3 py-2 text-right font-bold">{it.qty?.toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-emerald-700">{fmt(it.selling_price_snapshot)}</td>
                          <td className="px-3 py-2 text-right text-amber-700">{fmt(it.cmt_price_snapshot)}</td>
                          <td className={`px-3 py-2 text-right font-medium ${marginPcs >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{fmt(marginPcs)}</td>
                        </tr>
                      );
                    })}</tbody>
                    <tfoot><tr className="bg-muted/40 font-bold border-t-2 border-border">
                      <td className="px-3 py-2" colSpan={3}>Total</td>
                      <td className="px-3 py-2 text-right">{detailData.items.reduce((s,i)=>s+(i.qty||0),0).toLocaleString('id-ID')} pcs</td>
                      <td className="px-3 py-2 text-right text-emerald-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.selling_price_snapshot||0),0))}</td>
                      <td className="px-3 py-2 text-right text-amber-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.cmt_price_snapshot||0),0))}</td>
                      <td className="px-3 py-2 text-right text-blue-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*((i.selling_price_snapshot||0)-(i.cmt_price_snapshot||0)),0))}</td>
                    </tr></tfoot>
                  </table>
                </div>

                {/* Financial Summary */}
                {(() => {
                  const totalSales = detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.selling_price_snapshot||0),0);
                  const totalCMT = detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.cmt_price_snapshot||0),0);
                  const grossMargin = totalSales - totalCMT;
                  const marginPct = totalSales > 0 ? Math.round((grossMargin / totalSales) * 100) : 0;
                  return (
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                        <p className="text-xs text-emerald-600 font-medium">Total Nilai Penjualan</p>
                        <p className="text-xl font-bold text-emerald-700 mt-1">{fmt(totalSales)}</p>
                        <p className="text-xs text-emerald-500 mt-0.5">Selling Price × Qty</p>
                      </div>
                      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                        <p className="text-xs text-amber-600 font-medium">Total Biaya Vendor (CMT)</p>
                        <p className="text-xl font-bold text-amber-700 mt-1">{fmt(totalCMT)}</p>
                        <p className="text-xs text-amber-500 mt-0.5">CMT Price × Qty</p>
                      </div>
                      <div className={`border rounded-xl p-4 ${grossMargin >= 0 ? 'bg-blue-50 border-blue-200' : 'bg-red-50 border-red-200'}`}>
                        <p className={`text-xs font-medium ${grossMargin >= 0 ? 'text-blue-600' : 'text-red-600'}`}>Est. Gross Margin</p>
                        <p className={`text-xl font-bold mt-1 ${grossMargin >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{fmt(grossMargin)}</p>
                        <p className={`text-xs mt-0.5 ${grossMargin >= 0 ? 'text-blue-500' : 'text-red-500'}`}>{marginPct}% dari nilai penjualan</p>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
            {/* ── ACC-1: Kebutuhan Aksesoris (BOM explode + posisi stok + kekurangan) ── */}
            <div className="space-y-3" data-testid="po-accessory-requirements">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="font-semibold text-foreground/90 flex items-center gap-2">
                  <span className="w-5 h-5 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center text-xs font-bold">
                    {accReq?.requirements?.length ?? (detailData.po_accessories?.length || 0)}
                  </span>
                  Kebutuhan Aksesoris
                </h4>
                {accReq?.requirements?.length > 0 && (
                  <div className="flex items-center gap-2">
                    {accReq.summary?.shortage_lines > 0 ? (
                      <button
                        onClick={() => createAccRequest(detailData.id, true)}
                        disabled={accReqCreating}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-500 text-white hover:brightness-110 disabled:opacity-50"
                        data-testid="po-acc-create-request-btn"
                      >
                        {accReqCreating ? 'Membuat...' : `Buat Permintaan (${accReq.summary.shortage_lines} kurang)`}
                      </button>
                    ) : (
                      <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">
                        Stok mencukupi — tidak perlu permintaan
                      </span>
                    )}
                  </div>
                )}
              </div>

              {accReqLoading && <p className="text-xs text-muted-foreground">Memuat kebutuhan aksesoris...</p>}
              {accReq?.error && (
                <p className="text-xs text-red-700 dark:text-red-400">{accReq.error}</p>
              )}

              {accReqMsg && (
                <div
                  data-testid="po-acc-req-message"
                  className={`text-xs rounded-lg px-3 py-2 border ${
                    accReqMsg.type === 'success'
                      ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-300'
                      : 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30 text-red-800 dark:text-red-300'
                  }`}
                >
                  {accReqMsg.text}
                </div>
              )}

              {!accReqLoading && accReq && !accReq.error && accReq.requirements.length === 0 && (
                <p className="text-xs text-muted-foreground/80 italic border border-dashed border-border rounded-lg py-3 px-3">
                  Belum ada kebutuhan aksesoris. Untuk PO internal, kebutuhan dihitung otomatis dari
                  <strong> BOM aktif</strong> tiap item (qty per pcs × qty order). Pastikan BOM berisi
                  baris aksesoris, lalu simpan ulang PO.
                </p>
              )}

              {accReq?.summary?.unlinked_lines > 0 && (
                <div className="text-xs bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 text-amber-900 dark:text-amber-200 rounded-lg px-3 py-2">
                  <strong>{accReq.summary.unlinked_lines} baris belum tertaut ke master material</strong> —
                  stoknya tidak bisa dicek dan tidak akan ikut dalam permintaan. Perbaiki di modul BOM
                  (pilih material dari master, atau tombol "Perbaiki Otomatis").
                </div>
              )}

              {accReq?.requirements?.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="po-acc-req-table">
                    <thead><tr className="bg-emerald-50 dark:bg-emerald-500/10">
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">#</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Aksesoris</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Sumber</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Dibutuhkan</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Tersedia</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Kurang</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300 font-semibold">Status</th>
                    </tr></thead>
                    <tbody>{accReq.requirements.map((a, idx) => (
                      <tr key={a.id || idx} className="border-t border-emerald-100 dark:border-emerald-500/20 hover:bg-emerald-50/30 dark:hover:bg-emerald-500/5"
                        data-testid={`po-acc-req-row-${idx}`}>
                        <td className="px-3 py-2 text-xs text-muted-foreground/70">{idx + 1}</td>
                        <td className="px-3 py-2">
                          <div className="font-medium text-foreground/90">{a.material_name || a.accessory_name}</div>
                          <div className="font-mono text-xs text-emerald-700 dark:text-emerald-400">{a.material_code || a.accessory_code || '-'}</div>
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">
                          {a.source === 'bom_auto' ? 'BOM (otomatis)' : 'Manual'}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-foreground">
                          {(a.qty_needed || 0).toLocaleString('id-ID')} <span className="text-xs font-normal text-muted-foreground">{a.unit}</span>
                        </td>
                        <td className="px-3 py-2 text-right text-foreground/80">
                          {a.linked ? (a.available || 0).toLocaleString('id-ID') : <span className="text-muted-foreground">-</span>}
                        </td>
                        <td className={`px-3 py-2 text-right font-semibold ${a.shortage > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                          {a.linked ? (a.shortage || 0).toLocaleString('id-ID') : '-'}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {a.status === 'ok' && <span className="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-400/40">Cukup</span>}
                          {a.status === 'shortage' && <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-300 border border-red-400/40">Kurang</span>}
                          {a.status === 'unlinked' && <span className="px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-400/40">Belum tertaut</span>}
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}

              {accReq?.existing_requests?.length > 0 && (
                <div className="text-xs text-muted-foreground" data-testid="po-acc-existing-requests">
                  Permintaan aksesoris untuk PO ini:{' '}
                  {accReq.existing_requests.map(r => (
                    <span key={r.id} className="inline-block mr-2 px-2 py-0.5 rounded-full border border-border bg-muted/40 font-mono">
                      {r.request_code} · {r.status}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* File Attachments */}
            <FileAttachmentPanel
              entityType="production_po"
              entityId={detailData.id}
              userRole={userRole}
            />
          </div>
        </Modal>
      )}

      {confirmDelete && <ConfirmDialog title="Hapus Production PO?" message={`PO "${confirmDelete.po_number}" beserta semua work order dan progres akan dihapus permanen.`} onConfirm={handleDelete} onCancel={() => setConfirmDelete(null)} />}

      {/* Quick Complete Modal */}
      {quickCompletePO && (
        <QuickCompleteModal
          po={quickCompletePO}
          onClose={() => setQuickCompletePO(null)}
          onSuccess={() => { setQuickCompletePO(null); refetchPOs(); }}
        />
      )}
      {/* W2 — cetak SPP dengan kolom pilihan pemakai (Serial No dst.) */}
      {detailData && (
        <PdfColumnPicker
          docType="production-po"
          open={sppPickerOpen}
          onOpenChange={setSppPickerOpen}
          title={`Kolom PDF — SPP ${detailData.po_number || ''}`}
          hint="Centang kolom yang ingin tercetak pada tabel item SPP (mis. Serial No)."
          onConfirm={async (cols) => {
            try {
              const q = cols?.length ? `&cols=${encodeURIComponent(cols.join(','))}` : '';
              const res = await apiFetch(`/export-pdf?type=production-po&id=${detailData.id}${q}`);
              if (!res.ok) { alert('Gagal export PDF'); return; }
              const blob = await res.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = `SPP-${detailData.po_number}.pdf`; a.click();
              URL.revokeObjectURL(url);
            } catch (e) { alert('Gagal export PDF: ' + e.message); }
          }}
        />
      )}
    </div>
  );
}

