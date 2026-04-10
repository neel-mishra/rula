"use client";

import { useEffect, useMemo, useState } from "react";
import { roles, site, type RoleId } from "@/lib/copy";
import { tools } from "@/lib/copy";
import { RoleCard } from "@/components/RoleCard";
import { ToolSelectorCard } from "@/components/ToolSelectorCard";
import { StepIndicator } from "@/components/StepIndicator";
import { STORAGE_KEY_ROLE, buildStreamlitAppUrl } from "@/lib/streamlit-url";

function loadStoredRole(): RoleId {
  if (typeof window === "undefined") return "user";
  try {
    const v = window.localStorage.getItem(STORAGE_KEY_ROLE);
    if (v === "admin" || v === "user" || v === "viewer") return v;
  } catch {
    /* ignore */
  }
  return "user";
}

function roleLabel(id: RoleId): string {
  return roles.find((r) => r.id === id)?.label ?? id;
}

export function LandingShell() {
  const envBase = (process.env.NEXT_PUBLIC_STREAMLIT_BASE_URL ?? "").trim();
  /** Local dev works without `.env.local` when Streamlit runs on 8501. Production must set the env on Vercel. */
  const base =
    envBase ||
    (process.env.NODE_ENV === "development" ? "http://localhost:8501" : "");
  const [role, setRole] = useState<RoleId>("user");
  const [hydrated, setHydrated] = useState(false);
  /** UX: highlight step 2 after role is chosen (or restored from localStorage). */
  const [journeyStep, setJourneyStep] = useState<0 | 1>(0);

  useEffect(() => {
    const stored = loadStoredRole();
    setRole(stored);
    try {
      if (typeof window !== "undefined" && window.localStorage.getItem(STORAGE_KEY_ROLE)) {
        setJourneyStep(1);
      }
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY_ROLE, role);
    } catch {
      /* ignore */
    }
  }, [role, hydrated]);

  const onRoleSelect = (id: RoleId) => {
    setRole(id);
    setJourneyStep(1);
  };

  const prospectingUrl = useMemo(
    () => buildStreamlitAppUrl(base, role, "prospecting"),
    [base, role]
  );
  const mapUrl = useMemo(() => buildStreamlitAppUrl(base, role, "map"), [base, role]);

  const missingBase = !base;

  return (
    <div className="min-h-screen bg-[var(--rula-canvas)] dark:bg-slate-950">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(37,99,235,0.12),transparent)] dark:bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(37,99,235,0.18),transparent)]" />

      <header className="relative border-b border-slate-200/80 bg-white/90 backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/90">
        <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-10 sm:px-6 lg:px-8">
          <p className="text-xs font-semibold uppercase tracking-widest text-[var(--rula-blue)]">
            {site.eyebrow}
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--rula-navy)] dark:text-white sm:text-4xl sm:leading-tight">
            {site.title}
          </h1>
          <p className="max-w-3xl text-lg text-slate-600 dark:text-slate-300">{site.tagline}</p>
          <div className="pt-2">
            <StepIndicator steps={[...site.journeySteps]} activeIndex={journeyStep} />
          </div>
        </div>
      </header>

      <main className="relative mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="max-w-3xl text-base leading-relaxed text-slate-700 dark:text-slate-300">
          {site.heroLead}
        </p>

        <section className="mt-12" aria-labelledby="role-heading">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2
                id="role-heading"
                className="text-2xl font-semibold tracking-tight text-[var(--rula-navy)] dark:text-white"
              >
                Your role
              </h2>
              <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
                In local and dev, this mirrors the Streamlit sidebar. In production the app locks effective access—see
                the agent README.
              </p>
            </div>
          </div>
          <fieldset className="mt-6" aria-labelledby="role-heading">
            <legend className="sr-only">Select your demo role</legend>
            <div className="grid gap-4 sm:grid-cols-3">
              {roles.map((r) => (
                <RoleCard
                  key={r.id}
                  id={r.id}
                  label={r.label}
                  description={r.description}
                  selected={role === r.id}
                  onSelect={onRoleSelect}
                />
              ))}
            </div>
          </fieldset>
        </section>

        <section className="mt-14" aria-labelledby="tools-heading">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2
                id="tools-heading"
                className="text-2xl font-semibold tracking-tight text-[var(--rula-navy)] dark:text-white"
              >
                Choose a tool
              </h2>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                Deep-links include your role and starting page. You can switch pages inside Streamlit anytime.
              </p>
            </div>
            {hydrated && (
              <p
                className="mt-2 inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-[var(--rula-navy)] shadow-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 sm:mt-0"
                aria-live="polite"
              >
                Launching as <span className="ml-1 font-semibold text-[var(--rula-blue)]">{roleLabel(role)}</span>
              </p>
            )}
          </div>
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            {tools.map((t) => {
              const href = t.id === "prospecting" ? prospectingUrl : mapUrl;
              return (
                <ToolSelectorCard
                  key={t.id}
                  title={t.title}
                  description={t.description}
                  cta={t.cta}
                  href={href}
                  accent={t.id === "map" ? "emerald" : "blue"}
                  disabled={missingBase}
                  disabledReason={
                    missingBase
                      ? "Set NEXT_PUBLIC_STREAMLIT_BASE_URL (e.g. in .env.local) to your Streamlit app URL, then restart the dev server."
                      : undefined
                  }
                />
              );
            })}
          </div>
        </section>

        {missingBase && (
          <div
            className="mt-8 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
            role="status"
          >
            <strong className="font-semibold">Local setup:</strong> add{" "}
            <code className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs dark:bg-amber-900/80 dark:text-amber-50">
              .env.local
            </code>{" "}
            with{" "}
            <code className="font-mono text-xs">NEXT_PUBLIC_STREAMLIT_BASE_URL=http://localhost:8501</code> and run{" "}
            <code className="font-mono text-xs">streamlit run app.py</code> from <code className="font-mono text-xs">rula-gtm-agent</code>.
          </div>
        )}

        <p className="mt-12 max-w-3xl border-t border-slate-200 pt-8 text-xs leading-relaxed text-slate-500 dark:border-slate-700 dark:text-slate-400">
          {site.footerNote}
        </p>
      </main>
    </div>
  );
}
