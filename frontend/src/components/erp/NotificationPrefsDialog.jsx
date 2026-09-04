/**
 * NotificationPrefsDialog — "Notifikasi Saya" (preferensi per pengguna).
 *
 * MENGAPA ADA: backend sudah lama punya `GET/PUT /api/notifications/my-category-prefs`
 * (setiap orang boleh membisukan kategori untuk dirinya sendiri) tetapi TIDAK ADA
 * layarnya, jadi fiturnya tidak pernah bisa dipakai. Dialog ini dibuka dari ikon
 * gerigi di dropdown bel sehingga bisa dijangkau dari portal mana pun.
 *
 * ATURAN YANG DITAMPILKAN JUJUR KE PENGGUNA:
 *   · Kategori yang tidak dibuka admin untuk peran Anda tidak muncul di sini.
 *   · Kategori "Untuk Saya" selalu aktif dan tidak bisa dibisukan — isinya
 *     notifikasi yang memang dialamatkan langsung kepada Anda.
 */
import { useCallback, useEffect, useState } from 'react';
import { BellRing, BellOff, Loader2, Save, ShieldCheck, Lock } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export default function NotificationPrefsDialog({ token, onClose, onSaved }) {
  const [data, setData] = useState(null);
  const [muted, setMuted] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await fetch(`${BACKEND_URL}/api/notifications/my-category-prefs`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
      setData(body);
      setMuted(body.muted_categories || []);
    } catch (e) {
      setErr(e.message || 'Gagal memuat preferensi notifikasi');
    } finally { setLoading(false); }
     
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const locked = data?.locked_categories || ['personal'];
  const cats = data?.categories || [];

  const toggle = (key) => {
    if (locked.includes(key)) return;
    setMuted((m) => (m.includes(key) ? m.filter((x) => x !== key) : [...m, key]));
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${BACKEND_URL}/api/notifications/my-category-prefs`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ muted_categories: muted.filter((c) => !locked.includes(c)) }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
      const off = (body.muted_categories || []).length;
      toast.success('Preferensi notifikasi disimpan', {
        description: off
          ? `${off} kategori dibisukan untuk akun Anda`
          : 'Semua kategori yang tersedia aktif',
      });
      onSaved?.();
      onClose?.();
    } catch (e) {
      toast.error('Gagal menyimpan preferensi', { description: e.message });
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Notifikasi Saya" size="lg" onClose={onClose}>
      <div className="space-y-3" data-testid="notif-prefs-dialog">
        <div className="flex items-start gap-2 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--primary))]" />
          <p className="text-xs text-muted-foreground">
            Matikan kategori yang tidak Anda perlukan. Yang dimatikan berhenti muncul di bel
            <b className="text-foreground"> hanya untuk akun Anda</b> — rekan lain tidak terpengaruh.
            Kategori yang belum dibuka admin untuk peran Anda tidak ditampilkan di sini.
          </p>
        </div>

        {err && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">{err}</div>
        )}

        {loading ? (
          <div className="py-10 text-center">
            <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <ul className="divide-y divide-[var(--glass-border)] overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)]">
            {cats.map((c) => {
              const isLocked = locked.includes(c.key);
              const isOff = muted.includes(c.key) && !isLocked;
              return (
                <li key={c.key} className="flex items-center justify-between gap-3 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                      {c.label}
                      {isLocked && (
                        <span className="inline-flex items-center gap-1 rounded border border-[var(--glass-border)] px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                          <Lock className="h-2.5 w-2.5" /> selalu aktif
                        </span>
                      )}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {isLocked
                        ? 'Notifikasi yang dialamatkan langsung kepada Anda — tidak bisa dibisukan.'
                        : isOff ? 'Dibisukan — tidak muncul di bel Anda.' : 'Aktif — muncul di bel Anda.'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    disabled={isLocked}
                    aria-pressed={!isOff}
                    className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors
                      ${isLocked
                        ? 'cursor-not-allowed border-[var(--glass-border)] bg-[var(--nav-pill-bg)] text-muted-foreground'
                        : isOff
                          ? 'border-slate-300 bg-slate-100 text-slate-600 hover:bg-slate-200'
                          : 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                    data-testid={`notif-pref-${c.key}`}
                  >
                    {isOff
                      ? (<><BellOff className="h-3.5 w-3.5" /> Dibisukan</>)
                      : (<><BellRing className="h-3.5 w-3.5" /> Aktif</>)}
                  </button>
                </li>
              );
            })}
            {cats.length === 0 && (
              <li className="px-3 py-8 text-center text-sm text-muted-foreground">
                Belum ada kategori notifikasi yang dibuka untuk peran Anda.
              </li>
            )}
          </ul>
        )}

        <div className="flex items-center justify-end gap-2">
          <button onClick={onClose}
                  className="h-9 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] px-3 text-sm text-foreground hover:bg-[var(--nav-pill-active)]">
            Batal
          </button>
          <button onClick={save} disabled={saving || loading}
                  className="inline-flex h-9 items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 text-sm font-medium text-white disabled:opacity-60"
                  data-testid="notif-prefs-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Simpan
          </button>
        </div>
      </div>
    </Modal>
  );
}
