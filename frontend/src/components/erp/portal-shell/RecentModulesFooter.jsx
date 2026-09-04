/**
 * RecentModulesFooter — shows last 5 visited modules in sidebar footer.
 * Persists to localStorage per-portal.
 *
 * 2026-08-13 (temuan verifikasi F4.4): id yang TIDAK punya label di navigasi mana
 * pun (mis. deep-link lama `toko-products` yang kini hanya sebuah pengalih ke
 * `marketing-catalog`) dulu tampil sebagai **id mentah** — "toko-products" —
 * di daftar "Terakhir". Bagi pemakai itu tulisan yang tidak berarti apa pun, dan
 * mengkliknya hanya mengulang pengalihan. Sekarang id semacam itu **tidak
 * dimasukkan** ke daftar: daftar ini hanya berisi pintu yang benar-benar ada di
 * navigasi (punya nama), sehingga tidak ada baris "hantu" yang membingungkan.
 */

import { useState, useEffect } from 'react';
import { PORTAL_NAV, findModuleLabel } from './portalNav';

const MAX = 5;

/** Nama pintu menurut navigasi; `null` bila id ini tidak punya pintu bernama. */
function labelOf(modId) {
  for (const pid of Object.keys(PORTAL_NAV)) {
    const label = findModuleLabel(pid, modId);
    if (label && label !== modId) return label;
  }
  return null;
}

export default function RecentModulesFooter({ portal, currentModule, onModuleChange }) {
  const STORAGE_KEY = `erp_recent_${portal}`;

  const [recent, setRecent] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  });

  // Update recent list when module changes
  useEffect(() => {
    if (!currentModule || !labelOf(currentModule)) return;
    setRecent((prev) => {
      const next = [currentModule, ...prev.filter((m) => m !== currentModule)].slice(0, MAX);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // localStorage unavailable
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentModule, portal]);

  // Show only those NOT currently active and yang punya nama, max 4 items
  const shown = recent
    .filter((m) => m !== currentModule)
    .map((m) => ({ id: m, label: labelOf(m) }))
    .filter((m) => !!m.label)
    .slice(0, 4);
  if (shown.length === 0) return null;

  return (
    <div className="mb-1">
      <p className="text-[10px] text-foreground/30 uppercase tracking-wider mb-1">Terakhir</p>
      <div className="space-y-0.5">
        {shown.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => onModuleChange?.(id)}
            className="w-full text-left px-2 py-1 rounded-md text-[11px] text-foreground/50 hover:text-foreground hover:bg-[var(--glass-bg-hover)] transition-colors duration-150 truncate"
            data-testid={`recent-module-${id}`}
            title={label}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
