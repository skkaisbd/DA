/**
 * useUomOptions — daftar satuan SAH + faktornya untuk material tertentu.
 *
 * KENAPA ADA (ROADMAP P1, 2026-08-05)
 * Backend sudah lama menerima `input_uom` / `qty_uom` / `counted_uom` di titik
 * masuk stok (penerimaan, put-away, opname gudang, opname aksesoris,
 * pengeluaran material/aksesoris, cutting) — tetapi LAYARNYA tidak punya
 * pemilih satuan, sehingga operator hanya bisa memasukkan satuan dasar.
 * Hook ini menyediakan datanya (satu endpoint, di-cache, batch) supaya semua
 * layar memakai daftar satuan yang PASTI bisa dikonversi server.
 *
 * Endpoint: GET /api/rahaza/materials/uom-options?material_ids=a,b,c
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from '@/lib/api';

const cache = new Map();     // material_id → option
const inflight = new Map();  // material_id → Promise

const chunk = (arr, n) => {
  const out = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
};

/** Ambil opsi satuan untuk sekumpulan id (memakai cache + dedup request). */
export async function fetchUomOptions(ids = []) {
  const want = [...new Set(ids.filter(Boolean))];
  const missing = want.filter((id) => !cache.has(id) && !inflight.has(id));

  for (const group of chunk(missing, 80)) {
    const p = apiGet(`/rahaza/materials/uom-options?material_ids=${group.join(',')}`)
      .then((data) => {
        const opts = data?.options || {};
        group.forEach((id) => cache.set(id, opts[id] || null));
        return opts;
      })
      .catch(() => { group.forEach((id) => cache.set(id, null)); return {}; })
      .finally(() => group.forEach((id) => inflight.delete(id)));
    group.forEach((id) => inflight.set(id, p));
  }

  await Promise.all(want.map((id) => inflight.get(id)).filter(Boolean));
  const out = {};
  want.forEach((id) => { if (cache.get(id)) out[id] = cache.get(id); });
  return out;
}

/** Buang cache (dipakai setelah kemasan material diubah di Master Material). */
export function clearUomOptionsCache() {
  cache.clear();
}

/**
 * @param {string[]} materialIds daftar id material yang sedang tampil di layar
 * @returns {{options: Record<string, object>, loading: boolean, reload: Function}}
 */
export default function useUomOptions(materialIds = []) {
  const [options, setOptions] = useState({});
  const [loading, setLoading] = useState(false);
  const key = [...new Set((materialIds || []).filter(Boolean))].sort().join(',');
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  const load = useCallback(async () => {
    if (!key) { setOptions({}); return; }
    setLoading(true);
    try {
      const data = await fetchUomOptions(key.split(','));
      if (mounted.current) setOptions(data);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [key]);

  useEffect(() => { load(); }, [load]);

  const reload = useCallback(() => { clearUomOptionsCache(); return load(); }, [load]);

  return { options, loading, reload };
}
