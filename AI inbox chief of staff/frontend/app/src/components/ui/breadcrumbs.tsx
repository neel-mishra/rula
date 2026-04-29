"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  "": "Dashboard",
  assistant: "Assistant",
  memories: "Memories",
  briefs: "Briefs",
  experiments: "Experiments",
  slo: "SLOs",
  activity: "Activity",
  settings: "Settings",
  admin: "Admin",
  mailbox: "Mailbox",
};

function prettify(segment: string): string {
  const mapped = LABELS[segment];
  if (mapped) return mapped;
  // UUIDs and numeric IDs become "Details"
  if (/^[0-9a-f-]{8,}$/.test(segment) || /^\d+$/.test(segment)) return "Details";
  return segment.replace(/-/g, " ");
}

export function Breadcrumbs({ className }: { className?: string }) {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) return null;

  const crumbs = segments.map((seg, i) => {
    const href = "/" + segments.slice(0, i + 1).join("/");
    const isLast = i === segments.length - 1;
    return { href, label: prettify(seg), isLast };
  });

  return (
    <nav
      aria-label="Breadcrumb"
      className={cn(
        "hidden sm:flex items-center text-xs text-muted-foreground gap-1 min-w-0",
        className,
      )}
    >
      <Link href="/" className="hover:text-foreground transition-colors">
        {LABELS[""]}
      </Link>
      {crumbs.map((c) => (
        <span key={c.href} className="flex items-center gap-1 min-w-0">
          <ChevronRight className="h-3 w-3 shrink-0" />
          {c.isLast ? (
            <span className="text-foreground truncate">{c.label}</span>
          ) : (
            <Link
              href={c.href}
              className="hover:text-foreground transition-colors truncate"
            >
              {c.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
