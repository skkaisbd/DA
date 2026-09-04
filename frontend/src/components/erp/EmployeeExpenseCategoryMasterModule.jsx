/**
 * EmployeeExpenseCategoryMasterModule — Master Kategori Expense (EEM)
 * CV. Dewi Aditya — EEM Phase 5D
 *
 * CRUD master data kategori expense yang bisa dikelola Admin/Finance.
 * Backend: /api/hr/expenses/master-categories + /seed-default
 * Roles: superadmin, admin, owner, finance
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Pencil, Trash2, RefreshCw, Tag, CheckCircle2,
  XCircle, Search, Database, AlertCircle, Loader2
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || import.meta?.env?.REACT_APP_BACKEND_URL;

const ADMIN_ROLES = ['superadmin', 'admin', 'owner', 'finance'];

function getToken() {
  return localStorage.getItem('erp_token');
}

function getUserRole() {
  try {
    const raw = localStorage.getItem('erp_user');
    if (!raw) return null;
    const u = JSON.parse(raw);
    return u?.role || null;
  } catch {
    return null;
  }
}

// ── Category Form Dialog ─────────────────────────────────────────────────────
function CategoryFormDialog({ open, onClose, category, onSaved }) {
  const [form, setForm] = useState({ name: '', code: '', description: '', is_active: true });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      if (category) {
        setForm({
          name: category.name || '',
          code: category.code || '',
          description: category.description || '',
          is_active: category.is_active !== false,
        });
      } else {
        setForm({ name: '', code: '', description: '', is_active: true });
      }
      setError('');
    }
  }, [open, category]);

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError('Nama kategori wajib diisi.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const token = getToken();
      const url = category
        ? `${API}/api/hr/expenses/master-categories/${category.id}`
        : `${API}/api/hr/expenses/master-categories`;
      const method = category ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal menyimpan');
      toast.success(category ? 'Kategori berhasil diperbarui.' : 'Kategori berhasil ditambahkan.');
      onSaved(data);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{category ? 'Edit Kategori' : 'Tambah Kategori Baru'}</DialogTitle>
          <DialogDescription>
            {category ? 'Perbarui data kategori expense.' : 'Tambahkan kategori expense baru ke master data.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="cat-name">Nama Kategori <span className="text-destructive">*</span></Label>
            <Input
              id="cat-name"
              data-testid="category-name-input"
              placeholder="mis. Biaya Training, Sewa Kendaraan"
              value={form.name}
              onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cat-code">Kode Kategori <span className="text-muted-foreground text-xs">(opsional)</span></Label>
            <Input
              id="cat-code"
              data-testid="category-code-input"
              placeholder="mis. CAT-014"
              value={form.code}
              onChange={e => setForm(p => ({ ...p, code: e.target.value }))}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cat-desc">Deskripsi <span className="text-muted-foreground text-xs">(opsional)</span></Label>
            <Input
              id="cat-desc"
              data-testid="category-description-input"
              placeholder="Penjelasan singkat kategori ini"
              value={form.description}
              onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div>
              <p className="text-sm font-medium">Status Aktif</p>
              <p className="text-xs text-muted-foreground">Nonaktif = tidak muncul di dropdown klaim</p>
            </div>
            <Switch
              data-testid="category-active-switch"
              checked={form.is_active}
              onCheckedChange={v => setForm(p => ({ ...p, is_active: v }))}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Batal
          </Button>
          <Button
            data-testid="category-save-button"
            onClick={handleSave}
            disabled={saving}
          >
            {saving && <Loader2 size={14} className="mr-2 animate-spin" />}
            {category ? 'Simpan Perubahan' : 'Tambah Kategori'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function EmployeeExpenseCategoryMasterModule() {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCat, setEditingCat] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const userRole = getUserRole();
  const canEdit = ADMIN_ROLES.includes(userRole);

  const fetchCategories = useCallback(async () => {
    setLoading(true);
    try {
      const token = getToken();
      const url = `${API}/api/hr/expenses/master-categories?include_inactive=${showInactive}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setCategories(data.items || []);
      } else {
        toast.error('Gagal memuat master kategori');
      }
    } catch (err) {
      toast.error('Koneksi bermasalah');
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  const handleSeedDefault = async () => {
    setSeeding(true);
    try {
      const token = getToken();
      const res = await fetch(`${API}/api/hr/expenses/master-categories/seed-default`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        toast.success(`${data.message}`);
        await fetchCategories();
      } else {
        toast.error(data.detail || 'Gagal seed kategori');
      }
    } catch (err) {
      toast.error('Koneksi bermasalah');
    } finally {
      setSeeding(false);
    }
  };

  const handleOpenCreate = () => {
    setEditingCat(null);
    setDialogOpen(true);
  };

  const handleOpenEdit = (cat) => {
    setEditingCat(cat);
    setDialogOpen(true);
  };

  const handleDeactivate = async () => {
    if (!deleteTarget) return;
    try {
      const token = getToken();
      const res = await fetch(`${API}/api/hr/expenses/master-categories/${deleteTarget.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        toast.success(data.message);
        await fetchCategories();
      } else {
        toast.error(data.detail || 'Gagal menonaktifkan kategori');
      }
    } catch (err) {
      toast.error('Koneksi bermasalah');
    } finally {
      setDeleteTarget(null);
    }
  };

  const filtered = categories.filter(c =>
    c.name?.toLowerCase().includes(search.toLowerCase()) ||
    c.code?.toLowerCase().includes(search.toLowerCase()) ||
    c.description?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Master Kategori Expense</h1>
          <p className="text-sm text-muted-foreground">
            Kelola daftar kategori untuk klaim biaya karyawan (EEM).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && (
            <Button
              variant="outline"
              size="sm"
              data-testid="category-seed-button"
              onClick={handleSeedDefault}
              disabled={seeding}
              className="gap-2"
            >
              {seeding
                ? <Loader2 size={14} className="animate-spin" />
                : <Database size={14} />}
              Seed Default
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            data-testid="category-refresh-button"
            onClick={fetchCategories}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
          {canEdit && (
            <Button
              size="sm"
              data-testid="category-create-button"
              onClick={handleOpenCreate}
              className="gap-2"
            >
              <Plus size={14} />
              Tambah Kategori
            </Button>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <Card className="shadow-[var(--shadow-card)]">
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                data-testid="category-search-input"
                placeholder="Cari nama atau kode kategori..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="show-inactive"
                checked={showInactive}
                onCheckedChange={setShowInactive}
                data-testid="category-show-inactive-switch"
              />
              <Label htmlFor="show-inactive" className="text-sm cursor-pointer">
                Tampilkan nonaktif
              </Label>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Total Kategori</p>
            <p className="text-2xl font-bold text-foreground">{categories.length}</p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Aktif</p>
            <p className="text-2xl font-bold text-emerald-500">
              {categories.filter(c => c.is_active !== false).length}
            </p>
          </CardContent>
        </Card>
        <Card className="shadow-[var(--shadow-card)]">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Nonaktif</p>
            <p className="text-2xl font-bold text-muted-foreground">
              {categories.filter(c => c.is_active === false).length}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Table */}
      <Card className="shadow-[var(--shadow-card)]">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Tag size={16} className="text-primary" />
            Daftar Kategori
          </CardTitle>
          <CardDescription>
            {filtered.length} kategori {search ? 'ditemukan' : 'tersedia'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 gap-3 text-muted-foreground">
              <Loader2 size={20} className="animate-spin" />
              <span className="text-sm">Memuat data...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
              <Tag size={40} className="opacity-20" />
              <p className="text-sm">
                {search ? 'Tidak ada kategori yang cocok.' : 'Belum ada kategori. Klik "Seed Default" untuk isi data awal.'}
              </p>
              {canEdit && !search && (
                <Button size="sm" onClick={handleSeedDefault} disabled={seeding}>
                  {seeding ? <Loader2 size={12} className="mr-2 animate-spin" /> : <Database size={12} className="mr-2" />}
                  Seed Kategori Default
                </Button>
              )}
            </div>
          ) : (
            <div className="rounded-[var(--radius-md)] border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/30">
                    <TableHead className="text-xs uppercase tracking-wide w-24">Kode</TableHead>
                    <TableHead className="text-xs uppercase tracking-wide">Nama Kategori</TableHead>
                    <TableHead className="text-xs uppercase tracking-wide hidden md:table-cell">Deskripsi</TableHead>
                    <TableHead className="text-xs uppercase tracking-wide w-24 text-center">Status</TableHead>
                    {canEdit && (
                      <TableHead className="text-xs uppercase tracking-wide w-24 text-right">Aksi</TableHead>
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map(cat => (
                    <TableRow
                      key={cat.id}
                      className="hover:bg-[hsl(var(--muted)/0.35)] transition-colors"
                      data-testid={`category-row-${cat.id}`}
                    >
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {cat.code || '—'}
                      </TableCell>
                      <TableCell className="font-medium text-sm">
                        {cat.name}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground hidden md:table-cell max-w-xs truncate">
                        {cat.description || '—'}
                      </TableCell>
                      <TableCell className="text-center">
                        {cat.is_active !== false ? (
                          <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 text-xs gap-1">
                            <CheckCircle2 size={10} />
                            Aktif
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="border-muted-foreground/30 bg-muted/40 text-muted-foreground text-xs gap-1">
                            <XCircle size={10} />
                            Nonaktif
                          </Badge>
                        )}
                      </TableCell>
                      {canEdit && (
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              data-testid={`category-edit-${cat.id}`}
                              onClick={() => handleOpenEdit(cat)}
                            >
                              <Pencil size={13} />
                            </Button>
                            {cat.is_active !== false && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-destructive hover:text-destructive"
                                data-testid={`category-delete-${cat.id}`}
                                onClick={() => setDeleteTarget(cat)}
                              >
                                <Trash2 size={13} />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Form Dialog */}
      <CategoryFormDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        category={editingCat}
        onSaved={() => fetchCategories()}
      />

      {/* Deactivate Confirm Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={v => !v && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Nonaktifkan Kategori?</AlertDialogTitle>
            <AlertDialogDescription>
              Kategori <strong>{deleteTarget?.name}</strong> akan dinonaktifkan dan tidak akan muncul di dropdown klaim baru.
              Data klaim yang sudah ada tidak terpengaruh. Kategori dapat diaktifkan kembali kapan saja.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction
              data-testid="category-deactivate-confirm"
              onClick={handleDeactivate}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Nonaktifkan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
