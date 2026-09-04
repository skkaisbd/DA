import { forwardRef } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

/* PT Rahaza ERP — IconButton (Sprint 27)
   Reusable icon-only button with built-in Tooltip.
   Wrap any icon-only button with this for consistent UX & a11y.

   Usage:
     <IconButton
       label="Refresh data"
       onClick={fetchData}
       data-testid="refresh-btn"
     >
       <RefreshCw className="w-4 h-4" />
     </IconButton>

   Required: label (visible in tooltip + aria-label)
*/

export const IconButton = forwardRef(function IconButton(
  {
    label,
    children,
    className = 'p-2 rounded-xl hover:bg-[var(--glass-bg-hover)] transition-colors text-muted-foreground',
    side = 'top',
    type = 'button',
    delayDuration = 250,
    disabled,
    ...rest
  },
  ref
) {
  const btn = (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      disabled={disabled}
      className={className}
      {...rest}
    >
      {children}
    </button>
  );

  // If disabled, show button without tooltip wrapping (Radix tooltip on disabled
  // requires extra workaround — we keep aria-label so screen readers still get info)
  if (disabled) return btn;

  return (
    <Tooltip delayDuration={delayDuration}>
      <TooltipTrigger asChild>{btn}</TooltipTrigger>
      <TooltipContent
        side={side}
        className="max-w-xs px-2.5 py-1.5 text-[11px] leading-relaxed bg-[var(--glass-bg)] backdrop-blur-lg border border-[var(--glass-border)] text-foreground shadow-lg"
      >
        {label}
      </TooltipContent>
    </Tooltip>
  );
});

export default IconButton;
