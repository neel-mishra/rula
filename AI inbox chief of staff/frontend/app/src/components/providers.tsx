"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import { Toaster } from "@/components/ui/sonner";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      {children}
      <Toaster position="bottom-right" />
    </AuthProvider>
  );
}
