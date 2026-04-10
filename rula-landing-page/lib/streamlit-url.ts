import type { RoleId } from "./copy";

export type ToolPage = "prospecting" | "map";

export function buildStreamlitAppUrl(
  baseUrl: string | undefined,
  role: RoleId,
  page: ToolPage
): string {
  const raw = (baseUrl || "").trim() || "http://localhost:8501";
  const base = raw.replace(/\/+$/, "");
  const u = new URL(base);
  u.searchParams.set("role", role);
  u.searchParams.set("page", page === "prospecting" ? "prospecting" : "map");
  return u.toString();
}

export const STORAGE_KEY_ROLE = "rula-landing-role";
