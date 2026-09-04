/**
 * CreateLoanDialog — Pinjamkan 1 unit aset (ACC-3).
 *
 * Kenapa 1 unit (bukan qty): peminjaman itu domain ASET — yang dipinjam adalah
 * unit fisik ber-nomor (AST-xx-2026-0001), bukan barang habis pakai. Dropdown
 * hanya menampilkan aset yang benar-benar SIAP dipinjam (endpoint
 * /api/assets/loanable-assets sudah mengecualikan aset yang sedang dipinjam,
 * dalam pemeliharaan, atau sudah dilepas).
 */
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { PackageSearch } from 'lucide-react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { apicall } from '../utils';

const today = () => new Date().toISOString().slice(0, 10);

export function CreateLoanDialog({ open, onClose, token, onCreated }) {
  const [assets, setAssets] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loadingRef, setLoadingRef] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [form, setForm] = useState({
    asset_id: '', borrower_id: '', borrower_name: '', borrower_divisi: '',
    purpose: '', loan_date: today(), expected_return_date: '', notes: '',
  });

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const loadRef = useCallback(async () => {
    setLoadingRef(true);
    try {
      const [as, emp] = await Promise.all([
        apicall('GET', '/api/assets/loanable-assets', token),
        apicall('GET', '/api/rahaza/employees?active_only=true&limit=500', token).catch(() => ({ items: [] })),
      ]);
      setAssets(Array.isArray(as) ? as : []);
      setEmployees(Array.isArray(emp) ? emp : (emp.items || []));
    } catch (e) {
      setErr(e.message || 'Gagal memuat daftar aset');
    } finally { setLoadingRef(false); }
  }, [token]);

  useEffect(() => {
    if (!open) return;
    setErr('');
    setForm({
      asset_id: '', borrower_id: '', borrower_name: '', borrower_divisi: '',
      purpose: '', loan_date: today(), expected_return_date: '', notes: '',
    });
    loadRef();
  }, [open, loadRef]);

  // Pilih karyawan → isi otomatis nama + divisi (tetap bisa diubah manual
  // supaya peminjam eksternal/vendor juga bisa dicatat).
  const pickEmployee = (id) => {
    const e = employees.find(x => x.id === id);
    setForm(p => ({
      ...p,
      borrower_id: id,
      borrower_name: e ? e.name : p.borrower_name,
      borrower_divisi: e ? (e.department || p.borrower_divisi) : p.borrower_divisi,
    }));
  };

  const submit = async () => {
    // Kumpulkan SEMUA field wajib yang kosong sekaligus supaya user tidak
    // menebak satu-satu (submit → perbaiki → submit → error lain).
    const missing = [];
    if (!form.asset_id) missing.push('Aset');
    if (!form.borrower_name.trim()) missing.push('Nama Peminjam');
    if (missing.length) {
      setErr(`${missing.join(' & ')} wajib diisi.`);
      return;
    }
    setSaving(true); setErr('');
    try {
      const d = await apicall('POST', '/api/assets/loans', token, form);
      toast.success(`Peminjaman ${d.loan_number} dicatat`);
      onCreated?.(d);
      onClose();
    } catch (e) {
      setErr(e.message || 'Gagal mencatat peminjaman');
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg" data-testid="asset-loan-create-dialog">
        <DialogHeader>
          <DialogTitle>Pinjamkan Aset</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Catat alat/aset yang dibawa keluar. Aset akan berstatus <strong>Dipinjam</strong> sampai dikembalikan.
          </p>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Aset *</label>
            <SmartNativeSelect value={form.asset_id} onChange={e => set('asset_id', e.target.value)}
              className="w-full" data-testid="asset-loan-asset">
              <option value="">{loadingRef ? 'Memuat aset...' : '— pilih aset —'}</option>
              {assets.map(a => (
                <option key={a.id} value={a.id}>
                  {a.asset_number} · {a.name}{a.category_name ? ` (${a.category_name})` : ''}
                </option>
              ))}
            </SmartNativeSelect>
            {!loadingRef && assets.length === 0 && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1 flex items-start gap-1">
                <PackageSearch className="w-3 h-3 mt-0.5 flex-shrink-0" />
                Tidak ada aset yang siap dipinjam. Tambah aset baru di tab "Aset", atau kembalikan aset
                yang sedang dipinjam / selesaikan pemeliharaannya.
              </p>
            )}
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Peminjam (karyawan)</label>
            <SmartNativeSelect value={form.borrower_id} onChange={e => pickEmployee(e.target.value)}
              className="w-full" data-testid="asset-loan-employee">
              <option value="">— pilih karyawan (opsional) —</option>
              {employees.map(e => (
                <option key={e.id} value={e.id}>
                  {e.employee_code ? `${e.employee_code} · ` : ''}{e.name}{e.department ? ` (${e.department})` : ''}
                </option>
              ))}
            </SmartNativeSelect>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Nama Peminjam *</label>
              <Input value={form.borrower_name} onChange={e => set('borrower_name', e.target.value)}
                placeholder="Nama lengkap / vendor" data-testid="asset-loan-borrower" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Divisi / Unit</label>
              <Input value={form.borrower_divisi} onChange={e => set('borrower_divisi', e.target.value)}
                placeholder="mis. Produksi" data-testid="asset-loan-divisi" />
            </div>
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Tujuan Pemakaian</label>
            <Input value={form.purpose} onChange={e => set('purpose', e.target.value)}
              placeholder="mis. perbaikan mesin jahit line 2" data-testid="asset-loan-purpose" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Tanggal Pinjam *</label>
              <Input type="date" value={form.loan_date} onChange={e => set('loan_date', e.target.value)}
                data-testid="asset-loan-date" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Target Kembali</label>
              <Input type="date" value={form.expected_return_date}
                onChange={e => set('expected_return_date', e.target.value)}
                data-testid="asset-loan-expected" />
            </div>
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Catatan</label>
            <Input value={form.notes} onChange={e => set('notes', e.target.value)}
              placeholder="kondisi saat keluar, kelengkapan, dll." data-testid="asset-loan-notes" />
          </div>

          {err && (
            <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-3 py-2"
              data-testid="asset-loan-error">{err}</div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving} data-testid="asset-loan-submit">
            {saving ? 'Menyimpan...' : 'Catat Peminjaman'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
