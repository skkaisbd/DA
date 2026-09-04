/**
 * Modal dialogs for the Communication Hub: create-channel and start-DM.
 * Both are small enough to share a single file.
 */
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';

import { apicall, initials, avatarColor } from './utils';

export function CreateChannelDialog({ open, onClose, token, onCreated }) {
  const [form, setForm] = useState({ name: '', description: '', type: 'public' });
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!form.name.trim()) {
      toast.error('Nama channel wajib diisi');
      return;
    }
    setLoading(true);
    try {
      const data = await apicall('POST', '/api/comm/channels', token, form);
      if (data.id) {
        toast.success(`Channel #${data.name} dibuat`);
        onCreated(data);
        onClose();
      } else {
        toast.error(data.detail || 'Gagal membuat channel');
      }
    } catch {
      toast.error('Gagal membuat channel');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Buat Channel Baru</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Nama Channel</label>
            <Input
              placeholder="e.g. umum, produksi, keuangan"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              data-testid="channel-name-input"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Deskripsi (opsional)</label>
            <Input
              placeholder="Deskripsi singkat..."
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Tipe</label>
            <Select value={form.type} onValueChange={(v) => setForm((p) => ({ ...p, type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Publik (semua anggota)</SelectItem>
                <SelectItem value="private">Privat (anggota pilihan)</SelectItem>
                <SelectItem value="department">Departemen</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={loading} data-testid="create-channel-submit">
            {loading ? 'Membuat...' : 'Buat Channel'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function NewDMDialog({ open, onClose, token, currentUserId, onStartDM }) {
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!open) return;
    apicall('GET', '/api/auth/users?limit=100', token)
      .then((d) => setUsers(Array.isArray(d) ? d.filter((u) => u.id !== currentUserId) : []))
      .catch(() => {});
  }, [open, token, currentUserId]);

  const filtered = users.filter(
    (u) =>
      u.name?.toLowerCase().includes(search.toLowerCase()) ||
      u.email?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Pesan Langsung</DialogTitle></DialogHeader>
        <Input
          placeholder="Cari pengguna..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-2"
        />
        <ScrollArea className="h-56">
          <div className="space-y-1">
            {filtered.map((u) => (
              <button
                key={u.id}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/60 text-left transition-colors"
                onClick={() => { onStartDM(u); onClose(); }}
              >
                <div className={`w-8 h-8 rounded-full ${avatarColor(u.id)} flex items-center justify-center text-xs font-bold text-foreground shrink-0`}>
                  {initials(u.name)}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{u.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-4">
                Tidak ada pengguna ditemukan
              </p>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
