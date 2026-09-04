/**
 * pdf/PdfTemplateStudio.jsx — SATU layar untuk semua setelan dokumen PDF (SESI #19).
 *
 * MENGAPA LAYAR INI ADA (kata pemilik, `memory/PERMINTAAN_OWNER_PDF_EDITOR.md`):
 *   · "untuk pdf konfigurasi saat ini editor masih sangat buruk"
 *   · "cek ada dua halaman berbeda ui ux-nya jelas. saya ingin perbaiki ui ux-nya"
 *   · "header surat sangat buruk sekali"
 *
 * Yang digantikan: tab "PDF: Kolom Tabel" (`PDFConfigModule`, koleksi
 * `pdf_export_configs`) dan tab "PDF: Surat & TTD" (`PdfDocSettingsModule`, koleksi
 * `pdf_document_settings`). Dua layar itu mengatur SATU dokumen dari dua tempat
 * dengan tata letak, istilah, dan bahkan bahasa yang berbeda.
 *
 * Bentuk layar ini: EDITOR di kiri, PRATINJAU PDF SUNGGUHAN di kanan (permintaan
 * pemilik: "ada preview/viewer di samping editor supaya user langsung mengecek
 * hasilnya tanpa mengunduh"). Pratinjau memakai data CONTOH dan dibuat backend
 * dengan generator yang sama seperti dokumen sungguhan — bukan tiruan HTML yang
 * bisa berbeda dari hasil cetak.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText, Save, RotateCcw, RefreshCw, Plus, Trash2, ArrowUp, ArrowDown,
  Image as ImageIcon, Eye, ExternalLink, Loader2, Info, Layers, PenLine,
  Columns3, Sparkles,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { PageHeader } from '../moduleAtoms';
import pdfTplApi from './pdfTemplateApi';

const GLOBAL_KEY = '__global__';
const NAME_SOURCE_LABELS = {
  custom: 'Nama diketik di sini',
  field: 'Nama dari data dokumen',
  blank: 'Dikosongkan (ditulis tangan)',
};
const LAYOUT_LABELS = {
  'logo-left': 'Logo di kiri, identitas di kanan',
  'logo-center': 'Logo di tengah atas',
  'logo-right': 'Logo di kanan, identitas di kiri',
  'text-only': 'Tanpa logo (hanya teks)',
};
const ALIGN_LABELS = { left: 'Kiri', center: 'Tengah', right: 'Kanan' };

/** Label kecil di atas kontrol — dipakai konsisten supaya editor mudah dipindai. */
const Field = ({ label, hint, children, className = '' }) => (
  <div className={className}>
    <Label className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
      {label}
    </Label>
    <div className="mt-1">{children}</div>
    {hint && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
  </div>
);

const Toggle = ({ label, hint, checked, onCheckedChange, testId, disabled }) => (
  <div className="flex items-start justify-between gap-3 py-2">
    <div className="min-w-0">
      <p className="text-sm text-foreground">{label}</p>
      {hint && <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>}
    </div>
    <Switch
      checked={!!checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      data-testid={testId}
      aria-label={label}
    />
  </div>
);

const SectionCard = ({ icon: Icon, title, desc, children, testId }) => (
  <div className="rounded-[var(--radius-md)] border border-[var(--glass-border)] bg-card p-4"
       data-testid={testId}>
    <div className="flex items-center gap-2 mb-3">
      {Icon && <Icon className="w-4 h-4 text-[hsl(var(--primary))]" />}
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
    </div>
    {desc && <p className="text-[11px] text-muted-foreground -mt-2 mb-3">{desc}</p>}
    {children}
  </div>
);

export default function PdfTemplateStudio({ token }) {
  const [catalog, setCatalog] = useState(null);
  const [docKey, setDocKey] = useState(GLOBAL_KEY);
  const [tpl, setTpl] = useState(null);          // template yang sedang diedit
  const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState({});
  const [previewDoc, setPreviewDoc] = useState('delivery-note');  // contoh utk mode global
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewMode, setPreviewMode] = useState('gambar');   // 'gambar' | 'pdf'
  const [previewing, setPreviewing] = useState(false);
  const [previewErr, setPreviewErr] = useState('');
  const urlRef = useRef('');

  const isGlobal = docKey === GLOBAL_KEY;
  const docs = catalog?.docs || [];
  const activeDoc = useMemo(() => docs.find(d => d.doc_key === docKey) || null, [docs, docKey]);
  const previewKey = isGlobal ? previewDoc : docKey;

  const groups = useMemo(() => {
    const g = {};
    docs.forEach(d => { (g[d.group] = g[d.group] || []).push(d); });
    return g;
  }, [docs]);

  // ── muat katalog sekali ─────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    pdfTplApi.catalog(token)
      .then(d => { if (alive) setCatalog(d); })
      .catch(e => toast.error(e.message || 'Gagal memuat katalog dokumen'));
    return () => { alive = false; };
  }, [token]);

  // ── muat template saat jenis dokumen berganti ──────────────────────────────
  const load = useCallback(async () => {
    setLoaded(false);
    try {
      if (docKey === GLOBAL_KEY) {
        const d = await pdfTplApi.getGlobal(token);
        setProfile(d.company_profile || {});
        setTpl({
          header: d.header, signatures: d.signatures, footer: d.footer, table: d.table,
        });
      } else {
        const d = await pdfTplApi.getDoc(token, docKey);
        setTpl({
          header: d.header, signatures: d.signatures, footer: d.footer, table: d.table,
          columns: d.columns || [],
          override_header: !!d.override_header,
          override_signatures: !!d.override_signatures,
          override_footer: !!d.override_footer,
        });
      }
      setDirty(false);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat template');
    } finally {
      setLoaded(true);
    }
  }, [docKey, token]);

  useEffect(() => { load(); }, [load]);

  // ── pratinjau: PDF asli dari backend, di-debounce ──────────────────────────
  // Mode bawaan GAMBAR (PNG hasil render PDF yang sama): penampil PDF bawaan
  // browser tidak selalu tersedia dan iframe-nya tampil kosong tanpa pesan —
  // pemilik akan menyimpulkan pratinjaunya rusak. Mode PDF tetap tersedia.
  useEffect(() => {
    if (!tpl || !previewKey) return;
    setPreviewing(true);
    const t = setTimeout(async () => {
      try {
        const url = await pdfTplApi.previewUrl(
          token, previewKey, tpl, previewMode === 'gambar' ? 'png' : 'pdf');
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setPreviewUrl(url);
        setPreviewErr('');
      } catch (e) {
        setPreviewErr(e.message || 'Pratinjau gagal dibuat');
      } finally {
        setPreviewing(false);
      }
    }, 800);   // cukup untuk berhenti mengetik, tanpa terasa lambat
    return () => clearTimeout(t);
  }, [tpl, previewKey, token, previewMode]);

  const openPdfTab = async () => {
    try {
      const url = await pdfTplApi.previewUrl(token, previewKey, tpl, 'pdf');
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      toast.error(e.message || 'Gagal membuka PDF');
    }
  };

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);

  // ── penyunting ─────────────────────────────────────────────────────────────
  const patch = (section, key, value) => {
    setTpl(p => ({ ...p, [section]: { ...(p[section] || {}), [key]: value } }));
    setDirty(true);
  };
  const patchRoot = (key, value) => { setTpl(p => ({ ...p, [key]: value })); setDirty(true); };

  const setColumns = (cols) => { setTpl(p => ({ ...p, columns: cols })); setDirty(true); };
  const moveColumn = (i, dir) => {
    const cols = [...(tpl.columns || [])];
    const j = i + dir;
    if (j < 0 || j >= cols.length) return;
    [cols[i], cols[j]] = [cols[j], cols[i]];
    setColumns(cols);
  };
  const patchColumn = (i, key, value) => {
    const cols = [...(tpl.columns || [])];
    cols[i] = { ...cols[i], [key]: value };
    setColumns(cols);
  };
  const addColumn = () => {
    const cols = [...(tpl.columns || [])];
    const n = cols.filter(c => c.custom).length + 1;
    if (n > (catalog?.max_extra_columns || 6)) {
      toast.error(`Maksimal ${catalog?.max_extra_columns || 6} kolom tambahan.`);
      return;
    }
    cols.push({
      key: `tambahan_${n}`, label: `Kolom Tambahan ${n}`, visible: true,
      width: 0, align: 'left', custom: true, required: false,
    });
    setColumns(cols);
  };
  const removeColumn = (i) => setColumns((tpl.columns || []).filter((_, idx) => idx !== i));

  const sigBlocks = tpl?.signatures?.blocks || [];
  const setBlocks = (blocks) => patch('signatures', 'blocks', blocks);
  const patchBlock = (i, key, value) => {
    const b = [...sigBlocks];
    b[i] = { ...b[i], [key]: value };
    setBlocks(b);
  };
  const moveBlock = (i, dir) => {
    const b = [...sigBlocks];
    const j = i + dir;
    if (j < 0 || j >= b.length) return;
    [b[i], b[j]] = [b[j], b[i]];
    setBlocks(b);
  };
  const addBlock = () => {
    if (sigBlocks.length >= (catalog?.max_signature_blocks || 6)) {
      toast.error(`Maksimal ${catalog?.max_signature_blocks || 6} blok tanda tangan.`);
      return;
    }
    setBlocks([...sigBlocks, {
      subject: 'Penerima', name_source: 'blank', custom_name: '', field_key: '', note: '',
    }]);
  };
  const removeBlock = (i) => setBlocks(sigBlocks.filter((_, idx) => idx !== i));

  // ── logo (base64 di MongoDB, tanpa layanan penyimpanan luar) ───────────────
  const onLogoPick = (file) => {
    if (!file) return;
    const maxKb = catalog?.max_logo_kb || 700;
    if (file.size > maxKb * 1024) {
      toast.error(`Ukuran logo ${Math.round(file.size / 1024)} KB melebihi batas ${maxKb} KB.`);
      return;
    }
    const rd = new FileReader();
    rd.onload = () => {
      patch('header', 'logo_data', String(rd.result || ''));
      if ((tpl?.header?.layout || 'logo-left') === 'text-only') {
        patch('header', 'layout', 'logo-left');
      }
      toast.success('Logo dimuat — lihat pratinjau di sebelah kanan.');
    };
    rd.onerror = () => toast.error('Logo gagal dibaca.');
    rd.readAsDataURL(file);
  };

  const save = async () => {
    setSaving(true);
    try {
      if (isGlobal) {
        const d = await pdfTplApi.saveGlobal(token, tpl);
        setTpl({ header: d.header, signatures: d.signatures, footer: d.footer, table: d.table });
      } else {
        const d = await pdfTplApi.saveDoc(token, docKey, tpl);
        setTpl({
          header: d.header, signatures: d.signatures, footer: d.footer, table: d.table,
          columns: d.columns || [],
          override_header: !!d.override_header,
          override_signatures: !!d.override_signatures,
          override_footer: !!d.override_footer,
        });
      }
      setDirty(false);
      toast.success('Template tersimpan — dokumen baru langsung memakai setelan ini.');
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan template');
    } finally {
      setSaving(false);
    }
  };

  const resetDoc = async () => {
    if (isGlobal) return;
    try {
      await pdfTplApi.resetDoc(token, docKey);
      await load();
      toast.success('Override dihapus — dokumen ini kembali mengikuti template global.');
    } catch (e) {
      toast.error(e.message || 'Gagal mengembalikan ke global');
    }
  };

  const hdr = tpl?.header || {};
  const sig = tpl?.signatures || {};
  const ftr = tpl?.footer || {};
  const tbl = tpl?.table || {};
  const columns = tpl?.columns || [];
  const availableFields = activeDoc?.available_fields || [];

  return (
    <div className="space-y-5" data-testid="pdf-template-studio">
      <PageHeader
        icon={FileText}
        eyebrow="Administrasi Sistem · Dokumen"
        title="PDF & Kop Surat"
        subtitle="Satu tempat untuk kop surat (logo & identitas PT), kolom tabel, blok tanda tangan, dan footer semua dokumen. Pratinjau di kanan memakai generator PDF yang sama dengan dokumen sungguhan."
        testId="pdf-studio-header"
        actions={
          <>
            <Button
              variant="ghost" onClick={load}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="pdf-studio-reload"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
            </Button>
            {!isGlobal && (
              <Button
                variant="ghost" onClick={resetDoc}
                className="h-9 border border-[var(--glass-border)]"
                data-testid="pdf-studio-reset-doc"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />Ikuti Global
              </Button>
            )}
            <Button onClick={save} disabled={saving || !dirty} className="h-9"
                    data-testid="pdf-studio-save">
              {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      : <Save className="w-3.5 h-3.5 mr-1.5" />}
              Simpan
            </Button>
          </>
        }
      />

      {/* Pemilih lingkup: satu template global + override per jenis dokumen */}
      <GlassCard className="p-4" data-testid="pdf-studio-scope">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-end">
          <Field label="Yang sedang diatur" className="lg:col-span-5">
            <Select value={docKey} onValueChange={setDocKey}>
              <SelectTrigger className="h-9" data-testid="pdf-studio-doc-select">
                <SelectValue placeholder="Pilih jenis dokumen" />
              </SelectTrigger>
              <SelectContent className="max-h-[420px]">
                <SelectItem value={GLOBAL_KEY} data-testid="pdf-studio-doc-global">
                  Template Global (berlaku untuk semua dokumen)
                </SelectItem>
                {Object.entries(groups).map(([g, items]) => (
                  <SelectGroup key={g}>
                    <SelectLabel>{g}</SelectLabel>
                    {items.map(d => (
                      <SelectItem key={d.doc_key} value={d.doc_key}
                                  data-testid={`pdf-studio-doc-${d.doc_key}`}>
                        {d.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {isGlobal ? (
            <Field label="Dokumen contoh untuk pratinjau" className="lg:col-span-4">
              <Select value={previewDoc} onValueChange={setPreviewDoc}>
                <SelectTrigger className="h-9" data-testid="pdf-studio-preview-doc">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[420px]">
                  {docs.map(d => (
                    <SelectItem key={d.doc_key} value={d.doc_key}>{d.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          ) : (
            <div className="lg:col-span-4 flex flex-wrap gap-2" data-testid="pdf-studio-override-badges">
              <Badge variant="outline" className="text-[11px]">
                Kop: {tpl?.override_header ? 'khusus dokumen ini' : 'ikut global'}
              </Badge>
              <Badge variant="outline" className="text-[11px]">
                Tanda tangan: {tpl?.override_signatures ? 'khusus' : 'ikut global'}
              </Badge>
              <Badge variant="outline" className="text-[11px]">
                Footer: {tpl?.override_footer ? 'khusus' : 'ikut global'}
              </Badge>
              <Badge variant="outline" className="text-[11px]"
                     data-testid="pdf-studio-columns-badge">
                Kolom: {activeDoc?.columns_enforced === false
                  ? 'belum bisa diatur' : 'bisa diatur'}
              </Badge>
            </div>
          )}

          <div className="lg:col-span-3 flex lg:justify-end">
            {dirty ? (
              <Badge className="bg-[hsl(var(--warning)/0.15)] text-[hsl(var(--warning))] border border-[hsl(var(--warning)/0.35)]"
                     data-testid="pdf-studio-dirty">
                Ada perubahan belum disimpan
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[11px]" data-testid="pdf-studio-clean">
                Tersimpan
              </Badge>
            )}
          </div>
        </div>
        {!isGlobal && (
          <p className="text-[11px] text-muted-foreground mt-3 flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 mt-px shrink-0" />
            Kop, tanda tangan, dan footer dokumen ini mengikuti Template Global sampai
            Anda menyalakan override di tab masing-masing. Kolom tabel selalu milik
            jenis dokumen ini.
          </p>
        )}
      </GlassCard>

      {/* EDITOR (kiri) + PRATINJAU (kanan) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        <div className="xl:col-span-7 space-y-4" data-testid="pdf-studio-editor">
          {!loaded || !tpl ? (
            <GlassCard className="p-4 space-y-3">
              <Skeleton className="h-8 w-1/3" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </GlassCard>
          ) : (
            <Tabs defaultValue="kop">
              <TabsList data-testid="pdf-studio-tabs">
                <TabsTrigger value="kop" data-testid="pdf-studio-tab-kop">
                  <Layers className="w-3.5 h-3.5 mr-1.5" />Kop Surat
                </TabsTrigger>
                <TabsTrigger value="kolom" data-testid="pdf-studio-tab-kolom">
                  <Columns3 className="w-3.5 h-3.5 mr-1.5" />Kolom Tabel
                </TabsTrigger>
                <TabsTrigger value="ttd" data-testid="pdf-studio-tab-ttd">
                  <PenLine className="w-3.5 h-3.5 mr-1.5" />Tanda Tangan
                </TabsTrigger>
                <TabsTrigger value="lain" data-testid="pdf-studio-tab-lain">
                  <Sparkles className="w-3.5 h-3.5 mr-1.5" />Footer & Gaya Tabel
                </TabsTrigger>
              </TabsList>

              {/* ── KOP SURAT ─────────────────────────────────────────────── */}
              <TabsContent value="kop" className="space-y-4 mt-4">
                {!isGlobal && (
                  <SectionCard icon={Info} title="Sumber setelan kop" testId="pdf-kop-override">
                    <Toggle
                      label="Pakai kop khusus untuk dokumen ini"
                      hint="Mati = mengikuti Template Global (ubah sekali, berlaku untuk semua surat)."
                      checked={!!tpl.override_header}
                      onCheckedChange={v => patchRoot('override_header', v)}
                      testId="pdf-kop-override-switch"
                    />
                  </SectionCard>
                )}

                <SectionCard icon={ImageIcon} title="Logo perusahaan"
                             desc="PNG/JPG/WEBP maksimal 700 KB. Logo disimpan di database sistem."
                             testId="pdf-kop-logo">
                  <div className="flex items-start gap-4">
                    <div className="h-20 w-32 rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-muted/40 flex items-center justify-center overflow-hidden">
                      {hdr.logo_data ? (
                        <img src={hdr.logo_data} alt="Logo perusahaan"
                             className="max-h-full max-w-full object-contain"
                             data-testid="pdf-kop-logo-preview" />
                      ) : (
                        <span className="text-[11px] text-muted-foreground px-2 text-center">
                          Belum ada logo
                        </span>
                      )}
                    </div>
                    <div className="flex-1 space-y-2">
                      <div className="flex flex-wrap gap-2">
                        <label className="inline-flex">
                          <input
                            type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                            onChange={e => onLogoPick(e.target.files?.[0])}
                            data-testid="pdf-kop-logo-input"
                          />
                          <span className="inline-flex items-center h-9 px-3 rounded-[var(--radius-sm)] border border-[var(--glass-border)] text-sm cursor-pointer hover:bg-muted/50 transition-colors">
                            <ImageIcon className="w-3.5 h-3.5 mr-1.5" />Unggah Logo
                          </span>
                        </label>
                        {hdr.logo_data && (
                          <Button variant="ghost" onClick={() => patch('header', 'logo_data', '')}
                                  className="h-9 border border-[var(--glass-border)]"
                                  data-testid="pdf-kop-logo-remove">
                            <Trash2 className="w-3.5 h-3.5 mr-1.5" />Hapus Logo
                          </Button>
                        )}
                      </div>
                      <Field label={`Tinggi logo: ${Math.round(hdr.logo_height_mm || 16)} mm`}>
                        <Slider
                          min={6} max={40} step={1}
                          value={[Number(hdr.logo_height_mm || 16)]}
                          onValueChange={v => patch('header', 'logo_height_mm', v[0])}
                          data-testid="pdf-kop-logo-height"
                        />
                      </Field>
                    </div>
                  </div>
                </SectionCard>

                <SectionCard icon={Layers} title="Tata letak & identitas"
                             testId="pdf-kop-layout">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Field label="Tata letak kop">
                      <Select value={hdr.layout || 'logo-left'}
                              onValueChange={v => patch('header', 'layout', v)}>
                        <SelectTrigger className="h-9" data-testid="pdf-kop-layout-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(LAYOUT_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Perataan teks identitas">
                      <Select value={hdr.text_align || 'left'}
                              onValueChange={v => patch('header', 'text_align', v)}>
                        <SelectTrigger className="h-9" data-testid="pdf-kop-textalign-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ALIGN_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                  </div>

                  <Separator className="my-3" />
                  <Toggle
                    label="Ambil identitas dari Pengaturan Perusahaan"
                    hint="Nyala = kolom yang dibiarkan kosong di bawah diisi otomatis dari data perusahaan."
                    checked={hdr.use_company_profile !== false}
                    onCheckedChange={v => patch('header', 'use_company_profile', v)}
                    testId="pdf-kop-useprofile"
                  />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                    <Field label="Nama perusahaan">
                      <GlassInput value={hdr.company_name || ''}
                                  placeholder={profile.company_name || 'CV. Dewi Aditya'}
                                  onChange={e => patch('header', 'company_name', e.target.value)}
                                  data-testid="pdf-kop-company-name" />
                    </Field>
                    <Field label="Alamat">
                      <GlassInput value={hdr.address || ''}
                                  placeholder={profile.address || 'Alamat perusahaan'}
                                  onChange={e => patch('header', 'address', e.target.value)}
                                  data-testid="pdf-kop-address" />
                    </Field>
                    <Field label="Telepon">
                      <GlassInput value={hdr.phone || ''} placeholder={profile.phone || '0271-…'}
                                  onChange={e => patch('header', 'phone', e.target.value)}
                                  data-testid="pdf-kop-phone" />
                    </Field>
                    <Field label="Email">
                      <GlassInput value={hdr.email || ''} placeholder={profile.email || 'email@…'}
                                  onChange={e => patch('header', 'email', e.target.value)}
                                  data-testid="pdf-kop-email" />
                    </Field>
                    <Field label="Website">
                      <GlassInput value={hdr.website || ''} placeholder={profile.website || 'www…'}
                                  onChange={e => patch('header', 'website', e.target.value)}
                                  data-testid="pdf-kop-website" />
                    </Field>
                    <Field label="NPWP">
                      <GlassInput value={hdr.npwp || ''} placeholder={profile.npwp || '00.000.000.0-000.000'}
                                  onChange={e => patch('header', 'npwp', e.target.value)}
                                  data-testid="pdf-kop-npwp" />
                    </Field>
                    <Field label="Baris tambahan" className="md:col-span-2"
                           hint="Mis. cabang, izin usaha, atau catatan yang selalu ikut di kop.">
                      <GlassInput value={hdr.extra_line || ''}
                                  onChange={e => patch('header', 'extra_line', e.target.value)}
                                  data-testid="pdf-kop-extra" />
                    </Field>
                  </div>
                </SectionCard>

                <SectionCard icon={FileText} title="Judul dokumen & garis pemisah"
                             testId="pdf-kop-title">
                  <Toggle label="Tampilkan garis pemisah di bawah kop"
                          checked={hdr.show_divider !== false}
                          onCheckedChange={v => patch('header', 'show_divider', v)}
                          testId="pdf-kop-divider" />
                  <Toggle label="Tampilkan judul dokumen"
                          checked={hdr.show_title !== false}
                          onCheckedChange={v => patch('header', 'show_title', v)}
                          testId="pdf-kop-showtitle" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                    <Field label="Perataan judul">
                      <Select value={hdr.title_align || 'left'}
                              onValueChange={v => patch('header', 'title_align', v)}>
                        <SelectTrigger className="h-9" data-testid="pdf-kop-titlealign">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ALIGN_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Ganti teks judul"
                           hint={isGlobal
                             ? 'Kosongkan agar tiap dokumen memakai judul bawaannya.'
                             : `Kosong = "${activeDoc?.title || ''}"`}>
                      <GlassInput value={hdr.title_override || ''}
                                  onChange={e => patch('header', 'title_override', e.target.value)}
                                  data-testid="pdf-kop-title-override" />
                    </Field>
                  </div>
                </SectionCard>
              </TabsContent>

              {/* ── KOLOM TABEL ───────────────────────────────────────────── */}
              <TabsContent value="kolom" className="space-y-4 mt-4">
                {isGlobal ? (
                  <SectionCard icon={Columns3} title="Kolom tabel diatur per jenis dokumen"
                               testId="pdf-kolom-global-note">
                    <p className="text-sm text-muted-foreground">
                      Kolom SPP tidak berarti apa pun untuk slip gaji, jadi susunan kolom
                      selalu milik jenis dokumennya. Pilih satu jenis dokumen di atas untuk
                      mengatur kolomnya.
                    </p>
                  </SectionCard>
                ) : columns.length === 0 ? (
                  <SectionCard icon={Columns3} title="Dokumen ini tidak punya tabel yang bisa diatur"
                               testId="pdf-kolom-empty">
                    <p className="text-sm text-muted-foreground">
                      Jenis dokumen ini tidak memakai tabel kolom (mis. dokumen naratif).
                    </p>
                  </SectionCard>
                ) : activeDoc?.columns_enforced === false ? (
                  /* Kejujuran layar: kalau generatornya masih memakai daftar kolom
                     bawaan kode, penyunting kolom TIDAK ditampilkan. Setelan yang
                     tersimpan tetapi tidak berlaku sama buruknya dengan setelan yang
                     tidak ada — pemilik mengira sudah mengubah sesuatu. */
                  <SectionCard icon={Info} title="Kolom dokumen ini belum bisa diatur dari sini"
                               testId="pdf-kolom-locked">
                    <p className="text-sm text-muted-foreground">
                      {activeDoc?.columns_note
                        || 'Dokumen ini masih memakai daftar kolom bawaan sistem.'}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {columns.map(c => (
                        <Badge key={c.key} variant="outline" className="text-[11px]"
                               data-testid={`pdf-kolom-readonly-${c.key}`}>
                          {c.label}
                        </Badge>
                      ))}
                    </div>
                  </SectionCard>
                ) : (
                  <SectionCard icon={Columns3} title={`Kolom tabel · ${activeDoc?.label || ''}`}
                               desc="Urutan di daftar ini = urutan kolom di PDF. Kolom wajib tidak bisa disembunyikan karena total & penomoran baris dihitung darinya."
                               testId="pdf-kolom-editor">
                    <div className="space-y-2">
                      {columns.map((c, i) => (
                        <div key={c.key}
                             className="rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-muted/20 p-2.5"
                             data-testid={`pdf-kolom-row-${c.key}`}>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-mono text-muted-foreground w-6 text-right">
                              {i + 1}
                            </span>
                            <div className="flex flex-col gap-0.5">
                              <Button variant="ghost" size="icon"
                                      className="h-5 w-5" onClick={() => moveColumn(i, -1)}
                                      disabled={i === 0}
                                      aria-label={`Naikkan kolom ${c.label}`}
                                      data-testid={`pdf-kolom-up-${c.key}`}>
                                <ArrowUp className="w-3 h-3" />
                              </Button>
                              <Button variant="ghost" size="icon"
                                      className="h-5 w-5" onClick={() => moveColumn(i, 1)}
                                      disabled={i === columns.length - 1}
                                      aria-label={`Turunkan kolom ${c.label}`}
                                      data-testid={`pdf-kolom-down-${c.key}`}>
                                <ArrowDown className="w-3 h-3" />
                              </Button>
                            </div>
                            <GlassInput
                              value={c.label || ''} className="h-8 flex-1"
                              onChange={e => patchColumn(i, 'label', e.target.value)}
                              data-testid={`pdf-kolom-label-${c.key}`}
                            />
                            <Select value={c.align || 'left'}
                                    onValueChange={v => patchColumn(i, 'align', v)}>
                              <SelectTrigger className="h-8 w-[92px]"
                                             data-testid={`pdf-kolom-align-${c.key}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {Object.entries(ALIGN_LABELS).map(([k, v]) => (
                                  <SelectItem key={k} value={k}>{v}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <GlassInput
                              type="number" min={0} max={10} step={0.1}
                              className="h-8 w-[74px]" value={c.width ?? 0}
                              onChange={e => patchColumn(i, 'width', Number(e.target.value))}
                              title="Lebar relatif (0 = otomatis)"
                              data-testid={`pdf-kolom-width-${c.key}`}
                            />
                            {c.required ? (
                              <Badge variant="outline" className="text-[10px]"
                                     data-testid={`pdf-kolom-required-${c.key}`}>wajib</Badge>
                            ) : (
                              <Switch
                                checked={c.visible !== false}
                                onCheckedChange={v => patchColumn(i, 'visible', v)}
                                aria-label={`Tampilkan kolom ${c.label}`}
                                data-testid={`pdf-kolom-visible-${c.key}`}
                              />
                            )}
                            {c.custom && (
                              <Button variant="ghost" size="icon" className="h-7 w-7"
                                      onClick={() => removeColumn(i)}
                                      aria-label={`Hapus kolom ${c.label}`}
                                      data-testid={`pdf-kolom-remove-${c.key}`}>
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-1 pl-8 font-mono">
                            {c.key}{c.custom ? ' · kolom tambahan (dicetak kosong untuk ditulis tangan)' : ''}
                          </p>
                        </div>
                      ))}
                    </div>
                    <Button variant="ghost" onClick={addColumn}
                            className="mt-3 h-8 text-xs border border-dashed border-[var(--glass-border)]"
                            data-testid="pdf-kolom-add">
                      <Plus className="w-3 h-3 mr-1" />Tambah Kolom Kosong
                    </Button>
                  </SectionCard>
                )}
              </TabsContent>

              {/* ── TANDA TANGAN ──────────────────────────────────────────── */}
              <TabsContent value="ttd" className="space-y-4 mt-4">
                {!isGlobal && (
                  <SectionCard icon={Info} title="Sumber setelan tanda tangan"
                               testId="pdf-ttd-override">
                    <Toggle
                      label="Pakai blok tanda tangan khusus untuk dokumen ini"
                      hint="Mati = mengikuti Template Global; bila global belum diisi, dipakai blok bawaan dokumen ini."
                      checked={!!tpl.override_signatures}
                      onCheckedChange={v => patchRoot('override_signatures', v)}
                      testId="pdf-ttd-override-switch"
                    />
                  </SectionCard>
                )}

                <SectionCard icon={PenLine} title="Tata letak tanda tangan" testId="pdf-ttd-layout">
                  <Toggle label="Tampilkan blok tanda tangan"
                          checked={sig.show !== false}
                          onCheckedChange={v => patch('signatures', 'show', v)}
                          testId="pdf-ttd-show" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                    <Field label="Blok per baris">
                      <Select value={String(sig.per_row || 3)}
                              onValueChange={v => patch('signatures', 'per_row', Number(v))}>
                        <SelectTrigger className="h-9" data-testid="pdf-ttd-perrow">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[1, 2, 3, 4].map(n => (
                            <SelectItem key={n} value={String(n)}>{n} blok</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label={`Tinggi ruang tanda tangan: ${Math.round(sig.space_mm || 18)} mm`}>
                      <Slider min={8} max={40} step={1} value={[Number(sig.space_mm || 18)]}
                              onValueChange={v => patch('signatures', 'space_mm', v[0])}
                              data-testid="pdf-ttd-space" />
                    </Field>
                  </div>
                  <Separator className="my-3" />
                  <Toggle label="Tampilkan tempat & tanggal di atas tanda tangan"
                          checked={!!sig.show_place_date}
                          onCheckedChange={v => patch('signatures', 'show_place_date', v)}
                          testId="pdf-ttd-placedate" />
                  {sig.show_place_date && (
                    <Field label="Kota / tempat">
                      <GlassInput value={sig.place || ''} placeholder="mis. Sragen"
                                  onChange={e => patch('signatures', 'place', e.target.value)}
                                  data-testid="pdf-ttd-place" />
                    </Field>
                  )}
                </SectionCard>

                <SectionCard icon={PenLine} title="Blok tanda tangan"
                             desc="Tiap blok: SUBJECT di atas (mis. Penerima) · ruang kosong untuk tanda tangan · NAMA di bawah · keterangan kecil."
                             testId="pdf-ttd-blocks">
                  <div className="space-y-3">
                    {sigBlocks.length === 0 && (
                      <p className="text-sm text-muted-foreground">
                        Belum ada blok. Tambahkan minimal satu blok, atau matikan tampilan
                        tanda tangan di atas.
                      </p>
                    )}
                    {sigBlocks.map((b, i) => (
                      <div key={i}
                           className="rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-muted/20 p-3"
                           data-testid={`pdf-ttd-block-${i}`}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold">
                            Blok {i + 1}
                          </span>
                          <div className="flex items-center gap-1">
                            <Button variant="ghost" size="icon" className="h-7 w-7"
                                    onClick={() => moveBlock(i, -1)} disabled={i === 0}
                                    aria-label={`Naikkan blok ${i + 1}`}
                                    data-testid={`pdf-ttd-up-${i}`}>
                              <ArrowUp className="w-3.5 h-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-7 w-7"
                                    onClick={() => moveBlock(i, 1)}
                                    disabled={i === sigBlocks.length - 1}
                                    aria-label={`Turunkan blok ${i + 1}`}
                                    data-testid={`pdf-ttd-down-${i}`}>
                              <ArrowDown className="w-3.5 h-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-7 w-7"
                                    onClick={() => removeBlock(i)}
                                    aria-label={`Hapus blok ${i + 1}`}
                                    data-testid={`pdf-ttd-remove-${i}`}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <Field label="Subject (baris atas)">
                            <GlassInput value={b.subject || ''} placeholder="mis. Penerima"
                                        onChange={e => patchBlock(i, 'subject', e.target.value)}
                                        data-testid={`pdf-ttd-subject-${i}`} />
                          </Field>
                          <Field label="Nama di bawah tanda tangan">
                            <Select value={b.name_source || 'blank'}
                                    onValueChange={v => patchBlock(i, 'name_source', v)}>
                              <SelectTrigger className="h-9" data-testid={`pdf-ttd-source-${i}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {Object.entries(NAME_SOURCE_LABELS).map(([k, v]) => (
                                  <SelectItem key={k} value={k}
                                              disabled={k === 'field' && availableFields.length === 0}>
                                    {v}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </Field>
                          {b.name_source === 'custom' && (
                            <Field label="Nama yang dicetak">
                              <GlassInput value={b.custom_name || ''}
                                          onChange={e => patchBlock(i, 'custom_name', e.target.value)}
                                          data-testid={`pdf-ttd-customname-${i}`} />
                            </Field>
                          )}
                          {b.name_source === 'field' && (
                            <Field label="Ambil nama dari data">
                              <Select value={b.field_key || ''}
                                      onValueChange={v => patchBlock(i, 'field_key', v)}>
                                <SelectTrigger className="h-9" data-testid={`pdf-ttd-field-${i}`}>
                                  <SelectValue placeholder="Pilih field" />
                                </SelectTrigger>
                                <SelectContent>
                                  {availableFields.map(f => (
                                    <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </Field>
                          )}
                          <Field label="Keterangan kecil (di bawah nama)"
                                 className={b.name_source === 'blank' ? 'md:col-span-1' : 'md:col-span-2'}>
                            <GlassInput value={b.note || ''} placeholder="mis. Gudang / Nama & TTD"
                                        onChange={e => patchBlock(i, 'note', e.target.value)}
                                        data-testid={`pdf-ttd-note-${i}`} />
                          </Field>
                        </div>
                      </div>
                    ))}
                  </div>
                  <Button variant="ghost" onClick={addBlock}
                          className="mt-3 h-8 text-xs border border-dashed border-[var(--glass-border)]"
                          data-testid="pdf-ttd-add">
                    <Plus className="w-3 h-3 mr-1" />Tambah Blok Tanda Tangan
                  </Button>
                </SectionCard>
              </TabsContent>

              {/* ── FOOTER & GAYA TABEL ───────────────────────────────────── */}
              <TabsContent value="lain" className="space-y-4 mt-4">
                {!isGlobal && (
                  <SectionCard icon={Info} title="Sumber setelan footer" testId="pdf-footer-override">
                    <Toggle
                      label="Pakai footer khusus untuk dokumen ini"
                      hint="Mati = mengikuti Template Global."
                      checked={!!tpl.override_footer}
                      onCheckedChange={v => patchRoot('override_footer', v)}
                      testId="pdf-footer-override-switch"
                    />
                  </SectionCard>
                )}

                <SectionCard icon={FileText} title="Footer" testId="pdf-footer">
                  <Toggle label="Tampilkan footer"
                          checked={ftr.show !== false}
                          onCheckedChange={v => patch('footer', 'show', v)}
                          testId="pdf-footer-show" />
                  <Field label="Teks footer" className="mt-2"
                         hint="Mis. syarat pengiriman, catatan hukum, atau alamat cabang.">
                    <Textarea rows={2} value={ftr.text || ''}
                              onChange={e => patch('footer', 'text', e.target.value)}
                              className="bg-[var(--input-surface)] border-[var(--glass-border)]"
                              data-testid="pdf-footer-text" />
                  </Field>
                  <Toggle label="Cetak waktu pencetakan"
                          hint="Membantu membedakan cetakan ulang dari cetakan pertama."
                          checked={ftr.show_printed_at !== false}
                          onCheckedChange={v => patch('footer', 'show_printed_at', v)}
                          testId="pdf-footer-printedat" />
                </SectionCard>

                <SectionCard icon={Columns3} title="Gaya tabel" testId="pdf-table-style">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Field label="Warna latar baris judul">
                      <input
                        type="color" value={tbl.header_bg || '#334155'}
                        onChange={e => patch('table', 'header_bg', e.target.value)}
                        className="h-9 w-full rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-[var(--input-surface)] p-1 cursor-pointer"
                        data-testid="pdf-table-headerbg"
                        aria-label="Warna latar baris judul tabel"
                      />
                    </Field>
                    <Field label={`Ukuran font tabel: ${Number(tbl.font_size || 7.5).toFixed(1)} pt`}
                           hint="Jarak antarbaris dihitung otomatis 1,44 × ukuran font agar teks tidak pernah tumpang tindih.">
                      <Slider min={6} max={10} step={0.5} value={[Number(tbl.font_size || 7.5)]}
                              onValueChange={v => patch('table', 'font_size', v[0])}
                              data-testid="pdf-table-fontsize" />
                    </Field>
                  </div>
                  <Toggle label="Baris berwarna bergantian (zebra)"
                          checked={tbl.zebra !== false}
                          onCheckedChange={v => patch('table', 'zebra', v)}
                          testId="pdf-table-zebra" />
                  <Toggle label="Garis kisi penuh"
                          hint="Mati = hanya garis di bawah baris judul (tampilan lebih bersih)."
                          checked={tbl.grid !== false}
                          onCheckedChange={v => patch('table', 'grid', v)}
                          testId="pdf-table-grid" />
                </SectionCard>
              </TabsContent>
            </Tabs>
          )}
        </div>

        {/* ── PRATINJAU ───────────────────────────────────────────────────── */}
        <div className="xl:col-span-5" data-testid="pdf-studio-preview">
          <GlassCard className="p-3 xl:sticky xl:top-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <Eye className="w-4 h-4 text-[hsl(var(--primary))]" />
                <span className="text-sm font-semibold text-foreground truncate">
                  Pratinjau: {docs.find(d => d.doc_key === previewKey)?.label || previewKey}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                {previewing && (
                  <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1"
                        data-testid="pdf-preview-loading">
                    <Loader2 className="w-3 h-3 animate-spin" />memuat
                  </span>
                )}
                <div className="inline-flex rounded-[var(--radius-sm)] border border-[var(--glass-border)] overflow-hidden">
                  {[['gambar', 'Gambar'], ['pdf', 'PDF']].map(([m, label]) => (
                    <button
                      key={m} type="button"
                      onClick={() => setPreviewMode(m)}
                      className={`px-2.5 h-7 text-[11px] transition-colors ${
                        previewMode === m
                          ? 'bg-[hsl(var(--primary)/0.15)] text-foreground'
                          : 'text-muted-foreground hover:bg-muted/50'}`}
                      data-testid={`pdf-preview-mode-${m}`}
                      aria-pressed={previewMode === m}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={openPdfTab}
                        aria-label="Buka PDF di tab baru" data-testid="pdf-preview-open">
                  <ExternalLink className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>

            {previewErr ? (
              <div className="rounded-[var(--radius-sm)] border border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.08)] p-3"
                   data-testid="pdf-preview-error">
                <p className="text-sm text-foreground">{previewErr}</p>
                <Button variant="ghost" className="mt-2 h-8 text-xs border border-[var(--glass-border)]"
                        onClick={() => setTpl(p => ({ ...p }))} data-testid="pdf-preview-retry">
                  <RefreshCw className="w-3 h-3 mr-1" />Coba lagi
                </Button>
              </div>
            ) : previewUrl ? (
              previewMode === 'gambar' ? (
                <div className="w-full h-[76vh] overflow-auto rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-white">
                  <img src={previewUrl} alt="Pratinjau halaman pertama dokumen"
                       className="w-full h-auto block"
                       data-testid="pdf-preview-image" />
                </div>
              ) : (
                <iframe
                  key={previewUrl}
                  src={previewUrl}
                  title="Pratinjau dokumen PDF"
                  className="w-full h-[76vh] rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-white"
                  data-testid="pdf-preview-frame"
                />
              )
            ) : (
              <Skeleton className="w-full h-[76vh]" data-testid="pdf-preview-skeleton" />
            )}
            <p className="text-[11px] text-muted-foreground mt-2">
              Pratinjau memakai DATA CONTOH dan dibuat oleh generator PDF yang sama
              dengan dokumen sungguhan, jadi yang terlihat di sini itulah yang tercetak.
              Mode <b className="text-foreground">Gambar</b> menampilkan halaman pertama;
              mode <b className="text-foreground">PDF</b> memakai penampil PDF browser.
            </p>
            {docs.find(d => d.doc_key === previewKey)?.columns_enforced === false && (
              /* Kejujuran: untuk jenis yang tata letak isinya khusus (slip gaji A5,
                 panduan produksi), yang benar-benar berlaku dari template adalah kop,
                 tanda tangan, dan footer — bukan susunan tabelnya. */
              <p className="text-[11px] mt-1 text-[hsl(var(--warning))]"
                 data-testid="pdf-preview-caveat">
                Catatan untuk jenis ini: yang benar-benar diambil dari template adalah
                kop surat, blok tanda tangan, dan footer. Tata letak isinya memakai
                rancangan khusus dokumen ini, jadi bagian tabel di pratinjau hanya
                gambaran.
              </p>
            )}
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
