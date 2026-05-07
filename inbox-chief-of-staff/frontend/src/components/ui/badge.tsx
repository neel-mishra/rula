import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:     "bg-navy text-surface",
        secondary:   "bg-surface-muted text-navy",
        destructive: "bg-err-soft text-err",
        outline:     "border border-line text-ink-2",
        urgent:      "bg-urgent-bg text-urgent-fg",
        normal:      "bg-normal-bg text-normal-fg",
        brief:       "bg-brief-bg text-brief-fg",
        archive:     "bg-archive-bg text-archive-fg",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
