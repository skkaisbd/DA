/**
 * RnDColorPicker — komponen warna R&D yang memakai MASTER `rahaza_colors`.
 *
 * Kenapa ada: sebelum ini layar R&D menulis warna sebagai TEKS BEBAS sehingga
 * warna R&D tidak pernah cocok dengan warna produksi/gudang/marketing. Semua
 * pemilih warna R&D sekarang lewat komponen ini → satu master, satu kode warna.
 *
 * Ekspor:
 *   · useColorOptions()   — memuat master warna sekali, plus `addColor()` inline
 *   · ColorSelect         — pilih SATU warna (dropdown + swatch)
 *   · ColorMultiSelect    — pilih BANYAK warna (chip + tambah + "warna baru…")
 */
import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, X, Save } from 'lucide-react';
import { toast } from '../ui/sonner';
import { apiFetch, ApiError } from '@/lib/apiFetch';

const NEW = '__new__';

export function useColorOptions() {
  const [colors, setColors] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/dewi/rnd/color-options');
      setColors(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) {
        toast.error(e.detail || 'Gagal memuat master warna');
      }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  /** Tulis warna baru ke MASTER (bukan koleksi bayangan) lalu kembalikan dokumennya. */
  const addColor = useCallback(async ({ name, code, hex }) => {
    const created = await apiFetch('/dewi/rnd/color-options', {
      method: 'POST', body: { name, code, hex },
    });
    setColors(prev => [...prev, created]);
    return created;
  }, []);

  return { colors, loading, reload: load, addColor };
}

function NewColorInline({ onCreated, onCancel, addColor, testId }) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [hex, setHex] = useState('#4F46E5');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim()) return toast.error('Isi nama warna baru');
    setBusy(true);
    try {
      const created = await addColor({ name: name.trim(), code: code.trim(), hex });
      toast.success(`Warna "${created.name}" (${created.code}) masuk master & terpilih`);
      onCreated(created);
    } catch (e) {
      toast.error((e instanceof ApiError && e.detail) || 'Gagal menambah warna ke master');
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-2 grid grid-cols-[1fr_100px_44px_auto_auto] gap-2 items-center"
      data-testid={testId ? `${testId}-new` : undefined}>
      <Input value={name} onChange={e => setName(e.target.value)} className="h-9 text-sm"
        placeholder="Nama warna baru" data-testid={testId ? `${testId}-new-name` : undefined} />
      <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())}
        className="h-9 text-sm font-mono" placeholder="KODE"
        data-testid={testId ? `${testId}-new-code` : undefined} />
      <input type="color" value={hex} onChange={e => setHex(e.target.value)}
        className="w-11 h-9 rounded border border-input cursor-pointer bg-background" />
      <Button type="button" size="sm" onClick={save} disabled={busy} className="h-9 text-xs gap-1"
        data-testid={testId ? `${testId}-new-save` : undefined}>
        <Save className="w-3 h-3" /> {busy ? '…' : 'Simpan ke Master'}
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onCancel} className="h-9 text-xs">Batal</Button>
    </div>
  );
}

/** Pilih SATU warna. `value` = color_id ATAU kode warna. */
export function ColorSelect({ colors, addColor, value, onChange, testId, placeholder = '-- Warna --', allowCreate = true }) {
  const [adding, setAdding] = useState(false);
  const sel = colors.find(c => c.color_id === value) || colors.find(c => c.code === value);

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="w-7 h-7 rounded-md border border-foreground/20 flex-shrink-0"
          style={{ backgroundColor: sel?.hex || '#E5E7EB' }} />
        <SmartNativeSelect
          value={adding ? NEW : (sel?.color_id || '')}
          onChange={e => {
            if (e.target.value === NEW) { setAdding(true); return; }
            setAdding(false);
            const c = colors.find(x => x.color_id === e.target.value);
            onChange(c || null);
          }}
          data-testid={testId}
          className="flex-1 border border-input bg-background rounded-md px-2 py-2 text-sm text-foreground">
          <option value="">{placeholder}</option>
          {colors.map(c => <option key={c.color_id} value={c.color_id}>{`${c.name} (${c.code})`}</option>)}
          {allowCreate && <option value={NEW}>+ Warna baru…</option>}
        </SmartNativeSelect>
      </div>
      {adding && (
        <NewColorInline addColor={addColor} testId={testId}
          onCancel={() => setAdding(false)}
          onCreated={c => { setAdding(false); onChange(c); }} />
      )}
    </div>
  );
}

/** Pilih BANYAK warna. `value` = [{color_id, code, name, hex}] */
export function ColorMultiSelect({ colors, addColor, value = [], onChange, testId, label = 'Tambah warna' }) {
  const [adding, setAdding] = useState(false);
  const chosen = Array.isArray(value) ? value : [];
  const chosenIds = new Set(chosen.map(c => c.color_id));

  const add = (c) => {
    if (!c) return;
    if (chosenIds.has(c.color_id)) { toast.error(`Warna "${c.name}" sudah dipilih`); return; }
    onChange([...chosen, { color_id: c.color_id, code: c.code, name: c.name, hex: c.hex }]);
  };

  return (
    <div data-testid={testId}>
      <div className="flex flex-wrap gap-2 mb-2">
        {chosen.length === 0 && (
          <span className="text-xs text-foreground/40">Belum ada warna dipilih.</span>
        )}
        {chosen.map(c => (
          <span key={c.color_id}
            className="inline-flex items-center gap-1.5 text-xs pl-1.5 pr-1 py-1 rounded-full border border-foreground/15 bg-foreground/5"
            data-testid={testId ? `${testId}-chip-${c.code}` : undefined}>
            <span className="w-3.5 h-3.5 rounded-full border border-foreground/20" style={{ backgroundColor: c.hex }} />
            <span className="text-foreground">{c.name}</span>
            <span className="font-mono text-foreground/50">{c.code}</span>
            <button type="button" onClick={() => onChange(chosen.filter(x => x.color_id !== c.color_id))}
              className="ml-0.5 p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-500/20 text-red-600 dark:text-red-400"
              data-testid={testId ? `${testId}-remove-${c.code}` : undefined}>
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <SmartNativeSelect value="" onChange={e => {
          if (e.target.value === NEW) { setAdding(true); return; }
          add(colors.find(c => c.color_id === e.target.value));
        }}
          data-testid={testId ? `${testId}-select` : undefined}
          className="flex-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
          <option value="">{label}…</option>
          {colors.filter(c => !chosenIds.has(c.color_id)).map(c => (
            <option key={c.color_id} value={c.color_id}>{`${c.name} (${c.code})`}</option>
          ))}
          <option value={NEW}>+ Warna baru…</option>
        </SmartNativeSelect>
        {!adding && (
          <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}
            className="h-9 text-xs gap-1" data-testid={testId ? `${testId}-new-btn` : undefined}>
            <Plus className="w-3 h-3" /> Warna baru
          </Button>
        )}
      </div>

      {adding && (
        <NewColorInline addColor={addColor} testId={testId}
          onCancel={() => setAdding(false)}
          onCreated={c => { setAdding(false); add(c); }} />
      )}
    </div>
  );
}

export default ColorMultiSelect;
