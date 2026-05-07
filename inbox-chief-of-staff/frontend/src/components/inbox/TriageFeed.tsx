"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { MessageCard } from "./MessageCard";
import { DetailPane } from "./DetailPane";
import { CorrectionModal } from "./CorrectionModal";
import { InboxSkeleton } from "./InboxSkeleton";
import { InboxEmpty } from "./InboxEmpty";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, Tab } from "@/components/ui/tabs";
import { Field } from "@/components/ui/field";
import { useUIStore } from "@/store/ui-store";
import { relativeTime } from "@/lib/utils";
import type { Priority } from "@/types";

type TabValue = Priority | "all";

const TABS: Array<{ label: string; value: TabValue }> = [
  { label: "Urgent",  value: "urgent" },
  { label: "Normal",  value: "normal" },
  { label: "Brief",   value: "brief" },
  { label: "Archive", value: "archive" },
];

export function TriageFeed() {
  const { activeInboxFilter, setInboxFilter, selectedMessageId, setSelectedMessage, correctionModalMessageId, closeCorrectionModal } = useUIStore();
  const [search, setSearch] = useState("");

  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["messages", activeInboxFilter],
    queryFn: () =>
      api.messages.list({
        priority: activeInboxFilter === "all" ? undefined : activeInboxFilter,
      }),
    refetchInterval: 60_000,
  });

  const { data: allData } = useQuery({
    queryKey: ["messages", "all"],
    queryFn: () => api.messages.list({}),
    staleTime: 60_000,
  });

  const tabCounts: Record<TabValue, number | undefined> = {
    urgent:  allData?.items.filter((m) => m.triage?.priority === "urgent").length,
    normal:  allData?.items.filter((m) => m.triage?.priority === "normal").length,
    brief:   allData?.items.filter((m) => m.triage?.priority === "brief").length,
    archive: allData?.items.filter((m) => m.triage?.priority === "archive").length,
    all:     allData?.total,
  };

  const filtered = search.trim()
    ? data?.items.filter((m) => {
        const q = search.toLowerCase();
        return (
          (m.senderName || m.senderEmail).toLowerCase().includes(q) ||
          m.subject.toLowerCase().includes(q) ||
          m.bodyPreview.toLowerCase().includes(q)
        );
      })
    : data?.items;

  const lastSync = dataUpdatedAt ? relativeTime(new Date(dataUpdatedAt).toISOString()) : null;

  const correctionMessage = correctionModalMessageId
    ? (data?.items.find((m) => m.id === correctionModalMessageId) ?? null)
    : null;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Message list pane */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <PageHeader
          title="Inbox"
          sub="AI-triaged messages"
          right={
            lastSync && (
              <span className="flex items-center gap-1.5 text-xs text-ink-3">
                <RefreshCw size={11} />
                {lastSync}
              </span>
            )
          }
        />

        <Tabs className="px-4">
          {TABS.map(({ label, value }) => (
            <Tab
              key={value}
              active={activeInboxFilter === value}
              count={tabCounts[value]}
              countVariant={value === "urgent" ? "err" : value === "normal" ? "warn" : "default"}
              onClick={() => setInboxFilter(value)}
            >
              {label}
            </Tab>
          ))}
        </Tabs>

        <div className="px-4 py-2 border-b border-line bg-surface">
          <Field
            placeholder="Search sender, subject, or preview…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-sm py-1.5"
          />
        </div>

        <div className="flex-1 overflow-y-auto scroll-pretty bg-surface">
          {isLoading && <InboxSkeleton />}
          {error && (
            <div className="p-8 text-center text-sm text-err">
              Failed to load messages.
            </div>
          )}
          {!isLoading && !error && filtered?.length === 0 && (
            <InboxEmpty tab={activeInboxFilter} />
          )}
          {filtered?.map((message) => (
            <MessageCard key={message.id} message={message} />
          ))}
        </div>
      </div>

      {/* Detail pane */}
      {selectedMessageId && (
        <DetailPane
          messageId={selectedMessageId}
          onClose={() => setSelectedMessage(null)}
        />
      )}

      {/* Correction modal */}
      <CorrectionModal
        message={correctionMessage}
        onClose={closeCorrectionModal}
        onSave={closeCorrectionModal}
      />
    </div>
  );
}
