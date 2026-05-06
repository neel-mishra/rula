"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { relativeTime, cn } from "@/lib/utils";
import type { Draft, DraftStatus } from "@/types";

type FeedbackRating = "helpful" | "unhelpful" | null;

interface Props {
  draft: Draft;
}

export function DraftCard({ draft }: Props) {
  const qc = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editedBody, setEditedBody] = useState(draft.body);
  const [feedbackGiven, setFeedbackGiven] = useState<FeedbackRating>(null);

  const submitFeedback = useMutation({
    mutationFn: (rating: "helpful" | "unhelpful") =>
      api.feedback.draft(draft.id, rating),
    onSuccess: (_data, rating) => setFeedbackGiven(rating),
  });

  const updateDraft = useMutation({
    mutationFn: (payload: { status?: DraftStatus; body?: string }) =>
      api.drafts.update(draft.id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["drafts"] });
      setIsEditing(false);
    },
  });

  const handleApprove = () =>
    updateDraft.mutate({ status: "accepted", body: isEditing ? editedBody : undefined });

  const handleReject = () => updateDraft.mutate({ status: "rejected" });

  const handleSaveEdit = () =>
    updateDraft.mutate({ body: editedBody, status: "edited" });

  return (
    <div className="border rounded-lg p-4 mb-3 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-sm font-medium text-gray-900">{draft.subjectLine}</div>
          {draft.originalMessage && (
            <div className="text-xs text-gray-500 mt-0.5">
              Re: {draft.originalMessage.senderName} · {relativeTime(draft.createdAt)}
            </div>
          )}
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800 font-medium shrink-0">
          AI Draft · {Math.round(draft.confidence * 100)}% confidence
        </span>
      </div>

      {/* Draft body */}
      {isEditing ? (
        <textarea
          className="w-full border rounded p-2 text-sm text-gray-800 min-h-[120px] focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={editedBody}
          onChange={(e) => setEditedBody(e.target.value)}
        />
      ) : (
        <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded p-3">
          {draft.body}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-3">
        <button
          onClick={handleApprove}
          disabled={updateDraft.isPending}
          className="px-3 py-1.5 text-sm font-medium bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
        >
          {isEditing ? "Save & Approve" : "Approve"}
        </button>

        {!isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="px-3 py-1.5 text-sm font-medium border border-gray-300 text-gray-700 rounded hover:bg-gray-50"
          >
            Edit
          </button>
        )}

        {isEditing && (
          <button
            onClick={() => { setIsEditing(false); setEditedBody(draft.body); }}
            className="px-3 py-1.5 text-sm font-medium border border-gray-300 text-gray-700 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
        )}

        <button
          onClick={handleReject}
          disabled={updateDraft.isPending}
          className="px-3 py-1.5 text-sm font-medium text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50 ml-auto"
        >
          Reject
        </button>
      </div>

      {/* Draft quality feedback */}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
        <span className="text-xs text-gray-400">Was this draft helpful?</span>
        {feedbackGiven ? (
          <span className="text-xs text-gray-500 italic">Thanks for the feedback</span>
        ) : (
          <>
            <button
              onClick={() => submitFeedback.mutate("helpful")}
              disabled={submitFeedback.isPending}
              title="Helpful"
              className={cn(
                "p-1 rounded hover:bg-green-50 transition-colors disabled:opacity-50",
                "text-gray-400 hover:text-green-600",
              )}
            >
              👍
            </button>
            <button
              onClick={() => submitFeedback.mutate("unhelpful")}
              disabled={submitFeedback.isPending}
              title="Not helpful"
              className={cn(
                "p-1 rounded hover:bg-red-50 transition-colors disabled:opacity-50",
                "text-gray-400 hover:text-red-600",
              )}
            >
              👎
            </button>
          </>
        )}
      </div>

      {/* No-send notice */}
      <p className="text-xs text-gray-400 mt-2">
        Approving saves this to your Gmail Drafts — you send it yourself.
      </p>
    </div>
  );
}
