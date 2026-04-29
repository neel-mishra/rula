"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Archive,
  ArrowRightLeft,
  Clock,
  Eye,
  FileText,
  History,
  RefreshCw,
  ShieldAlert,
  Tag,
  Undo2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  api,
  type MailboxSummary,
  type TimelineItem,
  type TimelineKind,
} from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { ListSkeleton } from "@/components/ui/page-skeleton";
import { useQueryFilter } from "@/lib/use-query-filter";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const ALL_KINDS: TimelineKind[] = ["triage", "mutation", "draft", "audit"];

const kindMeta: Record<
  TimelineKind,
  { label: string; icon: LucideIcon; variant: "default" | "secondary" | "outline" }
> = {
  triage: { label: "Triage", icon: Eye, variant: "default" },
  mutation: { label: "Mutation", icon: ArrowRightLeft, variant: "secondary" },
  draft: { label: "Draft", icon: FileText, variant: "outline" },
  audit: { label: "Audit", icon: ShieldAlert, variant: "outline" },
};

function iconForItem(item: TimelineItem): LucideIcon {
  if (item.kind === "mutation") {
    const status = (item.extra?.status as string) || "";
    if (status === "undone") return Undo2;
    const headline = item.headline.toLowerCase();
    if (headline.startsWith("archive")) return Archive;
    if (headline.startsWith("label")) return Tag;
  }
  return kindMeta[item.kind].icon;
}

export default function TransparencyPage() {
  return (
    <Suspense fallback={null}>
      <TransparencyPageContent />
    </Suspense>
  );
}

function TransparencyPageContent() {
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [mailboxFilter, setMailboxFilter] = useQueryFilter("mb", "");
  const [kindFilter, setKindFilter] = useQueryFilter("kinds", "");
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    api.mailboxes
      .list()
      .then((mbs) => {
        setMailboxes(mbs);
        if (!mailboxFilter && mbs.length > 0) {
          setMailboxFilter(mbs[0].id);
        }
      })
      .catch(() => toast.error("Failed to load mailboxes"));
    // intentionally only run on mount; mailbox auto-pick fills in once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeKinds: TimelineKind[] = (kindFilter ? kindFilter.split(",") : [])
    .filter((k): k is TimelineKind => (ALL_KINDS as string[]).includes(k));

  const loadTimeline = useCallback(
    async (cursor?: string) => {
      if (!mailboxFilter) return;
      const setterLoading = cursor ? setLoadingMore : setLoading;
      setterLoading(true);
      try {
        const res = await api.activity.timeline({
          mailbox_id: mailboxFilter,
          limit: 50,
          before: cursor,
          kinds: activeKinds.length > 0 ? activeKinds : undefined,
        });
        setItems((prev) => (cursor ? [...prev, ...res.items] : res.items));
        setHasMore(res.has_more);
        setNextBefore(res.next_before);
      } catch {
        toast.error("Failed to load timeline");
      } finally {
        setterLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mailboxFilter, kindFilter],
  );

  useEffect(() => {
    setItems([]);
    setHasMore(false);
    setNextBefore(null);
    if (mailboxFilter) loadTimeline();
  }, [mailboxFilter, kindFilter, loadTimeline]);

  function toggleKind(kind: TimelineKind) {
    const set = new Set(activeKinds);
    if (set.has(kind)) set.delete(kind);
    else set.add(kind);
    setKindFilter(set.size === 0 ? "" : Array.from(set).join(","));
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Transparency</h1>
          <p className="text-sm text-muted-foreground">
            Per-mailbox chronological feed of every system action, fused from
            triage decisions, mutations, drafts, and audit events.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={mailboxFilter || ""}
            onValueChange={(v) => setMailboxFilter(v || "")}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Pick a mailbox" />
            </SelectTrigger>
            <SelectContent>
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
            onClick={() => loadTimeline()}
            disabled={loading || !mailboxFilter}
          >
            <RefreshCw
              className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="space-y-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="h-4 w-4" />
            Timeline
          </CardTitle>
          <CardDescription>
            Filter by event kind. Empty = show all kinds.
          </CardDescription>
          <div className="flex flex-wrap gap-2 pt-1">
            {ALL_KINDS.map((kind) => {
              const meta = kindMeta[kind];
              const Icon = meta.icon;
              const active = activeKinds.includes(kind);
              return (
                <Badge
                  key={kind}
                  variant={active ? meta.variant : "outline"}
                  className="cursor-pointer gap-1"
                  onClick={() => toggleKind(kind)}
                >
                  <Icon className="h-3 w-3" />
                  {meta.label}
                </Badge>
              );
            })}
          </div>
        </CardHeader>
        <CardContent>
          {!mailboxFilter ? (
            <EmptyState
              icon={AlertCircle}
              title="Pick a mailbox"
              description="Transparency is per-mailbox by design — pick one above to begin."
            />
          ) : loading ? (
            <ListSkeleton />
          ) : items.length === 0 ? (
            <EmptyState
              icon={History}
              title="No events yet"
              description="Once the system triages, mutates, or drafts in this mailbox, events appear here in real time."
            />
          ) : (
            <ul className="divide-y">
              {items.map((item) => (
                <TimelineRow key={item.id} item={item} />
              ))}
            </ul>
          )}

          {hasMore && (
            <div className="pt-4 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => nextBefore && loadTimeline(nextBefore)}
                disabled={loadingMore || !nextBefore}
              >
                {loadingMore ? "Loading…" : "Load older"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TimelineRow({ item }: { item: TimelineItem }) {
  const meta = kindMeta[item.kind];
  const Icon = iconForItem(item);
  return (
    <li className="flex items-start gap-3 py-3">
      <div className="flex flex-col items-center pt-0.5 shrink-0">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={meta.variant} className="shrink-0 text-xs">
            {meta.label}
          </Badge>
          <p className="text-sm font-medium truncate">{item.headline}</p>
        </div>
        {item.related_email_subject && (
          <p className="text-xs text-muted-foreground truncate">
            <span className="text-muted-foreground">re:</span>{" "}
            {item.related_email_subject}
            {item.related_email_from && (
              <>
                {" · "}
                <span className="text-muted-foreground">from</span>{" "}
                {item.related_email_from}
              </>
            )}
          </p>
        )}
        {item.detail && (
          <p className="text-xs text-muted-foreground">{item.detail}</p>
        )}
      </div>
      <span className="text-xs text-muted-foreground shrink-0 flex items-center gap-1">
        <Clock className="h-3 w-3" />
        {formatRelativeTime(item.timestamp)}
      </span>
    </li>
  );
}
