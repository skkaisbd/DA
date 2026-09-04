import * as React from "react"
import { ChevronDown, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * SmartNativeSelect — a DROP-IN replacement for a native <select>.
 *
 * Goal: give type-to-filter search to the many native <select> dropdowns that
 * are bound to large reference lists (materials, employees, accounts, ...),
 * WITHOUT changing the caller's data flow.
 *
 * Migration is a tag rename only:
 *   <select value={v} onChange={e => setV(e.target.value)} className="...">
 *     <option value="">All</option>
 *     {items.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
 *   </select>
 *  ->
 *   <SmartNativeSelect value={v} onChange={e => setV(e.target.value)} className="...">
 *     ...same <option> children...
 *   </SmartNativeSelect>
 *
 * - onChange is called native-style: onChange({ target: { value } }).
 * - <option> (and <optgroup>) children are parsed automatically.
 * - Search box appears automatically when options >= searchThreshold (default 8),
 *   or force via searchable={true}. Small enums stay simple (searchable={false} or few opts).
 *
 * TESTABILITY / A11Y (2026-07-25): karena ini BUKAN <select> native, dropdown-nya
 * dulu tidak bisa dikemudikan otomatis (opsi = <button> tanpa penanda) sehingga
 * beberapa alur UI tak pernah bisa diuji agent. Sekarang, bila caller mengirim
 * `data-testid="x"`, komponen mengekspos:
 *     x            → root
 *     x-trigger    → tombol pembuka (role=combobox, aria-expanded, data-value)
 *     x-list       → panel opsi (role=listbox)
 *     x-option-<v> → tiap opsi (role=option, aria-selected, data-value)
 * Pola pakai di test: klik `x-trigger`, lalu klik `x-option-<value>`.
 */
function nodeText(node) {
  if (node == null || node === false || node === true) return ""
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join(" ")
  if (React.isValidElement(node)) return nodeText(node.props?.children)
  return ""
}

function parseOptions(children, acc) {
  React.Children.forEach(children, (ch) => {
    if (!React.isValidElement(ch)) return
    if (ch.type === "option") {
      acc.push({
        value: String(ch.props.value ?? ""),
        label: nodeText(ch.props.children) || String(ch.props.value ?? ""),
        disabled: !!ch.props.disabled,
      })
    } else if (ch.type === "optgroup" || ch.props?.children) {
      parseOptions(ch.props.children, acc)
    }
  })
  return acc
}

export default function SmartNativeSelect({
  value = "",
  onChange,
  children,
  className = "",
  wrapperClassName = "",
  disabled = false,
  searchable = "auto",
  searchThreshold = 8,
  searchPlaceholder = "Cari...",
  placeholder,
  id,
  name,
  "data-testid": dataTestId,
  ...rest
}) {
  const options = React.useMemo(() => parseOptions(children, []), [children])
  const enabled = searchable === true || (searchable === "auto" && options.length >= searchThreshold)

  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const rootRef = React.useRef(null)
  const inputRef = React.useRef(null)

  const selected = React.useMemo(
    () => options.find((o) => o.value === String(value)),
    [options, value]
  )

  // Determine placeholder: explicit prop, else the empty-value option's label.
  const emptyOpt = options.find((o) => o.value === "")
  const ph = placeholder || emptyOpt?.label || "— Pilih —"

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
  }, [options, query])

  React.useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
        setQuery("")
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  React.useEffect(() => {
    if (open && enabled) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open, enabled])

  const emit = (v) => {
    onChange?.({ target: { value: v, name } })
    setOpen(false)
    setQuery("")
  }

  // Mirror the caller's width so filter-bar selects (w-40, w-32, ...) don't stretch,
  // while form fields (w-full or none) fill their container.
  const widthMatch = className.match(/\bw-(?:full|\d+(?:\.\d+)?|\[[^\]]+\]|px|screen|min|max|fit|auto)\b/)
  const wrapperWidth = wrapperClassName || (widthMatch ? widthMatch[0] : "w-full")

  return (
    <div ref={rootRef} className={cn("relative", wrapperWidth)} data-testid={dataTestId} id={id}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        data-testid={dataTestId ? `${dataTestId}-trigger` : undefined}
        data-value={String(value ?? "")}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 py-2 text-left text-sm text-foreground shadow-sm transition-colors",
          disabled ? "cursor-not-allowed opacity-50" : "hover:border-ring focus:outline-none focus:ring-1 focus:ring-ring",
          open && "ring-1 ring-ring",
          className
        )}
        {...rest}
      >
        <span className={cn("truncate", selected && selected.value !== "" ? "text-foreground" : "text-muted-foreground")}>
          {selected ? selected.label : ph}
        </span>
        <ChevronDown className={cn("h-4 w-4 flex-shrink-0 opacity-50 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-lg">
          {enabled && (
            <div className="flex items-center gap-2 border-b border-border/60 bg-popover px-2 py-1.5">
              <Search className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                autoComplete="off"
                spellCheck={false}
                placeholder={searchPlaceholder}
                data-testid="select-search-input"
                onChange={(e) => setQuery(e.target.value)}
                className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
              />
            </div>
          )}
          <div className="max-h-60 overflow-y-auto p-1" role="listbox"
            data-testid={dataTestId ? `${dataTestId}-list` : "select-option-list"}>
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-sm text-muted-foreground">Tidak ada hasil</div>
            ) : (
              filtered.map((o, i) => (
                <button
                  key={`${o.value}-${i}`}
                  type="button"
                  disabled={o.disabled}
                  onClick={() => !o.disabled && emit(o.value)}
                  role="option"
                  aria-selected={o.value === String(value)}
                  data-value={o.value}
                  data-testid={dataTestId ? `${dataTestId}-option-${o.value}` : undefined}
                  className={cn(
                    "flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm transition-colors",
                    o.disabled ? "cursor-not-allowed opacity-50" : "hover:bg-accent hover:text-accent-foreground",
                    o.value === String(value) && "bg-accent/60 font-medium"
                  )}
                >
                  <span className="truncate">{o.label}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
