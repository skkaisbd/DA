/**
 * SupplierMasterModule — MASTER SUPPLIER (SSOT Pengadaan)
 *
 * Sebelum modul ini, PO memakai `vendor_name` TEKS BEBAS sehingga:
 *   · satu supplier dengan dua ejaan memecah penilaian supplier,
 *   · termin bayar / rekening / NPWP harus diketik ulang tiap PO,
 *   · tidak ada daftar harga sehingga harga PO ditebak manual.
 *
 * Modul ini menyediakan: CRUD lengkap, kontak/PIC ganda, rekening bank ganda,
 * kategori barang, lead time, daftar harga per SATUAN BELI (dengan konversi
 * otomatis ke satuan dasar), scorecard, dan tarik-data supplier dari dokumen lama.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Ban, Building2, CheckCircle2, Contact, CreditCard, Download,
  Eye, Landmark, Pencil, Plus, RefreshCw, Search, Star, Tag, Trash2, Truck,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import Modal from '../Modal';
import { toast } from 'sonner';
import {
  CATEGORY_LABEL, EP, PAYMENT_TERM_LABEL, apiDelete, apiGet, apiPost, apiPut,
  fmtDate, fmtNum, fmtRp,
} from './procApi';

const EMPTY_FORM = {
  name: '', code: '', npwp: '', tax_name: '', tax_type: 'ppn',
  address: '', city: '', province: '', postal_code: '', country: 'Indonesia',
  phone: '', email: '', website: '',
  payment_terms: 'net30', currency: 'IDR',
  lead_time_days: 0, min_order_value: 0,
  categories: [], material_types: [],
  contacts: [], bank_accounts: [],
  rating_manual: '', notes: '', is_active: true,
};

function GradePill({ grade }) {
  const map = {
    'A+': 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-400/15 dark:text-emerald-300 dark:border-emerald-400/30',
    A: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-400/15 dark:text-emerald-300 dark:border-emerald-400/30',
    B: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-400/15 dark:text-blue-300 dark:border-blue-400/30',
    C: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-400/15 dark:text-amber-300 dark:border-amber-400/30',
    D: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-400/15 dark:text-red-300 dark:border-red-400/30',
  };
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${map[grade] || 'bg-muted text-muted-foreground border-border'}`}>
      {grade || '-'}
    </span>
  );
}

function ActivePill({ active }) {
  return active !== false ? (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-400/15 dark:text-emerald-300 dark:border-emerald-400/30">
      <CheckCircle2 className="w-3 h-3" /> Aktif
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-muted text-muted-foreground border-border">
      <Ban className="w-3 h-3" /> Nonaktif
    </span>
  );
}

// ── Form supplier ───────────────────────────────────────────────────────────
function SupplierForm({ token, meta, initial, onClose, onSaved }) {
  const isEdit = !!initial?.id;
  const [f, setF] = useState(() => ({ ...EMPTY_FORM, ...(initial || {}) }));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggleCat = (c) => setF((p) => ({
    ...p,
    categories: p.categories?.includes(c)
      ? p.categories.filter((x) => x !== c)
      : [...(p.categories || []), c],
  }));

  const addContact = () => setF((p) => ({
    ...p,
    contacts: [...(p.contacts || []), { name: '', position: '', phone: '', email: '', is_primary: !(p.contacts || []).length }],
  }));
  const setContact = (i, k, v) => setF((p) => ({
    ...p, contacts: p.contacts.map((c, idx) => (idx === i ? { ...c, [k]: v } : c)),
  }));
  const rmContact = (i) => setF((p) => ({ ...p, contacts: p.contacts.filter((_, idx) => idx !== i) }));

  const addBank = () => setF((p) => ({
    ...p,
    bank_accounts: [...(p.bank_accounts || []), { bank_name: '', account_number: '', account_holder: '', branch: '', is_primary: !(p.bank_accounts || []).length }],
  }));
  const setBank = (i, k, v) => setF((p) => ({
    ...p, bank_accounts: p.bank_accounts.map((b, idx) => (idx === i ? { ...b, [k]: v } : b)),
  }));
  const rmBank = (i) => setF((p) => ({ ...p, bank_accounts: p.bank_accounts.filter((_, idx) => idx !== i) }));

  const save = async () => {
    setErr('');
    if (!f.name?.trim()) { setErr('Nama supplier wajib diisi.'); return; }
    setSaving(true);
    try {
      const payload = {
        ...f,
        lead_time_days: Number(f.lead_time_days || 0),
        min_order_value: Number(f.min_order_value || 0),
        rating_manual: f.rating_manual === '' ? null : Number(f.rating_manual),
      };
      if (isEdit) delete payload.code;
      const out = isEdit
        ? await apiPut(token, EP.supplier(initial.id), payload)
        : await apiPost(token, EP.suppliers(), payload);
      toast.success(isEdit ? 'Supplier diperbarui' : `Supplier ${out?.code || ''} dibuat`);
      onSaved?.(out);
      onClose();
    } catch (e) {
      setErr(e.message);
      toast.error(e.message);
    } finally { setSaving(false); }
  };

  return (
    <Modal onClose={onClose} title={isEdit ? `Ubah Supplier: ${initial.code}` : 'Tambah Supplier Baru'} size="2xl">
      <div className="space-y-4">
        {err && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm"
               data-testid="supplier-form-error">
            {err}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium mb-1">Nama Supplier *</label>
            <GlassInput value={f.name} onChange={(e) => set('name', e.target.value)}
                        placeholder="PT Benang Jaya Abadi" data-testid="supplier-form-name" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">NPWP</label>
            <GlassInput value={f.npwp} onChange={(e) => set('npwp', e.target.value)}
                        placeholder="01.234.567.8-901.000" data-testid="supplier-form-npwp" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Nama Wajib Pajak</label>
            <GlassInput value={f.tax_name} onChange={(e) => set('tax_name', e.target.value)}
                        placeholder="Sesuai NPWP" data-testid="supplier-form-taxname" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Status Pajak</label>
            <SmartNativeSelect value={f.tax_type} onChange={(e) => set('tax_type', e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="supplier-form-taxtype">
              {(meta?.tax_types || [{ value: 'ppn', label: 'PKP (kena PPN)' }, { value: 'non_ppn', label: 'Non-PKP' }])
                .map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </SmartNativeSelect>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Termin Bayar</label>
            <SmartNativeSelect value={f.payment_terms} onChange={(e) => set('payment_terms', e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="supplier-form-terms">
              {(meta?.payment_terms || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </SmartNativeSelect>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Mata Uang</label>
            <SmartNativeSelect value={f.currency} onChange={(e) => set('currency', e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="supplier-form-currency">
              {(meta?.currencies || ['IDR']).map((c) => <option key={c} value={c}>{c}</option>)}
            </SmartNativeSelect>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Lead Time (hari)</label>
            <GlassInput type="number" min="0" value={f.lead_time_days}
                        onChange={(e) => set('lead_time_days', e.target.value)}
                        data-testid="supplier-form-leadtime" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Minimum Order (Rp)</label>
            <GlassInput type="number" min="0" value={f.min_order_value}
                        onChange={(e) => set('min_order_value', e.target.value)}
                        data-testid="supplier-form-minorder" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Rating Manual (1-5)</label>
            <GlassInput type="number" min="1" max="5" value={f.rating_manual ?? ''}
                        onChange={(e) => set('rating_manual', e.target.value)}
                        data-testid="supplier-form-rating" />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1.5">Kategori Barang / Jasa yang Disuplai</label>
          <div className="flex flex-wrap gap-1.5">
            {(meta?.categories || Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label })))
              .map((c) => {
                const on = f.categories?.includes(c.value);
                return (
                  <button key={c.value} type="button" onClick={() => toggleCat(c.value)}
                    data-testid={`supplier-form-cat-${c.value}`}
                    className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${on
                      ? 'bg-[hsl(var(--primary)/0.15)] border-[hsl(var(--primary)/0.4)] text-[hsl(var(--primary))] font-semibold'
                      : 'bg-[var(--input-surface)] border-[var(--glass-border)] text-muted-foreground hover:bg-[var(--glass-bg-hover)]'}`}>
                    {c.label}
                  </button>
                );
              })}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-3">
            <label className="block text-xs font-medium mb-1">Alamat</label>
            <textarea value={f.address} onChange={(e) => set('address', e.target.value)} rows="2"
              className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
              placeholder="Jl. Industri Raya No. 12" data-testid="supplier-form-address" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Kota</label>
            <GlassInput value={f.city} onChange={(e) => set('city', e.target.value)} data-testid="supplier-form-city" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Provinsi</label>
            <GlassInput value={f.province} onChange={(e) => set('province', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Kode Pos</label>
            <GlassInput value={f.postal_code} onChange={(e) => set('postal_code', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Telepon</label>
            <GlassInput value={f.phone} onChange={(e) => set('phone', e.target.value)}
                        placeholder="022-1234567" data-testid="supplier-form-phone" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Email</label>
            <GlassInput type="email" value={f.email} onChange={(e) => set('email', e.target.value)}
                        placeholder="sales@supplier.co.id" data-testid="supplier-form-email" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Website</label>
            <GlassInput value={f.website} onChange={(e) => set('website', e.target.value)} />
          </div>
        </div>

        {/* Kontak / PIC */}
        <div className="border-t border-[var(--glass-border)] pt-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold flex items-center gap-1.5">
              <Contact className="w-4 h-4" /> Kontak / PIC
            </h4>
            <Button size="sm" variant="secondary" onClick={addContact} data-testid="supplier-form-add-contact">
              <Plus className="w-3 h-3 mr-1" /> Tambah Kontak
            </Button>
          </div>
          {!f.contacts?.length && <p className="text-xs text-muted-foreground py-1">Belum ada kontak.</p>}
          {(f.contacts || []).map((c, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
              <GlassInput className="col-span-3" placeholder="Nama" value={c.name}
                          onChange={(e) => setContact(i, 'name', e.target.value)}
                          data-testid={`supplier-contact-name-${i}`} />
              <GlassInput className="col-span-3" placeholder="Jabatan" value={c.position}
                          onChange={(e) => setContact(i, 'position', e.target.value)} />
              <GlassInput className="col-span-2" placeholder="Telepon" value={c.phone}
                          onChange={(e) => setContact(i, 'phone', e.target.value)} />
              <GlassInput className="col-span-3" placeholder="Email" value={c.email}
                          onChange={(e) => setContact(i, 'email', e.target.value)} />
              <Button variant="ghost" size="sm" className="col-span-1" onClick={() => rmContact(i)}
                      data-testid={`supplier-contact-remove-${i}`}>
                <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
              </Button>
            </div>
          ))}
        </div>

        {/* Rekening bank */}
        <div className="border-t border-[var(--glass-border)] pt-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold flex items-center gap-1.5">
              <Landmark className="w-4 h-4" /> Rekening Bank
            </h4>
            <Button size="sm" variant="secondary" onClick={addBank} data-testid="supplier-form-add-bank">
              <Plus className="w-3 h-3 mr-1" /> Tambah Rekening
            </Button>
          </div>
          {!f.bank_accounts?.length && <p className="text-xs text-muted-foreground py-1">Belum ada rekening.</p>}
          {(f.bank_accounts || []).map((b, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
              <GlassInput className="col-span-3" placeholder="Bank" value={b.bank_name}
                          onChange={(e) => setBank(i, 'bank_name', e.target.value)}
                          data-testid={`supplier-bank-name-${i}`} />
              <GlassInput className="col-span-3" placeholder="No. Rekening" value={b.account_number}
                          onChange={(e) => setBank(i, 'account_number', e.target.value)}
                          data-testid={`supplier-bank-account-${i}`} />
              <GlassInput className="col-span-3" placeholder="Nama Pemilik" value={b.account_holder}
                          onChange={(e) => setBank(i, 'account_holder', e.target.value)} />
              <GlassInput className="col-span-2" placeholder="Cabang" value={b.branch}
                          onChange={(e) => setBank(i, 'branch', e.target.value)} />
              <Button variant="ghost" size="sm" className="col-span-1" onClick={() => rmBank(i)}>
                <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
              </Button>
            </div>
          ))}
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Catatan</label>
          <textarea value={f.notes} onChange={(e) => set('notes', e.target.value)} rows="2"
            className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-foreground text-sm"
            data-testid="supplier-form-notes" />
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t border-[var(--glass-border)]">
          <Button variant="secondary" onClick={onClose}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="supplier-form-submit">
            {saving ? 'Menyimpan...' : (isEdit ? 'Simpan Perubahan' : 'Simpan Supplier')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Detail + daftar harga + scorecard ───────────────────────────────────────
function SupplierDetail({ token, supplierId, materials, onClose, onChanged }) {
  const [sup, setSup] = useState(null);
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('info');
  const [priceForm, setPriceForm] = useState({ material_id: '', uom: '', price: '', moq: '', lead_time_days: '', notes: '' });
  const [uomOpts, setUomOpts] = useState(null);
  const [savingPrice, setSavingPrice] = useState(false);
  const [priceErr, setPriceErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        apiGet(token, EP.supplier(supplierId)),
        apiGet(token, EP.supplierScorecard(supplierId)).catch(() => null),
      ]);
      setSup(s);
      setCard(c);
    } catch (e) {
      toast.error(`Gagal memuat supplier: ${e.message}`);
    } finally { setLoading(false); }
  }, [token, supplierId]);

  useEffect(() => { load(); }, [load]);

  // Ambil daftar satuan sah untuk material terpilih (server yang menentukan)
  useEffect(() => {
    if (!priceForm.material_id) { setUomOpts(null); return; }
    let alive = true;
    apiGet(token, EP.uomOptions(priceForm.material_id))
      .then((r) => {
        if (!alive) return;
        const o = (r?.options || {})[priceForm.material_id] || null;
        setUomOpts(o);
        setPriceForm((p) => ({ ...p, uom: p.uom || o?.base_unit || '' }));
      })
      .catch(() => setUomOpts(null));
    return () => { alive = false; };
  }, [token, priceForm.material_id]);

  const factor = useMemo(() => {
    if (!uomOpts) return 1;
    const row = (uomOpts.units || []).find((u) => u.unit === priceForm.uom);
    return row ? Number(row.factor_to_base) : 1;
  }, [uomOpts, priceForm.uom]);

  const addPrice = async () => {
    setPriceErr('');
    if (!priceForm.material_id) { setPriceErr('Pilih material dulu.'); return; }
    if (!(Number(priceForm.price) > 0)) { setPriceErr('Harga harus lebih dari 0.'); return; }
    setSavingPrice(true);
    try {
      await apiPost(token, EP.priceList(supplierId), {
        material_id: priceForm.material_id,
        uom: priceForm.uom || undefined,
        price: Number(priceForm.price),
        moq: Number(priceForm.moq || 0),
        lead_time_days: Number(priceForm.lead_time_days || 0),
        notes: priceForm.notes,
      });
      toast.success('Harga supplier disimpan');
      setPriceForm({ material_id: '', uom: '', price: '', moq: '', lead_time_days: '', notes: '' });
      await load();
      onChanged?.();
    } catch (e) {
      setPriceErr(e.message);
      toast.error(e.message);
    } finally { setSavingPrice(false); }
  };

  const delPrice = async (rowId) => {
    if (!window.confirm('Hapus baris harga ini?')) return;
    try {
      await apiDelete(token, EP.priceRow(supplierId, rowId));
      toast.success('Baris harga dihapus');
      await load();
    } catch (e) { toast.error(e.message); }
  };

  if (loading) {
    return (
      <Modal onClose={onClose} title="Memuat supplier..." size="2xl">
        <div className="flex items-center justify-center h-40">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
        </div>
      </Modal>
    );
  }
  if (!sup) return null;

  const sc = card?.scorecard || {};
  const TABS = [
    { key: 'info', label: 'Informasi' },
    { key: 'price', label: `Daftar Harga (${(sup.price_list || []).length})` },
    { key: 'score', label: 'Penilaian' },
  ];

  return (
    <Modal onClose={onClose} title={`${sup.code} — ${sup.name}`} size="2xl">
      <div className="space-y-4" data-testid="supplier-detail">
        <div className="flex items-center gap-2 flex-wrap">
          <ActivePill active={sup.is_active} />
          <span className="text-xs px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
            {PAYMENT_TERM_LABEL[sup.payment_terms] || sup.payment_terms}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
            {sup.currency}
          </span>
          {sup.source === 'migrated' && (
            <span className="text-xs px-2 py-0.5 rounded-full border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300">
              Dari data lama
            </span>
          )}
          {(sup.categories || []).map((c) => (
            <span key={c} className="text-xs px-2 py-0.5 rounded-full border border-[hsl(var(--primary)/0.3)] bg-[hsl(var(--primary)/0.1)] text-[hsl(var(--primary))]">
              {CATEGORY_LABEL[c] || c}
            </span>
          ))}
        </div>

        <div className="flex gap-1 border-b border-[var(--glass-border)]">
          {TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              data-testid={`supplier-tab-${t.key}`}
              className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${tab === t.key
                ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
                : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'info' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div className="space-y-2">
              <div>
                <div className="text-xs text-muted-foreground">Alamat</div>
                <div>{[sup.address, sup.city, sup.province, sup.postal_code].filter(Boolean).join(', ') || '-'}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">NPWP</div>
                <div className="font-mono text-xs">{sup.npwp || '-'}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Telepon / Email</div>
                <div>{sup.phone || '-'} · {sup.email || '-'}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Lead time / Minimum order</div>
                <div>{sup.lead_time_days || 0} hari · {fmtRp(sup.min_order_value)}</div>
              </div>
              {sup.notes && (
                <div>
                  <div className="text-xs text-muted-foreground">Catatan</div>
                  <div className="text-xs">{sup.notes}</div>
                </div>
              )}
            </div>
            <div className="space-y-3">
              <div>
                <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                  <Contact className="w-3 h-3" /> Kontak
                </div>
                {(sup.contacts || []).length === 0 ? <div className="text-xs">-</div> : (
                  <ul className="space-y-1">
                    {sup.contacts.map((c) => (
                      <li key={c.id || c.name} className="text-xs">
                        <span className="font-medium">{c.name}</span>
                        {c.position && <span className="text-muted-foreground"> · {c.position}</span>}
                        {c.phone && <span className="text-muted-foreground"> · {c.phone}</span>}
                        {c.is_primary && <span className="ml-1 text-[hsl(var(--primary))]">(utama)</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                  <CreditCard className="w-3 h-3" /> Rekening
                </div>
                {(sup.bank_accounts || []).length === 0 ? <div className="text-xs">-</div> : (
                  <ul className="space-y-1">
                    {sup.bank_accounts.map((b) => (
                      <li key={b.id || b.account_number} className="text-xs font-mono">
                        {b.bank_name} {b.account_number} — {b.account_holder}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Rekap PO</div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.keys(sup.po_stats || {}).length === 0 ? (
                    <span className="text-xs">Belum ada PO</span>
                  ) : Object.entries(sup.po_stats).map(([st, n]) => (
                    <span key={st} className="text-[10px] px-2 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
                      {st}: {n}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === 'price' && (
          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                <Tag className="w-4 h-4" /> Tambah Harga
              </h4>
              {priceErr && (
                <div className="mb-2 p-2 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-xs"
                     data-testid="price-form-error">{priceErr}</div>
              )}
              <div className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-12 md:col-span-4">
                  <label className="block text-[11px] font-medium mb-1">Material</label>
                  <SmartNativeSelect value={priceForm.material_id}
                    onChange={(e) => setPriceForm((p) => ({ ...p, material_id: e.target.value, uom: '' }))}
                    className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                    data-testid="price-form-material">
                    <option value="">Pilih material</option>
                    {materials.map((m) => <option key={m.id} value={m.id}>{`${m.code} - ${m.name}`}</option>)}
                  </SmartNativeSelect>
                </div>
                <div className="col-span-4 md:col-span-2">
                  <label className="block text-[11px] font-medium mb-1">Satuan Beli</label>
                  <SmartNativeSelect value={priceForm.uom}
                    onChange={(e) => setPriceForm((p) => ({ ...p, uom: e.target.value }))}
                    disabled={!uomOpts}
                    className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                    data-testid="price-form-uom">
                    {(uomOpts?.units || []).map((u) => (
                      <option key={u.unit} value={u.unit}>{u.label || u.unit}</option>
                    ))}
                  </SmartNativeSelect>
                </div>
                <div className="col-span-4 md:col-span-2">
                  <label className="block text-[11px] font-medium mb-1">Harga / satuan</label>
                  <GlassInput type="number" min="0" value={priceForm.price}
                              onChange={(e) => setPriceForm((p) => ({ ...p, price: e.target.value }))}
                              className="text-right" data-testid="price-form-price" />
                </div>
                <div className="col-span-4 md:col-span-1">
                  <label className="block text-[11px] font-medium mb-1">MOQ</label>
                  <GlassInput type="number" min="0" value={priceForm.moq}
                              onChange={(e) => setPriceForm((p) => ({ ...p, moq: e.target.value }))}
                              className="text-right" data-testid="price-form-moq" />
                </div>
                <div className="col-span-6 md:col-span-1">
                  <label className="block text-[11px] font-medium mb-1">Lead</label>
                  <GlassInput type="number" min="0" value={priceForm.lead_time_days}
                              onChange={(e) => setPriceForm((p) => ({ ...p, lead_time_days: e.target.value }))}
                              className="text-right" />
                </div>
                <div className="col-span-6 md:col-span-2">
                  <Button className="w-full" onClick={addPrice} disabled={savingPrice}
                          data-testid="price-form-submit">
                    {savingPrice ? '...' : 'Simpan Harga'}
                  </Button>
                </div>
              </div>
              {uomOpts && priceForm.uom && Number(priceForm.price) > 0 && (
                <p className="text-[11px] text-muted-foreground mt-2" data-testid="price-form-preview">
                  1 {priceForm.uom} = {fmtNum(factor)} {uomOpts.base_unit} ⇒ harga per satuan dasar{' '}
                  <span className="font-semibold text-foreground">
                    {fmtRp(Number(priceForm.price) / (factor || 1))}
                  </span>{' '}/ {uomOpts.base_unit}
                </p>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                    <th className="pb-2">Material</th>
                    <th className="pb-2 text-right">Harga / Satuan Beli</th>
                    <th className="pb-2 text-right">Per Satuan Dasar</th>
                    <th className="pb-2 text-right">MOQ</th>
                    <th className="pb-2">Berlaku</th>
                    <th className="pb-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody data-testid="supplier-price-list">
                  {(sup.price_list || []).length === 0 && (
                    <tr><td colSpan="6" className="py-6 text-center text-muted-foreground text-xs">
                      Belum ada daftar harga. Tambahkan supaya harga PO terisi otomatis.
                    </td></tr>
                  )}
                  {(sup.price_list || []).map((r) => (
                    <tr key={r.id} className={`border-b border-[var(--glass-border)] ${r.is_active === false ? 'opacity-50' : ''}`}>
                      <td className="py-2">
                        <div className="font-medium text-xs">{r.material_code}</div>
                        <div className="text-[11px] text-muted-foreground line-clamp-1">{r.material_name}</div>
                      </td>
                      <td className="py-2 text-right font-mono text-xs">
                        {fmtRp(r.price)} <span className="text-muted-foreground">/ {r.uom}</span>
                      </td>
                      <td className="py-2 text-right font-mono text-xs">
                        {fmtRp(r.price_base)} <span className="text-muted-foreground">/ {r.base_uom}</span>
                      </td>
                      <td className="py-2 text-right font-mono text-xs">
                        {r.moq ? `${fmtNum(r.moq)} ${r.uom}` : '-'}
                      </td>
                      <td className="py-2 text-xs">
                        {fmtDate(r.valid_from)}{r.valid_to ? ` – ${fmtDate(r.valid_to)}` : ''}
                        {r.is_active === false && <span className="ml-1 text-[10px] text-muted-foreground">(riwayat)</span>}
                      </td>
                      <td className="py-2 text-right">
                        <Button variant="ghost" size="sm" onClick={() => delPrice(r.id)}
                                data-testid={`price-delete-${r.id}`}>
                          <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'score' && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { l: 'Penerimaan diperiksa', v: sc.total_grns ?? 0 },
                { l: 'Tingkat diterima', v: `${fmtNum(sc.accept_rate ?? 0, 2)}%` },
                { l: 'Tingkat cacat', v: `${fmtNum(sc.defect_rate ?? 0, 2)}%` },
                { l: 'Tepat waktu', v: sc.on_time_rate == null ? '-' : `${fmtNum(sc.on_time_rate, 2)}%` },
              ].map((x) => (
                <div key={x.l} className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
                  <div className="text-[11px] text-muted-foreground mb-1">{x.l}</div>
                  <div className="text-lg font-bold tabular-nums">{x.v}</div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Grade kualitas:</span>
              <GradePill grade={sc.quality_grade} />
              {sup.rating_manual && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                  <Star className="w-3 h-3" /> Rating manual {sup.rating_manual}/5
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              Total diterima {fmtNum(sc.total_received ?? 0)} · diterima baik {fmtNum(sc.total_accepted ?? 0)} ·
              ditolak {fmtNum(sc.total_rejected ?? 0)} (satuan dasar material).
            </div>
            {(card?.po_by_status || null) && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                      <th className="pb-2">Status PO</th>
                      <th className="pb-2 text-right">Jumlah</th>
                      <th className="pb-2 text-right">Nilai</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(card.po_by_status).map(([st, v]) => (
                      <tr key={st} className="border-b border-[var(--glass-border)]">
                        <td className="py-2 text-xs">{st}</td>
                        <td className="py-2 text-xs text-right tabular-nums">{v.count}</td>
                        <td className="py-2 text-xs text-right tabular-nums">{fmtRp(v.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

// ── Modal tarik data supplier dari dokumen lama ─────────────────────────────
function MigrateModal({ token, onClose, onDone }) {
  const [prev, setPrev] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    apiGet(token, EP.migratePreview)
      .then(setPrev)
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  const run = async () => {
    setRunning(true);
    try {
      const r = await apiPost(token, EP.migrate, {});
      const bf = Object.entries(r.backfilled || {})
        .filter(([, n]) => n > 0)
        .map(([c, n]) => `${c}: ${n}`)
        .join(', ');
      toast.success(`${r.created_count} supplier dibuat. Dokumen ditautkan → ${bf || 'tidak ada'}`);
      onDone?.();
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally { setRunning(false); }
  };

  return (
    <Modal onClose={onClose} title="Tarik Supplier dari Dokumen Lama" size="lg">
      <div className="space-y-3" data-testid="supplier-migrate-modal">
        <p className="text-sm text-muted-foreground">
          Sistem memindai nama supplier teks-bebas di Purchase Order, inspeksi QC penerimaan,
          dokumen penerimaan gudang, purchase request aksesoris, dan faktur hutang.
          Ejaan berbeda untuk entitas yang sama digabung otomatis, lalu dokumen lama
          ditautkan ke master supplier. Nama asli tidak dihapus.
        </p>
        {loading ? (
          <div className="flex items-center justify-center h-24">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[hsl(var(--primary))]" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                { l: 'Nama ditemukan', v: prev?.summary?.legacy_names ?? 0 },
                { l: 'Akan dibuat', v: prev?.summary?.to_create ?? 0 },
                { l: 'Sudah cocok', v: prev?.summary?.already_matched ?? 0 },
              ].map((x) => (
                <div key={x.l} className="rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
                  <div className="text-[11px] text-muted-foreground">{x.l}</div>
                  <div className="text-xl font-bold tabular-nums">{x.v}</div>
                </div>
              ))}
            </div>
            {(prev?.to_create || []).length > 0 && (
              <div className="max-h-56 overflow-y-auto rounded-lg border border-[var(--glass-border)]">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)] sticky top-0 bg-[var(--card-surface)]">
                    <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                      <th className="p-2">Nama Supplier Baru</th>
                      <th className="p-2">Ejaan Ditemukan</th>
                      <th className="p-2">Sumber</th>
                    </tr>
                  </thead>
                  <tbody data-testid="migrate-preview-list">
                    {prev.to_create.map((r) => (
                      <tr key={r.name_key} className="border-b border-[var(--glass-border)] last:border-0">
                        <td className="p-2 text-xs font-medium">{r.name}</td>
                        <td className="p-2 text-[11px] text-muted-foreground">{(r.variants || []).join(' · ')}</td>
                        <td className="p-2 text-[11px] text-muted-foreground">{(r.sources || []).length} koleksi</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(prev?.to_create || []).length === 0 && (
              <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 p-3 rounded-lg border border-emerald-300 dark:border-emerald-400/30 bg-emerald-50 dark:bg-emerald-400/10">
                <CheckCircle2 className="w-4 h-4" /> Semua nama supplier lama sudah punya master. Jalankan ulang tetap aman.
              </div>
            )}
          </>
        )}
        <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
          <Button variant="secondary" onClick={onClose}>Tutup</Button>
          <Button onClick={run} disabled={running || loading} data-testid="supplier-migrate-run">
            {running ? 'Menjalankan...' : 'Jalankan Sekarang'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Modul utama ─────────────────────────────────────────────────────────────
export default function SupplierMasterModule({ token }) {
  const [rows, setRows] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total: 0, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [meta, setMeta] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [scoreMap, setScoreMap] = useState({});
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [migrateOpen, setMigrateOpen] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async (page = 1) => {
    setLoading(true);
    setErr('');
    try {
      const qs = new URLSearchParams({ page: String(page), limit: '50', with_stats: 'true' });
      if (search) qs.set('search', search);
      if (category) qs.set('category', category);
      if (activeFilter) qs.set('is_active', activeFilter);
      const r = await apiGet(token, EP.suppliers(`?${qs.toString()}`));
      setRows(r?.items || []);
      setPagination(r?.pagination || { page, total: 0, total_pages: 1 });
    } catch (e) {
      setErr(e.message);
      toast.error(`Gagal memuat supplier: ${e.message}`);
    } finally { setLoading(false); }
  }, [token, search, category, activeFilter]);

  useEffect(() => { load(1); }, [load]);

  useEffect(() => {
    apiGet(token, EP.supplierMeta).then(setMeta).catch(() => {});
    apiGet(token, `${EP.materials}?include_inactive=false`)
      .then((m) => setMaterials((Array.isArray(m) ? m : m?.items || []).filter((x) => x.active !== false)))
      .catch(() => {});
    apiGet(token, EP.scorecard(365))
      .then((s) => {
        const map = {};
        (s?.items || []).forEach((x) => { if (x.supplier_id) map[x.supplier_id] = x; });
        setScoreMap(map);
      })
      .catch(() => {});
  }, [token]);

  const deactivate = async (s) => {
    if (!window.confirm(`Nonaktifkan supplier ${s.name}?`)) return;
    try {
      await apiDelete(token, EP.supplier(s.id));
      toast.success('Supplier dinonaktifkan');
      load(pagination.page);
    } catch (e) { toast.error(e.message); }
  };

  const activate = async (s) => {
    try {
      await apiPost(token, EP.supplierActivate(s.id), {});
      toast.success('Supplier diaktifkan');
      load(pagination.page);
    } catch (e) { toast.error(e.message); }
  };

  const exportCsv = () => {
    const head = ['Kode', 'Nama', 'NPWP', 'Kota', 'Telepon', 'Email', 'Termin', 'Mata Uang',
      'Lead Time', 'Kategori', 'Status'];
    const lines = rows.map((s) => [
      s.code, s.name, s.npwp || '', s.city || '', s.phone || '', s.email || '',
      PAYMENT_TERM_LABEL[s.payment_terms] || s.payment_terms, s.currency,
      s.lead_time_days || 0, (s.categories || []).map((c) => CATEGORY_LABEL[c] || c).join('|'),
      s.is_active === false ? 'Nonaktif' : 'Aktif',
    ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
    const blob = new Blob([[head.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `master-supplier-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    toast.success('Master supplier diekspor ke CSV');
  };

  return (
    <div className="space-y-5" data-testid="supplier-master-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Master Supplier</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Sumber tunggal data supplier: kontak, NPWP, termin bayar, rekening, dan daftar harga per satuan beli.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="secondary" onClick={() => setMigrateOpen(true)} data-testid="supplier-migrate-btn">
            <Truck className="w-4 h-4 mr-1.5" /> Tarik Data Lama
          </Button>
          <Button variant="secondary" onClick={exportCsv} data-testid="supplier-export-btn">
            <Download className="w-4 h-4 mr-1.5" /> Ekspor CSV
          </Button>
          <Button onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="supplier-create-btn">
            <Plus className="w-4 h-4 mr-1.5" /> Tambah Supplier
          </Button>
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <GlassInput className="pl-9" placeholder="Cari nama, kode, NPWP, kota..."
                      value={search} onChange={(e) => setSearch(e.target.value)}
                      data-testid="supplier-search" />
        </div>
        <SmartNativeSelect value={category} onChange={(e) => setCategory(e.target.value)}
          className="h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="supplier-filter-category">
          <option value="">Semua kategori</option>
          {Object.entries(CATEGORY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </SmartNativeSelect>
        <SmartNativeSelect value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)}
          className="h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="supplier-filter-active">
          <option value="">Semua status</option>
          <option value="true">Aktif</option>
          <option value="false">Nonaktif</option>
        </SmartNativeSelect>
        <Button variant="secondary" onClick={() => load(1)} data-testid="supplier-refresh">
          <RefreshCw className="w-4 h-4" />
        </Button>
      </div>

      <GlassCard>
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--glass-border)]">
                <tr className="text-left text-muted-foreground text-xs uppercase tracking-wide">
                  <th className="pb-3 pl-4">Kode</th>
                  <th className="pb-3">Supplier</th>
                  <th className="pb-3">Kategori</th>
                  <th className="pb-3">Termin</th>
                  <th className="pb-3 text-right">Lead</th>
                  <th className="pb-3 text-right">PO</th>
                  <th className="pb-3 text-right">Harga</th>
                  <th className="pb-3">Nilai QC</th>
                  <th className="pb-3">Status</th>
                  <th className="pb-3 pr-4 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody data-testid="supplier-table-body">
                {rows.length === 0 && (
                  <tr>
                    <td colSpan="10" className="py-12 text-center text-muted-foreground">
                      <Building2 className="w-10 h-10 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">Belum ada supplier di master.</p>
                      <p className="text-xs mt-1">
                        Klik <span className="font-semibold">Tarik Data Lama</span> untuk membuat master
                        dari nama supplier di dokumen yang sudah ada.
                      </p>
                    </td>
                  </tr>
                )}
                {rows.map((s, idx) => {
                  const sc = scoreMap[s.id];
                  return (
                    <tr key={s.id}
                        className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}
                        data-testid={`supplier-row-${s.id}`}>
                      <td className="py-3 pl-4 font-mono text-xs">{s.code}</td>
                      <td className="py-3">
                        <div className="font-medium">{s.name}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {[s.city, s.phone].filter(Boolean).join(' · ') || '—'}
                        </div>
                      </td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-1">
                          {(s.categories || []).slice(0, 3).map((c) => (
                            <span key={c} className="text-[10px] px-1.5 py-0.5 rounded-full border border-[var(--glass-border)] bg-[var(--input-surface)]">
                              {CATEGORY_LABEL[c] || c}
                            </span>
                          ))}
                          {!(s.categories || []).length && <span className="text-xs text-muted-foreground">—</span>}
                        </div>
                      </td>
                      <td className="py-3 text-xs">{PAYMENT_TERM_LABEL[s.payment_terms] || s.payment_terms}</td>
                      <td className="py-3 text-xs text-right tabular-nums">{s.lead_time_days || 0} hr</td>
                      <td className="py-3 text-xs text-right tabular-nums">{s.po_count ?? 0}</td>
                      <td className="py-3 text-xs text-right tabular-nums">{s.price_list_count ?? 0}</td>
                      <td className="py-3">
                        {sc ? (
                          <div className="flex items-center gap-1.5">
                            <GradePill grade={sc.quality_grade} />
                            <span className="text-[11px] text-muted-foreground tabular-nums">
                              {fmtNum(sc.accept_rate, 1)}%
                            </span>
                          </div>
                        ) : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                      <td className="py-3"><ActivePill active={s.is_active} /></td>
                      <td className="py-3 pr-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="sm" onClick={() => setDetailId(s.id)}
                                  data-testid={`supplier-view-${s.id}`} title="Detail">
                            <Eye className="w-4 h-4" />
                          </Button>
                          <Button variant="ghost" size="sm"
                                  onClick={() => { setEditing(s); setFormOpen(true); }}
                                  data-testid={`supplier-edit-${s.id}`} title="Ubah">
                            <Pencil className="w-4 h-4" />
                          </Button>
                          {s.is_active === false ? (
                            <Button variant="ghost" size="sm" onClick={() => activate(s)}
                                    data-testid={`supplier-activate-${s.id}`} title="Aktifkan">
                              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                            </Button>
                          ) : (
                            <Button variant="ghost" size="sm" onClick={() => deactivate(s)}
                                    data-testid={`supplier-deactivate-${s.id}`} title="Nonaktifkan">
                              <Ban className="w-4 h-4 text-red-600 dark:text-red-400" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {pagination.total_pages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Total {pagination.total} supplier · halaman {pagination.page}/{pagination.total_pages}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={pagination.page <= 1}
                    onClick={() => load(pagination.page - 1)} data-testid="supplier-prev-page">
              Sebelumnya
            </Button>
            <Button size="sm" variant="secondary" disabled={pagination.page >= pagination.total_pages}
                    onClick={() => load(pagination.page + 1)} data-testid="supplier-next-page">
              Berikutnya
            </Button>
          </div>
        </div>
      )}

      {formOpen && (
        <SupplierForm token={token} meta={meta} initial={editing}
                      onClose={() => { setFormOpen(false); setEditing(null); }}
                      onSaved={() => load(pagination.page)} />
      )}
      {detailId && (
        <SupplierDetail token={token} supplierId={detailId} materials={materials}
                        onClose={() => setDetailId(null)}
                        onChanged={() => load(pagination.page)} />
      )}
      {migrateOpen && (
        <MigrateModal token={token} onClose={() => setMigrateOpen(false)}
                      onDone={() => load(1)} />
      )}
    </div>
  );
}
