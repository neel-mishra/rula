import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { forwardRef } from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:       "bg-brand text-white hover:bg-brand-hover",
        destructive:   "bg-err text-white hover:opacity-90",
        outline:       "border border-line bg-surface text-navy hover:bg-lavender",
        secondary:     "bg-surface-muted text-navy hover:bg-lavender",
        ghost:         "text-ink-2 hover:bg-lavender hover:text-navy",
        soft:          "bg-brand-soft text-brand hover:bg-brand-soft/80",
        success:       "bg-ok text-white hover:opacity-90",
        danger:        "bg-err text-white hover:opacity-90",
        "danger-ghost":"text-err hover:bg-err-soft",
        link:          "text-brand underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        xs:      "h-6 px-2 text-xs",
        sm:      "h-7 px-3 text-xs",
        lg:      "h-11 px-6",
        icon:    "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  )
);
Button.displayName = "Button";
