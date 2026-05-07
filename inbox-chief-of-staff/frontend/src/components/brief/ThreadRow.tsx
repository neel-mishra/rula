"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Tag } from "@/components/ui/tag";
import { cn } from "@/lib/utils";
import type { BriefThread } from "@/types";

interface ThreadRowProps {
  thread: BriefThread;
  onMarkRead: () => void;
  last?: boolean;
}

export function ThreadRow({ thread, onMarkRead, last }: ThreadRowProps) {
  const [markedRead, setMarkedRead] = useState(thread.read);

  const handleMarkRead = () => {
    setMarkedRead(true);
    onMarkRead();
  };

  return (
    <div className={cn("flex items-start gap-4 py-4", !last && "border-b border-line")}>
      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-semibold text-navy">{thread.sender}</p>
        <p className="text-[14px] text-ink-2 truncate">{thread.subject}</p>
        <p className="text-xs text-ink-3 line-clamp-2 mt-0.5">{thread.snippet}</p>
      </div>

      <div className="flex flex-col items-end gap-2 shrink-0">
        <span className="text-[11px] text-ink-3">{thread.timestamp}</span>
        <div className="flex items-center gap-1.5">
          {markedRead ? (
            <Tag tone="ok">✓ Read</Tag>
          ) : (
            <button
              onClick={handleMarkRead}
              className="text-xs text-brand hover:underline"
            >
              Mark read
            </button>
          )}
          <a
            href={`https://mail.google.com`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-ink-3 hover:text-brand transition-colors"
            aria-label="Open thread"
          >
            <ExternalLink size={12} />
          </a>
        </div>
      </div>
    </div>
  );
}
