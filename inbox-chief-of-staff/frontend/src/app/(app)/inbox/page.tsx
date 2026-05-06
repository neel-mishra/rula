import type { Metadata } from "next";
import { TriageFeed } from "@/components/inbox/TriageFeed";

export const metadata: Metadata = { title: "Inbox | Chief of Staff" };

export default function InboxPage() {
  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b bg-white">
        <h1 className="text-lg font-semibold text-gray-900">Inbox</h1>
        <p className="text-sm text-gray-500">AI-triaged messages</p>
      </header>
      <div className="flex-1 overflow-hidden">
        <TriageFeed />
      </div>
    </div>
  );
}
