import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface ListRowProps {
  leading?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
  isSelected?: boolean;
  className?: string;
}

export function ListRow({
  leading,
  title,
  subtitle,
  meta,
  trailing,
  onClick,
  isSelected,
  className,
}: ListRowProps) {
  const interactive = Boolean(onClick);

  const body = (
    <>
      {leading && <div className="shrink-0 mt-0.5">{leading}</div>}
      <div className="min-w-0 flex-1">
        {title && (
          <div className="text-sm font-medium truncate">{title}</div>
        )}
        {subtitle && (
          <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
        )}
        {meta && (
          <p className="text-xs text-muted-foreground mt-0.5">{meta}</p>
        )}
      </div>
      {trailing && <div className="shrink-0">{trailing}</div>}
    </>
  );

  if (interactive) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex w-full items-start gap-3 py-3 px-2 rounded text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          isSelected && "bg-muted/60",
          className,
        )}
      >
        {body}
      </button>
    );
  }

  return (
    <div className={cn("flex items-start gap-3 py-3", className)}>
      {body}
    </div>
  );
}

export function ListRowGroup({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <ul className={cn("divide-y", className)}>{children}</ul>;
}
