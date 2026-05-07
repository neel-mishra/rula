import { cn } from "@/lib/utils";

type TagTone = "lavender" | "ok" | "warn" | "err" | "soft";

const toneMap: Record<TagTone, string> = {
  lavender: "bg-lavender text-brand",
  ok:       "bg-ok-soft text-ok",
  warn:     "bg-warn-soft text-warn",
  err:      "bg-err-soft text-err",
  soft:     "bg-surface-muted text-ink-2",
};

interface TagProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: TagTone;
}

export function Tag({ tone = "soft", className, children, ...props }: TagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        toneMap[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
