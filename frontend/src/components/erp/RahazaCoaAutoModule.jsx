import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, Save, PlayCircle, Eye, AlertCircle, CheckCircle2, Sparkles, Landmark } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';

/**
 * Phase 5 — Auto-Create COA Subledger (settings + backfill).
 * Finance dapat: aktif/matikan auto-akun per jenis entitas, pilih akun parent (kontrol),
 * dan menjalankan backfill untuk entitas lama. Akun subledger dibuat di bawah parent
 * sehingga GL menampilkan saldo per-entitas (mis. hutang per Vendor CMT).
 */
export default function RahazaCoaAutoModule({ token }) {
  const [settings, setSettings] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busyKey, setBusyKey] = useState('');
  const [backfillResult, setBackfillResult] = useState({}); // { entity_type: result }

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [sRes, aRes] = await Promise.all([
        fetch('/api/rahaza/coa-auto/settings', { headers }),
        fetch('/api/rahaza/coa/accounts?active_only=true', { headers }),
      ]);
      if (!sRes.ok) throw new Error('Gagal memuat settings');
      const s = await sRes.json();
      const a = aRes.ok ? await aRes.json() : [];
      setSettings(s);
      setAccounts(Array.isArray(a) ? a : (a.accounts || a.items || []));
    } catch (e) {
      setError(e.message || 'Gagal memuat data');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const patchEntity = (key, field, value) => {
    setSettings((prev) => ({
      ...prev,
      entity_types: {
        ...prev.entity_types,
        [key]: { ...prev.entity_types[key], [field]: value },
      },
    }));
  };

  const save = async () => {
    setSaving(true); setError(''); setInfo('');
    try {
      const payload = { entity_types: {} };
      Object.entries(settings.entity_types).forEach(([k, v]) => {
        payload.entity_types[k] = { enabled: !!v.enabled, parent_code: v.parent_code };
      });
      const r = await fetch('/api/rahaza/coa-auto/settings', {
        method: 'PUT', headers, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      setInfo('Pengaturan tersimpan.');
      setTimeout(() => setInfo(''), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const runBackfill = async (key, commit) => {
    setBusyKey(key + (commit ? ':commit' : ':preview')); setError(''); setInfo('');
    try {
      const r = await fetch(`/api/rahaza/coa-auto/backfill/${key}?commit=${commit}`, {
        method: 'POST', headers,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Backfill gagal');
      setBackfillResult((prev) => ({ ...prev, [key]: d }));
      if (commit) setInfo(`Backfill ${key}: ${d.created} akun dibuat, ${d.already_have_account} sudah ada.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyKey('');
    }
  };

  const accountOptions = accounts
    .filter((a) => !a.is_group) // parent kontrol biasanya postable; tetap tampilkan semua non-group + group
    .concat(accounts.filter((a) => a.is_group));

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground" data-testid="coa-auto-loading">Memuat pengaturan auto-COA…</div>;
  }

  return (
    <div className="space-y-4" data-testid="coa-auto-module">
      <PageHeader
        icon={Sparkles}
        title="Auto Akun Subledger (COA)"
        subtitle="Otomatis buat akun COA per-entitas (Vendor CMT, Supplier, Pelanggan, Channel Online, Bank/Kas) di bawah akun kontrol. GL jadi bisa menampilkan saldo per-entitas (hutang/piutang/kas)."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="coa-auto-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
            </Button>
            <Button onClick={save} disabled={saving} className="h-9" data-testid="coa-auto-save">
              <Save className="w-3.5 h-3.5 mr-1.5" /> {saving ? 'Menyimpan…' : 'Simpan Pengaturan'}
            </Button>
          </>
        }
      />

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2" data-testid="coa-auto-error">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}
      {info && (
        <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2" data-testid="coa-auto-info">
          <CheckCircle2 className="w-4 h-4" /> {info}
        </div>
      )}

      {settings && Object.entries(settings.entity_types).map(([key, cfg]) => {
        const res = backfillResult[key];
        return (
          <GlassCard key={key} className="p-4 space-y-3" data-testid={`coa-auto-card-${key}`}>
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <Landmark className="w-4 h-4 text-primary" />
                <div>
                  <div className="font-semibold text-sm text-foreground">{cfg.label || key}</div>
                  <div className="text-xs text-muted-foreground">
                    Koleksi: <code>{cfg.collection}</code> · Simpan kode ke: <code>{cfg.target_field}</code>
                  </div>
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer select-none" data-testid={`coa-auto-enabled-label-${key}`}>
                <input
                  type="checkbox"
                  checked={!!cfg.enabled}
                  onChange={(e) => patchEntity(key, 'enabled', e.target.checked)}
                  className="w-4 h-4 accent-[var(--primary)]"
                  data-testid={`coa-auto-enabled-${key}`}
                />
                <span className={cfg.enabled ? 'text-emerald-600 font-medium' : 'text-muted-foreground'}>
                  {cfg.enabled ? 'Aktif' : 'Nonaktif'}
                </span>
              </label>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Akun Parent (Kontrol)</label>
                <SmartNativeSelect
                  value={cfg.parent_code || ''}
                  onChange={(e) => patchEntity(key, 'parent_code', e.target.value)}
                  className="w-full h-9 rounded-lg border border-[var(--glass-border)] bg-background px-3 text-sm"
                  data-testid={`coa-auto-parent-${key}`}
                >
                  <option value="">— pilih akun —</option>
                  {accountOptions.map((a) => (
                    <option key={a.code} value={a.code}>{a.code} — {a.name}</option>
                  ))}
                </SmartNativeSelect>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  onClick={() => runBackfill(key, false)}
                  disabled={busyKey.startsWith(key)}
                  className="h-9 border border-[var(--glass-border)]"
                  data-testid={`coa-auto-preview-${key}`}
                >
                  <Eye className="w-3.5 h-3.5 mr-1.5" /> Pratinjau
                </Button>
                <Button
                  onClick={() => runBackfill(key, true)}
                  disabled={busyKey.startsWith(key) || !cfg.enabled}
                  className="h-9"
                  data-testid={`coa-auto-run-${key}`}
                  title={cfg.enabled ? '' : 'Aktifkan dulu untuk backfill'}
                >
                  <PlayCircle className="w-3.5 h-3.5 mr-1.5" /> Jalankan Backfill
                </Button>
              </div>
            </div>

            {res && (
              <div className="text-xs bg-muted/40 border border-[var(--glass-border)] rounded-lg p-3 space-y-1" data-testid={`coa-auto-result-${key}`}>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>Total entitas: <b>{res.total_entities}</b></span>
                  <span>Sudah ada akun: <b>{res.already_have_account}</b></span>
                  <span>{res.committed ? 'Dibuat' : 'Akan dibuat'}: <b>{res.committed ? res.created : res.would_create}</b></span>
                  <span className={res.committed ? 'text-emerald-600' : 'text-amber-600'}>
                    {res.committed ? '✓ committed' : 'dry-run (pratinjau)'}
                  </span>
                </div>
                {(res.samples || []).length > 0 && (
                  <div className="pt-1">
                    <div className="text-muted-foreground mb-0.5">Contoh:</div>
                    {res.samples.map((s, i) => (
                      <div key={i} className="font-mono">• {s.entity} → {s.account}</div>
                    ))}
                  </div>
                )}
                {(res.errors || []).length > 0 && (
                  <div className="text-red-500 pt-1">{res.errors.length} error saat backfill.</div>
                )}
              </div>
            )}
          </GlassCard>
        );
      })}

      <p className="text-xs text-muted-foreground px-1">
        Catatan: akun subledger dibuat di bawah akun parent/kontrol (mis. <code>2-1100</code> Hutang Usaha untuk Vendor CMT/Supplier,
        <code>1-1301</code> Piutang untuk Pelanggan, <code>1-220</code> untuk Channel Online, <code>1-1200</code> untuk Bank/Kas).
        Saat mem-posting invoice (AP/AR), jurnal otomatis memakai akun per-entitas tersebut; jika fitur nonaktif atau
        akun belum ada, jurnal jatuh ke akun kontrol. Idempotent &amp; aman dijalankan berulang.
      </p>
    </div>
  );
}
