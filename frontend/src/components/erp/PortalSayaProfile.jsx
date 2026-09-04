import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Loader2, User, Save, Building2, Link as LinkIcon, AlertCircle,
  Phone, MapPin, UserCheck, Camera, Upload, X,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PortalSayaProfile({ user, headers }) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [form, setForm] = useState({
    nama_panggilan: '', no_hp: '', alamat: '', foto_url: '',
    kontak_darurat: { nama: '', hubungan: '', no_hp: '' },
  });

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/portal/profile`, { headers });
      setProfile(data);
      setPreviewUrl(data.foto_url || null);
      setForm({
        nama_panggilan: data.nama_panggilan || '',
        no_hp: data.no_hp || '',
        alamat: data.alamat || '',
        foto_url: data.foto_url || '',
        kontak_darurat: data.kontak_darurat || { nama: '', hubungan: '', no_hp: '' },
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/api/portal/profile`, form, { headers });
      toast({ title: 'Profil berhasil diperbarui.' });
      load();
    } catch (e) {
      toast({ title: 'Gagal menyimpan.', description: e.response?.data?.detail, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handlePhotoSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Local preview
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    // Upload immediately
    uploadPhoto(file);
  };

  const uploadPhoto = async (file) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await axios.post(`${API}/api/portal/profile/photo`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      setForm(f => ({ ...f, foto_url: data.foto_url }));
      setPreviewUrl(`${API}${data.foto_url}`);
      toast({ title: 'Foto profil berhasil diunggah.' });
    } catch (e) {
      toast({ title: 'Gagal mengunggah foto.', description: e.response?.data?.detail, variant: 'destructive' });
      setPreviewUrl(form.foto_url || null);
    } finally {
      setUploading(false);
    }
  };

  const removePhoto = async () => {
    setPreviewUrl(null);
    const newForm = { ...form, foto_url: '' };
    setForm(newForm);
    try {
      await axios.put(`${API}/api/portal/profile`, { foto_url: '' }, { headers });
      toast({ title: 'Foto profil dihapus.' });
    } catch (e) {
      console.error(e);
    }
  };

  const set = (field, val) => setForm(f => ({ ...f, [field]: val }));
  const setKD = (field, val) => setForm(f => ({
    ...f,
    kontak_darurat: { ...(f.kontak_darurat || {}), [field]: val }
  }));

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
    </div>
  );

  const emp = profile?.employee;

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-bold">Profil Saya</h2>

      {/* Account info */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">Informasi Akun</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Photo section */}
          <div className="flex items-start gap-5">
            {/* Avatar with upload overlay */}
            <div className="relative group shrink-0">
              <div
                className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden border-2 border-primary/20 cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? (
                  <Loader2 className="w-7 h-7 animate-spin text-primary" />
                ) : previewUrl ? (
                  <img
                    src={previewUrl.startsWith('blob:') ? previewUrl : (previewUrl.startsWith('/api') ? `${API}${previewUrl}` : previewUrl)}
                    alt="foto profil"
                    className="w-full h-full object-cover"
                    onError={() => setPreviewUrl(null)}
                  />
                ) : (
                  <User className="w-10 h-10 text-primary/50" />
                )}
                {/* Hover overlay */}
                <div className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <Camera className="w-6 h-6 text-foreground" />
                </div>
              </div>
              {previewUrl && !uploading && (
                <button
                  onClick={removePhoto}
                  className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-foreground rounded-full flex items-center justify-center hover:bg-red-600"
                  title="Hapus foto"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Upload actions */}
            <div className="flex-1 space-y-1">
              <p className="font-semibold text-base">{profile?.name || user?.name}</p>
              <p className="text-sm text-muted-foreground">{profile?.email}</p>
              <p className="text-xs text-muted-foreground capitalize mt-0.5">{profile?.role}</p>
              <div className="flex items-center gap-2 mt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  data-testid="btn-upload-photo"
                  className="text-xs h-7"
                >
                  <Upload className="w-3 h-3 mr-1" />
                  {uploading ? 'Mengunggah...' : 'Upload Foto'}
                </Button>
                <Badge className={profile?.is_linked
                  ? 'bg-green-100 text-green-800 border-green-200'
                  : 'bg-amber-100 text-amber-800 border-amber-200'
                }>
                  {profile?.is_linked ? <><LinkIcon className="w-3 h-3 mr-1" />Terhubung</> : 'Belum Terhubung'}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">JPG, PNG, WEBP max 5 MB</p>
            </div>
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handlePhotoSelect}
            data-testid="input-photo-file"
          />

          {/* Employee info */}
          {emp && (
            <div className="bg-muted/50 rounded-lg p-3 space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <Building2 className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="font-medium">{emp.name || emp.full_name}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground text-xs">{emp.nik || emp.employee_id}</span>
              </div>
              {emp.department && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <UserCheck className="w-4 h-4 shrink-0" />
                  <span>{emp.department}{emp.position ? ` — ${emp.position}` : ''}</span>
                </div>
              )}
            </div>
          )}

          {!emp && (
            <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>Akun belum terhubung ke data karyawan. Hubungi HR untuk menghubungkan akun Anda.</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Editable fields */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">Data Pribadi</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-1.5 block">Nama Panggilan</label>
            <input
              data-testid="input-nama-panggilan"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 outline-none"
              value={form.nama_panggilan}
              onChange={e => set('nama_panggilan', e.target.value)}
              placeholder="Nama yang sering dipanggil"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block flex items-center gap-1">
              <Phone className="w-3.5 h-3.5" /> No. HP
            </label>
            <input
              data-testid="input-no-hp"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 outline-none"
              value={form.no_hp}
              onChange={e => set('no_hp', e.target.value)}
              placeholder="08xx-xxxx-xxxx"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5" /> Alamat
            </label>
            <textarea
              data-testid="input-alamat"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 outline-none resize-none"
              rows={2}
              value={form.alamat}
              onChange={e => set('alamat', e.target.value)}
              placeholder="Alamat tinggal saat ini"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">Kontak Darurat</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Nama</label>
              <input
                data-testid="input-kd-nama"
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                value={form.kontak_darurat?.nama || ''}
                onChange={e => setKD('nama', e.target.value)}
                placeholder="Nama kontak"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Hubungan</label>
              <input
                data-testid="input-kd-hubungan"
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                value={form.kontak_darurat?.hubungan || ''}
                onChange={e => setKD('hubungan', e.target.value)}
                placeholder="Ibu, Ayah, Pasangan..."
              />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block">No. HP Kontak</label>
            <input
              data-testid="input-kd-hp"
              className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              value={form.kontak_darurat?.no_hp || ''}
              onChange={e => setKD('no_hp', e.target.value)}
              placeholder="08xx-xxxx-xxxx"
            />
          </div>
        </CardContent>
      </Card>

      <Button
        data-testid="btn-save-profile"
        onClick={handleSave}
        disabled={saving || uploading}
        className="w-full"
      >
        {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Menyimpan...</> : <><Save className="w-4 h-4 mr-2" /> Simpan Profil</>}
      </Button>
    </div>
  );
}
