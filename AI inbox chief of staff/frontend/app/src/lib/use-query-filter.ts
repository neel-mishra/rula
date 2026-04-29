"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Hook that syncs a single filter key to the URL query string.
 *
 * Returns `[value, setValue]` — same shape as `useState`, but the value is
 * sourced from and persisted in the URL so reloading or sharing a link
 * preserves the state.
 *
 * Caller must sit inside a `<Suspense>` boundary: Next 16 requires it
 * whenever `useSearchParams` is used inside a client page.
 */
export function useQueryFilter(
  key: string,
  defaultValue: string,
): [string, (next: string) => void] {
  const pathname = usePathname();
  const router = useRouter();
  const params = useSearchParams();

  const value = params.get(key) ?? defaultValue;

  const setValue = useCallback(
    (next: string) => {
      const updated = new URLSearchParams(params.toString());
      if (!next || next === defaultValue) {
        updated.delete(key);
      } else {
        updated.set(key, next);
      }
      const qs = updated.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [defaultValue, key, params, pathname, router],
  );

  return [value, setValue];
}
