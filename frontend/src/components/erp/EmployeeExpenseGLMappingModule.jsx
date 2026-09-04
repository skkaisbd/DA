import React, { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Pencil, Trash2, Check, X, AlertCircle, Database, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';

const BACKEND_URL = import.meta.env.REACT_APP_BACKEND_URL || process.env.REACT_APP_BACKEND_URL;

export default function EmployeeExpenseGLMappingModule() {
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [editingMapping, setEditingMapping] = useState(null);
  const [coaAccounts, setCoaAccounts] = useState([]);
  
  const [formData, setFormData] = useState({
    category: '',
    gl_account_code: '',
    gl_account_name: '',
    is_active: true,
  });

  useEffect(() => {
    fetchMappings();
    fetchCOA();
  }, []);

  const fetchMappings = async () => {
    try {
      const token = localStorage.getItem('erp_token');
      const res = await fetch(`${BACKEND_URL}/api/hr/expenses/gl-mappings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMappings(data.items || []);
      }
    } catch (err) {
      console.error('Fetch mappings error:', err);
      toast.error('Gagal memuat data GL mapping');
    } finally {
      setLoading(false);
    }
  };

  const fetchCOA = async () => {
    try {
      const token = localStorage.getItem('erp_token');
      // FASE 20 — dulu '/api/finance/coa' (tidak pernah ada ⇒ 404 senyap, dropdown
      // akun GL selalu kosong sehingga mapping tak bisa dibuat). SSOT COA ada di
      // '/api/rahaza/coa/accounts' dan membalas ARRAY polos (bukan {items}).
      const res = await fetch(`${BACKEND_URL}/api/rahaza/coa/accounts`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCoaAccounts(Array.isArray(data) ? data : data.items || []);
      }
    } catch (err) {
      console.error('Fetch COA error:', err);
    }
  };

  const handleCreate = () => {
    setEditingMapping(null);
    setFormData({ category: '', gl_account_code: '', gl_account_name: '', is_active: true });
    setShowDialog(true);
  };

  const handleEdit = (mapping) => {
    setEditingMapping(mapping);
    setFormData({
      category: mapping.category,
      gl_account_code: mapping.gl_account_code,
      gl_account_name: mapping.gl_account_name,
      is_active: mapping.is_active,
    });
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!formData.category || !formData.gl_account_code || !formData.gl_account_name) {
      toast.error('Semua field wajib diisi');
      return;
    }

    try {
      const token = localStorage.getItem('erp_token');
      const url = editingMapping 
        ? `${BACKEND_URL}/api/hr/expenses/gl-mappings/${editingMapping.id}`
        : `${BACKEND_URL}/api/hr/expenses/gl-mappings`;
      
      const method = editingMapping ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      const data = await res.json();

      if (res.ok) {
        toast.success(editingMapping ? 'Mapping berhasil diupdate' : 'Mapping berhasil dibuat');
        setShowDialog(false);
        fetchMappings();
      } else {
        toast.error(data.detail || 'Gagal menyimpan mapping');
      }
    } catch (err) {
      console.error('Save mapping error:', err);
      toast.error('Terjadi kesalahan saat menyimpan');
    }
  };

  const handleDelete = async (mapping) => {
    if (!window.confirm(`Hapus mapping ${mapping.category}?`)) return;

    try {
      const token = localStorage.getItem('erp_token');
      const res = await fetch(`${BACKEND_URL}/api/hr/expenses/gl-mappings/${mapping.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        toast.success('Mapping berhasil dihapus');
        fetchMappings();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Gagal menghapus mapping');
      }
    } catch (err) {
      console.error('Delete mapping error:', err);
      toast.error('Terjadi kesalahan saat menghapus');
    }
  };

  const handleAccountSelect = (code) => {
    const account = coaAccounts.find(a => a.code === code);
    if (account) {
      setFormData(prev => ({
        ...prev,
        gl_account_code: code,
        gl_account_name: account.name,
      }));
    }
  };

  const handleSeedDefault = async () => {
    setSeeding(true);
    try {
      const token = localStorage.getItem('erp_token');
      const res = await fetch(`${BACKEND_URL}/api/hr/expenses/gl-mappings/seed-default`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        toast.success(`${data.message}`);
        await fetchMappings();
      } else {
        toast.error(data.detail || 'Gagal seed mapping');
      }
    } catch (err) {
      toast.error('Koneksi bermasalah');
    } finally {
      setSeeding(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Memuat data...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="gl-mapping-admin-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">GL Mapping Configuration</h1>
          <p className="text-muted-foreground mt-1">
            Konfigurasi mapping kategori expense ke GL account code
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleSeedDefault}
            disabled={seeding}
            data-testid="seed-gl-mapping-btn"
          >
            {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Database className="h-4 w-4 mr-2" />}
            Seed Default Mapping
          </Button>
          <Button onClick={handleCreate} data-testid="create-mapping-btn">
            <Plus className="h-4 w-4 mr-2" />
            Tambah Mapping
          </Button>
        </div>
      </div>

      {/* Info Alert */}
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Mapping ini digunakan untuk split posting GL saat settlement. Jika kategori tidak ada mapping, 
          sistem akan menggunakan default account <strong>6-3400 (Biaya Perjalanan Dinas)</strong>.
        </AlertDescription>
      </Alert>

      {/* Mappings Table */}
      <Card>
        <CardHeader>
          <CardTitle>Daftar GL Mapping</CardTitle>
          <CardDescription>
            Total {mappings.length} mapping terdaftar
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kategori Expense</TableHead>
                <TableHead>GL Account Code</TableHead>
                <TableHead>Nama Account</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mappings.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    Belum ada mapping. Klik "Tambah Mapping" untuk membuat mapping baru.
                  </TableCell>
                </TableRow>
              ) : (
                mappings.map((mapping) => (
                  <TableRow key={mapping.id} data-testid={`mapping-row-${mapping.id}`}>
                    <TableCell className="font-medium">{mapping.category}</TableCell>
                    <TableCell>
                      <code className="text-sm bg-muted px-2 py-1 rounded">
                        {mapping.gl_account_code}
                      </code>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{mapping.gl_account_name}</TableCell>
                    <TableCell>
                      {mapping.is_active ? (
                        <Badge variant="default" className="bg-green-600">
                          <Check className="h-3 w-3 mr-1" />
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="secondary">
                          <X className="h-3 w-3 mr-1" />
                          Inactive
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => handleEdit(mapping)}
                          data-testid={`edit-mapping-${mapping.id}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => handleDelete(mapping)}
                          data-testid={`delete-mapping-${mapping.id}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingMapping ? 'Edit GL Mapping' : 'Tambah GL Mapping Baru'}
            </DialogTitle>
            <DialogDescription>
              Mapping kategori expense ke GL account untuk posting otomatis
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="category">Kategori Expense</Label>
              <Input
                id="category"
                placeholder="e.g., Transportasi, Konsumsi, Akomodasi"
                value={formData.category}
                onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
                data-testid="mapping-category-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="gl_account">GL Account</Label>
              <SmartNativeSelect
                id="gl_account"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={formData.gl_account_code}
                onChange={(e) => handleAccountSelect(e.target.value)}
                data-testid="mapping-account-select"
              >
                <option value="">-- Pilih GL Account --</option>
                {coaAccounts
                  .filter(a => a.code.startsWith('6-') || a.code.startsWith('5-'))
                  .map(acc => (
                    <option key={acc.code} value={acc.code}>
                      {acc.code} - {acc.name}
                    </option>
                  ))}
              </SmartNativeSelect>
            </div>

            <div className="space-y-2">
              <Label htmlFor="gl_name">Nama Account</Label>
              <Input
                id="gl_name"
                value={formData.gl_account_name}
                onChange={(e) => setFormData(prev => ({ ...prev, gl_account_name: e.target.value }))}
                placeholder="Nama GL account"
                data-testid="mapping-account-name-input"
              />
            </div>

            <div className="flex items-center space-x-2">
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_active: checked }))}
                data-testid="mapping-active-switch"
              />
              <Label htmlFor="is_active">Active</Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              Batal
            </Button>
            <Button onClick={handleSave} data-testid="save-mapping-btn">
              {editingMapping ? 'Update' : 'Simpan'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
