"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, FileEdit, BookOpen, Settings, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";

const NAV_ITEMS = [
  { href: "/inbox", label: "Inbox", icon: MessageSquare },
  { href: "/drafts", label: "Drafts", icon: FileEdit },
  { href: "/brief", label: "Brief", icon: BookOpen },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  const handleSignOut = async () => {
    await api.auth.logout();
    window.location.href = "/login";
  };

  return (
    <aside className="w-56 h-screen flex flex-col border-r bg-gray-50 shrink-0">
      {/* Logo */}
      <div className="px-4 py-5 border-b">
        <span className="font-semibold text-gray-900 text-sm">Inbox Chief of Staff</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                active
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t px-4 py-3">
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-800 transition-colors w-full"
        >
          <LogOut size={14} />
          Sign out
        </button>
      </div>
    </aside>
  );
}
