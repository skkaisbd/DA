/**
 * ColorSelect · SizeSelect · ModelSelect — **pemilih dari MASTER** (Sesi #20)
 * ═════════════════════════════════════════════════════════════════════════════
 * ATURAN YANG DITEGAKKAN BERKAS INI (gate INV-F14 / `_audit_form_master_refs.py`)
 * ───────────────────────────────────────────────────────────────────────────
 * Form TIDAK BOLEH meminta orang mengetik apa yang sudah punya master. Alasannya
 * soal uang, bukan kenyamanan: "Navy", "navy", dan "Dongker" adalah tiga warna
 * berbeda bagi mesin ⇒ SKU varian tidak terbentuk, laporan per warna bocor, dan
 * model yang sama lahir dua kali di master stok.
 *
 * Ketiga pemilih di bawah membaca SSOT yang sudah dipakai layar lain:
 *   · warna  → `GET /api/rahaza/colors`  (`rahaza_colors`, dijaga gate INV-COLOR)
 *   · ukuran → `GET /api/rahaza/sizes`   (`rahaza_sizes`, dijaga INV-RND/INV-RND2)
 *   · model  → `GET /api/rahaza/models`  (`rahaza_models`, kodenya dibuat otomatis
 *                                        oleh `core.product_master`)
 *
 * Sengaja TIDAK ada mode "ketik sendiri": kalau nilainya belum ada di master,
 * jalan yang benar adalah menambahkannya di layar Master Data — satu tempat,
 * satu ejaan.
 */
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { apiGet } from '@/lib/api';

const BASE_CLS =
  'w-full h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm ' +
  'text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40';

function useMaster(path) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await apiGet(path);
        // Bentuk respons di repo ini tidak seragam: ada yang mengirim array
        // langsung, ada `{rows}`, `{items}`, `{models}`, dan `{categories}`.
        // Kalau satu bentuk terlewat, pemilih tampil "Master masih kosong"
        // padahal masternya penuh — dan pemakai jadi tidak bisa memilih.
        if (alive) {
          setRows(Array.isArray(d)
            ? d
            : (d.rows || d.items || d.models || d.categories || d.data || []));
        }
      } catch {
        if (alive) setRows([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [path]);
  return { rows, loading };
}

function MasterSelect({ label, hint, value, onChange, rows, loading, placeholder,
                        optionValue, optionLabel, testId, disabled }) {
  return (
    <div>
      {label ? <Label className="text-xs">{label}</Label> : null}
      <div className="relative">
        <select className={BASE_CLS} value={value || ''} disabled={disabled || loading}
                onChange={(e) => onChange(e.target.value)} data-testid={testId}>
          <option value="">{loading ? 'Memuat master…' : placeholder}</option>
          {rows.map((r) => (
            <option key={optionValue(r)} value={optionValue(r)}>{optionLabel(r)}</option>
          ))}
        </select>
        {loading && (
          <Loader2 className="w-4 h-4 animate-spin absolute right-8 top-3 text-muted-foreground" />
        )}
      </div>
      {hint ? <p className="text-[11px] text-muted-foreground mt-1">{hint}</p> : null}
      {!loading && rows.length === 0 && (
        <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
          Master masih kosong — lengkapi dulu di Master Data.
        </p>
      )}
    </div>
  );
}

/** Pemilih WARNA dari SSOT warna. Nilai yang dikembalikan = **nama** warna master. */
export function ColorSelect({ value, onChange, label = 'Warna', hint, testId = 'color-select',
                              disabled }) {
  const { rows, loading } = useMaster('/rahaza/colors');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— pilih warna master —"
                  optionValue={(r) => r.name}
                  optionLabel={(r) => `${r.name} (${r.code})`}
                  testId={testId} disabled={disabled} />
  );
}

/** Pemilih UKURAN dari SSOT ukuran. Nilai yang dikembalikan = **kode** ukuran. */
export function SizeSelect({ value, onChange, label = 'Ukuran', hint, testId = 'size-select',
                             disabled }) {
  const { rows, loading } = useMaster('/rahaza/sizes');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— pilih ukuran master —"
                  optionValue={(r) => r.code}
                  optionLabel={(r) => (r.name && r.name !== r.code ? `${r.code} · ${r.name}` : r.code)}
                  testId={testId} disabled={disabled} />
  );
}

/** Pemilih MODEL produk internal dari `rahaza_models`. Nilai = **id** model. */export function ModelSelect({ value, onChange, label = 'Model produk', hint,
                              testId = 'model-select', disabled }) {
  const { rows, loading } = useMaster('/rahaza/models');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— pilih model yang sudah ada —"
                  optionValue={(r) => r.id}
                  optionLabel={(r) => `${r.code} · ${r.name}`}
                  testId={testId} disabled={disabled} />
  );
}

/**
 * Pemilih KATEGORI produk dari `rahaza_product_categories`. Nilai = **kode**.
 * Kategori menentukan prefix kode model (`BLS-0001`, `AKS-0001`) — jadi ia
 * WAJIB dari master, bukan ketikan, kalau tidak kode model jadi liar.
 */
export function CategorySelect({ value, onChange, label = 'Kategori produk', hint,
                                 testId = 'category-select', disabled }) {
  const { rows, loading } = useMaster('/rahaza/product-categories');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— pakai usulan sistem —"
                  optionValue={(r) => r.code}
                  optionLabel={(r) => `${r.name} (${r.sku_prefix || r.code})`}
                  testId={testId} disabled={disabled} />
  );
}

/**
 * Pemilih OPSI varian (dimensi ke-3, Sesi #28). Nilai = **kode** opsi.
 * Tanpa dimensi ini 'PAKAI KARET' dan 'TANPA KARET' tertimpa menjadi satu
 * barang — 8 SKU nyata pernah jatuh ke satu identitas `hitam/XL`.
 */
export function VariantOptionSelect({ value, onChange, label = 'Opsi varian', hint,
                                      testId = 'variant-option-select', disabled }) {
  const { rows, loading } = useMaster('/variant-onboarding/options');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— Tidak Disebut —"
                  optionValue={(r) => r.code}
                  optionLabel={(r) => `${r.name} (${r.code})`}
                  testId={testId} disabled={disabled} />
  );
}


/**
 * Pemilih BARANG JADI (FG) dari master `rahaza_materials` (type=fg).
 * Nilai = **id** material. Dipakai layar yang harus MENGGERAKKAN STOK barang
 * jadi (mis. Retur Fisik gudang): sebelum ini kolomnya teks bebas "SKU / Kode
 * Produk", dan karena teks itu tidak pernah cocok dengan master, tombol
 * "Restock ke Gudang" tidak pernah menemukan barangnya ⇒ stok tak pernah
 * bertambah. Memilih dari master membuat restock selalu tepat sasaran.
 */
export function FGMaterialSelect({ value, onChange, label = 'Barang jadi (master)',
                                   hint, testId = 'fg-material-select', disabled }) {
  const { rows, loading } = useMaster('/rahaza/materials?type=fg');
  return (
    <MasterSelect label={label} hint={hint} value={value} onChange={onChange}
                  rows={rows.filter((r) => r.active !== false)} loading={loading}
                  placeholder="— pilih barang dari master produk jadi —"
                  optionValue={(r) => r.id}
                  optionLabel={(r) => `${r.code || r.sku} · ${r.name}`}
                  testId={testId} disabled={disabled} />
  );
}
