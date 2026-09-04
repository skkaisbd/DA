/**
 * CMTOverrideDailyRecap — **Rekap Harian** di dalam pintu "Input Vendor CMT".
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * MASALAH NYATA
 * ═══════════════════════════════════════════════════════════════════════════
 * Staf DA sudah bisa mengisi portal vendor CMT atas nama vendor, tapi tidak ada
 * yang memberitahu **vendor mana yang belum dikerjakan hari ini**. Dengan puluhan
 * vendor, satu yang terlewat = progress hari itu tidak masuk, dan karena
 * **tagihan CMT dihitung dari progress produksi**, uangnya tidak bisa ditagih.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * KEPUTUSAN OWNER (2026-08-08)
 * ═══════════════════════════════════════════════════════════════════════════
 *  1c  Bentuknya **checklist per tugas** (bukan lampu hijau/merah tunggal) —
 *      satu baris per vendor, kolom per jenis pekerjaan, supaya kelihatan
 *      KURANG APA, bukan cuma "belum beres".
 *  2a  Isinya **SEMUA vendor aktif**; yang tidak punya pekerjaan tetap tampil
 *      dengan status "tidak ada pekerjaan" (jangan menghilangkan nama tanpa
 *      penjelasan — staf akan curiga daftarnya tidak lengkap).
 *  3a  Yang **diisi vendor sendiri** ikut dihitung ✓, dengan tanda sumbernya.
 *  4a  Rekap = **blok pertama** layar, di atas kartu pilih vendor.
 *  5   Tambahan: lihat tanggal lain · export Excel/PDF · kirim reminder.
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * KENAPA CHIP-NYA BISA DIKLIK
 * ═══════════════════════════════════════════════════════════════════════════
 * Rekap yang cuma bisa dibaca akan memaksa staf mengingat "tadi yang merah siapa,
 * kolomnya apa" lalu mencari kartunya di bawah dan menebak tabnya. Setiap chip ✗
 * membawa `module` dari backend, jadi satu klik = langsung masuk mode override
 * vendor itu DENGAN tab yang tepat sudah terbuka.
 *
 * Angka di sini TIDAK dihitung ulang di browser — semuanya datang dari
 * `GET /api/cmt-override/daily-recap` (SSOT `backend/core/cmt_daily_recap.py`),
 * yang juga dipakai berkas export dan tombol reminder. Kalau frontend ikut
 * menghitung, suatu hari kartu ringkasan akan berdebat dengan tabelnya sendiri.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, BellRing, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight,
  ClipboardList, Download, FileSpreadsheet, FileText, Info, Loader2, MinusCircle,
  RefreshCw, Search, UserCog, X, XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ResponsiveTableWrapper } from '@/components/ui/responsive-table-wrapper';
import { apiGet, apiPost, apiFetch } from '../../../lib/api';
import { dayLabel, isoToday, shiftDay } from './recapDates';

// ── Tampilan per status kolom (empat status, bukan dua — lihat SSOT backend) ──
const CELL_STYLE = {
  done: {
    Icon: CheckCircle2,
    cls: 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100',
    label: 'Sudah diisi',
  },
  partial: {
    Icon: AlertTriangle,
    cls: 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100',
    label: 'Sudah diisi, masih ada sisa',
  },
  pending: {
    Icon: XCircle,
    cls: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100',
    label: 'BELUM diisi',
  },
  none: {
    Icon: MinusCircle,
    cls: 'border-border bg-muted/40 text-muted-foreground hover:bg-muted/70',
    label: 'Tidak ada pekerjaan',
  },
};

const ROW_STATUS = {
  pending: { text: 'Belum diisi', cls: 'border-red-300 bg-red-100 text-red-800' },
  partial: { text: 'Sebagian', cls: 'border-amber-300 bg-amber-100 text-amber-800' },
  done: { text: 'Lengkap', cls: 'border-emerald-300 bg-emerald-100 text-emerald-800' },
  idle: { text: 'Tidak ada pekerjaan', cls: 'border-border bg-muted text-muted-foreground' },
};

const SOURCE_TEXT = { staff: 'staf DA', vendor: 'vendor', mixed: 'staf + vendor' };

// `isoToday` / `shiftDay` / `dayLabel` pindah ke `./recapDates` (fase 4): tab
// Mingguan dan panel induknya memakai helper yang SAMA. Salinan per-komponen
// adalah salinan yang suatu hari akan berbeda — dan dua tab yang tidak setuju
// tentang "hari ini" adalah bug yang sangat mahal dilacak.

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
function TaskCell({ row, taskKey, task, onOpen, canFill }) {
  const vendorId = row.vendor_id;
  const st = CELL_STYLE[task?.state] || CELL_STYLE.none;
  const { Icon } = st;
  const src = SOURCE_TEXT[task?.source] || '';
  const clickable = canFill && task?.state !== 'none';
  // Untuk sel "—", keterangan backend-nya memang sama dengan labelnya ⇒ jangan
  // dicetak dua kali (tabel 5 kolom cepat penuh kebisingan dan yang merah jadi
  // sulit ditemukan — padahal justru itu yang dicari staf).
  const detail = (task?.detail && task.detail !== st.label) ? task.detail : '';
  const body = (
    <>
      <span className="flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 flex-shrink-0" />
        <span className="text-[11px] font-semibold">{st.label}</span>
      </span>
      {detail ? (
        <span className="mt-0.5 block text-[11px] leading-snug opacity-90">{detail}</span>
      ) : null}
      {src ? (
        <span className="mt-1 inline-flex items-center rounded-full border border-current/30 px-1.5 py-px text-[10px] font-medium opacity-90">
          diisi {src}
        </span>
      ) : null}
    </>
  );

  if (!clickable) {
    return (
      <div className={`rounded-lg border px-2.5 py-2 ${st.cls}`}
        data-testid={`cmt-recap-cell-${vendorId}-${taskKey}`}
        data-state={task?.state || 'none'}>
        {body}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(row, task?.module)}
      title={`Buka modul ini untuk ${taskKey}`}
      className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] ${st.cls}`}
      data-testid={`cmt-recap-cell-${vendorId}-${taskKey}`}
      data-state={task?.state || 'none'}
    >
      {body}
    </button>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
/**
 * Props tanggal (fase 4 — Rekap Mingguan):
 *   `day` + `onDayChange` membuat komponen ini **terkendali** oleh
 *   `CMTOverrideRecapPanel`, supaya klik satu kotak hari di tab Mingguan bisa
 *   membuka tab Harian PADA TANGGAL ITU. Tanpa prop, komponen tetap memegang
 *   tanggalnya sendiri (dipakai bila dirender langsung tanpa panel).
 */
export default function CMTOverrideDailyRecap({
  onOpenVendor, canFill = true, day: dayProp, onDayChange,
}) {
  const [dayLocal, setDayLocal] = useState(isoToday);
  const controlled = typeof dayProp === 'string' && !!dayProp;
  const day = controlled ? dayProp : dayLocal;

  const setDay = useCallback((next) => {
    const val = typeof next === 'function' ? next(day) : next;
    if (typeof onDayChange === 'function') onDayChange(val);
    if (!controlled) setDayLocal(val);
  }, [controlled, day, onDayChange]);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [onlyPending, setOnlyPending] = useState(false);
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmRemind, setConfirmRemind] = useState(false);

  const load = useCallback(async (d) => {
    setLoading(true); setErr('');
    try {
      const res = await apiGet(`/cmt-override/daily-recap?date=${d}`);
      setData(res);
    } catch (e) {
      setErr(e.message || 'Gagal memuat rekap harian');
      setData(null);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(day); }, [day, load]);

  const tasks = data?.tasks || [];
  const summary = data?.summary || {};
  // `useMemo` supaya identitas array-nya stabil: tanpa ini, dua useMemo turunan
  // di bawah dihitung ulang setiap render (dan ESLint memperingatkannya).
  const rows = useMemo(() => data?.rows || [], [data]);
  const isToday = day === isoToday();

  const pendingRows = useMemo(() => rows.filter(r => r.status === 'pending'), [rows]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(r => {
      if (onlyPending && r.status !== 'pending' && r.status !== 'partial') return false;
      if (!q) return true;
      return `${r.vendor_name} ${r.vendor_code} ${r.contact_name}`.toLowerCase().includes(q);
    });
  }, [rows, onlyPending, search]);

  const download = async (fmt) => {
    setBusy(fmt);
    try {
      const res = await apiFetch(`/cmt-override/daily-recap/export?format=${fmt}&date=${day}`);
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
      a.download = guess || `rekap-harian-cmt-${day}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Rekap ${fmt.toUpperCase()} tanggal ${day} diunduh.`);
    } catch (e) {
      toast.error(e.message || 'Gagal mengunduh rekap');
    } finally { setBusy(''); }
  };

  const sendReminders = async () => {
    setBusy('remind');
    try {
      const res = await apiPost('/cmt-override/daily-recap/remind', { date: day });
      const sent = res?.sent_count || 0;
      const skipped = res?.skipped_count || 0;
      if (sent > 0) {
        toast.success(
          `Reminder terkirim ke ${sent} vendor.` +
          (skipped ? ` ${skipped} dilewati (sudah ditegur untuk tanggal ini).` : ''),
        );
      } else if (skipped > 0) {
        toast.info(`Tidak ada yang dikirim — ${skipped} vendor sudah ditegur untuk tanggal ini.`);
      } else {
        toast.info('Tidak ada vendor yang perlu ditegur.');
      }
      setConfirmRemind(false);
      load(day);
    } catch (e) {
      toast.error(e.message || 'Gagal mengirim reminder');
    } finally { setBusy(''); }
  };

  // Baris rekap dikirim UTUH ke induk (bukan cuma id): induk butuh nama +
  // status akun portal untuk spanduk & peringatan dobel input, dan tidak boleh
  // bergantung pada daftar vendor yang mungkin belum selesai dimuat.
  const openVendor = (row, moduleId) => {
    if (typeof onOpenVendor === 'function') onOpenVendor(row, moduleId);
  };

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm" data-testid="cmt-recap-panel">
      {/* ── Kepala ───────────────────────────────────────────────────────── */}
      <div className="border-b border-border p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-blue-600">
              <ClipboardList className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">Rekap Harian</h2>
              <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
                Vendor mana yang <b>belum diisi</b> untuk tanggal ini — per jenis pekerjaan,
                supaya tidak ada yang terlewat. Klik kotak <b>Belum diisi</b> untuk langsung
                membuka modulnya atas nama vendor itu.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-1">
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0"
                onClick={() => setDay(d => shiftDay(d, -1))}
                title="Hari sebelumnya" data-testid="cmt-recap-prev-day">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="date"
                  value={day}
                  max={shiftDay(isoToday(), 1)}
                  onChange={e => e.target.value && setDay(e.target.value)}
                  className="h-8 rounded-md border border-border bg-background pl-7 pr-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))]"
                  data-testid="cmt-recap-date-input"
                />
              </div>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0"
                onClick={() => setDay(d => shiftDay(d, 1))}
                title="Hari berikutnya" data-testid="cmt-recap-next-day">
                <ChevronRight className="h-4 w-4" />
              </Button>
              {!isToday && (
                <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-semibold text-blue-700"
                  onClick={() => setDay(isoToday())} data-testid="cmt-recap-today">
                  Hari ini
                </Button>
              )}
            </div>

            <Button variant="outline" size="sm" onClick={() => load(day)} data-testid="cmt-recap-refresh">
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Muat ulang
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('xlsx')}
              disabled={busy === 'xlsx'} data-testid="cmt-recap-export-xlsx">
              {busy === 'xlsx'
                ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                : <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" />}
              Excel
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('pdf')}
              disabled={busy === 'pdf'} data-testid="cmt-recap-export-pdf">
              {busy === 'pdf'
                ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                : <FileText className="mr-1.5 h-3.5 w-3.5" />}
              PDF
            </Button>
          </div>
        </div>

        <p className="mt-3 text-xs font-medium text-foreground" data-testid="cmt-recap-day-label">
          {dayLabel(day)}
          {isToday
            ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-700">HARI INI</span>
            : <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">TANGGAL LAIN</span>}
        </p>

        {/* ── Kartu ringkasan ─────────────────────────────────────────────── */}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard testid="cmt-recap-summary-pending" tone="red" label="Belum diisi"
            value={summary.vendors_pending ?? 0} hint="ada tugas merah" />
          <StatCard testid="cmt-recap-summary-partial" tone="amber" label="Sebagian"
            value={summary.vendors_partial ?? 0} hint="terisi, masih ada sisa" />
          <StatCard testid="cmt-recap-summary-done" tone="green" label="Lengkap"
            value={summary.vendors_done ?? 0} hint="tidak ada sisa" />
          <StatCard testid="cmt-recap-summary-idle" tone="grey" label="Tanpa pekerjaan"
            value={summary.vendors_idle ?? 0} hint="tidak perlu diisi" />
          <StatCard testid="cmt-recap-summary-tasks" tone="blue" label="Tugas belum diisi"
            value={summary.tasks_pending_total ?? 0}
            hint={`${summary.qty_progress_today ?? 0} pcs progress masuk`} />
        </div>
      </div>

      {/* ── Bar aksi ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-4 py-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari vendor di rekap…" className="h-9 pl-9"
            data-testid="cmt-recap-search" />
        </div>
        <label className="flex cursor-pointer select-none items-center gap-2 text-xs font-medium text-foreground">
          <input type="checkbox" checked={onlyPending}
            onChange={e => setOnlyPending(e.target.checked)}
            className="h-4 w-4 rounded border-border"
            data-testid="cmt-recap-filter-pending" />
          Hanya yang belum lengkap
        </label>
        <Button size="sm" onClick={() => setConfirmRemind(true)}
          disabled={pendingRows.length === 0 || busy === 'remind'}
          className="bg-amber-600 text-white hover:bg-amber-700"
          data-testid="cmt-recap-remind">
          <BellRing className="mr-1.5 h-3.5 w-3.5" />
          Kirim reminder ({pendingRows.length})
        </Button>
      </div>

      {/* ── Konfirmasi reminder (bukan window.confirm: staf harus LIHAT dulu
             siapa yang akan ditegur — menegur vendor yang sudah setor merusak
             kepercayaan, dan itu tidak bisa ditarik kembali) ─────────────── */}
      {confirmRemind && (
        <div className="border-b border-amber-300 bg-amber-50 p-4" data-testid="cmt-recap-remind-confirm">
          <div className="flex items-start gap-3">
            <BellRing className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-amber-900">
                Kirim reminder ke {pendingRows.length} vendor yang belum diisi?
              </p>
              <p className="mt-1 text-xs text-amber-800">
                Reminder masuk ke <b>Inbox Reminder</b> vendor. Satu vendor hanya menerima
                satu reminder rekap per tanggal — klik dua kali tidak menggandakan.
              </p>
              <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-amber-900">
                {pendingRows.map(r => (
                  <li key={r.vendor_id}>
                    • <b>{r.vendor_name}</b>
                    <span className="opacity-80"> — {(r.pending_tasks || []).join(', ')}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={sendReminders} disabled={busy === 'remind'}
                  className="bg-amber-600 text-white hover:bg-amber-700"
                  data-testid="cmt-recap-remind-confirm-yes">
                  {busy === 'remind' && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  Ya, kirim sekarang
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirmRemind(false)}
                  data-testid="cmt-recap-remind-confirm-no">
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
      {/* Sejak `closed_at` ada, rekap tanggal lampau tidak lagi memaafkan kelalaian
          yang sudah terjadi. Sisa ketidaktahuannya HANYA job yang sudah tertutup
          sebelum fitur itu ada — dan obatnya satu perintah migrasi. Dinaikkan jadi
          amber (bukan diselipkan di ujung paragraf abu-abu 11px) karena catatan yang
          tidak terbaca sama saja dengan tidak mengaku, dan rekap yang diam soal
          batasnya sendiri akan dipercaya lebih daripada yang seharusnya. */}
      {data?.legacy_jobs_without_closed_at > 0 && data?.legacy_note && (
        <div className="flex items-start gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2.5"
          data-testid="cmt-recap-legacy-jobs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
          <p className="text-[11px] leading-snug text-amber-900">
            <span className="font-semibold">Sebagian tanggal lampau belum bisa dihitung penuh — </span>
            {data.legacy_note}
          </p>
        </div>
      )}

      {/* ── Catatan kejujuran data untuk tanggal lampau ──────────────────── */}
      {!isToday && (data?.as_of_note_base || data?.as_of_note) && (
        <div className="flex items-start gap-2 border-b border-border bg-muted/40 px-4 py-2.5"
          data-testid="cmt-recap-as-of-note">
          <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-blue-600" />
          <p className="text-[11px] leading-snug text-muted-foreground">
            {data.as_of_note_base || data.as_of_note}
          </p>
        </div>
      )}

      {/* ── Tabel ────────────────────────────────────────────────────────── */}
      {err ? (
        <div className="p-4">
          <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800"
            data-testid="cmt-recap-error">{err}</div>
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-16" data-testid="cmt-recap-loading">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : visible.length === 0 ? (
        <div className="py-14 text-center" data-testid="cmt-recap-empty">
          <CheckCircle2 className="mx-auto mb-2 h-9 w-9 text-emerald-500" />
          <p className="font-medium text-foreground">
            {rows.length === 0
              ? 'Belum ada vendor CMT aktif di master'
              : onlyPending
                ? 'Tidak ada vendor yang belum lengkap — semua sudah diisi'
                : 'Tidak ada vendor yang cocok dengan pencarian'}
          </p>
        </div>
      ) : (
        <ResponsiveTableWrapper stickyFirstCol>
          <table className="w-full min-w-[980px] text-sm">
            <thead className="bg-muted/60">
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2.5">Vendor</th>
                {tasks.map(t => (
                  <th key={t.key} className="px-2 py-2.5 font-semibold">{t.label}</th>
                ))}
                <th className="px-3 py-2.5 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visible.map(r => {
                const stat = ROW_STATUS[r.status] || ROW_STATUS.idle;
                return (
                  <tr key={r.vendor_id} className="align-top hover:bg-muted/30"
                    data-testid={`cmt-recap-row-${r.vendor_id}`} data-status={r.status}>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-foreground">{r.vendor_name}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {r.vendor_code || '—'}
                      </p>
                      <span className={`mt-1.5 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${stat.cls}`}
                        data-testid={`cmt-recap-status-${r.vendor_id}`}>
                        {stat.text}
                      </span>
                      {r.has_active_portal_account && (
                        <span className="mt-1 flex items-center gap-1 text-[10px] text-amber-700"
                          title="Vendor ini punya akun portal aktif — hati-hati dobel input">
                          <AlertTriangle className="h-3 w-3" /> punya akun portal
                        </span>
                      )}
                    </td>
                    {tasks.map(t => (
                      <td key={t.key} className="px-2 py-3">
                        <TaskCell row={r} taskKey={t.key}
                          task={(r.tasks || {})[t.key]} onOpen={openVendor} canFill={canFill} />
                      </td>
                    ))}
                    <td className="px-3 py-3 text-right">
                      <Button size="sm" variant="outline" className="whitespace-nowrap"
                        onClick={() => openVendor(r, null)}
                        data-testid={`cmt-recap-fill-${r.vendor_id}`}>
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

      {/* ── Legenda ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
        <span className="font-semibold text-foreground">Keterangan:</span>
        <span className="inline-flex items-center gap-1"><XCircle className="h-3.5 w-3.5 text-red-600" /> belum diisi (ada pekerjaan menunggu)</span>
        <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-600" /> sudah diisi, masih ada sisa</span>
        <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> sudah diisi</span>
        <span className="inline-flex items-center gap-1"><MinusCircle className="h-3.5 w-3.5" /> memang tidak ada pekerjaan</span>
        <span className="ml-auto inline-flex items-center gap-1"><Download className="h-3 w-3" /> Excel/PDF isinya sama dengan layar ini</span>
      </div>
    </div>
  );
}
