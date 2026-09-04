import { useState, useEffect } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import {
  X, Palette, FlaskConical, Layers, Ruler, Calculator,
  GitBranch, FileText, ExternalLink, CheckCircle2, Clock,
  XCircle, Send, RefreshCw, TrendingUp, Package
} from 'lucide-react';
import { toast } from '../ui/sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = (n) => n != null ? formatRupiah(n) : '—';

const STATUS_STYLE = {
  active:   { label: 'Aktif',   cls: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30' },
  draft:    { label: 'Draft',   cls: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30' },
  archived: { label: 'Arsip',   cls: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30' },
  review:   { label: 'Review',  cls: 'bg-sky-100 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 border-sky-400 dark:border-sky-500/30' },
};

const STATUS_SAMPLE = {
  draft:     { label: 'Draft',     cls: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30', Icon: Clock },
  submitted: { label: 'Diajukan', cls: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30', Icon: Send },
  approved:  { label: 'Disetujui',cls: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30', Icon: CheckCircle2 },
  rejected:  { label: 'Ditolak',  cls: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30', Icon: XCircle },
};

const TABS = [
  { id: 'overview',   label: 'Overview',   icon: Palette },
  { id: 'variants',   label: 'Varian',     icon: Layers },
  { id: 'samples',    label: 'Sampling',   icon: FlaskConical },
  { id: 'patterns',   label: 'Pola',       icon: Ruler },
  { id: 'hpp',        label: 'HPP',        icon: Calculator },
  { id: 'revisions',  label: 'Revisi',     icon: GitBranch },
  { id: 'techpack',   label: 'Tech Pack',  icon: FileText },
];

function InfoRow({ label, value, mono = false }) {
  return (
    <div className="flex items-start gap-4 py-2 border-b border-foreground/5 last:border-0">
      <span className="text-sm text-foreground/50 w-32 flex-shrink-0">{label}</span>
      <span className={`text-sm text-foreground ${mono ? 'font-mono' : ''}`}>{value || '—'}</span>
    </div>
  );
}

function SectionEmpty({ icon: Icon, text }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <Icon className="w-9 h-9 text-foreground/15 mb-2" />
      <p className="text-sm text-foreground/40">{text}</p>
    </div>
  );
}

export default function RnDStyleDetailPage({ token, styleId, onClose }) {
  const h = { Authorization: `Bearer ${token}` };
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState('overview');

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles/${styleId}/overview`, { headers: h });
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch { toast.error('Gagal memuat detail style'); }
    finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (styleId) load(); }, [styleId]);

  if (!styleId) return null;

  const style = data?.style || {};
  const sc = STATUS_STYLE[style.status] || STATUS_STYLE.draft;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-foreground/50" onClick={onClose} />
      {/* Panel */}
      <div className="w-full max-w-4xl bg-background border-l border-foreground/10 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-foreground/10 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-500/15 border border-violet-500/25 flex items-center justify-center">
              <Palette className="w-5 h-5 text-violet-500" />
            </div>
            <div>
              {loading ? (
                <div className="h-5 w-32 bg-foreground/10 rounded animate-pulse" />
              ) : (
                <>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-foreground text-lg font-mono">{style.style_code}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>{sc.label}</span>
                  </div>
                  <p className="text-sm text-foreground/60">{style.style_name}</p>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={load} className="h-8 w-8 p-0" disabled={loading}>
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0">
              <X className="w-5 h-5" />
            </Button>
          </div>
        </div>

        {/* Summary badges */}
        {!loading && data?.summary && (
          <div className="flex gap-3 px-6 py-3 border-b border-foreground/5 bg-foreground/[0.02] overflow-x-auto flex-shrink-0">
            {[
              { label: 'Varian',    val: data.summary.total_variants,  Icon: Layers },
              { label: 'Sample',    val: data.summary.total_samples,   Icon: FlaskConical },
              { label: 'Pola',      val: data.summary.total_patterns,  Icon: Ruler },
              { label: 'HPP',       val: data.summary.total_hpp,       Icon: Calculator },
              { label: 'Revisi',    val: data.summary.total_revisions, Icon: GitBranch },
              { label: 'Tech Pack', val: data.summary.total_tech_packs,Icon: FileText },
            ].map(({ label, val, Icon }) => (
              <div key={label}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-foreground/5 border border-foreground/[0.08] flex-shrink-0 cursor-pointer hover:bg-foreground/10 transition-colors"
                onClick={() => {
                  const m = { Varian:'variants', Sample:'samples', Pola:'patterns', HPP:'hpp', Revisi:'revisions', 'Tech Pack':'techpack' };
                  setTab(m[label] || 'overview');
                }}
              >
                <Icon className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />
                <span className="text-xs font-semibold text-foreground">{val}</span>
                <span className="text-xs text-foreground/40">{label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 px-6 pt-4 border-b border-foreground/10 flex-shrink-0 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 pb-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                tab === t.id
                  ? 'border-violet-500 text-violet-600 dark:text-violet-400'
                  : 'border-transparent text-foreground/50 hover:text-foreground'
              }`}>
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex justify-center h-32 items-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-violet-500" />
            </div>
          ) : (
            <>
              {/* ─── Overview ─── */}
              {tab === 'overview' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <GlassCard className="p-5">
                    <h3 className="text-sm font-semibold text-foreground mb-3">Informasi Style</h3>
                    <InfoRow label="Kode Style" value={style.style_code} mono />
                    <InfoRow label="Nama Style" value={style.style_name} />
                    <InfoRow label="Kategori" value={style.category} />
                    <InfoRow label="Buyer" value={style.buyer} />
                    <InfoRow label="Season" value={style.season} />
                    <InfoRow label="Jenis Kain" value={style.fabric_type} />
                  </GlassCard>
                  <GlassCard className="p-5">
                    <h3 className="text-sm font-semibold text-foreground mb-3">Deskripsi</h3>
                    <p className="text-sm text-foreground/70">{style.description || '—'}</p>
                    <div className="mt-4 pt-4 border-t border-foreground/10">
                      <div className="text-xs text-foreground/40">Dibuat: {style.created_at ? new Date(style.created_at).toLocaleDateString('id-ID') : '—'}</div>
                      <div className="text-xs text-foreground/40">Update: {style.updated_at ? new Date(style.updated_at).toLocaleDateString('id-ID') : '—'}</div>
                    </div>
                  </GlassCard>
                </div>
              )}

              {/* ─── Variants ─── */}
              {tab === 'variants' && (
                <div className="space-y-3">
                  {(data?.variants || []).length === 0 ? (
                    <SectionEmpty icon={Layers} text="Belum ada varian untuk style ini." />
                  ) : (
                    (data?.variants || []).map(v => (
                      <GlassCard key={v.id} className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-7 h-7 rounded-lg border border-foreground/20 flex-shrink-0"
                            style={{ backgroundColor: v.color_code || '#888' }} />
                          <div className="flex-1">
                            <span className="font-semibold text-foreground">{v.color}</span>
                            <span className="text-xs text-foreground/40 ml-2">{v.color_code}</span>
                          </div>
                          <span className="text-xs text-foreground/40">{v.sizes?.filter(s => s.qty_plan > 0).length || 0} ukuran aktif</span>
                        </div>
                        {v.sizes?.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {v.sizes.filter(s => s.qty_plan > 0 || s.sku).map((s, i) => (
                              <div key={i} className="text-xs bg-foreground/5 border border-foreground/10 rounded-lg px-2.5 py-1.5">
                                <span className="font-bold">{s.size}</span>
                                {s.qty_plan > 0 && <span className="text-foreground/50 ml-1">× {s.qty_plan}</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </GlassCard>
                    ))
                  )}
                </div>
              )}

              {/* ─── Samples ─── */}
              {tab === 'samples' && (
                <div className="space-y-3">
                  {(data?.samples || []).length === 0 ? (
                    <SectionEmpty icon={FlaskConical} text="Belum ada sample request untuk style ini." />
                  ) : (
                    (data?.samples || []).map(s => {
                      const ss = STATUS_SAMPLE[s.status] || STATUS_SAMPLE.draft;
                      const Icon = ss.Icon;
                      return (
                        <GlassCard key={s.id} className="p-4">
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="font-mono text-sm font-semibold text-foreground">{s.sample_code}</span>
                              <span className="text-xs text-foreground/40 ml-3">{s.quantity} pcs · {s.priority}</span>
                            </div>
                            <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${ss.cls}`}>
                              <Icon className="w-3 h-3" />{ss.label}
                            </span>
                          </div>
                          {s.notes && <p className="text-xs text-foreground/50 mt-2">{s.notes}</p>}
                          {s.due_date && <p className="text-xs text-foreground/40 mt-1">Deadline: {new Date(s.due_date).toLocaleDateString('id-ID')}</p>}
                        </GlassCard>
                      );
                    })
                  )}
                </div>
              )}

              {/* ─── Patterns ─── */}
              {tab === 'patterns' && (
                <div className="space-y-3">
                  {(data?.patterns || []).length === 0 ? (
                    <SectionEmpty icon={Ruler} text="Belum ada dokumentasi pola untuk style ini." />
                  ) : (
                    (data?.patterns || []).map(p => (
                      <GlassCard key={p.id} className="p-4">
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-sm font-semibold">{p.pattern_code}</span>
                              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                                p.status === 'approved'
                                  ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30'
                                  : 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30'
                              }`}>{p.status === 'approved' ? 'Disetujui' : 'Draft'}</span>
                            </div>
                            <div className="text-xs text-foreground/50 mt-1">
                              Range: {p.size_range || '—'} · Penggunaan: {p.fabric_usage_per_pcs || '—'}m/pcs
                              {p.efficiency_pct ? ` · Efisiensi: ${p.efficiency_pct}%` : ''}
                            </div>
                            {p.hpp_fabric_per_pcs > 0 && (
                              <div className="text-xs text-violet-600 dark:text-violet-400 mt-1">HPP Bahan: {fmt(p.hpp_fabric_per_pcs)}/pcs</div>
                            )}
                          </div>
                        </div>
                        {p.notes && <p className="text-xs text-foreground/40 mt-2">{p.notes}</p>}
                      </GlassCard>
                    ))
                  )}
                </div>
              )}

              {/* ─── HPP ─── */}
              {tab === 'hpp' && (
                <div className="space-y-3">
                  {(data?.hpp_records || []).length === 0 ? (
                    <SectionEmpty icon={Calculator} text="Belum ada kalkulasi HPP untuk style ini." />
                  ) : (
                    (data?.hpp_records || []).map(r => (
                      <GlassCard key={r.id} className="p-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="font-mono text-sm font-semibold">{r.hpp_code}</span>
                            <div className="flex gap-4 text-xs text-foreground/60 mt-1.5">
                              <span>Direct: <strong className="text-foreground">{fmt(r.direct_cost)}</strong></span>
                              <span>Overhead: <strong className="text-foreground">{fmt(r.overhead_value)}</strong></span>
                              <span>HPP: <strong className="text-foreground">{fmt(r.hpp_total)}</strong></span>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-lg font-bold text-emerald-500">{fmt(r.selling_price_proposal)}</div>
                            <div className="text-xs text-emerald-500/60">Harga Jual Proposal</div>
                            <div className="text-xs text-foreground/40">Margin {r.margin_pct}%</div>
                          </div>
                        </div>
                      </GlassCard>
                    ))
                  )}
                </div>
              )}

              {/* ─── Revisions ─── */}
              {tab === 'revisions' && (
                <div>
                  {(data?.revisions || []).length === 0 ? (
                    <SectionEmpty icon={GitBranch} text="Belum ada revisi untuk style ini." />
                  ) : (
                    <div className="relative">
                      <div className="absolute left-4 top-0 bottom-0 w-px bg-violet-100 dark:bg-violet-500/20" />
                      <div className="space-y-3">
                        {(data?.revisions || []).map(r => (
                          <div key={r.id} className="relative pl-11">
                            <div className="absolute left-2.5 top-3 w-3 h-3 rounded-full bg-violet-500/30 border-2 border-violet-500" />
                            <GlassCard className="p-3.5">
                              <div className="font-medium text-sm text-foreground">{r.revision_name}</div>
                              <div className="text-xs text-foreground/40 mt-1">
                                #{r.revision_number} · {r.created_by_name} · {new Date(r.created_at).toLocaleDateString('id-ID')}
                              </div>
                              {r.changes_summary && <p className="text-sm text-foreground/70 mt-2">{r.changes_summary}</p>}
                              {(r.old_value || r.new_value) && (
                                <div className="flex gap-2 mt-2">
                                  {r.old_value && <span className="text-xs bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 px-2 py-0.5 rounded">− {r.old_value}</span>}
                                  {r.new_value && <span className="text-xs bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded">+ {r.new_value}</span>}
                                </div>
                              )}
                            </GlassCard>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ─── Tech Pack ─── */}
              {tab === 'techpack' && (
                <div className="space-y-3">
                  {(data?.tech_packs || []).length === 0 ? (
                    <SectionEmpty icon={FileText} text="Belum ada tech pack untuk style ini." />
                  ) : (
                    (data?.tech_packs || []).map(tp => (
                      <GlassCard key={tp.id} className="p-4">
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-foreground">{tp.title || `Tech Pack ${tp.version}`}</span>
                              <span className="text-xs font-mono text-foreground/40">{tp.version}</span>
                              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                                tp.status === 'approved' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30'
                                  : tp.status === 'superseded' ? 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30'
                                  : 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30'
                              }`}>{tp.status === 'approved' ? 'Disetujui' : tp.status === 'superseded' ? 'Digantikan' : 'Draft'}</span>
                            </div>
                            {tp.description && <p className="text-xs text-foreground/50 mt-1">{tp.description}</p>}
                            <div className="text-xs text-foreground/40 mt-1">Base Size: {tp.base_size} · Range: {tp.size_range}</div>
                            {tp.construction_notes && (
                              <p className="text-xs text-foreground/60 mt-2 italic">{tp.construction_notes}</p>
                            )}
                          </div>
                          {tp.doc_url && (
                            <a href={tp.doc_url} target="_blank" rel="noreferrer"
                              className="ml-4 flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400 hover:text-violet-600 dark:text-violet-300 flex-shrink-0">
                              <ExternalLink className="w-3.5 h-3.5" /> Lihat Dokumen
                            </a>
                          )}
                        </div>
                        {tp.bom_items?.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-foreground/10">
                            <div className="text-xs font-semibold text-foreground/40 mb-2">BOM</div>
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                              {tp.bom_items.map((b, i) => (
                                <div key={i} className="text-xs bg-foreground/[0.04] rounded px-2.5 py-1.5">
                                  <div className="font-medium text-foreground">{b.material}</div>
                                  <div className="text-foreground/40">{b.spec}</div>
                                  <div className="text-foreground/60 mt-0.5">{b.qty} {b.unit}{b.supplier ? ` · ${b.supplier}` : ''}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </GlassCard>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

