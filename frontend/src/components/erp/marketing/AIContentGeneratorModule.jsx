import { useState, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Sparkles, Copy, History, Instagram, ShoppingCart, Film, Clock, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
// F14b — produk untuk caption WAJIB dari Master Produk (lihat komentar di
// komponennya): caption yang tayang ke pembeli memuat bahan & harga.
import MasterProductSelect from '../pickers/MasterProductSelect';

const PLATFORM_CONFIG = {
  instagram: { label: 'Instagram', icon: Instagram, color: 'from-pink-500 to-purple-600', badge: 'IG', limit: 150 },
  tiktok:    { label: 'TikTok',    icon: Film,      color: 'from-muted to-slate-600', badge: 'TikTok', limit: 100 },
  shopee:    { label: 'Shopee',    icon: ShoppingCart, color: 'from-orange-500 to-red-500', badge: 'Shopee', limit: 200 },
  tokopedia: { label: 'Tokopedia', icon: ShoppingCart, color: 'from-green-500 to-teal-600', badge: 'Tokped', limit: 180 },
};

function CopyButton({ text, className = '' }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <Button size="sm" variant="ghost" onClick={handleCopy} className={className}>
      {copied ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
      <span className="ml-1 text-xs">{copied ? 'Tersalin' : 'Copy'}</span>
    </Button>
  );
}

function GeneratorTab() {
  const { toast } = useToast();
  // F14b — produk yang dibuatkan caption adalah produk DA yang SUDAH ADA di
  // master. Sebelum ini nama/kategori/material/warna diketik bebas, dengan tiga
  // akibat yang tidak terlihat: (1) caption tersimpan atas nama produk yang
  // tidak ada di katalog mana pun ⇒ performa konten tidak bisa dikaitkan ke
  // produk; (2) AI menerima bahan/warna karangan lalu MENULISKANNYA ke caption
  // yang tayang ke pembeli — klaim produk yang salah; (3) satu produk punya
  // banyak ejaan ⇒ riwayat caption pecah.
  const [form, setForm] = useState({
    model_id: '', master: null,
    colors: '', price: '', platform: 'instagram', custom_notes: '',
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleChange = useCallback((field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  }, []);

  const handleGenerate = async () => {
    if (!form.model_id || !form.master) {
      toast({
        title: 'Pilih produk dari Master Produk',
        description: 'Caption ditulis untuk produk yang benar-benar dijual — '
          + 'supaya performanya bisa dikaitkan ke produk itu, dan supaya AI '
          + 'tidak menuliskan bahan/harga karangan ke teks yang dibaca pembeli.',
        variant: 'destructive',
      });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const m = form.master;
      const payload = {
        // Identitas produk DIAMBIL DARI MASTER, bukan dari ketikan.
        product_name: m.name,
        model_id: m.model_id,
        platform: form.platform,
        ...(m.category_name && { category: m.category_name }),
        ...(m.material && { material: m.material }),
        ...(form.colors && { colors: form.colors.split(',').map(c => c.trim()).filter(Boolean) }),
        ...(form.price && { price: parseFloat(form.price) }),
        ...(form.custom_notes && { custom_notes: form.custom_notes }),
      };
      const data = await apiFetch('/marketing/ai-content/generate-caption', { method: 'POST', body: payload });
      setResult(data.data);
      toast({ title: 'Caption berhasil digenerate! ✨' });
    } catch (err) {
      toast({ title: 'Gagal generate caption', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const platform = form.platform;
  const cfg = PLATFORM_CONFIG[platform] || PLATFORM_CONFIG.instagram;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Form */}
      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-500" />
            Input Produk
          </CardTitle>
          <CardDescription className="text-xs">Isi informasi produk untuk caption yang relevan</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label className="text-xs font-medium">Platform *</Label>
            <Select value={form.platform} onValueChange={v => handleChange('platform', v)}>
              <SelectTrigger className="mt-1 h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PLATFORM_CONFIG).map(([k, v]) => (
                  <SelectItem key={k} value={k}>
                    <span className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] px-1 py-0">{v.badge}</Badge>
                      {v.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            {/* F14b — satu pemilih menggantikan tiga kotak ketik (nama,
                kategori, material). Kategori & material mengikuti master. */}
            <MasterProductSelect
              value={form.model_id}
              testId="caption-product-select"
              label="Produk (dari Master Produk)"
              onChange={(m) => setForm(prev => ({
                ...prev,
                model_id: m?.model_id || '',
                master: m || null,
                // Harga berangkat dari harga RESMI master; boleh ditimpa untuk
                // caption promo, tetapi titik awalnya bukan angka karangan.
                price: prev.price !== '' && prev.price != null
                  ? prev.price : (m?.retail_price_master ?? ''),
              }))}
              helpText="Caption yang tayang ke pembeli memuat bahan & harga — keduanya harus berasal dari master, bukan ketikan."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-medium">Kategori (dari master)</Label>
              <div className="mt-1 h-9 flex items-center rounded-md border border-border bg-muted/50 px-3 text-sm"
                   data-testid="caption-category-readonly">
                {form.master
                  ? (form.master.category_name
                    || <span className="text-muted-foreground text-xs">Belum dicatat di master</span>)
                  : <span className="text-muted-foreground text-xs">Pilih produk dulu</span>}
              </div>
            </div>
            <div>
              <Label className="text-xs font-medium">Material (dari master)</Label>
              <div className="mt-1 h-9 flex items-center rounded-md border border-border bg-muted/50 px-3 text-sm"
                   data-testid="caption-material-readonly">
                {form.master
                  ? (form.master.material
                    || <span className="text-muted-foreground text-xs">Belum dicatat di master</span>)
                  : <span className="text-muted-foreground text-xs">Pilih produk dulu</span>}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-medium">Warna (dari varian master)</Label>
              <Select
                value={form.colors || 'ALL'}
                onValueChange={v => handleChange('colors', v === 'ALL' ? '' : v)}
                disabled={!form.master}
              >
                <SelectTrigger className="mt-1 h-9 text-sm" data-testid="caption-color-select">
                  <SelectValue placeholder={form.master ? 'Semua warna' : 'Pilih produk dulu'} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">Semua warna varian</SelectItem>
                  {[...new Set((form.master?.variants || [])
                    .map(v => v.color).filter(Boolean))].map(c => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-medium">Harga (Rp)</Label>
              <Input className="mt-1 h-9 text-sm" type="number" placeholder="85000" value={form.price} onChange={e => handleChange('price', e.target.value)} data-testid="caption-price" />
              {form.master && Number(form.master.retail_price_master || 0) > 0
                && Number(form.price || 0) > 0
                && Number(form.price) !== Number(form.master.retail_price_master) && (
                <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-400">
                  Beda dari harga resmi master (Rp {Number(form.master.retail_price_master).toLocaleString('id-ID')}).
                </p>
              )}
            </div>
          </div>

          <div>
            <Label className="text-xs font-medium">Catatan Tambahan (opsional)</Label>
            <Textarea
              className="mt-1 text-sm"
              rows={2}
              placeholder="Promosi flashsale, keunggulan khusus, target audience..."
              value={form.custom_notes}
              onChange={e => handleChange('custom_notes', e.target.value)}
            />
          </div>

          <Button
            className={`w-full bg-gradient-to-r ${cfg.color} text-foreground hover:opacity-90`}
            onClick={handleGenerate}
            disabled={loading}
            data-testid="btn-generate-caption"
          >
            {loading ? (
              <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Sedang generate...</>
            ) : (
              <><Sparkles className="h-4 w-4 mr-2" />Generate Caption AI</>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Result */}
      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Badge variant="outline" className={`text-[10px]`}>{cfg.badge}</Badge>
            Hasil Caption
          </CardTitle>
          <CardDescription className="text-xs">Caption dan hashtag siap copy-paste</CardDescription>
        </CardHeader>
        <CardContent>
          {!result && !loading && (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <Sparkles className="h-10 w-10 mb-3 opacity-30" />
              <p className="text-sm">Isi form di sebelah kiri lalu<br />klik &quot;Generate Caption AI&quot;</p>
            </div>
          )}
          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <RefreshCw className="h-8 w-8 animate-spin text-purple-500 mb-3" />
              <p className="text-sm text-muted-foreground">AI sedang menulis caption terbaik...</p>
            </div>
          )}
          {result && (
            <div className="space-y-4">
              <div className="bg-muted/50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Caption</Label>
                  <CopyButton text={result.caption} />
                </div>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.caption}</p>
                <p className="text-[11px] text-muted-foreground mt-2">{result.caption?.length || 0} karakter (maks {cfg.limit})</p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Hashtag</Label>
                  <CopyButton text={result.hashtags} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {result.hashtags?.split(' ').filter(h => h.startsWith('#')).map((h, i) => (
                    <Badge key={i} variant="secondary" className="text-xs font-normal">{h}</Badge>
                  ))}
                </div>
              </div>
              <CopyButton
                text={`${result.caption}\n\n${result.hashtags}`}
                className="w-full justify-center border border-dashed border-border"
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HistoryTab() {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const type = filter === 'all' ? '' : filter;
      const data = await apiFetch(`/marketing/ai-content/history?limit=30${type ? `&content_type=${type}` : ''}`);
      setHistory(data.data || []);
    } catch (err) {
      setHistory([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useState(() => { loadHistory(); }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <Select value={filter} onValueChange={v => { setFilter(v); loadHistory(); }}>
          <SelectTrigger className="w-40 h-8 text-sm">
            <SelectValue placeholder="Filter type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua</SelectItem>
            <SelectItem value="caption">Caption</SelectItem>
            <SelectItem value="image">Image</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={loadHistory}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />Refresh
        </Button>
      </div>

      {loading && <div className="text-center py-8 text-muted-foreground text-sm">Memuat riwayat...</div>}
      {!loading && !history?.length && <div className="text-center py-8 text-muted-foreground text-sm">Belum ada riwayat generate</div>}
      {!loading && history?.length > 0 && (
        <div className="space-y-3">
          {history.map((item, i) => (
            <Card key={i} className="border border-border">
              <CardContent className="p-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="text-[10px]">{item.type === 'caption' ? 'Caption' : 'Image'}</Badge>
                      {item.platform && <Badge variant="secondary" className="text-[10px]">{PLATFORM_CONFIG[item.platform]?.badge || item.platform}</Badge>}
                    </div>
                    <p className="text-sm font-medium">{item.product_name || item.prompt || 'N/A'}</p>
                    {item.caption && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.caption}</p>}
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {item.generated_at ? new Date(item.generated_at).toLocaleDateString('id-ID') : '-'}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AIContentGeneratorModule() {
  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <Sparkles className="h-4 w-4 text-foreground" />
            </div>
            AI Content Generator
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">Generate caption & hashtag untuk IG, TikTok, Shopee, Tokopedia</p>
        </div>
        <Badge className="bg-purple-100 text-purple-700 border-purple-200">Powered by AI</Badge>
      </div>

      <Tabs defaultValue="generator">
        <TabsList className="h-9">
          <TabsTrigger value="generator" className="text-xs"><Sparkles className="h-3.5 w-3.5 mr-1.5" />Generator</TabsTrigger>
          <TabsTrigger value="history" className="text-xs"><History className="h-3.5 w-3.5 mr-1.5" />Riwayat</TabsTrigger>
        </TabsList>
        <TabsContent value="generator" className="mt-4">
          <GeneratorTab />
        </TabsContent>
        <TabsContent value="history" className="mt-4">
          <HistoryTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
