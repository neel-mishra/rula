import { cn } from "@/lib/utils";
import { forwardRef } from "react";

type FieldAs = "input" | "textarea";

type FieldProps = {
  as?: FieldAs;
  label?: string;
  hint?: string;
  error?: string;
  className?: string;
  id?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "as"> &
  Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "as">;

const inputClass =
  "border border-line rounded-lg px-3 py-2 text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-brand w-full text-navy placeholder:text-ink-3 disabled:opacity-50";

export const Field = forwardRef<HTMLInputElement | HTMLTextAreaElement, FieldProps>(
  ({ as = "input", label, hint, error, className, id, ...props }, ref) => {
    const inputId = id ?? (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-[14px] font-medium text-navy">
            {label}
          </label>
        )}
        {as === "textarea" ? (
          <textarea
            ref={ref as React.Ref<HTMLTextAreaElement>}
            id={inputId}
            className={cn(inputClass, "resize-none", className)}
            {...(props as React.TextareaHTMLAttributes<HTMLTextAreaElement>)}
          />
        ) : (
          <input
            ref={ref as React.Ref<HTMLInputElement>}
            id={inputId}
            className={cn(inputClass, className)}
            {...(props as React.InputHTMLAttributes<HTMLInputElement>)}
          />
        )}
        {error ? (
          <p className="text-[12px] text-err">{error}</p>
        ) : hint ? (
          <p className="text-[12px] text-ink-3">{hint}</p>
        ) : null}
      </div>
    );
  }
);
Field.displayName = "Field";
