/**
 * UomEditor — editor satuan berjenjang (maks 3 tingkat) untuk form material.
 *
 * Dipakai di:
 *   - Master Material  (RahazaMaterialsModule)
 *   - Master Aksesoris (AccessoryModule)
 *
 * Prinsip yang dijaga (lihat memory/INVARIANTS.md §U):
 *   - INV-UOM-6  user mengetik "1 <satuan> = N <induk>", komponen ini yang
 *                mengalikan sampai ke satuan dasar. Yang DIKIRIM ke server
 *                selalu `factor` relatif ke satuan dasar.
 *   - INV-UOM-3  tepat satu satuan dasar berfaktor 1; kode unik; faktor > 0.
 *   - INV-UOM-1  harga tetap per satuan dasar → diberi pengingat di UI.
 *
 * Kontrak:
 *   value    : { unit, uoms[], purchase_uom, issue_uom, display_uom }
 *   onChange : (patch) => void   — dipanggil dengan potongan perubahan
 */
import React, { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Layers, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  MAX_UOMS, normalizeCode, sanitizeUoms, validateUoms, describeHierarchy,
} from '@/lib/uom';

const SATUAN_UMUM = [
  'pcs', 'lusin', 'kodi', 'gross', 'pak', 'bks', 'box', 'karton', 'bal',
  'rol', 'gulung', 'cone', 'set', 'pasang', 'lembar',
  'm', 'cm', 'yard', 'kg', 'gram', 'liter',
];

const inputCls =
  'w-full h-9 px-2.5 rounded-[var(--radius-sm)] border border-[var(--glass-border)] ' +
  'bg-[var(--input-surface)] text-sm text-foreground ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export const UomEditor = ({
  baseUnit, uoms, purchaseUom, issueUom, displayUom, onChange, resetKey = 'new',
  materialId = null, token = null, onRebased = null,
}) => {
  const base = normalizeCode(baseUnit) || 'pcs';

  /**
   * Baris kemasan disimpan sebagai DRAFT lokal.
   * Alasan: baris yang baru ditambahkan masih berkode kosong, dan
   * `sanitizeUoms()` (yang dipakai saat mengirim ke induk) sengaja membuang
   * baris tanpa kode. Kalau draft ikut disanitasi, baris baru langsung hilang
   * sebelum sempat diketik. Draft hanya disinkronkan ulang saat berpindah
   * material (`resetKey` berubah).
   */
  const [packs, setPacks] = useState(() =>
    (uoms || []).filter((u) => normalizeCode(u.code) !== base));
  const lastKey = useRef(resetKey);

  // ── Ubah Satuan Dasar (rebase) — hanya untuk material yang SUDAH tersimpan ──
  const [rebaseOpen, setRebaseOpen] = useState(false);
  const [rebase, setRebase] = useState({ new_base_uom: '', factor: '' });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rebaseErr, setRebaseErr] = useState('');

  const callRebase = async (dryRun) => {
    if (!materialId) return;
    setBusy(true); setRebaseErr('');
    try {
      const res = await fetch(`/api/rahaza/materials/${materialId}/rebase-uom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          new_base_uom: normalizeCode(rebase.new_base_uom),
          factor: Number(rebase.factor) || 0,
          preview: dryRun,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `Gagal (HTTP ${res.status})`);
      if (dryRun) setPreview(data);
      else {
        setPreview(null); setRebaseOpen(false);
        if (onRebased) onRebased(data);
      }
    } catch (e) {
      setRebaseErr(String(e.message || e));
    } finally { setBusy(false); }
  };

  useEffect(() => {
    if (lastKey.current !== resetKey) {
      lastKey.current = resetKey;
      setPacks((uoms || []).filter((u) => normalizeCode(u.code) !== base));
    }
  }, [resetKey, uoms, base]);

  const allRows = useMemo(
    () => [{ code: base, factor: 1, is_base: true, level: 0 }, ...packs],
    [base, packs],
  );

  const { errors } = useMemo(() => validateUoms(allRows, base), [allRows, base]);

  const emit = useCallback((nextPacks, extra = {}) => {
    setPacks(nextPacks);
    const rows = sanitizeUoms(
      [{ code: base, factor: 1, is_base: true }, ...nextPacks],
      base,
    );
    const codes = rows.map((r) => r.code);
    const keep = (v, fb) => (codes.includes(normalizeCode(v)) ? normalizeCode(v) : fb);
    onChange({
      uoms: rows,
      purchase_uom: keep(extra.purchase_uom ?? purchaseUom, base),
      issue_uom: keep(extra.issue_uom ?? issueUom, base),
      display_uom: keep(extra.display_uom ?? displayUom, base),
    });
  }, [base, purchaseUom, issueUom, displayUom, onChange]);

  const addPack = () => {
    if (packs.length >= MAX_UOMS - 1) return;
    const parent = packs.length ? packs[packs.length - 1].code : base;
    const parentFactor = packs.length ? Number(packs[packs.length - 1].factor) || 1 : 1;
    emit([...packs, { code: '', factor: parentFactor, parent, per_parent: 1 }]);
  };

  const removePack = (idx) => emit(packs.filter((_, i) => i !== idx));

  /** User mengetik "1 <baris ini> = N <induk>" → faktor ke satuan dasar. */
  const patchPack = (idx, patch) => {
    const next = packs.map((p, i) => (i === idx ? { ...p, ...patch } : p));
    // hitung ulang faktor berantai dari induk masing-masing
    let prevFactor = 1;
    let prevCode = base;
    const recalced = next.map((p) => {
      const perParent = Number(p.per_parent ?? (Number(p.factor) || 1) / prevFactor) || 1;
      const factor = perParent * prevFactor;
      const row = { ...p, per_parent: perParent, factor, parent: prevCode };
      prevFactor = factor;
      prevCode = normalizeCode(p.code) || prevCode;
      return row;
    });
    emit(recalced);
  };

  const hierarchy = describeHierarchy(allRows, base);

  return (
    <div className="border-t border-border pt-3 mt-3" data-testid="uom-editor">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-[hsl(var(--primary))]" aria-hidden="true" />
          <span className="text-sm font-semibold text-foreground">Satuan &amp; Kemasan</span>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={addPack}
          disabled={packs.length >= MAX_UOMS - 1}
          data-testid="uom-add-row">
          <Plus size={14} className="mr-1" /> Tambah kemasan
        </Button>
      </div>

      <p className="text-[11px] text-muted-foreground mb-3 flex items-start gap-1.5">
        <Info size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          Satuan dasar <b className="text-foreground">{base}</b> dipakai untuk menyimpan stok
          dan menghitung HPP. Kemasan hanya alat bantu saat membeli / memakai —
          isinya boleh berbeda tiap barang. Maksimal {MAX_UOMS - 1} tingkat kemasan.
        </span>
      </p>

      {/* Baris satuan dasar (read-only) */}
      <div className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-[var(--card-surface)] px-3 py-2 mb-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground w-20 shrink-0">Dasar</span>
        <span className="font-mono text-sm text-foreground" data-testid="uom-base-code">{base}</span>
        <span className="text-xs text-muted-foreground ml-auto">faktor 1 — tidak dapat diubah di sini</span>
      </div>

      {packs.map((p, i) => {
        const parent = i === 0 ? base : (normalizeCode(packs[i - 1].code) || base);
        const perParent = Number(p.per_parent ?? (Number(p.factor) || 1)) || 1;
        return (
          <div key={`pack-${i}`}
            className="grid grid-cols-12 gap-2 items-end mb-2"
            data-testid={`uom-row-${i}`}>
            <div className="col-span-4">
              <label className="block text-[11px] text-muted-foreground mb-1">
                Nama kemasan {i + 1}
              </label>
              <input list="uom-satuan-umum" value={p.code || ''}
                onChange={(e) => patchPack(i, { code: normalizeCode(e.target.value) })}
                placeholder="bks / karton / rol"
                className={inputCls}
                data-testid={`uom-code-${i}`} />
            </div>
            <div className="col-span-5">
              <label className="block text-[11px] text-muted-foreground mb-1">
                1 {p.code || `kemasan ${i + 1}`} = ? {parent}
              </label>
              <input type="number" min="0.0001" step="any" value={perParent}
                onChange={(e) => patchPack(i, { per_parent: parseFloat(e.target.value) || 0 })}
                className={inputCls}
                data-testid={`uom-perparent-${i}`} />
            </div>
            <div className="col-span-2">
              <label className="block text-[11px] text-muted-foreground mb-1">= {base}</label>
              <div className="h-9 flex items-center px-2 text-sm font-mono text-muted-foreground truncate"
                data-testid={`uom-factor-${i}`}>
                {Number(p.factor || 0).toLocaleString('id-ID')}
              </div>
            </div>
            <div className="col-span-1">
              <Button type="button" variant="ghost" size="icon"
                onClick={() => removePack(i)}
                aria-label={`Hapus kemasan ${i + 1}`}
                data-testid={`uom-remove-${i}`}>
                <Trash2 size={15} />
              </Button>
            </div>
          </div>
        );
      })}

      <datalist id="uom-satuan-umum">
        {SATUAN_UMUM.map((s) => <option key={s} value={s} />)}
      </datalist>

      {hierarchy && (
        <p className="text-xs text-[hsl(var(--primary))] font-medium mt-1" data-testid="uom-hierarchy">
          {hierarchy}
        </p>
      )}

      {errors.length > 0 && (
        <ul className="mt-2 space-y-0.5" data-testid="uom-errors">
          {errors.map((e) => (
            <li key={e} className="text-xs text-[hsl(var(--destructive))]">• {e}</li>
          ))}
        </ul>
      )}

      {packs.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mt-3">
          {[
            { key: 'purchase_uom', label: 'Satuan beli', value: purchaseUom, testid: 'uom-default-purchase' },
            { key: 'issue_uom', label: 'Satuan pakai', value: issueUom, testid: 'uom-default-issue' },
            { key: 'display_uom', label: 'Satuan tampil', value: displayUom, testid: 'uom-default-display' },
          ].map((f) => (
            <div key={f.key}>
              <label className="block text-[11px] text-muted-foreground mb-1">{f.label}</label>
              <select value={normalizeCode(f.value) || base}
                onChange={(e) => emit(packs, { [f.key]: e.target.value })}
                className={inputCls}
                data-testid={f.testid}>
                {allRows.map((r) => (
                  <option key={r.code || 'x'} value={r.code}>{r.code || '—'}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground mt-2">
        Harga satuan tetap disimpan <b className="text-foreground">per {base}</b>. Saat menerima
        barang dalam kemasan, sistem membagi otomatis.
      </p>

      {materialId && (
        <div className="mt-3 pt-3 border-t border-dashed border-[var(--glass-border)]">
          {!rebaseOpen ? (
            <Button type="button" variant="outline" size="sm"
              onClick={() => { setRebaseOpen(true); setPreview(null); setRebaseErr(''); }}
              data-testid="uom-rebase-open">
              Ubah satuan dasar ({base})
            </Button>
          ) : (
            <div className="rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
              <p className="text-xs text-muted-foreground mb-2">
                Mengubah satuan dasar akan <b className="text-foreground">mengonversi seluruh angka
                stok, HPP, dan min. stok</b>. Nilai persediaan tidak berubah. Perubahan dicatat di
                buku besar stok dan dapat ditelusuri.
              </p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">Satuan dasar baru</label>
                  <input list="uom-satuan-umum" value={rebase.new_base_uom}
                    onChange={(e) => { setRebase({ ...rebase, new_base_uom: e.target.value }); setPreview(null); }}
                    placeholder="m" className={inputCls} data-testid="uom-rebase-newbase" />
                </div>
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1">
                    1 {base} = ? {normalizeCode(rebase.new_base_uom) || 'satuan baru'}
                  </label>
                  <input type="number" min="0.0001" step="any" value={rebase.factor}
                    onChange={(e) => { setRebase({ ...rebase, factor: e.target.value }); setPreview(null); }}
                    placeholder="50" className={inputCls} data-testid="uom-rebase-factor" />
                </div>
              </div>

              {preview && (
                <div className="mt-2 text-xs space-y-0.5" data-testid="uom-rebase-preview">
                  <p className="text-foreground">
                    Stok <b>{preview.before.total_qty} {preview.from_uom}</b> → <b>{preview.after.total_qty} {preview.to_uom}</b>
                  </p>
                  <p className="text-foreground">
                    HPP <b>{preview.before.unit_cost}</b>/{preview.from_uom} → <b>{preview.after.unit_cost}</b>/{preview.to_uom}
                  </p>
                  <p className="text-foreground">
                    Min. stok <b>{preview.before.min_stock}</b> → <b>{preview.after.min_stock}</b>
                  </p>
                  <p className={preview.nilai_persediaan_tetap
                    ? 'text-[hsl(var(--success))]' : 'text-[hsl(var(--destructive))]'}>
                    {preview.nilai_persediaan_tetap
                      ? 'Nilai persediaan tidak berubah.'
                      : 'PERINGATAN: nilai persediaan bergeser — periksa faktornya.'}
                  </p>
                </div>
              )}
              {rebaseErr && (
                <p className="mt-2 text-xs text-[hsl(var(--destructive))]" data-testid="uom-rebase-error">{rebaseErr}</p>
              )}

              <div className="flex gap-2 mt-3">
                <Button type="button" variant="outline" size="sm" onClick={() => setRebaseOpen(false)}>Batal</Button>
                <Button type="button" variant="outline" size="sm" disabled={busy}
                  onClick={() => callRebase(true)} data-testid="uom-rebase-preview-btn">
                  {busy ? 'Menghitung…' : 'Pratinjau'}
                </Button>
                <Button type="button" size="sm" disabled={busy || !preview}
                  onClick={() => callRebase(false)} data-testid="uom-rebase-apply-btn">
                  Terapkan
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default UomEditor;
