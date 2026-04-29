"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArchiveRestore,
  ArrowRightLeft,
  FileText,
  Undo2,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
  Clock,
  MessageSquare,
  Activity as ActivityIcon,
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
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  api,
  type ActivityEvent,
  type ActivityStats,
  type MailboxSummary,
  type MutationSummary,
  type TriageDecisionSummary,
  type TriageOutcome,
} from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { ListSkeleton } from "@/components/ui/page-skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { useQueryFilter } from "@/lib/use-query-filter";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const TRIAGE_OUTCOMES: { value: TriageOutcome; label: string }[] = [
  { value: "inbox_keep", label: "Inbox keep" },
  { value: "brief_only", label: "Brief only" },
  { value: "draft_candidate", label: "Draft candidate" },
  { value: "protected", label: "Protected" },
  { value: "manual_review", label: "Manual review" },
];

const outcomeVariant: Record<TriageOutcome, "default" | "secondary" | "outline"> = {
  inbox_keep: "default",
  brief_only: "secondary",
  draft_candidate: "default",
  protected: "outline",
  manual_review: "outline",
};

const mutationStatusVariant: Record<
  MutationSummary["status"],
  "default" | "secondary" | "outline" | "destructive"
> = {
  pending: "secondary",
  applied: "default",
  undone: "outline",
  undo_failed: "destructive",
  expired: "outline",
};

export default function ActivityPage() {
  return (
    <Suspense fallback={null}>
      <ActivityPageContent />
    </Suspense>
  );
}

function ActivityPageContent() {
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [mailboxFilter, setMailboxFilter] = useQueryFilter("mb", "all");

  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loadingOverview, setLoadingOverview] = useState(true);

  const [mutations, setMutations] = useState<MutationSummary[]>([]);
  const [loadingMutations, setLoadingMutations] = useState(true);
  const [undoingId, setUndoingId] = useState<string | null>(null);

  const [decisions, setDecisions] = useState<TriageDecisionSummary[]>([]);
  const [loadingDecisions, setLoadingDecisions] = useState(true);
  const [selectedDecision, setSelectedDecision] =
    useState<TriageDecisionSummary | null>(null);
  const [correctionOutcome, setCorrectionOutcome] = useState<TriageOutcome | "">("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [correcting, setCorrecting] = useState(false);

  useEffect(() => {
    api.mailboxes
      .list()
      .then(setMailboxes)
      .catch(() => toast.error("Failed to load mailboxes"));
  }, []);

  const mailboxQuery = mailboxFilter === "all" ? undefined : mailboxFilter;

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const [s, e] = await Promise.all([
        api.activity.stats({ mailbox_id: mailboxQuery, window_days: 7 }),
        api.activity.events({ mailbox_id: mailboxQuery, limit: 30 }),
      ]);
      setStats(s);
      setEvents(e.events);
    } catch {
      toast.error("Failed to load activity");
    } finally {
      setLoadingOverview(false);
    }
  }, [mailboxQuery]);

  const loadMutations = useCallback(async () => {
    setLoadingMutations(true);
    try {
      const res = await api.undo.listMutations({
        mailbox_id: mailboxQuery,
        limit: 25,
      });
      setMutations(res.mutations);
    } catch {
      toast.error("Failed to load mutations");
    } finally {
      setLoadingMutations(false);
    }
  }, [mailboxQuery]);

  const loadDecisions = useCallback(async () => {
    setLoadingDecisions(true);
    try {
      const res = await api.feedback.listTriageDecisions({
        mailbox_id: mailboxQuery,
        limit: 25,
      });
      setDecisions(res.decisions);
    } catch {
      toast.error("Failed to load triage decisions");
    } finally {
      setLoadingDecisions(false);
    }
  }, [mailboxQuery]);

  useEffect(() => {
    loadOverview();
    loadMutations();
    loadDecisions();
  }, [loadOverview, loadMutations, loadDecisions]);

  async function handleUndo(mutation: MutationSummary) {
    setUndoingId(mutation.id);
    try {
      const res = await api.undo.mutation({ undo_token: mutation.undo_token });
      toast.success(res.message);
      await Promise.all([loadMutations(), loadOverview()]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Undo failed";
      toast.error(msg);
    } finally {
      setUndoingId(null);
    }
  }

  async function handleCorrection() {
    if (!selectedDecision || !correctionOutcome) return;
    setCorrecting(true);
    try {
      const res = await api.feedback.triageCorrection({
        email_id: selectedDecision.email_id,
        correct_outcome: correctionOutcome,
        reason: correctionReason.trim() || undefined,
      });
      toast.success(res.message);
      setSelectedDecision(null);
      setCorrectionOutcome("");
      setCorrectionReason("");
      await loadDecisions();
    } catch {
      toast.error("Correction failed");
    } finally {
      setCorrecting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
          <p className="text-sm text-muted-foreground">
            Live view of system actions, mutations, and triage decisions
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadOverview();
              loadMutations();
              loadDecisions();
            }}
            disabled={loadingOverview || loadingMutations || loadingDecisions}
          >
            <RefreshCw
              className={`mr-2 h-3 w-3 ${
                loadingOverview || loadingMutations || loadingDecisions
                  ? "animate-spin"
                  : ""
              }`}
            />
            Refresh
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="mutations">
            Undo{mutations.length > 0 && ` (${mutations.length})`}
          </TabsTrigger>
          <TabsTrigger value="corrections">
            Corrections{decisions.length > 0 && ` (${decisions.length})`}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 mt-4">
          <div className="grid gap-4 sm:grid-cols-4">
            <StatCard
              icon={ArchiveRestore}
              label={`Triaged · ${stats?.window_days ?? 7}d`}
              value={stats?.emails_triaged ?? 0}
              loading={loadingOverview}
            />
            <StatCard
              icon={FileText}
              label="Drafts generated"
              value={stats?.drafts_generated ?? 0}
              loading={loadingOverview}
            />
            <StatCard
              icon={CheckCircle2}
              label="Mutations applied"
              value={stats?.mutations_applied ?? 0}
              loading={loadingOverview}
            />
            <StatCard
              icon={Undo2}
              label="Undos performed"
              value={stats?.undos_performed ?? 0}
              loading={loadingOverview}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ArrowRightLeft className="h-4 w-4" />
                Recent events
              </CardTitle>
              <CardDescription>
                Audit log of system actions, newest first
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingOverview ? (
                <ListSkeleton />
              ) : events.length === 0 ? (
                <EmptyState
                  icon={AlertCircle}
                  title="No activity yet"
                  description="Events appear here once the system triages, labels, archives, or drafts"
                />
              ) : (
                <ul className="divide-y">
                  {events.map((e) => (
                    <li key={e.id} className="flex items-start gap-3 py-3">
                      <Badge variant={severityVariant(e.severity)} className="mt-0.5 shrink-0">
                        {e.event_type}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm">
                          <span className="text-muted-foreground">actor:</span>{" "}
                          {e.actor}
                          {e.resource_type && (
                            <>
                              {" · "}
                              <span className="text-muted-foreground">
                                {e.resource_type}:
                              </span>{" "}
                              <span className="font-mono text-xs">
                                {truncate(e.resource_id, 18)}
                              </span>
                            </>
                          )}
                        </p>
                        {Object.keys(e.payload).length > 0 && (
                          <p className="text-xs text-muted-foreground truncate">
                            {summarizePayload(e.payload)}
                          </p>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatRelativeTime(e.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="mutations" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Undo2 className="h-4 w-4" />
                Recent mutations
              </CardTitle>
              <CardDescription>
                System-initiated archive and label changes. Click Undo to reverse
                within the 7-day window.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingMutations ? (
                <ListSkeleton />
              ) : mutations.length === 0 ? (
                <EmptyState
                  icon={ActivityIcon}
                  title="No mutations recorded"
                  description="Archive and label actions appear here once the system is in observe or auto mode"
                />
              ) : (
                <ul className="divide-y">
                  {mutations.map((m) => (
                    <li key={m.id} className="flex items-start gap-3 py-3">
                      <div className="flex flex-col gap-1 shrink-0 w-28">
                        <Badge variant={mutationStatusVariant[m.status]}>
                          {m.status}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {m.mutation_type}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm truncate font-medium">
                          {m.email_subject || "(no subject)"}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          from {m.email_from || "unknown"} · {m.reason_trace}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatRelativeTime(m.created_at)} · undo expires{" "}
                          {new Date(m.undo_expires_at).toLocaleDateString()}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={m.status !== "applied" || undoingId === m.id}
                        onClick={() => handleUndo(m)}
                      >
                        {undoingId === m.id ? "Undoing..." : "Undo"}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="corrections" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent triage decisions</CardTitle>
              <CardDescription>
                Select a decision to correct. Corrections update memories and
                improve future triage.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingDecisions ? (
                <ListSkeleton />
              ) : decisions.length === 0 ? (
                <EmptyState
                  icon={ActivityIcon}
                  title="No triage decisions yet"
                  description="Decisions appear here once emails are ingested and classified"
                />
              ) : (
                <ul className="divide-y">
                  {decisions.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDecision(d);
                          setCorrectionOutcome("");
                          setCorrectionReason("");
                        }}
                        className={`flex w-full items-start gap-3 py-3 text-left hover:bg-muted/40 transition-colors px-2 rounded ${
                          selectedDecision?.id === d.id ? "bg-muted/60" : ""
                        }`}
                      >
                        <Badge
                          variant={outcomeVariant[d.outcome]}
                          className="shrink-0 mt-0.5"
                        >
                          {d.outcome.replace("_", " ")}
                        </Badge>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm truncate font-medium">
                            {d.email_subject || "(no subject)"}
                          </p>
                          <p className="text-xs text-muted-foreground truncate">
                            from {d.email_from || "unknown"} · confidence{" "}
                            {(d.confidence * 100).toFixed(0)}% · {d.method}
                            {d.rule_matched && ` · ${d.rule_matched}`}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-1 shrink-0">
                          <span className="text-xs text-muted-foreground">
                            {formatRelativeTime(d.created_at)}
                          </span>
                          {d.corrected_by_user && (
                            <Badge variant="outline" className="text-xs">
                              corrected
                            </Badge>
                          )}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {selectedDecision && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Correct decision</CardTitle>
                <CardDescription>
                  {selectedDecision.email_subject || "(no subject)"} — currently{" "}
                  <span className="font-medium">
                    {selectedDecision.outcome.replace("_", " ")}
                  </span>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {TRIAGE_OUTCOMES.filter(
                    (o) => o.value !== selectedDecision.outcome,
                  ).map((o) => (
                    <Badge
                      key={o.value}
                      variant={
                        correctionOutcome === o.value ? "default" : "outline"
                      }
                      className="cursor-pointer"
                      onClick={() => setCorrectionOutcome(o.value)}
                    >
                      {o.label}
                    </Badge>
                  ))}
                </div>
                <Input
                  placeholder="Reason (optional)"
                  value={correctionReason}
                  onChange={(e) => setCorrectionReason(e.target.value)}
                />
                <div className="flex gap-2 flex-wrap">
                  <Button
                    size="sm"
                    onClick={handleCorrection}
                    disabled={!correctionOutcome || correcting}
                  >
                    {correcting ? "Submitting..." : "Submit correction"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    render={
                      <Link
                        href={`/assistant?prefill=${encodeURIComponent(
                          buildDiscussPrefill(selectedDecision),
                        )}&scope=${selectedDecision.mailbox_id}`}
                      />
                    }
                  >
                    <MessageSquare className="mr-1 h-3 w-3" />
                    Discuss in chat
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelectedDecision(null)}
                    disabled={correcting}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}


function severityVariant(
  severity: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (severity === "critical") return "destructive";
  if (severity === "warn") return "secondary";
  return "outline";
}

function truncate(s: string | null, n: number): string {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n)}...` : s;
}

function buildDiscussPrefill(d: TriageDecisionSummary): string {
  const sender = d.email_from || "this sender";
  const subject = d.email_subject || "(no subject)";
  return (
    `I want to discuss the triage decision on "${subject}" from ${sender}. ` +
    `It was classified as ${d.outcome.replace("_", " ")} with ` +
    `${(d.confidence * 100).toFixed(0)}% confidence. What should the rule be?`
  );
}

function summarizePayload(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).slice(0, 3);
  return entries
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" · ");
}
