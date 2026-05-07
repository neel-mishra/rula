"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api-client";
import type { Priority } from "@/types";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    api.auth.me()
      .then(() => setAuthChecked(true))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
        } else {
          // Network error or timeout — show the app shell anyway
          setAuthChecked(true);
        }
      })
      .finally(() => clearTimeout(timeout));
  }, []);

  const { data: messagesData } = useQuery({
    queryKey: ["messages", "urgent" as Priority],
    queryFn: () => api.messages.list({ priority: "urgent" }),
    enabled: authChecked,
    staleTime: 1000 * 60,
  });

  const { data: draftsData } = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api.drafts.list(),
    enabled: authChecked,
    staleTime: 1000 * 30,
  });

  const urgentCount = messagesData?.total;
  const draftsCount = draftsData?.items.filter((d) => d.status === "pending").length;

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar urgentCount={urgentCount} draftsCount={draftsCount} />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
