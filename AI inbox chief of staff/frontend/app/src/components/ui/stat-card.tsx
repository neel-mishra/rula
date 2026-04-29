import type { ComponentType, ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatTone = "default" | "success" | "warning" | "danger" | "info";
type StatVariant = "compact" | "prominent";

const toneClass: Record<StatTone, string> = {
  default: "",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  info: "text-info",
};

export interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ComponentType<{ className?: string }>;
  secondary?: ReactNode;
  tone?: StatTone;
  variant?: StatVariant;
  loading?: boolean;
  className?: string;
}

export function StatCard({
  label,
  value,
  icon: Icon,
  secondary,
  tone = "default",
  variant = "compact",
  loading = false,
  className,
}: StatCardProps) {
  const iconClass = "h-5 w-5";
  const numberClass = cn(
    "text-2xl font-semibold tabular-nums",
    tone !== "default" && toneClass[tone],
  );

  if (variant === "prominent") {
    return (
      <Card className={className}>
        <CardContent className="pt-6 pb-5 text-center">
          {Icon && (
            <Icon className={cn(iconClass, "mx-auto mb-2 text-muted-foreground")} />
          )}
          <p className={cn(numberClass, "block")}>
            {loading ? (
              <span className="inline-block h-7 w-12 bg-muted animate-pulse rounded" />
            ) : (
              value
            )}
          </p>
          <p className="text-xs text-muted-foreground mt-1">{label}</p>
          {secondary && !loading && (
            <p className="text-xs text-muted-foreground">{secondary}</p>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardContent className="py-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {label}
        </div>
        <p className={cn(numberClass, "mt-1")}>
          {loading ? (
            <span className="inline-block h-7 w-12 bg-muted animate-pulse rounded" />
          ) : (
            value
          )}
        </p>
        {secondary && !loading && (
          <p className="text-xs text-muted-foreground">{secondary}</p>
        )}
      </CardContent>
    </Card>
  );
}
