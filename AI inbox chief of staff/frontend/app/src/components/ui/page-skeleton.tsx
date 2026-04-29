import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function CardGridSkeleton({
  count = 3,
  cols = "md:grid-cols-2 lg:grid-cols-3",
}: {
  count?: number;
  cols?: string;
}) {
  return (
    <div className={cn("grid gap-4", cols)}>
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} className="animate-pulse">
          <CardHeader>
            <div className="h-5 w-2/3 rounded bg-muted" />
            <div className="h-4 w-1/3 rounded bg-muted" />
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <ul className="divide-y">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="py-3 flex gap-3">
          <div className="h-5 w-24 rounded bg-muted animate-pulse" />
          <div className="flex-1 space-y-1">
            <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
            <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded bg-muted" />
      <div className="h-48 animate-pulse rounded bg-muted" />
      <div className="h-32 animate-pulse rounded bg-muted" />
    </div>
  );
}
