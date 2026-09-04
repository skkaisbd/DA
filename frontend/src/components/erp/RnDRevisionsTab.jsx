import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GitBranch, Plus, Trash2, Search, GitCompare } from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import RnDRevisionCompare from './RnDRevisionCompare';

const API = process.env.REACT_APP_BACKEND_URL || '';

const TYPE_CONF = {
  'design':    { label: 'Desain',      cls: 'bg-violet-500/20 text-violet-400 border-violet-500/30' },
  'material':  { label: 'Material',    cls: 'bg-amber-500/20  text-amber-400  border-amber-500/30'  },
  'fit':       { label: 'Fit',         cls: 'bg-sky-500/20    text-sky-400    border-sky-500/30'    },
  'costing':   { label: 'Costing',     cls: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
  'other':     { label: 'Lainnya',     cls: 'bg-muted/20   text-muted-foreground   border-border/30'   },
};

const emptyForm = {
  style_id: '', style_code: '', style_name: '',
  revision_name: '',
  revision_type: 'design',
  changes_summary: '',
  old_value: '',
  new_value: '',
  notes: '',
};

export default function RnDRevisionsTab({ token }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const [revisions, setRevisions] = useState([]);
  const [styles,    setStyles]    = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [search,    setSearch]    = useState('');
  const [filterStyle, setFilterStyle] = useState('');
  const [showForm,  setShowForm]  = useState(false);
  const [form,      setForm]      = useState({ ...emptyForm });
  const [delId,     setDelId]     = useState(null);
  const [compare,   setCompare]   = useState(null); // {styleId, left}

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const fetchRevisions = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStyle) qs.set('style_id', filterStyle);
      const res = await fetch(`${API}/api/dewi/rnd/revisions${qs.toString() ? '?' + qs : ''}`, { headers: h });
      if (res.ok) setRevisions(await res.json());
    } catch { toast.error('Gagal memuat revisi'); }
    finally { setLoading(false); }
  };

  const fetchStyles = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles`, { headers: h });
      if (res.ok) setStyles(await res.json());
    } catch { /* ignore */ }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchRevisions(); }, [filterStyle]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchStyles(); }, []);

  const setStyleField = sid => {
    const sel = styles.find(s => s.id === sid);
    setForm(p => ({ ...p, style_id: sid, style_code: sel?.style_code || '', style_name: sel?.style_name || '' }));
  };

  const handleSave = async () => {
    if (!form.style_id) return toast.error('Pilih style terlebih dahulu');
    if (!form.revision_name.trim()) return toast.error('Nama revisi wajib diisi');
    try {
      await fetch(`${API}/api/dewi/rnd/revisions`, {
        method: 'POST', headers: h, body: JSON.stringify(form),
      });
      toast.success('Revisi berhasil ditambahkan');
      setShowForm(false);
      setForm({ ...emptyForm });
      fetchRevisions();
    } catch { toast.error('Gagal menyimpan revisi'); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/rnd/revisions/${delId}`, { method: 'DELETE', headers: h });
      toast.success('Revisi dihapus');
      setDelId(null);
      fetchRevisions();
    } catch { toast.error('Gagal menghapus'); }
  };

  const filtered = revisions.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.style_code || '').toLowerCase().includes(q)
      || (r.revision_name || '').toLowerCase().includes(q)
      || (r.changes_summary || '').toLowerCase().includes(q);
  });

  return (
    <div className="p-6 space-y-5" data-testid="rnd-revisions-tab">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-violet-500" /> Revisi & Approval
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">Tracking riwayat perubahan design</p>
        </div>
        <Button onClick={() => { setForm({ ...emptyForm }); setShowForm(true); }}
          className="gap-2" data-testid="create-revision-btn">
          <Plus className="w-4 h-4" /> Tambah Revisi
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari revisi..." className="pl-9" />
        </div>
        <SmartNativeSelect value={filterStyle} onChange={e => setFilterStyle(e.target.value)}
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[200px]">
          <option value="">Semua Style</option>
          {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
        </SmartNativeSelect>
        <Button variant="outline" className="gap-2" disabled={!filterStyle}
          title={filterStyle ? 'Bandingkan dua revisi style ini' : 'Pilih satu style dulu'}
          onClick={() => setCompare({ styleId: filterStyle, left: '' })}
          data-testid="compare-revisions-btn">
          <GitCompare className="w-4 h-4" /> Bandingkan Revisi
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <GitBranch className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada revisi.</p>
          <Button variant="outline" className="mt-3" onClick={() => setShowForm(true)}>+ Catat Revisi Pertama</Button>
        </GlassCard>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-6 top-0 bottom-0 w-px bg-violet-500/20" />
          <div className="space-y-4">
            {filtered.map((r, idx) => {
              const tc = TYPE_CONF[r.revision_type] || TYPE_CONF.other;
              return (
                <div key={r.id} className="relative pl-14">
                  {/* Timeline dot */}
                  <div className="absolute left-4 top-4 w-4 h-4 rounded-full bg-violet-500/30 border-2 border-violet-500 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500" />
                  </div>
                  <GlassCard className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-foreground text-sm">{r.revision_name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${tc.cls}`}>{tc.label}</span>
                          <span className="text-xs text-foreground/40 font-mono">#{r.revision_number}</span>
                        </div>
                        <div className="text-xs text-foreground/50">
                          {r.style_code} · {r.created_by_name} · {new Date(r.created_at).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </div>
                        {r.changes_summary && <p className="text-sm text-foreground/70 mt-2">{r.changes_summary}</p>}
                        {(r.old_value || r.new_value) && (
                          <div className="flex gap-3 mt-2">
                            {r.old_value && (
                              <div className="text-xs bg-red-500/10 border border-red-500/20 rounded px-2 py-1 text-red-400">
                                Sebelum: {r.old_value}
                              </div>
                            )}
                            {r.new_value && (
                              <div className="text-xs bg-emerald-500/10 border border-emerald-500/20 rounded px-2 py-1 text-emerald-400">
                                Sesudah: {r.new_value}
                              </div>
                            )}
                          </div>
                        )}
                        {r.notes && <p className="text-xs text-foreground/40 italic mt-2">{r.notes}</p>}
                      </div>
                      <div className="flex items-center gap-1 ml-3">
                        <Button variant="ghost" size="sm"
                          onClick={() => setCompare({ styleId: r.style_id, left: r.id })}
                          data-testid={`compare-revision-${r.id}`}
                          title="Bandingkan revisi ini dengan versi lain"
                          className="h-7 px-2 text-xs gap-1">
                          <GitCompare className="w-3.5 h-3.5" /> Bandingkan
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setDelId(r.id)}
                          className="h-7 w-7 p-0 text-red-500 hover:bg-red-500/10">
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>
                  </GlassCard>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Create Form Modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)} title="Catat Revisi Baru">
        <div className="space-y-4">
          <div>
            <Label>Style <span className="text-red-400">*</span></Label>
            <SmartNativeSelect value={form.style_id} onChange={e => setStyleField(e.target.value)}
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
              <option value="">-- Pilih Style --</option>
              {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Nama Revisi <span className="text-red-400">*</span></Label>
              <Input className="mt-1" value={form.revision_name}
                onChange={e => f('revision_name', e.target.value)}
                placeholder="Contoh: Ubah kancing depan" />
            </div>
            <div>
              <Label>Tipe Revisi</Label>
              <SmartNativeSelect value={form.revision_type} onChange={e => f('revision_type', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                {Object.entries(TYPE_CONF).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </SmartNativeSelect>
            </div>
          </div>
          <div>
            <Label>Ringkasan Perubahan</Label>
            <textarea value={form.changes_summary} onChange={e => f('changes_summary', e.target.value)}
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-20 resize-none"
              placeholder="Jelaskan apa yang berubah..." />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Nilai Sebelumnya</Label>
              <Input className="mt-1" value={form.old_value}
                onChange={e => f('old_value', e.target.value)} placeholder="Kondisi lama" />
            </div>
            <div>
              <Label>Nilai Baru</Label>
              <Input className="mt-1" value={form.new_value}
                onChange={e => f('new_value', e.target.value)} placeholder="Kondisi baru" />
            </div>
          </div>
          <div>
            <Label>Catatan Tambahan</Label>
            <Input className="mt-1" value={form.notes} onChange={e => f('notes', e.target.value)} />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button onClick={handleSave} data-testid="save-revision-btn">Simpan Revisi</Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus Revisi?"
          message="Data revisi akan dihapus permanen."
        />
      )}

      {compare && (
        <RnDRevisionCompare
          token={token}
          styleId={compare.styleId}
          initialLeft={compare.left}
          onClose={() => setCompare(null)}
        />
      )}
    </div>
  );
}
