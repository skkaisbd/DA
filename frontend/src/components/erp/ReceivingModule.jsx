import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import Modal from '@/components/erp/Modal';
import ConfirmDialog from '@/components/erp/ConfirmDialog';
import { Button } from '@/components/ui/button';
import {
  ArrowDownToLine, Plus, Eye, CheckCircle, XCircle, Trash2,
  Package, Truck, Search, RefreshCw, FileText, Link2, AlertCircle, MapPin, Warehouse,
  Table2, LayoutGrid, ArrowUpDown,
} from 'lucide-react';
import { IconButton } from './IconButton';
import { Combobox } from './Combobox';
// Sprint A.1: UniversalScanner SSOT
import UniversalScanner from './scanner/UniversalScanner';
import OnwardCTA from './OnwardCTA';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
// FASE H-5 — rincian gulungan kain diisi DI SINI (pintu masuk kain), nomor roll otomatis.
import RollLinesEditor from './warehouse/RollLinesEditor';
import { isRollUnit, acceptedOf, rollLinesState, fmtQty } from './warehouse/rollLines';

const RECEIVING_VIEW_KEY = 'wh_receiving_view';
const CSV_HEAD = ['No. Penerimaan', 'Supplier / Sumber', 'Jenis', 'No. PO', 'Status',
  'Jml item', 'Qty diharap', 'Qty diterima', 'Qty ditolak', 'Lokasi', 'Tanggal',
  'Diterima oleh'];

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';

const STATUS_STYLES = {
  draft:      'bg-secondary text-muted-foreground border border-border',
  inspecting: 'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-300/20',
  received:   'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-300/20',
  failed:     'bg-red-50 dark:bg-red-400/15 text-red-700 dark:text-red-400 border border-red-300 dark:border-red-300/20',
};

const EMPTY_ITEM = () => ({
  product_name: '', sku: '',
  material_id: '', material_name: '',
  expected_qty: 0, received_qty: 0, rejected_qty: 0, unit: 'pcs',
  lot_number: '',   // U7: lot tracking
  expiry_date: '',  // U7: expiry date
  reject_reason: '', // FASE 6: alasan reject → dibawa ke Karantina QC
  rolls: [],        // FASE H-5: rincian gulungan (kain/benang) — nomor roll otomatis
});

export default function ReceivingModule({ token, deepLinkParams, onNavigate }) {
  const [receipts, setReceipts]   = useState([]);
  const [locations, setLocations] = useState([]);
  const [materials, setMaterials] = useState([]);
  // Sprint 2.1: PO integration
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showDetail, setShowDetail] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [search, setSearch] = useState('');
  // FASE 6: kategori alasan reject (dipakai saat qty rejected > 0 → masuk Karantina QC)
  const [rejectCats, setRejectCats] = useState([]);
  // FASE H-5: petunjuk nomor roll berikutnya (nomor TIDAK diketik) + salinan item
  // yang bisa disunting saat konfirmasi penerimaan (rincian gulungan sering baru
  // diketahui saat barang benar-benar ditimbang di gudang, bukan saat GR dibuat).
  const [rollPolicy, setRollPolicy] = useState(null);
  const [detailItems, setDetailItems] = useState([]);
  // Lokasi tujuan yang dipilih saat konfirmasi penerimaan (GR dari PO lahir
  // tanpa lokasi — kalau tidak ditanyakan di sini, stok mendarat di lokasi kosong).
  const [detailLocationId, setDetailLocationId] = useState('');
  const [receiveResult, setReceiveResult] = useState(null);
  const [missingRolls, setMissingRolls] = useState([]);

  // M12: memoized headers
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [form, setForm] = useState({
    source_type: 'supplier', source_ref: '', supplier_name: '',
    location_id: '', location_name: '', notes: '',
    // Sprint 2.1: PO fields
    po_id: '', po_number: '',
    items: [EMPTY_ITEM()]
  });

  const fetchData = useCallback(async () => {
    try {
      const [rRes, lRes, mRes, poRes] = await Promise.all([
        fetch('/api/wms/legacy/receiving',    { headers: { Authorization: `Bearer ${token}` } }),
        // FASE F+ (2026-07-25): dropdown lokasi tujuan pakai SSOT storage-locations
        // (wh_zones + rahaza storage), bukan lagi legacy warehouse_locations.
        fetch('/api/rahaza/storage-locations', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/rahaza/materials?limit=500', { headers: { Authorization: `Bearer ${token}` } }),
        // Sprint 2.1: Fetch approved POs (also include partially_received for resume)
        fetch('/api/rahaza/purchase-orders?status=approved', { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (rRes.ok) setReceipts(await rRes.json());
      if (lRes.ok) setLocations(await lRes.json());
      if (mRes.ok) {
        const data = await mRes.json();
        setMaterials(Array.isArray(data) ? data : (data.items || []));
      }
      if (poRes.ok) setPurchaseOrders(await poRes.json());
      // FASE H-5: baris kain yang sudah masuk stok tetapi belum punya gulungan.
      // Ditarik bersama daftar penerimaan supaya lubangnya terlihat di layar yang
      // sama tempat lubang itu tercipta.
      try {
        const mr = await fetch('/api/wms/fabric-rolls/missing-from-receipts?limit=50',
          { headers: { Authorization: `Bearer ${token}` } });
        if (mr.ok) setMissingRolls((await mr.json()).items || []);
      } catch { /* noop */ }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // FASE 6: ambil daftar kategori alasan reject sekali
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/wms/quarantine/reject-categories', { headers: { Authorization: `Bearer ${token}` } });
        if (r.ok) setRejectCats(await r.json());
      } catch { /* noop */ }
    })();
  }, [token]);

  // FASE H-5: kebijakan nomor roll (mode otomatis + nomor berikutnya) untuk ditampilkan
  // sebagai petunjuk. Kalau gagal diambil, layar tetap jalan — hanya petunjuknya hilang.
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/wms/fabric-rolls/number-policy', { headers: { Authorization: `Bearer ${token}` } });
        if (r.ok) setRollPolicy(await r.json());
      } catch { /* noop */ }
    })();
  }, [token]);

  // Buka detail → siapkan salinan item yang bisa disunting (rincian gulungan).
  const openDetail = (receipt) => {
    setShowDetail(receipt);
    setDetailItems((receipt.items || []).map(it => ({ ...it, rolls: (it.rolls || []).map(l => ({ ...l })) })));
    setDetailLocationId(receipt.location_id || '');
  };
  const updateDetailItem = (idx, patch) => setDetailItems(items =>
    items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));

  // Total qty pada layar detail — dihitung SEKALI supaya ringkasan, peringatan
  // "masih 0", dan tombol Confirm memakai angka yang sama benda-nya.
  const detailTotals = useMemo(() => {
    const items = detailItems.length ? detailItems : (showDetail?.items || []);
    const sum = (f) => items.reduce((s, it) => s + (parseFloat(it?.[f]) || 0), 0);
    const received = sum('received_qty');
    const rejected = sum('rejected_qty');
    return { received, rejected, expected: sum('expected_qty'), touched: received + rejected };
  }, [detailItems, showDetail]);

  // P1.C: Open the just-created GR from PO (deep-link from PurchaseOrderModule)
  useEffect(() => {
    if (deepLinkParams?.receipt_id && receipts.length > 0) {
      const gr = receipts.find(r => r.id === deepLinkParams.receipt_id);
      if (gr) {
        openDetail(gr);
      }
    }
  }, [deepLinkParams, receipts]);

  // Sprint 1.1: When user picks a material from dropdown, auto-fill name + unit
  const handleMaterialPick = (idx, materialId) => {
    const mat = materials.find(m => m.id === materialId);
    setForm(f => ({
      ...f,
      items: f.items.map((it, i) => i === idx ? {
        ...it,
        material_id:   mat?.id   || '',
        material_name: mat?.name || '',
        product_name:  mat?.name || it.product_name,
        sku:           mat?.code || it.sku,
        unit:          mat?.unit || it.unit,
        // FASE H-5: rincian gulungan hanya berlaku untuk satuan kain/benang.
        // Ganti material ke satuan pcs ⇒ rincian lama dibuang, bukan dibiarkan
        // menempel diam-diam dan ditolak server saat konfirmasi.
        rolls: isRollUnit(mat?.unit) ? (it.rolls || []) : [],
      } : it)
    }));
  };

  // Sprint 2.1: When user picks a PO, auto-fill vendor and items
  const handlePOPick = (poId) => {
    const po = purchaseOrders.find(p => p.id === poId);
    if (!po) {
      setForm(f => ({ ...f, po_id: '', po_number: '' }));
      return;
    }
    
    // Pre-fill items from PO
    const poItems = (po.items || []).map(item => ({
      product_name:  item.material_name || '',
      sku:           item.material_code || '',
      material_id:   item.material_id,
      material_name: item.material_name || '',
      expected_qty:  item.qty_ordered || 0,
      received_qty:  item.qty_ordered || 0,
      rejected_qty:  0,
      unit:          item.unit || 'pcs',
    }));

    setForm(f => ({
      ...f,
      po_id: po.id,
      po_number: po.po_number,
      supplier_name: po.vendor_name,
      items: poItems.length > 0 ? poItems : [EMPTY_ITEM()],
    }));
  };

  const handleCreate = async () => {
    try {
      const loc = locations.find(l => l.id === form.location_id);
      // FASE H-5: cegah rincian gulungan yang tidak menjelaskan qty diterima SEBELUM
      // dikirim — biar penolakannya bukan kejutan setelah tombol simpan ditekan.
      const badRoll = (form.items || []).find(it => {
        if (!isRollUnit(it.unit) || !(it.rolls || []).length) return false;
        return rollLinesState(it.rolls, acceptedOf(it)).state !== 'match';
      });
      if (badRoll) {
        const st = rollLinesState(badRoll.rolls, acceptedOf(badRoll));
        alert(`Rincian gulungan ${badRoll.sku || badRoll.product_name} belum cocok:\n\n`
          + `${st.count} gulungan = ${fmtQty(st.total)} ${badRoll.unit}, qty diterima ${fmtQty(acceptedOf(badRoll))} ${badRoll.unit}`
          + `${st.diff ? ` (selisih ${st.diff > 0 ? '+' : ''}${fmtQty(st.diff, 3)})` : ''}.\n\n`
          + 'Perbaiki angkanya — stok dan gulungan harus menjelaskan penerimaan yang sama.');
        return;
      }
      // FASE 6: ubah `reject_reason` (UI) → `reject_reasons[]` (kontrak backend/karantina)
      const items = (form.items || []).map(it => {
        const rej = parseFloat(it.rejected_qty) || 0;
        const out = { ...it };
        delete out.reject_reason;
        out.reject_reasons = rej > 0
          ? [{ code: it.reject_reason || 'OTHER', qty: rej, notes: '' }]
          : [];
        out.rolls = isRollUnit(it.unit)
          ? (it.rolls || []).filter(l => parseFloat(l.qty) > 0)
            .map(l => ({ qty: parseFloat(l.qty), color_lot: l.color_lot || '', notes: l.notes || '' }))
          : [];
        return out;
      });
      const payload = { ...form, items, location_name: loc?.name || form.location_name };
      const res = await fetch('/api/wms/legacy/receiving', { method: 'POST', headers, body: JSON.stringify(payload) });
      if (res.ok) { setShowCreate(false); resetForm(); fetchData(); }
      else {
        const err = await res.json().catch(() => ({}));
        alert('Error: ' + (err.detail || res.status));
      }
    } catch (e) { alert('Error: ' + e.message); }
  };

  const handleStatusChange = async (receipt, newStatus) => {
    try {
      // FASE H-5: item yang dikirim adalah SALINAN YANG DISUNTING di layar detail
      // (rincian gulungan biasanya baru terisi di sini, saat kain ditimbang).
      //
      // 2026-08-19 — DUA cacat diperbaiki pada jalur ini:
      //  (1) `reject_reason` (bentuk UI) TIDAK pernah dipetakan ke
      //      `reject_reasons[]` (kontrak backend/karantina) — `handleCreate`
      //      melakukannya, jalur konfirmasi detail TIDAK. Akibatnya alasan reject
      //      yang dipilih di modal detail hilang dalam perjalanan.
      //  (2) tidak ada penjaga qty 0: menekan Confirm pada GR dari PO (yang selalu
      //      lahir `received_qty=0`) mencatat penerimaan TANPA menambah stok
      //      sedikit pun — pembelian tampak selesai tetapi gudang tetap kosong.
      const items = (detailItems.length ? detailItems : receipt.items || []).map(it => {
        const rej = parseFloat(it.rejected_qty) || 0;
        const out = {
          ...it,
          received_qty: parseFloat(it.received_qty) || 0,
          rejected_qty: rej,
          rolls: isRollUnit(it.unit)
            ? (it.rolls || []).filter(l => parseFloat(l.qty) > 0)
              .map(l => ({ qty: parseFloat(l.qty), color_lot: l.color_lot || '', notes: l.notes || '' }))
            : [],
        };
        delete out.reject_reason;
        out.reject_reasons = rej > 0
          ? [{ code: it.reject_reason || 'OTHER', qty: rej, notes: '' }]
          : [];
        return out;
      });
      if (newStatus === 'received') {
        const touched = items.reduce(
          (s, it) => s + (parseFloat(it.received_qty) || 0) + (parseFloat(it.rejected_qty) || 0), 0);
        if (touched <= 0) {
          alert('Qty diterima masih 0.\n\nIsi dulu jumlah yang benar-benar datang pada '
            + 'setiap baris (atau tekan "Terima semua sesuai PO").\n\n'
            + 'Kalau dikonfirmasi sekarang, penerimaan tercatat tetapi stok TIDAK '
            + 'bertambah sama sekali — inilah sebabnya pembelian terlihat selesai '
            + 'padahal gudang tetap kosong.');
          return;
        }
        if (!(detailLocationId || receipt.location_id)) {
          alert('Lokasi tujuan belum dipilih.\n\nStok yang masuk harus mendarat di rak '
            + 'yang jelas — tanpa lokasi, barangnya ada di sistem tetapi tidak ada di '
            + 'rak mana pun, dan Put-Away tidak bisa menemukannya.');
          return;
        }
      }
      const locPick = locations.find(l => l.id === (detailLocationId || receipt.location_id));
      const badRoll = items.find(it => (it.rolls || []).length
        && rollLinesState(it.rolls, acceptedOf(it)).state !== 'match');
      if (badRoll) {
        const st = rollLinesState(badRoll.rolls, acceptedOf(badRoll));
        alert(`Rincian gulungan ${badRoll.sku || badRoll.product_name} belum cocok:\n\n`
          + `${st.count} gulungan = ${fmtQty(st.total)} ${badRoll.unit}, qty diterima ${fmtQty(acceptedOf(badRoll))} ${badRoll.unit}.\n\n`
          + 'Perbaiki angkanya dulu — kalau tidak, stok dan gulungan akan bercerita beda.');
        return;
      }
      const res = await fetch(`/api/wms/legacy/receiving/${receipt.id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          status: newStatus,
          items,
          location_id: detailLocationId || receipt.location_id || '',
          location_name: locPick ? `${locPick.code} - ${locPick.name}` : (receipt.location_name || ''),
        }),
      });
      if (res.ok) {
        // FASE 6: beri tahu bila ada qty reject yang masuk Karantina QC
        const updated = await res.json().catch(() => ({}));
        const qs = updated?.quarantine_summary;
        if (qs?.total_qty > 0) {
          alert(`Barang diterima.\n\n${qs.total_qty} unit REJECT dipindahkan ke ${qs.location?.name || 'Karantina QC'} `
            + `(stok diblokir).\nTindak lanjuti di menu Gudang → "Karantina QC": lepas ke stok, retur supplier, atau scrap.`);
        }
        // FASE H-5: umpan balik gulungan — nomor yang terbit & baris kain yang
        // masih menunggu gulungan (supaya Cutting tidak mandek tanpa peringatan).
        const created = updated?.rolls_created || [];
        const pending = updated?.rolls_pending || [];
        if (created.length || pending.length) {
          setReceiveResult({ receipt_number: updated?.receipt_number || receipt.receipt_number, created, pending });
        }
        setShowDetail(null); setDetailItems([]); fetchData();
      }
      else {
        const err = await res.json().catch(() => ({}));
        alert('Error: ' + (err.detail || res.status));
      }
    } catch (e) { alert('Error: ' + e.message); }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`/api/wms/legacy/receiving/${id}`, { method: 'DELETE', headers });
      setConfirmDelete(null); fetchData();
    } catch (e) { alert('Error: ' + e.message); }
  };

  const resetForm = () => setForm({
    source_type: 'supplier', source_ref: '', supplier_name: '',
    location_id: '', location_name: '', notes: '',
    items: [EMPTY_ITEM()]
  });

  const addItem    = () => setForm(f => ({ ...f, items: [...f.items, EMPTY_ITEM()] }));
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const updateItem = (idx, field, val) => setForm(f => ({
    ...f, items: f.items.map((it, i) => i === idx ? { ...it, [field]: val } : it)
  }));

  const filtered = search ? receipts.filter(r =>
    r.receipt_number?.toLowerCase().includes(search.toLowerCase()) ||
    r.supplier_name?.toLowerCase().includes(search.toLowerCase())
  ) : receipts;

  // ── F13-B (sesi #12) — PENERIMAAN BARANG HARUS BISA DIBAWA ────────────────
  // Ini pintu masuk SELURUH stok: setiap angka di gudang berawal di sini.
  // Sebelum ini layarnya hanya kartu — tidak ada kolom qty diterima/ditolak,
  // tidak ada urutan, tidak ada unduhan. Akibatnya dua pertanyaan yang paling
  // sering ditanya tidak terjawab tanpa membuka satu per satu:
  //   · "minggu ini kita menerima apa saja, dari supplier mana, berapa?"
  //   · "berapa yang DITOLAK, dan dari penerimaan yang mana?"  ← qty ditolak
  //     adalah dasar klaim ke supplier; kalau harus dihitung dengan mata,
  //     klaimnya tidak pernah diajukan.
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(RECEIVING_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem(RECEIVING_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [sort, setSort] = useState({ key: 'created_at', dir: 'desc' });

  // Ringkasan per penerimaan dihitung SEKALI di sini supaya tabel, kartu, dan
  // CSV memakai angka yang sama benda-nya (bukan tiga perhitungan berbeda).
  const enriched = useMemo(() => filtered.map((r) => {
    const items = r.items || [];
    const sum = (f) => items.reduce((s, it) => s + Number(it?.[f] || 0), 0);
    return {
      ...r,
      item_count: items.length,
      expected_total: sum('expected_qty'),
      received_total: sum('received_qty'),
      rejected_total: sum('rejected_qty'),
      source_label: r.supplier_name || r.source_type || '—',
    };
  }), [filtered]);

  const rows = useMemo(() => {
    const list = [...enriched];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = a?.[key], bv = b?.[key];
      const num = typeof av === 'number' || typeof bv === 'number';
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [enriched, sort]);
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 12);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const csvRows = rows.map((r) => [
    r.receipt_number, r.source_label, r.source_type || '', r.po_number || '',
    r.status, r.item_count, r.expected_total, r.received_total, r.rejected_total,
    r.location_name || r.location_code || '', String(r.created_at || '').slice(0, 10),
    r.received_by_name || r.created_by || '',
  ]);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>;

  return (
    <div className="space-y-5" data-testid="wh-receiving-module">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Goods Receiving</h1>
          <p className="text-muted-foreground text-sm">Terima barang dari supplier, produksi, atau transfer</p>
        </div>
        <div className="flex items-center gap-2">
          <IconButton label="Muat ulang penerimaan" onClick={fetchData} data-testid="receiving-refresh">
            <RefreshCw className="w-4 h-4 text-muted-foreground" />
          </IconButton>
          <Button onClick={() => setShowCreate(true)} className="bg-primary text-primary-foreground hover:brightness-110 gap-1.5" data-testid="create-receipt-btn">
            <Plus className="w-4 h-4" /> New Receipt
          </Button>
        </div>
      </div>

      {/* Sprint 1.1 info banner */}
      <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20">
        <Link2 className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
        <p className="text-xs text-blue-600 dark:text-blue-300">
          <strong>Sync Otomatis:</strong> Jika item dipilih dari master material, stok akan otomatis tercatat di modul Inventory (Material Issue / BOM) saat GR di-<em>Confirm Received</em>.
        </p>
      </div>

      {/* ── FASE H-5: peringatan kain yang masuk stok tanpa gulungan ─────────── */}
      {missingRolls.length > 0 && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-50 dark:bg-amber-400/10 border border-amber-300 dark:border-amber-400/25"
          data-testid="gr-missing-rolls-banner">
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-xs text-amber-800 dark:text-amber-300">
              <strong>{missingRolls.length} baris penerimaan kain belum punya gulungan.</strong>{' '}
              Kain ini ada di stok tetapi tidak bisa dipotong di Cutting sampai gulungannya diterbitkan
              ({missingRolls.slice(0, 3).map(m => m.material_code).join(', ')}
              {missingRolls.length > 3 ? `, +${missingRolls.length - 3} lagi` : ''}).
            </p>
          </div>
          {onNavigate && (
            <button onClick={() => onNavigate('wms-fabric-rolls')}
              className="shrink-0 text-xs px-2.5 py-1 rounded-lg bg-amber-600 text-white hover:brightness-110"
              data-testid="gr-banner-goto-rolls">
              Terbitkan Roll →
            </button>
          )}
        </div>
      )}

      {/* RC-FLOW-UX Alur 1/2 — GRN → Put-Away → Stok */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Langkah Berikutnya"
        actions={[
          { module: 'wh-putaway', label: 'Put-Away Sekarang', icon: MapPin, primary: true, hint: 'Alokasikan barang yang sudah diterima ke lokasi/bin' },
          { module: 'wms-stock-hub', label: 'Lihat Stok', icon: Warehouse, hint: 'Cek stok terkini setelah penerimaan' },
        ]}
      />

      {/* Search + pengalih tampilan + unduh */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative max-w-sm flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <GlassInput placeholder="Cari no. penerimaan / supplier..." value={search}
            onChange={e => setSearch(e.target.value)} className="pl-9"
            data-testid="receiving-search" />
        </div>
        <div className="inline-flex rounded-lg border border-[var(--glass-border)] overflow-hidden">
          <button type="button" onClick={() => setView('table')} data-testid="receiving-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="receiving-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
        <ExportCsvButton filename="penerimaan-barang" testId="receiving-export-csv"
          head={CSV_HEAD} rows={csvRows}
          note={`${rows.reduce((s, r) => s + r.rejected_total, 0)} ditolak`} />
      </div>

      {/* Receipts List */}
      {filtered.length === 0 ? (
        <GlassCard hover={false} className="p-8 text-center">
          <ArrowDownToLine className="w-10 h-10 text-muted-foreground/30 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">
            {search ? 'Tidak ada penerimaan yang cocok dengan pencarian' : 'Belum ada goods receipt'}
          </p>
        </GlassCard>
      ) : view === 'table' ? (
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--card-surface)]">
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="receiving-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left">
                  {[['receipt_number', 'No. Penerimaan'], ['source_label', 'Supplier / Sumber'],
                    ['source_type', 'Jenis'], ['po_number', 'No. PO'],
                    ['status', 'Status'], ['item_count', 'Jml item'],
                    ['expected_total', 'Qty diharap'], ['received_total', 'Qty diterima'],
                    ['rejected_total', 'Qty ditolak'],
                    ['created_at', 'Tanggal']].map(([k, label]) => (
                    <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                      <button type="button" onClick={() => toggleSort(k)}
                        data-testid={`receiving-sort-${k}`}
                        className="inline-flex items-center gap-1 hover:text-primary">
                        {label}
                        <ArrowUpDown size={10}
                          className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                      </button>
                    </th>
                  ))}
                  <th className="px-2.5 py-2 font-semibold text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg)] cursor-pointer"
                      onClick={() => openDetail(r)}
                      data-testid={`receipt-row-${r.receipt_number}`}>
                    <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.receipt_number}</td>
                    <td className="px-2.5 py-2">{r.source_label}</td>
                    <td className="px-2.5 py-2 text-muted-foreground">{r.source_type || '—'}</td>
                    <td className="px-2.5 py-2 font-mono">{r.po_number || '—'}</td>
                    <td className="px-2.5 py-2">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[r.status] || STATUS_STYLES.draft}`}>{r.status}</span>
                    </td>
                    <td className="px-2.5 py-2 text-right">{r.item_count}</td>
                    <td className="px-2.5 py-2 text-right">{r.expected_total.toLocaleString('id-ID')}</td>
                    <td className="px-2.5 py-2 text-right font-semibold">{r.received_total.toLocaleString('id-ID')}</td>
                    {/* Qty ditolak diberi warna hanya kalau memang > 0 — angka nol
                        yang diwarnai merah membuat orang berhenti memperhatikan. */}
                    <td className={`px-2.5 py-2 text-right ${r.rejected_total > 0 ? 'text-red-600 dark:text-red-400 font-semibold' : 'text-muted-foreground'}`}>
                      {r.rejected_total.toLocaleString('id-ID')}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                    <td className="px-2.5 py-2 text-right">
                      <button onClick={(e) => { e.stopPropagation(); openDetail(r); }}
                        className="h-7 px-2.5 rounded-lg border border-[var(--glass-border)] text-[11px] hover:bg-[var(--glass-bg)]">
                        Detail
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} className="px-3" />
        </div>
      ) : (
      <div className="space-y-3">
        {paged.map(r => (
          <GlassCard key={r.id} className="p-4 cursor-pointer" onClick={() => openDetail(r)} data-testid={`receipt-${r.receipt_number}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-primary/15 border border-primary/25 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground font-mono">{r.receipt_number}</p>
                  <p className="text-xs text-muted-foreground">
                    {r.supplier_name || r.source_type} &bull; {r.items?.length || 0} items
                    {r.items?.some(i => i.material_id) && (
                      <span className="ml-1.5 text-blue-600 dark:text-blue-400 font-medium">
                        <Link2 className="w-3 h-3 inline" /> synced
                      </span>
                    )}
                    {/* P1.C: Show "From PO" badge if linked */}
                    {r.po_number && (
                      <span className="ml-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                        &bull; <Truck className="w-3 h-3 inline" /> Dari PO {r.po_number}
                        {r.enforce_po_qty && <span className="ml-1 text-[10px] opacity-70">(qty terbatas)</span>}
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${STATUS_STYLES[r.status] || STATUS_STYLES.draft}`}>{r.status}</span>
                <p className="text-xs text-muted-foreground">{fmtDate(r.created_at)}</p>
              </div>
            </div>
          </GlassCard>
        ))}
        <PaginationLite page={page} totalPages={totalPages} total={total}
          pageSize={pageSize} onPageChange={setPage} />
      </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <Modal title="New Goods Receipt" onClose={() => setShowCreate(false)} size="xl">
          <div className="space-y-4">
            {/* Sprint 2.1: PO Selection */}
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20">
              <div className="flex items-start gap-2 mb-2">
                <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <label className="text-xs font-semibold text-blue-600 dark:text-blue-300 mb-1 block">Link ke Purchase Order (Optional)</label>
                  <Combobox
                    value={form.po_id}
                    onChange={(v) => handlePOPick(v)}
                    options={[
                      { value: '', label: 'Manual (tanpa PO)' },
                      ...purchaseOrders.map(po => ({
                        value: po.id,
                        label: `${po.po_number} - ${po.vendor_name}`,
                        description: `${po.item_count} items`,
                      }))
                    ]}
                    placeholder="Manual (tanpa PO)"
                    searchPlaceholder="Cari PO atau vendor..."
                    emptyMessage="PO tidak ditemukan"
                    className="border-blue-400 dark:border-blue-400/30"
                    data-testid="gr-po-select"
                  />
                  {form.po_number && (
                    <p className="text-xs text-blue-600 dark:text-blue-300 mt-1">✓ Items akan di-pre-fill dari PO {form.po_number}</p>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Source Type</label>
                <select value={form.source_type} onChange={e => setForm(f => ({ ...f, source_type: e.target.value }))} className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-3 py-2 text-sm text-foreground">
                  <option value="supplier">Supplier</option>
                  <option value="production">Production</option>
                  <option value="transfer">Transfer</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Reference (PO/SO)</label>
                <GlassInput value={form.source_ref} onChange={e => setForm(f => ({ ...f, source_ref: e.target.value }))} placeholder="PO-001" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Supplier / Source</label>
                <GlassInput value={form.supplier_name} onChange={e => setForm(f => ({ ...f, supplier_name: e.target.value }))} placeholder="Nama supplier" />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Location Tujuan</label>
                <Combobox
                  value={form.location_id}
                  onChange={(v) => setForm(f => ({ ...f, location_id: v }))}
                  options={locations.map(l => ({
                    value: l.id,
                    label: `${l.code} - ${l.name}`,
                    testId: `gr-location-option-${l.code}`,
                  }))}
                  placeholder="Pilih lokasi..."
                  searchPlaceholder="Cari lokasi..."
                  emptyMessage="Lokasi tidak ditemukan"
                  data-testid="gr-location-select"
                />
              </div>
            </div>

            {/* Items */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-muted-foreground">Items</label>
                <button onClick={addItem} className="text-xs text-primary hover:brightness-110 font-medium">+ Add Item</button>
              </div>
              <div className="space-y-3">
                {form.items.map((item, idx) => (
                  <div key={idx} className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-2">
                    {/* Row 1: Material picker */}
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[10px] text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
                          <Link2 className="w-3 h-3" /> Pilih dari Master Material (opsional)
                        </label>
                        <Combobox
                          value={item.material_id || ''}
                          onChange={(v) => handleMaterialPick(idx, v)}
                          options={[
                            { value: '', label: '-- Tanpa link material --' },
                            ...materials.map(m => ({
                              value: m.id,
                              label: `${m.code} — ${m.name}`,
                              description: m.unit,
                              testId: `item-material-option-${m.code}`,
                            }))
                          ]}
                          placeholder="-- Tanpa link material --"
                          searchPlaceholder="Cari material..."
                          emptyMessage="Material tidak ditemukan"
                          size="sm"
                          className="border-blue-400/25"
                          data-testid={`item-material-select-${idx}`}
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground">Product Name</label>
                        <GlassInput
                          value={item.product_name}
                          onChange={e => updateItem(idx, 'product_name', e.target.value)}
                          placeholder="Nama produk"
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>
                    {/* Row 2: Qty fields */}
                    <div className="grid grid-cols-5 gap-2 items-end">
                      <div>
                        <label className="text-[10px] text-muted-foreground">SKU</label>
                        {/* Sprint A.1: scan button next to SKU */}
                        <div className="flex gap-1">
                          <GlassInput value={item.sku} onChange={e => updateItem(idx, 'sku', e.target.value)} placeholder="SKU" className="h-8 text-xs flex-1" data-testid={`sku-input-${idx}`} />
                          <UniversalScanner
                            variant="button"
                            onScan={(code) => updateItem(idx, 'sku', code)}
                            title="Scan SKU"
                            size="icon"
                            btnVariant="outline"
                            className="h-8 w-8 shrink-0 p-0"
                            data-testid={`scan-sku-${idx}`}
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground">Unit</label>
                        <SmartNativeSelect
                          value={item.unit}
                          onChange={e => updateItem(idx, 'unit', e.target.value)}
                          className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-2 h-8 text-xs text-foreground"
                        >
                          {['pcs','kg','gram','m','set','pair','roll','lbr'].map(u => <option key={u} value={u}>{u}</option>)}
                        </SmartNativeSelect>
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground">Expected</label>
                        <GlassInput type="number" value={item.expected_qty} onChange={e => updateItem(idx, 'expected_qty', parseFloat(e.target.value) || 0)} className="h-8 text-xs" data-testid={`item-expected-${idx}`} />
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground">Received</label>
                        <GlassInput type="number" value={item.received_qty} onChange={e => updateItem(idx, 'received_qty', parseFloat(e.target.value) || 0)} className="h-8 text-xs" data-testid={`item-received-${idx}`} />
                      </div>
                      <div className="flex gap-1">
                        <div className="flex-1">
                          <label className="text-[10px] text-muted-foreground">Rejected</label>
                          <GlassInput type="number" value={item.rejected_qty} onChange={e => updateItem(idx, 'rejected_qty', parseFloat(e.target.value) || 0)} className="h-8 text-xs" data-testid={`item-rejected-${idx}`} />
                        </div>
                        {form.items.length > 1 && (
                          <button onClick={() => removeItem(idx)} className="text-red-700 dark:text-red-400 hover:text-red-600 dark:text-red-300 mt-3.5">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                      {/* FASE 6: alasan reject — qty reject otomatis masuk Karantina QC */}
                      {(parseFloat(item.rejected_qty) || 0) > 0 && (
                        <div className="col-span-2">
                          <label className="text-[10px] text-amber-700 dark:text-amber-400">
                            Alasan Reject — {item.rejected_qty} {item.unit} akan masuk <strong>Karantina QC</strong>
                          </label>
                          <SmartNativeSelect
                            value={item.reject_reason || ''}
                            onChange={e => updateItem(idx, 'reject_reason', e.target.value)}
                            className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-2 h-8 text-xs text-foreground"
                            data-testid={`item-reject-reason-${idx}`}
                          >
                            <option value="">— pilih alasan —</option>
                            {rejectCats.map(rc => <option key={rc.code} value={rc.code}>{rc.label}</option>)}
                          </SmartNativeSelect>
                        </div>
                      )}
                      {/* U7 — Lot & Expiry */}
                      <div>
                        <label className="text-[10px] text-muted-foreground">No. Lot / Batch</label>
                        <GlassInput
                          value={item.lot_number}
                          onChange={e => updateItem(idx, 'lot_number', e.target.value)}
                          placeholder="LOT-001"
                          className="h-8 text-xs"
                          data-testid={`receiving-lot-${idx}`}
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-muted-foreground">Tgl Kedaluwarsa</label>
                        <GlassInput
                          type="date"
                          value={item.expiry_date}
                          onChange={e => updateItem(idx, 'expiry_date', e.target.value)}
                          className="h-8 text-xs"
                          data-testid={`receiving-expiry-${idx}`}
                        />
                      </div>
                    </div>
                    {item.material_id && (
                      <p className="text-[10px] text-blue-600 dark:text-blue-400 flex items-center gap-1">
                        <Link2 className="w-3 h-3" /> Stok akan disinkronkan ke modul Inventory saat GR confirmed
                      </p>
                    )}
                    {/* ── FASE H-5: rincian gulungan untuk baris kain/benang ───────── */}
                    {isRollUnit(item.unit) && (
                      <RollLinesEditor
                        lines={item.rolls || []}
                        accepted={acceptedOf(item)}
                        unit={item.unit}
                        onChange={(lines) => updateItem(idx, 'rolls', lines)}
                        testPrefix={`gr-roll-lines-${idx}`}
                        nextNumberHint={rollPolicy?.next_number || ''}
                        subtitle={`Kain/benang dilacak per gulungan. Isi berat/panjang tiap gulungan — nomornya diterbitkan otomatis saat penerimaan dikonfirmasi. Total harus ${fmtQty(acceptedOf(item))} ${item.unit}.`}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Notes</label>
              <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-3 py-2 text-sm text-foreground h-16 resize-none placeholder:text-muted-foreground" placeholder="Optional notes..." />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowCreate(false)} className="border-[var(--glass-border)] text-muted-foreground hover:bg-[var(--glass-bg-hover)]">Batal</Button>
              <Button onClick={handleCreate} className="bg-primary text-primary-foreground hover:brightness-110" data-testid="submit-receipt-btn">Create Receipt</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && (
        <Modal title={`Receipt ${showDetail.receipt_number}`} onClose={() => setShowDetail(null)} size="lg">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div><p className="text-xs text-muted-foreground">Source</p><p className="text-sm font-medium text-foreground">{showDetail.supplier_name || showDetail.source_type}</p></div>
              <div><p className="text-xs text-muted-foreground">Reference</p><p className="text-sm font-medium text-foreground">{showDetail.source_ref || '-'}</p></div>
              <div><p className="text-xs text-muted-foreground">Location</p><p className="text-sm font-medium text-foreground">{showDetail.location_name || '-'}</p></div>
              <div><p className="text-xs text-muted-foreground">Status</p><span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${STATUS_STYLES[showDetail.status]}`}>{showDetail.status}</span></div>
            </div>

            <div className="border-t border-[var(--glass-border)] pt-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">Items ({showDetail.items?.length || 0})</p>
              {/* FASE 6: banner karantina bila ada qty reject yang ditahan */}
              {showDetail.quarantine_summary?.total_qty > 0 && (
                <div className="mb-3 rounded-xl border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10 px-3 py-2 flex items-start justify-between gap-3"
                  data-testid="gr-quarantine-banner">
                  <div className="text-xs text-amber-800 dark:text-amber-300">
                    <strong>{showDetail.quarantine_summary.total_qty} unit reject</strong> ditahan di{' '}
                    {showDetail.quarantine_summary.location?.name || 'Karantina QC'} — stok diblokir sampai ada keputusan
                    (lepas ke stok / retur supplier / scrap).
                  </div>
                  {onNavigate && (
                    <button onClick={() => { setShowDetail(null); onNavigate('wh-quarantine'); }}
                      className="shrink-0 text-xs px-2.5 py-1 rounded-lg bg-amber-600 text-white hover:brightness-110"
                      data-testid="gr-open-quarantine">
                      Buka Karantina QC →
                    </button>
                  )}
                </div>
              )}
              <div className="space-y-2">
                {(detailItems.length ? detailItems : (showDetail.items || [])).map((item, idx) => (
                  <div key={idx} className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <p className="text-sm font-medium text-foreground">{item.product_name}</p>
                          {item.material_id && (
                            <span className="text-[10px] text-blue-600 dark:text-blue-400 flex items-center gap-0.5 bg-blue-50 dark:bg-blue-400/10 px-1.5 py-0.5 rounded-full border border-blue-300 dark:border-blue-400/20">
                              <Link2 className="w-2.5 h-2.5" /> linked
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground font-mono">{item.sku}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-foreground">Received: <strong>{item.received_qty}</strong> / {item.expected_qty} {item.unit}</p>
                        {item.rejected_qty > 0 && <p className="text-xs text-red-700 dark:text-red-400">Rejected: {item.rejected_qty}</p>}
                        {item.quarantined_qty > 0 && (
                          <p className="text-xs text-amber-700 dark:text-amber-400">→ Karantina QC: {item.quarantined_qty} {item.unit}</p>
                        )}
                        {item.material_id && showDetail.status === 'received' && (
                          <p className="text-xs text-emerald-600 dark:text-emerald-400 flex items-center justify-end gap-1">
                            <CheckCircle className="w-3 h-3" /> stok ter-sync
                          </p>
                        )}
                      </div>
                    </div>

                    {/* ── QTY DITERIMA / DITOLAK — HARUS BISA DIISI DI SINI ──────────
                        Cacat yang ditutup blok ini (dilaporkan pemilik, terbukti pada
                        GR-00001: `expected_qty=100` tetapi `received_qty=0` walau
                        statusnya sudah `received`):

                        GR yang lahir dari PO (`created_from='po'`) SELALU dibuat
                        dengan `received_qty: 0.0` (rahaza_po.py) — memang benar,
                        karena barangnya belum dihitung. Tetapi satu-satunya layar
                        untuk memprosesnya adalah modal ini, dan di sini qty hanya
                        DITAMPILKAN sebagai teks. Tidak ada kolom isian sama sekali.
                        Akibatnya petugas gudang hanya bisa menekan "Confirm
                        Received", yang mengkonfirmasi angka NOL ⇒ pembelian tidak
                        pernah menambah stok. Form "New Receipt" punya kolomnya,
                        tetapi GR dari PO tidak pernah melewati form itu.

                        Backend sudah menerima item yang disunting di layar ini
                        (`PUT /receiving/{id}` body `{status, items}`) — jadi yang
                        hilang benar-benar hanya kolomnya. */}
                    {showDetail.status === 'draft' && (
                      <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] p-2.5"
                        data-testid={`gr-detail-qty-${idx}`}>
                        <div className="grid grid-cols-3 gap-2 items-end">
                          <div>
                            <label className="text-[10px] text-muted-foreground">Diharap (PO)</label>
                            <p className="h-8 flex items-center text-sm font-semibold tabular-nums">
                              {fmtQty(item.expected_qty)} <span className="ml-1 text-[10px] font-normal text-muted-foreground">{item.unit}</span>
                            </p>
                          </div>
                          <div>
                            <label className="text-[10px] text-emerald-700 dark:text-emerald-400 font-semibold">
                              Qty Diterima *
                            </label>
                            <GlassInput
                              type="number" min="0" step="any"
                              value={item.received_qty ?? 0}
                              onChange={e => updateDetailItem(idx, { received_qty: parseFloat(e.target.value) || 0 })}
                              className="h-8 text-xs"
                              data-testid={`gr-detail-received-${idx}`}
                            />
                          </div>
                          <div>
                            <label className="text-[10px] text-muted-foreground">Qty Ditolak</label>
                            <GlassInput
                              type="number" min="0" step="any"
                              value={item.rejected_qty ?? 0}
                              onChange={e => updateDetailItem(idx, { rejected_qty: parseFloat(e.target.value) || 0 })}
                              className="h-8 text-xs"
                              data-testid={`gr-detail-rejected-${idx}`}
                            />
                          </div>
                        </div>
                        {/* Anti over-receive: backend menolaknya (HTTP 400); dikatakan
                            di sini supaya penolakan bukan kejutan setelah diklik. */}
                        {showDetail.enforce_po_qty
                          && acceptedOf(item) - Number(item.expected_qty || 0) > 0.0001 && (
                          <p className="text-[11px] text-red-700 dark:text-red-400 mt-1.5"
                            data-testid={`gr-detail-over-${idx}`}>
                            Netto diterima {fmtQty(acceptedOf(item))} {item.unit} melebihi sisa PO
                            {' '}{fmtQty(item.expected_qty)} {item.unit} — penerimaan akan ditolak.
                          </p>
                        )}
                        {(parseFloat(item.rejected_qty) || 0) > 0 && (
                          <div className="mt-1.5">
                            <label className="text-[10px] text-amber-700 dark:text-amber-400">
                              Alasan Reject — {item.rejected_qty} {item.unit} akan masuk <strong>Karantina QC</strong>
                            </label>
                            <SmartNativeSelect
                              value={item.reject_reason || ''}
                              onChange={e => updateDetailItem(idx, { reject_reason: e.target.value })}
                              className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-2 h-8 text-xs text-foreground"
                              data-testid={`gr-detail-reject-reason-${idx}`}
                            >
                              <option value="">— pilih alasan —</option>
                              {rejectCats.map(rc => <option key={rc.code} value={rc.code}>{rc.label}</option>)}
                            </SmartNativeSelect>
                          </div>
                        )}
                      </div>
                    )}
                    {/* ── FASE H-5: gulungan kain per baris ────────────────────────── */}
                    {isRollUnit(item.unit) && showDetail.status !== 'received' && (
                      <RollLinesEditor
                        lines={item.rolls || []}
                        accepted={acceptedOf(item)}
                        unit={item.unit}
                        onChange={(lines) => updateDetailItem(idx, { rolls: lines })}
                        testPrefix={`gr-detail-roll-lines-${idx}`}
                        nextNumberHint={rollPolicy?.next_number || ''}
                        title="Rincian Gulungan (isi sebelum konfirmasi)"
                        subtitle={`Timbang/ukur tiap gulungan sekarang. Nomor roll otomatis. Total harus ${fmtQty(acceptedOf(item))} ${item.unit} — kalau dilewati, kain masuk daftar "Penerimaan tanpa roll" dan Cutting akan menolak memotongnya.`}
                      />
                    )}
                    {(item.roll_numbers || []).length > 0 && (
                      <div className="rounded-lg border border-violet-300 dark:border-violet-400/30 bg-violet-50 dark:bg-violet-400/10 px-2.5 py-2"
                        data-testid={`gr-item-rolls-${idx}`}>
                        <p className="text-[11px] font-semibold text-violet-800 dark:text-violet-200 mb-1">
                          {item.roll_numbers.length} gulungan terbit dari baris ini
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {item.roll_numbers.map((no) => (
                            <span key={no} className="font-mono text-[10px] px-1.5 py-0.5 rounded-md bg-violet-600 text-white">{no}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {showDetail.status === 'received' && isRollUnit(item.unit)
                      && !(item.roll_numbers || []).length && acceptedOf(item) > 0 && (
                      <div className="rounded-lg border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10 px-2.5 py-2 flex items-start justify-between gap-3"
                        data-testid={`gr-item-rolls-missing-${idx}`}>
                        <p className="text-[11px] text-amber-800 dark:text-amber-300">
                          <strong>{fmtQty(acceptedOf(item))} {item.unit} masuk stok tanpa gulungan.</strong> Cutting menolak
                          memotong kain yang tidak punya gulungan — terbitkan gulungannya di Roll Kain.
                        </p>
                        {onNavigate && (
                          <button onClick={() => { setShowDetail(null); onNavigate('wms-fabric-rolls'); }}
                            className="shrink-0 text-[11px] px-2.5 py-1 rounded-lg bg-amber-600 text-white hover:brightness-110"
                            data-testid={`gr-open-fabric-rolls-${idx}`}>
                            Terbitkan Roll →
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {showDetail.status === 'draft' && (
              <div className="pt-2 border-t border-[var(--glass-border)] space-y-2">
                {/* LOKASI TUJUAN — GR yang lahir dari PO dibuat tanpa lokasi
                    (`location_id: ""`), dan dulu modal ini tidak menyediakan
                    pemilihnya. Akibatnya stok yang masuk mendarat di baris
                    berlokasi KOSONG: barangnya ada di sistem tetapi tidak ada di
                    rak mana pun, sehingga Put-Away & pencarian posisi tidak bisa
                    menemukannya. Lokasi ditanyakan DI SINI karena inilah saat
                    barangnya benar-benar diletakkan. */}
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    Lokasi Tujuan {!(detailLocationId || showDetail.location_id) && (
                      <span className="text-amber-700 dark:text-amber-400">— wajib dipilih</span>
                    )}
                  </label>
                  <Combobox
                    value={detailLocationId || showDetail.location_id || ''}
                    onChange={setDetailLocationId}
                    options={locations.map(l => ({
                      value: l.id,
                      label: `${l.code} - ${l.name}`,
                      testId: `gr-detail-location-option-${l.code}`,
                    }))}
                    placeholder="Pilih lokasi penyimpanan..."
                    searchPlaceholder="Cari lokasi..."
                    emptyMessage="Lokasi tidak ditemukan"
                    data-testid="gr-detail-location-select"
                  />
                </div>
                {/* Jalan cepat untuk kasus paling umum: barang datang lengkap
                    sesuai PO. Tanpa ini petugas harus mengetik ulang tiap baris,
                    dan yang paling sering terjadi adalah ia menekan Confirm tanpa
                    mengisi apa pun (itulah cacat yang diperbaiki). */}
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" className="border-emerald-300 dark:border-emerald-300/30 text-emerald-700 dark:text-emerald-300"
                    onClick={() => setDetailItems(items => (items.length ? items : (showDetail.items || []))
                      .map(it => ({ ...it, received_qty: Number(it.expected_qty || 0), rejected_qty: 0 })))}
                    data-testid="gr-detail-receive-all">
                    Terima semua sesuai PO
                  </Button>
                  <span className="text-xs text-muted-foreground" data-testid="gr-detail-total">
                    Total diterima:{' '}
                    <strong className="text-foreground tabular-nums">{fmtQty(detailTotals.received)}</strong>
                    {detailTotals.rejected > 0 && (
                      <> · ditolak <strong className="text-red-700 dark:text-red-400 tabular-nums">{fmtQty(detailTotals.rejected)}</strong></>
                    )}
                    {' '}dari {fmtQty(detailTotals.expected)} diharap
                  </span>
                </div>
                {detailTotals.touched <= 0 && (
                  <p className="text-xs text-amber-800 dark:text-amber-300 rounded-lg border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10 px-2.5 py-2"
                    data-testid="gr-detail-zero-warning">
                    <strong>Qty diterima masih 0.</strong> Isi dulu jumlah yang benar-benar
                    datang — mengkonfirmasi angka 0 berarti penerimaan tercatat tetapi
                    <strong> stok tidak bertambah sama sekali</strong>.
                  </p>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => { setConfirmDelete(showDetail.id); setShowDetail(null); }} className="border-red-300 dark:border-red-300/20 text-red-700 dark:text-red-400 hover:bg-red-50 dark:bg-red-400/10">
                    <Trash2 className="w-4 h-4 mr-1" /> Delete
                  </Button>
                  <Button onClick={() => handleStatusChange(showDetail, 'received')}
                    disabled={detailTotals.touched <= 0}
                    className="bg-emerald-500 text-foreground hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
                    data-testid="confirm-receive-btn">
                    <CheckCircle className="w-4 h-4 mr-1" /> Confirm Received
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog title="Delete Receipt?" message="GR draft ini akan dihapus permanen." onConfirm={() => handleDelete(confirmDelete)} onCancel={() => setConfirmDelete(null)} />
      )}

      {/* ── FASE H-5: hasil penerbitan gulungan setelah GR dikonfirmasi ────────── */}
      {receiveResult && (
        <Modal title={`Gulungan — ${receiveResult.receipt_number}`} onClose={() => setReceiveResult(null)} size="md">
          <div className="space-y-3" data-testid="gr-roll-result">
            {receiveResult.created.length > 0 && (
              <div className="rounded-xl border border-emerald-300 dark:border-emerald-400/30 bg-emerald-50 dark:bg-emerald-400/10 p-3">
                <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200 mb-1.5">
                  {receiveResult.created.length} gulungan diterbitkan otomatis
                </p>
                <div className="flex flex-wrap gap-1">
                  {receiveResult.created.map((no) => (
                    <span key={no} className="font-mono text-[11px] px-1.5 py-0.5 rounded-md bg-emerald-600 text-white">{no}</span>
                  ))}
                </div>
                <p className="text-[11px] text-emerald-800/80 dark:text-emerald-300/80 mt-2">
                  Gulungan ini sudah bisa ditunjuk di Portal Cutting — sisa tiap gulungan berkurang saat kainnya dipotong.
                </p>
              </div>
            )}
            {receiveResult.pending.length > 0 && (
              <div className="rounded-xl border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10 p-3">
                <p className="text-sm font-semibold text-amber-800 dark:text-amber-200 mb-1.5">
                  {receiveResult.pending.length} baris kain masuk stok TANPA gulungan
                </p>
                <ul className="text-xs text-amber-800 dark:text-amber-300 space-y-1">
                  {receiveResult.pending.map((p) => (
                    <li key={p.item_id} className="font-mono">
                      {p.material_code} — {fmtQty(p.accepted_qty)} {p.unit}
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] text-amber-800/80 dark:text-amber-300/80 mt-2">
                  Cutting akan MENOLAK memotong kain tanpa gulungan. Terbitkan gulungannya di
                  Gudang → Roll Kain → tab “Penerimaan tanpa roll”.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setReceiveResult(null)}
                className="border-[var(--glass-border)] text-muted-foreground">Tutup</Button>
              {onNavigate && receiveResult.pending.length > 0 && (
                <Button onClick={() => { setReceiveResult(null); onNavigate('wms-fabric-rolls'); }}
                  className="bg-amber-600 text-white hover:brightness-110" data-testid="gr-result-goto-rolls">
                  Buka Roll Kain →
                </Button>
              )}
              {onNavigate && receiveResult.pending.length === 0 && receiveResult.created.length > 0 && (
                <Button onClick={() => { setReceiveResult(null); onNavigate('wms-fabric-rolls'); }}
                  className="bg-violet-600 text-white hover:brightness-110" data-testid="gr-result-view-rolls">
                  Lihat Roll Kain →
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
