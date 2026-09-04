
import { useState, useRef, useEffect, useMemo } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';

/**
 * SearchableSelect - Reusable searchable dropdown
 * Props:
 *   options: [{ value, label, sub? }]  — array of choices
 *   value: string                       — currently selected value
 *   onChange: fn(value)                 — callback
 *   placeholder: string
 *   disabled: bool
 *   className: string
 *   required: bool
 *   data-testid: string                 — test identifier for automation
 */
export default function SearchableSelect({
  options = [],
  value = '',
  onChange,
  placeholder = '— Pilih —',
  disabled = false,
  className = '',
  required = false,
  'data-testid': dataTestId,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ref = useRef(null);
  const inputRef = useRef(null);

  const selected = useMemo(() => options.find(o => o.value === value), [options, value]);

  const filtered = useMemo(() => {
    if (!search) return options;
    const q = search.toLowerCase();
    return options.filter(o =>
      o.label?.toLowerCase().includes(q) ||
      o.sub?.toLowerCase().includes(q)
    );
  }, [options, search]);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  const handleSelect = (opt) => {
    onChange(opt.value);
    setOpen(false);
    setSearch('');
  };

  const handleClear = (e) => {
    e.stopPropagation();
    onChange('');
    setSearch('');
  };

  return (
    <div ref={ref} className={`relative ${className}`} data-testid={dataTestId}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => { if (!disabled) setOpen(o => !o); }}
        data-testid={dataTestId ? `${dataTestId}-trigger` : undefined}
        className={`w-full flex items-center justify-between border rounded-lg px-3 py-2 text-sm bg-card text-left transition-all
          ${disabled ? 'opacity-50 cursor-not-allowed border-border' : 'cursor-pointer border-border hover:border-border focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-400'}
          ${open ? 'border-blue-400 ring-2 ring-blue-100' : ''}`}
      >
        <span className={selected ? 'text-foreground truncate flex-1' : 'text-muted-foreground/70 truncate flex-1'}>
          {selected ? (
            <span className="flex flex-col">
              <span className="font-medium">{selected.label}</span>
              {selected.sub && <span className="text-xs text-muted-foreground/70">{selected.sub}</span>}
            </span>
          ) : placeholder}
        </span>
        <div className="flex items-center gap-1 ml-2 flex-shrink-0">
          {value && !disabled && (
            <span
              onClick={handleClear}
              className="text-muted-foreground/50 hover:text-muted-foreground cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
          <ChevronDown className={`w-4 h-4 text-muted-foreground/70 transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 right-0 bg-card border border-border rounded-xl shadow-xl overflow-hidden">
          {/* Search input */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border/60">
            <Search className="w-3.5 h-3.5 text-muted-foreground/70 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Cari..."
              className="flex-1 text-sm text-foreground/90 placeholder:text-muted-foreground/60 focus:outline-none bg-transparent"
              onClick={e => e.stopPropagation()}
            />
          </div>
          {/* Options */}
          <div className="max-h-52 overflow-y-auto">
            {!required && (
              <button
                type="button"
                onClick={() => handleSelect({ value: '', label: placeholder })}
                className="w-full text-left px-3 py-2 text-sm text-muted-foreground hover:bg-muted/60 transition-colors"
              >
                {placeholder}
              </button>
            )}
            {filtered.length === 0 ? (
              <div className="px-3 py-3 text-sm text-muted-foreground/70 text-center">Tidak ada hasil</div>
            ) : (
              filtered.map((opt, oi) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => handleSelect(opt)}
                  data-testid={dataTestId ? `${dataTestId}-opt-${oi}` : undefined}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 transition-colors flex flex-col
                    ${value === opt.value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-foreground/90'}`}
                >
                  <span>{opt.label}</span>
                  {opt.sub && <span className="text-xs text-muted-foreground/70">{opt.sub}</span>}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
