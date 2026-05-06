"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api-client";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    api.auth.me().then(() => {
      setAuthChecked(true);
    }).catch((err) => {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "http://localhost:8000/auth/login";
      } else {
        // Non-401 error (network down, 500, etc.) — still let the app render
        setAuthChecked(true);
      }
    });
  }, []);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
