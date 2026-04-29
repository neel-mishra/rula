"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  Globe,
  Inbox,
  Pencil,
  RefreshCw,
  Trash2,
  X,
  Check,
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
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
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
  type MailboxSummary,
  type Memory,
  type MemoryScope,
  type MemoryTypeValue,
} from "@/lib/api";
import { useQueryFilter } from "@/lib/use-query-filter";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const TYPE_OPTIONS: { value: MemoryTypeValue | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "policy", label: "Policy" },
  { value: "profile", label: "Profile" },
  { value: "style", label: "Style" },
  { value: "sender", label: "Sender" },
];

const SCOPE_OPTIONS: { value: MemoryScope | "all"; label: string }[] = [
  { value: "all", label: "All scopes" },
  { value: "user_global", label: "User global" },
  { value: "mailbox_specific", label: "Mailbox-specific" },
];

const ACTIVE_OPTIONS = [
  { value: "all", label: "Active + inactive" },
  { value: "true", label: "Active only" },
  { value: "false", label: "Inactive only" },
];

const typeVariant: Record<
  MemoryTypeValue,
  "default" | "secondary" | "outline"
> = {
  policy: "default",
  profile: "secondary",
  style: "outline",
  sender: "outline",
};

export default function MemoriesPage() {
  return (
    <Suspense fallback={null}>
      <MemoriesPageContent />
    </Suspense>
  );
}

function MemoriesPageContent() {
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  const [mailboxFilter, setMailboxFilter] = useQueryFilter("mb", "all");
  const [scopeFilter, setScopeFilter] = useQueryFilter("scope", "all");
  const [typeFilter, setTypeFilter] = useQueryFilter("type", "all");
  const [activeFilter, setActiveFilter] = useQueryFilter("active", "all");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    api.mailboxes
      .list()
      .then(setMailboxes)
      .catch(() => toast.error("Failed to load mailboxes"));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.memories.list({
        mailbox_id: mailboxFilter === "all" ? undefined : mailboxFilter,
        scope:
          scopeFilter === "all"
            ? undefined
            : (scopeFilter as MemoryScope),
        memory_type:
          typeFilter === "all"
            ? undefined
            : (typeFilter as MemoryTypeValue),
        is_active:
          activeFilter === "all" ? undefined : activeFilter === "true",
        limit: 100,
      });
      setMemories(res.memories);
      setTotal(res.total);
    } catch {
      toast.error("Failed to load memories");
    } finally {
      setLoading(false);
    }
  }, [mailboxFilter, scopeFilter, typeFilter, activeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const mailboxEmailMap = useMemo(
    () => Object.fromEntries(mailboxes.map((m) => [m.id, m.gmail_email])),
    [mailboxes],
  );

  function startEdit(m: Memory) {
    setEditingId(m.id);
    setEditContent(m.content);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditContent("");
  }

  async function saveEdit(m: Memory) {
    if (!editContent.trim() || editContent === m.content) {
      cancelEdit();
      return;
    }
    setSavingId(m.id);
    try {
      const updated = await api.memories.update(m.id, {
        content: editContent.trim(),
      });
      setMemories((prev) =>
        prev.map((x) => (x.id === m.id ? updated : x)),
      );
      toast.success("Memory updated");
      cancelEdit();
    } catch {
      toast.error("Update failed");
    } finally {
      setSavingId(null);
    }
  }

  async function toggleActive(m: Memory, next: boolean) {
    setTogglingId(m.id);
    try {
      const updated = await api.memories.update(m.id, { is_active: next });
      setMemories((prev) =>
        prev.map((x) => (x.id === m.id ? updated : x)),
      );
      toast.success(next ? "Memory reactivated" : "Memory deactivated");
    } catch {
      toast.error("Toggle failed");
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(m: Memory) {
    setDeletingId(m.id);
    try {
      await api.memories.delete(m.id);
      setMemories((prev) => prev.filter((x) => x.id !== m.id));
      setTotal((t) => Math.max(0, t - 1));
      toast.success("Memory deleted");
    } catch {
      toast.error("Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  const activeCount = memories.filter((m) => m.is_active).length;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Memories</h1>
          <p className="text-sm text-muted-foreground">
            What the system has learned from your feedback and instructions
            {total > 0 && ` · ${activeCount}/${total} active`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw
            className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="pt-4 flex flex-wrap gap-2">
          <Select
            value={mailboxFilter}
            onValueChange={(v) => setMailboxFilter(v ?? "all")}
          >
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All mailboxes</SelectItem>
              {mailboxes.map((mb) => (
                <SelectItem key={mb.id} value={mb.id}>
                  {mb.gmail_email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={scopeFilter}
            onValueChange={(v) => setScopeFilter(v ?? "all")}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCOPE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={typeFilter}
            onValueChange={(v) => setTypeFilter(v ?? "all")}
          >
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={activeFilter}
            onValueChange={(v) => setActiveFilter(v ?? "all")}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACTIVE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader>
                <div className="h-5 w-2/3 bg-muted rounded" />
                <div className="h-4 w-1/3 bg-muted rounded" />
              </CardHeader>
            </Card>
          ))}
        </div>
      ) : memories.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <Brain className="h-10 w-10 text-muted-foreground mb-4" />
            <p className="font-medium">No memories yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Memories are learned when you give the assistant instructions or
              correct triage decisions. Try asking the assistant to remember a
              rule.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {memories.map((m) => (
            <Card
              key={m.id}
              className={m.is_active ? "" : "opacity-60"}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge variant={typeVariant[m.memory_type]}>
                        {m.memory_type}
                      </Badge>
                      <Badge variant="outline" className="gap-1">
                        {m.scope === "user_global" ? (
                          <>
                            <Globe className="h-3 w-3" />
                            global
                          </>
                        ) : (
                          <>
                            <Inbox className="h-3 w-3" />
                            {mailboxEmailMap[m.mailbox_id ?? ""] ||
                              "mailbox"}
                          </>
                        )}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        from {m.source}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        confidence {(m.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatRelativeTime(m.updated_at)}
                      </span>
                    </div>
                    {editingId === m.id ? (
                      <div className="space-y-2">
                        <Textarea
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          className="min-h-[72px]"
                          placeholder="Memory content"
                        />
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => saveEdit(m)}
                            disabled={savingId === m.id}
                          >
                            <Check className="mr-1 h-3 w-3" />
                            {savingId === m.id ? "Saving..." : "Save"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={cancelEdit}
                            disabled={savingId === m.id}
                          >
                            <X className="mr-1 h-3 w-3" />
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <CardTitle className="text-sm font-normal leading-relaxed">
                        {m.content}
                      </CardTitle>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Switch
                      checked={m.is_active}
                      onCheckedChange={(v) => toggleActive(m, v)}
                      disabled={togglingId === m.id}
                      aria-label="Active"
                    />
                    {editingId !== m.id && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => startEdit(m)}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                    )}
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={<Button variant="ghost" size="icon-sm" />}
                      >
                        <Trash2 className="h-3 w-3" />
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete memory?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This removes the memory permanently. The system
                            will no longer apply this rule. If you just want
                            to pause it, toggle the switch off instead.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDelete(m)}
                            disabled={deletingId === m.id}
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </CardHeader>
              {m.structured_data &&
                Object.keys(m.structured_data).length > 0 && (
                  <>
                    <Separator />
                    <CardContent className="py-3">
                      <StructuredDataView data={m.structured_data} />
                    </CardContent>
                  </>
                )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function StructuredDataView({ data }: { data: Record<string, unknown> }) {
  const [showRaw, setShowRaw] = useState(false);
  const entries = Object.entries(data);

  return (
    <div className="space-y-2">
      {showRaw ? (
        <pre className="font-mono text-xs text-muted-foreground break-all whitespace-pre-wrap bg-muted/40 rounded p-2">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {entries.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="break-all">{formatStructuredValue(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      <button
        type="button"
        className="text-[11px] text-muted-foreground hover:text-foreground hover:underline underline-offset-2"
        onClick={() => setShowRaw((s) => !s)}
      >
        {showRaw ? "Hide raw JSON" : "View raw JSON"}
      </button>
    </div>
  );
}

function formatStructuredValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map((x) => formatStructuredValue(x)).join(", ");
  return JSON.stringify(v);
}
