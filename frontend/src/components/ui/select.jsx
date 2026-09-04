import * as React from "react"
import * as SelectPrimitive from "@radix-ui/react-select"
import { Check, ChevronDown, ChevronUp, Search } from "lucide-react"

import { cn } from "@/lib/utils"

const Select = SelectPrimitive.Root

const SelectGroup = SelectPrimitive.Group

const SelectValue = SelectPrimitive.Value

// ─────────────────────────────────────────────────────────────────────────────
// Searchable-select enhancement (global, opt-out safe)
// Adds an in-dropdown search box to the shared shadcn <Select> so EVERY consumer
// gains type-to-filter for free. Design goals:
//   - Zero per-file changes: driven by children of <SelectContent>.
//   - "auto" mode: search box only appears when there are many options
//     (>= threshold). Small enum selects (status/bulan/terms) stay simple.
//   - Non-destructive filtering: non-matching <SelectItem>s are CSS-hidden
//     (kept mounted) so the React tree stays stable and SelectValue keeps working.
//   - Keyboard-safe: letter keys type into the box (Radix typeahead suppressed);
//     Arrow/Enter/Escape still drive Radix navigation & close.
// ─────────────────────────────────────────────────────────────────────────────
const SelectSearchContext = React.createContext({ query: "", enabled: false })

function nodeText(node) {
  if (node == null || node === false || node === true) return ""
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join(" ")
  if (React.isValidElement(node)) return nodeText(node.props?.children)
  return ""
}

// Collect [{text, value}] for every SelectItem in the children tree.
function collectItems(children, acc) {
  React.Children.forEach(children, (ch) => {
    if (!React.isValidElement(ch)) return
    if (ch.type === SelectItem) {
      acc.push({
        text: nodeText(ch.props?.children),
        value: String(ch.props?.value ?? ""),
      })
    } else if (ch.props && ch.props.children) {
      collectItems(ch.props.children, acc)
    }
  })
  return acc
}

const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-9 w-full items-center justify-between whitespace-nowrap rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background data-[placeholder]:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1",
      className
    )}
    {...props}>
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName

const SelectScrollUpButton = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}>
    <ChevronUp className="h-4 w-4" />
  </SelectPrimitive.ScrollUpButton>
))
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName

const SelectScrollDownButton = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}>
    <ChevronDown className="h-4 w-4" />
  </SelectPrimitive.ScrollDownButton>
))
SelectScrollDownButton.displayName =
  SelectPrimitive.ScrollDownButton.displayName

const SelectContent = React.forwardRef(({
  className,
  children,
  position = "popper",
  searchable = "auto",          // true | false | "auto"
  searchThreshold = 8,           // "auto" shows search when items >= this
  searchPlaceholder = "Cari...",
  onOpenAutoFocus,
  ...props
}, ref) => {
  const [query, setQuery] = React.useState("")
  const inputRef = React.useRef(null)

  const items = React.useMemo(() => collectItems(children, []), [children])
  const enabled = searchable === true || (searchable === "auto" && items.length >= searchThreshold)

  const q = query.trim().toLowerCase()
  const matchCount = React.useMemo(() => {
    if (!enabled || !q) return items.length
    return items.filter((it) => (`${it.text} ${it.value}`).toLowerCase().includes(q)).length
  }, [enabled, q, items])

  const handleOpenAutoFocus = (e) => {
    if (enabled) {
      // Keep focus in the search box instead of jumping to an item.
      e.preventDefault()
      setQuery("")
      requestAnimationFrame(() => inputRef.current?.focus())
    }
    onOpenAutoFocus?.(e)
  }

  return (
    <SelectSearchContext.Provider value={{ query: q, enabled }}>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          ref={ref}
          className={cn(
            "relative z-50 max-h-[--radix-select-content-available-height] min-w-[8rem] overflow-y-auto overflow-x-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 origin-[--radix-select-content-transform-origin]",
            position === "popper" &&
              "data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1",
            className
          )}
          position={position}
          onOpenAutoFocus={handleOpenAutoFocus}
          {...props}>
          <SelectScrollUpButton />
          <SelectPrimitive.Viewport
            className={cn("p-1", position === "popper" &&
              "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]")}>
            {enabled && (
              <div className="sticky top-0 z-10 -mx-1 -mt-1 mb-1 flex items-center gap-2 border-b border-border/60 bg-popover px-2 py-1.5">
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
                  onKeyDown={(e) => {
                    // Let Radix handle navigation/selection/close; block letter typeahead.
                    if (!["ArrowDown", "ArrowUp", "Enter", "Escape", "Tab"].includes(e.key)) {
                      e.stopPropagation()
                    }
                  }}
                  className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
                />
              </div>
            )}
            {children}
            {enabled && q && matchCount === 0 && (
              <div className="px-2 py-3 text-center text-sm text-muted-foreground">Tidak ada hasil</div>
            )}
          </SelectPrimitive.Viewport>
          <SelectScrollDownButton />
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectSearchContext.Provider>
  )
})
SelectContent.displayName = SelectPrimitive.Content.displayName

const SelectLabel = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    className={cn("px-2 py-1.5 text-sm font-semibold", className)}
    {...props} />
))
SelectLabel.displayName = SelectPrimitive.Label.displayName

const SelectItem = React.forwardRef(({ className, children, ...props }, ref) => {
  const { query, enabled } = React.useContext(SelectSearchContext)
  const hidden = enabled && query
    ? !(`${nodeText(children)} ${props.value ?? ""}`).toLowerCase().includes(query)
    : false
  return (
    <SelectPrimitive.Item
      ref={ref}
      className={cn(
        "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        hidden && "hidden",
        className
      )}
      {...props}>
      <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="h-4 w-4" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  )
})
SelectItem.displayName = SelectPrimitive.Item.displayName

const SelectSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator
    ref={ref}
    className={cn("-mx-1 my-1 h-px bg-muted", className)}
    {...props} />
))
SelectSeparator.displayName = SelectPrimitive.Separator.displayName

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
}
