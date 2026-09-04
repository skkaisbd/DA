import { useState, useEffect, useCallback, useMemo } from 'react';
import { Store, RefreshCw, Save, Eye, EyeOff, CheckCircle2, AlertTriangle, Clock, History, Loader2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { PageHeader } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import ImportExportToolbar from './ImportExportToolbar';

const CHANNEL_COLORS = {
  shopee: { bg: 'from-orange-500/25 to-orange-500/5', border: 'border-orange-400 dark:border-orange-400/30', text: 'text-orange-600 dark:text-orange-300', dot: 'bg-orange-400' },
  tokopedia: { bg: 'from-emerald-500/25 to-emerald-500/5', border: 'border-emerald-400 dark:border-emerald-400/30', text: 'text-emerald-600 dark:text-emerald-300', dot: 'bg-emerald-400' },
  tiktok_shop: { bg: 'from-pink-500/25 to-pink-500/5', border: 'border-pink-400 dark:border-pink-400/30', text: 'text-pink-600 dark:text-pink-300', dot: 'bg-pink-400' },
  tiktok: { bg: 'from-pink-500/25 to-pink-500/5', border: 'border-pink-400 dark:border-pink-400/30', text: 'text-pink-600 dark:text-pink-300', dot: 'bg-pink-400' },
  website: { bg: 'from-sky-500/25 to-sky-500/5', border: 'border-sky-400 dark:border-sky-400/30', text: 'text-sky-600 dark:text-sky-300', dot: 'bg-sky-400' },
};

const fmtDate = (d) => (d ? new Date(d).toLocaleString('id-ID') : 'Belum pernah');

// ── Marketing account shape → legacy-friendly view model ────────────────────
const readChannel = (a) => ({
  id: a.id,
  code: a.code || a.channel_code || a.platform,
  name: a.name || a.account_name || a.platform,
  enabled: a.enabled ?? (a.status === 'active'),
  last_sync_at: a.last_sync_at,
  last_sync_status: a.last_sync_status,
  last_sync_counts: a.last_sync_counts || {},
  mock: a.mock !== false,
  credentials: a.credentials || {},
  fee_pct: Number(a.fee_pct ?? 0),
  commission_pct: Number(a.commission_pct ?? 0),
  notes: a.notes || '',
});

export default function TokoChannelManagerModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(null);
  const [editing, setEditing] = useState(null);
  const [history, setHistory] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/marketing/accounts?_legacy_toko=true', { headers });
      if (r.ok) {
        const data = await r.json();
        const list = Array.isArray(data) ? data : (data.accounts || data.data || []);
        // Filter only legacy_toko entries (server may not filter by default)
        const legacy = list.filter((a) => a._legacy_toko === true);
        // Mask credential secrets for display
        const masked = legacy.map((a) => {
          const c = { ...(a.credentials || {}) };
          for (const sk of ['api_key', 'api_secret']) {
            if (c[sk] && !String(c[sk]).startsWith('***')) {
              const v = String(c[sk]);
              c[sk] = v.length > 4 ? '***' + v.slice(-4) : '***';
            }
          }
          return readChannel({ ...a, credentials: c });
        });
        setChannels(masked);
      }
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (ch) => {
    const r = await fetch(`/api/marketing/accounts/${ch.code}/legacy-config`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ enabled: !ch.enabled }),
    });
    if (r.ok) {
      toast.success(`${ch.name} ${!ch.enabled ? 'diaktifkan' : 'dinonaktifkan'}`);
      load();
    } else {
      toast.error('Gagal');
    }
  };

  const sync = async (ch) => {
    setSyncing(ch.code);
    try {
      const r = await fetch(`/api/marketing/accounts/${ch.code}/sync`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success(`${ch.name} sync (MOCK): ${d.counts.products} produk · ${d.counts.orders} order`);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSyncing(null);
    }
  };

  const loadHistory = async (ch) => {
    setHistory({ channel: ch, rows: null });
    try {
      const r = await fetch(`/api/marketing/accounts/${ch.code}/sync-history?limit=20`, { headers });
      if (r.ok) setHistory({ channel: ch, rows: await r.json() });
    } catch (e) {
      setHistory(null);
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="toko-channel-manager">
      <PageHeader
        title="Channel Manager"
        description="Konfigurasi marketplace & sinkronisasi produk/order via Marketing SSOT. Mode MOCK aktif."
        icon={Store}
        actions={
          <>
            <ImportExportToolbar collectionKey="platform_accounts" label="Akun Toko / Channel" onImported={load} />
            <Button size="sm" variant="outline" onClick={load} className="gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
          </>
        }
      />

      <div
        className="rounded-xl border border-amber-400 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/5 p-3 text-xs flex items-start gap-2"
        data-testid="toko-channel-mock-banner"
      >
        <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400 flex-shrink-0 mt-0.5" />
        <div>
          <span className="font-medium text-amber-200">MODE MOCK aktif.</span>
          <span className="text-foreground/65">
            {' '}
            Tombol &quot;Sync Now&quot; akan mensimulasikan pemanggilan API marketplace.
            Untuk produksi, masukkan kredensial real di masing-masing channel lalu admin akan swap MOCK handler ke real provider (Shopee Partner API, Tokopedia, TikTok Shop).
          </span>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-pulse">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-40 rounded-2xl bg-foreground/[0.05]" />)}
        </div>
      ) : channels.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Store className="w-10 h-10 mx-auto mb-3 text-foreground/25" />
          <p className="text-foreground/50 text-sm">Belum ada channel toko terkonfigurasi</p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="toko-channel-list">
          {channels.map((ch) => {
            const tone = CHANNEL_COLORS[ch.code] || CHANNEL_COLORS.website;
            const counts = ch.last_sync_counts || {};
            return (
              <GlassCard
                key={ch.id || ch.code}
                className={`p-5 border ${tone.border} bg-gradient-to-br ${tone.bg}`}
                data-testid={`toko-channel-${ch.code}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-black/30 flex items-center justify-center">
                      <Store className={`w-5 h-5 ${tone.text}`} />
                    </div>
                    <div>
                      <div className="text-base font-semibold">{ch.name}</div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${ch.enabled ? tone.dot + ' animate-pulse' : 'bg-foreground/30'}`} />
                        <span className="text-[11px] text-foreground/65">{ch.enabled ? 'Aktif' : 'Nonaktif'}</span>
                        {ch.mock && <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/30 text-foreground/55">MOCK</span>}
                      </div>
                    </div>
                  </div>
                  <Switch
                    checked={ch.enabled}
                    onCheckedChange={() => toggle(ch)}
                    data-testid={`toko-channel-toggle-${ch.code}`}
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 mb-3 text-xs">
                  <div className="rounded-lg bg-black/20 p-2">
                    <div className="text-[9px] uppercase tracking-wider text-foreground/55">Produk</div>
                    <div className="text-lg font-bold tabular-nums">{counts.products ?? 0}</div>
                  </div>
                  <div className="rounded-lg bg-black/20 p-2">
                    <div className="text-[9px] uppercase tracking-wider text-foreground/55">Order</div>
                    <div className="text-lg font-bold tabular-nums">{counts.orders ?? 0}</div>
                  </div>
                  <div className="rounded-lg bg-black/20 p-2">
                    <div className="text-[9px] uppercase tracking-wider text-foreground/55">Error</div>
                    <div className={`text-lg font-bold tabular-nums ${(counts.errors ?? 0) > 0 ? 'text-red-600 dark:text-red-300' : ''}`}>
                      {counts.errors ?? 0}
                    </div>
                  </div>
                </div>

                <div className="text-[11px] text-foreground/55 mb-3 flex items-center gap-1.5">
                  <Clock className="w-3 h-3" /> Sync terakhir: {fmtDate(ch.last_sync_at)}
                  {ch.last_sync_status === 'success' && <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400 ml-1" />}
                  {ch.last_sync_status === 'failed' && <AlertTriangle className="w-3 h-3 text-red-700 dark:text-red-400 ml-1" />}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={!ch.enabled || syncing === ch.code}
                    onClick={() => sync(ch)}
                    className="gap-1.5 flex-1"
                    data-testid={`toko-channel-sync-${ch.code}`}
                  >
                    {syncing === ch.code ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    {syncing === ch.code ? 'Syncing...' : 'Sync Now'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(ch)}
                    className="gap-1.5"
                    data-testid={`toko-channel-configure-${ch.code}`}
                  >
                    <Save className="w-3.5 h-3.5" /> Configure
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => loadHistory(ch)}
                    data-testid={`toko-channel-history-${ch.code}`}
                  >
                    <History className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {editing && (
        <ChannelEditor
          channel={editing}
          headers={headers}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
      {history && <SyncHistoryDialog data={history} onClose={() => setHistory(null)} />}
    </div>
  );
}

function ChannelEditor({ channel, headers, onClose, onSaved }) {
  const [form, setForm] = useState({
    api_key: channel.credentials?.api_key || '',
    api_secret: channel.credentials?.api_secret || '',
    shop_id: channel.credentials?.shop_id || '',
    webhook_url: channel.credentials?.webhook_url || '',
    fee_pct: channel.fee_pct || 0,
    commission_pct: channel.commission_pct || 0,
    notes: channel.notes || '',
  });
  const [showSecret, setShowSecret] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const save = async () => {
    setSaving(true);
    try {
      // Build credentials object — skip masked values to avoid overwriting
      const creds = {};
      for (const k of ['api_key', 'api_secret', 'shop_id', 'webhook_url']) {
        if (form[k] && !String(form[k]).startsWith('***')) {
          creds[k] = form[k];
        } else if (form[k] === '') {
          creds[k] = ''; // empty = clear
        }
      }
      const body = {
        credentials: creds,
        fee_pct: Number(form.fee_pct || 0),
        commission_pct: Number(form.commission_pct || 0),
        notes: form.notes,
      };
      const r = await fetch(`/api/marketing/accounts/${channel.code}/legacy-config`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json();
        throw new Error(d.detail || 'Gagal simpan');
      }
      toast.success('Konfigurasi disimpan');
      onSaved();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="toko-channel-editor">
      <div className="absolute inset-0 bg-foreground/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl border border-foreground/10 bg-[hsl(var(--background))] p-6 shadow-xl max-h-[85vh] overflow-y-auto">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Store className="w-4 h-4" /> Configure {channel.name}
        </h3>
        <p className="text-xs text-foreground/55 mt-1 mb-4">
          Kredensial API tersimpan terenkripsi (mask saat ditampilkan). Untuk clear, kosongkan field dan simpan.
        </p>

        <div className="space-y-3">
          <div>
            <Label className="text-xs">Shop ID / Merchant ID</Label>
            <Input
              value={form.shop_id}
              onChange={(e) => set({ shop_id: e.target.value })}
              placeholder="Contoh: dewi_aditya_shop"
            />
          </div>
          <div>
            <Label className="text-xs">API Key</Label>
            <Input
              value={form.api_key}
              onChange={(e) => set({ api_key: e.target.value })}
              placeholder="PK_xxxx..."
              data-testid="toko-channel-api-key"
            />
          </div>
          <div>
            <Label className="text-xs flex items-center gap-2">
              API Secret
              <button
                type="button"
                onClick={() => setShowSecret((s) => !s)}
                className="text-foreground/45 hover:text-foreground/70"
              >
                {showSecret ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              </button>
            </Label>
            <Input
              type={showSecret ? 'text' : 'password'}
              value={form.api_secret}
              onChange={(e) => set({ api_secret: e.target.value })}
              placeholder="SK_xxxx..."
            />
          </div>
          <div>
            <Label className="text-xs">Webhook URL</Label>
            <Input
              value={form.webhook_url}
              onChange={(e) => set({ webhook_url: e.target.value })}
              placeholder="https://..."
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Fee Marketplace (%)</Label>
              <Input
                type="number"
                step="0.1"
                value={form.fee_pct}
                onChange={(e) => set({ fee_pct: e.target.value })}
              />
            </div>
            <div>
              <Label className="text-xs">Commission KOL (%)</Label>
              <Input
                type="number"
                step="0.1"
                value={form.commission_pct}
                onChange={(e) => set({ commission_pct: e.target.value })}
              />
            </div>
          </div>
          <div>
            <Label className="text-xs">Catatan</Label>
            <Input value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button variant="ghost" onClick={onClose} disabled={saving}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="toko-channel-save-config">
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />}
            Simpan
          </Button>
        </div>
      </div>
    </div>
  );
}

function SyncHistoryDialog({ data, onClose }) {
  const { channel, rows } = data;
  const { page, setPage, totalPages, total, paged } = useClientPagination(rows, 10);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="toko-sync-history-dialog">
      <div className="absolute inset-0 bg-foreground/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-xl rounded-2xl border border-foreground/10 bg-[hsl(var(--background))] p-6 shadow-xl max-h-[80vh] overflow-y-auto">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <History className="w-4 h-4" /> Riwayat Sync — {channel.name}
        </h3>
        <div className="mt-4">
          {rows === null ? (
            <div className="text-center py-6 text-foreground/45 text-sm">Memuat...</div>
          ) : rows.length === 0 ? (
            <div className="text-center py-6 text-foreground/45 text-sm">Belum ada riwayat sync.</div>
          ) : (
            <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
              <table className="w-full text-xs">
                <thead className="bg-foreground/5 text-foreground/55">
                  <tr>
                    <th className="text-left font-medium px-3 py-2">Mulai</th>
                    <th className="text-left font-medium px-3 py-2">Status</th>
                    <th className="text-right font-medium px-3 py-2">Dur (ms)</th>
                    <th className="text-right font-medium px-3 py-2">Prd</th>
                    <th className="text-right font-medium px-3 py-2">Ord</th>
                    <th className="text-left font-medium px-3 py-2">Oleh</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map((r) => (
                    <tr key={r.id} className="border-t border-foreground/5">
                      <td className="px-3 py-2 whitespace-nowrap">{fmtDate(r.started_at)}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded ${
                            r.status === 'success' ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300'
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.duration_ms ?? '-'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.counts?.products ?? '-'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.counts?.orders ?? '-'}</td>
                      <td className="px-3 py-2 text-foreground/65 truncate max-w-[140px]">{r.triggered_by || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
            </div>
          )}
        </div>
        <div className="flex justify-end mt-5">
          <Button variant="outline" onClick={onClose}>Tutup</Button>
        </div>
      </div>
    </div>
  );
}
