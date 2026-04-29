"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Mail, Plus, Shield, Eye, Zap, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { WelcomeCard } from "@/components/onboarding/welcome-card";
import { api, type MailboxSummary } from "@/lib/api";
import { toast } from "sonner";

const modeConfig = {
  shadow: { label: "Shadow", icon: Shield, variant: "secondary" as const },
  observe: { label: "Observe", icon: Eye, variant: "outline" as const },
  auto: { label: "Auto", icon: Zap, variant: "default" as const },
};

export default function DashboardPage() {
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.mailboxes.list();
      setMailboxes(data);
    } catch {
      toast.error("Failed to load mailboxes");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleConnect() {
    try {
      const { authorization_url } = await api.mailboxConnect.connect();
      window.location.href = authorization_url;
    } catch {
      toast.error("Could not start Gmail connection");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Manage your connected mailboxes
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={handleConnect}>
            <Plus className="mr-2 h-3 w-3" />
            Connect Mailbox
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader>
                <div className="h-5 w-40 rounded bg-muted" />
                <div className="h-4 w-24 rounded bg-muted" />
              </CardHeader>
              <CardContent>
                <div className="h-4 w-full rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : mailboxes.length === 0 ? (
        <div className="space-y-4">
          <WelcomeCard />
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Mail className="h-10 w-10 text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">
                No mailboxes connected yet
              </p>
              <Button onClick={handleConnect}>
                <Plus className="mr-2 h-4 w-4" />
                Connect your first mailbox
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {mailboxes.map((mb) => {
            const mode = modeConfig[mb.activation_mode];
            const ModeIcon = mode.icon;
            return (
              <Link key={mb.id} href={`/mailbox/${mb.id}`}>
                <Card className="transition-colors hover:border-primary/30 cursor-pointer">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base truncate">
                        {mb.gmail_email}
                      </CardTitle>
                      <Badge variant={mode.variant} className="ml-2 shrink-0">
                        <ModeIcon className="mr-1 h-3 w-3" />
                        {mode.label}
                      </Badge>
                    </div>
                    <CardDescription>
                      {mb.is_connected ? "Connected" : "Disconnected"}
                      {mb.gmail_watch_expiration &&
                        ` · Watch expires ${new Date(mb.gmail_watch_expiration).toLocaleDateString()}`}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-2 text-xs">
                      <Badge variant={mb.brief_enabled ? "default" : "secondary"}>
                        Briefs {mb.brief_enabled ? "on" : "off"}
                      </Badge>
                      <Badge variant={mb.draft_enabled ? "default" : "secondary"}>
                        Drafts {mb.draft_enabled ? "on" : "off"}
                      </Badge>
                      <Badge variant={mb.auto_archive_enabled ? "default" : "secondary"}>
                        Archive {mb.auto_archive_enabled ? "on" : "off"}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
