"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { relativeTime } from "@/lib/utils";
import type { Brief } from "@/types";

function BriefCard({ brief }: { brief: Brief }) {
  return (
    <div className="border rounded-lg p-5 mb-4 bg-white shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          {brief.timeWindow === "morning" ? "☀️ Morning Brief" : "🌤 Afternoon Brief"}
        </span>
        <span className="text-xs text-gray-400">{relativeTime(brief.createdAt)}</span>
      </div>

      {/* Summary */}
      <div className="prose prose-sm max-w-none text-gray-800 mb-4 whitespace-pre-wrap">
        {brief.summaryMarkdown}
      </div>

      {/* Action items */}
      {brief.actionItems.length > 0 && (
        <div className="border-t pt-3">
          <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Action Items</div>
          <ul className="space-y-1">
            {brief.actionItems.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <input type="checkbox" className="mt-0.5 shrink-0" readOnly />
                <span>{typeof item === "string" ? item : item.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="text-xs text-gray-400 mt-3">
        {brief.messageIds.length} emails summarized
      </div>
    </div>
  );
}

export function BriefReader() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["briefs"],
    queryFn: () => api.briefs.list(),
    refetchInterval: 5 * 60 * 1000, // refresh every 5 min
  });

  if (isLoading) {
    return <div className="p-8 text-center text-gray-500">Loading your brief...</div>;
  }

  if (error) {
    return <div className="p-8 text-center text-red-500">Failed to load brief.</div>;
  }

  if (!data?.items.length) {
    return (
      <div className="p-8 text-center text-gray-400">
        <div className="text-2xl mb-2">📭</div>
        <div className="text-sm">No brief available yet. Check back later.</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-4">
      {data.items.map((brief) => (
        <BriefCard key={brief.id} brief={brief} />
      ))}
    </div>
  );
}
