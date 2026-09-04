import SmartNativeSelect from '@/components/ui/smart-native-select';

// Satuan yang dikenal konverter server (core/bom_uom.py). Satuan "kemasan"
// (rol/pak/karton/bal) hanya bisa dikonversi bila faktornya diisi di master
// material — server akan menandai barisnya bila belum.
export const RND_UNITS = [
  'm', 'cm', 'yard', 'inch',
  'kg', 'gram', 'ons', 'ton',
  'pcs', 'lusin', 'kodi', 'gross', 'pasang', 'lembar', 'set',
  'liter', 'ml',
  'rol', 'pak', 'karton', 'bal', 'ikat',
];

export const UOM_STATUS = {
  base: { label: 'satuan dasar', warn: false },
  uom: { label: 'kemasan master', warn: false },
  global: { label: 'konversi otomatis', warn: false },
  fabric: { label: 'via gramasi & lebar', warn: false },
  mismatch: { label: 'satuan tidak bisa dikonversi', warn: true },
  unlinked: { label: 'belum tertaut master material', warn: true },
};

export default function RnDUnitSelect({ value, onChange, className = '', testId, units }) {
  const list = units?.length ? units : RND_UNITS;
  return (
    <SmartNativeSelect
      value={value || ''}
      onChange={onChange}
      data-testid={testId}
      searchable
      searchPlaceholder="Cari satuan..."
      className={`w-full text-sm ${className}`}
    >
      <option value="">Satuan…</option>
      {list.map((u) => <option key={u} value={u}>{u}</option>)}
    </SmartNativeSelect>
  );
}
