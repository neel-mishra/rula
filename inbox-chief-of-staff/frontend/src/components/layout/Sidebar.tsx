"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, FileEdit, BookOpen, Settings, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";
import { Avatar } from "@/components/ui/avatar";
import { useQuery } from "@tanstack/react-query";

const NAV_ITEMS = [
  { href: "/inbox",    label: "Inbox",    icon: MessageSquare, countKey: "urgent" as const },
  { href: "/drafts",   label: "Drafts",   icon: FileEdit,      countKey: "drafts"  as const },
  { href: "/brief",    label: "Brief",    icon: BookOpen,      countKey: null },
  { href: "/settings", label: "Settings", icon: Settings,      countKey: null },
];

interface SidebarProps {
  urgentCount?: number;
  draftsCount?: number;
}

export function Sidebar({ urgentCount, draftsCount }: SidebarProps) {
  const pathname = usePathname();

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.auth.me(),
    retry: false,
    staleTime: 1000 * 60 * 5,
  });

  const handleSignOut = async () => {
    await api.auth.logout();
    window.location.href = "/login";
  };

  const counts: Record<string, number | undefined> = {
    urgent: urgentCount,
    drafts: draftsCount,
  };

  return (
    <aside className="w-56 shrink-0 h-screen flex flex-col bg-surface-muted border-r border-line">
      <div className="px-4 py-5 border-b border-line">
        <span className="font-semibold text-navy text-sm">Inbox Chief of Staff</span>
      </div>

      <nav className="flex-1 px-2 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon, countKey }) => {
          const active = pathname.startsWith(href);
          const count = countKey ? counts[countKey] : undefined;
          const isUrgent = countKey === "urgent";
          const isDrafts = countKey === "drafts";

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                active
                  ? "bg-brand-soft text-brand font-semibold"
                  : "text-ink-2 hover:bg-lavender hover:text-navy",
              )}
            >
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {count !== undefined && count > 0 && (
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                    isUrgent && "bg-err-soft text-err",
                    isDrafts && "bg-warn-soft text-warn",
                  )}
                >
                  {count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line px-4 py-3 flex items-center gap-2">
        {user?.email && (
          <Avatar name={user.email.split("@")[0]} size="sm" />
        )}
        <button
          onClick={handleSignOut}
          className="flex items-center gap-1.5 text-xs text-ink-3 hover:text-navy transition-colors"
        >
          <LogOut size={12} />
          Sign out
        </button>
      </div>
    </aside>
  );
}
