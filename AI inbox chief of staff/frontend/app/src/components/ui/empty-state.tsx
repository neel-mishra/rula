import type { ComponentType, ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  wrapInCard?: boolean;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  wrapInCard = true,
  className,
}: EmptyStateProps) {
  const body = (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-12 px-6",
        className,
      )}
    >
      <Icon className="h-10 w-10 text-muted-foreground mb-4" />
      <p className="font-medium">{title}</p>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-md">
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div className="flex gap-2 mt-4">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );

  if (!wrapInCard) return body;

  return (
    <Card>
      <CardContent className="p-0">{body}</CardContent>
    </Card>
  );
}
