import type { Metadata } from "next";
import { BriefReader } from "@/components/brief/BriefReader";

export const metadata: Metadata = { title: "Brief | Chief of Staff" };

export default function BriefPage() {
  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b bg-white">
        <h1 className="text-lg font-semibold text-gray-900">Daily Brief</h1>
        <p className="text-sm text-gray-500">Non-urgent email digest</p>
      </header>
      <div className="flex-1 overflow-y-auto">
        <BriefReader />
      </div>
    </div>
  );
}
