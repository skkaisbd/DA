/**
 * MaklonBuyerCatalogDetailDialog — Phase M2 (M2.1 + M2.2 + M2.3)
 *
 * Modal detail untuk 1 entry Buyer Catalog dengan 3 tab:
 *   - Detail       : info ringkas + samples linked (M2.1)
 *   - Price History: audit trail harga (M2.3)
 *   - BOM Templates: versioned material recipes + apply-to-PO (M2.2)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { GlassCard } from '@/components/ui/glass';
import {
  History,
  Package2,
  ClipboardCheck,
  Plus,
  TrendingUp,
  TrendingDown,
  Layers,
  CheckCircle2,
  Trash2,
  Edit2,
  Save,
  X,
  AlertTriangle,
  ShieldAlert,
  Sparkles,
  Boxes,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const fmtRp = formatRupiah;
const fmtDate = (s) =>
  s ? new Date(s).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : '-';

export default function MaklonBuyerCatalogDetailDialog({ catalog, headers, onClose }) {
  if (!catalog) return null;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="max-w-4xl max-h-[92vh] overflow-hidden flex flex-col"
        data-testid="bc-detail-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-violet-400" />
            {catalog.product_name}
            <span className="text-xs font-mono bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded ml-2 border border-violet-400/25">
              {catalog.artikel_code}
            </span>
            {catalog.buyer_ref_code && (
              <span className="text-xs text-foreground/50">↳ {catalog.buyer_ref_code}</span>
            )}
          </DialogTitle>
          <div className="text-xs text-foreground/55 mt-0.5">
            {catalog.client_name} · {catalog.category || 'Uncategorized'} · Default CMT:{' '}
            <strong className="text-amber-400">{fmtRp(catalog.default_cmt_price)}</strong>
          </div>
        </DialogHeader>

        <Tabs defaultValue="detail" className="flex-1 flex flex-col overflow-hidden mt-2">
          <TabsList className="grid w-full max-w-xl grid-cols-4">
            <TabsTrigger value="detail" className="gap-1.5" data-testid="bc-tab-detail">
              <Package2 className="w-3.5 h-3.5" /> Detail
            </TabsTrigger>
            <TabsTrigger value="variants" className="gap-1.5" data-testid="bc-tab-variants">
              <Boxes className="w-3.5 h-3.5" /> Varian
            </TabsTrigger>
            <TabsTrigger value="price-history" className="gap-1.5" data-testid="bc-tab-price-history">
              <History className="w-3.5 h-3.5" /> Harga
            </TabsTrigger>
            <TabsTrigger value="bom-templates" className="gap-1.5" data-testid="bc-tab-bom-templates">
              <ClipboardCheck className="w-3.5 h-3.5" /> BOM
            </TabsTrigger>
          </TabsList>

          <TabsContent value="detail" className="flex-1 overflow-y-auto mt-3">
            <DetailTab catalog={catalog} headers={headers} />
          </TabsContent>
          <TabsContent value="variants" className="flex-1 overflow-y-auto mt-3">
            <VariantsTab catalog={catalog} headers={headers} />
          </TabsContent>
          <TabsContent value="price-history" className="flex-1 overflow-y-auto mt-3">
            <PriceHistoryTab catalog={catalog} headers={headers} />
          </TabsContent>
          <TabsContent value="bom-templates" className="flex-1 overflow-y-auto mt-3">
            <BOMTemplatesTab catalog={catalog} headers={headers} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// DETAIL TAB — info ringkas + linked samples
// ════════════════════════════════════════════════════════════════════════════
function DetailTab({ catalog, headers }) {
  const [samples, setSamples] = useState({ samples: [], summary: {} });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const r = await fetch(
          `/api/dewi/maklon/buyer-catalog/${catalog.id}/samples`,
          { headers }
        );
        if (r.ok && !cancelled) {
          setSamples(await r.json());
        }
      } catch (_e) {
        // silent
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [catalog.id, headers]);

  const sum = samples.summary || {};

  return (
    <div className="space-y-4">
      {/* Detail fields */}
      <GlassCard className="p-3 grid grid-cols-2 gap-3 text-sm">
        <Field label="Klien (Buyer)" value={catalog.client_name} />
        <Field label="Status" value={catalog.status} pill />
        <Field label="Kode Artikel" value={catalog.artikel_code} mono />
        <Field label="Ref Buyer" value={catalog.buyer_ref_code || '-'} mono />
        <Field label="Kategori" value={catalog.category || '-'} />
        <Field label="Season / Gender" value={`${catalog.season || '-'} / ${catalog.gender || '-'}`} />
        <Field label="Harga CMT Default" value={fmtRp(catalog.default_cmt_price)} accent="amber" />
        <Field label="Harga Jual Default" value={fmtRp(catalog.default_selling_price)} accent="emerald" />
        <Field
          label="Opsi Warna"
          value={(catalog.color_options || []).join(', ') || '-'}
          className="col-span-2"
        />
        <Field
          label="Opsi Ukuran"
          value={(catalog.size_options || []).join(', ') || '-'}
          className="col-span-2"
        />
        {catalog.description && (
          <div className="col-span-2 text-xs text-foreground/65 whitespace-pre-wrap">
            <div className="text-foreground/40 mb-1">Deskripsi:</div>
            {catalog.description}
          </div>
        )}
        <div className="col-span-2 grid grid-cols-3 gap-3 pt-2 border-t border-border text-xs">
          <Field
            label="Total Produksi"
            value={`${(catalog.total_qty_produced || 0).toLocaleString('id-ID')} pcs`}
            accent="cyan"
          />
          <Field
            label="Total Revenue"
            value={fmtRp(catalog.total_revenue || 0)}
            accent="emerald"
          />
          <Field label="Terakhir Dipakai" value={fmtDate(catalog.last_used_at)} />
        </div>
      </GlassCard>

      {/* Samples linked */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label className="text-sm font-medium">Sample Terlink (Phase M2.1)</Label>
          <div className="flex gap-2 text-xs">
            <span className="bg-green-500/15 text-green-300 px-2 py-0.5 rounded border border-green-400/25">
              {sum.approved || 0} approved
            </span>
            <span className="bg-amber-500/15 text-amber-300 px-2 py-0.5 rounded border border-amber-400/25">
              {sum.in_progress || 0} on-going
            </span>
            <span className="bg-red-500/15 text-red-300 px-2 py-0.5 rounded border border-red-400/25">
              {sum.rejected || 0} rejected
            </span>
          </div>
        </div>
        {loading ? (
          <div className="text-center py-4 text-foreground/40 text-xs">Memuat samples...</div>
        ) : samples.samples?.length === 0 ? (
          <div className="text-center py-6 text-foreground/40 text-xs border border-dashed border-border rounded-lg">
            Belum ada sample terlink ke artikel ini.
            <br />
            <span className="text-[10px]">
              Saat buat Sample di menu Sample Management, pilih artikel ini sebagai referensi.
            </span>
          </div>
        ) : (
          <div className="space-y-1.5">
            {samples.samples.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between p-2 rounded border border-border/60 bg-foreground/[0.03] text-xs"
                data-testid={`bc-linked-sample-${s.id}`}
              >
                <div>
                  <div className="font-mono text-violet-300">{s.sample_code}</div>
                  <div className="text-foreground/60 mt-0.5">
                    {s.product_name} · {s.target_size} · {s.color_used || '-'}
                  </div>
                </div>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    s.status === 'approved'
                      ? 'bg-green-500/15 text-green-300 border-green-400/30'
                      : s.status === 'rejected'
                      ? 'bg-red-500/15 text-red-300 border-red-400/30'
                      : 'bg-amber-500/15 text-amber-300 border-amber-400/30'
                  }`}
                >
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono, pill, accent, className }) {
  const accentClass =
    accent === 'amber'
      ? 'text-amber-400'
      : accent === 'emerald'
      ? 'text-emerald-400'
      : accent === 'cyan'
      ? 'text-cyan-400'
      : 'text-foreground';
  return (
    <div className={className}>
      <div className="text-[10px] text-foreground/45 uppercase tracking-wide">{label}</div>
      {pill ? (
        <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-foreground/[0.08] mt-0.5">{value}</span>
      ) : (
        <div className={`text-sm ${accentClass} ${mono ? 'font-mono' : ''}`}>{value}</div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// VARIANTS TAB — Fase 3: varian ber-SKU maklon (SKU = artikel-warna-size)
// ════════════════════════════════════════════════════════════════════════════
function VariantsTab({ catalog, headers }) {
  const [variants, setVariants] = useState(catalog.variants || []);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [refDraft, setRefDraft] = useState('');

  const colors = catalog.color_options || [];
  const sizes = catalog.size_options || [];
  const canGenerate = colors.length > 0 && sizes.length > 0;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/dewi/maklon/buyer-catalog/${catalog.id}`, { headers });
      if (r.ok) {
        const d = await r.json();
        setVariants(d.variants || []);
      }
    } catch (_e) { /* silent */ }
    finally { setLoading(false); }
  }, [catalog.id, headers]);

  useEffect(() => { reload(); }, [reload]);

  const generate = async () => {
    setGenerating(true);
    try {
      const r = await fetch(`/api/dewi/maklon/buyer-catalog/${catalog.id}/variants/generate`, {
        method: 'POST', headers,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { toast.error(d.detail || 'Gagal generate varian'); return; }
      toast.success(`Varian: total ${d.total}, baru ${d.created}`);
      setVariants(d.variants || []);
    } finally { setGenerating(false); }
  };

  const saveRef = async (v) => {
    const r = await fetch(`/api/dewi/maklon/buyer-catalog/${catalog.id}/variants/${v.id}`, {
      method: 'PUT', headers, body: JSON.stringify({ buyer_ref_code: refDraft }),
    });
    if (r.ok) {
      toast.success('Kode ref buyer disimpan');
      setEditingId(null);
      reload();
    } else toast.error('Gagal menyimpan');
  };

  const toggleActive = async (v) => {
    const r = await fetch(`/api/dewi/maklon/buyer-catalog/${catalog.id}/variants/${v.id}`, {
      method: 'PUT', headers, body: JSON.stringify({ active: !(v.active !== false) }),
    });
    if (r.ok) reload();
    else toast.error('Gagal update status');
  };

  return (
    <div className="space-y-3" data-testid="bc-variants-tab">
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs text-foreground/60 bg-foreground/[0.03] rounded p-2 border border-border/60 flex-1">
          Varian ber-SKU otomatis dari kombinasi <strong>Opsi Warna × Opsi Ukuran</strong>.
          Format SKU: <span className="font-mono text-violet-300">{catalog.artikel_code}-WARNA-SIZE</span>.
          Isi <strong>Kode Ref Buyer</strong> per varian bila buyer punya kode sendiri.
        </div>
        <Button size="sm" onClick={generate} disabled={!canGenerate || generating}
          className="gap-1.5 shrink-0" data-testid="bc-variant-generate-btn">
          <Sparkles className="w-3.5 h-3.5" /> {generating ? 'Membuat...' : 'Generate Varian'}
        </Button>
      </div>

      {!canGenerate && (
        <div className="text-[11px] text-amber-400 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" />
          Lengkapi Opsi Warna & Opsi Ukuran di tab Detail (edit artikel) sebelum generate.
        </div>
      )}

      {loading ? (
        <div className="text-center py-6 text-foreground/40 text-sm">Memuat varian...</div>
      ) : variants.length === 0 ? (
        <div className="text-center py-8 text-foreground/40 text-sm border border-dashed border-border rounded">
          Belum ada varian. Klik <strong>Generate Varian</strong> untuk membuat matriks SKU.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-foreground/55">
                <th className="text-left p-2 font-normal">SKU (kita)</th>
                <th className="text-left p-2 font-normal">Warna</th>
                <th className="text-left p-2 font-normal">Size</th>
                <th className="text-left p-2 font-normal">Kode Ref Buyer</th>
                <th className="text-center p-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {variants.map((v) => (
                <tr key={v.id} className={`border-b border-foreground/5 ${v.active === false ? 'opacity-50' : ''}`}
                  data-testid={`bc-variant-row-${v.sku}`}>
                  <td className="p-2 font-mono text-violet-300">{v.sku}</td>
                  <td className="p-2">{v.color} <span className="text-foreground/40">({v.color_code})</span></td>
                  <td className="p-2 font-mono">{v.size}</td>
                  <td className="p-2">
                    {editingId === v.id ? (
                      <div className="flex items-center gap-1">
                        <Input value={refDraft} onChange={(e) => setRefDraft(e.target.value)}
                          className="h-7 text-xs w-36" placeholder="Kode buyer"
                          data-testid={`bc-variant-ref-input-${v.sku}`} />
                        <Button size="icon" variant="ghost" className="h-6 w-6 text-emerald-400"
                          onClick={() => saveRef(v)} data-testid={`bc-variant-ref-save-${v.sku}`}>
                          <Save className="w-3 h-3" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditingId(null)}>
                          <X className="w-3 h-3" />
                        </Button>
                      </div>
                    ) : (
                      <button className="flex items-center gap-1.5 hover:text-violet-300 group"
                        onClick={() => { setEditingId(v.id); setRefDraft(v.buyer_ref_code || ''); }}
                        data-testid={`bc-variant-ref-edit-${v.sku}`}>
                        <span className={v.buyer_ref_code ? 'font-mono' : 'text-foreground/35 italic'}>
                          {v.buyer_ref_code || 'set kode…'}
                        </span>
                        <Edit2 className="w-2.5 h-2.5 opacity-0 group-hover:opacity-60" />
                      </button>
                    )}
                  </td>
                  <td className="p-2 text-center">
                    <button onClick={() => toggleActive(v)} data-testid={`bc-variant-toggle-${v.sku}`}
                      className={`text-[10px] px-2 py-0.5 rounded border ${
                        v.active === false
                          ? 'bg-foreground/5 text-foreground/40 border-border/60'
                          : 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
                      }`}>
                      {v.active === false ? 'Nonaktif' : 'Aktif'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-right text-[10px] text-foreground/45 mt-1">{variants.length} varian</div>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PRICE HISTORY TAB — Phase M2.3
// ════════════════════════════════════════════════════════════════════════════
function PriceHistoryTab({ catalog, headers }) {
  const [data, setData] = useState({ price_history: [], thresholds: {} });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const r = await fetch(
          `/api/dewi/maklon/buyer-catalog/${catalog.id}/price-history`,
          { headers }
        );
        if (r.ok && !cancelled) setData(await r.json());
      } catch (_e) {
        // silent
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [catalog.id, headers]);

  const history = data.price_history || [];
  const t = data.thresholds || {};

  return (
    <div className="space-y-3">
      <div className="text-xs text-foreground/60 bg-foreground/[0.03] rounded p-2 border border-border/60">
        Audit trail tiap perubahan harga (master update / PO create). Threshold drift:{' '}
        <span className="text-amber-400 font-medium">warning ≥{t.warn_pct || 10}%</span>,{' '}
        <span className="text-red-400 font-medium">block ≥{t.block_pct || 25}%</span>.
      </div>

      {loading ? (
        <div className="text-center py-6 text-foreground/40 text-sm">Memuat history...</div>
      ) : history.length === 0 ? (
        <div className="text-center py-8 text-foreground/40 text-sm border border-dashed border-border rounded">
          Belum ada perubahan harga tercatat.
        </div>
      ) : (
        <div className="space-y-2">
          {history.map((h) => {
            const delta = (h.new_cmt_price || 0) - (h.old_cmt_price || 0);
            const pct = h.old_cmt_price > 0 ? (delta / h.old_cmt_price) * 100 : 0;
            const isUp = delta > 0;
            const isDown = delta < 0;
            const TrendIcon = isUp ? TrendingUp : isDown ? TrendingDown : Sparkles;
            const trendColor = isUp
              ? 'text-emerald-400'
              : isDown
              ? 'text-red-400'
              : 'text-foreground/50';
            return (
              <div
                key={h.id}
                className="p-2.5 rounded border border-border/60 bg-foreground/[0.03] text-xs"
                data-testid={`bc-price-history-${h.id}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded border border-violet-400/25">
                      {h.event_type}
                    </span>
                    {h.po_number && (
                      <span className="text-[10px] font-mono text-cyan-300">{h.po_number}</span>
                    )}
                    <span className="text-foreground/50 text-[10px]">
                      {fmtDate(h.timestamp)} · {h.changed_by_name}
                    </span>
                  </div>
                  <div className={`flex items-center gap-1 font-mono ${trendColor}`}>
                    <TrendIcon className="w-3 h-3" />
                    {pct > 0 ? '+' : ''}
                    {pct.toFixed(1)}%
                  </div>
                </div>
                <div className="flex items-center gap-2 text-foreground/75">
                  <span className="text-foreground/45">{fmtRp(h.old_cmt_price)}</span>
                  <span className="text-foreground/40">→</span>
                  <span className={`font-semibold ${trendColor}`}>{fmtRp(h.new_cmt_price)}</span>
                </div>
                {h.note && (
                  <div className="text-foreground/50 text-[10px] mt-1 italic">"{h.note}"</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BOM TEMPLATES TAB — Phase M2.2
// ════════════════════════════════════════════════════════════════════════════
function BOMTemplatesTab({ catalog, headers }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState(null); // null | { mode: 'create'|'edit', data }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(
        `/api/dewi/maklon/bom-templates?buyer_catalog_id=${catalog.id}`,
        { headers }
      );
      if (r.ok) setTemplates(await r.json());
    } catch (_e) {
      // silent
    } finally {
      setLoading(false);
    }
  }, [catalog.id, headers]);

  useEffect(() => {
    load();
  }, [load]);

  const activate = async (t) => {
    const r = await fetch(`/api/dewi/maklon/bom-templates/${t.id}/activate`, {
      method: 'POST',
      headers,
    });
    if (r.ok) {
      toast.success(`v${t.version} sekarang aktif`);
      load();
    } else toast.error('Gagal aktivasi');
  };

  const removeT = async (t) => {
    if (!window.confirm(`Hapus permanen BOM Template v${t.version}? Tidak bisa dibatalkan.`)) return;
    const r = await fetch(`/api/dewi/maklon/bom-templates/${t.id}`, {
      method: 'DELETE',
      headers,
    });
    if (r.ok) {
      toast.success('Template dihapus');
      load();
    } else toast.error('Gagal hapus');
  };

  if (editor) {
    return (
      <BOMTemplateEditor
        mode={editor.mode}
        data={editor.data}
        catalog={catalog}
        headers={headers}
        onClose={() => setEditor(null)}
        onSaved={() => {
          setEditor(null);
          load();
        }}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-foreground/60 bg-foreground/[0.03] rounded p-2 border border-border/60 flex-1 mr-2">
          BOM Template menyimpan resep material per artikel. Bisa multi-versi (v1, v2, ...). Hanya
          1 versi aktif (default saat "Apply to PO BOM").
        </div>
        <Button
          size="sm"
          onClick={() => setEditor({ mode: 'create', data: null })}
          className="gap-1.5"
          data-testid="bom-template-add-btn"
        >
          <Plus className="w-3.5 h-3.5" /> Versi Baru
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-6 text-foreground/40 text-sm">Memuat templates...</div>
      ) : templates.length === 0 ? (
        <div className="text-center py-8 text-foreground/40 text-sm border border-dashed border-border rounded">
          Belum ada BOM Template untuk artikel ini.
          <br />
          <span className="text-[10px]">Klik "Versi Baru" untuk membuat resep material pertama.</span>
        </div>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <div
              key={t.id}
              className={`p-3 rounded-lg border ${
                t.is_active
                  ? 'border-emerald-400/30 bg-emerald-500/5'
                  : 'border-border/60 bg-foreground/[0.03]'
              }`}
              data-testid={`bom-template-${t.id}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-sm font-bold text-violet-300">v{t.version}</span>
                  <span className="text-sm">{t.version_label}</span>
                  {t.is_active && (
                    <span className="text-[10px] bg-emerald-500/15 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-400/30 flex items-center gap-0.5">
                      <CheckCircle2 className="w-2.5 h-2.5" /> AKTIF
                    </span>
                  )}
                </div>
                <div className="flex gap-1">
                  {!t.is_active && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={() => activate(t)}
                      data-testid={`bom-template-activate-${t.id}`}
                    >
                      Aktifkan
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={() => setEditor({ mode: 'edit', data: t })}
                    data-testid={`bom-template-edit-${t.id}`}
                  >
                    <Edit2 className="w-3 h-3" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 text-red-400 hover:bg-red-500/10"
                    onClick={() => removeT(t)}
                    data-testid={`bom-template-delete-${t.id}`}
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </div>
              <div className="text-xs text-foreground/60 flex gap-3 flex-wrap">
                <span>📦 {t.material_count} material</span>
                <span>
                  💰 Cost/pcs: <strong className="text-amber-400">{fmtRp(t.total_cost_per_pcs)}</strong>
                </span>
                <span className="text-foreground/40">· {fmtDate(t.updated_at)}</span>
              </div>
              {t.materials?.length > 0 && (
                <div className="mt-2 text-[10px] text-foreground/50 flex flex-wrap gap-1">
                  {t.materials.slice(0, 5).map((m, i) => (
                    <span
                      key={i}
                      className="bg-foreground/5 px-1.5 py-0.5 rounded border border-border/60"
                    >
                      {m.material_name}
                    </span>
                  ))}
                  {t.materials.length > 5 && (
                    <span className="text-foreground/35">+{t.materials.length - 5} lagi</span>
                  )}
                </div>
              )}
              {t.notes && (
                <div className="mt-1.5 text-[10px] text-foreground/50 italic">"{t.notes}"</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── BOM Template Editor (create/edit) ─────────────────────────────────────
function BOMTemplateEditor({ mode, data, catalog, headers, onClose, onSaved }) {
  const [form, setForm] = useState({
    version_label: data?.version_label || '',
    materials: data?.materials?.length ? data.materials.map((m) => ({ ...m })) : [
      { material_name: '', category: '', unit: 'pcs', qty_per_pcs: 0, cost_per_unit: 0, supplier: '', notes: '' },
    ],
    notes: data?.notes || '',
    set_active: data ? !!data.is_active : true,
  });
  const [saving, setSaving] = useState(false);

  const totalCost = useMemo(
    () =>
      form.materials.reduce(
        (s, m) => s + (Number(m.qty_per_pcs) || 0) * (Number(m.cost_per_unit) || 0),
        0
      ),
    [form.materials]
  );

  const updateMat = (idx, field, val) =>
    setForm((f) => ({
      ...f,
      materials: f.materials.map((m, i) => (i === idx ? { ...m, [field]: val } : m)),
    }));
  const addMat = () =>
    setForm((f) => ({
      ...f,
      materials: [
        ...f.materials,
        { material_name: '', category: '', unit: 'pcs', qty_per_pcs: 0, cost_per_unit: 0, supplier: '', notes: '' },
      ],
    }));
  const removeMat = (idx) =>
    setForm((f) => ({ ...f, materials: f.materials.filter((_, i) => i !== idx) }));

  const save = async () => {
    if (form.materials.length === 0) return toast.error('Minimal 1 material');
    if (form.materials.some((m) => !m.material_name.trim())) return toast.error('Nama material wajib diisi');
    setSaving(true);
    try {
      const url =
        mode === 'edit'
          ? `/api/dewi/maklon/bom-templates/${data.id}`
          : '/api/dewi/maklon/bom-templates';
      const method = mode === 'edit' ? 'PUT' : 'POST';
      const body = JSON.stringify(
        mode === 'edit'
          ? {
              version_label: form.version_label,
              materials: form.materials,
              notes: form.notes,
            }
          : {
              buyer_catalog_id: catalog.id,
              version_label: form.version_label,
              materials: form.materials,
              notes: form.notes,
              set_active: form.set_active,
            }
      );
      const r = await fetch(url, { method, headers, body });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || 'Gagal');
      }
      toast.success(mode === 'edit' ? 'Template diperbarui' : 'Template baru dibuat');
      onSaved();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="bom-template-editor">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium flex items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-violet-400" />
          {mode === 'edit' ? `Edit BOM Template v${data.version}` : 'BOM Template Baru'}
        </div>
        <Button size="sm" variant="outline" onClick={onClose}>
          <X className="w-3.5 h-3.5 mr-1" /> Kembali
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Label Versi</Label>
          <Input
            value={form.version_label}
            onChange={(e) => setForm({ ...form, version_label: e.target.value })}
            placeholder={`v${data?.version || 'baru'} — misal: "Initial Material" atau "Revisi Q3"`}
            className="h-9"
            data-testid="bom-editor-version-label"
          />
        </div>
        <div className="flex items-end">
          {mode === 'create' && (
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={form.set_active}
                onChange={(e) => setForm({ ...form, set_active: e.target.checked })}
                className="accent-violet-500"
                data-testid="bom-editor-set-active"
              />
              Jadikan versi aktif (deactivate versi lain)
            </label>
          )}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <Label className="text-xs">Material (per pcs produk)</Label>
          <Button size="sm" variant="outline" onClick={addMat} className="h-7 text-xs">
            <Plus className="w-3 h-3 mr-1" /> Tambah Material
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-foreground/55">
                <th className="text-left p-1.5 font-normal">Material *</th>
                <th className="text-left p-1.5 font-normal">Kategori</th>
                <th className="text-left p-1.5 font-normal">Unit</th>
                <th className="text-right p-1.5 font-normal">Qty/pcs</th>
                <th className="text-right p-1.5 font-normal">Cost/unit</th>
                <th className="text-left p-1.5 font-normal">Supplier</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {form.materials.map((m, idx) => (
                <tr key={idx} className="border-b border-foreground/5">
                  <td className="p-1">
                    <Input
                      value={m.material_name}
                      onChange={(e) => updateMat(idx, 'material_name', e.target.value)}
                      placeholder="Linen Premium"
                      className="h-7 text-xs"
                      data-testid={`bom-mat-${idx}-name`}
                    />
                  </td>
                  <td className="p-1">
                    <Input
                      value={m.category}
                      onChange={(e) => updateMat(idx, 'category', e.target.value)}
                      placeholder="Fabric"
                      className="h-7 text-xs w-24"
                    />
                  </td>
                  <td className="p-1">
                    <Input
                      value={m.unit}
                      onChange={(e) => updateMat(idx, 'unit', e.target.value)}
                      className="h-7 text-xs w-16"
                    />
                  </td>
                  <td className="p-1">
                    <Input
                      type="number"
                      step="0.01"
                      value={m.qty_per_pcs}
                      onChange={(e) => updateMat(idx, 'qty_per_pcs', e.target.value)}
                      className="h-7 text-xs w-20 text-right"
                    />
                  </td>
                  <td className="p-1">
                    <Input
                      type="number"
                      value={m.cost_per_unit}
                      onChange={(e) => updateMat(idx, 'cost_per_unit', e.target.value)}
                      className="h-7 text-xs w-24 text-right"
                    />
                  </td>
                  <td className="p-1">
                    <Input
                      value={m.supplier}
                      onChange={(e) => updateMat(idx, 'supplier', e.target.value)}
                      placeholder="Supplier"
                      className="h-7 text-xs w-28"
                    />
                  </td>
                  <td className="p-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6 text-red-400 hover:bg-red-500/10"
                      onClick={() => removeMat(idx)}
                    >
                      <X className="w-3 h-3" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-right mt-2 text-xs text-foreground/65">
          Total Cost/pcs: <strong className="text-amber-400">{fmtRp(totalCost)}</strong>
        </div>
      </div>

      <div>
        <Label className="text-xs">Catatan Versi</Label>
        <Textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          rows={2}
          placeholder="Apa yang berubah di versi ini?"
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onClose} disabled={saving}>
          Batal
        </Button>
        <Button onClick={save} disabled={saving} data-testid="bom-editor-save">
          <Save className="w-3.5 h-3.5 mr-1" />
          {saving ? 'Menyimpan...' : mode === 'edit' ? 'Update' : 'Buat Versi'}
        </Button>
      </div>
    </div>
  );
}
