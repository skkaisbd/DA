/**
 * ResponsiveTableWrapper — TD-015 Mobile Responsive Tables (Session #11.13)
 * ==========================================================================
 *
 * Provides a smart horizontally-scrollable wrapper for ANY table on mobile.
 * Features:
 *   - Horizontal scroll with auto-detect of overflow
 *   - Scroll-shadow indicators (visual cues on left/right edges when scrollable)
 *   - Auto-hide indicators when no overflow
 *   - Works for any <table>, <DataTable>, or custom grid layout
 *   - Optional stickyFirstCol — make first column sticky-left on horizontal scroll
 *
 * Usage:
 *
 *   <ResponsiveTableWrapper>
 *     <table>...</table>
 *   </ResponsiveTableWrapper>
 *
 *   // Or wrap a DataTable
 *   <ResponsiveTableWrapper stickyFirstCol>
 *     <DataTable ... />
 *   </ResponsiveTableWrapper>
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

export function ResponsiveTableWrapper({
  children,
  className,
  stickyFirstCol = false,
  showScrollShadow = true,
}) {
  const scrollRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateShadows = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 1);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateShadows();
    el.addEventListener('scroll', updateShadows, { passive: true });
    const ro = new ResizeObserver(updateShadows);
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', updateShadows);
      ro.disconnect();
    };
  }, [updateShadows, children]);

  return (
    <div className={cn('relative', className)}>
      {/* Left scroll-shadow */}
      {showScrollShadow && canScrollLeft && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-0 z-10 w-6 bg-gradient-to-r from-background to-transparent"
        />
      )}
      {/* Right scroll-shadow */}
      {showScrollShadow && canScrollRight && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 z-10 w-6 bg-gradient-to-l from-background to-transparent"
        />
      )}
      {/* Scroll container */}
      <div
        ref={scrollRef}
        className={cn(
          'overflow-x-auto -mx-1 px-1',
          stickyFirstCol &&
            '[&_table_tbody_tr_td:first-child]:sticky [&_table_tbody_tr_td:first-child]:left-0 [&_table_tbody_tr_td:first-child]:bg-card [&_table_thead_tr_th:first-child]:sticky [&_table_thead_tr_th:first-child]:left-0 [&_table_thead_tr_th:first-child]:bg-card',
        )}
      >
        {children}
      </div>
    </div>
  );
}

export default ResponsiveTableWrapper;
