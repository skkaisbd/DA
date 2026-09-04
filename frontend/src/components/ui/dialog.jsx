import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const Dialog = DialogPrimitive.Root

const DialogTrigger = DialogPrimitive.Trigger

const DialogPortal = DialogPrimitive.Portal

const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80  data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props} />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

// ─────────────────────────────────────────────────────────────────────────────
// A11y polish (Session #11.13 — TD-A11y):
// Radix DialogContent emits a console warning when no aria-describedby is set.
// To keep all 80+ existing DialogContent consumers warning-free without
// touching each file, we auto-generate a stable id and render an invisible
// (sr-only) DialogDescription fallback ONLY when the consumer hasn't
// already supplied `aria-describedby` or a child <DialogDescription>.
// ─────────────────────────────────────────────────────────────────────────────
function _hasDialogDescriptionChild(children) {
  let found = false
  React.Children.forEach(children, (child) => {
    if (found) return
    if (!React.isValidElement(child)) return
    const type = child.type
    if (type === DialogDescription) {
      found = true
      return
    }
    // Radix Description fallback (some consumers wrap directly)
    const displayName = type?.displayName || type?.name || ""
    if (displayName === "DialogDescription" || displayName === "Description") {
      found = true
      return
    }
    if (child.props?.children) {
      if (_hasDialogDescriptionChild(child.props.children)) {
        found = true
      }
    }
  })
  return found
}

function _hasDialogTitleChild(children) {
  let found = false
  React.Children.forEach(children, (child) => {
    if (found) return
    if (!React.isValidElement(child)) return
    const type = child.type
    if (type === DialogTitle) {
      found = true
      return
    }
    const displayName = type?.displayName || type?.name || ""
    if (displayName === "DialogTitle" || displayName === "Title") {
      found = true
      return
    }
    if (child.props?.children) {
      if (_hasDialogTitleChild(child.props.children)) {
        found = true
      }
    }
  })
  return found
}

const DialogContent = React.forwardRef(({ className, children, "aria-describedby": ariaDescribedBy, "aria-labelledby": ariaLabelledBy, ...props }, ref) => {
  const autoDescId = React.useId()
  const autoTitleId = React.useId()
  const hasDescChild = React.useMemo(
    () => _hasDialogDescriptionChild(children),
    [children]
  )
  const hasTitleChild = React.useMemo(
    () => _hasDialogTitleChild(children),
    [children]
  )
  // If consumer explicitly provided aria-describedby OR already has a
  // DialogDescription child, do not auto-inject anything.
  // Otherwise use auto-generated id + hidden description for a11y compliance.
  const needsAutoDesc = !ariaDescribedBy && !hasDescChild
  const needsAutoTitle = !ariaLabelledBy && !hasTitleChild
  const finalDescribedBy = ariaDescribedBy || (needsAutoDesc ? autoDescId : undefined)
  const finalLabelledBy = ariaLabelledBy || (needsAutoTitle ? autoTitleId : undefined)
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        aria-describedby={finalDescribedBy}
        aria-labelledby={finalLabelledBy}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
          className
        )}
        {...props}>
        {needsAutoTitle && (
          <DialogPrimitive.Title id={autoTitleId} className="sr-only">
            Dialog
          </DialogPrimitive.Title>
        )}
        {needsAutoDesc && (
          <DialogPrimitive.Description id={autoDescId} className="sr-only">
            Dialog content
          </DialogPrimitive.Description>
        )}
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  )
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)}
    {...props} />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props} />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
