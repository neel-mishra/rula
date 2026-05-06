"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { relativeTime, confidenceLabel, cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui-store";
import type { Message, Priority } from "@/types";

const PRIORITY_COLORS: Record<Priority, string> = {
  urgent: "bg-red-100 text-red-800",
  normal: "bg-blue-100 text-blue-800",
  brief: "bg-gray-100 text-gray-700",
  archive: "bg-gray-50 text-gray-500",
};

interface Props {
  message: Message;
}

export function MessageCard({ message }: Props) {
  const qc = useQueryClient();
  const { selectedMessageId, setSelectedMessage } = useUIStore();
  const isSelected = selectedMessageId === message.id;

  const override = useMutation({
    mutationFn: async (priority: Priority) => {
      await api.messages.overrideTriage(message.id, priority);
      // Also record as triage feedback for Gate 1 composite metric
      await api.feedback.triage(message.id, priority);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["messages"] }),
  });

  const triage = message.triage;

  return (
    <div
      onClick={() => setSelectedMessage(isSelected ? null : message.id)}
      className={cn(
        "border-b px-4 py-3 cursor-pointer transition-colors",
        isSelected ? "bg-blue-50" : "hover:bg-gray-50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-sm truncate">
              {message.senderName || message.senderEmail}
            </span>
            <span className="text-xs text-gray-400 shrink-0">
              {relativeTime(message.receivedAt)}
            </span>
          </div>
          <div className="text-sm font-medium text-gray-900 truncate">
            {message.subject}
          </div>
          <div className="text-xs text-gray-500 truncate mt-0.5">
            {message.bodyPreview}
          </div>
        </div>

        {triage && (
          <div className="flex flex-col items-end gap-1 shrink-0">
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-full font-medium",
                PRIORITY_COLORS[triage.priority],
              )}
            >
              {triage.priority}
            </span>
            <span className="text-xs text-gray-400">
              {confidenceLabel(triage.confidence)}
            </span>
          </div>
        )}
      </div>

      {triage?.rationale && (
        <div className="mt-2 text-xs text-gray-500 bg-gray-50 rounded p-2">
          <span className="font-medium">Why: </span>
          {triage.rationale}
        </div>
      )}

      {/* Triage override controls — only visible when card is selected */}
      {isSelected && triage && (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 mr-1">Move to:</span>
          {(["urgent", "normal", "brief", "archive"] as Priority[])
            .filter((p) => p !== triage.priority)
            .map((p) => (
              <button
                key={p}
                onClick={(e) => {
                  e.stopPropagation();
                  override.mutate(p);
                }}
                disabled={override.isPending}
                className={cn(
                  "text-xs px-2 py-0.5 rounded-full border font-medium transition-colors",
                  PRIORITY_COLORS[p],
                  "hover:opacity-80 disabled:opacity-50",
                )}
              >
                {p}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
