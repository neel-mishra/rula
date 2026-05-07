"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/modal";
import { PriorityBadge } from "@/components/ui/priority-badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api-client";
import type { Message, Priority } from "@/types";

const PRIORITIES: Priority[] = ["urgent", "normal", "brief", "archive"];

interface CorrectionModalProps {
  message: Message | null;
  onClose: () => void;
  onSave: (priority: Priority, reason?: string) => void;
}

export function CorrectionModal({ message, onClose, onSave }: CorrectionModalProps) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Priority>(
    message?.triage?.priority ?? "normal",
  );
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => api.feedback.triage(message!.id, selected),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["messages"] });
      toast({ type: "success", title: "Correction saved", msg: `Marked as ${selected}` });
      onSave(selected, reason || undefined);
    },
    onError: () => toast({ type: "error", title: "Failed to save correction" }),
  });

  if (!message) return null;

  return (
    <Modal open title="Correct AI priority" onClose={onClose}>
      {message.triage && (
        <div className="mb-4 p-3 rounded-lg bg-surface-muted border border-line">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-3 mb-2">Current</p>
          <div className="flex items-center gap-2">
            <PriorityBadge priority={message.triage.priority} />
            <p className="text-xs text-ink-2 line-clamp-2">{message.triage.rationale}</p>
          </div>
        </div>
      )}

      <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-3 mb-2">Change to</p>
      <div className="grid grid-cols-2 gap-2 mb-4">
        {PRIORITIES.map((p) => (
          <button
            key={p}
            onClick={() => setSelected(p)}
            className={`rounded-xl border-2 px-4 py-3 flex items-center gap-2 transition-colors text-left ${
              selected === p ? "border-brand bg-brand-soft" : "border-line hover:bg-lavender"
            }`}
          >
            <PriorityBadge priority={p} size="sm" />
            <span className="text-xs text-navy capitalize">{p}</span>
          </button>
        ))}
      </div>

      <Field
        as="textarea"
        label="Reason (optional)"
        placeholder="Why should this be re-classified?"
        value={reason}
        onChange={(e) => setReason(e.target.value.slice(0, 280))}
        rows={3}
        className="mb-1"
      />
      <p className="text-[11px] text-ink-3 text-right mb-4">{reason.length}/280</p>

      <div className="flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button
          size="sm"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          Save correction
        </Button>
      </div>
    </Modal>
  );
}
