/**
 * SyncAuditModule — **Kesehatan Sinkronisasi Data** lintas portal (Sesi #20)
 * ═══════════════════════════════════════════════════════════════════════════
 * KENAPA LAYAR INI ADA
 * ───────────────────────────────────────────────────────────────────────────
 * Ketidaksinkronan yang membuat pemilik kehilangan kepercayaan ("id gudang dan
 * marketing tidak sama") baru ketahuan setelah seseorang menjalankan skrip
 * forensik di komputer pengembang. Pemilik tidak punya cara memeriksa sendiri,
 * jadi kerusakan senyap bisa berumur berbulan-bulan.
 *
 * Layar ini memindahkan pengukuran itu ke dalam aplikasi: 5 bagian (A–E),
 * temuan berperingkat, dan perbaikan yang **selalu bisa dipratinjau** sebelum
 * menulis. Angka datang dari `/api/sync-audit/report` (core/sync_audit.py) —
 * dihitung dari data hidup, bukan disalin dari laporan lama.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck, AlertTriangle, AlertCircle, Info, RefreshCw, Loader2, Eye,
  Wrench, CheckCircle2, ArrowRight, Link2, Database, Boxes, Store, Layers,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { apiGet, apiPost } from '@/lib/api';

const fmt = (v) => Number(v || 0).toLocaleString('id-ID');

const SEV = {
  CRITICAL: { label: 'KRITIS', icon: AlertCircle, chip: 'bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400/40' },
  HIGH: { label: 'TINGGI', icon: AlertTriangle, chip: 'bg-orange-100 dark:bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-400/40' },
  MED: { label: 'SEDANG', icon: Info, chip: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/40' },
  INFO: { label: 'INFO', icon: Info, chip: 'bg-sky-100 dark:bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/40' },
};

const VERDICT = {
  HIJAU: { text: 'Sinkron', chip: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/40', bar: 'bg-emerald-500' },
  KUNING: { text: 'Perlu perhatian', chip: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/40', bar: 'bg-amber-500' },
  MERAH: { text: 'Ada kerusakan tautan', chip: 'bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400/40', bar: 'bg-rose-500' },
};

const SECTION_ICON = { A: Store, B: Layers, C: Boxes, D: Database, E: Link2 };

const METRIC_LABEL = {
  orders: 'Pesanan marketing', lines: 'Baris pesanan', lines_linked: 'Baris tertaut',
  lines_linked_pct: '% baris tertaut', pcs: 'Total pcs', pcs_linked: 'Pcs tertaut',
  pcs_linked_pct: '% pcs tertaut', orders_ready: 'Pesanan siap dikerjakan',
  orders_partial: 'Pesanan sebagian tertaut', orders_blocked: 'Pesanan terhambat',
  queue_orders: 'Antrean gudang', queue_ready: 'Antrean siap',
  need_ship_not_in_queue: 'Perlu dikirim tapi di luar antrean',
  unmapped_sku_count: 'SKU platform belum dikenal', bridge_mappings: 'Pemetaan jembatan SKU',
  legacy_platform_sku_map: 'Pemetaan cara lama',
  items: 'Item katalog', linked: 'Item tertaut FG', dangling: 'Tautan FG rusak',
  fixable_by_sku: 'Bisa ditautkan lewat SKU', no_link: 'Tanpa tautan FG',
  stock_cache_drift: 'Cache stok melenceng', linked_without_stock_rows: 'Tertaut tanpa baris stok',
  variants: 'Varian model', fg_materials: 'Master FG', variants_with_fg: 'Varian punya FG',
  orphan_variants: 'Varian tanpa FG', fg_without_variant: 'FG tanpa varian',
  variants_with_fg_no_stock: 'Varian belum ada stok', variants_not_in_catalog: 'Varian belum dijual',
  sessions: 'Sesi opname', unknown_material_id: 'material_id asing',
  unknown_location_id: 'location_id asing', stock_dangling_material: 'Baris stok material hilang',
  stock_dangling_location: 'Baris stok lokasi hilang',
  rules_checked: 'Aturan diperiksa', broken_rules: 'Aturan rusak', empty_link_rules: 'Tautan tak pernah diisi',
};

function MetricGrid({ metrics }) {
  const entries = Object.entries(metrics || {}).filter(
    ([, v]) => typeof v === 'number' || typeof v === 'string');
  if (!entries.length) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-md border border-foreground/10 bg-foreground/[0.02] px-2.5 py-2">
          <div className="text-[11px] text-muted-foreground leading-tight">{METRIC_LABEL[k] || k}</div>
          <div className="text-sm font-semibold tabular-nums">
            {typeof v === 'number' ? fmt(v) : String(v)}
          </div>
        </div>
      ))}
    </div>
  );
}

function RepairCard({ repair, onRan }) {
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (apply) => {
    setBusy(true);
    try {
      const d = await apiPost('/sync-audit/repair', { action: repair.action, apply });
      setPreview(d);
      if (apply) { toast.success(d.message); onRan(); }
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-3"
         data-testid={`repair-${repair.action}`}>
      <div className="font-medium text-sm">{repair.label}</div>
      <p className="text-xs text-muted-foreground mt-1">{repair.explain}</p>
      {preview && (
        <div className="mt-2 rounded-md border border-blue-400/30 bg-blue-500/[0.06] px-2.5 py-2 text-xs"
             data-testid={`repair-result-${repair.action}`}>
          {preview.message}
        </div>
      )}
      <div className="flex gap-2 mt-2.5">
        <Button size="sm" variant="outline" onClick={() => run(false)} disabled={busy}
                className="border-foreground/10" data-testid={`repair-preview-${repair.action}`}>
          {busy ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Eye className="w-3.5 h-3.5 mr-1.5" />}
          Pratinjau
        </Button>
        <Button size="sm" onClick={() => run(true)} disabled={busy || !preview}
                data-testid={`repair-apply-${repair.action}`}>
          <Wrench className="w-3.5 h-3.5 mr-1.5" />Terapkan
        </Button>
      </div>
    </div>
  );
}

export default function SyncAuditModule({ onNavigate }) {
  const [report, setReport] = useState(null);
  const [repairs, setRepairs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, rp] = await Promise.all([
        apiGet('/sync-audit/report'),
        apiGet('/sync-audit/repairs'),
      ]);
      setReport(r); setRepairs(rp.repairs || []);
    } catch (e) { toast.error(`Gagal memuat audit: ${e.message}`); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const v = VERDICT[report?.verdict] || VERDICT.KUNING;
  const score = Number(report?.score || 0);

  return (
    <div className="space-y-5" data-testid="sync-audit-module">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-primary" />Sinkronisasi Data
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Memeriksa apakah data yang seharusnya saling menunjuk memang saling menunjuk:
            Marketing → Gudang, Katalog → Master FG, Varian → Stok, Stock Opname → Master,
            dan seluruh rujukan antar tabel.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="border-foreground/10"
                data-testid="refresh-audit">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />Periksa ulang
        </Button>
      </div>

      {loading && !report ? (
        <GlassCard className="p-14 text-center" hover={false}>
          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Mengukur tautan antar data…</p>
        </GlassCard>
      ) : !report ? null : (
        <>
          {/* Verdict */}
          <GlassCard className="p-5" hover={false} data-testid="audit-verdict">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <div className="text-4xl font-bold tabular-nums">{score}</div>
                  <div className="text-[11px] text-muted-foreground">skor</div>
                </div>
                <div>
                  <Badge variant="outline" className={`${v.chip} text-xs`} data-testid="verdict-badge">
                    {report.verdict} — {v.text}
                  </Badge>
                  <div className="flex gap-3 mt-2 text-xs text-muted-foreground">
                    {Object.entries(report.severity_counts || {}).map(([k, n]) => (
                      <span key={k}>{SEV[k]?.label || k}: <b>{fmt(n)}</b></span>
                    ))}
                  </div>
                </div>
              </div>
              {onNavigate && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" className="border-foreground/10"
                          onClick={() => onNavigate('sku-bridge')} data-testid="audit-goto-bridge">
                    <Link2 className="w-4 h-4 mr-1.5" />Jembatan SKU<ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                  <Button size="sm" variant="outline" className="border-foreground/10"
                          onClick={() => onNavigate('fulfillment')} data-testid="audit-goto-fulfillment">
                    <Boxes className="w-4 h-4 mr-1.5" />Antrean Gudang<ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                </div>
              )}
            </div>
            <div className="h-2 w-full rounded-full bg-foreground/10 overflow-hidden mt-4">
              <div className={`h-full ${v.bar} rounded-full transition-[width] duration-500`}
                   style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              Diperiksa {report.generated_at ? new Date(report.generated_at).toLocaleString('id-ID') : '—'}.
              Skor turun 25 per temuan KRITIS, 10 per TINGGI, 3 per SEDANG.
            </p>
          </GlassCard>

          {/* Temuan */}
          <GlassCard className="p-5" hover={false}>
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              Temuan ({fmt((report.findings || []).length)})
            </h3>
            {(report.findings || []).length === 0 ? (
              <div className="py-10 text-center" data-testid="audit-no-findings">
                <CheckCircle2 className="w-12 h-12 mx-auto text-emerald-500/50 mb-3" />
                <p className="font-medium">Tidak ada ketidaksinkronan yang terdeteksi.</p>
              </div>
            ) : (
              <div className="space-y-2" data-testid="audit-findings">
                {report.findings.map((f, i) => {
                  const s = SEV[f.severity] || SEV.INFO;
                  const Icon = s.icon;
                  return (
                    <div key={i} className="flex items-start gap-3 rounded-lg border border-foreground/10 bg-foreground/[0.02] p-3">
                      <Badge variant="outline" className={`${s.chip} text-[10px] shrink-0 mt-0.5`}>
                        <Icon className="w-3 h-3 mr-1" />{s.label}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm">{f.text}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">
                          {f.section}. {f.section_title} · kode {f.code}
                        </div>
                      </div>
                      {f.action === 'sku_bridge' && onNavigate && (
                        <Button size="sm" variant="outline" className="border-foreground/10 shrink-0"
                                onClick={() => onNavigate('sku-bridge')}
                                data-testid={`finding-action-${f.code}`}>
                          Buka Jembatan SKU
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </GlassCard>

          {/* Perbaikan */}
          <GlassCard className="p-5" hover={false}>
            <h3 className="font-semibold mb-1 flex items-center gap-2">
              <Wrench className="w-4 h-4 text-primary" />Perbaikan aman
            </h3>
            <p className="text-xs text-muted-foreground mb-3">
              Setiap perbaikan bisa <b>dipratinjau</b> lebih dulu (tidak menulis apa pun) dan
              aman dijalankan berulang. Tidak ada perbaikan yang menebak identitas barang —
              penebakan adalah pekerjaan manusia di Jembatan SKU.
            </p>
            <div className="grid md:grid-cols-2 gap-3">
              {repairs.map((r) => <RepairCard key={r.action} repair={r} onRan={load} />)}
            </div>
          </GlassCard>

          {/* Bagian A–E */}
          <div className="grid gap-4">
            {Object.entries(report.sections || {}).map(([key, sec]) => {
              const Icon = SECTION_ICON[key] || Database;
              return (
                <GlassCard key={key} className="p-5" hover={false} data-testid={`audit-section-${key}`}>
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4 text-primary" />
                    <h3 className="font-semibold">{key}. {sec.title}</h3>
                    {(sec.findings || []).length > 0 && (
                      <Badge variant="outline" className="text-[10px]">
                        {sec.findings.length} temuan
                      </Badge>
                    )}
                  </div>
                  <MetricGrid metrics={sec.metrics} />

                  {key === 'E' && (sec.rows || []).length > 0 && (
                    <div className="mt-3 rounded-lg border border-foreground/10 overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-foreground/[0.04] text-muted-foreground">
                          <tr>
                            <th className="text-left px-3 py-2 font-medium">Tabel.field</th>
                            <th className="text-left px-3 py-2 font-medium">Menunjuk ke</th>
                            <th className="text-right px-3 py-2 font-medium">Dokumen</th>
                            <th className="text-right px-3 py-2 font-medium">Terisi</th>
                            <th className="text-right px-3 py-2 font-medium">Rusak</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-foreground/5">
                          {sec.rows.slice(0, 30).map((r, i) => (
                            <tr key={i} className={r.dangling ? 'bg-rose-500/[0.06]' : ''}>
                              <td className="px-3 py-1.5 font-mono">{r.collection}.{r.field}</td>
                              <td className="px-3 py-1.5 text-muted-foreground">{r.note}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.docs)}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.filled)}</td>
                              <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${
                                r.dangling ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-600 dark:text-emerald-300'}`}>
                                {fmt(r.dangling)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {(sec.samples?.drift || []).length > 0 && (
                    <div className="mt-3">
                      <div className="text-xs font-semibold mb-1">Contoh cache stok melenceng</div>
                      <div className="rounded-lg border border-foreground/10 divide-y divide-foreground/5">
                        {sec.samples.drift.slice(0, 8).map((d, i) => (
                          <div key={i} className="px-3 py-1.5 text-xs flex justify-between gap-3">
                            <span className="font-mono">{d.sku}</span>
                            <span className="text-muted-foreground truncate flex-1">{d.name}</span>
                            <span>katalog <b>{fmt(d.cache)}</b> vs gudang <b>{fmt(d.live)}</b></span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </GlassCard>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
