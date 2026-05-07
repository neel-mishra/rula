"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api-client";
import { relativeTime, cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Tag } from "@/components/ui/tag";
import { Eyebrow } from "@/components/ui/eyebrow";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Field } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import type { Draft, DraftStatus } from "@/types";

const statusStripe: Record<DraftStatus, string> = {
  pending:  "bg-brand",
  accepted: "bg-ok",
  rejected: "bg-err",
  edited:   "bg-warn",
};

type FeedbackRating = "helpful" | "unhelpful" | null;

interface Props {
  draft: Draft;
}

export function DraftCard({ draft }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [isEditing, setIsEditing] = useState(false);
  const [editedBody, setEditedBody] = useState(draft.body);
  const [originalExpanded, setOriginalExpanded] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [feedbackGiven, setFeedbackGiven] = useState<FeedbackRating>(null);

  const isDirty = editedBody !== draft.body;

  const submitFeedback = useMutation({
    mutationFn: (rating: "helpful" | "unhelpful") => api.feedback.draft(draft.id, rating),
    onSuccess: (_data, rating) => setFeedbackGiven(rating),
  });

  const updateDraft = useMutation({
    mutationFn: (payload: { status?: DraftStatus; body?: string }) =>
      api.drafts.update(draft.id, payload),
    onSuccess: (_data, payload) => {
      qc.invalidateQueries({ queryKey: ["drafts"] });
      if (payload.status === "accepted") {
        toast({ type: "success", title: "Draft saved to Gmail Drafts" });
      }
      if (payload.status === "rejected") {
        toast({ type: "info", title: "Draft rejected" });
        setRejectOpen(false);
      }
      setIsEditing(false);
    },
    onError: () => toast({ type: "error", title: "Action failed — try again" }),
  });

  const handleApprove = () =>
    updateDraft.mutate({ status: "accepted", body: isEditing ? editedBody : undefined });

  const handleConfirmReject = () =>
    updateDraft.mutate({ status: "rejected" });

  return (
    <div className="rounded-xl border border-line bg-surface shadow-sm overflow-hidden mb-4">
      {/* Status stripe */}
      <div className={cn("h-1.5 w-full", statusStripe[draft.status])} />

      <div className="p-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold text-navy truncate">{draft.subjectLine}</p>
            {draft.originalMessage && (
              <p className="text-sm text-ink-2 mt-0.5">
                Re: {draft.originalMessage.senderName} · {relativeTime(draft.createdAt)}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <Tag tone="warn">AI Draft</Tag>
            <ConfidenceMeter value={draft.confidence} className="w-24" />
          </div>
        </div>

        {/* Original message collapsible */}
        {draft.originalMessage && (
          <div className="mb-4">
            <button
              onClick={() => setOriginalExpanded(!originalExpanded)}
              className="flex items-center gap-1.5 text-xs text-ink-3 hover:text-navy transition-colors"
            >
              {originalExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              Original message
            </button>
            {originalExpanded && (
              <div className="mt-2 bg-surface-muted rounded-lg border border-line p-4 text-xs text-ink-2 whitespace-pre-wrap">
                {draft.originalMessage.bodyPreview}
              </div>
            )}
          </div>
        )}

        {/* Draft body */}
        {isEditing ? (
          <div className="relative">
            <Field
              as="textarea"
              value={editedBody}
              onChange={(e) => setEditedBody(e.target.value)}
              className="min-h-[160px]"
            />
            {isDirty && (
              <span className="absolute top-2 right-2">
                <Tag tone="warn">Edited</Tag>
              </span>
            )}
          </div>
        ) : (
          <div className="bg-surface-muted rounded-lg border border-line p-4 text-sm text-navy whitespace-pre-wrap">
            {draft.body}
          </div>
        )}

        {/* Rationale strip */}
        {draft.userFeedback && (
          <div className="mt-3 rounded-lg bg-accent-soft border border-brand/20 px-3 py-2.5">
            <Eyebrow className="mb-1">Why this draft?</Eyebrow>
            <p className="text-xs text-ink-2">{draft.userFeedback}</p>
          </div>
        )}

        {/* Actions */}
        <div className="mt-5 flex items-center gap-2 flex-wrap">
          <Button
            variant="success"
            size="sm"
            onClick={handleApprove}
            disabled={updateDraft.isPending}
          >
            {isEditing ? "Save & Approve" : "Approve → Save to Gmail Drafts"}
          </Button>

          {!isEditing ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsEditing(true)}
            >
              Edit then Approve
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setIsEditing(false); setEditedBody(draft.body); }}
            >
              Cancel edit
            </Button>
          )}

          <Button
            variant="danger-ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setRejectOpen(true)}
            disabled={updateDraft.isPending}
          >
            Reject
          </Button>
        </div>

        {/* Footer */}
        <div className="mt-4 pt-3 border-t border-line flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-3">Was this draft helpful?</span>
            {feedbackGiven ? (
              <span className="text-xs text-ink-3 italic">Thanks!</span>
            ) : (
              <>
                <button
                  onClick={() => submitFeedback.mutate("helpful")}
                  disabled={submitFeedback.isPending}
                  className="text-base hover:scale-110 transition-transform disabled:opacity-50"
                  title="Helpful"
                >
                  👍
                </button>
                <button
                  onClick={() => submitFeedback.mutate("unhelpful")}
                  disabled={submitFeedback.isPending}
                  className="text-base hover:scale-110 transition-transform disabled:opacity-50"
                  title="Not helpful"
                >
                  👎
                </button>
              </>
            )}
          </div>
          <p className="flex items-center gap-1 text-xs text-ink-3 italic">
            <AlertTriangle size={11} />
            Saves to Gmail Drafts — you send from Gmail
          </p>
        </div>
      </div>

      {/* Reject modal */}
      <Modal open={rejectOpen} onClose={() => setRejectOpen(false)} title="Reject draft">
        <p className="text-sm text-ink-2 mb-4">
          Let us know why (optional) — this helps improve future drafts.
        </p>
        <Field
          as="textarea"
          placeholder="This draft missed the point because…"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          rows={3}
          className="mb-4"
        />
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={() => setRejectOpen(false)}>Cancel</Button>
          <Button
            variant="danger"
            size="sm"
            onClick={handleConfirmReject}
            disabled={updateDraft.isPending}
          >
            Reject draft
          </Button>
        </div>
      </Modal>
    </div>
  );
}
