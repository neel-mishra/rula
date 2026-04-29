import Link from "next/link";
import type { ComponentType } from "react";

import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

export interface FeatureCalloutProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
  href: string;
  className?: string;
}

export function FeatureCallout({
  icon: Icon,
  title,
  description,
  href,
  className,
}: FeatureCalloutProps) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex gap-3 rounded-lg border bg-card p-3 transition-colors hover:border-primary/30 hover:bg-muted/40",
        className,
      )}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium flex items-center gap-1">
          {title}
          <ArrowRight className="h-3 w-3 opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0" />
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </Link>
  );
}
