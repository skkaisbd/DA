/**
 * Karantina QC — Portal Gudang (FASE 6 / INV-8)
 *
 * Barang yang DITOLAK QC tidak lagi hilang tanpa jejak: qty reject masuk ke
 * lokasi KARANTINA (stok fisik tercatat tapi DIBLOKIR — tidak bisa dipakai
 * produksi/penjualan), lalu ditindaklanjuti lewat 3 disposisi:
 *   • Lepas ke Stok      → lolos re-inspeksi / setelah rework
 *   • Retur ke Supplier  → dikembalikan ke pemasok
 *   • Scrap (Buang)      → write-off (jurnal kerugian bila barang sudah bernilai)
 *
 * Sumber data: /api/wms/quarantine (+ /summary, /location, /reject-categories)
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  ShieldAlert, RefreshCw, Search, X, PackageCheck, Undo2, Trash2,
  AlertTriangle, Clock, Boxes, Banknote, Info, CheckCircle2, PackagePlus,
  ShieldOff, Lock,
} from 'lucide-react';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';

const API = process.env.REACT_APP_BACKEND_URL || '';

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID');
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const fmtDate = (iso) => {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return String(iso).slice(0, 16); }
};

const SOURCE_LABEL = {
  goods_receipt: 'Penerimaan (GR)',
  grn_inspection: 'Re-inspeksi QC',
  manual: 'Temuan Gudang',
};

function Stat({ icon: Icon, label, value, hint, tone = 'violet' }) {
  const tones = {
    violet: 'text-violet-600 dark:text-violet-400 bg-violet-500/5 border-violet-500/20',
    amber: 'text-amber-700 dark:text-amber-400 bg-amber-500/5 border-amber-500/20',
    red: 'text-red-700 dark:text-red-400 bg-red-500/5 border-red-500/20',
    emerald: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/5 border-emerald-500/20',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className="text-2xl font-bold leading-tight">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

function ActionModal({ item, action, locations, quarantineLoc, onClose, onSubmit }) {
  const CONF = {
    release: {
      title: 'Lepas ke Stok', color: 'bg-emerald-600',
      desc: 'Barang lolos re-inspeksi / sudah di-rework. Stok akan kembali TERSEDIA di lokasi tujuan.',
      needLoc: true,
    },
    return_supplier: {
      title: 'Retur ke Supplier', color: 'bg-sky-600',
      desc: 'Barang dikeluarkan dari gudang untuk dikembalikan ke pemasok.',
      needLoc: false,
    },
    scrap: {
      title: 'Scrap (Buang)', color: 'bg-red-600',
      desc: 'Barang dibuang. Bila barang sudah masuk nilai persediaan, jurnal kerugian (write-off) akan di-posting otomatis.',
      needLoc: false,
    },
  }[action];

  const [qty, setQty] = useState(item.remaining_qty);
  const [toLoc, setToLoc] = useState((locations[0] && locations[0].id) || '');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    const q = parseFloat(qty);
    if (!q || q <= 0) { setErr('Qty harus lebih dari 0'); return; }
    if (q > Number(item.remaining_qty) + 1e-6) { setErr(`Qty melebihi sisa karantina (${fmtNum(item.remaining_qty)})`); return; }
    if (CONF.needLoc && !toLoc) { setErr('Pilih lokasi tujuan'); return; }
    setBusy(true); setErr('');
    try {
      await onSubmit({ qty: q, to_location_id: CONF.needLoc ? toLoc : undefined, notes });
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-foreground/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold">{CONF.title}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{item.material_code} · {item.material_name}</p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-foreground/5 rounded"><X className="w-4 h-4" /></button>
        </div>

        <div className="text-xs bg-[var(--glass-bg)] border border-border rounded-lg px-3 py-2 mb-3 text-muted-foreground">
          {CONF.desc}
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Qty ({item.unit}) — sisa karantina {fmtNum(item.remaining_qty)}
            </label>
            <input type="number" min="0" step="0.01" value={qty} onChange={(e) => setQty(e.target.value)}
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
              data-testid="quarantine-action-qty" />
          </div>

          {CONF.needLoc && (
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Lokasi Tujuan</label>
              <SmartNativeSelect value={toLoc} onChange={(e) => setToLoc(e.target.value)}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                data-testid="quarantine-action-location">
                {locations.map((l) => <option key={l.id} value={l.id}>{l.name || l.code}</option>)}
              </SmartNativeSelect>
              <p className="text-[11px] text-muted-foreground mt-1">
                Lokasi karantina ({quarantineLoc?.name || 'Area Karantina QC'}) tidak bisa dipilih sebagai tujuan.
              </p>
            </div>
          )}

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Catatan</label>
            <textarea rows="2" value={notes} onChange={(e) => setNotes(e.target.value)}
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
              placeholder="Alasan / keterangan tindak lanjut..." data-testid="quarantine-action-notes" />
          </div>

          {!item.valued && action !== 'release' && (
            <div className="text-[11px] text-muted-foreground bg-[var(--glass-bg)] border border-border rounded-lg px-3 py-2">
              <Info className="w-3 h-3 inline mr-1" />
              Barang ini <strong>belum masuk nilai persediaan</strong> (reject saat penerimaan tidak ditagihkan supplier),
              jadi tidak ada jurnal keuangan yang dibuat.
            </div>
          )}
          {!item.valued && action === 'release' && (
            <div className="text-[11px] text-muted-foreground bg-[var(--glass-bg)] border border-border rounded-lg px-3 py-2">
              <Info className="w-3 h-3 inline mr-1" />
              Barang akan <strong>dikapitalisasi</strong> ke nilai persediaan (jurnal penyesuaian otomatis).
            </div>
          )}

          {err && <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-3 py-2">{err}</div>}
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
          <button onClick={submit} disabled={busy}
            className={`px-4 py-2 ${CONF.color} text-white rounded-lg text-sm hover:brightness-110 disabled:opacity-50`}
            data-testid="quarantine-action-submit">
            {busy ? 'Memproses...' : CONF.title}
          </button>
        </div>
      </div>
    </div>
  );
}

function ManualModal({ token, locations, onClose, onSaved }) {
  const [materials, setMaterials] = useState([]);
  const [reasons, setReasons] = useState([]);
  const [form, setForm] = useState({ material_id: '', qty: '', from_location_id: (locations[0] && locations[0].id) || '', reason_code: '', notes: '', unit: 'pcs' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const m = await api('GET', '/api/rahaza/materials?limit=500', token);
        setMaterials(Array.isArray(m) ? m : (m.items || []));
      } catch { /* noop */ }
      try { setReasons(await api('GET', '/api/wms/quarantine/reject-categories', token)); } catch { /* noop */ }
    })();
  }, [token]);

  const save = async () => {
    if (!form.material_id || !form.qty || !form.from_location_id) { setErr('Material, qty, dan lokasi asal wajib diisi'); return; }
    setBusy(true); setErr('');
    try {
      const mat = materials.find((m) => m.id === form.material_id);
      await api('POST', '/api/wms/quarantine/manual', token, { ...form, qty: parseFloat(form.qty), unit: mat?.unit || 'pcs' });
      onSaved();
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-foreground/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold mb-1">Karantina Manual</h3>
        <p className="text-xs text-muted-foreground mb-4">Pindahkan stok yang sudah ada di gudang ke Karantina QC (mis. ditemukan rusak saat penyimpanan).</p>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Material *</label>
            <SmartNativeSelect value={form.material_id} onChange={(e) => setForm({ ...form, material_id: e.target.value })}
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quarantine-manual-material">
              <option value="">— pilih material —</option>
              {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Qty *</label>
              <input type="number" min="0" step="0.01" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quarantine-manual-qty" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Lokasi Asal *</label>
              <SmartNativeSelect value={form.from_location_id} onChange={(e) => setForm({ ...form, from_location_id: e.target.value })}
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quarantine-manual-location">
                {locations.map((l) => <option key={l.id} value={l.id}>{l.name || l.code}</option>)}
              </SmartNativeSelect>
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Alasan</label>
            <SmartNativeSelect value={form.reason_code} onChange={(e) => setForm({ ...form, reason_code: e.target.value })}
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quarantine-manual-reason">
              <option value="">— pilih alasan —</option>
              {reasons.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
            </SmartNativeSelect>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Catatan</label>
            <textarea rows="2" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]" data-testid="quarantine-manual-notes" />
          </div>
          {err && <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-3 py-2">{err}</div>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
          <button onClick={save} disabled={busy} className="px-4 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50"
            data-testid="quarantine-manual-submit">
            {busy ? 'Menyimpan...' : 'Karantina'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function QuarantineModule({ token: tokenProp }) {
  const token = tokenProp || localStorage.getItem('token') || '';
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [locInfo, setLocInfo] = useState(null);
  const [status, setStatus] = useState('open');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [modal, setModal] = useState(null);     // {item, action}
  const [showManual, setShowManual] = useState(false);
  const [toast, setToast] = useState('');
  // "Perlu Tindakan Manual" = hanya item yang ketersediaannya BELUM terblokir,
  // yaitu barang reject yang MASIH terhitung tersedia dan bisa ikut dipakai
  // produksi / terkirim ke pembeli. Dulu kegagalan blokir hanya tercatat di log
  // server, jadi tak ada satu pun layar yang bisa menunjukkannya.
  const [needsAction, setNeedsAction] = useState(false);
  const [retrying, setRetrying] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [list, sm] = await Promise.all([
        api('GET', `/api/wms/quarantine?status=${status}${needsAction ? '&needs_action=true' : ''}`, token),
        api('GET', '/api/wms/quarantine/summary', token),
      ]);
      setItems(Array.isArray(list) ? list : []);
      setSummary(sm || null);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, [token, status, needsAction]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    (async () => {
      try { setLocInfo(await api('GET', '/api/wms/quarantine/location', token)); }
      catch { /* noop */ }
    })();
  }, [token]);

  const storageLocs = useMemo(() => (locInfo?.storage_locations || []), [locInfo]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => `${it.material_code} ${it.material_name} ${it.source?.number || ''} ${it.source?.supplier_name || ''}`.toLowerCase().includes(q));
  }, [items, search]);
  const pg = useClientPagination(filtered, 10);

  const doAction = async (payload) => {
    const { item, action } = modal;
    const path = action === 'release' ? 'release' : (action === 'return_supplier' ? 'return-supplier' : 'scrap');
    const res = await api('POST', `/api/wms/quarantine/${item.id}/${path}`, token, payload);
    setModal(null);
    const p = res.posting || {};
    const jeMsg = p.je_number ? ` · jurnal ${p.je_number} di-posting`
      : (p.skipped ? ' · tanpa jurnal keuangan' : (p.ok === false ? ` · jurnal GAGAL: ${p.error || ''}` : ''));
    setToast(`${action === 'release' ? 'Dilepas ke stok' : action === 'return_supplier' ? 'Diretur ke supplier' : 'Di-scrap'} ${fmtNum(payload.qty)} ${item.unit}${jeMsg}`);
    load();
    setTimeout(() => setToast(''), 6000);
  };

  // Coba blokir ulang ketersediaan — supaya daftar "Perlu Tindakan Manual" bisa
  // DITINDAK dari layar, bukan hanya diberitahukan (dulu harus lewat database).
  const retryBlock = async (it) => {
    setRetrying(it.id); setErr('');
    try {
      const res = await api('POST', `/api/wms/quarantine/${it.id}/retry-block`, token);
      setToast(res.pesan || 'Blokir ketersediaan berhasil dipasang ulang.');
      await load();
      setTimeout(() => setToast(''), 6000);
    } catch (e) { setErr(e.message); }
    finally { setRetrying(''); }
  };

  const unblockedCount = Number(summary?.unblocked_items || 0);
  const unblockedQty = Number(summary?.unblocked_qty || 0);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400" /> Karantina QC
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Barang <strong>reject QC</strong> ditahan di sini — stok tercatat tapi <strong>diblokir</strong> (tidak bisa dipakai produksi/penjualan)
            sampai ada keputusan: lepas ke stok, retur supplier, atau scrap.
          </p>
          {locInfo && (
            <p className="text-xs text-muted-foreground mt-1">
              Lokasi: <span className="font-mono">{locInfo.code}</span> · {locInfo.name}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowManual(true)}
            className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5"
            data-testid="quarantine-manual-btn">
            <PackagePlus className="w-4 h-4" /> Karantina Manual
          </button>
          <button onClick={load} className="p-2 border border-border rounded-lg hover:bg-foreground/5" data-testid="quarantine-refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {toast && (
        <div className="text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-2 flex items-center gap-2"
          data-testid="quarantine-toast">
          <CheckCircle2 className="w-4 h-4" /> {toast}
        </div>
      )}

      {/* PERINGATAN MERAH — barang reject yang ketersediaannya BELUM terblokir.
          Ini keadaan paling berbahaya di modul ini: barang cacat masih terhitung
          TERSEDIA (`available = qty − reserved`), jadi bisa ikut dipilih untuk
          produksi atau DIKIRIM KE PEMBELI. Penanda `quarantine/blocked` pada baris
          stok hanya menyembunyikannya dari dropdown, tidak menghalangi perhitungan. */}
      {unblockedCount > 0 && (
        <div className="rounded-xl border-2 border-red-500 bg-red-100 dark:bg-red-500/15 px-4 py-3"
          data-testid="quarantine-unblocked-banner">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <ShieldOff className="w-6 h-6 text-red-700 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold text-red-800 dark:text-red-300">
                  Ketersediaan BELUM terblokir — {fmtNum(unblockedCount)} item karantina ({fmtNum(unblockedQty)} unit)
                </div>
                <p className="text-sm text-red-800/90 dark:text-red-300/90 mt-1 max-w-3xl">
                  Barang <strong>REJECT</strong> ini masih terhitung sebagai stok <strong>TERSEDIA</strong>, sehingga
                  bisa ikut dipilih untuk produksi atau <strong>terkirim ke pembeli</strong>. Perlu tindakan manual:
                  tekan <em>Coba Blokir Ulang</em> pada barisnya. Bila tetap gagal, stok fisik di lokasi karantina
                  kemungkinan lebih kecil dari qty karantina — lakukan opname/koreksi stok dulu.
                </p>
                {(summary?.unblocked_groups || []).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {(summary.unblocked_groups || []).map((g) => (
                      <span key={`${g.material_id}-${g.location_id}`}
                        className="px-2 py-0.5 rounded-full text-xs bg-red-200 dark:bg-red-500/20 text-red-900 dark:text-red-200 font-mono">
                        {g.material_code || g.material_id} · belum terblokir {fmtNum(g.shortfall)} {g.unit}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {!needsAction && (
              <button onClick={() => { setStatus('open'); setNeedsAction(true); }}
                className="px-3 py-2 text-sm bg-red-600 text-white rounded-lg hover:brightness-110 whitespace-nowrap"
                data-testid="quarantine-show-needs-action">
                Lihat daftar
              </button>
            )}
          </div>
        </div>
      )}

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon={Boxes} label="Item Tertahan" value={fmtNum(summary?.open_items)} tone="amber"
          hint={`${fmtNum(summary?.closed_items)} sudah selesai`} />
        <Stat icon={ShieldAlert} label="Qty Tertahan" value={fmtNum(summary?.open_qty)} tone="violet"
          hint="stok diblokir (available 0)" />
        <Stat icon={Banknote} label="Nilai Tertahan" value={fmtRp(summary?.open_value)} tone="red"
          hint={`${fmtNum(summary?.valued_items)} sudah bernilai · ${fmtNum(summary?.unvalued_items)} belum`} />
        <Stat icon={Clock} label="Tertua" value={`${fmtNum(summary?.oldest_age_days)} hari`} tone="emerald"
          hint={`${fmtNum(summary?.dispositions_total)} tindak lanjut tercatat`} />
      </div>

      {/* by reason */}
      {summary && Object.keys(summary.by_reason || {}).length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Alasan reject:</span>
          {Object.entries(summary.by_reason).map(([code, qty]) => (
            <span key={code} className="px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400">
              {code} · {fmtNum(qty)}
            </span>
          ))}
        </div>
      )}

      {/* Tab: semua vs hanya yang perlu tindakan manual */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border">
        <button onClick={() => setNeedsAction(false)}
          className={`px-3 py-2 text-sm font-medium -mb-px border-b-2 ${!needsAction
            ? 'border-violet-600 text-violet-700 dark:text-violet-400'
            : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          data-testid="quarantine-tab-all">
          Semua Item Karantina
        </button>
        <button onClick={() => { setStatus('open'); setNeedsAction(true); }}
          className={`px-3 py-2 text-sm font-medium -mb-px border-b-2 flex items-center gap-2 ${needsAction
            ? 'border-red-600 text-red-700 dark:text-red-400'
            : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          data-testid="quarantine-tab-needs-action">
          Perlu Tindakan Manual
          <span className={`px-1.5 py-0.5 rounded-full text-[11px] font-bold ${unblockedCount > 0
            ? 'bg-red-600 text-white'
            : 'bg-foreground/10 text-muted-foreground'}`} data-testid="quarantine-needs-action-badge">
            {fmtNum(unblockedCount)}
          </span>
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] flex-1 min-w-48">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cari kode/nama material, no. GR, supplier..."
            className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="quarantine-search" />
          {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-muted-foreground" /></button>}
        </div>
        <SmartNativeSelect value={status} onChange={(e) => setStatus(e.target.value)} disabled={needsAction}
          className="border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] text-sm disabled:opacity-50" data-testid="quarantine-status-filter">
          <option value="open">Masih Tertahan</option>
          <option value="closed">Sudah Selesai</option>
          <option value="all">Semua</option>
        </SmartNativeSelect>
      </div>

      {err && <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-4 py-2">{err}</div>}

      {/* Table */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead className="bg-[var(--glass-bg)] border-b border-border">
            <tr>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Material</th>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Sumber</th>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Alasan</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Qty Reject</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Sisa</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Nilai</th>
              <th className="text-center px-4 py-3 text-muted-foreground font-medium">Umur</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Tindak Lanjut</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}>{[...Array(8)].map((__, j) => <td key={j} className="px-3 py-2.5"><Skeleton className="h-4" /></td>)}</tr>
              ))
            ) : filtered.length === 0 ? (
              <tr><td colSpan="8">
                {needsAction ? (
                  <EmptyState icon={Lock} title="Semua barang karantina sudah terblokir"
                    description="Tidak ada barang reject yang masih terhitung tersedia. Ini keadaan yang benar: seluruh stok karantina sudah dipastikan tidak bisa dipakai produksi maupun dikirim ke pembeli." />
                ) : (
                  <EmptyState icon={PackageCheck} title="Tidak ada barang di karantina"
                    description="Bagus! Semua barang reject QC sudah ditindaklanjuti. Qty reject dari penerimaan barang akan otomatis muncul di sini." />
                )}
              </td></tr>
            ) : pg.paged.map((it) => (
              <tr key={it.id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`quarantine-row-${it.id}`}>
                <td className="px-4 py-3">
                  <div className="font-medium">{it.material_name || '-'}</div>
                  <div className="font-mono text-xs text-muted-foreground">{it.material_code}</div>
                  {it.availability_blocked === false ? (
                    <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded text-[11px] font-bold bg-red-600 text-white"
                      title={`Barang reject ini MASIH terhitung tersedia sebanyak ${fmtNum(it.availability_shortfall)} ${it.unit} — bisa ikut dipakai produksi atau terkirim ke pembeli.`}
                      data-testid={`quarantine-unblocked-badge-${it.id}`}>
                      <ShieldOff className="w-3 h-3" /> TIDAK TERBLOKIR
                    </span>
                  ) : it.status === 'open' ? (
                    <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded text-[11px] bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                      title="Ketersediaan terblokir penuh — barang ini tidak bisa dipakai produksi/penjualan."
                      data-testid={`quarantine-blocked-badge-${it.id}`}>
                      <Lock className="w-3 h-3" /> terblokir
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-xs">
                  <div>{SOURCE_LABEL[it.source?.type] || it.source?.type || '-'}</div>
                  {it.source?.number && <div className="text-muted-foreground">{it.source.number}</div>}
                  {it.source?.supplier_name && <div className="text-muted-foreground">{it.source.supplier_name}</div>}
                </td>
                <td className="px-4 py-3 text-xs">
                  {(it.reject_reasons || []).length === 0 ? <span className="text-muted-foreground">-</span> :
                    (it.reject_reasons || []).map((r, i) => (
                      <div key={i} className="text-amber-700 dark:text-amber-400">{r.code} {r.qty ? `· ${fmtNum(r.qty)}` : ''}</div>
                    ))}
                </td>
                <td className="px-4 py-3 text-right">{fmtNum(it.qty)} <span className="text-xs text-muted-foreground">{it.unit}</span></td>
                <td className="px-4 py-3 text-right font-semibold">{fmtNum(it.remaining_qty)}</td>
                <td className="px-4 py-3 text-right text-xs">
                  {Number(it.unit_cost || 0) > 0 ? fmtRp(it.value) :
                    <span className="text-amber-700 dark:text-amber-400" title="Harga satuan material belum diisi — jurnal keuangan akan dilewati">harga belum diisi</span>}
                  <div className="text-muted-foreground">{it.valued ? 'sudah bernilai' : 'belum bernilai'}</div>
                </td>
                <td className="px-4 py-3 text-center text-xs">
                  <span className={Number(it.age_days) >= 14 ? 'text-red-700 dark:text-red-400 font-medium' : 'text-muted-foreground'}>
                    {fmtNum(it.age_days)} hari
                  </span>
                  <div className="text-muted-foreground">{fmtDate(it.created_at)}</div>
                </td>
                <td className="px-4 py-3">
                  {it.status === 'open' ? (
                    <div className="flex items-center justify-end gap-1.5 flex-wrap">
                      {it.availability_blocked === false && (
                        <button onClick={() => retryBlock(it)} disabled={retrying === it.id}
                          className="px-2.5 py-1.5 text-xs bg-red-600 text-white rounded-lg hover:brightness-110 flex items-center gap-1 disabled:opacity-60"
                          title="Pasang ulang blokir ketersediaan agar barang reject ini tidak terhitung tersedia"
                          data-testid={`quarantine-retry-block-${it.id}`}>
                          <ShieldOff className="w-3.5 h-3.5" />
                          {retrying === it.id ? 'Memblokir...' : 'Coba Blokir Ulang'}
                        </button>
                      )}
                      <button onClick={() => setModal({ item: it, action: 'release' })}
                        className="px-2.5 py-1.5 text-xs bg-emerald-600 text-white rounded-lg hover:brightness-110 flex items-center gap-1"
                        data-testid={`quarantine-release-${it.id}`}>
                        <PackageCheck className="w-3.5 h-3.5" /> Lepas
                      </button>
                      <button onClick={() => setModal({ item: it, action: 'return_supplier' })}
                        className="px-2.5 py-1.5 text-xs bg-sky-600 text-white rounded-lg hover:brightness-110 flex items-center gap-1"
                        data-testid={`quarantine-return-${it.id}`}>
                        <Undo2 className="w-3.5 h-3.5" /> Retur
                      </button>
                      <button onClick={() => setModal({ item: it, action: 'scrap' })}
                        className="px-2.5 py-1.5 text-xs border border-red-300 dark:border-red-500/40 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center gap-1"
                        data-testid={`quarantine-scrap-${it.id}`}>
                        <Trash2 className="w-3.5 h-3.5" /> Scrap
                      </button>
                    </div>
                  ) : (
                    <div className="text-right text-xs text-muted-foreground" data-testid={`quarantine-history-${it.id}`}>
                      {(it.dispositions || []).map((d) => (
                        <div key={d.id}>
                          {d.action === 'release' ? 'Dilepas' : d.action === 'return_supplier' ? 'Retur supplier' : 'Scrap'} {fmtNum(d.qty)} · {d.by || '-'}
                        </div>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pg.total > 0 && <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total} pageSize={pg.pageSize} onPageChange={pg.setPage} />}

      <div className="text-xs text-muted-foreground flex items-start gap-2 bg-[var(--glass-bg)] border border-border rounded-lg px-4 py-3">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
        <span>
          <strong>Cara kerja:</strong> saat Penerimaan Barang (GR) diset <em>received</em>, qty <em>accepted</em> masuk stok normal dan qty <em>reject</em>
          otomatis masuk Karantina QC. Bila reject baru ditemukan setelah barang masuk, gunakan re-inspeksi QC pada GR
          (opsi <em>lanjutkan meski sudah diterima</em>) — stok akan otomatis dipindahkan ke karantina.
        </span>
      </div>

      {modal && (
        <ActionModal item={modal.item} action={modal.action} locations={storageLocs} quarantineLoc={locInfo}
          onClose={() => setModal(null)} onSubmit={doAction} />
      )}
      {showManual && (
        <ManualModal token={token} locations={storageLocs} onClose={() => setShowManual(false)}
          onSaved={() => { setShowManual(false); load(); }} />
      )}
    </div>
  );
}
