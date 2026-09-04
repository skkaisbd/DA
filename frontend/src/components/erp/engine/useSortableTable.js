// Phase 8.4 — Reusable sortable-table hook with localStorage persistence.
// Usage:
//   const { sortedData, sortKey, sortDir, toggleSort } = useSortableTable(rawData, {
//     storageKey: 'productionPOTable',
//     defaultKey: 'created_at',
//     defaultDir: 'desc',
//     getValue: (row, key) => row[key],  // optional custom extractor
//   });
//
// Then render <SortableHeader sortKey={sortKey} sortDir={sortDir} columnKey="po_number" onToggle={toggleSort}>...</SortableHeader>
// in your table headers.

import { useCallback, useEffect, useMemo, useState } from 'react';

const readPersisted = (storageKey) => {
  if (!storageKey) return null;
  try {
    const raw = window.localStorage.getItem(`sort:${storageKey}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed;
  } catch (_) { return null; }
};

const writePersisted = (storageKey, state) => {
  if (!storageKey) return;
  try {
    window.localStorage.setItem(`sort:${storageKey}`, JSON.stringify(state));
  } catch (_) { /* ignore quota / privacy mode */ }
};

const parseDate = (v) => {
  if (!v) return null;
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
};

const smartCompare = (a, b) => {
  if (a === b) return 0;
  if (a == null) return 1;    // null/undefined sorts last
  if (b == null) return -1;
  // Try numeric compare
  const na = typeof a === 'number' ? a : Number(a);
  const nb = typeof b === 'number' ? b : Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb) && String(a).trim() !== '' && String(b).trim() !== '') {
    if (na < nb) return -1;
    if (na > nb) return 1;
    return 0;
  }
  // Try date compare
  if (typeof a === 'string' && typeof b === 'string') {
    const da = parseDate(a);
    const db = parseDate(b);
    if (da != null && db != null) {
      if (da < db) return -1;
      if (da > db) return 1;
      return 0;
    }
  }
  // Fallback: string locale compare
  const sa = String(a);
  const sb = String(b);
  return sa.localeCompare(sb, undefined, { numeric: true, sensitivity: 'base' });
};

export function useSortableTable(data, options = {}) {
  const {
    storageKey = null,
    defaultKey = null,
    defaultDir = 'asc',
    getValue = (row, key) => (row ? row[key] : undefined),
  } = options;

  const persisted = useMemo(() => readPersisted(storageKey), [storageKey]);
  const [sortKey, setSortKey] = useState(persisted?.sortKey ?? defaultKey);
  const [sortDir, setSortDir] = useState(persisted?.sortDir ?? defaultDir);

  useEffect(() => {
    if (!storageKey) return;
    writePersisted(storageKey, { sortKey, sortDir });
  }, [storageKey, sortKey, sortDir]);

  const toggleSort = useCallback((key) => {
    setSortKey((prevKey) => {
      if (prevKey !== key) {
        setSortDir('asc');
        return key;
      }
      // same key — cycle asc → desc → off (null)
      setSortDir((prevDir) => {
        if (prevDir === 'asc') return 'desc';
        if (prevDir === 'desc') return null; // will clear sortKey below
        return 'asc';
      });
      return key;
    });
  }, []);

  // Clear sortKey when direction goes to null (off)
  useEffect(() => {
    if (sortDir === null && sortKey !== null) {
      setSortKey(null);
    }
  }, [sortDir, sortKey]);

  const sortedData = useMemo(() => {
    if (!Array.isArray(data)) return data;
    if (!sortKey || !sortDir) return data;
    const copy = data.slice();
    const mult = sortDir === 'desc' ? -1 : 1;
    copy.sort((a, b) => {
      const va = getValue(a, sortKey);
      const vb = getValue(b, sortKey);
      return smartCompare(va, vb) * mult;
    });
    return copy;
  }, [data, sortKey, sortDir, getValue]);

  return { sortedData, sortKey, sortDir, toggleSort, setSortKey, setSortDir };
}

// Small reusable header component for custom tables
export function SortableHeader({ columnKey, sortKey, sortDir, onToggle, className = '', children, align = 'left', sortable = true }) {
  const active = sortable && sortKey === columnKey && !!sortDir;
  const indicator = active ? (sortDir === 'asc' ? '▲' : '▼') : (sortable ? '↕' : '');
  const alignCls = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';
  return (
    <th
      role={sortable ? 'button' : undefined}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={sortable ? () => onToggle(columnKey) : undefined}
      data-testid={sortable ? `sort-header-${columnKey}` : undefined}
      className={`${alignCls} ${sortable ? 'cursor-pointer select-none hover:bg-muted' : ''} ${className}`}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortable && (
          <span
            className={`text-[10px] ${active ? 'text-blue-600' : 'text-muted-foreground/50'}`}
            aria-hidden="true"
          >
            {indicator}
          </span>
        )}
      </span>
    </th>
  );
}

export default useSortableTable;
