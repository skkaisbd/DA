/**
 * PortalSayaAbsen — ABSEN DI DALAM PORTAL SAYA (tanpa pindah halaman / login ulang).
 *
 * ════════════════════════════════════════════════════════════════════════════
 * KENAPA MODUL INI ADA (temuan 2026-07-26, dilaporkan user)
 * ════════════════════════════════════════════════════════════════════════════
 * 1. Tombol "Absen Sekarang" di Portal Saya dulu memanggil
 *    `window.location.href = '/absen'` ⇒ KELUAR dari SPA, halaman penuh dimuat
 *    ulang dengan tampilan berbeda, dan terasa seperti "disuruh login lagi".
 * 2. Halaman `/absen` menampilkan KARYAWAN YANG SALAH (login Siti Rahayu DA-002
 *    tapi tampil "Budi Operator OP-001") karena backend jatuh ke "karyawan
 *    pertama di DB". Akar itu sudah ditutup di `utils/employee_identity.py`.
 * 3. Hanya ada clock-in & clock-out — TIDAK ADA tombol Istirahat (keluar/masuk)
 *    dan Izin (keluar/masuk), padahal keduanya harus tercatat di HR.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * FASE 16 — KEPUTUSAN USER 2026-07-26
 * ════════════════════════════════════════════════════════════════════════════
 * · **Selfie + lokasi WAJIB.** UI menuntun: minta izin kamera & lokasi lebih
 *   dulu, tampilkan jarak ke kantor, dan tombol absen dikunci + diberi alasan
 *   yang jelas bila syarat belum terpenuhi (bukan gagal diam-diam di server).
 * · **Izin keluar WAJIB disetujui atasan/HR.** Karyawan MENGAJUKAN; status
 *   "menunggu persetujuan" terlihat, bisa dibatalkan; sesi baru berjalan
 *   setelah disetujui. Istirahat tetap langsung.
 *
 * Modul ini memakai token SPA yang sama (prop `token`) sehingga tidak ada login
 * kedua, dan memanggil endpoint yang identitasnya ditentukan server (tanpa
 * mengirim `employee_id` ⇒ mustahil "titip absen").
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import {
  Clock, LogIn, LogOut, Coffee, DoorOpen, MapPin, Camera, Loader2,
  RefreshCw, AlertCircle, CheckCircle2, Timer, CalendarClock, ShieldCheck,
  Hourglass, XCircle, Upload, RotateCcw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const fmtTime = (v) => {
  if (!v) return '--:--';
  try {
    return new Date(v).toLocaleTimeString('id-ID', {
      hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta',
    });
  } catch { return '--:--'; }
};

const fmtDur = (mins) => {
  const m = Math.max(0, Math.round(Number(mins) || 0));
  if (m < 60) return `${m} mnt`;
  return `${Math.floor(m / 60)} j ${m % 60} mnt`;
};

const fmtMeter = (m) => (m == null ? '-' : (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`));

/** Haversine ringkas — hanya untuk PRATINJAU jarak di layar.
 *  Keputusan diterima/ditolaknya absen tetap 100% di server. */
const distanceM = (a, b) => {
  if (!a || !b || a.lat == null || b.lat == null) return null;
  const R = 6371000, rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const s = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
};

const APPROVAL_LABEL = {
  pending: { text: 'Menunggu persetujuan', cls: 'bg-amber-100 text-amber-800 border-amber-300' },
  approved: { text: 'Disetujui', cls: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  rejected: { text: 'Ditolak', cls: 'bg-red-100 text-red-800 border-red-300' },
  cancelled: { text: 'Dibatalkan', cls: 'bg-slate-100 text-slate-700 border-slate-300' },
  not_required: { text: 'Tercatat', cls: 'bg-blue-100 text-blue-800 border-blue-300' },
};

export default function PortalSayaAbsen({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [status, setStatus] = useState(null);
  const [office, setOffice] = useState(null);
  const [geo, setGeo] = useState(null);           // { lat, lng, accuracy }
  const [geoError, setGeoError] = useState('');
  const [izinOpen, setIzinOpen] = useState(false);
  const [izinReason, setIzinReason] = useState('');
  const [camOpen, setCamOpen] = useState(false);
  const [camAction, setCamAction] = useState('in');   // 'in' | 'out'
  const [camError, setCamError] = useState('');
  const [shot, setShot] = useState('');               // base64 hasil jepret
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);

  // ── Muat status + kebijakan kantor ─────────────────────────────────────
  const load = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([
        axios.get(`${API}/api/rahaza/attendance/my-status`, { headers }),
        axios.get(`${API}/api/rahaza/attendance/office-location`, { headers })
          .catch(() => ({ data: null })),
      ]);
      setStatus(s.data || {});
      setOffice(o.data || null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal memuat status kehadiran');
    } finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  // ── Lokasi: diminta sejak awal supaya karyawan tahu statusnya ──────────
  const askLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError('Perangkat/browser ini tidak mendukung lokasi GPS.');
      return;
    }
    setGeoError('');
    navigator.geolocation.getCurrentPosition(
      (p) => setGeo({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
      (err) => setGeoError(
        err.code === 1
          ? 'Izin lokasi ditolak. Aktifkan izin lokasi untuk situs ini lalu tekan "Coba lagi".'
          : `Lokasi belum terbaca (${err.message}).`),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    );
  }, []);

  useEffect(() => { askLocation(); }, [askLocation]);

  const stopCam = useCallback(() => {
    try { streamRef.current?.getTracks?.().forEach((t) => t.stop()); } catch { /* noop */ }
    streamRef.current = null;
  }, []);

  useEffect(() => () => stopCam(), [stopCam]);

  const openCam = async (action) => {
    setCamAction(action);
    setShot('');
    setCamError('');
    setCamOpen(true);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      streamRef.current = s;
      // video di-render setelah dialog terbuka → beri satu tick
      setTimeout(() => { if (videoRef.current) videoRef.current.srcObject = s; }, 120);
    } catch {
      setCamError('Kamera tidak bisa diakses. Izinkan kamera di browser, atau unggah foto dari galeri.');
    }
  };

  const capture = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) {
      setCamError('Kamera belum siap. Tunggu sebentar lalu coba lagi.');
      return;
    }
    const c = document.createElement('canvas');
    c.width = 640;
    c.height = Math.round((v.videoHeight / v.videoWidth) * 640) || 480;
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    setShot((c.toDataURL('image/jpeg', 0.8).split(',')[1]) || '');
    setCamError('');
  };

  /** Jalur cadangan: unggah foto (dipakai bila kamera tidak tersedia, dan
   *  dipakai QA otomatis yang tidak bisa memakai getUserMedia). */
  const onPickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!/^image\//.test(f.type)) { setCamError('File harus berupa gambar.'); return; }
    const rd = new FileReader();
    rd.onload = () => { setShot(String(rd.result).split(',')[1] || ''); setCamError(''); };
    rd.readAsDataURL(f);
  };

  const closeCam = () => { stopCam(); setCamOpen(false); setShot(''); setCamError(''); };

  // ── Aksi ───────────────────────────────────────────────────────────────
  const doClock = async (action) => {
    if (!shot) { setCamError('Ambil selfie dulu — foto wajib untuk absen.'); return; }
    setBusy(action);
    try {
      const url = action === 'in'
        ? `${API}/api/rahaza/attendance/selfie/clock-in`
        : `${API}/api/rahaza/attendance/selfie/clock-out`;
      // employee_id TIDAK dikirim → server memakai identitas token (anti titip absen)
      const r = await axios.post(url, {
        lat: geo?.lat ?? null, lng: geo?.lng ?? null,
        photo_base64: shot, do_face_check: true,
      }, { headers });
      toast.success(r.data?.message || (action === 'in' ? 'Absen masuk tercatat' : 'Absen pulang tercatat'));
      closeCam();
      load();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Gagal mencatat absen';
      setCamError(msg);
      toast.error(msg);
    } finally { setBusy(''); }
  };

  const startSession = async (kind, reason = '') => {
    setBusy(`start-${kind}`);
    try {
      const r = await axios.post(`${API}/api/rahaza/attendance/sessions/start`, {
        kind, reason, lat: geo?.lat ?? null, lng: geo?.lng ?? null,
      }, { headers });
      toast.success(r.data?.message || (kind === 'izin' ? 'Pengajuan izin terkirim' : 'Istirahat dimulai'));
      setIzinOpen(false); setIzinReason('');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal memulai sesi');
    } finally { setBusy(''); }
  };

  const endSession = async () => {
    setBusy('end');
    try {
      const r = await axios.post(`${API}/api/rahaza/attendance/sessions/end`, {
        lat: geo?.lat ?? null, lng: geo?.lng ?? null,
      }, { headers });
      toast.success(`Kembali kerja — tercatat ${fmtDur(r.data?.minutes)}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal menutup sesi');
    } finally { setBusy(''); }
  };

  const cancelPermit = async (id) => {
    setBusy('cancel');
    try {
      await axios.post(`${API}/api/rahaza/attendance/permits/${id}/cancel`, {}, { headers });
      toast.success('Pengajuan izin dibatalkan');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gagal membatalkan pengajuan');
    } finally { setBusy(''); }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="space-y-4 p-6" data-testid="portal-absen-loading">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  // Akun belum ditautkan ke data karyawan → jelaskan, jangan tampilkan orang lain.
  if (status && status.linked === false) {
    return (
      <div className="p-6" data-testid="portal-absen-unlinked">
        <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/30">
          <CardContent className="pt-5 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-amber-900 dark:text-amber-200">
                Akun belum ditautkan ke data karyawan
              </p>
              <p className="text-sm text-amber-800 dark:text-amber-300 mt-1">
                {status.message || 'Minta Admin HR menautkan akun Anda lewat menu Data Karyawan → Tautkan Akun.'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const emp = status?.employee || {};
  const today = status?.today || null;
  const active = status?.active_session || null;
  const sessions = today?.sessions || [];
  const pendingPermit = status?.pending_permit
    || sessions.find((s) => s.kind === 'izin' && (s.approval_status || 'pending') === 'pending');
  const hasIn = Boolean(today?.clock_in);
  const hasOut = Boolean(today?.clock_out);
  const late = Number(today?.late_minutes ?? status?.late_minutes ?? 0);

  const requireGeo = office?.require_geofence !== false;
  const officeSet = Boolean(office?.configured);
  const dist = officeSet && geo ? distanceM(geo, { lat: office.lat, lng: office.lng }) : null;
  const inRange = dist == null ? null : dist <= Number(office?.geofence_radius_m || 300);

  // Alasan tombol absen dikunci — DITAMPILKAN, bukan disembunyikan.
  let blockReason = '';
  if (requireGeo && !officeSet) {
    blockReason = 'Lokasi kantor belum diatur Admin HR (menu Absensi → Konfigurasi).';
  } else if (requireGeo && !geo) {
    blockReason = geoError || 'Menunggu izin lokasi GPS…';
  } else if (requireGeo && inRange === false) {
    blockReason = `Anda ${fmtMeter(dist)} dari ${office?.name || 'kantor'} (batas ${fmtMeter(office?.geofence_radius_m)}). Absen hanya bisa di area kantor.`;
  }
  const canClock = !blockReason;

  return (
    <div className="space-y-5 p-6" data-testid="portal-absen-page">
      {/* Identitas — dulu bisa salah orang, sekarang dijamin dari token */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2">
                <Clock className="w-5 h-5 text-primary" /> Absen Saya
              </h1>
              <p className="text-sm text-muted-foreground mt-0.5" data-testid="absen-identity">
                {emp.name || '-'} · {emp.employee_code || '-'}
                {emp.job_title ? ` · ${emp.job_title}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="gap-1">
                <CalendarClock className="w-3 h-3" />
                {new Date().toLocaleDateString('id-ID', {
                  weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
                })}
              </Badge>
              <Button variant="outline" size="sm" onClick={load} data-testid="absen-refresh">
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Kesiapan absen — selfie & lokasi WAJIB */}
      <Card data-testid="absen-readiness">
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="flex items-center gap-1.5 font-medium">
              <ShieldCheck className="w-4 h-4 text-primary" /> Syarat absen:
            </span>
            <span className="flex items-center gap-1.5">
              <Camera className="w-4 h-4" />
              Selfie {office?.require_selfie === false ? 'opsional' : <b>wajib</b>}
            </span>
            <span className="flex items-center gap-1.5" data-testid="absen-geo-status">
              <MapPin className={`w-4 h-4 ${inRange === true ? 'text-emerald-600' : inRange === false ? 'text-red-600' : 'text-muted-foreground'}`} />
              {!requireGeo && 'Lokasi tidak diwajibkan'}
              {requireGeo && !officeSet && 'Lokasi kantor belum diatur'}
              {requireGeo && officeSet && !geo && (geoError ? 'Lokasi belum diizinkan' : 'Membaca lokasi…')}
              {requireGeo && officeSet && geo && (
                inRange
                  ? <span className="text-emerald-700">Di area kantor ({fmtMeter(dist)})</span>
                  : <span className="text-red-700">Di luar area kantor ({fmtMeter(dist)})</span>
              )}
            </span>
            {requireGeo && !geo && (
              <Button size="sm" variant="outline" onClick={askLocation} data-testid="absen-retry-geo">
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Coba lagi
              </Button>
            )}
          </div>
          {blockReason && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-sm text-amber-900 dark:text-amber-200"
              data-testid="absen-block-reason">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> {blockReason}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Status hari ini */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Status Hari Ini</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Masuk</p>
              <p className="text-lg font-semibold" data-testid="absen-clock-in-time">{fmtTime(today?.clock_in)}</p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Pulang</p>
              <p className="text-lg font-semibold" data-testid="absen-clock-out-time">{fmtTime(today?.clock_out)}</p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Istirahat</p>
              <p className="text-lg font-semibold" data-testid="absen-break-total">
                {fmtDur(status?.break_minutes)}
              </p>
            </div>
            <div className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">Izin Keluar (disetujui)</p>
              <p className="text-lg font-semibold" data-testid="absen-permit-total">
                {fmtDur(status?.permit_minutes)}
              </p>
            </div>
          </div>

          {late > 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400"
              data-testid="absen-late-warning">
              <AlertCircle className="w-4 h-4" />
              Terlambat {fmtDur(late)}
              {today?.shift_start ? ` (jam masuk shift ${today.shift_start})` : ''}
            </div>
          )}
          {hasIn && !hasOut && late === 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 className="w-4 h-4" /> Tepat waktu
            </div>
          )}
          {today?.photo_selfie_url && (
            <div className="mt-3 flex items-center gap-3">
              <img src={`${API}${today.photo_selfie_url}`} alt="Bukti selfie absen masuk"
                className="w-16 h-16 rounded-lg object-cover border" data-testid="absen-selfie-proof" />
              <span className="text-xs text-muted-foreground">Bukti selfie absen masuk tersimpan.</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pengajuan izin menunggu keputusan */}
      {pendingPermit && (
        <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/30" data-testid="absen-pending-permit">
          <CardContent className="pt-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <Hourglass className="w-5 h-5 text-amber-600 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-900 dark:text-amber-200">
                  Izin menunggu persetujuan atasan/HR
                </p>
                <p className="text-sm text-amber-800 dark:text-amber-300">
                  &quot;{pendingPermit.reason}&quot; · diajukan {fmtTime(pendingPermit.requested_at)}
                  {' '}· Anda belum dianggap keluar sampai disetujui.
                </p>
              </div>
            </div>
            <Button variant="outline" onClick={() => cancelPermit(pendingPermit.id)}
              disabled={busy === 'cancel'} data-testid="absen-permit-cancel-pending">
              {busy === 'cancel' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <XCircle className="w-4 h-4 mr-1.5" />}
              Batalkan Pengajuan
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Sesi keluar yang masih terbuka */}
      {active && (
        <Card className="border-blue-300 bg-blue-50 dark:bg-blue-950/30" data-testid="absen-active-session">
          <CardContent className="pt-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <Timer className="w-5 h-5 text-blue-600 mt-0.5" />
              <div>
                <p className="font-semibold text-blue-900 dark:text-blue-200">
                  {active.kind === 'izin' ? 'Sedang IZIN keluar (disetujui)' : 'Sedang ISTIRAHAT'}
                </p>
                <p className="text-sm text-blue-800 dark:text-blue-300">
                  Keluar {fmtTime(active.out_at)}
                  {active.reason ? ` · "${active.reason}"` : ''}
                  {active.approved_by_name ? ` · disetujui ${active.approved_by_name}` : ''}
                </p>
              </div>
            </div>
            <Button onClick={endSession} disabled={busy === 'end'} data-testid="absen-session-end">
              {busy === 'end' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <LogIn className="w-4 h-4 mr-1.5" />}
              Kembali Kerja
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Tombol aksi */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Aksi Absen</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Button
              size="lg" className="h-16 flex-col gap-1"
              onClick={() => openCam('in')}
              disabled={hasIn || !canClock || Boolean(busy)}
              data-testid="absen-btn-clock-in"
            >
              <LogIn className="w-5 h-5" />
              <span className="text-sm">Absen Masuk</span>
            </Button>

            <Button
              size="lg" variant="secondary" className="h-16 flex-col gap-1"
              onClick={() => startSession('istirahat')}
              disabled={!hasIn || hasOut || Boolean(active) || Boolean(pendingPermit) || Boolean(busy)}
              data-testid="absen-btn-break-start"
            >
              {busy === 'start-istirahat' ? <Loader2 className="w-5 h-5 animate-spin" />
                : <Coffee className="w-5 h-5" />}
              <span className="text-sm">Istirahat Keluar</span>
            </Button>

            <Button
              size="lg" variant="secondary" className="h-16 flex-col gap-1"
              onClick={() => setIzinOpen(true)}
              disabled={!hasIn || hasOut || Boolean(active) || Boolean(pendingPermit) || Boolean(busy)}
              data-testid="absen-btn-permit-start"
            >
              <DoorOpen className="w-5 h-5" />
              <span className="text-sm">Ajukan Izin Keluar</span>
            </Button>

            <Button
              size="lg" variant="destructive" className="h-16 flex-col gap-1"
              onClick={() => openCam('out')}
              disabled={!hasIn || hasOut || Boolean(active) || Boolean(pendingPermit) || !canClock || Boolean(busy)}
              data-testid="absen-btn-clock-out"
            >
              <LogOut className="w-5 h-5" />
              <span className="text-sm">Absen Pulang</span>
            </Button>
          </div>

          <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5" />
            Selfie & lokasi dikirim sebagai bukti. Izin keluar baru berjalan setelah disetujui;
            tutup sesi istirahat/izin sebelum absen pulang.
          </p>
        </CardContent>
      </Card>

      {/* Riwayat sesi hari ini */}
      {sessions.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Riwayat Keluar-Masuk Hari Ini</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y" data-testid="absen-session-history">
              {sessions.map((s) => {
                const st = APPROVAL_LABEL[s.approval_status || (s.kind === 'izin' ? 'approved' : 'not_required')]
                  || APPROVAL_LABEL.not_required;
                return (
                  <div key={s.id} className="py-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                    <div className="flex items-center gap-2">
                      {s.kind === 'izin'
                        ? <DoorOpen className="w-4 h-4 text-amber-600" />
                        : <Coffee className="w-4 h-4 text-blue-600" />}
                      <span className="font-medium capitalize">{s.kind}</span>
                      {s.reason && <span className="text-muted-foreground italic">&quot;{s.reason}&quot;</span>}
                      <span className={`text-[11px] px-1.5 py-0.5 rounded border ${st.cls}`}>{st.text}</span>
                    </div>
                    <div className="text-muted-foreground">
                      {s.out_at ? fmtTime(s.out_at) : '—'} → {s.in_at ? fmtTime(s.in_at) : (s.out_at ? 'belum kembali' : '—')}
                      {s.minutes != null && s.minutes > 0 && ` · ${fmtDur(s.minutes)}`}
                      {s.decision_notes && ` · ${s.decision_notes}`}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Dialog alasan izin — WAJIB (server menolak izin tanpa alasan) */}
      <Dialog open={izinOpen} onOpenChange={(v) => { setIzinOpen(v); if (!v) setIzinReason(''); }}>
        <DialogContent data-testid="absen-permit-dialog">
          <DialogHeader>
            <DialogTitle>Ajukan Izin Keluar</DialogTitle>
            <DialogDescription>
              Alasan wajib diisi. Pengajuan dikirim ke atasan/HR — Anda baru dianggap keluar
              setelah <b>disetujui</b>, dan durasinya TIDAK dihitung sebagai jam kerja.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor="izin-reason">Alasan</Label>
            <Textarea
              id="izin-reason" rows={3} className="mt-1"
              placeholder="Contoh: ke klinik, urusan keluarga…"
              value={izinReason}
              onChange={(e) => setIzinReason(e.target.value)}
              data-testid="absen-permit-reason"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIzinOpen(false)}
              data-testid="absen-permit-cancel">Batal</Button>
            <Button
              onClick={() => startSession('izin', izinReason.trim())}
              disabled={!izinReason.trim() || busy === 'start-izin'}
              data-testid="absen-permit-confirm"
            >
              {busy === 'start-izin' && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}
              Kirim Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog kamera selfie */}
      <Dialog open={camOpen} onOpenChange={(v) => { if (!v) closeCam(); else setCamOpen(true); }}>
        <DialogContent data-testid="absen-camera-dialog">
          <DialogHeader>
            <DialogTitle>{camAction === 'in' ? 'Absen Masuk' : 'Absen Pulang'} — Selfie Wajib</DialogTitle>
            <DialogDescription>
              Ambil selfie sebagai bukti kehadiran. Foto disimpan dan bisa diperiksa HR.
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg overflow-hidden bg-muted aspect-video flex items-center justify-center">
            {shot
              ? <img src={`data:image/jpeg;base64,${shot}`} alt="Pratinjau selfie"
                className="w-full h-full object-cover" data-testid="absen-selfie-preview" />
              : <video ref={videoRef} autoPlay playsInline muted
                className="w-full h-full object-cover" data-testid="absen-camera-video" />}
          </div>

          {camError && (
            <p className="text-sm text-red-600 flex items-start gap-1.5" data-testid="absen-camera-error">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> {camError}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            {!shot ? (
              <Button variant="secondary" onClick={capture} data-testid="absen-camera-capture">
                <Camera className="w-4 h-4 mr-1.5" /> Ambil Foto
              </Button>
            ) : (
              <Button variant="secondary" onClick={() => setShot('')} data-testid="absen-camera-retake">
                <RotateCcw className="w-4 h-4 mr-1.5" /> Ulangi Foto
              </Button>
            )}
            <Button variant="outline" onClick={() => fileRef.current?.click()}
              data-testid="absen-camera-upload-btn">
              <Upload className="w-4 h-4 mr-1.5" /> Unggah Foto
            </Button>
            <input ref={fileRef} type="file" accept="image/*" className="hidden"
              onChange={onPickFile} data-testid="absen-camera-file" />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeCam} data-testid="absen-camera-cancel">Batal</Button>
            <Button onClick={() => doClock(camAction)} disabled={!shot || Boolean(busy)}
              data-testid="absen-camera-confirm">
              {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <CheckCircle2 className="w-4 h-4 mr-1.5" />}
              {camAction === 'in' ? 'Kirim Absen Masuk' : 'Kirim Absen Pulang'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
