import type { RoleId } from "./copy";

export type ToolPage = "prospecting" | "map";

/**
 * Builds the Streamlit app URL with query params consumed by `rula-gtm-agent/app.py`
 * (`_apply_landing_query_params`): `role` = `admin` | `user` | `viewer`, `page` =
 * `prospecting` | `map` (maps to Prospecting / MAP Review in the Navigate sidebar).
 */
export function buildStreamlitAppUrl(
  baseUrl: string | undefined,
  role: RoleId,
  page: ToolPage
): string {
  const trimmed = (baseUrl || "").trim();
  const devFallback =
    typeof process !== "undefined" && process.env.NODE_ENV === "development"
      ? "http://localhost:8501"
      : "";
  const raw = trimmed || devFallback;
  if (!raw) {
    return "#";
  }
  const base = raw.replace(/\/+$/, "");
  const u = new URL(base);
  u.searchParams.set("role", role);
  u.searchParams.set("page", page === "prospecting" ? "prospecting" : "map");
  return u.toString();
}

export const STORAGE_KEY_ROLE = "rula-landing-role";
