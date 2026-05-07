"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { DraftCard } from "./DraftCard";
import { DraftsEmpty } from "./DraftsEmpty";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, Tab } from "@/components/ui/tabs";
import { Tag } from "@/components/ui/tag";
import { Skeleton } from "@/components/ui/skeleton";
import type { DraftStatus } from "@/types";

type TabValue = DraftStatus | "all";

const TABS: Array<{ label: string; value: TabValue }> = [
  { label: "All",      value: "all" },
  { label: "Pending",  value: "pending" },
  { label: "Approved", value: "accepted" },
  { label: "Rejected", value: "rejected" },
];

export function DraftQueue() {
  const [activeTab, setActiveTab] = useState<TabValue>("pending");

  const { data, isLoading, error } = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api.drafts.list(),
    refetchInterval: 30_000,
  });

  const pendingCount = data?.items.filter((d) => d.status === "pending").length ?? 0;

  const filtered =
    activeTab === "all"
      ? (data?.items ?? [])
      : (data?.items ?? []).filter((d) => d.status === activeTab);

  const counts: Record<TabValue, number> = {
    all:      data?.items.length ?? 0,
    pending:  data?.items.filter((d) => d.status === "pending").length ?? 0,
    accepted: data?.items.filter((d) => d.status === "accepted").length ?? 0,
    rejected: data?.items.filter((d) => d.status === "rejected").length ?? 0,
    edited:   data?.items.filter((d) => d.status === "edited").length ?? 0,
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Drafts"
        sub="AI-written replies for your approval"
        right={
          pendingCount > 0 ? (
            <Tag tone="warn">{pendingCount} pending</Tag>
          ) : undefined
        }
      />

      <Tabs className="px-6">
        {TABS.map(({ label, value }) => (
          <Tab
            key={value}
            active={activeTab === value}
            count={counts[value]}
            countVariant={value === "pending" ? "warn" : "default"}
            onClick={() => setActiveTab(value)}
          >
            {label}
          </Tab>
        ))}
      </Tabs>

      <div className="flex-1 overflow-y-auto scroll-pretty">
        <div className="max-w-2xl mx-auto px-4 py-6">
          {isLoading && (
            <div className="flex flex-col gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="rounded-xl border border-line overflow-hidden">
                  <Skeleton className="h-1.5 w-full rounded-none" />
                  <div className="p-6 flex flex-col gap-3">
                    <Skeleton className="h-5 w-48" />
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-24 w-full rounded-lg" />
                    <div className="flex gap-2">
                      <Skeleton className="h-8 w-40 rounded-md" />
                      <Skeleton className="h-8 w-28 rounded-md" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && (
            <p className="text-center text-sm text-err py-8">Failed to load drafts.</p>
          )}

          {!isLoading && !error && filtered.length === 0 && (
            <DraftsEmpty tab={activeTab} />
          )}

          {filtered.map((draft) => (
            <DraftCard key={draft.id} draft={draft} />
          ))}
        </div>
      </div>
    </div>
  );
}
