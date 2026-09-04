/**
 * CMTOverrideWeeklyRecap — **Rekap Mingguan** (tab kedua pintu "Input Vendor CMT").
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * PERTANYAAN YANG DIJAWAB LAYAR INI
 * ═══════════════════════════════════════════════════════════════════════════
 * Tab Harian menjawab "siapa yang belum diisi HARI INI". Itu cukup untuk mengejar
 * pekerjaan hari ini, tapi tidak bisa menjawab pertanyaan yang dibawa ke rapat:
 * **"vendor mana yang BELAKANGAN INI sering bolong?"** Satu hari merah bisa
 * kebetulan (vendor libur, listrik mati). Tujuh hari berturut-turut merah adalah
 * masalah — dan karena tagihan CMT dihitung dari progress produksi, masalah itu
 * berujung ke uang yang tidak bisa ditagih.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * KEPUTUSAN OWNER (2026-08-10)
 * ═══════════════════════════════════════════════════════════════════════════
 *  1  Jendela = **7 hari terakhir BERGULIR** (bukan Senin–Minggu ISO).
 *  2  "Terlambat" ditampilkan sebagai **DUA angka terpisah**, tidak ada yang
 *     dibuang: **Terlambat** = hari yang ada pekerjaan menunggu tapi NOL bukti
 *     (merah, dipakai mengurutkan) · **Belum beres** = hari terlambat + hari yang
 *     sudah diisi tapi masih ada sisa (amber).
 *  3  Kolom: 7 kotak hari · terlambat · belum beres · hari tanpa setoran ·
 *     total pcs disetor/dikirim · tren pcs (sparkline) · streak.
 *  4  **Streak** = rentetan hari beruntun paling akhir; putus pada hari terlambat
 *     ATAU belum beres; hari tanpa pekerjaan bersifat netral.
 *  5  Export Excel + PDF · klik kotak hari → buka tab Harian tanggal itu ·
 *     tombol reminder menegur untuk SATU tanggal yang disebut jelas.
 *  6  **F12 — perbandingan antar-pekan** bersifat OPT-IN (tombol "Bandingkan
 *     pekan lalu"): membandingkan berarti backend membangun DUA jendela, dan
 *     gate `INV-REKAP` RK-27 menjaga layar mingguan tidak lebih mahal daripada
 *     7× rekap harian. Panelnya membawa kartu delta ringkasan, papan **vendor
 *     yang bergerak** (urutannya dari backend), kolom "vs pekan lalu" di tabel,
 *     dan filter "hanya yang memburuk". Vendor yang tidak punya pekerjaan di
 *     salah satu pekan TIDAK diperingkat — tapi alasannya ditulis, bukan
 *     dihilangkan diam-diam.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * SEMUA ANGKA DATANG DARI BACKEND — BROWSER TIDAK MENGHITUNG APA PUN
 * ═══════════════════════════════════════════════════════════════════════════
 * `GET /api/cmt-override/weekly-recap` memanggil `build_recap()` untuk tiap hari
 * (SSOT `backend/core/cmt_daily_recap.py`), jadi angka tab ini secara struktural
 * TIDAK BISA berbeda dari tab Harian. Kalau layar ini ikut menjumlah sendiri,
 * suatu hari kartu ringkasan akan berdebat dengan tabelnya sendiri — dan tidak
 * ada yang tahu mana yang benar.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, BellRing, CalendarDays, CalendarRange, CheckCircle2, ChevronLeft,
  ChevronRight, Download, FileSpreadsheet, FileText, Flame, GitCompareArrows, Info,
  Loader2, MinusCircle, RefreshCw, Search, TrendingDown, TrendingUp, UserCog, X, XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ResponsiveTableWrapper } from '@/components/ui/responsive-table-wrapper';
import { apiGet, apiPost, apiFetch } from '../../../lib/api';
import { dayLabel, isoToday, shiftDay as shiftDayUtil } from './recapDates';

// ── Tampilan satu KOTAK HARI ────────────────────────────────────────────────
// Lima keadaan, bukan dua. `future` sengaja dibedakan dari `idle`: hari yang
// belum terjadi BUKAN "tidak ada pekerjaan", dan menyamakannya membuat pembaca
// menyimpulkan vendor sedang kosong padahal harinya belum datang.
const DAY_STYLE = {
  done: {
    Icon: CheckCircle2,
    cls: 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100',
    label: 'Lengkap',
  },
  partial: {
    Icon: AlertTriangle,
    cls: 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100',
    label: 'Masih ada sisa',
  },
  pending: {
    Icon: XCircle,
    cls: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100',
    label: 'BELUM diisi',
  },
  idle: {
    Icon: MinusCircle,
    cls: 'border-border bg-muted/40 text-muted-foreground hover:bg-muted/70',
    label: 'Tidak ada pekerjaan',
  },
  future: {
    Icon: MinusCircle,
    cls: 'border-dashed border-border bg-background text-muted-foreground',
    label: 'Belum terjadi',
  },
};

const ROW_STATUS = {
  late: { text: 'Pernah terlambat', cls: 'border-red-300 bg-red-100 text-red-800' },
  unfinished: { text: 'Belum beres', cls: 'border-amber-300 bg-amber-100 text-amber-800' },
  clean: { text: 'Rapi sepekan', cls: 'border-emerald-300 bg-emerald-100 text-emerald-800' },
  idle: { text: 'Tidak ada pekerjaan', cls: 'border-border bg-muted text-muted-foreground' },
};

// ═════════════════════════════════════════════════════════════════════════════
function StatCard({ testid, label, value, tone, hint }) {
  const tones = {
    red: 'border-red-300 bg-red-50 text-red-900',
    amber: 'border-amber-300 bg-amber-50 text-amber-900',
    green: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    grey: 'border-border bg-muted/40 text-muted-foreground',
    blue: 'border-blue-300 bg-blue-50 text-blue-900',
  };
  return (
    <div className={`rounded-lg border p-3 ${tones[tone] || tones.grey}`} data-testid={testid}>
      <p className="text-[11px] font-medium leading-tight">{label}</p>
      <p className="mt-0.5 text-2xl font-bold leading-none">{value}</p>
      {hint ? <p className="mt-1 text-[10px] opacity-80">{hint}</p> : null}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
/**
 * Sparkline batang 7 hari — SVG mentah, tanpa pustaka grafik.
 *
 * Alasan: satu baris tabel per vendor bisa berisi puluhan sparkline. Memasang
 * komponen chart penuh (recharts) di setiap baris membuat layar pagi berat tanpa
 * menambah informasi — yang dibutuhkan hanya "hari mana yang tinggi/kosong".
 */
function Sparkline({ values = [], testid, title }) {
  const nums = values.map(v => Number(v) || 0);
  const max = Math.max(1, ...nums);
  const W = 74;
  const H = 24;
  const n = nums.length || 1;
  const bw = W / n;
  const kosong = nums.every(v => v <= 0);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={title || `Tren pcs per hari: ${nums.join(', ')}`}
      title={title} data-testid={testid} data-values={nums.join(',')}>
      <line x1="0" y1={H - 0.5} x2={W} y2={H - 0.5} stroke="#d4d4d8" strokeWidth="1" />
      {nums.map((v, i) => {
        const h = v > 0 ? Math.max(3, (v / max) * (H - 5)) : 1.5;
        return (
          <rect key={i} x={i * bw + 1} y={H - 1 - h} width={Math.max(2.5, bw - 2.5)}
            height={h} rx="1" fill={v > 0 ? '#2563eb' : '#e4e4e7'} />
        );
      })}
      {kosong && (
        <text x={W / 2} y={H / 2 + 3} textAnchor="middle" fontSize="8" fill="#a1a1aa">
          tanpa setoran
        </text>
      )}
    </svg>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
function DayBox({ cell, vendorId, onOpen }) {
  const st = DAY_STYLE[cell?.state] || DAY_STYLE.idle;
  const { Icon } = st;
  const qty = Number(cell?.qty_progress || 0);
  const future = cell?.is_future === true;
  const pendingTasks = (cell?.pending_tasks || []).join(', ');
  const tip = future
    ? `${cell?.date} — hari ini belum terjadi`
    : `${cell?.date} — ${st.label}${pendingTasks ? `: ${pendingTasks}` : ''}`
      + (qty ? ` · ${qty} pcs disetor` : '')
      + '\nKlik untuk membuka Rekap Harian tanggal ini';

  const body = (
    <>
      <span className="flex items-center justify-center gap-1">
        <Icon className="h-3.5 w-3.5 flex-shrink-0" />
        {cell?.is_today ? <span className="text-[9px] font-bold uppercase">kini</span> : null}
      </span>
      <span className="mt-0.5 block text-[10px] font-semibold leading-none">
        {qty > 0 ? `${qty} pcs` : future ? '—' : ''}
      </span>
    </>
  );

  const common = {
    'data-testid': `cmt-week-cell-${vendorId}-${cell?.date}`,
    'data-state': cell?.state || 'idle',
    title: tip,
  };

  if (future) {
    return (
      <div className={`w-full rounded-lg border px-1 py-1.5 text-center ${st.cls}`} {...common}>
        {body}
      </div>
    );
  }
  return (
    <button type="button" onClick={() => onOpen(cell?.date)}
      className={`w-full rounded-lg border px-1 py-1.5 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] ${st.cls}`}
      {...common}>
      {body}
    </button>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
/**
 * Satu angka selisih: `+3` / `-2` / `sama`, warnanya mengikuti KEPUTUSAN backend.
 *
 * `lowerIsBetter` dikirim eksplisit dan tidak ditebak dari nama field: aturan
 * "naik = buruk" untuk hari terlambat sudah diputuskan
 * `core/cmt_daily_recap.py`, dan menuliskannya ulang di sini akan membuat suatu
 * hari layar memberi warna hijau untuk angka yang di export disebut memburuk.
 */
function DeltaNum({ diff, lowerIsBetter, unit = '', testid }) {
  const n = Number(diff) || 0;
  const flat = n === 0;
  const better = lowerIsBetter ? n < 0 : n > 0;
  const Arrow = flat ? MinusCircle : (n > 0 ? TrendingUp : TrendingDown);
  const cls = flat
    ? 'text-muted-foreground'
    : better ? 'text-emerald-700' : 'text-red-700';
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-bold ${cls}`}
      data-testid={testid} data-diff={n}>
      <Arrow className="h-3 w-3" />
      {flat ? 'sama' : `${n > 0 ? '+' : ''}${n}${unit}`}
    </span>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
/**
 * Satu baris papan "vendor yang bergerak".
 *
 * Menyebut PERPINDAHAN STATUS ("rapi → terlambat") dan bukan cuma "+2", karena
 * kalimat itulah yang bisa langsung ditindaklanjuti di rapat. Barisnya bisa
 * diklik untuk membuka vendor tersebut — daftar yang tidak bisa ditindak hanya
 * jadi hiasan.
 */
function MoverRow({ v, tone, onOpen }) {
  const border = tone === 'worse' ? 'border-red-200 bg-white' : 'border-emerald-200 bg-white';
  const statusFrom = ROW_STATUS[v.status_prev]?.text || '—';
  const statusTo = ROW_STATUS[v.status_now]?.text || '—';
  return (
    <button type="button" onClick={() => onOpen(v)}
      className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] ${border}`}
      title={`Buka ${v.vendor_name}`}
      data-testid={`cmt-week-mover-${v.vendor_id}`} data-direction={v.direction}>
      <p className="flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-bold text-foreground">{v.vendor_name}</span>
        <DeltaNum diff={v.days_late_diff} lowerIsBetter unit=" hari"
          testid={`cmt-week-mover-late-${v.vendor_id}`} />
      </p>
      <p className="mt-0.5 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <span className="truncate">{statusFrom} → <b className="text-foreground">{statusTo}</b></span>
        <DeltaNum diff={v.qty_diff} unit=" pcs"
          testid={`cmt-week-mover-qty-${v.vendor_id}`} />
      </p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        terlambat {v.days_late_prev} → <b className="text-foreground">{v.days_late_now}</b> hari
        {' · '}pcs {v.qty_prev} → <b className="text-foreground">{v.qty_now}</b>
      </p>
    </button>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
export default function CMTOverrideWeeklyRecap({
  endDay, onEndDayChange, onOpenDay, onOpenVendor, canFill = true,
}) {
  const [dayLocal, setDayLocal] = useState(isoToday);
  const controlled = typeof endDay === 'string' && !!endDay;
  const end = controlled ? endDay : dayLocal;

  const setEnd = useCallback((next) => {
    const val = typeof next === 'function' ? next(end) : next;
    if (typeof onEndDayChange === 'function') onEndDayChange(val);
    if (!controlled) setDayLocal(val);
  }, [controlled, end, onEndDayChange]);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [onlyProblem, setOnlyProblem] = useState(false);
  const [onlyWorse, setOnlyWorse] = useState(false);
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmRemind, setConfirmRemind] = useState(false);
  // F12 — panel perbandingan antar-pekan. SENGAJA opt-in (tidak menyala sendiri):
  // membandingkan berarti backend membangun DUA jendela, dan gate INV-REKAP RK-27
  // menjaga layar mingguan tidak lebih mahal daripada 7× rekap harian. Jadi
  // biayanya hanya dibayar ketika seseorang benar-benar ingin melihatnya.
  const [compare, setCompare] = useState(false);

  const load = useCallback(async (e, withCompare) => {
    setLoading(true); setErr('');
    try {
      const res = await apiGet(
        `/cmt-override/weekly-recap?date=${e}${withCompare ? '&compare=true' : ''}`);
      setData(res);
    } catch (ex) {
      setErr(ex.message || 'Gagal memuat rekap mingguan');
      setData(null);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(end, compare); }, [end, compare, load]);

  const days = useMemo(() => data?.days || [], [data]);
  const perDay = useMemo(() => data?.per_day || [], [data]);
  const rows = useMemo(() => data?.rows || [], [data]);
  const summary = data?.summary || {};
  const comparison = data?.comparison || null;
  const remindPending = useMemo(() => data?.remind_pending || [], [data]);
  const isCurrent = data?.is_current === true;

  // Peta ringkasan per hari untuk badge di kepala kolom (angka backend, bukan
  // hitungan browser) — supaya kelihatan HARI MANA yang paling banyak bolong.
  const perDayMap = useMemo(() => {
    const m = {};
    perDay.forEach(p => { m[p.date] = p; });
    return m;
  }, [perDay]);

  // Peta perbandingan per vendor — dipakai kolom "vs pekan lalu" di tabel.
  // Isinya HANYA angka dari backend; layar tidak menghitung selisih sendiri,
  // supaya kolom tabel dan papan "vendor yang bergerak" mustahil berbeda.
  const cmpByVendor = useMemo(() => {
    const m = {};
    (comparison?.per_vendor || []).forEach(v => { m[v.vendor_id] = v; });
    return m;
  }, [comparison]);

  const movers = comparison?.movers || null;

  // Kolom "vs pekan lalu" hanya ada kalau datanya benar-benar ada. Menampilkan
  // kolom kosong lebih buruk daripada tidak menampilkannya: kolom yang selalu
  // "—" mengajari pembaca untuk mengabaikannya.
  const showCompareCol = compare && !!comparison && (comparison.per_vendor || []).length > 0;

  // Filter "hanya yang memburuk" hanya masuk akal saat perbandingan menyala.
  // Kalau panelnya ditutup, filternya ikut dilepas — kalau tidak, tabel akan
  // tampak kosong tanpa sebab yang terlihat di layar.
  useEffect(() => { if (!compare) setOnlyWorse(false); }, [compare]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(r => {
      if (onlyProblem && r.status !== 'late' && r.status !== 'unfinished') return false;
      if (onlyWorse && (cmpByVendor[r.vendor_id]?.direction !== 'worse')) return false;
      if (!q) return true;
      return `${r.vendor_name} ${r.vendor_code} ${r.contact_name}`.toLowerCase().includes(q);
    });
  }, [rows, onlyProblem, onlyWorse, cmpByVendor, search]);

  const download = async (fmt) => {
    setBusy(fmt);
    try {
      // Lampirannya mengikuti apa yang SEDANG DILIHAT: kalau panel perbandingan
      // terbuka, Excel/PDF ikut membawa bagian perbandingan. Legenda di bawah
      // layar menjanjikan "isinya sama dengan layar ini", dan yang dibawa ke
      // rapat justru lampirannya.
      const res = await apiFetch(
        `/cmt-override/weekly-recap/export?format=${fmt}&date=${end}`
        + (compare ? '&compare=true' : ''));
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const cd = res.headers.get('Content-Disposition') || '';
      const guess = (cd.match(/filename="?([^";]+)"?/) || [])[1];
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = guess || `rekap-mingguan-cmt-${end}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Rekap mingguan ${fmt.toUpperCase()} diunduh (${data?.start} … ${data?.end}).`);
    } catch (e) {
      toast.error(e.message || 'Gagal mengunduh rekap mingguan');
    } finally { setBusy(''); }
  };

  // Reminder memakai endpoint HARIAN dengan tanggal yang DISEBUT JELAS: reminder
  // tersimpan per vendor per tanggal (idempoten), jadi "tegur untuk 7 hari" tidak
  // punya tanggal yang bisa dipertanggungjawabkan.
  const sendReminders = async () => {
    const tgl = data?.remind_date;
    if (!tgl) return;
    setBusy('remind');
    try {
      const res = await apiPost('/cmt-override/daily-recap/remind', { date: tgl });
      const sent = res?.sent_count || 0;
      const skipped = res?.skipped_count || 0;
      if (sent > 0) {
        toast.success(
          `Reminder terkirim ke ${sent} vendor untuk tanggal ${tgl}.`
          + (skipped ? ` ${skipped} dilewati (sudah ditegur untuk tanggal ini).` : ''),
        );
      } else if (skipped > 0) {
        toast.info(`Tidak ada yang dikirim — ${skipped} vendor sudah ditegur untuk ${tgl}.`);
      } else {
        toast.info('Tidak ada vendor yang perlu ditegur.');
      }
      setConfirmRemind(false);
      // `compare` WAJIB diteruskan. Tanpa ini, memuat ulang setelah mengirim
      // reminder menjawab TANPA blok perbandingan, sehingga panel yang sedang
      // dibuka hilang sendiri tepat setelah staf menekan tombol — kelihatan
      // seperti fiturnya rusak, padahal cuma parameternya jatuh.
      load(end, compare);
    } catch (e) {
      toast.error(e.message || 'Gagal mengirim reminder');
    } finally { setBusy(''); }
  };

  const openDay = (iso) => {
    if (!iso) return;
    if (typeof onOpenDay === 'function') onOpenDay(iso);
    else setEnd(iso);
  };

  const openVendor = (row) => {
    if (typeof onOpenVendor === 'function') onOpenVendor(row, null);
  };

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm" data-testid="cmt-week-panel">
      {/* ── Kepala ───────────────────────────────────────────────────────── */}
      <div className="border-b border-border p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-indigo-600">
              <CalendarRange className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">Rekap Mingguan</h2>
              <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
                Vendor mana yang <b>sering bolong</b> dalam 7 hari terakhir — satu kotak
                per hari. Klik kotak hari untuk membuka <b>Rekap Harian</b> tanggal itu.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-1">
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0"
                onClick={() => setEnd(d => shiftDayUtil(d, -7))}
                title="7 hari sebelumnya" data-testid="cmt-week-prev">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="date"
                  value={end}
                  max={shiftDayUtil(isoToday(), 1)}
                  onChange={e => e.target.value && setEnd(e.target.value)}
                  className="h-8 rounded-md border border-border bg-background pl-7 pr-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))]"
                  title="Hari TERAKHIR jendela 7 hari"
                  data-testid="cmt-week-date-input"
                />
              </div>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0"
                onClick={() => setEnd(d => shiftDayUtil(d, 7))}
                title="7 hari berikutnya" data-testid="cmt-week-next">
                <ChevronRight className="h-4 w-4" />
              </Button>
              {!isCurrent && (
                <Button variant="ghost" size="sm"
                  className="h-8 px-2 text-xs font-semibold text-blue-700"
                  onClick={() => setEnd(isoToday())} data-testid="cmt-week-today">
                  7 hari terakhir
                </Button>
              )}
            </div>

            <Button variant="outline" size="sm" onClick={() => load(end, compare)} data-testid="cmt-week-refresh">
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Muat ulang
            </Button>
            <Button variant={compare ? 'default' : 'outline'} size="sm"
              onClick={() => setCompare(v => !v)} data-testid="cmt-week-compare-toggle"
              title="Bandingkan jendela ini dengan 7 hari sebelumnya">
              <GitCompareArrows className="mr-1.5 h-3.5 w-3.5" />
              {compare ? 'Sembunyikan perbandingan' : 'Bandingkan pekan lalu'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('xlsx')}
              disabled={busy === 'xlsx'} data-testid="cmt-week-export-xlsx">
              {busy === 'xlsx'
                ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                : <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" />}
              Excel
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('pdf')}
              disabled={busy === 'pdf'} data-testid="cmt-week-export-pdf">
              {busy === 'pdf'
                ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                : <FileText className="mr-1.5 h-3.5 w-3.5" />}
              PDF
            </Button>
          </div>
        </div>

        <p className="mt-3 text-xs font-medium text-foreground" data-testid="cmt-week-range-label">
          {data ? `${dayLabel(data.start)} — ${dayLabel(data.end)}` : '…'}
          {isCurrent
            ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-700">7 HARI TERAKHIR</span>
            : <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">JENDELA LAIN</span>}
          {summary.days_elapsed < summary.days && (
            <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
              {summary.days - summary.days_elapsed} hari belum terjadi
            </span>
          )}
        </p>

        {/* ── Kartu ringkasan ─────────────────────────────────────────────── */}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard testid="cmt-week-summary-late" tone="red" label="Pernah terlambat"
            value={summary.vendors_late ?? 0} hint="ada hari nol bukti" />
          <StatCard testid="cmt-week-summary-unfinished" tone="amber" label="Belum beres"
            value={summary.vendors_unfinished ?? 0} hint="terisi, masih ada sisa" />
          <StatCard testid="cmt-week-summary-clean" tone="green" label="Rapi sepekan"
            value={summary.vendors_clean ?? 0} hint="tanpa hari bolong" />
          <StatCard testid="cmt-week-summary-idle" tone="grey" label="Tanpa pekerjaan"
            value={summary.vendors_idle ?? 0} hint="tidak perlu diisi" />
          <StatCard testid="cmt-week-summary-days-late" tone="blue" label="Total hari terlambat"
            value={summary.days_late_total ?? 0}
            hint={`${summary.days_no_progress_total ?? 0} hari tanpa setoran`} />
          <StatCard testid="cmt-week-summary-qty" tone="blue" label="Pcs disetor sepekan"
            value={summary.qty_progress_total ?? 0}
            hint={`${summary.qty_shipped_total ?? 0} pcs dikirim`} />
        </div>

        {/* ── F12 — PERBANDINGAN DENGAN PEKAN SEBELUMNYA ───────────────────────
            Kenapa ada: "5 hari terlambat" tidak berarti apa-apa sendirian.
            Yang dibawa ke rapat adalah arahnya — membaik atau memburuk. Angkanya
            datang dari backend (`build_week()` dipanggil dua kali dengan ctx yang
            sama), jadi tidak mungkin berbeda dari kotak hariannya.
            Kejujuran: kalau pekan berjalan belum lengkap, banner mengatakannya dan
            kolom "per hari" dipakai supaya perbandingannya adil. */}
        {compare && comparison && (
          <div className="mt-3 rounded-lg border border-blue-300 bg-blue-50/70 p-3"
            data-testid="cmt-week-comparison">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-semibold text-blue-900">
                Dibandingkan pekan sebelumnya
                <span className="ml-1 font-normal opacity-80">
                  ({dayLabel(comparison.previous?.start)} — {dayLabel(comparison.previous?.end)})
                </span>
              </p>
              {!comparison.comparable && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800"
                  data-testid="cmt-week-comparison-not-comparable">
                  belum sebanding
                </span>
              )}
            </div>
            <p className="mt-1 text-[10px] leading-snug text-blue-900/80"
              data-testid="cmt-week-comparison-note">{comparison.note}</p>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {[
                ['qty_progress_total', 'Pcs disetor'],
                ['qty_shipped_total', 'Pcs dikirim'],
                ['days_late_total', 'Hari terlambat'],
                ['days_unfinished_total', 'Hari belum beres'],
                ['vendors_late', 'Vendor terlambat'],
              ].map(([key, label]) => {
                const d = comparison.delta?.[key];
                if (!d) return null;
                const flat = Math.abs(d.diff) < 0.005;
                const tone = flat
                  ? 'border-border bg-card text-muted-foreground'
                  : (d.better
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                    : 'border-red-300 bg-red-50 text-red-900');
                const Arrow = flat ? MinusCircle : (d.diff > 0 ? TrendingUp : TrendingDown);
                return (
                  <div key={key} className={`rounded-md border p-2 ${tone}`}
                    data-testid={`cmt-week-delta-${key}`}>
                    <p className="text-[10px] font-medium leading-tight">{label}</p>
                    <p className="mt-0.5 flex items-baseline gap-1 text-lg font-bold leading-none">
                      {d.now}
                      <span className="inline-flex items-center gap-0.5 text-[11px] font-semibold">
                        <Arrow className="h-3 w-3" />
                        {flat ? 'sama' : `${d.diff > 0 ? '+' : ''}${d.diff}`}
                      </span>
                    </p>
                    <p className="mt-1 text-[10px] opacity-80">
                      pekan lalu {d.prev}
                      {!comparison.comparable && (
                        <> · per hari {d.now_per_day} vs {d.prev_per_day}</>
                      )}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* ── Papan "VENDOR YANG BERGERAK" ───────────────────────────────
                Kenapa ada: kartu delta di atas menjawab "arahnya ke mana",
                dan pertanyaan berikutnya di rapat SELALU "vendor mana".
                Urutannya datang dari backend (`movers`), bukan diurutkan di
                browser — supaya Excel/PDF yang dibawa ke rapat menunjuk vendor
                terburuk yang SAMA. */}
            {movers && (
              <div className="mt-3 border-t border-blue-200 pt-2.5" data-testid="cmt-week-movers">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] font-semibold text-blue-900">Vendor yang bergerak</p>
                  <p className="text-[10px] text-blue-900/80" data-testid="cmt-week-movers-counts">
                    memburuk <b>{movers.counts?.worsened ?? 0}</b>
                    {' · '}membaik <b>{movers.counts?.improved ?? 0}</b>
                    {' · '}sama <b>{movers.counts?.flat ?? 0}</b>
                    {' · '}tidak diperingkat <b>{movers.counts?.incomparable ?? 0}</b>
                    {' dari '}{movers.counts?.vendors ?? 0} vendor
                  </p>
                </div>
                <div className="mt-2 grid gap-2 lg:grid-cols-2">
                  <div data-testid="cmt-week-movers-worsened">
                    <p className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-red-700">
                      <TrendingDown className="h-3 w-3" /> Paling memburuk
                    </p>
                    {(movers.worsened || []).length === 0 ? (
                      <p className="rounded-md border border-dashed border-border bg-card px-2 py-2 text-[10px] text-muted-foreground">
                        Tidak ada vendor yang memburuk dibanding pekan lalu.
                      </p>
                    ) : (
                      <div className="space-y-1.5">
                        {movers.worsened.map(v => (
                          <MoverRow key={v.vendor_id} v={v} tone="worse" onOpen={openVendor} />
                        ))}
                      </div>
                    )}
                  </div>
                  <div data-testid="cmt-week-movers-improved">
                    <p className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-emerald-700">
                      <TrendingUp className="h-3 w-3" /> Paling membaik
                    </p>
                    {(movers.improved || []).length === 0 ? (
                      <p className="rounded-md border border-dashed border-border bg-card px-2 py-2 text-[10px] text-muted-foreground">
                        Belum ada vendor yang membaik dibanding pekan lalu.
                      </p>
                    ) : (
                      <div className="space-y-1.5">
                        {movers.improved.map(v => (
                          <MoverRow key={v.vendor_id} v={v} tone="better" onOpen={openVendor} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <p className="mt-2 text-[10px] leading-snug text-blue-900/70"
                  data-testid="cmt-week-movers-rule">
                  {movers.rule}
                </p>
                {(movers.counts?.incomparable ?? 0) > 0 && (
                  <p className="mt-1 text-[10px] leading-snug text-amber-800"
                    data-testid="cmt-week-movers-excluded">
                    {movers.counts.incomparable} vendor tidak diperingkat karena tidak punya
                    pekerjaan di salah satu pekan
                    {(movers.counts?.new ?? 0) > 0
                      ? ` (termasuk ${movers.counts.new} vendor baru)`
                      : ''}
                    {' '}— mereka tetap tampil di tabel di bawah, lengkap dengan alasannya.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Bar aksi ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-4 py-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari vendor di rekap mingguan…" className="h-9 pl-9"
            data-testid="cmt-week-search" />
        </div>
        <label className="flex cursor-pointer select-none items-center gap-2 text-xs font-medium text-foreground">
          <input type="checkbox" checked={onlyProblem}
            onChange={e => setOnlyProblem(e.target.checked)}
            className="h-4 w-4 rounded border-border"
            data-testid="cmt-week-filter-problem" />
          Hanya yang bermasalah
        </label>
        {/* Filter ini hanya muncul saat perbandingan menyala: tanpa data pekan
            lalu, "memburuk" tidak punya arti dan kotaknya cuma akan mengosongkan
            tabel tanpa alasan yang terlihat. */}
        {compare && comparison && (
          <label className="flex cursor-pointer select-none items-center gap-2 rounded-md border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-900">
            <input type="checkbox" checked={onlyWorse}
              onChange={e => setOnlyWorse(e.target.checked)}
              className="h-4 w-4 rounded border-red-300"
              data-testid="cmt-week-filter-worse" />
            Hanya yang memburuk ({movers?.counts?.worsened ?? 0})
          </label>
        )}
        <Button size="sm" onClick={() => setConfirmRemind(true)}
          disabled={remindPending.length === 0 || busy === 'remind'}
          className="bg-amber-600 text-white hover:bg-amber-700"
          title={data?.remind_date
            ? `Menegur untuk tanggal ${data.remind_date} (hari terakhir yang sudah berjalan)`
            : 'Belum ada tanggal yang bisa ditegur'}
          data-testid="cmt-week-remind">
          <BellRing className="mr-1.5 h-3.5 w-3.5" />
          Kirim reminder ({remindPending.length})
        </Button>
      </div>

      {/* ── Konfirmasi reminder: tanggalnya WAJIB disebut ─────────────────── */}
      {confirmRemind && (
        <div className="border-b border-amber-300 bg-amber-50 p-4" data-testid="cmt-week-remind-confirm">
          <div className="flex items-start gap-3">
            <BellRing className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-amber-900">
                Kirim reminder ke {remindPending.length} vendor untuk tanggal{' '}
                <span data-testid="cmt-week-remind-date">{data?.remind_date}</span>?
              </p>
              <p className="mt-1 text-xs text-amber-800">
                Reminder selalu menempel pada <b>satu tanggal</b> (hari terakhir yang sudah
                berjalan di jendela ini), bukan pada rentang 7 hari — supaya vendor tahu
                data hari mana yang diminta. Satu vendor hanya menerima satu reminder rekap
                per tanggal: klik dua kali tidak menggandakan.
              </p>
              <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-amber-900">
                {remindPending.map(r => (
                  <li key={r.vendor_id}>
                    • <b>{r.vendor_name}</b>
                    <span className="opacity-80"> — {(r.pending_tasks || []).join(', ')}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={sendReminders} disabled={busy === 'remind'}
                  className="bg-amber-600 text-white hover:bg-amber-700"
                  data-testid="cmt-week-remind-confirm-yes">
                  {busy === 'remind' && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  Ya, kirim sekarang
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirmRemind(false)}
                  data-testid="cmt-week-remind-confirm-no">
                  Batal
                </Button>
              </div>
            </div>
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
              onClick={() => setConfirmRemind(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* ── Job WARISAN tanpa stempel waktu tutup (fase 5 `closed_at`) ───── */}
      {/* Angka & kalimatnya DIAMBIL dari rekap harian (tab ini tidak menghitung
          apa pun sendiri). Tampil di sini juga karena jendela 7 hari justru yang
          paling terpengaruh: satu job warisan bisa membuat beberapa kotak hari
          tampak lebih bersih daripada kenyataannya. */}
      {data?.legacy_jobs_without_closed_at > 0 && data?.legacy_note && (
        <div className="flex items-start gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2.5"
          data-testid="cmt-week-legacy-jobs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
          <p className="text-[11px] leading-snug text-amber-900">
            <span className="font-semibold">Sebagian kotak hari belum bisa dihitung penuh — </span>
            {data.legacy_note}
          </p>
        </div>
      )}

      {/* ── Catatan rentang & aturan ─────────────────────────────────────── */}
      {data?.as_of_note && (
        <div className="flex items-start gap-2 border-b border-border bg-muted/40 px-4 py-2.5"
          data-testid="cmt-week-as-of-note">
          <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-blue-600" />
          <p className="text-[11px] leading-snug text-muted-foreground">{data.as_of_note}</p>
        </div>
      )}

      {/* ── Tabel ────────────────────────────────────────────────────────── */}
      {err ? (
        <div className="p-4">
          <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800"
            data-testid="cmt-week-error">{err}</div>
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-16" data-testid="cmt-week-loading">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : visible.length === 0 ? (
        <div className="py-14 text-center" data-testid="cmt-week-empty">
          <CheckCircle2 className="mx-auto mb-2 h-9 w-9 text-emerald-500" />
          <p className="font-medium text-foreground">
            {rows.length === 0
              ? 'Belum ada vendor CMT aktif di master'
              : onlyWorse
                ? 'Tidak ada vendor yang memburuk dibanding pekan lalu'
                : onlyProblem
                  ? 'Tidak ada vendor bermasalah dalam 7 hari ini — semua rapi'
                  : 'Tidak ada vendor yang cocok dengan pencarian'}
          </p>
          {(onlyWorse || onlyProblem) && rows.length > 0 && (
            <Button variant="outline" size="sm" className="mt-3"
              onClick={() => { setOnlyWorse(false); setOnlyProblem(false); }}
              data-testid="cmt-week-clear-filters">
              <X className="mr-1.5 h-3.5 w-3.5" /> Tampilkan semua vendor
            </Button>
          )}
        </div>
      ) : (
        <ResponsiveTableWrapper stickyFirstCol>
          <table className={`w-full text-sm ${showCompareCol ? 'min-w-[1500px]' : 'min-w-[1320px]'}`}>
            <thead className="bg-muted/60">
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2.5">Vendor</th>
                {days.map(d => {
                  const pd = perDayMap[d.date] || {};
                  const npend = Number(pd.vendors_pending || 0);
                  return (
                    <th key={d.date} className="px-1 py-2 text-center font-semibold">
                      <button type="button" onClick={() => openDay(d.date)}
                        disabled={d.is_future}
                        className={`w-full rounded-md px-1 py-0.5 leading-tight ${
                          d.is_future ? 'cursor-default opacity-60' : 'hover:bg-muted'
                        }`}
                        title={d.is_future
                          ? `${d.date} — belum terjadi`
                          : `${d.date} — buka Rekap Harian tanggal ini`}
                        data-testid={`cmt-week-dayhead-${d.date}`}>
                        <span className={`block text-[11px] ${d.is_today ? 'text-blue-700' : ''}`}>
                          {d.short}
                        </span>
                        <span className="block text-[11px] font-bold text-foreground">
                          {d.day_num}
                        </span>
                        {d.is_future ? (
                          <span className="mt-0.5 block text-[9px] font-normal normal-case">—</span>
                        ) : (
                          <span className={`mt-0.5 block rounded-full px-1 text-[9px] font-bold normal-case ${
                            npend > 0 ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
                          }`} data-testid={`cmt-week-daycount-${d.date}`}>
                            {npend > 0 ? `${npend} belum` : 'aman'}
                          </span>
                        )}
                      </button>
                    </th>
                  );
                })}
                <th className="px-2 py-2.5 text-center">Terlambat</th>
                <th className="px-2 py-2.5 text-center">Belum beres</th>
                <th className="px-2 py-2.5 text-center">Tanpa setoran</th>
                <th className="px-2 py-2.5 text-center">Pcs setor / kirim</th>
                {showCompareCol && (
                  <th className="px-2 py-2.5 text-center" data-testid="cmt-week-th-vs-prev">
                    vs pekan lalu
                  </th>
                )}
                <th className="px-2 py-2.5 text-center">Tren pcs</th>
                <th className="px-2 py-2.5 text-center">Streak</th>
                <th className="px-3 py-2.5 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visible.map(r => {
                const stat = ROW_STATUS[r.status] || ROW_STATUS.idle;
                return (
                  <tr key={r.vendor_id} className="align-middle hover:bg-muted/30"
                    data-testid={`cmt-week-row-${r.vendor_id}`} data-status={r.status}>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-foreground">{r.vendor_name}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {r.vendor_code || '—'}
                      </p>
                      <span className={`mt-1.5 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${stat.cls}`}
                        data-testid={`cmt-week-status-${r.vendor_id}`}>
                        {stat.text}
                      </span>
                      {r.has_active_portal_account && (
                        <span className="mt-1 flex items-center gap-1 text-[10px] text-amber-700"
                          title="Vendor ini punya akun portal aktif — hati-hati dobel input">
                          <AlertTriangle className="h-3 w-3" /> punya akun portal
                        </span>
                      )}
                    </td>

                    {(r.cells || []).map(c => (
                      <td key={c.date} className="px-1 py-3">
                        <DayBox cell={c} vendorId={r.vendor_id} onOpen={openDay} />
                      </td>
                    ))}

                    <td className="px-2 py-3 text-center" data-testid={`cmt-week-late-${r.vendor_id}`}>
                      <span className={`inline-flex min-w-[2rem] justify-center rounded-md px-2 py-1 text-sm font-bold ${
                        r.days_late > 0 ? 'bg-red-100 text-red-800' : 'text-muted-foreground'
                      }`}>
                        {r.days_late}
                      </span>
                      <span className="mt-0.5 block text-[9px] text-muted-foreground">hari</span>
                    </td>
                    <td className="px-2 py-3 text-center" data-testid={`cmt-week-unfinished-${r.vendor_id}`}>
                      <span className={`inline-flex min-w-[2rem] justify-center rounded-md px-2 py-1 text-sm font-bold ${
                        r.days_unfinished > 0 ? 'bg-amber-100 text-amber-800' : 'text-muted-foreground'
                      }`}>
                        {r.days_unfinished}
                      </span>
                      <span className="mt-0.5 block text-[9px] text-muted-foreground">hari</span>
                    </td>
                    <td className="px-2 py-3 text-center" data-testid={`cmt-week-nosetor-${r.vendor_id}`}>
                      <span className={`text-sm font-bold ${
                        r.days_no_progress > 0 ? 'text-foreground' : 'text-muted-foreground'
                      }`}>
                        {r.days_no_progress}
                      </span>
                      <span className="mt-0.5 block text-[9px] text-muted-foreground">
                        dari {r.days_with_work} hari kerja
                      </span>
                    </td>
                    <td className="px-2 py-3 text-center" data-testid={`cmt-week-qty-${r.vendor_id}`}>
                      <p className="text-sm font-bold text-foreground">{r.qty_progress_total}</p>
                      <p className="text-[10px] text-muted-foreground">
                        kirim {r.qty_shipped_total}
                      </p>
                    </td>
                    {showCompareCol && (() => {
                      const cv = cmpByVendor[r.vendor_id];
                      if (!cv) {
                        return (
                          <td className="px-2 py-3 text-center text-[10px] text-muted-foreground"
                            data-testid={`cmt-week-vs-${r.vendor_id}`} data-direction="unknown">—</td>
                        );
                      }
                      // Vendor yang tidak bisa dibandingkan TIDAK dikosongkan
                      // begitu saja: alasannya ditulis, supaya tidak terbaca
                      // sebagai "tidak ada perubahan".
                      if (cv.direction === 'incomparable') {
                        return (
                          <td className="px-2 py-3 text-center"
                            data-testid={`cmt-week-vs-${r.vendor_id}`} data-direction="incomparable"
                            title={cv.incomparable_reason}>
                            <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                              tak sebanding
                            </span>
                            <p className="mt-1 max-w-[9rem] text-[9px] leading-tight text-muted-foreground">
                              {cv.incomparable_reason}
                            </p>
                          </td>
                        );
                      }
                      return (
                        <td className="px-2 py-3 text-center"
                          data-testid={`cmt-week-vs-${r.vendor_id}`} data-direction={cv.direction}>
                          <p className="flex justify-center">
                            <DeltaNum diff={cv.days_late_diff} lowerIsBetter unit=" hari"
                              testid={`cmt-week-vs-late-${r.vendor_id}`} />
                          </p>
                          <p className="mt-0.5 flex justify-center">
                            <DeltaNum diff={cv.qty_diff} unit=" pcs"
                              testid={`cmt-week-vs-qty-${r.vendor_id}`} />
                          </p>
                          <p className="mt-0.5 text-[9px] text-muted-foreground">
                            lalu: {cv.days_late_prev} hari · {cv.qty_prev} pcs
                          </p>
                        </td>
                      );
                    })()}
                    <td className="px-2 py-3">
                      <div className="flex justify-center">
                        <Sparkline values={r.trend} testid={`cmt-week-spark-${r.vendor_id}`}
                          title={`Pcs disetor per hari: ${(r.trend || []).join(', ')}`} />
                      </div>
                    </td>
                    <td className="px-2 py-3 text-center" data-testid={`cmt-week-streak-${r.vendor_id}`}>
                      <span className="inline-flex items-center gap-1 text-sm font-bold text-foreground">
                        {r.streak > 0 && <Flame className="h-3.5 w-3.5 text-orange-500" />}
                        {r.streak}
                      </span>
                      <span className="mt-0.5 block text-[9px] text-muted-foreground">
                        {r.streak_broken_by === 'pending'
                          ? 'putus: hari terlambat'
                          : r.streak_broken_by === 'partial'
                            ? 'putus: masih ada sisa'
                            : r.streak > 0 ? 'hari beruntun' : 'belum ada'}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button size="sm" variant="outline" className="whitespace-nowrap"
                        onClick={() => openVendor(r)} disabled={!canFill}
                        data-testid={`cmt-week-fill-${r.vendor_id}`}>
                        <UserCog className="mr-1.5 h-3.5 w-3.5" /> Isi
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ResponsiveTableWrapper>
      )}

      {/* ── Legenda + aturan ────────────────────────────────────────────── */}
      <div className="space-y-2 border-t border-border px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span className="font-semibold text-foreground">Keterangan:</span>
          <span className="inline-flex items-center gap-1"><XCircle className="h-3.5 w-3.5 text-red-600" /> terlambat (ada pekerjaan, nol bukti)</span>
          <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-600" /> terisi, masih ada sisa</span>
          <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> lengkap</span>
          <span className="inline-flex items-center gap-1"><MinusCircle className="h-3.5 w-3.5" /> tidak ada pekerjaan</span>
          <span className="inline-flex items-center gap-1"><TrendingUp className="h-3 w-3" /> batang = pcs disetor hari itu</span>
          {compare && (
            <span className="inline-flex items-center gap-1" data-testid="cmt-week-legend-compare">
              <GitCompareArrows className="h-3 w-3" /> hijau = membaik · merah = memburuk
              (dibanding pekan sebelumnya)
            </span>
          )}
          <span className="ml-auto inline-flex items-center gap-1"><Download className="h-3 w-3" />
            Excel/PDF isinya sama dengan layar ini{compare ? ' (termasuk perbandingan)' : ''}
          </span>
        </div>
        {data?.rules_note && (
          <p className="text-[11px] leading-snug text-muted-foreground" data-testid="cmt-week-rules-note">
            {data.rules_note}
          </p>
        )}
      </div>
    </div>
  );
}
