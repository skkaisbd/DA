import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Ruler, Wand2, RefreshCw, AlertTriangle, CheckCircle2, Link2,
  ChevronDown, ChevronRight, Layers, Info, PackageCheck,
} from 'lucide-react';
import { toast } from '../ui/sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';

/** Nilai khusus dropdown: buat ukuran baru di master (bukan memilih yang ada). */
const NEW_SIZE = '__new__';

async function readErr(res, fallback) {
  try { const d = await res.json(); return d?.detail || fallback; } catch { return fallback; }
}

/**
 * Padankan Ukuran — memetakan ukuran R&D yang masih "belum dipadankan" ke master
 * produksi (`rahaza_sizes`).
 *
 * Kenapa layar ini ada: ukuran R&D sengaja BEBAS (kebijakan B1), tapi PO produksi
 * internal MEWAJIBKAN `size_id` yang sah. Selain memblokir PO, ukuran yang belum
 * dipadankan juga membuat promosi style ke produksi menambah ukuran master BARU —
 * sehingga master bisa punya `ALLSIZE` dan `ALL SIZE` sekaligus dan SKU FG pecah.
 * Satu klik di sini menutup keduanya.
 */
export default function RnDSizeMappingModule({ token }) {
  const hdr = useMemo(
    () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }),
    [token],
  );

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [createMissing, setCreateMissing] = useState(true);
  const [choice, setChoice] = useState({});      // label → size_id | NEW_SIZE
  const [newCode, setNewCode] = useState({});    // label → kode master usulan
  const [picked, setPicked] = useState({});      // label → boolean (batch)
  const [showMatched, setShowMatched] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/size-mapping`, { headers: hdr });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal memuat pemadanan ukuran')); return; }
      const d = await res.json();
      setData(d);
      // Pilihan awal = saran sistem bila ada, kalau tidak → buat baru di master.
      const c = {}, n = {};
      (d.items || []).forEach(it => {
        c[it.label] = it.suggestion ? it.suggestion.size_id : NEW_SIZE;
        n[it.label] = it.proposed_new_code || '';
      });
      setChoice(c); setNewCode(n); setPicked({});
    } catch { toast.error('Gagal memuat pemadanan ukuran'); }
    finally { setLoading(false); }
  }, [hdr]);

  useEffect(() => { load(); }, [load]);

  const applyMappings = async (mappings, label) => {
    if (!mappings.length) { toast.error('Belum ada ukuran yang dipilih.'); return; }
    setBusy(label);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/size-mapping/apply`, {
        method: 'POST', headers: hdr, body: JSON.stringify({ mappings }),
      });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal memadankan ukuran')); return; }
      const out = await res.json();
      toast.success(
        `${out.applied} ukuran dipadankan · ${out.styles_updated} style & ` +
        `${out.variants_affected} varian ikut diperbarui` +
        (out.unmatched_after === 0 ? ' — tidak ada lagi yang tertahan' : ''),
      );
      await load();
    } catch { toast.error('Gagal memadankan ukuran'); }
    finally { setBusy(''); }
  };

  const rowMapping = (it) => {
    const sel = choice[it.label];
    if (sel === NEW_SIZE || !sel) {
      return { label: it.label, create_new: true, code: (newCode[it.label] || '').trim() };
    }
    return { label: it.label, size_id: sel };
  };

  const applyRow = (it) => applyMappings([rowMapping(it)], it.label);

  const applySelected = () => {
    const rows = (data?.items || []).filter(it => picked[it.label]);
    applyMappings(rows.map(rowMapping), '__selected__');
  };

  const autoAll = async () => {
    setBusy('__auto__');
    try {
      const res = await fetch(`${API}/api/dewi/rnd/size-mapping/auto`, {
        method: 'POST', headers: hdr, body: JSON.stringify({ create_missing: createMissing }),
      });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal memadankan otomatis')); return; }
      const out = await res.json();
      if (out.applied === 0 && (out.skipped || []).length) {
        toast.warning(
          `${out.skipped.length} ukuran tidak punya padanan di master: ${out.skipped.join(', ')}. ` +
          `Aktifkan "buat ukuran baru di master" atau pilih padanannya satu per satu.`,
        );
      } else {
        toast.success(
          `${out.applied} ukuran dipadankan (${out.unmatched_before} → ${out.unmatched_after} tertahan) · ` +
          `${out.styles_updated} style, ${out.variants_affected} varian`,
        );
      }
      await load();
    } catch { toast.error('Gagal memadankan otomatis'); }
    finally { setBusy(''); }
  };

  const items = data?.items || [];
  const pickedCount = items.filter(it => picked[it.label]).length;
  const allClear = !loading && data && items.length === 0;

  return (
    <div className="p-6" data-testid="rnd-size-mapping-module">
      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Ruler className="w-5 h-5 text-violet-500" /> Padankan Ukuran
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            Hubungkan ukuran R&amp;D yang ditulis bebas ke master ukuran produksi — supaya
            style bisa naik ke PO tanpa tertahan
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={load} disabled={loading || !!busy}
            className="gap-2" data-testid="rnd-size-mapping-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
          </Button>
          <Button onClick={autoAll} disabled={loading || !!busy || items.length === 0}
            className="gap-2" data-testid="rnd-size-mapping-auto-btn">
            <Wand2 className="w-4 h-4" />
            {busy === '__auto__' ? 'Memadankan…' : 'Padankan Semua'}
          </Button>
        </div>
      </div>

      {/* ── Kenapa ini penting ── */}
      <GlassCard className="p-4 mb-5 border-sky-300 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-500/10">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-sky-600 dark:text-sky-400 mt-0.5 flex-shrink-0" />
          <div className="text-xs text-sky-900/80 dark:text-sky-200/80 leading-relaxed">
            Ukuran di R&amp;D memang <b>bebas ditulis</b> (mis. <span className="font-mono">All Size</span>,
            <span className="font-mono"> 28/30</span>) — itu tidak diubah oleh layar ini.
            Tapi <b>PO produksi internal mewajibkan ukuran yang ada di master</b>. Selama sebuah
            ukuran belum dipadankan, style yang memakainya akan tertahan saat masuk PO, dan
            saat dipromosikan sistem akan menambah ukuran master baru — sehingga master bisa
            punya dua ukuran yang sebenarnya sama.
          </div>
        </div>
      </GlassCard>

      {/* ── Ringkasan ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {[
          { k: 'unmatched_labels', label: 'Belum dipadankan', icon: AlertTriangle,
            cls: items.length > 0
              ? 'text-amber-600 dark:text-amber-400'
              : 'text-emerald-600 dark:text-emerald-400' },
          { k: 'blocked_styles', label: 'Style tertahan', icon: Layers, cls: 'text-red-600 dark:text-red-400' },
          { k: 'matched_labels', label: 'Sudah dipadankan', icon: CheckCircle2, cls: 'text-emerald-600 dark:text-emerald-400' },
          { k: 'variants_scanned', label: 'Varian diperiksa', icon: PackageCheck, cls: 'text-foreground/70' },
        ].map(({ k, label, icon: Icon, cls }) => (
          <GlassCard key={k} className="p-4" data-testid={`rnd-size-stat-${k}`}>
            <div className="flex items-center gap-2 text-xs text-foreground/50 mb-1">
              <Icon className="w-3.5 h-3.5" /> {label}
            </div>
            <div className={`text-2xl font-bold ${cls}`}>{data?.[k] ?? '—'}</div>
          </GlassCard>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : allClear ? (
        <GlassCard className="p-10 text-center border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/10"
          data-testid="rnd-size-mapping-allclear">
          <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
          <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
            Semua ukuran sudah dipadankan ke master produksi.
          </p>
          <p className="text-xs text-emerald-700/80 dark:text-emerald-300/80 mt-1">
            Tidak ada style yang tertahan karena ukuran. {data?.matched_labels ?? 0} label
            ukuran terhubung ke master, {data?.variants_scanned ?? 0} varian diperiksa.
          </p>
        </GlassCard>
      ) : (
        <>
          {/* ── Aksi batch ── */}
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-foreground/70 cursor-pointer">
              <input type="checkbox" checked={createMissing}
                onChange={e => setCreateMissing(e.target.checked)}
                className="rounded border-input"
                data-testid="rnd-size-mapping-create-missing" />
              Boleh membuat ukuran baru di master bila tidak ada padanannya
            </label>
            <Button variant="outline" size="sm" onClick={applySelected}
              disabled={pickedCount === 0 || !!busy}
              className="h-8 text-xs gap-1" data-testid="rnd-size-mapping-apply-selected">
              <Link2 className="w-3 h-3" />
              {busy === '__selected__' ? 'Memadankan…' : `Padankan Terpilih (${pickedCount})`}
            </Button>
          </div>

          {/* ── Tabel label belum dipadankan ── */}
          <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead className="bg-foreground/5 border-b border-foreground/10">
                <tr>
                  <th className="px-3 py-3 w-10">
                    <input type="checkbox"
                      checked={pickedCount > 0 && pickedCount === items.length}
                      onChange={e => {
                        const all = {};
                        if (e.target.checked) items.forEach(it => { all[it.label] = true; });
                        setPicked(all);
                      }}
                      className="rounded border-input"
                      data-testid="rnd-size-mapping-pick-all" />
                  </th>
                  {['Ukuran R&D', 'Dipakai oleh', 'Terbaca dari', 'Padankan ke', 'Aksi'].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map(it => {
                  const sel = choice[it.label];
                  const isNew = sel === NEW_SIZE || !sel;
                  return (
                    <tr key={it.label} className="border-b border-foreground/5 last:border-0 hover:bg-foreground/[0.03] align-top"
                      data-testid={`rnd-size-row-${it.label}`}>
                      <td className="px-3 py-3">
                        <input type="checkbox" checked={!!picked[it.label]}
                          onChange={e => setPicked(p => ({ ...p, [it.label]: e.target.checked }))}
                          className="rounded border-input"
                          data-testid={`rnd-size-pick-${it.label}`} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-1 rounded-md font-mono text-sm font-bold
                          bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-200
                          border border-amber-300 dark:border-amber-500/40">
                          {it.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {it.styles.length === 0 ? (
                          <span className="text-xs text-foreground/40">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1 max-w-[240px]">
                            {it.styles.slice(0, 3).map(s => (
                              <span key={s.style_id} title={s.style_name}
                                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">
                                {s.style_code || s.style_id.slice(0, 6)}
                              </span>
                            ))}
                            {it.styles.length > 3 && (
                              <span className="text-[10px] px-1.5 py-0.5 text-foreground/50">
                                +{it.styles.length - 3} lagi
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {it.from_size_list && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded border border-sky-300 dark:border-sky-500/40 bg-sky-100 dark:bg-sky-500/20 text-sky-700 dark:text-sky-300">
                              daftar ukuran
                            </span>
                          )}
                          {it.from_variants && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded border border-violet-300 dark:border-violet-500/40 bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                              varian
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 min-w-[260px]">
                        <SmartNativeSelect
                          value={sel || NEW_SIZE}
                          onChange={e => setChoice(c => ({ ...c, [it.label]: e.target.value }))}
                          className="w-full"
                          data-testid={`rnd-size-target-${it.label}`}>
                          <option value={NEW_SIZE}>+ Buat ukuran baru di master…</option>
                          {(data?.master_sizes || []).map(m => (
                            <option key={m.size_id} value={m.size_id}>
                              {m.code}{m.name && m.name !== m.code ? ` — ${m.name}` : ''}
                            </option>
                          ))}
                        </SmartNativeSelect>

                        {isNew ? (
                          <div className="mt-2 flex items-center gap-2">
                            <span className="text-[10px] text-foreground/50 whitespace-nowrap">Kode master</span>
                            <Input value={newCode[it.label] ?? ''}
                              onChange={e => setNewCode(n => ({ ...n, [it.label]: e.target.value }))}
                              className="h-7 text-xs font-mono"
                              placeholder={it.proposed_new_code || 'KODE'}
                              data-testid={`rnd-size-newcode-${it.label}`} />
                          </div>
                        ) : it.suggestion && it.suggestion.size_id === sel ? (
                          <div className="mt-1.5 text-[10px] text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> saran sistem: {it.suggestion.reason}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <Button size="sm" variant="outline" disabled={!!busy}
                          onClick={() => applyRow(it)}
                          className="h-7 text-xs gap-1 whitespace-nowrap"
                          data-testid={`rnd-size-apply-${it.label}`}>
                          <Link2 className="w-3 h-3" />
                          {busy === it.label ? 'Memadankan…' : 'Padankan'}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Yang sudah dipadankan (transparansi) ── */}
      {!loading && (data?.matched || []).length > 0 && (
        <div className="mt-5">
          <button type="button" onClick={() => setShowMatched(v => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-foreground/60 hover:text-foreground transition-colors"
            data-testid="rnd-size-mapping-matched-toggle">
            {showMatched ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            {data.matched.length} ukuran sudah terhubung ke master
          </button>
          {showMatched && (
            <GlassCard className="p-4 mt-2" data-testid="rnd-size-mapping-matched-panel">
              <div className="flex flex-wrap gap-2">
                {data.matched.map(m => (
                  <span key={m.label}
                    className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md
                      bg-emerald-100 dark:bg-emerald-500/15 text-emerald-800 dark:text-emerald-200
                      border border-emerald-300 dark:border-emerald-500/30">
                    <span className="font-mono font-semibold">{m.label}</span>
                    <span className="opacity-50">→</span>
                    <span className="font-mono">{m.code}</span>
                  </span>
                ))}
              </div>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
