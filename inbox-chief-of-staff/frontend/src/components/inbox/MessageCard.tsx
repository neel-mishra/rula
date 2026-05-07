"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { relativeTime, cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui-store";
import { useToast } from "@/components/ui/toast";
import { Avatar } from "@/components/ui/avatar";
import { PriorityBadge } from "@/components/ui/priority-badge";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Eyebrow } from "@/components/ui/eyebrow";
import type { Message, Priority } from "@/types";

const PRIORITIES: Priority[] = ["urgent", "normal", "brief", "archive"];

interface Props {
  message: Message;
}

export function MessageCard({ message }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { selectedMessageId, setSelectedMessage, openCorrectionModal } = useUIStore();
  const isSelected = selectedMessageId === message.id;
  const triage = message.triage;
  const senderName = message.senderName || message.senderEmail;

  const override = useMutation({
    mutationFn: async (priority: Priority) => {
      await api.messages.overrideTriage(message.id, priority);
      await api.feedback.triage(message.id, priority);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["messages"] });
      toast({ type: "success", title: "Override saved" });
    },
    onError: () => toast({ type: "error", title: "Failed to save override" }),
  });

  return (
    <div
      onClick={() => setSelectedMessage(isSelected ? null : message.id)}
      className={cn(
        "flex items-start gap-3 px-4 py-3.5 border-b border-line cursor-pointer transition-colors",
        isSelected
          ? "bg-brand-soft border-l-2 border-l-brand"
          : "bg-surface hover:bg-lavender",
      )}
    >
      <Avatar name={senderName} size="md" className="mt-0.5 shrink-0" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-[14px] font-semibold text-navy truncate">{senderName}</span>
          <span className="text-[11px] text-ink-3 shrink-0 ml-auto">
            {relativeTime(message.receivedAt)}
          </span>
        </div>
        <p className="text-[14px] font-medium text-navy truncate">{message.subject}</p>
        <p className="text-xs text-ink-3 truncate mt-0.5">{message.bodyPreview}</p>

        {triage?.rationale && (
          <div className="mt-2 rounded-lg bg-surface-muted px-3 py-2">
            <Eyebrow className="inline mr-1.5">Why</Eyebrow>
            <span className="text-xs text-ink-2">{triage.rationale}</span>
          </div>
        )}

        {isSelected && triage && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-ink-3">Move to:</span>
            {PRIORITIES.filter((p) => p !== triage.priority).map((p) => (
              <button
                key={p}
                onClick={(e) => { e.stopPropagation(); override.mutate(p); }}
                disabled={override.isPending}
                className="disabled:opacity-50"
              >
                <PriorityBadge priority={p} size="sm" />
              </button>
            ))}
            <button
              onClick={(e) => { e.stopPropagation(); openCorrectionModal(message.id); }}
              className="text-xs text-brand hover:underline ml-auto"
            >
              Wrong priority?
            </button>
          </div>
        )}
      </div>

      {triage && (
        <div className="flex flex-col items-end gap-1.5 shrink-0 ml-2">
          <PriorityBadge priority={triage.priority} size="sm" />
          <ConfidenceMeter value={triage.confidence} className="w-20" />
        </div>
      )}
    </div>
  );
}
