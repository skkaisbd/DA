/**
 * ProductCostingModule — layar **HPP per Potong & per Model**.
 *
 * MENGAPA LAYAR INI ADA (fakta terukur 2026-08-23)
 * ------------------------------------------------
 * Sejak sesi #30 harga bahan lahir dari PEMBELIAN (rata-rata bergerak). Tetapi
 * HPP produk jadi belum pernah lahir dari angka itu: 321 dokumen FG semuanya
 * `hpp: 0` / `hpp_source: 'none'`, dan satu-satunya sumber HPP model adalah
 * kalkulator R&D atau KETIKAN manual (`base_hpp`). Akibatnya kolom margin di
 * Katalog Marketing selalu 0 dan pemilik tidak bisa tahu margin sebelum harga
 * jual ditetapkan.
 *
 * Di layar ini HPP/pcs dihitung dari data yang sudah ada:
 *   bahan (BOM × harga pembelian, sadar satuan) + upah CMT + upah cutting/internal
 *   [+ overhead OPSIONAL]
 * lalu bisa DITERAPKAN ke master produk, FG per ukuran, dan item katalog.
 *
 * Aturan jujur: setiap angka menyebut ASALNYA, dan setiap kekurangan tampil
 * sebagai daftar yang bisa diklik menuju layar perbaikannya — tidak ada angka 0
 * yang diam-diam dianggap benar.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Calculator, RefreshCw, Search, Wand2, AlertTriangle, CheckCircle2, Settings2,
  Loader2, ArrowRight, History, Lock, Info, TrendingUp, Layers,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from '../Modal';
import {
  costingApi, fmtRp, fmtNum, fmtPct, SOURCE_LABEL, COST_SOURCE_LABEL,
  STATUS_META, GAP_LABEL,
} from './costingApi';

const inputCls =
  'w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.35)]';

function SourcePill({ source, title }) {
  const m = SOURCE_LABEL[source] || SOURCE_LABEL.none;
  return (
    <span title={title || ''}
      className={`inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${m.cls}`}>
      {m.text}
    </span>
  );
}

function StatusPill({ status }) {
  const m = STATUS_META[status] || STATUS_META.no_bom;
  return (
    <span className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border ${m.cls}`}>
      {m.label}
    </span>
  );
}

export default function ProductCostingModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [totals, setTotals] = useState(null);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [targetMargin, setTargetMargin] = useState('');
  const [includeOverhead, setIncludeOverhead] = useState(false);
  const [detail, setDetail] = useState(null);         // hasil GET /models/{id}
  const [detailBusy, setDetailBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [applyingAll, setApplyingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ limit: '300' });
      if (search.trim()) p.set('q', search.trim());
      if (onlyGaps) p.set('only_gaps', 'true');
      if (targetMargin !== '') p.set('target_margin_pct', String(targetMargin));
      p.set('include_overhead', includeOverhead ? '1' : '0');
      const d = await costingApi('GET', `/models?${p}`, token);
      setRows(d.items || []);
      setTotals(d.totals || null);
      setSettings(d.settings || null);
      if (targetMargin === '' && d.settings) setTargetMargin(String(d.settings.target_margin_pct ?? 30));
    } catch (e) {
      toast.error(`Gagal memuat HPP produk: ${e.message}`);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, search, onlyGaps, includeOverhead, targetMargin]);

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [onlyGaps, includeOverhead]);
  useEffect(() => {
    const t = setTimeout(() => load(), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, targetMargin]);

  const openDetail = async (modelId) => {
    setDetailBusy(true);
    try {
      const p = new URLSearchParams();
      if (targetMargin !== '') p.set('target_margin_pct', String(targetMargin));
      p.set('include_overhead', includeOverhead ? '1' : '0');
      const d = await costingApi('GET', `/models/${modelId}?${p}`, token);
      setDetail(d);
    } catch (e) {
      toast.error(`Gagal memuat rincian: ${e.message}`);
    } finally { setDetailBusy(false); }
  };

  const applyModel = async (modelId) => {
    try {
      const d = await costingApi('POST', `/models/${modelId}/apply`, token,
        { include_overhead: includeOverhead });
      toast.success(
        `HPP diterapkan: ${d.applied.length} ukuran @${fmtRp(d.hpp_model)} · ` +
        `${d.fg_updated} produk jadi & ${d.catalog_items_updated} item katalog ikut diperbarui.`);
      await load();
      if (detail?.model?.id === modelId) await openDetail(modelId);
    } catch (e) {
      toast.error(`Gagal menerapkan HPP: ${e.message}`);
    }
  };

  const applyAll = async () => {
    setApplyingAll(true);
    try {
      const d = await costingApi('POST', '/apply-all', token, { include_overhead: includeOverhead });
      toast.success(
        `${d.applied_count} produk diterapkan · ${d.fg_updated} produk jadi & ` +
        `${d.catalog_items_updated} item katalog diperbarui` +
        (d.skipped_count ? ` · ${d.skipped_count} dilewati (belum bisa dihitung)` : ''));
      await load();
    } catch (e) {
      toast.error(`Gagal menerapkan: ${e.message}`);
    } finally { setApplyingAll(false); }
  };

  const goto = (target) => {
    if (!target || target === 'fin-hpp-produk') return;
    if (typeof onNavigate === 'function') { onNavigate(target); return; }
    window.location.hash = target;
    window.location.reload();
  };

  const stat = (k) => (totals ? (totals[k] ?? 0) : 0);
  const readyCount = useMemo(() => rows.filter(r => r.status === 'ready').length, [rows]);

  return (
    <div className="space-y-4" data-testid="product-costing-page">
      {/* ── kepala ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <Calculator className="w-5 h-5 text-primary" /> HPP per Potong &amp; per Model
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5 max-w-3xl">
            HPP/pcs dihitung dari <strong>BOM × harga bahan hasil pembelian</strong> (rata-rata
            bergerak) + <strong>upah CMT</strong> + <strong>upah cutting/internal</strong>. Tidak
            ada angka yang diketik: setiap komponen menyebut asalnya, dan yang belum ada muncul
            sebagai kekurangan yang bisa langsung diperbaiki.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="ghost" onClick={load} disabled={loading} data-testid="costing-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
          </Button>
          <Button variant="outline" onClick={() => setShowSettings(true)} data-testid="costing-open-settings">
            <Settings2 className="w-4 h-4 mr-1.5" /> Setelan Upah &amp; Margin
          </Button>
          <Button onClick={applyAll} disabled={applyingAll || !readyCount} data-testid="costing-apply-all">
            {applyingAll ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
              : <Wand2 className="w-4 h-4 mr-1.5" />}
            Terapkan semua yang siap{readyCount ? ` (${readyCount})` : ''}
          </Button>
        </div>
      </div>

      {/* ── ringkasan ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="costing-summary">
        {[
          { k: 'models', label: 'Produk dihitung', v: stat('models'), tone: 'text-foreground' },
          { k: 'ready', label: 'Siap (semua komponen ada)', v: stat('ready'), tone: 'text-emerald-600 dark:text-emerald-300' },
          { k: 'partial', label: 'Sebagian (masih ada kekurangan)', v: stat('partial'), tone: 'text-amber-600 dark:text-amber-300' },
          { k: 'no_bom', label: 'Belum ada BOM', v: stat('no_bom'), tone: 'text-red-500' },
        ].map(c => (
          <GlassCard key={c.k} className="p-3">
            <div className={`text-2xl font-bold ${c.tone}`} data-testid={`costing-stat-${c.k}`}>{c.v}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{c.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* ── penjelasan jujur bila belum ada yang siap ──────────────────── */}
      {!loading && stat('ready') === 0 && (
        <div className="flex items-start gap-2 bg-amber-400/10 border border-amber-300/25 rounded-lg px-4 py-3"
          data-testid="costing-empty-warning">
          <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-600 dark:text-amber-300">
            <strong>Belum ada produk yang bisa dihitung penuh.</strong> Yang paling sering kurang:
            BOM per ukuran belum dibuat, ada bahan yang belum pernah dibeli (jadi belum punya
            harga), atau upah CMT/cutting belum dikunci. Buka <em>Rincian</em> pada baris mana pun
            untuk melihat daftar kekurangannya dan tombol perbaikannya.
          </div>
        </div>
      )}

      {/* ── penyaring ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari kode / nama produk…" className={`${inputCls} pl-8`}
            data-testid="costing-search" />
        </div>
        <label className="flex items-center gap-2 text-xs text-foreground/80 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)]">
          <span>Target margin</span>
          <input type="number" min="0" max="99" step="1" value={targetMargin}
            onChange={e => setTargetMargin(e.target.value)}
            className="w-16 bg-transparent text-right font-semibold text-foreground focus:outline-none"
            data-testid="costing-target-margin" />
          <span>%</span>
        </label>
        <label className="flex items-center gap-2 text-xs text-foreground/80 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] cursor-pointer">
          <input type="checkbox" checked={includeOverhead}
            onChange={e => setIncludeOverhead(e.target.checked)}
            data-testid="costing-toggle-overhead" />
          Ikutkan overhead {settings ? `(${fmtRp(settings.overhead_rate_per_pcs)}/pcs)` : ''}
        </label>
        <label className="flex items-center gap-2 text-xs text-foreground/80 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] cursor-pointer">
          <input type="checkbox" checked={onlyGaps} onChange={e => setOnlyGaps(e.target.checked)}
            data-testid="costing-filter-gaps" />
          Hanya yang masih ada kekurangan
        </label>
      </div>

      {/* ── tabel ──────────────────────────────────────────────────────── */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="costing-table">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-3 py-3">Kode</th>
                <th className="px-3 py-3">Produk</th>
                <th className="px-3 py-3 text-center">Ukuran ber-BOM</th>
                <th className="px-3 py-3 text-right">Bahan/pcs</th>
                <th className="px-3 py-3 text-right">Upah CMT</th>
                <th className="px-3 py-3 text-right">Upah internal</th>
                <th className="px-3 py-3 text-right">HPP/pcs</th>
                <th className="px-3 py-3 text-right">Harga jual</th>
                <th className="px-3 py-3 text-right">Margin</th>
                <th className="px-3 py-3 text-right">Usulan harga</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={12} className="text-center py-12 text-muted-foreground">Memuat…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={12} className="text-center py-12 text-muted-foreground">
                  Tidak ada produk pada penyaring ini.
                </td></tr>
              ) : rows.map(r => (
                <tr key={r.model_id}
                  className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
                  data-testid={`costing-row-${r.code}`}>
                  <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">{r.code}</td>
                  <td className="px-3 py-2 text-foreground">
                    {r.name}
                    <span className="block text-[10px] text-muted-foreground">
                      {r.category_name || 'tanpa kategori'}
                      {r.hpp_bom_current > 0 && (
                        <span className="text-emerald-600 dark:text-emerald-300">
                          {' '}· tersimpan {fmtRp(r.hpp_bom_current)}
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center text-xs text-foreground whitespace-nowrap">
                    {r.sizes_with_bom}/{r.size_count}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-foreground whitespace-nowrap">
                    {r.material_cost_avg > 0 ? fmtRp(r.material_cost_avg) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <span className="font-mono text-xs text-foreground">
                      {r.cmt_cost > 0 ? fmtRp(r.cmt_cost) : '—'}
                    </span>
                    <span className="block mt-0.5"><SourcePill source={r.cmt_source} /></span>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <span className="font-mono text-xs text-foreground">
                      {r.internal_labor_cost > 0 ? fmtRp(r.internal_labor_cost) : '—'}
                    </span>
                    <span className="block mt-0.5"><SourcePill source={r.internal_labor_source} /></span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-sm font-bold text-foreground whitespace-nowrap"
                    data-testid={`costing-hpp-${r.code}`}>
                    {r.hpp_avg > 0 ? fmtRp(r.hpp_avg) : '—'}
                    {r.hpp_min > 0 && r.hpp_max > r.hpp_min && (
                      <span className="block text-[10px] font-normal text-muted-foreground">
                        {fmtRp(r.hpp_min)}–{fmtRp(r.hpp_max)} per ukuran
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-foreground whitespace-nowrap">
                    {r.price_best > 0 ? fmtRp(r.price_best)
                      : <span className="text-muted-foreground">belum ada</span>}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap"
                    data-testid={`costing-margin-${r.code}`}>
                    {r.margin_known ? (
                      <span className={r.margin_pct >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-red-500'}>
                        {fmtPct(r.margin_pct)}
                      </span>
                    ) : (
                      /* SESI #32 (temuan penguji): dulu sel ini hanya bertanda "—"
                         sehingga alasannya hanya terbaca kalau kursor didiamkan di
                         atasnya. Sekarang alasannya DITULIS. */
                      <span className="text-[10px] text-muted-foreground" title={r.price_best > 0
                        ? 'HPP belum bisa dihitung — margin tidak ditampilkan supaya tidak menyesatkan'
                        : 'Margin baru bisa dihitung setelah harga jual ditetapkan'}>
                        {r.price_best > 0 ? 'HPP belum ada' : 'harga jual belum ada'}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-primary whitespace-nowrap">
                    {r.suggested_price > 0 ? fmtRp(r.suggested_price) : '—'}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <StatusPill status={r.status} />
                    {r.gap_count > 0 && (
                      <span className="block text-[10px] text-amber-600 dark:text-amber-300 mt-0.5">
                        {r.gap_count} kekurangan
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button onClick={() => openDetail(r.model_id)}
                      className="text-primary hover:underline text-xs mr-3"
                      data-testid={`costing-detail-${r.code}`}>Rincian</button>
                    <button onClick={() => applyModel(r.model_id)}
                      disabled={r.sizes_with_bom === 0}
                      className="text-xs text-foreground hover:underline disabled:text-muted-foreground disabled:cursor-not-allowed"
                      data-testid={`costing-apply-${r.code}`}>Terapkan</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {detailBusy && !detail && (
        <div className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Memuat rincian…
        </div>
      )}

      {detail && (
        <CostDetailModal detail={detail} token={token} onClose={() => setDetail(null)}
          onApply={() => applyModel(detail.model.id)}
          onReload={() => openDetail(detail.model.id)}
          onGoto={goto} />
      )}

      {showSettings && (
        <CostingSettingsModal token={token} onClose={() => setShowSettings(false)}
          onSaved={() => { setShowSettings(false); load(); }} />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   RINCIAN PER MODEL — baris BOM, upah, kekurangan, riwayat penerapan
   ═══════════════════════════════════════════════════════════════════════ */
function CostDetailModal({ detail, token, onClose, onApply, onReload, onGoto }) {
  const m = detail.model || {};
  const [cmt, setCmt] = useState(detail.override?.cmt_rate_per_pcs ?? '');
  const [internal, setInternal] = useState(detail.override?.internal_labor_per_pcs ?? '');
  const [saving, setSaving] = useState(false);
  const [snapshots, setSnapshots] = useState(null);

  const saveLabor = async () => {
    setSaving(true);
    try {
      await costingApi('PUT', `/models/${m.id}/labor`, token, {
        cmt_rate_per_pcs: cmt === '' ? null : Number(cmt),
        internal_labor_per_pcs: internal === '' ? null : Number(internal),
      });
      toast.success('Upah dikunci — HPP dihitung ulang.');
      await onReload();
    } catch (e) {
      toast.error(`Gagal menyimpan upah: ${e.message}`);
    } finally { setSaving(false); }
  };

  const loadSnapshots = async () => {
    try {
      const d = await costingApi('GET', `/snapshots?model_id=${m.id}&limit=20`, token);
      setSnapshots(d.items || []);
    } catch (e) {
      toast.error(`Gagal memuat riwayat: ${e.message}`);
    }
  };

  /** Salin BOM ukuran yang sudah ada ke ukuran lain (endpoint master BOM). */
  const onCopyBom = async (g) => {
    try {
      const res = await fetch(
        `${process.env.REACT_APP_BACKEND_URL || ''}/api/rahaza/boms/${g.copy_bom_id}/copy-to-sizes`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
          },
          body: JSON.stringify({ target_size_ids: g.target_size_ids || [] }),
        });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d.detail || `HTTP ${res.status}`);
      toast.success(
        `BOM disalin ke ${(d.created || []).length} ukuran dari ukuran ${g.copy_from_size} — ` +
        'periksa & sesuaikan pemakaian tiap ukuran bila perlu.');
      await onReload();
    } catch (e) {
      toast.error(`Gagal menyalin BOM: ${e.message}`);
    }
  };

  return (
    <Modal title={`HPP — ${m.code} · ${m.name}`} onClose={onClose} size="3xl"
      data-testid="costing-detail-modal">
      <div className="space-y-4">
        {/* upah + target margin */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <GlassCard className="p-3 space-y-2">
            <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-primary" /> Upah CMT / jahit per pcs
            </div>
            <div className="flex items-center gap-2">
              <input type="number" min="0" step="100" value={cmt}
                onChange={e => setCmt(e.target.value)} placeholder="kosong = ikut data nyata"
                className={inputCls} data-testid="costing-input-cmt" />
            </div>
            <div className="text-[11px] text-muted-foreground">
              Berlaku: <strong className="text-foreground">{fmtRp(detail.cmt.rate)}</strong>{' '}
              <SourcePill source={detail.cmt.source} /> {detail.cmt.note}
            </div>
            {(detail.cmt.candidates || []).length > 0 && (
              <div className="flex flex-wrap gap-1.5" data-testid="costing-cmt-candidates">
                {detail.cmt.candidates.slice(0, 6).map((c, i) => (
                  <button key={i} onClick={() => setCmt(String(c.rate))}
                    title={`${c.label} — ${c.detail}`}
                    className="text-[10px] px-1.5 py-0.5 rounded-full border border-[var(--glass-border)] hover:bg-primary/10 text-foreground">
                    {fmtRp(c.rate)} · {c.label.slice(0, 22)}
                  </button>
                ))}
              </div>
            )}
          </GlassCard>

          <GlassCard className="p-3 space-y-2">
            <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-primary" /> Upah cutting / internal per pcs
            </div>
            <input type="number" min="0" step="100" value={internal}
              onChange={e => setInternal(e.target.value)} placeholder="kosong = ikut data produksi"
              className={inputCls} data-testid="costing-input-internal" />
            <div className="text-[11px] text-muted-foreground">
              Berlaku: <strong className="text-foreground">{fmtRp(detail.internal_labor.rate)}</strong>{' '}
              <SourcePill source={detail.internal_labor.source} /> {detail.internal_labor.note}
            </div>
            {(detail.internal_labor.processes || []).length > 0 && (
              <div className="text-[10px] text-muted-foreground">
                {detail.internal_labor.processes.map(p =>
                  `${p.process_code} ${fmtRp(p.rate_per_pcs)}`).join(' + ')}
              </div>
            )}
          </GlassCard>

          <GlassCard className="p-3 space-y-2">
            <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-primary" /> Ringkasan
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <div>HPP rata-rata: <strong className="text-foreground">{fmtRp(detail.hpp_model_avg)}</strong>/pcs</div>
              <div>Target margin {fmtPct(detail.target_margin_pct)} ⇒ usulan harga jual{' '}
                <strong className="text-primary">{fmtRp(detail.suggested_price_model)}</strong></div>
              <div>Overhead: {detail.overhead.included
                ? `ikut ${fmtRp(detail.overhead.rate)}/pcs` : 'tidak diikutkan'}</div>
              <div>HPP tersimpan sekarang: {fmtRp(m.hpp_current)}{' '}
                <span className="text-[10px]">({m.hpp_source_current})</span></div>
            </div>
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={saveLabor} disabled={saving} data-testid="costing-save-labor">
                {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Lock className="w-3.5 h-3.5 mr-1" />}
                Kunci upah
              </Button>
              <Button size="sm" variant="outline" onClick={onApply} data-testid="costing-detail-apply">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Hitung &amp; Terapkan
              </Button>
            </div>
          </GlassCard>
        </div>

        {/* kekurangan */}
        {(detail.gaps || []).length > 0 && (
          <GlassCard className="p-3" data-testid="costing-gaps">
            <div className="text-xs font-semibold text-amber-600 dark:text-amber-300 flex items-center gap-1.5 mb-2">
              <AlertTriangle className="w-3.5 h-3.5" /> {detail.gaps.length} kekurangan yang menahan HPP
            </div>
            <ul className="space-y-1.5">
              {detail.gaps.map((g, i) => (
                <li key={i} className="flex items-start justify-between gap-3 text-xs"
                  data-testid={`costing-gap-${g.code}`}>
                  <div className="text-foreground/90">
                    <span className="font-semibold">{GAP_LABEL[g.code] || g.code}</span>
                    <span className="block text-muted-foreground">{g.message}</span>
                  </div>
                  {g.code === 'bom_missing_other_sizes' && g.copy_bom_id ? (
                    <button onClick={() => onCopyBom(g)}
                      className="shrink-0 text-primary hover:underline inline-flex items-center gap-1"
                      data-testid="costing-copy-bom">
                      Salin BOM ke {(g.target_size_ids || []).length} ukuran <ArrowRight className="w-3 h-3" />
                    </button>
                  ) : g.target && g.target !== 'fin-hpp-produk' ? (
                    <button onClick={() => onGoto(g.target)}
                      className="shrink-0 text-primary hover:underline inline-flex items-center gap-1"
                      data-testid={`costing-fix-${g.code}`}>
                      {g.action || 'Perbaiki'} <ArrowRight className="w-3 h-3" />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </GlassCard>
        )}

        {/* per ukuran */}
        <div className="space-y-3">
          {(detail.sizes || []).map(s => (
            <GlassCard key={s.size_id} className="p-3" data-testid={`costing-size-${s.size_code || s.size_id}`}>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Layers className="w-4 h-4 text-primary" /> Ukuran {s.size_code || '—'}
                  {s.bom_id ? (
                    <span className="text-[10px] text-muted-foreground font-normal">
                      BOM v{s.bom_version} · {s.line_count} baris bahan
                    </span>
                  ) : (
                    <span className="text-[10px] text-red-500 font-normal">BOM belum ada</span>
                  )}
                </div>
                <div className="text-xs text-foreground flex items-center gap-3 flex-wrap">
                  {s.bom_id ? (
                    <>
                      <span>Bahan <strong>{fmtRp(s.material_cost)}</strong></span>
                      <span>CMT <strong>{fmtRp(s.cmt_cost)}</strong></span>
                      <span>Internal <strong>{fmtRp(s.internal_labor_cost)}</strong></span>
                      {s.overhead_cost > 0 && <span>Overhead <strong>{fmtRp(s.overhead_cost)}</strong></span>}
                      <span className="text-primary">HPP <strong>{fmtRp(s.hpp_unit)}</strong>/pcs</span>
                      <span>Usulan jual <strong>{fmtRp(s.suggested_price)}</strong></span>
                      {s.margin_known
                        ? <span className={s.margin_pct >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-red-500'}>
                            Margin <strong>{fmtRp(s.margin)}</strong> ({fmtPct(s.margin_pct)})
                          </span>
                        : <span className="text-muted-foreground">
                            {s.has_price ? 'margin belum bisa dihitung (HPP belum lengkap)'
                              : 'harga jual belum ada'}
                          </span>}
                    </>
                  ) : (
                    <span className="text-muted-foreground">
                      Belum bisa dihitung — buat BOM untuk ukuran ini dulu.
                    </span>
                  )}
                </div>
              </div>

              {s.lines?.length > 0 && (
                <div className="overflow-x-auto mt-2">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[10px] text-muted-foreground border-b border-[var(--glass-border)]">
                        <th className="py-1.5 pr-2">Bahan</th>
                        <th className="py-1.5 pr-2">Jenis</th>
                        <th className="py-1.5 pr-2 text-right">Pakai (BOM)</th>
                        <th className="py-1.5 pr-2 text-right">Satuan dasar</th>
                        <th className="py-1.5 pr-2 text-right">Harga satuan</th>
                        <th className="py-1.5 pr-2 text-right">Biaya/pcs</th>
                        <th className="py-1.5">Catatan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.lines.map((ln, i) => {
                        const cs = COST_SOURCE_LABEL[ln.cost_source] || COST_SOURCE_LABEL.none;
                        return (
                          <tr key={i} className="border-b border-[var(--glass-border)]/50">
                            <td className="py-1.5 pr-2 text-foreground">
                              <span className="font-mono text-[10px]">{ln.code}</span>
                              <span className="block">{ln.name}</span>
                            </td>
                            <td className="py-1.5 pr-2 text-muted-foreground">{ln.material_type}</td>
                            <td className="py-1.5 pr-2 text-right font-mono text-foreground">
                              {fmtNum(ln.qty_input, 4)} {ln.unit_input}
                            </td>
                            <td className="py-1.5 pr-2 text-right font-mono text-foreground">
                              {fmtNum(ln.qty_base, 4)} {ln.unit_base}
                            </td>
                            <td className="py-1.5 pr-2 text-right font-mono text-foreground">
                              {ln.unit_cost > 0 ? fmtRp(ln.unit_cost) : '—'}
                              <span className={`block text-[9px] ${cs.cls}`}>{cs.text}</span>
                            </td>
                            <td className="py-1.5 pr-2 text-right font-mono font-semibold text-foreground">
                              {fmtRp(ln.amount)}
                            </td>
                            <td className="py-1.5 text-muted-foreground">
                              {ln.status === 'unvalued' && (
                                <span className="text-red-500">belum punya harga — belum pernah dibeli</span>)}
                              {ln.status === 'unlinked' && (
                                <span className="text-red-500">belum tertaut master bahan</span>)}
                              {ln.status === 'uom_unclear' && (
                                <span className="text-amber-600 dark:text-amber-300">{ln.uom_note || 'satuan belum jelas'}</span>)}
                              {ln.status === 'ok' && <span className="text-[10px]">{ln.notes || ''}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {s.fg_variants?.length > 0 && s.bom_id && (
                <div className="mt-2 text-[11px] text-muted-foreground">
                  Produk jadi yang ikut diperbarui ({s.fg_variants.length}):{' '}
                  {s.fg_variants.slice(0, 6).map(v => (
                    <span key={v.id} className="mr-2">
                      <span className="font-mono">{v.code}</span>
                      {v.hpp_current > 0 && (
                        <span className="text-emerald-600 dark:text-emerald-300">
                          {' '}(HPP {fmtRp(v.hpp_current)} · {v.hpp_source_current})
                        </span>
                      )}
                    </span>
                  ))}
                  {s.fg_variants.length > 6 && (
                    <span>+{s.fg_variants.length - 6} varian lain</span>
                  )}
                </div>
              )}
            </GlassCard>
          ))}
        </div>

        {/* riwayat penerapan */}
        <div>
          {snapshots === null ? (
            <Button size="sm" variant="ghost" onClick={loadSnapshots} data-testid="costing-load-history">
              <History className="w-3.5 h-3.5 mr-1" /> Lihat riwayat penerapan HPP
            </Button>
          ) : snapshots.length === 0 ? (
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" /> HPP produk ini belum pernah diterapkan.
            </div>
          ) : (
            <GlassCard className="p-3" data-testid="costing-history">
              <div className="text-xs font-semibold text-foreground mb-2">Riwayat penerapan HPP</div>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {snapshots.map(s => (
                  <li key={s.id}>
                    <span className="font-mono text-foreground">{fmtRp(s.hpp_model)}</span>{' '}
                    · {(s.applied_sizes || []).length} ukuran · bahan+upah dari{' '}
                    {s.cmt_source}/{s.internal_labor_source} · {String(s.created_at).slice(0, 16).replace('T', ' ')}
                    {s.created_by_name ? ` · oleh ${s.created_by_name}` : ''}
                  </li>
                ))}
              </ul>
            </GlassCard>
          )}
        </div>
      </div>
    </Modal>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   SETELAN — tarif standar per proses, overhead, target margin
   ═══════════════════════════════════════════════════════════════════════ */
function CostingSettingsModal({ token, onClose, onSaved }) {
  const [rows, setRows] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const d = await costingApi('GET', '/processes', token);
        setRows(d.items || []);
        setSettings(d.settings || null);
      } catch (e) {
        toast.error(`Gagal memuat setelan: ${e.message}`);
      } finally { setLoading(false); }
    })();
  }, [token]);

  const setRate = (pid, v) => setRows(prev => prev.map(r =>
    r.process_id === pid ? { ...r, rate_per_pcs: v } : r));

  const save = async () => {
    setSaving(true);
    try {
      await costingApi('PUT', '/settings', token, {
        overhead_rate_per_pcs: Number(settings.overhead_rate_per_pcs || 0),
        include_overhead_in_product_hpp: !!settings.include_overhead_in_product_hpp,
        target_margin_pct: Number(settings.target_margin_pct || 0),
        labor_rate_fallback_per_pcs: Number(settings.labor_rate_fallback_per_pcs || 0),
        process_rates: rows.filter(r => Number(r.rate_per_pcs) > 0).map(r => ({
          process_id: r.process_id, code: r.code, name: r.name,
          rate_per_pcs: Number(r.rate_per_pcs),
        })),
      });
      toast.success('Setelan upah & margin disimpan.');
      onSaved();
    } catch (e) {
      toast.error(`Gagal menyimpan setelan: ${e.message}`);
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Setelan Upah, Overhead & Target Margin" onClose={onClose} size="lg"
      data-testid="costing-settings-modal">
      {loading || !settings ? (
        <div className="py-8 text-center text-muted-foreground text-sm">Memuat…</div>
      ) : (
        <div className="space-y-4">
          <div className="text-xs text-muted-foreground">
            Tarif standar per proses dipakai HANYA bila produk itu belum punya laporan produksi
            bertarif (upah nyata selalu didahulukan). Proses jahit/CMT tidak diikutkan di sini
            supaya upah CMT tidak dihitung dua kali.
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="py-2">Proses</th>
                  <th className="py-2">Kode</th>
                  <th className="py-2 text-right">Tarif standar / pcs</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.process_id} className="border-b border-[var(--glass-border)]/50">
                    <td className="py-2 text-foreground">
                      {r.name}
                      {r.is_cmt && (
                        <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full border border-amber-300/25 bg-amber-400/10 text-amber-600">
                          dihitung sebagai upah CMT
                        </span>
                      )}
                    </td>
                    <td className="py-2 font-mono text-xs text-muted-foreground">{r.code}</td>
                    <td className="py-2 text-right">
                      <input type="number" min="0" step="100" value={r.rate_per_pcs || ''}
                        onChange={e => setRate(r.process_id, e.target.value)}
                        disabled={r.is_cmt}
                        className={`${inputCls} w-28 text-right inline-block disabled:opacity-40`}
                        data-testid={`costing-rate-${r.code}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-foreground/80">Overhead per pcs</span>
              <input type="number" min="0" step="100" value={settings.overhead_rate_per_pcs}
                onChange={e => setSettings({ ...settings, overhead_rate_per_pcs: e.target.value })}
                className={`${inputCls} mt-1`} data-testid="costing-setting-overhead" />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-foreground/80">Target margin bawaan (%)</span>
              <input type="number" min="0" max="99" step="1" value={settings.target_margin_pct}
                onChange={e => setSettings({ ...settings, target_margin_pct: e.target.value })}
                className={`${inputCls} mt-1`} data-testid="costing-setting-margin" />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-foreground/80">Tarif cadangan upah/pcs</span>
              <input type="number" min="0" step="100" value={settings.labor_rate_fallback_per_pcs}
                onChange={e => setSettings({ ...settings, labor_rate_fallback_per_pcs: e.target.value })}
                className={`${inputCls} mt-1`} data-testid="costing-setting-fallback" />
            </label>
          </div>

          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input type="checkbox" checked={!!settings.include_overhead_in_product_hpp}
              onChange={e => setSettings({ ...settings, include_overhead_in_product_hpp: e.target.checked })}
              data-testid="costing-setting-include-overhead" />
            Ikutkan overhead ke HPP produk secara bawaan
            <span className="text-xs text-muted-foreground">(keputusan pemilik: default MATI)</span>
          </label>

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose} data-testid="costing-settings-cancel">Batal</Button>
            <Button onClick={save} disabled={saving} data-testid="costing-settings-save">
              {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null} Simpan setelan
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
