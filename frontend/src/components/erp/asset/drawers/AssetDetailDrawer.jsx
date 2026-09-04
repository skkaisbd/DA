/**
 * AssetDetailDrawer — Asset detail panel with tabs: Info, Depresiasi, Penugasan, Pemeliharaan.
 * Extracted from AssetManagementPortal.jsx (Phase 3 refactor)
 */
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import {
  Package, Edit, ArrowRight, Trash2, Barcode, QrCode, Printer,
} from 'lucide-react';
import { toast } from 'sonner';
import { apicall, fmtCurrency, fmtDate, API } from '../utils';
import { StatusBadge } from '../components/StatusBadge';
import { STATUS_CONFIG } from '../constants';

export function AssetDetailDrawer({ asset: assetProp, token, open, onClose, onRefresh, onTransferClick, onRequestDisposalClick }) {
  const [detail, setDetail] = useState(assetProp);
  const [deprPeriod, setDeprPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [assignForm, setAssignForm] = useState({ user_id: '', user_name: '', notes: '' });
  const [maintForm, setMaintForm] = useState({ type: 'corrective', description: '', cost: '', performed_by: '', maintenance_date: new Date().toISOString().slice(0, 10), status: 'completed' });
  const [activeTab, setActiveTab] = useState('info');
  const [loading, setLoading] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [assignments, setAssignments] = useState([]);
  const [maintenance, setMaintenance] = useState([]);
  const photoInputRef = useRef(null);

  // Keep local `detail` in sync when the parent passes a new/updated asset object.
  useEffect(() => { setDetail(assetProp); }, [assetProp]);

  // On open (or asset change) load the full detail (nbv + depreciation_history) and sub-lists.
  useEffect(() => {
    if (!open || !assetProp?.id) return;
    apicall('GET', `/api/assets/${assetProp.id}`, token).then(d => { if (d?.id) setDetail(d); }).catch(() => {});
    apicall('GET', `/api/assets/${assetProp.id}/assignments`, token).then(d => setAssignments(Array.isArray(d) ? d : [])).catch(() => {});
    apicall('GET', `/api/assets/${assetProp.id}/maintenance`, token).then(d => setMaintenance(Array.isArray(d) ? d : [])).catch(() => {});
  }, [open, assetProp, token]);

  if (!assetProp && !detail) return null;

  // `asset` is the freshest known state (detail from GET /{id}, falling back to the list prop).
  const asset = detail || assetProp;

  // Re-fetch this asset's detail + assignments after a mutation so the drawer reflects changes live.
  const reloadDetail = async () => {
    if (!assetProp?.id) return;
    try {
      const [d, asg] = await Promise.all([
        apicall('GET', `/api/assets/${assetProp.id}`, token),
        apicall('GET', `/api/assets/${assetProp.id}/assignments`, token),
      ]);
      if (d?.id) setDetail(d);
      setAssignments(Array.isArray(asg) ? asg : []);
    } catch { /* noop */ }
  };

  const nbv = (asset.purchase_cost || 0) - (asset.accumulated_depreciation || 0);
  const deprPct = asset.purchase_cost > 0
    ? Math.min(100, Math.round(asset.accumulated_depreciation / asset.purchase_cost * 100))
    : 0;

  const handlePhotoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      toast.error('File harus berupa gambar');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.error('Ukuran foto maksimal 5 MB');
      return;
    }

    setUploadingPhoto(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API}/api/assets/${asset.id}/upload-photo`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) throw new Error('Upload gagal');

      await res.json();
      toast.success('Foto asset berhasil diupload');
      onRefresh();
    } catch {
      toast.error('Gagal upload foto');
    } finally {
      setUploadingPhoto(false);
      if (photoInputRef.current) photoInputRef.current.value = '';
    }
  };

  const postDepr = async () => {
    if (!deprPeriod) return;
    setLoading(true);
    try {
      const d = await apicall('POST', `/api/assets/${asset.id}/depreciate/${deprPeriod}`, token, {});
      if (d.id) {
        toast.success(`Depresiasi ${deprPeriod} diposting: ${d.amount?.toLocaleString('id-ID')}`);
        await reloadDetail(); onRefresh();
      } else toast.error(d.detail || 'Gagal posting depresiasi');
    } catch (e) { toast.error(e.message || 'Gagal'); }
    finally { setLoading(false); }
  };

  const assignAsset = async () => {
    if (!assignForm.user_id) { toast.error('User ID wajib diisi'); return; }
    setLoading(true);
    try {
      await apicall('POST', `/api/assets/${asset.id}/assign`, token, assignForm);
      toast.success('Aset berhasil ditugaskan');
      setAssignForm({ user_id: '', user_name: '', notes: '' });
      await reloadDetail(); onRefresh();
    } catch { toast.error('Gagal menugaskan aset'); }
    finally { setLoading(false); }
  };

  const addMaintenance = async () => {
    if (!maintForm.description) { toast.error('Deskripsi wajib diisi'); return; }
    setLoading(true);
    try {
      await apicall('POST', `/api/assets/${asset.id}/maintenance`, token, {
        ...maintForm, cost: Number(maintForm.cost) || 0,
      });
      toast.success('Pemeliharaan berhasil dicatat');
      const d = await apicall('GET', `/api/assets/${asset.id}/maintenance`, token);
      setMaintenance(Array.isArray(d) ? d : []);
      await reloadDetail();
      setMaintForm({ type: 'corrective', description: '', cost: '', performed_by: '', maintenance_date: new Date().toISOString().slice(0, 10), status: 'completed' });
    } catch { toast.error('Gagal'); }
    finally { setLoading(false); }
  };

  const disposeAsset = async () => {
    if (!window.confirm(`Yakin ingin melepas aset ${asset.asset_number}?`)) return;
    setLoading(true);
    try {
      const d = await apicall('POST', `/api/assets/${asset.id}/dispose`, token, { disposal_date: new Date().toISOString().slice(0,10), disposal_value: 0, reason: 'Disposal' });
      if (d.ok) { toast.success('Aset berhasil dilepas'); onRefresh(); onClose(); }
      else toast.error(d.detail || 'Gagal');
    } catch { toast.error('Gagal'); }
    finally { setLoading(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:w-[520px] overflow-y-auto" side="right">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Package size={16} />
            <span className="truncate">{asset.name}</span>
          </SheetTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-mono">{asset.asset_number}</span>
            <StatusBadge status={asset.status} configMap={STATUS_CONFIG} />
          </div>
        </SheetHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          <TabsList className="w-full">
            <TabsTrigger value="info" className="flex-1">Info</TabsTrigger>
            <TabsTrigger value="depr" className="flex-1">Depresiasi</TabsTrigger>
            <TabsTrigger value="assign" className="flex-1">Penugasan</TabsTrigger>
            <TabsTrigger value="maint" className="flex-1">Pemeliharaan</TabsTrigger>
          </TabsList>

          {/* Info Tab */}
          <TabsContent value="info" className="space-y-3 mt-3">
            {/* Photo Section */}
            <div className="bg-muted/40 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Foto Asset</p>
              {asset.photo_url ? (
                <div className="relative group">
                  <img
                    src={`${API}${asset.photo_url}`}
                    alt={asset.name}
                    className="w-full h-48 object-cover rounded-lg border"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => photoInputRef.current?.click()}
                    disabled={uploadingPhoto}>
                    <Edit size={14} className="mr-1" /> Ganti Foto
                  </Button>
                </div>
              ) : (
                <div className="border-2 border-dashed rounded-lg p-6 text-center">
                  <Package size={32} className="mx-auto text-muted-foreground/40 mb-2" />
                  <p className="text-xs text-muted-foreground mb-2">Belum ada foto</p>
                  <Button size="sm" variant="outline" onClick={() => photoInputRef.current?.click()} disabled={uploadingPhoto}>
                    {uploadingPhoto ? 'Uploading...' : 'Upload Foto'}
                  </Button>
                </div>
              )}
              <input
                type="file"
                ref={photoInputRef}
                onChange={handlePhotoUpload}
                accept="image/*"
                className="hidden"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              {[
                ['Kategori', asset.category_name], ['Lokasi', asset.location || '-'],
                ['Departemen', asset.department || '-'], ['No. Seri', asset.serial_number || '-'],
                ['Merek', asset.brand || '-'], ['Model', asset.model || '-'],
                ['Tgl Beli', fmtDate(asset.purchase_date)], ['Ditugaskan ke', asset.assigned_to_name || '-'],
              ].map(([k, v]) => (
                <div key={k} className="bg-muted/40 rounded-lg p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{k}</p>
                  <p className="text-sm font-medium mt-0.5 truncate">{v}</p>
                </div>
              ))}
            </div>
            <div className="bg-muted/40 rounded-lg p-3 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Harga Beli</span>
                <span className="font-semibold">{fmtCurrency(asset.purchase_cost)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Akum. Depresiasi</span>
                <span className="font-semibold text-amber-600">{fmtCurrency(asset.accumulated_depreciation)}</span>
              </div>
              <Separator />
              <div className="flex justify-between text-sm font-bold">
                <span>Nilai Buku (NBV)</span>
                <span className="text-emerald-600">{fmtCurrency(nbv)}</span>
              </div>
              <Progress value={deprPct} className="h-2" />
              <p className="text-xs text-muted-foreground text-right">{deprPct}% terdepresiasi</p>
            </div>

            {/* Barcode & QR Actions */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Label & Barcode</p>
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" size="sm" className="w-full" onClick={() => {
                  const url = `${API}/api/assets/${asset.id}/barcode`;
                  window.open(url, '_blank');
                }} data-testid="view-barcode-btn">
                  <Barcode size={14} className="mr-1" /> Lihat Barcode
                </Button>
                <Button variant="outline" size="sm" className="w-full" onClick={() => {
                  const url = `${API}/api/assets/${asset.id}/qrcode`;
                  window.open(url, '_blank');
                }} data-testid="view-qr-btn">
                  <QrCode size={14} className="mr-1" /> Lihat QR Code
                </Button>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                  const url = `${API}/api/assets/${asset.id}/label-pdf?template=standard`;
                  window.open(url, '_blank');
                }} data-testid="print-label-standard-btn">
                  <Printer size={14} className="mr-1" /> Label Standard (90x50mm)
                </Button>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                  const url = `${API}/api/assets/${asset.id}/label-pdf?template=sticker`;
                  window.open(url, '_blank');
                }}>
                  <Printer size={14} className="mr-1" /> Sticker Kecil (50x25mm)
                </Button>
                <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                  const url = `${API}/api/assets/${asset.id}/label-pdf?template=a4`;
                  window.open(url, '_blank');
                }}>
                  <Printer size={14} className="mr-1" /> A4 Full Page
                </Button>
              </div>
            </div>

            {asset.status !== 'disposed' && asset.status !== 'pending_disposal' && (
              <div className="space-y-2">
                <Button variant="outline" size="sm" className="w-full" onClick={() => {
                  if (onTransferClick) onTransferClick(asset);
                }} data-testid="transfer-asset-btn">
                  <ArrowRight size={14} className="mr-1" /> Transfer Asset
                </Button>
                {/* Disposal: high-value (NBV > 5jt) require approval, else direct */}
                {(() => {
                  const cost = parseFloat(asset.purchase_cost || 0);
                  const accum = parseFloat(asset.accumulated_depreciation || 0);
                  const _nbv = cost - accum;
                  const THRESHOLD = 5_000_000;
                  if (_nbv > THRESHOLD) {
                    return (
                      <Button variant="outline" size="sm" className="w-full border-amber-500/40 text-amber-600 hover:bg-amber-100 dark:bg-amber-500/10"
                        onClick={() => onRequestDisposalClick?.(asset)}
                        data-testid="request-disposal-btn">
                        ⚠️ Request Disposal (Perlu Approval)
                      </Button>
                    );
                  }
                  return (
                    <Button variant="destructive" size="sm" className="w-full" onClick={disposeAsset} disabled={loading}
                      data-testid="dispose-asset-btn">
                      <Trash2 size={14} className="mr-1" /> Lepas Aset (Dispose)
                    </Button>
                  );
                })()}
              </div>
            )}
            {asset.status === 'pending_disposal' && (
              <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 rounded-lg p-3 text-xs text-amber-700">
                <p className="font-semibold">⏳ Menunggu Approval Disposal</p>
                <p className="mt-0.5">Permintaan pelepasan aset sedang menunggu review dari Finance/Admin.</p>
              </div>
            )}

            {/* Warranty Section */}
            {(asset.warranty_expiry_date || asset.warranty_provider) && (
              <div className="bg-blue-100 dark:bg-blue-500/5 border border-blue-300 dark:border-blue-500/20 rounded-lg p-3 space-y-1.5">
                <p className="text-xs font-semibold text-blue-600 flex items-center gap-1.5">🛡️ Garansi</p>
                {asset.warranty_expiry_date && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Expired</span>
                    <span className={`font-medium ${
                      new Date(asset.warranty_expiry_date) < new Date() ? 'text-destructive' :
                      new Date(asset.warranty_expiry_date) < new Date(Date.now() + 30*86400000) ? 'text-amber-600' :
                      'text-foreground'
                    }`}>{fmtDate(asset.warranty_expiry_date)}
                      {new Date(asset.warranty_expiry_date) < new Date() ? ' ⚠️ EXPIRED' :
                       new Date(asset.warranty_expiry_date) < new Date(Date.now() + 30*86400000) ? ' ⏰ <30 hari' : ''}
                    </span>
                  </div>
                )}
                {asset.warranty_provider && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Provider</span>
                    <span className="font-medium">{asset.warranty_provider}</span>
                  </div>
                )}
                {asset.warranty_terms && (
                  <p className="text-xs text-muted-foreground">{asset.warranty_terms}</p>
                )}
              </div>
            )}

            {/* Insurance Section */}
            {(asset.insurance_policy_number || asset.insurance_provider) && (
              <div className="bg-emerald-100 dark:bg-emerald-500/5 border border-emerald-300 dark:border-emerald-500/20 rounded-lg p-3 space-y-1.5">
                <p className="text-xs font-semibold text-emerald-600 flex items-center gap-1.5">🔒 Asuransi</p>
                {asset.insurance_policy_number && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">No. Polis</span>
                    <span className="font-mono text-xs">{asset.insurance_policy_number}</span>
                  </div>
                )}
                {asset.insurance_provider && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Provider</span>
                    <span className="font-medium">{asset.insurance_provider}</span>
                  </div>
                )}
                {asset.insurance_expiry_date && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Expired</span>
                    <span className={`font-medium ${
                      new Date(asset.insurance_expiry_date) < new Date() ? 'text-destructive' :
                      new Date(asset.insurance_expiry_date) < new Date(Date.now() + 30*86400000) ? 'text-amber-600' :
                      'text-foreground'
                    }`}>{fmtDate(asset.insurance_expiry_date)}
                      {new Date(asset.insurance_expiry_date) < new Date() ? ' ⚠️ EXPIRED' :
                       new Date(asset.insurance_expiry_date) < new Date(Date.now() + 30*86400000) ? ' ⏰ <30 hari' : ''}
                    </span>
                  </div>
                )}
                {asset.insurance_value > 0 && (
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Nilai Pertanggungan</span>
                    <span className="font-medium">{fmtCurrency(asset.insurance_value)}</span>
                  </div>
                )}
              </div>
            )}
          </TabsContent>

          {/* Depreciation Tab */}
          <TabsContent value="depr" className="space-y-3 mt-3">
            <Card>
              <CardContent className="pt-4 space-y-3">
                <p className="text-sm font-medium">Posting Depresiasi Bulanan</p>
                <div className="flex gap-2">
                  <Input type="month" value={deprPeriod}
                    onChange={e => setDeprPeriod(e.target.value)} className="flex-1" />
                  <Button size="sm" onClick={postDepr} disabled={loading} data-testid="post-depr-btn">
                    Posting
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Depresiasi bulanan: <span className="font-semibold">{fmtCurrency(asset.monthly_depreciation)}</span>
                </p>
              </CardContent>
            </Card>
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Riwayat Depresiasi</p>
              {(asset.depreciation_history || []).length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">Belum ada posting depresiasi</p>
              ) : (
                <div className="space-y-1">
                  {(asset.depreciation_history || []).map(d => (
                    <div key={d.id} className="flex items-center justify-between py-2 px-3 bg-muted/40 rounded-lg text-sm">
                      <span className="font-mono text-xs">{d.period}</span>
                      <span className="text-amber-600">{fmtCurrency(d.amount)}</span>
                      <span className="text-xs text-muted-foreground">{fmtCurrency(d.cumulative)} total</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>

          {/* Assignment Tab */}
          <TabsContent value="assign" className="space-y-3 mt-3">
            {asset.assigned_to_id ? (
              <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-400 dark:border-emerald-500/30 rounded-lg p-3">
                <p className="text-xs text-emerald-600 font-medium">Sedang Ditugaskan</p>
                <p className="text-sm font-semibold">{asset.assigned_to_name}</p>
                <Button variant="outline" size="sm" className="mt-2" onClick={async () => {
                  await apicall('POST', `/api/assets/${asset.id}/unassign`, token, {});
                  toast.success('Aset dikembalikan'); await reloadDetail(); onRefresh();
                }} data-testid="unassign-asset-btn">Kembalikan Aset</Button>
              </div>
            ) : (
              <Card>
                <CardContent className="pt-4 space-y-2">
                  <p className="text-sm font-medium">Tugaskan ke Karyawan</p>
                  <Input placeholder="ID Karyawan" data-testid="assign-user-id" value={assignForm.user_id}
                    onChange={e => setAssignForm(p => ({ ...p, user_id: e.target.value }))} />
                  <Input placeholder="Nama Karyawan" data-testid="assign-user-name" value={assignForm.user_name}
                    onChange={e => setAssignForm(p => ({ ...p, user_name: e.target.value }))} />
                  <Input placeholder="Catatan (opsional)" value={assignForm.notes}
                    onChange={e => setAssignForm(p => ({ ...p, notes: e.target.value }))} />
                  <Button size="sm" className="w-full" onClick={assignAsset} disabled={loading} data-testid="assign-submit-btn">Tugaskan</Button>
                </CardContent>
              </Card>
            )}
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Riwayat Penugasan</p>
              <div className="space-y-1">
                {assignments.map(a => (
                  <div key={a.id} className="flex items-center justify-between py-2 px-3 bg-muted/40 rounded-lg text-sm">
                    <span>{a.assigned_to_name}</span>
                    <span className="text-xs text-muted-foreground">{fmtDate(a.assigned_date)}{a.returned_date ? ` – ${fmtDate(a.returned_date)}` : ' (aktif)'}</span>
                  </div>
                ))}
                {assignments.length === 0 && <p className="text-xs text-muted-foreground text-center py-3">Belum pernah ditugaskan</p>}
              </div>
            </div>
          </TabsContent>

          {/* Maintenance Tab */}
          <TabsContent value="maint" className="space-y-3 mt-3">
            <Card>
              <CardContent className="pt-4 space-y-2">
                <p className="text-sm font-medium">Catat Pemeliharaan</p>
                <Select value={maintForm.type} onValueChange={v => setMaintForm(p => ({ ...p, type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="scheduled">Terjadwal</SelectItem>
                    <SelectItem value="corrective">Korektif</SelectItem>
                    <SelectItem value="preventive">Preventif</SelectItem>
                  </SelectContent>
                </Select>
                <Input placeholder="Deskripsi pemeliharaan..." value={maintForm.description}
                  onChange={e => setMaintForm(p => ({ ...p, description: e.target.value }))} />
                <Input type="number" placeholder="Biaya (Rp)" value={maintForm.cost}
                  onChange={e => setMaintForm(p => ({ ...p, cost: e.target.value }))} />
                <Input placeholder="Dilakukan oleh" value={maintForm.performed_by}
                  onChange={e => setMaintForm(p => ({ ...p, performed_by: e.target.value }))} />
                <Input type="date" value={maintForm.maintenance_date}
                  onChange={e => setMaintForm(p => ({ ...p, maintenance_date: e.target.value }))} />
                <Select value={maintForm.status} onValueChange={v => setMaintForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="completed">Selesai</SelectItem>
                    <SelectItem value="in_progress">Sedang Berjalan</SelectItem>
                    <SelectItem value="scheduled">Terjadwal</SelectItem>
                  </SelectContent>
                </Select>
                <Button size="sm" className="w-full" onClick={addMaintenance} disabled={loading}>Simpan Pemeliharaan</Button>
              </CardContent>
            </Card>
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Riwayat</p>
              <div className="space-y-1">
                {maintenance.map(m => (
                  <div key={m.id} className="py-2 px-3 bg-muted/40 rounded-lg">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{m.description}</span>
                      <span className="text-xs text-muted-foreground">{fmtDate(m.maintenance_date)}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground">{m.type}</span>
                      {m.cost > 0 && <span className="text-xs text-amber-600">{fmtCurrency(m.cost)}</span>}
                    </div>
                  </div>
                ))}
                {maintenance.length === 0 && <p className="text-xs text-muted-foreground text-center py-3">Belum ada riwayat pemeliharaan</p>}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
