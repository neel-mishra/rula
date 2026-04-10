"use client";

/** Primary stripe = brand purple; accent = softer lilac (MAP card), on-brand vs generic emerald. */
type Accent = "brand" | "accent";

type Props = {
  title: string;
  description: string;
  cta: string;
  href: string;
  accent?: Accent;
  disabled?: boolean;
  disabledReason?: string;
};

function ExternalIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

export function ToolSelectorCard({
  title,
  description,
  cta,
  href,
  accent = "brand",
  disabled,
  disabledReason,
}: Props) {
  const accentBar =
    accent === "accent"
      ? "bg-[var(--rula-accent)] group-hover:bg-[var(--rula-accent-hover)]"
      : "bg-[var(--rula-brand)] group-hover:bg-[var(--rula-brand-hover)]";

  if (disabled) {
    return (
      <div
        className="flex flex-col overflow-hidden rounded-2xl border-2 border-dashed border-[var(--rula-border)] bg-[var(--rula-surface-muted)] opacity-90"
        aria-disabled="true"
      >
        <div className={`h-1 w-full shrink-0 ${accentBar} opacity-50`} />
        <div className="flex flex-col p-8">
          <h3 className="text-xl font-semibold text-[var(--rula-navy)]">{title}</h3>
          <p className="mt-3 flex-1 text-sm leading-relaxed text-[var(--rula-text-secondary)]">{description}</p>
          <p className="mt-6 text-sm text-amber-800 dark:text-amber-200">{disabledReason}</p>
        </div>
      </div>
    );
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative flex flex-col overflow-hidden rounded-2xl border-2 border-[var(--rula-border)] bg-[var(--rula-surface)] shadow-sm transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-[var(--rula-brand)] hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--rula-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--rula-canvas)]"
    >
      <div className={`h-1.5 w-full shrink-0 ${accentBar} transition-colors`} />
      <div className="flex flex-1 flex-col p-8">
        <h3 className="text-xl font-semibold tracking-tight text-[var(--rula-navy)]">{title}</h3>
        <p className="mt-3 flex-1 text-sm leading-relaxed text-[var(--rula-text-secondary)]">{description}</p>
        <p className="mt-4 text-xs text-[var(--rula-text-tertiary)]">
          Opens the Streamlit workspace in a new tab. Use the ⋮ menu there for theme, rerun, and cache.
        </p>
        <span className="mt-5 inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--rula-brand)] px-5 py-3 text-center text-sm font-semibold text-[var(--rula-brand-foreground)] transition group-hover:bg-[var(--rula-brand-hover)]">
          {cta}
          <ExternalIcon className="opacity-90" />
        </span>
      </div>
    </a>
  );
}
