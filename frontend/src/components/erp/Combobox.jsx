import { useState, useMemo } from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { cn } from '@/lib/utils';

/* PT Rahaza ERP — Combobox (Sprint 27)
   Drop-in replacement for native <select>.

   Features:
   - Searchable filter
   - Keyboard navigation
   - Clearable (optional)
   - Disabled state
   - "data-testid" passthrough

   Usage:
     <Combobox
       value={form.shift_id}
       onChange={(v) => setForm(f => ({...f, shift_id: v}))}
       options={shifts.map(s => ({ value: s.id, label: `${s.code} — ${s.name}` }))}
       placeholder="Pilih shift..."
       searchPlaceholder="Cari shift..."
       emptyMessage="Tidak ada shift cocok"
       data-testid="shift-combobox"
     />

   Props:
     - value, onChange (controlled)
     - options: [{ value, label, description?, disabled? }]
     - placeholder: string ("Pilih...")
     - searchPlaceholder: string ("Cari...")
     - emptyMessage: string ("Tidak ada hasil")
     - disabled: bool
     - clearable: bool (show "x" to clear)
     - className: extra styles for trigger
     - size: 'sm' | 'md' (default 'md')
*/

export function Combobox({
  value,
  onChange,
  options = [],
  placeholder = 'Pilih...',
  searchPlaceholder = 'Cari...',
  emptyMessage = 'Tidak ada hasil',
  disabled = false,
  clearable = false,
  className = '',
  size = 'md',
  'data-testid': testId,
}) {
  const [open, setOpen] = useState(false);
  const safeOptions = useMemo(() => options || [], [options]);

  const selected = useMemo(
    () => safeOptions.find((o) => String(o.value) === String(value)),
    [safeOptions, value]
  );

  const heightCls = size === 'sm' ? 'h-8 text-xs' : 'h-9 text-sm';

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          data-testid={testId}
          className={cn(
            'inline-flex items-center justify-between w-full rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] px-3 text-foreground hover:bg-[var(--glass-bg-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors',
            heightCls,
            className
          )}
        >
          <span
            className={cn(
              'truncate text-left flex-1',
              !selected && 'text-muted-foreground'
            )}
          >
            {selected ? selected.label : placeholder}
          </span>
          <span className="ml-2 flex items-center gap-1 shrink-0">
            {clearable && selected && !disabled && (
              <span
                role="button"
                tabIndex={0}
                aria-label="Hapus pilihan"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  onChange?.('');
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation();
                    e.preventDefault();
                    onChange?.('');
                  }
                }}
                className="text-muted-foreground hover:text-foreground p-0.5 rounded"
                data-testid={testId ? `${testId}-clear` : undefined}
              >
                <X className="w-3 h-3" />
              </span>
            )}
            <ChevronsUpDown className="w-3.5 h-3.5 text-muted-foreground" />
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="p-0 w-[var(--radix-popover-trigger-width)] min-w-[220px] bg-[var(--popover-surface)] backdrop-blur-lg border border-[var(--glass-border)]"
        align="start"
        sideOffset={4}
      >
        <Command>
          <CommandInput placeholder={searchPlaceholder} className="h-9 text-sm" />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            <CommandGroup>
              {safeOptions.map((opt) => (
                <CommandItem
                  key={String(opt.value)}
                  value={`${opt.label} ${opt.value}`}
                  disabled={opt.disabled}
                  onSelect={() => {
                    onChange?.(opt.value);
                    setOpen(false);
                  }}
                  data-testid={opt.testId || (testId ? `${testId}-option-${opt.value}` : undefined)}
                >
                  <Check
                    className={cn(
                      'mr-2 h-3.5 w-3.5 transition-opacity',
                      String(value) === String(opt.value)
                        ? 'opacity-100 text-primary'
                        : 'opacity-0'
                    )}
                  />
                  <span className="flex-1 truncate">{opt.label}</span>
                  {opt.description && (
                    <span className="ml-2 text-[11px] text-muted-foreground truncate max-w-[40%]">
                      {opt.description}
                    </span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default Combobox;
