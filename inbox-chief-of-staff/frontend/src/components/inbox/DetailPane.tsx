"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, ExternalLink, Pencil } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { useUIStore } from "@/store/ui-store";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { PriorityBadge } from "@/components/ui/priority-badge";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Skeleton } from "@/components/ui/skeleton";
import { relativeTime } from "@/lib/utils";

interface DetailPaneProps {
  messageId: string;
  onClose: () => void;
}

export function DetailPane({ messageId, onClose }: DetailPaneProps) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const { openCorrectionModal } = useUIStore();

  const { data: message, isLoading, isError, refetch } = useQuery({
    queryKey: ["messages", messageId],
    queryFn: () => api.messages.get(messageId),
  });

  const approve = useMutation({
    mutationFn: () => api.messages.overrideTriage(messageId, message!.triage!.priority),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["messages"] });
      toast({ type: "success", title: "Triage approved" });
    },
    onError: () => toast({ type: "error", title: "Failed to approve" }),
  });

  return (
    <div className="w-[420px] shrink-0 h-full flex flex-col border-l border-line bg-surface animate-slideIn overflow-hidden">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface border-b border-line px-4 py-3 flex items-start gap-3">
        <button
          onClick={onClose}
          className="mt-0.5 text-ink-3 hover:text-navy transition-colors shrink-0"
          aria-label="Close"
        >
          <X size={16} />
        </button>
        {isLoading ? (
          <div className="flex-1 flex flex-col gap-1.5">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-48" />
          </div>
        ) : message ? (
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-navy text-sm truncate">
              {message.senderName || message.senderEmail}
            </h3>
            <p className="text-xs text-ink-3 truncate">
              {message.senderEmail} · {relativeTime(message.receivedAt)}
            </p>
          </div>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto scroll-pretty">
        {isLoading && (
          <div className="p-4 flex flex-col gap-4">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        )}

        {isError && (
          <div className="p-8 text-center">
            <p className="text-sm text-err mb-3">Failed to load message.</p>
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Retry</Button>
          </div>
        )}

        {message && (
          <div className="flex flex-col gap-4 p-4">
            {/* AI Decision block */}
            {message.triage && (
              <div className="rounded-xl bg-surface-muted border border-line p-4">
                <Eyebrow className="mb-3">AI Decision</Eyebrow>
                <div className="flex items-center gap-2 mb-2">
                  <PriorityBadge priority={message.triage.priority} size="lg" />
                </div>
                <ConfidenceMeter value={message.triage.confidence} className="mb-3" />
                <p className="text-sm text-navy leading-relaxed">{message.triage.rationale}</p>
                {message.triage.modelVersion && (
                  <p className="text-[11px] text-ink-3 mt-2">{message.triage.modelVersion}</p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                size="sm"
                onClick={() => approve.mutate()}
                disabled={approve.isPending}
              >
                Approve triage
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => openCorrectionModal(message.id)}
              >
                Override
              </Button>
              <a
                href={`https://mail.google.com/mail/u/0/#inbox/${message.gmailThreadId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-brand hover:underline ml-auto"
              >
                Open in Gmail
                <ExternalLink size={12} />
              </a>
            </div>

            {/* Draft callout */}
            {message.hasDraft && (
              <div className="rounded-xl border border-warn bg-warn-soft p-4 flex items-start gap-3">
                <Pencil size={16} className="text-warn mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-navy">Draft ready for this thread</p>
                  <a href="/drafts" className="text-xs text-brand hover:underline">
                    Review in Drafts →
                  </a>
                </div>
              </div>
            )}

            {/* Email subject */}
            <div>
              <Eyebrow className="mb-1.5">Subject</Eyebrow>
              <p className="text-sm font-medium text-navy">{message.subject}</p>
            </div>

            {/* Email body */}
            <div>
              <Eyebrow className="mb-1.5">Preview</Eyebrow>
              <p className="text-sm text-navy leading-relaxed whitespace-pre-wrap">
                {message.body ?? message.bodyPreview}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
