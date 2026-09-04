/**
 * DataImportWizard — Impor Data Marketing yang BEKERJA TANPA AI (F17).
 *
 * ALUR YANG DIPAKSAKAN LAYAR INI (dan alasannya)
 * ----------------------------------------------
 *   1. PILIH JENIS DATA   — dulu jenis data DITEBAK AI. Salah tebak = baris masuk
 *                            tabel yang salah dan tidak pernah muncul di mana pun.
 *   2. PILIH TOKO (+ host/kreator/katalog bila jenisnya menuntut) — ini akar
 *                            perbaikan F14: 60/60 order, 25/25 iklan, 18/18 sesi
 *                            live dulu tersimpan tanpa toko, sehingga filter per
 *                            toko selalu kosong dan laporan per akun Rp 0.
 *   3. UNDUH TEMPLATE     — supaya staf tidak menebak nama kolom.
 *   4. UNGGAH & PERIKSA PEMETAAN — pemetaan ditampilkan beserta SUMBER keputusannya
 *                            (pasti / sinonim / mirip / usulan). Pemetaan yang tidak
 *                            bisa diperiksa manusia akan dipercaya sampai laporannya
 *                            kacau.
 *   5. PRATINJAU & VALIDASI — baris bermasalah ditandai dan bisa diunduh.
 *   6. COMMIT / ROLLBACK  — hasil menyebut ke mana datanya masuk & di menu mana
 *                            bisa dilihat.
 *
 * AI hanya tombol bantuan pada langkah 4 dan hanya MENGUSULKAN untuk kolom yang
 * belum terpetakan; tidak pernah menimpa yang sudah pasti, tidak pernah wajib.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Upload, Download, CheckCircle2, AlertTriangle, XCircle, ArrowRight,
  ArrowLeft, Sparkles, RotateCcw, FileSpreadsheet, Info, Loader2, Table2,
  Store, ListChecks, Database, History, Search, Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import SkuMappingPanel from './SkuMappingPanel';
import ImportPlanPanel from './ImportPlanPanel';
import {
  MarketingAccountSelect, MarketingCreatorSelect, MarketingHostSelect,
} from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;
const BASE = `${API}/api/marketing/data-import`;

const GROUP_ICON = {
  // SESI #37 — 22 jenis diringkas jadi 6 KELOMPOK; label di sini mengikuti
  // `SOURCE_GROUPS` di backend (satu sumber, bukan dua daftar yang bisa beda).
  'Pesanan & Penjualan': '💰', Iklan: '📣', 'Live Selling': '🎥',
  'Katalog & Lainnya': '🏷️', Konten: '🗓️', 'Retur, Komplain & Ulasan': '↩️',
  'Belum dikelompokkan': '❓',
};

// BUG UX DITUTUP 2026-08-12 — grup dulu diurutkan ALFABETIS (`Object.keys().sort()`),
// sehingga "Penjualan" (berisi **Pesanan Marketplace** — jenis impor yang dipakai
// hampir setiap hari) jatuh di urutan ke-7 alias di bawah layar, di belakang
// After-Sales/Iklan/Katalog/Konten/Kreator/Live. Staf harus menggulir melewati 14
// kartu untuk mencapai satu-satunya kartu yang biasanya dia butuhkan.
// Urutan sekarang mengikuti alur kerja nyata (uang dulu), plus kotak pencarian.
const GROUP_ORDER = ['Pesanan & Penjualan', 'Iklan', 'Konten', 'Live Selling',
  'Retur, Komplain & Ulasan', 'Katalog & Lainnya', 'Belum dikelompokkan'];
// Jenis yang dipakai paling sering ⇒ diberi penanda supaya mata langsung menemukannya.
const PRIMARY_TYPES = new Set(['marketplace_orders']);

const METHOD_BADGE = {
  exact: { label: 'pasti', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' },
  synonym: { label: 'sinonim', cls: 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300' },
  fuzzy: { label: 'mirip', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' },
  manual: { label: 'manual', cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300' },
  suggest: { label: 'perlu dipilih', cls: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300' },
  none: { label: 'tidak dipakai', cls: 'bg-muted text-muted-foreground' },
};

function Step({ n, current, title, done }) {
  const active = current === n;
  return (
    <div className="flex items-center gap-2">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border
        ${done ? 'bg-emerald-600 text-white border-emerald-600'
          : active ? 'bg-[hsl(var(--primary))] text-white border-[hsl(var(--primary))]'
            : 'bg-muted text-muted-foreground border-border'}`}>
        {done ? '✓' : n}
      </div>
      <span className={`text-xs ${active ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
        {title}
      </span>
    </div>
  );
}

export default function DataImportWizard({ token }) {
  const { toast } = useToast();
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);

  const [step, setStep] = useState(1);
  const [types, setTypes] = useState([]);
  // SESI #37 — langkah pertama sekarang KELOMPOK (6 pintu), bukan 22 kartu jenis.
  // `groupKey` kosong = layar masih menampilkan pilihan kelompok.
  const [groups, setGroups] = useState([]);
  const [groupKey, setGroupKey] = useState('');
  const [detectRes, setDetectRes] = useState(null);   // hasil POST /detect
  const [showDeprecated, setShowDeprecated] = useState(false);
  const [typeKey, setTypeKey] = useState('');
  const [accountId, setAccountId] = useState('');
  const [hostId, setHostId] = useState('');
  const [creatorId, setCreatorId] = useState('');
  const [catalogId, setCatalogId] = useState('');
  const [catalogs, setCatalogs] = useState([]);
  // F18#3 — rincian produk menempel pada SATU sesi live tertentu; sesinya dipilih
  // di sini, bukan dicocokkan dari judul di berkas (judul mirip = baris nyangkut
  // di sesi yang salah).
  const [liveSessionId, setLiveSessionId] = useState('');
  const [liveSessions, setLiveSessions] = useState([]);
  const [file, setFile] = useState(null);
  const [session, setSession] = useState(null);
  const [mapping, setMapping] = useState([]);
  const [report, setReport] = useState(null);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState('');
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [rollbackTarget, setRollbackTarget] = useState(null);
  // F3.F — dua hal yang tidak boleh hanya lewat toast:
  //   `undoInfo`    = pratinjau APA yang akan dipulihkan sebelum tombol dipakai
  //   `undoReport`  = laporan pemulihan sesi yang SUDAH dibatalkan (bisa dibuka besok)
  const [undoInfo, setUndoInfo] = useState(null);
  const [undoReport, setUndoReport] = useState(null);
  // F8 "INGAT PEMETAAN SAYA" — daftar susunan kolom yang sistem sudah ingat.
  // Ingatan yang tidak bisa DILIHAT dan DILUPAKAN akan mengulang kesalahan yang
  // sama setiap hari sambil tampak "otomatis benar".
  const [dups, setDups] = useState(null);   // pratinjau: baris yang SUDAH ADA
  const [formats, setFormats] = useState(null);      // null = dialog tertutup
  const [forgotten, setForgotten] = useState(false); // ingatan sesi ini dilupakan
  // F1 (2026-08-12) — daftar toko dibaca di sini JUGA (bukan hanya di dalam
  // pemilih) supaya setiap langkah bisa MENAMPILKAN nama toko tujuan. Alasannya
  // mahal: saat uji, 559 pesanan gudang 'Outfit Boutique' masuk ke 'TikTok
  // Daluna' hanya karena satu klik salah pada daftar 5 toko TikTok yang namanya
  // mirip — dan tidak ada satu pun layar yang menyebut ke toko mana berkas itu
  // akan masuk sebelum tombol simpan ditekan.
  const [accounts, setAccounts] = useState([]);
  // Pesan penolakan yang MENETAP di layar (bukan hanya toast 5 detik).
  const [blockError, setBlockError] = useState(null);   // {where, title, detail}
  // GUDANG PLATFORM BELAJAR DARI BERKAS (2026-08-12).
  // Penjaga toko (F1) hanya bisa menahan "berkas masuk ke toko yang salah" kalau
  // master toko sudah menyimpan nama gudang platformnya — dan dari 9 toko hanya 1
  // yang terisi. Meminta pemilik mengetik 8 nama dari ingatan justru berbahaya:
  // satu salah ketik membuat penjaga menolak berkas yang BENAR, dan staf akan
  // belajar mengabaikan penjaga. Karena itu namanya diambil dari ekspor platform
  // itu sendiri (`session.shop_guard_warehouse`) lewat tombol di bawah.
  const [warehouseSaved, setWarehouseSaved] = useState(null);  // {ok, message}
  // FASE 4 (sesi #11) — RENCANA IMPOR per baris (lihat `ImportPlanPanel.jsx`).
  // Disimpan di sini juga karena tombol **Simpan** harus MATI ketika pratinjau
  // sudah tahu commit akan ditolak: tombol yang bisa diklik lalu gagal membuat
  // staf mengira sistemnya rusak, dan yang paling sering dilakukan sesudahnya
  // adalah mengunggah ulang berkas yang sama.
  const [planInfo, setPlanInfo] = useState(null);
  const fileRef = useRef(null);

  const selectedType = useMemo(
    () => types.find((t) => t.key === typeKey) || null, [types, typeKey]);

  const selectedAccount = useMemo(
    () => accounts.find((a) => a.id === accountId) || null, [accounts, accountId]);

  // F3.F — Riwayat impor perlu tahu SIFAT jenis impor tiap baris (mis. apakah
  // `update_only`) untuk memberi label tombol yang jujur. Sesi menyimpan
  // `source_type`, sifatnya ada di daftar jenis data.
  const typeByKey = useMemo(() => {
    const m = {};
    types.forEach((t) => { m[t.key] = t; });
    return m;
  }, [types]);

  const [typeQuery, setTypeQuery] = useState('');

  const visibleTypes = useMemo(() => {
    const q = typeQuery.trim().toLowerCase();
    // Tanpa pencarian: hanya jenis di KELOMPOK yang dipilih. Jenis yang ditandai
    // usang disembunyikan (tetap diterima /upload) sampai staf meminta melihatnya.
    const base = q ? types : types.filter((t) => t.group_key === groupKey);
    const kept = base.filter((t) => showDeprecated || !t.deprecated);
    if (!q) return kept;
    return kept.filter((t) => (
      `${t.label} ${t.describe} ${t.collection} ${t.group} ${t.key}`.toLowerCase().includes(q)
    ));
  }, [types, typeQuery, groupKey, showDeprecated]);

  const hiddenInGroup = useMemo(
    () => types.filter((t) => t.group_key === groupKey && t.deprecated),
    [types, groupKey]);

  // SESI #40 — SATU sumber angka untuk penghitung langkah 1. Sebelumnya header
  // memakai `types.length` (22, TERMASUK jenis usang) sedangkan badge tiap kartu
  // kelompok menghitung yang aktif saja (21) ⇒ satu layar memuat dua angka yang
  // tampak bertentangan. Yang dipakai sekarang: jumlah jenis AKTIF, dan jenis
  // usang disebut terpisah (bukan disembunyikan tanpa keterangan).
  const activeTypeCount = useMemo(
    () => types.filter((t) => !t.deprecated).length, [types]);
  const deprecatedCount = types.length - activeTypeCount;

  // Usulan jenis dari isi berkas, DISARING ke kelompok yang dipilih. Peringkat &
  // buktinya tetap ditampilkan: deteksi otomatis mengUSULKAN, bukan memutuskan.
  const detectRanking = useMemo(() => {
    const all = detectRes?.ranking || [];
    const byKey = {};
    types.forEach((t) => { byKey[t.key] = t; });
    return all
      .filter((r) => !groupKey || byKey[r.source_type || r.key]?.group_key === groupKey)
      .slice(0, 4);
  }, [detectRes, types, groupKey]);

  const grouped = useMemo(() => {
    const g = {};
    visibleTypes.forEach((t) => { (g[t.group] = g[t.group] || []).push(t); });
    // di dalam grup: jenis utama (paling sering dipakai) naik ke depan
    Object.values(g).forEach((list) => list.sort((a, b) => (
      (PRIMARY_TYPES.has(b.key) ? 1 : 0) - (PRIMARY_TYPES.has(a.key) ? 1 : 0)
      || String(a.label).localeCompare(String(b.label))
    )));
    return g;
  }, [visibleTypes]);

  const groupNames = useMemo(() => {
    const present = Object.keys(grouped);
    const known = GROUP_ORDER.filter((g) => present.includes(g));
    const rest = present.filter((g) => !GROUP_ORDER.includes(g)).sort();
    return [...known, ...rest];
  }, [grouped]);

  /* ── muat daftar jenis data & riwayat ── */
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${BASE}/source-types`, { headers: authH });
        setTypes(r.data?.source_types || []);
      } catch (e) {
        toast({ title: 'Gagal memuat jenis data impor', variant: 'destructive' });
      }
    })();
  }, [authH, toast]);

  /* ── SESI #37 — 6 KELOMPOK sebagai pintu pertama ──────────────────────────
     Daftar kelompok datang dari backend (`SOURCE_GROUPS`), bukan disusun ulang
     di browser: dua daftar untuk satu hal pasti berbeda suatu hari. */
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${BASE}/source-groups`, { headers: authH });
        setGroups(r.data?.groups || []);
      } catch (e) {
        toast({ title: 'Gagal memuat kelompok jenis data', variant: 'destructive' });
      }
    })();
  }, [authH, toast]);

  /* ── SESI #34 — SISTEM MEMBACA BERKAS DULU, LALU MENGUSULKAN JENIS ────────
     Deteksi hanya MENGUSULKAN: hasilnya berperingkat + membawa buktinya
     (platform, berapa kolom cocok, kolom wajib yang hilang). Keputusan tetap
     di tangan staf — satu klik "Pakai jenis ini". */
  const runDetect = useCallback(async (f) => {
    if (!f) return;
    setBusy('detect');
    setDetectRes(null);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const r = await axios.post(`${BASE}/detect`, fd, { headers: authH });
      setDetectRes(r.data || null);
      setFile(f);              // berkas yang sama dipakai lagi di langkah unggah
    } catch (e) {
      toast({
        title: 'Berkas tidak bisa dibaca',
        description: e?.response?.data?.detail || 'Coba berkas ekspor aslinya (CSV/XLSX).',
        variant: 'destructive',
      });
    } finally {
      setBusy('');
    }
  }, [authH, toast]);

  /* Jenis usulan dipakai: pindah ke kelompoknya, dan kalau berkas hanya cocok
     untuk SATU toko, toko itu langsung dipilih (staf tetap bisa menggantinya). */
  const applyDetectedType = useCallback((key) => {
    const t = types.find((x) => x.key === key);
    if (!t) return;
    setTypeKey(key);
    setGroupKey(t.group_key || '');
    const match = detectRes?.matching_accounts || [];
    if (t.account_scope === 'required' && match.length === 1) setAccountId(match[0].id);
    setStep(2);
  }, [types, detectRes]);

  /* ── daftar toko (untuk menampilkan TUJUAN di setiap langkah) ── */
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/api/marketing/accounts`, {
          headers: authH, params: { status: 'active' },
        });
        const list = Array.isArray(r.data) ? r.data
          : (r.data?.accounts || r.data?.data || []);
        setAccounts(list);
      } catch (e) { setAccounts([]); }
    })();
  }, [authH]);

  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${BASE}/history`, { headers: authH, params: { page_size: 20 } });
      setHistory(r.data?.history || []);
    } catch (e) { /* riwayat opsional */ }
  }, [authH]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  /* ── katalog / sesi live untuk jenis data yang menuntutnya ── */
  useEffect(() => {
    (async () => {
      const wantCatalog = !!selectedType?.context?.includes('catalog');
      const wantLive = !!selectedType?.context?.includes('live_session');
      if (!accountId || (!wantCatalog && !wantLive)) {
        setCatalogs([]); setLiveSessions([]); return;
      }
      try {
        const r = await axios.get(`${BASE}/context-options`, {
          headers: authH, params: { source_type: typeKey, account_id: accountId },
        });
        setCatalogs(r.data?.catalogs || []);
        setLiveSessions(r.data?.live_sessions || []);
      } catch (e) { setCatalogs([]); setLiveSessions([]); }
    })();
  }, [authH, accountId, typeKey, selectedType]);

  const needAccount = selectedType?.account_scope === 'required';
  const needHost = selectedType?.context?.includes('host');
  const needCreator = selectedType?.context?.includes('creator');
  const needCatalog = selectedType?.context?.includes('catalog');
  const needLiveSession = selectedType?.context?.includes('live_session');

  const contextReady = !!typeKey
    && (!needAccount || !!accountId)
    && (!needHost || !!hostId)
    && (!needCreator || !!creatorId)
    && (!needCatalog || !!catalogId)
    && (!needLiveSession || !!liveSessionId);

  /* ── F3.E — PENOLONG PEMETAAN KOLOM ────────────────────────────────────────
     Tiga pertanyaan yang PASTI muncul di langkah 4 dan tidak punya jawaban di
     layar sebelum ini:

       1. "kolom berkas ini isinya apa?"        → `sampleFor()`   (contoh isi nyata)
       2. "kolom mana yang tidak dipakai?"      → `unmappedCols`
       3. "field WAJIB X diambil dari kolom mana?" → `requiredHints`

     Jawaban #3 sengaja dihitung dengan MEMBALIK usulan mesin yang sudah ada di
     tiap kolom (`candidates: field→skor`) menjadi field→daftar kolom. Tanpa
     pembalikan itu staf harus membuka satu per satu dropdown 40+ kolom untuk
     mencari kolom yang cocok dengan satu field wajib — dan itulah sebabnya
     berkas yang kolomnya hanya beda nama berakhir "ditolak semua barisnya".
     Nilai contoh diambil dari `preview[].original` (baris berkas apa adanya),
     jadi tidak ada permintaan jaringan tambahan. */
  const sampleFor = useCallback((column) => {
    for (const r of rows.slice(0, 12)) {
      const v = r?.original?.[column];
      if (v !== undefined && v !== null && String(v).trim() !== '') {
        return String(v).trim();
      }
    }
    return '';
  }, [rows]);

  const unmappedCols = useMemo(
    () => mapping.filter((m) => !m.field).map((m) => m.column), [mapping]);

  const requiredHints = useMemo(() => {
    const missing = report?.missing_required || [];      // berisi LABEL field
    if (!missing.length) return [];
    const fields = selectedType?.fields || [];
    return missing.map((label) => {
      const f = fields.find((x) => x.label === label);
      const cands = [];
      if (f) {
        mapping.forEach((m) => {
          if (m.field) return;                           // kolom sudah terpakai
          (m.candidates || []).forEach((c) => {
            if (c.field === f.name) cands.push({ column: m.column, score: c.score || 0 });
          });
        });
        cands.sort((a, b) => b.score - a.score);
      }
      return { label, name: f?.name || '', example: f?.example || '',
        candidates: cands.slice(0, 3) };
    });
  }, [report, selectedType, mapping]);

  // Usulan yang MENUNGGU keputusan manusia (dipakai untuk memberi tahu jumlahnya
  // di header langkah 4 — tanpa angka ini panel usulan mudah terlewat).
  const pendingSuggestions = useMemo(
    () => mapping.filter((m) => !m.field && (m.candidates || []).length > 0).length,
    [mapping]);

  // SESI #34 — satu baris per kolom TEMPLATE (arah pemetaan yang benar menurut
  // pemilik). Kolom wajib di atas, lalu kolom yang sudah ketemu, lalu sisanya.
  const fieldRows = useMemo(() => {
    const fields = (selectedType?.fields || []).filter((f) => !f.derived);
    const byField = {};
    mapping.forEach((m) => { if (m.field) byField[m.field] = m; });
    const candFor = (name) => {
      const out = [];
      mapping.forEach((m) => {
        if (m.field) return;
        (m.candidates || []).forEach((c) => {
          if (c.field === name) out.push({ column: m.column, score: c.score || 0 });
        });
      });
      return out.sort((a, b) => b.score - a.score);
    };
    return fields.map((f) => ({
      name: f.name, label: f.label, kind: f.kind, required: !!f.required,
      example: f.example || '', column: byField[f.name]?.column || '',
      method: byField[f.name]?.method || '', candidates: candFor(f.name),
    })).sort((a, b) => {
      const rank = (x) => (x.required && !x.column ? 0 : x.required ? 1 : x.column ? 2 : 3);
      return rank(a) - rank(b);
    });
  }, [selectedType, mapping]);

  const resetAll = () => {
    setStep(1); setTypeKey(''); setAccountId(''); setHostId(''); setCreatorId('');
    setCatalogId(''); setLiveSessionId(''); setFile(null); setSession(null);
    setMapping([]); setReport(null); setRows([]); setSummary(null); setResult(null);
    setBlockError(null); setWarehouseSaved(null); setForgotten(false); setDups(null);
  };

  /* ── GUDANG PLATFORM: simpan nama gudang yang TERBACA di berkas ke master toko ──
     Sesudah tersimpan, impor berikutnya untuk toko ini terjaga otomatis dari
     salah pilih toko (penjaga F1 membandingkan kolom `Warehouse Name` berkas
     dengan `platform_warehouse_name` master toko). Penolakan (mis. gudang itu
     sudah dipakai toko lain ⇒ 409) DITAHAN di layar karena justru penolakan
     itulah yang berarti "tokonya kemungkinan salah pilih". */
  const learnWarehouse = async () => {
    const name = (session?.shop_guard_warehouse || '').trim();
    if (!name || !accountId) return;
    setBusy('learn-warehouse');
    setWarehouseSaved(null);
    try {
      const r = await axios.post(
        `${API}/api/marketing/accounts/${accountId}/learn-warehouse`,
        { warehouse_name: name, session_id: session?.id || '' },
        { headers: { ...authH, 'Content-Type': 'application/json' } });
      const msg = r.data?.message || `Gudang platform '${name}' disimpan ke master toko.`;
      setWarehouseSaved({ ok: true, message: msg });
      setSession((s) => (s ? { ...s, shop_guard_hint: '' } : s));
      setAccounts((list) => list.map((a) => (
        a.id === accountId ? { ...a, platform_warehouse_name: name } : a)));
      toast({ title: 'Gudang platform disimpan ke master toko', description: msg });
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      setWarehouseSaved({ ok: false, message: detail });
      toast({
        title: 'Gudang platform TIDAK disimpan',
        description: detail,
        variant: 'destructive',
      });
    } finally { setBusy(''); }
  };

  const downloadTemplate = async (fmt) => {
    try {
      setBusy('template');
      const r = await axios.get(`${BASE}/template/${typeKey}?fmt=${fmt}`, {
        headers: authH, responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = `template-impor-${typeKey}.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ title: 'Gagal mengunduh template', variant: 'destructive' });
    } finally { setBusy(''); }
  };

  const upload = async () => {
    if (!file) { toast({ title: 'Pilih berkas dulu', variant: 'destructive' }); return; }
    setBusy('upload');
    setBlockError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('source_type', typeKey);
      if (accountId) fd.append('account_id', accountId);
      if (hostId) fd.append('host_id', hostId);
      if (creatorId) fd.append('creator_id', creatorId);
      if (catalogId) fd.append('catalog_id', catalogId);
      if (liveSessionId) fd.append('live_session_id', liveSessionId);
      const r = await axios.post(`${BASE}/upload`, fd, { headers: authH });
      setSession(r.data.session);
      setMapping(r.data.session.mapping || []);
      setReport(r.data.session.mapping_report || null);
      setRows(r.data.preview || []);
      setSummary(r.data.summary || null);
      setDups(r.data.duplicates || null);
      setStep(4);
    } catch (e) {
      // Penolakan penjaga (platform/toko salah) adalah alasan PALING PENTING yang
      // harus dibaca staf, dan panjang. Toast hilang dalam 5 detik dan
      // meninggalkan layar langkah 3 tanpa satu pun keterangan — staf lalu
      // menekan "Unggah" berulang kali. Karena itu pesannya juga DITAHAN di layar.
      const detail = e.response?.data?.detail || e.message;
      setBlockError({ where: 'upload', title: 'Unggah ditolak', detail });
      toast({ title: 'Unggah ditolak', description: detail, variant: 'destructive' });
    } finally { setBusy(''); }
  };

  const saveMapping = async (next) => {
    setBusy('mapping');
    try {
      const r = await axios.put(`${BASE}/sessions/${session.id}/mapping`,
        { mapping: next.map((m) => ({ column: m.column, field: m.field })) },
        { headers: authH });
      setMapping(r.data.mapping);
      setReport(r.data.mapping_report);
      setRows(r.data.preview || []);
      setSummary(r.data.summary || null);
      setDups(r.data.duplicates || null);
    } catch (e) {
      toast({
        title: 'Pemetaan ditolak',
        description: e.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setBusy(''); }
  };

  const changeMap = (column, field) => {
    const next = mapping.map((m) => (m.column === column
      ? { ...m, field: field === '__none__' ? null : field } : m));
    setMapping(next);
    saveMapping(next);
  };

  /* ── SESI #34 — ARAH PEMETAAN DIBALIK ────────────────────────────────────────
     Sebelumnya layar bertanya "kolom berkas ini mau jadi field apa?" (satu baris
     per kolom berkas). Pemilik menegaskan yang benar kebalikannya: ACUANNYA
     adalah kolom TEMPLATE/sistem — untuk tiap kolom sistem, pilih kolom mana di
     berkas yang mengisinya. Bedanya nyata: dengan arah lama, kolom sistem yang
     TIDAK ADA di berkas tidak pernah muncul di layar sama sekali, jadi staf tidak
     pernah tahu ada field yang kosong sampai validasi menolak.
     Satu field hanya boleh diisi SATU kolom, jadi memilih kolom baru otomatis
     melepas kolom yang lama. */
  const changeField = (fieldName, column) => {
    const col = column === '__none__' ? null : column;
    const next = mapping.map((m) => {
      if (m.field === fieldName && m.column !== col) return { ...m, field: null };
      if (col && m.column === col) return { ...m, field: fieldName };
      return m;
    });
    setMapping(next);
    saveMapping(next);
  };

  const askAI = async () => {
    setBusy('ai');
    try {
      const r = await axios.post(`${BASE}/sessions/${session.id}/ai-assist`, {}, { headers: authH });
      const sug = r.data?.suggestion || [];
      if (!sug.length) { toast({ title: 'AI tidak punya usulan tambahan' }); return; }
      const next = mapping.map((m) => {
        const s = sug.find((x) => x.column === m.column);
        return s && s.field && !m.field ? { ...m, field: s.field } : m;
      });
      setMapping(next);
      await saveMapping(next);
      toast({
        title: `AI mengusulkan ${sug.filter((s) => s.field).length} pemetaan`,
        description: 'Periksa dulu — usulan AI tidak menimpa pemetaan yang sudah pasti.',
      });
    } catch (e) {
      toast({
        title: 'Bantuan AI tidak tersedia',
        description: `${e.response?.data?.detail || e.message} — pemetaan manual tetap bisa dipakai.`,
        variant: 'destructive',
      });
    } finally { setBusy(''); }
  };

  /* ── UNDUHAN YANG BENAR-BENAR TERUNDUH (diperbaiki Fase 4, sesi #11) ───────
     CACAT YANG DITEMUKAN: tombol "Unduh daftar baris bermasalah" memakai
     `window.open()`. Endpoint CSV-nya dijaga `require_auth` yang HANYA membaca
     header `Authorization`, dan tab baru tidak pernah membawa header itu ⇒ yang
     terbuka selalu `{"detail":"Unauthorized"}` (HTTP 401), bukan berkas. Jadi
     satu-satunya jalan keluar untuk memperbaiki baris bermasalah di berkas asli
     sebetulnya MATI sejak dibuat.
     Sekarang semua unduhan lewat axios (header ikut) → Blob → tautan sementara. */
  const downloadAuthed = async (path, filename, params) => {
    try {
      const r = await axios.get(`${BASE}/${path}`, {
        headers: authH, params: params || {}, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv;charset=utf-8;' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: 'Berkas terunduh', description: filename });
    } catch (e) {
      // Blob error body harus dibaca sebagai teks dulu, kalau tidak pesannya
      // muncul sebagai "[object Blob]" — galat yang tidak bisa ditindak.
      let detail = e.message;
      try {
        if (e.response?.data instanceof Blob) {
          const txt = await e.response.data.text();
          detail = JSON.parse(txt)?.detail || txt;
        } else { detail = e.response?.data?.detail || e.message; }
      } catch (e2) { /* pakai e.message */ }
      toast({ title: 'Gagal mengunduh', description: detail, variant: 'destructive' });
    }
  };

  const downloadErrors = () => downloadAuthed(
    `sessions/${session.id}/errors.csv`, `baris-bermasalah-${session.id.slice(0, 8)}.csv`);

  /* ── F8 — INGAT PEMETAAN SAYA ──────────────────────────────────────────────
     Dua tombol yang menutup dua cacat sekaligus:
       · "Lihat semua yang diingat" — ingatan yang tak bisa dilihat tidak bisa
         diperiksa; staf tidak tahu kenapa kolom sudah terpetakan.
       · "Lupakan pemetaan ini"     — satu kesalahan yang pernah di-commit dulu
         terpasang otomatis SELAMANYA tanpa jalan keluar di aplikasi. */
  const loadFormats = async () => {
    setBusy('formats');
    try {
      const r = await axios.get(`${BASE}/formats`, {
        headers: authH, params: typeKey ? { source_type: typeKey } : {},
      });
      setFormats(r.data?.formats || []);
    } catch (e) {
      toast({
        title: 'Gagal memuat daftar pemetaan tersimpan',
        description: e.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setBusy(''); }
  };

  const forgetFormat = async (fingerprint, stype, fromSession) => {
    setBusy('forget');
    try {
      const r = await axios.delete(`${BASE}/formats/${fingerprint}`, {
        headers: authH, params: { source_type: stype },
      });
      toast({ title: 'Pemetaan tersimpan dilupakan', description: r.data?.message });
      if (fromSession) {
        setForgotten(true);
        setSession((s) => (s ? { ...s, format_known: false, format_memory: null } : s));
      }
      if (formats) loadFormats();
    } catch (e) {
      toast({
        title: 'Gagal melupakan pemetaan',
        description: e.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setBusy(''); }
  };

  const commit = async () => {
    setBusy('commit');
    setBlockError(null);
    try {
      const r = await axios.post(`${BASE}/sessions/${session.id}/commit`,
        { on_duplicate: onDuplicate }, { headers: authH });
      setResult(r.data);
      setStep(6);
      loadHistory();
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      setBlockError({ where: 'commit', title: 'Commit ditolak', detail });
      toast({ title: 'Commit ditolak', description: detail, variant: 'destructive' });
    } finally { setBusy(''); }
  };

  /* ── F3.F — PRATINJAU PEMULIHAN sebelum tombol "Batalkan impor" dipakai ────
     Tombol pembatalan pada impor `update_only` tidak bisa menjanjikan hal yang
     sama dengan impor biasa: tidak ada baris untuk dihapus, dan pesanan yang
     berkasnya jadikan batal/retur TIDAK dihidupkan lagi (stoknya sudah dilepas).
     Dialog konfirmasi karena itu memuat angka dari `undo-report` — bukan
     kalimat umum yang bisa dibantah kenyataan sesudahnya. */
  const askRollback = async (sid) => {
    setRollbackTarget(sid);
    setUndoInfo(null);
    try {
      const r = await axios.get(`${BASE}/sessions/${sid}/undo-report`, { headers: authH });
      setUndoInfo(r.data || null);
    } catch (e) { setUndoInfo({ error: e.response?.data?.detail || e.message }); }
  };

  /* Laporan pemulihan sesi yang SUDAH dibatalkan — dibaca dari sesi (bukan dari
     berkas), jadi tetap bisa dibuka setelah berkasnya dibersihkan penjadwal. */
  const openUndoReport = async (sid) => {
    setUndoReport({ loading: true, session_id: sid });
    try {
      const r = await axios.get(`${BASE}/sessions/${sid}/undo-report`, { headers: authH });
      setUndoReport(r.data || null);
    } catch (e) {
      setUndoReport({ error: e.response?.data?.detail || e.message, session_id: sid });
    }
  };

  const rollback = async (sid) => {
    setBusy('rollback');
    try {
      const r = await axios.post(`${BASE}/sessions/${sid}/rollback`, {}, { headers: authH });
      // Rollback punya AKIBAT KEDUA yang tidak terlihat: rekap harian turunan ikut
      // dihapus/dihitung ulang — KECUALI tanggal yang angkanya sudah diganti SPV
      // (override sengaja tidak ditimpa). Kalau itu tidak diberitahukan, tanggal
      // tersebut tetap menampilkan omzet dari pesanan yang sudah tidak ada, dan
      // tidak ada satu pun layar yang menjelaskan kenapa.
      const ru = r.data?.daily_rollup || null;
      const parts = [];
      if (ru) {
        if (ru.deleted) parts.push(`${ru.deleted} tanggal rekap harian dihapus`);
        if (ru.upserted) parts.push(`${ru.upserted} tanggal dihitung ulang`);
        if (ru.skipped_override) {
          parts.push(`${ru.skipped_override} tanggal TIDAK dikembalikan karena angkanya `
            + 'sudah diganti SPV — periksa manual di menu Input Sales');
        }
      }
      toast({
        title: r.data?.message || 'Impor dibatalkan',
        description: parts.join(' · ') || undefined,
        duration: ru?.skipped_override ? 15000 : undefined,
      });
      loadHistory();
      // F3.F — kalau ada PEMULIHAN keadaan (bukan sekadar hapus baris), hasilnya
      // dibuka sebagai laporan yang MENETAP. Angka "3 pesanan hanya field-nya
      // yang bisa dipulihkan" beserta nomor pesanannya adalah pekerjaan manual
      // yang harus dilanjutkan orang — mustahil dikerjakan dari toast 5 detik.
      const rs = r.data?.restore || {};
      if (rs.restored || rs.fields_only || rs.missing) openUndoReport(sid);
      if (session?.id === sid) resetAll();
    } catch (e) {
      toast({
        title: 'Rollback gagal',
        description: e.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setBusy(''); setRollbackTarget(null); }
  };

  /* ─────────────────────────── RENDER ─────────────────────────── */
  return (
    <div className="space-y-4" data-testid="data-import-wizard">
      {/* header + stepper */}
      <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold flex items-center gap-2">
              <Upload className="w-5 h-5 text-[hsl(var(--primary))]" />
              Impor Data Marketing
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Berjalan penuh <b>tanpa AI</b>: kolom dipetakan dengan aturan pasti,
              kamus sinonim ekspor marketplace, lalu kemiripan teks. AI hanya tombol bantuan.
            </p>
          </div>
          {step > 1 && (
            <Button variant="outline" size="sm" onClick={resetAll} data-testid="import-reset">
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Mulai ulang
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3">
          <Step n={1} current={step} title="Jenis data" done={step > 1} />
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <Step n={2} current={step} title="Toko & konteks" done={step > 2} />
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <Step n={3} current={step} title="Template & unggah" done={step > 3} />
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <Step n={4} current={step} title="Pemetaan kolom" done={step > 4} />
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <Step n={5} current={step} title="Pratinjau" done={step > 5} />
          <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          <Step n={6} current={step} title="Selesai" done={step > 6} />
        </div>
      </div>

      {/* TUJUAN IMPOR — terlihat di SETIAP langkah sesudah toko dipilih.
          Satu klik salah pada daftar toko yang namanya mirip memindahkan omzet
          seluruh berkas ke toko lain; strip ini membuat kesalahan itu terlihat
          SEBELUM tombol simpan ditekan, bukan sesudah laporan aneh. */}
      {step > 1 && selectedType && (
        <div className="rounded-[var(--radius-md)] border border-[hsl(var(--primary))]/30
          bg-[hsl(var(--primary))]/5 px-4 py-2.5 flex flex-wrap items-center gap-x-6 gap-y-1"
          data-testid="import-destination-strip">
          <span className="text-xs text-muted-foreground">
            Jenis data: <b className="text-foreground">{selectedType.label}</b>
          </span>
          {selectedType.account_scope === 'required' && (
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Store className="w-3.5 h-3.5" /> Masuk ke toko:{' '}
              {selectedAccount ? (
                <b className="text-foreground" data-testid="import-destination-account">
                  {selectedAccount.account_name}
                  <span className="font-normal text-muted-foreground">
                    {' '}({selectedAccount.account_code} · {selectedAccount.platform})
                  </span>
                </b>
              ) : (
                <b className="text-amber-600 dark:text-amber-400">belum dipilih</b>
              )}
            </span>
          )}
          {session?.filename && (
            <span className="text-xs text-muted-foreground">
              Berkas: <b className="text-foreground">{session.filename}</b>
            </span>
          )}
          {/* Gudang platform toko tujuan — inilah yang dipakai penjaga toko untuk
              membandingkan kolom `Warehouse Name` di berkas. Kalau kosong, penjaga
              tidak punya pembanding, jadi statusnya harus terlihat SEBELUM unggah. */}
          {selectedType.account_scope === 'required' && selectedAccount && (
            <span className="text-xs text-muted-foreground"
              data-testid="import-destination-warehouse">
              Gudang platform:{' '}
              {selectedAccount.platform_warehouse_name ? (
                <b className="text-foreground">{selectedAccount.platform_warehouse_name}</b>
              ) : (
                <b className="text-amber-600 dark:text-amber-400">belum diisi</b>
              )}
            </span>
          )}
        </div>
      )}

      {/* PERINGATAN PENJAGA TOKO — gudang platform di berkas tidak bisa
          dipastikan milik toko tujuan (master tokonya belum diisi). Di sini juga
          jalan keluarnya: SIMPAN nama gudang yang terbaca di berkas ke master
          toko, supaya impor berikutnya terjaga otomatis. Nama datang dari ekspor
          platform — bukan dari ingatan staf. */}
      {session?.shop_guard_hint && step > 3 && (
        <div className="rounded-[var(--radius-md)] border border-amber-500/40 bg-amber-500/10
          p-3 text-xs space-y-2" data-testid="import-shop-guard-hint">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-px shrink-0 text-amber-600 dark:text-amber-400" />
            <span>{session.shop_guard_hint}</span>
          </div>
          {session?.shop_guard_warehouse && selectedAccount && (
            <div className="flex flex-wrap items-center gap-2 pl-6">
              <Button
                size="sm"
                variant="outline"
                onClick={learnWarehouse}
                disabled={busy === 'learn-warehouse'}
                data-testid="import-learn-warehouse">
                {busy === 'learn-warehouse'
                  ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  : <Store className="w-3.5 h-3.5 mr-1.5" />}
                Simpan gudang &lsquo;{session.shop_guard_warehouse}&rsquo; ke master toko
              </Button>
              <span className="text-[11px] text-muted-foreground">
                Tersimpan ke toko <b>{selectedAccount.account_name}</b> — sekali saja;
                impor berikutnya untuk toko ini otomatis terjaga dari salah pilih toko.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Hasil penyimpanan gudang platform — MENETAP di layar.
          Penolakan 409 ("gudang ini sudah dipakai toko lain") adalah petunjuk
          terpenting bahwa toko tujuannya kemungkinan salah pilih; kalau hanya
          muncul 5 detik sebagai toast, petunjuk itu hilang. */}
      {warehouseSaved && (
        <div
          className={`rounded-[var(--radius-md)] border p-3 text-xs flex items-start gap-2 ${
            warehouseSaved.ok
              ? 'border-emerald-500/40 bg-emerald-500/10'
              : 'border-red-500/40 bg-red-500/10'}`}
          data-testid={warehouseSaved.ok ? 'import-warehouse-saved' : 'import-warehouse-error'}>
          {warehouseSaved.ok
            ? <CheckCircle2 className="w-4 h-4 mt-px shrink-0 text-emerald-600 dark:text-emerald-400" />
            : <XCircle className="w-4 h-4 mt-px shrink-0 text-red-600 dark:text-red-400" />}
          <div className="space-y-1">
            <p className={warehouseSaved.ok
              ? 'text-emerald-700 dark:text-emerald-300'
              : 'text-red-700 dark:text-red-300'}>{warehouseSaved.message}</p>
            {!warehouseSaved.ok && (
              <Button size="sm" variant="outline" className="h-7"
                onClick={() => { setStep(2); setWarehouseSaved(null); }}
                data-testid="import-warehouse-change-account">
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Ganti toko tujuan
              </Button>
            )}
          </div>
        </div>
      )}

      {/* F3 — DUA PERINGATAN YANG MENETAP (bukan toast) untuk jenis impor
          "hanya memperbarui" (Ekspor B & C).

          Kenapa harus menetap: keduanya mengubah ARTI tombol simpan. Staf yang
          menyangka berkas ini "memasukkan pesanan" akan membaca hasil "0 baris
          masuk" sebagai kegagalan lalu mengunggah ulang berkas Ekspor A —
          dan justru itu yang membuat status pesanan lama membeku. Peringatan
          pemetaan juga tidak boleh hilang dalam 5 detik: pemetaan jenis ini
          disusun dari bentuk Ekspor A, jadi langkah "Pemetaan kolom" adalah
          satu-satunya tempat kesalahan kolom masih bisa ditangkap. */}
      {step > 1 && selectedType?.update_only && (
        <div className="rounded-[var(--radius-md)] border border-blue-500/40 bg-blue-500/10 p-3
          text-xs space-y-1" data-testid="import-update-only-notice">
          <p className="font-semibold text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
            <Info className="w-4 h-4" /> Berkas ini HANYA MEMPERBARUI pesanan yang sudah ada
          </p>
          <p className="text-muted-foreground">
            Impor ini tidak pernah membuat pesanan baru. Nomor pesanan yang belum
            pernah diimpor akan <b>ditolak</b> beserta alasannya — impor
            <b> Pesanan Marketplace (Ekspor A)</b> dulu. Statusnya juga tidak boleh
            MUNDUR (mis. dari “dikirim” kembali ke “perlu dikirim”) kecuali berkasnya
            membawa bukti batal/retur. Jadi angka <b>“Baris masuk” memang 0</b> —
            yang naik adalah <b>“Diperbarui”</b>.
          </p>
        </div>
      )}
      {step > 1 && selectedType?.mapping_unverified && (
        <div className="rounded-[var(--radius-md)] border border-amber-500/40 bg-amber-500/10 p-3
          text-xs space-y-1" data-testid="import-mapping-unverified">
          <p className="font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" />
            {step === 6
              ? 'Hasil di atas memakai pemetaan yang BELUM diverifikasi'
              : 'Periksa pemetaan kolom sebelum menyimpan'}
          </p>
          <p className="text-muted-foreground">{selectedType.mapping_unverified}</p>
          {/* Sesudah commit, kalimat "periksa sebelum menyimpan" sudah kehilangan
              gunanya — yang dibutuhkan staf adalah JALAN KELUAR-nya. */}
          {step === 6 && (
            <p className="text-muted-foreground">
              Kalau ada kolom yang ternyata salah tempat, pakai <b>“Batalkan &amp; pulihkan
              pesanan”</b> di bawah, lalu unggah ulang berkasnya dan perbaiki pemetaannya di
              langkah 4 — jangan menambal lewat entri manual.
            </p>
          )}
        </div>
      )}

      {/* STEP 1 — jenis data */}
      {step === 1 && (
        <div className="space-y-4">
          {/* pencarian — 17 jenis data tidak mungkin dihafal; tanpa ini staf menggulir
              melewati 6 grup untuk menemukan satu kartu */}
          <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3">
            {groupKey && (
              <Button variant="outline" size="sm" className="h-9"
                data-testid="import-group-back"
                onClick={() => { setGroupKey(''); setTypeQuery(''); }}>
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Semua kelompok
              </Button>
            )}
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={typeQuery}
                onChange={(e) => setTypeQuery(e.target.value)}
                placeholder="Cari jenis data… (mis. pesanan, iklan, live, katalog)"
                data-testid="import-type-search"
                className="w-full h-9 pl-8 pr-3 rounded-[var(--radius-sm)] border border-border
                  bg-[hsl(var(--background))] text-sm text-foreground
                  placeholder:text-muted-foreground focus:outline-none
                  focus:ring-2 focus:ring-[hsl(var(--primary))]"
              />
            </div>
            <span className="text-xs text-muted-foreground" data-testid="import-type-count">
              {!groupKey && !typeQuery.trim()
                ? `${activeTypeCount} jenis data dalam ${groups.length} kelompok`
                  + (deprecatedCount ? ` · ${deprecatedCount} usang disembunyikan` : '')
                : `${visibleTypes.length} dari ${activeTypeCount} jenis data`}
            </span>
            {hiddenInGroup.length > 0 && (
              <Button variant="ghost" size="sm" className="h-9 text-xs"
                data-testid="import-toggle-deprecated"
                onClick={() => setShowDeprecated((v) => !v)}>
                {showDeprecated ? 'Sembunyikan' : 'Tampilkan'} {hiddenInGroup.length} jenis usang
              </Button>
            )}
          </div>

          {/* ── PINTU PERTAMA: unggah dulu (deteksi) ATAU pilih kelompok ────────
              Sebelum ini layar langsung meminta staf memilih 1 dari 22 jenis —
              dan karena daftarnya disaring per kelompok, tanpa kelompok terpilih
              layar tampak KOSONG ("0 dari 22"). Dua jalan sekarang tersedia:
              biarkan sistem membaca berkasnya, atau pilih kelompoknya sendiri. */}
          {!groupKey && !typeQuery.trim() && (
            <div className="space-y-4" data-testid="import-step1-entry">
              <div className="rounded-[var(--radius-md)] border border-[hsl(var(--primary))]/40
                bg-[hsl(var(--primary))]/5 p-4 space-y-3" data-testid="import-detect-panel">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-[hsl(var(--primary))]" />
                      Belum tahu ini jenis data apa? Unggah berkasnya dulu
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Sistem membaca kolomnya, lalu <b>mengusulkan</b> jenis &amp; platform
                      beserta buktinya. Usulan bukan keputusan — Anda yang memilih.
                    </p>
                  </div>
                  <label className="shrink-0">
                    <input type="file" className="hidden"
                      accept=".csv,.xlsx,.xls,.xlsm,.tsv,.txt"
                      data-testid="import-detect-file"
                      onChange={(e) => runDetect(e.target.files?.[0])} />
                    <span className="inline-flex items-center h-9 px-3 rounded-[var(--radius-sm)]
                      text-sm font-medium cursor-pointer bg-[hsl(var(--primary))]
                      text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity">
                      {busy === 'detect'
                        ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Membaca…</>
                        : <><Upload className="w-4 h-4 mr-1.5" /> Periksa berkas</>}
                    </span>
                  </label>
                </div>

                {detectRes && (
                  <div className="space-y-2" data-testid="import-detect-result">
                    <p className="text-xs">
                      <b>{detectRes.filename}</b> · {detectRes.file_size_kb} KB ·
                      {' '}{(detectRes.headers || []).length} kolom ·
                      {' '}<b>{detectRes.row_count}</b> baris data
                      {detectRes.platform?.platform && (
                        <> · platform terbaca <b>{String(detectRes.platform.platform).toUpperCase()}</b></>
                      )}
                    </p>
                    {!detectRes.row_count && (
                      <p className="text-xs rounded-[var(--radius-sm)] border border-red-500/40
                        bg-red-500/10 p-2 text-red-700 dark:text-red-300"
                        data-testid="import-detect-empty-file">
                        <b>Berkas ini tidak punya satu pun baris data</b> (hanya baris kolom).
                        Ekspor ulang dari Seller Center dengan rentang tanggal yang benar —
                        mengunggahnya sekarang akan ditolak.
                      </p>
                    )}
                    {detectRes.platform_warning && (
                      <p className="text-xs rounded-[var(--radius-sm)] border border-amber-500/40
                        bg-amber-500/10 p-2 text-amber-700 dark:text-amber-300"
                        data-testid="import-detect-platform-warning">
                        {detectRes.platform_warning}
                      </p>
                    )}
                    {(detectRes.platform?.evidence || []).length > 0 && (
                      <p className="text-[11px] text-muted-foreground">
                        Bukti platform: {(detectRes.platform.evidence || []).slice(0, 6).join(' · ')}
                      </p>
                    )}
                    <div className="grid gap-2 sm:grid-cols-2">
                      {detectRanking.map((r, i) => {
                        const key = r.source_type || r.key;
                        const t = typeByKey[key];
                        return (
                          <div key={key || i}
                            className={`rounded-[var(--radius-sm)] border p-2.5 bg-[hsl(var(--card))]
                              ${i === 0 ? 'border-[hsl(var(--primary))]' : 'border-border'}`}>
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-sm font-semibold">{r.label || t?.label || key}</span>
                              {i === 0 && (
                                <Badge className="text-[10px] shrink-0 bg-[hsl(var(--primary))] text-white">
                                  paling cocok
                                </Badge>
                              )}
                            </div>
                            <p className="text-[11px] text-muted-foreground mt-1">
                              {r.mapped_columns}/{r.total_columns} kolom cocok ·
                              {' '}kolom wajib {r.required_hit}/{r.required_total} ·
                              {' '}skor {Math.round((r.score || 0) * 100)}%
                            </p>
                            {(r.required_missing || []).length > 0 && (
                              <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5">
                                Kolom wajib belum ada: {(r.required_missing || []).join(', ')}
                              </p>
                            )}
                            <Button size="sm" variant={i === 0 ? 'default' : 'outline'}
                              className="h-7 mt-2 text-xs"
                              data-testid={`import-detect-use-${key}`}
                              disabled={!t}
                              onClick={() => applyDetectedType(key)}>
                              Pakai jenis ini <ArrowRight className="w-3 h-3 ml-1" />
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                    {(detectRes.matching_accounts || []).length > 0 && (
                      <p className="text-[11px] text-muted-foreground">
                        Toko berplatform sama: {(detectRes.matching_accounts || [])
                          .map((a) => a.account_name).slice(0, 6).join(' · ')}
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  …atau pilih kelompoknya sendiri
                </h4>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {groups.map((g) => (
                    <button key={g.key}
                      data-testid={`import-group-${g.key}`}
                      onClick={() => setGroupKey(g.key)}
                      className="text-left rounded-[var(--radius-md)] border border-border p-3
                        bg-[hsl(var(--card))] transition hover:border-[hsl(var(--primary))]">
                      <div className="font-semibold text-sm">
                        {GROUP_ICON[g.label] || '📄'} {g.label}
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1 line-clamp-3">
                        {g.describe}
                      </p>
                      <Badge variant="outline" className="text-[10px] mt-2">
                        {(g.types || []).filter((t) => !t.deprecated).length} jenis data
                      </Badge>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {(groupKey || typeQuery.trim()) && types.length > 0 && visibleTypes.length === 0 && (
            <div className="rounded-[var(--radius-md)] border border-dashed border-border p-8 text-center"
              data-testid="import-type-empty">
              <p className="text-sm text-muted-foreground">
                {typeQuery.trim()
                  ? `Tidak ada jenis data yang cocok dengan “${typeQuery}”.`
                  : 'Kelompok ini belum punya jenis data yang aktif.'}
              </p>
              <Button variant="outline" size="sm" className="mt-3"
                onClick={() => { setTypeQuery(''); setGroupKey(''); }}>
                Kembali ke daftar kelompok
              </Button>
            </div>
          )}

          {groupNames.map((g) => (
            <div key={g}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                {GROUP_ICON[g] || '📄'} {g}
              </h4>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {grouped[g].map((t) => (
                  <button
                    key={t.key}
                    data-testid={`import-type-${t.key}`}
                    onClick={() => { setTypeKey(t.key); setStep(2); }}
                    className={`text-left rounded-[var(--radius-md)] border p-3 transition
                      bg-[hsl(var(--card))] hover:border-[hsl(var(--primary))]
                      ${typeKey === t.key ? 'border-[hsl(var(--primary))] ring-1 ring-[hsl(var(--primary))]'
                        : PRIMARY_TYPES.has(t.key) ? 'border-[hsl(var(--primary))]/60 shadow-sm'
                          : 'border-border'}`}
                  >
                    <div className="font-semibold text-sm flex items-start justify-between gap-2">
                      <span>{t.label}</span>
                      {PRIMARY_TYPES.has(t.key) && (
                        <Badge className="text-[10px] shrink-0 bg-[hsl(var(--primary))] text-white">
                          paling sering
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1 line-clamp-3">{t.describe}</p>
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                      <Badge variant="outline" className="text-[10px]">
                        <Database className="w-2.5 h-2.5 mr-1" />{t.collection}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">{t.total_columns} kolom</Badge>
                      {t.account_scope === 'required' && (
                        <Badge className="text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                          <Store className="w-2.5 h-2.5 mr-1" />pilih toko
                        </Badge>
                      )}
                      {(t.context || []).map((c) => (
                        <Badge key={c} className="text-[10px] bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300">
                          pilih {c === 'host' ? 'host' : c === 'creator' ? 'kreator' : 'katalog'}
                        </Badge>
                      ))}
                      {t.prenorm && (
                        <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                          berkas asli, tanpa dirapikan
                        </Badge>
                      )}
                      {/* F3 — dua penanda yang WAJIB terlihat sebelum staf memilih:
                          jenis ini tidak melahirkan pesanan baru, dan pemetaan
                          kolomnya belum diverifikasi dengan berkas asli owner. */}
                      {t.update_only && (
                        <Badge className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                          hanya memperbarui
                        </Badge>
                      )}
                      {t.mapping_unverified && (
                        <Badge className="text-[10px] bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300">
                          pemetaan perlu diperiksa
                        </Badge>
                      )}
                    </div>
                    {t.export_hint && (
                      <p className="text-[10px] text-muted-foreground mt-1.5 leading-snug">
                        Unduh dari: {t.export_hint}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* STEP 2 — konteks */}
      {step === 2 && selectedType && (
        <Card className="bg-[hsl(var(--card))]">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Store className="w-4 h-4" /> Konteks data: {selectedType.label}
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Konteks dipilih <b>sebelum</b> unggah supaya satu berkas tidak bisa
              tercampur antar toko, dan setiap baris hasil impor selalu bisa dicari
              lewat filter per toko.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              {needAccount && (
                <MarketingAccountSelect
                  token={token} value={accountId}
                  onChange={(v) => { setAccountId(v); setHostId(''); setCreatorId(''); setCatalogId(''); setLiveSessionId(''); }}
                  testId="import-account-select"
                />
              )}
              {needHost && (
                <MarketingHostSelect token={token} accountId={accountId}
                  value={hostId} onChange={setHostId} testId="import-host-select" />
              )}
              {needCreator && (
                <MarketingCreatorSelect token={token} accountId={accountId}
                  value={creatorId} onChange={setCreatorId} testId="import-creator-select" />
              )}
              {needCatalog && (
                <div>
                  <label className="text-xs font-medium text-foreground/80 mb-1 block">
                    Katalog tujuan <span className="text-red-500">*</span>
                  </label>
                  <Select value={catalogId} onValueChange={setCatalogId} disabled={!accountId}>
                    <SelectTrigger data-testid="import-catalog-select" className="h-9">
                      <SelectValue placeholder={accountId ? 'Pilih katalog…' : 'Pilih toko dulu'} />
                    </SelectTrigger>
                    <SelectContent>
                      {catalogs.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {needLiveSession && (
                <div className="sm:col-span-2">
                  <label className="text-xs font-medium text-foreground/80 mb-1 block">
                    Sesi live tujuan <span className="text-red-500">*</span>
                  </label>
                  <Select value={liveSessionId} onValueChange={setLiveSessionId}
                    disabled={!accountId}>
                    <SelectTrigger data-testid="import-live-session-select" className="h-9">
                      <SelectValue placeholder={accountId ? 'Pilih sesi live…' : 'Pilih toko dulu'} />
                    </SelectTrigger>
                    <SelectContent className="max-h-72">
                      {liveSessions.map((s) => (
                        <SelectItem key={s.id} value={s.id}>
                          {String(s.session_date || '').slice(0, 10)} · {s.title}
                          <span className="text-muted-foreground ml-1 text-xs">
                            ({s.host_name || 'tanpa host'} · Rp {Number(s.revenue || 0).toLocaleString('id-ID')})
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {accountId && liveSessions.length === 0 && (
                    <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1">
                      Toko ini belum punya sesi live. Catat sesinya dulu di
                      <b> Live Selling → Catat Sesi Live</b> — rincian produk harus
                      menempel pada sesi yang nyata.
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="rounded-[var(--radius-sm)] border border-border bg-muted/40 p-3">
              <p className="text-xs flex items-start gap-1.5">
                <Info className="w-3.5 h-3.5 mt-px shrink-0 text-[hsl(var(--primary))]" />
                <span>
                  Data akan masuk ke <b>{selectedType.collection}</b> dan bisa dilihat di
                  menu <b>{selectedType.module_hint || '—'}</b>.
                  {selectedType.prenorm ? (
                    <> Kolomnya dibaca otomatis dari bentuk ekspor Seller Center —
                    unggah berkasnya <b>apa adanya</b> (jangan dirapikan).</>
                  ) : (
                    <> Kolom wajib: <b>{(selectedType.required_columns || []).join(', ') || '—'}</b>.</>
                  )}
                </span>
              </p>
            </div>
            <div className="flex justify-between">
              <Button variant="outline" size="sm" onClick={() => setStep(1)}>
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Ganti jenis data
              </Button>
              <Button size="sm" disabled={!contextReady} onClick={() => setStep(3)}
                data-testid="import-context-next">
                Lanjut <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* STEP 3 — template & unggah */}
      {step === 3 && selectedType && (
        <Card className="bg-[hsl(var(--card))]">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4" /> Template &amp; unggah berkas
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedType.prenorm ? (
              /* F7.2 — berkas KPI Seller Center TIDAK punya template: baris pertamanya
                 memang bukan header. Menawarkan template di sini justru mengajak staf
                 "merapikan" berkas — persis yang membuat impor gagal. */
              <div className="rounded-[var(--radius-md)] border border-emerald-500/40 bg-emerald-500/10 p-3"
                data-testid="import-prenorm-hint">
                <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5" /> Unggah berkas ASLI — jangan diubah
                </p>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Jenis ini tidak memakai template. Sistem sudah mengenali bentuk ekspor
                  Seller Center: baris judul grup kolom, baris metadata (Username / Nama
                  Toko / Periode), blok “Sumber Penonton”, dan sheet ganda akan dipotong
                  otomatis. Menghapus/merapikan baris justru membuat berkas tidak dikenali.
                </p>
                {selectedType.export_hint && (
                  <p className="text-[11px] mt-1.5">
                    <b>Unduh dari:</b> {selectedType.export_hint}
                  </p>
                )}
              </div>
            ) : (
              <>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => downloadTemplate('xlsx')}
                    disabled={busy === 'template'} data-testid="import-template-xlsx">
                    <Download className="w-3.5 h-3.5 mr-1.5" /> Template Excel (.xlsx)
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => downloadTemplate('csv')}
                    disabled={busy === 'template'} data-testid="import-template-csv">
                    <Download className="w-3.5 h-3.5 mr-1.5" /> Template CSV
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Template Excel punya lembar <b>Petunjuk</b>: jenis isi tiap kolom,
                  mana yang wajib, dan header lain yang tetap dikenali (mis. header asli
                  ekspor Shopee/TikTok). Anda juga boleh mengunggah berkas ekspor apa adanya —
                  pemetaan kolom akan ditampilkan untuk diperiksa.
                </p>
              </>
            )}
            <div
              className="rounded-[var(--radius-md)] border-2 border-dashed border-border p-6 text-center bg-muted/30"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]); }}
            >
              <Upload className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm font-medium">{file ? file.name : 'Pilih berkas CSV / Excel'}</p>
              <p className="text-[11px] text-muted-foreground mt-1">Maks 15 MB · .csv .xlsx</p>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.tsv" className="hidden"
                data-testid="import-file-input"
                onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <Button variant="outline" size="sm" className="mt-3"
                onClick={() => fileRef.current?.click()} data-testid="import-file-browse">
                Pilih berkas
              </Button>
            </div>

            {/* F8 — pintu masuk ke ingatan pemetaan SEBELUM unggah. Kalau impor
                kemarin salah petakan, staf harus bisa melupakannya tanpa harus
                mengunggah berkas lagi lebih dulu. */}
            <p className="text-[11px] text-muted-foreground">
              Berkas rutin dengan susunan kolom yang sama akan memakai pemetaan yang
              pernah Anda konfirmasi (langsung siap, tanpa memetakan ulang).{' '}
              <button type="button" onClick={loadFormats} data-testid="import-formats-open-step3"
                className="underline text-[hsl(var(--primary))] hover:opacity-80">
                Lihat / lupakan pemetaan yang diingat
              </button>
            </p>

            <div className="flex justify-between">
              <Button variant="outline" size="sm" onClick={() => setStep(2)}>
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Kembali
              </Button>
              <Button size="sm" onClick={upload} disabled={!file || busy === 'upload'}
                data-testid="import-upload-btn">
                {busy === 'upload' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  : <Upload className="w-3.5 h-3.5 mr-1.5" />}
                Unggah &amp; periksa
              </Button>
            </div>

            {blockError?.where === 'upload' && (
              <div className="rounded-[var(--radius-md)] border border-red-500/40 bg-red-500/10 p-3"
                data-testid="import-upload-error">
                <p className="text-xs font-semibold text-red-600 dark:text-red-400 flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" /> {blockError.title}
                </p>
                <p className="text-xs mt-1">{blockError.detail}</p>
                <div className="flex gap-2 mt-2">
                  <Button variant="outline" size="sm" onClick={() => { setBlockError(null); setStep(2); }}>
                    <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Ganti toko tujuan
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setBlockError(null)}>
                    Tutup pesan
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* STEP 4 — pemetaan kolom */}
      {step === 4 && session && (
        <Card className="bg-[hsl(var(--card))]">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base flex items-center gap-2">
                <ListChecks className="w-4 h-4" /> Pemetaan kolom
                <Badge variant="outline" className="text-[10px]">{session.filename}</Badge>
                <Badge variant="outline" className="text-[10px]">{session.total_rows} baris</Badge>
              </CardTitle>
              <Button variant="outline" size="sm" onClick={askAI} disabled={busy === 'ai'}
                data-testid="import-ai-assist">
                {busy === 'ai' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  : <Sparkles className="w-3.5 h-3.5 mr-1.5" />}
                Bantu petakan dengan AI (opsional)
              </Button>
            </div>
            {report && (
              <div className="flex flex-wrap gap-2 mt-2 text-[11px]">
                <Badge variant="outline">{report.mapped}/{report.total_columns} kolom terpakai</Badge>
                {Object.entries(report.methods || {}).filter(([, v]) => v > 0).map(([k, v]) => (
                  <span key={k} className={`px-2 py-0.5 rounded-full ${METHOD_BADGE[k]?.cls || ''}`}>
                    {METHOD_BADGE[k]?.label || k}: {v}
                  </span>
                ))}
                {report.missing_required?.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300">
                    wajib belum terpetakan: {report.missing_required.join(', ')}
                  </span>
                )}
                {pendingSuggestions > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]"
                    data-testid="import-pending-suggestions">
                    {pendingSuggestions} kolom punya usulan menunggu keputusan Anda
                  </span>
                )}
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {/* ── SESI #34 · SISTEM MEMBANTAH PILIHAN JENIS YANG KEMUNGKINAN SALAH ──
                Pemilik: "bisa saja user ingin input pesanan tapi dia pilih
                importnya berbeda… saya ingin system bisa tau dan assist".
                Sistem TIDAK memindahkan apa pun sendiri — ia menunjukkan bukti
                (berapa kolom cocok, kolom wajib apa yang hilang) dan menyediakan
                satu tombol untuk pindah jenis. */}
            {session.detection?.type_mismatch && (
              <div className="rounded-[var(--radius-md)] border border-amber-500/50 bg-amber-500/10 p-3
                text-xs space-y-2" data-testid="import-type-mismatch">
                <p className="font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4" /> Jenis data ini sepertinya bukan yang Anda pilih
                </p>
                <p className="text-muted-foreground">{session.detection.type_mismatch.message}</p>
                <Button size="sm" variant="outline" data-testid="import-type-mismatch-switch"
                  onClick={() => {
                    setTypeKey(session.detection.type_mismatch.suggested);
                    setSession(null); setMapping([]); setReport(null); setRows([]);
                    setStep(1);
                    toast({ title: `Jenis diganti ke “${session.detection.type_mismatch.suggested_label}”`,
                      description: 'Unggah ulang berkasnya untuk jenis ini.' });
                  }}>
                  Pakai “{session.detection.type_mismatch.suggested_label}”
                </Button>
              </div>
            )}
            {(session.detection?.platform_detected || session.detection?.platform_mismatch) && (
              <div className={`rounded-[var(--radius-md)] border p-2.5 text-[11px] ${
                session.detection.platform_mismatch
                  ? 'border-red-500/50 bg-red-500/10' : 'border-border bg-muted/40'}`}
                data-testid="import-platform-detect">
                {session.detection.platform_mismatch ? (
                  <p className="text-red-600 dark:text-red-400 font-semibold">
                    {session.detection.platform_mismatch}
                  </p>
                ) : (
                  <p className="text-muted-foreground">
                    Platform berkas terdeteksi <b className="uppercase">{session.detection.platform_detected}</b>
                    {' '}dari sidik kolom{session.detection.platform_evidence?.length
                      ? ` (${session.detection.platform_evidence.slice(0, 3).join(', ')})` : ''} —
                    cocok dengan toko {session.account_name}.
                  </p>
                )}
              </div>
            )}
            {/* F8 — ASAL-USUL PEMETAAN. Tanpa panel ini, kolom yang sudah
                terpetakan sebelum staf menyentuh apa pun tampak seperti sihir
                (atau AI) — padahal itu pemetaan yang PERNAH DIKONFIRMASI MANUSIA
                untuk susunan kolom yang sama. Yang berbahaya: kalau konfirmasi
                dulu itu SALAH, kesalahannya terpasang otomatis setiap hari. */}
            {session.format_memory && !forgotten && (
              <div className="rounded-[var(--radius-md)] border border-[hsl(var(--primary))]/40
                bg-[hsl(var(--primary))]/5 p-3 text-xs space-y-1.5"
                data-testid="import-format-memory">
                <p className="font-semibold text-[hsl(var(--primary))] flex items-center gap-1.5">
                  <History className="w-4 h-4" /> Pemetaan ini DIINGAT dari impor sebelumnya
                </p>
                <p className="text-muted-foreground">
                  Susunan kolom berkas ini pernah Anda konfirmasi sendiri
                  {session.format_memory.use_count > 0
                    && ` dan sudah dipakai ${session.format_memory.use_count}×`}
                  {session.format_memory.last_used_by
                    && ` — terakhir oleh ${session.format_memory.last_used_by}`}
                  {session.format_memory.last_used_at
                    && ` (${String(session.format_memory.last_used_at).slice(0, 16).replace('T', ' ')})`}.
                  {' '}Ini <b>bukan tebakan AI</b>. Kalau pemetaannya ternyata salah,
                  perbaiki di tabel bawah — koreksi Anda yang akan diingat berikutnya —
                  atau lupakan ingatannya sekarang.
                </p>
                {(session.format_memory.dropped || []).length > 0 && (
                  <p className="text-amber-700 dark:text-amber-300"
                    data-testid="import-format-memory-dropped">
                    {session.format_memory.dropped.length} pemetaan tersimpan DIBUANG karena
                    field-nya sudah tidak ada di jenis data ini
                    ({session.format_memory.dropped.map((d) => d.column).join(', ')})
                    — kolomnya dipetakan ulang oleh mesin, periksa di tabel bawah.
                  </p>
                )}
                <div className="flex flex-wrap gap-2 pt-0.5">
                  <Button variant="outline" size="sm" className="h-7 text-[11px]"
                    disabled={busy === 'forget'}
                    onClick={() => forgetFormat(session.format_fingerprint, typeKey, true)}
                    data-testid="import-forget-format">
                    <Trash2 className="w-3 h-3 mr-1" /> Lupakan pemetaan ini
                  </Button>
                  <Button variant="ghost" size="sm" className="h-7 text-[11px]"
                    onClick={loadFormats} data-testid="import-open-formats">
                    Lihat semua susunan kolom yang diingat
                  </Button>
                </div>
              </div>
            )}
            {forgotten && (
              <p className="text-[11px] text-muted-foreground" data-testid="import-format-forgotten">
                Ingatan untuk susunan kolom ini sudah dilupakan. Pemetaan di bawah tetap
                berlaku untuk impor ini; impor <b>berikutnya</b> akan dipetakan ulang oleh
                mesin dan meminta konfirmasi Anda lagi.
              </p>
            )}
            {/* F3 — PANEL PENOLONG PEMETAAN. Tanpa ini, satu-satunya petunjuk
                "kolom wajib mana yang belum terpetakan" adalah badge kecil di
                header, dan staf harus menebak kolom berkas mana yang cocok. */}
            {report?.missing_required?.length > 0 && (
              <div className="rounded-[var(--radius-md)] border border-red-500/40 bg-red-500/10 p-3
                text-xs space-y-2" data-testid="import-missing-required">
                <p className="font-semibold text-red-600 dark:text-red-400 flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" /> Kolom WAJIB belum terpetakan:{' '}
                  {report.missing_required.join(', ')}
                </p>
                <p className="text-muted-foreground">
                  Tombol “Lihat pratinjau” terbuka begitu semua field wajib punya
                  kolomnya. Kalau ada usulan di bawah, satu klik langsung memasangnya —
                  <b> mesin tidak pernah memasang sendiri</b>.
                </p>
                {/* F3.E — pembalikan usulan: field wajib → kolom berkas kandidat.
                    Ini yang mengubah "silakan cari sendiri" menjadi satu klik. */}
                <div className="space-y-1.5">
                  {requiredHints.map((h) => (
                    <div key={h.label} className="flex flex-wrap items-center gap-1.5"
                      data-testid={`required-hint-${h.name || h.label}`}>
                      <span className="font-semibold">{h.label}</span>
                      {h.example && (
                        <span className="text-muted-foreground">(contoh isi: {h.example})</span>
                      )}
                      <span className="text-muted-foreground">←</span>
                      {h.candidates.length === 0 ? (
                        <span className="text-muted-foreground">
                          tidak ada kolom berkas yang mirip — pilih manual di tabel bawah
                        </span>
                      ) : h.candidates.map((c) => (
                        <button key={c.column} type="button"
                          onClick={() => changeMap(c.column, h.name)}
                          data-testid={`required-pick-${h.name}-${c.column}`}
                          className="px-1.5 py-0.5 rounded border border-[hsl(var(--primary))]/50
                            text-[10px] text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10">
                          pakai kolom “{c.column}” ({Math.round((c.score || 0) * 100)}%)
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {unmappedCols.length > 0 && (
              <p className="text-[11px] text-muted-foreground" data-testid="import-unused-columns">
                <b>{unmappedCols.length} kolom berkas tidak dipakai</b> — itu boleh:
                kolom yang tidak dikenali TIDAK ditebak diam-diam. Kalau salah satunya
                sebenarnya penting, pilih field-nya di tabel bawah.
              </p>
            )}
            {/* ── SESI #34 · VIEWER TABEL BERKAS ─────────────────────────────
                Pemilik: "saat ini pilih pemetaan kolom tidak ada visual
                table-nya, ini agak sulit". 10 baris pertama berkas ditampilkan
                apa adanya, dan judul kolomnya menyebut field tujuannya — jadi
                pemetaan bisa DIPERIKSA dengan mata, bukan dihafal. */}
            {(session?.raw_preview || []).length > 0 && (
              <div className="space-y-1.5" data-testid="import-file-viewer">
                <p className="text-[11px] text-muted-foreground">
                  <b>Isi berkas Anda</b> — {session.raw_preview.length} baris pertama dari{' '}
                  {session.total_rows} baris. Kolom berwarna sudah punya tujuan; kolom kelabu
                  belum dipakai.
                </p>
                <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border max-h-64">
                  <table className="text-[11px] whitespace-nowrap">
                    <thead className="bg-muted/60 sticky top-0">
                      <tr>
                        {(session.headers || []).map((h) => {
                          const m = mapping.find((x) => x.column === h);
                          return (
                            <th key={h} className={`px-2 py-1 text-left font-semibold border-r border-border
                              ${m?.field ? 'text-[hsl(var(--primary))]' : 'text-muted-foreground'}`}
                              data-testid={`viewer-col-${h}`}>
                              <div className="font-mono">{h}</div>
                              <div className="text-[9px] font-normal">
                                {m?.field ? `→ ${m.field_label || m.field}` : '(tidak dipakai)'}
                              </div>
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {session.raw_preview.map((r, i) => (
                        <tr key={i} className="border-t border-border">
                          {(session.headers || []).map((h) => (
                            <td key={h} className="px-2 py-1 border-r border-border max-w-[160px] truncate"
                              title={String(r[h] ?? '')}>
                              {String(r[h] ?? '') || '—'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── SESI #34 · PEMETAAN DIBALIK & KOMPAK ────────────────────────
                Satu baris = satu kolom TEMPLATE (data sistem). Yang dipilih
                adalah kolom BERKAS pengisinya. Kolom wajib di atas. */}
            <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border">
              <table className="w-full text-xs" data-testid="import-map-by-field">
                <thead className="bg-muted/60">
                  <tr>
                    <th className="px-2 py-1.5 text-left font-semibold">Kolom sistem (template)</th>
                    <th className="px-2 py-1.5 text-left font-semibold">Diisi kolom berkas</th>
                    <th className="px-2 py-1.5 text-left font-semibold">Contoh isi</th>
                    <th className="px-2 py-1.5 text-left font-semibold">Dasar</th>
                  </tr>
                </thead>
                <tbody>
                  {fieldRows.map((fr) => (
                    <tr key={fr.name} className={`border-t border-border hover:bg-muted/40 ${
                      fr.required && !fr.column ? 'bg-red-500/5' : ''}`}
                      data-testid={`fieldrow-${fr.name}`}>
                      <td className="px-2 py-1">
                        <span className="font-medium">{fr.label}</span>
                        {fr.required && <span className="text-red-500 ml-1">*</span>}
                        <span className="ml-1.5 text-[10px] text-muted-foreground">{fr.kind}</span>
                        {fr.example ? (
                          <div className="text-[10px] text-muted-foreground">contoh: {fr.example}</div>
                        ) : null}
                      </td>
                      <td className="px-2 py-1">
                        <Select value={fr.column || '__none__'}
                          onValueChange={(v) => changeField(fr.name, v)}>
                          <SelectTrigger className="h-7 w-full max-w-[240px] text-xs"
                            data-testid={`fieldmap-${fr.name}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            <SelectItem value="__none__">— tidak ada di berkas —</SelectItem>
                            {(session?.headers || []).map((h) => (
                              <SelectItem key={h} value={h}>{h}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="px-2 py-1 text-muted-foreground max-w-[160px] truncate"
                        title={fr.column ? sampleFor(fr.column) : ''}>
                        {fr.column ? (sampleFor(fr.column) || '—') : '—'}
                      </td>
                      <td className="px-2 py-1">
                        {fr.column ? (
                          <span className={`px-1.5 py-0.5 rounded-full ${METHOD_BADGE[fr.method]?.cls || ''}`}>
                            {METHOD_BADGE[fr.method]?.label || fr.method}
                          </span>
                        ) : fr.candidates.length ? (
                          <span className="inline-flex flex-wrap gap-1">
                            {fr.candidates.slice(0, 2).map((c) => (
                              <button key={c.column} type="button"
                                onClick={() => changeField(fr.name, c.column)}
                                data-testid={`fieldpick-${fr.name}-${c.column}`}
                                className="px-1.5 py-0.5 rounded border border-[hsl(var(--primary))]/50
                                  text-[10px] text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10">
                                pakai “{c.column}”
                              </button>
                            ))}
                          </span>
                        ) : (
                          <span className="text-[10px] text-muted-foreground">
                            {fr.required ? 'wajib — pilih kolomnya' : 'kosong (boleh)'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Arah lama tetap ada di bawah sebagai pemeriksaan silang: kolom
                berkas mana yang belum punya tujuan. */}
            <details className="rounded-[var(--radius-sm)] border border-border">
              <summary className="px-3 py-2 text-xs cursor-pointer text-muted-foreground"
                data-testid="import-map-by-column-toggle">
                Lihat dari sisi berkas ({mapping.length} kolom · {unmappedCols.length} belum dipakai)
              </summary>
              <div className="overflow-x-auto border-t border-border">
                <table className="w-full text-xs">
                  <thead className="bg-muted/60">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold">Kolom di berkas</th>
                      <th className="px-3 py-2 text-left font-semibold">Contoh isi</th>
                      <th className="px-3 py-2 text-left font-semibold">Dipetakan ke field</th>
                      <th className="px-3 py-2 text-left font-semibold">
                        Dasar keputusan &amp; usulan
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                  {mapping.map((m) => (
                    <tr key={m.column} className="border-t border-border hover:bg-muted/40">
                      <td className="px-3 py-1.5 font-mono">{m.column}</td>
                      <td className="px-3 py-1.5 text-muted-foreground max-w-[160px] truncate"
                        title={sampleFor(m.column)}>
                        {sampleFor(m.column) || '—'}
                      </td>
                      <td className="px-3 py-1.5">
                        <Select value={m.field || '__none__'}
                          onValueChange={(v) => changeMap(m.column, v)}>
                          <SelectTrigger className="h-8 w-full max-w-[260px]"
                            data-testid={`map-${m.column}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            <SelectItem value="__none__">— tidak dipakai —</SelectItem>
                            {(selectedType?.fields || []).map((f) => (
                              <SelectItem key={f.name} value={f.name}>
                                {f.label}{f.required ? ' *' : ''}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="px-3 py-1.5">
                        <span className={`px-2 py-0.5 rounded-full ${METHOD_BADGE[m.method]?.cls || ''}`}>
                          {METHOD_BADGE[m.method]?.label || m.method}
                          {m.method === 'fuzzy' || m.method === 'suggest'
                            ? ` ${Math.round((m.score || 0) * 100)}%` : ''}
                        </span>
                        {/* Usulan mesin: SEKALI KLIK dipakai, tetapi tetap PILIHAN
                            manusia — tidak pernah dipasang sendiri. */}
                        {!m.field && (m.candidates || []).length > 0 && (
                          <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                            {m.candidates.slice(0, 3).map((c) => (
                              <button key={c.field} type="button"
                                onClick={() => changeMap(m.column, c.field)}
                                data-testid={`map-suggest-${m.column}-${c.field}`}
                                className="px-1.5 py-0.5 rounded border border-[hsl(var(--primary))]/50
                                  text-[10px] text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10">
                                pakai: {c.field_label} ({Math.round((c.score || 0) * 100)}%)
                              </button>
                            ))}
                          </span>
                        )}
                        {m.note && (
                          <p className="text-[10px] text-muted-foreground mt-0.5">{m.note}</p>
                        )}
                      </td>
                    </tr>
                  ))}
                  </tbody>
                </table>
              </div>
            </details>
            <div className="flex justify-between">
              <Button variant="outline" size="sm" onClick={() => setStep(3)}>
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Ganti berkas
              </Button>
              <Button size="sm" onClick={() => setStep(5)} disabled={!report?.ready || busy === 'mapping'}
                data-testid="import-mapping-next">
                Lihat pratinjau <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* STEP 5 — pratinjau */}
      {step === 5 && session && (
        <Card className="bg-[hsl(var(--card))]">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Table2 className="w-4 h-4" /> Pratinjau &amp; validasi
            </CardTitle>
            {summary && (
              <div className="flex flex-wrap gap-2 mt-2 text-[11px]">
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                  <CheckCircle2 className="w-3 h-3 inline mr-1" />{summary.valid} siap
                </span>
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                  <AlertTriangle className="w-3 h-3 inline mr-1" />{summary.warning} peringatan
                </span>
                <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300">
                  <XCircle className="w-3 h-3 inline mr-1" />{summary.error} ditolak
                </span>
                <span className="text-muted-foreground">dari {summary.total} baris dibaca</span>
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border max-h-[420px]">
              <table className="w-full text-xs">
                <thead className="bg-muted/60 sticky top-0">
                  <tr>
                    <th className="px-2 py-2 text-left">#</th>
                    <th className="px-2 py-2 text-left">Status</th>
                    {(selectedType?.fields || []).filter((f) => f.required).map((f) => (
                      <th key={f.name} className="px-2 py-2 text-left">{f.label}</th>
                    ))}
                    <th className="px-2 py-2 text-left">Catatan</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.row_id} className="border-t border-border">
                      <td className="px-2 py-1.5 text-muted-foreground">{r.row_id + 2}</td>
                      <td className="px-2 py-1.5">
                        {r.status === 'valid' && <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 text-[10px]">siap</Badge>}
                        {r.status === 'warning' && <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300 text-[10px]">periksa</Badge>}
                        {r.status === 'error' && <Badge className="bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300 text-[10px]">ditolak</Badge>}
                      </td>
                      {(selectedType?.fields || []).filter((f) => f.required).map((f) => (
                        <td key={f.name} className="px-2 py-1.5">{String(r.data?.[f.name] ?? '—')}</td>
                      ))}
                      <td className="px-2 py-1.5 text-[11px] text-muted-foreground">
                        {[...(r.errors || []), ...(r.warnings || [])].join(' · ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* IMPOR BERTINDIH — dijawab SEBELUM tombol simpan ditekan.
                Berkas yang rentang tanggalnya beririsan (mis. 1–7 lalu 5–12) TIDAK
                melahirkan baris ganda: pencocokan dilakukan per BARIS lewat kunci
                dedupe. Tetapi memilih "Lewati" atau "Perbarui" tanpa tahu berapa
                baris yang terdampak = memilih dengan mata tertutup. */}
            {dups?.checked && (
              <div className={`rounded-[var(--radius-md)] border p-3 text-xs space-y-1
                ${dups.existing > 0 ? 'border-amber-500/40 bg-amber-500/10'
                  : 'border-border bg-muted/40'}`} data-testid="import-duplicates">
                {dups.existing > 0 ? (
                  <>
                    <p className="font-semibold text-amber-700 dark:text-amber-300">
                      {dups.existing} baris di berkas ini SUDAH ADA di sistem
                      {dups.overlap_date_from && (
                        <> — tanggal yang bertindih: {dups.overlap_date_from} s/d{' '}
                        {dups.overlap_date_to}</>)}
                    </p>
                    <p className="text-muted-foreground">
                      Sisanya <b>{dups.new} baris baru</b>. Pencocokan dilakukan
                      per baris memakai kunci <b>{(dups.dedupe || []).join(' + ')}</b>,
                      bukan per rentang tanggal — jadi mengimpor rentang yang
                      beririsan <b>tidak</b> melahirkan baris kembar. Pilihan di bawah
                      menentukan perlakuan {dups.existing} baris itu:{' '}
                      <b>Lewati</b> = biarkan apa adanya · <b>Perbarui yang lama</b> =
                      ikuti isi berkas ini (termasuk perubahan status, mis. dari
                      “perlu dikirim” menjadi “dibatalkan”). Status tidak pernah
                      dibuat MUNDUR, dan pembatalan otomatis melepas reservasi stok.
                    </p>
                    {(dups.sample || []).length > 0 && (
                      <p className="text-muted-foreground">
                        Contoh: {dups.sample.map((x) => (
                          `${x.ref}${x.status_now ? ` (sekarang: ${x.status_now})` : ''}`
                        )).join(' · ')}
                        {dups.existing > (dups.sample || []).length ? ' …' : ''}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-muted-foreground">
                    Tidak ada baris di berkas ini yang sudah ada di sistem
                    {dups.file_date_from && (
                      <> (rentang tanggal berkas: {dups.file_date_from} s/d{' '}
                      {dups.file_date_to})</>)} — semuanya baru.
                  </p>
                )}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Kalau baris sudah ada:</span>
                <Select value={onDuplicate} onValueChange={setOnDuplicate}>
                  <SelectTrigger className="h-8 w-44" data-testid="import-dup-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip">Lewati (jangan ganda)</SelectItem>
                    <SelectItem value="update">Perbarui yang lama</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {summary?.error > 0 && (
                <Button variant="outline" size="sm" onClick={downloadErrors}
                  data-testid="import-download-errors">
                  <Download className="w-3.5 h-3.5 mr-1.5" /> Unduh daftar baris bermasalah
                </Button>
              )}
            </div>

            {/* FASE 4 — RENCANA PER BARIS. Sengaja ditempatkan SESUDAH pemilih
                "kalau baris sudah ada" dan SEBELUM tombol Simpan: memilih mode
                lalu langsung melihat akibatnya, di layar yang sama, tanpa harus
                menyimpan dulu. */}
            <ImportPlanPanel sessionId={session.id} authH={authH}
              onDuplicate={onDuplicate} onPlan={setPlanInfo}
              onDownload={downloadAuthed} />

            <div className="flex justify-between">
              <Button variant="outline" size="sm" onClick={() => setStep(4)}>
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" /> Perbaiki pemetaan
              </Button>
              <Button size="sm" onClick={commit}
                disabled={busy === 'commit' || !summary?.valid
                  || (planInfo?.blockers || []).length > 0}
                title={(planInfo?.blockers || []).length > 0
                  ? 'Ada penghalang yang membuat penyimpanan pasti ditolak — lihat panel merah di atas'
                  : undefined}
                data-testid="import-commit-btn">
                {busy === 'commit' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                Simpan {summary?.valid || 0} baris
              </Button>
            </div>

            {blockError?.where === 'commit' && (
              <div className="rounded-[var(--radius-md)] border border-red-500/40 bg-red-500/10 p-3"
                data-testid="import-commit-error">
                <p className="text-xs font-semibold text-red-600 dark:text-red-400 flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" /> {blockError.title}
                </p>
                <p className="text-xs mt-1">{blockError.detail}</p>
                <Button variant="ghost" size="sm" className="mt-2"
                  onClick={() => setBlockError(null)}>Tutup pesan</Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* STEP 6 — hasil */}
      {step === 6 && result && (
        <Card className="bg-[hsl(var(--card))]" data-testid="import-result">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-5 h-5" /> Impor selesai
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">{result.message}</p>

            {/* F3.D — RINGKASAN KHUSUS "hanya memperbarui".
                Empat kartu yang sama dipakai untuk dua bentuk impor yang artinya
                berbeda. Pada Ekspor B/C, "Baris masuk 0" adalah HASIL YANG BENAR,
                tetapi staf membacanya sebagai kegagalan lalu mengunggah ulang
                Ekspor A — dan justru pengulangan itu yang membekukan status
                pesanan lama. Karena itu di sini urutan kartu dibalik (yang naik
                = "Diperbarui") dan angka 0 diberi keterangannya sendiri. */}
            {selectedType?.update_only ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3"
                  data-testid="import-result-update-only">
                  <div className="rounded-[var(--radius-sm)] border-2 border-blue-500/50 bg-blue-500/5 p-3">
                    <p className="text-[11px] text-muted-foreground">Pesanan diperbarui</p>
                    <p className="text-2xl font-bold text-blue-600 dark:text-blue-400"
                      data-testid="import-result-updated">{result.updated ?? 0}</p>
                    <p className="text-[10px] text-muted-foreground">ini angka yang dihitung</p>
                  </div>
                  <div className="rounded-[var(--radius-sm)] border border-border p-3">
                    <p className="text-[11px] text-muted-foreground">Ditolak</p>
                    <p className="text-xl font-bold text-red-600">{result.rejected ?? 0}</p>
                    <p className="text-[10px] text-muted-foreground">
                      belum pernah diimpor / status mundur
                    </p>
                  </div>
                  <div className="rounded-[var(--radius-sm)] border border-border p-3">
                    <p className="text-[11px] text-muted-foreground">Baris masuk</p>
                    <p className="text-xl font-bold text-muted-foreground">{result.inserted ?? 0}</p>
                    <p className="text-[10px] text-muted-foreground">
                      0 memang benar — jenis ini tidak membuat pesanan baru
                    </p>
                  </div>
                  <div className="rounded-[var(--radius-sm)] border border-border p-3">
                    <p className="text-[11px] text-muted-foreground">Bisa dipulihkan</p>
                    <p className="text-xl font-bold text-foreground">{result.undo_count ?? 0}</p>
                    <p className="text-[10px] text-muted-foreground">
                      keadaan sebelum diubah tersimpan
                    </p>
                  </div>
                </div>
                <div className="rounded-[var(--radius-sm)] border border-blue-500/30 bg-blue-500/5 p-3 text-xs"
                  data-testid="import-result-update-only-note">
                  <b>Jangan unggah ulang Ekspor A untuk “memperbaiki” angka ini.</b>{' '}
                  Ekspor A tidak memuat pesanan yang sudah selesai; mengunggahnya
                  ulang justru mengembalikan pesanan lama ke “perlu dikirim”.
                  Kalau ada baris yang ditolak, perbaiki nomor pesanannya atau
                  impor Ekspor A untuk pesanan yang benar-benar baru.
                </div>
              </>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[['Baris masuk', result.inserted, 'text-emerald-600'],
                  ['Diperbarui', result.updated, 'text-blue-600'],
                  ['Duplikat dilewati', result.skipped_duplicates, 'text-amber-600'],
                  ['Ditolak', result.rejected, 'text-red-600']].map(([l, v, c]) => (
                    <div key={l} className="rounded-[var(--radius-sm)] border border-border p-3">
                      <p className="text-[11px] text-muted-foreground">{l}</p>
                      <p className={`text-xl font-bold ${c}`}>{v ?? 0}</p>
                    </div>
                  ))}
              </div>
            )}
            {result.row_notes?.length > 0 && (
              <div className="rounded-[var(--radius-sm)] border border-border max-h-56 overflow-y-auto">
                <table className="w-full text-[11px]">
                  <thead className="bg-muted/60"><tr>
                    <th className="px-2 py-1.5 text-left">Baris</th>
                    <th className="px-2 py-1.5 text-left">Tindakan</th>
                    <th className="px-2 py-1.5 text-left">Keterangan</th>
                  </tr></thead>
                  <tbody>
                    {result.row_notes.map((n, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-2 py-1">{n.row}</td>
                        <td className="px-2 py-1">{n.action}</td>
                        <td className="px-2 py-1 text-muted-foreground">{(n.why || []).join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* FASE 4 — LAPORAN HASIL YANG BISA DIBAWA PULANG.
                Tabel di atas hanya memuat 200 catatan pertama dan hilang begitu
                halaman ditutup. Baris yang DITOLAK harus bisa dibawa kembali ke
                berkas aslinya untuk diperbaiki; kalau tidak, "12 baris ditolak"
                berakhir sebagai 12 pesanan yang hilang tanpa jejak. */}
            <div className="flex flex-wrap items-center gap-2" data-testid="import-result-download">
              <Button variant="outline" size="sm"
                onClick={() => downloadAuthed(
                  `sessions/${session.id}/result.csv`,
                  `hasil-impor-${session.id.slice(0, 8)}.csv`)}
                data-testid="import-result-csv">
                <Download className="w-3.5 h-3.5 mr-1.5" /> Unduh laporan hasil (CSV)
              </Button>
              {(result.rejected ?? 0) > 0 && (
                <Button variant="outline" size="sm"
                  onClick={() => downloadAuthed(
                    `sessions/${session.id}/result.csv`,
                    `baris-ditolak-${session.id.slice(0, 8)}.csv`,
                    { only_rejected: true })}
                  data-testid="import-result-csv-rejected">
                  <Download className="w-3.5 h-3.5 mr-1.5" />
                  Unduh {result.rejected} baris DITOLAK + alasannya
                </Button>
              )}
            </div>
            {result.daily_rollup && (
              <div className="rounded-[var(--radius-sm)] border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs"
                data-testid="import-rollup-info">
                <b>Rekap harian ikut diperbarui otomatis</b> — {result.daily_rollup.upserted} tanggal
                dihitung ulang dari pesanan ({result.daily_rollup.orders} pesanan ·
                Rp {Number(result.daily_rollup.revenue_product || 0).toLocaleString('id-ID')}).
                Angka ini yang dipakai Target, Dashboard, dan Laporan — tidak perlu diketik lagi.
              </div>
            )}
            {selectedType?.is_grouped && (
              <SkuMappingPanel sessionId={session.id} token={token} />
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={resetAll} data-testid="import-again">Impor berkas lain</Button>
              <Button variant="outline" size="sm"
                onClick={() => askRollback(session.id)} data-testid="import-rollback-btn">
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                {selectedType?.update_only ? 'Batalkan & pulihkan pesanan' : 'Batalkan impor ini'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* RIWAYAT */}
      <Card className="bg-[hsl(var(--card))]">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <History className="w-4 h-4" /> Riwayat impor
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Kolom <b>Masuk</b> = baris baru, <b>Diperbarui</b> = baris lama yang
            diubah. Impor “hanya memperbarui” (Ekspor B &amp; C) selalu 0 di kolom
            Masuk — itu benar, bukan gagal.
          </p>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-xs text-muted-foreground">Belum ada impor yang disimpan.</p>
          ) : (
            <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border">
              <table className="w-full text-xs" data-testid="import-history-table">
                <thead className="bg-muted/60"><tr>
                  <th className="px-3 py-2 text-left">Waktu</th>
                  <th className="px-3 py-2 text-left">Jenis</th>
                  <th className="px-3 py-2 text-left">Toko</th>
                  <th className="px-3 py-2 text-left">Berkas</th>
                  <th className="px-3 py-2 text-right">Masuk</th>
                  <th className="px-3 py-2 text-right">Diperbarui</th>
                  <th className="px-3 py-2 text-left">Oleh</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-right">Tindakan</th>
                </tr></thead>
                <tbody>
                  {history.map((h) => {
                    const ht = typeByKey[h.source_type];
                    const isUpd = !!ht?.update_only;
                    return (
                      <tr key={h.id} className="border-t border-border hover:bg-muted/40">
                        <td className="px-3 py-1.5">{(h.committed_at || h.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                        <td className="px-3 py-1.5">
                          {h.source_label || h.source_type}
                          {isUpd && (
                            <Badge className="ml-1.5 text-[9px] bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                              hanya memperbarui
                            </Badge>
                          )}
                        </td>
                        <td className="px-3 py-1.5">{h.account_name || '—'}</td>
                        <td className="px-3 py-1.5 font-mono text-[11px]">{h.filename}</td>
                        <td className="px-3 py-1.5 text-right font-semibold">
                          {isUpd
                            ? <span className="text-muted-foreground" title="jenis ini tidak membuat baris baru">0</span>
                            : (h.committed_count ?? 0)}
                        </td>
                        <td className="px-3 py-1.5 text-right font-semibold text-blue-600 dark:text-blue-400"
                          data-testid={`history-updated-${h.id}`}>
                          {h.updated_count ?? 0}
                        </td>
                        <td className="px-3 py-1.5">{h.committed_by || h.created_by}</td>
                        <td className="px-3 py-1.5">
                          {h.status === 'committed'
                            ? <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 text-[10px]">tersimpan</Badge>
                            : (
                              <div className="space-y-0.5">
                                <Badge variant="outline" className="text-[10px]">dibatalkan</Badge>
                                {(h.rolled_back_at || '') && (
                                  <p className="text-[10px] text-muted-foreground">
                                    {String(h.rolled_back_at).slice(0, 16).replace('T', ' ')}
                                  </p>
                                )}
                              </div>
                            )}
                        </td>
                        <td className="px-3 py-1.5 text-right whitespace-nowrap">
                          {h.status === 'committed' ? (
                            /* F3.F — LABEL YANG JUJUR. "Batalkan impor" pada Ekspor
                               B/C tidak menghapus baris apa pun; yang terjadi adalah
                               keadaan pesanan dipulihkan. Memakai label yang sama
                               untuk dua akibat berbeda adalah cara tercepat membuat
                               staf menekan tombol yang tidak ia maksud. */
                            <div className="inline-flex items-center gap-1">
                              {/* FASE 4 — laporan hasil impor LAMA tetap bisa
                                  diunduh. Tanpa ini, "kenapa 12 baris tidak
                                  masuk minggu lalu?" tidak punya jawaban selain
                                  ingatan orang. */}
                              <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]"
                                onClick={() => downloadAuthed(
                                  `sessions/${h.id}/result.csv`,
                                  `hasil-impor-${String(h.id).slice(0, 8)}.csv`)}
                                title="Unduh laporan hasil impor ini (termasuk baris ditolak + alasannya)"
                                data-testid={`history-result-csv-${h.id}`}>
                                <Download className="w-3 h-3" />
                              </Button>
                              <Button variant="outline" size="sm" className="h-7 px-2 text-[11px]"
                                onClick={() => askRollback(h.id)}
                                data-testid={`history-rollback-${h.id}`}>
                                <RotateCcw className="w-3 h-3 mr-1" />
                                {isUpd ? 'Batalkan & pulihkan' : 'Batalkan impor'}
                              </Button>
                            </div>
                          ) : (
                            <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px]"
                              onClick={() => openUndoReport(h.id)}
                              data-testid={`history-undo-report-${h.id}`}>
                              <FileSpreadsheet className="w-3 h-3 mr-1" /> Laporan pemulihan
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* F3.F — KONFIRMASI PEMBATALAN yang menyebut angka sebenarnya lebih dulu */}
      <AlertDialog open={!!rollbackTarget}
        onOpenChange={(o) => { if (!o) { setRollbackTarget(null); setUndoInfo(null); } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {undoInfo?.update_only ? 'Batalkan impor & pulihkan pesanan?' : 'Batalkan impor ini?'}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-xs" data-testid="rollback-preview">
                {!undoInfo && <p>Memeriksa apa yang bisa dipulihkan…</p>}
                {undoInfo?.error && (
                  <p className="text-red-600 dark:text-red-400">{undoInfo.error}</p>
                )}
                {undoInfo && !undoInfo.error && (
                  <>
                    {undoInfo.update_only ? (
                      <>
                        <p>
                          Impor <b>{undoInfo.source_label}</b> ini tidak membuat baris
                          baru, jadi tidak ada yang bisa “dihapus”. Yang terjadi:{' '}
                          <b>{undoInfo.undo_pending}</b> pesanan dikembalikan ke keadaan
                          sebelum berkas ini diunggah
                          {undoInfo.undo_restored > 0
                            && ` (${undoInfo.undo_restored} sudah pernah dipulihkan sebelumnya)`}.
                        </p>
                        <p className="text-amber-700 dark:text-amber-300">
                          Pesanan yang berkas ini jadikan <b>batal/retur</b> hanya
                          field susulannya yang dipulihkan — statusnya TIDAK
                          dihidupkan lagi karena reservasi stoknya sudah dilepas.
                          Nomor pesanannya disebut di laporan sesudah ini.
                        </p>
                      </>
                    ) : (
                      <p>
                        Hanya <b>{undoInfo.committed_count}</b> baris yang dibuat oleh
                        sesi impor ini yang dihapus. Data yang Anda input manual dan
                        hasil impor lain tidak tersentuh.
                        {undoInfo.updated_count > 0 && (
                          <> Selain itu <b>{undoInfo.updated_count}</b> baris lama
                          yang diperbarui sesi ini ikut dipulihkan bila jejaknya ada.</>
                        )}
                      </p>
                    )}
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Tidak</AlertDialogCancel>
            <AlertDialogAction onClick={() => rollback(rollbackTarget)}
              data-testid="rollback-confirm">Ya, batalkan</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* F3.F — LAPORAN PEMULIHAN (menetap; bisa dibuka lagi besok dari Riwayat) */}
      <AlertDialog open={!!undoReport} onOpenChange={(o) => !o && setUndoReport(null)}>
        <AlertDialogContent className="max-w-2xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Laporan pemulihan impor</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-xs" data-testid="undo-report">
                {undoReport?.loading && <p>Memuat laporan…</p>}
                {undoReport?.error && (
                  <p className="text-red-600 dark:text-red-400">{undoReport.error}</p>
                )}
                {undoReport && !undoReport.loading && !undoReport.error && (
                  <>
                    <p>
                      <b>{undoReport.source_label}</b> · status{' '}
                      <b>{undoReport.status === 'rolled_back' ? 'dibatalkan' : 'tersimpan'}</b>
                      {undoReport.rolled_back_at && (
                        <> pada {String(undoReport.rolled_back_at).slice(0, 16).replace('T', ' ')}
                          {undoReport.rolled_back_by ? ` oleh ${undoReport.rolled_back_by}` : ''}</>
                      )}
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {[['Diperbarui saat impor', undoReport.updated_count],
                        ['Dipulihkan', undoReport.restored_count],
                        ['Status dipulihkan', undoReport.restore_status_count],
                        ['Hanya field', undoReport.restore_fields_only],
                        ['Sudah tidak ada', undoReport.restore_missing],
                        ['Jejak belum dipakai', undoReport.undo_pending],
                        ['Jejak sudah dipakai', undoReport.undo_restored]].map(([l, v]) => (
                          <div key={l} className="rounded-[var(--radius-sm)] border border-border p-2">
                            <p className="text-[10px] text-muted-foreground">{l}</p>
                            <p className="text-base font-bold text-foreground">{v ?? 0}</p>
                          </div>
                        ))}
                    </div>
                    {undoReport.restore_fields_only > 0 && (
                      <p className="rounded-[var(--radius-sm)] border border-amber-500/40 bg-amber-500/10 p-2
                        text-amber-800 dark:text-amber-200">
                        <b>Perlu tindak lanjut manual.</b>{' '}
                        {undoReport.restore_fields_only} pesanan tidak dihidupkan
                        kembali statusnya (sudah batal/retur ⇒ stok sudah dilepas).
                        Kalau pesanan itu memang harus jalan lagi, buat pesanan
                        penggantinya di menu Pesanan — jangan paksa statusnya.
                      </p>
                    )}
                    {(undoReport.restore_notes || []).length > 0 && (
                      <div className="rounded-[var(--radius-sm)] border border-border max-h-40 overflow-y-auto p-2
                        space-y-1" data-testid="undo-report-notes">
                        {/* Catatan pemulihan adalah PEKERJAAN LANJUTAN untuk manusia
                            (nomor pesanan + apa yang terjadi). Menampilkannya sebagai
                            JSON mentah sama dengan tidak menampilkannya. */}
                        {undoReport.restore_notes.map((n, i) => (
                          typeof n === 'string' ? (
                            <p key={i} className="text-[11px] text-muted-foreground">• {n}</p>
                          ) : (
                            <p key={i} className="text-[11px] text-muted-foreground">
                              • <span className="font-mono text-foreground">{n.order || '—'}</span>
                              {n.result ? <> — <b>{n.result}</b></> : null}
                              {n.why ? `: ${n.why}` : ''}
                              {n.next ? ` · Langkah berikutnya: ${n.next}` : ''}
                            </p>
                          )
                        ))}
                      </div>
                    )}
                    {(undoReport.trail || []).length > 0 && (
                      <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border max-h-48">
                        <table className="w-full text-[11px]">
                          <thead className="bg-muted/60"><tr>
                            <th className="px-2 py-1 text-left">No. Pesanan</th>
                            <th className="px-2 py-1 text-left">Status sebelum diimpor</th>
                            <th className="px-2 py-1 text-left">Sudah dipulihkan?</th>
                          </tr></thead>
                          <tbody>
                            {undoReport.trail.map((t, i) => (
                              <tr key={`${t.order_ref}-${i}`} className="border-t border-border">
                                <td className="px-2 py-1 font-mono">{t.order_ref}</td>
                                <td className="px-2 py-1">{t.status_before || '—'}</td>
                                <td className="px-2 py-1">
                                  {t.restored_at
                                    ? String(t.restored_at).slice(0, 16).replace('T', ' ')
                                    : 'belum'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {!undoReport.update_only && undoReport.undo_pending === 0
                      && undoReport.undo_restored === 0 && (
                      <p className="text-muted-foreground">
                        Sesi ini hanya membuat baris baru — pembatalannya berupa
                        penghapusan baris ({undoReport.committed_count} baris), bukan
                        pemulihan keadaan, jadi tidak ada jejak pemulihan.
                      </p>
                    )}
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setUndoReport(null)}
              data-testid="undo-report-close">Tutup</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* F8 — DAFTAR SUSUNAN KOLOM YANG DIINGAT (bisa dilihat & dilupakan) */}
      <AlertDialog open={formats !== null} onOpenChange={(o) => !o && setFormats(null)}>
        <AlertDialogContent className="max-w-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Susunan kolom yang diingat sistem</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-xs" data-testid="import-formats-dialog">
                <p className="text-muted-foreground">
                  Setiap kali Anda menyimpan impor, susunan kolom berkasnya diingat
                  beserta pemetaan yang Anda konfirmasi — supaya berkas rutin harian
                  langsung siap. Ingatan ini <b>hanya dipakai kalau susunan kolomnya sama
                  persis</b>; berkas dengan kolom berbeda tetap dipetakan ulang dan
                  meminta konfirmasi (tidak ada tebakan diam-diam).
                </p>
                {(formats || []).length === 0 ? (
                  <p className="text-muted-foreground" data-testid="import-formats-empty">
                    Belum ada susunan kolom yang diingat untuk jenis data ini.
                  </p>
                ) : (
                  <div className="overflow-x-auto rounded-[var(--radius-sm)] border border-border max-h-72">
                    <table className="w-full text-[11px]">
                      <thead className="bg-muted/60 sticky top-0"><tr>
                        <th className="px-2 py-1.5 text-left">Jenis data</th>
                        <th className="px-2 py-1.5 text-left">Kolom</th>
                        <th className="px-2 py-1.5 text-right">Dipakai</th>
                        <th className="px-2 py-1.5 text-left">Terakhir dipakai</th>
                        <th className="px-2 py-1.5 text-left">Contoh kolom berkas</th>
                        <th className="px-2 py-1.5" />
                      </tr></thead>
                      <tbody>
                        {(formats || []).map((f) => (
                          <tr key={`${f.source_type}-${f.fingerprint}`} className="border-t border-border">
                            <td className="px-2 py-1.5">{f.source_label}</td>
                            <td className="px-2 py-1.5">{f.mapped_columns}/{f.columns} terpakai</td>
                            <td className="px-2 py-1.5 text-right font-semibold">{f.use_count}×</td>
                            <td className="px-2 py-1.5">
                              {String(f.last_used_at || '').slice(0, 16).replace('T', ' ') || '—'}
                              <span className="block text-muted-foreground">{f.last_used_by}</span>
                            </td>
                            <td className="px-2 py-1.5 text-muted-foreground max-w-[220px] truncate"
                              title={(f.headers_preview || []).join(' · ')}>
                              {(f.headers_preview || []).slice(0, 4).join(' · ')}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              <Button variant="outline" size="sm" className="h-6 text-[10px]"
                                disabled={busy === 'forget'}
                                onClick={() => forgetFormat(f.fingerprint, f.source_type, false)}
                                data-testid={`import-forget-${f.fingerprint}`}>
                                Lupakan
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setFormats(null)}
              data-testid="import-formats-close">Tutup</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
