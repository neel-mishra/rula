import Link from "next/link";
import { CheckCircle2, Clock, Archive, BookOpen, Inbox } from "lucide-react";
import type { Priority } from "@/types";

const config: Record<Priority | "all", { icon: React.ElementType; title: string; desc: React.ReactNode }> = {
  urgent:  { icon: CheckCircle2, title: "No urgent messages",      desc: "Nothing needs immediate attention." },
  normal:  { icon: CheckCircle2, title: "All caught up",           desc: "No messages needing a reply right now." },
  brief:   { icon: BookOpen,     title: "Check your brief",        desc: <><Link href="/brief" className="text-brand underline">View today's brief</Link> for low-priority threads.</> },
  archive: { icon: Archive,      title: "Nothing archived yet.",   desc: "Messages you archive will appear here." },
  all:     { icon: Inbox,        title: "Inbox is empty.",         desc: "No messages to show." },
};

export function InboxEmpty({ tab }: { tab: Priority | "all" }) {
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
