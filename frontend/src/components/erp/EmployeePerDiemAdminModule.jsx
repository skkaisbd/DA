/**
 * Employee Per Diem Admin Module
 * CV. Dewi Aditya — Employee Expense Management (EEM)
 *
 * Admin/HR dapat mengkonfigurasi tarif uang harian (per diem) per tipe destinasi.
 */
import { useState, useEffect, useCallback } from 'react';
import { Settings2, RefreshCw, Plus, Edit2, Check, X, AlertCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import { PageHeader } from './moduleAtoms';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = formatRupiah;

const DEST_TYPES = [
  { value: 'dalam_kota',  label: 'Dalam Kota',  emoji: '🏙️', description: 'Perjalanan dalam kota yang sama' },
  { value: 'luar_kota',   label: 'Luar Kota',   emoji: '🚗', description: 'Perjalanan ke kota/provinsi lain' },
  { value: 'luar_negeri', label: 'Luar Negeri', emoji: '✈️', description: 'Perjalanan ke luar negeri' },
];

function RateCard({ rate, onEdit }) {
  const dt = DEST_TYPES.find(d => d.value === rate.destination_type) || {};
  const isDefault = rate.is_default;

  return (
    <div className={`rounded-xl border p-5 space-y-4 ${
      isDefault ? 'border-dashed border-muted-foreground/50 bg-muted/20' : 'bg-card shadow-sm'
    }`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{dt.emoji}</span>
          <div>
            <h3 className="font-semibold">{rate.label || dt.label}</h3>
            <p className="text-xs text-muted-foreground">{dt.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isDefault && (
            <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full">Default</span>
          )}
          {rate.is_active === false && (
            <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded-full">Nonaktif</span>
          )}
          <Button size="sm" variant="outline" onClick={() => onEdit(rate)} className="h-7">
            <Edit2 className="w-3.5 h-3.5 mr-1" />{isDefault ? 'Konfigurasi' : 'Edit'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="text-center rounded-lg bg-blue-50 dark:bg-blue-950/30 p-3">
          <div className="text-xs text-muted-foreground mb-1">Uang Harian</div>
          <div className="text-lg font-bold text-blue-700 dark:text-blue-300">
            {fmt(rate.daily_rate)}
          </div>
          <div className="text-xs text-muted-foreground">/hari</div>
        </div>
        <div className="text-center rounded-lg bg-green-50 dark:bg-green-950/30 p-3">
          <div className="text-xs text-muted-foreground mb-1">Uang Makan</div>
          <div className="text-lg font-bold text-green-700 dark:text-green-300">
            {fmt(rate.meal_allowance)}
          </div>
          <div className="text-xs text-muted-foreground">/hari</div>
        </div>
        <div className="text-center rounded-lg bg-orange-50 dark:bg-orange-950/30 p-3">
          <div className="text-xs text-muted-foreground mb-1">Transport</div>
          <div className="text-lg font-bold text-orange-700 dark:text-orange-300">
            {fmt(rate.transport_allowance)}
          </div>
          <div className="text-xs text-muted-foreground">/hari</div>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Total per hari:</span>
        <span className="font-bold text-base">
          {fmt((rate.daily_rate || 0) + (rate.meal_allowance || 0) + (rate.transport_allowance || 0))}
        </span>
      </div>

      {rate.effective_date && (
        <p className="text-xs text-muted-foreground">Berlaku sejak: {rate.effective_date}</p>
      )}
      {rate.notes && (
        <p className="text-xs text-muted-foreground italic">{rate.notes}</p>
      )}
    </div>
  );
}

function RateFormDialog({ rate, onClose, token, onSaved }) {
  const dt = DEST_TYPES.find(d => d.value === rate.destination_type) || {};
  const [form, setForm] = useState({
    daily_rate: rate.daily_rate || 0,
    meal_allowance: rate.meal_allowance || 0,
    transport_allowance: rate.transport_allowance || 0,
    effective_date: rate.effective_date || new Date().toISOString().slice(0, 10),
    notes: rate.notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const handleSave = async () => {
    if (form.daily_rate <= 0) { setError('Uang harian harus lebih dari 0'); return; }
    setSaving(true); setError('');
    try {
      const body = {
        destination_type: rate.destination_type,
        label: dt.label,
        daily_rate: parseFloat(form.daily_rate),
        meal_allowance: parseFloat(form.meal_allowance) || 0,
        transport_allowance: parseFloat(form.transport_allowance) || 0,
        effective_date: form.effective_date,
        notes: form.notes,
      };
      const method = rate.is_default || !rate.id ? 'POST' : 'PUT';
      const url = rate.is_default || !rate.id
        ? `${API}/api/hr/expenses/per-diem-rates`
        : `${API}/api/hr/expenses/per-diem-rates/${rate.id}`;
      const r = await fetch(url, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal simpan');
      onSaved();
      onClose();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 p-3 rounded-lg bg-muted">
        <span className="text-2xl">{dt.emoji}</span>
        <div>
          <p className="font-semibold">{dt.label}</p>
          <p className="text-xs text-muted-foreground">{dt.description}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <div className="space-y-1">
          <label className="text-sm font-medium">Uang Harian (Rp/hari) *</label>
          <Input type="number" value={form.daily_rate} onChange={e => set('daily_rate', e.target.value)} placeholder="misal: 300000" />
          <p className="text-xs text-muted-foreground">Biaya hidup harian karyawan selama dinas</p>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Uang Makan (Rp/hari)</label>
          <Input type="number" value={form.meal_allowance} onChange={e => set('meal_allowance', e.target.value)} placeholder="misal: 75000" />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Tunjangan Transport (Rp/hari)</label>
          <Input type="number" value={form.transport_allowance} onChange={e => set('transport_allowance', e.target.value)} placeholder="misal: 100000" />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Berlaku Sejak</label>
          <Input type="date" value={form.effective_date} onChange={e => set('effective_date', e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Catatan</label>
          <Input placeholder="opsional" value={form.notes} onChange={e => set('notes', e.target.value)} />
        </div>
      </div>

      {/* Preview */}
      <div className="rounded-lg bg-blue-50 dark:bg-blue-950/30 p-3">
        <p className="text-xs font-medium text-blue-800 dark:text-blue-300 mb-1">Preview Total Per Hari</p>
        <p className="text-xl font-bold text-blue-700 dark:text-blue-300">
          {fmt((parseFloat(form.daily_rate) || 0) + (parseFloat(form.meal_allowance) || 0) + (parseFloat(form.transport_allowance) || 0))}
        </p>
      </div>

      {error && <div className="text-sm text-red-600 flex items-center gap-1"><AlertCircle className="w-4 h-4" />{error}</div>}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={handleSave} disabled={saving}>{saving ? 'Menyimpan...' : 'Simpan Tarif'}</Button>
      </DialogFooter>
    </div>
  );
}

export default function EmployeePerDiemAdminModule({ token, user }) {
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const headers = { Authorization: `Bearer ${token}` };

  const fetchRates = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/hr/expenses/per-diem-rates`, { headers });
      const d = await r.json();
      setRates(Array.isArray(d.items) ? d.items : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchRates(); }, [fetchRates]);

  return (
    <div className="space-y-5" data-testid="per-diem-admin-page">
      <PageHeader
        icon={Settings2}
        eyebrow="SDM · Konfigurasi"
        title="Konfigurasi Per Diem"
        subtitle="Atur tarif uang harian karyawan saat melakukan perjalanan dinas per tipe destinasi."
        actions={
          <Button variant="ghost" onClick={fetchRates} className="h-9 border">
            <RefreshCw className="w-3.5 h-3.5 mr-1" />Muat Ulang
          </Button>
        }
      />

      <div className="rounded-lg border bg-blue-50 dark:bg-blue-950/30 p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-800 dark:text-blue-300">
          <p className="font-medium">Tentang Per Diem</p>
          <p className="mt-1">Per Diem adalah kompensasi harian yang diberikan kepada karyawan yang melakukan perjalanan dinas.
            Tarif ini digunakan untuk menghitung otomatis estimasi uang harian saat karyawan mengajukan perjalanan dinas.</p>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-muted-foreground">
          <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
          Memuat konfigurasi...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {rates.map(rate => (
            <RateCard key={rate.destination_type} rate={rate} onEdit={setEditing} />
          ))}
        </div>
      )}

      <Dialog open={!!editing} onOpenChange={v => !v && setEditing(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings2 className="w-5 h-5 text-blue-600" />
              Konfigurasi Tarif Per Diem
            </DialogTitle>
          </DialogHeader>
          {editing && (
            <RateFormDialog
              rate={editing}
              token={token}
              onClose={() => setEditing(null)}
              onSaved={fetchRates}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
