"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Shield,
  Eye,
  Zap,
  Unplug,
  Sun,
  Sunset,
  Plus,
  X,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
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
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  api,
  type MailboxSummary,
  type Memory,
  type UpdateMailboxSettings,
} from "@/lib/api";
import { toast } from "sonner";

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => ({
  value: String(h),
  label: `${h.toString().padStart(2, "0")}:00`,
}));

export default function MailboxDetailPage() {
  const params = useParams();
  const router = useRouter();
  const mailboxId = params.id as string;

  const [mailbox, setMailbox] = useState<MailboxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [protectedMemories, setProtectedMemories] = useState<Memory[]>([]);
  const [protectedLoading, setProtectedLoading] = useState(true);
  const [newSender, setNewSender] = useState("");
  const [addingSender, setAddingSender] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const loadMailbox = useCallback(async () => {
    try {
      const data = await api.mailboxes.get(mailboxId);
      setMailbox(data);
    } catch {
      toast.error("Failed to load mailbox");
    } finally {
      setLoading(false);
    }
  }, [mailboxId]);

  const loadProtected = useCallback(async () => {
    setProtectedLoading(true);
    try {
      const res = await api.memories.list({
        mailbox_id: mailboxId,
        memory_type: "policy",
        limit: 100,
      });
      setProtectedMemories(
        res.memories.filter(
          (m) =>
            (m.structured_data as { rule?: string })?.rule === "always_inbox",
        ),
      );
    } catch {
      toast.error("Failed to load protected senders");
    } finally {
      setProtectedLoading(false);
    }
  }, [mailboxId]);

  useEffect(() => {
    loadMailbox();
    loadProtected();
  }, [loadMailbox, loadProtected]);

  async function updateSetting(update: UpdateMailboxSettings) {
    setSaving(true);
    try {
      await api.mailboxes.updateSettings(mailboxId, update);
      await loadMailbox();
      toast.success("Settings updated");
    } catch {
      toast.error("Failed to update settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    try {
      await api.mailboxConnect.disconnect(mailboxId);
      toast.success("Mailbox disconnected");
      router.push("/");
    } catch {
      toast.error("Failed to disconnect mailbox");
    }
  }

  async function addProtectedSender() {
    const target = newSender.trim().toLowerCase();
    if (!target) return;
    setAddingSender(true);
    try {
      const isDomain = !target.includes("@");
      await api.memories.create({
        mailbox_id: mailboxId,
        scope: "mailbox_specific",
        memory_type: "policy",
        content: `Always keep emails from ${target} in inbox`,
        structured_data: {
          rule: "always_inbox",
          targets: [target],
          source: "manual",
          target_type: isDomain ? "domain" : "address",
        },
        source: "manual",
        confidence: 1.0,
      });
      setNewSender("");
      await loadProtected();
      toast.success(`Protected ${target}`);
    } catch {
      toast.error("Failed to add protected sender");
    } finally {
      setAddingSender(false);
    }
  }

  async function removeProtectedSender(memory: Memory) {
    setRemovingId(memory.id);
    try {
      await api.memories.delete(memory.id);
      setProtectedMemories((prev) => prev.filter((m) => m.id !== memory.id));
      toast.success("Removed");
    } catch {
      toast.error("Remove failed");
    } finally {
      setRemovingId(null);
    }
  }

  if (loading || !mailbox) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-64 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const modeIcons = { shadow: Shield, observe: Eye, auto: Zap };
  const ModeIcon = modeIcons[mailbox.activation_mode];

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {mailbox.gmail_email}
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant={mailbox.is_connected ? "default" : "destructive"}>
              {mailbox.is_connected ? "Connected" : "Disconnected"}
            </Badge>
            <Badge variant="outline">
              <ModeIcon className="mr-1 h-3 w-3" />
              {mailbox.activation_mode}
            </Badge>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Activation Mode</CardTitle>
          <CardDescription>
            Controls how aggressively the system acts on your email.
            Shadow logs only. Observe logs and labels. Auto takes full action.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            value={mailbox.activation_mode}
            onValueChange={(v) =>
              v &&
              updateSetting({
                activation_mode: v as "shadow" | "observe" | "auto",
              })
            }
            disabled={saving}
          >
            <SelectTrigger className="w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="shadow">
                Shadow — log decisions only
              </SelectItem>
              <SelectItem value="observe">
                Observe — log + apply Gmail labels
              </SelectItem>
              <SelectItem value="auto">
                Auto — full automation (archive, draft, label)
              </SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Features</CardTitle>
          <CardDescription>
            Toggle individual capabilities for this mailbox
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="brief">Daily Briefs</Label>
              <p className="text-sm text-muted-foreground">
                Morning and afternoon email digests
              </p>
            </div>
            <Switch
              id="brief"
              checked={mailbox.brief_enabled}
              onCheckedChange={(v) => updateSetting({ brief_enabled: v })}
              disabled={saving}
            />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="draft">Draft Generation</Label>
              <p className="text-sm text-muted-foreground">
                Auto-generate reply drafts for actionable emails
              </p>
            </div>
            <Switch
              id="draft"
              checked={mailbox.draft_enabled}
              onCheckedChange={(v) => updateSetting({ draft_enabled: v })}
              disabled={saving}
            />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="archive">Auto Archive</Label>
              <p className="text-sm text-muted-foreground">
                Automatically archive low-priority emails
              </p>
            </div>
            <Switch
              id="archive"
              checked={mailbox.auto_archive_enabled}
              onCheckedChange={(v) =>
                updateSetting({ auto_archive_enabled: v })
              }
              disabled={saving}
            />
          </div>
        </CardContent>
      </Card>

      {mailbox.brief_enabled && (
        <Card>
          <CardHeader>
            <CardTitle>Brief schedule</CardTitle>
            <CardDescription>
              Local hours the morning and afternoon briefs are sent. Leave
              either blank to skip that window.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label className="flex items-center gap-1.5">
                <Sun className="h-3.5 w-3.5" />
                Morning
              </Label>
              <Select
                value={
                  mailbox.brief_morning_hour !== null
                    ? String(mailbox.brief_morning_hour)
                    : "none"
                }
                onValueChange={(v) =>
                  updateSetting({
                    brief_morning_hour:
                      v === "none" ? undefined : Number(v),
                  })
                }
                disabled={saving}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Disabled</SelectItem>
                  {HOUR_OPTIONS.slice(5, 12).map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="flex items-center gap-1.5">
                <Sunset className="h-3.5 w-3.5" />
                Afternoon
              </Label>
              <Select
                value={
                  mailbox.brief_afternoon_hour !== null
                    ? String(mailbox.brief_afternoon_hour)
                    : "none"
                }
                onValueChange={(v) =>
                  updateSetting({
                    brief_afternoon_hour:
                      v === "none" ? undefined : Number(v),
                  })
                }
                disabled={saving}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Disabled</SelectItem>
                  {HOUR_OPTIONS.slice(12, 20).map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            Protected senders
          </CardTitle>
          <CardDescription>
            Emails from these addresses or domains are always kept in the
            inbox — never archived or demoted to a brief. Highest precedence
            rule.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addProtectedSender();
            }}
            className="flex gap-2"
          >
            <Input
              value={newSender}
              onChange={(e) => setNewSender(e.target.value)}
              placeholder="boss@example.com or example.com"
              disabled={addingSender}
            />
            <Button
              type="submit"
              size="sm"
              disabled={!newSender.trim() || addingSender}
            >
              <Plus className="mr-1 h-3 w-3" />
              Add
            </Button>
          </form>

          {protectedLoading ? (
            <div className="space-y-1">
              {[0, 1].map((i) => (
                <div
                  key={i}
                  className="h-8 rounded bg-muted animate-pulse"
                />
              ))}
            </div>
          ) : protectedMemories.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">
              No protected senders yet. Add addresses or domains above, or
              correct a triage decision to &quot;protected&quot; to create
              one automatically.
            </p>
          ) : (
            <ul className="divide-y">
              {protectedMemories.map((m) => {
                const targets =
                  (m.structured_data as { targets?: string[] })?.targets ||
                  [];
                const target = targets[0] || m.content;
                const isDomain = !target.includes("@");
                return (
                  <li
                    key={m.id}
                    className="flex items-center justify-between py-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge variant="outline" className="text-[10px]">
                        {isDomain ? "domain" : "address"}
                      </Badge>
                      <span className="text-sm truncate">{target}</span>
                      {!m.is_active && (
                        <Badge
                          variant="secondary"
                          className="text-[10px]"
                        >
                          inactive
                        </Badge>
                      )}
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            disabled={removingId === m.id}
                            aria-label={`Remove ${target}`}
                          />
                        }
                      >
                        <X className="h-3 w-3" />
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            Remove protected sender?
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            Emails from{" "}
                            <span className="font-mono">{target}</span> will
                            no longer bypass triage automatically. You can
                            re-add it later.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => removeProtectedSender(m)}
                          >
                            Remove
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

      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="text-destructive">Danger Zone</CardTitle>
          <CardDescription>
            Disconnect this mailbox. All watches will be stopped and tokens
            revoked. Your email data will be retained for the configured
            retention period.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AlertDialog>
            <AlertDialogTrigger
              render={<Button variant="destructive" size="sm" />}
            >
              <Unplug className="mr-2 h-4 w-4" />
              Disconnect Mailbox
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Disconnect {mailbox.gmail_email}?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will stop all processing, revoke OAuth tokens, and remove
                  Gmail watch notifications. You can reconnect later.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDisconnect}>
                  Disconnect
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
    </div>
  );
}
