"use client";

type Step = { id: string; label: string };

type Props = {
  steps: Step[];
  activeIndex: number;
};

export function StepIndicator({ steps, activeIndex }: Props) {
  return (
    <ol className="flex flex-wrap items-center gap-2 sm:gap-4" aria-label="Steps to launch a tool">
      {steps.map((s, i) => {
        const done = i < activeIndex;
        const current = i === activeIndex;
        return (
          <li key={s.id} className="flex items-center gap-2 sm:gap-4">
            <span className="flex items-center gap-2">
              <span
                className={[
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors",
                  done
                    ? "bg-[var(--rula-lavender)] text-[var(--rula-brand)] ring-1 ring-[var(--rula-border)]"
                    : current
                      ? "bg-[var(--rula-brand)] text-[var(--rula-brand-foreground)] ring-2 ring-[var(--rula-brand)] ring-offset-2 ring-offset-[var(--rula-canvas)]"
                      : "border-2 border-[var(--rula-border-strong)] bg-[var(--rula-surface)] text-[var(--rula-text-tertiary)]",
                ].join(" ")}
                aria-current={current ? "step" : undefined}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={[
                  "text-sm font-medium",
                  current ? "text-[var(--rula-navy)]" : "text-[var(--rula-text-tertiary)]",
                ].join(" ")}
              >
                {s.label}
              </span>
            </span>
            {i < steps.length - 1 && (
              <span className="hidden h-px w-6 bg-[var(--rula-border-strong)] sm:block" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}
