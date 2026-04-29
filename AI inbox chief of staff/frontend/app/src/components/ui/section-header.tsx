import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface SectionHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function SectionHeader({
  title,
  subtitle,
  actions,
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 flex-wrap",
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
