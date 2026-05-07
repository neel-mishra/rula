import { cn } from "@/lib/utils";

interface ConfidenceMeterProps {
  value: number;
  className?: string;
}

export function ConfidenceMeter({ value, className }: ConfidenceMeterProps) {
  const pct = Math.max(0, Math.min(1, value));
  const low = pct < 0.6;
  const label = `${Math.round(pct * 100)}% confidence`;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", low ? "bg-warn" : "bg-accent")}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-ink-3">{label}</span>
        {low && (
          <span className="inline-flex items-center rounded-full bg-warn-soft text-warn px-2 py-0.5 text-[10px] font-medium">
            low
          </span>
        )}
      </div>
    </div>
  );
}
