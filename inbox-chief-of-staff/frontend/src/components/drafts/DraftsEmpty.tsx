import { CheckCircle2, ThumbsUp, ThumbsDown, Inbox } from "lucide-react";
import type { DraftStatus } from "@/types";

const config: Record<DraftStatus | "all", { icon: React.ElementType; title: string; desc: string }> = {
  pending:  { icon: CheckCircle2, title: "All caught up",           desc: "No drafts are waiting for your review." },
  accepted: { icon: ThumbsUp,     title: "No approved drafts yet",  desc: "Drafts you approve will appear here." },
  rejected: { icon: ThumbsDown,   title: "No rejected drafts",      desc: "Rejected drafts will appear here." },
  edited:   { icon: CheckCircle2, title: "No edited drafts yet",    desc: "Drafts you've edited will appear here." },
  all:      { icon: Inbox,        title: "No drafts yet",           desc: "AI-written drafts will appear here once your inbox has replies." },
};

export function DraftsEmpty({ tab }: { tab: DraftStatus | "all" }) {
  const { icon: Icon, title, desc } = config[tab];
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center px-8">
      <div className="w-12 h-12 rounded-full bg-brand-soft flex items-center justify-center">
        <Icon size={22} className="text-brand" />
      </div>
      <div>
        <p className="font-semibold text-navy text-sm">{title}</p>
        <p className="text-sm text-ink-2 mt-1">{desc}</p>
      </div>
    </div>
  );
}
