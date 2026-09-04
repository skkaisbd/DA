import * as React from "react"

import { cn } from "@/lib/utils"
import { ResponsiveTableWrapper } from "./responsive-table-wrapper"

/**
 * Session #11.13 TD-015: Table is now wrapped in ResponsiveTableWrapper,
 * which adds:
 *   - Horizontal scroll on small viewports
 *   - Scroll-shadow indicators (left/right) that auto-fade based on scroll position
 *   - Optional sticky-first-column via `stickyFirstCol`
 *
 * Props:
 *   - `stickyFirstCol` (bool) — sticky first column on horizontal scroll (default: false)
 *   - `wrapperClassName` (string) — extra classes for the wrapper div
 *   - `responsive` (bool) — disable wrapper entirely if false (default: true)
 */
const Table = React.forwardRef(({ className, stickyFirstCol = false, wrapperClassName, responsive = true, ...props }, ref) => {
  const tableEl = (
    <table
      ref={ref}
      className={cn("w-full caption-bottom text-sm min-w-max", className)}
      {...props}
    />
  );
  if (!responsive) {
    return <div className="relative w-full overflow-auto">{tableEl}</div>;
  }
  return (
    <ResponsiveTableWrapper stickyFirstCol={stickyFirstCol} className={wrapperClassName}>
      {tableEl}
    </ResponsiveTableWrapper>
  );
})
Table.displayName = "Table"

const TableHeader = React.forwardRef(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
))
TableHeader.displayName = "TableHeader"

const TableBody = React.forwardRef(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props} />
))
TableBody.displayName = "TableBody"

const TableFooter = React.forwardRef(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn("border-t bg-muted/50 font-medium [&>tr]:last:border-b-0", className)}
    {...props} />
))
TableFooter.displayName = "TableFooter"

const TableRow = React.forwardRef(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
      className
    )}
    {...props} />
))
TableRow.displayName = "TableRow"

const TableHead = React.forwardRef(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "h-10 px-2 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className
    )}
    {...props} />
))
TableHead.displayName = "TableHead"

const TableCell = React.forwardRef(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn(
      "p-2 align-middle [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
      className
    )}
    {...props} />
))
TableCell.displayName = "TableCell"

const TableCaption = React.forwardRef(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn("mt-4 text-sm text-muted-foreground", className)}
    {...props} />
))
TableCaption.displayName = "TableCaption"

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
