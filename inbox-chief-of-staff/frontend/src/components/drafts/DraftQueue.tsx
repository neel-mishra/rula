"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { DraftCard } from "./DraftCard";

export function DraftQueue() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api.drafts.list(),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return <div className="p-8 text-center text-gray-500">Loading drafts...</div>;
  }

  if (error) {
    return <div className="p-8 text-center text-red-500">Failed to load drafts.</div>;
  }

  const pending = data?.items.filter((d) => d.status === "pending") ?? [];

  if (pending.length === 0) {
    return (
      <div className="p-8 text-center text-gray-400">
        <div className="text-2xl mb-2">✅</div>
        <div className="text-sm">No drafts waiting for review.</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-4">
      <div className="text-sm text-gray-500 mb-4">{pending.length} draft{pending.length !== 1 ? "s" : ""} pending review</div>
      {pending.map((draft) => (
        <DraftCard key={draft.id} draft={draft} />
      ))}
    </div>
  );
}
