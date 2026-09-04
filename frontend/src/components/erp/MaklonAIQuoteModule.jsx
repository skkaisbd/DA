import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  Calculator, Sparkles, Loader2, Receipt, History, AlertTriangle,
  ThumbsUp, ChevronRight, Trash2, CheckCircle2
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';
import BuyerCatalogSelect from './pickers/BuyerCatalogSelect';

const CATEGORY_OPTIONS = [
  { value: 'kaos', label: 'Kaos / T-Shirt' },
  { value: 'kemeja', label: 'Kemeja' },
  { value: 'hijab', label: 'Hijab' },
  { value: 'celana', label: 'Celana' },
  { value: 'outerwear', label: 'Outerwear / Jaket' },
  { value: 'general', label: 'Lainnya' },
];

const MARKET_OPTIONS = [
  { value: 'mass', label: 'Mass Market' },
  { value: 'mid', label: 'Mid Market' },
  { value: 'premium', label: 'Premium' },
  { value: 'luxury', label: 'Luxury' },
];

const COMPETITIVENESS_COLOR = {
  high: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30',
  medium: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-400 dark:border-amber-500/30',
  low: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400 border-red-400 dark:border-red-500/30',
  'n/a': 'bg-muted dark:bg-slate-500/15 text-muted-foreground dark:text-muted-foreground border-border dark:border-slate-500/30',
};

const fmtIDR = (v) => (v == null) ? '—' : formatRupiah(v);

export default function MaklonAIQuoteModule({ token }) {
  const [activeTab, setActiveTab] = useState('generate');
  const [form, setForm] = useState({
    product_name: '',
    // F14b — kalau artikelnya sudah ada di Katalog Buyer, penawaran menempel
    // pada artikel itu (`buyer_catalog_id`). `is_new_article` membuat jumlah
    // penawaran untuk artikel yang belum terdaftar bisa DIHITUNG, bukan
    // tersembunyi di antara teks bebas.
    buyer_catalog_id: '',
    is_new_article: true,
    category: 'kaos',
    quantity: 1000,
    target_market: 'mid',
    target_unit_price: '',
    materials: '',
    finishing: '',
    required_lead_time_days: '',
    client_name: '',
    additional_notes: '',
    target_margin_pct: 25,
  });
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const BASE = process.env.REACT_APP_BACKEND_URL;

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/maklon/ai-quote/history?limit=30`, { headers });
      const data = await r.json();
      setHistory(data?.data || []);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const generate = async () => {
    if (!form.product_name?.trim()) {
      toast.error('Product name wajib diisi');
      return;
    }
    if (!form.quantity || Number(form.quantity) <= 0) {
      toast.error('Quantity harus > 0');
      return;
    }
    setGenerating(true);
    setResult(null);
    try {
      const body = {
        ...form,
        quantity: Number(form.quantity),
        target_unit_price: form.target_unit_price ? Number(form.target_unit_price) : null,
        required_lead_time_days: form.required_lead_time_days ? Number(form.required_lead_time_days) : null,
        target_margin_pct: Number(form.target_margin_pct) || 25,
      };
      const r = await fetch(`${BASE}/api/maklon/ai-quote/generate`, {
        method: 'POST', headers, body: JSON.stringify(body),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t.slice(0, 200));
      }
      const data = await r.json();
      setResult(data?.data || null);
      toast.success('Quote berhasil dibuat', { icon: <Sparkles className="w-4 h-4" /> });
      fetchHistory();
    } catch (e) {
      toast.error(`Gagal generate: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const openDetail = (q) => {
    setDetail(q);
    setDetailOpen(true);
  };

  const acceptQuote = async (id) => {
    try {
      const r = await fetch(`${BASE}/api/maklon/ai-quote/${id}/accept`, { method: 'POST', headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Quote ditandai accepted');
      fetchHistory();
      setDetailOpen(false);
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  const deleteQuote = async (id) => {
    if (!confirm('Hapus quote ini?')) return;
    try {
      const r = await fetch(`${BASE}/api/maklon/ai-quote/${id}`, { method: 'DELETE', headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Quote dihapus');
      fetchHistory();
      setDetailOpen(false);
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  const renderResult = (r) => {
    if (!r) return null;
    const res = r.result || r;
    return (
      <div className="space-y-4">
        <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-300 dark:border-emerald-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold flex items-center gap-1"><Calculator className="w-4 h-4 text-emerald-500" /> Estimated Unit Price</span>
            {res.competitiveness && (
              <Badge className={COMPETITIVENESS_COLOR[res.competitiveness] || ''} variant="outline">
                {res.competitiveness === 'high' ? '🟢 Kompetitif' : res.competitiveness === 'medium' ? '🟡 Medium' : res.competitiveness === 'low' ? '🔴 Mahal' : 'n/a'}
              </Badge>
            )}
          </div>
          <div className="flex items-baseline gap-4">
            <span className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{fmtIDR(res.estimated_unit_price)}</span>
            <span className="text-sm text-muted-foreground">/ pcs</span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Total order: <span className="font-semibold text-foreground">{fmtIDR(res.estimated_total)}</span> · Lead time ~{res.estimated_lead_time_days} hari · Margin {res.margin_pct}%
          </div>
        </div>

        {res.hpp_breakdown && (
          <div>
            <h4 className="text-sm font-semibold mb-2">HPP Breakdown (per pcs)</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <MiniStat label="Material" value={fmtIDR(res.hpp_breakdown.material)} />
              <MiniStat label="Labor" value={fmtIDR(res.hpp_breakdown.labor)} />
              <MiniStat label="Overhead" value={fmtIDR(res.hpp_breakdown.overhead)} />
              <MiniStat label="Finishing" value={fmtIDR(res.hpp_breakdown.finishing)} />
            </div>
            <div className="mt-2 p-2 rounded bg-[var(--glass)] text-xs text-muted-foreground">
              Margin: <span className="text-foreground font-medium">{fmtIDR(res.margin_amount)}</span> ({res.margin_pct}% over HPP)
            </div>
          </div>
        )}

        {res.summary && (
          <div>
            <h4 className="text-sm font-semibold mb-2">Summary</h4>
            <div className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] text-sm whitespace-pre-wrap text-muted-foreground">{res.summary}</div>
          </div>
        )}

        {res.risks?.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-500" /> Risks</h4>
            <ul className="space-y-1">
              {res.risks.map((rk, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <span className="text-amber-700 dark:text-amber-500 mt-0.5">⚠️</span><span>{rk}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {res.recommendations?.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2 flex items-center gap-2"><ThumbsUp className="w-4 h-4 text-emerald-500" /> Recommendations</h4>
            <ul className="space-y-1">
              {res.recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <ChevronRight className="w-3.5 h-3.5 mt-0.5 text-emerald-500" /><span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {res.source && (
          <p className="text-[10px] text-muted-foreground text-right">Source: {res.source}</p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Calculator className="w-6 h-6 text-emerald-500" /> AI Quote Generator
        </h1>
        <p className="text-sm text-muted-foreground">
          Generate quotation maklon AI dengan HPP breakdown, margin, lead time, dan rekomendasi (Emergent LLM).
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-2 w-full md:w-[360px]">
          <TabsTrigger value="generate" data-testid="quote-tab-generate"><Sparkles className="w-4 h-4 mr-1.5" /> Generate</TabsTrigger>
          <TabsTrigger value="history" data-testid="quote-tab-history"><History className="w-4 h-4 mr-1.5" /> History ({history.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="generate" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GlassCard className="p-6">
              <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><Receipt className="w-4 h-4 text-blue-500" /> Input Requirement</h3>
              <div className="space-y-3">
                <div>
                  {/* F14b — artikel yang SUDAH ada di Katalog Buyer dipilih,
                      bukan diketik ulang; artikel yang memang belum ada tetap
                      boleh diketik TAPI ditandai. Lihat komponennya. */}
                  <BuyerCatalogSelect
                    token={token}
                    value={form.buyer_catalog_id}
                    newName={form.product_name}
                    label="Produk / Artikel"
                    testId="quote-product-select"
                    onPick={(cat) => setForm((p) => ({
                      ...p,
                      buyer_catalog_id: cat?.id || '',
                      is_new_article: !cat,
                      product_name: cat?.product_name || '',
                      client_name: cat?.client_name || p.client_name,
                      materials: cat?.description || p.materials,
                    }))}
                    onNewName={(v) => setForm((p) => ({
                      ...p, product_name: v, buyer_catalog_id: '', is_new_article: true,
                    }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Category</Label>
                    <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {CATEGORY_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Target Market</Label>
                    <Select value={form.target_market} onValueChange={(v) => setForm({ ...form, target_market: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {MARKET_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <Label>Quantity *</Label>
                    <Input data-testid="quote-qty" type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
                  </div>
                  <div>
                    <Label>Target Unit Price (Rp)</Label>
                    <Input type="number" value={form.target_unit_price} onChange={(e) => setForm({ ...form, target_unit_price: e.target.value })} placeholder="opsional" />
                  </div>
                  <div>
                    <Label>Margin (%)</Label>
                    <Input type="number" value={form.target_margin_pct} onChange={(e) => setForm({ ...form, target_margin_pct: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Materials</Label>
                  <Input value={form.materials} onChange={(e) => setForm({ ...form, materials: e.target.value })} placeholder="Mis. Cotton combed 30s, gramasi 180gsm" />
                </div>
                <div>
                  <Label>Finishing</Label>
                  <Input value={form.finishing} onChange={(e) => setForm({ ...form, finishing: e.target.value })} placeholder="Mis. sablon rubber + bordir logo" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Lead Time Klien (hari)</Label>
                    <Input type="number" value={form.required_lead_time_days} onChange={(e) => setForm({ ...form, required_lead_time_days: e.target.value })} placeholder="opsional" />
                  </div>
                  <div>
                    <Label>Client Name</Label>
                    <Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Catatan Tambahan</Label>
                  <Textarea value={form.additional_notes} onChange={(e) => setForm({ ...form, additional_notes: e.target.value })} rows={2} placeholder="Spesifikasi khusus, packaging, dll" />
                </div>
                <Button onClick={generate} disabled={generating} className="w-full" data-testid="quote-generate-btn">
                  {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generating Quote (10-30s)...</> : <><Sparkles className="w-4 h-4 mr-2" /> Generate AI Quote</>}
                </Button>
              </div>
            </GlassCard>

            <GlassCard className="p-6">
              <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><Receipt className="w-4 h-4 text-emerald-500" /> Quote Result</h3>
              {result ? renderResult(result) : (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  <Sparkles className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  Quote akan muncul di sini setelah Generate.
                </div>
              )}
            </GlassCard>
          </div>
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          {history.length === 0 ? (
            <GlassCard className="p-10 text-center text-sm text-muted-foreground">Belum ada quote</GlassCard>
          ) : (
            <div className="space-y-2">
              {history.map((q) => (
                <div
                  key={q.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => openDetail(q)}
                  onKeyDown={(e) => e.key === 'Enter' && openDetail(q)}
                  data-testid={`quote-history-${q.id}`}
                  className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:border-emerald-500/40 cursor-pointer transition"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div>
                      <span className="font-medium text-sm">{q.request?.product_name || '—'}</span>
                      <span className="text-xs text-muted-foreground ml-2">{q.request?.quantity} pcs · {q.request?.client_name || 'no client'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">{fmtIDR(q.result?.estimated_unit_price)}</span>
                      {q.status === 'accepted' ? (
                        <Badge className="bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 border-emerald-400 dark:border-emerald-500/30" variant="outline">accepted</Badge>
                      ) : (
                        <Badge variant="outline">{q.status || 'draft'}</Badge>
                      )}
                    </div>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {q.created_at ? new Date(q.created_at).toLocaleString('id-ID') : '—'} · Total {fmtIDR(q.result?.estimated_total)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="w-5 h-5 text-emerald-500" /> Detail Quote
            </DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="text-xs text-muted-foreground">
                {detail.created_at ? new Date(detail.created_at).toLocaleString('id-ID') : '—'} · {detail.created_by_name || '—'}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-muted-foreground">Product:</span> <span className="font-medium">{detail.request?.product_name}</span></div>
                <div><span className="text-muted-foreground">Category:</span> {detail.request?.category}</div>
                <div><span className="text-muted-foreground">Quantity:</span> {detail.request?.quantity}</div>
                <div><span className="text-muted-foreground">Client:</span> {detail.request?.client_name || '—'}</div>
              </div>
              {renderResult(detail.result)}
              <div className="flex items-center gap-2 pt-2 border-t border-[var(--glass-border)]">
                {detail.status !== 'accepted' && (
                  <Button size="sm" onClick={() => acceptQuote(detail.id)} data-testid={`quote-accept-${detail.id}`}><CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Accept Quote</Button>
                )}
                <Button variant="destructive" size="sm" onClick={() => deleteQuote(detail.id)}><Trash2 className="w-3.5 h-3.5 mr-1" /> Hapus</Button>
                <Button variant="outline" size="sm" onClick={() => setDetailOpen(false)}>Tutup</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="p-2 rounded bg-[var(--glass)] border border-[var(--glass-border)]">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold text-foreground">{value}</div>
    </div>
  );
}

