"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Inbox,
  LayoutDashboard,
  MessageSquare,
  Activity,
  Settings,
  LogOut,
  FileText,
  Brain,
  FlaskConical,
  Gauge,
  Shield,
  History,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAuth } from "@/lib/auth";

type NavItem = {
  title: string;
  href: string;
  icon: LucideIcon;
  adminOnly?: boolean;
};

const navItems: NavItem[] = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard },
  { title: "Assistant", href: "/assistant", icon: MessageSquare },
  { title: "Memories", href: "/memories", icon: Brain },
  { title: "Briefs", href: "/briefs", icon: FileText },
  { title: "Experiments", href: "/experiments", icon: FlaskConical },
  { title: "SLOs", href: "/slo", icon: Gauge },
  { title: "Activity", href: "/activity", icon: Activity },
  { title: "Transparency", href: "/transparency", icon: History },
  { title: "Settings", href: "/settings", icon: Settings },
  { title: "Admin", href: "/admin", icon: Shield, adminOnly: true },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { logout, currentUser } = useAuth();

  const isAdmin = currentUser?.role === "admin";
  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || isAdmin,
  );

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Inbox className="h-5 w-5" />
          <span className="font-semibold text-sm">Inbox Chief of Staff</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {visibleItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    render={<Link href={item.href} />}
                    isActive={
                      item.href === "/"
                        ? pathname === "/"
                        : pathname.startsWith(item.href)
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="border-t p-2">
        {currentUser && (
          <div className="px-2 pb-2 text-xs text-muted-foreground truncate">
            {currentUser.email}
            {isAdmin && <span className="ml-1 text-primary">· admin</span>}
          </div>
        )}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => {
                logout();
                window.location.href = "/login";
              }}
            >
              <LogOut className="h-4 w-4" />
              <span>Sign out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
