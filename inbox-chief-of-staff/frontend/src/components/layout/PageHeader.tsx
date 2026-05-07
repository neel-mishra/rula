import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  sub?: string;
  right?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, sub, right, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur px-6 py-4 flex items-center justify-between shrink-0",
        className,
      )}
    >
      <div>
        <h1 className="text-[20px] font-semibold text-navy leading-tight">{title}</h1>
        {sub && <p className="text-sm text-ink-2 mt-0.5">{sub}</p>}
      </div>
      {right && <div className="ml-auto">{right}</div>}
    </header>
  );
}
