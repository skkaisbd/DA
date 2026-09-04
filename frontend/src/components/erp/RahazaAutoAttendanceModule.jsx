/**
 * RahazaAutoAttendanceModule — Manajemen Absen Otomatis (HR Admin View)
 * 
 * Tab 1: Konfigurasi (geofence, face threshold, office location)
 * Tab 2: Biometrik Devices (WebAuthn per karyawan)
 * Tab 3: Device Fingerprint Fisik (ZKTeco/Fingerspot)
 * Tab 4: Live Feed Absen Otomatis
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function RahazaAutoAttendanceModule({ token }) {
  const [activeTab, setActiveTab] = useState('config');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <span>PORTAL SDM</span><span>›</span><span>KEHADIRAN</span>
        </div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <span>🤖</span> Absen Otomatis
        </h2>
        <p className="text-muted-foreground text-sm mt-1">Kelola metode absen otomatis: Selfie+AI, Biometrik WebAuthn, dan Device Fingerprint Fisik</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-muted/40 p-1 rounded-xl w-fit flex-wrap">
        {[
          { id: 'config', label: '⚙️ Konfigurasi' },
          { id: 'webauthn', label: '🖐️ Biometrik' },
          { id: 'device', label: '🔌 Device Fisik' },
          { id: 'live', label: '📋 Live Feed' },
        ].map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === t.id ? 'bg-white shadow text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'config' && <ConfigTab headers={headers} token={token} />}
      {activeTab === 'webauthn' && <WebAuthnTab headers={headers} token={token} />}
      {activeTab === 'device' && <DeviceTab headers={headers} token={token} />}
      {activeTab === 'live' && <LiveFeedTab headers={headers} token={token} />}
    </div>
  );
}

// ─── Tab 1: Konfigurasi ────────────────────────────────────────────────────────
// FASE 16 — dua bug nyata diperbaiki di sini:
//  1. Kolom Latitude/Longitude MEMBACA `office_lat`/`office_lng` tapi MENULIS
//     `lat`/`lng` ⇒ angka yang diketik tidak pernah tampil (kolom terasa beku)
//     dan HR mengira fitur geofence rusak.
//  2. Tidak ada cara praktis mengisi koordinat → sekarang ada tombol
//     "Pakai lokasi saya sekarang" (navigator.geolocation) + tautan Google Maps.
// Ditambah: sakelar KEBIJAKAN WAJIB (selfie & lokasi) sesuai keputusan user.
function ConfigTab({ headers }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${BACKEND}/api/rahaza/attendance/auto-config`, { headers });
      setConfig(r.data); setForm(r.data);
    } catch (e) { console.error(e); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const setField = (patch) => setForm(f => ({ ...f, ...patch }));

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setMsg({ type: 'error', text: 'Browser ini tidak mendukung deteksi lokasi.' });
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setField({
          office_lat: Number(p.coords.latitude.toFixed(6)),
          office_lng: Number(p.coords.longitude.toFixed(6)),
        });
        setMsg({ type: 'success', text: `Koordinat terisi dari lokasi Anda (akurasi ±${Math.round(p.coords.accuracy)} m). Jangan lupa Simpan.` });
        setLocating(false);
      },
      (err) => {
        setMsg({ type: 'error', text: `Gagal membaca lokasi: ${err.message}. Isi manual dari Google Maps.` });
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      await axios.put(`${BACKEND}/api/rahaza/attendance/auto-config`, {
        office_name: form.office_name,
        geofence_radius_m: form.geofence_radius_m,
        office_lat: form.office_lat,
        office_lng: form.office_lng,
        require_selfie: form.require_selfie !== false,
        require_geofence: form.require_geofence !== false,
        face_match_threshold: form.face_match_threshold,
      }, { headers });
      setMsg({ type: 'success', text: 'Konfigurasi berhasil disimpan.' });
      await load();
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || 'Gagal menyimpan' });
    } finally { setSaving(false); }
  };

  if (!config) return <div className="text-center py-10"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-primary mx-auto" /></div>;

  const notConfigured = form.office_lat == null || form.office_lng == null;

  return (
    <div className="space-y-4 max-w-2xl" data-testid="attendance-config-tab">
      {msg && (
        <div data-testid="attendance-config-msg"
          className={`rounded-lg px-4 py-3 text-sm ${msg.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {msg.text}
        </div>
      )}

      {notConfigured && form.require_geofence !== false && (
        <div data-testid="attendance-config-warning"
          className="rounded-lg px-4 py-3 text-sm bg-amber-50 text-amber-800 border border-amber-300">
          ⚠️ Koordinat kantor belum diisi, padahal verifikasi lokasi diwajibkan.
          <strong> Selama ini kosong, karyawan TIDAK BISA absen</strong> (mereka akan melihat pesan
          &quot;Lokasi kantor belum diatur&quot;). Tekan &quot;Pakai lokasi saya sekarang&quot; saat Anda berada di kantor.
        </div>
      )}

      <div className="bg-card border rounded-xl p-5 space-y-5">
        <h3 className="font-semibold flex items-center gap-2">📍 Geofence (Zona Kantor)</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted-foreground block mb-1" htmlFor="cfg-office-name">Nama Kantor</label>
            <input id="cfg-office-name" data-testid="cfg-office-name" type="text" value={form.office_name || ''}
              onChange={e => setField({ office_name: e.target.value })}
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1" htmlFor="cfg-radius">Radius (meter)</label>
            <input id="cfg-radius" data-testid="cfg-radius" type="number" value={form.geofence_radius_m ?? 300} min={10} max={20000}
              onChange={e => setField({ geofence_radius_m: parseInt(e.target.value, 10) })}
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1" htmlFor="cfg-lat">Latitude Kantor</label>
            <input id="cfg-lat" data-testid="cfg-lat" type="number" step="any"
              value={form.office_lat ?? ''} placeholder="-6.2088"
              onChange={e => setField({ office_lat: e.target.value === '' ? null : parseFloat(e.target.value) })}
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1" htmlFor="cfg-lng">Longitude Kantor</label>
            <input id="cfg-lng" data-testid="cfg-lng" type="number" step="any"
              value={form.office_lng ?? ''} placeholder="106.8456"
              onChange={e => setField({ office_lng: e.target.value === '' ? null : parseFloat(e.target.value) })}
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={useMyLocation} disabled={locating}
            data-testid="cfg-use-my-location"
            className="border rounded-lg px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50">
            {locating ? '⏳ Membaca lokasi…' : '📍 Pakai lokasi saya sekarang'}
          </button>
          {form.office_lat != null && form.office_lng != null && (
            <a className="text-xs text-primary underline" target="_blank" rel="noreferrer"
              href={`https://www.google.com/maps?q=${form.office_lat},${form.office_lng}`}>
              Lihat titik ini di Google Maps
            </a>
          )}
        </div>

        <div className="border-t pt-4 space-y-3">
          <h4 className="font-semibold text-sm">Kebijakan Absen (berlaku untuk semua karyawan)</h4>
          <label className="flex items-start gap-3 text-sm cursor-pointer">
            <input type="checkbox" data-testid="cfg-require-selfie" className="w-4 h-4 mt-0.5"
              checked={form.require_selfie !== false}
              onChange={e => setField({ require_selfie: e.target.checked })} />
            <span>
              <strong>Selfie wajib</strong>
              <span className="block text-xs text-muted-foreground">Absen tanpa foto akan ditolak. Foto disimpan sebagai bukti dan bisa dibuka HR.</span>
            </span>
          </label>
          <label className="flex items-start gap-3 text-sm cursor-pointer">
            <input type="checkbox" data-testid="cfg-require-geofence" className="w-4 h-4 mt-0.5"
              checked={form.require_geofence !== false}
              onChange={e => setField({ require_geofence: e.target.checked })} />
            <span>
              <strong>Lokasi wajib (di dalam radius kantor)</strong>
              <span className="block text-xs text-muted-foreground">Absen di luar radius ditolak, bukan sekadar &quot;menunggu approval&quot;.</span>
            </span>
          </label>
        </div>

        <div className="bg-blue-50 border border-blue-200 text-blue-700 text-xs px-3 py-2 rounded-lg">
          💡 Alternatif: buka Google Maps → klik-kanan titik kantor → salin angka lat/lng ke kolom di atas.
        </div>
      </div>

      <div className="bg-card border rounded-xl p-5 space-y-4">
        <h3 className="font-semibold flex items-center gap-2">🤖 AI Face Recognition</h3>
        <div>
          <label className="text-sm font-medium block mb-2">
            Minimum Confidence Wajah: <span className="text-primary font-bold">{Math.round((form.face_match_threshold || 0.65) * 100)}%</span>
          </label>
          <input
            type="range" min={0} max={100} step={5}
            value={Math.round((form.face_match_threshold || 0.65) * 100)}
            onChange={e => setForm({...form, face_match_threshold: parseInt(e.target.value) / 100})}
            className="w-full accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>0% (Tidak ketat)</span>
            <span>100% (Sangat ketat)</span>
          </div>
        </div>
        <div className="bg-muted/40 rounded-lg px-3 py-2 text-xs text-muted-foreground">
          Selfie dengan confidence di bawah threshold ini akan masuk approval queue HR. Rekomendasi: 60-70%.
        </div>
      </div>

      <button onClick={save} disabled={saving} data-testid="cfg-save"
        className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 px-6 py-2.5 rounded-xl font-semibold text-sm transition-colors">
        {saving ? 'Menyimpan...' : '💾 Simpan Konfigurasi'}
      </button>
    </div>
  );
}

// ─── Tab 2: WebAuthn Biometrik ────────────────────────────────────────────────
function WebAuthnTab({ headers }) {
  const [devices, setDevices] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(false);
  const [revoking, setRevoking] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, e] = await Promise.all([
        axios.get(`${BACKEND}/api/rahaza/attendance/webauthn/devices`, { headers }),
        axios.get(`${BACKEND}/api/rahaza/employees`, { headers }),
      ]);
      setDevices(d.data || []);
      setEmployees(Array.isArray(e.data) ? e.data : (e.data?.items || e.data?.rows || e.data?.data || []));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const revoke = async (id) => {
    if (!window.confirm('Cabut credential biometrik ini?')) return;
    setRevoking(id);
    try {
      await axios.delete(`${BACKEND}/api/rahaza/attendance/webauthn/devices/${id}`, { headers });
      setMsg({ type: 'success', text: 'Credential dicabut.' });
      await load();
    } catch (e) { setMsg({ type: 'error', text: 'Gagal mencabut credential.' }); }
    finally { setRevoking(null); }
  };

  const empMap = Object.fromEntries(employees.map(e => [e.id, e]));

  const fmtDate = (d) => { if (!d) return '-'; try { return new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }); } catch { return d; } };

  const { page, setPage, totalPages, total, paged } = useClientPagination(devices, 10);
  return (
    <div className="space-y-4">
      {msg && (
        <div className={`rounded-lg px-4 py-3 text-sm ${msg.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {msg.text} <button onClick={() => setMsg(null)} className="ml-2 opacity-60">✕</button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Credential Biometrik Terdaftar</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Fingerprint/Face ID/Touch ID per karyawan. Karyawan dapat mendaftarkan di <code className="bg-muted px-1 rounded">/absen</code></p>
        </div>
        <button onClick={load} className="text-sm text-primary hover:underline">🔄 Refresh</button>
      </div>

      {loading ? (
        <div className="text-center py-10"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-primary mx-auto" /></div>
      ) : devices.length === 0 ? (
        <div className="bg-muted/30 rounded-xl p-8 text-center text-muted-foreground">
          <div className="text-4xl mb-3">🖐️</div>
          <p className="font-medium">Belum ada biometrik terdaftar</p>
          <p className="text-sm mt-1">Karyawan dapat mendaftarkan fingerprint/Face ID di halaman <strong>/absen</strong></p>
        </div>
      ) : (
        <div className="bg-card border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/20">
              <tr>
                <th className="px-4 py-3 text-left text-muted-foreground font-medium">Karyawan</th>
                <th className="px-4 py-3 text-left text-muted-foreground font-medium">Nama Device</th>
                <th className="px-4 py-3 text-left text-muted-foreground font-medium">Terdaftar</th>
                <th className="px-4 py-3 text-left text-muted-foreground font-medium">Terakhir Dipakai</th>
                <th className="px-4 py-3 text-left text-muted-foreground font-medium">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {paged.map(d => {
                const emp = empMap[d.employee_id] || {};
                return (
                  <tr key={d.id} className="border-b hover:bg-muted/20">
                    <td className="px-4 py-3">
                      <div className="font-medium">{emp.name || d.employee_id}</div>
                      <div className="text-xs text-muted-foreground">{emp.employee_code || '-'}</div>
                    </td>
                    <td className="px-4 py-3">{d.device_name || 'Device'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(d.created_at)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(d.last_used_at)}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => revoke(d.id)} disabled={revoking === d.id}
                        className="text-xs bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 px-2.5 py-1 rounded-lg transition-colors disabled:opacity-50">
                        {revoking === d.id ? '...' : 'Cabut'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}
    </div>
  );
}

// ─── Tab 3: ZKTeco Device ──────────────────────────────────────────────────────
function DeviceTab({ headers }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', ip: '', port: 4370, password: 0, timezone: 8, enabled: true });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [syncResults, setSyncResults] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND}/api/rahaza/devices/zkteco`, { headers });
      setDevices(r.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const saveDevice = async () => {
    if (!form.name || !form.ip) { setMsg({ type: 'error', text: 'Nama dan IP wajib diisi.' }); return; }
    setSaving(true);
    try {
      await axios.post(`${BACKEND}/api/rahaza/devices/zkteco`, form, { headers });
      setMsg({ type: 'success', text: 'Device berhasil ditambahkan.' });
      setShowForm(false);
      setForm({ name: '', ip: '', port: 4370, password: 0, timezone: 8, enabled: true });
      await load();
    } catch (e) { setMsg({ type: 'error', text: e.response?.data?.detail || 'Gagal menyimpan' }); }
    finally { setSaving(false); }
  };

  const deleteDevice = async (id) => {
    if (!window.confirm('Hapus device ini?')) return;
    try {
      await axios.delete(`${BACKEND}/api/rahaza/devices/zkteco/${id}`, { headers });
      await load();
    } catch (e) { setMsg({ type: 'error', text: 'Gagal menghapus' }); }
  };

  const syncDevice = async (id, simulator = false) => {
    setSyncing(id); setSyncResults(prev => ({...prev, [id]: null}));
    try {
      const r = await axios.post(`${BACKEND}/api/rahaza/devices/zkteco/${id}/sync`, { simulator }, { headers });
      setSyncResults(prev => ({...prev, [id]: { ok: true, data: r.data }}));
      await load();
    } catch (e) {
      const err = e.response?.data?.detail || 'Gagal sync';
      setSyncResults(prev => ({...prev, [id]: { ok: false, error: err }}));
    } finally { setSyncing(null); }
  };

  return (
    <div className="space-y-4">
      {msg && (
        <div className={`rounded-lg px-4 py-3 text-sm ${msg.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {msg.text} <button onClick={() => setMsg(null)} className="ml-2 opacity-60">✕</button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Device Fingerprint Fisik (ZKTeco/Fingerspot)</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Konfigurasi mesin absen fingerprint untuk sinkronisasi data</p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-xl text-sm font-medium transition-colors">
          + Tambah Device
        </button>
      </div>

      {/* Add Form */}
      {showForm && (
        <div className="bg-card border rounded-xl p-5 space-y-4">
          <h4 className="font-medium">Tambah Device Baru</h4>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Nama Device *</label>
              <input type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                placeholder="Mesin Absen Lantai 1"
                className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">IP Address *</label>
              <input type="text" value={form.ip} onChange={e => setForm({...form, ip: e.target.value})}
                placeholder="192.168.1.100"
                className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Port</label>
              <input type="number" value={form.port} onChange={e => setForm({...form, port: parseInt(e.target.value)})}
                className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Password Device</label>
              <input type="number" value={form.password} onChange={e => setForm({...form, password: parseInt(e.target.value)})}
                placeholder="0 jika tidak ada"
                className="w-full border rounded-lg px-3 py-2 text-sm bg-background" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm text-muted-foreground">Aktif?</label>
            <input type="checkbox" checked={form.enabled}
              onChange={e => setForm({...form, enabled: e.target.checked})} className="w-4 h-4" />
          </div>
          <div className="bg-amber-50 border border-amber-200 text-amber-700 text-xs px-3 py-2 rounded-lg">
            ⚠️ Device harus terhubung ke jaringan yang sama. Untuk testing tanpa hardware, gunakan mode Simulator.
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-xl text-sm hover:bg-muted/20">Batal</button>
            <button onClick={saveDevice} disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 px-4 py-2 rounded-xl text-sm font-semibold">
              {saving ? 'Menyimpan...' : 'Simpan'}
            </button>
          </div>
        </div>
      )}

      {/* Device List */}
      {loading ? (
        <div className="text-center py-10"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-primary mx-auto" /></div>
      ) : devices.length === 0 ? (
        <div className="bg-muted/30 rounded-xl p-8 text-center text-muted-foreground">
          <div className="text-4xl mb-3">🔌</div>
          <p className="font-medium">Belum ada device dikonfigurasi</p>
          <p className="text-sm mt-1">Tambah device ZKTeco/Fingerspot untuk sync data absen</p>
        </div>
      ) : (
        <div className="space-y-3">
          {devices.map(d => (
            <div key={d.id} className="bg-card border rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${d.enabled ? 'bg-green-400' : 'bg-muted'}`} />
                  <div>
                    <div className="font-semibold">{d.name}</div>
                    <div className="text-xs text-muted-foreground">{d.ip}:{d.port} {d.password ? '(pwd protected)' : ''}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => syncDevice(d.id, true)} disabled={syncing === d.id}
                    className="text-xs bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50">
                    {syncing === d.id ? '⏳' : '🧪'} Simulator
                  </button>
                  <button onClick={() => syncDevice(d.id, false)} disabled={syncing === d.id}
                    className="text-xs bg-green-50 hover:bg-green-100 text-green-600 border border-green-200 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50">
                    {syncing === d.id ? '⏳ Syncing...' : '🔄 Sync'}
                  </button>
                  <button onClick={() => deleteDevice(d.id)}
                    className="text-xs bg-red-50 hover:bg-red-100 text-red-500 border border-red-200 px-2.5 py-1.5 rounded-lg transition-colors">
                    🗑️
                  </button>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div className="bg-muted/30 rounded-lg p-2 text-center">
                  <div className="text-muted-foreground">Last Sync</div>
                  <div className="font-medium">{d.last_sync_at ? new Date(d.last_sync_at).toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'Belum pernah'}</div>
                </div>
                <div className="bg-muted/30 rounded-lg p-2 text-center">
                  <div className="text-muted-foreground">Records Terakhir</div>
                  <div className="font-medium">{d.last_sync_records || 0}</div>
                </div>
                <div className="bg-muted/30 rounded-lg p-2 text-center">
                  <div className="text-muted-foreground">Status</div>
                  <div className={`font-medium ${
                    d.last_sync_status === 'success' || d.last_sync_status === 'success_simulator' ? 'text-green-600' :
                    d.last_sync_status === 'error' ? 'text-red-500' : 'text-muted-foreground'
                  }`}>
                    {d.last_sync_status === 'success' ? '✓ OK' : d.last_sync_status === 'success_simulator' ? '🧪 Sim' : d.last_sync_status === 'error' ? '✗ Error' : '-'}
                  </div>
                </div>
              </div>

              {d.last_error && (
                <div className="mt-2 bg-red-50 border border-red-200 text-red-600 text-xs px-3 py-2 rounded-lg">
                  ✗ {d.last_error}
                </div>
              )}

              {syncResults[d.id] && (
                <div className={`mt-2 text-xs px-3 py-2 rounded-lg border ${
                  syncResults[d.id].ok
                    ? 'bg-green-50 border-green-200 text-green-700'
                    : 'bg-red-50 border-red-200 text-red-600'
                }`}>
                  {syncResults[d.id].ok
                    ? `✓ ${syncResults[d.id].data?.message || 'Sync berhasil'} (${syncResults[d.id].data?.synced || 0} records)`
                    : `✗ ${syncResults[d.id].error}`}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Tab 4: Live Feed ──────────────────────────────────────────────────────────
function LiveFeedTab({ headers }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [methodFilter, setMethodFilter] = useState('auto');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const params = new URLSearchParams({ status: 'all', from_date: today, to_date: today });
      const r = await axios.get(`${BACKEND}/api/rahaza/attendance/approvals?${params}`, { headers });
      let data = r.data || [];
      if (methodFilter === 'auto') {
        data = data.filter(r => r.attendance_method && r.attendance_method !== 'manual' && r.source !== 'supervisor');
      }
      setRecords(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [methodFilter, headers]);

  useEffect(() => { load(); }, [load]);

  const fmtTime = (ts) => { try { return new Date(ts).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }); } catch { return '-'; } };

  const methodLabel = {
    selfie_geo_ai: '📸 Selfie+AI',
    webauthn: '🖐️ Biometrik',
    device_zkteco: '🔌 Device',
    manual: '📝 Manual',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Live Feed Absen Hari Ini</h3>
          <p className="text-xs text-muted-foreground">{new Date().toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={methodFilter} onChange={e => setMethodFilter(e.target.value)}
            className="border rounded-lg px-2.5 py-1.5 text-sm bg-background">
            <option value="auto">Hanya Absen Otomatis</option>
            <option value="all">Semua Metode</option>
          </select>
          <button onClick={load} className="bg-primary/10 hover:bg-primary/20 text-primary px-3 py-1.5 rounded-lg text-sm">🔄</button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-10"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-primary mx-auto" /></div>
      ) : records.length === 0 ? (
        <div className="bg-muted/30 rounded-xl p-8 text-center text-muted-foreground">
          <div className="text-4xl mb-3">📋</div>
          <p>Belum ada absen otomatis hari ini</p>
        </div>
      ) : (
        <div className="space-y-2">
          {records.map(r => (
            <div key={r.id} className="bg-card border rounded-xl px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="text-xl">
                  {r.attendance_method === 'selfie_geo_ai' ? '📸' :
                   r.attendance_method === 'webauthn' ? '🖐️' :
                   r.attendance_method === 'device_zkteco' ? '🔌' : '📝'}
                </div>
                <div>
                  <div className="font-medium text-sm">{r.employee_name || r.employee_id}</div>
                  <div className="text-xs text-muted-foreground">
                    {methodLabel[r.attendance_method] || 'Manual'} ·
                    {r.geo_status === 'in_range' ? ' 📍 Dalam Zona' : r.geo_status === 'out_of_range' ? ' ⚠️ Luar Zona' : ''}
                    {r.face_match_status === 'checked' ? ` · 🤖 ${Math.round((r.face_match_score || 0) * 100)}%` : ''}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-green-600">{fmtTime(r.clock_in)}</div>
                {r.clock_out && <div className="text-orange-500 text-xs">{fmtTime(r.clock_out)}</div>}
                <div className={`text-xs mt-0.5 ${
                  r.approval_status === 'auto_approved' || r.approval_status === 'approved' ? 'text-green-600' :
                  r.approval_status === 'pending' ? 'text-yellow-600' : 'text-red-500'
                }`}>
                  {r.approval_status === 'auto_approved' ? '✓ Auto' :
                   r.approval_status === 'approved' ? '✓ Disetujui' :
                   r.approval_status === 'pending' ? '⏳ Pending' : '✗ Ditolak'}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
