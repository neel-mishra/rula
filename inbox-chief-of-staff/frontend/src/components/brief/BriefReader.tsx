"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock, Link as LinkIcon } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/layout/PageHeader";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Tag } from "@/components/ui/tag";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionRow } from "./ActionRow";
import { ThreadRow } from "./ThreadRow";
import type { ActionItem } from "@/types";
import Link from "next/link";

export function BriefReader() {
  const { toast } = useToast();
  const [doneIds, setDoneIds] = useState<Set<number>>(new Set());

  const { data, isLoading, error } = useQuery({
    queryKey: ["briefs", "current"],
    queryFn: () => api.briefs.list(),
    refetchInterval: 5 * 60 * 1000,
  });

  const brief = data?.items[0];

  const markAllRead = useMutation({
    mutationFn: async () => {
      await new Promise((r) => setTimeout(r, 600));
    },
    onSuccess: () => toast({ type: "success", title: "Brief marked as read" }),
  });

  const toggleDone = (idx: number) => {
    setDoneIds((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Daily Brief"
        sub="Your AI-curated inbox summary"
        right={
          brief ? (
            <Tag tone="soft">{brief.timeWindow === "morning" ? "Morning" : "Afternoon"}</Tag>
          ) : undefined
        }
      />

      <div className="flex-1 overflow-y-auto scroll-pretty">
        <div className="max-w-2xl mx-auto px-4 py-6 flex flex-col gap-6">
          {isLoading && (
            <>
              <Skeleton className="h-40 w-full rounded-2xl" />
              <Skeleton className="h-48 w-full rounded-2xl" />
              <Skeleton className="h-36 w-full rounded-2xl" />
            </>
          )}

          {error && (
            <p className="text-center text-sm text-err py-8">Failed to load brief.</p>
          )}

          {!isLoading && !error && !brief && (
            <div className="flex flex-col items-center py-20 gap-4 text-center">
              <div className="w-12 h-12 rounded-full bg-brand-soft flex items-center justify-center">
                <Clock size={22} className="text-brand" />
              </div>
              <div>
                <p className="font-semibold text-navy text-sm">Brief generates at 8 AM</p>
                <p className="text-sm text-ink-2 mt-1">Check back after your first daily brief is ready.</p>
              </div>
            </div>
          )}

          {brief && (
            <>
              {/* Summary section */}
              <section className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
                <Eyebrow className="mb-3">Summary</Eyebrow>
                <p className="text-[11px] text-ink-3 mb-3">{brief.messageIds.length} emails summarized</p>
                <p className="text-base text-navy leading-relaxed">{brief.summaryMarkdown}</p>
                <div className="mt-4 rounded-lg bg-accent-soft border border-brand/20 px-3 py-2.5">
                  <p className="text-xs text-ink-2">
                    Covering your {brief.timeWindow} — {new Date(brief.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </section>

              {/* Action items */}
              {brief.actionItems.length > 0 && (
                <section className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <Eyebrow>Action Items</Eyebrow>
                    <Tag tone="warn">{brief.actionItems.length}</Tag>
                  </div>
                  <div>
                    {brief.actionItems.map((item: ActionItem, i: number) => (
                      <ActionRow
                        key={i}
                        action={{ ...item, done: doneIds.has(i) }}
                        onToggle={() => toggleDone(i)}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Bottom actions */}
              <div className="flex items-center gap-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => markAllRead.mutate()}
                  disabled={markAllRead.isPending}
                >
                  {markAllRead.isPending ? "Marking…" : "Mark entire brief as read"}
                </Button>
                <Link href="/inbox" className="flex items-center gap-1.5 text-sm text-brand hover:underline">
                  View in Inbox
                  <LinkIcon size={12} />
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
