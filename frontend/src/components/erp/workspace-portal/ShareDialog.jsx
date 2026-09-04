/**
 * ShareDialog — grant/revoke access to a Workspace document.
 *
 * Search users (300 ms debounce) → grant view/edit → list current shares with
 * inline access change + revoke.
 */
import { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Share2, Search, Loader2, Eye, Pencil, Crown, X,
} from 'lucide-react';

import { apicall } from './utils';

export default function ShareDialog({ open, onClose, document: doc, token, onShared }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [shares, setShares] = useState([]);
  const [busy, setBusy] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (open && doc) {
      setShares(doc.permissions?.shared_with || []);
      setSearch('');
      setResults([]);
    }
  }, [open, doc]);

  const handleSearch = (q) => {
    setSearch(q);
    clearTimeout(timerRef.current);
    if (!q.trim()) { setResults([]); return; }
    timerRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await apicall('GET', `/api/auth/users?search=${encodeURIComponent(q)}&limit=10`, token);
        const ex = new Set([...(shares.map((s) => s.user_id)), doc?.owner_id]);
        setResults(Array.isArray(data) ? data.filter((u) => !ex.has(u.id)) : []);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  const handleAdd = async (user, access = 'view') => {
    setBusy(user.id);
    try {
      await apicall('POST', `/api/workspace/documents/${doc.id}/share`, token,
        { user_id: user.id, access });
      const ns = { user_id: user.id, user_name: user.name, access };
      const newShares = [...shares, ns];
      setShares(newShares);
      setResults((prev) => prev.filter((u) => u.id !== user.id));
      toast.success(`${user.name} diberi akses ${access}`);
      if (onShared) onShared({ ...doc, permissions: { ...doc.permissions, shared_with: newShares } });
    } catch (e) { toast.error(e.message); } finally { setBusy(null); }
  };

  const handleChangeAccess = async (userId, access) => {
    setBusy(userId);
    try {
      await apicall('POST', `/api/workspace/documents/${doc.id}/share`, token,
        { user_id: userId, access });
      setShares((prev) => prev.map((s) => s.user_id === userId ? { ...s, access } : s));
    } catch (e) { toast.error(e.message); } finally { setBusy(null); }
  };

  const handleRevoke = async (userId, name) => {
    if (!window.confirm(`Cabut akses ${name}?`)) return;
    setBusy(userId);
    try {
      await apicall('DELETE', `/api/workspace/documents/${doc.id}/share/${userId}`, token);
      setShares((prev) => prev.filter((s) => s.user_id !== userId));
      toast.success(`Akses ${name} dicabut`);
    } catch (e) { toast.error(e.message); } finally { setBusy(null); }
  };

  if (!doc) return null;
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="share-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Share2 size={18} />Bagikan "{doc.name}"
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-2">
          <div className="relative">
            {searching
              ? <Loader2 size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground" />
              : <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />}
            <Input
              placeholder="Cari user..."
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              className="pl-8 text-sm"
              data-testid="share-search-input"
            />
          </div>
          {results.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              {results.map((u) => (
                <div key={u.id} className="flex items-center justify-between p-2.5 hover:bg-muted/50 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{u.name}</p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </div>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="outline" className="h-7 text-xs"
                      disabled={busy === u.id} onClick={() => handleAdd(u, 'view')}>
                      <Eye size={12} className="mr-1" />View
                    </Button>
                    <Button size="sm" className="h-7 text-xs"
                      disabled={busy === u.id} onClick={() => handleAdd(u, 'edit')}>
                      <Pencil size={12} className="mr-1" />Edit
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground mb-2">Akses saat ini</p>
          <div className="flex items-center justify-between py-2 px-2 rounded-md bg-muted/30">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-violet-100 flex items-center justify-center">
                <Crown size={13} className="text-violet-600" />
              </div>
              <div>
                <p className="text-sm font-medium">{doc.owner_name || 'Owner'}</p>
                <p className="text-xs text-muted-foreground">Pemilik</p>
              </div>
            </div>
            <Badge variant="secondary" className="text-xs">Owner</Badge>
          </div>
          {shares.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-3">
              Belum dibagikan ke siapapun
            </p>
          )}
          {shares.map((s) => (
            <div key={s.user_id} className="flex items-center justify-between py-2 px-2 rounded-md hover:bg-muted/20">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs font-bold">
                  {(s.user_name || '?')[0].toUpperCase()}
                </div>
                <p className="text-sm">{s.user_name}</p>
              </div>
              <div className="flex items-center gap-2">
                <Select value={s.access} onValueChange={(v) => handleChangeAccess(s.user_id, v)} disabled={!!busy}>
                  <SelectTrigger className="h-7 w-[90px] text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="view">Lihat</SelectItem>
                    <SelectItem value="edit">Edit</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive"
                  disabled={busy === s.user_id}
                  onClick={() => handleRevoke(s.user_id, s.user_name)}
                  data-testid={`share-revoke-${s.user_id}`}>
                  {busy === s.user_id ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
                </Button>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="w-full">Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
