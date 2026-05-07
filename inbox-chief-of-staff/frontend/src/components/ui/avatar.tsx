import { cn } from "@/lib/utils";

interface AvatarProps {
  name: string;
  size?: "sm" | "md";
  className?: string;
}

function hue(name: string): number {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.charCodeAt(i);
  return sum % 360;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const sizeMap = { sm: "w-7 h-7 text-[11px]", md: "w-8 h-8 text-xs" };

export function Avatar({ name, size = "md", className }: AvatarProps) {
  const h = hue(name);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white select-none",
        sizeMap[size],
        className,
      )}
      style={{ backgroundColor: `hsl(${h}, 50%, 40%)` }}
      aria-label={name}
    >
      {initials(name)}
    </span>
  );
}
