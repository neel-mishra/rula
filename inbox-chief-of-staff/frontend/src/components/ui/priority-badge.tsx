import { cn } from "@/lib/utils";
import type { Priority } from "@/types";

const colorMap: Record<Priority, string> = {
  urgent:  "bg-urgent-bg text-urgent-fg",
  normal:  "bg-normal-bg text-normal-fg",
  brief:   "bg-brief-bg text-brief-fg",
  archive: "bg-archive-bg text-archive-fg",
};

const sizeMap = {
  sm: "px-1.5 py-0.5 text-[11px]",
  md: "px-2.5 py-0.5 text-xs",
  lg: "px-3 py-1 text-sm",
};

const labelMap: Record<Priority, string> = {
  urgent:  "URGENT",
  normal:  "NORMAL",
  brief:   "BRIEF",
  archive: "ARCHIVE",
};

interface PriorityBadgeProps {
  priority: Priority;
  size?: keyof typeof sizeMap;
  className?: string;
}

export function PriorityBadge({ priority, size = "md", className }: PriorityBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-semibold",
        colorMap[priority],
        sizeMap[size],
        className,
      )}
    >
      {labelMap[priority]}
    </span>
  );
}
