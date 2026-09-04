/**
 * DocNumberingModule — Penomoran Dokumen & SKU.
 * Owner mengatur format nomor tiap jenis dokumen. Modul ini TIDAK membuat
 * nomor sendiri: format disimpan lalu dibaca generator resmi di backend
 * (`utils/counters.gen_prefixed_number`), jadi tidak ada dua sumber kebenaran.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Hash, RefreshCw, Loader2, Save, RotateCcw, AlertCircle, Check, ListOrdered } from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from './moduleAtoms';

const API = process.env.REACT_APP_BACKEND_URL || '';
const BASE = `${API}/api/admin/doc-numbering`;

const TOKEN_HELP = [
  ['{YYYY}', 'tahun 4 digit — 2026'],
  ['{YY}', 'tahun 2 digit — 26'],
  ['{MM}', 'bulan — 07'],
  ['{DD}', 'tanggal — 27'],
  ['{SEQ:4}', 'nomor urut 4 digit — 0001 (wajib di akhir)'],
];

export default function DocNumberingModule({ token }) {
  const [items, setItems] = useState([]);
  const [groups, setGroups] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [previews, setPreviews] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [filter, setFilter] = useState('');
  const [counterFor, setCounterFor] = useState(null);
  const [counterVal, setCounterVal] = useState('');

  const h = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(BASE, { headers: h });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      const d = await r.json();
      setItems(d.items || []);
      setGroups(d.groups || []);
      setDrafts({});
      setPreviews({});
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, [h]);

  useEffect(() => { load(); }, [load]);

  const preview = async (key, format) => {
    try {
      const r = await fetch(`${BASE}/preview`, { method: 'POST', headers: h, body: JSON.stringify({ key, format }) });
      const d = await r.json();
      setPreviews(p => ({ ...p, [key]: d }));
    } catch (e) { /* pratinjau bersifat bantu, abaikan gangguan sesaat */ }
  };

  const onDraft = (key, format) => {
    setDrafts(d => ({ ...d, [key]: format }));
    preview(key, format);
  };

  const save = async (item) => {
    const format = drafts[item.key];
    setBusy(item.key);
    try {
      const r = await fetch(BASE, { method: 'PUT', headers: h, body: JSON.stringify({ key: item.key, format, active: true }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`Format ${item.label} disimpan — contoh: ${d.contoh}`);
      await load();
    } catch (e) { toast.error(e.message); } finally { setBusy(''); }
  };

  // FASE G (2026-08-16) — pindah mode OTOMATIS ⇄ MANUAL.
  // Otomatis: nomor dibuat sistem, kolom nomor di form dokumen dikunci.
  // Manual: nomor diketik, TETAPI wajib mengikuti pola format di sebelah —
  // itulah yang menghentikan nomor bebas seperti `PO-MKL-GAB-A` masuk arsip.
  const setMode = async (item, mode) => {
    if (mode === item.mode) return;
    setBusy(item.key);
    try {
      const r = await fetch(BASE, {
        method: 'PUT', headers: h,
        body: JSON.stringify({ key: item.key, mode, active: true }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(mode === 'auto'
        ? `${item.label}: nomor dibuat OTOMATIS oleh sistem`
        : `${item.label}: nomor DIKETIK, wajib mengikuti pola ${d.format}`);
      await load();
    } catch (e) { toast.error(e.message); } finally { setBusy(''); }
  };

  const reset = async (item) => {
    setBusy(item.key);
    try {
      const r = await fetch(`${BASE}/${item.key}`, { method: 'DELETE', headers: h });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      toast.success(`${item.label} kembali ke format bawaan`);
      await load();
    } catch (e) { toast.error(e.message); } finally { setBusy(''); }
  };

  const saveCounter = async () => {
    setBusy(counterFor.key);
    try {
      const r = await fetch(`${BASE}/counter`, {
        method: 'POST', headers: h,
        body: JSON.stringify({ key: counterFor.key, start_from: Number(counterVal) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`Nomor berikutnya: ${d.nomor_berikutnya}`);
      setCounterFor(null); setCounterVal('');
      await load();
    } catch (e) { toast.error(e.message); } finally { setBusy(''); }
  };

  const visible = items.filter(i => {
    const q = filter.trim().toLowerCase();
    return !q || i.label.toLowerCase().includes(q) || i.key.toLowerCase().includes(q) || i.group.toLowerCase().includes(q);
  });
  const customCount = items.filter(i => i.is_custom).length;

  if (loading) {
    return <div className="flex items-center justify-center py-20" data-testid="docnum-loading">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-6" data-testid="doc-numbering-module">
      <PageHeader
        icon={Hash}
        eyebrow="Administrasi Sistem"
        title="Penomoran Dokumen & SKU"
        subtitle={`${items.length} jenis dokumen · ${customCount} memakai format khusus. Perubahan hanya berlaku untuk dokumen BARU.`}
        actions={<Button variant="outline" size="sm" onClick={load} data-testid="docnum-refresh">
          <RefreshCw className="w-4 h-4 mr-2" />Muat Ulang</Button>}
        testId="docnum-header"
      />

      <GlassCard className="p-4">
        <p className="text-sm font-semibold mb-3 flex items-center gap-2"><ListOrdered className="w-4 h-4" />Token yang bisa dipakai</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {TOKEN_HELP.map(([t, d]) => (
            <div key={t} className="flex items-baseline gap-2 text-xs">
              <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-[11px]">{t}</code>
              <span className="text-muted-foreground">{d}</span>
            </div>
          ))}
        </div>
      </GlassCard>

      <Input placeholder="Cari jenis dokumen…" value={filter} onChange={e => setFilter(e.target.value)}
        className="max-w-sm" data-testid="docnum-search" />

      {groups.filter(g => visible.some(i => i.group === g)).map(group => (
        <div key={group} className="space-y-2">
          <h2 className="text-base font-semibold text-foreground/70">{group}</h2>
          <div className="space-y-2">
            {visible.filter(i => i.group === group).map(item => {
              const draft = drafts[item.key];
              const changed = draft !== undefined && draft !== item.format;
              const pv = previews[item.key];
              return (
                <GlassCard key={item.key} className="p-4" data-testid={`docnum-row-${item.key}`}>
                  <div className="flex flex-wrap items-start gap-4">
                    <div className="min-w-[190px] flex-1">
                      <p className="font-medium text-sm">{item.label}</p>
                      <p className="text-[11px] text-muted-foreground font-mono">{item.key}</p>
                      {item.catatan && <p className="text-[11px] text-muted-foreground mt-1">{item.catatan}</p>}
                      {item.tokens?.length > 0 && (
                        <p className="text-[11px] mt-1">Token khusus: {item.tokens.map(t => (
                          <code key={t} className="mx-0.5 px-1 rounded bg-muted font-mono">{'{' + t + '}'}</code>
                        ))}</p>
                      )}
                    </div>

                    <div className="flex-1 min-w-[240px] space-y-1.5">
                      <Input
                        value={draft !== undefined ? draft : item.format}
                        onChange={e => onDraft(item.key, e.target.value)}
                        className="font-mono text-sm"
                        data-testid={`docnum-input-${item.key}`}
                      />
                      <div className="flex items-center gap-2 text-[11px]">
                        {pv && !pv.ok
                          ? <span className="text-destructive flex items-center gap-1" data-testid="docnum-error"><AlertCircle className="w-3 h-3" />{pv.error}</span>
                          : <span className="text-muted-foreground">Contoh: <span className="font-mono text-foreground" data-testid={`docnum-sample-${item.key}`}>{pv?.contoh || item.contoh || '—'}</span></span>}
                        {item.is_custom && !changed && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary flex items-center gap-1"><Check className="w-3 h-3" />khusus</span>}
                      </div>
                      {item.nomor_terakhir != null && (
                        <p className="text-[11px] text-muted-foreground">Nomor urut terakhir terpakai: <b>{item.nomor_terakhir}</b></p>
                      )}
                    </div>

                    {/* FASE G — mode penomoran per jenis dokumen.
                        SESI #18 — KEJUJURAN: mode hanya bisa dipindah untuk jenis dokumen
                        yang JALUR TULISNYA sudah menegakkan kebijakan (`policy_enforced`).
                        Sebelum ini togglenya tampil untuk SEMUA 49 jenis padahal hanya
                        beberapa yang menegakkannya ⇒ owner memindah ke "Manual", tidak
                        terjadi apa pun, dan setelan itu berbohong. Sekarang jenis yang
                        belum ditegakkan mengatakannya terang-terangan. */}
                    <div className="min-w-[190px] space-y-1">
                      {item.policy_enforced ? (
                        <>
                          <div className="inline-flex rounded-lg border border-border overflow-hidden">
                            {[['auto', 'Otomatis'], ['manual', 'Manual']].map(([m, lbl]) => (
                              <button key={m} onClick={() => setMode(item, m)} disabled={busy === item.key}
                                data-testid={`docnum-mode-${item.key}-${m}`}
                                className={`px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                  item.mode === m
                                    ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
                                    : 'bg-transparent text-muted-foreground hover:text-foreground'}`}>
                                {lbl}
                              </button>
                            ))}
                          </div>
                          <p className="text-[11px] text-muted-foreground" data-testid={`docnum-mode-hint-${item.key}`}>
                            {item.mode === 'manual'
                              ? 'Nomor diketik petugas — yang tidak sesuai pola ditolak.'
                              : 'Nomor dibuat sistem — kolom nomor di form dikunci.'}
                            {item.mode_is_custom && item.mode !== item.mode_default && (
                              <span className="text-primary"> (bawaan: {item.mode_default === 'auto' ? 'otomatis' : 'manual'})</span>
                            )}
                          </p>
                        </>
                      ) : (
                        <>
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-[11px] font-semibold text-amber-800 dark:text-amber-200"
                            data-testid={`docnum-mode-locked-${item.key}`}>
                            {item.auto_only ? 'Selalu otomatis' : 'Otomatis saja'}
                          </span>
                          <p className="text-[11px] text-muted-foreground" data-testid={`docnum-mode-hint-${item.key}`}>
                            {item.auto_only ? (
                              /* SESI #19 — dokumen yang LAHIR TANPA MANUSIA: sebutkan
                                 alasannya apa adanya, jangan menjanjikan "nanti bisa". */
                              <>{item.alasan_otomatis || 'Dokumen ini dibuat sistem, bukan diketik.'}{' '}
                                Formatnya tetap bisa diubah di sini.</>
                            ) : (
                              <>Jalur dokumen ini <b>belum menegakkan</b> mode manual, jadi pilihannya
                                belum ditampilkan agar setelan tidak berbohong. Formatnya tetap berlaku.</>
                            )}
                          </p>
                        </>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <Button size="sm" disabled={!changed || (pv && !pv.ok) || busy === item.key}
                        onClick={() => save(item)} data-testid={`docnum-save-${item.key}`}>
                        {busy === item.key ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Save className="w-4 h-4 mr-1.5" />Simpan</>}
                      </Button>
                      {item.is_custom && (
                        <Button size="sm" variant="outline" onClick={() => reset(item)}
                          disabled={busy === item.key} data-testid={`docnum-reset-${item.key}`}>
                          <RotateCcw className="w-4 h-4 mr-1.5" />Bawaan
                        </Button>
                      )}
                      {item.sequenced !== false && (
                        <Button size="sm" variant="ghost" onClick={() => { setCounterFor(item); setCounterVal(String(item.nomor_terakhir || 0)); }}
                          data-testid={`docnum-counter-${item.key}`}>
                          <ListOrdered className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        </div>
      ))}

      {counterFor && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setCounterFor(null)}>
          <GlassCard className="p-5 w-full max-w-md space-y-4" onClick={e => e.stopPropagation()} data-testid="docnum-counter-dialog">
            <div>
              <h3 className="font-semibold">Setel Nomor Urut — {counterFor.label}</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Nomor dokumen berikutnya = angka ini + 1. Menurunkan angka ditolak bila
                sudah ada dokumen memakai awalan yang sama (mencegah nomor ganda).
              </p>
            </div>
            <Input type="number" min={0} value={counterVal} onChange={e => setCounterVal(e.target.value)}
              data-testid="docnum-counter-input" />
            {Number(counterVal) - (counterFor.nomor_terakhir || 0) > 100 && (
              <p className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-500" data-testid="docnum-counter-warning">
                <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Lompatan besar: dari {counterFor.nomor_terakhir || 0} ke {counterVal}. Nomor di antaranya
                tidak akan pernah terpakai. Pastikan ini memang disengaja.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setCounterFor(null)} data-testid="docnum-counter-cancel">Batal</Button>
              <Button size="sm" onClick={saveCounter} disabled={counterVal === '' || busy === counterFor.key} data-testid="docnum-counter-save">
                {busy === counterFor.key ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Simpan'}
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
