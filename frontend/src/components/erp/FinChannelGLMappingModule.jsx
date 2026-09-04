/**
 * FinChannelGLMappingModule — Manajemen Channel-to-GL Mapping
 *
 * Portal Keuangan · AR
 * Menampilkan dan mengelola pemetaan channel penjualan ke akun GL.
 * Setiap channel punya:
 *   - debit_ar     : akun Piutang yang didebet saat invoice dibuat
 *   - credit_revenue : akun Pendapatan yang dikredit saat invoice dibuat
 *
 * Finance dapat:
 *   1. Melihat semua channel dan routing GL-nya
 *   2. Mengedit akun Piutang/Pendapatan per channel
 *   3. Seed default 13 channel CV. Dewi Aditya
 */
import { useState, useEffect, useCallback, useReducer } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Store, RefreshCw, Plus, Edit2, Save, X, Zap, ShoppingBag,
  ArrowRight, Check, AlertCircle, Layers
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatusBadge, EmptyState } from './moduleAtoms';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const fmt_code = (code) => code || '—';

// Warna per platform
const PLATFORM_STYLE = {
  shopee:    { bg: 'bg-orange-500/10 border-orange-400/20', dot: 'bg-orange-400', text: 'Shopee' },
  tiktok:    { bg: 'bg-pink-500/10 border-pink-400/20',     dot: 'bg-pink-400',   text: 'TikTok' },
  tokopedia: { bg: 'bg-green-500/10 border-green-400/20',   dot: 'bg-green-400',  text: 'Tokopedia' },
  maklon:    { bg: 'bg-blue-500/10 border-blue-400/20',     dot: 'bg-blue-400',   text: 'Maklon' },
  other:     { bg: 'bg-muted/10 border-border/20',     dot: 'bg-muted',   text: 'Lainnya' },
};

function PlatformBadge({ platform }) {
  const s = PLATFORM_STYLE[platform] || PLATFORM_STYLE.other;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wider ${s.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.text}
    </span>
  );
}

const _INIT = { channels: [], coaAccounts: [], loading: true };
function _reducer(s, a) {
  if (a.type === 'loaded') return { ...s, ...a.data, loading: false };
  if (a.type === 'loading') return { ...s, loading: true };
  return s;
}

export default function FinChannelGLMappingModule({ token }) {
  const [{ channels, coaAccounts, loading }, dispatch] = useReducer(_reducer, _INIT);
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [filterPlatform, setFilterPlatform] = useState('all');
  const [tick, setTick] = useState(0);

  const hdrs = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const refresh = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    let x = false;
    dispatch({ type: 'loading' });
    Promise.all([
      fetch(`${BACKEND_URL}/api/rahaza/channel-gl-mapping`, { headers: hdrs })
        .then(r => r.json())
        .then(d => Array.isArray(d) ? d : [])
        .catch(() => []),
      fetch(`${BACKEND_URL}/api/rahaza/coa/accounts`, { headers: hdrs })
        .then(r => r.json())
        .then(d => Array.isArray(d) ? d : (d.items || d.accounts || []))
        .catch(() => []),
    ]).then(([chs, coa]) => {
      if (x) return;
      dispatch({ type: 'loaded', data: {
        channels: chs,
        coaAccounts: coa,
      }});
    }).catch(() => {
      if (!x) dispatch({ type: 'loaded', data: { channels: [], coaAccounts: [] } });
    });
    return () => { x = true; };
  }, [token, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const seedDefault = async () => {
    setSeeding(true);
    try {
      const r = await fetch(`${BACKEND_URL}/api/rahaza/channel-gl-mapping/seed-da`, {
        method: 'POST', headers: hdrs,
      });
      const d = await r.json();
      if (r.ok) {
        toast.success(`Seed selesai: ${d.inserted} channel baru, ${d.skipped} sudah ada.`);
        refresh();
      } else {
        toast.error(d.detail || 'Seed gagal');
      }
    } finally { setSeeding(false); }
  };

  const startEdit = (ch) => {
    setEditId(ch.id);
    setEditForm({ debit_ar: ch.debit_ar, credit_revenue: ch.credit_revenue });
  };

  const cancelEdit = () => { setEditId(null); setEditForm({}); };

  const saveEdit = async (ch) => {
    setSaving(true);
    try {
      const r = await fetch(`${BACKEND_URL}/api/rahaza/channel-gl-mapping/${ch.id}`, {
        method: 'PUT', headers: hdrs,
        body: JSON.stringify({
          channel_label: ch.channel_label,
          platform: ch.platform,
          debit_ar: editForm.debit_ar,
          credit_revenue: editForm.credit_revenue,
        }),
      });
      if (r.ok) {
        toast.success(`${ch.channel_label} berhasil diperbarui.`);
        setEditId(null);
        refresh();
      } else {
        const d = await r.json().catch(() => ({}));
        toast.error(d.detail || 'Gagal menyimpan');
      }
    } finally { setSaving(false); }
  };

  // Group channels by platform
  const platforms = ['all', ...([...new Set(channels.map(c => c.platform))].sort())];
  const filtered = filterPlatform === 'all'
    ? channels
    : channels.filter(c => c.platform === filterPlatform);

  // CoA lookup helpers — COA uses `code` and `name` fields
  const arAccounts = coaAccounts.filter(a =>
    (a.code?.startsWith('1-2') || a.code?.startsWith('1-1')) && !a.is_group
  );
  const revAccounts = coaAccounts.filter(a => a.code?.startsWith('4-') && !a.is_group);

  const getCoaName = (code) => {
    const acc = coaAccounts.find(a => a.code === code);
    return acc ? acc.name : code;
  };

  return (
    <div className="space-y-5" data-testid="fin-channel-gl-page">
      <PageHeader
        icon={Store}
        eyebrow="Portal Keuangan · AR"
        title="Channel → Akun GL"
        subtitle="Atur pemetaan channel penjualan ke akun Piutang (AR) dan akun Pendapatan. Digunakan saat invoice dikirim untuk auto-posting jurnal."
        actions={
          <>
            <Button
              variant="ghost"
              onClick={refresh}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="channel-gl-refresh-btn"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </Button>
            {channels.length < 10 && (
              <Button
                onClick={seedDefault}
                disabled={seeding}
                className="h-9 gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400"
                data-testid="channel-gl-seed-btn"
              >
                <Zap className="w-3.5 h-3.5" />
                {seeding ? 'Menyiapkan...' : 'Seed Default (13 Channel)'}
              </Button>
            )}
          </>
        }
      />

      {/* Info banner */}
      <div className="rounded-lg border border-[hsl(var(--primary)/0.20)] bg-[hsl(var(--primary)/0.06)] px-4 py-3 flex gap-3">
        <AlertCircle className="w-4 h-4 text-[hsl(var(--primary))] shrink-0 mt-0.5" />
        <div className="text-xs text-foreground/70 leading-relaxed">
          <strong className="text-foreground">Cara kerja:</strong> Saat invoice AR dikirim (<code className="text-[hsl(var(--primary))]">send</code>),
          sistem otomatis membuat jurnal <strong>Dr {'{debit_ar}'} / Cr {'{credit_revenue}'}</strong>
          sesuai channel yang dipilih pada invoice. Pastikan setiap channel sudah memiliki akun yang tepat.
        </div>
      </div>

      {/* Platform filter tabs */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {platforms.map(p => (
          <button
            key={p}
            onClick={() => setFilterPlatform(p)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors duration-150 ${
              filterPlatform === p
                ? 'bg-[hsl(var(--primary))] border-[hsl(var(--primary))] text-white'
                : 'bg-[var(--nav-pill-bg)] border-[var(--glass-border)] text-foreground/60 hover:text-foreground hover:bg-[var(--nav-pill-active)]'
            }`}
            data-testid={`platform-filter-${p}`}
          >
            {p === 'all' ? `Semua (${channels.length})` : `${(PLATFORM_STYLE[p] || PLATFORM_STYLE.other).text} (${channels.filter(c => c.platform === p).length})`}
          </button>
        ))}
      </div>

      {/* Table */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-[10px] uppercase tracking-wider text-foreground/50">
                <th className="px-4 py-3">Channel</th>
                <th className="px-3 py-3">Platform</th>
                <th className="px-3 py-3">
                  <span className="flex items-center gap-1">
                    <span className="text-amber-400">Dr</span> Piutang (AR)
                  </span>
                </th>
                <th className="px-3 py-3">
                  <span className="flex items-center gap-1">
                    <span className="text-emerald-400">Cr</span> Pendapatan
                  </span>
                </th>
                <th className="px-3 py-3 text-center">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="py-8">
                    <div className="space-y-2">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Skeleton key={i} className="h-12 rounded-lg mx-4" />
                      ))}
                    </div>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8">
                    <EmptyState
                      icon={Store}
                      title="Belum ada channel"
                      description={channels.length === 0
                        ? "Klik 'Seed Default' untuk menambahkan 13 channel CV. Dewi Aditya."
                        : "Tidak ada channel untuk filter ini."}
                    />
                  </td>
                </tr>
              ) : filtered.map((ch, idx) => {
                const isEditing = editId === ch.id;
                return (
                  <tr
                    key={ch.id}
                    className={`border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors ${idx % 2 === 0 ? '' : 'bg-[var(--glass-bg)]/20'}`}
                    data-testid={`channel-row-${ch.channel_key}`}
                  >
                    {/* Channel */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <ShoppingBag className="w-3.5 h-3.5 text-foreground/40 shrink-0" />
                        <div>
                          <div className="text-xs font-semibold text-foreground">{ch.channel_label}</div>
                          <div className="text-[10px] text-muted-foreground font-mono">{ch.channel_key}</div>
                        </div>
                      </div>
                    </td>

                    {/* Platform */}
                    <td className="px-3 py-2.5">
                      <PlatformBadge platform={ch.platform} />
                    </td>

                    {/* Debit AR */}
                    <td className="px-3 py-2.5">
                      {isEditing ? (
                        <SmartNativeSelect
                          value={editForm.debit_ar}
                          onChange={e => setEditForm(f => ({ ...f, debit_ar: e.target.value }))}
                          className="w-full h-8 px-2 rounded-md border border-amber-400/30 bg-amber-400/5 text-xs text-foreground font-mono"
                          data-testid={`edit-debit-ar-${ch.id}`}
                        >
                          {arAccounts.map(a => (
                            <option key={a.code} value={a.code}>
                              {a.code} · {a.name}
                            </option>
                          ))}
                        </SmartNativeSelect>
                      ) : (
                        <div>
                          <div className="font-mono text-xs font-bold text-amber-400">{fmt_code(ch.debit_ar)}</div>
                          <div className="text-[10px] text-foreground/50">{getCoaName(ch.debit_ar)}</div>
                        </div>
                      )}
                    </td>

                    {/* Credit Revenue */}
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <ArrowRight className="w-3 h-3 text-foreground/20 shrink-0" />
                        {isEditing ? (
                          <SmartNativeSelect
                            value={editForm.credit_revenue}
                            onChange={e => setEditForm(f => ({ ...f, credit_revenue: e.target.value }))}
                            className="w-full h-8 px-2 rounded-md border border-emerald-400/30 bg-emerald-400/5 text-xs text-foreground font-mono"
                            data-testid={`edit-credit-rev-${ch.id}`}
                          >
                            {revAccounts.map(a => (
                              <option key={a.code} value={a.code}>
                                {a.code} · {a.name}
                              </option>
                            ))}
                          </SmartNativeSelect>
                        ) : (
                          <div>
                            <div className="font-mono text-xs font-bold text-emerald-400">{fmt_code(ch.credit_revenue)}</div>
                            <div className="text-[10px] text-foreground/50">{getCoaName(ch.credit_revenue)}</div>
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Aksi */}
                    <td className="px-3 py-2.5 text-center">
                      <div className="flex items-center justify-center gap-1">
                        {isEditing ? (
                          <>
                            <button
                              onClick={() => saveEdit(ch)}
                              disabled={saving}
                              className="h-7 px-2.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 text-emerald-400 hover:bg-emerald-400/20 transition-colors flex items-center gap-1 text-[10px] font-semibold"
                              data-testid={`save-channel-${ch.id}`}
                            >
                              <Check className="w-3 h-3" />
                              {saving ? '...' : 'Simpan'}
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="h-7 px-2 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-foreground/60 hover:text-foreground transition-colors text-[10px]"
                              data-testid={`cancel-edit-${ch.id}`}
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => startEdit(ch)}
                            className="h-7 px-2.5 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-foreground/60 hover:text-foreground hover:bg-[var(--glass-bg-hover)] transition-colors flex items-center gap-1 text-[10px]"
                            data-testid={`edit-channel-${ch.id}`}
                          >
                            <Edit2 className="w-3 h-3" />
                            Edit
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Summary footer */}
      {channels.length > 0 && (
        <div className="flex items-center gap-4 text-xs text-foreground/50">
          <span className="flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5" />
            {channels.length} channel aktif
          </span>
          {platforms.filter(p => p !== 'all').map(p => (
            <span key={p} className="flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${(PLATFORM_STYLE[p] || PLATFORM_STYLE.other).dot}`} />
              {(PLATFORM_STYLE[p] || PLATFORM_STYLE.other).text}: {channels.filter(c => c.platform === p).length}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
