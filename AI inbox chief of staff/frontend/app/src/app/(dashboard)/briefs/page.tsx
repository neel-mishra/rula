"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  FileText,
  Inbox,
  Mail,
  RefreshCw,
  Sun,
  Sunset,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, type Brief, type MailboxSummary } from "@/lib/api";
import { useQueryFilter } from "@/lib/use-query-filter";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const windowMeta: Record<string, { icon: React.ElementType; label: string }> = {
  morning: { icon: Sun, label: "Morning" },
  afternoon: { icon: Sunset, label: "Afternoon" },
};

const statusVariant: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  delivered: "default",
  pending: "secondary",
  generating: "secondary",
  skipped: "outline",
  failed: "destructive",
  delivery_failed: "destructive",
};

const BRIEFS_PAGE_SIZE = 20;

export default function BriefsPage() {
  return (
    <Suspense fallback={null}>
      <BriefsPageContent />
    </Suspense>
  );
}

function BriefsPageContent() {
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [mailboxFilter, setMailboxFilter] = useQueryFilter("mb", "all");
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    api.mailboxes
      .list()
      .then(setMailboxes)
      .catch(() => toast.error("Failed to load mailboxes"));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.briefs.list({
        mailbox_id: mailboxFilter === "all" ? undefined : mailboxFilter,
        limit: BRIEFS_PAGE_SIZE,
      });
      setBriefs(res.briefs);
      setTotal(res.total);
    } catch {
      toast.error("Failed to load briefs");
    } finally {
      setLoading(false);
    }
  }, [mailboxFilter]);

  const loadMore = useCallback(async () => {
    if (loadingMore || briefs.length >= total) return;
    setLoadingMore(true);
    try {
      const res = await api.briefs.list({
        mailbox_id: mailboxFilter === "all" ? undefined : mailboxFilter,
        limit: BRIEFS_PAGE_SIZE,
        offset: briefs.length,
      });
      setBriefs((prev) => [...prev, ...res.briefs]);
      setTotal(res.total);
    } catch {
      toast.error("Failed to load more briefs");
    } finally {
      setLoadingMore(false);
    }
  }, [briefs.length, loadingMore, mailboxFilter, total]);

  useEffect(() => {
    load();
  }, [load]);

  const mailboxEmailMap = Object.fromEntries(
    mailboxes.map((m) => [m.id, m.gmail_email]),
  );

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Briefs</h1>
          <p className="text-sm text-muted-foreground">
            History of delivered morning and afternoon briefs
            {total > 0 && ` · ${total} total`}
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
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw
              className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

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
      ) : briefs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <FileText className="h-10 w-10 text-muted-foreground mb-4" />
            <p className="font-medium">No briefs yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Briefs are generated and delivered twice daily for mailboxes with
              briefs enabled. They appear here once the first window fires.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {briefs.map((b) => {
            const winMeta = windowMeta[b.window] || {
              icon: Mail,
              label: b.window,
            };
            const WinIcon = winMeta.icon;
            const mailboxEmail = mailboxEmailMap[b.mailbox_id];
            return (
              <Link key={b.id} href={`/briefs/${b.id}`} className="block">
                <Card className="transition-colors hover:border-primary/30 cursor-pointer">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-base truncate">
                          {b.subject_line || `${winMeta.label} brief`}
                        </CardTitle>
                        <CardDescription className="flex items-center gap-2 mt-1">
                          <WinIcon className="h-3 w-3" />
                          {winMeta.label}
                          {mailboxEmail && (
                            <>
                              <span>·</span>
                              <span className="truncate">{mailboxEmail}</span>
                            </>
                          )}
                          <span>·</span>
                          <Inbox className="h-3 w-3" />
                          {b.item_count ?? b.items.length} items
                        </CardDescription>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <Badge
                          variant={statusVariant[b.status] || "outline"}
                        >
                          {b.status}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {formatRelativeTime(b.delivered_at || b.created_at)}
                        </span>
                      </div>
                    </div>
                  </CardHeader>
                </Card>
              </Link>
            );
          })}
          {briefs.length < total && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore
                  ? "Loading..."
                  : `Load more (${total - briefs.length} remaining)`}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
