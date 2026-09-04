/**
 * WMS Delivery Notes — Surat Jalan PDF Generator
 * P0-WH-2: Create, issue, and download PDF delivery notes
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  FileText, Plus, RefreshCw, Eye, Download, Truck, X, Save, Edit2,
  CheckCircle2, XCircle, Loader2, Search, Calendar, User, Package, Layers,
  ChevronRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { EmptyState } from './EmptyState';
import OnwardCTA from './OnwardCTA';
import ExportCsvButton from '@/components/ui/export-csv-button';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

/* F13 (sesi #11) — Surat Jalan sudah punya pencarian, tab, dan paginasi, tetapi
   hanya bisa dibaca sebagai KARTU dan TIDAK bisa diunduh. Dua pertanyaan harian
   gudang karena itu tidak terjawab: "SJ mana yang masih DRAFT paling lama?"
   (butuh urutan) dan "kirim rekap kiriman minggu ini" (butuh unduhan; PDF hanya
   per satu SJ). Rekap yang tidak bisa diunduh berakhir diketik ulang. */
const CSV_HEAD = ['No. SJ', 'Jenis', 'Status', 'Penerima', 'Alamat', 'No. HP',
  'Pengirim', 'No. Kendaraan', 'Jumlah item', 'Dibuat'];
// FASE H-7 — kolom untuk daftar LINTAS SUMBER (gudang + vendor CMT + buyer)
const CSV_HEAD_ALL = ['No. Surat Jalan', 'Sumber', 'Jenis', 'Tanggal', 'Tujuan',
  'Acuan (PO/Ref)', 'Status', 'Jumlah baris', 'Total qty'];
const SJ_VIEW_KEY = 'wms_delivery_notes_view';

const SOURCE_BADGE = {
  gudang: { label: 'Gudang', cls: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30' },
  vendor: { label: 'Vendor CMT', cls: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-500/30' },
  buyer: { label: 'Buyer', cls: 'bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-500/30' },
};
const fmtQty = (n) => Number(n || 0).toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const API = process.env.REACT_APP_BACKEND_URL;

const SJ_TYPES = {
  'SJ-CMT': { label: 'CMT', color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300' },
  'SJ-MAKLON': { label: 'Maklon', color: 'bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-300' },
  'SJ-SUPPLIER': { label: 'Supplier Return', color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300' },
  'SJ-INTERNAL': { label: 'Internal Transfer', color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300' },
  'SJ-ONLINE': { label: 'Online Shop', color: 'bg-pink-100 dark:bg-pink-500/20 text-pink-600 dark:text-pink-300' },
};

const STATUS_COLORS = {
  draft: 'bg-muted dark:bg-zinc-500/20 text-foreground/80',
  issued: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300',
  received: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300',
  cancelled: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300',
};

export default function WMSDeliveryNotesModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(false);
  // SESI #19 — kebijakan penomoran Surat Jalan Gudang (Otomatis/Manual) dibaca dari
  // Administrasi Sistem → Penomoran Dokumen supaya layar & backend tidak bisa berbeda.
  const [sjType, setSjType] = useState('');
  const numPolicy = useDocNumberPolicy('wh_delivery_notes.sj_number', token,
    // {TIPE} ikut menentukan nomor, jadi pratinjaunya harus memakai tipe yang
    // BENAR-BENAR dipilih — bukan token contoh "TIP".
    useMemo(() => ({ TIPE: sjType }), [sjType]));
  const [sjNumber, setSjNumber] = useState('');
  const [tab, setTab] = useState('sources');
  // ── FASE H-7: daftar surat jalan LINTAS SUMBER ────────────────────────────
  // Sebelum ini layar ini hanya membaca `wh_delivery_notes` (2 dokumen demo),
  // sementara surat jalan operasional hidup di `vendor_shipments` (kirim material
  // ke CMT) dan `buyer_shipments` (dispatch ke buyer). Orang gudang harus membuka
  // tiga layar di dua portal untuk menjawab "surat jalan apa saja yang keluar?".
  const [allRows, setAllRows] = useState([]);
  const [allMeta, setAllMeta] = useState({ total: 0, by_source: {}, total_qty: 0 });
  const [allLoading, setAllLoading] = useState(false);
  const [srcFilter, setSrcFilter] = useState('all');
  const [range, setRange] = useState({ from: '', to: '' });
  const [search, setSearch] = useState('');
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(SJ_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  // Default: SJ paling BARU di atas (yang sedang dikerjakan gudang hari ini).
  const [sort, setSort] = useState({ key: 'created_at', dir: 'desc' });
  useEffect(() => {
    try { localStorage.setItem(SJ_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  const [createDialog, setCreateDialog] = useState(false);
  const [viewDialog, setViewDialog] = useState(null);
  const [editingLines, setEditingLines] = useState([{ line_no: 1, description: '', qty: 0, unit: 'pcs', remarks: '' }]);
  // FASE P4: auto-isi Surat Jalan Internal dari BOM aktif (yarn + aksesoris) x qty job
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [bomLoading, setBomLoading] = useState(false);

  const loadJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/production-jobs?business_type=internal`, { headers });
      const d = await r.json();
      const list = Array.isArray(d) ? d : (d.items || []);
      setJobs(list);
    } catch {
      /* silent — dropdown BOM opsional */
    }
  }, [headers]);

  useEffect(() => { if (createDialog) loadJobs(); }, [createDialog, loadJobs]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (!['all', 'sources'].includes(tab)) params.set('status', tab);
      const r = await fetch(`${API}/api/wms/delivery-notes?${params}`, { headers });
      const d = await r.json();
      setNotes(d.items || []);
    } catch {
      toast.error('Gagal memuat surat jalan');
    } finally {
      setLoading(false);
    }
  }, [headers, search, tab]);

  useEffect(() => { load(); }, [load]);

  // FASE H-7: satu daftar lintas sumber (read-only) — dipakai tab "Semua Sumber".
  const loadAllSources = useCallback(async () => {
    setAllLoading(true);
    try {
      const p = new URLSearchParams();
      if (srcFilter && srcFilter !== 'all') p.set('source', srcFilter);
      if (search) p.set('q', search);
      if (range.from) p.set('date_from', range.from);
      if (range.to) p.set('date_to', range.to);
      const r = await fetch(`${API}/api/wms/delivery-notes/sources?${p}`, { headers });
      const d = await r.json();
      setAllRows(d.items || []);
      setAllMeta({ total: d.total || 0, by_source: d.by_source || {}, total_qty: d.total_qty || 0 });
    } catch {
      toast.error('Gagal memuat daftar surat jalan lintas sumber');
    } finally {
      setAllLoading(false);
    }
  }, [headers, srcFilter, search, range.from, range.to]);

  useEffect(() => { if (tab === 'sources') loadAllSources(); }, [tab, loadAllSources]);

  // Unduh PDF dokumen asli (bukan generator kedua) — nomor & isi tetap milik sumbernya.
  const downloadFromUrl = async (url, filename) => {
    try {
      const r = await fetch(`${API}${url}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) {
        const t = await r.text().catch(() => '');
        throw new Error(t.slice(0, 160) || `HTTP ${r.status}`);
      }
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      window.URL.revokeObjectURL(a.href);
      toast.success(`PDF ${filename} diunduh`);
    } catch (e) {
      toast.error(`Gagal mengunduh PDF: ${e.message}`, { duration: 8000 });
    }
  };

  const downloadRecap = () => {
    const p = new URLSearchParams();
    if (srcFilter && srcFilter !== 'all') p.set('source', srcFilter);
    if (search) p.set('q', search);
    if (range.from) p.set('date_from', range.from);
    if (range.to) p.set('date_to', range.to);
    downloadFromUrl(`/api/wms/delivery-notes/sources/recap-pdf?${p}`,
      `rekap-surat-jalan-${range.from || 'semua'}.pdf`);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = {
      sj_type: sjType || fd.get('sj_type'),
      ...docNumberPayload(numPolicy, 'sj_number', sjNumber),
      recipient_name: fd.get('recipient_name'),
      recipient_address: fd.get('recipient_address'),
      recipient_phone: fd.get('recipient_phone') || '',
      shipper_name: fd.get('shipper_name') || '',
      vehicle_no: fd.get('vehicle_no') || '',
      notes: fd.get('notes') || '',
      lines: editingLines.filter(l => l.description),
    };
    try {
      const r = await fetch(`${API}/api/wms/delivery-notes`, { method: 'POST', headers, body: JSON.stringify(data) });
      // SESI #19 — DULU semua kegagalan jadi satu pesan buta ("Gagal membuat surat
      // jalan"). Dengan penomoran yang ditegakkan, penolakan justru berisi jalan
      // keluarnya (pola nomor yang benar / nomor yang akan dipakai) — menelannya
      // membuat pemakai mencoba berulang tanpa tahu apa yang salah.
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d?.detail || 'Gagal membuat surat jalan');
      toast.success('Surat jalan berhasil dibuat');
      setCreateDialog(false);
      setSjNumber('');
      setSjType('');
      setEditingLines([{ line_no: 1, description: '', qty: 0, unit: 'pcs', remarks: '' }]);
      setSelectedJobId('');
      load();
    } catch (err) {
      toast.error(err?.message || 'Gagal membuat surat jalan');
    }
  };

  const handleIssue = async (id) => {
    try {
      const r = await fetch(`${API}/api/wms/delivery-notes/${id}/issue`, { method: 'POST', headers, body: JSON.stringify({}) });
      if (!r.ok) throw new Error();
      toast.success('Surat jalan berhasil di-issue');
      load();
    } catch {
      toast.error('Gagal issue surat jalan');
    }
  };

  const handleReceive = async (id) => {
    try {
      const r = await fetch(`${API}/api/wms/delivery-notes/${id}/receive`, {
        method: 'POST', headers, body: JSON.stringify({ received_by: '' }),
      });
      if (!r.ok) throw new Error();
      toast.success('Surat jalan dikonfirmasi diterima');
      load();
    } catch {
      toast.error('Gagal konfirmasi terima surat jalan');
    }
  };

  const handleDownloadPDF = async (id) => {
    try {
      const r = await fetch(`${API}/api/wms/delivery-notes/${id}/pdf`, { headers });
      if (!r.ok) throw new Error();
      const blob = await r.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `SJ-${id}.pdf`;
      a.click();
      toast.success('PDF berhasil didownload');
    } catch {
      toast.error('Gagal download PDF');
    }
  };

  const addLine = () => {
    setEditingLines([...editingLines, { line_no: editingLines.length + 1, description: '', qty: 0, unit: 'pcs', remarks: '' }]);
  };

  // FASE P4: ambil baris material dari BOM aktif job internal & append ke item pengiriman.
  // Qty sudah otomatis = qty BOM per unit x qty job (dihitung di backend).
  const handleFillFromBOM = async () => {
    if (!selectedJobId) { toast.error('Pilih job produksi internal dulu'); return; }
    setBomLoading(true);
    try {
      const r = await fetch(`${API}/api/production-jobs/${selectedJobId}/bom-material-lines`, { headers });
      if (!r.ok) throw new Error();
      const d = await r.json();
      const bomLines = d.lines || [];
      if (bomLines.length === 0) {
        toast.warning('Tidak ada baris BOM untuk job ini (BOM belum aktif / item tanpa BOM)');
        return;
      }
      // Append: pertahankan baris terisi yang sudah ada, lalu tambahkan baris BOM, nomori ulang
      setEditingLines((prev) => {
        const existing = prev.filter((l) => l.description && l.description.trim());
        const merged = [
          ...existing,
          ...bomLines.map((l) => ({
            description: l.description, qty: l.qty, unit: l.unit, remarks: l.remarks || '',
          })),
        ];
        return merged.map((l, i) => ({ ...l, line_no: i + 1 }));
      });
      toast.success(`${bomLines.length} baris material BOM ditambahkan (Job ${d.job_number || ''})`);
      if (Array.isArray(d.missing_bom) && d.missing_bom.length > 0) {
        toast.warning(`${d.missing_bom.length} item job tidak punya BOM aktif dan dilewati`);
      }
    } catch {
      toast.error('Gagal mengambil baris BOM job');
    } finally {
      setBomLoading(false);
    }
  };

  const removeLine = (idx) => {
    setEditingLines(editingLines.filter((_, i) => i !== idx));
  };

  const updateLine = (idx, field, value) => {
    const updated = [...editingLines];
    updated[idx][field] = value;
    setEditingLines(updated);
  };

  const filteredNotes = useMemo(() => {
    const base = tab === 'all' ? notes : notes.filter(n => n.status === tab);
    const list = [...base];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = key === 'lines' ? (a?.lines?.length || 0) : a?.[key];
      const bv = key === 'lines' ? (b?.lines?.length || 0) : b?.[key];
      const num = key === 'lines';
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [notes, tab, sort]);

  // RC-UI-03: client-side pagination (10/hal)
  const { page, setPage, totalPages, total, paged } = useClientPagination(filteredNotes, 10);

  // F13 — yang diunduh = baris YANG TERLIHAT (sesudah tab + pencarian).
  const csvRows = filteredNotes.map((n) => [
    n.sj_number, SJ_TYPES[n.sj_type]?.label || n.sj_type, n.status,
    n.recipient_name, n.recipient_address, n.recipient_phone || '',
    n.shipper_name || '', n.vehicle_no || '', (n.lines?.length || 0),
    n.created_at ? String(n.created_at).slice(0, 10) : '',
  ]);

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-card via-card to-muted text-foreground" data-testid="wms-delivery-notes-module">
      {/* Header */}
      <div className="border-b border-foreground/10 bg-black/20 backdrop-blur-sm">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-100 dark:bg-emerald-500/20 border border-emerald-400 dark:border-emerald-500/30">
                <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-300" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold text-foreground">Surat Jalan</h1>
                <p className="text-sm text-muted-foreground/60 dark:text-zinc-400 mt-0.5">Generate PDF delivery notes untuk pengiriman</p>
              </div>
            </div>
            <Button
              onClick={() => setCreateDialog(true)}
              className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
              data-testid="create-sj-btn"
            >
              <Plus className="w-4 h-4 mr-2" />
              Surat Jalan Baru
            </Button>
          </div>

          {/* Search & Filters */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 dark:text-zinc-500" />
              <Input
                placeholder="Cari nomor SJ, penerima..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-foreground/5 border-foreground/10 text-foreground"
                data-testid="search-sj-input"
              />
            </div>
            <Button
              variant="outline"
              onClick={load}
              disabled={loading}
              className="border-foreground/10 hover:bg-foreground/5"
              data-testid="refresh-sj-btn"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <ExportCsvButton filename="surat-jalan" testId="sj-export-csv"
              head={CSV_HEAD} rows={csvRows}
              className="h-10 border-foreground/10"
              note={`${filteredNotes.length} surat jalan`} />
            <div className="inline-flex rounded-lg border border-foreground/10 overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="sj-view-table"
                className={`px-2.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-emerald-600 text-white' : 'bg-foreground/5 text-foreground'}`}>
                Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="sj-view-grid"
                className={`px-2.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-emerald-600 text-white' : 'bg-foreground/5 text-foreground'}`}>
                Kartu
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={tab} onValueChange={setTab} className="px-6">
          <TabsList className="bg-foreground/5 border-b border-foreground/10 w-full justify-start rounded-none">
            {/* FASE H-7 — pintu utama: SATU daftar lintas sumber */}
            <TabsTrigger value="sources" data-testid="tab-all-sources">
              Semua Sumber
              {allMeta.total > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-emerald-600 text-white text-[10px] font-semibold"
                  data-testid="all-sources-count">{allMeta.total}</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="all" data-testid="tab-all">SJ Gudang</TabsTrigger>
            <TabsTrigger value="draft" data-testid="tab-draft">Draft</TabsTrigger>
            <TabsTrigger value="issued" data-testid="tab-issued">Issued</TabsTrigger>
            <TabsTrigger value="received" data-testid="tab-received">Received</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Delivery Notes List */}
      <div className="flex-1 overflow-auto p-6">
        {tab === 'sources' ? (
          /* ── FASE H-7: SATU DAFTAR SURAT JALAN LINTAS SUMBER ───────────────
             Read-only: tiap baris mencetak PDF RESMI dari dokumen aslinya dan bisa
             dibuka di modul sumbernya. Tidak ada nomor baru & tidak ada generator
             PDF kedua — surat jalan tetap milik sumbernya masing-masing. */
          <div className="space-y-4" data-testid="sj-all-sources-panel">
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-3 flex flex-wrap items-end gap-3">
              <div>
                <Label className="text-[11px] text-muted-foreground">Sumber</Label>
                <div className="flex gap-1 mt-1">
                  {[['all', `Semua (${allMeta.total})`],
                    ['gudang', `Gudang (${allMeta.by_source?.gudang ?? 0})`],
                    ['vendor', `Vendor CMT (${allMeta.by_source?.vendor ?? 0})`],
                    ['buyer', `Buyer (${allMeta.by_source?.buyer ?? 0})`]].map(([k, lbl]) => (
                    <button key={k} type="button" onClick={() => setSrcFilter(k)}
                      className={`h-8 px-2.5 rounded-lg text-xs border ${srcFilter === k
                        ? 'bg-emerald-600 text-white border-emerald-600'
                        : 'bg-foreground/5 text-foreground border-foreground/10 hover:bg-foreground/10'}`}
                      data-testid={`sj-src-${k}`}>
                      {lbl}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <Label className="text-[11px] text-muted-foreground">Dari tanggal</Label>
                <Input type="date" value={range.from}
                  onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
                  className="h-8 w-40 bg-foreground/5 border-foreground/10" data-testid="sj-date-from" />
              </div>
              <div>
                <Label className="text-[11px] text-muted-foreground">Sampai tanggal</Label>
                <Input type="date" value={range.to}
                  onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
                  className="h-8 w-40 bg-foreground/5 border-foreground/10" data-testid="sj-date-to" />
              </div>
              <div className="flex items-center gap-2 ml-auto">
                <Button variant="outline" onClick={loadAllSources} disabled={allLoading}
                  className="h-8 border-foreground/10" data-testid="sj-all-refresh">
                  <RefreshCw className={`w-4 h-4 ${allLoading ? 'animate-spin' : ''}`} />
                </Button>
                <ExportCsvButton filename="surat-jalan-semua-sumber" testId="sj-all-export-csv"
                  head={CSV_HEAD_ALL}
                  rows={allRows.map((r) => [r.number, r.source_label, r.doc_type,
                    (r.date || '').slice(0, 10), r.recipient, r.reference || '', r.status,
                    r.lines, r.qty])}
                  className="h-8 border-foreground/10"
                  note={`${allRows.length} surat jalan`} />
                <Button onClick={downloadRecap} className="h-8 bg-emerald-600 hover:bg-emerald-700 text-white"
                  data-testid="sj-recap-pdf">
                  <Download className="w-4 h-4 mr-1.5" /> Cetak Rekap
                </Button>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Satu daftar untuk tiga sumber: <b className="text-foreground">Gudang</b> (surat jalan internal/manual),{' '}
              <b className="text-foreground">Vendor CMT</b> (kirim material), dan{' '}
              <b className="text-foreground">Buyer</b> (tiap pengiriman bertahap = satu baris).
              Total {fmtQty(allMeta.total_qty)} qty pada {allMeta.total} dokumen. Tombol PDF mengunduh
              dokumen RESMI dari sumbernya — nomornya tidak dibuat ulang di sini.
            </p>

            {allLoading ? (
              <div className="space-y-2" data-testid="sj-all-loading">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : allRows.length === 0 ? (
              <EmptyState icon={FileText} title="Tidak ada surat jalan pada filter ini"
                description="Ubah filter sumber / rentang tanggal, atau buat surat jalan gudang baru." />
            ) : (
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs" data-testid="sj-all-sources-table">
                    <thead className="bg-foreground/10">
                      <tr className="text-left">
                        {['No. Surat Jalan', 'Sumber', 'Jenis', 'Tanggal', 'Tujuan', 'Acuan',
                          'Status', 'Baris', 'Total qty', 'Tindakan'].map((h) => (
                          <th key={h} className="px-2.5 py-2 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {allRows.map((r) => {
                        const b = SOURCE_BADGE[r.source] || SOURCE_BADGE.gudang;
                        return (
                          <tr key={r.key} className="border-t border-foreground/10 hover:bg-foreground/5"
                            data-testid={`sj-all-row-${r.number}`}>
                            <td className="px-2.5 py-2 font-mono whitespace-nowrap">{r.number}</td>
                            <td className="px-2.5 py-2">
                              <span className={`px-1.5 py-0.5 rounded-full border text-[10px] font-semibold ${b.cls}`}>
                                {b.label}
                              </span>
                            </td>
                            <td className="px-2.5 py-2 whitespace-nowrap">{r.doc_type}</td>
                            <td className="px-2.5 py-2 whitespace-nowrap">{(r.date || '').slice(0, 10) || '-'}</td>
                            <td className="px-2.5 py-2">{r.recipient || '-'}</td>
                            <td className="px-2.5 py-2 font-mono">{r.reference || '-'}</td>
                            <td className="px-2.5 py-2 whitespace-nowrap">{r.status || '-'}</td>
                            <td className="px-2.5 py-2 text-right tabular-nums">{r.lines}</td>
                            <td className="px-2.5 py-2 text-right tabular-nums">{fmtQty(r.qty)}</td>
                            <td className="px-2.5 py-2 whitespace-nowrap">
                              <button type="button"
                                onClick={() => downloadFromUrl(r.pdf_url, `${(r.number || 'surat-jalan').replace(/[/#]/g, '-')}.pdf`)}
                                className="text-emerald-700 dark:text-emerald-400 hover:underline mr-2 inline-flex items-center gap-1"
                                data-testid={`sj-all-pdf-${r.number}`}>
                                <Download className="w-3 h-3" /> PDF
                              </button>
                              {r.pdf_alt_url && (
                                <button type="button"
                                  onClick={() => downloadFromUrl(r.pdf_alt_url, `${(r.number || 'sj').replace(/[/#]/g, '-')}-kumulatif.pdf`)}
                                  className="text-blue-700 dark:text-blue-400 hover:underline mr-2"
                                  data-testid={`sj-all-pdf-alt-${r.number}`}>
                                  {r.pdf_alt_label || 'PDF kumulatif'}
                                </button>
                              )}
                              {onNavigate && (
                                <button type="button" onClick={() => onNavigate(r.module)}
                                  className="text-muted-foreground hover:underline inline-flex items-center gap-0.5"
                                  data-testid={`sj-all-open-${r.number}`}>
                                  Buka sumber <ChevronRight className="w-3 h-3" />
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
        <OnwardCTA
          onNavigate={onNavigate}
          title="Setelah Surat Jalan Terbit"
          className="mb-4"
          actions={[
            { module: 'wms-stock-hub', label: 'Lihat Stok Terkini', icon: Package, primary: true, hint: 'Cek posisi stok setelah barang keluar gudang' },
          ]}
        />
        {loading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="loading-sj">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="border border-foreground/10 rounded-xl p-4 space-y-3">
                <div className="flex justify-between">
                  <Skeleton className="h-5 w-28" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-4 w-44" />
                <Skeleton className="h-4 w-32" />
                <div className="flex gap-2 pt-1">
                  <Skeleton className="h-7 w-20" />
                  <Skeleton className="h-7 w-20" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredNotes.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="Belum ada surat jalan"
            description="Surat jalan akan muncul di sini setelah dibuat. Klik 'Buat Surat Jalan' untuk memulai."
            data-testid="empty-sj"
          />
        ) : (
          view === 'table' ? (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5">
              <div className="overflow-x-auto">
                <table className="w-full text-xs" data-testid="sj-table">
                  <thead className="bg-foreground/10">
                    <tr className="text-left">
                      {[['sj_number', 'No. SJ'], ['sj_type', 'Jenis'], ['status', 'Status'],
                        ['recipient_name', 'Penerima'], ['recipient_address', 'Alamat'],
                        ['recipient_phone', 'No. HP'], ['shipper_name', 'Pengirim'],
                        ['vehicle_no', 'Kendaraan'], ['lines', 'Item'],
                        ['created_at', 'Dibuat']].map(([k, label]) => (
                        <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                          <button type="button" onClick={() => toggleSort(k)}
                            data-testid={`sj-sort-${k}`}
                            className="inline-flex items-center gap-1 hover:text-emerald-500">
                            {label}
                            <ChevronRight size={10}
                              className={`${sort.key === k ? 'text-emerald-500' : 'opacity-40'} ${
                                sort.key === k && sort.dir === 'asc' ? '-rotate-90' : 'rotate-90'}`} />
                          </button>
                        </th>
                      ))}
                      <th className="px-2.5 py-2 font-semibold text-right">Tindakan</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/10">
                    {paged.map((note) => (
                      <tr key={note.id} className="hover:bg-foreground/10"
                        data-testid={`sj-row-${note.sj_number}`}>
                        <td className="px-2.5 py-2 font-mono whitespace-nowrap">{note.sj_number}</td>
                        <td className="px-2.5 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${SJ_TYPES[note.sj_type]?.color || ''}`}>
                            {SJ_TYPES[note.sj_type]?.label || note.sj_type}
                          </span>
                        </td>
                        <td className="px-2.5 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_COLORS[note.status] || ''}`}>
                            {note.status}
                          </span>
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{note.recipient_name}</td>
                        <td className="px-2.5 py-2 max-w-[16rem] truncate" title={note.recipient_address}>
                          {note.recipient_address}
                        </td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{note.recipient_phone || '—'}</td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{note.shipper_name || '—'}</td>
                        <td className="px-2.5 py-2 whitespace-nowrap">{note.vehicle_no || '—'}</td>
                        <td className="px-2.5 py-2 text-right">{note.lines?.length || 0}</td>
                        <td className="px-2.5 py-2 whitespace-nowrap">
                          {note.created_at ? String(note.created_at).slice(0, 10) : '—'}
                        </td>
                        <td className="px-2.5 py-2 text-right whitespace-nowrap">
                          <div className="inline-flex gap-1">
                            {note.status === 'draft' && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-foreground/10"
                                onClick={() => handleIssue(note.id)}
                                data-testid={`issue-btn-${note.sj_number}`}>Issue</Button>
                            )}
                            {(note.status === 'issued' || note.status === 'received') && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-foreground/10"
                                onClick={() => handleDownloadPDF(note.id)}
                                data-testid={`download-btn-${note.sj_number}`}>PDF</Button>
                            )}
                            {note.status === 'issued' && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-foreground/10"
                                onClick={() => handleReceive(note.id)}
                                data-testid={`receive-btn-${note.sj_number}`}>Terima</Button>
                            )}
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-foreground/10"
                              onClick={() => setViewDialog(note)}
                              data-testid={`view-btn-${note.sj_number}`}>Detail</Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {paged.map((note) => (
              <div
                key={note.id}
                className="bg-foreground/5 border border-foreground/10 rounded-xl p-4 hover:bg-foreground/10 transition-colors"
                data-testid={`sj-card-${note.sj_number}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      <h3 className="font-semibold text-foreground">{note.sj_number}</h3>
                    </div>
                    <p className="text-sm text-muted-foreground/60 dark:text-zinc-400">{note.recipient_name}</p>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${SJ_TYPES[note.sj_type]?.color || ''}`}>
                      {SJ_TYPES[note.sj_type]?.label || note.sj_type}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_COLORS[note.status] || ''}`}>
                      {note.status}
                    </span>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-500">Alamat:</span>
                    <span className="text-foreground text-right truncate max-w-[200px]">{note.recipient_address}</span>
                  </div>
                  {note.vehicle_no && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground/60 dark:text-zinc-500">Kendaraan:</span>
                      <span className="text-foreground">{note.vehicle_no}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-500">Items:</span>
                    <span className="text-foreground">{note.lines?.length || 0} item</span>
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-foreground/10 flex gap-2">
                  {note.status === 'draft' && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 border-foreground/10 hover:bg-foreground/5 text-xs"
                      onClick={() => handleIssue(note.id)}
                      data-testid={`issue-btn-${note.sj_number}`}
                    >
                      <CheckCircle2 className="w-3 h-3 mr-1" />
                      Issue
                    </Button>
                  )}
                  {(note.status === 'issued' || note.status === 'received') && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 border-foreground/10 hover:bg-foreground/5 text-xs"
                      onClick={() => handleDownloadPDF(note.id)}
                      data-testid={`download-btn-${note.sj_number}`}
                    >
                      <Download className="w-3 h-3 mr-1" />
                      PDF
                    </Button>
                  )}
                  {note.status === 'issued' && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 border-emerald-300 dark:border-emerald-400/30 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 text-xs"
                      onClick={() => handleReceive(note.id)}
                      data-testid={`receive-btn-${note.sj_number}`}
                    >
                      <CheckCircle2 className="w-3 h-3 mr-1" />
                      Terima
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 border-foreground/10 hover:bg-foreground/5 text-xs"
                    onClick={() => setViewDialog(note)}
                    data-testid={`view-btn-${note.sj_number}`}
                  >
                    <Eye className="w-3 h-3 mr-1" />
                    Detail
                  </Button>
                </div>
              </div>
            ))}
          </div>
          )
        )}
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
          </>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={createDialog} onOpenChange={(o) => { setCreateDialog(o); if (!o) setSelectedJobId(''); }}>
        <DialogContent className="bg-card text-foreground border-foreground/10 max-w-3xl max-h-[90vh] overflow-auto" data-testid="create-sj-dialog">
          <DialogHeader>
            <DialogTitle>Buat Surat Jalan Baru</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate}>
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipe SJ *</Label>
                  <Select name="sj_type" required value={sjType} onValueChange={setSjType}>
                    <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="input-sj-type">
                      <SelectValue placeholder="Pilih tipe" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="SJ-CMT">CMT</SelectItem>
                      <SelectItem value="SJ-MAKLON">Maklon</SelectItem>
                      <SelectItem value="SJ-SUPPLIER">Supplier Return</SelectItem>
                      <SelectItem value="SJ-INTERNAL">Internal Transfer</SelectItem>
                      <SelectItem value="SJ-ONLINE">Online Shop</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Nama Penerima *</Label>
                  <Input name="recipient_name" required className="bg-foreground/5 border-foreground/10" data-testid="input-recipient-name" />
                </div>
              </div>

              {/* SESI #19 — kolom nomor mengikuti kebijakan Otomatis/Manual owner.
                  Sebelum ini form tidak punya kolom nomor sama sekali, sehingga setelan
                  MANUAL membuat surat jalan TIDAK BISA dibuat ("nomor wajib diisi"). */}
              <DocNumberField
                policy={numPolicy}
                value={sjNumber}
                onChange={setSjNumber}
                label="Nomor Surat Jalan"
                testId="sj-number"
              />

              <div>
                <Label>Alamat Penerima *</Label>
                <Textarea name="recipient_address" required className="bg-foreground/5 border-foreground/10" data-testid="input-recipient-address" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Telepon Penerima</Label>
                  <Input name="recipient_phone" className="bg-foreground/5 border-foreground/10" data-testid="input-recipient-phone" />
                </div>
                <div>
                  <Label>Nama Pengirim</Label>
                  <Input name="shipper_name" className="bg-foreground/5 border-foreground/10" data-testid="input-shipper-name" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Nomor Kendaraan</Label>
                  <Input name="vehicle_no" className="bg-foreground/5 border-foreground/10" data-testid="input-vehicle-no" />
                </div>
                <div>
                  <Label>Catatan</Label>
                  <Input name="notes" className="bg-foreground/5 border-foreground/10" data-testid="input-sj-notes" />
                </div>
              </div>

              {/* FASE P4: Auto-isi dari BOM (Job Produksi Internal) */}
              <div className="border-t border-foreground/10 pt-4">
                <div className="flex items-center gap-2 mb-3">
                  <Layers className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <Label className="text-base">Isi dari BOM (Job Internal)</Label>
                </div>
                <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-3">
                  Pilih job produksi internal untuk menambahkan otomatis kebutuhan material (bahan + aksesoris)
                  dari BOM aktif. Kuantitas dihitung otomatis = qty BOM per unit × qty job.
                </p>
                <div className="flex gap-2 items-center">
                  <div className="flex-1">
                    <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                      <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="bom-job-select">
                        <SelectValue placeholder="Pilih job produksi internal" />
                      </SelectTrigger>
                      <SelectContent>
                        {jobs.length === 0 ? (
                          <div className="px-3 py-2 text-sm text-muted-foreground/60">Tidak ada job internal</div>
                        ) : (
                          jobs.map((j) => (
                            <SelectItem key={j.id} value={j.id} data-testid={`bom-job-option-${j.job_number}`}>
                              {j.job_number} · {j.status}{j.total_available ? ` · ${j.total_available} pcs` : ''}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleFillFromBOM}
                    disabled={bomLoading || !selectedJobId}
                    className="border-emerald-300 dark:border-emerald-400/30 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10"
                    data-testid="fill-from-bom-btn"
                  >
                    {bomLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Layers className="w-4 h-4 mr-2" />}
                    Isi dari BOM
                  </Button>
                </div>
              </div>

              {/* Line Items */}
              <div className="border-t border-foreground/10 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <Label className="text-base">Item Pengiriman</Label>
                  <Button type="button" size="sm" variant="outline" onClick={addLine} className="border-foreground/10" data-testid="add-line-btn">
                    <Plus className="w-4 h-4 mr-1" />
                    Tambah Item
                  </Button>
                </div>
                <div className="space-y-3">
                  {editingLines.map((line, idx) => (
                    <div key={idx} className="flex gap-2 items-start bg-foreground/5 p-3 rounded-lg border border-foreground/10">
                      <div className="flex-1 grid grid-cols-4 gap-2">
                        <Input
                          placeholder="Deskripsi"
                          value={line.description}
                          onChange={(e) => updateLine(idx, 'description', e.target.value)}
                          className="col-span-2 bg-foreground/5 border-foreground/10"
                          data-testid={`line-desc-${idx}`}
                        />
                        <Input
                          type="number"
                          placeholder="Qty"
                          value={line.qty}
                          onChange={(e) => updateLine(idx, 'qty', parseFloat(e.target.value) || 0)}
                          className="bg-foreground/5 border-foreground/10"
                          data-testid={`line-qty-${idx}`}
                        />
                        <Input
                          placeholder="Unit"
                          value={line.unit}
                          onChange={(e) => updateLine(idx, 'unit', e.target.value)}
                          className="bg-foreground/5 border-foreground/10"
                          data-testid={`line-unit-${idx}`}
                        />
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => removeLine(idx)}
                        className="text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                        data-testid={`remove-line-${idx}`}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateDialog(false)} className="border-foreground/10">
                Batal
              </Button>
              <Button type="submit" className="bg-emerald-600 hover:bg-emerald-700" data-testid="submit-create-sj">
                <Save className="w-4 h-4 mr-2" />
                Simpan
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* View Dialog */}
      {viewDialog && (
        <Dialog open={!!viewDialog} onOpenChange={() => setViewDialog(null)}>
          <DialogContent className="bg-card text-foreground border-foreground/10 max-w-2xl" data-testid="view-sj-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                {viewDialog.sj_number}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Tipe:</span>
                  <p className="text-foreground font-medium">{SJ_TYPES[viewDialog.sj_type]?.label || viewDialog.sj_type}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Status:</span>
                  <p className="text-foreground font-medium">{viewDialog.status}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Penerima:</span>
                  <p className="text-foreground font-medium">{viewDialog.recipient_name}</p>
                </div>
                <div>
                  <span className="text-muted-foreground/60 dark:text-zinc-500">Telepon:</span>
                  <p className="text-foreground font-medium">{viewDialog.recipient_phone || '-'}</p>
                </div>
              </div>

              <div>
                <span className="text-muted-foreground/60 dark:text-zinc-500">Alamat:</span>
                <p className="text-foreground font-medium">{viewDialog.recipient_address}</p>
              </div>

              <div className="border-t border-foreground/10 pt-4">
                <h3 className="font-medium mb-3 text-muted-foreground/60 dark:text-zinc-400">Items</h3>
                <div className="space-y-2">
                  {viewDialog.lines?.map((line, idx) => (
                    <div key={idx} className="bg-foreground/5 border border-foreground/10 rounded p-3">
                      <div className="flex justify-between">
                        <span className="text-foreground">{line.description}</span>
                        <span className="text-muted-foreground/60 dark:text-zinc-400">{line.qty} {line.unit}</span>
                      </div>
                      {line.remarks && <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-1">{line.remarks}</p>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
