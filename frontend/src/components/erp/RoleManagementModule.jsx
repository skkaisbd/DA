/**
 * RoleManagementModule — SATU-SATUNYA layar konfigurasi akses (Peran & Hak Akses).
 *
 * LATAR BELAKANG (2026-08-06)
 * ---------------------------
 * Sebelumnya ada DUA tempat mengatur akses dan owner bingung:
 *   1) tab "Peran"     -> dialog Edit Role berisi chip permission
 *   2) tab "Hak Akses" -> "Matriks Role & Permission" (tabel raksasa, sulit dipakai)
 * `RoleMatrixModule.jsx` DIHAPUS. Semua pengaturan sekarang di sini, memakai
 * layout master–detail: kiri daftar peran, kanan panel konfigurasi bertahap.
 *
 * SUMBER DATA (tanpa katalog kedua di frontend)
 *   GET  /api/permissions?grouped=1   -> katalog izin (backend/data/permission_catalog.py)
 *   GET  /api/roles                   -> peran + portals + hidden_modules + permission_keys + user_count
 *   GET  /api/roles/audit?role_id=..  -> riwayat perubahan peran
 *   POST /api/roles                   -> buat peran
 *   PUT  /api/roles/{id}              -> SATU jalur simpan (identitas + portal + menu + izin)
 *   DELETE /api/roles/{id}
 *
 * Daftar portal & menu diambil dari SSOT navigasi `portal-shell/portalNav.js`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Shield, Plus, Trash2, Search, Save, RotateCcw, Loader2, Users, LayoutGrid,
  KeyRound, History, Copy, TriangleAlert, EyeOff, Check, Columns3, X, Info,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
} from '@/components/ui/accordion';
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogFooter,
  AlertDialogTitle, AlertDialogDescription, AlertDialogAction, AlertDialogCancel,
} from '@/components/ui/alert-dialog';
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { GlassCard } from '@/components/ui/glass';
import { PageHeader, EmptyState } from './moduleAtoms';
import { PORTAL_NAV, PORTAL_LABEL } from './portal-shell/portalNav';

const API = process.env.REACT_APP_BACKEND_URL || '';

/* Preset cepat — dihitung dari metadata `action` katalog, bukan daftar hardcode. */
const PRESETS = [
  { id: 'view', label: 'Lihat saja', actions: ['view'], hint: 'Hanya membaca data' },
  { id: 'operator', label: 'Operator', actions: ['view', 'input'], hint: 'Baca + catat data harian' },
  { id: 'approver', label: 'Approver', actions: ['view', 'approve'], hint: 'Baca + setujui dokumen' },
  { id: 'full', label: 'Penuh', actions: ['view', 'input', 'manage', 'approve', 'run', 'export'], hint: 'Semua izin' },
];

const LEVELS = [
  { id: 'none', label: 'Tidak ada' },
  { id: 'view', label: 'Lihat saja' },
  { id: 'full', label: 'Penuh' },
];

const emptyDraft = () => ({ name: '', description: '', portals: [], hidden_modules: [], permissions: [] });

const sameSet = (a = [], b = []) => {
  if (a.length !== b.length) return false;
  const sb = new Set(b);
  return a.every((x) => sb.has(x));
};

/* Semua menu (pintu modul) per portal, dari SSOT navigasi. */
const menusOfPortal = (pid) => {
  const sections = PORTAL_NAV[pid]?.sections || [];
  return sections.flatMap((sec) => (sec.items || []).concat(
    (sec.groups || []).flatMap((g) => g.items || []),
  ));
};

export default function RoleManagementModule({ token, userRole }) {
  const canEdit = userRole === 'superadmin';

  const [groups, setGroups] = useState([]);      // katalog izin (portal > modul > izin)
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(emptyDraft());
  const [roleSearch, setRoleSearch] = useState('');
  const [permSearch, setPermSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newRole, setNewRole] = useState({ name: '', description: '' });
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [auditRows, setAuditRows] = useState([]);
  const [auditOpen, setAuditOpen] = useState(false);
  const [compareWith, setCompareWith] = useState('');
  const [compareOpen, setCompareOpen] = useState(false);

  const headers = useMemo(() => ({
    'Content-Type': 'application/json', Authorization: `Bearer ${token}`,
  }), [token]);

  /* Ref supaya `load()` tidak perlu bergantung pada selectedId (mencegah refetch
     tiap kali peran diklik, yang akan menghapus perubahan yang belum disimpan). */
  const selectedIdRef = useRef(null);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);

  /* ── memuat data ─────────────────────────────────────────────────────── */
  const load = useCallback(async (keepId) => {
    setLoading(true);
    try {
      const [rRoles, rPerms] = await Promise.all([
        fetch(`${API}/api/roles`, { headers }),
        fetch(`${API}/api/permissions?grouped=1`, { headers }),
      ]);
      if (!rRoles.ok) throw new Error(`Gagal memuat peran (HTTP ${rRoles.status})`);
      if (!rPerms.ok) throw new Error(`Gagal memuat katalog izin (HTTP ${rPerms.status})`);
      const rolesData = await rRoles.json();
      const permData = await rPerms.json();
      setRoles(Array.isArray(rolesData) ? rolesData : []);
      setGroups(permData.groups || []);
      const list = Array.isArray(rolesData) ? rolesData : [];
      const next = list.find((r) => r.id === (keepId || selectedIdRef.current)) || list[0];
      if (next) {
        setSelectedId(next.id);
        setDraft({
          name: next.name || '',
          description: next.description || '',
          portals: [...(next.portals || [])],
          hidden_modules: [...(next.hidden_modules || [])],
          permissions: [...(next.permission_keys || [])],
        });
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const selected = useMemo(
    () => roles.find((r) => r.id === selectedId) || null, [roles, selectedId],
  );

  const selectRole = (role) => {
    setSelectedId(role.id);
    setPermSearch('');
    setAuditOpen(false);
    setAuditRows([]);
    setDraft({
      name: role.name || '',
      description: role.description || '',
      portals: [...(role.portals || [])],
      hidden_modules: [...(role.hidden_modules || [])],
      permissions: [...(role.permission_keys || [])],
    });
  };

  const dirty = useMemo(() => {
    if (!selected) return false;
    return draft.name !== (selected.name || '')
      || (draft.description || '') !== (selected.description || '')
      || !sameSet(draft.portals, selected.portals || [])
      || !sameSet(draft.hidden_modules, selected.hidden_modules || [])
      || !sameSet(draft.permissions, selected.permission_keys || []);
  }, [draft, selected]);

  /* ── katalog izin: indeks bantu ──────────────────────────────────────── */
  const allPerms = useMemo(
    () => groups.flatMap((g) => g.modules.flatMap((m) => m.permissions)), [groups],
  );
  const permSet = useMemo(() => new Set(draft.permissions), [draft.permissions]);

  const visibleGroups = useMemo(() => {
    const q = permSearch.trim().toLowerCase();
    if (!q) return groups;
    return groups
      .map((g) => ({
        ...g,
        modules: g.modules
          .map((m) => ({
            ...m,
            permissions: m.permissions.filter((p) => (
              p.key.toLowerCase().includes(q)
              || (p.description || '').toLowerCase().includes(q)
              || (m.label || '').toLowerCase().includes(q)
              || (g.portal_label || '').toLowerCase().includes(q)
            )),
          }))
          .filter((m) => m.permissions.length),
      }))
      .filter((g) => g.modules.length);
  }, [groups, permSearch]);

  /* ── aksi izin ───────────────────────────────────────────────────────── */
  const setPerms = (updater) => setDraft((d) => ({ ...d, permissions: updater(new Set(d.permissions)) }));

  const togglePerm = (key) => setPerms((s) => {
    if (s.has(key)) s.delete(key); else s.add(key);
    return Array.from(s);
  });

  const applyLevelToModule = (mod, level) => setPerms((s) => {
    mod.permissions.forEach((p) => s.delete(p.key));
    if (level === 'view') mod.permissions.filter((p) => p.action === 'view').forEach((p) => s.add(p.key));
    if (level === 'full') mod.permissions.forEach((p) => s.add(p.key));
    return Array.from(s);
  });

  const applyLevelToGroup = (grp, level) => setPerms((s) => {
    grp.modules.forEach((m) => m.permissions.forEach((p) => s.delete(p.key)));
    if (level === 'view') {
      grp.modules.forEach((m) => m.permissions.filter((p) => p.action === 'view').forEach((p) => s.add(p.key)));
    }
    if (level === 'full') grp.modules.forEach((m) => m.permissions.forEach((p) => s.add(p.key)));
    return Array.from(s);
  });

  const applyPreset = (preset) => {
    const scope = draft.portals.length ? new Set(draft.portals) : null;
    const keys = allPerms
      .filter((p) => (!scope || scope.has(p.portal)) && preset.actions.includes(p.action))
      .map((p) => p.key);
    setDraft((d) => ({ ...d, permissions: keys }));
    toast.success(`Preset "${preset.label}" diterapkan (${keys.length} izin)`, {
      description: scope ? 'Dibatasi pada portal yang dipilih peran ini.' : 'Berlaku untuk semua portal.',
    });
  };

  const clearPerms = () => setDraft((d) => ({ ...d, permissions: [] }));

  const copyFromRole = (rid) => {
    const src = roles.find((r) => r.id === rid);
    if (!src) return;
    setDraft((d) => ({
      ...d,
      portals: [...(src.portals || [])],
      hidden_modules: [...(src.hidden_modules || [])],
      permissions: [...(src.permission_keys || [])],
    }));
    toast.success(`Disalin dari peran "${src.name}"`, { description: 'Belum tersimpan — tekan Simpan bila sudah sesuai.' });
  };

  const levelOfModule = (mod) => {
    const total = mod.permissions.length;
    const on = mod.permissions.filter((p) => permSet.has(p.key)).length;
    if (on === 0) return 'none';
    if (on === total) return 'full';
    const views = mod.permissions.filter((p) => p.action === 'view');
    if (views.length && on === views.length && views.every((p) => permSet.has(p.key))) return 'view';
    return 'partial';
  };

  /* ── portal & menu ───────────────────────────────────────────────────── */
  const togglePortal = (pid) => setDraft((d) => ({
    ...d,
    portals: d.portals.includes(pid) ? d.portals.filter((x) => x !== pid) : [...d.portals, pid],
  }));

  const toggleMenu = (mid) => setDraft((d) => ({
    ...d,
    hidden_modules: d.hidden_modules.includes(mid)
      ? d.hidden_modules.filter((x) => x !== mid)
      : [...d.hidden_modules, mid],
  }));

  /* ── simpan / buat / hapus ───────────────────────────────────────────── */
  const save = async () => {
    if (!selected) return;
    if (!draft.name.trim()) { toast.error('Nama peran wajib diisi.'); return; }
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/roles/${selected.id}`, {
        method: 'PUT', headers, body: JSON.stringify(draft),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      toast.success(`Peran "${draft.name}" tersimpan`, {
        description: `${draft.permissions.length} izin · ${draft.portals.length || 'bawaan'} portal · ${draft.hidden_modules.length} menu disembunyikan`,
      });
      await load(selected.id);
    } catch (e) {
      toast.error('Gagal menyimpan', { description: e.message });
    } finally {
      setSaving(false);
    }
  };

  const createRole = async () => {
    const name = newRole.name.trim();
    if (!name) { toast.error('Nama peran wajib diisi.'); return; }
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/roles`, {
        method: 'POST', headers,
        body: JSON.stringify({ name, description: newRole.description, portals: [], hidden_modules: [], permissions: [] }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      toast.success(`Peran "${name}" dibuat`, { description: 'Sekarang atur portal & hak aksesnya di panel kanan.' });
      setShowCreate(false);
      setNewRole({ name: '', description: '' });
      await load(body.id);
    } catch (e) {
      toast.error('Gagal membuat peran', { description: e.message });
    } finally {
      setSaving(false);
    }
  };

  const removeRole = async () => {
    const role = confirmDelete;
    if (!role) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/roles/${role.id}`, { method: 'DELETE', headers });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      toast.success(`Peran "${role.name}" dihapus`);
      setConfirmDelete(null);
      setSelectedId(null);
      await load(null);
    } catch (e) {
      toast.error('Gagal menghapus peran', { description: e.message });
    } finally {
      setSaving(false);
    }
  };

  const loadAudit = async () => {
    if (!selected) return;
    try {
      const res = await fetch(`${API}/api/roles/audit?role_id=${selected.id}&limit=20`, { headers });
      const body = await res.json();
      setAuditRows(body.items || []);
    } catch (e) {
      toast.error('Gagal memuat riwayat', { description: e.message });
    }
  };

  /* ── daftar peran (kolom kiri) ───────────────────────────────────────── */
  const filteredRoles = useMemo(() => {
    const q = roleSearch.trim().toLowerCase();
    if (!q) return roles;
    return roles.filter((r) => (r.name || '').toLowerCase().includes(q)
      || (r.description || '').toLowerCase().includes(q));
  }, [roles, roleSearch]);

  const compareRole = roles.find((r) => r.id === compareWith) || null;

  /* ── render ──────────────────────────────────────────────────────────── */
  return (
    <div className="space-y-4" data-testid="role-access-page">
      <PageHeader
        icon={Shield}
        title="Peran & Hak Akses"
        subtitle="Satu tempat untuk semuanya: portal yang boleh dibuka, menu yang disembunyikan, dan izin aksi/approval."
        testId="role-access-header"
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => {
                      if (!compareWith) {
                        const other = roles.find((r) => r.id !== selectedId);
                        if (other) setCompareWith(other.id);
                      }
                      setCompareOpen(true);
                    }}
                    disabled={!selected} data-testid="compare-roles-btn">
              <Columns3 /> Bandingkan
            </Button>
            {canEdit && (
              <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-role-btn">
                <Plus /> Tambah Peran
              </Button>
            )}
          </div>
        )}
      />

      <div className="flex items-start gap-2 rounded-lg border border-border bg-[var(--glass-bg)] px-3 py-2"
           data-testid="role-access-notice">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <p className="text-xs leading-relaxed text-muted-foreground">
          Matriks izin yang lama sudah dihapus. Semua konfigurasi akses kini di layar ini.
          Selama daftar izin sebuah peran <span className="font-medium text-foreground">masih kosong</span>,
          sistem memakai aturan bawaan lama (tidak ada fitur yang mati). Begitu Anda mencentang minimal satu izin,
          peran itu mengikuti daftar izin di bawah.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(240px,300px)_1fr]">
        {/* ── KIRI: daftar peran ──────────────────────────────────────── */}
        <GlassCard className="self-start p-3 lg:sticky lg:top-4" hover={false}>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={roleSearch}
              onChange={(e) => setRoleSearch(e.target.value)}
              placeholder="Cari peran..."
              className="pl-8"
              data-testid="role-search-input"
            />
          </div>
          <div className="max-h-[62vh] space-y-1.5 overflow-y-auto pr-1" data-testid="role-list">
            {loading && Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
            {!loading && filteredRoles.length === 0 && (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">Tidak ada peran yang cocok.</p>
            )}
            {!loading && filteredRoles.map((r) => {
              const active = r.id === selectedId;
              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => selectRole(r)}
                  data-testid={`role-item-${r.name}`}
                  aria-current={active ? 'true' : undefined}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    active
                      ? 'border-primary bg-primary/10'
                      : 'border-border bg-transparent hover:border-primary/40 hover:bg-[var(--glass-bg-hover)]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold text-foreground">{r.name}</span>
                    {r.is_system && <Badge variant="outline" className="shrink-0 text-[10px]">sistem</Badge>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{r.user_count || 0}</span>
                    <span className="inline-flex items-center gap-1"><LayoutGrid className="h-3 w-3" />{(r.portals || []).length || 'bawaan'}</span>
                    <span className="inline-flex items-center gap-1"><KeyRound className="h-3 w-3" />{(r.permission_keys || []).length}</span>
                    {(r.hidden_modules || []).length > 0 && (
                      <span className="inline-flex items-center gap-1"><EyeOff className="h-3 w-3" />{r.hidden_modules.length}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </GlassCard>

        {/* ── KANAN: detail peran ─────────────────────────────────────── */}
        {!selected && !loading ? (
          <GlassCard className="p-6" hover={false}>
            <EmptyState
              icon={Shield}
              title="Belum ada peran dipilih"
              description="Pilih peran di kiri, atau buat peran baru untuk mulai mengatur akses."
              testId="role-detail-empty"
            />
          </GlassCard>
        ) : (
          <div className="space-y-4" data-testid="role-detail-panel">
            {/* Ringkasan + tombol simpan */}
            <GlassCard className="p-4" hover={false}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-lg font-semibold text-foreground" data-testid="role-detail-name">
                      {selected?.name || '—'}
                    </h3>
                    {dirty && (
                      <Badge variant="outline" className="border-amber-500/50 text-amber-600 dark:text-amber-400"
                             data-testid="role-dirty-badge">
                        Belum disimpan
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground" data-testid="role-detail-summary">
                    Boleh membuka <span className="font-medium text-foreground">
                      {draft.portals.length ? `${draft.portals.length} portal` : 'portal bawaan sistem'}
                    </span> · <span className="font-medium text-foreground">{draft.permissions.length} izin</span>
                    {' '}· <span className="font-medium text-foreground">{draft.hidden_modules.length} menu disembunyikan</span>
                    {' '}· dipakai <span className="font-medium text-foreground">{selected?.user_count || 0} pengguna</span>
                  </p>
                </div>
                {canEdit && (
                  <div className="flex items-center gap-2">
                    <Button variant="ghost" size="sm" disabled={!dirty || saving}
                            onClick={() => selected && selectRole(selected)} data-testid="role-reset-btn">
                      <RotateCcw /> Batalkan
                    </Button>
                    <Button size="sm" disabled={!dirty || saving} onClick={save} data-testid="role-save-btn">
                      {saving ? <Loader2 className="animate-spin" /> : <Save />} Simpan
                    </Button>
                  </div>
                )}
              </div>
              {!canEdit && (
                <p className="mt-3 rounded-md bg-[var(--glass-bg)] px-3 py-2 text-xs text-muted-foreground">
                  Hanya Super Admin yang boleh mengubah konfigurasi peran. Anda melihat mode baca.
                </p>
              )}
            </GlassCard>

            {/* 1. Identitas */}
            <GlassCard className="p-4" hover={false}>
              <SectionTitle step="1" title="Identitas Peran"
                            desc="Nama dipakai sebagai kode role pada akun pengguna." />
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="role-name">Nama peran</label>
                  <Input id="role-name" value={draft.name} disabled={!canEdit}
                         onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                         placeholder="cth. approver_material" data-testid="role-name" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="role-desc">Keterangan</label>
                  <Input id="role-desc" value={draft.description} disabled={!canEdit}
                         onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                         placeholder="cth. Menyetujui pengeluaran material" data-testid="role-description" />
                </div>
              </div>
              {canEdit && roles.length > 1 && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">Salin pengaturan dari peran lain:</span>
                  <Select onValueChange={copyFromRole}>
                    <SelectTrigger className="h-8 w-56 text-xs" data-testid="copy-from-role">
                      <SelectValue placeholder="Pilih peran sumber..." />
                    </SelectTrigger>
                    <SelectContent>
                      {roles.filter((r) => r.id !== selectedId).map((r) => (
                        <SelectItem key={r.id} value={r.id} className="text-xs">
                          {r.name} ({(r.permission_keys || []).length} izin)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
              )}
            </GlassCard>

            {/* 2. Akses Portal */}
            <GlassCard className="p-4" hover={false}>
              <SectionTitle
                step="2" title="Portal yang Boleh Dibuka"
                desc="Kosongkan semua bila ingin memakai aturan bawaan sistem untuk peran ini."
                right={canEdit && (
                  <div className="flex gap-1.5">
                    <Button variant="outline" size="sm" data-testid="portal-select-all"
                            onClick={() => setDraft((d) => ({ ...d, portals: Object.keys(PORTAL_NAV) }))}>
                      Pilih semua
                    </Button>
                    <Button variant="ghost" size="sm" data-testid="portal-clear"
                            onClick={() => setDraft((d) => ({ ...d, portals: [] }))}>
                      Pakai bawaan
                    </Button>
                  </div>
                )}
              />
              <div className="flex flex-wrap gap-2" data-testid="role-portals">
                {Object.keys(PORTAL_NAV).map((pid) => {
                  const on = draft.portals.includes(pid);
                  return (
                    <button
                      key={pid} type="button" disabled={!canEdit}
                      onClick={() => togglePortal(pid)}
                      data-testid={`role-portal-${pid}`}
                      aria-pressed={on}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 ${
                        on
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-transparent text-foreground/70 hover:border-primary/50 hover:bg-[var(--glass-bg-hover)]'
                      }`}
                    >
                      {on && <Check className="h-3 w-3" />}
                      {PORTAL_LABEL?.[pid] || pid}
                    </button>
                  );
                })}
              </div>
            </GlassCard>

            {/* 3. Hak Akses */}
            <GlassCard className="p-4" hover={false}>
              <SectionTitle
                step="3" title="Hak Akses (Izin Aksi & Approval)"
                desc="Pilih cepat per modul: Tidak ada / Lihat saja / Penuh. Buka detail bila perlu presisi."
                right={(
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-[11px]" data-testid="perm-count-badge">
                      {draft.permissions.length} izin dipilih
                    </Badge>
                  </div>
                )}
              />

              {canEdit && (
                <div className="mb-3 flex flex-wrap items-center gap-1.5">
                  <span className="mr-1 text-xs text-muted-foreground">Preset:</span>
                  {PRESETS.map((p) => (
                    <Button key={p.id} variant="outline" size="sm" title={p.hint}
                            onClick={() => applyPreset(p)} data-testid={`preset-${p.id}`}>
                      {p.label}
                    </Button>
                  ))}
                  <Button variant="ghost" size="sm" onClick={clearPerms} data-testid="preset-clear">
                    <X /> Kosongkan
                  </Button>
                </div>
              )}

              {draft.permissions.length > 0 && (
                <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    Peran ini memakai daftar izin di bawah. Aturan bawaan lama tidak lagi dipakai untuk peran ini —
                    pastikan izin yang dibutuhkan sudah dicentang sebelum menyimpan.
                  </p>
                </div>
              )}

              <div className="relative mb-3">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={permSearch} onChange={(e) => setPermSearch(e.target.value)}
                       placeholder="Cari izin, modul, atau portal..." className="pl-8"
                       data-testid="perm-search-input" />
              </div>

              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}
                </div>
              ) : visibleGroups.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">Tidak ada izin yang cocok dengan pencarian.</p>
              ) : (
                <Accordion type="multiple" className="space-y-2" data-testid="perm-accordion">
                  {visibleGroups.map((grp) => {
                    const total = grp.modules.reduce((n, m) => n + m.permissions.length, 0);
                    const on = grp.modules.reduce(
                      (n, m) => n + m.permissions.filter((p) => permSet.has(p.key)).length, 0,
                    );
                    const inScope = !draft.portals.length || draft.portals.includes(grp.portal);
                    return (
                      <AccordionItem key={grp.portal} value={grp.portal}
                                     className="overflow-hidden rounded-lg border border-border px-3">
                        <AccordionTrigger className="py-3 hover:no-underline" data-testid={`perm-group-${grp.portal}`}>
                          <div className="flex w-full items-center justify-between gap-3 pr-2">
                            <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                              {grp.portal_label}
                              {!inScope && (
                                <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                                  portal tidak dipilih
                                </Badge>
                              )}
                            </span>
                            <Badge variant={on ? 'default' : 'secondary'} className="shrink-0 text-[11px]">
                              {on}/{total}
                            </Badge>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="pb-3">
                          {canEdit && (
                            <div className="mb-3 flex flex-wrap items-center gap-1.5">
                              <span className="text-[11px] text-muted-foreground">Seluruh portal ini:</span>
                              {LEVELS.map((lv) => (
                                <Button key={lv.id} variant="outline" size="sm" className="h-7 text-[11px]"
                                        onClick={() => applyLevelToGroup(grp, lv.id)}
                                        data-testid={`group-${grp.portal}-level-${lv.id}`}>
                                  {lv.label}
                                </Button>
                              ))}
                            </div>
                          )}
                          <div className="space-y-2">
                            {grp.modules.map((mod) => {
                              const lvl = levelOfModule(mod);
                              return (
                                <div key={mod.id} className="rounded-lg border border-border/70 p-2.5"
                                     data-testid={`perm-module-${mod.id}`}>
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <span className="text-xs font-semibold text-foreground">{mod.label}</span>
                                    {canEdit && (
                                      <div className="inline-flex overflow-hidden rounded-md border border-border"
                                           role="group" aria-label={`Tingkat akses ${mod.label}`}>
                                        {LEVELS.map((lv) => (
                                          <button
                                            key={lv.id} type="button"
                                            onClick={() => applyLevelToModule(mod, lv.id)}
                                            data-testid={`module-${mod.id}-level-${lv.id}`}
                                            aria-pressed={lvl === lv.id}
                                            className={`px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                                              lvl === lv.id
                                                ? 'bg-primary text-primary-foreground'
                                                : 'bg-transparent text-muted-foreground hover:bg-[var(--glass-bg-hover)]'
                                            }`}
                                          >
                                            {lv.label}
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                  <div className="mt-2 flex flex-wrap gap-1.5">
                                    {mod.permissions.map((p) => {
                                      const on2 = permSet.has(p.key);
                                      return (
                                        <button
                                          key={p.key} type="button" disabled={!canEdit}
                                          onClick={() => togglePerm(p.key)}
                                          title={`${p.key} — ${p.description}`}
                                          data-testid={`perm-${p.key}`}
                                          aria-pressed={on2}
                                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 ${
                                            on2
                                              ? 'border-primary bg-primary/15 text-primary'
                                              : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'
                                          }`}
                                        >
                                          {on2 && <Check className="h-3 w-3" />}
                                          {p.description}
                                          <span className="opacity-50">· {p.action}</span>
                                        </button>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    );
                  })}
                </Accordion>
              )}
            </GlassCard>

            {/* 4. Menu disembunyikan */}
            <GlassCard className="p-4" hover={false}>
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <button type="button" className="flex w-full items-center justify-between gap-2 text-left"
                          data-testid="hidden-menus-toggle">
                    <SectionTitle step="4" title="Sembunyikan Menu Tertentu (opsional)"
                                  desc="Untuk kasus khusus: menu tetap ada di sistem tapi tidak muncul untuk peran ini." />
                    <Badge variant="secondary" className="shrink-0 text-[11px]">
                      {draft.hidden_modules.length} disembunyikan
                    </Badge>
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3 space-y-3" data-testid="role-hidden-modules">
                  {(draft.portals.length ? draft.portals : Object.keys(PORTAL_NAV)).map((pid) => {
                    const items = menusOfPortal(pid);
                    if (!items.length) return null;
                    return (
                      <div key={pid}>
                        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-foreground/50">
                          {PORTAL_LABEL?.[pid] || pid}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {items.map((it) => {
                            const off = draft.hidden_modules.includes(it.id);
                            return (
                              <button
                                key={`${pid}-${it.id}`} type="button" disabled={!canEdit}
                                onClick={() => toggleMenu(it.id)}
                                data-testid={`role-menu-${it.id}`}
                                aria-pressed={off}
                                className={`rounded-md border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 ${
                                  off
                                    ? 'border-destructive/40 bg-destructive/10 text-destructive line-through'
                                    : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'
                                }`}
                              >
                                {it.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </CollapsibleContent>
              </Collapsible>
            </GlassCard>

            {/* 5. Riwayat perubahan */}
            <GlassCard className="p-4" hover={false}>
              <Collapsible open={auditOpen} onOpenChange={(v) => { setAuditOpen(v); if (v) loadAudit(); }}>
                <CollapsibleTrigger asChild>
                  <button type="button" className="flex w-full items-center justify-between gap-2 text-left"
                          data-testid="role-audit-toggle">
                    <SectionTitle step="5" title="Riwayat Perubahan" desc="Siapa mengubah akses peran ini dan kapan." />
                    <History className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3" data-testid="role-audit-list">
                  {auditRows.length === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">Belum ada perubahan tercatat.</p>
                  ) : (
                    <ul className="space-y-2">
                      {auditRows.map((row) => (
                        <li key={row.id} className="rounded-md border border-border px-3 py-2 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-medium text-foreground">
                              {row.action === 'create' ? 'Dibuat' : row.action === 'delete' ? 'Dihapus' : 'Diubah'}
                              {' '}oleh {row.user_name || '—'}
                            </span>
                            <span className="text-muted-foreground">
                              {row.timestamp ? new Date(row.timestamp).toLocaleString('id-ID') : ''}
                            </span>
                          </div>
                          <AuditDiff row={row} />
                        </li>
                      ))}
                    </ul>
                  )}
                </CollapsibleContent>
              </Collapsible>
            </GlassCard>

            {/* Hapus peran */}
            {canEdit && selected && !selected.is_system && (
              <div className="flex justify-end">
                <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/10"
                        onClick={() => setConfirmDelete(selected)} data-testid="role-delete-btn">
                  <Trash2 /> Hapus peran ini
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Dialog tambah peran */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent data-testid="create-role-dialog">
          <DialogHeader>
            <DialogTitle>Tambah Peran</DialogTitle>
            <DialogDescription>
              Beri nama dulu. Portal & hak aksesnya diatur setelah peran dibuat.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="new-role-name">Nama peran</label>
              <Input id="new-role-name" value={newRole.name} data-testid="new-role-name"
                     onChange={(e) => setNewRole((s) => ({ ...s, name: e.target.value }))}
                     placeholder="cth. approver_material" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="new-role-desc">Keterangan</label>
              <Input id="new-role-desc" value={newRole.description} data-testid="new-role-description"
                     onChange={(e) => setNewRole((s) => ({ ...s, description: e.target.value }))}
                     placeholder="cth. Menyetujui pengeluaran material" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)} data-testid="create-role-cancel">Batal</Button>
            <Button onClick={createRole} disabled={saving || !newRole.name.trim()} data-testid="create-role-submit">
              {saving ? <Loader2 className="animate-spin" /> : <Plus />} Buat Peran
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Konfirmasi hapus */}
      <AlertDialog open={!!confirmDelete} onOpenChange={(v) => !v && setConfirmDelete(null)}>
        <AlertDialogContent data-testid="delete-role-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus peran &ldquo;{confirmDelete?.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              Peran beserta izinnya akan dihapus permanen. Peran yang masih dipakai pengguna tidak bisa dihapus.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-role-cancel">Batal</AlertDialogCancel>
            <AlertDialogAction onClick={removeRole} data-testid="delete-role-confirm"
                               className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Hapus
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bandingkan peran */}
      <Sheet open={compareOpen} onOpenChange={setCompareOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl" data-testid="compare-sheet">
          <SheetHeader>
            <SheetTitle>Bandingkan Peran</SheetTitle>
            <SheetDescription>
              Lihat selisih izin antara peran terpilih dan peran lain.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant="default" className="text-[11px]">{selected?.name || '—'}</Badge>
              <span className="text-xs text-muted-foreground">dibandingkan dengan</span>
              <Select value={compareWith} onValueChange={setCompareWith}>
                <SelectTrigger className="h-8 w-48 text-xs" data-testid="compare-role-select">
                  <SelectValue placeholder="Pilih peran..." />
                </SelectTrigger>
                <SelectContent>
                  {roles.filter((r) => r.id !== selectedId).map((r) => (
                    <SelectItem key={r.id} value={r.id} className="text-xs">{r.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {compareRole ? (
              <CompareBody
                a={{ name: selected?.name, portals: draft.portals, perms: draft.permissions }}
                b={{ name: compareRole.name, portals: compareRole.portals || [], perms: compareRole.permission_keys || [] }}
                allPerms={allPerms}
              />
            ) : (
              <p className="py-6 text-center text-xs text-muted-foreground">Pilih peran pembanding di atas.</p>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/* ── potongan UI kecil ───────────────────────────────────────────────────── */
function SectionTitle({ step, title, desc, right }) {
  return (
    <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
      <div className="flex items-start gap-2">
        {step && (
          <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-bold text-primary">
            {step}
          </span>
        )}
        <div>
          <h4 className="text-sm font-semibold text-foreground">{title}</h4>
          {desc && <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

function AuditDiff({ row }) {
  const before = (row.before?.permissions) || [];
  const after = (row.after?.permissions) || [];
  const added = after.filter((k) => !before.includes(k));
  const removed = before.filter((k) => !after.includes(k));
  const pBefore = (row.before?.portals) || [];
  const pAfter = (row.after?.portals) || [];
  const portalChanged = pBefore.join(',') !== pAfter.join(',');
  if (!added.length && !removed.length && !portalChanged) return null;
  return (
    <div className="mt-1.5 space-y-1 text-[11px]">
      {portalChanged && (
        <p className="text-muted-foreground">
          Portal: <span className="line-through">{pBefore.join(', ') || 'bawaan'}</span>
          {' → '}<span className="text-foreground">{pAfter.join(', ') || 'bawaan'}</span>
        </p>
      )}
      {added.length > 0 && (
        <p className="text-emerald-700 dark:text-emerald-400">+ {added.join(', ')}</p>
      )}
      {removed.length > 0 && (
        <p className="text-destructive">− {removed.join(', ')}</p>
      )}
    </div>
  );
}

function CompareBody({ a, b, allPerms }) {
  const setA = new Set(a.perms);
  const setB = new Set(b.perms);
  const onlyA = allPerms.filter((p) => setA.has(p.key) && !setB.has(p.key));
  const onlyB = allPerms.filter((p) => setB.has(p.key) && !setA.has(p.key));
  const both = allPerms.filter((p) => setA.has(p.key) && setB.has(p.key));
  return (
    <div className="space-y-4" data-testid="compare-body">
      <div className="grid grid-cols-3 gap-2 text-center">
        {[['Hanya ' + (a.name || 'A'), onlyA.length], ['Sama', both.length], ['Hanya ' + (b.name || 'B'), onlyB.length]].map(([label, n]) => (
          <div key={label} className="rounded-lg border border-border px-2 py-3">
            <p className="text-lg font-bold text-foreground">{n}</p>
            <p className="truncate text-[11px] text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>
      <Separator />
      <div>
        <p className="mb-1.5 text-xs font-semibold text-foreground">Portal</p>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-md border border-border p-2">
            <p className="mb-1 font-medium">{a.name}</p>
            <p className="text-muted-foreground">{a.portals.length ? a.portals.join(', ') : 'bawaan sistem'}</p>
          </div>
          <div className="rounded-md border border-border p-2">
            <p className="mb-1 font-medium">{b.name}</p>
            <p className="text-muted-foreground">{b.portals.length ? b.portals.join(', ') : 'bawaan sistem'}</p>
          </div>
        </div>
      </div>
      {[[`Hanya ada di ${a.name}`, onlyA], [`Hanya ada di ${b.name}`, onlyB]].map(([label, list]) => (
        <div key={label}>
          <p className="mb-1.5 text-xs font-semibold text-foreground">{label} ({list.length})</p>
          {list.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">Tidak ada.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {list.map((p) => (
                <span key={p.key} className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {p.description}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
