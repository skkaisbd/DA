/**
 * Kesehatan Skema Stok — Portal Gudang (FASE 6.6-A, diperluas FASE 12)
 *
 * MASALAH YANG DIJAGA MODUL INI
 * Koleksi stok kanonik `rahaza_material_stock` dulu ditulis 3 kelompok writer dengan
 * bentuk berbeda:
 *   • Skema A (kanonik)        {material_id, location_id, qty}
 *   • Skema B (aksesoris lama) lokasi tersimpan BERSARANG (location.id) + total_qty
 *   • Skema C (barang jadi)    TANPA lokasi + available_quantity terpisah
 * Sejak konsolidasi, semua tulisan baru sudah kanonik — TAPI baris warisan di database
 * yang sudah berjalan bisa masih berbentuk B/C. Akibatnya layar yang membaca stok
 * PER LOKASI (Put-Away, Opname per-bin, peta gudang) tidak melihat baris itu, dan bisa
 * muncul baris kembar untuk material+lokasi yang sama.
 *
 * FASE 12 menambah penyakit ke-8 `unmapped_location`: baris stok yang duduk di lokasi
 * yang BUKAN zona penyimpanan (mis. gudang demo warisan `GDG-UTAMA-DEMO`, atau id
 * lokasi yang sudah dihapus). Totalnya benar, tapi peta gudang menyesatkan. Modul ini
 * kini menampilkan **peta lokasi** + usulan zona tujuan, dan rekonsiliasi memindahkan
 * baris tersebut ke zona kanonik sesuai kategori material (Bahan / Aksesoris / Produk
 * Jadi). Lantai produksi & karantina QC SENGAJA dikecualikan.
 *
 * Modul ini: diagnosa (read-only) + rekonsiliasi (pratinjau dulu, lalu terapkan) +
 * rollback presisi lewat jurnal. Rekonsiliasi TIDAK PERNAH mengubah total stok —
 * hanya membenahi bentuk baris, memindahkan ke zona yang benar, & menggabungkan kembar.
 *
 * Sumber data: /api/wms/stock-schema/{health,reconcile,reconcile/rollback,logs}
 */

import { useState, useEffect, useCallback } from 'react';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  ShieldCheck, ShieldAlert, RefreshCw, Wrench, Undo2, Layers, Boxes,
  AlertTriangle, Info, CheckCircle2, Database, History, Loader2, MapPin, ArrowRight,
} from 'lucide-react';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';

const API = process.env.REACT_APP_BACKEND_URL || '';

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(data.detail || `HTTP ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return data;
}

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 });
const fmtDate = (iso) => {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleDateString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return String(iso).slice(0, 16); }
};

const SCHEMA_LABEL = {
  A: 'Kanonik (lokasi datar)',
  B: 'Warisan — lokasi bersarang',
  C: 'Warisan — tanpa lokasi',
};

// FASE 12 — klasifikasi lokasi (SSOT backend: core/location_resolver.KIND_*)
const KIND_BADGE = {
  storage: { label: 'Zona penyimpanan', cls: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' },
  exempt: { label: 'Produksi / Karantina', cls: 'bg-sky-500/10 text-sky-700 dark:text-sky-400' },
  unmapped: { label: 'Bukan zona penyimpanan', cls: 'bg-amber-500/10 text-amber-700 dark:text-amber-400' },
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
      <div className="text-2xl font-bold">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

export default function StockSchemaHealthModule({ token }) {
  const [health, setHealth] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [plan, setPlan] = useState(null);
  const [canReconcile, setCanReconcile] = useState(true);
  const [confirmApply, setConfirmApply] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const h = await api('GET', '/api/wms/stock-schema/health', token);
      setHealth(h);
      try {
        const l = await api('GET', '/api/wms/stock-schema/logs?limit=20', token);
        setLogs(Array.isArray(l) ? l : []);
      } catch { setLogs([]); }
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const preview = async () => {
    setBusy('preview'); setErr(''); setMsg('');
    try {
      const res = await api('POST', '/api/wms/stock-schema/reconcile', token, { dry_run: true });
      setPlan(res);
      setMsg('Pratinjau selesai — belum ada data yang diubah.');
    } catch (e) {
      if (e.status === 403) setCanReconcile(false);
      setErr(e.message);
    } finally { setBusy(''); }
  };

  const apply = async () => {
    setBusy('apply'); setErr(''); setMsg(''); setConfirmApply(false);
    try {
      const res = await api('POST', '/api/wms/stock-schema/reconcile', token, { dry_run: false });
      const s = res.summary || {};
      setMsg(
        `Rekonsiliasi diterapkan · ${s.rows_normalized || 0} baris dinormalkan · `
        + `${s.rows_relocated || 0} baris dipindah ke zona yang benar · `
        + `${s.rows_merged || 0} baris kembar digabung · total stok ${s.total_qty_preserved ? 'TIDAK berubah' : 'BERUBAH (periksa!)'}`
        + (res.log_id ? ` · log ${String(res.log_id).slice(0, 8)}` : ''),
      );
      setPlan(null);
      await load();
    } catch (e) {
      if (e.status === 403) setCanReconcile(false);
      setErr(e.message);
    } finally { setBusy(''); }
  };

  const rollback = async (logId) => {
    setBusy(`rb-${logId}`); setErr(''); setMsg('');
    try {
      const res = await api('POST', '/api/wms/stock-schema/reconcile/rollback', token, { log_id: logId });
      setMsg(`Rollback selesai · ${res.rows_restored || 0} baris dipulihkan · ${res.rows_reinserted || 0} baris dihidupkan kembali.`);
      await load();
    } catch (e) {
      if (e.status === 403) setCanReconcile(false);
      setErr(e.message);
    } finally { setBusy(''); }
  };

  const details = health?.details || [];
  const detailsPg = useClientPagination(details, 10);
  const locations = health?.locations || [];
  const unmappedLocations = locations.filter((l) => l.kind === 'unmapped');
  const roleTargets = health?.role_targets || [];
  const counts = health?.counts || {};
  const labels = health?.labels || {};
  const hints = health?.hints || {};
  const reportOnly = health?.report_only || [];
  const issueRows = Object.keys(counts).filter((k) => counts[k] > 0);

  if (loading) {
    return (
      <div className="space-y-4" data-testid="stock-schema-loading">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="stock-schema-module">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Database className="w-5 h-5 text-violet-500" /> Kesehatan Skema Stok
          </h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Memastikan setiap baris stok memakai bentuk kanonik (lokasi datar, alias jumlah sinkron,
            jumlah tersedia benar) <b>dan duduk di zona penyimpanan yang benar</b>, sehingga layar
            per-lokasi seperti Put-Away dan Opname tidak kehilangan stok. Rekonsiliasi tidak pernah
            mengubah total stok.
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5"
          data-testid="stock-schema-refresh">
          <RefreshCw className="w-4 h-4" /> Muat ulang
        </button>
      </div>

      {err && (
        <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-lg px-4 py-2"
          data-testid="stock-schema-error">{err}</div>
      )}
      {msg && (
        <div className="text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg px-4 py-2"
          data-testid="stock-schema-msg">{msg}</div>
      )}

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon={Boxes} label="Baris stok" value={fmtNum(health?.total_rows)}
          hint={`Total on-hand ${fmtNum(health?.total_qty)}`} />
        <Stat icon={health?.healthy ? ShieldCheck : ShieldAlert}
          label="Baris bermasalah" value={fmtNum(health?.affected_rows)}
          tone={health?.healthy ? 'emerald' : 'amber'}
          hint={health?.healthy ? 'Semua baris kanonik' : 'Perlu rekonsiliasi'} />
        <Stat icon={Wrench} label="Bisa diperbaiki otomatis" value={fmtNum(health?.fixable_issues)}
          tone={health?.fixable_issues ? 'amber' : 'emerald'} hint="Lewat tombol Rekonsiliasi" />
        <Stat icon={AlertTriangle} label="Perlu keputusan manual" value={fmtNum(health?.manual_issues)}
          tone={health?.manual_issues ? 'red' : 'emerald'} hint="Stok negatif / baris yatim" />
      </div>

      {/* Bentuk baris */}
      <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4">
        <div className="text-sm font-medium mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4 text-muted-foreground" /> Bentuk baris stok
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {['A', 'B', 'C'].map((k) => (
            <div key={k} className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
              data-testid={`schema-count-${k}`}>
              <div>
                <div className="text-xs text-muted-foreground">Skema {k}</div>
                <div className="text-xs">{SCHEMA_LABEL[k]}</div>
              </div>
              <div className={`text-xl font-bold ${k === 'A' ? 'text-emerald-600 dark:text-emerald-400' : (health?.by_schema?.[k] ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground')}`}>
                {fmtNum(health?.by_schema?.[k])}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Peta lokasi stok (FASE 12) */}
      <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4" data-testid="stock-location-map">
        <div className="text-sm font-medium mb-1 flex items-center gap-2">
          <MapPin className="w-4 h-4 text-muted-foreground" /> Peta lokasi stok
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Setiap baris stok harus duduk di zona penyimpanan resmi supaya terlihat di Put-Away,
          Opname per-bin, dan peta gudang. Lantai produksi &amp; karantina QC sengaja dikecualikan —
          barang di sana memang belum/tidak disimpan di rak.
        </p>
        {locations.length === 0 ? (
          <div className="text-xs text-muted-foreground">Belum ada baris stok.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="bg-[var(--glass-bg)] border-b border-border">
                <tr>
                  <th className="text-left px-3 py-2 text-muted-foreground font-medium">Lokasi</th>
                  <th className="text-left px-3 py-2 text-muted-foreground font-medium">Status</th>
                  <th className="text-right px-3 py-2 text-muted-foreground font-medium">Baris</th>
                  <th className="text-right px-3 py-2 text-muted-foreground font-medium">Total qty</th>
                </tr>
              </thead>
              <tbody>
                {locations.map((l) => {
                  const badge = KIND_BADGE[l.kind] || KIND_BADGE.unmapped;
                  return (
                    <tr key={l.location_id} className="border-b border-border last:border-0"
                      data-testid={`stock-loc-${l.location_id}`}>
                      <td className="px-3 py-2">
                        <div className="font-medium">{l.name || l.code || l.location_id}</div>
                        <div className="text-xs text-muted-foreground font-mono">{l.code || l.location_id}</div>
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${badge.cls}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">{fmtNum(l.rows)}</td>
                      <td className="px-3 py-2 text-right font-medium">{fmtNum(l.qty)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {unmappedLocations.length > 0 && (
          <div className="mt-3 text-xs text-amber-700 dark:text-amber-400" data-testid="stock-loc-unmapped-note">
            {unmappedLocations.length} lokasi bukan zona penyimpanan. Rekonsiliasi akan memindahkan
            barisnya ke zona kanonik sesuai kategori material (total stok tidak berubah).
          </div>
        )}
        {roleTargets.some((r) => r.location_id) && (
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            {roleTargets.filter((r) => r.location_id).map((r) => (
              <span key={r.role} className="px-2 py-1 rounded-lg border border-border"
                data-testid={`role-target-${r.role}`}>
                {r.role} <ArrowRight className="w-3 h-3 inline mx-0.5" /> <b>{r.code || r.location_id}</b>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Status + aksi */}
      {health?.healthy ? (
        <div className="bg-emerald-100 dark:bg-emerald-500/5 border border-emerald-300 dark:border-emerald-500/20 rounded-xl p-4 flex items-start gap-3"
          data-testid="stock-schema-healthy">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Skema stok sehat</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Semua {fmtNum(health?.total_rows)} baris memakai bentuk kanonik. Tidak ada tindakan yang diperlukan.
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-amber-100 dark:bg-amber-500/5 border border-amber-300 dark:border-amber-500/20 rounded-xl p-4"
          data-testid="stock-schema-issues">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
            <span className="text-sm font-medium text-amber-700 dark:text-amber-400">
              {fmtNum(health?.affected_rows)} baris perlu perhatian
            </span>
          </div>
          <div className="space-y-2">
            {issueRows.map((k) => (
              <div key={k} className="flex items-start gap-3 text-xs" data-testid={`issue-${k}`}>
                <span className={`shrink-0 px-2 py-0.5 rounded-full font-medium ${reportOnly.includes(k)
                  ? 'bg-red-500/10 text-red-700 dark:text-red-400'
                  : 'bg-amber-500/10 text-amber-700 dark:text-amber-400'}`}>
                  {fmtNum(counts[k])}
                </span>
                <div>
                  <div className="font-medium">{labels[k] || k}
                    {reportOnly.includes(k) && <span className="ml-2 text-red-700 dark:text-red-400">· perlu keputusan manual</span>}
                  </div>
                  <div className="text-muted-foreground">{hints[k]}</div>
                </div>
              </div>
            ))}
          </div>
          {canReconcile && (
            <div className="flex flex-wrap items-center gap-2 mt-4">
              <button onClick={preview} disabled={!!busy}
                className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5 disabled:opacity-50 bg-[var(--card-surface)]"
                data-testid="stock-schema-preview-btn">
                {busy === 'preview' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Info className="w-4 h-4" />}
                Pratinjau Rekonsiliasi
              </button>
              <button onClick={() => setConfirmApply(true)} disabled={!!busy || !health?.fixable_issues}
                className="flex items-center gap-2 px-3 py-2 bg-primary text-foreground rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50"
                data-testid="stock-schema-apply-btn">
                <Wrench className="w-4 h-4" /> Terapkan Rekonsiliasi
              </button>
              {!health?.fixable_issues && (
                <span className="text-xs text-muted-foreground">
                  Tidak ada yang bisa diperbaiki otomatis — sisa masalah perlu Opname / Penyesuaian resmi.
                </span>
              )}
            </div>
          )}
          {!canReconcile && (
            <div className="mt-4 text-xs text-muted-foreground bg-[var(--card-surface)] border border-border rounded-lg px-3 py-2">
              Akun Anda tidak berwenang menjalankan rekonsiliasi. Silakan ajukan ke Admin Gudang / Admin sistem.
            </div>
          )}
        </div>
      )}

      {/* Konfirmasi terapkan */}
      {confirmApply && (
        <div className="bg-[var(--card-surface)] border-2 border-amber-500/40 rounded-xl p-4" data-testid="stock-schema-confirm">
          <div className="text-sm font-medium mb-1">Terapkan rekonsiliasi sekarang?</div>
          <p className="text-xs text-muted-foreground mb-3">
            Bentuk baris stok akan dinormalkan, baris yang berada di luar zona penyimpanan
            dipindahkan ke zona kanonik sesuai kategori material, dan baris kembar digabung.
            Total stok tidak berubah, dan setiap perubahan dicatat di riwayat sehingga bisa
            dibatalkan (rollback).
          </p>
          <div className="flex items-center gap-2">
            <button onClick={apply} disabled={busy === 'apply'}
              className="flex items-center gap-2 px-3 py-2 bg-primary text-foreground rounded-lg text-sm font-medium disabled:opacity-50"
              data-testid="stock-schema-confirm-yes">
              {busy === 'apply' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wrench className="w-4 h-4" />}
              Ya, terapkan
            </button>
            <button onClick={() => setConfirmApply(false)}
              className="px-3 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5"
              data-testid="stock-schema-confirm-no">Batal</button>
          </div>
        </div>
      )}

      {/* Hasil pratinjau */}
      {plan && (
        <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4" data-testid="stock-schema-plan">
          <div className="text-sm font-medium mb-2">Rencana rekonsiliasi (belum diterapkan)</div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
            <div><div className="text-muted-foreground">Baris dinormalkan</div><div className="text-lg font-bold">{fmtNum(plan.summary?.rows_normalized)}</div></div>
            <div><div className="text-muted-foreground">Baris dipindah zona</div><div className="text-lg font-bold" data-testid="plan-relocated">{fmtNum(plan.summary?.rows_relocated)}</div></div>
            <div><div className="text-muted-foreground">Baris kembar digabung</div><div className="text-lg font-bold">{fmtNum(plan.summary?.rows_merged)}</div></div>
            <div><div className="text-muted-foreground">Lokasi tak terselesaikan</div><div className="text-lg font-bold">{fmtNum(plan.summary?.unresolved_location)}</div></div>
            <div><div className="text-muted-foreground">Perlu keputusan manual</div><div className="text-lg font-bold">{fmtNum(plan.summary?.manual_attention)}</div></div>
          </div>
          {(plan.relocations || []).length > 0 && (
            <div className="mt-3 border-t border-border pt-3" data-testid="plan-relocation-list">
              <div className="text-xs font-medium mb-2">Perpindahan yang direncanakan</div>
              <ul className="space-y-1 text-xs text-muted-foreground max-h-48 overflow-y-auto">
                {(plan.relocations || []).map((r) => (
                  <li key={r.row_id} className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono">{r.from_location_code || r.from_location_id}</span>
                    <ArrowRight className="w-3 h-3" />
                    <span className="font-mono text-foreground">{r.to_location_code || r.to_location_id}</span>
                    <span className="ml-1">· {fmtNum(r.qty)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.summary?.unresolved_location > 0 && (
            <div className="mt-3 text-xs text-amber-700 dark:text-amber-400">
              Sebagian baris tanpa lokasi belum bisa diselesaikan karena zona penyimpanan kanonik belum ada —
              buat dulu di menu Struktur Gudang.
            </div>
          )}
        </div>
      )}

      {/* Detail baris bermasalah */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
        <div className="px-4 py-3 border-b border-border text-sm font-medium">Detail baris bermasalah</div>
        <table className="w-full text-sm min-w-[1000px]">
          <thead className="bg-[var(--glass-bg)] border-b border-border">
            <tr>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Material</th>
              <th className="text-center px-4 py-2.5 text-muted-foreground font-medium">Skema</th>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Lokasi</th>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Usulan zona</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Qty</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Reserved</th>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Masalah</th>
            </tr>
          </thead>
          <tbody>
            {details.length === 0 ? (
              <tr><td colSpan="7">
                <EmptyState icon={ShieldCheck} title="Tidak ada baris bermasalah"
                  description="Semua baris stok sudah memakai bentuk kanonik." />
              </td></tr>
            ) : detailsPg.paged.map((d) => (
              <tr key={d.row_id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`schema-row-${d.row_id}`}>
                <td className="px-4 py-2.5">
                  <div className="font-medium">{d.material_name}</div>
                  <div className="text-xs text-muted-foreground font-mono">{d.material_code || d.material_id}</div>
                </td>
                <td className="px-4 py-2.5 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${d.schema === 'A'
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                    : 'bg-amber-500/10 text-amber-700 dark:text-amber-400'}`}>{d.schema}</span>
                </td>
                <td className="px-4 py-2.5 text-xs">
                  {d.location_id || d.nested_location_id ? (
                    <>
                      <div className="font-mono">{d.location_code || d.location_id || d.nested_location_id}</div>
                      {d.location_name && d.location_name !== d.location_code && (
                        <div className="text-muted-foreground">{d.location_name}</div>
                      )}
                    </>
                  ) : (
                    <span className="text-amber-700 dark:text-amber-400">tanpa lokasi</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs" data-testid={`schema-suggest-${d.row_id}`}>
                  {d.suggested_location_code ? (
                    <span className="inline-flex items-center gap-1 font-mono text-emerald-700 dark:text-emerald-400">
                      <ArrowRight className="w-3 h-3" /> {d.suggested_location_code}
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-4 py-2.5 text-right font-medium">{fmtNum(d.qty)} <span className="text-xs text-muted-foreground">{d.unit}</span></td>
                <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">{fmtNum(d.reserved)}</td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap gap-1">
                    {(d.issues || []).map((i) => (
                      <span key={i} title={labels[i] || i}
                        className={`px-2 py-0.5 rounded-full text-[10px] ${reportOnly.includes(i)
                          ? 'bg-red-500/10 text-red-700 dark:text-red-400'
                          : 'bg-amber-500/10 text-amber-700 dark:text-amber-400'}`}>{i}</span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <PaginationLite page={detailsPg.page} totalPages={detailsPg.totalPages} total={detailsPg.total}
          pageSize={detailsPg.pageSize} onPageChange={detailsPg.setPage} />
        {health?.details_truncated && (
          <div className="px-4 py-2 text-xs text-muted-foreground border-t border-border">
            Hanya sebagian baris ditampilkan — jalankan rekonsiliasi untuk membenahi semuanya.
          </div>
        )}
      </div>

      {/* Riwayat rekonsiliasi */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
        <div className="px-4 py-3 border-b border-border text-sm font-medium flex items-center gap-2">
          <History className="w-4 h-4 text-muted-foreground" /> Riwayat rekonsiliasi
        </div>
        <table className="w-full text-sm min-w-[720px]">
          <thead className="bg-[var(--glass-bg)] border-b border-border">
            <tr>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Waktu</th>
              <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Oleh</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Dinormalkan</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Dipindah</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Digabung</th>
              <th className="text-center px-4 py-2.5 text-muted-foreground font-medium">Status</th>
              <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan="7">
                <EmptyState icon={History} title="Belum pernah direkonsiliasi"
                  description="Riwayat akan muncul setelah rekonsiliasi pertama dijalankan." />
              </td></tr>
            ) : logs.map((l) => (
              <tr key={l.id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`schema-log-${l.id}`}>
                <td className="px-4 py-2.5 text-xs">{fmtDate(l.created_at)}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">{l.actor?.name || l.actor?.id || '-'}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(l.summary?.rows_normalized)}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(l.summary?.rows_relocated)}</td>
                <td className="px-4 py-2.5 text-right">{fmtNum(l.summary?.rows_merged)}</td>
                <td className="px-4 py-2.5 text-center">
                  {l.rolled_back_at ? (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">sudah di-rollback</span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">aktif</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {!l.rolled_back_at && canReconcile && (
                    <button onClick={() => rollback(l.id)} disabled={busy === `rb-${l.id}`}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 border border-border rounded-lg text-xs hover:bg-foreground/5 disabled:opacity-50"
                      data-testid={`schema-rollback-${l.id}`}>
                      {busy === `rb-${l.id}` ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Undo2 className="w-3.5 h-3.5" />}
                      Rollback
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
