import { useState, useEffect, useCallback, useMemo } from 'react';
import { Users, Plus, Star, Edit2, Eye, RefreshCw, Phone, Mail, MapPin, Ban, CheckCircle2, KeyRound, Copy, ShieldCheck } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { EmptyState } from './EmptyState';
import ImportExportToolbar from './ImportExportToolbar';

const PRODUCT_SPECIALIZATIONS = ['Rok', 'Blouse', 'Dress', 'Celana', 'Set/Setelan', 'Baju Anak', 'Hijab', 'Aksesoris', 'Lainnya'];

export default function MaklonClientManagement({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [clientDialog, setClientDialog] = useState(null);
  const [viewDialog, setViewDialog] = useState(null);
  const [portalDialog, setPortalDialog] = useState(null);

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const url = filterStatus === 'all' ? '/api/dewi/maklon/clients' : `/api/dewi/maklon/clients?status=${filterStatus}`;
      const r = await fetch(url, { headers });
      if (r.ok) setClients(await r.json());
    } catch(e) { toast.error('Gagal memuat data klien'); }
    finally { setLoading(false); }
  }, [headers, filterStatus]);

  useEffect(() => { fetchClients(); }, [fetchClients]);

  const toggleClient = async (client) => {
    const r = await fetch(`/api/dewi/maklon/clients/${client.id}/toggle`, { method: 'PUT', headers });
    if (r.ok) { toast.success(`Klien ${client.name} ${client.status === 'active' ? 'dinonaktifkan' : 'diaktifkan'}`); fetchClients(); }
    else toast.error('Gagal mengubah status');
  };

  const filteredClients = clients;

  return (
    <div className="p-6 space-y-6" data-testid="maklon-clients">
      <PageHeader
        title="Master Klien Maklon"
        description="Database klien jasa maklon, kontrak, dan riwayat kerjasama"
        icon={Users}
        actions={
          <div className="flex gap-2">
            <ImportExportToolbar collectionKey="maklon_clients" label="Klien Maklon" onImported={fetchClients} />
            <Button size="sm" onClick={fetchClients} variant="outline" className="gap-2">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button size="sm" onClick={() => setClientDialog({})} className="gap-1.5">
              <Plus className="w-3.5 h-3.5" /> Tambah Klien
            </Button>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Klien', value: clients.length, color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-400/20', icon: Users },
          { label: 'Aktif', value: clients.filter(c => c.status === 'active').length, color: 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border-green-300 dark:border-green-400/20', icon: CheckCircle2 },
          { label: 'Non-Aktif', value: clients.filter(c => c.status === 'inactive').length, color: 'text-orange-400 bg-orange-500/10 border-orange-400/20', icon: Ban },
        ].map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
            <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
              <div className={`w-8 h-8 rounded-lg border ${s.color} flex items-center justify-center mb-2`}>
                <s.icon className={`w-4 h-4 ${s.color.split(' ')[0]}`} />
              </div>
              <div className="text-2xl font-bold text-foreground">{s.value}</div>
              <div className="text-xs text-foreground/50">{s.label}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {['all', 'active', 'inactive'].map(s => (
          <Button
            key={s}
            size="sm"
            variant={filterStatus === s ? 'default' : 'outline'}
            onClick={() => setFilterStatus(s)}
          >
            {s === 'all' ? 'Semua' : s === 'active' ? 'Aktif' : 'Non-Aktif'}
          </Button>
        ))}
      </div>

      {/* Client Cards */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-2 text-center py-10 text-foreground/40 text-sm">Memuat...</div>
        ) : filteredClients.length === 0 ? (
          <div className="col-span-2">
            <EmptyState
              icon={Users}
              title="Belum ada klien terdaftar"
              description="Tambahkan klien maklon pertama untuk mulai melacak kontrak dan pengiriman."
            />
          </div>
        ) : (
          filteredClients.map(c => (
            <GlassCard key={c.id} className={`p-4 border transition-all ${c.status === 'active' ? 'border-foreground/[0.08] hover:border-foreground/[0.15]' : 'border-foreground/5 opacity-60'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-foreground">{c.name}</span>
                    <span className="text-[10px] bg-foreground/[0.08] px-1.5 py-0.5 rounded text-foreground/50 font-mono">{c.code}</span>
                    {c.status === 'inactive' && <span className="text-[10px] bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400 px-1.5 py-0.5 rounded border border-red-400 dark:border-red-400/25">Nonaktif</span>}
                  </div>
                  <div className="space-y-1 text-xs text-foreground/50">
                    {c.pic_name && <div className="flex items-center gap-1"><span className="text-foreground/70">{c.pic_name}</span></div>}
                    {c.pic_phone && <div className="flex items-center gap-1"><Phone className="w-3 h-3" />{c.pic_phone}</div>}
                    {c.city && <div className="flex items-center gap-1"><MapPin className="w-3 h-3" />{c.city}</div>}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs text-foreground/60"><strong className="text-foreground">Rp {(c.standard_rate_per_pcs || 0).toLocaleString('id-ID')}</strong>/pcs</span>
                    <span className="text-xs text-foreground/40">•</span>
                    <span className="text-xs text-foreground/40">{c.payment_terms || 'net_30'}</span>
                  </div>
                  {(c.product_specialization || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {c.product_specialization.slice(0,3).map(s => <span key={s} className="text-[10px] bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 px-1.5 py-0.5 rounded border border-violet-400 dark:border-violet-400/25">{s}</span>)}
                      {c.product_specialization.length > 3 && <span className="text-[10px] text-foreground/40">+{c.product_specialization.length-3}</span>}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <div className="flex items-center gap-0.5">
                    {[1,2,3,4,5].map(n => <Star key={n} className={`w-3 h-3 ${n <= Math.round(c.rating||0) ? 'text-amber-700 dark:text-amber-400 fill-amber-400' : 'text-foreground/20'}`} />)}
                  </div>
                  <div className="flex gap-1 mt-1">
                    <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setViewDialog(c)} data-testid={`maklon-client-view-${c.id}`}><Eye className="w-3.5 h-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setClientDialog({ data: c })} data-testid={`maklon-client-edit-${c.id}`}><Edit2 className="w-3.5 h-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="w-7 h-7 text-violet-600 dark:text-violet-300 hover:bg-violet-100 dark:bg-violet-500/15" onClick={() => setPortalDialog(c)} title="Akses Portal Klien" data-testid={`maklon-client-portal-${c.id}`}><KeyRound className="w-3.5 h-3.5" /></Button>
                    <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => toggleClient(c)}>{c.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}</Button>
                  </div>
                </div>
              </div>
            </GlassCard>
          ))
        )}
      </div>

      {/* Dialogs */}
      {clientDialog !== null && (
        <ClientDialog data={clientDialog?.data || null} headers={headers} onClose={() => setClientDialog(null)} onSuccess={() => { setClientDialog(null); fetchClients(); }} />
      )}
      {viewDialog && <ViewClientDialog client={viewDialog} onClose={() => setViewDialog(null)} />}
      {portalDialog && <PortalAccessDialog client={portalDialog} headers={headers} onClose={() => setPortalDialog(null)} />}
    </div>
  );
}

// Portal Access Management Dialog (Phase 4)
function PortalAccessDialog({ client, headers, onClose }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [provisionMode, setProvisionMode] = useState(false);
  const [email, setEmail] = useState(client.pic_email || '');
  const [picName, setPicName] = useState(client.pic_name || '');
  const [credential, setCredential] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/dewi/maklon/clients/${client.id}/portal-status`, { headers });
      if (r.ok) {
        const d = await r.json();
        setAccounts(d.accounts || []);
      }
    } finally {
      setLoading(false);
    }
  }, [client.id, headers]);

  useEffect(() => { load(); }, [load]);

  const provision = async () => {
    if (!email) { toast.error('Email wajib diisi'); return; }
    setSubmitting(true);
    try {
      const r = await fetch(`/api/dewi/maklon/clients/${client.id}/provision-portal`, {
        method: 'POST', headers, body: JSON.stringify({ email, name: picName }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      setCredential({ email: d.email, password: d.password });
      toast.success('Akun portal klien dibuat');
      setProvisionMode(false);
      load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const reset = async (acc) => {
    if (!window.confirm(`Reset password untuk ${acc.email}?`)) return;
    try {
      const r = await fetch(`/api/dewi/maklon/clients/${client.id}/portal-accounts/${acc.id}/reset-password`, {
        method: 'POST', headers, body: JSON.stringify({}),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      setCredential({ email: d.email, password: d.password });
      toast.success('Password direset');
    } catch (e) {
      toast.error(e.message);
    }
  };

  const toggle = async (acc) => {
    try {
      const r = await fetch(`/api/dewi/maklon/clients/${client.id}/portal-accounts/${acc.id}/toggle`, {
        method: 'POST', headers,
      });
      if (!r.ok) throw new Error('Gagal');
      toast.success('Status akun diubah');
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const removeAccount = async (acc) => {
    if (!window.confirm(`Hapus akun portal ${acc.email}?`)) return;
    try {
      const r = await fetch(`/api/dewi/maklon/clients/${client.id}/portal-accounts/${acc.id}`, {
        method: 'DELETE', headers,
      });
      if (!r.ok) throw new Error('Gagal');
      toast.success('Akun dihapus');
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast.success('Disalin'); } catch (e) {}
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-xl" data-testid="maklon-portal-access-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Akses Portal Klien — {client.name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-2 text-sm">
          <div className="rounded-lg border border-violet-400 dark:border-violet-400/25 bg-violet-50 dark:bg-violet-500/5 p-3 text-xs text-foreground/75">
            <div className="font-medium text-violet-600 dark:text-violet-300 mb-1">Portal Klien Maklon (Phase 4)</div>
            Klien dapat login di <code className="font-mono text-violet-600 dark:text-violet-300">/client</code> untuk melihat status order, approve sample, dan invoice secara mandiri.
          </div>

          {credential && (
            <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/5 p-3 space-y-2">
              <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-300 text-xs font-medium">
                <ShieldCheck className="w-3.5 h-3.5" /> Kredensial Sekali Tampil — Catat Sekarang
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-foreground/55 text-xs w-16">Email:</span>
                  <code className="font-mono text-xs text-foreground flex-1">{credential.email}</code>
                  <Button size="icon" variant="ghost" className="w-6 h-6" onClick={() => copy(credential.email)}><Copy className="w-3 h-3" /></Button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-foreground/55 text-xs w-16">Password:</span>
                  <code className="font-mono text-xs text-foreground flex-1">{credential.password}</code>
                  <Button size="icon" variant="ghost" className="w-6 h-6" onClick={() => copy(credential.password)}><Copy className="w-3 h-3" /></Button>
                </div>
              </div>
              <div className="text-[11px] text-foreground/55">Klien wajib mengganti password saat login pertama.</div>
            </div>
          )}

          {loading ? (
            <div className="text-foreground/40 text-xs py-4 text-center">Memuat akun...</div>
          ) : accounts.length === 0 && !provisionMode ? (
            <div className="rounded-lg border border-dashed border-foreground/10 p-6 text-center">
              <KeyRound className="w-8 h-8 mx-auto text-foreground/30 mb-2" />
              <div className="text-foreground/55 text-sm mb-3">Belum ada akun portal untuk klien ini.</div>
              <Button size="sm" onClick={() => setProvisionMode(true)} data-testid="maklon-portal-provision-btn">
                <Plus className="w-3.5 h-3.5 mr-1.5" /> Buat Akun Portal
              </Button>
            </div>          ) : (
            <div className="space-y-2">
              {accounts.map((acc) => (
                <div key={acc.id} className="rounded-lg border border-foreground/[0.08] p-3 flex items-center justify-between gap-2" data-testid={`maklon-portal-account-${acc.id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-foreground text-sm truncate">{acc.email}</div>
                    <div className="text-xs text-foreground/55 flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${acc.status === 'active' ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-600 dark:text-red-300'}`}>{acc.status}</span>
                      {acc.must_change_password && <span className="text-[10px] text-amber-700 dark:text-amber-400">Wajib ganti pwd</span>}
                      {acc.last_login_at && <span className="text-[10px] text-foreground/40">Login terakhir: {new Date(acc.last_login_at).toLocaleDateString('id-ID')}</span>}
                    </div>
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => reset(acc)} data-testid={`maklon-portal-reset-${acc.id}`}>Reset Pwd</Button>
                    <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => toggle(acc)}>{acc.status === 'active' ? 'Nonaktif' : 'Aktif'}</Button>
                    <Button size="icon" variant="ghost" className="w-7 h-7 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/15" onClick={() => removeAccount(acc)}><Ban className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>
              ))}
              {!provisionMode && (
                <Button size="sm" variant="outline" onClick={() => setProvisionMode(true)} className="w-full"><Plus className="w-3.5 h-3.5 mr-1.5" /> Tambah Akun Lain</Button>
              )}
            </div>
          )}

          {provisionMode && (
            <div className="rounded-lg border border-violet-400 dark:border-violet-400/25 bg-violet-50 dark:bg-violet-500/5 p-3 space-y-2">
              <div className="text-xs font-medium text-violet-600 dark:text-violet-300">Buat Akun Portal Baru</div>
              <div className="space-y-1.5">
                <Label className="text-xs">Email Login *</Label>
                <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="klien@perusahaan.id" data-testid="maklon-portal-email-input" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Nama PIC (opsional)</Label>
                <Input value={picName} onChange={(e) => setPicName(e.target.value)} />
              </div>
              <div className="text-[11px] text-foreground/55">Password akan di-generate otomatis dan ditampilkan setelah submit.</div>
              <div className="flex gap-2 justify-end pt-1">
                <Button size="sm" variant="ghost" onClick={() => setProvisionMode(false)}>Batal</Button>
                <Button size="sm" onClick={provision} disabled={submitting} data-testid="maklon-portal-provision-submit">
                  {submitting ? 'Membuat...' : 'Buat Akun'}
                </Button>
              </div>
            </div>
          )}
        </div>

        <DialogFooter><Button variant="outline" onClick={onClose}>Tutup</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Client Form Dialog
function ClientDialog({ data, headers, onClose, onSuccess }) {
  const isEdit = !!data;
  const [form, setForm] = useState(data || {
    code: '', name: '', pic_name: '', pic_phone: '', pic_email: '', address: '', city: 'Sragen',
    contract_type: 'per_order', standard_rate_per_pcs: '', payment_terms: 'net_30',
    product_specialization: [], quality_standard: 'standard', notes: ''
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  const toggleSpec = (s) => setForm(p => ({ ...p, product_specialization: p.product_specialization.includes(s) ? p.product_specialization.filter(x => x !== s) : [...p.product_specialization, s] }));

  const save = async () => {
    if (!form.code || !form.name) { toast.error('Kode dan nama klien wajib diisi'); return; }
    setSaving(true);
    const url = isEdit ? `/api/dewi/maklon/clients/${data.id}` : '/api/dewi/maklon/clients';
    const method = isEdit ? 'PUT' : 'POST';
    const r = await fetch(url, { method, headers, body: JSON.stringify({ ...form, standard_rate_per_pcs: Number(form.standard_rate_per_pcs || 0) }) });
    setSaving(false);
    if (r.ok) { toast.success(isEdit ? 'Klien diperbarui' : 'Klien ditambahkan'); onSuccess(); }
    else { const e = await r.json(); toast.error(e.detail || 'Gagal menyimpan'); }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{isEdit ? `Edit Klien: ${data.name}` : 'Tambah Klien Baru'}</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>Kode Klien *</Label><Input value={form.code} onChange={e => set('code', e.target.value)} placeholder="CLT001" /></div>
            <div className="space-y-1 col-span-2"><Label>Nama Perusahaan/Brand *</Label><Input value={form.name} onChange={e => set('name', e.target.value)} /></div>
            <div className="space-y-1"><Label>Nama PIC</Label><Input value={form.pic_name} onChange={e => set('pic_name', e.target.value)} /></div>
            <div className="space-y-1"><Label>No. HP PIC</Label><Input value={form.pic_phone} onChange={e => set('pic_phone', e.target.value)} /></div>
            <div className="space-y-1 col-span-2"><Label>Email PIC</Label><Input type="email" value={form.pic_email} onChange={e => set('pic_email', e.target.value)} /></div>
            <div className="space-y-1 col-span-2"><Label>Alamat</Label><Input value={form.address} onChange={e => set('address', e.target.value)} /></div>
            <div className="space-y-1"><Label>Kota</Label><Input value={form.city} onChange={e => set('city', e.target.value)} /></div>
            <div className="space-y-1"><Label>Rate Standar (Rp/pcs)</Label><Input type="number" value={form.standard_rate_per_pcs} onChange={e => set('standard_rate_per_pcs', e.target.value)} /></div>
            <div className="space-y-1"><Label>Payment Terms</Label><Select value={form.payment_terms} onValueChange={v => set('payment_terms', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="net_7">Net 7</SelectItem><SelectItem value="net_14">Net 14</SelectItem><SelectItem value="net_30">Net 30</SelectItem><SelectItem value="net_60">Net 60</SelectItem></SelectContent></Select></div>
            <div className="space-y-1"><Label>Quality Standard</Label><Select value={form.quality_standard} onValueChange={v => set('quality_standard', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="standard">Standard</SelectItem><SelectItem value="premium">Premium</SelectItem><SelectItem value="luxury">Luxury</SelectItem></SelectContent></Select></div>
          </div>
          <div className="space-y-1"><Label>Spesialisasi Produk</Label><div className="flex flex-wrap gap-1.5 pt-1">{PRODUCT_SPECIALIZATIONS.map(s => <button key={s} onClick={() => toggleSpec(s)} className={`text-xs px-2.5 py-1 rounded-full border transition-all ${form.product_specialization.includes(s) ? 'bg-violet-500/20 border-violet-500 dark:border-violet-400/40 text-violet-600 dark:text-violet-300' : 'bg-foreground/5 border-foreground/10 text-foreground/60 hover:border-foreground/25'}`}>{s}</button>)}</div></div>
          <div className="space-y-1"><Label>Catatan</Label><Textarea value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} /></div>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Batal</Button><Button onClick={save} disabled={saving}>{saving ? 'Menyimpan...' : (isEdit ? 'Simpan' : 'Tambah Klien')}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// View Client Detail Dialog
function ViewClientDialog({ client, onClose }) {
  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Detail Klien: {client.name}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2 text-sm">
          <InfoRow label="Kode" value={client.code} />
          <InfoRow label="Nama" value={client.name} />
          <InfoRow label="PIC" value={client.pic_name} />
          <InfoRow label="No. HP" value={client.pic_phone} />
          <InfoRow label="Email" value={client.pic_email} />
          <InfoRow label="Alamat" value={client.address} />
          <InfoRow label="Kota" value={client.city} />
          <InfoRow label="Rate Standar" value={`Rp ${(client.standard_rate_per_pcs || 0).toLocaleString('id-ID')}/pcs`} />
          <InfoRow label="Payment Terms" value={client.payment_terms} />
          <InfoRow label="Quality Standard" value={client.quality_standard} />
          <InfoRow label="Rating" value={`${client.rating || 0}/5`} />
          <InfoRow label="Status" value={<span className={`px-2 py-0.5 rounded text-xs ${client.status === 'active' ? 'bg-green-100 dark:bg-green-500/15 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400'}`}>{client.status === 'active' ? 'Aktif' : 'Non-Aktif'}</span>} />
          {(client.product_specialization || []).length > 0 && <InfoRow label="Spesialisasi" value={(client.product_specialization || []).join(', ')} />}
          <InfoRow label="Catatan" value={client.notes} />
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Tutup</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InfoRow({ label, value }) {
  if (!value && value !== 0) return null;
  return <div className="flex gap-3"><span className="text-foreground/50 shrink-0 w-32">{label}:</span><span className="text-foreground/80">{value}</span></div>;
}
