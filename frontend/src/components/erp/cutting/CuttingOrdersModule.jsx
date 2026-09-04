/**
 * CuttingOrdersModule — pintu utama Portal Cutting.
 *
 * Satu layar, tiga pekerjaan:
 *   1. Daftar order cutting + filter status/pencarian
 *   2. Buat cutting (pilih kain dari master material, opsional pilih roll fisik)
 *   3. Detail: input progres berulang, selesaikan, batalkan
 *
 * Semua mutasi stok terjadi di backend lewat SSOT gudang — UI hanya melaporkan
 * hasilnya (stok kain turun, stok potongan naik) supaya user melihat efeknya.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Scissors, Plus, RefreshCw, Search, PlayCircle, CheckCircle2, XCircle,
  Trash2, Package, ArrowRight, Layers, AlertCircle, Loader2, History,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import Modal from '../Modal';
import { cuttingApi, StatusPill, fmtNum, fmtRp, fmtDateTime } from './cuttingApi';
import useUomOptions from '../../../hooks/useUomOptions';
import { UomSelect, UomConversionHint } from '../uom/UomPicker';
// FASE H-6 — gulungan WAJIB ditunjuk saat memotong kain yang punya gulungan.
import { previewAllocation, fmtQty } from '../warehouse/rollLines';

const EMPTY_FORM = {
  input_material_id: '',
  location_id: '',
  planned_input_qty: '',
  planned_output_qty: '',
  // Identitas produk DARI MASTER — `style_name`/`style_sku` hanya cerminan model
  // yang dipilih (tidak lagi diketik pemakai).
  model_id: '',
  variant_id: '',
  size_id: '',
  style_name: '',
  style_sku: '',
  output_color: '',
  output_size: '',
  notes: '',
  roll_ids: [],
};

function Field({ label, children, hint, required }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-foreground/80">
        {label} {required && <span className="text-red-500">*</span>}
      </span>
      <div className="mt-1">{children}</div>
      {hint && <span className="text-[11px] text-muted-foreground mt-1 block">{hint}</span>}
    </label>
  );
}

/** Angka pemakaian bahan: tampilkan apa adanya tanpa nol berekor ("6" bukan "6,0000"). */
const fmtQtyTrim = (v) =>
  Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 });

const inputCls =
  'w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.35)]';

export default function CuttingOrdersModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [materials, setMaterials] = useState([]);
  const [locations, setLocations] = useState([]);
  const [onlyInStock, setOnlyInStock] = useState(true);
  const [rolls, setRolls] = useState([]);
  const [rollMeta, setRollMeta] = useState({ roll_required: false, total_remaining: 0, uom: '' });
  const [saving, setSaving] = useState(false);
  // Master produk (model + varian) — sumber identitas potongan.
  const [models, setModels] = useState([]);
  const [variants, setVariants] = useState([]);
  const [showNewModel, setShowNewModel] = useState(false);
  const [newModel, setNewModel] = useState({ code: '', name: '' });
  const [savingModel, setSavingModel] = useState(false);
  // 2026-08-23 — KEBUTUHAN BAHAN DARI BOM. Sebelum ini "Rencana Pemakaian Kain"
  // diketik manual (ditebak) walau BOM per model+size sudah menyimpan kebutuhan
  // per pcs. Kartu ini membacanya dari BOM dan menyediakan tombol "Pakai angka
  // BOM"; kalau BOM/satuan/kain-nya tidak cocok, alasannya DIKATAKAN.
  const [bomReq, setBomReq] = useState(null);
  const [bomLoading, setBomLoading] = useState(false);
  // Ukuran untuk model yang BOM-nya sudah ada tetapi variannya belum didaftarkan
  // (kalau tidak disediakan, ukuran itu mustahil dipilih ⇒ BOM tidak terpakai).
  const [sizes, setSizes] = useState([]);
  const [sizeId, setSizeId] = useState('');

  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [prog, setProg] = useState({ input_consumed: '', output_qty: '', waste_qty: '', note: '', roll_id: '', input_uom: '', roll_ids: [] });
  const [acting, setActing] = useState(false);
  // FASE H-6: gulungan yang masih bersisa untuk kain order ini (dimuat saat detail
  // dibuka). `rollRequired` datang dari server — layar tidak menebak sendiri.
  const [detailRolls, setDetailRolls] = useState({ items: [], roll_required: false, total_remaining: 0, uom: '' });

  // ── FASE H-6b (2026-08-17) — progres yang kainnya sudah keluar tetapi BELUM
  // punya dokumen "Pengeluaran Material". Ini keadaan data LAMA (sebelum H-6b)
  // atau sisa kegagalan penerbitan dokumen. Ditampilkan supaya tidak ada arus
  // keluar yang hilang dari daftar gudang, dan bisa diterbitkan sekali klik.
  const [miMissing, setMiMissing] = useState({ items: [], count: 0 });
  const [miFixing, setMiFixing] = useState(false);

  // ROADMAP P1 (2026-08-05) — operator lantai boleh mencatat pemakaian kain
  // dalam satuan lain (rol/gram/yard); server menerjemahkan ke satuan order.
  const { options: uomOpts } = useUomOptions(detail?.input_material_id ? [detail.input_material_id] : []);
  const progUomOpt = detail?.input_material_id ? uomOpts[detail.input_material_id] : null;
  const orderUnit = String(detail?.input_unit || '').toLowerCase();
  const effProgUom = prog.input_uom || orderUnit;

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr('');
    try {
      const qs = new URLSearchParams();
      if (status) qs.set('status', status);
      if (q) qs.set('q', q);
      setRows(await cuttingApi('GET', `/orders${qs.toString() ? `?${qs}` : ''}`, token));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, status, q]);

  useEffect(() => { load(); }, [load]);

  // FASE H-6b — dimuat bersamaan dengan daftar order.
  const loadMiMissing = useCallback(async () => {
    if (!token) return;
    try {
      setMiMissing(await cuttingApi('GET', '/issue-docs/missing?limit=200', token));
    } catch {
      setMiMissing({ items: [], count: 0 });
    }
  }, [token]);

  useEffect(() => { loadMiMissing(); }, [loadMiMissing]);

  const backfillMiDocs = async () => {
    setMiFixing(true);
    try {
      const res = await cuttingApi('POST', '/issue-docs/backfill', token, { limit: 500 });
      const n = res?.created || 0;
      if (n > 0) {
        toast.success(`${n} dokumen Pengeluaran Material diterbitkan — arus keluar kain kini tampil di layar Gudang.`);
      } else {
        toast.info('Tidak ada progres yang perlu dokumen baru.');
      }
      if ((res?.failed || []).length) {
        toast.error(`${res.failed.length} progres gagal: ${res.failed[0]?.error || ''}`);
      }
      await loadMiMissing();
      await load();
    } catch (e) {
      toast.error(`Gagal menerbitkan dokumen: ${e.message}`);
    } finally {
      setMiFixing(false);
    }
  };

  const openCreate = async () => {
    setForm(EMPTY_FORM);
    setRolls([]);
    setVariants([]);
    setSizeId('');
    setBomReq(null);
    setShowCreate(true);
    try {
      const [mats, locs] = await Promise.all([
        cuttingApi('GET', '/input-materials', token),
        cuttingApi('GET', '/locations', token),
      ]);
      setMaterials(mats);
      setLocations(locs);
    } catch (e) {
      toast.error(`Gagal memuat master kain: ${e.message}`);
    }
    await loadModels();
  };

  const loadModels = async () => {
    try {
      const r = await fetch('/api/rahaza/models', {
        headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
      });
      const d = await r.json();
      const list = Array.isArray(d) ? d : (d?.items || []);
      setModels(list.filter((m) => m.active !== false));
    } catch {
      setModels([]);
    }
  };

  const onPickModel = async (id) => {
    const m = models.find((x) => x.id === id) || null;
    setForm((f) => ({
      ...f,
      model_id: id,
      variant_id: '',
      size_id: '',
      style_name: m?.name || '',
      style_sku: m?.code || '',
      output_color: '',
      output_size: '',
    }));
    setVariants([]);
    setSizeId('');
    if (!id) return;
    try {
      const r = await fetch(`/api/rahaza/models/${id}/variants`, {
        headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
      });
      const d = await r.json();
      setVariants((Array.isArray(d) ? d : (d?.items || [])).filter((v) => v.active !== false));
    } catch {
      setVariants([]);
    }
  };

  const onPickVariant = (vid) => {
    const v = variants.find((x) => x.id === vid) || null;
    setForm((f) => ({
      ...f,
      variant_id: vid,
      output_color: v?.color_name || v?.color || '',
      output_size: v?.size_code || v?.size || '',
    }));
  };

  // ── Kebutuhan bahan menurut BOM (model + ukuran) ─────────────────────────
  // Dimuat ulang setiap kali model/varian/kain/target pcs berubah supaya angka
  // yang ditawarkan selalu milik kombinasi yang sedang dipilih.
  useEffect(() => {
    if (!showCreate || !form.model_id) { setBomReq(null); return; }
    const variant = variants.find((x) => x.id === form.variant_id) || null;
    const effSizeId = variant?.size_id || sizeId || '';
    let alive = true;
    const t = setTimeout(async () => {
      setBomLoading(true);
      try {
        const p = new URLSearchParams({ model_id: form.model_id });
        if (effSizeId) p.set('size_id', effSizeId);
        if (form.variant_id) p.set('variant_id', form.variant_id);
        if (form.planned_output_qty) p.set('qty_pcs', String(form.planned_output_qty));
        if (form.input_material_id) p.set('input_material_id', form.input_material_id);
        const d = await cuttingApi('GET', `/bom-requirement?${p}`, token);
        if (alive) setBomReq(d);
      } catch {
        if (alive) setBomReq(null);
      } finally {
        if (alive) setBomLoading(false);
      }
    }, 250);
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showCreate, form.model_id, form.variant_id, form.planned_output_qty,
      form.input_material_id, variants, sizeId, token]);

  // Master ukuran (dipakai saat model belum punya varian).
  useEffect(() => {
    if (!showCreate || sizes.length) return;
    (async () => {
      try {
        const r = await fetch('/api/rahaza/sizes', {
          headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
        });
        const d = await r.json();
        setSizes((Array.isArray(d) ? d : (d?.items || [])).filter((s) => s.active !== false));
      } catch { setSizes([]); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showCreate]);

  const pickSize = (sid) => {
    setSizeId(sid);
    const s = sizes.find((x) => x.id === sid);
    setForm((f) => ({ ...f, size_id: sid, output_size: s?.code || '' }));
  };

  // SESI #32 — ukuran mana yang SUDAH punya BOM, ditandai LANGSUNG di daftar
  // pilihan. Sebelumnya keterangan itu hanya muncul sebagai kalimat di bawah
  // kartu ("Ukuran yang SUDAH punya BOM: ALLSIZE"), jadi admin cutting tetap
  // memilih ukuran secara buta lalu baru tahu BOM-nya kosong sesudah memilih.
  const sizesWithBom = useMemo(() => {
    const s = new Set();
    (bomReq?.other_sizes_with_bom || []).forEach((x) => {
      if (x?.size_id) s.add(x.size_id);
    });
    if (bomReq?.has_bom && (bomReq?.size_id || sizeId)) s.add(bomReq?.size_id || sizeId);
    return s;
  }, [bomReq, sizeId]);

  const useBomQty = () => {
    const q = Number(bomReq?.fabric?.qty_total || 0);
    if (!(q > 0)) {
      toast.error('Angka BOM belum bisa dipakai — isi target potongan (pcs) dulu.');
      return;
    }
    setForm((f) => ({ ...f, planned_input_qty: String(q) }));
    toast.success(`Rencana pemakaian kain diisi dari BOM: ${fmtQtyTrim(q)} ${bomReq.fabric.unit}.`);
  };

  const createModel = async () => {
    if (!newModel.name.trim()) return toast.error('Nama model wajib diisi.');
    setSavingModel(true);
    try {
      const r = await fetch('/api/rahaza/models', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newModel.name.trim(), code: newModel.code.trim() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || d.error || `HTTP ${r.status}`);
      toast.success(`Model ${d.code || d.name} ditambahkan ke master.`);
      setShowNewModel(false);
      setNewModel({ code: '', name: '' });
      await loadModels();
      setModels((prev) => (prev.some((x) => x.id === d.id) ? prev : [...prev, d]));
      await onPickModel(d.id);
    } catch (e) {
      toast.error(`Gagal membuat model: ${e.message}`);
    } finally {
      setSavingModel(false);
    }
  };

  const selectedMaterial = useMemo(
    () => materials.find((m) => m.id === form.input_material_id) || null,
    [materials, form.input_material_id],
  );

  // Stok disimpan PER GUDANG. Dropdown kain menampilkan lokasi yang benar-benar
  // memegang stok agar user tidak membuat cutting di gudang yang kosong
  // (penyebab kegagalan "stok tidak cukup" saat input progres).
  const materialOptions = useMemo(() => {
    const list = onlyInStock ? materials.filter((m) => Number(m.stock_qty || 0) > 0) : materials;
    return list;
  }, [materials, onlyInStock]);

  const onPickMaterial = async (id) => {
    const m = materials.find((x) => x.id === id);
    setForm((f) => ({
      ...f,
      input_material_id: id,
      location_id: m?.best_location_id || '',
      roll_ids: [],
    }));
    setRolls([]);
    setRollMeta({ roll_required: false, total_remaining: 0, uom: '' });
    if (!id) return;
    try {
      // FASE H-6: respons kini objek ({items, roll_required, total_remaining, uom})
      // supaya layar tahu apakah gulungan WAJIB dan berapa sisa totalnya.
      const res = await cuttingApi('GET', `/rolls?material_id=${id}`, token);
      const items = Array.isArray(res) ? res : (res?.items || []);
      setRolls(items);
      setRollMeta({
        roll_required: !!res?.roll_required,
        total_remaining: Number(res?.total_remaining || 0),
        uom: res?.uom || items[0]?.uom || '',
      });
    } catch {
      setRolls([]);
      setRollMeta({ roll_required: false, total_remaining: 0, uom: '' });
    }
  };

  const stockAtLocation = useMemo(() => {
    if (!selectedMaterial) return null;
    const loc = (selectedMaterial.stock_locations || []).find((l) => l.location_id === form.location_id);
    return loc ? loc.qty : 0;
  }, [selectedMaterial, form.location_id]);

  const submitCreate = async (e) => {
    e.preventDefault();
    if (!form.input_material_id) return toast.error('Pilih material kain dulu.');
    if (!form.model_id) return toast.error('Pilih Model/Style dari Master Produk dulu.');
    if (!(Number(form.planned_input_qty) > 0)) return toast.error('Rencana pemakaian kain harus > 0.');
    if (!(Number(form.planned_output_qty) > 0)) return toast.error('Target potongan harus > 0.');
    setSaving(true);
    try {
      const created = await cuttingApi('POST', '/orders', token, {
        ...form,
        planned_input_qty: Number(form.planned_input_qty),
        planned_output_qty: Number(form.planned_output_qty),
      });
      toast.success(`Cutting ${created.number} dibuat (draft).`);
      setShowCreate(false);
      await load();
      openDetail(created.id);
    } catch (e2) {
      toast.error(e2.message);
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (id) => {
    setDetailLoading(true);
    setProg({ input_consumed: '', output_qty: '', waste_qty: '', note: '', roll_id: '', input_uom: '', roll_ids: [] });
    setDetailRolls({ items: [], roll_required: false, total_remaining: 0, uom: '' });
    try {
      const d = await cuttingApi('GET', `/orders/${id}`, token);
      setDetail(d);
      await loadDetailRolls(d);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  // FASE H-6: gulungan yang bisa dipotong untuk order ini. Dimuat setiap kali
  // detail dibuka/diperbarui supaya sisa tiap gulungan yang tampil = sisa nyata.
  const loadDetailRolls = useCallback(async (order) => {
    if (!order?.input_material_id) return;
    try {
      const res = await cuttingApi('GET', `/rolls?material_id=${order.input_material_id}`, token);
      const items = Array.isArray(res) ? res : (res?.items || []);
      setDetailRolls({
        items,
        roll_required: !!res?.roll_required,
        total_remaining: Number(res?.total_remaining || 0),
        uom: res?.uom || items[0]?.uom || '',
      });
    } catch {
      setDetailRolls({ items: [], roll_required: false, total_remaining: 0, uom: '' });
    }
  }, [token]);

  const refreshDetail = async (id) => {
    try {
      const d = await cuttingApi('GET', `/orders/${id}`, token);
      setDetail(d);
      await loadDetailRolls(d);
    } catch { /* ignore */ }
    load();
  };

  const doAction = async (path, body, okMsg) => {
    if (!detail) return;
    setActing(true);
    try {
      const res = await cuttingApi('POST', `/orders/${detail.id}${path}`, token, body);
      toast.success(okMsg);
      if (res?.notice) toast.info(res.notice, { duration: 6000 });
      // SESI #32 — kain SUDAH terpotong tetapi nilainya belum bisa dihitung
      // (harga kain 0). Ini bukan info biasa: nilai persediaan potongan akan
      // 0 sampai harga kainnya lahir dari pembelian, jadi ditampilkan sebagai
      // PERINGATAN yang bertahan lebih lama.
      if (res?.value_warning) toast.warning(res.value_warning, { duration: 12000 });
      await refreshDetail(detail.id);
    } catch (e) {
      toast.error(e.message, { duration: 8000 });
    } finally {
      setActing(false);
    }
  };

  // FASE H-6: rencana pemakaian gulungan (FIFO) dihitung di layar supaya operator
  // melihat "gulungan mana dipakai berapa" SEBELUM menekan Catat — cermin dari
  // `fabric_roll_engine.allocate()` di server.
  const pickedRolls = useMemo(
    () => detailRolls.items.filter((r) => (prog.roll_ids || []).includes(r.id)),
    [detailRolls.items, prog.roll_ids],
  );
  const consumedInOrderUnit = useMemo(() => {
    const q = Number(prog.input_consumed || 0);
    if (!q) return 0;
    // konversi satuan operator ditangani server; pratinjau memakai angka apa adanya
    return q;
  }, [prog.input_consumed]);
  const allocPreview = useMemo(
    () => previewAllocation(pickedRolls, consumedInOrderUnit),
    [pickedRolls, consumedInOrderUnit],
  );
  const rollBlocking = detailRolls.roll_required && (prog.roll_ids || []).length === 0;

  const toggleProgRoll = (id) => setProg((p) => {
    const has = (p.roll_ids || []).includes(id);
    return { ...p, roll_ids: has ? p.roll_ids.filter((x) => x !== id) : [...(p.roll_ids || []), id] };
  });

  const submitProgress = async (e) => {
    e.preventDefault();
    if (!(Number(prog.input_consumed) > 0)) return toast.error('Kain terpakai harus > 0.');
    if (!(Number(prog.output_qty) > 0)) return toast.error('Jumlah potongan jadi harus > 0.');
    if (rollBlocking) {
      return toast.error(
        'Pilih gulungan yang dipotong dulu — tanpa itu sisa gulungan di sistem akan menyimpang '
        + 'dari kenyataan dan lot kain tidak bisa dipertanggungjawabkan ke buyer.',
        { duration: 8000 });
    }
    setActing(true);
    try {
      const res = await cuttingApi('POST', `/orders/${detail.id}/progress`, token, {
        input_consumed: Number(prog.input_consumed),
        output_qty: Number(prog.output_qty),
        waste_qty: Number(prog.waste_qty || 0),
        note: prog.note,
        roll_ids: (prog.roll_ids || []).length ? prog.roll_ids : undefined,
        roll_id: prog.roll_id || undefined,
        input_uom: (effProgUom && effProgUom !== orderUnit) ? effProgUom : undefined,
      });
      toast.success('Progres tercatat — stok gudang sudah diperbarui.');
      // FASE H-6b — beri tahu nomor dokumen arus keluarnya (atau peringatkan kalau
      // dokumen gagal terbit; stok TETAP sudah berkurang, jadi ini harus terlihat).
      const miNo = res?.last_progress?.material_issue_number;
      if (miNo) {
        toast.info(`Dokumen Pengeluaran Material ${miNo} diterbitkan — arus keluar kain tampil di layar Gudang.`,
          { duration: 8000 });
      } else if (res?.mi_warning) {
        toast.error(res.mi_warning, { duration: 12000 });
      }
      const used = res?.last_progress?.roll_consumption || [];
      if (used.length) {
        toast.info(
          'Gulungan dipakai: ' + used.map((u) => `${u.roll_no} −${fmtQty(u.qty)} (sisa ${fmtQty(u.remaining_after)})`).join(' · '),
          { duration: 9000 });
      }
      // SESI #32 — NILAI yang berpindah dari kain ke potongan. Kalau kainnya
      // belum bernilai, ini jadi PERINGATAN (bukan info) karena nilai persediaan
      // potongan akan 0 sampai harga kainnya lahir dari pembelian.
      const lp = res?.last_progress || {};
      if (lp.value_status === 'valued' && Number(lp.value_out) > 0) {
        toast.info(
          `Nilai kain keluar ${fmtRp(lp.value_out)} → HPP potongan ${fmtRp(lp.panel_unit_cost_after)}/pcs`
          + (Number(lp.panel_unit_cost_before) > 0
            ? ` (dari ${fmtRp(lp.panel_unit_cost_before)}, rata-rata bergerak)` : ''),
          { duration: 9000 });
      } else if (res?.value_warning) {
        toast.warning(res.value_warning, { duration: 12000 });
      }
      setProg({ input_consumed: '', output_qty: '', waste_qty: '', note: '', roll_id: '', input_uom: '', roll_ids: [] });
      await refreshDetail(detail.id);
      await loadMiMissing();
    } catch (e2) {
      toast.error(e2.message, { duration: 9000 });
    } finally {
      setActing(false);
    }
  };

  const removeDraft = async (row) => {
    if (!window.confirm(`Hapus draft ${row.number}?`)) return;
    try {
      await cuttingApi('DELETE', `/orders/${row.id}`, token);
      toast.success('Draft dihapus.');
      if (detail?.id === row.id) setDetail(null);
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div className="space-y-5" data-testid="cutting-orders-module">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-orange-500/12 border border-orange-500/25 grid place-items-center">
            <Scissors className="w-5 h-5 text-orange-600 dark:text-orange-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-foreground">Order Cutting</h2>
            <p className="text-sm text-muted-foreground">
              Ubah roll kain menjadi kain pola (potongan) — hasilnya jadi material untuk BOM produksi.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load}
            className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-sm text-foreground hover:bg-[var(--nav-pill-active)]"
            data-testid="cutting-refresh-btn">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Muat Ulang
          </button>
          <button onClick={openCreate}
            className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm font-medium hover:opacity-90"
            data-testid="cutting-create-btn">
            <Plus className="w-4 h-4" /> Buat Cutting
          </button>
        </div>
      </div>

      {/* Filters */}
      <GlassCard className="p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Cari nomor / style / kain / kode potongan…"
              className={`${inputCls} pl-9`}
              data-testid="cutting-search-input"
            />
          </div>
          <select value={status} onChange={(e) => setStatus(e.target.value)}
            className={`${inputCls} w-auto min-w-[160px]`} data-testid="cutting-status-filter">
            <option value="">Semua Status</option>
            <option value="draft">Draft</option>
            <option value="in_progress">Berjalan</option>
            <option value="completed">Selesai</option>
            <option value="cancelled">Dibatalkan</option>
          </select>
        </div>
      </GlassCard>

      {err && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4" /> {err}
        </div>
      )}

      {/* ── FASE H-6b — PROGRES TANPA DOKUMEN PENGELUARAN MATERIAL ─────────────
          Kain sudah keluar & gulungan sudah berkurang, tetapi dokumennya belum ada
          (data sebelum H-6b, atau penerbitan dokumen gagal). Tanpa panel ini arus
          keluar itu tidak akan pernah muncul di layar Gudang. Menerbitkan dokumen
          TIDAK memotong stok lagi. */}
      {miMissing.count > 0 && (
        <div className="rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-4"
          data-testid="cutting-mi-missing-panel">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-700 dark:text-amber-300 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">
                  {miMissing.count} laporan progres belum punya dokumen Pengeluaran Material
                </div>
                <p className="text-xs text-amber-900/80 dark:text-amber-100/80 mt-0.5 max-w-2xl">
                  Kain &amp; gulungannya SUDAH berkurang, tetapi arus keluarnya belum tampil di layar
                  Gudang → Pengeluaran Material. Menerbitkan dokumen hanya membuat bukti/jejak —
                  <b> stok tidak dipotong lagi</b>.
                </p>
              </div>
            </div>
            <button onClick={backfillMiDocs} disabled={miFixing}
              className="inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-60 text-white text-sm font-medium"
              data-testid="cutting-mi-backfill-btn">
              {miFixing ? <Loader2 className="w-4 h-4 animate-spin" /> : <History className="w-4 h-4" />}
              {miFixing ? 'Menerbitkan…' : 'Terbitkan dokumen'}
            </button>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs" data-testid="cutting-mi-missing-table">
              <thead>
                <tr className="text-left text-amber-900/70 dark:text-amber-100/70 border-b border-amber-300/50 dark:border-amber-500/20">
                  <th className="px-2 py-1.5 font-medium">Order</th>
                  <th className="px-2 py-1.5 font-medium">Kain</th>
                  <th className="px-2 py-1.5 font-medium text-right">Kain keluar</th>
                  <th className="px-2 py-1.5 font-medium">Gudang</th>
                  <th className="px-2 py-1.5 font-medium">Gulungan</th>
                  <th className="px-2 py-1.5 font-medium">Waktu</th>
                </tr>
              </thead>
              <tbody>
                {(miMissing.items || []).slice(0, 8).map((m) => (
                  <tr key={m.progress_id} className="border-b border-amber-300/30 dark:border-amber-500/10 last:border-0"
                    data-testid={`cutting-mi-missing-row-${m.progress_id}`}>
                    <td className="px-2 py-1.5 font-mono text-amber-900 dark:text-amber-100">{m.cutting_number || '-'}</td>
                    <td className="px-2 py-1.5 text-amber-900 dark:text-amber-100">
                      <span className="font-mono">{m.material_code || '-'}</span>
                      <span className="text-amber-900/60 dark:text-amber-100/60"> · {m.material_name || ''}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-amber-900 dark:text-amber-100">
                      {fmtNum(m.input_consumed, 2)} {m.unit || ''}
                    </td>
                    <td className="px-2 py-1.5 text-amber-900/80 dark:text-amber-100/80">{m.location_name || '-'}</td>
                    <td className="px-2 py-1.5 font-mono text-amber-900/80 dark:text-amber-100/80">
                      {(m.roll_numbers || []).join(', ') || '-'}
                    </td>
                    <td className="px-2 py-1.5 text-amber-900/70 dark:text-amber-100/70">{fmtDateTime(m.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {miMissing.count > 8 && (
              <p className="text-[11px] text-amber-900/70 dark:text-amber-100/70 mt-1.5">
                …dan {miMissing.count - 8} lagi. Tombol di atas menerbitkan semuanya.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <GlassCard className="p-0 overflow-hidden">
        {loading && rows.length === 0 ? (
          <div className="p-6 space-y-2">
            {[0, 1, 2, 3].map((i) => <div key={i} className="h-9 rounded-lg bg-foreground/5 animate-pulse" />)}
          </div>
        ) : rows.length === 0 ? (
          <div className="p-12 text-center" data-testid="cutting-empty-state">
            <Scissors className="w-10 h-10 mx-auto text-muted-foreground/40" />
            <p className="mt-3 font-medium text-foreground">Belum ada order cutting</p>
            <p className="text-sm text-muted-foreground">Mulai dengan memilih kain dari master material Gudang.</p>
            <button onClick={openCreate}
              className="mt-4 inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm">
              <Plus className="w-4 h-4" /> Buat Cutting
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="cutting-orders-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)] bg-[var(--nav-pill-bg)]">
                  <th className="px-4 py-2.5 font-medium">Nomor</th>
                  <th className="px-4 py-2.5 font-medium">Style / Potongan</th>
                  <th className="px-4 py-2.5 font-medium">Kain (input)</th>
                  <th className="px-4 py-2.5 font-medium text-right">Kain Terpakai</th>
                  <th className="px-4 py-2.5 font-medium text-right">Potongan Jadi</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}
                    className="border-b border-[var(--glass-border)] last:border-0 hover:bg-[var(--nav-pill-active)]/40 cursor-pointer"
                    onClick={() => openDetail(r.id)}
                    data-testid={`cutting-row-${r.number}`}>
                    <td className="px-4 py-2.5 font-mono text-xs text-foreground whitespace-nowrap">{r.number}</td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-foreground">{r.style_name || '-'}</div>
                      <div className="text-[11px] text-muted-foreground font-mono">
                        {r.output_material_code || 'kode dibuat saat Mulai'}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">
                      {r.input_material_name}<br />
                      <span className="font-mono">{r.input_material_code}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                      {fmtNum(r.consumed_input_qty, 2)} / {fmtNum(r.planned_input_qty, 2)} {r.input_unit}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      <span className="text-foreground font-medium">{fmtNum(r.produced_qty)}</span>
                      <span className="text-muted-foreground"> / {fmtNum(r.planned_output_qty)} pcs</span>
                      <div className="h-1 mt-1 rounded-full bg-foreground/10 overflow-hidden">
                        <div className="h-full bg-[hsl(var(--primary))]"
                             style={{ width: `${Math.min(r.progress_pct || 0, 100)}%` }} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5"><StatusPill status={r.status} /></td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <button onClick={(e) => { e.stopPropagation(); openDetail(r.id); }}
                        className="text-xs text-[hsl(var(--primary))] hover:underline mr-3">Detail</button>
                      {r.status === 'draft' && (
                        <button onClick={(e) => { e.stopPropagation(); removeDraft(r); }}
                          className="text-xs text-red-600 hover:underline inline-flex items-center gap-1">
                          <Trash2 className="w-3 h-3" /> Hapus
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* ── CREATE MODAL ─────────────────────────────────────────────── */}
      {showCreate && (
        <Modal title="Buat Order Cutting" size="xl" onClose={() => setShowCreate(false)}>
          <form onSubmit={submitCreate} className="space-y-4" data-testid="cutting-create-form">
            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--nav-pill-bg)] p-3 text-xs text-muted-foreground flex items-start gap-2">
              <Layers className="w-4 h-4 mt-0.5 text-[hsl(var(--primary))] shrink-0" />
              <span>
                Input diambil dari <b className="text-foreground">master material Gudang</b> (kain / benang).
                Output otomatis dibuat sebagai <b className="text-foreground">item master baru</b> bertipe potongan
                (satuan pcs) saat cutting dimulai.
              </span>
            </div>

            <Field label="Material Kain (input)" required
                   hint={selectedMaterial
                     ? `Total stok ${fmtNum(selectedMaterial.stock_qty, 2)} ${selectedMaterial.unit} · ${selectedMaterial.roll_count} roll aktif`
                     : 'Stok kain disimpan per gudang — pilih kain dulu untuk melihat sebarannya.'}>
              <div className="flex items-center gap-2 mb-1.5">
                <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                  <input type="checkbox" checked={onlyInStock}
                    onChange={(e) => setOnlyInStock(e.target.checked)}
                    data-testid="cutting-only-instock" />
                  Tampilkan hanya kain yang ada stoknya ({materialOptions.length} dari {materials.length})
                </label>
              </div>
              <select value={form.input_material_id} onChange={(e) => onPickMaterial(e.target.value)}
                className={inputCls} data-testid="cutting-input-material-select" required>
                <option value="">— Pilih kain —</option>
                {materialOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} · {m.name} — stok {fmtNum(m.stock_qty, 2)} {m.unit}
                    {m.best_location_name ? ` @ ${m.best_location_name}` : ' (belum ada stok)'}
                  </option>
                ))}
              </select>
            </Field>

            {selectedMaterial && (
              <Field label="Gudang Sumber Kain" required
                     hint={stockAtLocation !== null
                       ? `Stok di gudang ini: ${fmtNum(stockAtLocation, 2)} ${selectedMaterial.unit}. Pemotongan stok saat input progres diambil dari gudang ini.`
                       : ''}>
                <select value={form.location_id}
                  onChange={(e) => setForm((f) => ({ ...f, location_id: e.target.value }))}
                  className={inputCls} data-testid="cutting-location-select" required>
                  <option value="">— Pilih gudang —</option>
                  {(selectedMaterial.stock_locations || []).map((l) => (
                    <option key={l.location_id} value={l.location_id}>
                      {l.location_name} — stok {fmtNum(l.qty, 2)} {selectedMaterial.unit}
                    </option>
                  ))}
                  {(selectedMaterial.stock_locations || []).length === 0 &&
                    locations.map((l) => (
                      <option key={l.id} value={l.id}>{l.name} (stok 0)</option>
                    ))}
                </select>
              </Field>
            )}

            {selectedMaterial && Number(selectedMaterial.stock_qty || 0) <= 0 && (
              <div className="flex items-start gap-2 p-2.5 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/30 text-xs text-amber-800 dark:text-amber-300">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                Kain ini belum punya stok di gudang manapun. Cutting bisa disimpan sebagai draft,
                tetapi tidak bisa dimulai sebelum penerimaan barang dicatat di Portal Gudang.
              </div>
            )}

            {/* ── FASE H-6: gulungan WAJIB untuk kain yang dilacak per gulungan ── */}
            {selectedMaterial && rollMeta.roll_required && rolls.length > 0 && (
              <Field label={`Gulungan Kain (${rolls.length} tersedia · sisa ${fmtQty(rollMeta.total_remaining)} ${rollMeta.uom})`}
                     hint="Centang gulungan yang akan dipotong. Boleh dipilih sekarang atau saat lapor progres — tetapi progres TIDAK bisa dicatat tanpa menunjuk gulungan.">
                <div className="max-h-40 overflow-y-auto rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]"
                  data-testid="cutting-roll-picker">
                  {rolls.map((r) => {
                    const checked = form.roll_ids.includes(r.id);
                    const remaining = Number(r.remaining ?? (r.uom === 'kg' ? r.remaining_kg : r.remaining_m) ?? 0);
                    return (
                      <label key={r.id} className="flex items-center gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-[var(--nav-pill-active)]/40"
                        data-testid={`cutting-roll-option-${r.roll_no}`}>
                        <input type="checkbox" checked={checked}
                          onChange={() => setForm((f) => ({
                            ...f,
                            roll_ids: checked ? f.roll_ids.filter((x) => x !== r.id) : [...f.roll_ids, r.id],
                          }))} />
                        <span className="font-mono text-foreground">{r.roll_no}</span>
                        <span className="text-muted-foreground">
                          sisa {fmtQty(remaining)} {r.uom} · {r.color || r.color_lot || '-'}
                          {r.source_receipt_number ? ` · dari ${r.source_receipt_number}` : ''}
                        </span>
                      </label>
                    );
                  })}
                </div>
                {form.roll_ids.length > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-1" data-testid="cutting-roll-picked-summary">
                    {form.roll_ids.length} gulungan dipilih · sisa terpilih{' '}
                    {fmtQty(rolls.filter((r) => form.roll_ids.includes(r.id))
                      .reduce((s, r) => s + Number(r.remaining ?? (r.uom === 'kg' ? r.remaining_kg : r.remaining_m) ?? 0), 0))} {rollMeta.uom}
                    {Number(form.planned_input_qty) > 0 && ` · rencana pakai ${fmtQty(form.planned_input_qty)} ${selectedMaterial.unit}`}
                  </p>
                )}
              </Field>
            )}

            {selectedMaterial && rollMeta.roll_required && rolls.length === 0 && (
              <div className="flex items-start gap-2 p-2.5 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300"
                data-testid="cutting-no-rolls-warning">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Kain ini <b>belum punya gulungan</b> di sistem, jadi order tidak bisa disimpan — tidak akan
                  bisa dibuktikan gulungan mana yang dipotong. Terbitkan gulungannya dulu di
                  <b> Gudang → Roll Kain → tab “Penerimaan tanpa roll”</b>, atau isi Rincian Roll saat Penerimaan Barang.
                </span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label={`Rencana Pemakaian Kain (${selectedMaterial?.unit || 'satuan'})`} required>
                <input type="number" step="0.01" min="0" value={form.planned_input_qty}
                  onChange={(e) => setForm((f) => ({ ...f, planned_input_qty: e.target.value }))}
                  className={inputCls} data-testid="cutting-planned-input" required />
              </Field>
              <Field label="Target Potongan (pcs)" required>
                <input type="number" step="1" min="0" value={form.planned_output_qty}
                  onChange={(e) => setForm((f) => ({ ...f, planned_output_qty: e.target.value }))}
                  className={inputCls} data-testid="cutting-planned-output" required />
              </Field>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Style/produk DARI MASTER (2026-08-21). Ketikan bebas membuat order
                  cutting tidak pernah menunjuk model, sehingga BOM (per model+size)
                  dan produksi tidak bisa tahu potongan ini milik produk yang mana. */}
              <Field label="Model / Style (dari Master Produk)" required
                hint="Wajib dipilih dari master supaya BOM & produksi mengenali produknya.">
                <div className="flex gap-2">
                  <select value={form.model_id}
                    onChange={(e) => onPickModel(e.target.value)}
                    className={inputCls} data-testid="cutting-model-select" required>
                    <option value="">— pilih model —</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.code ? `${m.code} · ` : ''}{m.name}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setShowNewModel(true)}
                    className="h-9 px-3 shrink-0 rounded-lg border border-[var(--glass-border)] text-xs font-medium text-foreground hover:bg-foreground/5"
                    data-testid="cutting-new-model-btn">+ Model Baru</button>
                </div>
              </Field>
              <Field label="Varian (Warna · Size)"
                hint={form.model_id
                  ? (variants.length ? 'Diambil dari varian model terpilih.' : 'Model ini belum punya varian — warna/size dibiarkan kosong.')
                  : 'Pilih model dulu.'}>
                <select value={form.variant_id}
                  onChange={(e) => onPickVariant(e.target.value)}
                  disabled={!form.model_id || !variants.length}
                  className={inputCls} data-testid="cutting-variant-select">
                  <option value="">{variants.length ? '— pilih warna/size —' : '(tidak ada varian)'}</option>
                  {variants.map((v) => (
                    <option key={v.id} value={v.id}>
                      {(v.color_name || v.color || '-')} · {(v.size_code || v.size || '-')}
                      {v.sku ? ` · ${v.sku}` : ''}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            {form.model_id && (
              <div className="text-[11px] text-muted-foreground -mt-1" data-testid="cutting-style-preview">
                Potongan akan tercatat sebagai <strong className="text-foreground">
                  {form.style_name}{form.output_color ? ` · ${form.output_color}` : ''}{form.output_size ? ` · ${form.output_size}` : ''}
                </strong>{form.style_sku ? ` (kode master ${form.style_sku})` : ''}
              </div>
            )}

            {/* ── KEBUTUHAN MENURUT BOM (2026-08-23) ───────────────────────
                Rencana pemakaian kain tidak lagi ditebak: angkanya datang dari
                BOM model+ukuran. Bila BOM/satuan/kain tidak cocok, alasannya
                ditulis apa adanya beserta jalan keluarnya. */}
            {form.model_id && (
              <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3"
                data-testid="cutting-bom-card">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="text-xs font-semibold text-foreground inline-flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
                    Kebutuhan menurut BOM
                    {bomLoading && <Loader2 className="w-3 h-3 animate-spin" />}
                    {bomReq?.has_bom && (
                      <span className="font-normal text-muted-foreground">
                        · BOM v{bomReq.bom_version} ukuran {bomReq.size_code || '—'}
                      </span>
                    )}
                  </div>
                  {bomReq?.fabric?.qty_total > 0 && (
                    <button type="button" onClick={useBomQty}
                      className="h-7 px-2.5 rounded-lg bg-[hsl(var(--primary))] text-white text-[11px] font-medium"
                      data-testid="cutting-use-bom-qty">
                      Pakai angka BOM ({fmtQtyTrim(bomReq.fabric.qty_total)} {bomReq.fabric.unit})
                    </button>
                  )}
                </div>

                {/* Ukuran fallback: model yang BOM-nya ada tapi variannya belum
                    didaftarkan tetap bisa memakai BOM-nya (dulu jalan buntu). */}
                {!variants.length && (
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-muted-foreground">
                      Model ini belum punya varian — pilih ukuran untuk membaca BOM-nya:
                    </span>
                    <select value={sizeId} onChange={(e) => pickSize(e.target.value)}
                      className="h-8 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground"
                      data-testid="cutting-bom-size-select">
                      <option value="">— pilih ukuran —</option>
                      {sizes.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.code}{sizesWithBom.has(s.id) ? ' · ada BOM' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {bomReq?.has_bom && bomReq.fabric ? (                  <div className="mt-2 text-[11px] text-foreground/90 space-y-1">
                    <div data-testid="cutting-bom-fabric">
                      Kain <strong>{bomReq.fabric.code || bomReq.fabric.name}</strong>:{' '}
                      <strong>{fmtQtyTrim(bomReq.fabric.qty_per_pcs)} {bomReq.fabric.unit}</strong>/pcs
                      {Number(form.planned_output_qty) > 0 ? (
                        <> × {fmtNum(form.planned_output_qty, 0)} pcs ={' '}
                          <strong className="text-[hsl(var(--primary))]">
                            {fmtQtyTrim(bomReq.fabric.qty_total)} {bomReq.fabric.unit}
                          </strong>
                          {bomReq.fabric.unit_cost > 0 && (
                            <span className="text-muted-foreground"> · nilai {fmtRp(bomReq.fabric.amount_total)}</span>
                          )}
                        </>
                      ) : (
                        <span className="text-muted-foreground"> — isi target potongan (pcs) untuk melihat totalnya</span>
                      )}
                    </div>
                    {Number(form.planned_input_qty) > 0 && bomReq.fabric.qty_total > 0 &&
                      Math.abs(Number(form.planned_input_qty) - bomReq.fabric.qty_total) /
                        bomReq.fabric.qty_total > 0.1 && (
                      <div className="text-amber-600 dark:text-amber-300 inline-flex items-start gap-1"
                        data-testid="cutting-bom-deviation">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        Rencana manual {fmtQtyTrim(form.planned_input_qty)} {bomReq.fabric.unit} berbeda
                        &gt;10% dari kebutuhan BOM {fmtQtyTrim(bomReq.fabric.qty_total)}{' '}
                        {bomReq.fabric.unit}{' '}
                        — pastikan memang disengaja (mis. ada penyusutan/marker khusus).
                      </div>
                    )}
                    {bomReq.accessories?.length > 0 && (
                      <div className="text-muted-foreground" data-testid="cutting-bom-accessories">
                        Aksesoris yang ikut dibutuhkan:{' '}
                        {bomReq.accessories.map((a) => (
                          <span key={a.material_id || a.code} className="mr-2 text-foreground/80">
                            {a.code || a.name} {fmtQtyTrim(a.qty_per_pcs)} {a.unit}/pcs
                            {Number(form.planned_output_qty) > 0 && ` (total ${fmtQtyTrim(a.qty_total)} ${a.unit})`}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ) : !bomLoading && (
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    {bomReq?.gaps?.length
                      ? null
                      : 'Pilih varian (warna · size) untuk membaca BOM ukuran itu.'}
                  </div>
                )}

                {bomReq?.gaps?.length > 0 && (
                  <ul className="mt-2 space-y-1" data-testid="cutting-bom-gaps">
                    {bomReq.gaps.map((g, i) => (
                      <li key={i} className="text-[11px] text-amber-600 dark:text-amber-300 flex items-start gap-1">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        <span>
                          {g.message}
                          {g.target && g.target !== 'cutting-orders' && (
                            <button type="button"
                              onClick={() => (typeof onNavigate === 'function'
                                ? onNavigate(g.target)
                                : (window.location.hash = g.target))}
                              className="ml-1 underline text-[hsl(var(--primary))]"
                              data-testid={`cutting-bom-fix-${g.code}`}>
                              {g.action || 'Perbaiki'}
                            </button>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                {bomReq?.has_bom === false && bomReq?.other_sizes_with_bom?.length > 0 && (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    Ukuran yang SUDAH punya BOM untuk model ini:{' '}
                    {bomReq.other_sizes_with_bom.map((s) => s.size_code || s.size_id).join(', ')}
                  </div>
                )}
              </div>
            )}

            <Field label="Catatan">
              <textarea value={form.notes} rows={2}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                className={`${inputCls} h-auto py-2`} data-testid="cutting-notes" />
            </Field>

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowCreate(false)}
                className="h-9 px-4 rounded-lg border border-[var(--glass-border)] text-sm text-foreground">Batal</button>
              <button type="submit" disabled={saving}
                className="h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm font-medium disabled:opacity-60 inline-flex items-center gap-2"
                data-testid="cutting-submit-create">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Simpan Draft
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── MODAL MODEL BARU (master produk) ──────────────────────────── */}
      {showNewModel && (
        <Modal title="Model / Style Baru" size="sm" onClose={() => setShowNewModel(false)}>
          <div className="space-y-3" data-testid="cutting-new-model-modal">
            <p className="text-xs text-muted-foreground">
              Model ini akan tersimpan di Master Produk sehingga BOM & produksi bisa memakainya.
            </p>
            <Field label="Nama Model / Style" required>
              <input value={newModel.name} autoFocus
                onChange={(e) => setNewModel((n) => ({ ...n, name: e.target.value }))}
                placeholder="mis. Dress Jemina" className={inputCls}
                data-testid="new-model-name" />
            </Field>
            <Field label="Kode Model (opsional)" hint="Dibuat otomatis bila dibiarkan kosong.">
              <input value={newModel.code}
                onChange={(e) => setNewModel((n) => ({ ...n, code: e.target.value }))}
                placeholder="mis. DRS-JMN" className={inputCls}
                data-testid="new-model-code" />
            </Field>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setShowNewModel(false)}
                className="h-9 px-4 rounded-lg border border-[var(--glass-border)] text-sm text-foreground">Batal</button>
              <button type="button" onClick={createModel} disabled={savingModel}
                className="h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm font-medium disabled:opacity-60 inline-flex items-center gap-2"
                data-testid="new-model-submit">
                {savingModel && <Loader2 className="w-4 h-4 animate-spin" />} Simpan Model
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── DETAIL MODAL ─────────────────────────────────────────────── */}
      {detail && (
        <Modal title={`Cutting ${detail.number}`} size="2xl" onClose={() => setDetail(null)}>
          <div className="space-y-4" data-testid="cutting-detail-panel">
            {detailLoading && <div className="h-1 bg-[hsl(var(--primary))] animate-pulse rounded" />}

            {/* Ringkas */}
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill status={detail.status} />
              <span className="text-xs text-muted-foreground">Dibuat {fmtDateTime(detail.created_at)} oleh {detail.created_by_name || '-'}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <GlassCard className="p-3">
                <p className="text-[11px] text-muted-foreground">Kain (input)</p>
                <p className="text-sm font-medium text-foreground mt-0.5">{detail.input_material_name}</p>
                <p className="text-[11px] font-mono text-muted-foreground">{detail.input_material_code}</p>
                <p className="text-xs mt-2 text-foreground">
                  Terpakai <b>{fmtNum(detail.consumed_input_qty, 2)}</b> / {fmtNum(detail.planned_input_qty, 2)} {detail.input_unit}
                </p>
                <p className="text-[11px] text-muted-foreground">Stok gudang saat ini: {fmtNum(detail.input_stock, 2)} {detail.input_unit}</p>
                <p className="text-[11px] text-muted-foreground">Gudang sumber: <b className="text-foreground">{detail.location_name || '-'}</b></p>
                {detailRolls.roll_required && (
                  <p className="text-[11px] mt-1.5 text-violet-700 dark:text-violet-300" data-testid="cutting-roll-summary">
                    {detailRolls.items.length} gulungan bersisa · total {fmtQty(detailRolls.total_remaining)} {detailRolls.uom}
                  </p>
                )}
                {(detail.roll_ids || []).some((r) => Number(r.consumed_qty || 0) > 0) && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Sudah dipakai:{' '}
                    {(detail.roll_ids || []).filter((r) => Number(r.consumed_qty || 0) > 0)
                      .map((r) => `${r.roll_no} (${fmtQty(r.consumed_qty)})`).join(', ')}
                  </p>
                )}
              </GlassCard>
              <div className="hidden md:flex items-center justify-center">
                <ArrowRight className="w-5 h-5 text-muted-foreground" />
              </div>
              <GlassCard className="p-3">
                <p className="text-[11px] text-muted-foreground">Potongan (output)</p>
                <p className="text-sm font-medium text-foreground mt-0.5">
                  {detail.output_material_name || `${detail.style_name} ${detail.output_color} ${detail.output_size}`}
                </p>
                <p className="text-[11px] font-mono text-muted-foreground">
                  {detail.output_material_code || 'kode dibuat saat Mulai'}
                </p>
                <p className="text-xs mt-2 text-foreground">
                  Jadi <b>{fmtNum(detail.produced_qty)}</b> / {fmtNum(detail.planned_output_qty)} pcs
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Stok potongan: {fmtNum(detail.output_stock)} pcs
                  {detail.output_unit_cost > 0 && ` · HPP ${fmtRp(detail.output_unit_cost)}/pcs`}
                </p>
              </GlassCard>
            </div>

            {/* Aksi status */}
            <div className="flex flex-wrap gap-2">
              {detail.status === 'draft' && (
                <button onClick={() => doAction('/start', {}, 'Cutting dimulai — master potongan dibuat.')}
                  disabled={acting}
                  className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm disabled:opacity-60"
                  data-testid="cutting-start-btn">
                  <PlayCircle className="w-4 h-4" /> Mulai Cutting
                </button>
              )}
              {detail.status === 'in_progress' && (
                <button onClick={() => doAction('/complete', {}, 'Cutting selesai — HPP potongan dihitung.')}
                  disabled={acting}
                  className="inline-flex items-center gap-2 h-9 px-4 rounded-lg bg-emerald-600 text-white text-sm disabled:opacity-60"
                  data-testid="cutting-complete-btn">
                  <CheckCircle2 className="w-4 h-4" /> Selesaikan
                </button>
              )}
              {(detail.status === 'draft' || detail.status === 'in_progress') && (
                <button onClick={() => doAction('/cancel', { reason: 'dibatalkan user' }, 'Cutting dibatalkan.')}
                  disabled={acting}
                  className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-red-300 dark:border-red-500/30 text-red-600 dark:text-red-400 text-sm disabled:opacity-60"
                  data-testid="cutting-cancel-btn">
                  <XCircle className="w-4 h-4" /> Batalkan
                </button>
              )}
              {detail.status === 'completed' && detail.output_material_code && (
                <button onClick={() => onNavigate?.('cutting-panels')}
                  className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-[var(--glass-border)] text-sm text-foreground"
                  data-testid="cutting-goto-panels">
                  <Package className="w-4 h-4" /> Lihat Master Potongan
                </button>
              )}
            </div>

            {/* Input progres */}
            {detail.status === 'in_progress' && (
              <GlassCard className="p-4">
                <h4 className="text-sm font-semibold text-foreground mb-1">Input Progres Potong</h4>
                <p className="text-xs text-muted-foreground mb-3">
                  Setiap input langsung memotong stok kain, menambah stok potongan, dan mengurangi sisa
                  gulungan yang ditunjuk{detailRolls.roll_required
                    ? ' — untuk kain yang dilacak per gulungan, gulungan WAJIB dipilih.'
                    : '.'}
                </p>
                <form onSubmit={submitProgress} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end"
                      data-testid="cutting-progress-form">
                  <Field label={`Kain Terpakai (${effProgUom || detail.input_unit})`} required>
                    <div className="flex gap-2">
                      <input type="number" step="0.0001" min="0" value={prog.input_consumed}
                        onChange={(e) => setProg((p) => ({ ...p, input_consumed: e.target.value }))}
                        className={inputCls} data-testid="cutting-progress-input" required />
                      <UomSelect opt={progUomOpt} value={effProgUom} fallbackUnit={detail.input_unit}
                        onChange={(e) => setProg((p) => ({ ...p, input_uom: e.target.value }))}
                        testId="cutting-progress-uom" className="w-20 shrink-0" />
                    </div>
                    <UomConversionHint opt={progUomOpt} qty={prog.input_consumed} unit={effProgUom}
                      fallbackUnit={detail.input_unit} className="mt-1" testId="cutting-progress-uom-hint" />
                  </Field>
                  <Field label="Potongan Jadi (pcs)" required>
                    <input type="number" step="1" min="0" value={prog.output_qty}
                      onChange={(e) => setProg((p) => ({ ...p, output_qty: e.target.value }))}
                      className={inputCls} data-testid="cutting-progress-output" required />
                  </Field>
                  <Field label="Waste / Sisa">
                    <input type="number" step="0.01" min="0" value={prog.waste_qty}
                      onChange={(e) => setProg((p) => ({ ...p, waste_qty: e.target.value }))}
                      className={inputCls} data-testid="cutting-progress-waste" />
                  </Field>
                  <button type="submit" disabled={acting || rollBlocking || allocPreview.shortage > 0}
                    className="h-9 px-4 rounded-lg bg-[hsl(var(--primary))] text-white text-sm font-medium disabled:opacity-60 inline-flex items-center justify-center gap-2"
                    data-testid="cutting-progress-submit">
                    {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Catat
                  </button>
                  {(detailRolls.roll_required || (detail.roll_ids || []).length > 0) && (
                    <div className="sm:col-span-4">
                      <Field
                        label={detailRolls.roll_required ? 'Gulungan yang dipotong (WAJIB)' : 'Gulungan yang dipotong'}
                        required={detailRolls.roll_required}
                        hint={detailRolls.items.length
                          ? 'Centang gulungan yang benar-benar dipotong. Pemakaian dibagi otomatis FIFO (gulungan tertua dulu) dan sisanya langsung berkurang.'
                          : ''}>
                        {detailRolls.items.length === 0 ? (
                          <div className="flex items-start gap-2 p-2.5 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300"
                            data-testid="cutting-progress-no-rolls">
                            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                            <span>
                              Kain ini tidak punya gulungan bersisa. Terbitkan gulungan di{' '}
                              <b>Gudang → Roll Kain → “Penerimaan tanpa roll”</b>
                              {onNavigate && (
                                <button type="button" onClick={() => onNavigate('wms-fabric-rolls')}
                                  className="ml-1 underline font-medium" data-testid="cutting-goto-rolls">
                                  buka sekarang →
                                </button>
                              )}
                            </span>
                          </div>
                        ) : (
                          <>
                            <div className="max-h-40 overflow-y-auto rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]"
                              data-testid="cutting-progress-roll-picker">
                              {detailRolls.items.map((r) => {
                                const checked = (prog.roll_ids || []).includes(r.id);
                                const remaining = Number(r.remaining ?? (r.uom === 'kg' ? r.remaining_kg : r.remaining_m) ?? 0);
                                const inPlan = allocPreview.plan.find((p) => p.roll_id === r.id);
                                return (
                                  <label key={r.id}
                                    className={`flex items-center gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-[var(--nav-pill-active)]/40 ${checked ? 'bg-[var(--nav-pill-active)]/30' : ''}`}
                                    data-testid={`cutting-progress-roll-${r.roll_no}`}>
                                    <input type="checkbox" checked={checked}
                                      onChange={() => toggleProgRoll(r.id)}
                                      data-testid={`cutting-progress-roll-cb-${r.roll_no}`} />
                                    <span className="font-mono text-foreground">{r.roll_no}</span>
                                    <span className="text-muted-foreground">
                                      sisa {fmtQty(remaining)} {r.uom}
                                      {r.color_lot ? ` · lot ${r.color_lot}` : ''}
                                      {r.source_receipt_number ? ` · dari ${r.source_receipt_number}` : ''}
                                    </span>
                                    {inPlan && (
                                      <span className="ml-auto text-[11px] font-semibold text-[hsl(var(--primary))]">
                                        pakai {fmtQty(inPlan.qty)} → sisa {fmtQty(inPlan.remaining_after)}
                                      </span>
                                    )}
                                  </label>
                                );
                              })}
                            </div>
                            {/* Pratinjau alokasi FIFO — supaya tidak ada kejutan setelah ditekan */}
                            {(prog.roll_ids || []).length > 0 && Number(prog.input_consumed) > 0 && (
                              <div className={`mt-1.5 text-[11px] px-2.5 py-1.5 rounded-lg border ${
                                allocPreview.shortage > 0
                                  ? 'border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-red-700 dark:text-red-300'
                                  : 'border-emerald-300 bg-emerald-50 dark:bg-emerald-500/10 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300'}`}
                                data-testid="cutting-alloc-preview">
                                {allocPreview.shortage > 0 ? (
                                  <>Sisa gulungan terpilih kurang {fmtQty(allocPreview.shortage, 3)} {detailRolls.uom} —
                                     tersedia {fmtQty(allocPreview.available)} untuk {fmtQty(prog.input_consumed)}.
                                     Pilih gulungan tambahan atau kurangi jumlah pemakaian.</>
                                ) : (
                                  <>Rencana: {allocPreview.plan.map((p) => `${p.roll_no} −${fmtQty(p.qty)}`).join(' · ')}</>
                                )}
                              </div>
                            )}
                            {rollBlocking && (
                              <p className="mt-1.5 text-[11px] text-amber-700 dark:text-amber-300" data-testid="cutting-roll-required-hint">
                                Pilih minimal satu gulungan — progres tidak bisa dicatat tanpa itu.
                              </p>
                            )}
                          </>
                        )}
                      </Field>
                    </div>
                  )}
                  <div className="sm:col-span-2">
                    <Field label="Catatan">
                      <input value={prog.note} onChange={(e) => setProg((p) => ({ ...p, note: e.target.value }))}
                        placeholder="mis. shift pagi" className={inputCls} data-testid="cutting-progress-note" />
                    </Field>
                  </div>
                </form>
              </GlassCard>
            )}

            {/* Riwayat progres */}
            <GlassCard className="p-0 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[var(--glass-border)] flex items-center gap-2">
                <History className="w-4 h-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold text-foreground">Riwayat Progres ({(detail.progress || []).length})</h4>
                {/* FASE H-6b — pintu ke daftar arus keluar gudang (dokumen MI). */}
                {onNavigate && (detail.progress || []).length > 0 && (
                  <button onClick={() => { setDetail(null); onNavigate('wh-material-issue'); }}
                    className="ml-auto inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-[var(--glass-border)] text-[11px] text-muted-foreground hover:text-foreground hover:bg-[var(--nav-pill-active)]"
                    data-testid="cutting-open-material-issue">
                    <Package className="w-3 h-3" /> Lihat di Pengeluaran Material
                  </button>
                )}
              </div>
              {(detail.progress || []).length === 0 ? (
                <p className="p-6 text-center text-sm text-muted-foreground">Belum ada progres dicatat.</p>
              ) : (
                <table className="w-full text-sm" data-testid="cutting-progress-table">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                      <th className="px-4 py-2 font-medium">Waktu</th>
                      <th className="px-4 py-2 font-medium text-right">Kain</th>
                      <th className="px-4 py-2 font-medium text-right">Potongan</th>
                      <th className="px-4 py-2 font-medium text-right">Waste</th>
                      {/* SESI #32 — nilai yang BERPINDAH dari kain ke potongan */}
                      <th className="px-4 py-2 font-medium text-right">Nilai kain keluar</th>
                      <th className="px-4 py-2 font-medium text-right">HPP potongan</th>
                      <th className="px-4 py-2 font-medium">Gulungan dipakai</th>
                      <th className="px-4 py-2 font-medium">Dokumen keluar</th>
                      <th className="px-4 py-2 font-medium">Catatan</th>
                      <th className="px-4 py-2 font-medium">Oleh</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.progress || []).map((p) => (
                      <tr key={p.id} className="border-b border-[var(--glass-border)] last:border-0">
                        <td className="px-4 py-2 text-xs text-muted-foreground">{fmtDateTime(p.created_at)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-foreground">{fmtNum(p.input_consumed, 2)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-foreground">{fmtNum(p.output_qty)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">{fmtNum(p.waste_qty, 2)}</td>
                        {/* SESI #32 — nilai kain yang keluar & HPP potongan sebelum→sesudah.
                            Kalau kainnya belum bernilai, alasannya DITULIS (bukan "-"). */}
                        <td className="px-4 py-2 text-right text-xs"
                          data-testid={`cutting-progress-value-${p.id}`}>
                          {Number(p.value_out || 0) > 0 ? (
                            <>
                              <span className="tabular-nums font-medium text-foreground">
                                {fmtRp(p.value_out)}
                              </span>
                              <span className="block text-[10px] text-muted-foreground">
                                {fmtRp(p.fabric_unit_cost)}/{detail.input_unit || 'satuan'}
                              </span>
                            </>
                          ) : (
                            <span className="text-amber-600 dark:text-amber-300 text-[11px]">
                              belum bernilai
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right text-xs">
                          {Number(p.panel_unit_cost_after || 0) > 0 ? (
                            <>
                              <span className="tabular-nums font-medium text-foreground">
                                {fmtRp(p.panel_unit_cost_after)}/pcs
                              </span>
                              {Number(p.panel_unit_cost_before || 0) > 0
                                && Number(p.panel_unit_cost_before) !== Number(p.panel_unit_cost_after) && (
                                <span className="block text-[10px] text-muted-foreground">
                                  dari {fmtRp(p.panel_unit_cost_before)} (rata-rata bergerak)
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-xs" data-testid={`cutting-progress-rolls-${p.id}`}>
                          {(p.roll_consumption || []).length ? (
                            <div className="flex flex-wrap gap-1">
                              {p.roll_consumption.map((rc) => (
                                <span key={rc.roll_id}
                                  className="font-mono text-[10px] px-1.5 py-0.5 rounded-md bg-violet-100 dark:bg-violet-400/15 text-violet-800 dark:text-violet-200 border border-violet-300 dark:border-violet-400/30"
                                  title={`sisa setelah dipakai: ${fmtQty(rc.remaining_after)}`}>
                                  {rc.roll_no} −{fmtQty(rc.qty)}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-muted-foreground">{p.roll_id ? 'tercatat' : '—'}</span>
                          )}
                        </td>
                        {/* FASE H-6b — nomor dokumen "Pengeluaran Material" per progres.
                            Kalau kosong, kainnya sudah keluar tanpa dokumen: itu HARUS
                            terlihat (bukan strip diam-diam) supaya bisa diterbitkan ulang. */}
                        <td className="px-4 py-2 text-xs" data-testid={`cutting-progress-mi-${p.id}`}>
                          {p.material_issue_number ? (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-400/15 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-400/30"
                              title="Dokumen Pengeluaran Material yang mencatat arus keluar kain ini">
                              {p.material_issue_number}
                            </span>
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-100 dark:bg-amber-400/15 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-400/30">
                              belum ada
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{p.note || '-'}</td>
                        <td className="px-4 py-2 text-xs text-muted-foreground">{p.created_by_name || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </GlassCard>

            {detail.notes && (
              <p className="text-xs text-muted-foreground">Catatan: {detail.notes}</p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
