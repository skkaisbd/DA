import { useState, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ImageIcon, RefreshCw, Download, Sparkles, History, Clock, Maximize2, Square, LayoutTemplate } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const ASPECT_RATIOS = [
  { value: 'square',    label: 'Kotak (1:1)',        desc: '1024×1024 — IG Feed, Marketplace',   icon: Square },
  { value: 'portrait',  label: 'Potret (9:16)',      desc: '1024×1792 — IG Story, TikTok',       icon: Maximize2 },
  { value: 'landscape', label: 'Landscape (16:9)',   desc: '1792×1024 — Banner, Cover',           icon: LayoutTemplate },
];

const PRESET_STYLES = [
  'foto produk profesional, background putih bersih',
  'foto produk lifestyle, model cantik Indonesia',
  'flat lay estetik, props bunga dan dekorasi',
  'outdoor shoot natural lighting, bokeh background',
  'studio lighting profesional, shadow dramatis',
];

function GeneratorTab() {
  const { toast } = useToast();
  const [prompt, setPrompt] = useState('');
  const [aspectRatio, setAspectRatio] = useState('square');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      toast({ title: 'Prompt wajib diisi', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = await apiFetch('/marketing/ai-content/generate-image', {
        method: 'POST',
        body: { prompt, aspect_ratio: aspectRatio, mode: 'generate' },
      });
      setResult(data.data);
      toast({ title: 'Gambar berhasil digenerate! 🎨' });
    } catch (err) {
      toast({ title: 'Gagal generate gambar', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = useCallback(() => {
    if (!result?.image_base64) return;
    const link = document.createElement('a');
    link.href = `data:image/png;base64,${result.image_base64}`;
    link.download = `product-image-${Date.now()}.png`;
    link.click();
  }, [result]);

  const applyPreset = (preset) => {
    setPrompt(prev => prev ? `${prev}, ${preset}` : preset);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Controls */}
      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ImageIcon className="h-4 w-4 text-blue-500" />
            Pengaturan Gambar
          </CardTitle>
          <CardDescription className="text-xs">Deskripsikan gambar produk yang ingin Anda buat</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs font-medium">Prompt Gambar *</Label>
            <Textarea
              className="mt-1 text-sm"
              rows={5}
              placeholder="Contoh: Blouse batik modern berwarna navy, model wanita Indonesia cantik, foto profesional, background studio putih bersih..."
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              data-testid="image-prompt-input"
            />
          </div>

          <div>
            <Label className="text-xs font-medium mb-2 block">Preset Style Cepat</Label>
            <div className="flex flex-wrap gap-1.5">
              {PRESET_STYLES.map((p, i) => (
                <button
                  key={i}
                  onClick={() => applyPreset(p)}
                  className="text-[11px] px-2 py-1 rounded-full bg-muted hover:bg-muted/80 border border-border text-muted-foreground hover:text-foreground transition-colors"
                >
                  {p.substring(0, 30)}...
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs font-medium">Rasio Gambar</Label>
            <div className="grid grid-cols-3 gap-2 mt-2">
              {ASPECT_RATIOS.map(r => (
                <button
                  key={r.value}
                  onClick={() => setAspectRatio(r.value)}
                  className={`p-2 rounded-lg border text-center transition-all ${
                    aspectRatio === r.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:border-primary/50 text-muted-foreground'
                  }`}
                >
                  <r.icon className="h-4 w-4 mx-auto mb-1" />
                  <p className="text-[11px] font-medium">{r.label}</p>
                  <p className="text-[10px] text-muted-foreground leading-tight">{r.desc.split('—')[0].trim()}</p>
                </button>
              ))}
            </div>
          </div>

          <Button
            className="w-full bg-gradient-to-r from-blue-600 to-purple-600 text-foreground hover:opacity-90"
            onClick={handleGenerate}
            disabled={loading}
            data-testid="btn-generate-image"
          >
            {loading ? (
              <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />AI sedang menggambar...</>
            ) : (
              <><Sparkles className="h-4 w-4 mr-2" />Generate Gambar AI</>
            )}
          </Button>

          <p className="text-[11px] text-muted-foreground text-center">
            Powered by GPT Image 1 · Estimasi 15–30 detik
          </p>
        </CardContent>
      </Card>

      {/* Preview */}
      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ImageIcon className="h-4 w-4 text-green-500" />
            Hasil Gambar
          </CardTitle>
          <CardDescription className="text-xs">Preview dan unduh hasil generasi</CardDescription>
        </CardHeader>
        <CardContent>
          {!result && !loading && (
            <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground border-2 border-dashed border-border rounded-lg">
              <ImageIcon className="h-12 w-12 mb-3 opacity-20" />
              <p className="text-sm">Gambar akan muncul di sini</p>
            </div>
          )}
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 border-2 border-dashed border-primary/30 rounded-lg">
              <div className="relative">
                <div className="h-16 w-16 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
                <ImageIcon className="h-6 w-6 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>
              <p className="text-sm text-muted-foreground mt-4">AI sedang membuat gambar...</p>
              <p className="text-xs text-muted-foreground mt-1">Mohon tunggu ±20 detik</p>
            </div>
          )}
          {result && (
            <div className="space-y-3">
              <div className="rounded-lg overflow-hidden border border-border">
                <img
                  src={`data:image/png;base64,${result.image_base64}`}
                  alt="Generated product"
                  className="w-full object-contain max-h-80"
                  data-testid="generated-image-preview"
                />
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{result.size} · {result.aspect_ratio}</span>
                <span>~{result.image_size_kb?.toFixed(1)} KB</span>
              </div>
              <Button className="w-full" variant="outline" onClick={handleDownload}>
                <Download className="h-4 w-4 mr-2" />Unduh Gambar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HistoryTab() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useState(() => {
    apiFetch('/marketing/ai-content/history?limit=20&content_type=image')
      .then(d => setHistory(d.data || []))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {loading && <div className="text-center py-8 text-sm text-muted-foreground">Memuat riwayat...</div>}
      {!loading && !history.length && (
        <div className="text-center py-12 text-muted-foreground">
          <ImageIcon className="h-10 w-10 mx-auto mb-2 opacity-20" />
          <p className="text-sm">Belum ada riwayat generate gambar</p>
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {history.filter(h => h.type === 'image').map((item, i) => (
          <Card key={i} className="border border-border overflow-hidden">
            <div className="bg-muted h-24 flex items-center justify-center">
              <ImageIcon className="h-8 w-8 text-muted-foreground opacity-50" />
            </div>
            <CardContent className="p-2">
              <p className="text-xs line-clamp-2 text-muted-foreground">{item.prompt}</p>
              <div className="flex items-center gap-1 mt-1">
                <Badge variant="outline" className="text-[10px]">{item.aspect_ratio}</Badge>
                <span className="text-[10px] text-muted-foreground ml-auto flex items-center gap-0.5">
                  <Clock className="h-2.5 w-2.5" />
                  {item.generated_at ? new Date(item.generated_at).toLocaleDateString('id-ID') : '-'}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function AIImageGeneratorModule() {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <ImageIcon className="h-4 w-4 text-foreground" />
            </div>
            AI Image Generator
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">Generate foto produk profesional dengan GPT Image 1</p>
        </div>
        <Badge className="bg-blue-100 text-blue-700 border-blue-200">GPT Image 1</Badge>
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
