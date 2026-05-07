import { Skeleton } from "@/components/ui/skeleton";

export function InboxSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-4 py-3.5 border-b border-line">
          <Skeleton className="w-8 h-8 rounded-full shrink-0" />
          <div className="flex-1 flex flex-col gap-2">
            <Skeleton className="h-3.5 w-[200px]" />
            <Skeleton className="h-3 w-[160px]" />
            <Skeleton className="h-8 w-full rounded-lg" />
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
      ))}
    </>
  );
}
