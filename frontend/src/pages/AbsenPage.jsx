/**
 * AbsenPage — Halaman Absen Mandiri Karyawan
 * Route: /absen
 * 
 * Mendukung:
 * 1. Selfie + Geolocation + AI Face Recognition
 * 2. WebAuthn (Fingerprint/Touch ID/Face ID)
 * 3. Status kehadiran hari ini
 * 4. Login jika belum auth
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { startRegistration, startAuthentication } from '@simplewebauthn/browser';

const BACKEND = process.env.REACT_APP_BACKEND_URL;

function api(path, opts = {}) {
  const token = localStorage.getItem('absen_token') || localStorage.getItem('erp_token');
  return fetch(`${BACKEND}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  }).then(r => r.json());
}

// ─── Login Component ──────────────────────────────────────────────────────────
function AbsenLogin({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${BACKEND}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login gagal');
      localStorage.setItem('absen_token', data.token);
      onLogin(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dark min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-500/20 border border-blue-400 dark:border-blue-500/30 mb-4">
            <span className="text-3xl">👤</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground">Portal Absen</h1>
          <p className="text-muted-foreground text-sm mt-1">CV. Dewi Aditya ERP</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-800/60 backdrop-blur border border-slate-700 rounded-2xl p-6 space-y-4">
          {error && (
            <div className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 text-red-600 dark:text-red-300 text-sm px-3 py-2 rounded-lg">
              {error}
            </div>
          )}
          <div>
            <label className="text-foreground/70 text-sm font-medium block mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              placeholder="email@perusahaan.com"
              className="w-full bg-slate-700/50 border border-slate-600 text-foreground placeholder-slate-400 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-foreground/70 text-sm font-medium block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              placeholder="Password Anda"
              className="w-full bg-slate-700/50 border border-slate-600 text-foreground placeholder-slate-400 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-foreground font-semibold py-2.5 rounded-lg transition-colors"
          >
            {loading ? 'Masuk...' : 'Masuk'}
          </button>
        </form>

        <p className="text-center text-muted-foreground/60 text-xs mt-4">
          Kembali ke{' '}
          <a href="/" className="text-blue-600 dark:text-blue-400 hover:underline">Portal Utama</a>
        </p>
      </div>
    </div>
  );
}

// ─── Selfie Camera Component ───────────────────────────────────────────────────
function SelfieCapture({ onCapture, onCancel }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [streaming, setStreaming] = useState(false);
  const [captured, setCaptured] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, []);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setStreaming(true);
      }
    } catch (err) {
      setError('Kamera tidak bisa diakses: ' + err.message);
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setStreaming(false);
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
    const base64 = dataUrl.split(',')[1];
    setCaptured({ dataUrl, base64 });
    stopCamera();
  };

  const retake = () => {
    setCaptured(null);
    startCamera();
  };

  if (error) {
    return (
      <div className="text-center p-4">
        <p className="text-red-700 dark:text-red-400 text-sm mb-3">{error}</p>
        <button onClick={onCancel} className="text-muted-foreground hover:text-foreground text-sm underline">Batal</button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {!captured ? (
        <>
          <div className="relative bg-black rounded-xl overflow-hidden" style={{ aspectRatio: '4/3' }}>
            <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
            {streaming && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-48 h-48 border-2 border-foreground/50 rounded-full" />
              </div>
            )}
          </div>
          <canvas ref={canvasRef} className="hidden" />
          <div className="flex gap-2">
            <button onClick={onCancel} className="flex-1 bg-slate-700 hover:bg-slate-600 text-foreground py-2.5 rounded-lg text-sm transition-colors">
              Batal
            </button>
            <button
              onClick={capturePhoto}
              disabled={!streaming}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-foreground py-2.5 rounded-lg text-sm font-semibold transition-colors"
            >
              📸 Ambil Foto
            </button>
          </div>
        </>
      ) : (
        <>
          <img src={captured.dataUrl} alt="Selfie" className="w-full rounded-xl" />
          <div className="flex gap-2">
            <button onClick={retake} className="flex-1 bg-slate-700 hover:bg-slate-600 text-foreground py-2.5 rounded-lg text-sm transition-colors">
              Ulangi
            </button>
            <button
              onClick={() => onCapture(captured.base64)}
              className="flex-1 bg-green-600 hover:bg-green-500 text-foreground py-2.5 rounded-lg text-sm font-semibold transition-colors"
            >
              ✓ Gunakan Foto Ini
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Status Badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status, approval }) {
  const badges = {
    hadir: { bg: 'bg-green-100 dark:bg-green-500/20 border-green-400 dark:border-green-500/30 text-green-600 dark:text-green-300', icon: '✓', label: 'Hadir' },
    izin: { bg: 'bg-yellow-100 dark:bg-yellow-500/20 border-yellow-400 dark:border-yellow-500/30 text-yellow-600 dark:text-yellow-300', icon: '📋', label: 'Izin' },
    sakit: { bg: 'bg-orange-100 dark:bg-orange-500/20 border-orange-400 dark:border-orange-500/30 text-orange-600 dark:text-orange-300', icon: '🤒', label: 'Sakit' },
    alfa: { bg: 'bg-red-100 dark:bg-red-500/20 border-red-400 dark:border-red-500/30 text-red-600 dark:text-red-300', icon: '✗', label: 'Tidak Hadir' },
    cuti: { bg: 'bg-blue-100 dark:bg-blue-500/20 border-blue-400 dark:border-blue-500/30 text-blue-600 dark:text-blue-300', icon: '🌴', label: 'Cuti' },
  };
  const b = badges[status] || { bg: 'bg-slate-100 dark:bg-slate-500/20 border-slate-400 dark:border-slate-500/30 text-foreground/70', icon: '?', label: status || '-' };
  const pendingBadge = approval === 'pending' ? ' (Menunggu Approval)' : '';
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full border text-sm font-medium ${b.bg}`}>
      {b.icon} {b.label}{pendingBadge}
    </span>
  );
}

// ─── Main AbsenPage ────────────────────────────────────────────────────────────
export default function AbsenPage() {
  const [auth, setAuth] = useState(null);
  const [status, setStatus] = useState(null); // today attendance status
  const [employee, setEmployee] = useState(null);
  const [hasWebAuthn, setHasWebAuthn] = useState(false);
  const [method, setMethod] = useState('selfie'); // 'selfie' | 'webauthn'
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null); // { type: 'success'|'error'|'warning', text }
  const [showCamera, setShowCamera] = useState(false);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoData, setGeoData] = useState(null);
  const [clockAction, setClockAction] = useState(null); // 'in' | 'out'
  const [selfieBase64, setSelfieBase64] = useState(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  // Check existing auth
  useEffect(() => {
    const token = localStorage.getItem('absen_token') || localStorage.getItem('erp_token');
    const user = localStorage.getItem('erp_user');
    if (token) {
      try {
        const u = user ? JSON.parse(user) : {};
        setAuth({ token, user: u });
      } catch { setAuth({ token, user: {} }); }
    }
    setBootstrapped(true);
  }, []);

  // Load today status
  const loadStatus = useCallback(async () => {
    try {
      const data = await api('/api/rahaza/attendance/my-status');
      setStatus(data.today);
      setEmployee(data.employee);
      setHasWebAuthn(data.has_webauthn || false);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    if (auth) loadStatus();
  }, [auth, loadStatus]);

  const handleLogin = (data) => {
    setAuth(data);
  };

  const getGeo = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) return resolve(null);
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      pos => { setGeoLoading(false); setGeoData({ lat: pos.coords.latitude, lng: pos.coords.longitude }); resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }); },
      err => { setGeoLoading(false); resolve(null); },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  });

  const doSelfieClockIn = async (photoB64) => {
    setSelfieBase64(photoB64);
    setLoading(true);
    setMsg(null);
    try {
      const geo = await getGeo();
      const body = {
        employee_id: employee?.id,
        lat: geo?.lat, lng: geo?.lng,
        photo_base64: photoB64,
        do_face_check: true,
      };
      const res = await api('/api/rahaza/attendance/selfie/clock-in', {
        method: 'POST', body: JSON.stringify(body)
      });
      if (res.ok) {
        setMsg({ type: res.approval_status === 'auto_approved' ? 'success' : 'warning', text: res.message });
        await loadStatus();
      } else {
        setMsg({ type: 'error', text: res.detail || 'Gagal clock-in' });
      }
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setLoading(false);
      setShowCamera(false);
      setSelfieBase64(null);
    }
  };

  const doSelfieClockOut = async (photoB64) => {
    setLoading(true);
    setMsg(null);
    try {
      const geo = await getGeo();
      const body = {
        employee_id: employee?.id,
        lat: geo?.lat, lng: geo?.lng,
        photo_base64: photoB64,
      };
      const res = await api('/api/rahaza/attendance/selfie/clock-out', {
        method: 'POST', body: JSON.stringify(body)
      });
      if (res.ok) {
        setMsg({ type: 'success', text: `Clock-out berhasil! ${res.hours_worked ? `(${res.hours_worked} jam kerja)` : ''}` });
        await loadStatus();
      } else {
        setMsg({ type: 'error', text: res.detail || 'Gagal clock-out' });
      }
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setLoading(false);
      setShowCamera(false);
    }
  };

  const handleSelfieCapture = async (base64) => {
    if (clockAction === 'in') await doSelfieClockIn(base64);
    else await doSelfieClockOut(base64);
  };

  const handleWebAuthnClockIn = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const optRes = await api('/api/rahaza/attendance/webauthn/auth/options', {
        method: 'POST', body: JSON.stringify({ employee_id: employee?.id })
      });
      if (optRes.detail) throw new Error(optRes.detail);
      const assertion = await startAuthentication(optRes);
      const verifyRes = await api('/api/rahaza/attendance/webauthn/clock-in', {
        method: 'POST',
        body: JSON.stringify({ ...assertion, employee_id: employee?.id })
      });
      if (verifyRes.ok) {
        setMsg({ type: 'success', text: verifyRes.message || 'Clock-in biometrik berhasil!' });
        await loadStatus();
      } else {
        setMsg({ type: 'error', text: verifyRes.detail || 'Clock-in biometrik gagal' });
      }
    } catch (err) {
      const msg = err.message || 'Gagal autentikasi biometrik';
      if (msg.includes('NotAllowed') || msg.includes('cancel')) {
        setMsg({ type: 'warning', text: 'Autentikasi dibatalkan.' });
      } else {
        setMsg({ type: 'error', text: msg });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleWebAuthnClockOut = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const optRes = await api('/api/rahaza/attendance/webauthn/auth/options', {
        method: 'POST', body: JSON.stringify({ employee_id: employee?.id })
      });
      if (optRes.detail) throw new Error(optRes.detail);
      const assertion = await startAuthentication(optRes);
      const verifyRes = await api('/api/rahaza/attendance/webauthn/clock-out', {
        method: 'POST',
        body: JSON.stringify({ ...assertion, employee_id: employee?.id })
      });
      if (verifyRes.ok) {
        setMsg({ type: 'success', text: `Clock-out biometrik berhasil! ${verifyRes.hours_worked ? `(${verifyRes.hours_worked}j)` : ''}` });
        await loadStatus();
      } else {
        setMsg({ type: 'error', text: verifyRes.detail || 'Clock-out biometrik gagal' });
      }
    } catch (err) {
      setMsg({ type: 'error', text: err.message || 'Gagal autentikasi biometrik' });
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterWebAuthn = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const optRes = await api('/api/rahaza/attendance/webauthn/register/options', {
        method: 'POST', body: JSON.stringify({ employee_id: employee?.id })
      });
      if (optRes.detail) throw new Error(optRes.detail);
      const credential = await startRegistration(optRes);
      const verifyRes = await api('/api/rahaza/attendance/webauthn/register/verify', {
        method: 'POST',
        body: JSON.stringify({ ...credential, employee_id: employee?.id, device_name: 'Perangkat ' + new Date().toLocaleDateString('id-ID') })
      });
      if (verifyRes.ok) {
        setMsg({ type: 'success', text: 'Biometrik berhasil didaftarkan! Sekarang Anda bisa absen via fingerprint/Face ID.' });
        setHasWebAuthn(true);
      } else {
        setMsg({ type: 'error', text: verifyRes.detail || 'Gagal mendaftarkan biometrik' });
      }
    } catch (err) {
      const msg = err.message || 'Gagal mendaftarkan biometrik';
      if (msg.includes('NotAllowed') || msg.includes('cancel')) {
        setMsg({ type: 'warning', text: 'Pendaftaran dibatalkan.' });
      } else {
        setMsg({ type: 'error', text: msg });
      }
    } finally {
      setLoading(false);
    }
  };

  if (!bootstrapped) {
    return (
      <div className="dark min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (!auth) return <AbsenLogin onLogin={handleLogin} />;

  const hasClockedIn = status?.clock_in;
  const hasClockedOut = status?.clock_out;
  const today = new Date().toLocaleDateString('id-ID', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  const formatTime = (ts) => {
    if (!ts) return '-';
    try { return new Date(ts).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }); }
    catch { return '-'; }
  };

  return (
    <div className="dark">
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-4 flex flex-col items-center justify-center">
      <div className="w-full max-w-sm space-y-4">

        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-blue-100 dark:bg-blue-500/20 border border-blue-400 dark:border-blue-500/30 mb-3">
            <span className="text-2xl">🕐</span>
          </div>
          <h1 className="text-xl font-bold text-foreground">Portal Absen Karyawan</h1>
          <p className="text-muted-foreground text-xs mt-1">{today}</p>
          {employee && <p className="text-blue-600 dark:text-blue-300 text-sm font-medium mt-1">{employee.name} ({employee.employee_code})</p>}
        </div>

        {/* Today Status Card */}
        <div className="bg-slate-800/60 backdrop-blur border border-slate-700 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-foreground/70 text-sm font-medium">Status Hari Ini</span>
            {status ? <StatusBadge status={status.status} approval={status.approval_status} /> : <span className="text-muted-foreground/60 text-sm">Belum Absen</span>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-700/40 rounded-xl p-3 text-center">
              <div className="text-muted-foreground text-xs mb-1">Masuk</div>
              <div className={`text-lg font-bold ${hasClockedIn ? 'text-green-700 dark:text-green-400' : 'text-muted-foreground/60'}`}>
                {hasClockedIn ? formatTime(status.clock_in) : '--:--'}
              </div>
              {status?.geo_status && <div className={`text-xs mt-1 ${status.geo_status === 'in_range' ? 'text-green-700 dark:text-green-400' : status.geo_status === 'out_of_range' ? 'text-orange-600 dark:text-orange-400' : 'text-muted-foreground/60'}`}>
                {status.geo_status === 'in_range' ? '📍 Dalam Zona' : status.geo_status === 'out_of_range' ? `⚠️ Luar Zona (${status.geo_distance_m}m)` : ''}
              </div>}
            </div>
            <div className="bg-slate-700/40 rounded-xl p-3 text-center">
              <div className="text-muted-foreground text-xs mb-1">Pulang</div>
              <div className={`text-lg font-bold ${hasClockedOut ? 'text-blue-600 dark:text-blue-400' : 'text-muted-foreground/60'}`}>
                {hasClockedOut ? formatTime(status.clock_out) : '--:--'}
              </div>
              {hasClockedOut && status?.hours_worked > 0 && <div className="text-xs text-blue-600 dark:text-blue-300 mt-1">{status.hours_worked}j kerja</div>}
            </div>
          </div>

          {status?.attendance_method && (
            <div className="text-center">
              <span className="text-xs text-muted-foreground/60">
                Metode: {status.attendance_method === 'selfie_geo_ai' ? '📸 Selfie + GPS' : status.attendance_method === 'webauthn' ? '🖐️ Biometrik' : status.attendance_method === 'device_zkteco' ? '🔌 Fingerprint Device' : '📝 Manual HR'}
              </span>
            </div>
          )}
        </div>

        {/* Message */}
        {msg && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${
            msg.type === 'success' ? 'bg-green-100 dark:bg-green-500/10 border-green-400 dark:border-green-500/30 text-green-600 dark:text-green-300' :
            msg.type === 'warning' ? 'bg-yellow-100 dark:bg-yellow-500/10 border-yellow-400 dark:border-yellow-500/30 text-yellow-600 dark:text-yellow-300' :
            'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30 text-red-600 dark:text-red-300'
          }`}>
            {msg.type === 'success' ? '✓ ' : msg.type === 'warning' ? '⚠️ ' : '✗ '}{msg.text}
          </div>
        )}

        {/* Camera for selfie */}
        {showCamera && (
          <div className="bg-slate-800/60 backdrop-blur border border-slate-700 rounded-2xl p-4">
            <SelfieCapture
              onCapture={handleSelfieCapture}
              onCancel={() => setShowCamera(false)}
            />
          </div>
        )}

        {/* Action Buttons */}
        {!showCamera && !hasClockedOut && (
          <div className="space-y-3">
            {/* Method Selector */}
            <div className="bg-slate-800/60 backdrop-blur border border-slate-700 rounded-2xl p-4 space-y-3">
              <p className="text-foreground/70 text-sm font-medium">Pilih Metode Absen</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setMethod('selfie')}
                  className={`py-2.5 rounded-xl text-sm font-medium border transition-colors ${
                    method === 'selfie'
                      ? 'bg-blue-600/30 border-blue-500 text-blue-600 dark:text-blue-300'
                      : 'bg-slate-700/40 border-slate-600 text-foreground/70 hover:border-slate-500'
                  }`}
                >
                  📸 Selfie + GPS
                </button>
                <button
                  onClick={() => setMethod('webauthn')}
                  className={`py-2.5 rounded-xl text-sm font-medium border transition-colors ${
                    method === 'webauthn'
                      ? 'bg-purple-600/30 border-purple-500 text-purple-600 dark:text-purple-300'
                      : 'bg-slate-700/40 border-slate-600 text-foreground/70 hover:border-slate-500'
                  }`}
                >
                  🖐️ Biometrik
                </button>
              </div>
            </div>

            {/* Clock In/Out Buttons */}
            {method === 'selfie' && (
              <div className="space-y-2">
                {!hasClockedIn && (
                  <button
                    onClick={() => { setClockAction('in'); setShowCamera(true); setMsg(null); }}
                    disabled={loading}
                    className="w-full bg-green-600 hover:bg-green-500 disabled:opacity-50 text-foreground font-bold py-4 rounded-2xl text-lg transition-colors flex items-center justify-center gap-2"
                  >
                    📸 Absen Masuk
                  </button>
                )}
                {hasClockedIn && !hasClockedOut && (
                  <button
                    onClick={() => { setClockAction('out'); setShowCamera(true); setMsg(null); }}
                    disabled={loading}
                    className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-foreground font-bold py-4 rounded-2xl text-lg transition-colors flex items-center justify-center gap-2"
                  >
                    📸 Absen Pulang
                  </button>
                )}
              </div>
            )}

            {method === 'webauthn' && (
              <div className="space-y-2">
                {!hasWebAuthn ? (
                  <div className="space-y-2">
                    <div className="bg-yellow-100 dark:bg-yellow-500/10 border border-yellow-300 dark:border-yellow-500/20 text-yellow-600 dark:text-yellow-300 text-xs px-3 py-2 rounded-lg text-center">
                      Biometrik belum didaftarkan untuk perangkat ini
                    </div>
                    <button
                      onClick={handleRegisterWebAuthn}
                      disabled={loading}
                      className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-foreground font-bold py-4 rounded-2xl text-base transition-colors"
                    >
                      {loading ? 'Mendaftarkan...' : '🖐️ Daftarkan Biometrik'}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {!hasClockedIn && (
                      <button
                        onClick={handleWebAuthnClockIn}
                        disabled={loading}
                        className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-foreground font-bold py-4 rounded-2xl text-lg transition-colors"
                      >
                        {loading ? 'Verifikasi...' : '🖐️ Absen Masuk'}
                      </button>
                    )}
                    {hasClockedIn && !hasClockedOut && (
                      <button
                        onClick={handleWebAuthnClockOut}
                        disabled={loading}
                        className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-foreground font-bold py-4 rounded-2xl text-lg transition-colors"
                      >
                        {loading ? 'Verifikasi...' : '🖐️ Absen Pulang'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Already clocked out */}
        {hasClockedOut && (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">✅</div>
            <p className="text-green-600 dark:text-green-300 font-semibold">Absen Hari Ini Selesai!</p>
            <p className="text-muted-foreground text-sm">Terima kasih, sampai besok!</p>
          </div>
        )}

        {/* Logout */}
        <div className="text-center">
          <button
            onClick={() => { localStorage.removeItem('absen_token'); setAuth(null); setStatus(null); setEmployee(null); }}
            className="text-muted-foreground/60 hover:text-muted-foreground text-xs underline"
          >
            Keluar
          </button>
          <span className="text-muted-foreground/50 mx-2">·</span>
          <a href="/" className="text-muted-foreground/60 hover:text-muted-foreground text-xs underline">Portal Utama</a>
        </div>
      </div>
    </div>
    </div>
  );
}
