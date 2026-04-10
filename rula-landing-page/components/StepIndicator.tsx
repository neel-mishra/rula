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
                    ? "bg-[var(--rula-green)] text-white"
                    : current
                      ? "bg-[var(--rula-blue)] text-white ring-2 ring-[var(--rula-blue)] ring-offset-2 ring-offset-[var(--rula-canvas)] dark:ring-offset-slate-900"
                      : "border-2 border-slate-300 bg-white text-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-400",
                ].join(" ")}
                aria-current={current ? "step" : undefined}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={[
                  "text-sm font-medium",
                  current ? "text-[var(--rula-navy)] dark:text-slate-100" : "text-slate-500 dark:text-slate-400",
                ].join(" ")}
              >
                {s.label}
              </span>
            </span>
            {i < steps.length - 1 && (
              <span className="hidden h-px w-6 bg-slate-300 sm:block dark:bg-slate-600" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}
