/**
 * DatabaseCollectionsPanel — jelajah koleksi database aktif & pengosongan terpilih.
 * Dipakai di dalam BackupRestoreModule (tab "Koleksi Database").
 *
 * Sengaja berlapis pengaman: koleksi fondasi (pengguna, hak akses, counter,
 * bagan akun) terkunci, wajib mengetik KOSONGKAN, dan cadangan pengaman dibuat
 * lebih dulu secara bawaan.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, RefreshCw, Loader2, Lock, Trash2, AlertTriangle, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const API = process.env.REACT_APP_BACKEND_URL || '';

export default function DatabaseCollectionsPanel({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState([]);
  const [filter, setFilter] = useState('');
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [createBackup, setCreateBackup] = useState(true);
  const [allowProtected, setAllowProtected] = useState(false);
  const [unlocked, setUnlocked] = useState(false);
  const [busy, setBusy] = useState(false);

  const h = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/admin/backup/live-collections`, { headers: h });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      setData(await r.json());
      setSelected([]);
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  }, [h]);

  useEffect(() => { load(); }, [load]);

  const toggle = (name) => setSelected(s => s.includes(name) ? s.filter(x => x !== name) : [...s, name]);

  // Koleksi fondasi tetap terlihat, tapi baru bisa dicentang setelah kunci dibuka
  // secara sadar. Backend juga menolaknya lagi (pengaman berlapis).
  const lockedFor = (c) => c.protected && !unlocked;

  const visible = (data?.collections || []).filter(c => {
    const q = filter.trim().toLowerCase();
    return !q || c.name.toLowerCase().includes(q) || c.group.toLowerCase().includes(q);
  });

  const toggleGroup = (group) => {
    const names = visible.filter(c => c.group === group && !c.protected).map(c => c.name);
    const allOn = names.every(n => selected.includes(n));
    setSelected(s => allOn ? s.filter(n => !names.includes(n)) : [...new Set([...s, ...names])]);
  };

  const selectedDocs = selected.reduce((sum, n) =>
    sum + ((data?.collections || []).find(c => c.name === n)?.count || 0), 0);
  const selectedProtected = selected.filter(n =>
    (data?.collections || []).find(c => c.name === n)?.protected);

  const runClear = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/admin/backup/clear-collections`, {
        method: 'POST', headers: h,
        body: JSON.stringify({
          collections: selected, confirm_text: confirmText,
          create_backup: createBackup, allow_protected: allowProtected,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`${d.cleared.length} koleksi dikosongkan · ${d.total_deleted} dokumen dihapus`
        + (d.safety_backup ? ` · cadangan: ${d.safety_backup}` : ''));
      if (d.failed?.length) toast.error(`${d.failed.length} koleksi gagal dikosongkan`);
      setShowConfirm(false); setConfirmText(''); setAllowProtected(false);
      await load();
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-16" data-testid="collections-loading">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-4" data-testid="db-collections-panel">
      <GlassCard className="p-4 flex flex-wrap items-center gap-3">
        <Database className="w-5 h-5 text-primary" />
        <div className="flex-1 min-w-[200px]">
          <p className="text-sm font-semibold" data-testid="collections-summary">
            {data?.total_collections} koleksi · {data?.total_documents?.toLocaleString('id-ID')} dokumen
          </p>
          <p className="text-xs text-muted-foreground">Database aktif: <span className="font-mono">{data?.database}</span></p>
        </div>
        <Input placeholder="Cari koleksi…" value={filter} onChange={e => setFilter(e.target.value)}
          className="max-w-xs" data-testid="collections-search" />
        <Button variant="outline" size="sm" onClick={load} data-testid="collections-refresh">
          <RefreshCw className="w-4 h-4 mr-1.5" />Muat Ulang
        </Button>
        <label className="flex items-center gap-2 text-xs text-muted-foreground w-full sm:w-auto">
          <input type="checkbox" checked={unlocked}
            onChange={e => { setUnlocked(e.target.checked); if (!e.target.checked) setSelected(sel => sel.filter(n => !(data?.collections || []).find(c => c.name === n)?.protected)); }}
            data-testid="collections-unlock-protected" />
          <Lock className="w-3 h-3 text-amber-500" />Buka kunci koleksi terlindungi
        </label>
      </GlassCard>

      {selected.length > 0 && (
        <GlassCard className="p-4 border-destructive/40 bg-destructive/5 flex flex-wrap items-center gap-3" data-testid="collections-action-bar">
          <AlertTriangle className="w-5 h-5 text-destructive" />
          <p className="text-sm flex-1">
            <b>{selected.length}</b> koleksi dipilih · <b>{selectedDocs.toLocaleString('id-ID')}</b> dokumen akan dihapus
            {selectedProtected.length > 0 && <span className="text-destructive"> · {selectedProtected.length} di antaranya koleksi terlindungi</span>}
          </p>
          <Button variant="ghost" size="sm" onClick={() => setSelected([])} data-testid="collections-clear-selection">Batal pilih</Button>
          <Button variant="destructive" size="sm" onClick={() => setShowConfirm(true)} data-testid="collections-clear-btn">
            <Trash2 className="w-4 h-4 mr-1.5" />Kosongkan
          </Button>
        </GlassCard>
      )}

      {(data?.groups || []).filter(g => visible.some(c => c.group === g)).map(group => (
        <GlassCard key={group} className="p-4" data-testid={`collections-group-${group}`}>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-foreground/70">{group}</h3>
            <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => toggleGroup(group)}>
              Pilih semua yang boleh
            </Button>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
            {visible.filter(c => c.group === group).map(c => (
              <label key={c.name}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors ${
                  lockedFor(c) ? 'opacity-50 cursor-not-allowed'
                    : selected.includes(c.name) ? 'bg-destructive/10 cursor-pointer' : 'hover:bg-muted/50 cursor-pointer'}`}
                title={lockedFor(c) ? 'Koleksi fondasi — buka kuncinya dulu di atas' : undefined}
                data-testid={`collection-item-${c.name}`}>
                <input type="checkbox" checked={selected.includes(c.name)} onChange={() => toggle(c.name)}
                  disabled={lockedFor(c)}
                  className="accent-[hsl(var(--destructive))]" data-testid={`collection-check-${c.name}`} />
                <span className="font-mono truncate flex-1">{c.name}</span>
                {c.protected && <Lock className="w-3 h-3 text-amber-500 flex-shrink-0" aria-label="terlindungi" />}
                <span className="text-muted-foreground tabular-nums">{c.count.toLocaleString('id-ID')}</span>
              </label>
            ))}
          </div>
        </GlassCard>
      ))}

      {showConfirm && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => !busy && setShowConfirm(false)}>
          <GlassCard className="p-6 max-w-lg w-full space-y-4" onClick={e => e.stopPropagation()} data-testid="clear-confirm-dialog">
            <div className="flex items-start gap-3">
              <ShieldAlert className="w-6 h-6 text-destructive flex-shrink-0" />
              <div>
                <h2 className="text-lg font-bold">Kosongkan {selected.length} koleksi?</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  <b>{selectedDocs.toLocaleString('id-ID')}</b> dokumen akan dihapus permanen dari database aktif.
                  Struktur koleksi tetap ada, isinya saja yang dikosongkan.
                </p>
              </div>
            </div>

            <div className="max-h-32 overflow-y-auto rounded-md bg-muted/40 p-2 text-xs font-mono space-y-0.5">
              {selected.map(n => <div key={n}>{n}</div>)}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={createBackup} onChange={e => setCreateBackup(e.target.checked)}
                data-testid="clear-backup-toggle" />
              Buat cadangan pengaman dulu <span className="text-muted-foreground text-xs">(sangat disarankan)</span>
            </label>

            {selectedProtected.length > 0 && (
              <label className="flex items-start gap-2 text-sm text-destructive">
                <input type="checkbox" checked={allowProtected} onChange={e => setAllowProtected(e.target.checked)}
                  className="mt-0.5" data-testid="clear-protected-toggle" />
                <span>Izinkan koleksi terlindungi ({selectedProtected.join(', ')}). Ini bisa membuat sistem tidak bisa dipakai.</span>
              </label>
            )}

            <div>
              <p className="text-xs text-muted-foreground mb-1">Ketik <b>KOSONGKAN</b> untuk melanjutkan:</p>
              <Input value={confirmText} onChange={e => setConfirmText(e.target.value)}
                placeholder="KOSONGKAN" className="font-mono" data-testid="clear-confirm-input" />
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowConfirm(false)} disabled={busy} data-testid="clear-cancel">Batal</Button>
              <Button variant="destructive" size="sm" onClick={runClear}
                disabled={busy || confirmText.trim().toUpperCase() !== 'KOSONGKAN'} data-testid="clear-confirm">
                {busy ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />Memproses…</> : 'Kosongkan Sekarang'}
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
