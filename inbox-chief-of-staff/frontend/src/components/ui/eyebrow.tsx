import { cn } from "@/lib/utils";

export function Eyebrow({ className, children }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-[11px] font-semibold uppercase tracking-widest text-ink-3", className)}>
      {children}
    </p>
  );
}
