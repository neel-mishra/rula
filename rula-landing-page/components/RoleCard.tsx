"use client";

import type { RoleId } from "@/lib/copy";

type Props = {
  id: RoleId;
  label: string;
  description: string;
  selected: boolean;
  onSelect: (id: RoleId) => void;
};

export function RoleCard({ id, label, description, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={() => onSelect(id)}
      className={[
        "group flex w-full flex-col rounded-2xl border-2 p-5 text-left transition-all duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--rula-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--rula-canvas)]",
        selected
          ? "border-[var(--rula-brand)] bg-[var(--rula-surface)] shadow-md shadow-[var(--rula-brand-soft)]"
          : "border-[var(--rula-border)] bg-[var(--rula-surface-muted)] hover:-translate-y-0.5 hover:border-[var(--rula-border-strong)] hover:bg-[var(--rula-surface)]",
      ].join(" ")}
    >
      <span className="text-lg font-semibold text-[var(--rula-navy)]">{label}</span>
      <span className="mt-2 text-sm leading-relaxed text-[var(--rula-text-secondary)]">{description}</span>
      <span
        className={[
          "mt-4 inline-flex items-center gap-1.5 text-sm font-medium",
          selected
            ? "text-[var(--rula-brand)]"
            : "text-[var(--rula-text-tertiary)] group-hover:text-[var(--rula-text-secondary)]",
        ].join(" ")}
      >
        {selected ? (
          <>
            <span
              className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--rula-brand-soft)] text-xs text-[var(--rula-brand)]"
              aria-hidden
            >
              ✓
            </span>
            Selected
          </>
        ) : (
          "Select"
        )}
      </span>
    </button>
  );
}
