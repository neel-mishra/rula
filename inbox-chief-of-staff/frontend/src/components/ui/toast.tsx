"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Toast {
  id: string;
  type: "success" | "error" | "info";
  title: string;
  msg?: string;
}

interface ToastContextValue {
  toast: (opts: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const stripeMap: Record<Toast["type"], string> = {
  success: "border-l-4 border-l-ok",
  error:   "border-l-4 border-l-err",
  info:    "border-l-4 border-l-brand",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((opts: Omit<Toast, "id">) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...opts, id }]);
    setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "animate-toastIn pointer-events-auto flex max-w-sm gap-3 rounded-xl bg-surface border border-line shadow-lg px-4 py-3",
              stripeMap[t.type],
            )}
          >
            <div className="flex flex-1 flex-col gap-0.5">
              <p className="text-sm font-semibold text-navy">{t.title}</p>
              {t.msg && <p className="text-xs text-ink-2">{t.msg}</p>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 text-ink-3 hover:text-navy transition-colors"
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
