import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { IconButton } from './IconButton';
import {
  ScanLine, Plus, Check, X, RotateCcw, ClipboardList, MapPin, AlertTriangle,
  PackageCheck, ArrowLeft, RefreshCw, ShieldCheck, ListChecks, Boxes,
} from 'lucide-react';
import useUomOptions from '@/hooks/useUomOptions';
import { UomSelect, UomConversionHint, baseUnitOf } from './uom/UomPicker';

const fmtNum = (v) => (v || 0).toLocaleString('id-ID');
const fmtRp = (v) => 'Rp ' + Math.round(v || 0).toLocaleString('id-ID');
const STATUS_BADGE = {
  counting: 'bg-blue-400/10 text-blue-400 border-blue-300/20',
  submitted: 'bg-amber-400/10 text-amber-400 border-amber-300/20',
  approved: 'bg-emerald-400/10 text-emerald-400 border-emerald-300/20',
  rejected: 'bg-red-400/10 text-red-400 border-red-300/20',
  cancelled: 'bg-muted text-muted-foreground border-[var(--glass-border)]',
};
const STATUS_LABEL = { counting: 'Menghitung', submitted: 'Menunggu Approval', approved: 'Disetujui', rejected: 'Ditolak', cancelled: 'Dibatalkan' };

export default function WMSOpnameScanModule({ token }) {
  const [sessions, setSessions] = useState([]);
  const [loc, setLoc] = useState({ buildings: [], zones: [], racks: [], positions: [] });
  const [active, setActive] = useState(null);       // active session (summary)
  const [detail, setDetail] = useState(null);       // {session, counts, variance}
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  // new-session scope form
  const [showNew, setShowNew] = useState(false);
  const [scopeType, setScopeType] = useState('all');
  const [scopeId, setScopeId] = useState('');

  // counting state
  const [activeBin, setActiveBin] = useState(null);   // {id, barcode, label, full_label}
  const [binBarcode, setBinBarcode] = useState('');
  const [itemInput, setItemInput] = useState('');
  const [lastScan, setLastScan] = useState(null);
  // Satuan & jumlah per scan (ROADMAP P1) — default 1 satuan dasar ⇒ perilaku lama
  const [scanQty, setScanQty] = useState(1);
  const [scanUom, setScanUom] = useState('');
  const focusItem = () => setTimeout(() => document.querySelector('[data-testid="opname-item-input"]')?.focus(), 40);

  const authH = { Authorization: `Bearer ${token}` };
  const jsonH = { ...authH, 'Content-Type': 'application/json' };
  const flash = (type, text) => { setMessage({ type, text }); setTimeout(() => setMessage(null), 3500); };

  const loadSessions = useCallback(async () => {
    try {
      const r = await fetch('/api/wms/opname3/sessions', { headers: authH });
      if (r.ok) setSessions(await r.json());
    } catch (e) { console.error(e); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadLocations = useCallback(async () => {
    try {
      const r = await fetch('/api/wms/putaway/locations', { headers: authH });
      if (r.ok) setLoc(await r.json());
    } catch (e) { console.error(e); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadDetail = useCallback(async (id) => {
    try {
      const r = await fetch(`/api/wms/opname3/sessions/${id}`, { headers: authH });
      if (r.ok) { const d = await r.json(); setDetail(d); setActive(d.session); return d; }
    } catch (e) { console.error(e); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    (async () => { setLoading(true); await Promise.all([loadSessions(), loadLocations()]); setLoading(false); })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // bins within active session scope (for active-bin selector)
  const scopeBins = useMemo(() => {
    if (!active) return [];
    const st = active.scope_type, sid = active.scope_id;
    return loc.positions.filter((p) => st === 'all' || (st === 'building' && p.building_id === sid) || (st === 'zone' && p.zone_id === sid) || (st === 'rack' && p.rack_id === sid));
  }, [loc.positions, active]);

  const snapshotByBin = useMemo(() => {
    const map = {};
    (detail?.session?.snapshot || []).forEach((s) => { map[s.bin_id] = s; });
    return map;
  }, [detail]);

  // Satuan yang sah untuk barang yang DIHARAPKAN di bin aktif — dipakai dropdown
  // "satuan hitung". Bila bin kosong/tak dikenal, hanya satuan dasar yang tampil.
  const expectedMat = activeBin ? snapshotByBin[activeBin.id] : null;
  const { options: uomOpts } = useUomOptions(expectedMat?.material_id ? [expectedMat.material_id] : []);
  const scanUomOpt = expectedMat?.material_id ? uomOpts[expectedMat.material_id] : null;
  const scanBaseUnit = baseUnitOf(scanUomOpt, '');

  const createSession = async () => {
    setBusy(true);
    try {
      const r = await fetch('/api/wms/opname3/sessions', { method: 'POST', headers: jsonH, body: JSON.stringify({ scope_type: scopeType, scope_id: scopeType === 'all' ? '' : scopeId }) });
      const d = await r.json();
      if (r.ok) { setShowNew(false); setScopeType('all'); setScopeId(''); await loadSessions(); await loadDetail(d.id); setActiveBin(null); flash('success', `Sesi opname ${d.session_no} dibuat (${d.occupied_bins} bin terisi)`); }
      else flash('error', d.detail || 'Gagal membuat sesi');
    } catch (e) { flash('error', e.message); } finally { setBusy(false); }
  };

  const openSession = async (s) => { await loadDetail(s.id); setActiveBin(null); setLastScan(null); };
  const backToList = async () => { setActive(null); setDetail(null); setActiveBin(null); await loadSessions(); };

  const pickBinByBarcode = () => {
    const code = binBarcode.trim(); if (!code) return;
    const pos = scopeBins.find((p) => p.barcode === code);
    if (!pos) { flash('error', `Bin "${code}" tidak ada dalam cakupan sesi ini`); return; }
    setActiveBin({ id: pos.id, barcode: pos.barcode, label: pos.label, full_label: pos.full_label });
    setBinBarcode('');
    focusItem();
  };

  const doScan = async () => {
    const code = itemInput.trim();
    if (!code) return;
    if (!activeBin) { flash('error', 'Pilih / scan BIN dulu sebelum scan barang'); return; }
    const q = Number(scanQty) > 0 ? Number(scanQty) : 1;
    try {
      const payload = { session_id: active.id, bin_id: activeBin.id, item_barcode: code, qty: q };
      if (scanUom && scanUom !== scanBaseUnit) payload.input_uom = scanUom;
      const r = await fetch('/api/wms/opname3/scan', { method: 'POST', headers: jsonH, body: JSON.stringify(payload) });
      const d = await r.json();
      if (r.ok) {
        setLastScan(d);
        setItemInput('');
        await loadDetail(active.id);
        focusItem();
      } else { flash('error', d.detail || 'Barang tidak dikenal'); setItemInput(''); focusItem(); }
    } catch (e) { flash('error', e.message); }
  };

  const undoCount = async (row) => {
    try {
      const r = await fetch('/api/wms/opname3/scan-undo', { method: 'POST', headers: jsonH, body: JSON.stringify({ session_id: active.id, bin_id: row.bin_id, item_material_id: row.material_id, qty: 1 }) });
      if (r.ok) await loadDetail(active.id);
    } catch (e) { flash('error', e.message); }
  };

  const doAction = async (action, needReason = false) => {
    let notes = '';
    if (needReason) { notes = window.prompt(action === 'reject' ? 'Alasan penolakan:' : 'Catatan:') || ''; if (action === 'reject' && !notes) return; }
    setBusy(true);
    try {
      const r = await fetch(`/api/wms/opname3/${action}`, { method: 'POST', headers: jsonH, body: JSON.stringify({ session_id: active.id, notes }) });
      const d = await r.json();
      if (r.ok) {
        if (action === 'approve') { const je = d.session?.summary?.je_posted || 0; flash('success', `Opname disetujui. Stok direkonsiliasi, ${je} jurnal finance diposting.`); await loadDetail(active.id); }
        else if (action === 'submit') { flash('success', 'Opname disubmit, menunggu approval supervisor'); await loadDetail(active.id); }
        else { flash('success', `Opname di-${action}`); await loadDetail(active.id); }
      } else flash('error', d.detail || `Gagal ${action}`);
    } catch (e) { flash('error', e.message); } finally { setBusy(false); }
  };

  // ── RENDER ─────────────────────────────────────────────────────────────
  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>;

  const banner = message && (
    <div data-testid="opname-message" className={`p-3 rounded-xl text-sm font-medium ${message.type === 'success' ? 'bg-emerald-400/10 text-emerald-400 border border-emerald-300/20' : 'bg-red-400/10 text-red-400 border border-red-300/20'}`}>{message.text}</div>
  );

  // LIST VIEW
  if (!active) {
    return (
      <div className="space-y-6" data-testid="wms-opname-scan-module">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Stock Opname</h1>
            <p className="text-muted-foreground text-sm">Hitung fisik dengan scan barang per bin (gudang &rarr; zona &rarr; rak &rarr; bin). Approval supervisor + rekonsiliasi finance.</p>
          </div>
          <div className="flex gap-2">
            <IconButton label="Refresh" onClick={loadSessions} data-testid="opname-refresh"><RefreshCw className="w-4 h-4 text-muted-foreground" /></IconButton>
            <Button onClick={() => setShowNew((v) => !v)} className="bg-primary text-primary-foreground hover:brightness-110" data-testid="opname-new-btn"><Plus className="w-4 h-4 mr-1" /> Opname Baru</Button>
          </div>
        </div>
        {banner}

        {showNew && (
          <GlassCard hover={false} className="p-5" data-testid="opname-new-panel">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2"><ListChecks className="w-4 h-4 text-primary" /> Sesi Opname Baru</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Cakupan</label>
                <SmartNativeSelect value={scopeType} onChange={(e) => { setScopeType(e.target.value); setScopeId(''); }} className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-3 py-2 text-sm text-foreground" data-testid="opname-scope-type">
                  <option value="all">Semua Lokasi</option>
                  <option value="building">Per Gudang</option>
                  <option value="zone">Per Zona</option>
                  <option value="rack">Per Rak</option>
                </SmartNativeSelect>
              </div>
              {scopeType !== 'all' && (
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">Pilih {scopeType === 'building' ? 'Gudang' : scopeType === 'zone' ? 'Zona' : 'Rak'}</label>
                  <SmartNativeSelect value={scopeId} onChange={(e) => setScopeId(e.target.value)} className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-3 py-2 text-sm text-foreground" data-testid="opname-scope-id">
                    <option value="">Pilih...</option>
                    {(scopeType === 'building' ? loc.buildings : scopeType === 'zone' ? loc.zones : loc.racks).map((x) => <option key={x.id} value={x.id}>{x.code} - {x.name}</option>)}
                  </SmartNativeSelect>
                </div>
              )}
              <Button onClick={createSession} disabled={busy || (scopeType !== 'all' && !scopeId)} className="bg-primary text-primary-foreground hover:brightness-110" data-testid="opname-create-btn"><Check className="w-4 h-4 mr-1" /> Mulai</Button>
            </div>
          </GlassCard>
        )}

        <GlassCard hover={false} className="p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">Riwayat Sesi Opname</h3>
          {sessions.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">Belum ada sesi opname. Klik &ldquo;Opname Baru&rdquo; untuk memulai.</p>
          ) : (
            <div className="space-y-2">
              {sessions.map((s) => (
                <button key={s.id} onClick={() => openSession(s)} className="w-full text-left p-3 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors flex items-center justify-between" data-testid={`opname-session-${s.session_no}`}>
                  <div>
                    <p className="text-sm font-medium text-foreground font-mono">{s.session_no}</p>
                    <p className="text-xs text-muted-foreground">{s.scope_label} · {s.occupied_bins} bin · {new Date(s.created_at).toLocaleString('id-ID')}</p>
                  </div>
                  <span className={`text-[11px] px-2 py-1 rounded-full border ${STATUS_BADGE[s.status] || ''}`}>{STATUS_LABEL[s.status] || s.status}</span>
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    );
  }

  const variance = detail?.variance;
  const status = active.status;

  return (
    <div className="space-y-6" data-testid="wms-opname-scan-module">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <IconButton label="Kembali" onClick={backToList} data-testid="opname-back"><ArrowLeft className="w-4 h-4 text-muted-foreground" /></IconButton>
          <div>
            <h1 className="text-xl font-bold text-foreground font-mono">{active.session_no}</h1>
            <p className="text-muted-foreground text-xs">{active.scope_label}</p>
          </div>
        </div>
        <span className={`text-xs px-3 py-1 rounded-full border ${STATUS_BADGE[status] || ''}`} data-testid="opname-status">{STATUS_LABEL[status] || status}</span>
      </div>
      {banner}

      {/* COUNTING VIEW */}
      {status === 'counting' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2"><ScanLine className="w-4 h-4 text-primary" /> Scan Barang</h3>
            {/* Active bin */}
            <div className="space-y-2 mb-4">
              <label className="text-xs font-medium text-muted-foreground flex items-center gap-1"><MapPin className="w-3 h-3" /> Bin Aktif (scan atau pilih)</label>
              <div className="flex gap-2">
                <GlassInput placeholder="Scan barcode bin..." value={binBarcode} onChange={(e) => setBinBarcode(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && pickBinByBarcode()} data-testid="opname-bin-barcode" />
                <Button variant="outline" onClick={pickBinByBarcode} data-testid="opname-bin-scan-btn"><ScanLine className="w-4 h-4" /></Button>
              </div>
              <SmartNativeSelect value={activeBin?.id || ''} onChange={(e) => { const p = scopeBins.find((b) => b.id === e.target.value); setActiveBin(p ? { id: p.id, barcode: p.barcode, label: p.label, full_label: p.full_label } : null); focusItem(); }} className="w-full border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg px-3 py-2 text-sm text-foreground" data-testid="opname-bin-select">
                <option value="">— pilih bin —</option>
                {scopeBins.map((p) => <option key={p.id} value={p.id}>{p.full_label}{snapshotByBin[p.id] ? ` · exp: ${snapshotByBin[p.id].material_code}` : ''}</option>)}
              </SmartNativeSelect>
              {activeBin && (
                <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-xs text-foreground flex items-center gap-2" data-testid="opname-active-bin">
                  <MapPin className="w-3 h-3 text-primary" /> {activeBin.full_label}
                  {snapshotByBin[activeBin.id] && <span className="text-muted-foreground">· diharapkan: {snapshotByBin[activeBin.id].material_code} ({fmtNum(snapshotByBin[activeBin.id].expected_qty)})</span>}
                </div>
              )}
            </div>
            {/* Item scan */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                Jumlah &amp; satuan per scan (default 1 satuan dasar)
              </label>
              <div className="flex gap-2">
                <GlassInput type="number" min={0} step="0.0001" value={scanQty}
                  onChange={(e) => setScanQty(e.target.value)}
                  className="w-28" data-testid="opname-scan-qty" />
                <UomSelect opt={scanUomOpt} value={scanUom || scanBaseUnit}
                  onChange={(e) => setScanUom(e.target.value)}
                  fallbackUnit={expectedMat?.unit || ''}
                  testId="opname-scan-uom" className="w-24 shrink-0" />
                <div className="flex-1">
                  <UomConversionHint opt={scanUomOpt} qty={scanQty} unit={scanUom || scanBaseUnit}
                    fallbackUnit={expectedMat?.unit || ''} testId="opname-scan-uom-hint" />
                </div>
              </div>
              <label className="text-xs font-medium text-muted-foreground">Scan Barang. Tekan Enter, terus-menerus.</label>
              <GlassInput autoFocus placeholder="Scan / ketik kode barang lalu Enter..." value={itemInput} onChange={(e) => setItemInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doScan()} disabled={!activeBin} data-testid="opname-item-input" />
            </div>
            {lastScan && (
              <div className={`mt-3 p-3 rounded-xl border ${lastScan.salah_lokasi ? 'bg-amber-400/10 border-amber-300/30' : 'bg-emerald-400/10 border-emerald-300/20'}`} data-testid="opname-last-scan">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground">{lastScan.material_code}</span>
                  <span className="text-lg font-bold text-foreground">×{fmtNum(lastScan.counted_qty)}</span>
                </div>
                {lastScan.salah_lokasi ? (
                  <p className="text-[11px] text-amber-400 flex items-center gap-1 mt-1"><AlertTriangle className="w-3 h-3" /> Salah lokasi{lastScan.expected_bin_label ? ` — harusnya di ${lastScan.expected_bin_label}` : ' — barang tidak diharapkan di bin ini'}</p>
                ) : (
                  <p className="text-[11px] text-emerald-400 flex items-center gap-1 mt-1"><Check className="w-3 h-3" /> Lokasi benar</p>
                )}
                <p className="text-[11px] text-muted-foreground mt-1">Total ter-scan sesi: {fmtNum(lastScan.session_total_scanned)}</p>
              </div>
            )}
          </GlassCard>

          {/* Tally */}
          <GlassCard hover={false} className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2"><ClipboardList className="w-4 h-4 text-primary" /> Hasil Hitung</h3>
              <Button onClick={() => doAction('submit')} disabled={busy || !(detail?.counts?.length)} className="bg-primary text-primary-foreground hover:brightness-110" size="sm" data-testid="opname-submit-btn"><PackageCheck className="w-4 h-4 mr-1" /> Selesai &amp; Submit</Button>
            </div>
            <div className="space-y-2 max-h-[440px] overflow-y-auto">
              {!(detail?.counts?.length) ? (
                <p className="text-xs text-muted-foreground text-center py-8">Belum ada barang di-scan.</p>
              ) : detail.counts.map((c) => (
                <div key={c.id} className={`p-2.5 rounded-lg border flex items-center justify-between ${c.salah_lokasi ? 'border-amber-300/30 bg-amber-400/5' : 'border-[var(--glass-border)] bg-[var(--glass-bg)]'}`} data-testid={`opname-count-${c.material_code}`}>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{c.material_code} <span className="text-muted-foreground font-normal">@ {c.bin_label}</span></p>
                    {c.salah_lokasi && <p className="text-[11px] text-amber-400 flex items-center gap-1"><AlertTriangle className="w-2.5 h-2.5" /> salah lokasi{c.expected_bin_label ? ` (→ ${c.expected_bin_label})` : ''}</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-base font-bold text-foreground">{fmtNum(c.counted_qty)}</span>
                    <IconButton label="Kurangi 1" onClick={() => undoCount(c)} data-testid={`opname-undo-${c.material_code}`}><RotateCcw className="w-3.5 h-3.5 text-muted-foreground" /></IconButton>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* REVIEW / APPROVED / etc. */}
      {status !== 'counting' && variance && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <GlassCard hover={false} className="p-4"><p className="text-xs text-muted-foreground">Material Dihitung</p><p className="text-xl font-bold text-foreground">{variance.totals.materials_counted}</p></GlassCard>
            <GlassCard hover={false} className="p-4"><p className="text-xs text-muted-foreground">Selisih (item)</p><p className="text-xl font-bold text-foreground">{variance.totals.materials_with_variance}</p></GlassCard>
            <GlassCard hover={false} className="p-4"><p className="text-xs text-muted-foreground">Nilai Selisih</p><p className={`text-xl font-bold ${variance.totals.total_variance_value < 0 ? 'text-red-400' : variance.totals.total_variance_value > 0 ? 'text-emerald-400' : 'text-foreground'}`}>{fmtRp(variance.totals.total_variance_value)}</p></GlassCard>
            <GlassCard hover={false} className="p-4"><p className="text-xs text-muted-foreground">Salah Lokasi</p><p className="text-xl font-bold text-amber-400">{variance.totals.salah_lokasi_count}</p></GlassCard>
          </div>

          {status === 'submitted' && (
            <div className="flex flex-wrap gap-2" data-testid="opname-approval-actions">
              <Button onClick={() => doAction('approve')} disabled={busy} className="bg-emerald-500 text-white hover:brightness-110" data-testid="opname-approve-btn"><ShieldCheck className="w-4 h-4 mr-1" /> Approve (Supervisor)</Button>
              <Button onClick={() => doAction('reject', true)} disabled={busy} variant="outline" className="border-red-300/30 text-red-400" data-testid="opname-reject-btn"><X className="w-4 h-4 mr-1" /> Tolak</Button>
              <Button onClick={() => doAction('cancel')} disabled={busy} variant="ghost" className="text-muted-foreground" data-testid="opname-cancel-btn">Batalkan</Button>
            </div>
          )}
          {status === 'approved' && (
            <div className="p-3 rounded-xl bg-emerald-400/10 border border-emerald-300/20 text-sm text-emerald-400 flex items-center gap-2" data-testid="opname-approved-banner">
              <PackageCheck className="w-4 h-4" /> Disetujui oleh {active.approved_by_name || 'supervisor'}. Stok direkonsiliasi &amp; {active.summary?.je_posted || 0} jurnal finance diposting.
            </div>
          )}

          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2"><Boxes className="w-4 h-4 text-primary" /> Variance per Barang</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                    <th className="text-left py-2">Kode</th><th className="text-left">Nama</th>
                    <th className="text-right">Sistem</th><th className="text-right">Fisik</th><th className="text-right">Selisih</th><th className="text-right">Nilai</th>
                  </tr>
                </thead>
                <tbody>
                  {variance.lines.map((l) => (
                    <tr key={l.material_id} className={`border-b border-[var(--glass-border)]/50 ${l.variance_qty !== 0 ? 'bg-amber-400/5' : ''}`} data-testid={`opname-var-${l.material_code}`}>
                      <td className="py-2 font-mono text-foreground">{l.material_code}</td>
                      <td className="text-muted-foreground">{l.material_name}</td>
                      <td className="text-right text-foreground">{fmtNum(l.expected_qty)}</td>
                      <td className="text-right text-foreground">{fmtNum(l.counted_qty)}</td>
                      <td className={`text-right font-semibold ${l.variance_qty < 0 ? 'text-red-400' : l.variance_qty > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>{l.variance_qty > 0 ? '+' : ''}{fmtNum(l.variance_qty)}</td>
                      <td className="text-right text-muted-foreground">{fmtRp(l.variance_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          {variance.salah_lokasi?.length > 0 && (
            <GlassCard hover={false} className="p-5">
              <h3 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Barang Salah Lokasi ({variance.salah_lokasi.length})</h3>
              <div className="space-y-1.5">
                {variance.salah_lokasi.map((c) => (
                  <div key={c.id} className="text-xs text-foreground flex items-center justify-between p-2 rounded-lg bg-amber-400/5 border border-amber-300/20">
                    <span>{c.material_code} ditemukan di <b>{c.bin_label}</b></span>
                    <span className="text-muted-foreground">{c.expected_bin_label ? `harusnya: ${c.expected_bin_label}` : 'tidak terdaftar di bin ini'} · ×{fmtNum(c.counted_qty)}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
