/**
 * ⚠️ LAYAR PENSIUN (SESI #19, 2026-08-18) — JANGAN DIPASANG LAGI KE MENU.
 *
 * Digantikan `erp/pdf/PdfTemplateStudio.jsx` ("PDF & Kop Surat"): satu layar untuk
 * kop surat (logo & identitas PT), kolom tabel (tampil/urutan/tambah), blok tanda
 * tangan, footer, PLUS pratinjau PDF di sampingnya. Keluhan pemilik yang membuat
 * layar ini dipensiunkan: "cek ada dua halaman berbeda ui ux-nya jelas" —
 * berkas ini adalah salah satu dari dua halaman itu.
 *
 * Berkas TIDAK dihapus supaya riwayat & pola lamanya bisa dibaca, tetapi tidak
 * dirujuk `moduleRegistry.js` maupun hub mana pun. Penjaga INV-F26 (P1) akan MERAH
 * bila berkas ini dipasang kembali sebagai tab/menu.
 */
/**
 * PdfDocSettingsModule — Pengaturan PDF per jenis surat/dokumen.
 *
 * Wire ke API framework:
 *   GET  /api/pdf-doc-settings/doc-types        → katalog jenis dokumen + field TTD
 *   GET  /api/pdf-doc-settings/{doc_type}       → pengaturan (default bila belum di-set)
 *   PUT  /api/pdf-doc-settings/{doc_type}        → simpan (admin only)
 *
 * Mengatur: branding per dokumen (logo/header/footer override) + blok tanda tangan
 * (label, sumber nama, jabatan) untuk payslip, surat jalan, invoice maklon, dll.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  FileSignature, Save, RefreshCw, CheckCircle, Plus, Trash2,
  Image as ImageIcon, PenLine, Info,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// Sumber nama penandatangan → label ramah untuk UI
const NAME_SOURCES = [
  { value: 'custom', label: 'Nama tetap (ketik manual)' },
  { value: 'field',  label: 'Ambil dari data dokumen' },
  { value: 'user',   label: 'Nama pencetak (user login)' },
  { value: 'blank',  label: 'Kosong (tanda tangan basah)' },
];

const emptySig = () => ({
  key: `sig_${Math.random().toString(36).slice(2, 8)}`,
  label: '',
  name_source: 'blank',
  custom_name: '',
  field_key: '',
  role_label: '',
});

export default function PdfDocSettingsModule({ token, userRole }) {
  const [docTypes, setDocTypes] = useState([]);
  const [selected, setSelected] = useState('');
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const canEdit = ['superadmin', 'admin'].includes(userRole);
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const currentSpec = useMemo(
    () => docTypes.find((d) => d.doc_type === selected) || null,
    [docTypes, selected]
  );
  const availableFields = currentSpec?.available_fields || [];

  // ── Load katalog jenis dokumen ─────────────────────────────────────
  const loadDocTypes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/pdf-doc-settings/doc-types`, { headers });
      const data = await res.json();
      const list = data.doc_types || [];
      setDocTypes(list);
      if (list.length && !selected) setSelected(list[0].doc_type);
    } catch (e) {
      console.error('Gagal memuat jenis dokumen PDF', e);
    }
    setLoading(false);
  }, [headers]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load pengaturan satu jenis dokumen ─────────────────────────────
  const loadSettings = useCallback(async (docType) => {
    if (!docType) return;
    setLoadingDoc(true);
    try {
      const res = await fetch(`${API}/api/pdf-doc-settings/${docType}`, { headers });
      const data = await res.json();
      setSettings({
        show_logo: data.show_logo ?? true,
        show_signatures: data.show_signatures ?? true,
        header_line1: data.header_line1 || '',
        header_line2: data.header_line2 || '',
        footer_text: data.footer_text || '',
        signatures: Array.isArray(data.signatures) ? data.signatures.map((s) => ({
          key: s.key || emptySig().key,
          label: s.label || '',
          name_source: s.name_source || 'blank',
          custom_name: s.custom_name || '',
          field_key: s.field_key || '',
          role_label: s.role_label || '',
        })) : [],
      });
    } catch (e) {
      console.error('Gagal memuat pengaturan dokumen', e);
    }
    setLoadingDoc(false);
  }, [headers]);

  useEffect(() => { loadDocTypes(); }, [loadDocTypes]);
  useEffect(() => { if (selected) loadSettings(selected); }, [selected, loadSettings]);

  // ── Mutators ───────────────────────────────────────────────────────
  const setField = (k, v) => setSettings((s) => ({ ...s, [k]: v }));
  const setSig = (idx, patch) =>
    setSettings((s) => ({
      ...s,
      signatures: s.signatures.map((sig, i) => (i === idx ? { ...sig, ...patch } : sig)),
    }));
  const addSig = () =>
    setSettings((s) => ({ ...s, signatures: [...(s.signatures || []), emptySig()] }));
  const removeSig = (idx) =>
    setSettings((s) => ({ ...s, signatures: s.signatures.filter((_, i) => i !== idx) }));
  const resetToDefault = () => {
    if (!currentSpec) return;
    setSettings((s) => ({
      ...s,
      signatures: (currentSpec.default_signatures || []).map((sig) => ({ ...sig })),
    }));
  };

  // ── Save ───────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!selected || !settings) return;
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch(`${API}/api/pdf-doc-settings/${selected}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        const data = await res.json();
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
        // sinkronkan dari respons kanonik
        if (data && Array.isArray(data.signatures)) {
          setSettings((s) => ({ ...s, signatures: data.signatures }));
        }
      } else {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || 'Gagal menyimpan pengaturan');
      }
    } catch (e) {
      alert('Gagal menyimpan: ' + e.message);
    }
    setSaving(false);
  };

  const previewName = (sig) => {
    if (sig.name_source === 'custom') return sig.custom_name || '(nama tetap kosong)';
    if (sig.name_source === 'field') {
      const f = availableFields.find((af) => af.key === sig.field_key);
      return `‹${f ? f.label : sig.field_key || 'pilih field'}›`;
    }
    if (sig.name_source === 'user') return '‹nama pencetak›';
    return '________________';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Kelompokkan jenis dokumen per grup
  const groups = docTypes.reduce((acc, d) => {
    (acc[d.group] = acc[d.group] || []).push(d);
    return acc;
  }, {});

  return (
    <div className="space-y-6 max-w-5xl" data-testid="pdf-doc-settings">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <FileSignature className="w-5 h-5 text-primary" /> Surat &amp; Tanda Tangan
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Atur branding &amp; blok tanda tangan tiap jenis surat/dokumen resmi.
          </p>
        </div>
        {saved && (
          <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2 text-sm text-emerald-700">
            <CheckCircle className="w-4 h-4" /> Berhasil disimpan!
          </div>
        )}
      </div>

      {!canEdit && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>Hanya admin yang dapat mengubah pengaturan ini. Anda dapat melihat konfigurasi saat ini.</span>
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Sidebar: pilih jenis dokumen */}
        <div className="col-span-12 md:col-span-4 lg:col-span-3">
          <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
            <div className="px-4 py-3 border-b border-border">
              <h3 className="font-semibold text-sm text-foreground">Jenis Dokumen</h3>
            </div>
            <div className="p-2 space-y-3 max-h-[520px] overflow-y-auto">
              {Object.entries(groups).map(([grp, docs]) => (
                <div key={grp}>
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground px-2 mb-1">{grp}</p>
                  <div className="space-y-0.5">
                    {docs.map((d) => (
                      <button
                        key={d.doc_type}
                        data-testid={`pdf-doc-pick-${d.doc_type}`}
                        onClick={() => setSelected(d.doc_type)}
                        className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                          selected === d.doc_type
                            ? 'bg-primary/10 text-primary font-medium border border-primary/20'
                            : 'text-foreground hover:bg-foreground/5 border border-transparent'
                        }`}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Editor */}
        <div className="col-span-12 md:col-span-8 lg:col-span-9 space-y-6">
          {loadingDoc || !settings ? (
            <div className="flex items-center justify-center h-64">
              <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Branding */}
              <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
                <div className="flex items-center gap-2 px-5 py-4 border-b border-border">
                  <ImageIcon className="w-5 h-5 text-primary" />
                  <h3 className="font-semibold text-foreground">Branding Dokumen — {currentSpec?.label}</h3>
                </div>
                <div className="p-5 space-y-4">
                  <div className="flex flex-wrap gap-6">
                    <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                      <input type="checkbox" disabled={!canEdit} className="w-4 h-4 accent-[hsl(var(--primary))]"
                        checked={!!settings.show_logo}
                        data-testid="pdf-doc-show-logo"
                        onChange={(e) => setField('show_logo', e.target.checked)} />
                      Tampilkan logo perusahaan
                    </label>
                    <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                      <input type="checkbox" disabled={!canEdit} className="w-4 h-4 accent-[hsl(var(--primary))]"
                        checked={!!settings.show_signatures}
                        data-testid="pdf-doc-show-signatures"
                        onChange={(e) => setField('show_signatures', e.target.checked)} />
                      Tampilkan blok tanda tangan
                    </label>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-1">Header Baris 1 (override)</label>
                      <input type="text" disabled={!canEdit}
                        className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--glass-bg)]"
                        value={settings.header_line1}
                        onChange={(e) => setField('header_line1', e.target.value)}
                        placeholder="Kosong = pakai nama perusahaan" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-1">Header Baris 2 (override)</label>
                      <input type="text" disabled={!canEdit}
                        className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--glass-bg)]"
                        value={settings.header_line2}
                        onChange={(e) => setField('header_line2', e.target.value)}
                        placeholder="Kosong = pakai alamat/tagline" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-sm font-medium text-foreground mb-1">Footer (override)</label>
                      <input type="text" disabled={!canEdit}
                        className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--glass-bg)]"
                        value={settings.footer_text}
                        onChange={(e) => setField('footer_text', e.target.value)}
                        placeholder="Kosong = pakai footer default perusahaan" />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground flex items-start gap-1.5">
                    <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    Kolom override yang kosong akan otomatis memakai profil perusahaan (tab "Perusahaan").
                  </p>
                </div>
              </div>

              {/* Blok Tanda Tangan */}
              <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
                <div className="flex items-center justify-between gap-2 px-5 py-4 border-b border-border">
                  <div className="flex items-center gap-2">
                    <PenLine className="w-5 h-5 text-primary" />
                    <h3 className="font-semibold text-foreground">Blok Tanda Tangan</h3>
                    <span className="text-xs text-muted-foreground">({settings.signatures.length})</span>
                  </div>
                  {canEdit && (
                    <button onClick={resetToDefault}
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                      data-testid="pdf-doc-reset-default">
                      <RefreshCw className="w-3.5 h-3.5" /> Reset ke default
                    </button>
                  )}
                </div>
                <div className="p-5 space-y-4">
                  {settings.signatures.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">Belum ada blok tanda tangan.</p>
                  )}
                  {settings.signatures.map((sig, idx) => (
                    <div key={sig.key || idx} className="rounded-lg border border-border p-4 bg-[var(--glass-bg)]"
                      data-testid={`pdf-doc-sig-${idx}`}>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">Label</label>
                          <input type="text" disabled={!canEdit}
                            className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--card-surface)]"
                            value={sig.label}
                            onChange={(e) => setSig(idx, { label: e.target.value })}
                            placeholder="mis. Disetujui oleh" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">Jabatan / Peran</label>
                          <input type="text" disabled={!canEdit}
                            className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--card-surface)]"
                            value={sig.role_label}
                            onChange={(e) => setSig(idx, { role_label: e.target.value })}
                            placeholder="mis. HRD / Finance" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-muted-foreground mb-1">Sumber Nama</label>
                          <select disabled={!canEdit}
                            className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] text-foreground disabled:opacity-70"
                            value={sig.name_source}
                            onChange={(e) => setSig(idx, { name_source: e.target.value })}>
                            {NAME_SOURCES.map((ns) => (
                              <option key={ns.value} value={ns.value}>{ns.label}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          {sig.name_source === 'custom' && (
                            <>
                              <label className="block text-xs font-medium text-muted-foreground mb-1">Nama (tetap)</label>
                              <input type="text" disabled={!canEdit}
                                className="w-full border border-border rounded-lg px-3 py-2 text-sm disabled:bg-[var(--card-surface)]"
                                value={sig.custom_name}
                                onChange={(e) => setSig(idx, { custom_name: e.target.value })}
                                placeholder="mis. Ibu Dewi" />
                            </>
                          )}
                          {sig.name_source === 'field' && (
                            <>
                              <label className="block text-xs font-medium text-muted-foreground mb-1">Field Data</label>
                              <SmartNativeSelect disabled={!canEdit}
                                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)] text-foreground disabled:opacity-70"
                                value={sig.field_key}
                                onChange={(e) => setSig(idx, { field_key: e.target.value })}>
                                <option value="">— pilih field —</option>
                                {availableFields.map((af) => (
                                  <option key={af.key} value={af.key}>{af.label}</option>
                                ))}
                              </SmartNativeSelect>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                        <div className="text-xs text-muted-foreground">
                          Pratinjau nama: <span className="font-medium text-foreground">{previewName(sig)}</span>
                        </div>
                        {canEdit && (
                          <button onClick={() => removeSig(idx)}
                            className="text-xs text-red-600 hover:text-red-700 flex items-center gap-1"
                            data-testid={`pdf-doc-sig-remove-${idx}`}>
                            <Trash2 className="w-3.5 h-3.5" /> Hapus
                          </button>
                        )}
                      </div>
                    </div>
                  ))}

                  {canEdit && (
                    <button onClick={addSig}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-primary border border-dashed border-primary/30 rounded-lg hover:bg-primary/5 w-full justify-center"
                      data-testid="pdf-doc-sig-add">
                      <Plus className="w-4 h-4" /> Tambah Blok Tanda Tangan
                    </button>
                  )}
                </div>
              </div>

              {/* Preview blok TTD */}
              {settings.show_signatures && settings.signatures.length > 0 && (
                <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
                  <div className="px-5 py-4 border-b border-border">
                    <h3 className="font-semibold text-foreground">Preview Blok Tanda Tangan</h3>
                  </div>
                  <div className="p-5">
                    <div className="flex flex-wrap gap-8 justify-around border-2 border-border rounded-lg p-6 bg-[var(--glass-bg)]">
                      {settings.signatures.map((sig, idx) => (
                        <div key={sig.key || idx} className="text-center min-w-[140px]">
                          <p className="text-xs text-muted-foreground mb-10">{sig.label || '(label)'}</p>
                          <p className="text-sm font-medium text-foreground border-t border-foreground/40 pt-1 min-w-[120px]">
                            {previewName(sig)}
                          </p>
                          {sig.role_label && <p className="text-[11px] text-muted-foreground">{sig.role_label}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {canEdit && (
                <button onClick={handleSave} disabled={saving}
                  data-testid="pdf-doc-save"
                  className="flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl text-sm font-medium hover:brightness-110 disabled:opacity-50 shadow-sm">
                  <Save className="w-4 h-4" />
                  {saving ? 'Menyimpan...' : 'Simpan Pengaturan'}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
