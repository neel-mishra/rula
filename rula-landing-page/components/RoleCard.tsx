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
        "group flex w-full flex-col rounded-2xl border-2 p-5 text-left transition-all duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--rula-blue)] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900",
        selected
          ? "border-[var(--rula-blue)] bg-white shadow-md shadow-slate-200/80 dark:bg-slate-800 dark:shadow-slate-950/40"
          : "border-slate-200 bg-slate-50/80 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-slate-500 dark:hover:bg-slate-800",
      ].join(" ")}
    >
      <span className="text-lg font-semibold text-[var(--rula-navy)] dark:text-slate-100">{label}</span>
      <span className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{description}</span>
      <span
        className={[
          "mt-4 inline-flex items-center gap-1.5 text-sm font-medium",
          selected ? "text-[var(--rula-blue)]" : "text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200",
        ].join(" ")}
      >
        {selected ? (
          <>
            <span
              className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--rula-blue)]/10 text-xs text-[var(--rula-blue)]"
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
