import { ExternalLink } from "lucide-react";
import { Tag } from "@/components/ui/tag";
import { cn } from "@/lib/utils";
import type { ActionItem } from "@/types";

interface ActionRowProps {
  action: ActionItem & { done?: boolean };
  onToggle: () => void;
}

const urgentDues = new Set(["today", "friday", "tomorrow"]);

export function ActionRow({ action, onToggle }: ActionRowProps) {
  const dueLabel = action.due?.toLowerCase() ?? "";
  const dueTone = urgentDues.has(dueLabel) ? "warn" : "soft";

  return (
    <div className="flex items-start gap-3 py-3 border-b border-line last:border-b-0">
      <button
        onClick={onToggle}
        className={cn(
          "mt-0.5 w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center transition-colors",
          action.done
            ? "bg-brand border-brand"
            : "border-line hover:border-brand",
        )}
        aria-label={action.done ? "Mark incomplete" : "Mark done"}
      >
        {action.done && (
          <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
            <path d="M1 4l3 3 5-6" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>

      <div className="flex-1 min-w-0">
        <p className={cn("text-[14px] font-medium text-navy", action.done && "line-through text-ink-3")}>
          {action.text}
        </p>
        {(action.from || action.due) && (
          <p className="text-xs text-ink-3 mt-0.5 flex items-center gap-1.5 flex-wrap">
            {action.from && <span>From: {action.from}</span>}
            {action.due && (
              <Tag tone={dueTone} className="text-[10px]">{action.due}</Tag>
            )}
          </p>
        )}
      </div>

      {action.messageId && (
        <a
          href={`/inbox`}
          className="text-ink-3 hover:text-brand transition-colors shrink-0"
          aria-label="Open message"
        >
          <ExternalLink size={13} />
        </a>
      )}
    </div>
  );
}
