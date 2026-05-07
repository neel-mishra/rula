import { cn } from "@/lib/utils";

type CountVariant = "err" | "warn" | "default";

const countVariantMap: Record<CountVariant, string> = {
  err:     "bg-err-soft text-err",
  warn:    "bg-warn-soft text-warn",
  default: "bg-surface-muted text-ink-2",
};

interface TabProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active: boolean;
  count?: number;
  countVariant?: CountVariant;
}

export function Tab({ active, count, countVariant = "default", className, children, ...props }: TabProps) {
  return (
    <button
      role="tab"
      aria-selected={active}
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px",
        active
          ? "text-brand border-brand"
          : "text-ink-2 border-transparent hover:text-navy hover:border-line",
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined && (
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[11px] font-semibold",
            countVariantMap[countVariant],
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export function Tabs({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn("flex border-b border-line", className)}
      {...props}
    >
      {children}
    </div>
  );
}
