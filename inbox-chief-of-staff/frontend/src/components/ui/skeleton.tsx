import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-shimmer rounded bg-surface-muted", className)} />;
}
