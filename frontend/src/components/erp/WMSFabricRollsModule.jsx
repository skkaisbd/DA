/**
 * WMS Fabric Rolls — Garment Roll Tracking
 * P0-WH-1: Fabric roll tracking dengan barcode, QC status, position management
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Plus, RefreshCw, Eye, Search, MapPin, QrCode, CheckCircle2,
  XCircle, AlertCircle, Truck, RotateCcw, Edit2, ArrowRightLeft, Loader2,
  ChevronRight, Filter, Download, X, Save, Printer, Sparkles, Brain
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { EmptyState } from './EmptyState';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
// FASE H-5 — gulungan LAHIR dari penerimaan kain; layar ini juga menutup lubang
// penerimaan lama yang belum punya gulungan (backfill).
import RollLinesEditor from './warehouse/RollLinesEditor';
import { rollLinesState, fmtQty } from './warehouse/rollLines';

/* F13 (sesi #11) — stok kain per ROLL tanpa tabel & tanpa unduhan.
   Layar ini punya pencarian & tab, tetapi hasilnya hanya bisa dibaca sebagai
   KARTU tiga kolom dan SEMUANYA dirender sekaligus. Untuk gudang yang isinya
   ratusan roll, dua pertanyaan harian tidak bisa dijawab: "roll mana yang
   sisanya paling sedikit?" (butuh urutan) dan "kirim daftar sisa kain ke
   pembelian" (butuh unduhan). Angka yang tidak bisa diurutkan & dibawa keluar
   berakhir diketik ulang. */
const ROLLS_VIEW_KEY = 'wms_fabric_rolls_view';
const CSV_HEAD = ['No. Roll', 'Kode material', 'Material', 'Warna', 'Lot', 'Supplier',
  'No. PO', 'Status QC', 'Status stok', 'Satuan', 'Total', 'Sisa',
  '≈ Total (m)', '≈ Sisa (m)', 'Posisi'];

// Satuan roll ADA DI DATANYA (`uom`) — layar tidak boleh menebak "meter" dari
// nama field warisan `length_m`/`remaining_m`. Keluhan pemilik (2026-08-21):
// kain dibeli YARD tetapi tabel menulis "(m)", sehingga angka gulungan terlihat
// tidak cocok dengan PO padahal tidak ada konversi yang terjadi.
const rollUom = (r) => (r?.uom || '').toLowerCase() || 'satuan';
const rollTotal = (r) => Number(r?.qty_total ?? (r?.is_weight ? r?.weight_kg : r?.length_m) ?? 0);
const rollRemaining = (r) => Number(r?.qty_remaining ?? (r?.is_weight ? r?.remaining_kg : r?.remaining_m) ?? 0);

const API = process.env.REACT_APP_BACKEND_URL;

const QC_STATUS = {
  pending: { label: 'Pending', color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-500/30' },
  pass: { label: 'Pass', color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-500/30' },
  partial: { label: 'Partial', color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-500/30' },
  reject: { label: 'Reject', color: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 border-red-400 dark:border-red-500/30' },
};

const STOCK_STATUS = {
  in_stock: { label: 'In Stock', color: 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-300' },
  partly_issued: { label: 'Sebagian Terpakai', color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300' },
  fully_issued: { label: 'Habis', color: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400' },
  returned: { label: 'Dikembalikan', color: 'bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-300' },
  rejected: { label: 'Ditolak', color: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300' },
};

const fmt = (n) => new Intl.NumberFormat('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n ?? 0);

export default function WMSFabricRollsModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [rolls, setRolls] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({ qc_status: 'all', status: '' });
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(ROLLS_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  // Default: SISA panjang paling sedikit di atas — roll yang hampir habis adalah
  // yang paling perlu dilihat gudang (dan paling sering dicari pembelian).
  const [sort, setSort] = useState({ key: 'qty_remaining', dir: 'asc' });
  useEffect(() => {
    try { localStorage.setItem(ROLLS_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [viewDialog, setViewDialog] = useState(null); // {roll, movements}
  const [createDialog, setCreateDialog] = useState(false);
  const [issueDialog, setIssueDialog] = useState(null); // {roll}
  const [putawayDialog, setPutawayDialog] = useState(null); // {roll}
  const [aiAnalysisDialog, setAiAnalysisDialog] = useState(null); // AI insights
  const [aiLoading, setAiLoading] = useState(false);
  // ── FASE H-5 ───────────────────────────────────────────────────────────────
  // `missing` = baris penerimaan kain yang SUDAH masuk stok tetapi belum punya
  // gulungan. Ini bukan hiasan: Portal Cutting (H-6) MENOLAK memotong kain yang
  // tidak punya gulungan, jadi daftar ini adalah daftar pekerjaan yang menahan
  // bagian potong. `rollPolicy` dipakai untuk memberi tahu nomor berikutnya —
  // nomor roll tidak pernah diketik.
  const [missing, setMissing] = useState([]);
  const [missingLoading, setMissingLoading] = useState(false);
  const [rollPolicy, setRollPolicy] = useState(null);
  const [issueRollsDialog, setIssueRollsDialog] = useState(null); // {row, lines}
  const [issuing, setIssuing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (filters.qc_status && filters.qc_status !== 'all') params.set('qc_status', filters.qc_status);
      if (filters.status) params.set('status', filters.status);
      if (tab !== 'all' && tab !== 'missing') params.set('status', tab);
      const r = await fetch(`${API}/api/wms/fabric-rolls?${params}`, { headers });
      const d = await r.json();
      setRolls(d.items || []);
    } catch (e) {
      toast.error('Gagal memuat data roll');
    } finally {
      setLoading(false);
    }
  }, [headers, search, filters, tab]);

  useEffect(() => { load(); }, [load]);

  // FASE H-5: daftar penerimaan kain tanpa gulungan + kebijakan nomor roll.
  const loadMissing = useCallback(async () => {
    setMissingLoading(true);
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls/missing-from-receipts?limit=100`, { headers });
      const d = await r.json();
      setMissing(d.items || []);
    } catch {
      toast.error('Gagal memuat daftar penerimaan tanpa roll');
    } finally {
      setMissingLoading(false);
    }
  }, [headers]);

  useEffect(() => { loadMissing(); }, [loadMissing]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/wms/fabric-rolls/number-policy`, { headers });
        if (r.ok) setRollPolicy(await r.json());
      } catch { /* petunjuk nomor gagal diambil — layar tetap jalan */ }
    })();
  }, [headers]);

  const openIssueRolls = (row) => setIssueRollsDialog({
    row,
    lines: [{ qty: row.accepted_qty, color_lot: '', notes: '' }],
  });

  const submitIssueRolls = async () => {
    if (!issueRollsDialog) return;
    const { row, lines } = issueRollsDialog;
    const st = rollLinesState(lines, row.accepted_qty);
    if (st.state !== 'match') {
      toast.error(`Total gulungan ${fmtQty(st.total)} ${row.unit} belum sama dengan qty diterima `
        + `${fmtQty(row.accepted_qty)} ${row.unit}. Perbaiki angkanya dulu.`);
      return;
    }
    setIssuing(true);
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls/issue-from-receipt`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          receipt_id: row.receipt_id,
          item_id: row.item_id,
          lines: lines.filter(l => parseFloat(l.qty) > 0)
            .map(l => ({ qty: parseFloat(l.qty), color_lot: l.color_lot || '', notes: l.notes || '' })),
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(d.message || `${(d.roll_numbers || []).length} gulungan diterbitkan`, { duration: 7000 });
      setIssueRollsDialog(null);
      await Promise.all([load(), loadMissing()]);
    } catch (e) {
      toast.error(e.message, { duration: 9000 });
    } finally {
      setIssuing(false);
    }
  };

  const handleView = async (roll) => {
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls/${roll.id}`, { headers });
      const d = await r.json();
      // Endpoint mengembalikan dokumen roll (spread) + `movements`, sedangkan
      // dialog membaca `viewDialog.roll.*` → dulu semua kolom detail tampil
      // kosong ("0,00 / 0,00") tanpa satu pun error di console.
      setViewDialog({ roll: d, movements: d.movements || [] });
    } catch {
      toast.error('Gagal memuat detail roll');
    }
  };

  const handleCreateRoll = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = {
      // FASE H-5: `roll_no` TIDAK dikirim — nomor diterbitkan server (mode otomatis).
      // Dua gulungan fisik bernomor sama membuat pertanyaan "gulungan mana yang
      // dipotong" tidak bisa dijawab, jadi nomor tidak boleh datang dari ketikan.
      material_id: fd.get('material_id') || '',
      material_code: fd.get('material_code') || '',
      material_name: fd.get('material_name'),
      color: fd.get('color') || '',
      color_lot: fd.get('color_lot') || '',
      supplier_name: fd.get('supplier_name') || '',
      uom: fd.get('uom') || 'meter',
      length_m: parseFloat(fd.get('length_m')) || 0,
      weight_kg: parseFloat(fd.get('weight_kg')) || 0,
      po_no: fd.get('po_no') || '',
      unit_cost: parseFloat(fd.get('unit_cost')) || 0,
      notes: fd.get('notes') || '',
    };
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls`, {
        method: 'POST',
        headers,
        body: JSON.stringify(data),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`Roll ${d?.roll?.roll_no || ''} dibuat`);
      setCreateDialog(false);
      load();
    } catch (e2) {
      toast.error(e2.message || 'Gagal membuat roll', { duration: 8000 });
    }
  };

  const handlePutaway = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls/${putawayDialog.id}/putaway`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          position_id: fd.get('position_id'),
          position_barcode: fd.get('position_barcode') || '',
          notes: fd.get('notes') || '',
        }),
      });
      if (!r.ok) throw new Error();
      toast.success('Roll berhasil dipindahkan ke posisi');
      setPutawayDialog(null);
      load();
    } catch {
      toast.error('Gagal put-away');
    }
  };

  const handleIssue = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await fetch(`${API}/api/wms/fabric-rolls/${issueDialog.id}/issue`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          qty: parseFloat(fd.get('qty')),
          unit: rollUom(issueDialog),
          reference_type: fd.get('reference_type') || 'wo',
          reference_no: fd.get('reference_no') || '',
          notes: fd.get('notes') || '',
        }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || d.error || `HTTP ${r.status}`);
      }
      toast.success('Roll berhasil di-issue');
      setIssueDialog(null);
      load();
    } catch (err) {
      toast.error(`Gagal issue roll: ${err.message || err}`);
    }
  };

  const handleAIAnalysis = async () => {
    setAiLoading(true);
    try {
      const rejectedRolls = rolls.filter(r => r.qc_status === 'reject' || r.qc_status === 'partial');
      const rollIds = rejectedRolls.map(r => r.id);
      
      const r = await fetch(`${API}/api/wms/ai/fabric-rolls/quality-analysis`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          roll_ids: rollIds,
          time_period_days: 30
        }),
      });
      
      if (!r.ok) throw new Error();
      const data = await r.json();
      setAiAnalysisDialog(data);
      toast.success('🤖 AI Analysis berhasil!');
    } catch (e) {
      toast.error('Gagal melakukan AI analysis');
      console.error(e);
    } finally {
      setAiLoading(false);
    }
  };

  const filteredRolls = useMemo(() => {
    if (tab === 'all') return rolls;
    return rolls.filter(r => r.status === tab);
  }, [rolls, tab]);

  // F13 — urutan & unduhan atas baris YANG TERLIHAT.
  const sortedRolls = useMemo(() => {
    const list = [...filteredRolls];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const num = ['qty_total', 'qty_remaining', 'length_m', 'remaining_m',
        'weight_kg', 'remaining_kg'].includes(key);
      const av = key === 'qty_remaining' ? rollRemaining(a) : key === 'qty_total' ? rollTotal(a) : a?.[key];
      const bv = key === 'qty_remaining' ? rollRemaining(b) : key === 'qty_total' ? rollTotal(b) : b?.[key];
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [filteredRolls, sort]);
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(sortedRolls, 15);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  const csvRows = sortedRolls.map((r) => [
    r.roll_no, r.material_code, r.material_name, r.color, r.color_lot,
    r.supplier_name, r.po_no, QC_STATUS[r.qc_status]?.label || r.qc_status,
    STOCK_STATUS[r.status]?.label || r.status, rollUom(r),
    rollTotal(r), rollRemaining(r),
    r.qty_total_m ?? '', r.qty_remaining_m ?? '', r.position_barcode || '',
  ]);
  // Ringkasan sisa dikelompokkan PER SATUAN — menjumlahkan yard dengan kg
  // adalah angka yang tidak berarti apa pun.
  const remainingBySatuan = useMemo(() => {
    const acc = {};
    sortedRolls.forEach((r) => {
      const u = rollUom(r);
      acc[u] = (acc[u] || 0) + rollRemaining(r);
    });
    return Object.entries(acc).map(([u, v]) => `${fmt(v)} ${u}`).join(' · ');
  }, [sortedRolls]);

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-card via-card to-muted text-foreground" data-testid="wms-fabric-rolls-module">
      {/* Header */}
      <div className="border-b border-foreground/10 bg-black/20 backdrop-blur-sm">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-violet-100 dark:bg-violet-500/20 border border-violet-400 dark:border-violet-500/30">
                <Package className="w-5 h-5 text-violet-600 dark:text-violet-300" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold text-foreground">Fabric Roll Tracking</h1>
                <p className="text-sm text-muted-foreground/60 dark:text-zinc-400 mt-0.5">Tracking kain garment per roll dengan barcode</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleAIAnalysis}
                disabled={aiLoading}
                variant="outline"
                className="border-violet-400 dark:border-violet-500/30 bg-violet-100 dark:bg-violet-500/10 hover:bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-300"
                data-testid="ai-analysis-btn"
              >
                {aiLoading ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Brain className="w-4 h-4 mr-2" />
                )}
                AI Insights
              </Button>
              <Button
                onClick={() => setCreateDialog(true)}
                className="bg-violet-600 hover:bg-violet-700 text-foreground"
                data-testid="create-roll-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Roll Baru
              </Button>
            </div>
          </div>

          {/* Search & Filters */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 dark:text-zinc-500" />
              <Input
                placeholder="Cari roll number, material, color, supplier..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-foreground/5 border-foreground/10 text-foreground"
                data-testid="search-roll-input"
              />
            </div>
            <Select value={filters.qc_status} onValueChange={(v) => setFilters({ ...filters, qc_status: v })}>
              <SelectTrigger className="w-40 bg-foreground/5 border-foreground/10" data-testid="qc-filter">
                <SelectValue placeholder="Semua QC" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua QC</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="pass">Pass</SelectItem>
                <SelectItem value="partial">Partial</SelectItem>
                <SelectItem value="reject">Reject</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={load}
              disabled={loading}
              className="border-foreground/10 hover:bg-foreground/5"
              data-testid="refresh-rolls-btn"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <div className="inline-flex rounded-lg border border-foreground/10 overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="rolls-view-table"
                className={`px-2.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-violet-600 text-white' : 'bg-foreground/5 text-foreground'}`}>
                <Filter size={12} /> Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="rolls-view-grid"
                className={`px-2.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-violet-600 text-white' : 'bg-foreground/5 text-foreground'}`}>
                <Package size={12} /> Kartu
              </button>
            </div>
            <ExportCsvButton filename="stok-kain-per-roll" testId="rolls-export-csv"
              head={CSV_HEAD} rows={csvRows}
              className="h-10 border-foreground/10"
              note={`${remainingBySatuan || '0'} sisa`} />
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={tab} onValueChange={setTab} className="px-6">
          <TabsList className="bg-foreground/5 border-b border-foreground/10 w-full justify-start rounded-none">
            <TabsTrigger value="all" data-testid="tab-all">Semua</TabsTrigger>
            <TabsTrigger value="in_stock" data-testid="tab-in-stock">In Stock</TabsTrigger>
            <TabsTrigger value="partly_issued" data-testid="tab-partly-issued">Sebagian Terpakai</TabsTrigger>
            <TabsTrigger value="fully_issued" data-testid="tab-fully-issued">Habis</TabsTrigger>
            {/* FASE H-5: pekerjaan yang menahan bagian potong */}
            <TabsTrigger value="missing" data-testid="tab-missing-rolls"
              className="data-[state=active]:text-amber-700 dark:data-[state=active]:text-amber-300">
              Penerimaan tanpa roll
              {missing.length > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-semibold"
                  data-testid="missing-rolls-count">{missing.length}</span>
              )}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Rolls List */}
      <div className="flex-1 overflow-auto p-6">
        {tab === 'missing' ? (
          /* ── FASE H-5: penerimaan kain yang belum punya gulungan ─────────────
             Kenapa layar ini penting: kain yang ada di stok tetapi tidak punya
             gulungan akan MENGHENTIKAN Portal Cutting (H-6 mewajibkan gulungan).
             Daftar ini membuat lubangnya kelihatan sebelum bagian potong berhenti. */
          <div className="space-y-3" data-testid="missing-rolls-panel">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 text-amber-600 dark:text-amber-400 shrink-0" />
                <p className="text-xs text-muted-foreground max-w-3xl">
                  Kain yang <strong className="text-foreground">sudah masuk stok</strong> lewat Penerimaan Barang tetapi
                  belum punya satu pun gulungan. Portal Cutting menolak memotong kain tanpa gulungan — terbitkan
                  gulungannya di sini (nomor otomatis{rollPolicy?.next_number ? `, berikutnya ${rollPolicy.next_number}` : ''}).
                </p>
              </div>
              <Button variant="outline" onClick={loadMissing} disabled={missingLoading}
                className="border-foreground/10" data-testid="refresh-missing-btn">
                <RefreshCw className={`w-4 h-4 ${missingLoading ? 'animate-spin' : ''}`} />
              </Button>
            </div>

            {missingLoading ? (
              <div className="flex items-center justify-center h-48">
                <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
              </div>
            ) : missing.length === 0 ? (
              <div className="rounded-xl border border-emerald-300 dark:border-emerald-400/25 bg-emerald-50 dark:bg-emerald-400/10 p-8 text-center"
                data-testid="missing-rolls-empty">
                <CheckCircle2 className="w-9 h-9 mx-auto text-emerald-600 dark:text-emerald-400" />
                <p className="mt-2 font-semibold text-emerald-800 dark:text-emerald-200">
                  Semua penerimaan kain sudah punya gulungan
                </p>
                <p className="text-xs text-emerald-800/80 dark:text-emerald-300/80 mt-1">
                  Tidak ada kain yang menahan bagian potong. Gulungan baru akan lahir sendiri
                  dari Penerimaan Barang berikutnya.
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs" data-testid="missing-rolls-table">
                    <thead className="bg-foreground/10">
                      <tr className="text-left">
                        {['No. Penerimaan', 'Supplier', 'Kode kain', 'Nama kain', 'Qty diterima',
                          'Lokasi', 'Tanggal', 'Aksi'].map((h) => (
                          <th key={h} className="px-2.5 py-2 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {missing.map((m) => (
                        <tr key={m.item_id} className="border-t border-foreground/10 hover:bg-foreground/5"
                          data-testid={`missing-row-${m.material_code}`}>
                          <td className="px-2.5 py-2 font-mono whitespace-nowrap">{m.receipt_number}</td>
                          <td className="px-2.5 py-2">{m.supplier_name || '-'}</td>
                          <td className="px-2.5 py-2 font-mono">{m.material_code}</td>
                          <td className="px-2.5 py-2">{m.material_name}</td>
                          <td className="px-2.5 py-2 tabular-nums whitespace-nowrap">
                            <strong>{fmtQty(m.accepted_qty)}</strong> {m.unit}
                          </td>
                          <td className="px-2.5 py-2">{m.location_name || '-'}</td>
                          <td className="px-2.5 py-2 whitespace-nowrap">{String(m.created_at || '').slice(0, 10)}</td>
                          <td className="px-2.5 py-2 whitespace-nowrap">
                            <Button size="sm" onClick={() => openIssueRolls(m)}
                              className="h-7 bg-amber-600 hover:bg-amber-700 text-white text-xs"
                              data-testid={`issue-rolls-btn-${m.material_code}`}>
                              <Plus className="w-3 h-3 mr-1" /> Terbitkan Roll
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64" data-testid="loading-rolls">
            <Loader2 className="w-8 h-8 animate-spin text-violet-600 dark:text-violet-400" />
          </div>
        ) : filteredRolls.length === 0 ? (
          <EmptyState 
            icon={Package}
            title={search ? 'Tidak ada hasil pencarian' : 'Belum ada data roll'}
            description={search
              ? `Tidak ditemukan roll dengan kata kunci "${search}"`
              : 'Gulungan LAHIR otomatis dari Penerimaan Barang: isi "Rincian Gulungan" pada baris kain, dan nomor roll (RL-YYYYMM-####) diterbitkan sistem. Untuk penerimaan yang sudah lewat, buka tab "Penerimaan tanpa roll".'}
            action={{
              label: 'Buat Roll Manual',
              onClick: () => setCreateDialog(true),
              icon: Plus
            }}
          />
        ) : (
          view === 'table' ? (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5">
              <div className="overflow-x-auto">
                <table className="w-full text-xs" data-testid="rolls-table">
                  <thead className="bg-foreground/10">
                    <tr className="text-left">
                      {[['roll_no', 'No. Roll'], ['material_name', 'Material'],
                        ['color', 'Warna / Lot'], ['supplier_name', 'Supplier'],
                        ['po_no', 'No. PO'], ['qc_status', 'QC'],
                        ['status', 'Status stok'], ['qty_remaining', 'Sisa / Total'],
                        ['uom', 'Satuan'],
                        ['position_barcode', 'Posisi']].map(([k, label]) => (
                        <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                          <button type="button" onClick={() => toggleSort(k)}
                            data-testid={`rolls-sort-${k}`}
                            className="inline-flex items-center gap-1 hover:text-violet-500">
                            {label}
                            <ChevronRight size={10}
                              className={`${sort.key === k ? 'text-violet-500' : 'opacity-40'} ${
                                sort.key === k && sort.dir === 'asc' ? '-rotate-90' : 'rotate-90'}`} />
                          </button>
                        </th>
                      ))}
                      <th className="px-2.5 py-2 font-semibold text-right">Tindakan</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/10">
                    {paged.map((roll) => (
                      <tr key={roll.id} className="hover:bg-foreground/10 cursor-pointer"
                        onClick={() => handleView(roll)}
                        data-testid={`roll-row-${roll.roll_no}`}>
                        <td className="px-2.5 py-2 font-mono whitespace-nowrap">{roll.roll_no}</td>
                        <td className="px-2.5 py-2">
                          {roll.material_name}
                          {roll.material_code && (
                            <span className="text-muted-foreground/60 dark:text-zinc-500 ml-1">
                              ({roll.material_code})
                            </span>
                          )}
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap">
                          {roll.color || '—'} / {roll.color_lot || '—'}
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{roll.supplier_name || '—'}</td>
                        <td className="px-2.5 py-2 font-mono whitespace-nowrap">{roll.po_no || '—'}</td>
                        <td className="px-2.5 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs border ${QC_STATUS[roll.qc_status]?.color || ''}`}>
                            {QC_STATUS[roll.qc_status]?.label || roll.qc_status}
                          </span>
                        </td>
                        <td className="px-2.5 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${STOCK_STATUS[roll.status]?.color || ''}`}>
                            {STOCK_STATUS[roll.status]?.label || roll.status}
                          </span>
                        </td>
                        <td className="px-2.5 py-2 text-right font-mono whitespace-nowrap"
                          data-testid={`roll-qty-${roll.roll_no}`}>
                          {fmt(rollRemaining(roll))} / {fmt(rollTotal(roll))}
                          {roll.qty_remaining_m != null && (
                            <span className="block text-[10px] text-muted-foreground font-sans">
                              ≈ {fmt(roll.qty_remaining_m)} / {fmt(roll.qty_total_m)} m
                            </span>
                          )}
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap" data-testid={`roll-uom-${roll.roll_no}`}>
                          {rollUom(roll)}
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap">
                          {roll.position_barcode || <span className="text-amber-500">belum di-putaway</span>}
                        </td>
                        <td className="px-2.5 py-2 text-right whitespace-nowrap">
                          <div className="inline-flex gap-1">
                            <Button size="sm" variant="outline"
                              className="h-7 px-2 text-xs border-foreground/10"
                              onClick={(e) => { e.stopPropagation(); setPutawayDialog(roll); }}
                              data-testid={`putaway-btn-${roll.roll_no}`}>
                              Put-Away
                            </Button>
                            <Button size="sm" variant="outline"
                              className="h-7 px-2 text-xs border-foreground/10"
                              disabled={roll.status === 'fully_issued'}
                              onClick={(e) => { e.stopPropagation(); setIssueDialog(roll); }}
                              data-testid={`issue-btn-${roll.roll_no}`}>
                              Issue
                            </Button>
                          </div>
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
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {paged.map((roll) => (
              <div
                key={roll.id}
                className="bg-foreground/5 border border-foreground/10 rounded-xl p-4 hover:bg-foreground/10 transition-colors cursor-pointer"
                onClick={() => handleView(roll)}
                data-testid={`roll-card-${roll.roll_no}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <QrCode className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                      <h3 className="font-semibold text-foreground">{roll.roll_no}</h3>
                    </div>
                    <p className="text-sm text-muted-foreground/60 dark:text-zinc-400">{roll.material_name}</p>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    <span className={`px-2 py-0.5 rounded-full text-xs border ${QC_STATUS[roll.qc_status]?.color || ''}`}>
                      {QC_STATUS[roll.qc_status]?.label || roll.qc_status}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-xs ${STOCK_STATUS[roll.status]?.color || ''}`}>
                      {STOCK_STATUS[roll.status]?.label || roll.status}
                    </span>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-500">Color / Lot:</span>
                    <span className="text-foreground">{roll.color || '-'} / {roll.color_lot || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-500">Sisa / Total:</span>
                    <span className="text-foreground font-mono text-right">
                      {fmt(rollRemaining(roll))} / {fmt(rollTotal(roll))} {rollUom(roll)}
                      {roll.qty_remaining_m != null && (
                        <span className="block text-[10px] text-muted-foreground font-sans">
                          ≈ {fmt(roll.qty_remaining_m)} / {fmt(roll.qty_total_m)} m
                        </span>
                      )}
                    </span>
                  </div>
                  {!roll.is_weight && roll.weight_kg > 0 && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground/60 dark:text-zinc-500">Berat:</span>
                      <span className="text-foreground font-mono">{fmt(roll.remaining_kg)} / {fmt(roll.weight_kg)} kg</span>
                    </div>
                  )}
                  {roll.position_barcode && (
                    <div className="flex items-center gap-2 text-xs text-violet-600 dark:text-violet-400">
                      <MapPin className="w-3 h-3" />
                      {roll.position_barcode}
                    </div>
                  )}
                </div>

                <div className="mt-3 pt-3 border-t border-foreground/10 flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 border-foreground/10 hover:bg-foreground/5 text-xs"
                    onClick={(e) => { e.stopPropagation(); setPutawayDialog(roll); }}
                    data-testid={`putaway-btn-${roll.roll_no}`}
                  >
                    <ArrowRightLeft className="w-3 h-3 mr-1" />
                    Put-Away
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 border-foreground/10 hover:bg-foreground/5 text-xs"
                    onClick={(e) => { e.stopPropagation(); setIssueDialog(roll); }}
                    disabled={roll.status === 'fully_issued'}
                    data-testid={`issue-btn-${roll.roll_no}`}
                  >
                    <Truck className="w-3 h-3 mr-1" />
                    Issue
                  </Button>
                </div>
              </div>
            ))}
          </div>
          )
        )}
        {view === 'grid' && !loading && sortedRolls.length > 0 && (
          <PaginationLite page={page} totalPages={totalPages} total={total}
            pageSize={pageSize} onPageChange={setPage} />
        )}
      </div>

      {/* Create Roll Dialog */}
      <Dialog open={createDialog} onOpenChange={setCreateDialog}>
        <DialogContent className="bg-card text-foreground border-foreground/10 max-w-2xl" data-testid="create-roll-dialog">
          <DialogHeader>
            <DialogTitle>Buat Roll Baru</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateRoll}>
            <div className="grid grid-cols-2 gap-4 py-4">
              <div>
                <Label>Nomor Roll</Label>
                <div className="h-10 px-3 rounded-md border border-violet-300 dark:border-violet-400/30 bg-violet-50 dark:bg-violet-400/10 flex items-center justify-between"
                  data-testid="roll-no-auto">
                  <span className="font-mono text-sm text-violet-800 dark:text-violet-200">
                    {rollPolicy?.next_number || 'RL-…'}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-violet-700 dark:text-violet-300">otomatis</span>
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Pola {rollPolicy?.format || 'RL-{YYYY}{MM}-{SEQ:4}'} — diatur di Administrasi Sistem → Penomoran Dokumen.
                </p>
              </div>
              <div>
                <Label>Material Code</Label>
                <Input name="material_code" className="bg-foreground/5 border-foreground/10" data-testid="input-material-code" />
              </div>
              <div className="col-span-2">
                <Label>Material Name *</Label>
                <Input name="material_name" required className="bg-foreground/5 border-foreground/10" data-testid="input-material-name" />
              </div>
              <div>
                <Label>Color</Label>
                <Input name="color" className="bg-foreground/5 border-foreground/10" data-testid="input-color" />
              </div>
              <div>
                <Label>Color Lot</Label>
                <Input name="color_lot" className="bg-foreground/5 border-foreground/10" data-testid="input-color-lot" />
              </div>
              <div>
                <Label>Supplier Name</Label>
                <Input name="supplier_name" className="bg-foreground/5 border-foreground/10" data-testid="input-supplier" />
              </div>
              <div>
                <Label>PO Number</Label>
                <Input name="po_no" className="bg-foreground/5 border-foreground/10" data-testid="input-po-no" />
              </div>
              <div>
                <Label>Satuan</Label>
                <Select name="uom" defaultValue="meter">
                  <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="input-uom">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="meter">Meter</SelectItem>
                    <SelectItem value="yard">Yard</SelectItem>
                    <SelectItem value="rol">Rol</SelectItem>
                    <SelectItem value="gulung">Gulung</SelectItem>
                    <SelectItem value="kg">Kilogram</SelectItem>
                    <SelectItem value="bal">Bal</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Panjang / Jumlah (sesuai satuan)</Label>
                <Input name="length_m" type="number" step="0.01" defaultValue="0" className="bg-foreground/5 border-foreground/10" data-testid="input-length" />
              </div>
              <div>
                <Label>Weight (kg)</Label>
                <Input name="weight_kg" type="number" step="0.01" defaultValue="0" className="bg-foreground/5 border-foreground/10" data-testid="input-weight" />
              </div>
              <div>
                <Label>Unit Cost</Label>
                <Input name="unit_cost" type="number" step="0.01" defaultValue="0" className="bg-foreground/5 border-foreground/10" data-testid="input-unit-cost" />
              </div>
              <div className="col-span-2">
                <Label>Notes</Label>
                <Input name="notes" className="bg-foreground/5 border-foreground/10" data-testid="input-notes" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateDialog(false)} className="border-foreground/10">
                Batal
              </Button>
              <Button type="submit" className="bg-violet-600 hover:bg-violet-700" data-testid="submit-create-roll">
                <Save className="w-4 h-4 mr-2" />
                Simpan
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── FASE H-5: terbitkan gulungan untuk penerimaan yang sudah lewat ───── */}
      {issueRollsDialog && (
        <Dialog open onOpenChange={() => setIssueRollsDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10 max-w-3xl" data-testid="issue-rolls-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Package className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                Terbitkan Gulungan — {issueRollsDialog.row.material_code}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-muted-foreground">Penerimaan</p>
                  <p className="font-mono text-foreground">{issueRollsDialog.row.receipt_number}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Supplier</p>
                  <p className="text-foreground">{issueRollsDialog.row.supplier_name || '-'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Kain</p>
                  <p className="text-foreground">{issueRollsDialog.row.material_name}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Qty diterima</p>
                  <p className="text-foreground font-semibold tabular-nums">
                    {fmtQty(issueRollsDialog.row.accepted_qty)} {issueRollsDialog.row.unit}
                  </p>
                </div>
              </div>

              <RollLinesEditor
                lines={issueRollsDialog.lines}
                accepted={issueRollsDialog.row.accepted_qty}
                unit={issueRollsDialog.row.unit}
                onChange={(lines) => setIssueRollsDialog((d) => ({ ...d, lines }))}
                testPrefix="backfill-roll-lines"
                nextNumberHint={rollPolicy?.next_number || ''}
                title="Rincian Gulungan (retroaktif)"
                subtitle={`Timbang/ukur gulungan yang ada di rak sekarang. Totalnya harus sama dengan qty yang dulu diterima (${fmtQty(issueRollsDialog.row.accepted_qty)} ${issueRollsDialog.row.unit}) — gulungan dan stok harus menjelaskan penerimaan yang sama.`}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setIssueRollsDialog(null)}
                className="border-foreground/10">Batal</Button>
              <Button type="button" onClick={submitIssueRolls} disabled={issuing}
                className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="submit-issue-rolls">
                {issuing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                Terbitkan Gulungan
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* View Dialog */}
      {viewDialog && (
        <Dialog open={!!viewDialog} onOpenChange={() => setViewDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10 max-w-3xl" data-testid="view-roll-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <QrCode className="w-5 h-5 text-violet-600 dark:text-violet-400" />
                Roll {viewDialog.roll?.roll_no}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Material:</span>
                  <p className="text-foreground font-medium">{viewDialog.roll?.material_name}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Color / Lot:</span>
                  <p className="text-foreground font-medium">{viewDialog.roll?.color || '-'} / {viewDialog.roll?.color_lot || '-'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Supplier:</span>
                  <p className="text-foreground font-medium">{viewDialog.roll?.supplier_name || '-'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">PO Number:</span>
                  <p className="text-foreground font-medium">{viewDialog.roll?.po_no || '-'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Sisa:</span>
                  <p className="text-foreground font-medium tabular-nums" data-testid="roll-detail-qty">
                    {fmt(rollRemaining(viewDialog.roll))} / {fmt(rollTotal(viewDialog.roll))} {rollUom(viewDialog.roll)}
                    {viewDialog.roll?.qty_remaining_m != null && (
                      <span className="block text-[11px] text-muted-foreground font-normal">
                        ≈ {fmt(viewDialog.roll.qty_remaining_m)} / {fmt(viewDialog.roll.qty_total_m)} m
                      </span>
                    )}
                  </p>
                </div>
                <div>
                  {/* FASE H-5: asal gulungan — jejak balik ke penerimaan yang melahirkannya */}
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Asal gulungan:</span>
                  <p className="text-foreground font-medium">
                    {viewDialog.roll?.source_receipt_number
                      ? <span className="font-mono">Penerimaan {viewDialog.roll.source_receipt_number}</span>
                      : 'dibuat manual di layar Roll Kain'}
                  </p>
                </div>
              </div>

              <div className="border-t border-foreground/10 pt-4">
                <h3 className="text-sm font-medium mb-3 text-muted-foreground/60 dark:text-zinc-400">Movement History</h3>
                {viewDialog.movements?.length === 0 ? (
                  <p className="text-muted-foreground/60 text-sm">Belum ada pergerakan</p>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-auto">
                    {viewDialog.movements?.map((m, i) => (
                      <div key={i} className="bg-foreground/5 border border-foreground/10 rounded p-3 text-sm">
                        <div className="flex justify-between mb-1">
                          <span className="font-medium text-violet-600 dark:text-violet-400">{m.movement_type}</span>
                          <span className="text-muted-foreground/60 dark:text-zinc-500">{new Date(m.created_at).toLocaleString('id-ID')}</span>
                        </div>
                        <p className="text-muted-foreground/60 dark:text-zinc-400">Qty: {fmt(m.qty)} {m.unit} - {m.notes || 'No notes'}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Put-Away Dialog */}
      {putawayDialog && (
        <Dialog open={!!putawayDialog} onOpenChange={() => setPutawayDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10" data-testid="putaway-dialog">
            <DialogHeader>
              <DialogTitle>Put-Away Roll {putawayDialog.roll_no}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handlePutaway}>
              <div className="space-y-4 py-4">
                <div>
                  <Label>Position ID *</Label>
                  <Input name="position_id" required className="bg-foreground/5 border-foreground/10" data-testid="input-position-id" />
                </div>
                <div>
                  <Label>Position Barcode</Label>
                  <Input name="position_barcode" className="bg-foreground/5 border-foreground/10" data-testid="input-position-barcode" />
                </div>
                <div>
                  <Label>Notes</Label>
                  <Input name="notes" className="bg-foreground/5 border-foreground/10" data-testid="input-putaway-notes" />
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setPutawayDialog(null)} className="border-foreground/10">
                  Batal
                </Button>
                <Button type="submit" className="bg-violet-600 hover:bg-violet-700" data-testid="submit-putaway">
                  Simpan
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}

      {/* Issue Dialog */}
      {issueDialog && (
        <Dialog open={!!issueDialog} onOpenChange={() => setIssueDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10" data-testid="issue-dialog">
            <DialogHeader>
              <DialogTitle>Issue Roll {issueDialog.roll_no}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleIssue}>
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Qty *</Label>
                    <Input name="qty" type="number" step="0.01" required className="bg-foreground/5 border-foreground/10" data-testid="input-issue-qty" />
                  </div>
                  <div>
                    <Label>Satuan gulungan</Label>
                    {/* Gulungan hanya bisa dikeluarkan dalam satuannya sendiri —
                        dulu pilihan meter/kg di sini membuat gulungan yard
                        terkurangi dengan label yang salah. */}
                    <Input value={rollUom(issueDialog)} readOnly
                      className="bg-foreground/5 border-foreground/10 font-mono"
                      data-testid="input-issue-unit" />
                  </div>
                </div>
                <div>
                  <Label>Reference Type</Label>
                  <Select name="reference_type" defaultValue="wo">
                    <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="input-ref-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="wo">Work Order</SelectItem>
                      <SelectItem value="cmt">CMT</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Reference No</Label>
                  <Input name="reference_no" className="bg-foreground/5 border-foreground/10" data-testid="input-ref-no" />
                </div>
                <div>
                  <Label>Notes</Label>
                  <Input name="notes" className="bg-foreground/5 border-foreground/10" data-testid="input-issue-notes" />
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setIssueDialog(null)} className="border-foreground/10">
                  Batal
                </Button>
                <Button type="submit" className="bg-violet-600 hover:bg-violet-700" data-testid="submit-issue">
                  Issue
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
      
      {/* AI Analysis Dialog */}
      {aiAnalysisDialog && (
        <Dialog open={!!aiAnalysisDialog} onOpenChange={() => setAiAnalysisDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10 max-w-4xl max-h-[85vh] overflow-auto" data-testid="ai-analysis-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-violet-600 dark:text-violet-400" />
                🤖 AI Quality Pattern Analysis
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {/* Summary Stats */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-500/20 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-1">Total Rejections</div>
                  <div className="text-2xl font-bold text-violet-600 dark:text-violet-300">{aiAnalysisDialog.data_summary?.total_rejections || 0}</div>
                </div>
                <div className="bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-500/20 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-1">Affected Suppliers</div>
                  <div className="text-2xl font-bold text-violet-600 dark:text-violet-300">{aiAnalysisDialog.data_summary?.affected_suppliers || 0}</div>
                </div>
                <div className="bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-500/20 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-1">Period</div>
                  <div className="text-2xl font-bold text-violet-600 dark:text-violet-300">{aiAnalysisDialog.data_summary?.period_days || 30} hari</div>
                </div>
              </div>

              {/* AI Analysis Content */}
              <div className="bg-foreground/5 border border-foreground/10 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                  <h3 className="font-semibold text-foreground">AI Analysis Results</h3>
                </div>
                <div className="prose prose-invert prose-sm max-w-none">
                  <div className="whitespace-pre-wrap text-foreground/80 leading-relaxed">
                    {aiAnalysisDialog.analysis}
                  </div>
                </div>
              </div>

              {/* Timestamp */}
              <div className="text-xs text-muted-foreground/60 dark:text-zinc-500 text-center">
                Generated at: {new Date(aiAnalysisDialog.generated_at).toLocaleString('id-ID')}
              </div>
            </div>
            <DialogFooter>
              <Button 
                onClick={() => setAiAnalysisDialog(null)} 
                className="bg-violet-600 hover:bg-violet-700"
                data-testid="close-ai-dialog"
              >
                Tutup
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
