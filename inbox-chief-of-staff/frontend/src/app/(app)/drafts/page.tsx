import type { Metadata } from "next";
import { DraftQueue } from "@/components/drafts/DraftQueue";

export const metadata: Metadata = { title: "Drafts | Chief of Staff" };

export default function DraftsPage() {
  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b bg-white">
        <h1 className="text-lg font-semibold text-gray-900">Draft Review</h1>
        <p className="text-sm text-gray-500">AI-generated drafts awaiting your approval</p>
      </header>
      <div className="flex-1 overflow-y-auto">
        <DraftQueue />
      </div>
    </div>
  );
}
