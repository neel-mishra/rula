"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseDraftOptions {
  debounceMs?: number;
}

interface UseDraftResult<T> {
  draft: T;
  setDraft: (next: T) => void;
  patchDraft: (patch: Partial<T>) => void;
  clearDraft: () => void;
  hasRestored: boolean;
}

export function useDraft<T extends object>(
  key: string,
  initial: T,
  options: UseDraftOptions = {},
): UseDraftResult<T> {
  const { debounceMs = 500 } = options;
  const [draft, setDraftState] = useState<T>(initial);
  const [hasRestored, setHasRestored] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      setHasRestored(true);
      return;
    }
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        setDraftState({ ...initial, ...(JSON.parse(raw) as Partial<T>) });
      }
    } catch {
      // ignore
    }
    setHasRestored(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const persist = useCallback(
    (next: T) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        try {
          localStorage.setItem(key, JSON.stringify(next));
        } catch {
          // quota exceeded, ignore
        }
      }, debounceMs);
    },
    [key, debounceMs],
  );

  const setDraft = useCallback(
    (next: T) => {
      setDraftState(next);
      persist(next);
    },
    [persist],
  );

  const patchDraft = useCallback(
    (patch: Partial<T>) => {
      setDraftState((prev) => {
        const next = { ...prev, ...patch };
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const clearDraft = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore
    }
    setDraftState(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { draft, setDraft, patchDraft, clearDraft, hasRestored };
}
