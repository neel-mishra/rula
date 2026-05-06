"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { MessageCard } from "./MessageCard";
import { useUIStore } from "@/store/ui-store";
import type { Priority } from "@/types";

const FILTER_TABS: Array<{ label: string; value: Priority | "all" }> = [
  { label: "All", value: "all" },
  { label: "Urgent", value: "urgent" },
  { label: "Normal", value: "normal" },
  { label: "Brief", value: "brief" },
  { label: "Archive", value: "archive" },
];

export function TriageFeed() {
  const { activeInboxFilter, setInboxFilter } = useUIStore();

  const { data, isLoading, error } = useQuery({
    queryKey: ["messages", activeInboxFilter],
    queryFn: () =>
      api.messages.list({
        priority: activeInboxFilter === "all" ? undefined : activeInboxFilter,
      }),
    refetchInterval: 60_000,
  });

  return (
    <div className="flex flex-col h-full">
      {/* Filter tabs */}
      <div className="flex gap-2 p-4 border-b bg-white sticky top-0 z-10">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setInboxFilter(tab.value)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              activeInboxFilter === tab.value
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto bg-white">
        {isLoading && (
          <div className="p-8 text-center text-gray-500">
            Loading messages...
          </div>
        )}
        {error && (
          <div className="p-8 text-center text-red-500">
            Failed to load messages.
          </div>
        )}
        {data?.items.map((message) => (
          <MessageCard key={message.id} message={message} />
        ))}
        {!isLoading && !error && data?.items.length === 0 && (
          <div className="p-8 text-center text-gray-500">
            No messages in this category.
          </div>
        )}
      </div>
    </div>
  );
}
