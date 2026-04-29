"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw,
  Shield,
  ShieldAlert,
  Users,
  Inbox,
  FileText,
  ArchiveRestore,
  Undo2,
  MessageSquareWarning,
  Activity,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  api,
  type AdminActivityStats,
  type AdminUserSummary,
  type UserRole,
} from "@/lib/api";
import { StatCard } from "@/components/ui/stat-card";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const WINDOW_OPTIONS = [
  { value: "7", label: "Last 7 days" },
  { value: "14", label: "Last 14 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

export default function AdminPage() {
  const { currentUser, isLoading: authLoading } = useAuth();
  const isAdmin = currentUser?.role === "admin";

  const [stats, setStats] = useState<AdminActivityStats | null>(null);
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [windowDays, setWindowDays] = useState("7");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const [s, u] = await Promise.all([
        api.admin.activityStats({ window_days: Number(windowDays) }),
        api.admin.listUsers({ limit: 200 }),
      ]);
      setStats(s);
      setUsers(u.users);
      setTotal(u.total);
    } catch {
      toast.error("Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, [isAdmin, windowDays]);

  useEffect(() => {
    if (!authLoading) load();
  }, [authLoading, load]);

  async function toggleRole(user: AdminUserSummary) {
    const nextRole: UserRole = user.role === "admin" ? "user" : "admin";
    setUpdatingId(user.id);
    try {
      await api.admin.setRole(user.id, nextRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, role: nextRole } : u)),
      );
      toast.success(`${user.email}: ${nextRole}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Role change failed";
      toast.error(msg);
    } finally {
      setUpdatingId(null);
    }
  }

  if (authLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-48 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="max-w-2xl">
        <Card>
          <CardContent className="flex flex-col items-center py-16 text-center">
            <ShieldAlert className="h-10 w-10 text-destructive mb-3" />
            <p className="font-medium">Admin access required</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              This page is only visible to accounts with the admin role.
              Contact an existing admin to grant access.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Admin
          </h1>
          <p className="text-sm text-muted-foreground">
            Cross-user operations — activity rollups and role management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={windowDays}
            onValueChange={(v) => v && setWindowDays(v)}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOW_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw
              className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Cross-user activity */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Activity ({stats?.window_days ?? 7}d)
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          <StatCard
            icon={Users}
            label="Users"
            value={stats?.total_users ?? 0}
            secondary={
              stats ? `${stats.active_users_in_window} active` : undefined
            }
            loading={loading}
          />
          <StatCard
            icon={Inbox}
            label="Mailboxes"
            value={stats?.total_mailboxes ?? 0}
            loading={loading}
          />
          <StatCard
            icon={ArchiveRestore}
            label="Triaged"
            value={stats?.triage_decisions ?? 0}
            secondary={
              stats ? `${stats.corrections_submitted} corrections` : undefined
            }
            loading={loading}
          />
          <StatCard
            icon={FileText}
            label="Drafts"
            value={stats?.drafts_generated ?? 0}
            loading={loading}
          />
          <StatCard
            icon={Activity}
            label="Mutations"
            value={stats?.mutations_applied ?? 0}
            loading={loading}
          />
          <StatCard
            icon={Undo2}
            label="Undos"
            value={stats?.undos_performed ?? 0}
            loading={loading}
          />
          <StatCard
            icon={MessageSquareWarning}
            label="Critical events"
            value={stats?.critical_audit_events ?? 0}
            loading={loading}
            tone={
              (stats?.critical_audit_events ?? 0) > 0 ? "danger" : "default"
            }
          />
        </div>
      </div>

      <Separator />

      {/* Users */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Users ({total})
          </h2>
        </div>
        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-4 space-y-2">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-12 bg-muted rounded animate-pulse"
                  />
                ))}
              </div>
            ) : users.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                No users yet
              </div>
            ) : (
              <ul className="divide-y">
                {users.map((u) => {
                  const isSelf = u.id === currentUser?.id;
                  const nextRole: UserRole =
                    u.role === "admin" ? "user" : "admin";
                  return (
                    <li
                      key={u.id}
                      className="flex items-center justify-between gap-3 px-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium truncate">
                            {u.email}
                          </p>
                          <Badge
                            variant={
                              u.role === "admin" ? "default" : "outline"
                            }
                            className="text-[10px]"
                          >
                            {u.role}
                          </Badge>
                          {!u.is_active && (
                            <Badge
                              variant="secondary"
                              className="text-[10px]"
                            >
                              inactive
                            </Badge>
                          )}
                          {isSelf && (
                            <Badge
                              variant="outline"
                              className="text-[10px]"
                            >
                              you
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {u.mailbox_count} mailbox
                          {u.mailbox_count === 1 ? "" : "es"} · joined{" "}
                          {formatRelativeTime(u.created_at)}
                        </p>
                      </div>
                      <AlertDialog>
                        <AlertDialogTrigger
                          render={
                            <Button
                              size="xs"
                              variant="outline"
                              disabled={
                                updatingId === u.id ||
                                (isSelf && u.role === "admin")
                              }
                            />
                          }
                        >
                          {updatingId === u.id
                            ? "Updating..."
                            : `Make ${nextRole}`}
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              Change {u.email} to {nextRole}?
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              {nextRole === "admin"
                                ? "They will gain access to cross-user data and role management."
                                : "They will lose access to the admin dashboard. You cannot demote yourself."}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => toggleRole(u)}>
                              Confirm
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {stats?.critical_audit_events && stats.critical_audit_events > 0 ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2 text-destructive">
              <AlertCircle className="h-4 w-4" />
              {stats.critical_audit_events} critical event
              {stats.critical_audit_events === 1 ? "" : "s"} in window
            </CardTitle>
            <CardDescription>
              Review the audit trail via the activity feed or CloudWatch.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}
    </div>
  );
}

