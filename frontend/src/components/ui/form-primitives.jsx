/**
 * Canonical Form Components — TD-016 Form Patterns (Session #11.13)
 * ==================================================================
 *
 * Lightweight, stateless form primitives that work with the prevailing
 * useState-based pattern in this codebase (no react-hook-form required).
 *
 * Goal: Replace the ad-hoc <div className="space-y-...">/<label>/<input>
 * scaffolding found in 39+ modal forms with a consistent set of components
 * for label, helper text, required-marker, error display, and spacing.
 *
 * Modules can adopt these incrementally — they don't need any wrapper
 * <Form> context (unlike shadcn ui/form.jsx which requires react-hook-form).
 *
 * Components:
 *   <FormSection title="..." description="..." >          // labelled card section
 *   <FormGrid cols={1|2}>                                  // 1 or 2 column responsive grid
 *   <FormField label="..." htmlFor="..." required error="..." helper="..." >  // single labelled field
 *   <FormActions align="right|between">                    // footer with cancel/submit
 *
 * Usage:
 *   <form onSubmit={handleSubmit} className="space-y-6">
 *     <FormSection title="Data Dasar" description="Informasi utama produk">
 *       <FormGrid cols={2}>
 *         <FormField label="Nama Produk" htmlFor="name" required error={errors.name}>
 *           <input id="name" value={name} onChange={...} className="input-base" />
 *         </FormField>
 *         <FormField label="Kategori" htmlFor="cat" helper="Pilih kategori produk">
 *           <select id="cat" ...>...</select>
 *         </FormField>
 *       </FormGrid>
 *     </FormSection>
 *     <FormActions>
 *       <button type="button">Batal</button>
 *       <button type="submit">Simpan</button>
 *     </FormActions>
 *   </form>
 */
import React from 'react';
import { cn } from '@/lib/utils';

/* ───────────────── FormSection ─────────────────
   A grouped section of fields with optional title & description.
   Renders nothing extra if title/description omitted (acts as a passthrough). */
export function FormSection({ title, description, children, className }) {
  return (
    <section className={cn('space-y-3', className)}>
      {(title || description) && (
        <header className="space-y-0.5">
          {title && (
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          )}
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </header>
      )}
      <div className="space-y-3">{children}</div>
    </section>
  );
}

/* ───────────────── FormGrid ─────────────────
   1- or 2-column responsive grid (collapses to 1 col below sm). */
export function FormGrid({ cols = 2, gap = 3, className, children }) {
  const colClass = cols === 1 ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2';
  return (
    <div className={cn('grid', colClass, `gap-${gap}`, className)}>
      {children}
    </div>
  );
}

/* ───────────────── FormField ─────────────────
   Labelled field with optional helper text & error display.
   The child input must wire `id={htmlFor}` for proper label association. */
export function FormField({
  label,
  htmlFor,
  required = false,
  error,
  helper,
  className,
  labelClassName,
  fullSpan = false,
  children,
}) {
  return (
    <div className={cn('space-y-1.5', fullSpan && 'sm:col-span-2', className)}>
      {label && (
        <label
          htmlFor={htmlFor}
          className={cn(
            'block text-xs font-medium text-foreground/80',
            labelClassName,
          )}
        >
          {label}
          {required && (
            <span className="text-red-500 ml-0.5" aria-label="wajib diisi">*</span>
          )}
        </label>
      )}
      {children}
      {error && (
        <p className="text-[11px] text-red-500" role="alert">
          {error}
        </p>
      )}
      {!error && helper && (
        <p className="text-[11px] text-muted-foreground">{helper}</p>
      )}
    </div>
  );
}

/* ───────────────── FormActions ─────────────────
   Footer container for submit/cancel buttons with consistent spacing. */
export function FormActions({ align = 'right', className, children }) {
  const alignClass = {
    right:    'justify-end',
    between:  'justify-between',
    left:     'justify-start',
    center:   'justify-center',
  }[align] || 'justify-end';
  return (
    <div
      className={cn(
        'flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-2 pt-4 border-t border-[var(--glass-border)]',
        alignClass,
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ───────────────── Canonical input-base class ─────────────────
   Use on raw <input>, <select>, <textarea> to get consistent visual style.
   Modules can also pass `className={INPUT_BASE_CLASS}` or use shadcn Input. */
export const INPUT_BASE_CLASS =
  'block w-full h-9 px-2.5 text-sm border border-[var(--glass-border)] ' +
  'rounded-md bg-[var(--input-surface)] text-foreground placeholder:text-muted-foreground ' +
  'focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] focus:border-transparent ' +
  'disabled:opacity-50 disabled:cursor-not-allowed transition-colors';

export const TEXTAREA_BASE_CLASS =
  INPUT_BASE_CLASS.replace('h-9', 'min-h-[80px] py-2');

export default FormSection;
